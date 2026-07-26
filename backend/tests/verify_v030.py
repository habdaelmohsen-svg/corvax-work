"""Brand migration verification for CORVAX v0.30."""
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as client:
    health = client.get('/health')
    assert health.status_code == 200, health.text
    payload = health.json()
    assert payload['app'].startswith('CORVAX'), payload
    assert payload['version'] == '1.0.0-agreement-completion-rc27.3', payload

    login = client.post('/api/v1/auth/login', json={
        'email': 'admin@corvaxplatform.com',
        'password': 'Corvax@123',
    })
    assert login.status_code == 200, login.text
    assert login.json().get('access_token')

runtime_files = [
    Path('app/core/config.py'),
    Path('../frontend/src/components/Login.tsx'),
    Path('../frontend/src/components/CompanySelector.tsx'),
    Path('../frontend/src/components/Dashboard.tsx'),
]
for file in runtime_files:
    text = file.read_text(encoding='utf-8')
    assert 'NEXORA' not in text, file

print('CORVAX v0.30 brand migration: ALL VERIFICATIONS PASSED')
