"""CORVAX RC27.4 H13 - CIP projects API.

Key endpoints (prefix /cip):
  Projects:      POST/GET /projects, GET /projects/{id}
  Contracts:     POST/GET /contracts            (signing posts NO journal)
  Certificates:  POST /certificates             (this posts the obligation)
                 POST /certificates/{id}/approve
  Costs:         POST/GET /costs                (classification with warning)
  Payments:      POST /payments                 (certificate payment / retention release)
  Statement:     GET  /contracts/{id}/statement (كشف حساب المقاول - solves the manual work)
  Capitalize:    POST /projects/{id}/capitalize (transfer CIP -> fixed asset)

Accounting:
  Certificate approval:
      Dr 155010 CIP                work_value
      Dr 114010 VAT recoverable    vat_amount
         Cr 217040 Contractors payable   (work + vat - retention)
         Cr 217050 Retention payable     retention_amount
  Payment:
      Dr 217040 Contractors payable / Cr bank
  Retention release:
      Dr 217050 Retention payable / Cr bank
  Capitalization:
      Dr 151010 Property & equipment / Cr 155010 CIP
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import Account, BankAccount, Party, User
from app.models.assets_close import AssetCategory, FixedAsset
from app.models.cip_projects import (
    CipContract, CipCost, CipPayment, CipProgressCertificate, CipProject,
)
from app.services.audit import write_audit
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/cip", tags=["construction in progress"])

CIP_CODE = "155010"
CONTRACTORS_PAYABLE = "217040"
RETENTION_PAYABLE = "217050"
VAT_INPUT = "114010"
PPE_CODE = "151010"

# Categories that IAS 16/38 do not allow to be capitalized into the asset.
NON_CAPITALIZABLE = {
    "FORMATION_COSTS": ("مصاريف تأسيس", "Formation costs", "IAS 38.69 - تُصرف فورًا ولا تُرسمل"),
    "TRAINING": ("تدريب", "Training", "IAS 16.19 - تكاليف تدريب الموظفين تُصرف"),
    "ADMIN_OVERHEAD": ("مصاريف إدارية عامة", "Admin overhead", "IAS 16.19 - المصاريف الإدارية العامة تُصرف"),
    "MARKETING": ("تسويق وافتتاح", "Marketing & opening", "IAS 16.19 - تكاليف الافتتاح والترويج تُصرف"),
    "ABNORMAL_WASTE": ("هدر غير طبيعي", "Abnormal waste", "IAS 16.22 - الهدر غير الطبيعي يُصرف"),
    "IDLE_TIME": ("توقف غير مخطط", "Idle time", "IAS 16.22 - تكاليف التوقف تُصرف"),
    "PRE_OPENING_LOSSES": ("خسائر تشغيل تجريبي", "Pre-opening losses", "IAS 16.20-21 - خسائر التشغيل الأولي تُصرف"),
}
CAPITALIZABLE = {
    "MATERIALS": ("مواد", "Materials"),
    "DIRECT_LABOR": ("عمالة مباشرة", "Direct labor"),
    "SITE_PREPARATION": ("تجهيز الموقع", "Site preparation"),
    "ENGINEERING": ("إشراف هندسي وتصميم", "Engineering & design"),
    "PERMITS": ("تصاريح بناء", "Building permits"),
    "TRANSPORT_INSTALLATION": ("نقل وتركيب", "Transport & installation"),
    "TESTING": ("اختبار قبل التشغيل", "Pre-operational testing"),
    "BORROWING_COST": ("تكاليف اقتراض", "Borrowing costs (IAS 23)"),
}


def _money(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


def _account(db: Session, company_id: int, code: str) -> Account:
    acc = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code, Account.active.is_(True)))
    if not acc or not acc.is_postable:
        raise HTTPException(422, f"Postable account not found: {code}")
    return acc


_CIP_DEFS = {
    CIP_CODE: ("مشروعات تحت التنفيذ", "Construction in Progress", "ASSET", "NON_CURRENT_ASSETS", "150000"),
    CONTRACTORS_PAYABLE: ("مستحق لمقاولين", "Contractors Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
    RETENTION_PAYABLE: ("محتجز ضمان مقاولين", "Contractor Retention Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000"),
}


def _ensure_account(db: Session, company_id: int, code: str) -> Account:
    acc = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == code))
    if acc:
        return acc
    if code not in _CIP_DEFS:
        raise HTTPException(422, f"Postable account not found: {code}")
    name_ar, name_en, atype, group, parent_code = _CIP_DEFS[code]
    parent = db.scalar(select(Account).where(Account.company_id == company_id, Account.code == parent_code))
    acc = Account(company_id=company_id, code=code, name_ar=name_ar, name_en=name_en,
                  account_type=atype, statement_group=group, parent_id=parent.id if parent else None,
                  level=3, is_postable=True, is_cash=False, active=True)
    db.add(acc); db.flush()
    return acc


def _next_number(db: Session, model, company_id: int, prefix: str, year: int) -> str:
    count = db.scalar(
        select(func.count(model.id)).where(
            model.company_id == company_id,
            func.extract("year", model.created_at) == year,
        )
    ) or 0
    return f"{prefix}-{company_id}-{year}-{count + 1:05d}"


# ==================================================================== PROJECTS
class ProjectIn(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=40)
    name_ar: str
    name_en: str
    description: str | None = None
    budget_amount: float = 0
    start_date: date | None = None
    expected_completion_date: date | None = None


@router.post("/projects", status_code=201)
def create_project(data: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "cip.manage")
    dup = db.scalar(select(CipProject).where(CipProject.company_id == data.company_id, CipProject.code == data.code))
    if dup:
        raise HTTPException(409, "Project code already exists")
    p = CipProject(**data.model_dump(), status="PLANNING", created_by=user.id)
    db.add(p); db.flush()
    write_audit(db, action="CIP_PROJECT_CREATED", entity_type="CIP_PROJECT", entity_id=p.id, user_id=user.id, company_id=data.company_id, after={"code": p.code})
    db.commit()
    return {"id": p.id, "code": p.code, "name_ar": p.name_ar, "status": p.status}


@router.get("/projects")
def list_projects(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "cip.read")
    # AUDIT C-05: limit rows to the branches this user may see.
    _scope = branch_scope_condition(db, user, company_id, CipProject)
    query = select(CipProject).where(CipProject.company_id == company_id)
    if _scope is not None:
        query = query.where(_scope)
    rows = db.scalars(query.order_by(CipProject.code)).all()
    out = []
    for p in rows:
        committed = db.scalar(select(func.coalesce(func.sum(CipContract.contract_value), 0)).where(CipContract.project_id == p.id, CipContract.status != "TERMINATED")) or 0
        out.append({"id": p.id, "code": p.code, "name_ar": p.name_ar, "name_en": p.name_en,
                    "budget_amount": p.budget_amount, "capitalized_cost": p.capitalized_cost,
                    "expensed_cost": p.expensed_cost, "committed_contracts": _money(committed),
                    "start_date": p.start_date.isoformat() if p.start_date else None,
                    "ready_for_use_date": p.ready_for_use_date.isoformat() if p.ready_for_use_date else None,
                    "status": p.status, "fixed_asset_id": p.fixed_asset_id})
    return out


# ==================================================================== CONTRACTS
class ContractIn(BaseModel):
    company_id: int
    project_id: int
    party_id: int
    title_ar: str
    title_en: str
    contract_type: str = "CONTRACTOR"
    contract_value: float = Field(gt=0)
    vat_rate: float = 15
    retention_rate: float = 0
    signed_date: date | None = None
    warranty_end_date: date | None = None
    notes: str | None = None


@router.post("/contracts", status_code=201)
def create_contract(data: ContractIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Signing a contract records a CAPITAL COMMITMENT only - no journal entry.

    This is deliberate: VAT arises with the certificate/invoice, not with the
    signature, and recognising the full contract would inflate the balance sheet
    with work that has not been performed.
    """
    ensure_permission(db, user, data.company_id, "cip.manage")
    project = db.scalar(select(CipProject).where(CipProject.id == data.project_id, CipProject.company_id == data.company_id))
    if not project:
        raise HTTPException(404, "Project not found")
    party = db.scalar(select(Party).where(Party.id == data.party_id, Party.company_id == data.company_id))
    if not party:
        raise HTTPException(404, "Party (contractor/supplier) not found")
    if not (0 <= data.retention_rate <= 50):
        raise HTTPException(422, "retention_rate must be between 0 and 50")
    c = CipContract(
        company_id=data.company_id, project_id=data.project_id,
        number=_next_number(db, CipContract, data.company_id, "CTR", (data.signed_date or date.today()).year),
        party_id=data.party_id, title_ar=data.title_ar, title_en=data.title_en,
        contract_type=data.contract_type, contract_value=data.contract_value,
        vat_rate=data.vat_rate, retention_rate=data.retention_rate,
        signed_date=data.signed_date, warranty_end_date=data.warranty_end_date,
        notes=data.notes, status="ACTIVE", created_by=user.id,
    )
    db.add(c); db.flush()
    if project.status == "PLANNING":
        project.status = "IN_PROGRESS"
    write_audit(db, action="CIP_CONTRACT_SIGNED", entity_type="CIP_CONTRACT", entity_id=c.id, user_id=user.id, company_id=data.company_id, after={"number": c.number, "value": str(c.contract_value)})
    db.commit()
    return {"id": c.id, "number": c.number, "contract_value": c.contract_value,
            "retention_rate": c.retention_rate, "status": c.status,
            "note": "Capital commitment recorded. No journal entry until a progress certificate is approved."}


