@echo off
setlocal
cd /d %~dp0\backend
if not exist .venv py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
start "" http://localhost:8000
uvicorn app.main:app --host 0.0.0.0 --port 8000
endlocal
