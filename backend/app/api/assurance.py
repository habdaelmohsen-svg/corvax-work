from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.api.period_close import _checks as period_close_checks, _period_company
from app.db import get_db
from app.dependencies import ensure_permission, get_current_user
from app.models import (
    Account,
    AuditFinding,
    BankStatement,
    ControlledDocument,
    CorrectiveAction,
    CreditExposure,
    EclRun,
    EInvoice,
    FinancialAssuranceCheck,
    FinancialAssuranceRun,
    FinancialCertification,
    FiscalPeriod,
    FxRevaluationRun,
    ForeignCurrencyBalance,
    GovernanceControl,
    GovernanceRisk,
    IntercompanyRecord,
    JournalEntry,
    JournalLine,
    StockMovement,
    User,
    UserCompanyRole,
    Role,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/assurance", tags=["financial assurance and certification"])


class AssuranceReviewIn(BaseModel):
    company_id: int
    fiscal_period_id: int
    scope: str = "MONTH_END"
    materiality_amount: Decimal = Field(gt=0)
    performance_materiality: Decimal | None = Field(default=None, gt=0)
    trivial_threshold: Decimal | None = Field(default=None, gt=0)
    management_representation: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_thresholds(self):
        self.scope = self.scope.upper()
        if self.scope not in {"PRE_CLOSE", "MONTH_END", "YEAR_END", "INTERIM"}:
            raise ValueError("Unsupported assurance scope")
        if self.performance_materiality is None:
            self.performance_materiality = (self.materiality_amount * Decimal("0.75")).quantize(Decimal("0.01"))
        if self.trivial_threshold is None:
            self.trivial_threshold = (self.materiality_amount * Decimal("0.05")).quantize(Decimal("0.01"))
        if self.performance_materiality > self.materiality_amount:
            raise ValueError("Performance materiality cannot exceed overall materiality")
        if self.trivial_threshold > self.performance_materiality:
            raise ValueError("Trivial threshold cannot exceed performance materiality")
        return self


class CertificationIn(BaseModel):
    certification_role: str
    statement_ar: str = Field(min_length=20, max_length=4000)
    statement_en: str = Field(min_length=20, max_length=4000)
    exceptions: str | None = Field(default=None, max_length=4000)


class RemediationIn(BaseModel):
    owner_user_id: int
    due_date: date


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _check(
    code: str,
    category: str,
    ar: str,
    en: str,
    status: str,
    severity: str,
    blocking: bool,
    metric=None,
    threshold=None,
    details: dict | None = None,
) -> dict:
    return {
        "code": code,
        "category": category,
        "ar": ar,
        "en": en,
        "status": status,
        "severity": severity,
        "blocking": blocking,
        "metric": metric,
        "threshold": threshold,
        "details": details or {},
    }


def _assurance_checks(db: Session, company_id: int, period: FiscalPeriod, data: AssuranceReviewIn) -> list[dict]:
    end = period.end_date
    checks: list[dict] = []

    # Reuse the operational close gate so the assurance conclusion cannot bypass the accounting close controls.
    for item in period_close_checks(db, company_id, period):
        checks.append(
            _check(
                item["code"],
                "FINANCIAL_CLOSE",
                item["ar"],
                item["en"],
                item["status"],
                "HIGH" if item["blocking"] else "MEDIUM",
                bool(item["blocking"]),
                details=item["details"],
            )
        )

    # Independent balance-sheet equation check, not only debit/credit equality.
    balances = db.execute(
        select(
            Account.account_type,
            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(
            Account.company_id == company_id,
            JournalEntry.company_id == company_id,
            JournalEntry.entry_date <= end,
            JournalEntry.status.in_(["POSTED", "REVERSED"]),
        )
        .group_by(Account.account_type)
    ).all()
    by_type = {row[0]: _decimal(row[1]) for row in balances}
    assets = by_type.get("ASSET", Decimal("0"))
    liabilities = -by_type.get("LIABILITY", Decimal("0"))
    equity = -by_type.get("EQUITY", Decimal("0"))
    revenue = -by_type.get("REVENUE", Decimal("0"))
    expenses = by_type.get("EXPENSE", Decimal("0"))
    current_result = revenue - expenses
    equation_difference = (assets - liabilities - equity - current_result).quantize(Decimal("0.01"))
    equation_status = "PASS" if abs(equation_difference) <= data.trivial_threshold else "FAIL"
    checks.append(
        _check(
            "FINANCIAL_STATEMENT_EQUATION",
            "FINANCIAL_STATEMENTS",
            "معادلة المركز المالي متوازنة بعد نتيجة الفترة",
            "Statement of financial position equation balances after current result",
            equation_status,
            "CRITICAL",
            True,
            equation_difference,
            data.trivial_threshold,
            {
                "assets": str(assets),
                "liabilities": str(liabilities),
                "equity": str(equity),
                "current_result": str(current_result),
            },
        )
    )

    high_risks = db.scalar(
        select(func.count(GovernanceRisk.id)).where(
            GovernanceRisk.company_id == company_id,
            GovernanceRisk.status != "CLOSED",
            GovernanceRisk.residual_score >= 15,
        )
    ) or 0
    checks.append(
        _check(
            "HIGH_RESIDUAL_RISKS",
            "GOVERNANCE",
            "لا توجد مخاطر متبقية مرتفعة غير معالجة",
            "No untreated high residual risks",
            "PASS" if high_risks == 0 else "FAIL",
            "HIGH",
            True,
            high_risks,
            0,
            {"count": high_risks, "threshold_score": 15},
        )
    )

    ineffective_controls = db.scalar(
        select(func.count(GovernanceControl.id)).where(
            GovernanceControl.company_id == company_id,
            (
                GovernanceControl.design_status.in_(["INEFFECTIVE", "DEFICIENT"])
                | GovernanceControl.operating_status.in_(["INEFFECTIVE", "DEFICIENT"])
            ),
        )
    ) or 0
    checks.append(
        _check(
            "INEFFECTIVE_CONTROLS",
            "INTERNAL_CONTROL",
            "الضوابط الجوهرية مصممة وتعمل بفعالية",
            "Material controls are effectively designed and operating",
            "PASS" if ineffective_controls == 0 else "FAIL",
            "CRITICAL",
            True,
            ineffective_controls,
            0,
            {"count": ineffective_controls},
        )
    )

    high_findings = db.scalar(
        select(func.count(AuditFinding.id)).where(
            AuditFinding.company_id == company_id,
            AuditFinding.status != "CLOSED",
            AuditFinding.severity.in_(["HIGH", "CRITICAL"]),
        )
    ) or 0
    checks.append(
        _check(
            "HIGH_AUDIT_FINDINGS",
            "AUDIT",
            "لا توجد ملاحظات مراجعة مرتفعة أو حرجة مفتوحة",
            "No open high or critical audit findings",
            "PASS" if high_findings == 0 else "FAIL",
            "CRITICAL",
            True,
            high_findings,
            0,
            {"count": high_findings},
        )
    )

    overdue_actions = db.scalar(
        select(func.count(CorrectiveAction.id)).where(
            CorrectiveAction.company_id == company_id,
            CorrectiveAction.status.not_in(["COMPLETED", "CLOSED"]),
            CorrectiveAction.due_date.is_not(None),
            CorrectiveAction.due_date <= end,
        )
    ) or 0
    checks.append(
        _check(
            "OVERDUE_CORRECTIVE_ACTIONS",
            "AUDIT",
            "الإجراءات التصحيحية المتأخرة مغلقة",
            "Overdue corrective actions are closed",
            "PASS" if overdue_actions == 0 else "FAIL",
            "HIGH",
            True,
            overdue_actions,
            0,
            {"count": overdue_actions},
        )
    )

    unmatched_ic = db.scalar(
        select(func.count(IntercompanyRecord.id)).where(
            IntercompanyRecord.company_id == company_id,
            IntercompanyRecord.transaction_date <= end,
            IntercompanyRecord.status != "MATCHED",
        )
    ) or 0
    checks.append(
        _check(
            "INTERCOMPANY_RECONCILIATION",
            "CONSOLIDATION",
            "جميع معاملات الأطراف المرتبطة مطابقة",
            "All intercompany balances are reconciled",
            "PASS" if unmatched_ic == 0 else "FAIL",
            "HIGH",
            True,
            unmatched_ic,
            0,
            {"count": unmatched_ic},
        )
    )

    foreign_balances = db.scalar(
        select(func.count(ForeignCurrencyBalance.id)).where(
            ForeignCurrencyBalance.company_id == company_id,
            ForeignCurrencyBalance.foreign_amount != 0,
        )
    ) or 0
    latest_fx = db.scalar(
        select(func.max(FxRevaluationRun.revaluation_date)).where(
            FxRevaluationRun.company_id == company_id,
            FxRevaluationRun.status.in_(["POSTED", "COMPLETED"]),
            FxRevaluationRun.revaluation_date <= end,
        )
    )
    fx_ok = foreign_balances == 0 or latest_fx == end
    checks.append(
        _check(
            "FX_REVALUATION",
            "IAS21",
            "أرصدة العملات الأجنبية معاد تقييمها بسعر الإقفال",
            "Foreign-currency balances are revalued at closing rate",
            "PASS" if fx_ok else "FAIL",
            "HIGH",
            True,
            foreign_balances,
            0,
            {"foreign_balance_count": foreign_balances, "latest_revaluation_date": str(latest_fx) if latest_fx else None, "required_date": str(end)},
        )
    )

    open_exposure = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(CreditExposure.carrying_amount), 0)).where(
                CreditExposure.company_id == company_id,
                CreditExposure.status == "OPEN",
            )
        )
    )
    latest_ecl = db.scalar(
        select(func.max(EclRun.as_of_date)).where(EclRun.company_id == company_id, EclRun.as_of_date <= end)
    )
    ecl_required = open_exposure >= data.trivial_threshold
    ecl_ok = (not ecl_required) or latest_ecl == end
    checks.append(
        _check(
            "IFRS9_ECL",
            "IFRS9",
            "خسائر الائتمان المتوقعة محتسبة حتى تاريخ التقرير",
            "Expected credit losses are calculated through reporting date",
            "PASS" if ecl_ok else "FAIL",
            "HIGH",
            True,
            open_exposure,
            data.trivial_threshold,
            {"latest_ecl_date": str(latest_ecl) if latest_ecl else None, "required_date": str(end)},
        )
    )

    overdue_documents = db.scalar(
        select(func.count(ControlledDocument.id)).where(
            ControlledDocument.company_id == company_id,
            ControlledDocument.status == "APPROVED",
            ControlledDocument.review_date.is_not(None),
            ControlledDocument.review_date <= end,
        )
    ) or 0
    checks.append(
        _check(
            "POLICY_REVIEW",
            "GOVERNANCE",
            "السياسات المحاسبية والرقابية سارية ومراجعة",
            "Accounting and control policies are current and reviewed",
            "PASS" if overdue_documents == 0 else "WARNING",
            "MEDIUM",
            False,
            overdue_documents,
            0,
            {"documents_due": overdue_documents},
        )
    )

    unreported_invoices = db.scalar(
        select(func.count(EInvoice.id)).where(
            EInvoice.company_id == company_id,
            EInvoice.issue_datetime <= datetime.combine(end, datetime.max.time()),
            EInvoice.status.not_in(["CLEARED", "REPORTED"]),
        )
    ) or 0
    checks.append(
        _check(
            "ZATCA_STATUS",
            "COMPLIANCE",
            "حالة الفواتير الإلكترونية مكتملة لدى الهيئة",
            "E-invoice clearance/reporting status is complete",
            "PASS" if unreported_invoices == 0 else "WARNING",
            "HIGH",
            False,
            unreported_invoices,
            0,
            {"count": unreported_invoices, "external_dependency": True},
        )
    )

    if data.scope in {"MONTH_END", "YEAR_END"}:
        checks.append(
            _check(
                "PERIOD_CLOSED",
                "FINANCIAL_CLOSE",
                "الفترة المالية مغلقة قبل الاعتماد النهائي",
                "Fiscal period is closed before final certification",
                "PASS" if period.status == "CLOSED" else "FAIL",
                "CRITICAL",
                True,
                details={"period_status": period.status},
            )
        )

    return checks


