from __future__ import annotations

import csv
import hashlib
import io
import json
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account, BillOfMaterial, BillOfMaterialLine, Budget, BudgetLine, CostRollupLine,
    CostRollupSnapshot, ExportEvidence, FiscalPeriod, FiscalYear, GoodsReceipt,
    GoodsReceiptLine, ImportDeclaration, ImportDeclarationLine, InventoryCount,
    InventoryCountLine, InventoryWriteDown, Item, ItemUomConversion, JournalEntry,
    JournalLine, LandedCostAllocation, LandedCostCharge, LandedCostDocument,
    ManufacturingRouting, ManufacturingRoutingOperation, Party, PurchaseInvoice,
    PurchaseInvoiceLine, SalesInvoice, StockMovement, TaxCode, User, Warehouse,
    WorkCenter,
)
from app.services.ar_ap import ensure_purchase_invoice_open_item
from app.services.audit import write_audit
from app.services.operations import get_account, get_item, get_warehouse, money, quantity, stock_balance, stock_value
from app.services.posting import create_posted_journal, ensure_open_period
from app.services.tax import calculate_line, ensure_default_tax_codes

router = APIRouter(prefix="/operational-controls", tags=["trade costing inventory budget controls"])

Q6 = Decimal("0.000001")


def q6(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q6, rounding=ROUND_HALF_UP)


def _number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(select(func.count(model.id)).where(model.company_id == company_id)) or 0
    return f"{prefix}-{company_id}-{year}-{int(count)+1:05d}"


def _same_company(row, company_id: int, label: str):
    if not row or row.company_id != company_id:
        raise HTTPException(404, f"{label} not found")
    return row


def _maker_checker(creator_id: int | None, user_id: int):
    if creator_id == user_id:
        raise HTTPException(409, "Maker-checker control: creator cannot approve or review the same document")


def _party(db: Session, company_id: int, party_id: int, party_type: str | None = None) -> Party:
    row = db.scalar(select(Party).where(Party.id == party_id, Party.company_id == company_id, Party.active.is_(True)))
    if not row or (party_type and row.party_type not in {party_type, "BOTH"}):
        raise HTTPException(404, "Party not found or incompatible")
    return row


def _csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ------------------------- Imports / exports -------------------------

class ImportLineIn(BaseModel):
    item_id: int | None = None
    hs_code: str | None = None
    description: str = Field(min_length=2, max_length=500)
    quantity: Decimal = Field(default=0, ge=0)
    uom: str = "EA"
    customs_value: Decimal = Field(default=0, ge=0)
    customs_duty: Decimal = Field(default=0, ge=0)
    excise_tax: Decimal = Field(default=0, ge=0)
    other_charges: Decimal = Field(default=0, ge=0)
    vat_base: Decimal = Field(default=0, ge=0)
    vat_due: Decimal = Field(default=0, ge=0)


class ImportDeclarationIn(BaseModel):
    company_id: int
    declaration_date: date
    supplier_id: int | None = None
    purchase_invoice_id: int | None = None
    goods_receipt_id: int | None = None
    origin_country: str = Field(min_length=2, max_length=3)
    customs_port: str | None = None
    customs_reference: str | None = None
    treatment: str
    customs_value: Decimal = Field(ge=0)
    freight_insurance_value: Decimal = Field(default=0, ge=0)
    customs_duty: Decimal = Field(default=0, ge=0)
    excise_tax: Decimal = Field(default=0, ge=0)
    other_customs_charges: Decimal = Field(default=0, ge=0)
    vat_base: Decimal = Field(default=0, ge=0)
    vat_rate: Decimal = Field(default=15, ge=0, le=100)
    vat_collected_on_declaration: Decimal = Field(default=0, ge=0)
    vat_accounted_in_return: Decimal = Field(default=0, ge=0)
    release_date: date | None = None
    evidence: dict = Field(default_factory=dict)
    lines: list[ImportLineIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_treatment(self):
        t = self.treatment.upper()
        if t not in {"AT_CUSTOMS", "THROUGH_RETURN", "SUSPENDED", "EXEMPT"}:
            raise ValueError("Invalid import VAT treatment")
        if t == "AT_CUSTOMS" and self.vat_collected_on_declaration <= 0:
            raise ValueError("AT_CUSTOMS requires VAT collected on the customs declaration")
        if t == "THROUGH_RETURN" and self.vat_collected_on_declaration != 0:
            raise ValueError("THROUGH_RETURN requires zero VAT collected on the customs declaration")
        if t in {"SUSPENDED", "EXEMPT"} and (self.vat_collected_on_declaration or self.vat_accounted_in_return):
            raise ValueError("Suspended/exempt imports cannot carry collected or return-accounted VAT at this stage")
        return self


@router.post("/imports", status_code=201)
def create_import(data: ImportDeclarationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    ensure_open_period(db, data.company_id, data.declaration_date)
    if data.supplier_id:
        _party(db, data.company_id, data.supplier_id, "SUPPLIER")
    if data.goods_receipt_id:
        _same_company(db.get(GoodsReceipt, data.goods_receipt_id), data.company_id, "Goods receipt")
    vat_due = money(data.vat_base * data.vat_rate / Decimal("100"))
    row = ImportDeclaration(
        company_id=data.company_id, number=_number(db, ImportDeclaration, data.company_id, "IMP", data.declaration_date.year),
        declaration_date=data.declaration_date, supplier_id=data.supplier_id, purchase_invoice_id=data.purchase_invoice_id,
        goods_receipt_id=data.goods_receipt_id, origin_country=data.origin_country.upper(), customs_port=data.customs_port,
        customs_reference=data.customs_reference, treatment=data.treatment.upper(), customs_value=money(data.customs_value),
        freight_insurance_value=money(data.freight_insurance_value), customs_duty=money(data.customs_duty),
        excise_tax=money(data.excise_tax), other_customs_charges=money(data.other_customs_charges), vat_base=money(data.vat_base),
        vat_rate=q6(data.vat_rate), vat_due=vat_due, vat_collected_on_declaration=money(data.vat_collected_on_declaration),
        vat_accounted_in_return=money(data.vat_accounted_in_return or (vat_due if data.treatment.upper() == "THROUGH_RETURN" else 0)),
        release_date=data.release_date, evidence_json=json.dumps(data.evidence, ensure_ascii=False), created_by=user.id,
    )
    for src in data.lines:
        if src.item_id:
            get_item(db, data.company_id, src.item_id)
        row.lines.append(ImportDeclarationLine(
            item_id=src.item_id, hs_code=src.hs_code, description=src.description, quantity=quantity(src.quantity), uom=src.uom,
            customs_value=money(src.customs_value), customs_duty=money(src.customs_duty), excise_tax=money(src.excise_tax),
            other_charges=money(src.other_charges), vat_base=money(src.vat_base), vat_due=money(src.vat_due),
        ))
    db.add(row); db.flush()
    write_audit(db, action="IMPORT_DECLARATION_CREATED", entity_type="IMPORT_DECLARATION", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"number": row.number, "treatment": row.treatment, "vat_collected": str(row.vat_collected_on_declaration)})
    db.commit()
    return _serialize_import(row)


def _serialize_import(row: ImportDeclaration) -> dict:
    return {
        "id": row.id, "company_id": row.company_id, "number": row.number, "declaration_date": row.declaration_date,
        "origin_country": row.origin_country, "customs_reference": row.customs_reference, "treatment": row.treatment,
        "customs_value": money(row.customs_value), "customs_duty": money(row.customs_duty), "excise_tax": money(row.excise_tax),
        "vat_base": money(row.vat_base), "vat_due": money(row.vat_due), "vat_collected_on_declaration": money(row.vat_collected_on_declaration),
        "vat_accounted_in_return": money(row.vat_accounted_in_return), "zero_customs_vat_reason": row.treatment if money(row.vat_collected_on_declaration) == 0 else None,
        "status": row.status, "journal_id": row.journal_id,
        "lines": [{"id": x.id, "item_id": x.item_id, "description": x.description, "quantity": x.quantity, "customs_value": x.customs_value} for x in row.lines],
    }


@router.get("/imports")
def list_imports(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(ImportDeclaration).where(ImportDeclaration.company_id == company_id).options(selectinload(ImportDeclaration.lines)).order_by(ImportDeclaration.declaration_date.desc(), ImportDeclaration.id.desc())).all()
    return [_serialize_import(row) for row in rows]


@router.post("/imports/{row_id}/submit")
def submit_import(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ImportDeclaration, row_id)
    if not row: raise HTTPException(404, "Import declaration not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft declaration can be submitted")
    row.status = "SUBMITTED"; row.submitted_by = user.id; row.submitted_at = utc_now(); db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/imports/{row_id}/approve")
def approve_import(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ImportDeclaration, row_id)
    if not row: raise HTTPException(404, "Import declaration not found")
    ensure_permission(db, user, row.company_id, "compliance.manage"); _maker_checker(row.created_by, user.id)
    if row.status != "SUBMITTED": raise HTTPException(409, "Only submitted declaration can be approved")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/imports/{row_id}/post")
def post_import(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ImportDeclaration, row_id)
    if not row: raise HTTPException(404, "Import declaration not found")
    ensure_permission(db, user, row.company_id, "compliance.manage"); _maker_checker(row.created_by, user.id)
    if row.status != "APPROVED": raise HTTPException(409, "Only approved declaration can be posted")
    journal = None
    tax = money(row.vat_collected_on_declaration if row.treatment == "AT_CUSTOMS" else row.vat_accounted_in_return if row.treatment == "THROUGH_RETURN" else 0)
    if tax:
        input_vat = get_account(db, row.company_id, "114010")
        credit = get_account(db, row.company_id, "212020" if row.treatment == "AT_CUSTOMS" else "212010")
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.declaration_date,
            reference=row.number, description=f"Import VAT {row.treatment} {row.customs_reference or row.number}",
            lines=[{"account_id": input_vat.id, "debit": tax, "credit": 0}, {"account_id": credit.id, "debit": 0, "credit": tax}])
        row.journal_id = journal.id
    row.status = "POSTED"; row.posted_by = user.id; row.posted_at = utc_now()
    write_audit(db, action="IMPORT_DECLARATION_POSTED", entity_type="IMPORT_DECLARATION", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"treatment": row.treatment, "tax": str(tax), "journal_id": row.journal_id})
    db.commit(); return _serialize_import(row)


