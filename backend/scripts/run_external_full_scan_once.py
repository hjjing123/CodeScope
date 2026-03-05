from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import SystemRole, User
from app.security.password import hash_password


def main() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with session_local() as db:
        _seed_user(db)

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db

        with tempfile.TemporaryDirectory(prefix="codescope-external-full-") as tmp_dir:
            root = Path(tmp_dir)
            settings = get_settings()
            _configure_settings(settings=settings, temp_root=root)

            with TestClient(app) as client:
                tokens = _login(client, email="full-smoke@example.com", password="Password123!")
                project_id = _create_project(client, tokens["access_token"])
                version_id = _create_version(client, tokens["access_token"], project_id)
                _create_source_snapshot(Path(settings.snapshot_storage_root), version_id)
                job_id = _create_scan_job(client, tokens["access_token"], project_id, version_id)

                detail = client.get(
                    f"/api/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                ).json()["data"]
                logs = client.get(
                    f"/api/v1/jobs/{job_id}/logs",
                    params={"tail": 2000},
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                ).json()["data"]["items"]

            output = {
                "job_id": job_id,
                "status": detail.get("status"),
                "failure_code": detail.get("failure_code"),
                "stage": detail.get("stage"),
                "result_summary": detail.get("result_summary"),
                "log_count": len(logs),
                "log_tail": logs[-12:],
            }
            print(json.dumps(output, ensure_ascii=True, indent=2))

    app.dependency_overrides.clear()
    engine.dispose()


def _seed_user(db: Session) -> None:
    user = User(
        email="full-smoke@example.com",
        password_hash=hash_password("Password123!"),
        display_name="full-smoke",
        role=SystemRole.DEVELOPER.value,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()


def _configure_settings(*, settings, temp_root: Path) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    workspace_root = backend_root.parent
    reports_root = temp_root / "reports"
    snapshots_root = temp_root / "snapshots"
    scans_root = temp_root / "scan-workspaces"
    logs_root = temp_root / "job-logs"
    reports_root.mkdir(parents=True, exist_ok=True)
    snapshots_root.mkdir(parents=True, exist_ok=True)
    scans_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    settings.scan_engine_mode = "external"
    settings.scan_dispatch_backend = "sync"
    settings.scan_dispatch_fallback_to_sync = True
    settings.scan_external_runner_command = ""

    settings.snapshot_storage_root = str(snapshots_root)
    settings.scan_workspace_root = str(scans_root)
    settings.scan_log_root = str(logs_root)
    settings.scan_external_reports_dir = str(reports_root / "{job_id}")
    settings.scan_external_runner_workdir = str(backend_root)

    settings.scan_external_stage_joern_command = "builtin:joern"
    settings.scan_external_stage_import_command = "builtin:neo4j_import"
    settings.scan_external_stage_post_labels_command = "builtin:post_labels"
    settings.scan_external_stage_rules_command = "builtin:rules"

    settings.scan_external_joern_home = str(workspace_root / "infra" / "tools" / "joern-cli")
    settings.scan_external_joern_bin = str(workspace_root / "infra" / "tools" / "joern-cli" / "joern.bat")
    settings.scan_external_joern_export_script = str(backend_root / "assets" / "scan" / "joern" / "export_java_min.sc")

    settings.scan_external_post_labels_cypher = str(backend_root / "assets" / "scan" / "query" / "post_labels.cypher")
    settings.scan_external_rules_dir = str(backend_root / "assets" / "scan" / "rules")
    settings.scan_external_rules_allowlist_file = str(backend_root / "assets" / "scan" / "rules" / "allowlist.txt")
    settings.scan_external_rules_max_count = int(os.getenv("CODESCOPE_SCAN_EXTERNAL_RULES_MAX_COUNT", "1"))

    settings.scan_external_neo4j_uri = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_URI", "bolt://127.0.0.1:7687")
    settings.scan_external_neo4j_user = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_USER", "neo4j")
    settings.scan_external_neo4j_password = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD", "")
    settings.scan_external_neo4j_database = os.getenv("CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE", "neo4j")
    settings.scan_external_neo4j_connect_retry = 30
    settings.scan_external_neo4j_connect_wait_seconds = 1

    settings.scan_external_import_docker_image = os.getenv("CODESCOPE_SCAN_EXTERNAL_IMPORT_DOCKER_IMAGE", "neo4j:latest")
    settings.scan_external_import_data_mount = os.getenv("CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT", "data")
    settings.scan_external_import_database = settings.scan_external_neo4j_database
    settings.scan_external_import_clean_db = True
    settings.scan_external_import_preflight = True
    settings.scan_external_import_multiline_fields = True
    settings.scan_external_import_array_delimiter = "\\001"

    settings.scan_external_neo4j_runtime_restart_mode = "docker"
    settings.scan_external_neo4j_runtime_container_name = os.getenv(
        "CODESCOPE_SCAN_EXTERNAL_NEO4J_CONTAINER_NAME",
        "neo4j",
    )
    settings.scan_external_neo4j_runtime_restart_wait_seconds = 8


def _login(client: TestClient, *, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["data"]


def _create_project(client: TestClient, access_token: str) -> str:
    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "live-full-smoke-project"},
    )
    response.raise_for_status()
    return response.json()["data"]["id"]


def _create_version(client: TestClient, access_token: str, project_id: str) -> str:
    response = client.post(
        f"/api/v1/projects/{project_id}/versions",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": "live-full-smoke-v1",
            "source": "UPLOAD",
            "snapshot_object_key": "snapshots/live-full-smoke-v1.zip",
        },
    )
    response.raise_for_status()
    return response.json()["data"]["id"]


def _create_source_snapshot(snapshot_root: Path, version_id: str) -> None:
    source_dir = snapshot_root / version_id / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SmokeController.java").write_text(
        "public class SmokeController {\n"
        "  public String echo(String input) {\n"
        "    return input;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )


def _create_scan_job(client: TestClient, access_token: str, project_id: str, version_id: str) -> str:
    response = client.post(
        "/api/v1/scan-jobs",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"project_id": project_id, "version_id": version_id, "scan_mode": "FULL"},
    )
    response.raise_for_status()
    return response.json()["data"]["job_id"]


if __name__ == "__main__":
    main()
