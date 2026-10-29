"""
LangGraph Agent API 路由
比赛评分点：Task Planning 动态规划 / Multi-Agent 路由 / Function Calling
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"  # 多轮会话 ID
    history: Optional[list] = None


class AgentChatResponse(BaseModel):
    answer: str
    tool_used: str          # 第一个工具
    all_tools: list         # 所有调用过的工具（多工具串联结果）
    sources: list
    iterations: int          # Agent 循环次数
    thinking: Optional[list] = None
    thinking_trace: Optional[list] = None   # 结构化思考链：每步 意图/工具/查询/结果/耗时
    max_iterations: Optional[int] = 3


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat_endpoint(req: AgentChatRequest):
    """
    Agent 对话接口 - LangGraph 多工具自动串联

    流程：decide → execute → decide → execute → ... → synthesize
    （最多 max_iterations 次循环，防止死循环）
    """
    from app.agent.langgraph_agent import agent_chat
    result = agent_chat(req.message, session_id=req.session_id or "default")

    all_tools = result.get("all_tools", [])
    thinking = [f"迭代 {result.get('iterations', 0)} 轮"]
    for t in all_tools:
        thinking.append(f"🔧 调用工具: {t}")
    thinking.append("✨ 汇总生成最终回答")

    return AgentChatResponse(
        answer=result["answer"],
        tool_used=result.get("tool_used", ""),
        all_tools=all_tools,
        sources=result.get("sources", []),
        iterations=result.get("iterations", 0),
        thinking=thinking,
        thinking_trace=result.get("thinking_trace", []),
        max_iterations=result.get("max_iterations", 3),
    )


@router.get("/tools")
def list_tools():
    """列出 Agent 可用的所有工具（比赛展示 Function Calling）"""
    from app.agent.langgraph_agent import ALL_TOOLS
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "args": list(t.args.keys()) if hasattr(t, "args") else [],
            }
            for t in ALL_TOOLS
        ]
    }


@router.get("/health")
def agent_health():
    """Agent 健康检查"""
    try:
        from app.agent.langgraph_agent import get_agent
        get_agent()
        return {"status": "ok", "agent": "langgraph_stategraph"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
