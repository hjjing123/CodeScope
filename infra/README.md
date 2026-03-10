# Docker Runtime Notes

`infra/docker-compose.yml` still only starts infrastructure dependencies.

Use `infra/docker-compose.app.yml` when you want the full local Docker runtime for this repository.

Before the first startup, copy the committed example env file:

```bash
cp infra/docker.env.example infra/docker.env
```

Required for the current code paths:

- `backend`: FastAPI API and frontend reverse proxy.
- `frontend`: Vite dev server used because the current frontend tree does not pass `npm run build` yet.
- `worker`: Celery worker for import jobs and asynchronous scan/self-test jobs.
- `postgres`: primary application database.
- `redis`: Celery broker and result backend.
- shared `codescope_backend_storage` volume: upload, snapshot, scan workspace, and task log local storage.

Not required for the default Docker runtime:

- a separate production static-file container: once the frontend build is clean, the backend can serve `frontend/dist` directly.
- `minio`: task logs can fall back to local filesystem storage (`CODESCOPE_TASK_LOG_STORAGE_BACKEND=local`).
- `neo4j`: only needed when you switch from stub scan mode to external scan mode.
- `infra/tools/joern-cli`: only needed for external scan mode, so it is intentionally not baked into the default image.

Start the app stack:

```bash
docker compose -f infra/docker-compose.app.yml up --build -d
```

Open:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/healthz`

The backend proxies `/`, `/login`, `/register`, `/dashboard`, assets, and SPA routes to the internal Vite container, so you only need to open port `8000`.

Default bootstrap login after migrations:

- email: `admin@example.com`
- password: `admin123`

Stop and remove containers:

```bash
docker compose -f infra/docker-compose.app.yml down
```

Remove containers plus local Docker volumes:

```bash
docker compose -f infra/docker-compose.app.yml down -v
```

If you later need external scan mode, add Neo4j, Docker socket access, Joern runtime, and container/host path mapping intentionally instead of enabling them by default.