def _serialize(run: FinancialAssuranceRun, checks: list[FinancialAssuranceCheck], certs: list[FinancialCertification]) -> dict:
    return {
        "id": run.id,
        "company_id": run.company_id,
        "fiscal_period_id": run.fiscal_period_id,
        "scope": run.scope,
        "materiality_amount": run.materiality_amount,
        "performance_materiality": run.performance_materiality,
        "trivial_threshold": run.trivial_threshold,
        "status": run.status,
        "conclusion": run.conclusion,
        "prepared_by": run.prepared_by,
        "reviewed_by": run.reviewed_by,
        "approved_by": run.approved_by,
        "created_at": run.created_at,
        "reviewed_at": run.reviewed_at,
        "approved_at": run.approved_at,
        "checks": [
            {
                "id": c.id,
                "code": c.code,
                "category": c.category,
                "name_ar": c.name_ar,
                "name_en": c.name_en,
                "status": c.status,
                "severity": c.severity,
                "blocking": c.blocking,
                "metric_value": c.metric_value,
                "threshold_value": c.threshold_value,
                "details": json.loads(c.details or "{}"),
                "remediation_owner_id": c.remediation_owner_id,
                "remediation_due_date": c.remediation_due_date,
            }
            for c in checks
        ],
        "certifications": [
            {
                "id": c.id,
                "role": c.certification_role,
                "status": c.certification_status,
                "statement_ar": c.statement_ar,
                "statement_en": c.statement_en,
                "exceptions": c.exceptions,
                "certified_by": c.certified_by,
                "certified_at": c.certified_at,
            }
            for c in certs
        ],
    }


