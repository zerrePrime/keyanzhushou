"""
LangGraph Agent 状态机 - 科研助手核心编排

比赛评分点：
- Task Planning 动态规划（多工具自动串联）
- Multi-Agent 路由 / Function Calling
- 多轮对话记忆

流程：
  agent_decide → execute_tool → [再次 decide?] → synthesize → END
                   ↑________ 如果需要多工具，循环 _______↓

支持的工具（7 个 Function Callable Tools）:
  1. rag_qa          - 文献库 RAG 问答
  2. arxiv_search    - arXiv 检索最新论文
  3. graph_analyze   - 引用图谱分析 + 基石论文
  4. auto_survey     - 自动生成领域综述
  5. write_framework - 生成论文框架
  6. list_papers     - 列出文献库所有论文
  7. future_work     - 从结论/展望提取未来研究方向
"""
from typing import TypedDict, Annotated, Literal
import operator
import json
import re
import time
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

from app.rag.qa_service import answer_with_sources, llm_chat, extract_future_work, translate_text
from app.services.arxiv_service import search_arxiv
from app.services.graph_service import build_citation_graph, generate_auto_survey
from app.services.paper_service import list_papers as _svc_list_papers


# ====== 1. Agent 状态 ======
def _merge_dicts(a: dict, b: dict) -> dict:
    """LangGraph dict reducer: 合并两个 dict（后者覆盖前者）"""
    merged = dict(a)
    merged.update(b)
    return merged

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    next_action: str
    next_query: str       # 本轮实际传给工具的查询（可被 Agent 重写）
    next_intent: str      # 本轮选择该工具的理由
    intermediate_results: Annotated[dict, _merge_dicts]
    thinking_trace: Annotated[list, operator.add]  # 思考链：每一步的决策与执行记录
    final_answer: str
    direct_answer: str  # 通用知识问题的直接回答（不经过工具）
    max_iterations: int  # 防止死循环
    iteration: int


# ====== 2. LangChain Tools（Function Calling 格式） ======

# 缓存最近一次 rag_qa 的溯源信息，供 agent_chat 直接复用（避免重复跑一次完整问答）
_rag_sources_cache = {}


@tool
def rag_qa(query: str) -> str:
    """在本地文献库中检索回答问题，带原文溯源。当用户问关于已上传论文的内容时用这个。"""
    result = answer_with_sources(query)
    sources = result.get("sources", [])
    _rag_sources_cache["sources"] = sources
    sources_str = "\n".join(
        f"  - {s.get('title','?')} p{s.get('page','?')}"
        for s in sources
    )
    return f"答案：{result['answer']}\n来源：\n{sources_str}"


@tool
def arxiv_search(query: str) -> str:
    """在 arXiv 上搜索最新论文。当用户问最新研究进展、前沿方向、外部论文时用这个。"""
    papers = search_arxiv(query, max_results=5)
    if not papers or (len(papers) == 1 and "error" in papers[0]):
        return f"arXiv 搜索失败: {papers[0].get('error','未知错误') if papers else '无结果'}"
    lines = [f"- [{p['arxiv_id']}] {p['title']} ({', '.join(p['authors'][:3])})" for p in papers]
    return f"找到 {len(papers)} 篇最新论文：\n" + "\n".join(lines)


@tool
def graph_analyze() -> str:
    """分析引用图谱，找出领域基石论文和引用关系。当用户问哪些是核心论文、领域脉络时用这个。"""
    graph = build_citation_graph()
    top = graph.get("top_cited", [])
    if not top:
        return "文献库为空，无法分析图谱。请先上传论文。"
    lines = [f"- {p['title']} (PageRank: {p['pagerank']}, 入度: {p.get('in_degree','?')})"
             for p in top[:5]]
    return f"基石论文 Top 5：\n" + "\n".join(lines)


@tool
def auto_survey() -> str:
    """基于文献库自动生成领域综述。当用户要求总结领域现状、写综述、介绍研究方向时用这个。"""
    return generate_auto_survey()


