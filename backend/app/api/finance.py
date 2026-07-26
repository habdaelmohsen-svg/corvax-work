from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user, branch_scope_condition
from app.models import (
    Account, Branch, CostCenter, FiscalPeriod, FiscalYear, JournalEntry, JournalLine, User,
)
from app.schemas.finance import JournalCreate, JournalLineOut, JournalOut
from app.services.audit import write_audit
from app.services.posting import next_journal_number

router = APIRouter(prefix="/finance", tags=["financial engine"])
POSTED_STATUSES = ("POSTED", "REVERSED")


def journal_to_out(entry: JournalEntry) -> JournalOut:
    return JournalOut(
        id=entry.id,
        company_id=entry.company_id,
        number=entry.number,
        entry_date=entry.entry_date,
        reference=entry.reference,
        description=entry.description,
        status=entry.status,
        total_debit=entry.total_debit,
        total_credit=entry.total_credit,
        created_by=entry.created_by,
        approved_by=entry.approved_by,
        posted_by=entry.posted_by,
        created_at=entry.created_at,
        lines=[
            JournalLineOut(
                account_code=line.account.code,
                account_name_ar=line.account.name_ar,
                account_name_en=line.account.name_en,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
                cost_center_code=line.cost_center.code if line.cost_center else None,
                branch_code=line.branch.code if line.branch else None,
            )
            for line in entry.lines
        ],
    )


def get_entry(db: Session, journal_id: int) -> JournalEntry:
    entry = db.scalar(
        select(JournalEntry)
        .options(
            selectinload(JournalEntry.lines).selectinload(JournalLine.account),
            selectinload(JournalEntry.lines).selectinload(JournalLine.cost_center),
            selectinload(JournalEntry.lines).selectinload(JournalLine.branch),
        )
        .where(JournalEntry.id == journal_id)
    )
    if not entry:
        raise HTTPException(404, "Journal not found")
    return entry


def next_number(db: Session, company_id: int, entry_date: date) -> str:
    """Allocate a journal number using the single race-safe sequence.

    DEFECT FIXED (H16): this used to compute ``count + 1`` over existing journals,
    while every service-layer posting (assets, leases, prepaids, accruals, CIP,
    commissions, invoices) allocated numbers from the atomic JournalSequence table.
    The two mechanisms diverged as soon as journals were reversed or created through
    both paths, producing duplicate numbers and a 500 error from the unique
    constraint uq_journal_company_number. All journal numbering now flows through
    the same sequence.
    """
    return next_journal_number(db, company_id, entry_date)


def validate_open_period(db: Session, company_id: int, entry_date: date) -> FiscalPeriod:
    period = db.scalar(
        select(FiscalPeriod)
        .join(FiscalYear)
        .where(
            FiscalYear.company_id == company_id,
            FiscalPeriod.start_date <= entry_date,
            FiscalPeriod.end_date >= entry_date,
        )
    )
    if not period:
        raise HTTPException(422, "No fiscal period covers the journal date")
    if period.status != "OPEN":
        raise HTTPException(422, f"Fiscal period is not open: {period.status}")
    return period


