"""R6 verification for document storage, configuration and session controls."""
from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_rc274_r6_document_security_lifecycle.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-r6-documents",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
})
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def main() -> None:
    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={
            "email": "admin@corvaxplatform.com", "password": "Corvax@123",
        }))
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        # Company context must be explicit and return the caller's real scope.
        context = ok(client.post("/api/v1/auth/company-context", headers=headers, json={"company_id": 1}))
        assert context["company_id"] == 1 and context["status"] == "active"
        assert context["permissions"]

        # Configuration lifecycles: create, reject duplicates/invalid policy, deactivate.
        category = ok(client.post("/api/v1/assets/categories", headers=headers, json={
            "company_id": 1, "code": "R6-DOC-EQP", "name_ar": "معدات تحقق R6",
            "name_en": "R6 Verification Equipment", "useful_life_months": 60,
            "residual_percent": 5, "depreciation_convention": "FULL_MONTH_BY_15TH",
        }), 201)
        assert category["code"] == "R6-DOC-EQP" and category["useful_life_months"] == 60
        duplicate = client.post("/api/v1/assets/categories", headers=headers, json={
            "company_id": 1, "code": "R6-DOC-EQP", "name_ar": "مكرر",
            "name_en": "Duplicate", "useful_life_months": 12,
        })
        assert duplicate.status_code == 409

        tax = ok(client.post("/api/v1/compliance/tax-codes", headers=headers, json={
            "company_id": 1, "code": "R6-ZERO", "name_ar": "صفري تحقق R6",
            "name_en": "R6 Zero Rated", "direction": "SALES", "category": "ZERO_RATED",
            "rate": 0, "return_box": "1", "deductible_percent": 100,
            "tax_category_code": "Z", "effective_from": "2026-01-01",
        }), 201)
        assert tax["active"] is True and float(tax["rate"]) == 0
        invalid_tax = client.post("/api/v1/compliance/tax-codes", headers=headers, json={
            "company_id": 1, "code": "R6-BAD-ZERO", "name_ar": "خاطئ",
            "name_en": "Invalid", "direction": "SALES", "category": "ZERO_RATED",
            "rate": 15, "return_box": "1", "effective_from": "2026-01-01",
        })
        assert invalid_tax.status_code == 422
        tax_off = ok(client.patch(f"/api/v1/compliance/tax-codes/{tax['id']}/status", headers=headers, json={"active": False}))
        assert tax_off["active"] is False

        # Inline attachment round-trip, safety headers, tenant isolation and deletion.
        raw = b"%PDF-1.4\nR6 controlled attachment\n%%EOF\n"
        attachment = ok(client.post("/api/v1/attachments", headers=headers, json={
            "company_id": 1, "entity_type": "OTHER", "entity_id": 6001,
            "file_name": "../r6-controlled.pdf", "content_type": "application/pdf",
            "content_base64": base64.b64encode(raw).decode(),
            "description_ar": "مرفق اختبار دورة المستند",
        }), 201)
        assert attachment["file_name"] == "r6-controlled.pdf"
        assert attachment["size_bytes"] == len(raw)
        assert attachment["checksum_sha256"] == hashlib.sha256(raw).hexdigest()
        listed = ok(client.get("/api/v1/attachments?company_id=1&entity_type=OTHER&entity_id=6001", headers=headers))
        assert [row["id"] for row in listed] == [attachment["id"]]
        download = client.get(f"/api/v1/attachments/{attachment['id']}/download?company_id=1", headers=headers)
        assert download.status_code == 200 and download.content == raw
        assert download.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in download.headers["content-security-policy"]
        cross_company = client.get(f"/api/v1/attachments/{attachment['id']}/download?company_id=2", headers=headers)
        assert cross_company.status_code == 404
        deleted = ok(client.delete(f"/api/v1/attachments/{attachment['id']}?company_id=1", headers=headers))
        assert deleted == {"deleted": True, "id": attachment["id"]}
        assert client.get(f"/api/v1/attachments/{attachment['id']}/download?company_id=1", headers=headers).status_code == 404

        # Executable masquerading as a PDF must be rejected.
        unsafe = client.post("/api/v1/attachments", headers=headers, json={
            "company_id": 1, "entity_type": "OTHER", "entity_id": 6002,
            "file_name": "unsafe.pdf", "content_type": "application/pdf",
            "content_base64": base64.b64encode(b"MZ-not-a-pdf").decode(),
        })
        assert unsafe.status_code == 415

        # AI help must return traceable guidance, not mutate data.
        ai = ok(client.post("/api/v1/ai-assistant/messages", headers=headers, json={
            "company_id": 1, "mode": "help", "message": "كيف أراجع المرفقات؟",
            "locale": "ar", "screen_context": {"module": "attachments", "screen": "list"},
        }))
        assert ai["answer"] and ai["conversation_id"] and ai["tool_trace_id"]
        assert ai["sources"]

        # Session revocation is proven by using the same token after logout.
        logout = ok(client.post("/api/v1/auth/logout", headers=headers))
        assert logout["status"] == "logged_out" and logout["revoked_sessions"] == 1
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    DB_PATH.unlink(missing_ok=True)
    print("CORVAX RC27.4 R6 DOCUMENT, CONFIGURATION AND SESSION LIFECYCLES VERIFIED")


if __name__ == "__main__":
    main()
