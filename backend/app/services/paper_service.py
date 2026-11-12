"""论文管理服务 — 含语义级去重检测"""
import os, shutil
from pathlib import Path
from app.config import settings
from app.rag.chroma_client import get_collection, get_embedding_function
from app.rag.pdf_parser import parse_pdf, chunks_for_rag


# ====== 语义去重阈值 ======
# ONNX MiniLM cosine 相似度，用 top-1 mean 算法
# 实测：自比对 = 1.0000，不同论文间全 ≤ 0.57，且 0 个 chunk ≥ 0.9
# v1 vs v7 预期 ≥ 0.95（几乎所有 chunk 相同）
HIGH_OVERLAP_THRESHOLD = 0.90       # 几乎同一版（≥0.90，MD5 不同但正文几乎完全一致）
VERSION_EVOLVE_THRESHOLD = 0.70     # 疑似版本演进（0.70~0.90，如 arXiv v1→v7 有少量修订）

# 参与去重比对的 chunk 上限，超出则等距抽样。
# ONNX MiniLM 在 2 核 CPU 上约 10 段/秒，几百页的书有上千个 chunk，全量算要几分钟。
MAX_DEDUP_CHUNKS = 200


def check_semantic_duplicate(new_paper, collection=None) -> list:
    """
    语义级去重检测 —— top-1 mean 算法
    对新论文的每个 chunk，在每篇已有论文中找最相似 chunk（top-1），
    收集所有 top-1 相似度的均值作为两篇论文的整体相似度。

    算法精度（已实测校准）：
      - 完全相同论文（自比对）  → top-1 mean = 1.0000
      - 不同领域/风格论文       → top-1 mean ≈ 0.50~0.57（且 0 个 chunk ≥ 0.90）
      - v1 vs v7（99% 相同）    → top-1 mean ≥ 0.95

    Args:
        new_paper: ParsedPaper 对象（含 chunks）
        collection: 可选，已有 Chroma collection

    Returns:
        detections: 按相似度降序排列的检测结果列表
            [{"paper_id": str, "title": str, "top1_mean": float,
              "identical_chunks": int, "total_chunks": int,
              "status": str, "suggestion": str}]
            status:
              - "high_overlap"   → 几乎完全重复（top1_mean ≥ 0.90）
              - "version_evolve" → 疑似版本演进（0.70 ≤ top1_mean < 0.90）
            低于 0.70 的不返回
    """
    if collection is None:
        collection = get_collection()

    # 1. 查库中已有哪些论文
    existing = collection.get(include=["metadatas"])
    existing_ids = existing.get("ids", [])
    if not existing_ids:
        return []

    # 收集已有 paper_id → title 映射
    existing_papers = {}
    for meta in existing.get("metadatas", []):
        pid = meta.get("paper_id", "")
        if pid and pid not in existing_papers:
            existing_papers[pid] = meta.get("title", "")

    # 过滤掉自己（MD5 精确重复已被上层拦截，这里防御性跳过）
    candidates = {
        pid: title for pid, title in existing_papers.items()
        if pid != new_paper.paper_id
    }
    if not candidates:
        return []

    # 2. 新论文 chunks 文本（超大文档等距抽样，去重只需代表性子集）
    new_texts = [c["text"] for c in new_paper.chunks if c.get("text")]
    if not new_texts:
        return []
    if len(new_texts) > MAX_DEDUP_CHUNKS:
        step = len(new_texts) / MAX_DEDUP_CHUNKS
        new_texts = [new_texts[int(i * step)] for i in range(MAX_DEDUP_CHUNKS)]

    # 2.1 embedding 只算一次：逐篇 query 时传向量，避免每篇重复 embedding
    #     （57 段约 5.8 秒，8 篇论文逐篇算就是 46 秒）
    try:
        new_embeddings = get_embedding_function()(new_texts)
    except Exception as e:
        print(f"[semantic_dedup] embedding 失败，跳过检测: {e}")
        return []

    # 3. 逐篇已有论文精准比对：对每个已有 pid 单独 query
    #    这样可以精准拿到"新论文每个 chunk 在该已有论文中的 top-1 相似度"
    detections = []

    for pid, title in candidates.items():
        try:
            results = collection.query(
                query_embeddings=new_embeddings,
                n_results=1,              # 只要最相似的那一个
                include=["distances"],
                where={"paper_id": pid},  # 只查这一篇
            )
        except Exception as e:
            print(f"[semantic_dedup] query {pid} 失败，跳过: {e}")
            continue

        # 收集每个新 chunk 的 top-1 similarity
        top1_sims = []
        for dist_list in results.get("distances", []):
            if dist_list:
                # Chroma cosine distance = 1 - cosine_similarity
                sim = max(0.0, min(1.0, 1.0 - dist_list[0]))
                top1_sims.append(sim)

        if not top1_sims:
            continue

        top1_mean = sum(top1_sims) / len(top1_sims)
        identical = sum(1 for s in top1_sims if s >= 0.98)   # 几乎完全相同的 chunk 数
        total = len(top1_sims)

        # 阈值判定
        if top1_mean >= HIGH_OVERLAP_THRESHOLD:
            status = "high_overlap"
            pct = int(top1_mean * 100)
            suggestion = (
                f"⚠️ 内容高度重合！与《{title}》相似度 {pct}%"
                f"（{identical}/{total} 个 chunk 几乎相同）— 建议确认不要重复入库"
            )
        elif top1_mean >= VERSION_EVOLVE_THRESHOLD:
            status = "version_evolve"
            pct = int(top1_mean * 100)
            suggestion = (
                f"🔍 疑似版本演进：与《{title}》相似度 {pct}%"
                f"（如 arXiv v1→v7 修订版）— 建议保留最新版本"
            )
        else:
            continue  # 低于阈值不报告

        detections.append({
            "paper_id": pid,
            "title": title,
            "top1_mean": round(top1_mean, 4),
            "identical_chunks": identical,
            "total_chunks": total,
            "status": status,
            "suggestion": suggestion,
        })

    # 4. 按相似度降序
    detections.sort(key=lambda x: x["top1_mean"], reverse=True)
    return detections


