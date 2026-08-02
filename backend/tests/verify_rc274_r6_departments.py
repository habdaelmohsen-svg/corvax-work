"""R6 lifecycle verification for the fleet/logistics and legal departments."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = Path("/tmp/verify_rc274_r6_departments.db")
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-r6-departments",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r6",
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

        vehicle = ok(client.post("/api/v1/departments/fleet/vehicles", headers=headers, json={
            "company_id": 1, "plate_number": "R6-TRK-001",
            "name_ar": "شاحنة مبردة R6", "name_en": "R6 Refrigerated Truck",
            "vehicle_type": "REFRIGERATED_TRUCK", "is_refrigerated": True,
            "odometer_km": 25000,
        }), 201)
        driver = ok(client.post("/api/v1/departments/fleet/drivers", headers=headers, json={
            "company_id": 1, "name_ar": "سائق تحقق R6", "name_en": "R6 Driver",
            "license_number": "R6-LIC-001", "license_expiry": "2027-12-31",
            "phone": "0500000000",
        }), 201)
        foreign_vehicle = client.post("/api/v1/departments/fleet/trips", headers=headers, json={
            "company_id": 2, "vehicle_id": vehicle["id"], "driver_id": driver["id"],
            "trip_date": "2026-08-01", "origin_ar": "الرياض", "destination_ar": "المدينة",
        })
        assert foreign_vehicle.status_code == 422
        trip = ok(client.post("/api/v1/departments/fleet/trips", headers=headers, json={
            "company_id": 1, "vehicle_id": vehicle["id"], "driver_id": driver["id"],
            "trip_date": "2026-08-01", "origin_ar": "الرياض", "destination_ar": "المدينة",
            "purpose": "DELIVERY", "distance_km": 850, "fuel_cost": 550,
            "cargo_description_ar": "مواد غذائية مبردة", "cargo_temperature": 4,
        }), 201)
        trips = ok(client.get("/api/v1/departments/fleet/trips?company_id=1", headers=headers))
        stored_trip = next(row for row in trips if row["id"] == trip["id"])
        assert stored_trip["vehicle_plate"] == vehicle["plate_number"]
        assert stored_trip["driver_name_ar"] == "سائق تحقق R6"
        assert float(stored_trip["cargo_temperature"]) == 4

        contract = ok(client.post("/api/v1/departments/legal/contracts", headers=headers, json={
            "company_id": 1, "title_ar": "عقد توريد R6", "title_en": "R6 Supply Contract",
            "contract_type": "SUPPLIER", "counterparty_ar": "مورد الاختبار",
            "start_date": "2026-08-01", "end_date": "2027-07-31",
            "value": 125000, "auto_renew": False,
        }), 201)
        case = ok(client.post("/api/v1/departments/legal/cases", headers=headers, json={
            "company_id": 1, "title_ar": "مطالبة تجارية R6", "title_en": "R6 Commercial Claim",
            "case_type": "COMMERCIAL", "counterparty_ar": "طرف الاختبار",
            "court_ar": "المحكمة التجارية", "filing_date": "2026-08-02",
            "hearing_date": "2026-09-01", "claim_amount": 25000,
        }), 201)
        license_row = ok(client.post("/api/v1/departments/legal/licenses", headers=headers, json={
            "company_id": 1, "name_ar": "رخصة تشغيل R6", "name_en": "R6 Operating License",
            "license_type": "OPERATING_LICENSE", "license_number": "R6-OP-001",
            "issuer_ar": "جهة الاختبار", "issue_date": "2026-01-01",
            "expiry_date": "2027-12-31",
        }), 201)
        contracts = ok(client.get("/api/v1/departments/legal/contracts?company_id=1", headers=headers))
        cases = ok(client.get("/api/v1/departments/legal/cases?company_id=1", headers=headers))
        licenses = ok(client.get("/api/v1/departments/legal/licenses?company_id=1", headers=headers))
        assert any(row["id"] == contract["id"] and float(row["value"]) == 125000 for row in contracts)
        assert any(row["id"] == case["id"] and float(row["claim_amount"]) == 25000 for row in cases)
        assert any(row["id"] == license_row["id"] and row["status"] == "VALID" for row in licenses)

    DB_PATH.unlink(missing_ok=True)
    print("CORVAX RC27.4 R6 FLEET AND LEGAL LIFECYCLES VERIFIED")


if __name__ == "__main__":
    main()
