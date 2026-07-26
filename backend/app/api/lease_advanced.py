from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    BankAccount, LeaseContract, LeaseSchedule, LeaseVariablePayment,
    SaleLeasebackTransaction, SubleaseArrangement, User,
)
from app.services.audit import write_audit
from app.services.operations import get_account, money
from app.services.posting import create_posted_journal

router = APIRouter(prefix="/leases/advanced", tags=["IFRS 16 advanced leases"])


class VariablePaymentIn(BaseModel):
    lease_id: int
    payment_date: date
    payment_basis: str
    amount: Decimal
    reason: str = Field(min_length=5)
    expense_account_code: str | None = None

    @model_validator(mode="after")
    def validate_basis(self):
        self.payment_basis = self.payment_basis.upper()
        if self.payment_basis not in {"INDEX_RATE", "PERFORMANCE_USAGE", "RESIDUAL_GUARANTEE"}:
            raise ValueError("Unsupported variable payment basis")
        if self.amount == 0:
            raise ValueError("amount cannot be zero")
        if self.payment_basis == "PERFORMANCE_USAGE" and not self.expense_account_code:
            raise ValueError("expense_account_code is required for performance/usage payments")
        return self


class SaleLeasebackIn(BaseModel):
    company_id: int
    lease_id: int
    transaction_date: date
    transfer_is_sale: bool
    carrying_amount: Decimal = Field(gt=0)
    fair_value: Decimal = Field(gt=0)
    sale_proceeds: Decimal = Field(gt=0)
    retained_right_percent: Decimal = Field(ge=0, le=1)
    evidence_reference: str = Field(min_length=5)
    underlying_asset_account_code: str
    gain_account_code: str
    financing_liability_account_code: str


class SubleaseIn(BaseModel):
    company_id: int
    head_lease_id: int
    code: str
    commencement_date: date
    end_date: date
    payment_amount: Decimal = Field(gt=0)
    discount_rate: Decimal = Field(ge=0, le=1)
    carrying_rou_asset: Decimal = Field(gt=0)
    evidence_reference: str = Field(min_length=5)
    net_investment_account_code: str
    gain_loss_account_code: str

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date <= self.commencement_date:
            raise ValueError("Sublease end date must be after commencement")
        return self


def _months(start: date, end: date) -> int:
    return max((end.year - start.year) * 12 + end.month - start.month + 1, 1)


def _lease(lease_id: int, db: Session) -> LeaseContract:
    lease = db.get(LeaseContract, lease_id)
    if not lease:
        raise HTTPException(404, "Lease not found")
    return lease


def _check_review(row, user: User) -> None:
    if row.status != "READY_FOR_REVIEW":
        raise HTTPException(422, "Record is not ready for review")
    if row.prepared_by == user.id:
        raise HTTPException(409, "Preparer cannot review the record")


def _check_approve(row, user: User) -> None:
    if row.status != "REVIEWED":
        raise HTTPException(422, "Record must be reviewed first")
    if user.id in {row.prepared_by, row.reviewed_by}:
        raise HTTPException(409, "Approver must be independent")


