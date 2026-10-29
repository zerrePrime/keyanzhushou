"""RAG 问答路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.rag.qa_service import answer_with_sources, multi_paper_compare, translate_text

router = APIRouter(prefix="/api/qa", tags=["qa"])


class QuestionReq(BaseModel):
    question: str
    mode: str = "single"


class TranslateReq(BaseModel):
    text: str
    target: str = "zh"        # zh = 译成中文, en = 译成英文
    max_segments: int = 12    # 单次最多翻译的段落数，防止整篇请求超时


@router.post("/ask")
async def ask(req: QuestionReq):
    if req.mode == "compare":
        return multi_paper_compare(req.question)
    return answer_with_sources(req.question)


@router.post("/translate")
async def translate(req: TranslateReq):
    """划词 / 整页 / 整篇翻译入口"""
    if req.target not in ("zh", "en"):
        raise HTTPException(status_code=400, detail="target 仅支持 zh / en")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    return translate_text(text[:20000], req.target, max(1, min(req.max_segments, 20)))
