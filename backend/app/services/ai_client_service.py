from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Iterator
from typing import Any, Callable

import httpx

from app.core.errors import AppError


@dataclass(slots=True)
class AIChatResult:
    content: str
    raw_payload: dict[str, object]


@dataclass(slots=True)
class AIChatStreamChunk:
    content: str
    raw_payload: dict[str, object]
    done: bool = False


@dataclass(slots=True)
class OllamaPullStreamResult:
    event_count: int
    success_status_received: bool
    last_event: dict[str, object]


def normalize_base_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="AI 服务地址不能为空",
        )
    return normalized


def list_ollama_models(
    *, base_url: str, timeout_seconds: int
) -> list[dict[str, object]]:
    payload = _request_json(
        method="GET",
        url=f"{normalize_base_url(base_url)}/api/tags",
        timeout_seconds=timeout_seconds,
    )
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    return [item for item in models if isinstance(item, dict)]


def test_ollama_connection(*, base_url: str, timeout_seconds: int) -> dict[str, object]:
    models = list_ollama_models(base_url=base_url, timeout_seconds=timeout_seconds)
    return {"model_count": len(models)}


def pull_ollama_model(
    *, base_url: str, name: str, timeout_seconds: int
) -> dict[str, object]:
    return _request_json(
        method="POST",
        url=f"{normalize_base_url(base_url)}/api/pull",
        timeout_seconds=timeout_seconds,
        json_payload={"name": str(name).strip(), "stream": False},
    )


def stream_ollama_model_pull(
    *,
    base_url: str,
    name: str,
    timeout_seconds: int,
    on_event: Callable[[dict[str, object]], None] | None = None,
) -> OllamaPullStreamResult:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise AppError(
            code="INVALID_ARGUMENT",
            status_code=422,
            message="模型名称不能为空",
        )

    event_count = 0
    success_status_received = False
    last_event: dict[str, object] = {}
    url = f"{normalize_base_url(base_url)}/api/pull"

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=max(1, int(timeout_seconds)),
            write=30.0,
            pool=5.0,
        )
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                method="POST",
                url=url,
                json={"name": normalized_name, "stream": True},
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    line = str(raw_line or "").strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise AppError(
                            code="AI_PROVIDER_INVALID_RESPONSE",
                            status_code=502,
                            message="Ollama 返回了无法解析的进度响应",
                            detail={"url": url, "body": line[:1000]},
                        ) from exc
                    if not isinstance(payload, dict):
                        raise AppError(
                            code="AI_PROVIDER_INVALID_RESPONSE",
                            status_code=502,
                            message="Ollama 返回了不支持的进度响应",
                            detail={"url": url, "body": line[:1000]},
                        )

                    completed = _coerce_non_negative_int(payload.get("completed"))
                    total = _coerce_non_negative_int(payload.get("total"))
                    percent = None
                    if total and completed is not None:
                        percent = max(0, min(100, int((completed / total) * 100)))

                    last_event = {
                        "status": str(payload.get("status") or "").strip(),
                        "completed": completed,
                        "total": total,
                        "percent": percent,
                        "digest": str(payload.get("digest") or "").strip() or None,
                        "raw": payload,
                    }
                    event_count += 1
                    if callable(on_event):
                        on_event(dict(last_event))
                    if str(payload.get("status") or "").strip().lower() == "success":
                        success_status_received = True

    except httpx.HTTPStatusError as exc:
        raise AppError(
            code="AI_PROVIDER_HTTP_ERROR",
            status_code=502,
            message="AI Provider 请求失败",
            detail={
                "status_code": exc.response.status_code,
                "url": url,
                "body": exc.response.text[:1000],
            },
        ) from exc
    except httpx.ReadTimeout as exc:
        raise AppError(
            code="OLLAMA_PULL_TIMEOUT",
            status_code=504,
            message="Ollama 拉取模型超时",
            detail={"url": url, "error": str(exc)},
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
            message="AI Provider 不可用",
            detail={"url": url, "error": str(exc)},
        ) from exc

    if event_count == 0:
        raise AppError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            status_code=502,
            message="Ollama 未返回任何拉取进度",
            detail={"url": url},
        )
    if not success_status_received:
        raise AppError(
            code="OLLAMA_PULL_NO_SUCCESS_STATUS",
            status_code=502,
            message="Ollama 拉取未返回 success 状态",
            detail={"last_event": last_event},
        )
    return OllamaPullStreamResult(
        event_count=event_count,
        success_status_received=success_status_received,
        last_event=last_event,
    )


