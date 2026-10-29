"""FastAPI 主入口 - 挂载所有路由 + CORS"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from app.api.routes import papers, qa, arxiv, graph, writing, agent, csv
app.include_router(papers.router)
app.include_router(qa.router)
app.include_router(arxiv.router)
app.include_router(graph.router)
app.include_router(writing.router)
app.include_router(agent.router)
app.include_router(csv.router)


@app.get("/")
def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=True)