@tool
def write_framework(idea: str) -> str:
    """根据研究 idea 生成学术论文框架（标题、摘要、引言、相关工作、方法、实验、结论）。"""
    prompt = f"""请为以下研究 idea 生成学术论文框架（800字以内）：

idea: {idea}

框架格式：标题、摘要、引言、相关工作、方法、实验、结论。"""
    return llm_chat(prompt)


@tool
def list_papers() -> str:
    """列出本地文献库中已有的所有论文。当用户问文献库有什么论文时用这个。"""
    papers = _svc_list_papers()
    if not papers:
        return "文献库为空"
    return "文献库论文列表：\n" + "\n".join(f"- [{p['paper_id']}] {p['title']}" for p in papers)


@tool
def future_work(query: str) -> str:
    """从文献库论文的结论、局限性与展望中提取未来研究方向。当用户问论文的不足、未来工作、可研究方向、选题灵感、limitations 时用这个。"""
    result = extract_future_work(query)
    kept = result.get("directions") or []
    excluded = result.get("excluded") or []
    if not kept and not excluded:
        return result.get("answer", "未找到相关内容")
    lines = "\n".join(
        f"{i+1}. {d['idea'].split('【')[0].strip()}"
        + (f"【{d['source']} {d['year']}】" if d.get("source") and d.get("year") else "")
        + f" 状态：{d['status']}"
        + (f"（已由 {d['solved_by']} 部分解决）" if d.get("solved_by") else "")
        for i, d in enumerate(kept)
    )
    tail = ""
    if excluded:
        tail = "\n已被后续工作解决、已排除的旧方向：" + "；".join(
            e["idea"].split("【")[0].strip() for e in excluded
        )
    srcs = "；".join(f"{s.get('title','?')} p{s.get('page','?')}" for s in result.get("sources", [])[:3])
    return f"未来研究方向：\n{lines}{tail}\n来源：{srcs}"


@tool
def translate(query: str) -> str:
    """把一段文本翻译成中文或英文。query 格式：'翻译方向 | 要翻译的文本'，方向填 'zh' 或 'en'，也接受自然语言如 '译成中文'/'翻译成英文'。"""
    try:
        text = query
        target = "zh"
        # 解析方向
        m = re.match(r"^\s*(zh|en)\s*[|：:\s]+(.+)$", query, re.I)
        if m:
            target = m.group(1).lower()
            text = m.group(2)
        else:
            low = query.lower()
            if "译为英文" in query or "翻译成英文" in query or "译成英文" in query or "translate to english" in low or "to en" in low:
                target = "en"
            elif "译成中文" in query or "翻译成中文" in query or "译成中文" in query or "translate to chinese" in low or "to zh" in low:
                target = "zh"
        text = text.strip().strip("'\"“”")
        if not text:
            return "翻译失败：文本为空"
        result = translate_text(text, target=target, max_segments=6)
        return result.get("text", "翻译失败")
    except Exception as e:
        return f"翻译失败: {str(e)[:200]}"


ALL_TOOLS = [rag_qa, arxiv_search, graph_analyze, auto_survey, write_framework, list_papers, future_work, translate]
TOOLS_MAP = {t.name: t for t in ALL_TOOLS}


