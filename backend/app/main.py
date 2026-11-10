"""FastAPI 主入口 - 挂载所有路由 + CORS + 登录鉴权"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.api.routes import auth

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 登录前可访问的接口
PUBLIC_API = {"/api/auth/login", "/api/auth/logout", "/api/auth/me"}


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """除登录相关接口外，所有 /api/* 必须携带有效会话 Cookie"""
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API:
        if not auth.current_user(request):
            return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
    return await call_next(request)


# 注册路由
from app.api.routes import papers, qa, arxiv, graph, writing, agent, csv
app.include_router(auth.router)
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
