from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / 'backend/app/main.py').read_text()
health = main[main.index('@app.get("/health")'):main.index('@app.get("/health/live")')]
ready = main[main.index('@app.get("/health/ready")'):main.index('@app.get("/metrics"')]
assert '"active"' not in health
assert 'SELECT version_num FROM alembic_version' in ready
assert 'Migration head mismatch' in ready
print('verify_health_contract: PASSED')