# ====== 3. Agent 决策（Task Planning / ReAct） ======
def _parse_decision(raw: str, remain: list, done_tools: list, user_input: str) -> tuple:
    """
    鲁棒解析 LLM 的决策输出，返回 (action, query, intent)
    本地 7B 模型输出不稳定，需要多级兜底，避免死循环
    """
    text = (raw or "").replace("```json", "").replace("```", "").strip()
    action, query, intent = "", "", ""

    # 优先按 JSON 解析
    m = re.search(r"\{.*?\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            action = str(obj.get("action", "")).strip()
            query = str(obj.get("query", "")).strip()
            intent = str(obj.get("intent", "")).strip()
        except Exception:
            pass

    # JSON 解析失败 → 从纯文本里找工具名
    if not action:
        for name in remain:
            if name in text:
                action = name
                break
        if not action and "FINISH" in text.upper():
            action = "FINISH"

    # 归一化 FINISH / DIRECT
    if action.upper() == "FINISH":
        return "FINISH", "", intent or "信息已充足，可以汇总"
    if action.upper() == "DIRECT":
        return "DIRECT", "", intent or "通用知识问题，直接回答"
    if not action and "DIRECT" in text.upper():
        return "DIRECT", "", intent or "通用知识问题，直接回答"

    # 工具名非法（未知名 / 已执行过）→ 分级兜底
    if action not in remain:
        if not done_tools and "rag_qa" in remain:
            return "rag_qa", user_input, intent or "默认使用文献库检索"
        # 已有结果却决策异常 → 强制终止，避免死循环
        return "FINISH", "", intent or "决策异常，直接汇总已有结果"

    if not query:
        query = user_input
    if not intent:
        intent = f"调用 {action} 补充信息"
    return action, query, intent


def agent_decide(state: AgentState) -> AgentState:
    """
    Agent 核心决策：基于用户请求 + 已执行工具的结果，决定下一步
    - 信息足够 → FINISH
    - 还缺信息 → 选一个未执行过的工具，并重写查询语句
    """
    user_input = state["messages"][0] if state["messages"] else ""
    results = state.get("intermediate_results", {})
    done_tools = list(results.keys())
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 3)
    step_no = iteration + 1

    # 终止条件 A：已达最大轮数
    if iteration >= max_iter:
        return {
            "next_action": "FINISH",
            "thinking_trace": [{
                "step": step_no, "intent": f"已达最大 {max_iter} 轮工具调用，开始汇总",
                "tool": "FINISH", "query": "", "output_summary": "",
                "elapsed_ms": 0, "status": "finish",
            }],
        }

    # 终止条件 B：所有工具都执行过了
    remain = [t.name for t in ALL_TOOLS if t.name not in done_tools]
    if not remain:
        return {
            "next_action": "FINISH",
            "thinking_trace": [{
                "step": step_no, "intent": "全部工具已执行完毕，开始汇总",
                "tool": "FINISH", "query": "", "output_summary": "",
                "elapsed_ms": 0, "status": "finish",
            }],
        }

    # 终止条件 C（最小必要工具原则）：简单信息类问题，一次库内检索即可回答，
    # 不再额外调用图谱/综述等重工具，避免过度规划拖慢响应并浪费 token
    MULTI_STEP_HINTS = ("分析", "关系", "图谱", "综述", "未来", "方向", "检索", "最新",
                        "对比", "演进", "多篇", "脉络", "翻译", "译文", "译为",
                        "limitation", "limitations", "不足", "局限")
    if "rag_qa" in done_tools and not any(h in user_input for h in MULTI_STEP_HINTS):
        return {
            "next_action": "FINISH",
            "thinking_trace": [{
                "step": step_no, "intent": "已获得文献依据，问题不要求多步分析",
                "tool": "FINISH", "query": "", "output_summary": "",
                "elapsed_ms": 0, "status": "finish",
            }],
        }

    # 拼装已执行结果摘要，供 LLM 判断下一步
    history = ""
    if results:
        parts = [f"[{name}] {str(res)[:200]}" for name, res in results.items()]
        history = "已执行工具及结果摘要：\n" + "\n".join(parts) + "\n"

    tool_descs = "\n".join(f"  {t.name}: {t.description}" for t in ALL_TOOLS if t.name in remain)

    prompt = f"""你是科研助手 Agent，正在执行 ReAct 式多步任务规划。

用户请求：{user_input}

{history}
本轮还可选择的工具（不要选已执行过的）：
{tool_descs}

请判断下一步：
- 用户的问题是通用知识/概念解释类（如「XX 是什么」「XX 有哪些方法」），与本地文献库内容无直接关系，也不需要查最新论文 → action 填 "DIRECT"
- 现有信息已足够回答 → action 填 "FINISH"（**默认优先选这条**）
- 遵循「最小必要工具」原则：已执行结果足以回答就必须 FINISH，不要为了"更全面"再多调工具
- 只有当用户明确要求引用图谱、综述、未来方向、最新论文、翻译等**多步分析**时，才继续选下一个工具
- 严禁调用与当前问题无关的工具（例如用户只是要总结单篇论文贡献时，不要调 auto_survey）
- 还缺文献库/图谱/arXiv 信息 → 从上面选一个工具继续补充

**同义词路由**（query 里要体现）：
- limitation / limitations / 不足 / 局限 / 展望 → 调用 future_work
- 翻译 / translate / 译为 / 译文 → 调用 translate
- 最新 / 年份（如 2024、2025）/ 新论文 → 调用 arxiv_search

严格按要求输出 JSON，不要任何其他文字：
{{"action": "工具名或FINISH或DIRECT", "query": "传给该工具的查询语句", "intent": "选择它的理由，15字以内"}}

注意：query 应结合已获得的结果重新组织，不要照抄用户原句。"""

    raw = llm_chat(prompt, system="你是任务规划器，只输出一个 JSON 对象，不要任何解释。").strip()
    action, query, intent = _parse_decision(raw, remain, done_tools, user_input)

    # 兜底：尚无任何工具结果时 FINISH 没有内容可汇总（如指代型追问「那它呢」），
    # 强制先检索本地文献库，避免直接返回空回答
    if action == "FINISH" and not results:
        action, query, intent = "rag_qa", user_input, "无历史结果，先检索文献库"

    # 通用知识问题：不经过工具，直接用模型自身知识回答
    if action == "DIRECT":
        direct = llm_chat(
            user_input,
            system="你是严谨的科研助手。用简洁清晰的中文回答这个通用知识问题（3-6 句话），不确定时说不知道，不要假装引用了任何文献。",
        )
        return {
            "next_action": "FINISH",
            "next_query": "",
            "next_intent": intent,
            "iteration": step_no,
            "messages": ["[Agent 决策] DIRECT 直接回答"],
            "direct_answer": direct,
            "thinking_trace": [{
                "step": step_no, "intent": intent or "通用知识问题，直接回答",
                "tool": "DIRECT", "query": "", "output_summary": "",
                "elapsed_ms": 0, "status": "finish",
            }],
        }

    result = {
        "next_action": action,
        "next_query": query,
        "next_intent": intent,
        "iteration": step_no,
        "messages": [f"[Agent 决策] {action}"],
    }
    # FINISH 不会进入 execute，这里补一条思考链记录
    if action == "FINISH":
        result["thinking_trace"] = [{
            "step": step_no, "intent": intent or "信息已充足",
            "tool": "FINISH", "query": "", "output_summary": "",
            "elapsed_ms": 0, "status": "finish",
        }]
    return result


