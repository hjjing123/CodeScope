from __future__ import annotations

import sys
from typing import Any

from app.config import get_settings

try:
    from celery import Celery
except Exception:  # pragma: no cover
    Celery = None  # type: ignore[assignment]


def create_celery_app() -> Any | None:
    if Celery is None:
        return None

    settings = get_settings()
    is_windows = sys.platform.startswith("win")
    app = Celery("codescope", include=["app.worker.tasks"])
    config: dict[str, Any] = {
        "broker_url": settings.celery_broker_url,
        "result_backend": settings.celery_result_backend,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "task_always_eager": settings.celery_task_always_eager,
        "task_eager_propagates": settings.celery_task_eager_propagates,
        "task_routes": {
            "scan.run_scan_job": {"queue": "scan"},
            "import.run_import_job": {"queue": "import"},
            "rule.run_selftest_job": {"queue": "low"},
            "rule.aggregate_stats": {"queue": "low"},
        },
    }

    if is_windows:
        config["worker_pool"] = "solo"
        config["worker_concurrency"] = 1

    app.conf.update(**config)
    return app


celery_app = create_celery_app()
