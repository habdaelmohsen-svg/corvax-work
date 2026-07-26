# تقرير اختبارات CORVAX v0.32

## السيناريو المختبر

- إنشاء ربح تشغيلي 100,000 ريال.
- تسجيل مصروفات 60,000 ريال.
- إغلاق الفترات 1–11 وترك الفترة 12 مفتوحة.
- تشغيل مراجعة الإقفال السنوي.
- التحقق من نتيجة سنة مقدارها 40,000 ريال.
- منع طالب الإقفال من الاعتماد.
- اعتماد الإقفال بواسطة مستخدم CFO مختلف.
- تصفير حسابات الإيرادات والمصروفات.
- ترحيل 40,000 ريال إلى الأرباح المبقاة.
- إغلاق السنة والفترة النهائية.
- إنشاء FY 2027 و12 فترة.

## نتائج التحقق

- FastAPI health version: `0.32.0`.
- Year-end engine: active.
- قيد الإقفال متوازن.
- P&L balances after close: zero.
- Retained earnings updated.
- Maker-checker enforced.
- Alembic head: `e32000000001`.
- Fresh database: 101 tables.
- Upgrade from e280 to e320 preserved 4 companies and 204 accounts.
- React/TypeScript production build passed.

## النتيجة

`CORVAX v0.32 year-end close and retained earnings: ALL VERIFICATIONS PASSED`
