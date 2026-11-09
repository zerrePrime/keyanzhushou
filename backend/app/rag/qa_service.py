"""
RAG 问答服务 - 抗幻觉 + 源头溯源
"""
import json
import re
from pathlib import Path
from typing import Optional
from app.rag.chroma_client import get_collection
from app.config import settings


# ====== LLM 统一调用层（本地 Ollama / 云端 OpenAI 兼容 API）======
def _ollama_chat(prompt: str, system: str) -> str:
    import requests
    resp = requests.post(
        f"{settings.OLLAMA_BASE_URL}/api/generate",
        json={
            "model": settings.OLLAMA_LLM_MODEL,
            "prompt": f"{system}\n\n{prompt}",
            "stream": False,
            "options": {
                "temperature": settings.LLM_TEMPERATURE,
                "num_ctx": 8192,
                "num_predict": settings.LLM_MAX_TOKENS,
            },
        },
        timeout=settings.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def _openai_chat(prompt: str, system: str) -> str:
    import requests
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 未配置，无法使用云 API")
    resp = requests.post(
        f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": False,
        },
        timeout=settings.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def llm_chat(prompt: str, system: str = "你是一个严谨的科研助手，回答必须基于提供的参考资料，不确定时说不知道。") -> str:
    """统一 LLM 入口，按 settings.LLM_PROVIDER 分发到本地 Ollama 或云端 API"""
    try:
        if settings.LLM_PROVIDER == "openai_compatible":
            return _openai_chat(prompt, system)
        return _ollama_chat(prompt, system)
    except Exception as e:
        return f"[LLM 调用失败: {e}]"


# ====== 中文→英文关键词 fallback ======
ZH_TO_EN = {
    "优化器": "optimizer", "优化": "optimizer", "梯度": "gradient",
    "学习率": "learning rate", "批量": "batch", "损失": "loss",
    "注意力": "attention", "多头": "multi-head", "编码器": "encoder",
    "解码器": "decoder", "残差": "residual", "归一化": "normalization",
    "训练": "training", "参数": "parameter", "模型": "model",
    "效果": "performance", "性能": "performance", "准确率": "accuracy",
    "论文": "paper", "作者": "author", "摘要": "abstract",
    "引用": "cite", "参考": "reference", "实验": "experiment",
    "结果": "result", "结论": "conclusion", "介绍": "introduction",
    "相关工作": "related work", "方法": "method",
    "Transformer": "Transformer", "BERT": "BERT", "GPT": "GPT",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TRANSLATE_CACHE: dict[str, str] = {}


def _keyword_translate(query: str) -> str:
    """逐词替换式翻译，作为 LLM 翻译失败时的兜底"""
    result = query
    for zh, en in ZH_TO_EN.items():
        result = result.replace(zh, en)
    return result if any(c.isascii() and c.isalpha() for c in result) else query


def zh_to_en_query(query: str) -> str:
    """
    中文问题翻译成完整英文检索语句，用于检索英文论文库。
    优先调用 LLM 翻译（结果缓存），失败时退回关键词替换。
    逐词替换会得到"decoder由几个相同的层组成"这类中英混杂查询，向量质量很差。
    """
    if not _CJK_RE.search(query):
        return query
    cached = _TRANSLATE_CACHE.get(query)
    if cached:
        return cached

    system = (
        "你是学术检索助手。把用户的中文问题翻译成一句简洁的英文学术检索语句，"
        "保留专业术语原文。只输出译文本身，不要解释、不要加引号。"
    )
    out = llm_chat(query, system).strip().strip('"“”「」')
    # 翻译失败 / 仍含中文 / 异常长，一律退回关键词替换
    if (
        not out
        or out.startswith("[LLM 调用失败")
        or _CJK_RE.search(out)
        or len(out) > 300
    ):
        return _keyword_translate(query)

    if len(_TRANSLATE_CACHE) < 500:
        _TRANSLATE_CACHE[query] = out
    return out


# ====== 核心 RAG 检索 ======
def retrieve_context(query: str, top_k: int = 5, paper_id: str = None) -> tuple[list[str], list[dict]]:
    """
    检索最相关的 top_k 个段落
    paper_id 传入时只在指定论文内检索（单篇模式），否则全库检索
    返回 (文档列表, 元数据列表)
    """
    collection = get_collection()

    # 构造查询：中文原 query + 关键词翻英文的 query
    queries = [query]
    en_query = zh_to_en_query(query)
    if en_query != query:
        queries.append(en_query)

    best_docs, best_meta, best_dist = [], [], []
    seen_ids = set()

    where = {"paper_id": paper_id} if paper_id else None
    # 候选池放大：多取一些再按论文配额挑选，避免超大型文档（如 541 页书籍）
    # 靠切块数量优势淹没库内的短文论文
    pool_size = max(top_k * 6, 20)

    candidates = []  # (dist, doc, meta, source_key)
    for q in queries:
        results = collection.query(
            query_texts=[q],
            n_results=pool_size,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        dists = results["distances"][0] if results["distances"] else []

        for doc, meta, dist in zip(docs, metas, dists):
            if dist >= 0.9:  # 放宽阈值，过远的不进上下文
                continue
            candidates.append((dist, doc, meta, meta.get("source", "")))

    candidates.sort(key=lambda x: x[0])

    # 第一轮：每篇论文最多取 2 条，保证来源多样性
    MAX_PER_PAPER = 2
    per_paper = {}
    leftovers = []
    for dist, doc, meta, key in candidates:
        if key in seen_ids:
            continue
        pid = meta.get("paper_id", "")
        if per_paper.get(pid, 0) >= MAX_PER_PAPER:
            leftovers.append((dist, doc, meta, key))
            continue
        per_paper[pid] = per_paper.get(pid, 0) + 1
        seen_ids.add(key)
        best_docs.append(doc)
        best_meta.append(meta)
        best_dist.append(dist)
        if len(best_docs) >= top_k:
            break

    # 第二轮：结果不足 top_k 时放开配额补足
    if len(best_docs) < top_k:
        for dist, doc, meta, key in leftovers:
            if key in seen_ids:
                continue
            seen_ids.add(key)
            best_docs.append(doc)
            best_meta.append(meta)
            best_dist.append(dist)
            if len(best_docs) >= top_k:
                break

    return best_docs, best_meta


# ====== 生成带溯源的回答 ======
def answer_with_sources(query: str, paper_id: str = None) -> dict:
    """
    RAG 主函数：提问 → 检索 → 生成 → 附带来源
    paper_id 传入时仅在该论文范围内检索（单篇提问），否则全库检索
    """
    documents, metadatas = retrieve_context(query, top_k=5, paper_id=paper_id)

    if not documents:
        return {
            "answer": "抱歉，我在当前文献库中找不到与这个问题相关的内容。请先上传相关论文。",
            "sources": [],
        }

    # 构造 Prompt：把检索到的内容喂给 LLM
    context_text = "\n\n---\n\n".join(
        f"[来源: {meta.get('title', '未知')}, 第 {meta.get('page', '?')} 页]\n{doc}"
        for doc, meta in zip(documents, metadatas)
    )

    prompt = f"""请基于以下参考资料回答问题。

参考资料：
{context_text}

问题：{query}

要求：
1. 只根据参考资料回答，不要编造
2. 回答里标出信息来自哪篇论文第几页
3. 如果参考资料里没有答案，明确说"资料不足，无法回答"
"""

    answer = llm_chat(prompt)

    # 提取来源信息（给前端高亮用）
    sources = []
    for meta in metadatas:
        sources.append({
            "paper_id": meta.get("paper_id", ""),
            "title": meta.get("title", ""),
            "page": meta.get("page", 0),
            "source": meta.get("source", ""),
        })

    return {
        "answer": answer,
        "sources": sources,
    }


# ====== 跨论文多文对比 ======
def multi_paper_compare(query: str) -> dict:
    """
    跨多篇论文对比推理
    （与单文问答类似，但检索 top_k 更大，Prompt 强调对比）
    """
    documents, metadatas = retrieve_context(query, top_k=10)

    if not documents:
        return {"answer": "文献库内容不足", "sources": []}

    # 按 paper_id 分组
    papers_seen = {}
    for doc, meta in zip(documents, metadatas):
        pid = meta.get("paper_id", "?")
        if pid not in papers_seen:
            papers_seen[pid] = {"title": meta.get("title", ""), "chunks": []}
        papers_seen[pid]["chunks"].append(f"第{meta.get('page', '?')}页: {doc[:200]}...")

    summary = ""
    for pid, info in papers_seen.items():
        summary += f"\n【{info['title']}】({pid}):\n"
        summary += "\n".join(info["chunks"][:3])
        summary += "\n"

    prompt = f"""请对比分析以下多篇论文的相关内容，回答用户问题。

多文信息：{summary}

对比问题：{query}

要求：
- 分点列出每篇论文的关键信息
- 指出它们之间的相同点和不同点
- 给出综合结论
"""

    answer = llm_chat(prompt)
    sources = [{"paper_id": pid, "title": info["title"]} for pid, info in papers_seen.items()]

    return {"answer": answer, "sources": sources}


# ====== 中英互译（划词 / 整页 / 整篇） ======
TRANSLATE_SYSTEM = (
    "你是专业的学术论文翻译，只输出译文本身：不要解释、不要复述原文、不要加引号或 Markdown 包裹。"
    "保留公式、变量名、数字、引用标记（如 [1]）和专有名词原名。"
)

_MAX_SEGMENT = 1200


def _split_segments(text: str, limit: int = _MAX_SEGMENT) -> list[str]:
    """把长文本按空行段落聚合切块，避免单次调用超出模型上下文"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    segments, buf = [], ""
    for para in paragraphs:
        if len(para) > limit:
            if buf:
                segments.append(buf)
                buf = ""
            for i in range(0, len(para), limit):
                segments.append(para[i:i + limit])
            continue
        if len(buf) + len(para) + 1 > limit:
            segments.append(buf)
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        segments.append(buf)
    return segments


def translate_text(text: str, target: str = "zh", max_segments: int = 12) -> dict:
    """
    逐段翻译，返回 {"text": 译文, "segments": 段数, "truncated": 是否因段数上限截断}
    单次请求最多翻 max_segments 段，前端整篇翻译时按页分批调用。
    """
    text = (text or "").strip()
    if not text:
        return {"text": "", "segments": 0, "truncated": False}

    segments = _split_segments(text)
    truncated = len(segments) > max_segments
    segments = segments[:max_segments]

    lang = "中文" if target == "zh" else "英文"
    out = []
    for seg in segments:
        prompt = f"请把下面的学术内容翻译成{lang}：\n\n{seg}"
        out.append(llm_chat(prompt, TRANSLATE_SYSTEM).strip())

    return {
        "text": "\n\n".join(out),
        "segments": len(segments),
        "truncated": truncated,
    }


# ====== Future Work 提取：从论文结论/展望中挖掘未来研究方向 ======
_FUTURE_QUERIES = [
    "future work limitations future research directions",
    "conclusion discussion open problems",
]

_FUTURE_HINT_RE = re.compile(
    r"future|limitation|further|remain|open (problem|question)|direction|展望|未来|局限",
    re.I,
)


_YEAR_CACHE = Path(settings.UPLOAD_DIR) / "_paper_years.json"
_BRACKET_RE = re.compile(r"[【\[]([^】\]]+)[】\]]")


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _match_title(src: str, titles: list) -> str:
    """把 LLM 写出的来源标题对回文献库真实标题，对不上就返回空（不展示编造标题）"""
    ns = _norm_title(src)
    if not ns:
        return ""
    for t in titles:
        nt = _norm_title(t)
        if nt and (ns == nt or ns in nt or nt in ns):
            return t
    return ""


def paper_timeline(collection) -> dict:
    """
    推断各论文发表年份（Chroma 元数据未存年份，用 LLM 推断并本地缓存，
    只有首次调用会产生额外 LLM 开销）。
    """
    results = collection.get(include=["metadatas"])
    titles = []
    for m in results.get("metadatas", []) or []:
        t = (m.get("title") or "").strip()
        if t and t not in titles:
            titles.append(t)
    if not titles:
        return {}

    cache = {}
    if _YEAR_CACHE.exists():
        try:
            cache = json.loads(_YEAR_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    missing = [t for t in titles if t not in cache]
    if missing:
        missing = missing[:20]
        listing = "\n".join(f"{i}. {t}" for i, t in enumerate(missing, start=1))
        prompt = f"""请为下列学术论文标注发表年份：

{listing}

输出格式：每行一条「序号=年份」，例如 "1=2017"。只输出这些行，不要任何解释。"""
        try:
            raw = llm_chat(prompt, system="你只输出「序号=年份」格式的行。")
            for m in re.finditer(r"(\d+)\s*[=:：]\s*((?:19|20)\d{2})", raw):
                idx, year = int(m.group(1)), int(m.group(2))
                if 1 <= idx <= len(missing) and 1950 < year < 2030:
                    cache[missing[idx - 1]] = year
        except Exception:
            pass

        # 兜底：用归一化标题做模糊匹配，覆盖 LLM 改写过标题的情况
        for t in missing:
            if t in cache:
                continue
            nt = _norm_title(t)
            for k, v in list(cache.items()):
                nk = _norm_title(k)
                if nk and (nk in nt or nt in nk):
                    cache[t] = v
                    break

        try:
            _YEAR_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {t: cache[t] for t in titles if t in cache}


def _verify_directions(collection, directions: list, timeline: dict) -> tuple:
    """
    对每个方向检索「其他论文」中的相近段落，再由 LLM 判定它是否已被后续工作解决。
    返回 (verdicts, evidence_titles)：
      verdicts = {方向序号: {"status", "solved_by"}}
      evidence_titles = {方向序号: [实际检索到的论文标题]}，用于校验 solved_by 不是幻觉
    """
    blocks = []
    evidence_titles = {}
    for i, d in enumerate(directions, start=1):
        m = _BRACKET_RE.search(d)
        src = m.group(1) if m else ""
        results = collection.query(
            query_texts=[d[:300]],
            n_results=4,
            include=["documents", "metadatas", "distances"],
        )
        lines, titles = [], []
        for doc, meta, dist in zip(
            results.get("documents", [[]])[0] or [],
            results.get("metadatas", [[]])[0] or [],
            results.get("distances", [[]])[0] or [],
        ):
            title = meta.get("title", "")
            if not title or _norm_title(title) == _norm_title(src) or dist >= 0.86:
                continue
            if title in titles:
                continue
            year = timeline.get(title, "?")
            lines.append(f"  · [{title} | {year} | 第{meta.get('page', '?')}页] {doc[:240]}")
            titles.append(title)
            if len(lines) >= 2:
                break
        evidence_titles[i] = titles
        evidence = "\n".join(lines) if lines else "  · （其他论文中无相近内容）"
        blocks.append(f"方向 {i}：{d}\n{evidence}")

    prompt = f"""你是一名严格的学术审稿人。下面是候选未来研究方向，以及从**其他论文**中检索到的相近片段：

{chr(10).join(blocks)}

请逐条判断该方向在后续研究中是否已被解决：
- 已解决：其他论文明确提出了该方向并给出方法/结果
- 部分解决：有相关工作涉及，但仍有明显空白
- 仍开放：其他论文中没有实质进展

输出格式：每行一条「序号=状态」，已解决的再追加「=解决方案论文标题」，例如：
1=仍开放
2=已解决=BERT: Pre-training of Deep Bidirectional Transformers
只输出这些行，不要解释。"""

    raw = llm_chat(prompt, system="你只输出「序号=状态」格式的行，不做解释。")
    verdicts = {}
    for line in raw.splitlines():
        m = re.match(r"\s*(\d+)\s*[=＝:：]\s*(仍开放|部分解决|已解决)\s*(?:[=＝:：]\s*(.+))?", line)
        if not m:
            continue
        idx = int(m.group(1))
        if not 1 <= idx <= len(directions):
            continue
        verdicts[idx] = {
            "status": m.group(2),
            "solved_by": (m.group(3) or "").strip(),
        }
    return verdicts, evidence_titles


def extract_future_work(topic: str = "", top_k: int = 12) -> dict:
    """
    从文献库中定位与「未来工作 / 局限性 / 结论」相关的段落，
    归纳成带溯源的未来研究方向，并结合论文时间线剔除「已被后续工作解决」的旧 idea。
    topic 为空时对整个文献库做挖掘，否则按主题过滤。
    """
    collection = get_collection()

    queries = list(_FUTURE_QUERIES)
    if topic:
        queries.append(f"{topic} future work")
        en = zh_to_en_query(topic)
        if en != topic:
            queries.append(f"{en} future work")

    docs, metas = [], []
    seen = set()
    for q in queries:
        results = collection.query(
            query_texts=[q],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        for doc, meta, dist in zip(
            results.get("documents", [[]])[0] or [],
            results.get("metadatas", [[]])[0] or [],
            results.get("distances", [[]])[0] or [],
        ):
            key = meta.get("source", "")
            if key in seen or dist >= 0.9:
                continue
            seen.add(key)
            docs.append(doc)
            metas.append(meta)

    # 优先保留明确提到 future/limitation 的段落，其余按检索顺序补足
    hinted = [(d, m) for d, m in zip(docs, metas) if _FUTURE_HINT_RE.search(d)]
    picked = (hinted + [(d, m) for d, m in zip(docs, metas) if _FUTURE_HINT_RE.search(d) is None])[:8]
    if not picked:
        return {"answer": "文献库中未找到与未来研究方向相关的内容，请先上传论文。", "directions": [], "sources": []}

    context = "\n\n---\n\n".join(
        f"[来源: {m.get('title', '未知')}, 第 {m.get('page', '?')} 页]\n{d[:600]}"
        for d, m in picked
    )
    topic_line = f"\n请聚焦主题：{topic}\n" if topic else ""
    prompt = f"""以下是从多篇学术论文中检索到的结论 / 局限性 / 展望片段：

{context}
{topic_line}
请按下面格式逐行输出 3-6 个未来研究方向，每行都必须带来源：

1. 方向描述（中文一句话）【论文标题】
2. 方向描述（中文一句话）【论文标题】

要求：
- 每行都要有实际的研究方向内容，不要输出「来自《某论文》」这类只有来源的行
- 只基于上述片段归纳，不要编造"""

    answer = llm_chat(prompt)

    # 从回答中拆出方向条目（按换行 + 序号/项目符号切分）
    directions = []
    for line in answer.splitlines():
        line = line.strip(" -•*\t")
        line = re.sub(r"^\d+[.、)]\s*", "", line).strip()
        if len(line) < 10 or line.endswith(("：", ":")):
            continue
        # 去掉来源标记后，必须还有实质内容，否则视为纯来源行丢弃
        body = _BRACKET_RE.sub("", line).strip()
        if len(body) < 8 or re.match(r"^(来自|来源|出处|source|from)\b", body, re.I):
            continue
        directions.append(line)
    directions = directions[:6]

    sources = [
        {
            "paper_id": m.get("paper_id", ""),
            "title": m.get("title", ""),
            "page": m.get("page", 0),
            "source": m.get("source", ""),
        }
        for m in metas[:6]
    ]

    if not directions:
        return {"answer": answer, "directions": [], "excluded": [],
                "timeline": [], "sources": sources}

    # ===== 结合时间线筛选：剔除已被后续工作解决的旧 idea =====
    timeline = paper_timeline(collection)
    verdicts, evidence_titles = _verify_directions(collection, directions, timeline)

    kept, excluded = [], []
    for i, d in enumerate(directions, start=1):
        m = _BRACKET_RE.search(d)
        raw_src = m.group(1) if m else ""
        # 来源标题必须是文献库里真实存在的论文，模型编造的标题不展示
        src_title = _match_title(raw_src, list(timeline.keys())) or _match_title(raw_src, [s["title"] for s in sources])
        status = verdicts.get(i, {}).get("status", "仍开放")
        solver = verdicts.get(i, {}).get("solved_by", "")

        # 校验：solved_by 必须能在实际检索到的证据论文里对上，防止模型编造或反指来源论文
        if solver:
            ns = _norm_title(solver)
            hit = next(
                (t for t in evidence_titles.get(i, [])
                 if ns == _norm_title(t) or ns in _norm_title(t) or _norm_title(t) in ns),
                "",
            )
            solver = hit
        # 判为「已解决」却找不到对应证据时，降级为「部分解决」
        if status == "已解决" and not solver:
            status = "部分解决"

        item = {
            "idea": d,
            "source": src_title,
            "year": timeline.get(src_title, 0),
            "status": status,
            "solved_by": solver,
        }
        (excluded if status == "已解决" else kept).append(item)

    timeline_list = [
        {"title": t, "year": y} for t, y in
        sorted(timeline.items(), key=lambda kv: kv[1])
    ]

    return {
        "answer": answer,
        "directions": kept,
        "excluded": excluded,
        "timeline": timeline_list,
        "sources": sources,
    }
