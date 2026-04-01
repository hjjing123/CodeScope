from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import AppError
from app.models import (
    AIChatMessage,
    AIChatSession,
    AIAssessmentStatus,
    Finding,
    FindingAIAssessment,
    FindingPath,
    FindingPathEdge,
    FindingPathStep,
    Job,
    JobType,
    Project,
    ProjectRole,
    SystemAIProvider,
    SystemOllamaPullJob,
    SystemOllamaPullJobStage,
    SystemOllamaPullJobStatus,
    SystemRole,
    User,
    UserProjectRole,
    Version,
    VersionSource,
    VersionStatus,
    utc_now,
)
from app.security.password import hash_password
from app.services.ai_client_service import (
    AIChatResult,
    AIChatStreamChunk,
    OllamaPullStreamResult,
    delete_ollama_model,
    run_provider_chat,
)
from app.services.ai_service import (
    _build_assessment_messages,
    _parse_assessment_content,
)
from app.services.task_log_service import append_task_log


def _create_user(db, *, email: str, password: str, role: str) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=email.split("@")[0],
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, *, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(db, *, name: str) -> Project:
    project = Project(name=name, description="ai-test")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _add_member(
    db,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    role: str = ProjectRole.OWNER.value,
) -> UserProjectRole:
    membership = UserProjectRole(
        user_id=user_id, project_id=project_id, project_role=role
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def _create_version(db, *, project_id: uuid.UUID, name: str = "v1") -> Version:
    version = Version(
        project_id=project_id,
        name=name,
        source=VersionSource.UPLOAD.value,
        snapshot_object_key=f"snapshots/{name}.tar.gz",
        status=VersionStatus.READY.value,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def _create_finding(db, *, project_id: uuid.UUID, version_id: uuid.UUID) -> Finding:
    job = Job(
        project_id=project_id,
        version_id=version_id,
        job_type=JobType.SCAN.value,
        status="SUCCEEDED",
        payload={},
        result_summary={},
    )
    db.add(job)
    db.flush()

    finding = Finding(
        project_id=project_id,
        version_id=version_id,
        job_id=job.id,
        rule_key="any_any_xss",
        vuln_type="XSS",
        evidence_json={},
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


def _create_finding_path(
    db,
    *,
    finding_id: uuid.UUID,
    steps: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> None:
    finding_path = FindingPath(
        finding_id=finding_id,
        path_order=0,
        path_length=max(0, len(edges)),
    )
    db.add(finding_path)
    db.flush()

    for index, step in enumerate(steps):
        db.add(
            FindingPathStep(
                finding_path_id=finding_path.id,
                step_order=index,
                labels_json=list(step.get("labels") or []),
                file_path=step.get("file_path"),
                line_no=step.get("line_no"),
                func_name=step.get("func_name"),
                display_name=step.get("display_name"),
                node_kind=step.get("node_kind"),
                code_snippet=step.get("code_snippet"),
                node_ref=str(step.get("node_ref") or f"step-{index}"),
                raw_props_json={},
            )
        )

    for index, edge in enumerate(edges):
        db.add(
            FindingPathEdge(
                finding_path_id=finding_path.id,
                edge_order=index,
                from_step_order=edge.get("from_step_order"),
                to_step_order=edge.get("to_step_order"),
                edge_type=str(edge.get("edge_type") or "STEP_NEXT"),
                label=edge.get("label"),
                is_hidden=False,
                props_json={},
            )
        )

    db.commit()


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        chunk = block.strip()
        if not chunk:
            continue
        payload: dict[str, object] = {"event": "message", "id": None, "data": {}}
        data_lines: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("event:"):
                payload["event"] = line.split(":", 1)[1].strip()
                continue
            if line.startswith("id:"):
                raw_id = line.split(":", 1)[1].strip()
                try:
                    payload["id"] = int(raw_id)
                except ValueError:
                    payload["id"] = None
                continue
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            payload["data"] = json.loads("\n".join(data_lines))
        events.append(payload)
    return events


def _wait_for_pull_job_terminal(client, headers, pull_job_id: str) -> dict[str, object]:
    for _ in range(40):
        response = client.get(
            f"/api/v1/system/ai/ollama/pull-jobs/{pull_job_id}", headers=headers
        )
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        if payload["status"] in {"SUCCEEDED", "FAILED", "TIMEOUT", "CANCELED"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("pull job did not reach terminal status in time")


def test_admin_can_configure_and_test_system_ollama(client, db_session, monkeypatch):
    admin = _create_user(
        db_session,
        email="admin-ai@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    monkeypatch.setattr(
        "app.api.v1.ai.test_system_ollama_provider",
        lambda _provider: {
            "ok": True,
            "provider_type": "ollama_local",
            "provider_label": "System Ollama",
            "detail": {"model_count": 2},
        },
    )
    monkeypatch.setattr(
        "app.api.v1.ai.get_ollama_model_payloads",
        lambda _provider: [
            {
                "name": "qwen2.5-coder:7b",
                "size": 123,
                "digest": "abc",
                "modified_at": "2026-03-16T00:00:00Z",
                "details": {"family": "qwen"},
            }
        ],
    )

    response = client.patch(
        "/api/v1/system/ai/ollama",
        headers=headers,
        json={
            "display_name": "System Ollama",
            "base_url": "http://127.0.0.1:11434",
            "enabled": True,
            "default_model": "qwen2.5-coder:7b",
            "published_models": ["qwen2.5-coder:7b"],
            "timeout_seconds": 90,
            "temperature": 0.2,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["enabled"] is True

    response = client.post("/api/v1/system/ai/ollama/test", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["detail"]["model_count"] == 2

    response = client.get("/api/v1/system/ai/ollama/models", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["name"] == "qwen2.5-coder:7b"


def test_system_ollama_auto_configures_and_probes_connection(
    client, db_session, monkeypatch
):
    admin = _create_user(
        db_session,
        email="admin-auto-ai@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    user = _create_user(
        db_session,
        email="user-auto-ai@example.com",
        password="user12345",
        role=SystemRole.USER.value,
    )
    admin_headers = _login(client, email=admin.email, password="admin1234")
    user_headers = _login(client, email=user.email, password="user12345")

    settings = get_settings()
    old_base_url = settings.ai_system_ollama_base_url
    old_display_name = settings.ai_system_ollama_display_name
    settings.ai_system_ollama_base_url = "http://127.0.0.1:11434"
    settings.ai_system_ollama_display_name = "System Ollama"

    monkeypatch.setattr(
        "app.services.ai_service.list_ollama_models",
        lambda **_kwargs: [
            {
                "name": "qwen2.5-coder:7b",
                "size": 123,
                "digest": "abc",
                "modified_at": "2026-03-16T00:00:00Z",
                "details": {"family": "qwen"},
            }
        ],
    )

    try:
        response = client.get("/api/v1/system/ai/ollama", headers=admin_headers)
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["auto_configured"] is True
        assert payload["base_url"] == "http://127.0.0.1:11434"
        assert payload["connection_ok"] is True
        assert payload["published_models"] == ["qwen2.5-coder:7b"]

        provider = db_session.scalar(select(SystemAIProvider).limit(1))
        assert provider is not None
        assert provider.default_model == "qwen2.5-coder:7b"

        options_response = client.get("/api/v1/me/ai/options", headers=user_headers)
        assert options_response.status_code == 200, options_response.text
        options = options_response.json()["data"]
        assert options["system_ollama"]["available"] is True
        assert options["system_ollama"]["connection_ok"] is True
        assert options["default_selection"]["ai_source"] == "system_ollama"
    finally:
        settings.ai_system_ollama_base_url = old_base_url
        settings.ai_system_ollama_display_name = old_display_name


def test_system_ollama_auto_probe_falls_back_to_docker_alias(
    client, db_session, monkeypatch
):
    admin = _create_user(
        db_session,
        email="admin-fallback-ai@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    settings = get_settings()
    old_base_url = settings.ai_system_ollama_base_url
    settings.ai_system_ollama_base_url = "http://127.0.0.1:11434"

    def _mock_list_ollama_models(*, base_url: str, timeout_seconds: int):
        if base_url in {"http://127.0.0.1:11434", "http://localhost:11434"}:
            from app.core.errors import AppError

            raise AppError(
                code="AI_PROVIDER_UNAVAILABLE",
                status_code=503,
                message="host probe failed",
            )
        assert timeout_seconds > 0
        assert base_url == "http://ollama:11434"
        return [{"name": "qwen2.5-coder:7b"}]

    monkeypatch.setattr(
        "app.services.ai_service.list_ollama_models", _mock_list_ollama_models
    )

    try:
        response = client.get("/api/v1/system/ai/ollama", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["connection_ok"] is True
        assert payload["base_url"] == "http://ollama:11434"
        assert payload["connection_detail"]["base_url"] == "http://ollama:11434"
    finally:
        settings.ai_system_ollama_base_url = old_base_url


def test_delete_ollama_model_resolves_latest_name_and_accepts_empty_response(
    monkeypatch,
):
    requests: list[tuple[str, str, dict[str, object] | None]] = []

    class _FakeResponse:
        def __init__(self, *, method: str, url: str, payload: dict[str, object] | None):
            self.status_code = 200
            self.request = httpx.Request(method, url, json=payload)
            if url.endswith("/api/tags"):
                self.content = json.dumps(
                    {
                        "models": [
                            {
                                "name": "phi4-mini:latest",
                                "model": "phi4-mini:latest",
                            }
                        ]
                    }
                ).encode("utf-8")
                self.text = self.content.decode("utf-8")
            else:
                self.content = b""
                self.text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            if not self.content:
                raise ValueError("empty body")
            return json.loads(self.text)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method: str, url: str, headers=None, json=None):
            requests.append((method, url, json))
            return _FakeResponse(method=method, url=url, payload=json)

    monkeypatch.setattr("app.services.ai_client_service.httpx.Client", _FakeClient)

    result = delete_ollama_model(
        base_url="http://127.0.0.1:11434",
        name="phi4-mini",
        timeout_seconds=60,
    )

    assert result == {"ok": True, "name": "phi4-mini:latest"}
    assert requests == [
        ("GET", "http://127.0.0.1:11434/api/tags", None),
        (
            "DELETE",
            "http://127.0.0.1:11434/api/delete",
            {"name": "phi4-mini:latest"},
        ),
    ]


def test_run_provider_chat_handles_unread_stream_error_response(monkeypatch):
    class _FakeStreamResponse:
        def __init__(self, url: str):
            self.status_code = 429
            self.request = httpx.Request("POST", url)
            self._body = b'{"error":{"message":"quota exceeded"}}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=self.request,
                response=self,
            )

        def iter_lines(self):
            return iter(())

        def read(self) -> bytes:
            self._content = self._body
            return self._content

        @property
        def text(self) -> str:
            if not hasattr(self, "_content"):
                raise httpx.ResponseNotRead()
            return self._content.decode("utf-8")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method: str, url: str, headers=None, json=None):
            return _FakeStreamResponse(url)

    monkeypatch.setattr("app.services.ai_client_service.httpx.Client", _FakeClient)

    with pytest.raises(AppError) as exc_info:
        run_provider_chat(
            provider_snapshot={
                "provider_type": "openai_compatible",
                "display_name": "Gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "models/gemini-2.0-flash",
                "api_key": "test-key",
                "timeout_seconds": 30,
                "temperature": 0.0,
            },
            messages=[{"role": "user", "content": "ping"}],
        )

    assert exc_info.value.code == "AI_PROVIDER_HTTP_ERROR"
    assert exc_info.value.detail["status_code"] == 429
    assert "quota exceeded" in str(exc_info.value.detail["body"])


def test_admin_can_pull_system_ollama_model_with_progress(
    client, db_session, monkeypatch
):
    admin = _create_user(
        db_session,
        email="admin-pull-ai@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    configure_resp = client.patch(
        "/api/v1/system/ai/ollama",
        headers=headers,
        json={
            "display_name": "System Ollama",
            "base_url": "http://127.0.0.1:11434",
            "enabled": True,
            "default_model": None,
            "published_models": [],
            "timeout_seconds": 90,
            "temperature": 0.2,
        },
    )
    assert configure_resp.status_code == 200, configure_resp.text

    target_model = "qwen2.5-coder:7b"
    calls = {"count": 0}

    def _mock_list_ollama_models(*, base_url: str, timeout_seconds: int):
        assert base_url == "http://127.0.0.1:11434"
        assert timeout_seconds > 0
        calls["count"] += 1
        if calls["count"] < 3:
            return []
        return [{"name": target_model}]

    def _mock_stream_ollama_pull(
        *, base_url: str, name: str, timeout_seconds: int, on_event
    ):
        assert base_url == "http://127.0.0.1:11434"
        assert name == target_model
        assert timeout_seconds >= 300
        events = [
            {
                "status": "pulling manifest",
                "completed": 0,
                "total": 100,
                "percent": 0,
                "digest": None,
                "raw": {"status": "pulling manifest"},
            },
            {
                "status": "downloading",
                "completed": 50,
                "total": 100,
                "percent": 50,
                "digest": "sha256:test",
                "raw": {
                    "status": "downloading",
                    "completed": 50,
                    "total": 100,
                    "digest": "sha256:test",
                },
            },
            {
                "status": "success",
                "completed": 100,
                "total": 100,
                "percent": 100,
                "digest": "sha256:test",
                "raw": {
                    "status": "success",
                    "completed": 100,
                    "total": 100,
                    "digest": "sha256:test",
                },
            },
        ]
        for event in events:
            on_event(event)
        return OllamaPullStreamResult(
            event_count=len(events),
            success_status_received=True,
            last_event=events[-1],
        )

    monkeypatch.setattr(
        "app.services.system_ollama_pull_service.list_ollama_models",
        _mock_list_ollama_models,
    )
    monkeypatch.setattr(
        "app.services.system_ollama_pull_service.stream_ollama_model_pull",
        _mock_stream_ollama_pull,
    )

    response = client.post(
        "/api/v1/system/ai/ollama/pull",
        headers=headers,
        json={"name": target_model},
    )
    assert response.status_code == 202, response.text
    payload = response.json()["data"]
    assert payload["idempotent_replay"] is False
    assert payload["already_present"] is False

    pull_job_id = payload["pull_job_id"]
    final_job = _wait_for_pull_job_terminal(client, headers, pull_job_id)
    assert final_job["status"] == "SUCCEEDED"
    assert final_job["progress"]["percent"] == 100
    assert final_job["progress"]["verified"] is True
    assert final_job["result_summary"]["verification"]["verified"] is True

    provider = db_session.scalar(select(SystemAIProvider).limit(1))
    assert provider is not None
    assert target_model in provider.published_models_json
    assert provider.default_model == target_model

    logs_response = client.get(
        f"/api/v1/system/ai/ollama/pull-jobs/{pull_job_id}/logs",
        headers=headers,
    )
    assert logs_response.status_code == 200, logs_response.text
    lines = [
        line for item in logs_response.json()["data"]["items"] for line in item["lines"]
    ]
    assert any("拉取进度" in line for line in lines)


def test_system_ollama_pull_does_not_publish_model_when_verify_fails(
    client, db_session, monkeypatch
):
    admin = _create_user(
        db_session,
        email="admin-pull-fail@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    configure_resp = client.patch(
        "/api/v1/system/ai/ollama",
        headers=headers,
        json={
            "display_name": "System Ollama",
            "base_url": "http://127.0.0.1:11434",
            "enabled": True,
            "default_model": None,
            "published_models": [],
            "timeout_seconds": 90,
            "temperature": 0.2,
        },
    )
    assert configure_resp.status_code == 200, configure_resp.text

    target_model = "llama3.1:8b"
    calls = {"count": 0}

    def _mock_list_ollama_models(*, base_url: str, timeout_seconds: int):
        calls["count"] += 1
        return []

    def _mock_stream_ollama_pull(
        *, base_url: str, name: str, timeout_seconds: int, on_event
    ):
        event = {
            "status": "success",
            "completed": 100,
            "total": 100,
            "percent": 100,
            "digest": "sha256:missing",
            "raw": {"status": "success", "completed": 100, "total": 100},
        }
        on_event(event)
        return OllamaPullStreamResult(
            event_count=1,
            success_status_received=True,
            last_event=event,
        )

    monkeypatch.setattr(
        "app.services.system_ollama_pull_service.list_ollama_models",
        _mock_list_ollama_models,
    )
    monkeypatch.setattr(
        "app.services.system_ollama_pull_service.stream_ollama_model_pull",
        _mock_stream_ollama_pull,
    )

    response = client.post(
        "/api/v1/system/ai/ollama/pull",
        headers=headers,
        json={"name": target_model},
    )
    assert response.status_code == 202, response.text

    pull_job_id = response.json()["data"]["pull_job_id"]
    final_job = _wait_for_pull_job_terminal(client, headers, pull_job_id)
    assert final_job["status"] == "FAILED"
    assert final_job["failure_code"] == "OLLAMA_PULL_VERIFY_FAILED"

    provider = db_session.scalar(select(SystemAIProvider).limit(1))
    assert provider is not None
    assert provider.published_models_json == []
    assert provider.default_model is None


def test_system_ollama_pull_accepts_latest_tag_for_untagged_request(
    client, db_session, monkeypatch
):
    admin = _create_user(
        db_session,
        email="admin-pull-latest-tag@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    configure_resp = client.patch(
        "/api/v1/system/ai/ollama",
        headers=headers,
        json={
            "display_name": "System Ollama",
            "base_url": "http://127.0.0.1:11434",
            "enabled": True,
            "default_model": None,
            "published_models": [],
            "timeout_seconds": 90,
            "temperature": 0.2,
        },
    )
    assert configure_resp.status_code == 200, configure_resp.text

    requested_model = "phi4-mini"
    resolved_model = "phi4-mini:latest"
    calls = {"count": 0}

    def _mock_list_ollama_models(*, base_url: str, timeout_seconds: int):
        assert base_url == "http://127.0.0.1:11434"
        assert timeout_seconds > 0
        calls["count"] += 1
        if calls["count"] < 3:
            return []
        return [{"name": resolved_model}]

    def _mock_stream_ollama_pull(
        *, base_url: str, name: str, timeout_seconds: int, on_event
    ):
        assert base_url == "http://127.0.0.1:11434"
        assert name == requested_model
        assert timeout_seconds >= 300
        event = {
            "status": "success",
            "completed": 100,
            "total": 100,
            "percent": 100,
            "digest": "sha256:phi4-mini",
            "raw": {
                "status": "success",
                "completed": 100,
                "total": 100,
                "digest": "sha256:phi4-mini",
            },
        }
        on_event(event)
        return OllamaPullStreamResult(
            event_count=1,
            success_status_received=True,
            last_event=event,
        )

    monkeypatch.setattr(
        "app.services.system_ollama_pull_service.list_ollama_models",
        _mock_list_ollama_models,
    )
    monkeypatch.setattr(
        "app.services.system_ollama_pull_service.stream_ollama_model_pull",
        _mock_stream_ollama_pull,
    )

    response = client.post(
        "/api/v1/system/ai/ollama/pull",
        headers=headers,
        json={"name": requested_model},
    )
    assert response.status_code == 202, response.text

    pull_job_id = response.json()["data"]["pull_job_id"]
    final_job = _wait_for_pull_job_terminal(client, headers, pull_job_id)
    assert final_job["status"] == "SUCCEEDED"
    assert final_job["result_summary"]["verification"]["available_models"] == [
        resolved_model
    ]

    provider = db_session.scalar(select(SystemAIProvider).limit(1))
    assert provider is not None
    assert provider.published_models_json == [resolved_model]
    assert provider.default_model == resolved_model


def test_admin_can_delete_system_ollama_model_and_rotate_default(
    client, db_session, monkeypatch
):
    admin = _create_user(
        db_session,
        email="admin-delete-ai@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    provider = SystemAIProvider(
        provider_key="system_ollama",
        display_name="System Ollama",
        provider_type="ollama_local",
        base_url="http://127.0.0.1:11434",
        enabled=True,
        default_model="phi4-mini:latest",
        published_models_json=["phi4-mini:latest", "qwen2.5-coder:7b"],
        timeout_seconds=90,
        temperature=0.2,
    )
    db_session.add(provider)
    db_session.commit()

    monkeypatch.setattr(
        "app.services.ai_service.delete_ollama_model",
        lambda **_kwargs: {"ok": True, "name": "phi4-mini:latest"},
    )

    response = client.delete(
        "/api/v1/system/ai/ollama/models/phi4-mini%3Alatest",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["ok"] is True

    db_session.refresh(provider)
    assert provider.published_models_json == ["qwen2.5-coder:7b"]
    assert provider.default_model == "qwen2.5-coder:7b"


def test_system_ollama_pull_replays_same_model_and_rejects_other_running_model(
    client, db_session
):
    admin = _create_user(
        db_session,
        email="admin-pull-replay@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    provider = SystemAIProvider(
        provider_key="system_ollama",
        display_name="System Ollama",
        provider_type="ollama_local",
        base_url="http://127.0.0.1:11434",
        enabled=True,
        default_model=None,
        published_models_json=[],
        timeout_seconds=90,
        temperature=0.2,
    )
    db_session.add(provider)
    db_session.flush()
    active_job = SystemOllamaPullJob(
        provider_id=provider.id,
        model_name="qwen2.5-coder:7b",
        payload={"request_id": "req-pull-active"},
        status=SystemOllamaPullJobStatus.RUNNING.value,
        stage=SystemOllamaPullJobStage.PULL.value,
        result_summary={},
        created_by=admin.id,
        started_at=utc_now(),
    )
    db_session.add(active_job)
    db_session.commit()

    same_response = client.post(
        "/api/v1/system/ai/ollama/pull",
        headers=headers,
        json={"name": "qwen2.5-coder:7b"},
    )
    assert same_response.status_code == 200, same_response.text
    assert same_response.json()["data"]["idempotent_replay"] is True
    assert same_response.json()["data"]["pull_job_id"] == str(active_job.id)

    other_response = client.post(
        "/api/v1/system/ai/ollama/pull",
        headers=headers,
        json={"name": "llama3.1:8b"},
    )
    assert other_response.status_code == 409, other_response.text
    assert other_response.json()["error"]["code"] == "OLLAMA_PULL_ALREADY_RUNNING"


def test_system_ollama_pull_log_stream_returns_events(client, db_session):
    admin = _create_user(
        db_session,
        email="admin-pull-logstream@example.com",
        password="admin1234",
        role=SystemRole.ADMIN.value,
    )
    headers = _login(client, email=admin.email, password="admin1234")

    provider = SystemAIProvider(
        provider_key="system_ollama",
        display_name="System Ollama",
        provider_type="ollama_local",
        base_url="http://127.0.0.1:11434",
        enabled=True,
        default_model=None,
        published_models_json=["qwen2.5-coder:7b"],
        timeout_seconds=90,
        temperature=0.2,
    )
    db_session.add(provider)
    db_session.flush()
    job = SystemOllamaPullJob(
        provider_id=provider.id,
        model_name="qwen2.5-coder:7b",
        payload={"request_id": "req-pull-stream"},
        status=SystemOllamaPullJobStatus.SUCCEEDED.value,
        stage=SystemOllamaPullJobStage.FINALIZE.value,
        result_summary={
            "progress": {
                "phase": "finalize",
                "status_text": "模型可用",
                "percent": 100,
                "verified": True,
            }
        },
        created_by=admin.id,
        started_at=utc_now(),
        finished_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()

    append_task_log(
        task_type="OLLAMA_PULL",
        task_id=job.id,
        stage="Pull",
        message="拉取进度: status=downloading, progress=50%",
        project_id=None,
    )
    append_task_log(
        task_type="OLLAMA_PULL",
        task_id=job.id,
        stage="Finalize",
        message="模型拉取完成: model=qwen2.5-coder:7b",
        project_id=None,
    )

    logs_response = client.get(
        f"/api/v1/system/ai/ollama/pull-jobs/{job.id}/logs",
        headers=headers,
    )
    assert logs_response.status_code == 200, logs_response.text
    assert logs_response.json()["data"]["task_type"] == "OLLAMA_PULL"

    stream_resp = client.get(
        f"/api/v1/system/ai/ollama/pull-jobs/{job.id}/logs/stream",
        headers=headers,
    )
    assert stream_resp.status_code == 200, stream_resp.text
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")
    events = _parse_sse_events(stream_resp.text)
    log_events = [item for item in events if item["event"] == "log"]
    assert log_events
    assert any("拉取进度" in item["data"]["line"] for item in log_events)
    assert events[-1]["event"] == "done"


def test_user_can_manage_and_test_external_ai_provider(client, db_session, monkeypatch):
    user = _create_user(
        db_session,
        email="user-ai@example.com",
        password="user12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="user12345")

    response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "vendor_name": "DeepSeek",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-1234567890",
            "default_model": "deepseek-chat",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert response.status_code == 201, response.text
    provider_id = response.json()["data"]["id"]
    assert response.json()["data"]["display_name"] == "deepseek-chat"
    assert response.json()["data"]["api_key_masked"]
    assert "api_key" not in response.json()["data"]

    monkeypatch.setattr(
        "app.api.v1.ai.test_user_ai_provider",
        lambda _provider: {
            "ok": True,
            "provider_type": "openai_compatible",
            "provider_label": "My DeepSeek",
            "detail": {"model_count": 5},
        },
    )
    response = client.post(
        f"/api/v1/me/ai/providers/{provider_id}/test", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["detail"]["model_count"] == 5

    response = client.get("/api/v1/me/ai/providers", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 1
    assert response.json()["data"]["items"][0]["is_default"] is True

    response = client.get("/api/v1/me/ai/options", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["user_providers"][0]["id"] == provider_id

    response = client.patch(
        f"/api/v1/me/ai/providers/{provider_id}",
        headers=headers,
        json={"default_model": "deepseek-reasoner"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["display_name"] == "deepseek-reasoner"


def test_user_can_probe_provider_draft_and_verify_selected_model(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="draft-probe-ai@example.com",
        password="user12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="user12345")

    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [
            {"id": "gemini-2.5-flash"},
            {"id": "gemini-2.5-pro"},
        ],
    )
    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **kwargs: AIChatResult(
            content=f"OK from {kwargs['provider_snapshot']['model']}",
            raw_payload={"provider": "mock"},
        ),
    )
    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **kwargs: AIChatResult(
            content=f"OK from {kwargs['provider_snapshot']['model']}",
            raw_payload={"provider": "mock"},
        ),
    )

    response = client.post(
        "/api/v1/me/ai/providers/test-draft",
        headers=headers,
        json={
            "vendor_name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "gemini-test-key",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["ok"] is True
    assert payload["model_count"] == 2
    assert payload["models"][0]["name"] == "gemini-2.5-flash"
    assert payload["selected_model_verification"] is None

    verify_response = client.post(
        "/api/v1/me/ai/providers/test-draft",
        headers=headers,
        json={
            "vendor_name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "gemini-test-key",
            "selected_model": "gemini-2.5-flash",
            "verify_selected_model": True,
        },
    )
    assert verify_response.status_code == 200, verify_response.text
    verify_payload = verify_response.json()["data"]
    assert verify_payload["ok"] is True
    assert verify_payload["selected_model_verification"]["ok"] is True
    assert verify_payload["selected_model_verification"]["model"] == "gemini-2.5-flash"


def test_user_can_detect_unusable_selected_model_in_provider_draft_probe(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="draft-probe-fail-ai@example.com",
        password="user12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="user12345")

    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [
            {"id": "gemini-2.5-flash"},
            {"id": "gemini-2.5-pro"},
        ],
    )

    def _mock_run_provider_chat(**kwargs):
        if kwargs["provider_snapshot"]["model"] == "gemini-2.5-pro":
            raise AppError(
                code="AI_PROVIDER_HTTP_ERROR",
                status_code=502,
                message="所选模型当前不可用",
                detail={"status_code": 404},
            )
        return AIChatResult(content="OK", raw_payload={"provider": "mock"})

    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        _mock_run_provider_chat,
    )

    response = client.post(
        "/api/v1/me/ai/providers/test-draft",
        headers=headers,
        json={
            "vendor_name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "gemini-test-key",
            "selected_model": "gemini-2.5-pro",
            "verify_selected_model": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["ok"] is False
    assert payload["model_count"] == 2
    assert payload["selected_model_verification"]["ok"] is False
    assert (
        payload["selected_model_verification"]["error_code"] == "AI_PROVIDER_HTTP_ERROR"
    )
    assert payload["selected_model_verification"]["model"] == "gemini-2.5-pro"


def test_user_can_test_gemini_provider_via_openai_compatible_flow(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="user-gemini@example.com",
        password="user12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="user12345")

    response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "My Gemini",
            "vendor_name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "gemini-test-key",
            "default_model": "gemini-2.5-flash",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert response.status_code == 201, response.text
    provider_id = response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [
            {"id": "gemini-2.5-flash"},
            {"id": "gemini-2.5-pro"},
        ],
    )
    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **kwargs: AIChatResult(
            content=f"OK from {kwargs['provider_snapshot']['model']}",
            raw_payload={"provider": "mock"},
        ),
    )

    response = client.post(
        f"/api/v1/me/ai/providers/{provider_id}/test", headers=headers
    )
    assert response.status_code == 200, response.text
    detail = response.json()["data"]["detail"]
    assert detail["vendor_name"] == "Google Gemini"
    assert detail["model_count"] == 2
    assert detail["model_catalog_ok"] is True
    assert detail["allow_manual_model_input"] is False


def test_user_can_test_external_provider_in_manual_model_mode(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="user-manual-test@example.com",
        password="user12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="user12345")

    response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Gemini Manual",
            "vendor_name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "gemini-test-key",
            "default_model": "gemini-2.5-flash",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert response.status_code == 201, response.text
    provider_id = response.json()["data"]["id"]

    def _mock_list_models(**_kwargs):
        raise AppError(
            code="AI_PROVIDER_HTTP_ERROR",
            status_code=502,
            message="models unsupported",
            detail={"status_code": 405},
        )

    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        _mock_list_models,
    )
    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content="OK",
            raw_payload={"provider": "mock"},
        ),
    )

    response = client.post(
        f"/api/v1/me/ai/providers/{provider_id}/test", headers=headers
    )
    assert response.status_code == 200, response.text
    detail = response.json()["data"]["detail"]
    assert detail["model_count"] == 0
    assert detail["model_catalog_ok"] is False
    assert detail["allow_manual_model_input"] is True
    assert detail["status_label"] == "目录不可用，需手填模型"


def test_scan_with_ai_enabled_creates_ai_job_and_assessments(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="scan-ai@example.com",
        password="scan12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="AI Scan Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    headers = _login(client, email=user.email, password="scan12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "My OpenAI Compatible",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-scan-1234567890",
            "default_model": "demo-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert provider_response.status_code == 201, provider_response.text
    provider_id = provider_response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content=json.dumps(
                {
                    "verdict": "TP",
                    "confidence": "high",
                    "summary": "Looks exploitable.",
                    "risk_reason": "Source reaches sink.",
                    "false_positive_signals": [],
                    "fix_suggestions": ["Validate input"],
                    "evidence_refs": ["trace_summary"],
                },
                ensure_ascii=False,
            ),
            raw_payload={"provider": "mock"},
        ),
    )
    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [{"id": "demo-model"}],
    )
    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [{"id": "demo-model"}],
    )

    response = client.post(
        "/api/v1/scan-jobs",
        headers=headers,
        json={
            "project_id": str(project.id),
            "version_id": str(version.id),
            "rule_keys": ["any_any_xss"],
            "ai_enabled": True,
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "demo-model",
        },
    )
    assert response.status_code == 202, response.text
    scan_job_id = response.json()["data"]["job_id"]

    scan_job = db_session.get(Job, uuid.UUID(scan_job_id))
    assert scan_job is not None
    assert scan_job.payload["ai"]["enabled"] is True
    assert "api_key_encrypted" in scan_job.payload["ai"]["provider_snapshot"]

    ai_jobs = db_session.scalars(
        select(Job).where(Job.job_type == JobType.AI.value)
    ).all()
    assert len(ai_jobs) == 1
    ai_job = ai_jobs[0]
    assert ai_job.status == "SUCCEEDED"
    assert ai_job.payload["scan_job_id"] == scan_job_id

    assessments = db_session.scalars(select(FindingAIAssessment)).all()
    assert assessments
    assert assessments[0].summary_json["verdict"] == "TP"
    assert assessments[0].summary_json["prompt_meta"]["max_context_tokens"] == 32768
    assert assessments[0].request_messages_json
    assert assessments[0].context_snapshot_json
    assert assessments[0].context_snapshot_json["extraction"]["profile"] == "XSS"
    assert (
        assessments[0].context_snapshot_json["analysis_focus"]["data_flow_chain"] == []
    )

    finding = db_session.scalar(select(Finding).where(Finding.job_id == scan_job.id))
    assert finding is not None
    assert finding.evidence_json["assessment_profile"] == "XSS"
    assert finding.evidence_json["assessment_extraction"]["profile"] == "XSS"
    assert finding.evidence_json["assessment_extraction"]["filter_points"]

    response = client.get(f"/api/v1/jobs/{scan_job_id}/ai-enrichment", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["enabled"] is True
    assert response.json()["data"]["latest_status"] == "SUCCEEDED"


def test_assessment_prompt_includes_key_flow_and_respects_budget(db_session):
    project = _create_project(db_session, name="AI Prompt Budget Project")
    version = _create_version(db_session, project_id=project.id)
    finding = _create_finding(db_session, project_id=project.id, version_id=version.id)
    finding.rule_key = "any_fastjson_deserialization"
    finding.vuln_type = "DESERIALIZATION"
    finding.severity = "HIGH"
    finding.file_path = "src/main/java/com/demo/FastjsonController.java"
    finding.line_start = 42
    finding.source_file = "src/main/java/com/demo/FastjsonController.java"
    finding.source_line = 38
    finding.sink_file = "src/main/java/com/demo/FastjsonService.java"
    finding.sink_line = 88
    finding.evidence_json = {
        "llm_payload": {
            "rule_key": "any_fastjson_deserialization",
            "severity": "HIGH",
            "vuln_type": "DESERIALIZATION",
            "location": {
                "file_path": "src/main/java/com/demo/FastjsonController.java",
                "line_start": 42,
            },
            "source": {
                "file": "src/main/java/com/demo/FastjsonController.java",
                "line": 38,
            },
            "sink": {
                "file": "src/main/java/com/demo/FastjsonService.java",
                "line": 88,
            },
            "trace_summary": "HTTP body -> controller parse -> service parseObject -> target class init",
            "why_flagged": "Untrusted request body reaches Fastjson parseObject without an allowlist.",
            "evidence_preview": [
                "user_input=request.body",
                "api=JSON.parseObject",
                "target_type=com.demo.UserDto",
                "guard=none",
            ],
            "code_context": {
                "focus": "JSON.parseObject(body, UserDto.class);" * 20,
                "source": "String body = request.getBody();" * 20,
                "sink": "return JSON.parseObject(body, clazz);" * 20,
            },
        },
        "assessment_extraction": {
            "source_highlights": [
                {
                    "kind": "deserialization_guard",
                    "location": "src/main/java/com/demo/FastjsonService.java:88-89",
                    "snippet": "88: return JSON.parseObject(body, clazz);\n89: // no safeMode enabled",
                }
            ]
        },
    }
    db_session.commit()

    _create_finding_path(
        db_session,
        finding_id=finding.id,
        steps=[
            {
                "file_path": "src/main/java/com/demo/FastjsonController.java",
                "line_no": 38,
                "display_name": "request body",
                "node_kind": "Param",
                "code_snippet": "String body = request.getBody();",
                "node_ref": "source-1",
            },
            {
                "file_path": "src/main/java/com/demo/FastjsonController.java",
                "line_no": 42,
                "display_name": "parse request",
                "node_kind": "Call",
                "code_snippet": "service.parse(body);",
                "node_ref": "call-2",
            },
            {
                "file_path": "src/main/java/com/demo/FastjsonService.java",
                "line_no": 88,
                "display_name": "JSON.parseObject",
                "node_kind": "Call",
                "code_snippet": "return JSON.parseObject(body, clazz);",
                "node_ref": "sink-3",
            },
        ],
        edges=[
            {
                "from_step_order": 0,
                "to_step_order": 1,
                "edge_type": "PARAM_PASS",
                "label": "跨函数参数传递",
            },
            {
                "from_step_order": 1,
                "to_step_order": 2,
                "edge_type": "REF",
                "label": "引用传播",
            },
        ],
    )

    bundle = _build_assessment_messages(
        db_session,
        finding=finding,
        provider_snapshot={
            "provider_type": "ollama_local",
            "max_context_tokens": 4096,
            "max_output_tokens": 1024,
        },
    )

    assert bundle.budget_meta["profile"] == "DESERIALIZATION"
    assert (
        bundle.budget_meta["input_tokens_estimate"]
        <= bundle.budget_meta["max_input_tokens"]
    )
    assert bundle.context_payload["extraction"]["profile"] == "DESERIALIZATION"
    assert (
        bundle.context_payload["extraction"]["structured_facts"][
            "deserializes_untrusted_input"
        ]
        == "yes"
    )
    assert bundle.context_payload["extraction"]["filter_points"]
    assert bundle.context_payload["extraction"]["source_highlights"]
    assert "Fastjson" in bundle.messages[0]["content"]
    assert "data_flow_chain" in bundle.messages[1]["content"]
    assert "structured_facts" in bundle.messages[1]["content"]
    assert "source_highlights" in bundle.messages[1]["content"]
    assert "JSON.parseObject" in bundle.messages[1]["content"]
    assert "跨函数参数传递" in bundle.messages[1]["content"]


def test_parse_assessment_content_supports_labeled_fallback():
    raw = """
    Verdict: TP
    Confidence: high
    Summary: 输入可控并进入高危反序列化入口。
    Risk Reason: 外部请求体未经白名单校验进入 JSON.parseObject。
    False Positive Signals:
    - 仅当 parseObject 实际不可达时才可能误报
    Fix Suggestions:
    - 禁用危险 autoType
    - 增加目标类型白名单
    Evidence Refs:
    - trace_summary
    - data_flow_chain
    """

    payload = _parse_assessment_content(raw)
    assert payload["schema_version"] == "codescope.ai_assessment.v1"
    assert payload["verdict"] == "TP"
    assert payload["confidence"] == "high"
    assert payload["fix_suggestions"] == ["禁用危险 autoType", "增加目标类型白名单"]
    assert payload["evidence_refs"] == ["trace_summary", "data_flow_chain"]


def test_failed_assessment_persists_request_context_and_cannot_seed_chat(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="failed-assessment-ai@example.com",
        password="scan12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="Failed Assessment Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    headers = _login(client, email=user.email, password="scan12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Failing Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-failed-1234567890",
            "default_model": "demo-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    provider_id = provider_response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [{"id": "demo-model"}],
    )
    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: (_ for _ in ()).throw(
            AppError(
                code="AI_PROVIDER_UNAVAILABLE",
                status_code=503,
                message="provider unavailable",
            )
        ),
    )

    response = client.post(
        "/api/v1/scan-jobs",
        headers=headers,
        json={
            "project_id": str(project.id),
            "version_id": str(version.id),
            "rule_keys": ["any_any_xss"],
            "ai_enabled": True,
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "demo-model",
        },
    )
    assert response.status_code == 202, response.text

    finding = db_session.scalar(select(Finding).where(Finding.version_id == version.id))
    assert finding is not None
    assessment = db_session.scalar(
        select(FindingAIAssessment).where(FindingAIAssessment.finding_id == finding.id)
    )
    assert assessment is not None
    assert assessment.status == AIAssessmentStatus.FAILED.value
    assert assessment.request_messages_json
    assert assessment.context_snapshot_json
    assert assessment.context_snapshot_json["finding_core"]["rule_key"] == "any_any_xss"

    seed_response = client.post(
        f"/api/v1/findings/{finding.id}/ai/chat/sessions/from-latest-assessment",
        headers=headers,
    )
    assert seed_response.status_code == 409, seed_response.text
    assert seed_response.json()["error"]["code"] == "AI_ASSESSMENT_NOT_READY"


def test_findings_include_latest_ai_review_summary_and_context(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="scan-ai-review@example.com",
        password="scan12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="AI Review Finding Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    headers = _login(client, email=user.email, password="scan12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "My OpenAI Compatible",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-scan-1234567890",
            "default_model": "demo-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    provider_id = provider_response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content=json.dumps(
                {
                    "verdict": "TP",
                    "confidence": "high",
                    "summary": "Looks exploitable.",
                    "risk_reason": "Source reaches sink.",
                    "false_positive_signals": [],
                    "fix_suggestions": ["Validate input"],
                    "evidence_refs": ["trace_summary"],
                },
                ensure_ascii=False,
            ),
            raw_payload={"provider": "mock"},
        ),
    )
    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [{"id": "demo-model"}],
    )

    response = client.post(
        "/api/v1/scan-jobs",
        headers=headers,
        json={
            "project_id": str(project.id),
            "version_id": str(version.id),
            "rule_keys": ["any_any_xss"],
            "ai_enabled": True,
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "demo-model",
        },
    )
    scan_job_id = response.json()["data"]["job_id"]

    finding = db_session.scalar(
        select(Finding).where(Finding.job_id == uuid.UUID(scan_job_id))
    )
    assert finding is not None

    findings_response = client.get(
        f"/api/v1/findings?job_id={scan_job_id}",
        headers=headers,
    )
    assert findings_response.status_code == 200, findings_response.text
    item = findings_response.json()["data"]["items"][0]
    assert item["severity"] == finding.severity
    assert item["ai_review"]["has_assessment"] is True
    assert item["ai_review"]["verdict"] == "TP"
    assert item["ai_review"]["confidence"] == "high"

    detail_response = client.get(f"/api/v1/findings/{finding.id}", headers=headers)
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["data"]["severity"] == finding.severity
    assert detail_response.json()["data"]["ai_review"]["confidence"] == "high"

    context_response = client.get(
        f"/api/v1/findings/{finding.id}/ai/assessment/latest/context",
        headers=headers,
    )
    assert context_response.status_code == 200, context_response.text
    context_payload = context_response.json()["data"]
    assert context_payload["request_messages"]
    assert (
        context_payload["context_snapshot"]["finding_core"]["rule_key"] == "any_any_xss"
    )
    assert context_payload["context_snapshot"]["extraction"]["profile"] == "XSS"


def test_can_create_and_reuse_seeded_assessment_chat_session(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="seeded-chat@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="AI Seeded Chat Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Chat Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-chat-1234567890",
            "default_model": "chat-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    provider_id = provider_response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content=json.dumps(
                {
                    "verdict": "TP",
                    "confidence": "medium",
                    "summary": "XSS appears reachable.",
                    "risk_reason": "Unsanitized data reaches output.",
                    "false_positive_signals": [],
                    "fix_suggestions": ["Escape output"],
                    "evidence_refs": ["data_flow_chain"],
                },
                ensure_ascii=False,
            ),
            raw_payload={"provider": "mock"},
        ),
    )
    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [{"id": "chat-model"}],
    )

    scan_response = client.post(
        "/api/v1/scan-jobs",
        headers=headers,
        json={
            "project_id": str(project.id),
            "version_id": str(version.id),
            "rule_keys": ["any_any_xss"],
            "ai_enabled": True,
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "chat-model",
        },
    )
    scan_job_id = scan_response.json()["data"]["job_id"]
    finding = db_session.scalar(
        select(Finding).where(Finding.job_id == uuid.UUID(scan_job_id))
    )
    assert finding is not None

    assessment = db_session.scalar(
        select(FindingAIAssessment).where(FindingAIAssessment.finding_id == finding.id)
    )
    assert assessment is not None

    seed_response = client.post(
        f"/api/v1/findings/{finding.id}/ai/chat/sessions/from-latest-assessment",
        headers=headers,
    )
    assert seed_response.status_code == 200, seed_response.text
    seed_payload = seed_response.json()["data"]
    assert seed_payload["assessment_id"] == str(assessment.id)
    assert seed_payload["idempotent_replay"] is False

    session_id = seed_payload["session_id"]
    detail_response = client.get(
        f"/api/v1/ai/chat/sessions/{session_id}", headers=headers
    )
    assert detail_response.status_code == 200, detail_response.text
    session_payload = detail_response.json()["data"]
    assert session_payload["seed_kind"] == "assessment_review"
    assert session_payload["seed_assessment_id"] == str(assessment.id)
    assert len(session_payload["messages"]) == 2
    assert "本次 AI 研判实际发送内容" in session_payload["messages"][0]["content"]
    assert (
        session_payload["messages"][0]["meta_json"]["message_kind"]
        == "assessment_seed_input"
    )
    assert (
        session_payload["messages"][1]["meta_json"]["message_kind"]
        == "assessment_seed_output"
    )

    replay_response = client.post(
        f"/api/v1/findings/{finding.id}/ai/chat/sessions/from-latest-assessment",
        headers=headers,
    )
    assert replay_response.status_code == 200, replay_response.text
    replay_payload = replay_response.json()["data"]
    assert replay_payload["session_id"] == session_id
    assert replay_payload["idempotent_replay"] is True


def test_finding_ai_chat_session_can_send_messages(client, db_session, monkeypatch):
    user = _create_user(
        db_session,
        email="chat-ai@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="AI Chat Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Chat Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-chat-1234567890",
            "default_model": "chat-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    provider_id = provider_response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content="这是基于当前证据的回答。",
            raw_payload={"provider": "mock"},
        ),
    )

    scan_response = client.post(
        "/api/v1/scan-jobs",
        headers=headers,
        json={
            "project_id": str(project.id),
            "version_id": str(version.id),
            "rule_keys": ["any_any_xss"],
        },
    )
    assert scan_response.status_code == 202, scan_response.text

    finding_row = db_session.scalar(
        select(Job).where(Job.job_type == JobType.SCAN.value)
    )
    assert finding_row is not None
    finding_model = db_session.scalar(
        select(Finding).where(Finding.job_id == finding_row.id)
    )
    assert finding_model is not None

    session_response = client.post(
        f"/api/v1/findings/{finding_model.id}/ai/chat/sessions",
        headers=headers,
        json={
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "chat-model",
            "title": "漏洞复核",
        },
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["data"]["id"]

    message_response = client.post(
        f"/api/v1/ai/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "这个漏洞为什么会被命中？"},
    )
    assert message_response.status_code == 201, message_response.text
    assert message_response.json()["data"]["assistant_message"]["content"]

    session_model = db_session.get(AIChatSession, uuid.UUID(session_id))
    assert session_model is not None
    messages = db_session.scalars(
        select(AIChatMessage).where(AIChatMessage.session_id == session_model.id)
    ).all()
    assert len(messages) == 2

    list_response = client.get(
        f"/api/v1/me/ai/chat/sessions?finding_id={finding_model.id}", headers=headers
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["data"]["items"][0]["id"] == session_id


def test_general_ai_chat_session_can_send_messages(client, db_session, monkeypatch):
    user = _create_user(
        db_session,
        email="general-chat-ai@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "General Chat Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-general-1234567890",
            "default_model": "chat-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert provider_response.status_code == 201, provider_response.text

    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content="这是一个通用 AI 对话回答。",
            raw_payload={"provider": "mock"},
        ),
    )

    session_response = client.post(
        "/api/v1/me/ai/chat/sessions",
        headers=headers,
        json={"title": "通用对话"},
    )
    assert session_response.status_code == 201, session_response.text
    session_data = session_response.json()["data"]
    session_id = session_data["id"]
    assert session_data["session_mode"] == "general"
    assert session_data["finding_id"] is None

    message_response = client.post(
        f"/api/v1/ai/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "帮我解释一下这个漏洞类型的常见成因"},
    )
    assert message_response.status_code == 201, message_response.text
    assert (
        message_response.json()["data"]["assistant_message"]["content"]
        == "这是一个通用 AI 对话回答。"
    )

    session_model = db_session.get(AIChatSession, uuid.UUID(session_id))
    assert session_model is not None
    assert session_model.session_mode == "general"
    assert session_model.finding_id is None

    list_response = client.get("/api/v1/me/ai/chat/sessions", headers=headers)
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["data"]["items"][0]["session_mode"] == "general"

    detail_response = client.get(
        f"/api/v1/ai/chat/sessions/{session_id}", headers=headers
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["data"]["finding_id"] is None


def test_general_ai_chat_session_can_stream_messages(client, db_session, monkeypatch):
    user = _create_user(
        db_session,
        email="general-chat-stream@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Stream Chat Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-stream-1234567890",
            "default_model": "chat-model",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert provider_response.status_code == 201, provider_response.text

    session_response = client.post(
        "/api/v1/me/ai/chat/sessions",
        headers=headers,
        json={"title": "流式对话"},
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["data"]["id"]

    def _mock_stream(**_kwargs):
        yield AIChatStreamChunk(content="流式", raw_payload={"index": 1})
        yield AIChatStreamChunk(content="回答", raw_payload={"index": 2}, done=True)

    monkeypatch.setattr("app.api.v1.ai.iter_provider_chat_stream", _mock_stream)

    message_response = client.post(
        f"/api/v1/ai/chat/sessions/{session_id}/messages/stream",
        headers=headers,
        json={"content": "请流式解释一下漏洞"},
    )
    assert message_response.status_code == 200, message_response.text
    assert "text/event-stream" in message_response.headers.get("content-type", "")

    events = _parse_sse_events(message_response.text)
    event_names = [item["event"] for item in events]
    assert event_names == [
        "user_message",
        "assistant_delta",
        "assistant_delta",
        "assistant_message",
        "done",
    ]
    assert events[1]["data"]["delta"] == "流式"
    assert events[2]["data"]["delta"] == "回答"
    assert events[3]["data"]["content"] == "流式回答"

    session_model = db_session.get(AIChatSession, uuid.UUID(session_id))
    assert session_model is not None
    messages = db_session.scalars(
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session_model.id)
        .order_by(AIChatMessage.created_at.asc())
    ).all()
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].content == "流式回答"


def test_owner_can_delete_general_ai_chat_session(client, db_session):
    user = _create_user(
        db_session,
        email="delete-general-owner@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="chat12345")

    session = AIChatSession(
        session_mode="general",
        provider_source="system_ollama",
        provider_type="ollama_local",
        provider_label="System Ollama",
        model_name="qwen2.5-coder:7b",
        title="待删除会话",
        provider_snapshot_json={},
        created_by=user.id,
    )
    db_session.add(session)
    db_session.flush()
    db_session.add_all(
        [
            AIChatMessage(
                session_id=session.id,
                role="user",
                content="hello",
                meta_json={},
            ),
            AIChatMessage(
                session_id=session.id,
                role="assistant",
                content="world",
                meta_json={},
            ),
        ]
    )
    db_session.commit()

    response = client.delete(f"/api/v1/ai/chat/sessions/{session.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["ok"] is True
    assert response.json()["data"]["session_id"] == str(session.id)

    assert db_session.get(AIChatSession, session.id) is None
    messages = db_session.scalars(
        select(AIChatMessage).where(AIChatMessage.session_id == session.id)
    ).all()
    assert messages == []


def test_owner_can_delete_finding_ai_chat_session(client, db_session):
    user = _create_user(
        db_session,
        email="delete-finding-owner@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="Delete Finding Session Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    finding = _create_finding(db_session, project_id=project.id, version_id=version.id)
    headers = _login(client, email=user.email, password="chat12345")

    session = AIChatSession(
        session_mode="finding_context",
        finding_id=finding.id,
        project_id=finding.project_id,
        version_id=finding.version_id,
        provider_source="system_ollama",
        provider_type="ollama_local",
        provider_label="System Ollama",
        model_name="qwen2.5-coder:7b",
        title="漏洞会话",
        provider_snapshot_json={},
        created_by=user.id,
    )
    db_session.add(session)
    db_session.flush()
    db_session.add(
        AIChatMessage(
            session_id=session.id,
            role="user",
            content="need review",
            meta_json={},
        )
    )
    db_session.commit()

    response = client.delete(f"/api/v1/ai/chat/sessions/{session.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["session_id"] == str(session.id)

    assert db_session.get(AIChatSession, session.id) is None
    messages = db_session.scalars(
        select(AIChatMessage).where(AIChatMessage.session_id == session.id)
    ).all()
    assert messages == []


def test_non_owner_cannot_delete_general_ai_chat_session(client, db_session):
    owner = _create_user(
        db_session,
        email="delete-general-session-owner@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    other = _create_user(
        db_session,
        email="delete-general-session-other@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=other.email, password="chat12345")

    session = AIChatSession(
        session_mode="general",
        provider_source="system_ollama",
        provider_type="ollama_local",
        provider_label="System Ollama",
        model_name="qwen2.5-coder:7b",
        title="受保护会话",
        provider_snapshot_json={},
        created_by=owner.id,
    )
    db_session.add(session)
    db_session.commit()

    response = client.delete(f"/api/v1/ai/chat/sessions/{session.id}", headers=headers)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["message"] == "仅创建者可以删除该 AI 会话"
    assert db_session.get(AIChatSession, session.id) is not None


def test_non_owner_cannot_delete_finding_ai_chat_session_even_with_finding_access(
    client, db_session
):
    owner = _create_user(
        db_session,
        email="delete-finding-session-owner@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    reviewer = _create_user(
        db_session,
        email="delete-finding-session-reviewer@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    project = _create_project(db_session, name="Finding Delete Permission Project")
    _add_member(db_session, user_id=owner.id, project_id=project.id)
    _add_member(db_session, user_id=reviewer.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)
    finding = _create_finding(db_session, project_id=project.id, version_id=version.id)
    headers = _login(client, email=reviewer.email, password="chat12345")

    session = AIChatSession(
        session_mode="finding_context",
        finding_id=finding.id,
        project_id=finding.project_id,
        version_id=finding.version_id,
        provider_source="system_ollama",
        provider_type="ollama_local",
        provider_label="System Ollama",
        model_name="qwen2.5-coder:7b",
        title="仅创建者可删",
        provider_snapshot_json={},
        created_by=owner.id,
    )
    db_session.add(session)
    db_session.commit()

    response = client.delete(f"/api/v1/ai/chat/sessions/{session.id}", headers=headers)
    assert response.status_code == 403, response.text
    assert response.json()["error"]["message"] == "仅创建者可以删除该 AI 会话"
    assert db_session.get(AIChatSession, session.id) is not None


def test_ai_model_catalog_exposes_selectable_models(client, db_session, monkeypatch):
    user = _create_user(
        db_session,
        email="model-catalog-ai@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Catalog Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-catalog-1234567890",
            "default_model": "deepseek-chat",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert provider_response.status_code == 201, provider_response.text
    provider_id = provider_response.json()["data"]["id"]

    monkeypatch.setattr(
        "app.services.ai_service.ensure_system_ollama_provider",
        lambda db, probe=True: (
            SystemAIProvider(
                provider_key="system_ollama",
                display_name="System Ollama",
                provider_type="ollama_local",
                base_url="http://127.0.0.1:11434",
                enabled=True,
                default_model="qwen2.5-coder:7b",
                published_models_json=["qwen2.5-coder:7b", "llama3.1:8b"],
                timeout_seconds=60,
                temperature=0.1,
            ),
            {"connection_ok": True, "connection_detail": {}},
        ),
    )
    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        lambda **_kwargs: [
            {"id": "deepseek-chat"},
            {"id": "deepseek-reasoner"},
        ],
    )

    response = client.get("/api/v1/me/ai/model-catalog", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert len(payload["items"]) == 2
    system_item = next(
        item for item in payload["items"] if item["provider_source"] == "system_ollama"
    )
    assert system_item["models"][0]["name"] == "qwen2.5-coder:7b"
    assert system_item["available"] is True
    assert system_item["source_label"] == "本地"
    user_item = next(
        item
        for item in payload["items"]
        if item["provider_source"] == "user_external"
        and item["provider_id"] == provider_id
    )
    assert user_item["models"] == [
        {
            "name": "deepseek-chat",
            "label": "deepseek-chat",
            "is_default": True,
            "selectable": True,
            "details": {},
        }
    ]
    assert user_item["available"] is True
    assert user_item["connection_ok"] is True
    assert user_item["model_catalog_ok"] is True
    assert user_item["allow_manual_model_input"] is False


def test_model_catalog_allows_manual_input_when_external_models_unavailable(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="manual-model-ai@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Manual Model Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.manual.example.com/v1",
            "api_key": "sk-manual-1234567890",
            "default_model": "manual-default",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert provider_response.status_code == 201, provider_response.text
    provider_id = provider_response.json()["data"]["id"]

    def _mock_list_models(**_kwargs):
        raise AppError(
            code="AI_PROVIDER_HTTP_ERROR",
            status_code=502,
            message="models unsupported",
            detail={"status_code": 404},
        )

    monkeypatch.setattr(
        "app.services.ai_service.list_openai_compatible_models",
        _mock_list_models,
    )
    monkeypatch.setattr(
        "app.services.ai_service.run_provider_chat",
        lambda **_kwargs: AIChatResult(
            content=json.dumps(
                {
                    "verdict": "TP",
                    "confidence": "high",
                    "summary": "reachable",
                    "risk_reason": "manual model works",
                    "false_positive_signals": [],
                    "fix_suggestions": [],
                    "evidence_refs": [],
                },
                ensure_ascii=False,
            ),
            raw_payload={"provider": "mock"},
        ),
    )

    catalog_response = client.get("/api/v1/me/ai/model-catalog", headers=headers)
    assert catalog_response.status_code == 200, catalog_response.text
    user_item = next(
        item
        for item in catalog_response.json()["data"]["items"]
        if item["provider_id"] == provider_id
    )
    assert user_item["available"] is True
    assert user_item["model_catalog_ok"] is False
    assert user_item["allow_manual_model_input"] is True
    assert user_item["models"] == [
        {
            "name": "manual-default",
            "label": "manual-default",
            "is_default": True,
            "selectable": True,
            "details": {},
        }
    ]

    project = _create_project(db_session, name="Manual Model Scan Project")
    _add_member(db_session, user_id=user.id, project_id=project.id)
    version = _create_version(db_session, project_id=project.id)

    scan_response = client.post(
        "/api/v1/scan-jobs",
        headers=headers,
        json={
            "project_id": str(project.id),
            "version_id": str(version.id),
            "rule_keys": ["any_any_xss"],
            "ai_enabled": True,
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "manual-chat-model",
        },
    )
    assert scan_response.status_code == 202, scan_response.text

    scan_job = db_session.get(Job, uuid.UUID(scan_response.json()["data"]["job_id"]))
    assert scan_job is not None
    ai_payload = scan_job.payload.get("ai")
    assert isinstance(ai_payload, dict)
    provider_snapshot = ai_payload.get("provider_snapshot")
    assert isinstance(provider_snapshot, dict)
    assert provider_snapshot["model"] == "manual-chat-model"


def test_general_chat_session_selection_can_switch_model(
    client, db_session, monkeypatch
):
    user = _create_user(
        db_session,
        email="selection-ai@example.com",
        password="chat12345",
        role=SystemRole.USER.value,
    )
    headers = _login(client, email=user.email, password="chat12345")

    provider_response = client.post(
        "/api/v1/me/ai/providers",
        headers=headers,
        json={
            "display_name": "Selection Provider",
            "vendor_name": "OpenAI Compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-selection-1234567890",
            "default_model": "deepseek-chat",
            "timeout_seconds": 45,
            "temperature": 0.1,
            "enabled": True,
            "is_default": True,
        },
    )
    assert provider_response.status_code == 201, provider_response.text
    provider_id = provider_response.json()["data"]["id"]

    session_response = client.post(
        "/api/v1/me/ai/chat/sessions",
        headers=headers,
        json={"title": "通用对话"},
    )
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["data"]["id"]

    update_response = client.patch(
        f"/api/v1/ai/chat/sessions/{session_id}/selection",
        headers=headers,
        json={
            "ai_source": "user_external",
            "ai_provider_id": provider_id,
            "ai_model": "deepseek-reasoner",
        },
    )
    assert update_response.status_code == 200, update_response.text
    payload = update_response.json()["data"]
    assert payload["model_name"] == "deepseek-reasoner"
    assert payload["provider_source"] == "user_external"

    session_model = db_session.get(AIChatSession, uuid.UUID(session_id))
    assert session_model is not None
    assert session_model.model_name == "deepseek-reasoner"
