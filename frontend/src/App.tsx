import { useEffect, useState } from 'react';
import { Login } from './components/Login';
import { ForcePasswordChange } from './dashboard/usersPage';
import { CompanySelector } from './components/CompanySelector';
import { Dashboard } from './components/Dashboard';
import { CorvaxThemeProvider } from './theme/CorvaxThemeProvider';

type Lang = 'ar' | 'en';
type Screen = 'login' | 'password' | 'company' | 'dashboard';

const LEGACY_KEYS = {
  token: 'nexora_token',
  user: 'nexora_user',
  company: 'nexora_company',
};
const CORVAX_KEYS = {
  token: 'corvax_token',
  user: 'corvax_user',
  company: 'corvax_company',
};

function migrateLegacyBrowserSession() {
  Object.entries(LEGACY_KEYS).forEach(([key, legacyKey]) => {
    const currentKey = CORVAX_KEYS[key as keyof typeof CORVAX_KEYS];
    if (!localStorage.getItem(currentKey) && localStorage.getItem(legacyKey)) {
      localStorage.setItem(currentKey, localStorage.getItem(legacyKey) as string);
    }
    localStorage.removeItem(legacyKey);
  });
}

export default function App() {
  migrateLegacyBrowserSession();
  const [lang, setLang] = useState<Lang>('ar');
  const [screen, setScreen] = useState<Screen>(() => {
    const hasToken = Boolean(sessionStorage.getItem(CORVAX_KEYS.token));
    const hasCompany = Boolean(localStorage.getItem(CORVAX_KEYS.company));
    return hasToken ? (hasCompany ? 'dashboard' : 'company') : 'login';
  });

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  }, [lang]);

  let content;
  if (screen === 'login') {
    content = <Login lang={lang} setLang={setLang} onLogin={() => {
      // H17: a temporary password must be replaced before anything else.
      try {
        const raw = localStorage.getItem(CORVAX_KEYS.user);
        if (raw && JSON.parse(raw)?.require_password_change) { setScreen('password'); return; }
      } catch { /* fall through to the normal flow */ }
      setScreen('company');
    }} />;
  } else if (screen === 'password') {
    content = <ForcePasswordChange ar={lang === 'ar'} onDone={() => {
      try {
        const raw = localStorage.getItem(CORVAX_KEYS.user);
        if (raw) {
          const u = JSON.parse(raw);
          u.require_password_change = false;
          localStorage.setItem(CORVAX_KEYS.user, JSON.stringify(u));
        }
      } catch { /* ignore */ }
      setScreen('company');
    }} />;
  } else if (screen === 'company') {
    content = <CompanySelector lang={lang} setLang={setLang} onContinue={(company: unknown) => {
      localStorage.setItem(CORVAX_KEYS.company, JSON.stringify(company));
      setScreen('dashboard');
    }} />;
  } else {
    content = <Dashboard
      lang={lang}
      setLang={setLang}
      onChangeCompany={() => setScreen('company')}
      onLogout={() => {
        sessionStorage.removeItem(CORVAX_KEYS.token);
        Object.values(CORVAX_KEYS).filter(key => key !== CORVAX_KEYS.token).forEach(key => localStorage.removeItem(key));
        setScreen('login');
      }}
    />;
  }
  return <CorvaxThemeProvider lang={lang}>{content}</CorvaxThemeProvider>;
}