def _get_run(db: Session, run_id: int) -> FinancialAssuranceRun:
    run = db.get(FinancialAssuranceRun, run_id)
    if not run:
        raise HTTPException(404, "Assurance run not found")
    return run


def _load_run(db: Session, run: FinancialAssuranceRun) -> dict:
    checks = db.scalars(
        select(FinancialAssuranceCheck).where(FinancialAssuranceCheck.assurance_run_id == run.id).order_by(FinancialAssuranceCheck.blocking.desc(), FinancialAssuranceCheck.category, FinancialAssuranceCheck.id)
    ).all()
    certs = db.scalars(
        select(FinancialCertification).where(FinancialCertification.assurance_run_id == run.id).order_by(FinancialCertification.id)
    ).all()
    return _serialize(run, list(checks), list(certs))


@router.post("/review", status_code=201)
def review_assurance(data: AssuranceReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, data.company_id, "assurance.review")
    period = _period_company(db, data.fiscal_period_id, data.company_id)
    run = db.scalar(
        select(FinancialAssuranceRun).where(
            FinancialAssuranceRun.company_id == data.company_id,
            FinancialAssuranceRun.fiscal_period_id == data.fiscal_period_id,
            FinancialAssuranceRun.scope == data.scope,
        )
    )
    if not run:
        run = FinancialAssuranceRun(
            company_id=data.company_id,
            fiscal_period_id=data.fiscal_period_id,
            scope=data.scope,
            materiality_amount=data.materiality_amount,
            performance_materiality=data.performance_materiality,
            trivial_threshold=data.trivial_threshold,
            status="REVIEWED",
            conclusion="NOT_ASSESSED",
            prepared_by=user.id,
            management_representation=data.management_representation,
        )
        db.add(run)
        db.flush()
    else:
        if run.status == "APPROVED":
            raise HTTPException(409, "Approved assurance run cannot be overwritten")
        db.query(FinancialAssuranceCheck).filter(FinancialAssuranceCheck.assurance_run_id == run.id).delete()
        db.query(FinancialCertification).filter(FinancialCertification.assurance_run_id == run.id).delete()
        run.materiality_amount = data.materiality_amount
        run.performance_materiality = data.performance_materiality
        run.trivial_threshold = data.trivial_threshold
        run.status = "REVIEWED"
        run.prepared_by = user.id
        run.reviewed_by = None
        run.approved_by = None
        run.reviewed_at = None
        run.approved_at = None
        run.management_representation = data.management_representation

    generated = _assurance_checks(db, data.company_id, period, data)
    blocking_failures = 0
    warnings = 0
    for item in generated:
        if item["blocking"] and item["status"] == "FAIL":
            blocking_failures += 1
        if item["status"] == "WARNING":
            warnings += 1
        db.add(
            FinancialAssuranceCheck(
                assurance_run_id=run.id,
                code=item["code"],
                category=item["category"],
                name_ar=item["ar"],
                name_en=item["en"],
                status=item["status"],
                severity=item["severity"],
                blocking=item["blocking"],
                metric_value=item["metric"],
                threshold_value=item["threshold"],
                details=json.dumps(item["details"], default=str),
            )
        )
    run.conclusion = "NOT_READY" if blocking_failures else ("CONDITIONAL" if warnings else "READY")
    write_audit(
        db,
        action="FINANCIAL_ASSURANCE_REVIEWED",
        entity_type="FINANCIAL_ASSURANCE",
        entity_id=run.id,
        user_id=user.id,
        company_id=data.company_id,
        after={"scope": data.scope, "conclusion": run.conclusion, "blocking_failures": blocking_failures, "warnings": warnings},
    )
    db.commit()
    return _load_run(db, run)