@router.post("/journals", response_model=JournalOut, status_code=201)
def create_journal(
    data: JournalCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, data.company_id, "journals.create")
    validate_open_period(db, data.company_id, data.entry_date)

    # H8-DUPLICATE-REFERENCE-GUARD: block re-posting the same document reference.
    if data.reference and str(data.reference).strip() and not getattr(data, "allow_duplicate_reference", False):
        existing = db.scalar(
            select(JournalEntry.id).where(
                JournalEntry.company_id == data.company_id,
                JournalEntry.reference == data.reference,
            )
        )
        if existing is not None:
            raise HTTPException(
                409,
                f"A journal with reference '{data.reference}' already exists "
                "(pass allow_duplicate_reference=true to override).",
            )
    debit = sum((line.debit for line in data.lines), Decimal("0"))
    credit = sum((line.credit for line in data.lines), Decimal("0"))
    if debit != credit:
        raise HTTPException(422, f"Journal is not balanced: debit={debit}, credit={credit}")
    if debit <= 0:
        raise HTTPException(422, "Journal total must be greater than zero")

    account_codes = {line.account_code for line in data.lines}
    accounts = {
        row.code: row
        for row in db.scalars(
            select(Account).where(Account.company_id == data.company_id, Account.code.in_(account_codes))
        ).all()
    }
    missing = sorted(account_codes - set(accounts))
    if missing:
        raise HTTPException(422, f"Unknown account codes: {', '.join(missing)}")
    invalid = sorted(code for code, account in accounts.items() if not account.active or not account.is_postable)
    if invalid:
        raise HTTPException(422, f"Accounts are inactive or non-postable: {', '.join(invalid)}")

    cc_codes = {line.cost_center_code for line in data.lines if line.cost_center_code}
    cost_centers = {
        row.code: row
        for row in db.scalars(
            select(CostCenter).where(CostCenter.company_id == data.company_id, CostCenter.code.in_(cc_codes))
        ).all()
    } if cc_codes else {}
    if cc_codes - set(cost_centers):
        raise HTTPException(422, f"Unknown cost centers: {', '.join(sorted(cc_codes - set(cost_centers)))}")

    branch_codes = {line.branch_code for line in data.lines if line.branch_code}
    branches = {
        row.code: row
        for row in db.scalars(
            select(Branch).where(Branch.company_id == data.company_id, Branch.code.in_(branch_codes))
        ).all()
    } if branch_codes else {}
    if branch_codes - set(branches):
        raise HTTPException(422, f"Unknown branches: {', '.join(sorted(branch_codes - set(branches)))}")

    entry = JournalEntry(
        company_id=data.company_id,
        number=next_number(db, data.company_id, data.entry_date),
        entry_date=data.entry_date,
        reference=data.reference,
        description=data.description,
        status="DRAFT",
        cash_flow_activity=data.cash_flow_activity,
        cash_flow_kind=data.cash_flow_kind,
        total_debit=debit,
        total_credit=credit,
        created_by=user.id,
    )
    for line in data.lines:
        entry.lines.append(
            JournalLine(
                account_id=accounts[line.account_code].id,
                description=line.description or data.description,
                debit=line.debit,
                credit=line.credit,
                cost_center_id=cost_centers[line.cost_center_code].id if line.cost_center_code else None,
                branch_id=branches[line.branch_code].id if line.branch_code else None,
            )
        )
    db.add(entry)
    db.flush()
    write_audit(
        db,
        action="JOURNAL_CREATED",
        entity_type="JOURNAL",
        entity_id=entry.id,
        user_id=user.id,
        company_id=data.company_id,
        after={"number": entry.number, "total": str(debit), "status": entry.status},
    )
    db.commit()
    entry = get_entry(db, entry.id)
    return journal_to_out(entry)


def _default_period_start() -> date:
    """First day of the current year - resolved per request, never frozen."""
    return date(date.today().year, 1, 1)


def _default_period_end() -> date:
    """Today - resolved per request, never frozen."""
    return date.today()