class ExportEvidenceIn(BaseModel):
    company_id: int
    sales_invoice_id: int
    export_declaration_number: str
    export_date: date
    destination_country: str = Field(min_length=2, max_length=3)
    exit_port: str | None = None
    transport_document: str
    evidence: dict = Field(default_factory=dict)


@router.post("/exports/evidence", status_code=201)
def create_export_evidence(data: ExportEvidenceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    invoice = _same_company(db.get(SalesInvoice, data.sales_invoice_id), data.company_id, "Sales invoice")
    if invoice.status != "POSTED": raise HTTPException(409, "Export evidence requires a posted sales invoice")
    row = ExportEvidence(company_id=data.company_id, sales_invoice_id=invoice.id, export_declaration_number=data.export_declaration_number,
        export_date=data.export_date, destination_country=data.destination_country.upper(), exit_port=data.exit_port,
        transport_document=data.transport_document, evidence_json=json.dumps(data.evidence, ensure_ascii=False), created_by=user.id)
    db.add(row); db.flush(); db.commit()
    return {"id": row.id, "status": row.status, "sales_invoice_id": row.sales_invoice_id, "export_declaration_number": row.export_declaration_number}


@router.post("/exports/evidence/{row_id}/submit")
def submit_export_evidence(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ExportEvidence, row_id)
    if not row: raise HTTPException(404, "Export evidence not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft evidence can be submitted")
    row.status = "SUBMITTED"; row.submitted_by = user.id; row.submitted_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/exports/evidence/{row_id}/approve")
def approve_export_evidence(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ExportEvidence, row_id)
    if not row: raise HTTPException(404, "Export evidence not found")
    ensure_permission(db, user, row.company_id, "compliance.manage"); _maker_checker(row.created_by, user.id)
    if row.status != "SUBMITTED": raise HTTPException(409, "Only submitted evidence can be approved")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.get("/imports/export.csv")
def export_imports(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(ImportDeclaration).where(ImportDeclaration.company_id == company_id).order_by(ImportDeclaration.declaration_date)).all()
    return _csv_response("import_declarations.csv", ["Number", "Date", "Origin", "Treatment", "Customs value", "VAT collected", "VAT through return", "Status"],
        [[x.number, x.declaration_date, x.origin_country, x.treatment, x.customs_value, x.vat_collected_on_declaration, x.vat_accounted_in_return, x.status] for x in rows])


# ------------------------- Landed cost -------------------------

class LandedChargeIn(BaseModel):
    supplier_id: int
    supplier_invoice_number: str
    invoice_date: date
    due_date: date
    charge_type: str
    description: str
    amount: Decimal = Field(gt=0)
    capitalizable: bool = True
    tax_code: str


class LandedCostIn(BaseModel):
    company_id: int
    document_date: date
    goods_receipt_id: int
    import_declaration_id: int | None = None
    allocation_method: str = "VALUE"
    charges: list[LandedChargeIn] = Field(min_length=1)


@router.post("/landed-costs", status_code=201)
def create_landed_cost(data: LandedCostIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.manage")
    grn = db.scalar(select(GoodsReceipt).where(GoodsReceipt.id == data.goods_receipt_id, GoodsReceipt.company_id == data.company_id).options(selectinload(GoodsReceipt.lines)))
    if not grn: raise HTTPException(404, "Goods receipt not found")
    if data.allocation_method.upper() not in {"VALUE", "QUANTITY", "EQUAL"}: raise HTTPException(422, "Invalid allocation method")
    clearing = get_account(db, data.company_id, "119010")
    codes = ensure_default_tax_codes(db, data.company_id, user.id)
    row = LandedCostDocument(company_id=data.company_id, number=_number(db, LandedCostDocument, data.company_id, "LC", data.document_date.year),
        document_date=data.document_date, goods_receipt_id=grn.id, import_declaration_id=data.import_declaration_id,
        allocation_method=data.allocation_method.upper(), clearing_account_id=clearing.id, created_by=user.id)
    cap = Decimal("0"); noncap = Decimal("0")
    for src in data.charges:
        _party(db, data.company_id, src.supplier_id, "SUPPLIER")
        code = codes.get(src.tax_code.upper())
        if not code or code.direction not in {"PURCHASE", "BOTH"}: raise HTTPException(422, f"Invalid purchase tax code {src.tax_code}")
        calc = calculate_line(src.amount, code)
        cost = money(src.amount + (calc["non_deductible_tax"] if src.capitalizable else 0))
        cap += cost if src.capitalizable else 0; noncap += cost if not src.capitalizable else 0
        row.charges.append(LandedCostCharge(supplier_id=src.supplier_id, supplier_invoice_number=src.supplier_invoice_number,
            invoice_date=src.invoice_date, due_date=src.due_date, charge_type=src.charge_type.upper(), description=src.description,
            amount=money(src.amount), capitalizable=src.capitalizable, tax_code_id=code.id))
    row.total_capitalizable_cost = money(cap); row.total_noncapitalizable_cost = money(noncap)
    db.add(row); db.flush(); db.commit(); return _serialize_landed(row)


def _serialize_landed(row: LandedCostDocument) -> dict:
    return {"id": row.id, "number": row.number, "document_date": row.document_date, "goods_receipt_id": row.goods_receipt_id,
        "goods_receipt_number": row.goods_receipt.number if row.goods_receipt else None,
        "allocation_method": row.allocation_method, "status": row.status,
        "total_amount": money(Decimal(row.total_capitalizable_cost) + Decimal(row.total_noncapitalizable_cost)),
        "total_capitalizable_cost": row.total_capitalizable_cost,
        "total_noncapitalizable_cost": row.total_noncapitalizable_cost, "journal_id": row.journal_id,
        "charges": [{"id": c.id, "type": c.charge_type, "amount": c.amount, "capitalizable": c.capitalizable, "tax_code": c.tax_code.code if c.tax_code else None, "purchase_invoice_id": c.purchase_invoice_id} for c in row.charges],
        "allocations": [{"item_id": a.item_id, "allocated_amount": a.allocated_amount, "unit_cost_increment": a.unit_cost_increment} for a in row.allocations]}


@router.get("/landed-costs")
def list_landed_costs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    rows = db.scalars(select(LandedCostDocument).where(
        LandedCostDocument.company_id == company_id,
    ).options(
        selectinload(LandedCostDocument.charges).selectinload(LandedCostCharge.tax_code),
        selectinload(LandedCostDocument.allocations),
    ).order_by(LandedCostDocument.document_date.desc(), LandedCostDocument.id.desc())).all()
    return [_serialize_landed(row) | {"created_by": row.created_by, "submitted_by": row.submitted_by, "approved_by": row.approved_by, "posted_by": row.posted_by} for row in rows]


@router.post("/landed-costs/{row_id}/submit")
def submit_landed(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(LandedCostDocument, row_id)
    if not row: raise HTTPException(404, "Landed cost document not found")
    ensure_permission(db, user, row.company_id, "inventory.manage")
    if row.status != "DRAFT": raise HTTPException(409, "Only draft landed cost can be submitted")
    row.status = "SUBMITTED"; row.submitted_by = user.id; row.submitted_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/landed-costs/{row_id}/approve")
def approve_landed(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(LandedCostDocument, row_id)
    if not row: raise HTTPException(404, "Landed cost document not found")
    ensure_permission(db, user, row.company_id, "inventory.manage"); _maker_checker(row.created_by, user.id)
    if row.status != "SUBMITTED": raise HTTPException(409, "Only submitted landed cost can be approved")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/landed-costs/{row_id}/post")
def post_landed(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(LandedCostDocument).where(LandedCostDocument.id == row_id).options(
        selectinload(LandedCostDocument.charges).selectinload(LandedCostCharge.tax_code),
        selectinload(LandedCostDocument.goods_receipt).selectinload(GoodsReceipt.lines).selectinload(GoodsReceiptLine.item),
        selectinload(LandedCostDocument.allocations),
    ))
    if not row: raise HTTPException(404, "Landed cost document not found")
    ensure_permission(db, user, row.company_id, "inventory.manage"); _maker_checker(row.created_by, user.id)
    if row.status != "APPROVED": raise HTTPException(409, "Only approved landed cost can be posted")
    ensure_open_period(db, row.company_id, row.document_date)
    ap = get_account(db, row.company_id, "211010"); input_vat = get_account(db, row.company_id, "114010"); output_vat = get_account(db, row.company_id, "212010")
    noncap_account = get_account(db, row.company_id, "613010")
    for charge in row.charges:
        code = charge.tax_code; calc = calculate_line(charge.amount, code)
        debit_account = row.clearing_account if charge.capitalizable else noncap_account
        debit_amount = money(charge.amount + calc["non_deductible_tax"])
        lines = [{"account_id": debit_account.id, "debit": debit_amount, "credit": 0, "description": charge.description}]
        if calc["deductible_tax"]:
            lines.append({"account_id": input_vat.id, "debit": calc["deductible_tax"], "credit": 0, "description": charge.description})
        if code.category in {"REVERSE_CHARGE", "IMPORTS_RETURN"} and calc["tax"]:
            lines.append({"account_id": output_vat.id, "debit": 0, "credit": calc["tax"], "description": charge.description})
            payable = money(charge.amount)
        else:
            payable = calc["document_total"]
        lines.append({"account_id": ap.id, "debit": 0, "credit": payable, "description": charge.supplier_invoice_number})
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=charge.invoice_date,
            reference=charge.supplier_invoice_number, description=f"Landed cost charge {row.number}: {charge.description}", lines=lines)
        invoice = PurchaseInvoice(company_id=row.company_id, number=_number(db, PurchaseInvoice, row.company_id, "PI-LC", charge.invoice_date.year),
            invoice_date=charge.invoice_date, due_date=charge.due_date, supplier_id=charge.supplier_id,
            supplier_invoice_number=charge.supplier_invoice_number, status="POSTED", subtotal=money(charge.amount),
            vat_amount=money(calc["tax"] if code.category not in {"REVERSE_CHARGE", "IMPORTS_RETURN"} else 0), total=payable, journal_id=journal.id, created_by=user.id)
        invoice.lines.append(PurchaseInvoiceLine(description=charge.description, expense_account_id=debit_account.id, quantity=1,
            unit_price=money(charge.amount), vat_rate=code.rate, tax_code_id=code.id, subtotal=money(charge.amount),
            vat_amount=invoice.vat_amount, total=payable))
        db.add(invoice); db.flush(); ensure_purchase_invoice_open_item(db, invoice); charge.purchase_invoice_id = invoice.id
    cap = money(row.total_capitalizable_cost)
    if cap:
        grn_lines = row.goods_receipt.lines
        if not grn_lines: raise HTTPException(422, "Goods receipt has no lines")
        bases = []
        for line in grn_lines:
            if row.allocation_method == "VALUE": base = Decimal(line.quantity) * Decimal(line.unit_cost)
            elif row.allocation_method == "QUANTITY": base = Decimal(line.quantity)
            else: base = Decimal("1")
            bases.append(base)
        total_base = sum(bases, Decimal("0"))
        if total_base <= 0: raise HTTPException(422, "Allocation basis is zero")
        remaining = cap; journal_lines = []
        for idx, (line, base) in enumerate(zip(grn_lines, bases)):
            allocated = remaining if idx == len(grn_lines)-1 else money(cap * base / total_base)
            remaining = money(remaining - allocated)
            increment = q6(allocated / Decimal(line.quantity)) if Decimal(line.quantity) else Decimal("0")
            movement = StockMovement(company_id=row.company_id, warehouse_id=row.goods_receipt.warehouse_id, item_id=line.item_id,
                movement_date=row.document_date, movement_type="LANDED_COST", quantity=0, unit_cost=increment, total_cost=allocated,
                lot_number=line.lot_number, expiry_date=line.expiry_date, reference_type="LANDED_COST", reference_id=row.id, created_by=user.id)
            db.add(movement); db.flush()
            row.allocations.append(LandedCostAllocation(goods_receipt_line_id=line.id, item_id=line.item_id, allocation_basis=q6(base),
                allocated_amount=allocated, unit_cost_increment=increment, stock_movement_id=movement.id))
            journal_lines.append({"account_id": line.item.inventory_account_id, "debit": allocated, "credit": 0, "description": line.item.name_en})
        journal_lines.append({"account_id": row.clearing_account_id, "debit": 0, "credit": cap, "description": row.number})
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.document_date,
            reference=row.number, description=f"Allocate landed cost to inventory {row.goods_receipt.number}", lines=journal_lines)
        row.journal_id = journal.id
        for alloc in row.allocations:
            alloc.stock_movement.journal_id = journal.id
    row.status = "POSTED"; row.posted_by = user.id; row.posted_at = utc_now()
    write_audit(db, action="LANDED_COST_POSTED", entity_type="LANDED_COST", entity_id=row.id, user_id=user.id, company_id=row.company_id,
                after={"capitalized": str(row.total_capitalizable_cost), "noncapitalized": str(row.total_noncapitalizable_cost), "allocations": len(row.allocations)})
    db.commit(); return _serialize_landed(row)


# ------------------------- Recursive cost roll-up -------------------------

class CostRollupIn(BaseModel):
    company_id: int
    item_id: int
    quantity: Decimal = Field(gt=0)
    as_of_date: date
    cost_basis: str = "STANDARD"


def _active_bom(db: Session, company_id: int, item_id: int) -> BillOfMaterial | None:
    return db.scalar(select(BillOfMaterial).where(BillOfMaterial.company_id == company_id,
        BillOfMaterial.finished_item_id == item_id, BillOfMaterial.status == "ACTIVE").options(
        selectinload(BillOfMaterial.lines).selectinload(BillOfMaterialLine.component_item), selectinload(BillOfMaterial.work_center)
    ).order_by(BillOfMaterial.version.desc()))


def _unit_cost(db: Session, company_id: int, item: Item, basis: str) -> Decimal:
    if basis == "ACTUAL":
        qty = db.scalar(select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.company_id == company_id, StockMovement.item_id == item.id)) or 0
        val = db.scalar(select(func.coalesce(func.sum(StockMovement.total_cost), 0)).where(StockMovement.company_id == company_id, StockMovement.item_id == item.id)) or 0
        if Decimal(qty) > 0: return q6(Decimal(val) / Decimal(qty))
    return q6(item.standard_cost)


def _rollup(db: Session, company_id: int, item: Item, required_qty: Decimal, basis: str, path: list[int], level: int, out: list[dict]) -> dict[str, Decimal]:
    if item.id in path: raise HTTPException(422, f"BOM cycle detected at item {item.code}")
    bom = _active_bom(db, company_id, item.id)
    totals = defaultdict(Decimal)
    if not bom:
        unit = _unit_cost(db, company_id, item, basis); total = money(required_qty * unit)
        kind = "PACKAGING" if item.item_type.upper() in {"PACKAGING", "PACK"} or item.code.upper().startswith("PKG") else "DIRECT_MATERIAL"
        totals[kind] += total
        out.append({"level": level, "path": "/".join(map(str, path+[item.id])), "parent_item_id": path[-1] if path else None,
            "item_id": item.id, "line_type": kind, "description_ar": item.name_ar, "description_en": item.name_en,
            "quantity": q6(required_qty), "unit_cost": unit, "total_cost": total, "source_reference": "STOCK_AVERAGE" if basis == "ACTUAL" else "ITEM_STANDARD"})
        return totals
    scale = required_qty / Decimal(bom.output_quantity)
    for line in bom.lines:
        component_qty = Decimal(line.quantity) * (Decimal("1") + Decimal(line.scrap_percent)/Decimal("100")) * scale
        child = _rollup(db, company_id, line.component_item, component_qty, basis, path+[item.id], level+1, out)
        for k, v in child.items(): totals[k] += v
    routing = db.scalar(select(ManufacturingRouting).where(ManufacturingRouting.company_id == company_id,
        ManufacturingRouting.bom_id == bom.id, ManufacturingRouting.status == "APPROVED").options(
        selectinload(ManufacturingRouting.operations).selectinload(ManufacturingRoutingOperation.work_center)
    ).order_by(ManufacturingRouting.version.desc()))
    if routing:
        for op in routing.operations:
            hours = (Decimal(op.setup_minutes) + Decimal(op.run_minutes_per_unit) * required_qty) / Decimal("60")
            labor_rate = Decimal(op.standard_labor_rate or op.work_center.hourly_labor_rate or 0)
            labor = money(hours * labor_rate)
            direct_expense = money(hours * Decimal(op.work_center.direct_expense_rate or 0) + Decimal(op.outside_processing_cost or 0) * required_qty)
            variable_oh = money(hours * Decimal(op.work_center.variable_overhead_rate or op.standard_overhead_rate or op.work_center.hourly_overhead_rate or 0))
            fixed_oh = money(hours * Decimal(op.work_center.fixed_overhead_rate or 0))
            for kind, val, ar, en in [
                ("DIRECT_LABOR", labor, "أجور مباشرة", "Direct labor"), ("DIRECT_EXPENSE", direct_expense, "مصروفات مباشرة", "Direct expenses"),
                ("VARIABLE_OVERHEAD", variable_oh, "تكاليف صناعية غير مباشرة متغيرة", "Variable manufacturing overhead"),
                ("FIXED_OVERHEAD", fixed_oh, "تكاليف صناعية غير مباشرة ثابتة", "Fixed manufacturing overhead")]:
                if val:
                    totals[kind] += val; out.append({"level": level+1, "path": f"{'/'.join(map(str,path+[item.id]))}/OP-{op.id}", "parent_item_id": item.id,
                        "item_id": None, "line_type": kind, "description_ar": f"{ar} - {op.name_ar}", "description_en": f"{en} - {op.name_en}",
                        "quantity": q6(hours), "unit_cost": q6(val / hours) if hours else 0, "total_cost": val, "source_reference": f"ROUTING:{routing.code}:OP:{op.operation_code}"})
    elif bom.work_center and Decimal(bom.standard_hours):
        hours = Decimal(bom.standard_hours) * scale
        rates = [("DIRECT_LABOR", bom.work_center.hourly_labor_rate), ("DIRECT_EXPENSE", bom.work_center.direct_expense_rate),
                 ("VARIABLE_OVERHEAD", bom.work_center.variable_overhead_rate or bom.work_center.hourly_overhead_rate), ("FIXED_OVERHEAD", bom.work_center.fixed_overhead_rate)]
        for kind, rate in rates:
            val = money(hours * Decimal(rate or 0)); totals[kind] += val
            if val: out.append({"level": level+1, "path": f"{'/'.join(map(str,path+[item.id]))}/{kind}", "parent_item_id": item.id, "item_id": None,
                "line_type": kind, "description_ar": kind, "description_en": kind.replace("_", " ").title(), "quantity": q6(hours), "unit_cost": q6(rate), "total_cost": val,
                "source_reference": f"BOM:{bom.code}"})
    return totals


@router.post("/cost-rollups", status_code=201)
def create_cost_rollup(data: CostRollupIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "manufacturing.cost.prepare")
    item = get_item(db, data.company_id, data.item_id); bom = _active_bom(db, data.company_id, item.id)
    if not bom: raise HTTPException(422, "Active BOM not found for finished product")
    basis = data.cost_basis.upper()
    if basis not in {"STANDARD", "ACTUAL"}: raise HTTPException(422, "Cost basis must be STANDARD or ACTUAL")
    lines: list[dict] = []; totals = _rollup(db, data.company_id, item, Decimal(data.quantity), basis, [], 0, lines)
    direct_material = money(totals["DIRECT_MATERIAL"]); packaging = money(totals["PACKAGING"])
    labor = money(totals["DIRECT_LABOR"]); direct_exp = money(totals["DIRECT_EXPENSE"])
    variable = money(totals["VARIABLE_OVERHEAD"]); fixed = money(totals["FIXED_OVERHEAD"])
    total = money(sum((direct_material, packaging, labor, direct_exp, variable, fixed), Decimal("0")))
    digest = hashlib.sha256(json.dumps(lines, sort_keys=True, default=str).encode()).hexdigest()
    row = CostRollupSnapshot(company_id=data.company_id, number=_number(db, CostRollupSnapshot, data.company_id, "CR", data.as_of_date.year),
        item_id=item.id, bom_id=bom.id, as_of_date=data.as_of_date, quantity=quantity(data.quantity), cost_basis=basis,
        direct_material_cost=direct_material, packaging_cost=packaging, direct_labor_cost=labor, direct_expense_cost=direct_exp,
        variable_overhead_cost=variable, fixed_overhead_cost=fixed, total_cost=total, unit_cost=q6(total/Decimal(data.quantity)),
        current_standard_cost=q6(item.standard_cost), standard_cost_variance=money(total/Decimal(data.quantity)-Decimal(item.standard_cost)),
        analysis_hash=digest, prepared_by=user.id)
    for x in lines: row.lines.append(CostRollupLine(**x))
    db.add(row); db.flush(); db.commit(); return _serialize_rollup(row)


def _serialize_rollup(row: CostRollupSnapshot) -> dict:
    return {"id": row.id, "number": row.number, "item_id": row.item_id, "quantity": row.quantity, "cost_basis": row.cost_basis, "status": row.status,
        "direct_material_cost": row.direct_material_cost, "packaging_cost": row.packaging_cost, "direct_labor_cost": row.direct_labor_cost,
        "direct_expense_cost": row.direct_expense_cost, "variable_overhead_cost": row.variable_overhead_cost, "fixed_overhead_cost": row.fixed_overhead_cost,
        "overhead_total": money(Decimal(row.variable_overhead_cost)+Decimal(row.fixed_overhead_cost)), "total_cost": row.total_cost, "unit_cost": row.unit_cost,
        "current_standard_cost": row.current_standard_cost, "standard_cost_variance": row.standard_cost_variance,
        "lines": [{"level": x.level, "path": x.path, "item_id": x.item_id, "line_type": x.line_type, "description_ar": x.description_ar,
                   "description_en": x.description_en, "quantity": x.quantity, "unit_cost": x.unit_cost, "total_cost": x.total_cost} for x in row.lines]}


@router.get("/cost-rollups")
def list_cost_rollups(company_id: int, limit: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Reviewers and approvers must be able to reopen the prepared snapshot.
    # Requiring the maker-only permission here made the maker/checker buttons
    # unusable after a role switch.
    ensure_permission(db, user, company_id, "manufacturing.read")
    safe_limit = min(max(limit, 1), 100)
    rows = db.scalars(
        select(CostRollupSnapshot)
        .where(CostRollupSnapshot.company_id == company_id)
        .options(selectinload(CostRollupSnapshot.lines))
        .order_by(CostRollupSnapshot.created_at.desc(), CostRollupSnapshot.id.desc())
        .limit(safe_limit)
    ).all()
    return [_serialize_rollup(row) | {
        "item_code": row.item.code,
        "item_name_ar": row.item.name_ar,
        "item_name_en": row.item.name_en,
        "as_of_date": row.as_of_date,
        "created_at": row.created_at,
    } for row in rows]


@router.post("/cost-rollups/{row_id}/review")
def review_rollup(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CostRollupSnapshot, row_id)
    if not row: raise HTTPException(404, "Cost roll-up not found")
    ensure_permission(db, user, row.company_id, "manufacturing.cost.review"); _maker_checker(row.prepared_by, user.id)
    if row.status != "READY_FOR_REVIEW": raise HTTPException(409, "Cost roll-up is not ready for review")
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/cost-rollups/{row_id}/approve")
def approve_rollup(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(CostRollupSnapshot, row_id)
    if not row: raise HTTPException(404, "Cost roll-up not found")
    ensure_permission(db, user, row.company_id, "manufacturing.cost.approve"); _maker_checker(row.prepared_by, user.id)
    if row.reviewed_by == user.id: raise HTTPException(409, "Reviewer cannot approve the same cost roll-up")
    if row.status != "REVIEWED": raise HTTPException(409, "Only reviewed cost roll-up can be approved")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now(); row.item.standard_cost = row.unit_cost
    db.commit(); return _serialize_rollup(row)


@router.get("/cost-rollups/{row_id}/export.csv")
def export_rollup(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(CostRollupSnapshot).where(CostRollupSnapshot.id == row_id).options(selectinload(CostRollupSnapshot.lines)))
    if not row: raise HTTPException(404, "Cost roll-up not found")
    ensure_permission(db, user, row.company_id, "manufacturing.read")
    return _csv_response(f"cost_rollup_{row.number}.csv", ["Level", "Path", "Type", "Description", "Quantity", "Unit cost", "Total cost"],
        [[x.level, x.path, x.line_type, x.description_en, x.quantity, x.unit_cost, x.total_cost] for x in row.lines])


# ------------------------- Perpetual inventory, counts, aging, NRV -------------------------

class InventoryCountIn(BaseModel):
    company_id: int
    warehouse_id: int
    count_date: date
    count_type: str = "FULL"


class CountLineUpdate(BaseModel):
    counted_quantity: Decimal = Field(ge=0)
    reason: str | None = None


@router.post("/inventory-counts", status_code=201)
def create_inventory_count(data: InventoryCountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.manage"); warehouse = get_warehouse(db, data.company_id, data.warehouse_id)
    loss = get_account(db, data.company_id, "624090"); gain = get_account(db, data.company_id, "424010")
    existing = db.scalar(select(InventoryCount).where(InventoryCount.company_id == data.company_id, InventoryCount.warehouse_id == warehouse.id,
        InventoryCount.status.in_(["FROZEN", "SUBMITTED"])))
    if existing: raise HTTPException(409, "Warehouse already has an open frozen count")
    row = InventoryCount(company_id=data.company_id, number=_number(db, InventoryCount, data.company_id, "CNT", data.count_date.year),
        warehouse_id=warehouse.id, count_date=data.count_date, count_type=data.count_type.upper(), loss_account_id=loss.id, gain_account_id=gain.id, created_by=user.id)
    aggregates = db.execute(select(StockMovement.item_id, func.coalesce(StockMovement.lot_number, ""), func.sum(StockMovement.quantity), func.sum(StockMovement.total_cost))
        .where(StockMovement.company_id == data.company_id, StockMovement.warehouse_id == warehouse.id, StockMovement.movement_date <= data.count_date)
        .group_by(StockMovement.item_id, func.coalesce(StockMovement.lot_number, ""))).all()
    for item_id, lot, qty, val in aggregates:
        if Decimal(qty or 0) == 0 and Decimal(val or 0) == 0: continue
        unit = q6(Decimal(val or 0)/Decimal(qty)) if Decimal(qty or 0) else Decimal("0")
        row.lines.append(InventoryCountLine(item_id=item_id, lot_number=lot or "", book_quantity=quantity(qty or 0), book_value=money(val or 0), unit_cost=unit))
    db.add(row); db.flush(); db.commit(); return _serialize_count(row)


def _serialize_count(row: InventoryCount) -> dict:
    return {"id": row.id, "number": row.number, "warehouse_id": row.warehouse_id,
        "warehouse_code": row.warehouse.code if row.warehouse else None,
        "count_date": row.count_date, "count_type": row.count_type, "status": row.status,
        "lines": [{"id": x.id, "item_id": x.item_id, "item_code": x.item.code if x.item else None, "lot_number": x.lot_number, "book_quantity": x.book_quantity,
                   "counted_quantity": x.counted_quantity, "variance_quantity": x.variance_quantity, "unit_cost": x.unit_cost, "variance_value": x.variance_value, "reason": x.reason} for x in row.lines]}


@router.get("/inventory-counts")
def list_inventory_counts(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    rows = db.scalars(select(InventoryCount).where(
        InventoryCount.company_id == company_id,
    ).options(selectinload(InventoryCount.lines)).order_by(InventoryCount.count_date.desc(), InventoryCount.id.desc())).all()
    return [_serialize_count(row) | {"created_by": row.created_by, "submitted_by": row.submitted_by, "approved_by": row.approved_by, "journal_id": row.journal_id} for row in rows]


@router.patch("/inventory-counts/{count_id}/lines/{line_id}")
def update_count_line(count_id: int, line_id: int, data: CountLineUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(InventoryCount, count_id); line = db.get(InventoryCountLine, line_id)
    if not row or not line or line.inventory_count_id != row.id: raise HTTPException(404, "Count line not found")
    ensure_permission(db, user, row.company_id, "inventory.manage")
    if row.status != "FROZEN": raise HTTPException(409, "Count lines can only be edited while frozen")
    line.counted_quantity = quantity(data.counted_quantity); line.variance_quantity = quantity(Decimal(line.counted_quantity)-Decimal(line.book_quantity))
    line.variance_value = money(Decimal(line.variance_quantity)*Decimal(line.unit_cost)); line.reason = data.reason
    db.commit(); return {"id": line.id, "variance_quantity": line.variance_quantity, "variance_value": line.variance_value}


@router.post("/inventory-counts/{count_id}/submit")
def submit_count(count_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(InventoryCount).where(InventoryCount.id == count_id).options(selectinload(InventoryCount.lines)))
    if not row: raise HTTPException(404, "Inventory count not found")
    ensure_permission(db, user, row.company_id, "inventory.manage")
    if row.status != "FROZEN": raise HTTPException(409, "Only frozen count can be submitted")
    if any(x.counted_quantity is None for x in row.lines): raise HTTPException(422, "All count lines must be entered")
    row.status = "SUBMITTED"; row.submitted_by = user.id; row.submitted_at = utc_now(); db.commit(); return {"id": row.id, "status": row.status}


@router.post("/inventory-counts/{count_id}/approve")
def approve_count(count_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(InventoryCount).where(InventoryCount.id == count_id).options(selectinload(InventoryCount.lines).selectinload(InventoryCountLine.item)))
    if not row: raise HTTPException(404, "Inventory count not found")
    ensure_permission(db, user, row.company_id, "inventory.manage"); _maker_checker(row.created_by, user.id)
    if row.status != "SUBMITTED": raise HTTPException(409, "Only submitted count can be approved")
    journal_lines = []
    for line in row.lines:
        var = money(line.variance_value)
        if var > 0:
            journal_lines += [{"account_id": line.item.inventory_account_id, "debit": var, "credit": 0}, {"account_id": row.gain_account_id, "debit": 0, "credit": var}]
        elif var < 0:
            journal_lines += [{"account_id": row.loss_account_id, "debit": abs(var), "credit": 0}, {"account_id": line.item.inventory_account_id, "debit": 0, "credit": abs(var)}]
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.count_date, reference=row.number,
        description=f"Inventory count adjustment {row.number}", lines=journal_lines) if journal_lines else None
    for line in row.lines:
        if Decimal(line.variance_quantity):
            db.add(StockMovement(company_id=row.company_id, warehouse_id=row.warehouse_id, item_id=line.item_id, movement_date=row.count_date,
                movement_type="COUNT_ADJUSTMENT_IN" if line.variance_quantity > 0 else "COUNT_ADJUSTMENT_OUT", quantity=line.variance_quantity,
                unit_cost=line.unit_cost, total_cost=line.variance_value, lot_number=line.lot_number or None, reference_type="INVENTORY_COUNT",
                reference_id=row.id, journal_id=journal.id if journal else None, created_by=user.id))
    row.status = "POSTED"; row.approved_by = user.id; row.approved_at = utc_now(); row.journal_id = journal.id if journal else None
    db.commit(); return _serialize_count(row)


@router.get("/inventory-aging")
def inventory_aging(company_id: int, as_of: date, slow_days: int = 90, obsolete_days: int = 180,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "inventory.read")
    rows = db.execute(select(StockMovement.item_id, StockMovement.warehouse_id, func.sum(StockMovement.quantity), func.sum(StockMovement.total_cost),
        func.max(StockMovement.movement_date), func.min(StockMovement.expiry_date)).where(StockMovement.company_id == company_id, StockMovement.movement_date <= as_of)
        .group_by(StockMovement.item_id, StockMovement.warehouse_id)).all()
    result=[]
    for item_id, warehouse_id, qty, val, last_date, expiry in rows:
        days = (as_of-last_date).days if last_date else 99999
        status = "EXPIRED" if expiry and expiry < as_of else "OBSOLETE" if days >= obsolete_days else "SLOW_MOVING" if days >= slow_days else "ACTIVE"
        result.append({"item_id": item_id, "warehouse_id": warehouse_id, "quantity": quantity(qty or 0), "carrying_value": money(val or 0),
                       "last_movement_date": last_date, "days_without_movement": days, "earliest_expiry": expiry, "classification": status})
    return {"company_id": company_id, "as_of": as_of, "rows": result,
            "summary": {k: money(sum((Decimal(x["carrying_value"]) for x in result if x["classification"]==k), Decimal("0"))) for k in ["ACTIVE","SLOW_MOVING","OBSOLETE","EXPIRED"]}}


class WriteDownIn(BaseModel):
    company_id: int
    warehouse_id: int
    item_id: int
    write_down_date: date
    reason_type: str
    quantity: Decimal = Field(gt=0)
    nrv_unit_cost: Decimal = Field(ge=0)


@router.post("/inventory-write-downs", status_code=201)
def create_write_down(data: WriteDownIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "inventory.manage"); get_warehouse(db, data.company_id, data.warehouse_id); item=get_item(db,data.company_id,data.item_id)
    qty = stock_balance(db,data.company_id,data.warehouse_id,data.item_id)
    if data.quantity > qty: raise HTTPException(422,"Write-down quantity exceeds stock")
    val=stock_value(db,data.company_id,data.warehouse_id,data.item_id); carrying=q6(val/qty) if qty else q6(item.standard_cost)
    amount=money((carrying-Decimal(data.nrv_unit_cost))*Decimal(data.quantity))
    if amount <= 0: raise HTTPException(422,"NRV must be below carrying cost")
    row=InventoryWriteDown(company_id=data.company_id,number=_number(db,InventoryWriteDown,data.company_id,"WD",data.write_down_date.year),warehouse_id=data.warehouse_id,
        item_id=data.item_id,write_down_date=data.write_down_date,reason_type=data.reason_type.upper(),quantity=quantity(data.quantity),carrying_unit_cost=carrying,
        nrv_unit_cost=q6(data.nrv_unit_cost),write_down_amount=amount,expense_account_id=get_account(db,data.company_id,"624100").id,
        provision_account_id=get_account(db,data.company_id,"113020").id,created_by=user.id)
    db.add(row);db.flush();db.commit();return {"id":row.id,"number":row.number,"amount":row.write_down_amount,"status":row.status}


@router.post("/inventory-write-downs/{row_id}/approve")
def approve_write_down(row_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=db.get(InventoryWriteDown,row_id)
    if not row:raise HTTPException(404,"Write-down not found")
    ensure_permission(db,user,row.company_id,"inventory.manage");_maker_checker(row.created_by,user.id)
    if row.status!="PENDING_APPROVAL":raise HTTPException(409,"Write-down is not pending approval")
    j=create_posted_journal(db,company_id=row.company_id,user_id=user.id,posting_date=row.write_down_date,reference=row.number,description=f"Inventory write-down {row.reason_type}",
        lines=[{"account_id":row.expense_account_id,"debit":row.write_down_amount,"credit":0},{"account_id":row.provision_account_id,"debit":0,"credit":row.write_down_amount}])
    row.status="POSTED";row.approved_by=user.id;row.approved_at=utc_now();row.journal_id=j.id;db.commit();return {"id":row.id,"status":row.status,"journal_id":j.id}


@router.get("/perpetual-reconciliation")
def perpetual_reconciliation(company_id:int,as_of:date,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,company_id,"inventory.read")
    items=db.scalars(select(Item).where(Item.company_id==company_id)).all();account_ids={x.inventory_account_id for x in items}
    results=[]
    for account_id in sorted(account_ids):
        account=db.get(Account,account_id)
        item_ids=[x.id for x in items if x.inventory_account_id==account_id]
        sub=money(db.scalar(select(func.coalesce(func.sum(StockMovement.total_cost),0)).where(StockMovement.company_id==company_id,StockMovement.item_id.in_(item_ids),StockMovement.movement_date<=as_of)) or 0)
        gl=money(db.scalar(select(func.coalesce(func.sum(JournalLine.debit-JournalLine.credit),0)).join(JournalEntry,JournalEntry.id==JournalLine.journal_id).where(
            JournalEntry.company_id==company_id,JournalEntry.status.in_(["POSTED","REVERSED"]),JournalEntry.entry_date<=as_of,JournalLine.account_id==account_id)) or 0)
        results.append({"account_code":account.code,"stock_subledger":sub,"general_ledger":gl,"difference":money(sub-gl),"reconciled":money(sub-gl)==0})
    return {"company_id":company_id,"as_of":as_of,"rows":results,"all_reconciled":all(x["reconciled"] for x in results)}


class UomIn(BaseModel):
    company_id:int
    item_id:int
    from_uom:str
    to_uom:str
    factor:Decimal=Field(gt=0)


@router.post("/uom-conversions",status_code=201)
def create_uom(data:UomIn,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    ensure_permission(db,user,data.company_id,"inventory.manage");get_item(db,data.company_id,data.item_id)
    row=ItemUomConversion(company_id=data.company_id,item_id=data.item_id,from_uom=data.from_uom.upper(),to_uom=data.to_uom.upper(),factor=q6(data.factor),created_by=user.id)
    db.add(row);db.flush();db.commit();return {"id":row.id,"factor":row.factor}


# ------------------------- Budget vs actual vs historical -------------------------

def _natural_actual(account: Account, debit: Decimal, credit: Decimal) -> Decimal:
    value = Decimal(debit or 0)-Decimal(credit or 0)
    if account.account_type in {"REVENUE","LIABILITY","EQUITY"}: value=-value
    return money(value)


def _comment(ar: bool, actual: Decimal, budget: Decimal, historical: Decimal, favorable: bool) -> str:
    var=money(actual-budget);pct=money(var/budget*100) if budget else Decimal("0")
    hist_var=money(actual-historical);direction="أعلى" if var>0 else "أقل" if var<0 else "مطابق"
    if ar:
        quality="إيجابي" if favorable else "سلبي"
        return f"الفعلي {direction} من الموازنة بمبلغ {abs(var):,.2f} ({abs(pct):,.2f}%)، والانحراف {quality}. الفرق عن المتوسط التاريخي {hist_var:,.2f}."
    quality="favorable" if favorable else "unfavorable"
    return f"Actual is {'above' if var>0 else 'below' if var<0 else 'equal to'} budget by {abs(var):,.2f} ({abs(pct):,.2f}%), a {quality} variance. Difference from historical average: {hist_var:,.2f}."


@router.get("/budget-analytics")
def budget_analytics(budget_id:int,start_date:date,end_date:date,granularity:str="MONTHLY",historical_years:int=2,language:str="ar",
                     user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    budget=db.scalar(select(Budget).where(Budget.id==budget_id).options(selectinload(Budget.lines).selectinload(BudgetLine.account)))
    if not budget:raise HTTPException(404,"Budget not found")
    ensure_permission(db,user,budget.company_id,"budget.read")
    if end_date<start_date:raise HTTPException(422,"Invalid date range")
    granularity=granularity.upper()
    if granularity not in {"DAILY","MONTHLY","ANNUAL"}:raise HTTPException(422,"Invalid granularity")
    buckets=[];cursor=start_date
    while cursor<=end_date:
        if granularity=="DAILY": bstart=bend=cursor;cursor+=timedelta(days=1)
        elif granularity=="MONTHLY": bstart=cursor.replace(day=1);bend=min(date(cursor.year,cursor.month,monthrange(cursor.year,cursor.month)[1]),end_date);cursor=bend+timedelta(days=1)
        else:bstart=date(cursor.year,1,1);bend=min(date(cursor.year,12,31),end_date);cursor=bend+timedelta(days=1)
        buckets.append((bstart,bend))
    rows=[]
    for bstart,bend in buckets:
        for account in {line.account for line in budget.lines}:
            relevant=[line for line in budget.lines if line.account_id==account.id and line.period_number in {bstart.month}]
            monthly_budget=sum((Decimal(x.amount) for x in relevant),Decimal("0"))
            if granularity=="DAILY": budget_amt=money(monthly_budget/Decimal(monthrange(bstart.year,bstart.month)[1]))
            elif granularity=="ANNUAL": budget_amt=money(sum((Decimal(x.amount) for x in budget.lines if x.account_id==account.id),Decimal("0")))
            else:budget_amt=money(monthly_budget)
            debit,credit=db.execute(select(func.coalesce(func.sum(JournalLine.debit),0),func.coalesce(func.sum(JournalLine.credit),0)).join(JournalEntry,JournalEntry.id==JournalLine.journal_id).where(
                JournalEntry.company_id==budget.company_id,JournalEntry.status.in_(["POSTED","REVERSED"]),JournalEntry.entry_date.between(bstart,bend),JournalLine.account_id==account.id)).one()
            actual=_natural_actual(account,Decimal(debit),Decimal(credit))
            hist_values=[]
            for y in range(1,historical_years+1):
                hs=date(bstart.year-y,bstart.month,bstart.day)
                try:he=date(bend.year-y,bend.month,bend.day)
                except ValueError:he=date(bend.year-y,bend.month,monthrange(bend.year-y,bend.month)[1])
                hd,hc=db.execute(select(func.coalesce(func.sum(JournalLine.debit),0),func.coalesce(func.sum(JournalLine.credit),0)).join(JournalEntry,JournalEntry.id==JournalLine.journal_id).where(
                    JournalEntry.company_id==budget.company_id,JournalEntry.status.in_(["POSTED","REVERSED"]),JournalEntry.entry_date.between(hs,he),JournalLine.account_id==account.id)).one()
                hist_values.append(_natural_actual(account,Decimal(hd),Decimal(hc)))
            historical=money(sum(hist_values,Decimal("0"))/Decimal(len(hist_values))) if hist_values else Decimal("0")
            variance=money(actual-budget_amt);favorable=variance>=0 if account.account_type=="REVENUE" else variance<=0
            rows.append({"period_start":bstart,"period_end":bend,"account_code":account.code,"account_name_ar":account.name_ar,"account_name_en":account.name_en,
                "budget":budget_amt,"actual":actual,"variance":variance,"variance_percent":money(variance/budget_amt*100) if budget_amt else 0,
                "historical_average":historical,"vs_historical":money(actual-historical),"favorable":favorable,
                "comment":_comment(language.lower().startswith("ar"),actual,budget_amt,historical,favorable)})
    totals={k:money(sum((Decimal(x[k]) for x in rows),Decimal("0"))) for k in ["budget","actual","variance","historical_average","vs_historical"]}
    return {"budget_id":budget.id,"granularity":granularity,"start_date":start_date,"end_date":end_date,"historical_years":historical_years,"totals":totals,"rows":rows}


@router.get("/budget-analytics/export.csv")
def export_budget_analytics(budget_id:int,start_date:date,end_date:date,granularity:str="MONTHLY",historical_years:int=2,
                            user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    data=budget_analytics(budget_id,start_date,end_date,granularity,historical_years,"ar",user,db)
    return _csv_response("budget_actual_historical.csv",["From","To","Account","Budget","Actual","Variance","Variance %","Historical average","Vs historical","Comment"],
        [[x["period_start"],x["period_end"],x["account_code"],x["budget"],x["actual"],x["variance"],x["variance_percent"],x["historical_average"],x["vs_historical"],x["comment"]] for x in data["rows"]])
