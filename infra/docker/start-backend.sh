#!/bin/sh

set -eu

if [ -n "${FRONTEND_DEV_HOST:-}" ]; then
    FRONTEND_DEV_URL="$(python -c "import os, socket; host = os.environ['FRONTEND_DEV_HOST']; port = os.environ.get('FRONTEND_DEV_PORT', '5173'); print(f'http://{socket.gethostbyname(host)}:{port}')")"
    export FRONTEND_DEV_URL
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
