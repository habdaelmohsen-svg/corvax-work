# نشر CORVAX v1.0 RC1

## Staging السريع على Render

1. أنشئ مستودع GitHub وارفع محتويات المشروع.
2. استخدم `render.yaml`.
3. راجع اسم النطاق واضبط `ALLOWED_ORIGINS` و`TRUSTED_HOSTS` إذا تغير اسم الخدمة.
4. شغّل Staging ببيانات غير حساسة.

## Production الموصى به

- PostgreSQL مدارة.
- Container service أو Kubernetes/VPS مُدار.
- Reverse proxy/TLS.
- Secret Manager.
- Object Storage للمرفقات والنسخ.
- Sentry/OpenTelemetry أو أداة مراقبة مماثلة.
- بيئات منفصلة: Development، Staging، Production.

## الترقية

```bash
alembic upgrade head
```

الرأس المتوقع:

```text
e10000000001
```

## فحص النشر

```bash
curl https://your-domain/health/live
curl https://your-domain/health/ready
```

## العودة للإصدار السابق

لا تنفذ Downgrade مباشرًا على قاعدة إنتاج دون نسخة واستشارة DBA. الطريقة الأكثر أمانًا هي استعادة Snapshot سابق ونشر صورة التطبيق السابقة.
