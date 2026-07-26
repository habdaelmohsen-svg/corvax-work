from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    Branch,
    Company,
    InventoryWriteDown,
    Item,
    JournalEntry,
    PurchaseInvoice,
    PurchaseOrder,
    SalesInvoice,
    StockMovement,
    Warehouse,
)


@dataclass(frozen=True)
class ToolResult:
    name: str
    title_ar: str
    title_en: str
    data: dict[str, Any]
    reference: str
    limitation_ar: str | None = None
    limitation_en: str | None = None


def _decimal(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def company_overview(db: Session, company_id: int, visible_branch_ids: set[int]) -> ToolResult:
    company = db.get(Company, company_id)
    if not company:
        raise ValueError("company_not_found")
    branches = db.scalars(
        select(Branch).where(Branch.company_id == company_id, Branch.id.in_(visible_branch_ids)).order_by(Branch.code)
    ).all() if visible_branch_ids else []
    return ToolResult(
        name="company_overview",
        title_ar="ملخص الشركة والفروع المسموحة",
        title_en="Company and permitted branches",
        data={
            "company": {"id": company.id, "code": company.code, "name_ar": company.name_ar, "name_en": company.name_en, "currency": company.currency},
            "branches": [{"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "city_ar": row.city_ar, "city_en": row.city_en} for row in branches],
        },
        reference=f"COMPANY-{company_id}",
    )


def sales_summary(db: Session, company_id: int, branch_id: int | None) -> ToolResult:
    if branch_id is not None:
        return ToolResult(
            name="sales_summary",
            title_ar="ملخص المبيعات",
            title_en="Sales summary",
            data={"available": False},
            reference="SALES-INVOICES",
            limitation_ar="فواتير المبيعات الحالية لا تحمل بُعد الفرع بصورة مباشرة؛ تم رفض إجمالي الشركة عند اختيار فرع لمنع تسرب بيانات فروع أخرى.",
            limitation_en="Sales invoices do not carry an authoritative branch dimension; company totals are denied when a branch is selected to prevent cross-branch disclosure.",
        )
    today = date.today()
    start = today.replace(day=1)
    posted_statuses = ("POSTED", "APPROVED", "PAID")
    row = db.execute(
        select(
            func.count(SalesInvoice.id),
            func.coalesce(func.sum(case((SalesInvoice.status.in_(posted_statuses), SalesInvoice.total), else_=0)), 0),
            func.coalesce(func.sum(case((SalesInvoice.status.notin_(posted_statuses), 1), else_=0)), 0),
        ).where(SalesInvoice.company_id == company_id, SalesInvoice.invoice_date >= start, SalesInvoice.invoice_date <= today)
    ).one()
    return ToolResult(
        name="sales_summary",
        title_ar="ملخص مبيعات الشهر الحالي",
        title_en="Current-month sales summary",
        data={"period_start": start.isoformat(), "period_end": today.isoformat(), "invoice_count": int(row[0] or 0), "posted_total": _decimal(row[1]), "unposted_count": int(row[2] or 0)},
        reference=f"SALES-{start.isoformat()}-{today.isoformat()}",
    )


def pending_documents(db: Session, company_id: int, branch_id: int | None) -> ToolResult:
    statuses = ("DRAFT", "SUBMITTED", "PENDING", "PENDING_APPROVAL", "READY_FOR_REVIEW")
    counts: dict[str, int] = {}
    limitations: list[str] = []
    if branch_id is None:
        mappings = {
            "journal_entries": JournalEntry,
            "sales_invoices": SalesInvoice,
            "purchase_invoices": PurchaseInvoice,
            "purchase_orders": PurchaseOrder,
            "inventory_write_downs": InventoryWriteDown,
        }
        for key, model in mappings.items():
            counts[key] = int(db.scalar(select(func.count(model.id)).where(model.company_id == company_id, model.status.in_(statuses))) or 0)
    else:
        counts["purchase_orders"] = int(db.scalar(
            select(func.count(PurchaseOrder.id)).join(Warehouse, Warehouse.id == PurchaseOrder.warehouse_id).where(
                PurchaseOrder.company_id == company_id,
                Warehouse.company_id == company_id,
                Warehouse.branch_id == branch_id,
                PurchaseOrder.status.in_(statuses),
            )
        ) or 0)
        counts["inventory_write_downs"] = int(db.scalar(
            select(func.count(InventoryWriteDown.id)).join(Warehouse, Warehouse.id == InventoryWriteDown.warehouse_id).where(
                InventoryWriteDown.company_id == company_id,
                Warehouse.company_id == company_id,
                Warehouse.branch_id == branch_id,
                InventoryWriteDown.status.in_(statuses),
            )
        ) or 0)
        limitations.append("Branch-unsafe document types were excluded")
    return ToolResult(
        name="pending_documents",
        title_ar="المستندات المعلقة",
        title_en="Pending documents",
        data={"counts": counts, "total": sum(counts.values())},
        reference=f"PENDING-{company_id}-{branch_id or 'ALL'}",
        limitation_ar="تم استبعاد أنواع المستندات التي لا تحمل بُعد فرع موثوقًا." if limitations else None,
        limitation_en="Document types without an authoritative branch dimension were excluded." if limitations else None,
    )


def low_stock(db: Session, company_id: int, branch_id: int | None, limit: int = 20) -> ToolResult:
    quantity = func.coalesce(func.sum(StockMovement.quantity), 0)
    statement = (
        select(Item.id, Item.code, Item.name_ar, Item.name_en, Item.uom, Item.reorder_level, quantity.label("quantity"))
        .join(StockMovement, StockMovement.item_id == Item.id)
        .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
        .where(Item.company_id == company_id, StockMovement.company_id == company_id, Warehouse.company_id == company_id, Item.active.is_(True), Item.reorder_level > 0)
    )
    if branch_id is not None:
        statement = statement.where(Warehouse.branch_id == branch_id)
    statement = statement.group_by(Item.id, Item.code, Item.name_ar, Item.name_en, Item.uom, Item.reorder_level).having(quantity < Item.reorder_level).order_by((Item.reorder_level - quantity).desc()).limit(limit)
    rows = db.execute(statement).all()
    return ToolResult(
        name="low_stock",
        title_ar="الأصناف تحت حد إعادة الطلب",
        title_en="Items below reorder level",
        data={"items": [{"id": row.id, "code": row.code, "name_ar": row.name_ar, "name_en": row.name_en, "uom": row.uom, "quantity": _decimal(row.quantity), "reorder_level": _decimal(row.reorder_level)} for row in rows], "count": len(rows)},
        reference=f"LOW-STOCK-{company_id}-{branch_id or 'ALL'}",
    )
