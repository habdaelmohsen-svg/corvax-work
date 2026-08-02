from __future__ import annotations

import base64
import hashlib
import json
import uuid as uuid_lib
from datetime import date, datetime, time
from decimal import Decimal
import xml.etree.ElementTree as ET  # nosec B405 -- generation only; no untrusted XML parsing

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Company, EInvoice, LegalRuleVersion, PosOrder, PosOrderLine, PurchaseInvoice, SalesInvoice,
    SalesInvoiceLine, TaxCode, User, VatReturnLine, VatReturnSnapshot,
)
from app.services.audit import write_audit
from app.services.operations import money
from app.services.tax import build_vat_return, ensure_default_tax_codes, serialize_tax_code, serialize_vat_return
from app.core.time import utc_now

router = APIRouter(prefix="/compliance", tags=["Saudi compliance and tax"])


class EInvoiceGenerateIn(BaseModel):
    company_id: int
    source_type: str
    source_id: int


class VatReturnIn(BaseModel):
    company_id: int
    period_start: date
    period_end: date


class VatTaxpayerProfileIn(BaseModel):
    legal_name_ar: str | None = Field(default=None, max_length=250)
    legal_name_en: str | None = Field(default=None, max_length=250)
    vat_number: str | None = Field(default=None, max_length=30)
    commercial_registration: str | None = Field(default=None, max_length=30)
    zatca_distinguished_number: str | None = Field(default=None, max_length=50)
    tax_account_number: str | None = Field(default=None, max_length=50)
    taxpayer_identity_number: str | None = Field(default=None, max_length=50)
    registered_address: str | None = Field(default=None, max_length=1000)


class VatLineAdjustmentIn(BaseModel):
    box_code: str = Field(min_length=1, max_length=50)
    adjustment_base: Decimal


class VatAdjustmentsIn(BaseModel):
    lines: list[VatLineAdjustmentIn] = Field(default_factory=list)
    prior_period_correction: Decimal = Decimal("0")
    carried_forward_vat: Decimal = Field(default=Decimal("0"), ge=0)
    adjustment_reason: str | None = Field(default=None, max_length=1000)


class TaxCodeIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=30)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    direction: str = Field(pattern="^(SALES|PURCHASE|BOTH)$")
    category: str = Field(pattern="^(STANDARD|ZERO_RATED|EXPORT|EXEMPT|OUT_OF_SCOPE|IMPORTS_CUSTOMS|REVERSE_CHARGE|NON_DEDUCTIBLE)$")
    rate: Decimal = Field(ge=0, le=100)
    return_box: str = Field(min_length=1, max_length=50)
    deductible_percent: Decimal = Field(default=100, ge=0, le=100)
    tax_category_code: str = Field(default="S", pattern="^(S|Z|E|O)$")
    exemption_reason_code: str | None = Field(default=None, max_length=20)
    exemption_reason: str | None = Field(default=None, max_length=500)
    effective_from: date
    effective_to: date | None = None


class TaxCodeStatusIn(BaseModel):
    active: bool


def _taxpayer_profile(company: Company) -> dict:
    return {
        "company_id": company.id,
        "legal_name_ar": company.legal_name_ar or company.name_ar,
        "legal_name_en": company.legal_name_en or company.name_en,
        "vat_number": company.vat_number,
        "commercial_registration": company.commercial_registration,
        "zatca_distinguished_number": company.zatca_distinguished_number,
        "tax_account_number": company.tax_account_number,
        "taxpayer_identity_number": company.taxpayer_identity_number,
        "registered_address": company.registered_address,
    }


def _recalculate_adjusted_vat(row: VatReturnSnapshot) -> None:
    output_boxes = {"SALES_STANDARD", "PURCHASE_REVERSE_CHARGE", "PURCHASE_IMPORTS_THROUGH_RETURN"}
    input_boxes = {"PURCHASE_STANDARD", "PURCHASE_IMPORTS_CUSTOMS", "PURCHASE_REVERSE_CHARGE", "PURCHASE_IMPORTS_THROUGH_RETURN"}
    reported = {
        line.box_code: money(Decimal(line.tax_amount) - Decimal(line.adjustment_tax))
        for line in row.lines
    }
    row.output_vat = money(sum((reported.get(code, Decimal("0")) for code in output_boxes), Decimal("0")))
    row.input_vat = money(sum((reported.get(code, Decimal("0")) for code in input_boxes), Decimal("0")))
    row.net_vat_payable = money(
        Decimal(row.output_vat) - Decimal(row.input_vat)
        + Decimal(row.prior_period_correction or 0)
        - Decimal(row.carried_forward_vat or 0)
    )


