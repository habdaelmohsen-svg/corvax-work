from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.core.security import hash_password
from app.models import (
    Account, AssetCategory, BankAccount, BillOfMaterial, BillOfMaterialLine, Branch, Budget, BudgetLine, Company, CostCenter,
    DeliveryPlatform, DemoDataRecord, Employee, EmployeeShiftAssignment, FiscalPeriod, FiscalYear, GymCafeProductProfile, GymDepartment, GymDepartmentPlanAccess, GymFacility, Item, JournalEntry, JournalLine, LeaveType, LegalRuleVersion, Member, MembershipPlan, MenuItem, Party, Permission, Role,
    Shift, SoDRule, StockMovement, User, UserCompanyRole, Warehouse, WorkCenter,
)

PERMISSIONS = {
    "reports.read": ("عرض مركز التقارير الشامل", "View comprehensive reporting center"),
    "reports.export": ("تصدير تقارير النظام", "Export system reports"),
    "reports.tax.configure": ("إدارة إعدادات تقارير الضريبة", "Manage tax reporting settings"),
    "company.read": ("عرض الشركات", "View companies"),
    "masterdata.read": ("عرض البيانات الأساسية", "View master data"),
    "masterdata.manage": ("إدارة البيانات الأساسية", "Manage master data"),
    "users.manage": ("إدارة المستخدمين", "Manage users"),
    "journals.create": ("إنشاء القيود", "Create journals"),
    "journals.approve": ("اعتماد القيود", "Approve journals"),
    "journals.post": ("ترحيل القيود", "Post journals"),
    "journals.reverse": ("عكس القيود", "Reverse journals"),
    "finance.read": ("عرض المالية", "View finance"),
    "finance.arap.read": ("عرض أعمار العملاء والموردين", "View AR/AP aging"),
    "finance.arap.allocate": ("تخصيص التحصيلات والمدفوعات", "Allocate receipts and payments"),
    "finance.arap.opening": ("إدارة الأرصدة الافتتاحية التفصيلية", "Manage detailed opening balances"),
    "finance.reporting.manage": ("إعداد التقارير المالية المتقدمة", "Prepare advanced financial reporting"),
    "finance.reporting.approve": ("اعتماد التقارير المالية المتقدمة", "Approve advanced financial reporting"),
    "finance.disclosures.manage": ("إعداد الإيضاحات المالية", "Prepare financial disclosures"),
    "finance.disclosures.approve": ("مراجعة واعتماد الإيضاحات المالية", "Review and approve financial disclosures"),
    "finance.corporate.read": ("عرض التقارير المؤسسية والضريبة المؤجلة", "View corporate reporting and deferred tax"),
    "finance.corporate.manage": ("إعداد التقارير المؤسسية والضريبة المؤجلة", "Prepare corporate reporting and deferred tax"),
    "finance.corporate.review": ("مراجعة التقارير المؤسسية والضريبة المؤجلة", "Review corporate reporting and deferred tax"),
    "finance.corporate.approve": ("اعتماد وترحيل التقارير المؤسسية والضريبة المؤجلة", "Approve and post corporate reporting and deferred tax"),
    "audit.read": ("عرض سجل المراجعة", "View audit log"),
    "bank.statement.prepare": ("إعداد ومطابقة كشوف البنك", "Prepare and match bank statements"),
    "bank.reconcile": ("اعتماد التسويات البنكية", "Approve bank reconciliations"),
    "budget.read": ("عرض الموازنة", "View budgets"),
    "budget.manage": ("إدارة الموازنة", "Manage budgets"),
    "budget.approve": ("اعتماد الموازنة", "Approve budgets"),
    "inventory.read": ("عرض المخزون", "View inventory"),
    "inventory.manage": ("إدارة المخزون", "Manage inventory"),
    "inventory.receive": ("استلام المخزون", "Receive inventory"),
    "inventory.issue": ("صرف المخزون", "Issue inventory"),
    "inventory.transfer": ("تحويل المخزون", "Transfer inventory"),
    "procurement.manage": ("إدارة المشتريات", "Manage procurement"),
    "procurement.approve": ("اعتماد أوامر الشراء", "Approve purchase orders"),
    "procurement.invoice": ("مطابقة فواتير الموردين", "Match supplier invoices"),
    "gym.read": ("عرض النادي", "View gym"),
    "gym.manage": ("إدارة النادي", "Manage gym"),
    "gym.memberships.manage": ("إعداد تعديلات العضويات", "Prepare membership modifications"),
    "gym.memberships.approve": ("اعتماد تعديلات واستردادات العضويات", "Approve membership modifications and refunds"),
    "gym.classes.manage": ("إدارة الحصص والجداول", "Manage classes and schedules"),
    "gym.bookings.manage": ("إدارة حجوزات الحصص وقوائم الانتظار", "Manage class bookings and waitlists"),
    "gym.pt.manage": ("إدارة باقات وجلسات التدريب الشخصي", "Manage personal-training packages and sessions"),
    "gym.pt.complete": ("إتمام جلسات التدريب الشخصي", "Complete personal-training sessions"),
    "gym.commissions.review": ("إعداد ومراجعة عمولات المدربين", "Prepare and review trainer commissions"),
    "gym.commissions.approve": ("اعتماد وصرف عمولات المدربين", "Approve and pay trainer commissions"),
    "gym.access.capture": ("تسجيل دخول وخروج أعضاء النادي", "Capture gym member access"),
    "gym.lockers.manage": ("إدارة خزائن الأعضاء", "Manage member lockers"),
    "gym.transfers.manage": ("إعداد تحويل العضويات بين الفروع", "Prepare membership branch transfers"),
    "gym.transfers.approve": ("اعتماد تحويل العضويات بين الفروع", "Approve membership branch transfers"),
    "gym.departments.manage": ("إدارة أقسام النادي ومراكز الربحية", "Manage gym departments and profit centers"),
    "gym.facilities.manage": ("إدارة مرافق وحجوزات النادي", "Manage gym facilities and bookings"),
    "gym.facilities.approve": ("اعتماد حجوزات واستردادات مرافق النادي", "Approve gym facility bookings and refunds"),
    "gym.cafe.manage": ("إدارة منتجات وتشغيل كوفي شوب النادي", "Manage gym cafe products and operations"),
    "revenue.recognize": ("الاعتراف بالإيراد", "Recognize revenue"),
    "leases.manage": ("إدارة عقود الإيجار", "Manage leases"),
    "leases.post": ("ترحيل جداول الإيجار", "Post lease schedules"),
    "leases.modify": ("إدارة تعديلات عقود الإيجار", "Manage lease modifications"),
    "leases.modify.approve": ("اعتماد تعديلات عقود الإيجار", "Approve lease modifications"),
    "manufacturing.read": ("عرض التصنيع", "View manufacturing"),
    "manufacturing.manage": ("إدارة التصنيع", "Manage manufacturing"),
    "manufacturing.issue": ("صرف خامات الإنتاج", "Issue production materials"),
    "manufacturing.complete": ("إتمام الإنتاج", "Complete production"),
    "manufacturing.routing": ("إعداد مسارات الإنتاج", "Prepare manufacturing routings"),
    "manufacturing.routing.approve": ("اعتماد مسارات الإنتاج", "Approve manufacturing routings"),
    "manufacturing.plan": ("تشغيل تخطيط الاحتياجات", "Run material requirements planning"),
    "manufacturing.plan.approve": ("اعتماد خطط الاحتياجات", "Approve material requirements plans"),
    "manufacturing.scrap": ("تسجيل الهالك والإعادة", "Record production scrap and rework"),
    "manufacturing.cost.prepare": ("إعداد إقفال تكلفة الإنتاج", "Prepare production cost close"),
    "manufacturing.cost.review": ("مراجعة إقفال تكلفة الإنتاج", "Review production cost close"),
    "manufacturing.cost.approve": ("اعتماد إقفال تكلفة الإنتاج", "Approve production cost close"),
    "quality.read": ("عرض الجودة", "View quality"),
    "quality.manage": ("إدارة الجودة", "Manage quality"),
    "quality.objectives": ("إدارة أهداف الجودة", "Manage quality objectives"),
    "quality.plans": ("إدارة خطط الفحص", "Manage inspection plans"),
    "quality.capa": ("إدارة الإجراءات التصحيحية والوقائية", "Manage CAPA"),
    "quality.complaints": ("إدارة شكاوى الجودة", "Manage quality complaints"),
    "quality.suppliers": ("تقييم جودة الموردين", "Evaluate supplier quality"),
    "quality.review": ("إدارة مراجعة الإدارة للجودة", "Manage quality management review"),
    "audit.verify_integrity": ("التحقق من سلامة سجل المراجعة", "Verify audit-log integrity"),
    "food_safety.read": ("عرض سلامة الغذاء وHACCP", "View food safety and HACCP"),
    "food_safety.manage": ("إدارة سلامة الغذاء وHACCP", "Manage food safety and HACCP"),
    "food_safety.approve": ("اعتماد خطط HACCP وCOA والاستدعاء", "Approve HACCP, COA and recalls"),
    "access.review": ("مراجعة الصلاحيات وفصل المهام", "Review access and segregation of duties"),
    "access.manage": ("إدارة مراجعات الصلاحيات وفصل المهام", "Manage access reviews and SoD"),
    "access.approve": ("اعتماد مراجعات الصلاحيات", "Approve access reviews"),
    "assets.read": ("عرض الأصول الثابتة", "View fixed assets"),
    "assets.manage": ("إدارة الأصول الثابتة", "Manage fixed assets"),
    "assets.depreciate": ("تشغيل إهلاك الأصول", "Run asset depreciation"),
    "prepaids.read": ("عرض المصروفات المدفوعة مقدمًا", "View prepaid expenses"),
    "prepaids.manage": ("إدارة المصروفات المدفوعة مقدمًا", "Manage prepaid expenses"),
    "prepaids.amortize": ("ترحيل إطفاء المصروفات المقدمة", "Post prepaid amortization"),
    "accruals.read": ("عرض المصروفات والإيرادات المستحقة", "View accruals"),
    "accruals.manage": ("إدارة الاستحقاقات", "Manage accruals"),
    "accruals.post": ("ترحيل الاستحقاقات", "Post accruals"),
    "accruals.reverse": ("عكس الاستحقاقات", "Reverse accruals"),
    "recurring.read": ("عرض القيود المتكررة", "View recurring journals"),
    "recurring.manage": ("إدارة القيود المتكررة", "Manage recurring journals"),
    "recurring.run": ("تشغيل القيود المتكررة", "Run recurring journals"),
    "payroll.read": ("عرض الرواتب", "View payroll"),
    "payroll.manage": ("إدارة الموظفين والرواتب", "Manage employees and payroll"),
    "payroll.post": ("ترحيل الرواتب", "Post payroll"),
    "payroll.pay": ("صرف الرواتب", "Pay payroll"),
    "hr.contracts.manage": ("إدارة عقود الموظفين", "Manage employee contracts"),
    "hr.overtime.manage": ("إدارة طلبات العمل الإضافي", "Manage overtime requests"),
    "hr.overtime.approve": ("اعتماد العمل الإضافي", "Approve overtime"),
    "payroll.adjustments.manage": ("إعداد تعديلات الرواتب", "Prepare payroll adjustments"),
    "payroll.adjustments.review": ("مراجعة تعديلات الرواتب", "Review payroll adjustments"),
    "payroll.adjustments.approve": ("اعتماد تعديلات الرواتب", "Approve payroll adjustments"),
    "payroll.review": ("مراجعة مسير الرواتب", "Review payroll run"),
    "payroll.approve": ("اعتماد وترحيل مسير الرواتب", "Approve and post payroll run"),
    "payroll.wps": ("إدارة دفعات حماية الأجور", "Manage WPS batches"),
    "benefits.manage": ("إعداد تقييم منافع الموظفين", "Prepare employee-benefit valuation"),
    "benefits.review": ("مراجعة تقييم منافع الموظفين", "Review employee-benefit valuation"),
    "benefits.approve": ("اعتماد تقييم منافع الموظفين", "Approve employee-benefit valuation"),
    "pos.read": ("عرض نقاط البيع", "View POS"),
    "pos.manage": ("إدارة نقاط البيع", "Manage POS"),
    "pos.sell": ("تنفيذ مبيعات نقاط البيع", "Post POS sales"),
    "pos.settle": ("تسوية منصات التوصيل", "Settle delivery platforms"),
    "pos.tables.manage": ("إدارة طاولات المطعم", "Manage restaurant tables"),
    "pos.reservations.manage": ("إدارة حجوزات المطعم", "Manage restaurant reservations"),
    "pos.shifts.manage": ("إدارة ورديات الكاشير", "Manage cashier shifts"),
    "pos.shifts.approve": ("اعتماد إقفال ورديات الكاشير", "Approve cashier shift close"),
    "pos.kds.manage": ("إدارة شاشة المطبخ", "Manage kitchen display system"),
    "pos.controls.request": ("طلب إلغاء أو مرتجع نقطة البيع", "Request POS void or return"),
    "pos.controls.approve": ("اعتماد إلغاء أو مرتجع نقطة البيع", "Approve POS void or return"),
    "pos.settlements.manage": ("إعداد ومراجعة تسويات منصات التوصيل", "Prepare and review platform settlements"),
    "pos.settlements.approve": ("اعتماد تسويات منصات التوصيل", "Approve platform settlements"),
    "pos.waste.manage": ("إعداد سجلات هدر المطعم", "Prepare restaurant waste records"),
    "pos.waste.approve": ("اعتماد هدر المطعم", "Approve restaurant waste"),
    "pos.offline.sync": ("مزامنة مبيعات نقطة البيع دون اتصال", "Sync offline POS sales"),
    "attendance.read": ("عرض الحضور", "View attendance"),
    "attendance.manage": ("إدارة الورديات والحضور", "Manage shifts and attendance"),
    "attendance.capture": ("تسجيل الحضور والانصراف", "Capture attendance"),
    "attendance.override": ("تعديل الحضور يدويًا", "Override attendance"),
    "leave.read": ("عرض الإجازات", "View leave"),
    "leave.manage": ("إدارة طلبات الإجازة", "Manage leave requests"),
    "leave.approve": ("اعتماد الإجازات", "Approve leave"),
    "eos.manage": ("احتساب نهاية الخدمة", "Calculate end of service"),
    "eos.approve": ("اعتماد نهاية الخدمة", "Approve end of service"),
    "period.close": ("إقفال الفترات", "Close periods"),
    "year.close": ("إقفال السنة المالية", "Close fiscal year"),
    "compliance.read": ("عرض الالتزام والضرائب", "View compliance and tax"),
    "compliance.manage": ("إدارة الالتزام والفوترة الإلكترونية", "Manage compliance and e-invoicing"),
    "backup.manage": ("إدارة النسخ الاحتياطية", "Manage backups"),
    "data.reset": ("حذف بيانات العرض التجريبي", "Delete registered demo data"),
    "finance.manage_fx": ("إدارة العملات الأجنبية", "Manage foreign currency"),
    "consolidation.manage": ("إدارة التوحيد والمعاملات بين الشركات", "Manage consolidation and intercompany"),
    "grc.read": ("عرض المخاطر والضوابط والحوكمة", "View risk, controls and governance"),
    "grc.manage": ("إدارة المخاطر والضوابط والإجراءات التصحيحية", "Manage risks, controls and corrective actions"),
    "audit.manage": ("إدارة مهام وملاحظات المراجعة", "Manage audit engagements and findings"),
    "documents.manage": ("إدارة الوثائق والسياسات المضبوطة", "Manage controlled documents and policies"),
    "itsm.read": ("عرض الأصول التقنية وتذاكر الدعم", "View IT assets and service tickets"),
    "itsm.manage": ("إدارة الأصول التقنية وتذاكر الدعم", "Manage IT assets and service tickets"),
    "crm.read": ("عرض إدارة العملاء والتسويق", "View CRM and marketing"),
    "crm.manage": ("إدارة العملاء المحتملين والحملات والفرص", "Manage leads, campaigns and opportunities"),
    "assurance.read": ("عرض ملف التأكيد المالي والرقابي", "View financial assurance file"),
    "assurance.review": ("إعداد ومراجعة ملف التأكيد المالي", "Prepare and review financial assurance file"),
    "assurance.approve": ("اعتماد الإقرارات المالية والرقابية", "Approve financial and control certifications"),
}

