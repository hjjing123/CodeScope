from __future__ import annotations

import argparse

from app.worker.celery_app import celery_app


DEFAULT_QUEUES = "import,scan,patch,env,report,low"


def run_worker(*, queues: str, log_level: str) -> int:
    if celery_app is None:
        raise RuntimeError("Celery is not available in current environment")

    argv = ["worker", "-Q", queues, "-l", log_level]
    result = celery_app.worker_main(argv)
    return 0 if result is None else int(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CodeScope Celery worker")
    parser.add_argument(
        "--queues",
        default=DEFAULT_QUEUES,
        help="Comma-separated queue names",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        help="Worker log level",
    )
    args = parser.parse_args()
    raise SystemExit(run_worker(queues=args.queues, log_level=args.log_level))


if __name__ == "__main__":
    main()
