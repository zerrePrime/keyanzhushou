"""引用图谱路由"""
from fastapi import APIRouter
from app.services.graph_service import build_citation_graph, generate_auto_survey

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/citation")
async def citation_graph():
    return build_citation_graph()


@router.get("/survey")
async def survey():
    return {"survey": generate_auto_survey()}