ROLE_PERMISSION_MAP = {
    "SUPER_ADMIN": ["*"],
    "FINANCIAL_CONTROLLER": ["gym.facilities.approve", "gym.memberships.approve", "gym.commissions.review", "gym.transfers.approve", "manufacturing.cost.review", "manufacturing.read", "finance.corporate.read", "finance.corporate.manage", "finance.corporate.review", "finance.corporate.approve", "access.review", "audit.verify_integrity", "company.read", "masterdata.read", "journals.create", "journals.approve", "journals.post", "finance.read", "finance.arap.read", "finance.arap.allocate", "finance.arap.opening", "leases.modify.approve", "finance.reporting.manage", "finance.reporting.approve", "finance.disclosures.manage", "finance.disclosures.approve", "audit.read", "bank.reconcile", "budget.read", "inventory.read", "assets.read", "prepaids.read", "accruals.read", "recurring.read", "payroll.read", "payroll.review", "payroll.adjustments.review", "benefits.review", "pos.read", "pos.shifts.approve", "pos.controls.approve", "pos.settlements.manage", "pos.waste.approve", "period.close", "compliance.read", "grc.read", "assurance.read", "assurance.review", "assurance.approve"],
    "CFO": ["gym.facilities.approve", "gym.memberships.approve", "gym.commissions.approve", "gym.transfers.approve", "manufacturing.routing.approve", "manufacturing.plan.approve", "manufacturing.cost.approve", "manufacturing.read", "finance.corporate.read", "finance.corporate.manage", "finance.corporate.review", "finance.corporate.approve", "food_safety.read", "access.review", "access.approve", "quality.objectives", "quality.review", "audit.verify_integrity", "company.read", "masterdata.read", "journals.create", "journals.approve", "journals.post", "journals.reverse", "finance.read", "finance.arap.read", "finance.arap.allocate", "finance.arap.opening", "finance.reporting.manage", "finance.reporting.approve", "finance.disclosures.manage", "finance.disclosures.approve", "audit.read", "bank.reconcile", "budget.read", "budget.manage", "budget.approve", "inventory.read", "procurement.approve", "procurement.invoice", "revenue.recognize", "leases.manage", "leases.post", "leases.modify", "leases.modify.approve", "assets.read", "assets.manage", "assets.depreciate", "prepaids.read", "prepaids.manage", "prepaids.amortize", "accruals.read", "accruals.manage", "accruals.post", "accruals.reverse", "recurring.read", "recurring.manage", "recurring.run", "payroll.read", "payroll.manage", "payroll.post", "payroll.pay", "payroll.approve", "payroll.wps", "payroll.adjustments.approve", "benefits.approve", "pos.read", "pos.manage", "pos.sell", "pos.settle", "pos.tables.manage", "pos.reservations.manage", "pos.shifts.manage", "pos.shifts.approve", "pos.kds.manage", "pos.controls.request", "pos.controls.approve", "pos.settlements.manage", "pos.settlements.approve", "pos.waste.manage", "pos.waste.approve", "pos.offline.sync", "attendance.read", "attendance.manage", "attendance.capture", "attendance.override", "leave.read", "leave.manage", "leave.approve", "eos.manage", "eos.approve", "period.close", "year.close", "compliance.read", "compliance.manage", "backup.manage", "finance.manage_fx", "consolidation.manage", "grc.read", "grc.manage", "audit.manage", "documents.manage", "itsm.read", "assurance.read", "assurance.review", "assurance.approve"],
    "ACCOUNTANT": ["gym.commissions.review", "manufacturing.routing", "manufacturing.plan", "manufacturing.cost.prepare", "manufacturing.read", "finance.corporate.read", "finance.corporate.manage", "company.read", "masterdata.read", "journals.create", "finance.read", "finance.arap.read", "finance.arap.allocate", "finance.arap.opening", "finance.reporting.manage", "finance.disclosures.manage", "budget.read", "inventory.read", "procurement.manage", "inventory.receive", "inventory.issue", "leases.modify", "assets.read", "prepaids.read", "prepaids.manage", "prepaids.amortize", "accruals.read", "accruals.manage", "accruals.post", "accruals.reverse", "recurring.read", "recurring.manage", "recurring.run", "payroll.read", "payroll.adjustments.manage", "benefits.manage", "pos.read", "pos.sell", "pos.controls.request", "pos.settlements.manage", "pos.waste.manage", "pos.offline.sync", "attendance.read", "attendance.capture", "leave.read", "leave.manage", "eos.manage", "compliance.read", "finance.manage_fx", "grc.read", "itsm.read", "crm.read", "assurance.read", "assurance.review"],
    "AUDITOR": ["gym.commissions.review", "manufacturing.cost.review", "finance.corporate.read", "finance.corporate.review", "finance.corporate.approve", "food_safety.read", "food_safety.approve", "access.review", "access.approve", "quality.review", "audit.verify_integrity", "company.read", "masterdata.read", "finance.read", "finance.arap.read", "leases.modify.approve", "finance.reporting.approve", "finance.disclosures.approve", "audit.read", "budget.read", "inventory.read", "gym.read", "manufacturing.read", "quality.read", "assets.read", "prepaids.read", "accruals.read", "recurring.read", "payroll.read", "benefits.review", "pos.read", "pos.settlements.manage", "attendance.read", "leave.read", "compliance.read", "grc.read", "grc.manage", "audit.manage", "documents.manage", "itsm.read", "assurance.read", "assurance.approve"],
    "IT_MANAGER": ["access.review", "access.manage", "company.read", "masterdata.read", "audit.read", "itsm.read", "itsm.manage", "documents.manage"],
    "QUALITY_MANAGER": ["food_safety.read", "food_safety.manage", "food_safety.approve", "company.read", "masterdata.read", "quality.read", "quality.manage", "quality.objectives", "quality.plans", "quality.capa", "quality.complaints", "quality.suppliers", "quality.review", "audit.verify_integrity", "grc.read", "grc.manage", "documents.manage", "itsm.read"],
    "HR_MANAGER": ["company.read", "masterdata.read", "payroll.read", "payroll.manage", "payroll.review", "attendance.read", "attendance.manage", "attendance.capture", "attendance.override", "leave.read", "leave.manage", "leave.approve", "eos.manage", "hr.contracts.manage", "hr.overtime.manage", "hr.overtime.approve", "payroll.adjustments.manage", "payroll.adjustments.review", "benefits.manage", "benefits.review", "audit.read"],
    "SALES_MANAGER": ["company.read", "masterdata.read", "inventory.read", "pos.read", "pos.tables.manage", "pos.reservations.manage", "pos.kds.manage", "crm.read", "crm.manage"],
    "RESTAURANT_MANAGER": ["company.read", "masterdata.read", "inventory.read", "pos.read", "pos.manage", "pos.sell", "pos.settle", "pos.tables.manage", "pos.reservations.manage", "pos.shifts.manage", "pos.kds.manage", "pos.controls.request", "pos.settlements.manage", "pos.waste.manage", "pos.offline.sync", "audit.read"],
    "GYM_MANAGER": ["company.read", "masterdata.read", "gym.read", "gym.manage", "gym.departments.manage", "gym.facilities.manage", "gym.cafe.manage", "pos.read", "pos.manage", "pos.sell", "gym.memberships.manage", "gym.classes.manage", "gym.bookings.manage", "gym.pt.manage", "gym.pt.complete", "gym.commissions.review", "gym.access.capture", "gym.lockers.manage", "gym.transfers.manage", "audit.read"],
    "GYM_TRAINER": ["company.read", "gym.read", "gym.bookings.manage", "gym.pt.complete", "gym.access.capture"],
    "GYM_CAFE_CASHIER": ["company.read", "masterdata.read", "gym.read", "pos.read", "pos.sell"],
    "GYM_FACILITY_SUPERVISOR": ["company.read", "gym.read", "gym.facilities.manage", "gym.bookings.manage", "gym.access.capture"],
    "PRODUCTION_MANAGER": ["company.read", "masterdata.read", "inventory.read", "inventory.issue", "manufacturing.read", "manufacturing.manage", "manufacturing.issue", "manufacturing.complete", "manufacturing.routing", "manufacturing.plan", "manufacturing.scrap", "manufacturing.cost.prepare", "quality.read", "quality.manage", "food_safety.read"],
}

