"""CORVAX RC16 operational workspace verification."""
from __future__ import annotations
import os, sys
from pathlib import Path
BACKEND_DIR=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_DIR))
DB_PATH=BACKEND_DIR/'data'/'verify_v116.db';DB_PATH.unlink(missing_ok=True)
os.environ.update({'DATABASE_URL':f'sqlite:///{DB_PATH}','SECRET_KEY':'verification-secret-key-corvax-rc16','SEED_DEMO_DATA':'true','AUTO_CREATE_SCHEMA':'true','TRUSTED_HOSTS':'testserver,localhost,127.0.0.1','APP_VERSION':'1.0.0-agreement-completion-rc27.3','ENABLE_RATE_LIMIT_TESTING':'true'})
from fastapi.testclient import TestClient
from app.main import app

def main():
    with TestClient(app) as client:
        login=client.post('/api/v1/auth/login',json={'email':'admin@corvaxplatform.com','password':'Corvax@123'})
        assert login.status_code==200,login.text
        headers={'Authorization':f"Bearer {login.json()['access_token']}"}
        queue=client.get('/api/v1/workspace/work-queue?company_id=2',headers=headers)
        assert queue.status_code==200,queue.text
        payload=queue.json();assert 'items' in payload and 'by_module' in payload and payload['control']['maker_checker'] is True
        search=client.get('/api/v1/workspace/search?company_id=2&q=POSTED',headers=headers)
        assert search.status_code==200,search.text
        export=client.get('/api/v1/workspace/work-queue.csv?company_id=2',headers=headers)
        assert export.status_code==200,export.text
        assert export.content.startswith(b'\xef\xbb\xbf') and b'module,item_type' in export.content
    print('CORVAX v1.0 RC16 operational workspace: ALL VERIFICATIONS PASSED')
if __name__=='__main__':main()
