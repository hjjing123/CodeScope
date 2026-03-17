# AGENTS Guide for This Repository

## Scope and current state
- Current repo content is design documentation under `文档/`; no runnable source tree is present yet.
- No `package.json`, `pyproject.toml`, `go.mod`, or `Cargo.toml` was found.
- Intended stack (from docs): FastAPI + Celery + Redis + PostgreSQL + Neo4j + MinIO, plus React + TypeScript + Vite + antd.
- Use this file as the baseline operating contract until real build config files are committed.

## Expected layout when code is added
- `backend/`: FastAPI app, Celery workers, Python tests.
- `frontend/`: React/Vite app, TypeScript tests.
- `infra/`: docker compose, deployment and local dependency setup.
- `文档/`: architecture specs; keep aligned with implementation.

## Build, lint, and test commands

## Backend (Python/FastAPI/Celery)
- Dependency install (choose one standard and keep consistent):
- `uv sync` (preferred) or `pip install -r requirements.txt`.
- Run API locally:
- `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
- Run worker:
- `uv run celery -A app.worker.celery_app worker -Q import,scan,patch,env,report,low -l info`.
- Lint:
- `uv run ruff check backend`.
- Format:
- `uv run ruff format backend`.
- Type-check:
- `uv run mypy backend`.
- Test all:
- `uv run pytest -q`.
- Single test file:
- `uv run pytest backend/tests/test_jobs.py -q`.
- Single test function (node id):
- `uv run pytest backend/tests/test_jobs.py::test_scan_job_timeout -q`.
- Single test class:
- `uv run pytest backend/tests/test_api_findings.py::TestFindingList -q`.
- Pattern-based subset:
- `uv run pytest -k "timeout and scan" -q`.

## Frontend (React/TypeScript/Vite)
- Dependency install:
- `npm ci` (preferred in CI) or `npm install` (local dev).
- Dev server:
- `npm run dev`.
- Type-check:
- `npm run typecheck`.
- Lint:
- `npm run lint`.
- Format check:
- `npm run format:check`.
- Build:
- `npm run build`.
- Test all:
- `npm run test` (or `npm test`).
- Single test file (Vitest style):
- `npm run test -- src/pages/FindingsPage.test.tsx`.
- Single test by name:
- `npm run test -- -t "renders risk overview"`.

## Full-stack and integration
- Start local dependencies:
- `docker compose up -d postgres redis minio ollama`.
- Typical local run:
- Start frontend in `frontend/`, API and worker in `backend/`.
- Expected critical E2E path:
- Upload -> Scan -> Findings -> Report.
- Patch -> Verify.
- AI path:
- Configure system Ollama or personal external API -> Scan with AI enabled -> AI enrichment job -> Finding AI review/chat.

## Recommended CI order
- Backend: `ruff check` -> `ruff format --check` -> `mypy` -> `pytest`.
- Frontend: `npm run lint` -> `npm run typecheck` -> `npm run test -- --run` -> `npm run build`.
- Use lockfiles and non-interactive commands for reproducibility.

## Code style guidelines

## General principles
- Prefer readability, traceability, and explicit side effects.
- Keep route/controller layers thin; move business logic to services.
- Keep I/O boundaries obvious and auditable.
- Include identifiers (`request_id`, `job_id`, `project_id`, `version_id`) in operational flows.

## Formatting and structure
- Python target: 3.11+.
- Formatter/linter: Ruff (`ruff check`, `ruff format`).
- Line length target: 100 unless project config says otherwise.
- Favor small focused modules over large multi-purpose files.

## Imports
- Order groups: stdlib -> third-party -> local.
- Avoid wildcard imports.
- Prefer one import per line (except tightly coupled typing imports).
- Use local imports only for optional heavy deps or to break cycles.

## Naming conventions
- Python module/file: `snake_case.py`.
- Python functions/variables: `snake_case`.
- Classes/types/components: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Async functions should be verb-first and explicit (`fetch_findings`, `run_scan_job`).
- Celery task names should be stable and explicit (`scan.run_version_scan`).

## Typing and data models
- Prefer concrete typing; avoid `Any` unless justified.
- Use Pydantic models (or `TypedDict` where appropriate) for API/data contracts.
- Validate untrusted input at API boundaries.
- Avoid returning raw untyped dicts from service layers when a model is feasible.

## Error handling and logging
- Never silently swallow exceptions.
- Raise domain-specific errors in service/repository layers.
- Map domain errors to consistent API-level error contracts.
- Redact secrets/tokens/credentials from logs and error payloads.
- AI/optional subsystems must fail open and never block core scan/result flows.

## FastAPI conventions
- Keep request/response schemas explicit.
- Use dependency injection for auth, DB session, and permission checks.
- Keep pagination/sorting conventions consistent across endpoints.
- Preserve backward compatibility for public API fields where possible.

## React/TypeScript conventions
- Use strict TypeScript; avoid `any` in props and API clients.
- Prefer functional components and hooks.
- Keep components focused; extract reusable hooks/utils.
- Use explicit UI state names (`isLoading`, `hasError`, `selectedVersionId`).
- Separate loading, empty, and failure states clearly.

## Testing guidelines
- Keep tests deterministic; mock external systems at boundaries.
- Unit tests: business rules, status transitions, permission checks, error mapping.
- Integration tests: API + DB behavior.
- E2E tests: core security workflow paths from docs.
- Name tests as behavior statements (`test_marks_scan_timeout_with_stage`).

## Security and operational guardrails
- Treat uploaded archives and Git inputs as untrusted.
- Enforce zip-slip/path traversal protection in import pipelines.
- Use command allowlists for worker execution.
- Isolate per-task workspaces to avoid cross-task contamination.
- Use least privilege for services and containers.

## Documentation and change management
- Update docs in `文档/` when behavior diverges from design.
- Record major decisions (schema/queue/error model) in ADR-style notes.
- When adding or changing commands, update this file and CI config in the same PR.

## Cursor and Copilot rules
- No Cursor rules were found in `.cursor/rules/` or `.cursorrules`.
- No Copilot rules file was found in `.github/copilot-instructions.md`.
- If these files appear later, import their non-conflicting rules here and honor stricter rules first.

## Agent execution checklist
- Confirm target area (`backend/`, `frontend/`, `infra/`) before editing.
- During iteration, run the smallest relevant test set first (single test preferred).
- Before handoff, run lint/type-check/tests relevant to changed files.
- If validation is partial, state exactly what was run and what was skipped.