ROLE_PERMISSION_MAP["ACCOUNTANT"] = [
    "bank.statement.prepare",
    *ROLE_PERMISSION_MAP["ACCOUNTANT"],
]

# R7 employee simulation: people who maintain customers/suppliers need a
# narrowly scoped master-data write permission, while quality staff must be
# able to select inventory items in inspections and NCRs.  Previously both
# screens were present but unusable for the intended roles.
for _masterdata_role in ("ACCOUNTANT", "SALES_MANAGER", "CFO"):
    ROLE_PERMISSION_MAP[_masterdata_role] = [
        "masterdata.manage",
        *ROLE_PERMISSION_MAP[_masterdata_role],
    ]
ROLE_PERMISSION_MAP["QUALITY_MANAGER"] = [
    "inventory.read",
    *ROLE_PERMISSION_MAP["QUALITY_MANAGER"],
]

# Unified reporting permissions are explicit and remain separate from the
# underlying finance/inventory permissions used by the source engines.
for _report_role in ("FINANCIAL_CONTROLLER", "CFO"):
    ROLE_PERMISSION_MAP[_report_role] = [
        "reports.read",
        "reports.export",
        "reports.tax.configure",
        *ROLE_PERMISSION_MAP[_report_role],
    ]
for _report_role in ("ACCOUNTANT", "AUDITOR"):
    ROLE_PERMISSION_MAP[_report_role] = [
        "reports.read",
        "reports.export",
        *ROLE_PERMISSION_MAP[_report_role],
    ]

COMPANIES = [
    (1, "HOLD", "المجموعة القابضة", "Holding Group", "HOLDING", "#3157D5"),
    (2, "GYM", "جيم ماستر", "Gym Master", "GYM", "#6D5DFC"),
    (3, "REST", "مجموعة المطاعم", "Restaurant Group", "RESTAURANT", "#C97845"),
    (4, "MFG", "شركة التصنيع", "Manufacturing Company", "MANUFACTURING", "#238B7E"),
]

