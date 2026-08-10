# CORVAX Production Checklist — v1.0 RC1

## إعدادات إلزامية

- [ ] `ENVIRONMENT=production`
- [ ] `SECRET_KEY` عشوائي بطول 32+ حرفًا ومخزن في Secret Manager.
- [ ] `SEED_DEMO_DATA=false`
- [ ] `ALLOW_DATA_RESET=false` ولا يوجد أي استثناء لهذا الشرط في الإنتاج.
- [ ] `ALLOWED_ORIGINS` نطاقات HTTPS محددة وليست `*`.
- [ ] `TRUSTED_HOSTS` نطاقات محددة وليست `*`.
- [ ] `FORCE_HTTPS=true` أو تطبيق HTTPS Redirect على Load Balancer موثوق.
- [ ] `DOCS_ENABLED=false` إلا إذا كانت وثائق API محمية.
- [ ] حذف مستخدم التجربة أو تغيير بياناته وعدم منحه صلاحيات شاملة.
- [ ] PostgreSQL إنتاجية مشفرة ومدارة.

## الأمن

- [ ] تفعيل MFA لجميع المستخدمين ذوي الصلاحيات الحساسة.
- [ ] مراجعة مصفوفة الأدوار وفصل المهام SoD.
- [ ] تشفير أي حقول حساسة إضافية حسب تصنيف بيانات الشركة.
- [ ] تخزين المرفقات في Object Storage خاص مع فحص Malware.
- [ ] اختبار اختراق مستقل وإغلاق النتائج.
- [ ] إعداد WAF وRate Limiting موزع ومراقبة محاولات الدخول.
- [ ] تدوير Secrets وخطة استجابة للحوادث.

## قاعدة البيانات والنسخ

- [ ] تفعيل PostgreSQL PITR ونسخة جغرافية ثانية.
- [ ] تخزين النسخ خارج خادم التطبيق وتشفيرها.
- [ ] تشغيل `scripts/verify_restore.py` على كل نسخة مختارة.
- [ ] تنفيذ Restore Drill إلى خادم مستقل.
- [ ] اعتماد RPO/RTO.
- [ ] مراقبة الاتصال والاستعلامات البطيئة والمساحة.

## التطبيق

- [ ] `alembic upgrade head` يصل إلى `e20500000001`، مع التحقق عبر `/health/ready`.
- [ ] `/health/live` و`/health/ready` يعملان.
- [ ] مراجعة logs و`X-Request-ID` في منصة المراقبة.
- [ ] اختبار ضغط على عدد المستخدمين والحركات المتوقع.
- [ ] فحص كل صلاحية API وعدم الاكتفاء بصلاحيات الواجهة.
- [ ] توقيع Release Manifest وChecksum للحزمة المنشورة.

## المحاسبة والامتثال

- [ ] اعتماد شجرة الحسابات والسياسات المحاسبية.
- [ ] اعتماد قواعد IFRS 9/15/16/18 القابلة للتطبيق.
- [ ] اعتماد سياسات الإهلاك والمصروفات المقدمة والاستحقاقات والإقفال.
- [ ] ZATCA onboarding وCSID واختبارات الهيئة.
- [ ] مراجعة VAT/Zakat/WHT حسب طبيعة كل شركة.
- [ ] مراجعة قواعد العمل والتأمينات وWPS ونهاية الخدمة قانونيًا.

## التحويل والإطلاق

- [ ] تنظيف وتحويل البيانات من المصدر القديم.
- [ ] مطابقة الأرصدة الافتتاحية والدفاتر الفرعية.
- [ ] Parallel Run للرواتب والفواتير والإقفال.
- [ ] UAT موقع من كل إدارة.
- [ ] تدريب المستخدمين وأدلة عربية وإنجليزية.
- [ ] خطة Rollback وHypercare بعد الإطلاق.

## Financial assurance gate — RC2

- [ ] Materiality, performance materiality and trivial threshold approved for the period.
- [ ] Financial assurance review conclusion is READY or formally accepted CONDITIONAL.
- [ ] No blocking check remains FAIL.
- [ ] Financial Controller certification completed by a user other than the preparer.
- [ ] CFO certification completed after Financial Controller certification.
- [ ] Internal Audit certification completed for year-end scope.
- [ ] Certification users are distinct and evidence is retained.
- [ ] All warnings and exceptions have named owners and due dates.

## RC5 — سلامة الغذاء والصلاحيات

- [ ] اعتماد فريق HACCP وخطط المنتجات من إدارة الجودة والتشغيل.
- [ ] تحميل المواصفات الفعلية وحدود CCP وأجهزة القياس المعتمدة.
- [ ] تنفيذ Recall Drill على بيانات حقيقية وقياس زمن التتبع والاسترداد.
- [ ] اعتماد قواعد SoD حسب مصفوفة الصلاحيات الفعلية للشركة.
- [ ] تنفيذ أول حملة Access Review وتوقيع مالكي الأنظمة والإدارات.
- [ ] إزالة جميع التعارضات الحرجة أو توثيق الضوابط المخففة المعتمدة.
