from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import main as main_module
from app.db.session import get_db
from app.main import create_app


def _build_client(*, monkeypatch, frontend_dev_port: str = "5173") -> TestClient:
    monkeypatch.setenv("FRONTEND_DEV_PORT", frontend_dev_port)
    app = create_app()

    def override_get_db(request: Request):
        request.state.db_session = None
        yield None
        request.state.db_session = None

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_vite_client_returns_gateway_timeout_when_frontend_dev_proxy_times_out(
    monkeypatch,
) -> None:
    client = _build_client(monkeypatch=monkeypatch)

    class FakeClient:
        def __init__(self, *, follow_redirects, timeout, trust_env):
            assert follow_redirects is False
            assert timeout == 30.0
            assert trust_env is False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url, *, headers):
            assert url == "http://testserver:5173/@vite/client"
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(main_module.httpx, "Client", FakeClient)

    response = client.get("/@vite/client")

    assert response.status_code == 504
    assert "Frontend dev server timed out while rendering" in response.text


def test_vite_client_uses_configured_frontend_dev_proxy_timeout(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_DEV_PROXY_TIMEOUT_SECONDS", "45")
    client = _build_client(monkeypatch=monkeypatch)

    class FakeClient:
        def __init__(self, *, follow_redirects, timeout, trust_env):
            assert follow_redirects is False
            assert timeout == 45.0
            assert trust_env is False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url, *, headers):
            assert url == "http://testserver:5173/@vite/client"
            return httpx.Response(
                200,
                text="<html>ok</html>",
                headers={"Content-Type": "text/html; charset=utf-8"},
            )

    monkeypatch.setattr(main_module.httpx, "Client", FakeClient)

    response = client.get("/@vite/client")

    assert response.status_code == 200
    assert response.text == "<html>ok</html>"


def test_vite_client_returns_bad_gateway_when_frontend_dev_server_is_unavailable(
    monkeypatch,
) -> None:
    client = _build_client(monkeypatch=monkeypatch)

    class FakeClient:
        def __init__(self, *, follow_redirects, timeout, trust_env):
            assert follow_redirects is False
            assert timeout == 30.0
            assert trust_env is False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url, *, headers):
            raise httpx.ConnectError(
                "connection refused",
                request=httpx.Request("GET", url, headers=headers),
            )

    monkeypatch.setattr(main_module.httpx, "Client", FakeClient)

    response = client.get("/@vite/client")

    assert response.status_code == 502
    assert "Frontend dev server unavailable" in response.text
