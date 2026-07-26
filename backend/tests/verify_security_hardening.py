from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
login = (ROOT / 'frontend/src/components/Login.tsx').read_text()
client = (ROOT / 'frontend/src/api/client.ts').read_text()
auth = (ROOT / 'backend/app/api/auth.py').read_text()
app = (ROOT / 'frontend/src/App.tsx').read_text()

assert "useState('admin@corvaxplatform.com')" not in login
assert "useState('Corvax@123')" not in login
assert "corvax_refresh_token" not in client
assert "localStorage.getItem(ACCESS_KEY)" not in client
assert "sessionStorage.getItem(ACCESS_KEY)" in client
assert 'httponly=True' in auth
assert 'response.delete_cookie("corvax_refresh_token"' in auth
assert "sessionStorage.getItem(CORVAX_KEYS.token)" in app
print('verify_security_hardening: PASSED')
