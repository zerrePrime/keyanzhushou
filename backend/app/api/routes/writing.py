"""写作 Copilot 路由 - 学术框架生成 + Mermaid 架构图"""
from fastapi import APIRouter
from pydantic import BaseModel
from app.rag.qa_service import llm_chat

router = APIRouter(prefix="/api/writing", tags=["writing"])


class FrameworkReq(BaseModel):
    idea: str  # 用户的研究 idea


@router.post("/framework")
async def gen_framework(req: FrameworkReq):
    """根据 idea 生成论文框架"""
    prompt = f"""请为以下研究 idea 生成学术论文框架（1000字以内）：

idea: {req.idea}

框架格式：
1. 标题（中英文）
2. 摘要
3. 引言（研究背景 + 动机 + 贡献点）
4. 相关工作 Related Work（真实可查的参考文献）
5. 方法（模型架构 + 关键算法）
6. 实验设置
7. 结果与分析
8. 结论与未来工作

要求：参考文献要真实存在，不要编造。"""

    return {"framework": llm_chat(prompt)}


class DiagramReq(BaseModel):
    description: str  # 架构描述


@router.post("/diagram")
async def gen_mermaid(req: DiagramReq):
    """生成 Mermaid 架构图代码"""
    prompt = f"""请把下面的架构描述转成 Mermaid flowchart TD 代码。

架构描述: {req.description}

严格规则：
1. 第一行必须是 flowchart TD
2. 节点用 A[中文标签] 或 A(中文) 格式
3. 连线用 --> 或 -->|标签|
4. 不要用 subgraph、classDef 等高级语法
5. 不要用引号、括号、特殊字符作为节点 ID
6. 只输出 Mermaid 代码本身，不要解释不要 markdown"""

    code = llm_chat(prompt, system="你是 Mermaid 代码生成器，只输出有效 Mermaid 代码。")
    # 清理 markdown 代码块标记
    code = code.strip()
    if "```" in code:
        code = code.split("```")[1]
        if code.startswith("mermaid"):
            code = code[7:]
        code = code.strip()
    # 确保以 flowchart 开头
    if not code.startswith("flowchart") and not code.startswith("graph"):
        code = "flowchart TD\n    A[输入] --> B[处理]\n" + code
    return {"mermaid": code.strip()}


class CaptionReq(BaseModel):
    chart_type: str  # 折线图 / 柱状图 / 雷达图
    data_summary: str  # 数据概要


@router.post("/caption")
async def gen_caption(req: CaptionReq):
    """生成学术图表 caption"""
    prompt = f"""请为下面的{req.chart_type}生成学术论文风格的 Figure Caption：

数据概要：{req.data_summary}

要求：英文，80词以内，含图编号、内容描述、关键发现。"""
    return {"caption": llm_chat(prompt, system="你是学术写作专家")}
