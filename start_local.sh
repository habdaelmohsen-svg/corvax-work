#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
