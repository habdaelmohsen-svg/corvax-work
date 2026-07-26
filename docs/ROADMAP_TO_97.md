# CORVAX — الخريطة المتبقية للوصول إلى 95–97%

## الحالة بعد RC10

التقييم الداخلي الصارم التقريبي: **92%**. المالية وصلت إلى 96–97% داخليًا، والتصنيع والتكاليف إلى نحو 91%.

## الحزم المتبقية ذات الأولوية

### 1. الموارد البشرية والرواتب

- ربط نهائي بين الورديات والحضور والإجازات والجزاءات والإضافي والمسير.
- WPS متعدد البنوك، التسويات، السلف والقروض، وتدقيق صافي الرواتب.
- IAS 19 ومكافأة نهاية الخدمة والتذاكر والتأمين الطبي.

### 2. المطاعم والنادي

- KDS والطاولات والورديات والإغلاقات والمرتجعات وتكامل منصات التوصيل.
- العضويات والتجميد والتمديد والحجوزات والمدربين والعمولات وPT.
- الاعتراف بالإيراد المؤجل والمستحق بصورة كاملة لكل حالة.

### 3. التصنيع المتبقي

- Lead Times، Lot Sizing، Min/Max وPurchase Order Receipts في MRP.
- تقويم المصنع والورديات وجدولة الطاقة المحدودة.
- الموارد البديلة والعمليات المتوازية والتشغيل لدى الغير.
- أوامر إعادة التشغيل والمنتجات الثانوية واسترداد الهالك للمخزون.
- Actual Cost Roll-up دوري ومتعدد المستويات.

### 4. الأمن والجاهزية التشغيلية

- MFA إلزامي للأدوار الحساسة.
- Vault للأسرار وتشفير الحقول الحساسة.
- PostgreSQL Restore Drill، RPO/RTO، اختبار ضغط واختبار اختراق مستقل.
- مراقبة وأحداث أمنية وتنبيهات مركزية.

### 5. تجربة الاستخدام والتقارير

- إعادة تصميم جميع الشاشات الداخلية بنفس مستوى لوحة القيادة.
- نماذج إدخال كاملة بدل أزرار العرض التجريبي.
- طباعة وتصدير Excel/PDF موحدة.
- بحث عالمي، فلاتر محفوظة، Drill-down وتقارير أدوار.

## المستثنى مؤقتًا من نسبة الإنجاز

الربط الإنتاجي مع ZATCA والبنوك ومدد وقوى ومقيم والتأمينات وأي منصة تتطلب اعتمادًا أو بيانات دخول رسمية. تبقى واجهات الربط ضمن خطة ما بعد اكتمال النطاق الداخلي.

---

## RC11 audit-remediation update — 15 July 2026

Internally implemented: RS256/refresh rotation, field encryption, rate limiting, journal sequence allocator, demo endpoint removal, frontend/model refactor, UTC cleanup, observability foundation, MRP planning improvements, IFRS 9 general approach and advanced IFRS 16 cases.

Still gating the 95–97% production-readiness claim: independent penetration test, actual data migration/UAT/parallel run, production load and DR drills, and official Saudi/bank integrations.