@router.post("/variable-payments", status_code=201)
def create_variable_payment(data: VariablePaymentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lease = _lease(data.lease_id, db)
    ensure_permission(db, user, lease.company_id, "leases.modify")
    included = data.payment_basis in {"INDEX_RATE", "RESIDUAL_GUARANTEE"}
    row = LeaseVariablePayment(
        lease_id=lease.id, payment_date=data.payment_date, payment_basis=data.payment_basis,
        amount=money(data.amount), included_in_liability=included,
        remeasurement_amount=money(data.amount) if included else Decimal("0"),
        pnl_expense_amount=Decimal("0") if included else money(data.amount), reason=data.reason,
        prepared_by=user.id,
    )
    # Account choice is stored as audit evidence until final approval.
    row.reason = f"{data.reason} | expense_account={data.expense_account_code or ''}"
    db.add(row); db.flush()
    write_audit(db, action="IFRS16_VARIABLE_PAYMENT_PREPARED", entity_type="LEASE_VARIABLE_PAYMENT", entity_id=row.id,
                user_id=user.id, company_id=lease.company_id,
                after={"basis": row.payment_basis, "amount": str(row.amount), "included_in_liability": included})
    db.commit(); return {"id": row.id, "status": row.status, "included_in_liability": included,
                         "remeasurement_amount": row.remeasurement_amount, "pnl_expense_amount": row.pnl_expense_amount}


@router.post("/variable-payments/{row_id}/review")
def review_variable_payment(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(LeaseVariablePayment, row_id)
    if not row: raise HTTPException(404, "Variable payment not found")
    ensure_permission(db, user, row.lease.company_id, "leases.modify.approve")
    _check_review(row, user)
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now()
    write_audit(db, action="IFRS16_VARIABLE_PAYMENT_REVIEWED", entity_type="LEASE_VARIABLE_PAYMENT", entity_id=row.id,
                user_id=user.id, company_id=row.lease.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/variable-payments/{row_id}/approve")
def approve_variable_payment(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(LeaseVariablePayment, row_id)
    if not row: raise HTTPException(404, "Variable payment not found")
    lease = row.lease
    ensure_permission(db, user, lease.company_id, "leases.modify.approve")
    _check_approve(row, user)
    bank = db.get(BankAccount, lease.bank_account_id)
    if not bank: raise HTTPException(422, "Lease bank account is unavailable")
    if row.included_in_liability:
        rou = get_account(db, lease.company_id, "152010")
        liability = get_account(db, lease.company_id, "222010")
        amount = money(row.remeasurement_amount)
        lines = ([{"account_id": rou.id, "debit": amount, "credit": 0},
                  {"account_id": liability.id, "debit": 0, "credit": amount}]
                 if amount > 0 else
                 [{"account_id": liability.id, "debit": -amount, "credit": 0},
                  {"account_id": rou.id, "debit": 0, "credit": -amount}])
    else:
        marker = "expense_account="
        expense_code = row.reason.split(marker, 1)[1].strip() if marker in row.reason else ""
        expense = get_account(db, lease.company_id, expense_code)
        amount = money(row.pnl_expense_amount)
        lines = [{"account_id": expense.id, "debit": amount, "credit": 0},
                 {"account_id": bank.gl_account_id, "debit": 0, "credit": amount}]
    journal = create_posted_journal(db, company_id=lease.company_id, user_id=user.id, posting_date=row.payment_date,
                                    reference=f"IFRS16-VAR-{row.id}", description=f"IFRS 16 variable lease payment {row.id}",
                                    lines=lines)
    row.journal_id = journal.id; row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="IFRS16_VARIABLE_PAYMENT_APPROVED", entity_type="LEASE_VARIABLE_PAYMENT", entity_id=row.id,
                user_id=user.id, company_id=lease.company_id, after={"status": row.status, "journal": journal.number})
    db.commit(); return {"id": row.id, "status": row.status, "journal_number": journal.number}


@router.post("/sale-leasebacks", status_code=201)
def create_sale_leaseback(data: SaleLeasebackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lease = _lease(data.lease_id, db)
    if lease.company_id != data.company_id: raise HTTPException(404, "Lease not found for company")
    ensure_permission(db, user, data.company_id, "leases.modify")
    retained = Decimal(data.retained_right_percent)
    if data.transfer_is_sale:
        rou = money(Decimal(data.carrying_amount) * retained)
        gain = money((Decimal(data.fair_value) - Decimal(data.carrying_amount)) * (Decimal("1") - retained))
        excess = money(max(Decimal(data.sale_proceeds) - Decimal(data.fair_value), Decimal("0")))
        shortfall = money(max(Decimal(data.fair_value) - Decimal(data.sale_proceeds), Decimal("0")))
        rou = money(rou + shortfall)
        financing = excess
    else:
        rou = Decimal("0"); gain = Decimal("0"); financing = money(data.sale_proceeds)
    row = SaleLeasebackTransaction(
        company_id=data.company_id, lease_id=lease.id, transaction_date=data.transaction_date,
        transfer_is_sale=data.transfer_is_sale, carrying_amount=money(data.carrying_amount),
        fair_value=money(data.fair_value), sale_proceeds=money(data.sale_proceeds),
        retained_right_percent=retained, initial_rou_asset=rou, lease_liability=money(lease.initial_liability),
        gain_on_rights_transferred=gain, financing_liability=financing,
        off_market_adjustment=money(Decimal(data.sale_proceeds) - Decimal(data.fair_value)),
        evidence_reference=(f"{data.evidence_reference} | asset={data.underlying_asset_account_code} | "
                            f"gain={data.gain_account_code} | financing={data.financing_liability_account_code}"),
        prepared_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="IFRS16_SALE_LEASEBACK_PREPARED", entity_type="SALE_LEASEBACK", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"transfer_is_sale": row.transfer_is_sale, "rou": str(row.initial_rou_asset),
                       "gain": str(row.gain_on_rights_transferred), "financing": str(row.financing_liability)})
    db.commit(); return {"id": row.id, "status": row.status, "initial_rou_asset": row.initial_rou_asset,
                         "gain": row.gain_on_rights_transferred, "financing_liability": row.financing_liability}


@router.post("/sale-leasebacks/{row_id}/review")
def review_sale_leaseback(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SaleLeasebackTransaction, row_id)
    if not row: raise HTTPException(404, "Sale-and-leaseback not found")
    ensure_permission(db, user, row.company_id, "leases.modify.approve"); _check_review(row, user)
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now()
    write_audit(db, action="IFRS16_SALE_LEASEBACK_REVIEWED", entity_type="SALE_LEASEBACK", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/sale-leasebacks/{row_id}/approve")
def approve_sale_leaseback(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SaleLeasebackTransaction, row_id)
    if not row: raise HTTPException(404, "Sale-and-leaseback not found")
    ensure_permission(db, user, row.company_id, "leases.modify.approve"); _check_approve(row, user)
    lease = row.lease; bank = db.get(BankAccount, lease.bank_account_id)
    if not bank: raise HTTPException(422, "Lease bank account unavailable")
    tokens = {chunk.split("=", 1)[0].strip(): chunk.split("=", 1)[1].strip()
              for chunk in row.evidence_reference.split("|") if "=" in chunk}
    asset = get_account(db, row.company_id, tokens.get("asset", ""))
    financing = get_account(db, row.company_id, tokens.get("financing", ""))
    if not row.transfer_is_sale:
        lines = [{"account_id": bank.gl_account_id, "debit": row.sale_proceeds, "credit": 0},
                 {"account_id": financing.id, "debit": 0, "credit": row.sale_proceeds}]
    else:
        rou_account = get_account(db, row.company_id, "152010")
        gain_account = get_account(db, row.company_id, tokens.get("gain", ""))
        # The linked lease already recognized its liability and initial ROU asset.
        # This journal records the sale and adjusts that existing ROU to the retained right only.
        rou_delta = money(Decimal(row.initial_rou_asset) - Decimal(lease.initial_rou_asset))
        lines = [
            {"account_id": bank.gl_account_id, "debit": row.sale_proceeds, "credit": 0},
            {"account_id": asset.id, "debit": 0, "credit": row.carrying_amount},
        ]
        if rou_delta > 0:
            lines.append({"account_id": rou_account.id, "debit": rou_delta, "credit": 0})
        elif rou_delta < 0:
            lines.append({"account_id": rou_account.id, "debit": 0, "credit": -rou_delta})
        if row.gain_on_rights_transferred > 0:
            lines.append({"account_id": gain_account.id, "debit": 0, "credit": row.gain_on_rights_transferred})
        elif row.gain_on_rights_transferred < 0:
            lines.append({"account_id": gain_account.id, "debit": -row.gain_on_rights_transferred, "credit": 0})
        if row.financing_liability > 0:
            lines.append({"account_id": financing.id, "debit": 0, "credit": row.financing_liability})
        debit = money(sum(Decimal(str(line["debit"])) for line in lines))
        credit = money(sum(Decimal(str(line["credit"])) for line in lines))
        difference = money(debit - credit)
        if abs(difference) > Decimal("0.10"):
            raise HTTPException(422, "Sale-and-leaseback inputs do not reconcile; retained right must reflect lease liability/fair value")
        if difference > 0:
            lines.append({"account_id": gain_account.id, "debit": 0, "credit": difference})
        elif difference < 0:
            lines.append({"account_id": gain_account.id, "debit": -difference, "credit": 0})
    journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.transaction_date,
                                    reference=f"IFRS16-SLB-{row.id}", description=f"IFRS 16 sale and leaseback {row.id}", lines=lines)
    row.journal_id = journal.id; row.status = "APPROVED_POSTED"; row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="IFRS16_SALE_LEASEBACK_APPROVED", entity_type="SALE_LEASEBACK", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"status": row.status, "journal": journal.number})
    db.commit(); return {"id": row.id, "status": row.status, "journal_number": journal.number}


@router.post("/subleases", status_code=201)
def create_sublease(data: SubleaseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lease = _lease(data.head_lease_id, db)
    if lease.company_id != data.company_id: raise HTTPException(404, "Head lease not found for company")
    ensure_permission(db, user, data.company_id, "leases.modify")
    remaining = _months(max(data.commencement_date, lease.commencement_date), lease.end_date)
    submonths = _months(data.commencement_date, data.end_date)
    classification = "FINANCE" if Decimal(submonths) / Decimal(remaining) >= Decimal("0.75") else "OPERATING"
    monthly_rate = float(data.discount_rate) / 12
    net_investment = money(sum(float(data.payment_amount) / ((1 + monthly_rate) ** m) for m in range(1, submonths + 1)))
    derecognized = money(Decimal(data.carrying_rou_asset) * min(Decimal(submonths) / Decimal(remaining), Decimal("1"))) if classification == "FINANCE" else Decimal("0")
    gain_loss = money(net_investment - derecognized) if classification == "FINANCE" else Decimal("0")
    row = SubleaseArrangement(
        company_id=data.company_id, head_lease_id=lease.id, code=data.code,
        commencement_date=data.commencement_date, end_date=data.end_date,
        remaining_head_lease_months=remaining, sublease_months=submonths, classification=classification,
        payment_amount=money(data.payment_amount), discount_rate=data.discount_rate,
        net_investment=net_investment, derecognized_rou_asset=derecognized, gain_loss=gain_loss,
        evidence_reference=(f"{data.evidence_reference} | net={data.net_investment_account_code} | "
                            f"gain={data.gain_loss_account_code}"), prepared_by=user.id,
    )
    db.add(row); db.flush()
    write_audit(db, action="IFRS16_SUBLEASE_PREPARED", entity_type="SUBLEASE", entity_id=row.id,
                user_id=user.id, company_id=data.company_id,
                after={"classification": classification, "net_investment": str(net_investment), "gain_loss": str(gain_loss)})
    db.commit(); return {"id": row.id, "status": row.status, "classification": classification,
                         "net_investment": net_investment, "gain_loss": gain_loss}


@router.post("/subleases/{row_id}/review")
def review_sublease(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SubleaseArrangement, row_id)
    if not row: raise HTTPException(404, "Sublease not found")
    ensure_permission(db, user, row.company_id, "leases.modify.approve"); _check_review(row, user)
    row.status = "REVIEWED"; row.reviewed_by = user.id; row.reviewed_at = utc_now()
    write_audit(db, action="IFRS16_SUBLEASE_REVIEWED", entity_type="SUBLEASE", entity_id=row.id,
                user_id=user.id, company_id=row.company_id, after={"status": row.status})
    db.commit(); return {"id": row.id, "status": row.status}


@router.post("/subleases/{row_id}/approve")
def approve_sublease(row_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SubleaseArrangement, row_id)
    if not row: raise HTTPException(404, "Sublease not found")
    ensure_permission(db, user, row.company_id, "leases.modify.approve"); _check_approve(row, user)
    if row.classification == "FINANCE":
        tokens = {chunk.split("=", 1)[0].strip(): chunk.split("=", 1)[1].strip()
                  for chunk in row.evidence_reference.split("|") if "=" in chunk}
        net_account = get_account(db, row.company_id, tokens.get("net", ""))
        rou_account = get_account(db, row.company_id, "152010")
        gain_account = get_account(db, row.company_id, tokens.get("gain", ""))
        lines = [{"account_id": net_account.id, "debit": row.net_investment, "credit": 0},
                 {"account_id": rou_account.id, "debit": 0, "credit": row.derecognized_rou_asset}]
        if row.gain_loss >= 0:
            lines.append({"account_id": gain_account.id, "debit": 0, "credit": row.gain_loss})
        else:
            lines.append({"account_id": gain_account.id, "debit": -row.gain_loss, "credit": 0})
        journal = create_posted_journal(db, company_id=row.company_id, user_id=user.id, posting_date=row.commencement_date,
                                        reference=f"IFRS16-SUB-{row.id}", description=f"IFRS 16 finance sublease {row.code}", lines=lines)
        row.journal_id = journal.id
    row.status = "APPROVED_POSTED" if row.journal_id else "APPROVED_OPERATING"
    row.approved_by = user.id; row.approved_at = utc_now()
    write_audit(db, action="IFRS16_SUBLEASE_APPROVED", entity_type="SUBLEASE", entity_id=row.id,
                user_id=user.id, company_id=row.company_id,
                after={"status": row.status, "journal_id": row.journal_id})
    db.commit(); return {"id": row.id, "status": row.status, "journal_id": row.journal_id}


@router.get("/summary")
def advanced_lease_summary(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "finance.read")
    variable = db.scalars(select(LeaseVariablePayment).join(LeaseContract).where(LeaseContract.company_id == company_id)).all()
    slb = db.scalars(select(SaleLeasebackTransaction).where(SaleLeasebackTransaction.company_id == company_id)).all()
    subleases = db.scalars(select(SubleaseArrangement).where(SubleaseArrangement.company_id == company_id)).all()
    return {"variable_payments": len(variable), "sale_leasebacks": len(slb), "subleases": len(subleases),
            "pending_review": sum(1 for row in [*variable, *slb, *subleases] if row.status == "READY_FOR_REVIEW")}