COA = [
    ("100000", "الأصول", "Assets", "ASSET", "ASSETS", None, 1, False, False),
    ("110000", "الأصول المتداولة", "Current Assets", "ASSET", "CURRENT_ASSETS", "100000", 2, False, False),
    ("111010", "البنك الرئيسي", "Main Bank", "ASSET", "CASH", "110000", 3, True, True),
    ("112010", "العملاء", "Trade Receivables", "ASSET", "RECEIVABLES", "110000", 3, True, False),
    ("113010", "المخزون", "Inventory", "ASSET", "INVENTORY", "110000", 3, True, False),
    ("114010", "ضريبة قيمة مضافة قابلة للاسترداد", "VAT Recoverable", "ASSET", "VAT_RECOVERABLE", "110000", 3, True, False),
    ("119010", "حساب تسوية التكاليف الواصلة", "Landed Cost Clearing", "ASSET", "OTHER_CURRENT_ASSET", "110000", 3, True, False),
    ("119020", "أصول محتفظ بها للبيع", "Assets Held for Sale", "ASSET", "CURRENT_ASSETS", "110000", 3, True, False),
    ("113020", "مخصص انخفاض قيمة المخزون", "Inventory Write-down Provision", "ASSET", "INVENTORY", "110000", 3, True, False),
    ("117010", "المصروفات المدفوعة مقدمًا", "Prepaid Expenses", "ASSET", "PREPAID_EXPENSES", "110000", 3, True, False),
    ("118010", "إيرادات مستحقة", "Accrued Revenue", "ASSET", "ACCRUED_REVENUE", "110000", 3, True, False),
    ("150000", "الأصول غير المتداولة", "Non-current Assets", "ASSET", "NON_CURRENT_ASSETS", "100000", 2, False, False),
    ("151010", "الممتلكات والمعدات", "Property and Equipment", "ASSET", "PPE", "150000", 3, True, False),
    ("200000", "الالتزامات", "Liabilities", "LIABILITY", "LIABILITIES", None, 1, False, False),
    ("210000", "الالتزامات المتداولة", "Current Liabilities", "LIABILITY", "CURRENT_LIABILITIES", "200000", 2, False, False),
    ("211010", "الموردون", "Trade Payables", "LIABILITY", "PAYABLES", "210000", 3, True, False),
    ("212010", "ضريبة القيمة المضافة", "VAT Payable", "LIABILITY", "VAT", "210000", 3, True, False),
    ("212020", "حساب تسوية ضريبة الاستيراد", "Import VAT Clearing", "LIABILITY", "VAT", "210000", 3, True, False),
    ("213010", "إيراد مقدم / التزام عقود", "Deferred Revenue / Contract Liability", "LIABILITY", "CONTRACT_LIABILITY", "210000", 3, True, False),
    ("213020", "أرصدة دائنة للأعضاء", "Member Credit Liability", "LIABILITY", "CONTRACT_LIABILITY", "210000", 3, True, False),
    ("217010", "مصروفات مستحقة", "Accrued Expenses", "LIABILITY", "ACCRUED_EXPENSES", "210000", 3, True, False),
    ("217020", "عمولات مدربين مستحقة", "Trainer Commissions Payable", "LIABILITY", "ACCRUED_EXPENSES", "210000", 3, True, False),
    ("218010", "ضريبة استقطاع مستحقة", "Withholding Tax Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("218030", "زكاة مستحقة", "Zakat Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("218040", "ضريبة دخل مستحقة", "Corporate Income Tax Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("118020", "دفعات زكاة وضريبة مقدمة", "Zakat and Tax Prepayments", "ASSET", "OTHER_CURRENT_ASSETS", "110000", 3, True, False),
    ("220000", "الالتزامات غير المتداولة", "Non-current Liabilities", "LIABILITY", "NON_CURRENT_LIABILITIES", "200000", 2, False, False),
    ("221010", "قرض طويل الأجل", "Long-term Loan", "LIABILITY", "BORROWINGS", "220000", 3, True, False),
    ("300000", "حقوق الملكية", "Equity", "EQUITY", "EQUITY", None, 1, False, False),
    ("311010", "رأس المال", "Share Capital", "EQUITY", "CAPITAL", "300000", 2, True, False),
    ("312010", "الأرباح المبقاة", "Retained Earnings", "EQUITY", "RETAINED_EARNINGS", "300000", 2, True, False),
    ("400000", "الإيرادات", "Revenue", "REVENUE", "REVENUE", None, 1, False, False),
    ("411010", "إيراد التشغيل", "Operating Revenue", "REVENUE", "OPERATING_REVENUE", "400000", 2, True, False),
    ("421010", "أرباح إنهاء وتعديل عقود الإيجار", "Lease Termination and Modification Gains", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("424010", "أرباح فروق جرد المخزون", "Inventory Count Gains", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("424020", "أرباح مرتجعات المشتريات", "Purchase Return Cost Gains", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("425010", "أرباح بيع واستبعاد الأصول", "Gain on Disposal of PPE", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("426010", "عكس خسائر انخفاض الأصول", "Reversal of Asset Impairment", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("422010", "أرباح إعادة قياس المقابل المحتمل", "Contingent Consideration Remeasurement Gains", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("423010", "أرباح التخلص من عملية أجنبية", "Gain on Disposal of Foreign Operation", "REVENUE", "OTHER_INCOME", "400000", 2, True, False),
    ("500000", "تكلفة الإيرادات", "Cost of Revenue", "EXPENSE", "COST_OF_REVENUE", None, 1, False, False),
    ("511010", "تكلفة المبيعات", "Cost of Sales", "EXPENSE", "COST_OF_REVENUE", "500000", 2, True, False),
    ("600000", "المصروفات التشغيلية", "Operating Expenses", "EXPENSE", "OPERATING_EXPENSES", None, 1, False, False),
    ("611010", "الرواتب والأجور", "Salaries and Wages", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("612010", "الإيجارات", "Rent Expense", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("613010", "المرافق والخدمات", "Utilities", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("624010", "انحراف سعر المواد", "Material Price Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624020", "انحراف استخدام المواد", "Material Usage Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624030", "انحراف معدل العمل", "Labor Rate Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624040", "انحراف كفاءة العمل", "Labor Efficiency Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624050", "انحراف الإنفاق الصناعي", "Overhead Spending Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624060", "انحراف حجم الإنتاج", "Overhead Volume Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624070", "تكلفة الهالك غير الطبيعي", "Abnormal Scrap Cost", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624080", "فرق إقفال تكلفة الإنتاج", "Production Cost Close Residual", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624090", "خسائر فروق جرد المخزون", "Inventory Count Losses", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624100", "خسائر انخفاض وركود وتلف المخزون", "Inventory Obsolescence and NRV Losses", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624110", "خسائر تكاليف مرتجعات المشتريات", "Purchase Return Unrecovered Costs", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624120", "انحراف مزيج المواد", "Material Mix Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624130", "انحراف عائد المواد", "Material Yield Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624140", "انحراف كفاءة التكاليف الصناعية المتغيرة", "Variable Overhead Efficiency Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624150", "انحراف موازنة التكاليف الصناعية الثابتة", "Fixed Overhead Budget Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624160", "تكلفة الطاقة العاطلة", "Idle Capacity Cost", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624170", "تكلفة إعادة التشغيل", "Rework Cost", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("624180", "انحراف توزيع أقسام الخدمات", "Service Department Allocation Variance", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("700000", "تكاليف التمويل", "Finance Costs", "EXPENSE", "FINANCE_COSTS", None, 1, False, False),
    ("711010", "مصروف الفوائد", "Interest Expense", "EXPENSE", "FINANCE_COSTS", "700000", 2, True, False),
    ("800000", "الزكاة والضرائب", "Zakat and Tax", "EXPENSE", "ZAKAT_TAX", None, 1, False, False),
    ("811010", "مصروف الزكاة والضريبة", "Zakat and Tax Expense", "EXPENSE", "ZAKAT_TAX", "800000", 2, True, False),
    ("811020", "مصروف ضريبة الدخل الحالية", "Current Income Tax Expense", "EXPENSE", "ZAKAT_TAX", "800000", 2, True, False),
    ("115010", "الإنتاج تحت التشغيل", "Work in Progress", "ASSET", "INVENTORY", "110000", 3, True, False),
    ("152010", "أصول حق الاستخدام", "Right-of-use Assets", "ASSET", "PPE", "150000", 3, True, False),
    ("152020", "مجمع إهلاك أصول حق الاستخدام", "Accumulated Depreciation - ROU", "ASSET", "ACCUMULATED_DEPRECIATION", "150000", 3, True, False),
    ("214010", "استلامات غير مفوترة", "Goods Received Not Invoiced", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("222010", "التزامات عقود الإيجار", "Lease Liabilities", "LIABILITY", "NON_CURRENT_LIABILITIES", "220000", 3, True, False),
    ("412010", "إيراد عضويات النادي", "Gym Membership Revenue", "REVENUE", "OPERATING_REVENUE", "400000", 2, True, False),
    ("412020", "إيراد التدريب الشخصي", "Personal Training Revenue", "REVENUE", "OPERATING_REVENUE", "400000", 2, True, False),
    ("614010", "إهلاك أصول حق الاستخدام", "ROU Depreciation Expense", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("615010", "تكاليف صناعية محملة", "Manufacturing Overhead Absorbed", "EXPENSE", "COST_OF_REVENUE", "600000", 2, True, False),
    ("116010", "ذمم منصات التوصيل", "Delivery Platform Receivables", "ASSET", "RECEIVABLES", "110000", 3, True, False),
    ("153010", "مجمع إهلاك الممتلكات والمعدات", "Accumulated Depreciation - PPE", "ASSET", "ACCUMULATED_DEPRECIATION", "150000", 3, True, False),
    ("215010", "رواتب مستحقة", "Payroll Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("215020", "تأمينات اجتماعية مستحقة", "GOSI Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("215030", "استقطاعات رواتب مستحقة", "Payroll Deductions Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("616010", "عمولات منصات التوصيل", "Delivery Platform Commissions", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("617010", "مصروف إهلاك الممتلكات والمعدات", "PPE Depreciation Expense", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("618010", "مساهمة صاحب العمل في التأمينات", "Employer Social Insurance Expense", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("619010", "مصروف مكافأة نهاية الخدمة", "End-of-Service Benefit Expense", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("216010", "مكافأة نهاية الخدمة المستحقة", "End-of-Service Benefit Payable", "LIABILITY", "CURRENT_LIABILITIES", "210000", 3, True, False),
    ("154010", "أصل ضريبة مؤجلة", "Deferred Tax Asset", "ASSET", "NON_CURRENT_ASSETS", "150000", 3, True, False),
    ("154020", "الشهرة", "Goodwill", "ASSET", "NON_CURRENT_ASSETS", "150000", 3, True, False),
    ("154030", "مجمع خسائر انخفاض القيمة", "Accumulated Impairment Losses", "ASSET", "ACCUMULATED_DEPRECIATION", "150000", 3, True, False),
    ("223010", "التزام ضريبة مؤجلة", "Deferred Tax Liability", "LIABILITY", "NON_CURRENT_LIABILITIES", "220000", 3, True, False),
    ("224010", "التزام المقابل المحتمل", "Contingent Consideration Liability", "LIABILITY", "NON_CURRENT_LIABILITIES", "220000", 3, True, False),
    ("313010", "احتياطي فروق ترجمة العملات", "Foreign Currency Translation Reserve", "EQUITY", "EQUITY", "300000", 2, True, False),
    ("313020", "الأثر الضريبي لبنود الدخل الشامل الآخر", "Tax Effects in Other Comprehensive Income", "EQUITY", "EQUITY", "300000", 2, True, False),
    ("314010", "حقوق غير المسيطرين", "Non-controlling Interests", "EQUITY", "EQUITY", "300000", 2, True, False),
    ("620010", "خسائر انخفاض القيمة", "Impairment Losses", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("621010", "خسائر إنهاء وتعديل عقود الإيجار", "Lease Termination and Modification Losses", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("622010", "خسائر إعادة قياس المقابل المحتمل", "Contingent Consideration Remeasurement Losses", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("623010", "خسائر التخلص من عملية أجنبية", "Loss on Disposal of Foreign Operation", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("625010", "عمولات المدربين", "Trainer Commission Expense", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("626010", "خسائر بيع واستبعاد الأصول", "Loss on Disposal of PPE", "EXPENSE", "OPERATING_EXPENSES", "600000", 2, True, False),
    ("812010", "مصروف الضريبة المؤجلة", "Deferred Tax Expense", "EXPENSE", "ZAKAT_TAX", "800000", 2, True, False),
]


def _create_journal(
    db: Session,
    company_id: int,
    user_id: int,
    number: str,
    entry_date: date,
    reference: str,
    description: str,
    lines: list[tuple[str, Decimal, Decimal]],
    activity: str | None = None,
    kind: str | None = None,
) -> None:
    accounts = {a.code: a for a in db.scalars(select(Account).where(Account.company_id == company_id)).all()}
    total_debit = sum((line[1] for line in lines), Decimal("0"))
    total_credit = sum((line[2] for line in lines), Decimal("0"))
    entry = JournalEntry(
        company_id=company_id,
        number=number,
        entry_date=entry_date,
        reference=reference,
        description=description,
        status="POSTED",
        cash_flow_activity=activity,
        cash_flow_kind=kind,
        total_debit=total_debit,
        total_credit=total_credit,
        created_by=user_id,
        approved_by=user_id,
        posted_by=user_id,
        created_at=utc_now(),
        submitted_at=utc_now(),
        approved_at=utc_now(),
        posted_at=utc_now(),
    )
    for code, debit, credit in lines:
        entry.lines.append(
            JournalLine(account_id=accounts[code].id, description=description, debit=debit, credit=credit)
        )
    db.add(entry)
    db.flush()
    _register_demo_record(db, company_id, "journal_entries", entry.id)
    for line in entry.lines:
        _register_demo_record(db, company_id, "journal_lines", line.id)


def _register_demo_record(
    db: Session,
    company_id: int,
    table_name: str,
    record_id: int,
) -> None:
    """Mark a record created by the trusted system seeder as demonstrational."""
    record_key = str(record_id)
    exists = db.scalar(
        select(DemoDataRecord.id).where(
            DemoDataRecord.company_id == company_id,
            DemoDataRecord.table_name == table_name,
            DemoDataRecord.record_id == record_key,
        )
    )
    if not exists:
        db.add(
            DemoDataRecord(
                company_id=company_id,
                table_name=table_name,
                record_id=record_key,
                source="SYSTEM_SEED",
            )
        )


# Exact fingerprint of the ten GL journals created by historical CORVAX demo
# seeders.  The upgrade path registers only an unchanged match.  A row edited by
# a person is intentionally left unregistered and therefore cannot be purged.
_SEEDED_JOURNAL_FINGERPRINTS = {
    "0001": (date(2026, 1, 1), "OPENING", "Opening capital", Decimal("2000000"), 2),
    "0002": (date(2026, 7, 2), "INV-001", "Sales invoice", Decimal("575000"), 3),
    "0003": (date(2026, 7, 4), "RCPT-001", "Customer receipt", Decimal("575000"), 2),
    "0004": (date(2026, 7, 5), "PUR-001", "Inventory purchased on credit", Decimal("300000"), 2),
    "0005": (date(2026, 7, 6), "COGS-001", "Cost of sales", Decimal("220000"), 2),
    "0006": (date(2026, 7, 7), "PAY-EMP", "Employee payments", Decimal("200000"), 2),
    "0007": (date(2026, 7, 8), "RENT-001", "Rent paid", Decimal("80000"), 2),
    "0008": (date(2026, 7, 9), "PPE-001", "Equipment purchase", Decimal("300000"), 2),
    "0009": (date(2026, 7, 10), "LOAN-001", "Loan proceeds", Decimal("500000"), 2),
    "0010": (date(2026, 7, 11), "SUP-PAY", "Supplier payment", Decimal("100000"), 2),
}


def _register_unchanged_historical_demo_journals(db: Session) -> None:
    """Backfill explicit markers for old databases without guessing.

    Matching all stable seeded attributes prevents a user-created or edited
    journal from becoming deletable merely because its number resembles a demo
    number.
    """
    for company in db.scalars(select(Company).order_by(Company.id)).all():
        for suffix, fingerprint in _SEEDED_JOURNAL_FINGERPRINTS.items():
            entry_date, reference, description, total, line_count = fingerprint
            number = f"JV-{company.id}-2026-{suffix}"
            entry = db.scalar(
                select(JournalEntry).where(
                    JournalEntry.company_id == company.id,
                    JournalEntry.number == number,
                    JournalEntry.entry_date == entry_date,
                    JournalEntry.reference == reference,
                    JournalEntry.description == description,
                    JournalEntry.status == "POSTED",
                    JournalEntry.total_debit == total,
                    JournalEntry.total_credit == total,
                )
            )
            if not entry or len(entry.lines) != line_count:
                continue
            _register_demo_record(db, company.id, "journal_entries", entry.id)
            for line in entry.lines:
                _register_demo_record(db, company.id, "journal_lines", line.id)


def _register_unchanged_historical_demo_stock_movements(db: Session) -> None:
    """Register only the two unchanged opening movements from older seeders."""
    admin = db.scalar(
        select(User).where(User.email == "admin@corvaxplatform.com")
    )
    if not admin:
        return
    fingerprints = (
        ("RAW-001", Decimal("6000"), Decimal("10"), Decimal("60000")),
        ("PACK-001", Decimal("10000"), Decimal("2"), Decimal("20000")),
    )
    for company in db.scalars(select(Company).order_by(Company.id)).all():
        warehouse = db.scalar(
            select(Warehouse).where(
                Warehouse.company_id == company.id,
                Warehouse.code == "MAIN",
            )
        )
        if not warehouse:
            continue
        for item_code, quantity, unit_cost, total_cost in fingerprints:
            item = db.scalar(
                select(Item).where(
                    Item.company_id == company.id,
                    Item.code == item_code,
                )
            )
            if not item:
                continue
            rows = db.scalars(
                select(StockMovement).where(
                    StockMovement.company_id == company.id,
                    StockMovement.warehouse_id == warehouse.id,
                    StockMovement.item_id == item.id,
                    StockMovement.movement_date == date(2026, 7, 4),
                    StockMovement.movement_type == "OPENING",
                    StockMovement.quantity == quantity,
                    StockMovement.unit_cost == unit_cost,
                    StockMovement.total_cost == total_cost,
                    StockMovement.reference_type == "OPENING_BALANCE",
                    StockMovement.reference_id.is_(None),
                    StockMovement.journal_id.is_(None),
                    StockMovement.lot_number.is_(None),
                    StockMovement.expiry_date.is_(None),
                    StockMovement.inbound_shipment_id.is_(None),
                    StockMovement.created_by == admin.id,
                )
            ).all()
            if len(rows) == 1:
                _register_demo_record(
                    db,
                    company.id,
                    "stock_movements",
                    rows[0].id,
                )



def _ensure_operational_masters(db: Session, admin: User) -> None:
    for company in db.scalars(select(Company).order_by(Company.id)).all():
        accounts = {a.code: a for a in db.scalars(select(Account).where(Account.company_id == company.id)).all()}
        branch = db.scalar(select(Branch).where(Branch.company_id == company.id).order_by(Branch.id))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.company_id == company.id, Warehouse.code == "MAIN"))
        if not warehouse:
            warehouse = Warehouse(
                company_id=company.id,
                branch_id=branch.id if branch else None,
                code="MAIN",
                name_ar="المستودع الرئيسي",
                name_en="Main Warehouse",
                # Use the canonical vocabulary (inventory.py::WAREHOUSE_TYPES).
                # GENERAL was the old spelling of MAIN and left fresh databases
                # holding a value the write guard now rejects.
                warehouse_type="RAW_AND_FINISHED" if company.company_type == "MANUFACTURING" else "MAIN",
                active=True,
            )
            db.add(warehouse)
            db.flush()

        item_specs = [
            ("RAW-001", "مادة خام رئيسية", "Primary Raw Material", "RAW_MATERIAL", "KG", Decimal("10"), Decimal("500")),
            ("PACK-001", "مواد تعبئة", "Packaging Material", "PACKAGING", "EA", Decimal("2"), Decimal("1000")),
            ("FG-001", "منتج تام", "Finished Product", "FINISHED_GOOD", "EA", Decimal("25"), Decimal("100")),
        ]
        items: dict[str, Item] = {}
        for code, ar, en, item_type, uom, standard_cost, reorder in item_specs:
            item = db.scalar(select(Item).where(Item.company_id == company.id, Item.code == code))
            if not item:
                item = Item(
                    company_id=company.id,
                    code=code,
                    name_ar=ar,
                    name_en=en,
                    item_type=item_type,
                    uom=uom,
                    valuation_method="WEIGHTED_AVERAGE",
                    standard_cost=standard_cost,
                    reorder_level=reorder,
                    inventory_account_id=accounts["113010"].id,
                    cogs_account_id=accounts["511010"].id,
                    revenue_account_id=accounts["411010"].id,
                    active=True,
                )
                db.add(item)
                db.flush()
            items[code] = item

        if not db.scalar(select(func.count(StockMovement.id)).where(StockMovement.company_id == company.id)):
            demo_movements = [
                StockMovement(company_id=company.id, warehouse_id=warehouse.id, item_id=items["RAW-001"].id, movement_date=date(2026, 7, 4), movement_type="OPENING", quantity=Decimal("6000"), unit_cost=Decimal("10"), total_cost=Decimal("60000"), reference_type="OPENING_BALANCE", created_by=admin.id),
                StockMovement(company_id=company.id, warehouse_id=warehouse.id, item_id=items["PACK-001"].id, movement_date=date(2026, 7, 4), movement_type="OPENING", quantity=Decimal("10000"), unit_cost=Decimal("2"), total_cost=Decimal("20000"), reference_type="OPENING_BALANCE", created_by=admin.id),
            ]
            db.add_all(demo_movements)
            db.flush()
            for movement in demo_movements:
                _register_demo_record(
                    db,
                    company.id,
                    "stock_movements",
                    movement.id,
                )

        fy = db.scalar(select(FiscalYear).where(FiscalYear.company_id == company.id, FiscalYear.name == "FY 2026"))
        if fy and not db.scalar(select(Budget).where(Budget.company_id == company.id, Budget.name == "Operating Budget 2026")):
            budget = Budget(company_id=company.id, fiscal_year_id=fy.id, name="Operating Budget 2026", version=1, status="APPROVED", created_by=admin.id, approved_by=admin.id)
            for period in range(1, 13):
                budget.lines.extend([
                    BudgetLine(account_id=accounts["611010"].id, period_number=period, amount=Decimal("300000")),
                    BudgetLine(account_id=accounts["612010"].id, period_number=period, amount=Decimal("100000")),
                    BudgetLine(account_id=accounts["613010"].id, period_number=period, amount=Decimal("75000")),
                ])
            db.add(budget)

        if company.company_type == "GYM":
            if not db.scalar(select(Member).where(Member.company_id == company.id, Member.member_number == "M-0001")):
                db.add(Member(company_id=company.id, member_number="M-0001", name_ar="عضو تجريبي", name_en="Demo Member", mobile="0500000000", active=True))
            plan = db.scalar(select(MembershipPlan).where(MembershipPlan.company_id == company.id, MembershipPlan.code == "ANNUAL"))
            if not plan:
                plan = MembershipPlan(company_id=company.id, code="ANNUAL", name_ar="عضوية سنوية", name_en="Annual Membership", duration_months=12, net_price=Decimal("1200"), vat_rate=Decimal("15"), active=True)
                db.add(plan); db.flush()
            gym_cost_centers = {}
            for code, ar, en in [
                ("GYM-SWIM", "قسم السباحة", "Swimming Department"),
                ("GYM-STRENGTH", "قسم ألعاب القوة", "Strength Department"),
                ("GYM-PADEL", "قسم البادل", "Padel Department"),
                ("GYM-CAFE", "كوفي شوب النادي", "Gym Cafe"),
            ]:
                cc = db.scalar(select(CostCenter).where(CostCenter.company_id == company.id, CostCenter.code == code))
                if not cc:
                    cc = CostCenter(company_id=company.id, code=code, name_ar=ar, name_en=en, active=True); db.add(cc); db.flush()
                gym_cost_centers[code] = cc
            department_specs = [
                ("SWIM", "السباحة", "Swimming", "SWIMMING", "GYM-SWIM", 80, True),
                ("STRENGTH", "ألعاب القوة", "Strength", "STRENGTH", "GYM-STRENGTH", 150, False),
                ("PADEL", "البادل", "Padel", "PADEL", "GYM-PADEL", 24, True),
                ("CAFE", "كوفي شوب النادي", "Gym Cafe", "CAFE", "GYM-CAFE", 40, False),
            ]
            departments = {}
            for code, ar, en, dtype, cc_code, capacity, booking_required in department_specs:
                dept = db.scalar(select(GymDepartment).where(GymDepartment.company_id == company.id, GymDepartment.branch_id == branch.id, GymDepartment.code == code))
                if not dept:
                    dept = GymDepartment(company_id=company.id, branch_id=branch.id, code=code, name_ar=ar, name_en=en, department_type=dtype, cost_center_id=gym_cost_centers[cc_code].id, revenue_account_id=accounts["411010"].id, capacity=capacity, booking_required=booking_required, active=True, created_by=admin.id)
                    db.add(dept); db.flush()
                departments[code] = dept
            for dept_code, mode, limit, days in [("SWIM", "INCLUDED", 12, 14), ("STRENGTH", "INCLUDED", None, 0), ("PADEL", "PAY_PER_USE", None, 14)]:
                if not db.scalar(select(GymDepartmentPlanAccess).where(GymDepartmentPlanAccess.plan_id == plan.id, GymDepartmentPlanAccess.department_id == departments[dept_code].id)):
                    db.add(GymDepartmentPlanAccess(company_id=company.id, plan_id=plan.id, department_id=departments[dept_code].id, access_mode=mode, monthly_visit_limit=limit, advance_booking_days=days, guest_allowed=dept_code == "PADEL", active=True, created_by=admin.id))
            facility_specs = [
                (departments["SWIM"], "POOL-L1", "حارة سباحة 1", "Swimming Lane 1", "LANE", 6, 60, Decimal("50")),
                (departments["PADEL"], "PADEL-C1", "ملعب بادل 1", "Padel Court 1", "PADEL_COURT", 4, 90, Decimal("160")),
                (departments["STRENGTH"], "STRENGTH-Z1", "منطقة القوة الرئيسية", "Main Strength Zone", "ZONE", 100, 60, Decimal("0")),
            ]
            for dept, code, ar, en, ftype, capacity, slot, rate in facility_specs:
                if not db.scalar(select(GymFacility).where(GymFacility.department_id == dept.id, GymFacility.code == code)):
                    db.add(GymFacility(company_id=company.id, department_id=dept.id, code=code, name_ar=ar, name_en=en, facility_type=ftype, capacity=capacity, slot_minutes=slot, hourly_rate=rate, vat_rate=Decimal("15"), status="AVAILABLE", active=True, created_by=admin.id))
            cafe_wc = db.scalar(select(WorkCenter).where(WorkCenter.company_id == company.id, WorkCenter.code == "GYM-CAFE-01"))
            if not cafe_wc:
                cafe_wc = WorkCenter(company_id=company.id, code="GYM-CAFE-01", name_ar="تحضير كوفي شوب النادي", name_en="Gym Cafe Preparation", hourly_labor_rate=Decimal("45"), hourly_overhead_rate=Decimal("20"), active=True); db.add(cafe_wc); db.flush()
            cafe_recipe = db.scalar(select(BillOfMaterial).where(BillOfMaterial.company_id == company.id, BillOfMaterial.code == "RECIPE-GYM-COFFEE", BillOfMaterial.version == 1))
            if not cafe_recipe:
                cafe_recipe = BillOfMaterial(company_id=company.id, code="RECIPE-GYM-COFFEE", version=1, finished_item_id=items["FG-001"].id, output_quantity=Decimal("1"), work_center_id=cafe_wc.id, standard_hours=Decimal("0.03"), status="ACTIVE")
                cafe_recipe.lines.extend([BillOfMaterialLine(component_item_id=items["RAW-001"].id, quantity=Decimal("0.08"), scrap_percent=Decimal("2")), BillOfMaterialLine(component_item_id=items["PACK-001"].id, quantity=Decimal("1"), scrap_percent=Decimal("0"))]); db.add(cafe_recipe); db.flush()
            coffee = db.scalar(select(MenuItem).where(MenuItem.company_id == company.id, MenuItem.code == "GYM-COFFEE-001"))
            if not coffee:
                coffee = MenuItem(company_id=company.id, code="GYM-COFFEE-001", name_ar="قهوة النادي", name_en="Gym Coffee", inventory_item_id=items["FG-001"].id, recipe_bom_id=cafe_recipe.id, selling_price=Decimal("18"), vat_rate=Decimal("15"), active=True); db.add(coffee); db.flush()
            healthy = db.scalar(select(MenuItem).where(MenuItem.company_id == company.id, MenuItem.code == "GYM-HEALTHY-001"))
            if not healthy:
                healthy = MenuItem(company_id=company.id, code="GYM-HEALTHY-001", name_ar="وجبة بروتين صحية", name_en="Healthy Protein Meal", inventory_item_id=items["FG-001"].id, recipe_bom_id=cafe_recipe.id, selling_price=Decimal("32"), vat_rate=Decimal("15"), active=True); db.add(healthy); db.flush()
            cafe_profiles = [
                (coffee, "COFFEE", "BEVERAGE", Decimal("15"), Decimal("80"), Decimal("2"), Decimal("10"), Decimal("2"), Decimal("6"), Decimal("90"), "Milk"),
                (healthy, "HEALTHY_MEAL", "PREPARED", Decimal("28"), Decimal("420"), Decimal("35"), Decimal("38"), Decimal("12"), Decimal("5"), None, "Milk, nuts"),
            ]
            for menu, category, ptype, member_price, calories, protein, carbs, fat, sugar, caffeine, allergens in cafe_profiles:
                if not db.scalar(select(GymCafeProductProfile).where(GymCafeProductProfile.company_id == company.id, GymCafeProductProfile.branch_id == branch.id, GymCafeProductProfile.menu_item_id == menu.id)):
                    db.add(GymCafeProductProfile(company_id=company.id, branch_id=branch.id, department_id=departments["CAFE"].id, menu_item_id=menu.id, category=category, product_type=ptype, member_price=member_price, calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat, sugar_g=sugar, caffeine_mg=caffeine, allergens=allergens, is_healthy=True, active=True, created_by=admin.id))

        if company.company_type == "MANUFACTURING":
            work_center = db.scalar(select(WorkCenter).where(WorkCenter.company_id == company.id, WorkCenter.code == "LINE-01"))
            if not work_center:
                work_center = WorkCenter(company_id=company.id, code="LINE-01", name_ar="خط الإنتاج الأول", name_en="Production Line 01", hourly_labor_rate=Decimal("120"), hourly_overhead_rate=Decimal("80"), active=True)
                db.add(work_center)
                db.flush()
            if not db.scalar(select(BillOfMaterial).where(BillOfMaterial.company_id == company.id, BillOfMaterial.code == "BOM-FG-001", BillOfMaterial.version == 1)):
                bom = BillOfMaterial(company_id=company.id, code="BOM-FG-001", version=1, finished_item_id=items["FG-001"].id, output_quantity=Decimal("100"), work_center_id=work_center.id, standard_hours=Decimal("4"), status="ACTIVE")
                bom.lines.extend([
                    BillOfMaterialLine(component_item_id=items["RAW-001"].id, quantity=Decimal("120"), scrap_percent=Decimal("2")),
                    BillOfMaterialLine(component_item_id=items["PACK-001"].id, quantity=Decimal("100"), scrap_percent=Decimal("1")),
                ])
                db.add(bom)

        if not db.scalar(select(AssetCategory).where(AssetCategory.company_id == company.id, AssetCategory.code == "EQUIP")):
            db.add(AssetCategory(company_id=company.id, code="EQUIP", name_ar="الآلات والمعدات", name_en="Machinery and Equipment", asset_account_id=accounts["151010"].id, accumulated_depreciation_account_id=accounts["153010"].id, depreciation_expense_account_id=accounts["617010"].id, useful_life_months=60, residual_percent=Decimal("0"), depreciation_convention="FULL_MONTH_BY_15TH", active=True))

        employee = db.scalar(select(Employee).where(Employee.company_id == company.id, Employee.employee_number == "EMP-0001"))
        if not employee:
            employee = Employee(company_id=company.id, employee_number="EMP-0001", name_ar="موظف تجريبي", name_en="Demo Employee", nationality_group="SAUDI", hire_date=date(2026,1,1), basic_salary=Decimal("8000"), housing_allowance=Decimal("2000"), other_allowance=Decimal("500"), employee_gosi_rate=Decimal("9.75"), employer_gosi_rate=Decimal("11.75"), branch_id=branch.id if branch else None, active=True)
            db.add(employee); db.flush()

        shift = db.scalar(select(Shift).where(Shift.company_id == company.id, Shift.code == "DAY"))
        if not shift:
            from datetime import time
            shift = Shift(company_id=company.id, code="DAY", name_ar="الوردية النهارية", name_en="Day Shift", start_time=time(8, 0), end_time=time(17, 0), grace_minutes=10, working_days="6,0,1,2,3", active=True)
            db.add(shift); db.flush()
        for code, ar, en, paid, affects in [("ANNUAL", "إجازة سنوية", "Annual Leave", True, False), ("UNPAID", "إجازة بدون راتب", "Unpaid Leave", False, True), ("SICK", "إجازة مرضية", "Sick Leave", True, False)]:
            if not db.scalar(select(LeaveType).where(LeaveType.company_id == company.id, LeaveType.code == code)):
                db.add(LeaveType(company_id=company.id, code=code, name_ar=ar, name_en=en, paid=paid, affects_payroll=affects, active=True))
        if employee and branch and not db.scalar(select(EmployeeShiftAssignment).where(EmployeeShiftAssignment.employee_id == employee.id, EmployeeShiftAssignment.active.is_(True))):
            db.add(EmployeeShiftAssignment(company_id=company.id, employee_id=employee.id, shift_id=shift.id, branch_id=branch.id, effective_from=date(2026,1,1), active=True, created_by=admin.id))

        if company.company_type == "RESTAURANT":
            work_center = db.scalar(select(WorkCenter).where(WorkCenter.company_id == company.id, WorkCenter.code == "KITCHEN-01"))
            if not work_center:
                work_center = WorkCenter(company_id=company.id, code="KITCHEN-01", name_ar="المطبخ الرئيسي", name_en="Main Kitchen", hourly_labor_rate=Decimal("80"), hourly_overhead_rate=Decimal("40"), active=True)
                db.add(work_center); db.flush()
            recipe = db.scalar(select(BillOfMaterial).where(BillOfMaterial.company_id == company.id, BillOfMaterial.code == "RECIPE-MEAL-001", BillOfMaterial.version == 1))
            if not recipe:
                recipe = BillOfMaterial(company_id=company.id, code="RECIPE-MEAL-001", version=1, finished_item_id=items["FG-001"].id, output_quantity=Decimal("1"), work_center_id=work_center.id, standard_hours=Decimal("0.05"), status="ACTIVE")
                recipe.lines.extend([
                    BillOfMaterialLine(component_item_id=items["RAW-001"].id, quantity=Decimal("0.25"), scrap_percent=Decimal("2")),
                    BillOfMaterialLine(component_item_id=items["PACK-001"].id, quantity=Decimal("1"), scrap_percent=Decimal("0")),
                ])
                db.add(recipe); db.flush()
            if not db.scalar(select(MenuItem).where(MenuItem.company_id == company.id, MenuItem.code == "MEAL-001")):
                db.add(MenuItem(company_id=company.id, code="MEAL-001", name_ar="وجبة تجريبية", name_en="Demo Meal", inventory_item_id=items["FG-001"].id, recipe_bom_id=recipe.id, selling_price=Decimal("35"), vat_rate=Decimal("15"), active=True))
            if not db.scalar(select(DeliveryPlatform).where(DeliveryPlatform.company_id == company.id, DeliveryPlatform.code == "KEETA")):
                db.add(DeliveryPlatform(company_id=company.id, code="KEETA", name_ar="كيتا", name_en="Keeta", commission_rate=Decimal("21"), active=True))
    if not db.scalar(select(LegalRuleVersion).where(LegalRuleVersion.code == "SA_LABOR_EOS")):
        import json
        db.add(LegalRuleVersion(
            code="SA_LABOR_EOS", jurisdiction="SA", name_ar="مكافأة نهاية الخدمة - نظام العمل السعودي",
            name_en="Saudi Labor Law End-of-Service Award", effective_from=date(2025,2,19),
            parameters_json=json.dumps({"first_five_years_months_per_year": 0.5, "after_five_years_months_per_year": 1.0, "resignation_bands": [[0,2,0],[2,5,0.333333],[5,10,0.666667],[10,999,1.0]]}),
            source_url="https://www.hrsd.gov.sa/en/knowledge-centre/articles/317", active=True,
        ))
    default_sod_rules = [
        ("JE_CREATE_APPROVE", "إنشاء واعتماد القيود", "Journal creation and approval", "journals.create", "journals.approve", "CRITICAL", "No user should prepare and approve the same class of journal entries."),
        ("JE_CREATE_POST", "إنشاء وترحيل القيود", "Journal creation and posting", "journals.create", "journals.post", "HIGH", "Journal preparers should not independently post entries."),
        ("PAYROLL_MANAGE_PAY", "إدارة وصرف الرواتب", "Payroll preparation and payment", "payroll.manage", "payroll.pay", "CRITICAL", "Payroll preparation and cash disbursement must be separated."),
        ("BUDGET_MANAGE_APPROVE", "إعداد واعتماد الموازنة", "Budget preparation and approval", "budget.manage", "budget.approve", "HIGH", "Budget preparers should not approve their own budgets."),
        ("ACCESS_MANAGE_APPROVE", "إدارة واعتماد الصلاحيات", "Access management and approval", "access.manage", "access.approve", "CRITICAL", "Access provisioning and certification approval must be separated."),
    ]
    for code, ar, en, permission_a, permission_b, severity, rationale in default_sod_rules:
        if not db.scalar(select(SoDRule).where(SoDRule.code == code)):
            db.add(SoDRule(code=code, name_ar=ar, name_en=en, permission_a=permission_a, permission_b=permission_b, severity=severity, rationale=rationale, active=True))
    db.flush()


def _upgrade_existing_database(db: Session) -> None:
    # v0.30 brand migration for demo/staging databases created under the former identity.
    legacy_admin = db.scalar(select(User).where(User.email == "admin@nexoraerp.com"))
    if legacy_admin:
        legacy_admin.email = "admin@corvaxplatform.com"
        legacy_admin.password_hash = hash_password("Corvax@123")

    permission_rows = {row.code: row for row in db.scalars(select(Permission)).all()}
    for code, (name_ar, name_en) in PERMISSIONS.items():
        if code not in permission_rows:
            row = Permission(code=code, name_ar=name_ar, name_en=name_en)
            db.add(row)
            permission_rows[code] = row
    if "*" not in permission_rows:
        wildcard = Permission(code="*", name_ar="كامل الصلاحيات", name_en="All permissions")
        db.add(wildcard)
        permission_rows["*"] = wildcard
    db.flush()
    role_names = {
        "SUPER_ADMIN": ("مدير النظام", "System Administrator"),
        "FINANCIAL_CONTROLLER": ("المراقب المالي", "Financial Controller"),
        "CFO": ("المدير المالي", "Chief Financial Officer"),
        "ACCOUNTANT": ("محاسب", "Accountant"),
        "AUDITOR": ("مراجع", "Auditor"),
        "IT_MANAGER": ("مدير تقنية المعلومات", "IT Manager"),
        "QUALITY_MANAGER": ("مدير الجودة", "Quality Manager"),
        "HR_MANAGER": ("مدير الموارد البشرية", "HR Manager"),
        "SALES_MANAGER": ("مدير المبيعات والتسويق", "Sales and Marketing Manager"),
        "RESTAURANT_MANAGER": ("مدير المطعم", "Restaurant Manager"),
        "GYM_MANAGER": ("مدير النادي", "Gym Manager"),
        "GYM_TRAINER": ("مدرب النادي", "Gym Trainer"),
        "PRODUCTION_MANAGER": ("مدير الإنتاج", "Production Manager"),
    }
    roles = {row.code: row for row in db.scalars(select(Role)).all()}
    for code, names in role_names.items():
        role = roles.get(code)
        if role is None:
            role = Role(code=code, name_ar=names[0], name_en=names[1])
            db.add(role)
            db.flush()
            roles[code] = role
        else:
            role.name_ar, role.name_en = names
        role.permissions = [permission_rows[permission_code] for permission_code in ROLE_PERMISSION_MAP[code]]
    for company in db.scalars(select(Company)).all():
        if not company.vat_number:
            company.vat_number = f"31000000000000{company.id}"
        if not company.commercial_registration:
            company.commercial_registration = f"700000000{company.id}"
        branch = db.scalar(select(Branch).where(Branch.company_id == company.id).order_by(Branch.id))
        if branch and branch.latitude is None:
            branch.latitude = Decimal("24.4672000"); branch.longitude = Decimal("39.6111000"); branch.geofence_radius_m = 300
        account_by_code = {a.code: a for a in db.scalars(select(Account).where(Account.company_id == company.id)).all()}
        for code_, ar, en, account_type, group, parent_code, level, postable, cash in COA:
            if code_ in account_by_code:
                continue
            parent = account_by_code.get(parent_code) if parent_code else None
            account = Account(company_id=company.id, code=code_, name_ar=ar, name_en=en, account_type=account_type, statement_group=group, parent_id=parent.id if parent else None, level=level, is_postable=postable, is_cash=cash, active=True)
            db.add(account)
            db.flush()
            account_by_code[code_] = account
    admin = db.scalar(select(User).where(User.email == "admin@corvaxplatform.com")) or db.scalar(select(User).order_by(User.id))
    if admin:
        _ensure_operational_masters(db, admin)
    _register_unchanged_historical_demo_journals(db)
    _register_unchanged_historical_demo_stock_movements(db)
    db.commit()

def seed_database(db: Session) -> None:
    if db.scalar(select(func.count(Company.id))) > 0:
        _upgrade_existing_database(db)
        return

    # Alembic revisions may already seed selected permissions before demo companies exist.
    # Reuse those rows so first startup remains idempotent.
    permission_rows: dict[str, Permission] = {row.code: row for row in db.scalars(select(Permission)).all()}
    for code, (name_ar, name_en) in PERMISSIONS.items():
        row = permission_rows.get(code)
        if row is None:
            row = Permission(code=code, name_ar=name_ar, name_en=name_en)
            db.add(row)
            permission_rows[code] = row
        else:
            row.name_ar = name_ar
            row.name_en = name_en
    if "*" not in permission_rows:
        wildcard = Permission(code="*", name_ar="كامل الصلاحيات", name_en="All permissions")
        db.add(wildcard)
        permission_rows["*"] = wildcard
    db.flush()

    role_names = {
        "SUPER_ADMIN": ("مدير النظام", "System Administrator"),
        "FINANCIAL_CONTROLLER": ("المراقب المالي", "Financial Controller"),
        "CFO": ("المدير المالي", "Chief Financial Officer"),
        "ACCOUNTANT": ("محاسب", "Accountant"),
        "AUDITOR": ("مراجع", "Auditor"),
        "IT_MANAGER": ("مدير تقنية المعلومات", "IT Manager"),
        "QUALITY_MANAGER": ("مدير الجودة", "Quality Manager"),
        "HR_MANAGER": ("مدير الموارد البشرية", "HR Manager"),
        "SALES_MANAGER": ("مدير المبيعات والتسويق", "Sales and Marketing Manager"),
        "RESTAURANT_MANAGER": ("مدير المطعم", "Restaurant Manager"),
        "GYM_MANAGER": ("مدير النادي", "Gym Manager"),
        "GYM_TRAINER": ("مدرب النادي", "Gym Trainer"),
        "PRODUCTION_MANAGER": ("مدير الإنتاج", "Production Manager"),
    }
    roles: dict[str, Role] = {row.code: row for row in db.scalars(select(Role)).all()}
    for code, names in role_names.items():
        role = roles.get(code)
        if role is None:
            role = Role(code=code, name_ar=names[0], name_en=names[1])
            db.add(role)
            roles[code] = role
        else:
            role.name_ar = names[0]
            role.name_en = names[1]
        role.permissions = [permission_rows[p] for p in ROLE_PERMISSION_MAP[code]]

    for company_id, code, name_ar, name_en, company_type, color in COMPANIES:
        company = Company(
            id=company_id,
            code=code,
            name_ar=name_ar,
            name_en=name_en,
            legal_name_ar=name_ar,
            legal_name_en=name_en,
            currency="SAR",
            country_code="SA",
            company_type=company_type,
            primary_color=color,
            vat_number=f"31000000000000{company_id}",
            commercial_registration=f"700000000{company_id}",
        )
        db.add(company)
        db.flush()
        db.add(
            Branch(
                company_id=company.id,
                code="HQ" if company_id == 1 else f"{code}-01",
                name_ar="الفرع الرئيسي",
                name_en="Main Branch",
                city_ar="المدينة المنورة",
                city_en="Madinah",
                latitude=Decimal("24.4672000"),
                longitude=Decimal("39.6111000"),
                geofence_radius_m=300,
            )
        )
        db.add(CostCenter(company_id=company.id, code="ADM", name_ar="الإدارة العامة", name_en="General Administration"))
        if company_type == "MANUFACTURING":
            db.add(CostCenter(company_id=company.id, code="PROD", name_ar="الإنتاج", name_en="Production"))
            db.add(CostCenter(company_id=company.id, code="QA", name_ar="الجودة", name_en="Quality"))
        elif company_type == "GYM":
            db.add(CostCenter(company_id=company.id, code="GYM-OPS", name_ar="تشغيل النادي", name_en="Gym Operations"))
        elif company_type == "RESTAURANT":
            db.add(CostCenter(company_id=company.id, code="KITCHEN", name_ar="المطبخ", name_en="Kitchen"))

        fy = FiscalYear(
            company_id=company.id,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="OPEN",
        )
        db.add(fy)
        db.flush()
        for month in range(1, 13):
            _, last_day = calendar.monthrange(2026, month)
            status = "SOFT_CLOSED" if month < 7 else "OPEN" if month == 7 else "FUTURE"
            db.add(
                FiscalPeriod(
                    fiscal_year_id=fy.id,
                    number=month,
                    name_ar=f"الفترة {month}",
                    name_en=f"Period {month}",
                    start_date=date(2026, month, 1),
                    end_date=date(2026, month, last_day),
                    status=status,
                )
            )

        account_by_code: dict[str, Account] = {}
        for code_, ar, en, account_type, group, parent_code, level, postable, cash in COA:
            account = Account(
                company_id=company.id,
                code=code_,
                name_ar=ar,
                name_en=en,
                account_type=account_type,
                statement_group=group,
                parent_id=account_by_code[parent_code].id if parent_code else None,
                level=level,
                is_postable=postable,
                is_cash=cash,
            )
            db.add(account)
            db.flush()
            account_by_code[code_] = account

        db.add(BankAccount(
            company_id=company.id, code="BANK-01", bank_name_ar="البنك الرئيسي",
            bank_name_en="Main Bank", iban=f"SA00CORVAX{company.id:04d}",
            gl_account_id=account_by_code["111010"].id, active=True,
        ))
        db.add(Party(
            company_id=company.id, code="CUST-001", name_ar="عميل تجريبي",
            name_en="Demo Customer", party_type="CUSTOMER", credit_limit=Decimal("1000000"), active=True,
        ))
        db.add(Party(
            company_id=company.id, code="SUP-001", name_ar="مورد تجريبي",
            name_en="Demo Supplier", party_type="SUPPLIER", credit_limit=Decimal("0"), active=True,
        ))

    admin = User(
        name_ar="مدير النظام",
        name_en="System Administrator",
        email="admin@corvaxplatform.com",
        password_hash=hash_password("Corvax@123"),
        active=True,
    )
    db.add(admin)
    db.flush()
    for company_id, *_ in COMPANIES:
        db.add(UserCompanyRole(user_id=admin.id, company_id=company_id, role_id=roles["SUPER_ADMIN"].id))
    db.flush()

    for company_id, *_ in COMPANIES:
        prefix = f"JV-{company_id}-2026"
        _create_journal(db, company_id, admin.id, f"{prefix}-0001", date(2026, 1, 1), "OPENING", "Opening capital",
                        [("111010", Decimal("2000000"), Decimal("0")), ("311010", Decimal("0"), Decimal("2000000"))],
                        "FINANCING", "CAPITAL_CONTRIBUTION")
        _create_journal(db, company_id, admin.id, f"{prefix}-0002", date(2026, 7, 2), "INV-001", "Sales invoice",
                        [("112010", Decimal("575000"), Decimal("0")), ("411010", Decimal("0"), Decimal("500000")), ("212010", Decimal("0"), Decimal("75000"))])
        _create_journal(db, company_id, admin.id, f"{prefix}-0003", date(2026, 7, 4), "RCPT-001", "Customer receipt",
                        [("111010", Decimal("575000"), Decimal("0")), ("112010", Decimal("0"), Decimal("575000"))],
                        "OPERATING", "CUSTOMER_RECEIPTS")
        _create_journal(db, company_id, admin.id, f"{prefix}-0004", date(2026, 7, 5), "PUR-001", "Inventory purchased on credit",
                        [("113010", Decimal("300000"), Decimal("0")), ("211010", Decimal("0"), Decimal("300000"))])
        _create_journal(db, company_id, admin.id, f"{prefix}-0005", date(2026, 7, 6), "COGS-001", "Cost of sales",
                        [("511010", Decimal("220000"), Decimal("0")), ("113010", Decimal("0"), Decimal("220000"))])
        _create_journal(db, company_id, admin.id, f"{prefix}-0006", date(2026, 7, 7), "PAY-EMP", "Employee payments",
                        [("611010", Decimal("200000"), Decimal("0")), ("111010", Decimal("0"), Decimal("200000"))],
                        "OPERATING", "EMPLOYEE_PAYMENTS")
        _create_journal(db, company_id, admin.id, f"{prefix}-0007", date(2026, 7, 8), "RENT-001", "Rent paid",
                        [("612010", Decimal("80000"), Decimal("0")), ("111010", Decimal("0"), Decimal("80000"))],
                        "OPERATING", "OTHER_OPERATING_PAYMENTS")
        _create_journal(db, company_id, admin.id, f"{prefix}-0008", date(2026, 7, 9), "PPE-001", "Equipment purchase",
                        [("151010", Decimal("300000"), Decimal("0")), ("111010", Decimal("0"), Decimal("300000"))],
                        "INVESTING", "ASSET_PURCHASES")
        _create_journal(db, company_id, admin.id, f"{prefix}-0009", date(2026, 7, 10), "LOAN-001", "Loan proceeds",
                        [("111010", Decimal("500000"), Decimal("0")), ("221010", Decimal("0"), Decimal("500000"))],
                        "FINANCING", "BORROWINGS")
        _create_journal(db, company_id, admin.id, f"{prefix}-0010", date(2026, 7, 11), "SUP-PAY", "Supplier payment",
                        [("211010", Decimal("100000"), Decimal("0")), ("111010", Decimal("0"), Decimal("100000"))],
                        "OPERATING", "SUPPLIER_PAYMENTS")

    _ensure_operational_masters(db, admin)

    db.commit()
