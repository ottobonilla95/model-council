import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import accounts, auth, config, storage
from .engine import execute_run
from .schemas import RunRequest

TASKS = {}


@asynccontextmanager
async def lifespan(app):
    storage.init()
    yield
    active = list(TASKS.values())
    for task in active:
        task.cancel()
    await asyncio.gather(*active, return_exceptions=True)


app = FastAPI(title="Parallax", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts())
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("APP_SESSION_SECRET") or secrets.token_urlsafe(48),
    session_cookie="parallax_oauth",
    max_age=600,
    same_site="lax",
    https_only=auth.base_url().startswith("https://"),
)
app.include_router(auth.router)


@app.middleware("http")
async def local_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Open the app directly on its own domain to make changes."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.get("/api/config")
def app_config(user=Depends(auth.current_user)):
    credentials = config.keys()
    return {
        "keys": {name: bool(value) for name, value in credentials.items()},
        "managed_credentials": config.hosted(),
        "models": config.DEFAULT_MODELS,
        "judge": config.DEFAULT_MODELS[0]["id"],
        "chat_model": "google/gemini-3.8-flash",
        "search_provider": "tavily" if credentials["tavily"] else "openrouter",
        "limits": {
            "standard": {"model_calls": 6, "tool_calls": 6, "seconds": 180},
            "deep": {"model_calls": 12, "tool_calls": 24, "seconds": 360},
        },
    }


class Credentials(BaseModel):
    openrouter: str = Field(default="", max_length=500)
    tavily: str = Field(default="", max_length=500)


@app.post("/api/settings")
def settings(values: Credentials, user=Depends(auth.current_user)):
    if any(values.model_dump().values()) and user["role"] != "admin":
        raise HTTPException(403, "Only an administrator can change provider keys.")
    try:
        config.save_keys(values.model_dump())
    except ValueError as error:
        raise HTTPException(403, str(error)) from None
    return app_config(user)


@app.get("/api/models")
async def models(user=Depends(auth.current_user)):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
        return {
            "models": [
                {"id": m["id"], "name": m["name"]}
                for m in response.json()["data"]
                if "tools" in m.get("supported_parameters", []) and ":batch" not in m["id"]
            ]
        }
    except (httpx.HTTPError, KeyError):
        return {"models": config.DEFAULT_MODELS, "warning": "Could not refresh catalog; showing configured defaults."}


@app.get("/api/sessions")
def sessions(user=Depends(auth.current_user)):
    storage.expire_abandoned()
    return storage.sessions(user["id"])


@app.get("/api/sessions/{session_id}")
def session(session_id: str, user=Depends(auth.current_user)):
    if not storage.owns_session(session_id, user["id"]):
        raise HTTPException(404, "Conversation not found.")
    return [{**run, "events": storage.events(run["id"])} for run in storage.session_runs(session_id)]


@app.post("/api/runs", status_code=201)
async def start(request: RunRequest, user=Depends(auth.current_user)):
    storage.expire_abandoned()
    credentials = config.keys()
    if request.session_id and not storage.owns_session(request.session_id, user["id"]):
        raise HTTPException(404, "Conversation not found.")
    if not request.demo and not credentials["openrouter"]:
        location = "Vercel environment variables" if config.hosted() else "Settings"
        raise HTTPException(400, f"Add your OpenRouter key in {location} to start chatting.")
    histories = (
        {model: storage.research_history(request.session_id, model) for model in request.models}
        if request.session_id and not request.fresh
        else {}
    )
    try:
        run_id, session_id = storage.create_run(request, user["id"])
    except storage.OwnershipError as error:
        raise HTTPException(404, str(error)) from None
    except storage.CapacityError as error:
        raise HTTPException(429, str(error)) from None
    except storage.SessionBusyError as error:
        raise HTTPException(409, str(error)) from None
    storage.event(run_id, {"type": "started", "models": request.models, "demo": request.demo})
    if config.hosted():
        from .jobs import enqueue

        try:
            await enqueue(run_id)
        except Exception:
            storage.finish(run_id, "failed", terminal={"type": "error", "message": "Could not queue this round. Please try again."})
            raise HTTPException(503, "Could not queue this round. Please try again.") from None
    else:
        task = asyncio.create_task(execute_run(request, run_id, credentials, histories))
        TASKS[run_id] = task
        task.add_done_callback(lambda _: TASKS.pop(run_id, None))
    return {"run_id": run_id, "session_id": session_id}


@app.get("/api/runs/{run_id}")
def run(run_id: str, user=Depends(auth.current_user)):
    storage.expire_abandoned()
    saved = storage.get_run(run_id)
    if not saved or not storage.owns_session(saved["session_id"], user["id"]):
        raise HTTPException(404, "Round not found.")
    return {**saved, "events": storage.events(run_id)}


@app.post("/api/runs/{run_id}/cancel")
async def cancel(run_id: str, user=Depends(auth.current_user)):
    saved = storage.get_run(run_id)
    if not saved or not storage.owns_session(saved["session_id"], user["id"]):
        raise HTTPException(404, "Round not found.")
    if config.hosted():
        storage.finish(
            run_id,
            "cancelled",
            {"reports": list(storage.completed_reports(run_id).values())},
            terminal={"type": "cancelled", "message": "Round stopped. Completed answers have been saved."},
        )
    task = TASKS.get(run_id)
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def stream(run_id: str, request: Request, after: int = 0, user=Depends(auth.current_user)):
    saved = storage.get_run(run_id)
    if not saved or not storage.owns_session(saved["session_id"], user["id"]):
        raise HTTPException(404, "Round not found.")
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        cursor = after

    async def generate():
        nonlocal cursor
        while not await request.is_disconnected():
            if auth.required() and not await asyncio.to_thread(accounts.session_user, request.cookies.get(auth.COOKIE, "")):
                break
            for event in await asyncio.to_thread(storage.events, run_id, cursor):
                cursor = event["id"]
                yield f"id: {cursor}\ndata: {json.dumps(event['payload'])}\n\n"
            if (await asyncio.to_thread(storage.get_run, run_id))["status"] != "running":
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}/export")
def export(run_id: str, user=Depends(auth.current_user)):
    saved = run(run_id, user)
    return JSONResponse(saved, headers={"Content-Disposition": f'attachment; filename="parallax-{run_id[:8]}.json"'})


DIST = config.ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def index():
    if not DIST.exists():
        return JSONResponse({"message": "Build the interface first: cd frontend && npm install && npm run build"}, status_code=503)
    return FileResponse(DIST / "index.html")


@app.get("/privacy")
def privacy():
    return FileResponse(DIST / "privacy.html")
