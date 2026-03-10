# CodeScope Backend

Backend service for the CodeScope platform.

## Local development (quick start)

```bash
uv sync --extra dev
# load PostgreSQL + Redis + MinIO + Neo4j settings from ./config/database.env
docker compose -f ../infra/docker-compose.yml up -d postgres redis minio neo4j
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# run Celery worker from backend code
uv run codescope-worker
```

## WSL local run (recommended for external scan)

Run all backend and scan commands inside WSL Ubuntu.

### 1) Prerequisites

- Windows 11 + WSL2 (Ubuntu)
- Docker Desktop with WSL integration enabled
- `uv` installed in WSL
- `infra/tools/joern-cli` exists (for builtin `joern`)

Install `uv` once in WSL if needed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2) Prerequisite checks in WSL

```bash
cd /mnt/e/CodeScope/backend
python3 --version
uv --version
docker --version
docker info --format '{{.ServerVersion}}'
```

### 3) Start dependencies and backend

```bash
cd /mnt/e/CodeScope/backend
export UV_PROJECT_ENVIRONMENT=.venv-wsl
uv sync --extra dev
docker compose -f ../infra/docker-compose.yml up -d postgres redis minio neo4j
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open another WSL terminal:

```bash
cd /mnt/e/CodeScope/backend
export UV_PROJECT_ENVIRONMENT=.venv-wsl
uv run codescope-worker
```

Or start the full dev stack from the repo root:

```bash
cd /mnt/e/CodeScope
./start-dev-wsl.sh
```

`start-dev-wsl.sh` automatically syncs `backend/.venv-wsl` when `uv` is available, so it does not conflict with a Windows-created `backend/.venv`.

### 4) Recommended WSL scan-related env defaults

The backend defaults to WSL runtime profile. Keep these values in `backend/config/database.env`:

```dotenv
CODESCOPE_SCAN_ENGINE_MODE=external
CODESCOPE_SCAN_EXTERNAL_RUNTIME_PROFILE=wsl
CODESCOPE_SCAN_EXTERNAL_CONTAINER_COMPAT_MODE=0
CODESCOPE_SCAN_EXTERNAL_STAGE_JOERN_COMMAND=builtin:joern
CODESCOPE_SCAN_EXTERNAL_STAGE_IMPORT_COMMAND=builtin:neo4j_import
CODESCOPE_SCAN_EXTERNAL_STAGE_POST_LABELS_COMMAND=builtin:post_labels
CODESCOPE_SCAN_EXTERNAL_STAGE_RULES_COMMAND=builtin:rules
CODESCOPE_SCAN_EXTERNAL_IMPORT_CSV_HOST_PATH=
```

`CODESCOPE_SCAN_EXTERNAL_IMPORT_CSV_HOST_PATH` can be empty for WSL mode. The system falls back to scan workspace `import_csv` path automatically.

## Test

```bash
uv run pytest -q
```

## Migration

```bash
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

## WSL troubleshooting

- `SCAN_EXTERNAL_NOT_CONFIGURED` + message `WSL 模式下导入目录必须为 Linux 绝对路径`
  - Cause: import host path is Windows-style (`C:/...`) while runtime profile is `wsl`.
  - Fix: use Linux path (`/mnt/...`) or leave `CODESCOPE_SCAN_EXTERNAL_IMPORT_CSV_HOST_PATH` empty.
- `SCAN_EXTERNAL_IMPORT_FAILED` + detail `failure_kind=docker_daemon_unreachable`
  - Cause: Docker daemon is not reachable from WSL.
  - Fix: start Docker Desktop and enable WSL integration; verify with `docker info`.
- `SCAN_EXTERNAL_JOERN_FAILED` + message `Joern 导出关键 CSV 产物缺失`
  - Cause: Joern export did not produce required `nodes_*` / `edges_*` CSV files.
  - Fix: verify `infra/tools/joern-cli` is complete and `CODESCOPE_SCAN_EXTERNAL_JOERN_EXPORT_SCRIPT` path is valid.
- `SCAN_EXTERNAL_IMPORT_FAILED` + detail `failure_kind=import_mount_unreachable`
  - Cause: Docker cannot mount CSV source directory.
  - Fix: ensure the source path is visible in WSL and Docker Desktop file sharing policy allows it.
- Neo4j auth/connection failures during import/post-labels/rules
  - Cause: invalid `CODESCOPE_SCAN_EXTERNAL_NEO4J_*` settings.
  - Fix: verify `bolt://127.0.0.1:7687`, username, password, and target database.
- `SCAN_EXTERNAL_RULES_FAILED` during rules stage
  - Cause: rule query execution failed in Neo4j or the rule statement itself has a runtime problem.
  - Fix: inspect the failed rule detail and verify the Cypher syntax, graph schema assumptions, and Neo4j runtime environment.
- `SCAN_EXTERNAL_RULES_FAILED` + message `规则执行失败（strict 模式）`
  - Cause: `CODESCOPE_SCAN_EXTERNAL_RULES_FAILURE_MODE=strict` and at least one rule failed.
  - Fix: inspect failed rule detail and fix rule/Neo4j runtime issue, or switch to `permissive` mode.

