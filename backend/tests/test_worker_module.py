from __future__ import annotations

import sys

import pytest

from app.worker.celery_app import celery_app


def test_celery_worker_tasks_are_discoverable() -> None:
    if celery_app is None:
        pytest.skip("Celery is not available in current environment")

    celery_app.loader.import_default_modules()

    assert "scan.run_scan_job" in celery_app.tasks
    assert "ai.run_system_ollama_pull_job" in celery_app.tasks
    assert "import.run_import_job" in celery_app.tasks
    assert "rule.run_selftest_job" in celery_app.tasks
    assert "rule.aggregate_stats" in celery_app.tasks


def test_celery_worker_pool_default_matches_platform() -> None:
    if celery_app is None:
        pytest.skip("Celery is not available in current environment")

    expected_pool = "solo" if sys.platform.startswith("win") else "prefork"
    assert celery_app.conf.worker_pool == expected_pool
    if expected_pool == "solo":
        assert int(celery_app.conf.worker_concurrency) == 1
