# CodeScope Backend

Backend service for the CodeScope platform.

## Local development

```bash
uv sync --extra dev
# load PostgreSQL + Redis + MinIO settings from ./config/database.env
docker compose -f ../infra/docker-compose.yml up -d postgres redis minio
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# run Celery worker from backend code
uv run codescope-worker
```

## Test

```bash
uv run pytest -q
```

## Migration

```bash
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

Notes:

- Database settings are read from `backend/config/database.env` (`CODESCOPE_DATABASE_URL`).
- Local PostgreSQL container is `CodeScope_postgresql`.
- Local Redis container is `CodeScope_redis` (`redis://127.0.0.1:6379`).
- Local MinIO container is `CodeScope_minio` (`http://127.0.0.1:19000`, console `http://127.0.0.1:19001`).
- Worker process runs from backend code: `uv run codescope-worker` (or `uv run python -m app.worker`).
- Task logs are stored in MinIO (`CODESCOPE_TASK_LOG_STORAGE_BACKEND=minio`), metadata is indexed in PostgreSQL (`task_log_index`).
- `alembic upgrade head` seeds/normalizes a bootstrap admin for local login debug.
- Default bootstrap admin credentials are `admin@example.com / admin123` (override via `CODESCOPE_BOOTSTRAP_ADMIN_*`).
- Backend serves frontend `dist` for `/`, `/login`, `/register`, `/dashboard`; run `npm run build` in `frontend/` before direct access via `http://127.0.0.1:8000/`.
- Public registration endpoint: `POST /api/v1/auth/register` (`role` supports `Developer` / `RedTeam`).

Project import/version module:

- Upload import: `POST /api/v1/projects/{project_id}/imports/upload`
- Git import: `POST /api/v1/projects/{project_id}/imports/git`
- Import job query: `GET /api/v1/import-jobs/{job_id}`
- Version tree/file browse: `GET /api/v1/versions/{version_id}/tree`, `GET /api/v1/versions/{version_id}/file`
- Import idempotency: pass `Idempotency-Key` header for replay-safe trigger
- Credential placeholder: when `credential_id` is provided, API returns `CREDENTIAL_PROVIDER_NOT_CONFIGURED`

Storage defaults (local object gateway):

- `CODESCOPE_IMPORT_WORKSPACE_ROOT=./storage/workspaces/imports`
- `CODESCOPE_SNAPSHOT_STORAGE_ROOT=./storage/snapshots`

External scan (four-stage orchestration):

- Joern tool home (trimmed Java profile): `../infra/tools/joern-cli`
- Joern export script: `./assets/scan/joern/export_java_min.sc`
- Built-in stage defaults:
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_JOERN_COMMAND=builtin:joern`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_IMPORT_COMMAND=builtin:neo4j_import`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_POST_LABELS_COMMAND=builtin:post_labels`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_RULES_COMMAND=builtin:rules`
- Stage commands are overrideable (optional):
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_JOERN_COMMAND`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_IMPORT_COMMAND`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_POST_LABELS_COMMAND`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_RULES_COMMAND`
- Stage timeouts (seconds):
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_JOERN_TIMEOUT_SECONDS`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_IMPORT_TIMEOUT_SECONDS`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_POST_LABELS_TIMEOUT_SECONDS`
  - `CODESCOPE_SCAN_EXTERNAL_STAGE_RULES_TIMEOUT_SECONDS`
- Built-in assets:
  - `CODESCOPE_SCAN_EXTERNAL_POST_LABELS_CYPHER=./assets/scan/query/post_labels.cypher`
  - `CODESCOPE_SCAN_EXTERNAL_RULES_DIR=./assets/scan/rules`
  - `CODESCOPE_SCAN_EXTERNAL_RULES_ALLOWLIST_FILE=./assets/scan/rules/allowlist.txt`
  - `CODESCOPE_SCAN_EXTERNAL_RULES_MAX_COUNT=0` (0 means no cap)
- Neo4j runtime:
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_URI`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_USER`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE`
- Neo4j admin import runtime:
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DOCKER_IMAGE`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DATABASE`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_MODE` (`none` or `docker`)
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_CONTAINER_NAME`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_WAIT_SECONDS`

Optional live smoke test (requires reachable Neo4j):

- `CODESCOPE_RUN_EXTERNAL_SMOKE=1`
- `CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD=<password>`
- Run: `python -m pytest tests/test_scan_job_module.py -q -k live_smoke`

Optional live full smoke (includes builtin Joern + neo4j-admin import):

- `CODESCOPE_RUN_EXTERNAL_FULL_SMOKE=1`
- `CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD=<password>`
- Optional: `CODESCOPE_SCAN_EXTERNAL_NEO4J_CONTAINER_NAME=neo4j`
- Run: `python -m pytest tests/test_scan_job_module.py -q -k full_smoke`