def delete_ollama_model(
    *, base_url: str, name: str, timeout_seconds: int
) -> dict[str, object]:
    return _request_json(
        method="DELETE",
        url=f"{normalize_base_url(base_url)}/api/delete",
        timeout_seconds=timeout_seconds,
        json_payload={"name": str(name).strip()},
    )


def test_openai_compatible_connection(
    *, base_url: str, api_key: str, timeout_seconds: int
) -> dict[str, object]:
    data = list_openai_compatible_models(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    return {"model_count": len(data)}


def list_openai_compatible_models(
    *, base_url: str, api_key: str, timeout_seconds: int
) -> list[dict[str, object]]:
    payload = _request_json(
        method="GET",
        url=f"{normalize_base_url(base_url)}/models",
        timeout_seconds=timeout_seconds,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def run_provider_chat(
    *,
    provider_snapshot: dict[str, object],
    messages: list[dict[str, str]],
) -> AIChatResult:
    content_parts: list[str] = []
    raw_events: list[dict[str, object]] = []
    for chunk in iter_provider_chat_stream(
        provider_snapshot=provider_snapshot,
        messages=messages,
    ):
        raw_events.append(chunk.raw_payload)
        if chunk.content:
            content_parts.append(chunk.content)

    content = "".join(content_parts).strip()
    if not content:
        raise AppError(
            code="AI_EMPTY_RESPONSE",
            status_code=502,
            message="外部 AI Provider 未返回有效内容",
        )
    return AIChatResult(
        content=content,
        raw_payload={"events": raw_events},
    )


def iter_provider_chat_stream(
    *,
    provider_snapshot: dict[str, object],
    messages: list[dict[str, str]],
) -> Iterator[AIChatStreamChunk]:
    provider_type = str(provider_snapshot.get("provider_type") or "").strip().lower()
    if provider_type == "ollama_local":
        yield from _iter_ollama_chat_stream(
            provider_snapshot=provider_snapshot,
            messages=messages,
        )
        return
    if provider_type == "openai_compatible":
        yield from _iter_openai_compatible_chat_stream(
            provider_snapshot=provider_snapshot, messages=messages
        )
        return
    raise AppError(
        code="AI_PROVIDER_UNSUPPORTED",
        status_code=422,
        message="暂不支持该 AI Provider 类型",
        detail={"provider_type": provider_type},
    )


def _iter_ollama_chat_stream(
    *, provider_snapshot: dict[str, object], messages: list[dict[str, str]]
) -> Iterator[AIChatStreamChunk]:
    url = f"{normalize_base_url(str(provider_snapshot.get('base_url') or ''))}/api/chat"
    event_count = 0

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=max(1, int(provider_snapshot.get("timeout_seconds") or 60)),
            write=30.0,
            pool=5.0,
        )
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                method="POST",
                url=url,
                json={
                    "model": str(provider_snapshot.get("model") or ""),
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": float(
                            provider_snapshot.get("temperature") or 0.1
                        ),
                    },
                },
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    line = str(raw_line or "").strip()
                    if not line:
                        continue
                    payload = _parse_json_object_line(
                        line,
                        invalid_message="Ollama 返回了无法解析的对话流响应",
                        url=url,
                    )
                    event_count += 1
                    message = (
                        payload.get("message")
                        if isinstance(payload.get("message"), dict)
                        else {}
                    )
                    content = str(message.get("content") or "")
                    yield AIChatStreamChunk(
                        content=content,
                        raw_payload=payload,
                        done=bool(payload.get("done")),
                    )
    except httpx.HTTPStatusError as exc:
        raise AppError(
            code="AI_PROVIDER_HTTP_ERROR",
            status_code=502,
            message="AI Provider 请求失败",
            detail={
                "status_code": exc.response.status_code,
                "url": url,
                "body": exc.response.text[:1000],
            },
        ) from exc
    except httpx.ReadTimeout as exc:
        raise AppError(
            code="AI_CHAT_TIMEOUT",
            status_code=504,
            message="AI 对话响应超时",
            detail={"url": url, "error": str(exc)},
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
            message="AI Provider 不可用",
            detail={"url": url, "error": str(exc)},
        ) from exc

    if event_count == 0:
        raise AppError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            status_code=502,
            message="Ollama 未返回任何对话流响应",
            detail={"url": url},
        )


