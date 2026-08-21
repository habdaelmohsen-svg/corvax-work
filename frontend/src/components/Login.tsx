import { useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Copy,
  KeyRound,
  Languages,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Smartphone,
} from 'lucide-react';
import '../styles/auth.css';

type Lang = 'ar' | 'en';

type Enrollment = {
  secret: string;
  otpauthUri: string;
  token: string;
};

type ApiDetailItem = string | {
  msg?: string;
  message?: string;
  loc?: Array<string | number>;
};

type ApiDetail = string | ApiDetailItem[] | {
  message?: string;
  enrollment_required?: boolean;
  secret?: string;
  otpauth_uri?: string;
  enrollment_token?: string;
};

function localizedMessage(detail: ApiDetail | undefined, ar: boolean): string {
  const raw = Array.isArray(detail)
    ? detail.map((item) => typeof item === 'string'
      ? item
      : String(item.message || item.msg || '')).filter(Boolean).join(' · ')
    : typeof detail === 'object'
      ? String(detail.message || '')
      : String(detail || '');
  if (!ar) return raw || 'Login failed.';
  const messages: Array<[string, string]> = [
    ['Account is temporarily locked', 'الحساب مقفل مؤقتًا بسبب تكرار المحاولات. انتظر 15 دقيقة أو استخدم رابط الاستعادة.'],
    ['Invalid username or password', 'اسم المستخدم أو كلمة المرور غير صحيحة.'],
    ['Valid MFA code required', 'أدخل رمز الحماية المكوّن من 6 أرقام.'],
    ['Invalid MFA code', 'رمز الحماية غير صحيح أو انتهت صلاحيته.'],
    ['Recovery link is invalid, expired, or already used', 'رابط الاستعادة غير صالح أو انتهت مدته أو تم استخدامه من قبل.'],
    ['Administrator recovery is unavailable', 'تعذر العثور على حساب مدير صالح للاستعادة.'],
    ['Password must contain at least', 'يجب ألا تقل كلمة المرور عن 12 حرفًا.'],
    ['Password must include an uppercase letter', 'يجب أن تحتوي كلمة المرور على حرف إنجليزي كبير.'],
    ['Password must include a lowercase letter', 'يجب أن تحتوي كلمة المرور على حرف إنجليزي صغير.'],
    ['Password must include a number', 'يجب أن تحتوي كلمة المرور على رقم.'],
    ['Password must include a special character', 'يجب أن تحتوي كلمة المرور على رمز خاص مثل ! أو @.'],
    ['Password was used recently', 'تم استخدام كلمة المرور هذه مؤخرًا؛ اختر كلمة مختلفة.'],
    ['New password must differ from the current password', 'يجب أن تختلف كلمة المرور الجديدة عن الحالية.'],
    ['String should have at least 12 characters', 'يجب ألا تقل كلمة المرور عن 12 حرفًا.'],
    ['Method Not Allowed', 'هذه نسخة قديمة من شاشة الاستعادة. افتح رابط الاستعادة الجديد ثم حاول مرة أخرى.'],
    ['Rate limit exceeded', 'تمت محاولات كثيرة. انتظر دقيقة واحدة ثم حاول مجددًا.'],
  ];
  const translated = messages.find(([source]) => raw.includes(source));
  return translated?.[1] || raw || 'تعذر تسجيل الدخول.';
}