@router.post("/{run_id}/submit")
def submit_assurance(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    ensure_permission(db, user, run.company_id, "assurance.review")
    if run.prepared_by != user.id:
        raise HTTPException(403, "Only the preparer may submit the assurance file")
    blockers = db.scalar(
        select(func.count(FinancialAssuranceCheck.id)).where(
            FinancialAssuranceCheck.assurance_run_id == run.id,
            FinancialAssuranceCheck.blocking.is_(True),
            FinancialAssuranceCheck.status == "FAIL",
        )
    ) or 0
    if blockers:
        raise HTTPException(409, {"message": "Assurance submission blocked", "blocking_failures": blockers})
    run.status = "SUBMITTED"
    required_roles = ["FINANCIAL_CONTROLLER", "CFO"]
    if run.scope == "YEAR_END":
        required_roles.append("INTERNAL_AUDIT")
    for role in required_roles:
        db.add(
            FinancialCertification(
                assurance_run_id=run.id,
                certification_role=role,
                certification_status="PENDING",
                statement_ar="في انتظار إقرار المسؤول المختص بعد مراجعة الأدلة والاستثناءات.",
                statement_en="Pending responsible officer certification after reviewing evidence and exceptions.",
            )
        )
    write_audit(db, action="FINANCIAL_ASSURANCE_SUBMITTED", entity_type="FINANCIAL_ASSURANCE", entity_id=run.id, user_id=user.id, company_id=run.company_id, after={"required_roles": required_roles})
    db.commit()
    return _load_run(db, run)


@router.post("/{run_id}/certify")
def certify_assurance(run_id: int, data: CertificationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    ensure_permission(db, user, run.company_id, "assurance.approve")
    if run.status not in {"SUBMITTED", "CERTIFICATION_IN_PROGRESS"}:
        raise HTTPException(409, "Assurance file is not awaiting certification")
    if run.prepared_by == user.id:
        raise HTTPException(409, "Maker-checker control: preparer cannot certify the assurance file")
    role = data.certification_role.upper()
    allowed_roles = {
        "FINANCIAL_CONTROLLER": {"FINANCIAL_CONTROLLER", "SUPER_ADMIN"},
        "CFO": {"CFO", "SUPER_ADMIN"},
        "INTERNAL_AUDIT": {"AUDITOR", "SUPER_ADMIN"},
    }
    membership_roles = set(
        db.scalars(
            select(Role.code)
            .join(UserCompanyRole, UserCompanyRole.role_id == Role.id)
            .where(UserCompanyRole.user_id == user.id, UserCompanyRole.company_id == run.company_id)
        ).all()
    )
    if role not in allowed_roles or not membership_roles.intersection(allowed_roles[role]):
        raise HTTPException(403, f"User role is not authorized to certify as {role}")
    prior_certifier = db.scalar(
        select(FinancialCertification.id).where(
            FinancialCertification.assurance_run_id == run.id,
            FinancialCertification.certified_by == user.id,
            FinancialCertification.certification_status == "CERTIFIED",
        )
    )
    if prior_certifier:
        raise HTTPException(409, "Segregation of duties: one user cannot provide multiple certifications")
    cert = db.scalar(
        select(FinancialCertification).where(
            FinancialCertification.assurance_run_id == run.id,
            FinancialCertification.certification_role == role,
        )
    )
    if not cert:
        raise HTTPException(404, "Certification role is not required for this assurance scope")
    if cert.certification_status == "CERTIFIED":
        raise HTTPException(409, "Certification already completed")
    if role == "CFO":
        controller = db.scalar(
            select(FinancialCertification).where(
                FinancialCertification.assurance_run_id == run.id,
                FinancialCertification.certification_role == "FINANCIAL_CONTROLLER",
            )
        )
        if not controller or controller.certification_status != "CERTIFIED":
            raise HTTPException(409, "Financial Controller certification is required before CFO certification")
    cert.certification_status = "CERTIFIED"
    cert.statement_ar = data.statement_ar
    cert.statement_en = data.statement_en
    cert.exceptions = data.exceptions
    cert.certified_by = user.id
    cert.certified_at = utc_now()
    if role == "FINANCIAL_CONTROLLER":
        run.reviewed_by = user.id
        run.reviewed_at = utc_now()
        run.status = "CERTIFICATION_IN_PROGRESS"
    db.flush()
    pending = db.scalar(
        select(func.count(FinancialCertification.id)).where(
            FinancialCertification.assurance_run_id == run.id,
            FinancialCertification.certification_status != "CERTIFIED",
        )
    ) or 0
    if pending == 0:
        run.status = "APPROVED"
        run.approved_by = user.id
        run.approved_at = utc_now()
    write_audit(db, action="FINANCIAL_ASSURANCE_CERTIFIED", entity_type="FINANCIAL_ASSURANCE", entity_id=run.id, user_id=user.id, company_id=run.company_id, after={"role": role, "status": run.status, "exceptions": data.exceptions})
    db.commit()
    return _load_run(db, run)


@router.patch("/checks/{check_id}/remediation")
def assign_remediation(check_id: int, data: RemediationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check = db.get(FinancialAssuranceCheck, check_id)
    if not check:
        raise HTTPException(404, "Assurance check not found")
    run = _get_run(db, check.assurance_run_id)
    ensure_permission(db, user, run.company_id, "assurance.review")
    check.remediation_owner_id = data.owner_user_id
    check.remediation_due_date = data.due_date
    write_audit(db, action="ASSURANCE_REMEDIATION_ASSIGNED", entity_type="FINANCIAL_ASSURANCE_CHECK", entity_id=check.id, user_id=user.id, company_id=run.company_id, after={"owner_user_id": data.owner_user_id, "due_date": str(data.due_date)})
    db.commit()
    return {"check_id": check.id, "owner_user_id": check.remediation_owner_id, "due_date": check.remediation_due_date}


@router.get("/runs")
def list_assurance_runs(company_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(db, user, company_id, "assurance.read")
    runs = db.scalars(select(FinancialAssuranceRun).where(FinancialAssuranceRun.company_id == company_id).order_by(FinancialAssuranceRun.created_at.desc())).all()
    return [_load_run(db, run) for run in runs]


@router.get("/{run_id}")
def get_assurance_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    ensure_permission(db, user, run.company_id, "assurance.read")
    return _load_run(db, run)