def _iter_openai_compatible_chat_stream(
    *, provider_snapshot: dict[str, object], messages: list[dict[str, str]]
) -> Iterator[AIChatStreamChunk]:
    api_key = str(provider_snapshot.get("api_key") or "").strip()
    if not api_key:
        raise AppError(
            code="AI_PROVIDER_SECRET_MISSING",
            status_code=422,
            message="外部 AI Provider 缺少可用密钥",
        )
    url = (
        f"{normalize_base_url(str(provider_snapshot.get('base_url') or ''))}"
        "/chat/completions"
    )
    event_count = 0

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=max(1, int(provider_snapshot.get("timeout_seconds") or 60)),
            write=30.0,
            pool=5.0,
        )
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                method="POST",
                url=url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": str(provider_snapshot.get("model") or ""),
                    "messages": messages,
                    "temperature": float(provider_snapshot.get("temperature") or 0.1),
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    line = str(raw_line or "").strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    raw_data = line[5:].strip()
                    if not raw_data:
                        continue
                    if raw_data == "[DONE]":
                        break
                    payload = _parse_json_object_line(
                        raw_data,
                        invalid_message="外部 AI Provider 返回了无法解析的对话流响应",
                        url=url,
                    )
                    event_count += 1
                    choices = (
                        payload.get("choices")
                        if isinstance(payload.get("choices"), list)
                        else []
                    )
                    first = (
                        choices[0] if choices and isinstance(choices[0], dict) else {}
                    )
                    delta = (
                        first.get("delta")
                        if isinstance(first.get("delta"), dict)
                        else {}
                    )
                    content = str(delta.get("content") or "")
                    finish_reason = str(first.get("finish_reason") or "").strip()
                    yield AIChatStreamChunk(
                        content=content,
                        raw_payload=payload,
                        done=bool(finish_reason),
                    )
    except httpx.HTTPStatusError as exc:
        raise AppError(
            code="AI_PROVIDER_HTTP_ERROR",
            status_code=502,
            message="AI Provider 请求失败",
            detail={
                "status_code": exc.response.status_code,
                "url": url,
                "body": exc.response.text[:1000],
            },
        ) from exc
    except httpx.ReadTimeout as exc:
        raise AppError(
            code="AI_CHAT_TIMEOUT",
            status_code=504,
            message="AI 对话响应超时",
            detail={"url": url, "error": str(exc)},
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
            message="AI Provider 不可用",
            detail={"url": url, "error": str(exc)},
        ) from exc

    if event_count == 0:
        raise AppError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            status_code=502,
            message="外部 AI Provider 未返回任何对话流响应",
            detail={"url": url},
        )


def _request_json(
    *,
    method: str,
    url: str,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, object]:
    try:
        with httpx.Client(timeout=max(1, timeout_seconds)) as client:
            response = client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_payload,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AppError(
            code="AI_PROVIDER_HTTP_ERROR",
            status_code=502,
            message="AI Provider 请求失败",
            detail={
                "status_code": exc.response.status_code,
                "url": url,
                "body": exc.response.text[:1000],
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            code="AI_PROVIDER_UNAVAILABLE",
            status_code=503,
            message="AI Provider 不可用",
            detail={"url": url, "error": str(exc)},
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            status_code=502,
            message="AI Provider 返回了无法解析的响应",
            detail={"url": url, "body": response.text[:1000]},
        ) from exc
    return payload if isinstance(payload, dict) else {"data": payload}


def _parse_json_object_line(
    line: str,
    *,
    invalid_message: str,
    url: str,
) -> dict[str, object]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            status_code=502,
            message=invalid_message,
            detail={"url": url, "body": line[:1000]},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="AI_PROVIDER_INVALID_RESPONSE",
            status_code=502,
            message=invalid_message,
            detail={"url": url, "body": line[:1000]},
        )
    return payload


def _coerce_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