export function Login({
  lang,
  setLang,
  onLogin,
}: {
  lang: Lang;
  setLang: (language: Lang) => void;
  onLogin: () => void;
}) {
  const ar = lang === 'ar';
  const Arrow = ar ? ArrowLeft : ArrowRight;
  const recoveryFromUrl = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('recover') || '';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [needsOtp, setNeedsOtp] = useState(false);
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [enrollmentCode, setEnrollmentCode] = useState('');
  const [recoveryToken, setRecoveryToken] = useState(recoveryFromUrl);
  const [recoveryMode, setRecoveryMode] = useState(Boolean(recoveryFromUrl));
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const recoveryChecks = [
    { key: 'length', valid: newPassword.length >= 12, ar: '12 حرفًا على الأقل', en: 'At least 12 characters' },
    { key: 'upper', valid: /[A-Z]/.test(newPassword), ar: 'حرف إنجليزي كبير A–Z', en: 'An uppercase English letter A-Z' },
    { key: 'lower', valid: /[a-z]/.test(newPassword), ar: 'حرف إنجليزي صغير a–z', en: 'A lowercase English letter a-z' },
    { key: 'number', valid: /\d/.test(newPassword), ar: 'رقم واحد على الأقل', en: 'At least one number' },
    { key: 'symbol', valid: /[^A-Za-z0-9]/.test(newPassword), ar: 'رمز خاص مثل ! أو @', en: 'A symbol such as ! or @' },
    { key: 'match', valid: confirmPassword.length > 0 && newPassword === confirmPassword, ar: 'التأكيد مطابق تمامًا', en: 'Confirmation matches exactly' },
  ];
  const recoveryReady = recoveryChecks.every((check) => check.valid);

  function clearRecoveryUrl() {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  }

  async function loginWithCredentials(mfaCode?: string) {
    setLoading(true);
    setError('');
    setNotice('');
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, otp: mfaCode || otp || null }),
      });
      const payload = await response.json().catch(() => ({}));
      const detail = payload.detail as ApiDetail | undefined;
      if (
        response.status === 428
        && typeof detail === 'object'
        && !Array.isArray(detail)
        && detail.enrollment_required
        && detail.secret
        && detail.otpauth_uri
        && detail.enrollment_token
      ) {
        setEnrollment({
          secret: detail.secret,
          otpauthUri: detail.otpauth_uri,
          token: detail.enrollment_token,
        });
        setNeedsOtp(false);
        return;
      }
      if (!response.ok) {
        const message = localizedMessage(detail, ar);
        if (message.includes('رمز الحماية') || message.toLowerCase().includes('mfa')) setNeedsOtp(true);
        throw new Error(message);
      }
      sessionStorage.setItem('corvax_token', payload.access_token);
      localStorage.setItem('corvax_user', JSON.stringify(payload.user));
      onLogin();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : (ar ? 'تعذر تسجيل الدخول.' : 'Login failed.'));
    } finally {
      setLoading(false);
    }
  }

  async function submitLogin(event: React.FormEvent) {
    event.preventDefault();
    await loginWithCredentials();
  }

  async function completeEnrollment(event: React.FormEvent) {
    event.preventDefault();
    if (!enrollment || enrollmentCode.length !== 6) return;
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/v1/auth/mfa/enable-preauth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enrollment_token: enrollment.token, code: enrollmentCode }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(localizedMessage(payload.detail, ar));
      setEnrollment(null);
      setOtp(enrollmentCode);
      await loginWithCredentials(enrollmentCode);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : (ar ? 'تعذر تفعيل الحماية.' : 'Could not enable MFA.'));
    } finally {
      setLoading(false);
    }
  }

  async function submitRecovery(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    setNotice('');
    if (!recoveryReady) {
      const missing = recoveryChecks.filter((check) => !check.valid).map((check) => ar ? check.ar : check.en);
      setError(ar ? `كلمة المرور غير مقبولة بعد: ${missing.join('، ')}.` : `Password is not ready: ${missing.join(', ')}.`);
      return;
    }
    setLoading(true);
    try {
      const response = await fetch('/api/v1/auth/recover-admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: recoveryToken, new_password: newPassword }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const requestId = response.headers.get('X-Request-ID') || '';
        const message = payload.detail !== undefined
          ? localizedMessage(payload.detail, ar)
          : `${ar ? 'فشل داخلي في الخادم' : 'Internal server failure'} (HTTP ${response.status})${requestId ? ` · ${ar ? 'رقم التتبع' : 'Request ID'}: ${requestId}` : ''}.`;
        throw new Error(message);
      }
      setEmail(String(payload.login || 'admin'));
      setPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setRecoveryToken('');
      setRecoveryMode(false);
      clearRecoveryUrl();
      setNotice(ar
        ? 'تم تغيير كلمة المرور وفتح الحساب. أدخل كلمة المرور الجديدة الآن.'
        : 'Password changed and account unlocked. Sign in with the new password.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : (ar ? 'تعذرت استعادة الحساب.' : 'Recovery failed.'));
    } finally {
      setLoading(false);
    }
  }

  function loginPanel() {
    if (recoveryMode) {
      return <>
        <div className="auth-copy">
          <span>{ar ? 'استعادة آمنة لمرة واحدة' : 'ONE-TIME SECURE RECOVERY'}</span>
          <h1>{ar ? 'أنشئ كلمة مرور جديدة' : 'Create a new password'}</h1>
          <p>{ar ? 'سيتم فتح حساب المدير وإلغاء الجلسات القديمة.' : 'The admin account will be unlocked and old sessions revoked.'}</p>
        </div>
        <form onSubmit={submitRecovery}>
          <label>{ar ? 'كلمة المرور الجديدة' : 'New password'}
            <div className="field"><KeyRound size={18}/><input value={newPassword} onChange={(event) => setNewPassword(event.target.value)} type="password" autoComplete="new-password" autoCapitalize="none" spellCheck={false} minLength={12} maxLength={200} required/></div>
          </label>
          <label>{ar ? 'تأكيد كلمة المرور' : 'Confirm password'}
            <div className="field"><LockKeyhole size={18}/><input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} type="password" autoComplete="new-password" autoCapitalize="none" spellCheck={false} minLength={12} maxLength={200} required/></div>
          </label>
          <div className="password-checks" aria-live="polite">
            {recoveryChecks.map((check) => <span key={check.key} className={check.valid ? 'passed' : ''}>
              <b>{check.valid ? '✓' : '○'}</b>{ar ? check.ar : check.en}
            </span>)}
          </div>
          {error && <div className="error">{error}</div>}
          <button className="primary-btn" disabled={loading || !recoveryReady}>{loading ? (ar ? 'جارٍ الحفظ...' : 'Saving...') : (ar ? 'تغيير كلمة المرور وفتح الحساب' : 'Change password and unlock')}<Arrow size={18}/></button>
        </form>
      </>;
    }

    if (enrollment) {
      return <>
        <div className="auth-copy">
          <span>{ar ? 'خطوة حماية مطلوبة' : 'SECURITY STEP REQUIRED'}</span>
          <h1>{ar ? 'فعّل المصادقة الثنائية' : 'Enable two-factor authentication'}</h1>
          <p>{ar ? 'افتح تطبيق كلمات السر أو Google Authenticator وأضف المفتاح التالي.' : 'Open your password manager or authenticator and add this key.'}</p>
        </div>
        <form onSubmit={completeEnrollment}>
          <a className="auth-secondary-action" href={enrollment.otpauthUri}><Smartphone size={17}/>{ar ? 'فتح تطبيق المصادقة' : 'Open authenticator app'}</a>
          <div className="auth-secret" dir="ltr"><code>{enrollment.secret}</code><button type="button" aria-label={ar ? 'نسخ المفتاح' : 'Copy key'} onClick={() => navigator.clipboard?.writeText(enrollment.secret)}><Copy size={16}/></button></div>
          <label>{ar ? 'الرمز المكوّن من 6 أرقام' : '6-digit code'}
            <div className="field"><ShieldCheck size={18}/><input value={enrollmentCode} onChange={(event) => setEnrollmentCode(event.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" pattern="[0-9]{6}" placeholder="000000" required/></div>
          </label>
          {error && <div className="error">{error}</div>}
          <button className="primary-btn" disabled={loading || enrollmentCode.length !== 6}>{loading ? (ar ? 'جارٍ التفعيل...' : 'Enabling...') : (ar ? 'تفعيل ومتابعة الدخول' : 'Enable and sign in')}<Arrow size={18}/></button>
        </form>
      </>;
    }

    return <>
      <div className="auth-copy">
        <span>{ar ? 'الوصول الآمن' : 'SECURE ACCESS'}</span>
        <h1>{ar ? 'مرحبًا بعودتك' : 'Welcome back'}</h1>
        <p>{ar ? 'سجّل الدخول للوصول إلى شركاتك ولوحات العمل.' : 'Sign in to access your companies and workspaces.'}</p>
      </div>
      <form onSubmit={submitLogin}>
        <label>{ar ? 'اسم المستخدم أو البريد' : 'Username or email'}
          <div className="field"><Mail size={18}/><input value={email} onChange={(event) => setEmail(event.target.value)} type="text" autoComplete="username" required/></div>
        </label>
        <label>{ar ? 'كلمة المرور' : 'Password'}
          <div className="field"><LockKeyhole size={18}/><input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required/></div>
        </label>
        {needsOtp && <label>{ar ? 'رمز المصادقة الثنائية' : 'MFA code'}
          <div className="field"><ShieldCheck size={18}/><input value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" pattern="[0-9]{6}" placeholder="000000" required/></div>
        </label>}
        {notice && <div className="notice">{notice}</div>}
        {error && <div className="error">{error}</div>}
        <button className="primary-btn" disabled={loading}>{loading ? (ar ? 'جارٍ الدخول...' : 'Signing in...') : (ar ? 'دخول إلى مساحة العمل' : 'Enter workspace')}<Arrow size={18}/></button>
      </form>
    </>;
  }

  return <main className="auth-page" dir={ar ? 'rtl' : 'ltr'}>
    <button className="auth-lang" onClick={() => setLang(ar ? 'en' : 'ar')}><Languages size={17}/>{ar ? 'English' : 'العربية'}</button>
    <aside className="auth-showcase">
      <div className="auth-brand"><div className="corvax-symbol"><span>C</span></div><div><strong>CORVAX</strong><small>THE CORE BUSINESS PLATFORM</small></div></div>
      <div className="showcase-copy"><span>{ar ? 'منصة أعمال مؤسسية متكاملة' : 'Unified enterprise business platform'}</span><h2>{ar ? 'شغّل أعمالك من مركز قيادة واحد.' : 'Run your business from one command center.'}</h2><p>{ar ? 'المالية والمبيعات والتشغيل والموارد البشرية والحوكمة—مسار بيانات واحد وقرار أسرع.' : 'Finance, sales, operations, people and governance—one data path for faster decisions.'}</p></div>
      <div className="showcase-preview" aria-hidden="true"><div className="preview-rail"><b>C</b><i/><i/><i/></div><div className="preview-canvas"><div className="preview-bar"><span/><em/></div><div className="preview-title"><strong/><small/></div><div className="preview-kpis"><i/><i/><i/></div><div className="preview-chart"><span/><svg viewBox="0 0 240 64" preserveAspectRatio="none"><polyline points="0,52 35,41 70,46 105,25 140,34 180,12 215,18 240,5"/></svg></div></div></div>
      <div className="showcase-metrics"><article><strong>121+</strong><span>{ar ? 'جدول مترابط' : 'connected tables'}</span></article><article><strong>26</strong><span>{ar ? 'محرك أعمال' : 'business engines'}</span></article><article><strong>AR / EN</strong><span>{ar ? 'ثنائي اللغة' : 'bilingual'}</span></article></div>
      <div className="showcase-security"><ShieldCheck size={18}/><span>{ar ? 'صلاحيات مؤسسية · MFA · سجل تدقيق' : 'Enterprise access · MFA · Audit trail'}</span></div>
    </aside>
    <section className="auth-card">
      <div className="brand large mobile-auth-brand"><div className="corvax-symbol"><span>C</span></div><div><strong>CORVAX</strong><span>THE CORE BUSINESS PLATFORM</span></div></div>
      {loginPanel()}
      <div className="demo-note"><ShieldCheck size={15}/>{ar ? 'جلسة مشفرة ومحمية بالمصادقة الثنائية' : 'Encrypted session with MFA protection'}</div>
    </section>
  </main>;
}
