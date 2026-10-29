"""引用图谱 + 图论分析

改进：从 Chroma metadata 里读真正的 references 字段做引用匹配，
不再是全连接 baseline。
"""
import networkx as nx
from app.rag.chroma_client import get_collection


def build_citation_graph() -> dict:
    """
    从文献库构建真正的引用关系图
    - 节点 = 论文
    - 边 = 引用关系（从 references 字段匹配其他论文的标题）
    """
    collection = get_collection()
    results = collection.get(include=["metadatas"])

    # 按 paper_id 分组取唯一元数据
    papers_seen = {}
    for meta in results["metadatas"]:
        pid = meta.get("paper_id", "")
        if pid and pid not in papers_seen:
            papers_seen[pid] = {
                "paper_id": pid,
                "title": meta.get("title", ""),
                "references": meta.get("references", ""),
            }

    G = nx.DiGraph()
    for pid, info in papers_seen.items():
        G.add_node(pid, title=info["title"])

    # ====== 真正的引用匹配 ======
    titles = {pid: info["title"].lower() for pid, info in papers_seen.items()}

    for src_id, info in papers_seen.items():
        refs_raw = info.get("references", "")
        if not refs_raw:
            continue

        ref_lines = [r.strip() for r in refs_raw.split("||") if r.strip()]

        for ref_line in ref_lines:
            ref_lower = ref_line.lower()

            # 策略 1: 标题包含匹配（如果 A 的参考文献里出现了 B 的标题关键词 → A 引 B）
            for tgt_id, tgt_title in titles.items():
                if tgt_id == src_id or not tgt_title:
                    continue
                # 标题至少有 3 个连续字符匹配，且被引标题长度 > 5
                if len(tgt_title) > 5 and tgt_title[:8] in ref_lower:
                    G.add_edge(src_id, tgt_id, weight=1, method="title_match")
                    break  # 一条 reference 最多匹配一条

    # ====== 如果没抽到任何 references，降级：互相作为 baseline ======
    if G.number_of_edges() == 0 and len(papers_seen) > 1:
        pids = list(papers_seen.keys())
        for i, src in enumerate(pids):
            for j, tgt in enumerate(pids):
                if i != j:
                    G.add_edge(src, tgt, weight=1, method="baseline")

    top = find_foundation_papers(G, {pid: info["title"] for pid, info in papers_seen.items()})

    return {
        "nodes": [{"id": k, "title": v["title"]} for k, v in papers_seen.items()],
        "edges": [{"source": e[0], "target": e[1], "method": e[2].get("method", "")}
                  for e in G.edges(data=True)],
        "top_cited": top,
        "edge_count": G.number_of_edges(),
        "edge_method": "reference_matching" if any(e[2].get("method") == "title_match" for e in G.edges(data=True)) else "baseline_fallback",
    }


def find_foundation_papers(G: nx.DiGraph, titles: dict) -> list:
    """用 PageRank 找基石论文"""
    if G.number_of_nodes() == 0:
        return []
    pagerank = nx.pagerank(G, alpha=0.85)
    ranked = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)
    return [
        {"paper_id": pid, "title": titles.get(pid, ""), "pagerank": round(score, 4),
         "in_degree": G.in_degree(pid)}
        for pid, score in ranked[:10]
    ]


def generate_auto_survey() -> str:
    """自动综述：把所有论文标题汇总喂 LLM"""
    from app.rag.chroma_client import get_collection
    from app.rag.qa_service import llm_chat

    collection = get_collection()
    results = collection.get(include=["metadatas"])
    titles = list({m.get("title", "") for m in results["metadatas"] if m.get("title")})

    if not titles:
        return "文献库为空，无法生成综述"

    prompt = f"""请基于以下论文列表，写一段这个研究方向的综述：

论文列表：
{chr(10).join(f"- {t}" for t in titles[:20])}

要求：150-300字，分起源、发展、前沿三部分。"""

    return llm_chat(prompt, system="你是一个学术综述专家")