@router.get("/contracts")
def list_contracts(company_id: int, project_id: int | None = Query(default=None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "cip.read")
    q = select(CipContract).where(CipContract.company_id == company_id)
    if project_id:
        q = q.where(CipContract.project_id == project_id)
    rows = db.scalars(q.order_by(CipContract.id.desc())).all()
    out = []
    for c in rows:
        certified = db.scalar(select(func.coalesce(func.sum(CipProgressCertificate.work_value), 0)).where(
            CipProgressCertificate.contract_id == c.id, CipProgressCertificate.status.in_(("APPROVED", "PAID")))) or 0
        party = db.get(Party, c.party_id)
        out.append({"id": c.id, "number": c.number, "project_id": c.project_id,
                    "party_name_ar": party.name_ar if party else None,
                    "title_ar": c.title_ar, "title_en": c.title_en, "contract_type": c.contract_type,
                    "contract_value": c.contract_value, "certified_value": _money(certified),
                    "remaining_value": _money(Decimal(str(c.contract_value)) - Decimal(str(certified))),
                    "vat_rate": c.vat_rate, "retention_rate": c.retention_rate, "status": c.status})
    return out


# ==================================================================== CERTIFICATES
class CertificateIn(BaseModel):
    company_id: int
    contract_id: int
    certificate_date: date
    work_value: float = Field(gt=0)
    supplier_invoice_number: str | None = None
    notes: str | None = None


@router.post("/certificates", status_code=201)
def create_certificate(data: CertificateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a progress certificate (draft). VAT and retention are computed here."""
    ensure_permission(db, user, data.company_id, "cip.manage")
    contract = db.scalar(select(CipContract).where(CipContract.id == data.contract_id, CipContract.company_id == data.company_id))
    if not contract:
        raise HTTPException(404, "Contract not found")
    if contract.status != "ACTIVE":
        raise HTTPException(409, "Contract is not active")
    certified = db.scalar(select(func.coalesce(func.sum(CipProgressCertificate.work_value), 0)).where(
        CipProgressCertificate.contract_id == contract.id, CipProgressCertificate.status.in_(("DRAFT", "APPROVED", "PAID")))) or 0
    remaining = Decimal(str(contract.contract_value)) - Decimal(str(certified))
    work = _money(data.work_value)
    if work > remaining:
        raise HTTPException(422, f"Certificate exceeds remaining contract value ({remaining})")
    vat = _money(work * Decimal(str(contract.vat_rate)) / Decimal("100"))
    retention = _money(work * Decimal(str(contract.retention_rate)) / Decimal("100"))
    net = _money(work + vat - retention)
    cert = CipProgressCertificate(
        company_id=data.company_id, contract_id=contract.id,
        number=_next_number(db, CipProgressCertificate, data.company_id, "PC", data.certificate_date.year),
        certificate_date=data.certificate_date, work_value=work, vat_amount=vat,
        retention_amount=retention, net_payable=net, supplier_invoice_number=data.supplier_invoice_number,
        notes=data.notes, status="DRAFT", created_by=user.id,
    )
    db.add(cert); db.flush(); db.commit()
    return {"id": cert.id, "number": cert.number, "work_value": cert.work_value, "vat_amount": cert.vat_amount,
            "retention_amount": cert.retention_amount, "net_payable": cert.net_payable, "status": cert.status}


@router.post("/certificates/{cert_id}/approve")
def approve_certificate(cert_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Approving posts the obligation - this is where CIP and VAT are recognised."""
    ensure_permission(db, user, company_id, "cip.approve")
    cert = db.scalar(select(CipProgressCertificate).where(CipProgressCertificate.id == cert_id, CipProgressCertificate.company_id == company_id))
    if not cert:
        raise HTTPException(404, "Certificate not found")
    if cert.status != "DRAFT":
        raise HTTPException(409, f"Certificate already {cert.status}")
    if cert.created_by == user.id:
        raise HTTPException(403, "Approver must be different from the preparer")
    contract = db.get(CipContract, cert.contract_id)
    project = db.get(CipProject, contract.project_id)

    cip = _ensure_account(db, company_id, CIP_CODE)
    payable = _ensure_account(db, company_id, CONTRACTORS_PAYABLE)
    lines = [{"account_id": cip.id, "debit": cert.work_value, "credit": 0, "description": f"CIP {project.code} - {contract.number}"}]
    if Decimal(str(cert.vat_amount)) > 0:
        vat_acc = _account(db, company_id, VAT_INPUT)
        lines.append({"account_id": vat_acc.id, "debit": cert.vat_amount, "credit": 0, "description": "VAT input"})
    payable_amount = _money(Decimal(str(cert.work_value)) + Decimal(str(cert.vat_amount)) - Decimal(str(cert.retention_amount)))
    lines.append({"account_id": payable.id, "debit": 0, "credit": payable_amount, "description": f"Payable {contract.number}"})
    if Decimal(str(cert.retention_amount)) > 0:
        ret = _ensure_account(db, company_id, RETENTION_PAYABLE)
        lines.append({"account_id": ret.id, "debit": 0, "credit": cert.retention_amount, "description": "Retention held"})

    journal = create_posted_journal(
        db, company_id=company_id, user_id=user.id, posting_date=cert.certificate_date,
        reference=cert.number, description=f"Progress certificate {cert.number} - {contract.title_ar}",
        lines=lines,
    )
    cert.status = "APPROVED"; cert.journal_id = journal.id
    cert.approved_by = user.id; cert.approved_at = utc_now()
    project.capitalized_cost = _money(Decimal(str(project.capitalized_cost)) + Decimal(str(cert.work_value)))
    write_audit(db, action="CIP_CERTIFICATE_APPROVED", entity_type="CIP_CERTIFICATE", entity_id=cert.id, user_id=user.id, company_id=company_id, after={"number": cert.number, "journal": journal.number})
    db.commit()
    return {"id": cert.id, "number": cert.number, "status": cert.status, "journal_number": journal.number,
            "posted": {"cip_debit": str(cert.work_value), "vat_debit": str(cert.vat_amount),
                       "payable_credit": str(payable_amount), "retention_credit": str(cert.retention_amount)}}


# ==================================================================== COSTS
class CostIn(BaseModel):
    company_id: int
    project_id: int
    cost_date: date
    category: str
    treatment: str | None = None   # CAPITALIZE / EXPENSE - defaults from category
    description_ar: str
    description_en: str | None = None
    amount: float = Field(gt=0)
    vat_amount: float = 0
    party_id: int | None = None
    expense_account_code: str | None = None
    acknowledge_warning: bool = False


@router.get("/cost-categories")
def cost_categories(user: User = Depends(get_current_user)):
    """Expose the classification so the UI can warn before the user posts."""
    return {
        "capitalizable": [{"code": k, "ar": v[0], "en": v[1]} for k, v in CAPITALIZABLE.items()],
        "non_capitalizable": [{"code": k, "ar": v[0], "en": v[1], "reason": v[2]} for k, v in NON_CAPITALIZABLE.items()],
    }


@router.post("/costs", status_code=201)
def create_cost(data: CostIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Record a direct project cost.

    If the category is not capitalizable the system WARNS (and requires an explicit
    acknowledgement to capitalize anyway) but leaves the decision to the user.
    """
    ensure_permission(db, user, data.company_id, "cip.manage")
    project = db.scalar(select(CipProject).where(CipProject.id == data.project_id, CipProject.company_id == data.company_id))
    if not project:
        raise HTTPException(404, "Project not found")
    treatment = (data.treatment or ("EXPENSE" if data.category in NON_CAPITALIZABLE else "CAPITALIZE")).upper()
    if treatment not in ("CAPITALIZE", "EXPENSE"):
        raise HTTPException(422, "treatment must be CAPITALIZE or EXPENSE")

    warning = None
    if data.category in NON_CAPITALIZABLE and treatment == "CAPITALIZE":
        info = NON_CAPITALIZABLE[data.category]
        warning = f"{info[0]}: {info[2]}"
        if not data.acknowledge_warning:
            raise HTTPException(422, {
                "message_ar": f"تحذير: {info[0]} لا تُرسمل عادةً. {info[2]}",
                "message_en": f"Warning: {info[1]} is normally expensed. {info[2]}",
                "action": "set acknowledge_warning=true to capitalize anyway, or use treatment=EXPENSE",
            })

    amount = _money(data.amount)
    vat = _money(data.vat_amount)
    payable = _ensure_account(db, data.company_id, CONTRACTORS_PAYABLE)
    lines = []
    if treatment == "CAPITALIZE":
        target = _ensure_account(db, data.company_id, CIP_CODE)
    else:
        code = data.expense_account_code or "613010"
        target = _account(db, data.company_id, code)
    lines.append({"account_id": target.id, "debit": amount, "credit": 0, "description": data.description_ar[:100]})
    if vat > 0:
        vat_acc = _account(db, data.company_id, VAT_INPUT)
        lines.append({"account_id": vat_acc.id, "debit": vat, "credit": 0, "description": "VAT input"})
    lines.append({"account_id": payable.id, "debit": 0, "credit": _money(amount + vat), "description": "Project cost payable"})

    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=data.cost_date,
        reference=f"CIPCOST-{project.code}", description=f"Project cost {project.code} - {data.description_ar[:60]}",
        lines=lines,
    )
    cost = CipCost(
        company_id=data.company_id, project_id=project.id,
        number=_next_number(db, CipCost, data.company_id, "PCST", data.cost_date.year),
        cost_date=data.cost_date, category=data.category, treatment=treatment,
        description_ar=data.description_ar, description_en=data.description_en,
        amount=amount, vat_amount=vat, party_id=data.party_id,
        expense_account_code=None if treatment == "CAPITALIZE" else target.code,
        journal_id=journal.id, warning_acknowledged=bool(warning and data.acknowledge_warning),
        created_by=user.id,
    )
    db.add(cost); db.flush()
    if treatment == "CAPITALIZE":
        project.capitalized_cost = _money(Decimal(str(project.capitalized_cost)) + amount)
    else:
        project.expensed_cost = _money(Decimal(str(project.expensed_cost)) + amount)
    db.commit()
    return {"id": cost.id, "number": cost.number, "treatment": treatment, "amount": cost.amount,
            "journal_number": journal.number, "warning": warning}


@router.get("/costs")
def list_costs(company_id: int, project_id: int | None = Query(default=None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "cip.read")
    q = select(CipCost).where(CipCost.company_id == company_id)
    if project_id:
        q = q.where(CipCost.project_id == project_id)
    rows = db.scalars(q.order_by(CipCost.id.desc())).all()
    return [{"id": r.id, "number": r.number, "cost_date": r.cost_date.isoformat(), "category": r.category,
             "treatment": r.treatment, "description_ar": r.description_ar, "amount": r.amount,
             "vat_amount": r.vat_amount, "warning_acknowledged": r.warning_acknowledged} for r in rows]


# ==================================================================== PAYMENTS
class PaymentIn(BaseModel):
    company_id: int
    contract_id: int
    certificate_id: int | None = None
    payment_date: date
    amount: float = Field(gt=0)
    payment_kind: str = "CERTIFICATE"   # CERTIFICATE / RETENTION_RELEASE
    bank_account_id: int
    reference: str | None = None


@router.post("/payments", status_code=201)
def create_payment(data: PaymentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "cip.manage")
    contract = db.scalar(select(CipContract).where(CipContract.id == data.contract_id, CipContract.company_id == data.company_id))
    if not contract:
        raise HTTPException(404, "Contract not found")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id))
    if not bank or not bank.gl_account_id:
        raise HTTPException(422, "Bank account not found or has no GL account")
    amount = _money(data.amount)
    kind = data.payment_kind.upper()
    if kind == "RETENTION_RELEASE":
        src = _ensure_account(db, data.company_id, RETENTION_PAYABLE)
        desc = f"Retention release {contract.number}"
    else:
        src = _ensure_account(db, data.company_id, CONTRACTORS_PAYABLE)
        desc = f"Payment {contract.number}"
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=data.payment_date,
        reference=data.reference or contract.number, description=desc,
        lines=[
            {"account_id": src.id, "debit": amount, "credit": 0, "description": desc},
            {"account_id": bank.gl_account_id, "debit": 0, "credit": amount, "description": desc},
        ],
    )
    pay = CipPayment(
        company_id=data.company_id, contract_id=contract.id, certificate_id=data.certificate_id,
        number=_next_number(db, CipPayment, data.company_id, "PPAY", data.payment_date.year),
        payment_date=data.payment_date, amount=amount, payment_kind=kind,
        bank_account_id=bank.id, reference=data.reference, journal_id=journal.id, created_by=user.id,
    )
    db.add(pay); db.flush()
    if data.certificate_id:
        cert = db.get(CipProgressCertificate, data.certificate_id)
        if cert and cert.company_id == data.company_id:
            cert.paid_amount = _money(Decimal(str(cert.paid_amount)) + amount)
            if Decimal(str(cert.paid_amount)) >= Decimal(str(cert.net_payable)):
                cert.status = "PAID"
    db.commit()
    return {"id": pay.id, "number": pay.number, "amount": pay.amount, "journal_number": journal.number}


# ==================================================================== STATEMENT
@router.get("/contracts/{contract_id}/statement")
def contractor_statement(contract_id: int, company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """كشف حساب المقاول - the report that replaces the manual Excel work.

    Separates two numbers that are easy to confuse:
      * remaining_contract_value = contract value - certified work (excl. VAT)
        -> how much WORK is still owed by the contractor
      * outstanding_balance      = payable raised - paid
        -> how much CASH the company owes right now
    """
    ensure_permission(db, user, company_id, "cip.read")
    contract = db.scalar(select(CipContract).where(CipContract.id == contract_id, CipContract.company_id == company_id))
    if not contract:
        raise HTTPException(404, "Contract not found")
    party = db.get(Party, contract.party_id)
    project = db.get(CipProject, contract.project_id)
    certs = db.scalars(select(CipProgressCertificate).where(
        CipProgressCertificate.contract_id == contract.id,
        CipProgressCertificate.status.in_(("APPROVED", "PAID")),
    ).order_by(CipProgressCertificate.certificate_date)).all()
    payments = db.scalars(select(CipPayment).where(CipPayment.contract_id == contract.id).order_by(CipPayment.payment_date)).all()

    certified = sum((Decimal(str(c.work_value)) for c in certs), Decimal("0"))
    vat_total = sum((Decimal(str(c.vat_amount)) for c in certs), Decimal("0"))
    retention_total = sum((Decimal(str(c.retention_amount)) for c in certs), Decimal("0"))
    payable_raised = certified + vat_total - retention_total
    paid_certificates = sum((Decimal(str(p.amount)) for p in payments if p.payment_kind != "RETENTION_RELEASE"), Decimal("0"))
    retention_released = sum((Decimal(str(p.amount)) for p in payments if p.payment_kind == "RETENTION_RELEASE"), Decimal("0"))

    return {
        "contract": {"id": contract.id, "number": contract.number, "title_ar": contract.title_ar,
                     "party_name_ar": party.name_ar if party else None,
                     "project_code": project.code if project else None,
                     "contract_value": _money(Decimal(str(contract.contract_value))),
                     "vat_rate": contract.vat_rate, "retention_rate": contract.retention_rate},
        "work": {
            "certified_value": _money(certified),
            "remaining_contract_value": _money(Decimal(str(contract.contract_value)) - certified),
            "progress_percent": _money(certified / Decimal(str(contract.contract_value)) * 100) if Decimal(str(contract.contract_value)) else Decimal("0"),
        },
        "money": {
            "vat_total": _money(vat_total),
            "gross_certified": _money(certified + vat_total),
            "retention_held": _money(retention_total - retention_released),
            "retention_released": _money(retention_released),
            "payable_raised": _money(payable_raised),
            "paid": _money(paid_certificates),
            "outstanding_balance": _money(payable_raised - paid_certificates),
        },
        "certificates": [{"number": c.number, "date": c.certificate_date.isoformat(), "work_value": c.work_value,
                          "vat_amount": c.vat_amount, "retention_amount": c.retention_amount,
                          "net_payable": c.net_payable, "paid_amount": c.paid_amount, "status": c.status} for c in certs],
        "payments": [{"number": p.number, "date": p.payment_date.isoformat(), "amount": p.amount,
                      "kind": p.payment_kind, "reference": p.reference} for p in payments],
    }


# ==================================================================== CAPITALIZE
class CapitalizeIn(BaseModel):
    company_id: int
    ready_for_use_date: date
    asset_category_id: int
    useful_life_months: int = Field(gt=0)
    residual_value: float = 0
    depreciation_method: str = "STRAIGHT_LINE"
    bank_account_id: int
    asset_name_ar: str | None = None
    asset_name_en: str | None = None


@router.post("/projects/{project_id}/capitalize")
def capitalize_project(project_id: int, data: CapitalizeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Transfer the accumulated CIP balance into a fixed asset and start depreciation.

    Capitalization happens when the asset is READY for use (IAS 16.20), which may be
    before it is actually operated.
    """
    ensure_permission(db, user, data.company_id, "cip.approve")
    project = db.scalar(select(CipProject).where(CipProject.id == project_id, CipProject.company_id == data.company_id))
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status == "CAPITALIZED":
        raise HTTPException(409, "Project already capitalized")
    cost = Decimal(str(project.capitalized_cost))
    if cost <= 0:
        raise HTTPException(422, "Project has no capitalized cost to transfer")
    category = db.scalar(select(AssetCategory).where(AssetCategory.id == data.asset_category_id, AssetCategory.company_id == data.company_id))
    if not category:
        raise HTTPException(404, "Asset category not found")
    bank = db.scalar(select(BankAccount).where(BankAccount.id == data.bank_account_id, BankAccount.company_id == data.company_id))
    if not bank:
        raise HTTPException(404, "Bank account not found")

    cip = _ensure_account(db, data.company_id, CIP_CODE)
    ppe = _account(db, data.company_id, PPE_CODE)
    journal = create_posted_journal(
        db, company_id=data.company_id, user_id=user.id, posting_date=data.ready_for_use_date,
        reference=project.code, description=f"Capitalize project {project.code} into fixed asset",
        lines=[
            {"account_id": ppe.id, "debit": cost, "credit": 0, "description": f"PPE from {project.code}"},
            {"account_id": cip.id, "debit": 0, "credit": cost, "description": f"CIP cleared {project.code}"},
        ],
    )
    count = db.scalar(select(func.count(FixedAsset.id)).where(FixedAsset.company_id == data.company_id)) or 0
    asset = FixedAsset(
        company_id=data.company_id, asset_number=f"FA-{data.company_id}-{data.ready_for_use_date.year}-{count + 1:05d}",
        name_ar=data.asset_name_ar or project.name_ar, name_en=data.asset_name_en or project.name_en,
        category_id=category.id, acquisition_date=data.ready_for_use_date, in_service_date=data.ready_for_use_date,
        cost=cost, residual_value=_money(data.residual_value), useful_life_months=data.useful_life_months,
        depreciation_method=data.depreciation_method, accumulated_depreciation=0, accumulated_impairment=0,
        net_book_value=cost, status="ACTIVE", acquisition_journal_id=journal.id,
        bank_account_id=bank.id, branch_id=project.branch_id, cost_center_id=project.cost_center_id,
        created_by=user.id,
    )
    db.add(asset); db.flush()
    project.status = "CAPITALIZED"
    project.ready_for_use_date = data.ready_for_use_date
    project.fixed_asset_id = asset.id
    project.capitalization_journal_id = journal.id
    write_audit(db, action="CIP_CAPITALIZED", entity_type="CIP_PROJECT", entity_id=project.id, user_id=user.id, company_id=data.company_id, after={"asset_number": asset.asset_number, "cost": str(cost)})
    db.commit()
    return {"project_id": project.id, "status": project.status, "asset_id": asset.id,
            "asset_number": asset.asset_number, "capitalized_cost": _money(cost),
            "journal_number": journal.number,
            "note": "Depreciation starts from the ready-for-use date."}
