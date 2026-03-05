from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.requests import Request


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def success_response(
    request: Request,
    *,
    data: object = None,
    meta: dict[str, object] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    content = {
        "request_id": get_request_id(request),
        "data": data if data is not None else {},
        "meta": meta if meta is not None else {},
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content))


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    detail: dict[str, object] | None = None,
    status_code: int,
) -> JSONResponse:
    content = {
        "request_id": get_request_id(request),
        "error": {
            "code": code,
            "message": message,
            "detail": detail if detail is not None else {},
        },
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content))
