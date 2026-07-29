# تقرير إصلاح وتحقق — CORVAX RC27.4 Remediation R1

**التاريخ:** 28 يوليو 2026  
**الإصدار الأساسي:** `1.0.0-agreement-completion-rc27.4`  
**رأس الترحيل المعتمد:** `e19600000001`

## الحكم

هذه الحزمة هي نسخة إصلاح مستقلة مشتقة من الملف المرفق، وليست تعديلًا للملف
الأصلي. أُغلقت العيوب المثبتة في المراجعة الأولى، وأضيفت بوابة إصدار تمنع
عودة تعارضات الإصدار وواجهات القراءة والصلاحيات.

النسخة مؤهلة للمعاينة وStaging. لا تعني هذه النتيجة اعتماد Go-Live؛ الاعتماد
الإنتاجي يحتاج PostgreSQL فعليًا، نشر Render ناجحًا، Restore Drill، UAT،
تشغيلًا موازيًا، واختبار اختراق مستقل.

## الإصلاحات المنفذة

1. توحيد رأس Alembic على `e19600000001` في README وقائمة الإنتاج.
2. إضافة `GET /api/v1/gym/class-types` مع صلاحية `gym.read`.
3. إضافة `GET /api/v1/gym/pt-packages` مع صلاحية `gym.read`.
4. ربط شاشة النادي بنقاط القراءة الفعلية وإزالة الاستنتاجات والرسائل المؤقتة.
5. تصحيح سعر باقات التدريب لاستخدام `net_price`.
6. إصلاح تشغيل اختبار عزل الفروع من أي مسار.
7. إزالة بقايا الشارات والاستيرادات الوهمية من رأس الواجهة.
8. إزالة `xlsx` المصابة بثغرات Prototype Pollution وReDoS.
9. إزالة `react-router-dom` المتأثرة بتنبيهات أمنية واستبدالها بموجّه Hash داخلي.
10. إنشاء كاتب XLSX محلي محدود وآمن باستخدام ملفات OpenXML مضغوطة.
11. إضافة `backend/scripts/release_gate.py` للتحقق من:
    - هوية الإصدار ورأس الترحيل.
    - عدم رجوع شارات وهمية أو اسم RC23.
    - اكتمال عقود قراءة النادي.
    - وجود المصادقة في جميع مسارات API عدا قائمة عامة محددة.
    - عدم رجوع رأس ترحيل قديم إلى وثائق النشر.

## نتائج التحقق الفعلية

| الفحص | النتيجة |
|---|---|
| Python compileall | ناجح |
| Alembic fresh SQLite migration | ناجح حتى `e19600000001` |
| Release Gate | ناجح 5/5 |
| Admin tenant hardening | ناجح |
| Branch scope security | ناجح |
| Demo surface hardening | ناجح |
| Health contract | ناجح |
| Module registry | ناجح |
| Production UI controls | ناجح |
| Security hardening | ناجح |
| UI quality | ناجح |
| Production data guards | ناجح |
| Frontend TypeScript + Vite | ناجح، 2,030 modules |
| npm production audit | **0 vulnerabilities** |

## حدود نسبة 98%

الوصول إلى 98% لا يجوز حسابه من عدد الملفات أو الشاشات. بعد هذه الإصلاحات أصبحت
الحزمة أقوى كمرشح داخلي، لكن 98% **لا تُعتمد نهائيًا** قبل:

- تشغيل جميع الدورات المالية على PostgreSQL.
- التأكد من عزل كل شركة وفرع بمستخدمين فعليين.
- مطابقة الأستاذ مع AR/AP والمخزون والأصول والرواتب والضرائب.
- تجربة النسخ والاستعادة من تخزين خارجي.
- معاينة بشرية لكل شاشة وزر وتصدير.
- UAT موقع وتشغيل موازٍ.

لذلك تُسلم هذه النسخة باعتبارها **98%-Target Internal Candidate**، وليس شهادة
Production بنسبة 98%. المشاكل التي تظهر في معاينة المستخدم تُسجل ضد هذه الحزمة
نفسها ويُبنى عليها الإصدار التالي دون الرجوع إلى نسخة أقدم.

## الملفات المرجعية

- `README.md`
- `deploy/PRODUCTION_CHECKLIST.md`
- `backend/scripts/release_gate.py`
- `backend/app/api/gym_operations_advanced.py`
- `frontend/src/dashboard/gymRealPage.tsx`
- `frontend/src/dashboard/reportBuilderTab.tsx`
- `frontend/src/dashboard/routes.tsx`
