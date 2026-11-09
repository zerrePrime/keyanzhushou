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
    """
    自动综述：按论文取一段代表性正文喂 LLM。
    只喂标题会得到与文献库无关的通用套话，喂正文片段才能让综述真正基于库内内容；
    还要避开版权页/参考文献列表这类模板文字，否则会把出版社、许可证或书目条目写进综述。
    """
    import re as _re
    from app.rag.chroma_client import get_collection
    from app.rag.qa_service import llm_chat

    collection = get_collection()
    results = collection.get(include=["documents", "metadatas"])

    docs = results.get("documents") or []
    metas = results.get("metadatas") or []

    # 版权/许可/出版类模板词：出现即认为这段不适合作为该文献的代表内容
    boiler_terms = ("copyright", "©", "all rights reserved", "license", "licence",
                    "permission", "isbn", "mit press", "springer", "elsevier",
                    "版权所有", "许可", "出版社")

    def is_bad_chunk(raw: str, text: str) -> bool:
        """参考文献列表、目录、索引、表格这类片段不适合当作文献的代表内容。"""
        low = text.lower()
        if low.count("et al") >= 3:
            return True
        if low.count("proceedings") >= 2 or low.count("arxiv") >= 4:
            return True
        if len(_re.findall(r"(?:19|20)\d{2}", text)) >= 8:
            return True
        if sum(c.isdigit() for c in text) / len(text) > 0.06:
            return True
        # 版式判断：目录/索引一行一个短条目，正文行明显更长
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            avg_len = sum(len(ln) for ln in lines) / len(lines)
            numbered = sum(1 for ln in lines if _re.match(r"\d+(\.\d+)*\s", ln))
            if avg_len < 40 or numbered >= 6:
                return True
        return "…" in text or "......" in text

    # 每篇论文选一段作为代表：摘要段最优，其次正文较长的段；版权页排最后
    best = {}
    for doc, meta in zip(docs, metas):
        title = (meta.get("title") or "").strip()
        if not title or not doc:
            continue
        try:
            page = int(meta.get("page", 999))
        except (TypeError, ValueError):
            page = 999
        text = _re.sub(r"\s+", " ", doc).strip()
        if len(text) < 60:
            continue  # 页眉页脚、目录条目这类碎片
        if is_bad_chunk(doc, text):
            continue  # 参考文献列表、目录、索引
        # 用词边界匹配，避免把 abstractive summarization 这类词误判成摘要
        is_abstract = 0 if (_re.search(r"\babstract\b", text.lower()) or "摘要" in text) else 1
        boiler = 1 if any(t in text.lower() or t in text for t in boiler_terms) else 0
        key = (is_abstract, boiler, -min(len(text), 1500), page)
        if title not in best or key < best[title][0]:
            best[title] = (key, text)

    if not best:
        return "文献库为空，无法生成综述"

    # 摘要前的标题、作者、单位会占满截断额度，从 Abstract 标题处开始取
    def snippet(text: str) -> str:
        m = _re.search(r"\babstract\b", text, _re.I)
        if m and m.start() > 0:
            return text[m.start():m.start() + 700]
        return text[:800]

    entries = [f"### {title}\n{snippet(text)}" for title, (key, text) in list(best.items())[:8]]

    prompt = f"""以下是文献库中全部文献的代表性正文片段（共 {len(entries)} 段）：

{chr(10).join(entries)}

请仅依据上述片段写一段该研究方向的综述，要求：
1. 150-300 字，分「起源」「发展」「前沿」三部分；
2. 每条论断都必须来自上述片段的原文内容，并在括号中标注对应标题；
3. 不得依据标题推测论文内容，片段没写到的主题一律不要出现；
4. 若某一部分在片段中找不到依据，该部分正文只写「现有片段未覆盖」，不要补充其他内容；
5. 不要描述版权、许可、出版或版本发布信息，这些不属于研究进展。"""

    return llm_chat(prompt, system="你是一个严谨的学术综述专家，只依据给定材料写作，不添加材料外的事实。")