# ====== 4. 工具执行 ======
def execute_tool(state: AgentState) -> AgentState:
    tool_name = state.get("next_action", "")
    user_input = state["messages"][0] if state["messages"] else ""
    query = state.get("next_query") or user_input
    intent = state.get("next_intent", "")
    step_no = state.get("iteration", 1)

    if tool_name == "FINISH":
        return {"messages": ["[信息充足，跳过执行]"]}

    tool = TOOLS_MAP.get(tool_name)
    if not tool:
        return {"messages": [f"[工具不存在: {tool_name}]"]}

    t0 = time.time()
    status = "ok"
    try:
        # 按工具签名精确构造参数，避免多余键导致校验失败
        kwargs = {}
        if "query" in tool.args:
            kwargs["query"] = query
        if "idea" in tool.args:
            kwargs["idea"] = query
        result = tool.invoke(kwargs)
    except Exception as e:
        result = f"[工具执行错误: {e}]"
        status = "error"
    elapsed = int((time.time() - t0) * 1000)

    summary = " ".join(str(result).split())[:180]
    full = str(result)[:2000]

    return {
        "messages": [f"[{tool_name} 结果] {summary}"],
        "intermediate_results": {tool_name: result},
        "thinking_trace": [{
            "step": step_no,
            "intent": intent or f"调用 {tool_name} 补充信息",
            "tool": tool_name,
            "query": query,
            "output_summary": summary,
            "output_full": full,
            "elapsed_ms": elapsed,
            "status": status,
        }],
    }


# ====== 5. 路由：继续循环还是汇总？ ======
def should_continue(state: AgentState) -> str:
    """决定下一步：再调一次 decide 还是进入 synthesize"""
    action = state.get("next_action", "")
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 3)

    if action == "FINISH" or iteration >= max_iter:
        return "synthesize"
    return "decide"


