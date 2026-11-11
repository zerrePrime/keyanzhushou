"""登录鉴权：签名 Cookie 会话

替代 nginx Basic Auth 原生弹框，改为可定制的登录页。
会话态存在 HttpOnly Cookie 中，由 HMAC 签名，服务端无需存储。
"""
import base64
import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginReq(BaseModel):
    username: str
    password: str


def _sign(payload: str) -> str:
    sig = hmac.new(
        settings.AUTH_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def _verify(token: str | None) -> str | None:
    """校验 Cookie，返回用户名；无效返回 None"""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = raw.rsplit(".", 1)
        expect = hmac.new(
            settings.AUTH_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        username, expire = payload.split(":", 1)
        if int(expire) < int(time.time()):
            return None
        return username
    except Exception:
        return None


def current_user(request: Request) -> str | None:
    return _verify(request.cookies.get(settings.AUTH_COOKIE))


@router.post("/login")
def login(req: LoginReq, response: Response):
    if not settings.APP_PASSWORD:
        raise HTTPException(status_code=503, detail="服务端未配置登录密码")

    ok_user = hmac.compare_digest(req.username, settings.APP_USERNAME)
    ok_pwd = hmac.compare_digest(req.password, settings.APP_PASSWORD)
    if not (ok_user and ok_pwd):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    payload = f"{req.username}:{int(time.time()) + settings.AUTH_MAX_AGE}"
    response.set_cookie(
        settings.AUTH_COOKIE,
        _sign(payload),
        max_age=settings.AUTH_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"username": req.username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.AUTH_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"username": user}
