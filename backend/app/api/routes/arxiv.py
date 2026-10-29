"""arXiv 检索路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.arxiv_service import search_arxiv, get_daily_papers

router = APIRouter(prefix="/api/arxiv", tags=["arxiv"])


class SearchReq(BaseModel):
    query: str
    max_results: int = 10


@router.post("/search")
async def search(req: SearchReq):
    return {"papers": search_arxiv(req.query, req.max_results)}


@router.get("/daily")
async def daily():
    return {"papers": get_daily_papers()}
