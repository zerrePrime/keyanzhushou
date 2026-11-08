"""arXiv 检索服务 - 支持库内已入库标记 + 每日推送去重"""
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from app.config import settings
from app.rag.chroma_client import get_collection


def _norm_title(t: str) -> str:
    """归一化标题：小写 + 去空白/标点/非字母数字，用于匹配"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (t or "").lower())


def _get_library_title_keys() -> dict:
    """
    取库内所有论文的归一化标题 → 原文标题映射。
    用 Chroma metadata 里 title 字段做匹配，不依赖 arxiv_id（因为用户也可能上传非 arXiv PDF）。
    """
    collection = get_collection()
    results = collection.get(include=["metadatas"])
    mapping = {}
    seen = set()
    for meta in results.get("metadatas", []) or []:
        t = (meta.get("title") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        nt = _norm_title(t)
        if nt and nt not in mapping:
            mapping[nt] = t
    return mapping


def _mark_library_status(papers: list, library_map: dict) -> list:
    """
    给 arXiv 结果每一条加 in_library 标记。
    匹配规则：归一化后标题完全相等 / 互相包含（容错 PyMuPDF 抓到的标题跟 arXiv 返回的标题小有差异）。
    """
    for p in papers:
        nt = _norm_title(p.get("title", ""))
        hit = False
        matched = ""
        if nt:
            # 完全相等
            if nt in library_map:
                hit, matched = True, library_map[nt]
            else:
                # 双向包含（取最长命中，更稳）
                best = ""
                for k, orig in library_map.items():
                    if len(k) >= 10 and (k in nt or nt in k):
                        if len(orig) > len(best):
                            best = orig
                if best:
                    hit, matched = True, best
        p["in_library"] = hit
        p["matched_title"] = matched
    return papers


def search_arxiv(query: str, max_results: int = 10, mark_library: bool = True) -> list:
    """
    调 arXiv API 搜索论文。

    Args:
        query: 搜索关键词
        max_results: 返回条数
        mark_library: True 时为每条结果附加 in_library / matched_title 字段（默认 True）

    返回:
        [{arxiv_id, title, authors, summary, updated, pdf_url, in_library, matched_title}]
    """
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{settings.ARXIV_API_URL}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read().decode("utf-8")
    except Exception as e:
        return [{"error": f"arXiv API 调用失败: {e}"}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)

    papers = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", "", ns).strip()
        summary = entry.findtext("atom:summary", "", ns).strip()
        updated = entry.findtext("atom:updated", "", ns)

        authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]

        arxiv_id = entry.findtext("atom:id", "", ns).split("/abs/")[-1]
        pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf":
                pdf_link = link.get("href", pdf_link)
                break

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "summary": summary[:300] + "...",
            "updated": updated,
            "pdf_url": pdf_link,
        })

    if mark_library and papers and "error" not in papers[0]:
        library_map = _get_library_title_keys()
        if library_map:
            _mark_library_status(papers, library_map)
        else:
            for p in papers:
                p["in_library"] = False
                p["matched_title"] = ""

    return papers


def get_daily_papers(max_results: int = 20) -> dict:
    """
    每日新推荐：按提交时间 freshness 排序 + 过滤掉已入库论文。

    返回 {"papers": [...], "skipped_count": int} 结构，skipped_count 是因已入库被过滤的条数。
    """
    keywords = "artificial intelligence OR machine learning OR retrieval augmented generation OR RAG OR agent OR LLM"
    params = urllib.parse.urlencode({
        "search_query": keywords,
        "start": 0,
        "max_results": max_results * 2,   # 多拉一些，过滤后够数
        "sortBy": "submittedDate",        # 按提交时间倒序 = freshness 排序
        "sortOrder": "descending",
    })
    url = f"{settings.ARXIV_API_URL}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read().decode("utf-8")
    except Exception as e:
        return {"papers": [{"error": f"arXiv API 调用失败: {e}"}], "skipped_count": 0}

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)

    raw = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", "", ns).strip()
        summary = entry.findtext("atom:summary", "", ns).strip()
        updated = entry.findtext("atom:updated", "", ns)
        authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        arxiv_id = entry.findtext("atom:id", "", ns).split("/abs/")[-1]
        pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf":
                pdf_link = link.get("href", pdf_link)
                break
        raw.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "summary": summary[:300] + "...",
            "updated": updated,
            "pdf_url": pdf_link,
        })

    # 过滤已入库
    library_map = _get_library_title_keys()
    marked = _mark_library_status(raw, library_map) if library_map else [
        {**p, "in_library": False, "matched_title": ""} for p in raw
    ]
    fresh = [p for p in marked if not p.get("in_library")]
    skipped = len(marked) - len(fresh)

    # 截断到 max_results
    return {"papers": fresh[:max_results], "skipped_count": skipped}
