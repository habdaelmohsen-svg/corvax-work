import { useEffect, useMemo, useState } from 'react';
import { CorvaxAiAssistant } from './CorvaxAiAssistant';
import type {
  CorvaxAiApiResponse,
  CorvaxAiMessage,
  CorvaxAiMode,
  CorvaxAiScreenContext,
} from './ai-assistant.types';

type Lang = 'ar' | 'en';
type StoredCompany = {
  apiId?: number;
  id?: string | number;
  name_ar?: string;
  name_en?: string;
  branchId?: number;
  branchName?: string;
};

const INITIAL: Record<Lang, string> = {
  ar: 'يمكنني شرح CORVAX والاستعلام عن البيانات المسموح بها. الإجابات قراءة فقط وتظهر مصادرها وحدودها.',
  en: 'I can explain CORVAX and query data you are allowed to view. Answers are read-only and include sources and limitations.',
};

function parseStoredCompany(): StoredCompany | null {
  try {
    const raw = localStorage.getItem('corvax_company');
    return raw ? (JSON.parse(raw) as StoredCompany) : null;
  } catch {
    return null;
  }
}

function currentScreen(): { module: string; screen: string } {
  const normalized = window.location.hash.replace(/^#\/?/, '').split('?')[0] || 'dashboard';
  const parts = normalized.split('/').filter(Boolean);
  return { module: parts[0] || 'dashboard', screen: parts.join('/') || 'dashboard' };
}

function makeId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return `${prefix}-${crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function CorvaxAiAssistantHost({ lang }: { lang: Lang }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<CorvaxAiMode>('help');
  const [busy, setBusy] = useState(false);
  const [route, setRoute] = useState(currentScreen);
  const [messages, setMessages] = useState<CorvaxAiMessage[]>([
    { id: 'welcome', role: 'assistant', text: INITIAL[lang], confidence: 'high' },
  ]);
  const company = useMemo(parseStoredCompany, [open]);

  useEffect(() => {
    const sync = () => setRoute(currentScreen());
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);

  useEffect(() => {
    setMessages((current) => {
      if (current.length !== 1 || current[0].id !== 'welcome') return current;
      return [{ ...current[0], text: INITIAL[lang] }];
    });
  }, [lang]);

  useEffect(() => {
    document.documentElement.classList.toggle('corvax-ai-open', open);
    return () => document.documentElement.classList.remove('corvax-ai-open');
  }, [open]);

  if (!company) return null;
  const companyId = Number(company.apiId);
  if (!Number.isInteger(companyId) || companyId <= 0) return null;

  const context: CorvaxAiScreenContext = {
    companyId,
    companyName: lang === 'ar' ? company.name_ar ?? company.name_en ?? `#${companyId}` : company.name_en ?? company.name_ar ?? `#${companyId}`,
    branchId: company.branchId,
    branchName: company.branchName,
    module: route.module,
    screen: route.screen,
    locale: lang,
    readOnly: true,
  };

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    const userMessage: CorvaxAiMessage = { id: makeId('user'), role: 'user', text: trimmed };
    setMessages((current) => [...current, userMessage]);
    setBusy(true);
    try {
      const token = sessionStorage.getItem('corvax_token');
      if (!token) throw new Error(lang === 'ar' ? 'انتهت جلسة الدخول.' : 'The login session has expired.');
      const response = await fetch('/api/v1/ai-assistant/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          company_id: companyId,
          branch_id: context.branchId ?? null,
          mode,
          message: trimmed,
          locale: lang,
          screen_context: {
            module: context.module,
            screen: context.screen,
            document_reference: context.documentReference ?? null,
          },
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as Partial<CorvaxAiApiResponse> & { detail?: unknown };
      if (!response.ok) {
        const rawDetail = payload.detail;
        const detail = typeof rawDetail === 'string'
          ? rawDetail
          : rawDetail && typeof rawDetail === 'object' && 'message' in rawDetail
            ? String((rawDetail as {message: unknown}).message)
            : lang === 'ar'
              ? 'تعذر تنفيذ الاستعلام ضمن الصلاحيات الحالية.'
              : 'The query could not be completed within the current permissions.';
        throw new Error(detail);
      }
      const result = payload as CorvaxAiApiResponse;
      setMessages((current) => [...current, {
        id: result.message_id || makeId('assistant'),
        role: 'assistant',
        text: result.answer,
        confidence: result.confidence,
        limitation: result.limitations?.join(lang === 'ar' ? '، ' : '; '),
        sources: result.sources?.map((source, index) => ({
          id: `${result.message_id || 'source'}-${index}`,
          title: source.title,
          type: source.type,
          reference: source.reference,
          updatedAt: source.updated_at ?? undefined,
        })),
      }]);
    } catch (error) {
      const text = error instanceof Error ? error.message : (lang === 'ar' ? 'حدث خطأ غير متوقع.' : 'An unexpected error occurred.');
      setMessages((current) => [...current, {
        id: makeId('error'),
        role: 'assistant',
        text,
        confidence: 'low',
        limitation: lang === 'ar' ? 'لم يتم إرجاع بيانات من النظام.' : 'No system data was returned.',
      }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <CorvaxAiAssistant
      open={open}
      mode={mode}
      context={context}
      messages={messages}
      busy={busy}
      onOpenChange={setOpen}
      onModeChange={setMode}
      onSend={send}
    />
  );
}
