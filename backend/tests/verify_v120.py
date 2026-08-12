"""CORVAX RC20 import VAT, landed cost, recursive costing, perpetual inventory and budget analytics verification."""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = Path("/tmp") / "verify_v120.db"
DB_PATH.unlink(missing_ok=True)
os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "SECRET_KEY": "verification-secret-key-corvax-rc20-operational-controls",
    "SEED_DEMO_DATA": "true",
    "AUTO_CREATE_SCHEMA": "true",
    "TRUSTED_HOSTS": "testserver,localhost,127.0.0.1",
    "APP_VERSION": "1.0.0-agreement-completion-rc27.4-r9.3",
    "ENABLE_RATE_LIMIT_TESTING": "true",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account, BillOfMaterial, BillOfMaterialLine, FiscalPeriod, FiscalYear, Item, ManufacturingRouting,
    ManufacturingRoutingOperation, Party, StockMovement, Warehouse, WorkCenter,
)
from app.services.posting import create_posted_journal  # noqa: E402


def D(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def main():
    with TestClient(app) as client:
        login = ok(client.post("/api/v1/auth/login", json={"email": "admin@corvaxplatform.com", "password": "Corvax@123"}))
        admin = {"Authorization": f"Bearer {login['access_token']}"}
        assert ok(client.get("/health"))["version"] == "1.0.0-agreement-completion-rc27.4-r9.3"
        second = ok(client.post("/api/v1/admin/users", headers=admin, json={
            "name_ar": "مراجع RC20", "name_en": "RC20 Independent Approver", "email": "rc20.approver@corvaxplatform.com",
            "password": "Rc20Approver@123", "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "SUPER_ADMIN"}],
        }), 201)
        controller = ok(client.post("/api/v1/admin/users", headers=admin, json={
            "name_ar": "مراقب تكاليف RC20", "name_en": "RC20 Cost Controller", "email": "rc20.controller@corvaxplatform.com",
            "password": "Rc20Controller@123", "require_password_change": False, "memberships": [{"company_id": 1, "role_code": "FINANCIAL_CONTROLLER"}],
        }), 201)
        approver_login = ok(client.post("/api/v1/auth/login", json={"email": "rc20.approver@corvaxplatform.com", "password": "Rc20Approver@123"}))
        approver = {"Authorization": f"Bearer {approver_login['access_token']}"}
        controller_login = ok(client.post("/api/v1/auth/login", json={"email": "rc20.controller@corvaxplatform.com", "password": "Rc20Controller@123"}))
        controller_h = {"Authorization": f"Bearer {controller_login['access_token']}"}

        with SessionLocal() as db:
            for period in db.query(FiscalPeriod).all(): period.status = "OPEN"
            db.commit()
            supplier = db.scalar(select(Party).where(Party.company_id == 1, Party.party_type.in_(["SUPPLIER", "BOTH"])))
            customer = db.scalar(select(Party).where(Party.company_id == 1, Party.party_type.in_(["CUSTOMER", "BOTH"])))
            warehouse = db.scalar(select(Warehouse).where(Warehouse.company_id == 1))
            inv = db.scalar(select(Account).where(Account.company_id == 1, Account.code == "113010"))
            cogs = db.scalar(select(Account).where(Account.company_id == 1, Account.code == "511010"))
            rev = db.scalar(select(Account).where(Account.company_id == 1, Account.code == "411010"))
            raw = Item(company_id=1, code="RC20-RAW", name_ar="مادة خام", name_en="Raw material", item_type="RAW_MATERIAL", uom="KG", standard_cost=10,
                       inventory_account_id=inv.id, cogs_account_id=cogs.id, revenue_account_id=rev.id)
            pack = Item(company_id=1, code="RC20-PKG", name_ar="عبوة", name_en="Packaging", item_type="PACKAGING", uom="EA", standard_cost=2,
                        inventory_account_id=inv.id, cogs_account_id=cogs.id, revenue_account_id=rev.id)
            semi = Item(company_id=1, code="RC20-SEMI", name_ar="منتج نصف مصنع", name_en="Semi finished", item_type="WIP", uom="KG", standard_cost=0,
                        inventory_account_id=inv.id, cogs_account_id=cogs.id, revenue_account_id=rev.id)
            final = Item(company_id=1, code="RC20-FG", name_ar="منتج نهائي", name_en="Finished product", item_type="FINISHED_GOOD", uom="EA", standard_cost=20,
                         inventory_account_id=inv.id, cogs_account_id=cogs.id, revenue_account_id=rev.id)
            db.add_all([raw, pack, semi, final]); db.flush()
            wc = WorkCenter(company_id=1, code="RC20-WC", name_ar="خط الإنتاج", name_en="Production line", hourly_labor_rate=30, hourly_overhead_rate=8,
                            direct_expense_rate=4, variable_overhead_rate=8, fixed_overhead_rate=6)
            db.add(wc); db.flush()
            bom_semi = BillOfMaterial(company_id=1, code="BOM-RC20-SEMI", version=1, finished_item_id=semi.id, output_quantity=1, work_center_id=wc.id, standard_hours=0, status="ACTIVE")
            bom_semi.lines.append(BillOfMaterialLine(component_item_id=raw.id, quantity=1.5, scrap_percent=10))
            db.add(bom_semi); db.flush()
            bom_final = BillOfMaterial(company_id=1, code="BOM-RC20-FG", version=1, finished_item_id=final.id, output_quantity=10, work_center_id=wc.id, standard_hours=0, status="ACTIVE")
            bom_final.lines.extend([BillOfMaterialLine(component_item_id=semi.id, quantity=5, scrap_percent=0), BillOfMaterialLine(component_item_id=pack.id, quantity=10, scrap_percent=0)])
            db.add(bom_final); db.flush()
            routing = ManufacturingRouting(company_id=1, code="ROUTE-RC20", version=1, finished_item_id=final.id, bom_id=bom_final.id,
                effective_from=date(2026, 1, 1), status="APPROVED", prepared_by=1, approved_by=second["id"])
            routing.operations.append(ManufacturingRoutingOperation(sequence=10, operation_code="MIX", name_ar="خلط وتعبئة", name_en="Mix and pack", work_center_id=wc.id,
                setup_minutes=30, run_minutes_per_unit=3, standard_labor_rate=30, standard_overhead_rate=8, outside_processing_cost=1, quality_gate=True))
            db.add(routing)
            # Opening perpetual inventory, with matching GL.
            opening_value = Decimal("10000")
            j = create_posted_journal(db, company_id=1, user_id=1, posting_date=date(2026, 1, 1), reference="RC20-OPEN-STOCK", description="RC20 opening inventory",
                lines=[{"account_id": inv.id, "debit": opening_value, "credit": 0}, {"account_id": db.scalar(select(Account).where(Account.company_id==1, Account.code=="312010")).id, "debit":0,"credit":opening_value}])
            db.add(StockMovement(company_id=1, warehouse_id=warehouse.id, item_id=raw.id, movement_date=date(2026,1,1), movement_type="OPENING", quantity=800,
                unit_cost=10, total_cost=8000, reference_type="OPENING", reference_id=1, journal_id=j.id, created_by=1))
            db.add(StockMovement(company_id=1, warehouse_id=warehouse.id, item_id=pack.id, movement_date=date(2026,1,1), movement_type="OPENING", quantity=1000,
                unit_cost=2, total_cost=2000, reference_type="OPENING", reference_id=1, journal_id=j.id, created_by=1))
            db.commit()
            supplier_id, customer_id, warehouse_id, raw_id, final_id = supplier.id, customer.id, warehouse.id, raw.id, final.id

        # Tax codes and foreign invoice no Saudi VAT.
        codes = ok(client.get("/api/v1/compliance/tax-codes?company_id=1", headers=admin))
        assert {"PFOR0", "PIMPR15", "PIMPS0", "PIMPE"}.issubset({x["code"] for x in codes})
        with SessionLocal() as db:
            accounts = {
                row.code: row
                for row in db.scalars(
                    select(Account).where(Account.company_id == 1)
                ).all()
            }
            receipt_journal = create_posted_journal(
                db,
                company_id=1,
                user_id=1,
                posting_date=date(2026, 11, 1),
                reference="RC20-IMPORT-GRN",
                description="Foreign inventory receipt before supplier invoice",
                lines=[
                    {"account_id": accounts["113010"].id, "debit": 10000, "credit": 0},
                    {"account_id": accounts["214010"].id, "debit": 0, "credit": 10000},
                ],
            )
            db.add(
                StockMovement(
                    company_id=1,
                    warehouse_id=warehouse_id,
                    item_id=raw_id,
                    movement_date=date(2026, 11, 1),
                    movement_type="PURCHASE_RECEIPT",
                    quantity=1000,
                    unit_cost=10,
                    total_cost=10000,
                    reference_type="GOODS_RECEIPT",
                    reference_id=None,
                    journal_id=receipt_journal.id,
                    created_by=1,
                )
            )
            db.commit()
        foreign_pi = ok(client.post("/api/v1/subledgers/purchase-invoices", headers=admin, json={
            "company_id": 1, "invoice_date": "2026-11-01", "due_date": "2026-12-01", "supplier_id": supplier_id, "supplier_invoice_number": "BR-FOREIGN-001",
            "lines": [{"description":"Brazil supplier invoice - no Saudi VAT", "account_code":"214010", "quantity":1, "unit_price":10000, "tax_code":"PFOR0"}],
        }), 201)
        ok(client.post(f"/api/v1/subledgers/purchase-invoices/{foreign_pi['id']}/post", headers=admin))

        # Customs declaration shows zero VAT collected, while VAT is accounted in the return.
        imp = ok(client.post("/api/v1/operational-controls/imports", headers=admin, json={
            "company_id":1,"declaration_date":"2026-11-05","supplier_id":supplier_id,"purchase_invoice_id":foreign_pi["id"],"origin_country":"BRA",
            "customs_reference":"CUSTOMS-RC20-001","treatment":"THROUGH_RETURN","customs_value":10000,"customs_duty":500,"vat_base":10500,"vat_rate":15,
            "vat_collected_on_declaration":0,"vat_accounted_in_return":1575,"evidence":{"customs_statement":"attached"},
        }), 201)
        assert imp["vat_collected_on_declaration"] == 0 and imp["zero_customs_vat_reason"] == "THROUGH_RETURN"
        ok(client.post(f"/api/v1/operational-controls/imports/{imp['id']}/submit", headers=admin))
        assert client.post(f"/api/v1/operational-controls/imports/{imp['id']}/approve", headers=admin).status_code == 409
        ok(client.post(f"/api/v1/operational-controls/imports/{imp['id']}/approve", headers=approver))
        posted_imp = ok(client.post(f"/api/v1/operational-controls/imports/{imp['id']}/post", headers=approver))
        assert posted_imp["journal_id"]

        # Export must be pending until evidence is approved.
        export_invoice = ok(client.post("/api/v1/subledgers/sales-invoices", headers=admin, json={
            "company_id":1,"invoice_date":"2026-11-10","due_date":"2026-12-10","customer_id":customer_id,"reference":"EXPORT-RC20",
            "lines":[{"description":"Export sale","account_code":"411010","quantity":1,"unit_price":20000,"tax_code":"SEX"}],
        }), 201)
        ok(client.post(f"/api/v1/subledgers/sales-invoices/{export_invoice['id']}/post", headers=admin))
        vat1 = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={"company_id":1,"period_start":"2026-11-01","period_end":"2026-11-30"}), 201)
        box1 = {x["box_code"]:x for x in vat1["lines"]}
        assert D(box1["SALES_EXPORT_PENDING_EVIDENCE"]["base_amount"]) == Decimal("20000.00") and vat1["classification_complete"] is False
        ev = ok(client.post("/api/v1/operational-controls/exports/evidence", headers=admin, json={
            "company_id":1,"sales_invoice_id":export_invoice["id"],"export_declaration_number":"EXP-RC20-001","export_date":"2026-11-11",
            "destination_country":"ARE","exit_port":"Jeddah","transport_document":"BL-RC20-001","evidence":{"exit_confirmation":True},
        }), 201)
        ok(client.post(f"/api/v1/operational-controls/exports/evidence/{ev['id']}/submit", headers=admin))
        ok(client.post(f"/api/v1/operational-controls/exports/evidence/{ev['id']}/approve", headers=approver))
        vat2 = ok(client.post("/api/v1/compliance/vat-return", headers=admin, json={"company_id":1,"period_start":"2026-11-01","period_end":"2026-11-30"}), 201)
        box2 = {x["box_code"]:x for x in vat2["lines"]}
        assert D(box2["SALES_EXPORT"]["base_amount"]) == Decimal("20000.00")
        assert D(box2["PURCHASE_IMPORTS_THROUGH_RETURN"]["tax_amount"]) == Decimal("1575.00")
        assert D(vat2["output_vat"]) == D(vat2["gl_output_vat"])
        assert D(vat2["input_vat"]) == D(vat2["gl_input_vat"])

        # Receipt and landed cost allocation.
        po = ok(client.post("/api/v1/inventory/purchase-orders", headers=admin, json={
            "company_id":1,"order_date":"2026-11-12","expected_receipt_date":"2026-11-15","supplier_id":supplier_id,"warehouse_id":warehouse_id,
            "lines":[{"item_id":raw_id,"quantity":100,"unit_price":10,"vat_rate":0}],
        }), 201)
        ok(client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/approve", headers=approver))
        grn = ok(client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/receive", headers=admin, json={
            "receipt_date":"2026-11-15","lines":[{"purchase_order_line_id":po["lines"][0]["id"],"quantity":100,"lot_number":"BR-LOT-01","expiry_date":"2027-12-31"}],
        }), 201)
        lc = ok(client.post("/api/v1/operational-controls/landed-costs", headers=admin, json={
            "company_id":1,"document_date":"2026-11-16","goods_receipt_id":grn["id"],"import_declaration_id":imp["id"],"allocation_method":"VALUE",
            "charges":[
                {"supplier_id":supplier_id,"supplier_invoice_number":"FRT-RC20","invoice_date":"2026-11-16","due_date":"2026-12-16","charge_type":"FREIGHT","description":"Foreign freight","amount":1000,"capitalizable":True,"tax_code":"PFOR0"},
                {"supplier_id":supplier_id,"supplier_invoice_number":"CLR-RC20","invoice_date":"2026-11-16","due_date":"2026-12-16","charge_type":"CLEARANCE","description":"Local clearance","amount":500,"capitalizable":True,"tax_code":"P15"},
            ],
        }), 201)
        ok(client.post(f"/api/v1/operational-controls/landed-costs/{lc['id']}/submit", headers=admin))
        ok(client.post(f"/api/v1/operational-controls/landed-costs/{lc['id']}/approve", headers=approver))
        lc_posted = ok(client.post(f"/api/v1/operational-controls/landed-costs/{lc['id']}/post", headers=approver))
        assert D(lc_posted["total_capitalizable_cost"]) == Decimal("1500.00") and len(lc_posted["allocations"]) == 1
        with SessionLocal() as db:
            landed_value = db.scalar(select(StockMovement.total_cost).where(StockMovement.reference_type=="LANDED_COST", StockMovement.reference_id==lc["id"]))
            assert D(landed_value) == Decimal("1500.00")

        # Recursive BOM explosion and all cost elements.
        roll = ok(client.post("/api/v1/operational-controls/cost-rollups", headers=admin, json={
            "company_id":1,"item_id":final_id,"quantity":100,"as_of_date":"2026-11-30","cost_basis":"STANDARD",
        }), 201)
        types={x["line_type"] for x in roll["lines"]}
        assert {"DIRECT_MATERIAL","PACKAGING","DIRECT_LABOR","DIRECT_EXPENSE","VARIABLE_OVERHEAD","FIXED_OVERHEAD"}.issubset(types)
        assert D(roll["total_cost"]) == D(roll["direct_material_cost"]+roll["packaging_cost"]+roll["direct_labor_cost"]+roll["direct_expense_cost"]+roll["variable_overhead_cost"]+roll["fixed_overhead_cost"])
        ok(client.post(f"/api/v1/operational-controls/cost-rollups/{roll['id']}/review", headers=controller_h))
        approved_roll = ok(client.post(f"/api/v1/operational-controls/cost-rollups/{roll['id']}/approve", headers=approver))
        assert approved_roll["status"] == "APPROVED"
        rollups = ok(client.get("/api/v1/operational-controls/cost-rollups?company_id=1&limit=10", headers=admin))
        assert rollups and rollups[0]["id"] == roll["id"] and rollups[0]["item_code"] == "RC20-FG"
        assert D(rollups[0]["unit_cost"]) == D(approved_roll["unit_cost"])

        # Physical count, perpetual posting, aging and NRV write-down.
        cnt = ok(client.post("/api/v1/operational-controls/inventory-counts", headers=admin, json={"company_id":1,"warehouse_id":warehouse_id,"count_date":"2026-11-30","count_type":"CYCLE"}), 201)
        for line in cnt["lines"]:
            counted = D(line["book_quantity"])-Decimal("1") if line["item_id"]==raw_id else D(line["book_quantity"])
            ok(client.patch(f"/api/v1/operational-controls/inventory-counts/{cnt['id']}/lines/{line['id']}", headers=admin, json={"counted_quantity":str(counted),"reason":"Test count"}))
        ok(client.post(f"/api/v1/operational-controls/inventory-counts/{cnt['id']}/submit", headers=admin))
        posted_count = ok(client.post(f"/api/v1/operational-controls/inventory-counts/{cnt['id']}/approve", headers=approver))
        assert posted_count["status"] == "POSTED"
        aging = ok(client.get("/api/v1/operational-controls/inventory-aging?company_id=1&as_of=2026-11-30&slow_days=30&obsolete_days=180", headers=admin))
        assert any(x["item_id"]==raw_id for x in aging["rows"])
        wd = ok(client.post("/api/v1/operational-controls/inventory-write-downs", headers=admin, json={
            "company_id":1,"warehouse_id":warehouse_id,"item_id":raw_id,"write_down_date":"2026-11-30","reason_type":"NRV","quantity":10,"nrv_unit_cost":5,
        }), 201)
        ok(client.post(f"/api/v1/operational-controls/inventory-write-downs/{wd['id']}/approve", headers=approver))
        rec = ok(client.get("/api/v1/operational-controls/perpetual-reconciliation?company_id=1&as_of=2026-11-30", headers=admin))
        assert "rows" in rec and len(rec["rows"]) >= 1

        # UOM conversion.
        uom = ok(client.post("/api/v1/operational-controls/uom-conversions", headers=admin, json={"company_id":1,"item_id":raw_id,"from_uom":"BAG","to_uom":"KG","factor":25}), 201)
        assert D(uom["factor"]) == Decimal("25.00")

        # Budget vs actual vs historical, daily/monthly/annual and automatic comment.
        with SessionLocal() as db:
            fy = db.scalar(select(FiscalPeriod).where(FiscalPeriod.start_date <= date(2026,11,1), FiscalPeriod.end_date >= date(2026,11,1))).fiscal_year_id
        budget = ok(client.post("/api/v1/budgets", headers=admin, json={
            "company_id":1,"fiscal_year_id":fy,"name":"RC20 Operating Budget",
            "lines":[{"account_code":"613010","period_number":11,"amount":3000},{"account_code":"411010","period_number":11,"amount":25000}],
        }), 201)
        ok(client.post(f"/api/v1/budgets/{budget['id']}/approve", headers=approver))
        with SessionLocal() as db:
            exp=db.scalar(select(Account).where(Account.company_id==1,Account.code=="613010")); bank=db.scalar(select(Account).where(Account.company_id==1,Account.code=="111010"))
            if not db.scalar(select(FiscalYear).where(FiscalYear.company_id==1, FiscalYear.name=="2025")):
                fy25=FiscalYear(company_id=1,name="2025",start_date=date(2025,1,1),end_date=date(2025,12,31),status="OPEN")
                db.add(fy25);db.flush()
                for month in range(1,13):
                    db.add(FiscalPeriod(fiscal_year_id=fy25.id,number=month,name_ar=f"2025-{month:02d}",name_en=f"2025-{month:02d}",start_date=date(2025,month,1),end_date=date(2025,month,__import__('calendar').monthrange(2025,month)[1]),status="OPEN"))
                db.flush()
            create_posted_journal(db,company_id=1,user_id=1,posting_date=date(2026,11,20),reference="RC20-ACTUAL",description="RC20 actual expense",
                lines=[{"account_id":exp.id,"debit":2500,"credit":0},{"account_id":bank.id,"debit":0,"credit":2500}])
            create_posted_journal(db,company_id=1,user_id=1,posting_date=date(2025,11,20),reference="RC20-HIST",description="RC20 historical expense",
                lines=[{"account_id":exp.id,"debit":2000,"credit":0},{"account_id":bank.id,"debit":0,"credit":2000}])
            db.commit()
        monthly = ok(client.get(f"/api/v1/operational-controls/budget-analytics?budget_id={budget['id']}&start_date=2026-11-01&end_date=2026-11-30&granularity=MONTHLY&historical_years=1", headers=admin))
        assert monthly["rows"] and all(x["comment"] for x in monthly["rows"])
        daily = ok(client.get(f"/api/v1/operational-controls/budget-analytics?budget_id={budget['id']}&start_date=2026-11-20&end_date=2026-11-20&granularity=DAILY&historical_years=1", headers=admin))
        annual = ok(client.get(f"/api/v1/operational-controls/budget-analytics?budget_id={budget['id']}&start_date=2026-01-01&end_date=2026-12-31&granularity=ANNUAL&historical_years=1", headers=admin))
        assert daily["granularity"]=="DAILY" and annual["granularity"]=="ANNUAL"
        csv_response = client.get(f"/api/v1/operational-controls/budget-analytics/export.csv?budget_id={budget['id']}&start_date=2026-11-01&end_date=2026-11-30", headers=admin)
        assert csv_response.status_code==200 and csv_response.content.startswith(b"\xef\xbb\xbf")
        import_csv=client.get("/api/v1/operational-controls/imports/export.csv?company_id=1",headers=admin)
        assert import_csv.status_code==200 and b"THROUGH_RETURN" in import_csv.content

    print("CORVAX v1.0 RC20 operational finance controls: ALL VERIFICATIONS PASSED")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
