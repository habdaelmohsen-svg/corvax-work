# نشر CORVAX v0.16 من GitHub إلى Render

## 1. تجهيز GitHub

1. فك الملف المضغوط.
2. أنشئ مستودع GitHub فارغًا.
3. ارفع محتويات مجلد المشروع إلى جذر المستودع.
4. تأكد من وجود `Dockerfile` و`render.yaml` و`backend` و`frontend`.

## 2. النشر التجريبي

1. في Render اختر **New → Blueprint**.
2. اربط مستودع GitHub.
3. ينشئ `render.yaml` خدمة Web وقاعدة PostgreSQL.
4. Docker يبني React، يثبت Python، ينفذ `alembic upgrade head`، ثم يشغّل FastAPI.

بيئة Blueprint تبدأ بدون بيانات تجريبية عبر `SEED_DEMO_DATA=false` حتى تُدخل أرصدة الافتتاح والمعاملات الفعلية فقط.

## 3. بيانات التجربة

- Email: `admin@corvaxplatform.com`
- Password: `Corvax@123`

## 4. التحويل إلى إنتاج

- غيّر `ENVIRONMENT=production`.
- ضع `SEED_DEMO_DATA=false`.
- حدد `ALLOWED_ORIGINS` ولا تستخدم `*`.
- استخدم PostgreSQL مدفوعة ونسخًا خارجية.
- احذف بيانات الدخول التجريبية.
- راجع `deploy/PRODUCTION_CHECKLIST.md`.

## 5. تنبيه

Render Free مناسب للعرض والاختبار فقط. النظام المالي الحقيقي يحتاج موارد مستقرة، مراقبة، نسخًا خارجية، سياسة استعادة، اختبارًا أمنيًا، واعتمادًا ضريبيًا وقانونيًا قبل إدخال البيانات الرسمية.