@router.get("/vat-taxpayer-profile")
def read_vat_taxpayer_profile(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return _taxpayer_profile(company)


@router.put("/vat-taxpayer-profile")
def update_vat_taxpayer_profile(company_id: int, data: VatTaxpayerProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.manage")
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    before = _taxpayer_profile(company)
    for field_name, value in data.model_dump().items():
        setattr(company, field_name, value.strip() if isinstance(value, str) and value.strip() else None)
    after = _taxpayer_profile(company)
    write_audit(
        db, action="VAT_TAXPAYER_PROFILE_UPDATED", entity_type="COMPANY",
        entity_id=company.id, user_id=user.id, company_id=company_id,
        before={key: bool(value) for key, value in before.items() if key != "company_id"},
        after={key: bool(value) for key, value in after.items() if key != "company_id"},
    )
    db.commit()
    return after



def _tlv(tag: int, value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 255:
        raise HTTPException(422, f"QR field tag {tag} exceeds 255 bytes")
    return bytes([tag, len(encoded)]) + encoded


def _qr(company: Company, timestamp: datetime, total: Decimal, vat: Decimal) -> str:
    payload = b"".join([
        _tlv(1, company.legal_name_en or company.name_en),
        _tlv(2, company.vat_number or ""),
        _tlv(3, timestamp.isoformat()),
        _tlv(4, f"{money(total):.2f}"),
        _tlv(5, f"{money(vat):.2f}"),
    ])
    return base64.b64encode(payload).decode()


def _source(db: Session, company_id: int, source_type: str, source_id: int) -> tuple[dict, list[dict]]:
    source_type = source_type.upper()
    if source_type == "SALES_INVOICE":
        row = db.scalar(select(SalesInvoice).where(SalesInvoice.id == source_id, SalesInvoice.company_id == company_id).options(selectinload(SalesInvoice.lines), selectinload(SalesInvoice.customer)))
        if not row:
            raise HTTPException(404, "Sales invoice not found")
        lines = [{"description": line.description, "quantity": Decimal(line.quantity), "unit_price": Decimal(line.unit_price), "net": Decimal(line.subtotal), "vat": Decimal(line.vat_amount), "total": Decimal(line.total), "vat_rate": Decimal(line.vat_rate), "tax_category": line.tax_code.tax_category_code if line.tax_code else ("S" if Decimal(line.vat_rate) else "Z"), "exemption_reason_code": line.tax_code.exemption_reason_code if line.tax_code else None, "exemption_reason": line.tax_code.exemption_reason if line.tax_code else None} for line in row.lines]
        return {"number": row.number, "date": row.invoice_date, "customer_name": row.customer.name_en, "customer_vat": row.customer.vat_number or "", "subtotal": Decimal(row.subtotal), "vat": Decimal(row.vat_amount), "total": Decimal(row.total), "type_code": "388"}, lines
    if source_type == "POS_ORDER":
        row = db.scalar(select(PosOrder).where(PosOrder.id == source_id, PosOrder.company_id == company_id).options(selectinload(PosOrder.lines).selectinload(PosOrderLine.menu_item)))
        if not row:
            raise HTTPException(404, "POS order not found")
        lines = [{"description": line.menu_item.name_en, "quantity": Decimal(line.quantity), "unit_price": Decimal(line.unit_price), "net": Decimal(line.net_amount), "vat": Decimal(line.vat_amount), "total": Decimal(line.total_amount), "vat_rate": Decimal(line.menu_item.vat_rate), "tax_category": line.tax_code.tax_category_code if line.tax_code else (line.menu_item.tax_code.tax_category_code if line.menu_item.tax_code else ("S" if Decimal(line.menu_item.vat_rate) else "Z")), "exemption_reason_code": (line.tax_code.exemption_reason_code if line.tax_code else (line.menu_item.tax_code.exemption_reason_code if line.menu_item.tax_code else None)), "exemption_reason": (line.tax_code.exemption_reason if line.tax_code else (line.menu_item.tax_code.exemption_reason if line.menu_item.tax_code else None))} for line in row.lines]
        return {"number": row.number, "date": row.order_date, "customer_name": "Cash Customer", "customer_vat": "", "subtotal": Decimal(row.subtotal), "vat": Decimal(row.vat_amount), "total": Decimal(row.total), "type_code": "388"}, lines
    raise HTTPException(422, "source_type must be SALES_INVOICE or POS_ORDER")


def _xml(company: Company, invoice: dict, lines: list[dict], invoice_uuid: str, counter: int, previous_hash: str, timestamp: datetime) -> str:
    ns = {
        "": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)
    root = ET.Element(f"{{{ns['']}}}Invoice")
    def cbc(element_name: str, value: str, parent=root, **attrs):
        node = ET.SubElement(parent, f"{{{ns['cbc']}}}{element_name}", attrs); node.text = value; return node
    cbc("ProfileID", "reporting:1.0")
    cbc("ID", invoice["number"]); cbc("UUID", invoice_uuid); cbc("IssueDate", invoice["date"].isoformat()); cbc("IssueTime", timestamp.time().replace(microsecond=0).isoformat())
    cbc("InvoiceTypeCode", invoice["type_code"], name="0100000")
    cbc("DocumentCurrencyCode", company.currency); cbc("TaxCurrencyCode", "SAR")
    additional = ET.SubElement(root, f"{{{ns['cac']}}}AdditionalDocumentReference")
    cbc("ID", "ICV", additional); cbc("UUID", str(counter), additional)
    previous = ET.SubElement(root, f"{{{ns['cac']}}}AdditionalDocumentReference")
    cbc("ID", "PIH", previous); attachment = ET.SubElement(previous, f"{{{ns['cac']}}}Attachment"); cbc("EmbeddedDocumentBinaryObject", previous_hash, attachment, mimeCode="text/plain")
    supplier = ET.SubElement(root, f"{{{ns['cac']}}}AccountingSupplierParty")
    party = ET.SubElement(supplier, f"{{{ns['cac']}}}Party"); tax = ET.SubElement(party, f"{{{ns['cac']}}}PartyTaxScheme"); cbc("CompanyID", company.vat_number or "", tax)
    tax_scheme = ET.SubElement(tax, f"{{{ns['cac']}}}TaxScheme"); cbc("ID", "VAT", tax_scheme)
    legal = ET.SubElement(party, f"{{{ns['cac']}}}PartyLegalEntity"); cbc("RegistrationName", company.legal_name_en or company.name_en, legal)
    customer = ET.SubElement(root, f"{{{ns['cac']}}}AccountingCustomerParty")
    customer_party = ET.SubElement(customer, f"{{{ns['cac']}}}Party"); customer_legal = ET.SubElement(customer_party, f"{{{ns['cac']}}}PartyLegalEntity"); cbc("RegistrationName", invoice["customer_name"], customer_legal)
    tax_total = ET.SubElement(root, f"{{{ns['cac']}}}TaxTotal"); cbc("TaxAmount", f"{money(invoice['vat']):.2f}", tax_total, currencyID="SAR")
    monetary = ET.SubElement(root, f"{{{ns['cac']}}}LegalMonetaryTotal")
    cbc("LineExtensionAmount", f"{money(invoice['subtotal']):.2f}", monetary, currencyID=company.currency)
    cbc("TaxExclusiveAmount", f"{money(invoice['subtotal']):.2f}", monetary, currencyID=company.currency)
    cbc("TaxInclusiveAmount", f"{money(invoice['total']):.2f}", monetary, currencyID=company.currency)
    cbc("PayableAmount", f"{money(invoice['total']):.2f}", monetary, currencyID=company.currency)
    for index, line in enumerate(lines, 1):
        invoice_line = ET.SubElement(root, f"{{{ns['cac']}}}InvoiceLine")
        cbc("ID", str(index), invoice_line); cbc("InvoicedQuantity", f"{line['quantity']:.4f}", invoice_line, unitCode="PCE")
        cbc("LineExtensionAmount", f"{money(line['net']):.2f}", invoice_line, currencyID=company.currency)
        item = ET.SubElement(invoice_line, f"{{{ns['cac']}}}Item"); cbc("Name", line["description"], item)
        classified = ET.SubElement(item, f"{{{ns['cac']}}}ClassifiedTaxCategory"); cbc("ID", line.get("tax_category", "S"), classified); cbc("Percent", f"{line['vat_rate']:.2f}", classified)
        if line.get("exemption_reason_code"):
            cbc("TaxExemptionReasonCode", line["exemption_reason_code"], classified)
        if line.get("exemption_reason"):
            cbc("TaxExemptionReason", line["exemption_reason"], classified)
        price = ET.SubElement(invoice_line, f"{{{ns['cac']}}}Price"); cbc("PriceAmount", f"{line['unit_price']:.4f}", price, currencyID=company.currency)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _validate_local(company: Company, invoice: dict, lines: list[dict]) -> list[str]:
    errors: list[str] = []
    if not company.vat_number or len(company.vat_number) != 15 or not company.vat_number.isdigit():
        errors.append("Company VAT number must be 15 digits")
    if not lines:
        errors.append("Invoice must contain at least one line")
    if money(sum((line["net"] for line in lines), Decimal("0"))) != money(invoice["subtotal"]):
        errors.append("Line net amounts do not reconcile to invoice subtotal")
    if money(sum((line["vat"] for line in lines), Decimal("0"))) != money(invoice["vat"]):
        errors.append("Line VAT does not reconcile to invoice VAT")
    if money(invoice["subtotal"] + invoice["vat"]) != money(invoice["total"]):
        errors.append("Invoice total does not reconcile")
    return errors


@router.post("/e-invoices/generate", status_code=201)
def generate_einvoice(data: EInvoiceGenerateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    company = db.get(Company, data.company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    source_type = data.source_type.upper()
    if db.scalar(select(EInvoice).where(EInvoice.company_id == data.company_id, EInvoice.source_type == source_type, EInvoice.source_id == data.source_id)):
        raise HTTPException(409, "Electronic invoice already generated for this source")
    invoice, lines = _source(db, data.company_id, source_type, data.source_id)
    errors = _validate_local(company, invoice, lines)
    counter = int(db.scalar(select(func.coalesce(func.max(EInvoice.invoice_counter), 0)).where(EInvoice.company_id == data.company_id)) or 0) + 1
    previous = db.scalar(select(EInvoice).where(EInvoice.company_id == data.company_id).order_by(EInvoice.invoice_counter.desc()))
    previous_hash = previous.invoice_hash if previous else base64.b64encode(bytes(32)).decode()
    invoice_uuid = str(uuid_lib.uuid4()); timestamp = datetime.combine(invoice["date"], time(12, 0))
    xml = _xml(company, invoice, lines, invoice_uuid, counter, previous_hash, timestamp)
    invoice_hash = base64.b64encode(hashlib.sha256(xml.encode()).digest()).decode()
    qr = _qr(company, timestamp, invoice["total"], invoice["vat"])
    row = EInvoice(company_id=data.company_id, source_type=source_type, source_id=data.source_id, uuid=invoice_uuid, invoice_counter=counter, issue_datetime=timestamp, invoice_type_code=invoice["type_code"], xml_content=xml, invoice_hash=invoice_hash, previous_invoice_hash=previous_hash, qr_tlv_base64=qr, status="LOCAL_VALIDATED" if not errors else "LOCAL_VALIDATION_FAILED", validation_errors=json.dumps(errors), created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="EINVOICE_GENERATED", entity_type="EINVOICE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"source_type": source_type, "source_id": data.source_id, "counter": counter, "status": row.status})
    db.commit()
    return {"id": row.id, "uuid": row.uuid, "invoice_counter": row.invoice_counter, "invoice_hash": row.invoice_hash, "previous_invoice_hash": row.previous_invoice_hash, "qr_tlv_base64": row.qr_tlv_base64, "status": row.status, "validation_errors": errors, "integration_status": "NOT_CONNECTED_TO_ZATCA", "xml": row.xml_content}


@router.get("/e-invoices")
def list_einvoices(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(EInvoice).where(EInvoice.company_id == company_id).order_by(EInvoice.invoice_counter.desc())).all()
    return [{"id": r.id, "source_type": r.source_type, "source_id": r.source_id, "uuid": r.uuid, "invoice_counter": r.invoice_counter, "issue_datetime": r.issue_datetime, "invoice_hash": r.invoice_hash, "status": r.status, "validation_errors": json.loads(r.validation_errors or "[]")} for r in rows]


@router.get("/tax-codes")
def list_tax_codes(company_id: int, active_only: bool = True, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    ensure_default_tax_codes(db, company_id, user.id)
    query = select(TaxCode).where(TaxCode.company_id == company_id).order_by(TaxCode.direction, TaxCode.code)
    if active_only:
        query = query.where(TaxCode.active.is_(True))
    rows = db.scalars(query).all()
    db.commit()
    return [serialize_tax_code(row) for row in rows]


@router.post("/tax-codes", status_code=201)
def create_tax_code(data: TaxCodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    if data.effective_to and data.effective_to < data.effective_from:
        raise HTTPException(422, "Tax code effective-to date cannot precede effective-from date")
    code = data.code.strip().upper()
    if db.scalar(select(TaxCode).where(TaxCode.company_id == data.company_id, TaxCode.code == code)):
        raise HTTPException(409, "Tax code already exists")
    if data.category in {"ZERO_RATED", "EXPORT", "EXEMPT", "OUT_OF_SCOPE"} and data.rate != 0:
        raise HTTPException(422, "Zero-rated, export, exempt and out-of-scope tax codes must use a zero rate")
    row = TaxCode(**data.model_dump(exclude={"code"}), code=code, system_code=False, active=True, created_by=user.id)
    db.add(row); db.flush()
    write_audit(db, action="TAX_CODE_CREATED", entity_type="TAX_CODE", entity_id=row.id, user_id=user.id, company_id=data.company_id, after=serialize_tax_code(row))
    db.commit()
    return serialize_tax_code(row)


@router.patch("/tax-codes/{tax_code_id}/status")
def update_tax_code_status(tax_code_id: int, data: TaxCodeStatusIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(TaxCode, tax_code_id)
    if not row:
        raise HTTPException(404, "Tax code not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    before = {"active": row.active}; row.active = data.active
    write_audit(db, action="TAX_CODE_STATUS_CHANGED", entity_type="TAX_CODE", entity_id=row.id, user_id=user.id, company_id=row.company_id, before=before, after={"active": row.active})
    db.commit()
    return serialize_tax_code(row)


@router.post("/vat-return", status_code=201)
def create_vat_return(data: VatReturnIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "compliance.manage")
    row = build_vat_return(db, company_id=data.company_id, period_start=data.period_start, period_end=data.period_end, user_id=user.id)
    write_audit(db, action="VAT_RETURN_SNAPSHOT_CREATED", entity_type="VAT_RETURN", entity_id=row.id, user_id=user.id, company_id=data.company_id, after={"period_start": str(data.period_start), "period_end": str(data.period_end), "net_vat": str(row.net_vat_payable), "classification_complete": row.classification_complete})
    db.commit(); db.refresh(row)
    row = db.scalar(select(VatReturnSnapshot).where(VatReturnSnapshot.id == row.id).options(selectinload(VatReturnSnapshot.lines)))
    return serialize_vat_return(row)


@router.get("/vat-returns")
def list_vat_returns(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    rows = db.scalars(select(VatReturnSnapshot).where(VatReturnSnapshot.company_id == company_id).options(selectinload(VatReturnSnapshot.lines)).order_by(VatReturnSnapshot.period_end.desc())).all()
    return [serialize_vat_return(row) for row in rows]


@router.get("/vat-returns/{vat_return_id}")
def read_vat_return(vat_return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(VatReturnSnapshot).where(VatReturnSnapshot.id == vat_return_id).options(selectinload(VatReturnSnapshot.lines)))
    if not row:
        raise HTTPException(404, "VAT return not found")
    ensure_permission(db, user, row.company_id, "compliance.read")
    return serialize_vat_return(row)


@router.put("/vat-returns/{vat_return_id}/adjustments")
def update_vat_adjustments(vat_return_id: int, data: VatAdjustmentsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(
        select(VatReturnSnapshot)
        .where(VatReturnSnapshot.id == vat_return_id)
        .options(selectinload(VatReturnSnapshot.lines))
    )
    if not row:
        raise HTTPException(404, "VAT return not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT":
        raise HTTPException(409, "Only a draft VAT return can be adjusted")
    by_code = {line.box_code: line for line in row.lines}
    seen: set[str] = set()
    for adjustment in data.lines:
        code = adjustment.box_code.upper()
        if code in seen:
            raise HTTPException(422, f"Duplicate VAT box adjustment: {code}")
        seen.add(code)
        line = by_code.get(code)
        if not line:
            raise HTTPException(422, f"Unknown VAT box: {code}")
        line.adjustment_base = money(adjustment.adjustment_base)
        line.adjustment_tax = money(
            Decimal(line.adjustment_base) * Decimal("0.15")
            if code in {
                "SALES_STANDARD", "PURCHASE_STANDARD", "PURCHASE_IMPORTS_CUSTOMS",
                "PURCHASE_REVERSE_CHARGE", "PURCHASE_IMPORTS_THROUGH_RETURN",
            }
            else Decimal("0")
        )
    for code, line in by_code.items():
        if code not in seen:
            line.adjustment_base = Decimal("0.00")
            line.adjustment_tax = Decimal("0.00")
    has_changes = any(Decimal(line.adjustment_base) != 0 for line in row.lines)
    has_changes = has_changes or data.prior_period_correction != 0 or data.carried_forward_vat != 0
    if has_changes and not (data.adjustment_reason or "").strip():
        raise HTTPException(422, "Adjustment reason is required when VAT adjustments are entered")
    row.prior_period_correction = money(data.prior_period_correction)
    row.carried_forward_vat = money(data.carried_forward_vat)
    row.adjustment_reason = (data.adjustment_reason or "").strip() or None
    row.adjustments_updated_by = user.id
    row.adjustments_updated_at = utc_now()
    _recalculate_adjusted_vat(row)
    write_audit(
        db, action="VAT_RETURN_ADJUSTMENTS_UPDATED", entity_type="VAT_RETURN",
        entity_id=row.id, user_id=user.id, company_id=row.company_id,
        after={
            "adjusted_boxes": sorted(seen),
            "prior_period_correction": str(row.prior_period_correction),
            "carried_forward_vat": str(row.carried_forward_vat),
            "net_vat": str(row.net_vat_payable),
        },
    )
    db.commit()
    return serialize_vat_return(row)


@router.post("/vat-returns/{vat_return_id}/submit")
def submit_vat_return(vat_return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(VatReturnSnapshot).where(VatReturnSnapshot.id == vat_return_id).options(selectinload(VatReturnSnapshot.lines)))
    if not row:
        raise HTTPException(404, "VAT return not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "DRAFT":
        raise HTTPException(409, "VAT return must be draft")
    if not row.classification_complete or money(row.output_reconciliation_difference) != 0 or money(row.input_reconciliation_difference) != 0:
        raise HTTPException(409, "VAT return cannot be submitted until classification and GL reconciliations pass")
    row.status = "PENDING_APPROVAL"; row.submitted_by = user.id; row.submitted_at = utc_now()
    write_audit(db, action="VAT_RETURN_SUBMITTED", entity_type="VAT_RETURN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit()
    return serialize_vat_return(row)


@router.post("/vat-returns/{vat_return_id}/approve")
def approve_vat_return(vat_return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(VatReturnSnapshot).where(VatReturnSnapshot.id == vat_return_id).options(selectinload(VatReturnSnapshot.lines)))
    if not row:
        raise HTTPException(404, "VAT return not found")
    ensure_permission(db, user, row.company_id, "compliance.manage")
    if row.status != "PENDING_APPROVAL":
        raise HTTPException(409, "VAT return must be pending approval")
    if row.created_by == user.id or row.submitted_by == user.id:
        raise HTTPException(409, "Maker-checker control: creator or submitter cannot approve the VAT return")
    row.status = "APPROVED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="VAT_RETURN_APPROVED", entity_type="VAT_RETURN", entity_id=row.id, user_id=user.id, company_id=row.company_id, after={"status": row.status, "net_vat": str(row.net_vat_payable)})
    db.commit()
    return serialize_vat_return(row)


@router.get("/legal-rules")
def legal_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(LegalRuleVersion).where(LegalRuleVersion.active.is_(True)).order_by(LegalRuleVersion.code, LegalRuleVersion.effective_from.desc())).all()
    return [{"code": r.code, "name_ar": r.name_ar, "name_en": r.name_en, "effective_from": r.effective_from, "effective_to": r.effective_to, "parameters": json.loads(r.parameters_json), "source_url": r.source_url} for r in rows]


@router.get("/status")
def compliance_status(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "compliance.read")
    generated = db.scalar(select(func.count(EInvoice.id)).where(EInvoice.company_id == company_id)) or 0
    failed = db.scalar(select(func.count(EInvoice.id)).where(EInvoice.company_id == company_id, EInvoice.status == "LOCAL_VALIDATION_FAILED")) or 0
    return {
        "company_id": company_id,
        "e_invoices_generated": generated,
        "local_validation_failures": failed,
        "xml_generation": "ACTIVE",
        "hash_chain": "ACTIVE",
        "qr_tlv": "ACTIVE",
        "zatca_phase_2_integration": "PENDING_CSID_AND_SANDBOX_CERTIFICATION",
        "production_claim": "NOT_CERTIFIED",
    }