def upload_paper(filepath: str, filename: str) -> dict:
    """上传 PDF → 解析 → 语义去重检测 → 入库"""
    paper = parse_pdf(filepath)
    collection = get_collection()

    # ---- 第一层：MD5 精确重复（文件哈希） ----
    existing_exact = collection.get(where={"paper_id": paper.paper_id})
    if len(existing_exact["ids"]) > 0:
        return {
            "status": "duplicate",
            "reason": "md5_exact_match",
            "paper_id": paper.paper_id,
            "title": paper.title,
            "message": "文件哈希完全相同，已存在于库中，跳过入库",
        }

    # ---- 第二层：语义级去重（用 Chroma Embedding 比对） ----
    detections = check_semantic_duplicate(paper, collection=collection)

    # ---- 正常入库（无论语义检测结果如何都入库，warning 通过 detections 返回） ----
    docs, metas, ids = chunks_for_rag(paper)
    if docs:
        collection.add(documents=docs, metadatas=metas, ids=ids)

    dest_dir = Path(settings.UPLOAD_DIR) / paper.paper_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(filepath, str(dest_dir / filename))

    # 构造返回状态
    if detections:
        has_high = any(d["status"] == "high_overlap" for d in detections)
        has_version = any(d["status"] == "version_evolve" for d in detections)
        if has_high:
            status = "semantic_duplicate"
        elif has_version:
            status = "version_warning"
        else:
            status = "success"
    else:
        status = "success"

    return {
        "status": status,
        "paper_id": paper.paper_id,
        "title": paper.title,
        "authors": paper.authors,
        "chunks_count": len(docs),
        "total_pages": paper.total_pages,
        "detections": detections,      # 前端据此弹提示
        "version_hint": "",             # 旧字段保留兼容
    }


def list_papers() -> list:
    collection = get_collection()
    results = collection.get(include=["metadatas"])
    papers = {}
    for meta in results["metadatas"]:
        pid = meta.get("paper_id", "")
        if pid and pid not in papers:
            papers[pid] = {
                "paper_id": pid,
                "title": meta.get("title", "未知"),
                "page": meta.get("page", 0),
            }
    return list(papers.values())


def delete_paper(paper_id: str) -> dict:
    collection = get_collection()
    collection.delete(where={"paper_id": paper_id})
    dir_path = Path(settings.UPLOAD_DIR) / paper_id
    if dir_path.exists():
        shutil.rmtree(str(dir_path))
    return {"status": "deleted", "paper_id": paper_id}
