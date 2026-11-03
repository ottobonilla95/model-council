"""Google OIDC sign-in through Authlib; app sessions are opaque and server-revocable."""

import os
import secrets
from typing import Literal
from urllib.parse import urlparse

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from . import accounts, config

router = APIRouter()
COOKIE = "parallax_login"
LOCAL_USER = {"id": None, "email": "", "name": "Local workspace", "role": "admin", "active": 1}
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
)


def required():
    return config.hosted() or bool(os.getenv("GOOGLE_CLIENT_ID")) or os.getenv("PARALLAX_REQUIRE_AUTH") == "1"


def base_url():
    value = os.getenv("APP_BASE_URL", "http://127.0.0.1:8310").rstrip("/")
    parsed = urlparse(value)
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return ""
    if config.hosted() and parsed.scheme != "https":
        return ""
    return value if parsed.netloc and parsed.scheme in ("http", "https") else ""


def configured():
    return bool(
        os.getenv("GOOGLE_CLIENT_ID")
        and os.getenv("GOOGLE_CLIENT_SECRET")
        and len(os.getenv("APP_SESSION_SECRET", "")) >= 32
        and accounts.owner_email()
        and base_url()
    )


def current_user(request: Request):
    if not required():
        return LOCAL_USER
    if not configured():
        raise HTTPException(503, "Sign-in is being configured. Please try again shortly.")
    token = request.cookies.get(COOKIE, "")
    user = accounts.session_user(token)
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), accounts.csrf_token(token)):
            raise HTTPException(403, "Your session needs refreshing. Reload the page and try again.")
    return user


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access is required.")
    return user


@router.get("/api/auth/me")
def me(request: Request):
    user = accounts.session_user(request.cookies.get(COOKIE, "")) if required() else LOCAL_USER
    return {
        "required": required(),
        "configured": configured(),
        "user": user,
        "csrf_token": accounts.csrf_token(request.cookies[COOKIE]) if user and required() else "",
        "allow_signup": os.getenv("PARALLAX_ALLOW_SIGNUP", "1") == "1",
    }


@router.get("/auth/google")
async def google_login(request: Request):
    if not configured():
        return RedirectResponse("/?auth_error=configuration", status_code=303)
    canonical = base_url()
    if str(request.base_url).rstrip("/") != canonical:
        return RedirectResponse(canonical + "/auth/google", status_code=303)
    return await oauth.google.authorize_redirect(request, canonical + "/auth/google/callback", prompt="select_account")


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    if not configured():
        return RedirectResponse("/?auth_error=configuration", status_code=303)
    try:
        # Authlib validates state, issuer, audience, signature, exp and nonce.
        token = await oauth.google.authorize_access_token(request)
        user = accounts.from_google(token.get("userinfo") or {})
    except ValueError as error:
        request.session.clear()
        message = str(error)
        code = "disabled" if "disabled" in message else "invite" if "create your account" in message else "verification"
        return RedirectResponse("/?auth_error=" + code, status_code=303)
    except Exception:
        request.session.clear()
        return RedirectResponse("/?auth_error=signin", status_code=303)
    request.session.clear()
    session_token = accounts.new_session(user["id"])
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE,
        session_token,
        max_age=accounts.SESSION_SECONDS,
        httponly=True,
        secure=base_url().startswith("https://"),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/api/auth/logout")
def logout(request: Request, user=Depends(current_user)):
    accounts.revoke_session(request.cookies.get(COOKIE, ""))
    request.session.clear()
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


class NewUser(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=120)


class UserAccess(BaseModel):
    role: Literal["user", "admin"]
    active: bool


@router.get("/api/admin/users")
def users(user=Depends(admin)):
    return {"users": accounts.list_users(), "owner_email": accounts.owner_email()}


@router.post("/api/admin/users", status_code=201)
def create_user(values: NewUser, user=Depends(admin)):
    try:
        return accounts.create_user(str(values.email).strip().lower(), values.name.strip())
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


@router.patch("/api/admin/users/{user_id}")
def update_user(user_id: str, values: UserAccess, user=Depends(admin)):
    try:
        return accounts.update_user(user_id, user["id"], values.role, values.active)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
