# Docker Runtime Notes

当前仓库默认使用 `infra/docker-compose.yml` 启动本地依赖组，项目名为 `CodeScope`。

当前系统暂未整体部署到 Docker 中，因此推荐模式是：

- 后端、前端、Worker 在宿主机本地运行
- PostgreSQL / Redis / MinIO / Ollama 通过 Docker 启动

`infra/docker-compose.app.yml` 仍保留给后续整套应用容器化时使用，但不是当前默认路径。

Before the first startup, copy the committed example env file:

```bash
cp infra/docker.env.example infra/docker.env
```

当前本地 Docker 依赖组包含：

- `postgres`: primary application database.
- `redis`: Celery broker and result backend.
- `minio`: 对象存储与任务日志兼容路径。
- `ollama`: system-level local AI runtime used by the AI Center and asynchronous AI enrichment jobs.

`neo4j` 不属于常驻依赖组：

- 外部扫描模式下由扫描任务运行时按需拉起临时 Neo4j 容器
- 不需要在当前 `CodeScope` 本地依赖组里常驻运行

当前模式下，不需要放入 Docker 的服务：

- `backend`
- `frontend`
- `worker`

启动当前本地 Docker 依赖组：

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis minio ollama
```

可访问：

- `http://127.0.0.1:5432`
- `http://127.0.0.1:6379`
- `http://127.0.0.1:19000`
- `http://127.0.0.1:19001`
- `http://127.0.0.1:11434`

Ollama 集成说明：

- `infra/docker-compose.yml` 已将 `ollama` 加入当前本地 `CodeScope` 组，容器名为 `CodeScope_ollama`。
- Ollama 对宿主机暴露为 `http://127.0.0.1:11434`。
- 后端会在首次访问 AI 相关能力时自动创建系统级 Ollama Provider，并优先探测 `CODESCOPE_AI_SYSTEM_OLLAMA_BASE_URL`，默认值为 `http://127.0.0.1:11434`。
- 为了兼容后续容器化部署，后端还会自动尝试 `http://localhost:11434` 和 `http://ollama:11434` 作为回退地址。
- 管理员打开 `AI Center -> System Ollama` 时，可以直接看到自动探测结果，不需要先手工填地址。
- Ordinary users can then choose either the published system Ollama models or their own external API profiles when creating scan jobs or AI chat sessions.

本地宿主机运行建议：

- 后端读取 `CODESCOPE_AI_SYSTEM_OLLAMA_BASE_URL=http://127.0.0.1:11434`
- 前端继续本地 `npm run dev`
- 后端继续本地 `uv run uvicorn app.main:app --reload`
- Worker 继续本地 `uv run celery -A app.worker.celery_app worker -Q import,scan,patch,env,report,low -l info`

If you want GPU-backed Ollama locally, add your platform-specific GPU settings to the `ollama` service before startup. The committed Compose file stays CPU-safe by default.

Default bootstrap login after migrations:

- email: `admin`
- password: `admin123`

停止当前本地 Docker 依赖组：

```bash
docker compose -f infra/docker-compose.yml down
```

删除容器和本地卷：

```bash
docker compose -f infra/docker-compose.yml down -v
```

如果后续需要把整套系统也放进 Docker，再切换到 `infra/docker-compose.app.yml`，并把 `CODESCOPE_AI_SYSTEM_OLLAMA_BASE_URL` 改成容器网络可达的 `http://ollama:11434` 即可。