@router.get("/journals", response_model=list[JournalOut])
def list_journals(
    company_id: int,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_permission(db, user, company_id, "finance.read")
    query = (
        select(JournalEntry)
        .options(
            selectinload(JournalEntry.lines).selectinload(JournalLine.account),
            selectinload(JournalEntry.lines).selectinload(JournalLine.cost_center),
            selectinload(JournalEntry.lines).selectinload(JournalLine.branch),
        )
        .where(JournalEntry.company_id == company_id)
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .limit(limit)
    )
    if status:
        query = query.where(JournalEntry.status == status)
    # AUDIT C-05: a journal is a balanced document, so its LINES are never filtered -
    # hiding some would show an unbalanced entry, which is worse than hiding nothing.
    # Instead a branch-scoped user only sees entries that touch one of their branches
    # (or carry no branch at all), and sees those entries complete.
    line_scope = branch_scope_condition(db, user, company_id, JournalLine)
    if line_scope is not None:
        query = query.where(
            JournalEntry.id.in_(select(JournalLine.journal_id).where(line_scope))
        )
    return [journal_to_out(row) for row in db.scalars(query).all()]


@router.get("/journals/{journal_id}", response_model=JournalOut)
def read_journal(journal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = get_entry(db, journal_id)
    ensure_permission(db, user, entry.company_id, "finance.read")
    # AUDIT C-05: reading one entry by id must respect the same branch restriction,
    # otherwise the list is filtered but the detail view leaks.
    line_scope = branch_scope_condition(db, user, entry.company_id, JournalLine)
    if line_scope is not None:
        permitted = db.scalar(
            select(func.count(JournalLine.id)).where(
                JournalLine.journal_id == entry.id, line_scope
            )
        )
        if not permitted:
            raise HTTPException(403, "Journal entry belongs to another branch")
    return journal_to_out(entry)


def transition(
    db: Session,
    entry: JournalEntry,
    user: User,
    *,
    required_permission: str,
    expected_status: str,
    new_status: str,
    action: str,
) -> JournalEntry:
    permissions = ensure_permission(db, user, entry.company_id, required_permission)
    if entry.status != expected_status:
        raise HTTPException(409, f"Journal status must be {expected_status}")
    if required_permission == "journals.approve" and entry.created_by == user.id and "*" not in permissions:
        raise HTTPException(409, "Maker-checker control: creator cannot approve this journal")
    before = {"status": entry.status}
    entry.status = new_status
    now = utc_now()
    if new_status == "PENDING_APPROVAL":
        entry.submitted_at = now
    elif new_status == "APPROVED":
        entry.approved_by = user.id
        entry.approved_at = now
    elif new_status == "POSTED":
        entry.posted_by = user.id
        entry.posted_at = now
    write_audit(
        db,
        action=action,
        entity_type="JOURNAL",
        entity_id=entry.id,
        user_id=user.id,
        company_id=entry.company_id,
        before=before,
        after={"status": entry.status},
    )
    db.commit()
    return get_entry(db, entry.id)


@router.post("/journals/{journal_id}/submit", response_model=JournalOut)
def submit_journal(journal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return journal_to_out(transition(db, get_entry(db, journal_id), user, required_permission="journals.create", expected_status="DRAFT", new_status="PENDING_APPROVAL", action="JOURNAL_SUBMITTED"))


@router.post("/journals/{journal_id}/approve", response_model=JournalOut)
def approve_journal(journal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return journal_to_out(transition(db, get_entry(db, journal_id), user, required_permission="journals.approve", expected_status="PENDING_APPROVAL", new_status="APPROVED", action="JOURNAL_APPROVED"))


@router.post("/journals/{journal_id}/post", response_model=JournalOut)
def post_journal(journal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = get_entry(db, journal_id)
    validate_open_period(db, entry.company_id, entry.entry_date)
    return journal_to_out(transition(db, entry, user, required_permission="journals.post", expected_status="APPROVED", new_status="POSTED", action="JOURNAL_POSTED"))


@router.post("/journals/{journal_id}/reverse", response_model=JournalOut, status_code=201)
def reverse_journal(journal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    original = get_entry(db, journal_id)
    ensure_permission(db, user, original.company_id, "journals.reverse")
    if original.status != "POSTED":
        raise HTTPException(409, "Only posted journals can be reversed")
    today = date.today()
    validate_open_period(db, original.company_id, today)
    reversal = JournalEntry(
        company_id=original.company_id,
        number=next_number(db, original.company_id, today),
        entry_date=today,
        reference=f"REV-{original.number}",
        description=f"Reversal of {original.number}: {original.description}",
        status="POSTED",
        cash_flow_activity=original.cash_flow_activity,
        cash_flow_kind=original.cash_flow_kind,
        total_debit=original.total_credit,
        total_credit=original.total_debit,
        created_by=user.id,
        approved_by=user.id,
        posted_by=user.id,
        created_at=utc_now(),
        submitted_at=utc_now(),
        approved_at=utc_now(),
        posted_at=utc_now(),
    )
    for line in original.lines:
        reversal.lines.append(
            JournalLine(
                account_id=line.account_id,
                description=f"Reversal: {line.description or original.description}",
                debit=line.credit,
                credit=line.debit,
                cost_center_id=line.cost_center_id,
                branch_id=line.branch_id,
            )
        )
    db.add(reversal)
    db.flush()
    original.status = "REVERSED"
    original.reversed_entry_id = reversal.id
    write_audit(
        db,
        action="JOURNAL_REVERSED",
        entity_type="JOURNAL",
        entity_id=original.id,
        user_id=user.id,
        company_id=original.company_id,
        before={"status": "POSTED"},
        after={"status": "REVERSED", "reversal_id": reversal.id},
    )
    db.commit()
    return journal_to_out(get_entry(db, reversal.id))


def account_balances(db: Session, company_id: int, end_date: date, start_date: date | None = None) -> list[dict]:
    conditions = [
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(POSTED_STATUSES),
        JournalEntry.entry_date <= end_date,
    ]
    if start_date:
        conditions.append(JournalEntry.entry_date >= start_date)
    rows = db.execute(
        select(
            Account.id,
            Account.code,
            Account.name_ar,
            Account.name_en,
            Account.account_type,
            Account.statement_group,
            func.coalesce(func.sum(JournalLine.debit), 0).label("debit"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("credit"),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(Account.company_id == company_id, *conditions)
        .group_by(Account.id)
        .order_by(Account.code)
    ).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name_ar": row.name_ar,
            "name_en": row.name_en,
            "account_type": row.account_type,
            "statement_group": row.statement_group,
            "debit": Decimal(row.debit),
            "credit": Decimal(row.credit),
        }
        for row in rows
    ]


@router.get("/trial-balance")
def trial_balance(
    company_id: int,
    end_date: date | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    end_date = end_date or _default_period_end()
    ensure_permission(db, user, company_id, "finance.read")
    rows = account_balances(db, company_id, end_date)
    result = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for row in rows:
        net = row["debit"] - row["credit"]
        closing_debit = max(net, Decimal("0"))
        closing_credit = max(-net, Decimal("0"))
        total_debit += closing_debit
        total_credit += closing_credit
        result.append({**row, "closing_debit": closing_debit, "closing_credit": closing_credit})
    return {
        "company_id": company_id,
        "end_date": end_date,
        "rows": result,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": total_debit == total_credit,
    }


def natural_amount(row: dict) -> Decimal:
    if row["account_type"] in {"LIABILITY", "EQUITY", "REVENUE"}:
        return row["credit"] - row["debit"]
    return row["debit"] - row["credit"]


def sum_groups(rows: list[dict], groups: set[str]) -> Decimal:
    return sum((natural_amount(row) for row in rows if row["statement_group"] in groups), Decimal("0"))


def sum_account_codes(rows: list[dict], codes: set[str]) -> Decimal:
    """Return the natural balance of a controlled set of posting accounts.

    Cash-flow adjustments must be based on the ledger account actually posted,
    not on descriptions or journal references.  Keeping the account-code sets
    explicit also makes the calculation reviewable and prevents accidental
    inclusion of ordinary cash expenses in non-cash adjustments.
    """
    return sum((natural_amount(row) for row in rows if row["code"] in codes), Decimal("0"))


def working_capital_adjustment(
    opening_rows: list[dict],
    closing_rows: list[dict],
    groups: set[str],
    *,
    asset: bool,
) -> Decimal:
    """Convert a balance-sheet movement to its indirect cash-flow sign.

    An increase in an operating asset consumes cash, while an increase in an
    operating liability provides cash.
    """
    movement = sum_groups(closing_rows, groups) - sum_groups(opening_rows, groups)
    return -movement if asset else movement


@router.get("/statements")
def financial_statements(
    company_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    method: str = Query(default="indirect", pattern="^(direct|indirect)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start_date = start_date or _default_period_start()
    end_date = end_date or _default_period_end()
    ensure_permission(db, user, company_id, "finance.read")
    if start_date > end_date:
        raise HTTPException(422, "start_date must not be after end_date")

    period_rows = account_balances(db, company_id, end_date, start_date)
    cumulative_rows = account_balances(db, company_id, end_date)

    revenue = sum_groups(period_rows, {"OPERATING_REVENUE"})
    other_income = sum_groups(period_rows, {"OTHER_INCOME"})
    cost_of_revenue = sum_groups(period_rows, {"COST_OF_REVENUE"})
    operating_expenses = sum_groups(period_rows, {"OPERATING_EXPENSES"})
    other_expenses = sum_groups(period_rows, {"OTHER_EXPENSE"})
    finance_cost = sum_groups(period_rows, {"FINANCE_COSTS"})
    zakat_tax = sum_groups(period_rows, {"ZAKAT_TAX"})
    gross_profit = revenue - cost_of_revenue
    operating_profit = gross_profit - operating_expenses
    profit_before_finance_and_tax = operating_profit + other_income - other_expenses
    profit_before_tax = profit_before_finance_and_tax - finance_cost
    net_profit = profit_before_tax - zakat_tax

    current_assets = sum_groups(cumulative_rows, {"CASH", "RECEIVABLES", "INVENTORY", "VAT_RECOVERABLE", "PREPAID_EXPENSES", "ACCRUED_REVENUE"})
    non_current_assets = sum_groups(cumulative_rows, {"PPE", "NON_CURRENT_ASSETS", "ACCUMULATED_DEPRECIATION"})
    current_liabilities = sum_groups(cumulative_rows, {"PAYABLES", "VAT", "CONTRACT_LIABILITY", "CURRENT_LIABILITIES", "ACCRUED_EXPENSES"})
    non_current_liabilities = sum_groups(cumulative_rows, {"BORROWINGS", "NON_CURRENT_LIABILITIES"})
    contributed_equity = sum_groups(cumulative_rows, {"CAPITAL", "RETAINED_EARNINGS"})
    cumulative_profit = sum_groups(cumulative_rows, {"OPERATING_REVENUE", "OTHER_INCOME"}) - sum_groups(
        cumulative_rows,
        {"COST_OF_REVENUE", "OPERATING_EXPENSES", "OTHER_EXPENSE", "FINANCE_COSTS", "ZAKAT_TAX"},
    )
    total_assets = current_assets + non_current_assets
    total_liabilities = current_liabilities + non_current_liabilities
    equity = contributed_equity + cumulative_profit

    before_rows = account_balances(db, company_id, start_date - timedelta(days=1))

    cash_entries = db.scalars(
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        .where(
            JournalEntry.company_id == company_id,
            JournalEntry.status.in_(POSTED_STATUSES),
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date,
        )
    ).all()
    cash_by_activity: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    cash_by_kind: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unclassified_cash_change = Decimal("0")
    for entry in cash_entries:
        cash_change = sum((line.debit - line.credit for line in entry.lines if line.account.is_cash), Decimal("0"))
        if cash_change == 0:
            continue
        if entry.cash_flow_activity:
            cash_by_activity[entry.cash_flow_activity] += cash_change
            cash_by_kind[entry.cash_flow_kind or "OTHER"] += cash_change
        else:
            unclassified_cash_change += cash_change

    net_operating = cash_by_activity["OPERATING"]
    net_investing = cash_by_activity["INVESTING"]
    net_financing = cash_by_activity["FINANCING"]
    classified_net_change = net_operating + net_investing + net_financing
    net_change = classified_net_change + unclassified_cash_change
    opening_cash = sum_groups(before_rows, {"CASH"})
    closing_cash = sum_groups(cumulative_rows, {"CASH"})
    cash_balance_movement = closing_cash - opening_cash
    cash_reconciliation_difference = cash_balance_movement - net_change
    if method == "direct":
        cash_flows = {
            "method": "direct",
            "customer_receipts": cash_by_kind["CUSTOMER_RECEIPTS"],
            "supplier_payments": cash_by_kind["SUPPLIER_PAYMENTS"],
            "employee_payments": cash_by_kind["EMPLOYEE_PAYMENTS"],
            "other_operating_payments": cash_by_kind["OTHER_OPERATING_PAYMENTS"],
            "net_operating": net_operating,
            "net_investing": net_investing,
            "net_financing": net_financing,
            "classified_net_change": classified_net_change,
            "unclassified_cash_change": unclassified_cash_change,
            "net_change": net_change,
            "opening_cash": opening_cash,
            "closing_cash": closing_cash,
            "cash_reconciliation_difference": cash_reconciliation_difference,
            "classification_complete": unclassified_cash_change == 0,
            "cash_reconciled": cash_reconciliation_difference == 0,
        }
    else:
        depreciation_and_amortization = sum_account_codes(period_rows, {"614010", "617010"})
        ecl_and_impairment = sum_account_codes(period_rows, {"620010"})
        other_non_cash_losses = sum_account_codes(period_rows, {"621010", "622010", "623010"})
        non_cash_gains = sum_account_codes(period_rows, {"421010", "422010", "423010"})
        non_cash_adjustments = (
            depreciation_and_amortization
            + ecl_and_impairment
            + other_non_cash_losses
            - non_cash_gains
        )

        working_capital_changes = {
            "trade_and_other_receivables": working_capital_adjustment(
                before_rows, cumulative_rows, {"RECEIVABLES", "ACCRUED_REVENUE"}, asset=True
            ),
            "inventories": working_capital_adjustment(
                before_rows, cumulative_rows, {"INVENTORY"}, asset=True
            ),
            "prepayments": working_capital_adjustment(
                before_rows, cumulative_rows, {"PREPAID_EXPENSES"}, asset=True
            ),
            "vat_recoverable": working_capital_adjustment(
                before_rows, cumulative_rows, {"VAT_RECOVERABLE"}, asset=True
            ),
            "trade_and_other_payables": working_capital_adjustment(
                before_rows, cumulative_rows, {"PAYABLES", "ACCRUED_EXPENSES"}, asset=False
            ),
            "contract_and_current_liabilities": working_capital_adjustment(
                before_rows, cumulative_rows, {"CONTRACT_LIABILITY", "CURRENT_LIABILITIES"}, asset=False
            ),
            "vat_payable": working_capital_adjustment(
                before_rows, cumulative_rows, {"VAT"}, asset=False
            ),
        }
        working_capital_total = sum(working_capital_changes.values(), Decimal("0"))
        cash_generated_before_other_adjustments = net_profit + non_cash_adjustments + working_capital_total
        other_operating_reconciliation = net_operating - cash_generated_before_other_adjustments
        cash_flows = {
            "method": "indirect",
            "net_profit": net_profit,
            "depreciation_and_amortization": depreciation_and_amortization,
            "ecl_and_impairment": ecl_and_impairment,
            "other_non_cash_losses": other_non_cash_losses,
            "non_cash_gains": non_cash_gains,
            "non_cash_adjustments": non_cash_adjustments,
            "working_capital_changes": {**working_capital_changes, "total": working_capital_total},
            "working_capital_adjustments": working_capital_total,
            "cash_generated_before_other_adjustments": cash_generated_before_other_adjustments,
            "other_operating_reconciliation": other_operating_reconciliation,
            "working_capital_and_other_adjustments": working_capital_total + other_operating_reconciliation,
            "net_operating": net_operating,
            "net_investing": net_investing,
            "net_financing": net_financing,
            "classified_net_change": classified_net_change,
            "unclassified_cash_change": unclassified_cash_change,
            "net_change": net_change,
            "opening_cash": opening_cash,
            "closing_cash": closing_cash,
            "cash_reconciliation_difference": cash_reconciliation_difference,
            "classification_complete": unclassified_cash_change == 0,
            "cash_reconciled": cash_reconciliation_difference == 0,
            "indirect_reconciles_to_direct_operating": (
                net_profit + non_cash_adjustments + working_capital_total + other_operating_reconciliation
            ) == net_operating,
        }

    opening_equity = sum_groups(before_rows, {"CAPITAL", "RETAINED_EARNINGS", "OPERATING_REVENUE", "OTHER_INCOME"}) - sum_groups(
        before_rows, {"COST_OF_REVENUE", "OPERATING_EXPENSES", "OTHER_EXPENSE", "FINANCE_COSTS", "ZAKAT_TAX"}
    )
    capital_contributions = cash_by_kind["CAPITAL_CONTRIBUTION"]

    return {
        "company_id": company_id,
        "period": {"start_date": start_date, "end_date": end_date},
        "currency": "SAR",
        "source": "POSTED_GENERAL_LEDGER",
        "income_statement": {
            "revenue": revenue,
            "operating_revenue": revenue,
            "cost_of_revenue": cost_of_revenue,
            "gross_profit": gross_profit,
            "operating_expenses": operating_expenses,
            "operating_profit": operating_profit,
            "other_income": other_income,
            "other_expenses": other_expenses,
            "profit_before_finance_and_tax": profit_before_finance_and_tax,
            "finance_cost": finance_cost,
            "profit_before_tax": profit_before_tax,
            "zakat_tax": zakat_tax,
            "net_profit": net_profit,
        },
        "financial_position": {
            "current_assets": current_assets,
            "non_current_assets": non_current_assets,
            "total_assets": total_assets,
            "current_liabilities": current_liabilities,
            "non_current_liabilities": non_current_liabilities,
            "total_liabilities": total_liabilities,
            "equity": equity,
            "liabilities_and_equity": total_liabilities + equity,
            "balanced": total_assets == total_liabilities + equity,
        },
        "cash_flows": cash_flows,
        "changes_in_equity": {
            "opening": opening_equity,
            "capital_contributions": capital_contributions,
            "profit": net_profit,
            "dividends": Decimal("0"),
            "other_comprehensive_income": Decimal("0"),
            "closing": equity,
        },
        "notes": [
            {"id": 1, "title": "Basis of preparation", "standard": "IFRS / SOCPA", "status": "MAPPED"},
            {"id": 2, "title": "Revenue recognition", "standard": "IFRS 15", "status": "ENGINE_FOUNDATION"},
            {"id": 3, "title": "Leases", "standard": "IFRS 16", "status": "PENDING_ENGINE"},
            {"id": 4, "title": "Presentation and disclosure", "standard": "IFRS 18", "status": "MAPPED"},
            {"id": 5, "title": "Cash flows", "standard": "IAS 7", "status": "LEDGER_DRIVEN"},
        ],
    }
