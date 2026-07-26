# CORVAX Business Platform v0.10 — تقرير الاختبار

تاريخ الاختبار: 12 يوليو 2026

## النتائج

- React + TypeScript production build: **PASS**.
- Python compileall: **PASS**.
- Alembic migration 1 — persistent core: **PASS**.
- Alembic migration 2 — AR/AP/Treasury: **PASS**.
- عدد الجداول بعد الترحيل: **23 جدولًا** شاملًا `alembic_version`.
- Database authentication: **PASS**.
- Company access isolation: **PASS**.
- User/role creation: **PASS**.
- Manual journal create/submit/approve/post: **PASS**.
- Maker-checker rejection: **PASS**.
- Closed-period rejection: **PASS**.
- Sales invoice + output VAT + GL posting: **PASS**.
- Customer receipt + bank/AR posting: **PASS**.
- Purchase invoice + recoverable VAT + AP posting: **PASS**.
- Supplier payment + bank/AP posting: **PASS**.
- Trial balance equality: **PASS**.
- Statement of financial position equality: **PASS**.
- Direct cash-flow update from posted transactions: **PASS**.
- Audit trail event creation: **PASS**.
- Static frontend served by FastAPI: **PASS**.

## ملاحظة مراجعة

أظهر الاختبار الأول لفاتورة الشراء فرقًا قدره 150 ريالًا في المركز المالي بسبب استبعاد ضريبة المدخلات القابلة للاسترداد من الأصول المتداولة. تم تصحيح التصنيف وإعادة جميع اختبارات الدفاتر والقوائم بنجاح.
