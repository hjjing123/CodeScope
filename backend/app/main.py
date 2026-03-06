from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings
from app.core.errors import AppError
from app.core.response import error_response, success_response
from app.services.runtime_log_service import (
    append_runtime_log,
    build_request_runtime_detail,
    infer_error_code_from_payload,
    normalize_level_for_status,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CodeScope Backend", version="0.1.0")
    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    frontend_assets = frontend_dist / "assets"
    frontend_index = frontend_dist / "index.html"
    frontend_favicon = frontend_dist / "favicon.ico"
    frontend_icon = frontend_dist / "vite.svg"
    frontend_dev_url = os.getenv("FRONTEND_DEV_URL", "").rstrip("/")
    frontend_dev_port = os.getenv("FRONTEND_DEV_PORT", "").strip()

    if frontend_assets.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(frontend_assets)),
            name="frontend-assets",
        )

    def serve_frontend_index():
        if frontend_index.exists():
            return FileResponse(frontend_index)
        return PlainTextResponse(
            "Frontend build not found. Run `npm run build` in the frontend directory.",
            status_code=503,
        )

    def resolve_frontend_dev_base(request: Request):
        if frontend_dev_url:
            return frontend_dev_url
        if frontend_dev_port:
            host = request.url.hostname or "127.0.0.1"
            return f"{request.url.scheme}://{host}:{frontend_dev_port}"
        return ""

    def proxy_frontend_dev(request: Request, path: str):
        frontend_dev_base = resolve_frontend_dev_base(request)
        if not frontend_dev_base:
            return None
        query = f"?{request.url.query}" if request.url.query else ""
        target = f"{frontend_dev_base}{path}{query}"
        headers = {
            "Accept": request.headers.get("accept", "*/*"),
            "User-Agent": request.headers.get("user-agent", "CodeScope-DevProxy"),
        }
        cookie_header = request.headers.get("cookie")
        if cookie_header:
            headers["Cookie"] = cookie_header
        proxy_request = urllib.request.Request(url=target, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(proxy_request, timeout=10) as upstream:
                body = upstream.read()
                response_headers = {
                    key: value
                    for key, value in upstream.headers.items()
                    if key.lower() not in {"transfer-encoding", "connection"}
                }
                return Response(
                    content=body,
                    status_code=upstream.getcode(),
                    headers=response_headers,
                )
        except urllib.error.HTTPError as exc:
            error_body = exc.read()
            response_headers = {
                key: value
                for key, value in exc.headers.items()
                if key.lower() not in {"transfer-encoding", "connection"}
            }
            return Response(content=error_body, status_code=exc.code, headers=response_headers)
        except urllib.error.URLError:
            return PlainTextResponse(
                "Frontend dev server unavailable. Check `npm run dev` status.",
                status_code=502,
            )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        start = time.perf_counter()
        response = None
        status_code = 500
        error_code: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code

            raw_body = getattr(response, "body", None)
            if isinstance(raw_body, (bytes, bytearray)) and raw_body:
                try:
                    payload = json.loads(raw_body)
                    error_code = infer_error_code_from_payload(payload)
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    error_code = None
        except Exception:
            error_code = "INTERNAL_SERVER_ERROR"
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            detail_json = build_request_runtime_detail(
                method=request.method,
                path=request.url.path,
                query=request.url.query,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
            )
            db_for_runtime = getattr(request.state, "db_session", None)
            if db_for_runtime is not None:
                append_runtime_log(
                    level=normalize_level_for_status(status_code),
                    service="api",
                    module="http",
                    event="api.request.completed",
                    message=f"{request.method} {request.url.path} -> {status_code}",
                    request_id=request_id,
                    operator_user_id=getattr(request.state, "operator_user_id", None),
                    status_code=status_code,
                    duration_ms=duration_ms,
                    error_code=error_code,
                    detail_json=detail_json,
                    db=db_for_runtime,
                )

        if response is None:
            response = PlainTextResponse("Internal Server Error", status_code=500)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return error_response(
            request,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return error_response(
            request,
            code="INVALID_ARGUMENT",
            message="请求参数校验失败",
            detail={"errors": exc.errors()},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _exc: Exception):
        return error_response(
            request,
            code="INTERNAL_SERVER_ERROR",
            message="服务器内部错误",
            status_code=500,
        )

    @app.get("/healthz")
    def healthz(request: Request):
        return success_response(
            request, data={"status": "ok", "api_prefix": settings.api_prefix}
        )

    @app.get("/", include_in_schema=False)
    def root_entry(request: Request):
        target = "/dashboard" if request.cookies.get("token") else "/login"
        return RedirectResponse(url=target, status_code=302)

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        dev_proxy = proxy_frontend_dev(request, "/login")
        if dev_proxy:
            return dev_proxy
        return serve_frontend_index()

    @app.get("/register", include_in_schema=False)
    def register_page(request: Request):
        dev_proxy = proxy_frontend_dev(request, "/register")
        if dev_proxy:
            return dev_proxy
        return serve_frontend_index()

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_page(request: Request):
        dev_proxy = proxy_frontend_dev(request, "/dashboard")
        if dev_proxy:
            return dev_proxy
        return serve_frontend_index()

    @app.get("/vite.svg", include_in_schema=False)
    def favicon_page(request: Request):
        dev_proxy = proxy_frontend_dev(request, "/vite.svg")
        if dev_proxy:
            return dev_proxy
        if frontend_icon.exists():
            return FileResponse(frontend_icon)
        return PlainTextResponse("Not Found", status_code=404)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_ico_page(request: Request):
        dev_proxy = proxy_frontend_dev(request, "/favicon.ico")
        if dev_proxy:
            return dev_proxy
        if frontend_favicon.exists():
            return FileResponse(frontend_favicon)
        return PlainTextResponse("Not Found", status_code=404)

    app.include_router(api_router)

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_spa_fallback(request: Request, full_path: str):
        normalized_path = full_path.strip("/")
        if normalized_path == "api" or normalized_path.startswith("api/"):
            return PlainTextResponse("Not Found", status_code=404)

        dev_proxy = proxy_frontend_dev(request, f"/{normalized_path}")
        if dev_proxy:
            return dev_proxy

        if "." in Path(normalized_path).name:
            return PlainTextResponse("Not Found", status_code=404)

        return serve_frontend_index()

    return app


app = create_app()