Notes:

- Database settings are read from `backend/config/database.env` (`CODESCOPE_DATABASE_URL`).
- Local PostgreSQL container is `CodeScope_postgresql`.
- Local Redis container is `CodeScope_redis` (`redis://127.0.0.1:6379`).
- Local MinIO container is `CodeScope_minio` (`http://127.0.0.1:19000`, console `http://127.0.0.1:19001`).
- Local Neo4j container is `CodeScope_neo4j` (`http://127.0.0.1:7474`, `bolt://127.0.0.1:7687`).
- Worker process runs from backend code: `uv run codescope-worker` (or `uv run python -m app.worker`).
- On Windows, worker defaults to `solo` pool (`concurrency=1`) to avoid `billiard` spawn permission errors.
- If you run Celery manually on Windows, add `-P solo` (example: `uv run celery -A app.worker.celery_app worker -Q import,scan,env,report,low -l info -P solo`).
- Task logs are stored in MinIO (`CODESCOPE_TASK_LOG_STORAGE_BACKEND=minio`), metadata is indexed in PostgreSQL (`task_log_index`).
- `alembic upgrade head` seeds/normalizes a bootstrap admin for local login debug.
- Default bootstrap admin credentials are `admin@example.com / admin123` (override via `CODESCOPE_BOOTSTRAP_ADMIN_*`).
- Backend serves frontend `dist` for `/`, `/login`, `/register`, `/dashboard`; run `npm run build` in `frontend/` before direct access via `http://127.0.0.1:8000/`.
- In frontend dev-proxy mode, tune `FRONTEND_DEV_PROXY_TIMEOUT_SECONDS` if the first Vite render is slow while dependencies are being optimized.
- Public registration endpoint: `POST /api/v1/auth/register` (`role` supports `Admin` / `User`).

Code management module:

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
  - `CODESCOPE_SCAN_EXTERNAL_RULES_MAX_COUNT=0` (0 means no cap)
  - `CODESCOPE_SCAN_EXTERNAL_RULES_FAILURE_MODE=permissive` (`permissive` or `strict`)
- Neo4j runtime:
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_URI`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_USER`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_DATABASE`
- Neo4j admin import runtime:
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DOCKER_IMAGE`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_CSV_HOST_PATH`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DATABASE`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_ID_TYPE`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_ARRAY_DELIMITER`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_CLEAN_DB`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_MULTILINE_FIELDS`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_MULTILINE_FIELDS_FORMAT`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_PREFLIGHT`
  - `CODESCOPE_SCAN_EXTERNAL_IMPORT_PREFLIGHT_CHECK_DOCKER`
  - `CODESCOPE_SCAN_EXTERNAL_CLEANUP_HOST_PATH_ALLOWLIST`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_MODE` (`none`, `docker`, or `docker_ephemeral`)
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_CONTAINER_NAME`
  - `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_WAIT_SECONDS`
  - `CODESCOPE_SCAN_EXTERNAL_RUNTIME_MAX_SLOTS`
  - `CODESCOPE_SCAN_EXTERNAL_RUNTIME_SLOT_WAIT_SECONDS`
  - `CODESCOPE_SCAN_EXTERNAL_RUNTIME_SLOT_TIMEOUT_SECONDS`
- Containerized backend/worker for builtin `neo4j_import`:
  - Mount docker socket: `/var/run/docker.sock:/var/run/docker.sock`
  - Mount repo workspace to keep import host path visible in container and host
  - Recommended task-scoped pair:
    - `CODESCOPE_SCAN_EXTERNAL_IMPORT_CSV_HOST_PATH=/workspace/backend/storage/workspaces/scans`
    - `CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT=codescope_neo4j_data_{job_id}`
  - If `CODESCOPE_SCAN_EXTERNAL_IMPORT_DATA_MOUNT` uses a host path instead of a Docker volume name, cleanup only deletes paths under `CODESCOPE_SCAN_EXTERNAL_CLEANUP_HOST_PATH_ALLOWLIST`
  - Recommended runtime mode: `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_RESTART_MODE=docker_ephemeral`
  - Recommended runtime container template: `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_CONTAINER_NAME=codescope_neo4j_{job_id}`

Optional live smoke test (requires reachable Neo4j):

- `CODESCOPE_RUN_EXTERNAL_SMOKE=1`
- `CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD=<password>`
- Run: `python -m pytest tests/test_scan_job_module.py -q -k live_smoke`

Optional live full smoke (includes builtin Joern + neo4j-admin import):

- `CODESCOPE_RUN_EXTERNAL_FULL_SMOKE=1`
- `CODESCOPE_SCAN_EXTERNAL_NEO4J_PASSWORD=<password>`
- Optional: `CODESCOPE_SCAN_EXTERNAL_NEO4J_RUNTIME_CONTAINER_NAME=codescope_neo4j_{job_id}`
- Run: `python -m pytest tests/test_scan_job_module.py -q -k full_smoke`