# ====== 6. 汇总 ======
def synthesize(state: AgentState) -> AgentState:
    results = state.get("intermediate_results", {})
    user_input = state["messages"][0] if state["messages"] else ""

    if not results:
        direct = state.get("direct_answer")
        if direct:
            return {"final_answer": direct}
        return {"final_answer": "未能在本地文献库中找到与该问题相关的内容。可以换一种问法，或先上传相关论文后再试。"}

    context = "\n\n".join(f"[{name}]\n{res}" for name, res in results.items())
    tools_used = " → ".join(results.keys())
    tool_count = len(results)

    prompt = f"""基于以下工具执行结果，用自然语言回答用户问题。

用户问题：{user_input}

本次共串联调用 {tool_count} 个工具：{tools_used}

工具结果：
{context}

要求：
1. 用简洁清晰的中文回答（3-6 句话）
2. 如果 rag_qa 有来源/页码，明确标出
3. 不要编造工具结果里没有的信息
4. 如果涉及多篇论文，说清楚各自的关键信息
5. 若多个工具的结果存在互补关系，请在回答中体现综合结论"""

    answer = llm_chat(prompt)
    return {"final_answer": answer}


# ====== 7. 状态机构建 ======
def build_agent_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("decide", agent_decide)
    workflow.add_node("execute", execute_tool)
    workflow.add_node("synthesize", synthesize)

    workflow.set_entry_point("decide")
    workflow.add_edge("decide", "execute")
    workflow.add_conditional_edges("execute", should_continue, {
        "decide": "decide",       # 继续循环调工具
        "synthesize": "synthesize",
    })
    workflow.add_edge("synthesize", END)

    return workflow.compile()


# ====== 8. 对外接口 ======
_agent_graph = None

def get_agent():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph


# 多轮对话内存（进程内简单实现）
_conversation_memory = {}
MAX_HISTORY_PER_USER = 10


def agent_chat(user_input: str, session_id: str = "default") -> dict:
    """
    Agent 对话接口（支持多工具串联 + 多轮记忆）

    返回：{"answer", "tool_used", "all_tools", "sources", "iterations", "thinking_trace"}
    """
    # 多轮记忆：把历史摘要塞进第一句 messages
    history = _conversation_memory.get(session_id, [])
    history_context = ""
    if history:
        history_context = f"（上下文：{'; '.join(history[-3:])}）"
        full_input = f"{user_input}{history_context}"
    else:
        full_input = user_input

    # 清空上一轮的溯源缓存，避免串轮
    _rag_sources_cache.pop("sources", None)

    max_iterations = 3
    agent = get_agent()

    try:
        result = agent.invoke({
            "messages": [full_input],
            "next_action": "",
            "next_query": "",
            "next_intent": "",
            "intermediate_results": {},
            "thinking_trace": [],
            "final_answer": "",
            "direct_answer": "",
            "max_iterations": max_iterations,
            "iteration": 0,
        })
    except Exception as e:
        return {
            "answer": f"抱歉，Agent 执行过程出现异常：{e}",
            "tool_used": "",
            "all_tools": [],
            "sources": [],
            "iterations": 0,
            "thinking_trace": [],
        }

    # 记录到多轮记忆
    _conversation_memory.setdefault(session_id, []).append(user_input)
    if len(_conversation_memory[session_id]) > MAX_HISTORY_PER_USER:
        _conversation_memory[session_id] = _conversation_memory[session_id][-MAX_HISTORY_PER_USER:]

    # 溯源信息直接复用 rag_qa 工具执行时的结果，不再重复调用一次问答
    sources = _rag_sources_cache.get("sources", []) if "rag_qa" in result.get("intermediate_results", {}) else []
    _rag_sources_cache.pop("sources", None)

    all_tools = list(result.get("intermediate_results", {}).keys())
    trace = result.get("thinking_trace", []) or []

    return {
        "answer": result.get("final_answer", "无回答"),
        "tool_used": all_tools[0] if all_tools else "",
        "all_tools": all_tools,
        "sources": sources,
        "iterations": result.get("iteration", 0),
        "thinking_trace": trace,
        "max_iterations": max_iterations,
    }
