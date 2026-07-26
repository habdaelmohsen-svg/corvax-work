from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeEntry:
    code: str
    title_ar: str
    title_en: str
    body_ar: str
    body_en: str
    keywords: tuple[str, ...]


ENTRIES: tuple[KnowledgeEntry, ...] = (
    KnowledgeEntry("KB-CORE-001", "التنقل والسياق", "Navigation and context", "اختر الشركة أولًا، ثم استخدم القائمة الجانبية للوصول إلى الموديول. صلاحيات المستخدم وسياق الشركة يحددان الشاشات والبيانات المتاحة.", "Select a company first, then use the sidebar to open a module. User permissions and company context determine the available screens and data.", ("شركة", "الشاشة", "قائمة", "company", "screen", "navigation")),
    KnowledgeEntry("KB-FIN-001", "المالية والقيود", "Finance and journals", "تبدأ الحركة بمستند تشغيلي أو قيد مسودة، ثم تمر بالمراجعة والاعتماد والترحيل وفق الصلاحيات والفترة المالية. لا يُعد المستند مؤثرًا في الأستاذ قبل الترحيل.", "A transaction starts as an operational document or draft journal, then moves through review, approval, and posting based on permissions and period status. It does not affect the ledger before posting.", ("قيد", "ترحيل", "الأستاذ", "journal", "posting", "ledger")),
    KnowledgeEntry("KB-ARAP-001", "العملاء والموردون", "Receivables and payables", "تعرض تقارير أعمار الديون أرصدة العملاء أو الموردين حسب تاريخ الاستحقاق، وتحتاج الفواتير والسداد والتخصيص إلى نفس الشركة والفترة المرجعية.", "Aging reports classify customer or supplier balances by due date. Invoices, settlements, and allocations must share the correct company and reference period.", ("أعمار", "عملاء", "مورد", "aging", "receivable", "payable")),
    KnowledgeEntry("KB-INV-001", "المخزون", "Inventory", "تعتمد الكمية المتاحة على حركات المخزون والمستودع والفرع. حد إعادة الطلب خاص ببطاقة الصنف، بينما الرصيد يُستخرج من الحركات المرحلة.", "Available quantity is derived from stock movements, warehouse, and branch. Reorder level belongs to the item master, while balance comes from posted movements.", ("مخزون", "صنف", "إعادة الطلب", "inventory", "item", "reorder")),
    KnowledgeEntry("KB-SC-001", "المشتريات", "Procurement", "المسار المعتاد هو طلب شراء ثم أمر شراء ثم استلام ثم فاتورة مورد ومطابقة. قد يمنع النظام الاعتماد أو الترحيل إذا كانت حالة المستند أو المطابقة أو الفترة غير صحيحة.", "The normal flow is purchase request, purchase order, receipt, supplier invoice, and matching. Approval or posting can be blocked by document status, matching, or period controls.", ("شراء", "استلام", "مطابقة", "purchase", "receipt", "match")),
    KnowledgeEntry("KB-MFG-001", "التصنيع والتكلفة", "Manufacturing and costing", "يربط أمر الإنتاج بين قائمة المواد والصرف والإنتاج التام والهدر والانحرافات. يجب اعتماد الوصفة والوحدات والمستودعات قبل احتساب التكلفة.", "A production order connects the bill of materials, issues, finished output, waste, and variances. Approved recipes, units, and warehouses are required before costing.", ("تصنيع", "تكلفة", "وصفة", "production", "costing", "bom")),
    KnowledgeEntry("KB-HR-001", "الموارد البشرية والرواتب", "HR and payroll", "تعتمد الرواتب على ملف الموظف والعقد والحضور والبدلات والاستقطاعات والفترة. لا تُعتمد نتيجة الرواتب دون مراجعة الصلاحيات ومراكز التكلفة.", "Payroll depends on the employee master, contract, attendance, allowances, deductions, and period. Results require permission and cost-center review before approval.", ("موظف", "رواتب", "حضور", "employee", "payroll", "attendance")),
    KnowledgeEntry("KB-POS-001", "نقاط البيع والمطاعم", "POS and restaurants", "يجب فتح وردية الكاشير وربط نقطة البيع والفرع والضريبة. الإغلاق يطابق المبيعات ووسائل الدفع والنقدية وحركات المخزون.", "The cashier shift, POS, branch, and tax configuration must be active. Closing reconciles sales, payment methods, cash, and stock movements.", ("كاشير", "مطعم", "وردية", "pos", "restaurant", "shift")),
    KnowledgeEntry("KB-GYM-001", "النادي والعضويات", "Gym and memberships", "تربط العضوية العميل والباقة والفترة والمرافق. الإيراد المقدم يعترف به على مدة الخدمة وفق إعدادات العقد والاعتراف بالإيراد.", "A membership connects the customer, package, period, and facilities. Deferred revenue is recognized across the service period based on contract and revenue rules.", ("نادي", "عضوية", "باقة", "gym", "membership", "package")),
    KnowledgeEntry("KB-ASSET-001", "الأصول والإيجارات", "Assets and leases", "تمر الأصول بالإضافة والتشغيل والإهلاك والنقل والاستبعاد. عقود الإيجار تنتج أصل حق استخدام والتزامًا وفق الجدول المعتمد.", "Assets move through addition, capitalization, depreciation, transfer, and disposal. Leases create a right-of-use asset and liability based on the approved schedule.", ("أصل", "إهلاك", "إيجار", "asset", "depreciation", "lease")),
    KnowledgeEntry("KB-TAX-001", "الضريبة والزكاة", "Tax and Zakat", "تعتمد ضريبة القيمة المضافة والزكاة وضريبة الدخل على بيانات مرحّلة وسياسات وفترات معتمدة. المساعد يشرح ولا يقدم إقرارًا أو اعتمادًا نظاميًا.", "VAT, Zakat, and income tax depend on posted data, approved policies, and periods. The assistant explains results but does not submit or approve statutory filings.", ("ضريبة", "زكاة", "دخل", "vat", "zakat", "tax")),
    KnowledgeEntry("KB-GOV-001", "الصلاحيات وسير العمل", "Permissions and workflow", "تُطبق الصلاحيات على المستخدم والشركة والفرع. مسار Maker–Checker يمنع المستخدم من إعداد واعتماد نفس الحركة عندما تكون السياسة مطبقة.", "Permissions are evaluated for the user, company, and branch. Maker–Checker prevents the same user from preparing and approving a transaction when the policy applies.", ("صلاحية", "اعتماد", "فرع", "permission", "approval", "branch")),
    KnowledgeEntry("KB-UI-001", "العربية والإنجليزية والوضع الليلي", "Arabic, English, and dark mode", "تعمل العربية باتجاه RTL والقائمة على اليمين، والإنجليزية باتجاه LTR والقائمة على اليسار. يجب الإبلاغ عن أي شاشة لا تتبع الاتجاه أو الوضع المختار.", "Arabic uses RTL with the sidebar on the right; English uses LTR with the sidebar on the left. Report any screen that does not follow the selected direction or theme.", ("عربي", "إنجليزي", "ليلي", "rtl", "ltr", "dark")),
    KnowledgeEntry("KB-OPS-001", "النسخ الاحتياطي والمراقبة", "Backup and monitoring", "النسخ الاحتياطي لا يُعد ناجحًا قبل اختبار الاستعادة. سجلات التشغيل والتنبيهات وHealth checks ضرورية لإثبات الجاهزية على البيئة السحابية.", "A backup is not proven until restore is tested. Logs, alerts, and health checks are required to demonstrate readiness in the cloud environment.", ("نسخ", "استعادة", "مراقبة", "backup", "restore", "monitoring")),
)


def search_knowledge(message: str, locale: str, limit: int = 4) -> list[KnowledgeEntry]:
    normalized = message.casefold()
    scored: list[tuple[int, KnowledgeEntry]] = []
    for entry in ENTRIES:
        score = sum(1 for keyword in entry.keywords if keyword.casefold() in normalized)
        title = entry.title_ar if locale == "ar" else entry.title_en
        if title.casefold() in normalized:
            score += 2
        if score:
            scored.append((score, entry))
    if not scored:
        scored = [(1, ENTRIES[0])]
    scored.sort(key=lambda pair: (-pair[0], pair[1].code))
    return [entry for _, entry in scored[:limit]]
