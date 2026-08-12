import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import {createPortal} from 'react-dom';
import type {
  CorvaxAiAssistantProps,
  CorvaxAiMessage,
  CorvaxAiMode,
} from './ai-assistant.types';

type Copy = {
  title: string;
  readonly: string;
  company: string;
  screen: string;
  sources: string;
  limitation: string;
  confidence: string;
  high: string;
  medium: string;
  low: string;
  checking: string;
  placeholder: string;
  composerLabel: string;
  disclaimer: string;
  send: string;
  open: string;
  close: string;
  launcher: string;
  suggested: string;
};

const COPY: Record<'ar' | 'en', Copy> = {
  ar: {
    title: 'مساعد كورفاكس الذكي',
    readonly: 'قراءة فقط',
    company: 'الشركة',
    screen: 'الشاشة الحالية',
    sources: 'المصادر',
    limitation: 'حدود الإجابة',
    confidence: 'ثقة المصدر',
    high: 'مرتفعة',
    medium: 'متوسطة',
    low: 'منخفضة',
    checking: 'جارٍ التحقق من المصادر والصلاحيات…',
    placeholder: 'اسأل عن النظام أو البيانات المسموح بها…',
    composerLabel: 'اكتب سؤالك',
    disclaimer: 'لن ينفذ المساعد أي اعتماد أو تعديل.',
    send: 'إرسال',
    open: 'فتح مساعد كورفاكس',
    close: 'إغلاق مساعد كورفاكس',
    launcher: 'اسأل عن النظام',
    suggested: 'أسئلة مقترحة',
  },
  en: {
    title: 'CORVAX AI Assistant',
    readonly: 'Read only',
    company: 'Company',
    screen: 'Current screen',
    sources: 'Sources',
    limitation: 'Limitations',
    confidence: 'Source confidence',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
    checking: 'Checking sources and permissions…',
    placeholder: 'Ask about CORVAX or data you are allowed to view…',
    composerLabel: 'Type your question',
    disclaimer: 'The assistant cannot approve, post, edit, or delete.',
    send: 'Send',
    open: 'Open CORVAX Assistant',
    close: 'Close CORVAX Assistant',
    launcher: 'Ask about CORVAX',
    suggested: 'Suggested questions',
  },
};

const MODE_LABELS: Record<CorvaxAiMode, Record<'ar' | 'en', { title: string; sub: string; hint: string }>> = {
  help: {
    ar: { title: 'شرح النظام', sub: 'Help', hint: 'شرح الشاشة والخطوات ورسائل الخطأ' },
    en: { title: 'System help', sub: 'Help', hint: 'Explain screens, steps, and error messages' },
  },
  data: {
    ar: { title: 'بيانات الشركة', sub: 'Data', hint: 'استعلامات قراءة فقط ضمن صلاحياتك' },
    en: { title: 'Company data', sub: 'Data', hint: 'Read-only queries within your permissions' },
  },
  analysis: {
    ar: { title: 'التحليل', sub: 'Analysis', hint: 'تفسير المؤشرات والفروقات والمخاطر' },
    en: { title: 'Analysis', sub: 'Analysis', hint: 'Explain indicators, variances, and risks' },
  },
};

const QUICK_PROMPTS: Record<CorvaxAiMode, Record<'ar' | 'en', string[]>> = {
  help: {
    ar: ['اشرح هذه الشاشة', 'لماذا لا يمكن ترحيل المستند؟', 'أين أجد تقرير أعمار الديون؟'],
    en: ['Explain this screen', 'Why can this document not be posted?', 'Where is the aging report?'],
  },
  data: {
    ar: ['ما المستندات المعلقة؟', 'لخص مبيعات الشهر الحالي', 'ما الأصناف تحت حد إعادة الطلب؟'],
    en: ['Which documents are pending?', 'Summarize current-month sales', 'Which items are below reorder level?'],
  },
  analysis: {
    ar: ['حلل المخاطر المفتوحة', 'اشرح انحراف المبيعات', 'ما الذي يحتاج انتباهًا اليوم؟'],
    en: ['Analyze open risks', 'Explain the sales variance', 'What needs attention today?'],
  },
};

function SourceList({ message, locale }: { message: CorvaxAiMessage; locale: 'ar' | 'en' }) {
  if (!message.sources?.length) return null;
  const copy = COPY[locale];
  return (
    <div className="corvax-ai-sources" aria-label={copy.sources}>
      <span className="corvax-ai-sources__label">{copy.sources}</span>
      <div className="corvax-ai-sources__items">
        {message.sources.map((source) => (
          <div className="corvax-ai-source" key={source.id} role="note">
            <span aria-hidden="true">✓</span>
            <span>
              <strong>{source.title}</strong>
              <small>{source.reference ?? source.type}</small>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CorvaxAiAssistant({
  open,
  mode,
  context,
  messages,
  busy = false,
  onOpenChange,
  onModeChange,
  onSend,
}: CorvaxAiAssistantProps) {
  const [draft, setDraft] = useState('');
  const titleId = useId();
  const panelRef = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const launcherRef = useRef<HTMLButtonElement | null>(null);
  const locale = context.locale;
  const copy = COPY[locale];

  const closePanel = () => {
    onOpenChange(false);
    window.setTimeout(() => launcherRef.current?.focus(), 0);
  };

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closePanel();
        return;
      }
      if (event.key !== 'Tab' || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute('hidden'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  });

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const value = draft.trim();
    if (!value || busy) return;
    onSend(value);
    setDraft('');
  };

  const handleComposerKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const assistant = (
    <div className={`corvax-ai ${open ? 'is-open' : ''}`} dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <button
        ref={launcherRef}
        type="button"
        className="corvax-ai-launcher"
        aria-expanded={open}
        aria-controls="corvax-ai-panel"
        aria-haspopup="dialog"
        aria-label={open ? copy.close : copy.open}
        title={open ? copy.close : copy.open}
        onClick={() => (open ? closePanel() : onOpenChange(true))}
      >
        <span className="corvax-ai-launcher__mark" aria-hidden="true">C</span>
        <span className="corvax-ai-launcher__copy">
          <strong>CORVAX AI</strong>
          <small>{copy.launcher}</small>
        </span>
      </button>

      {open && (
        <button className="corvax-ai-backdrop" type="button" aria-label={copy.close} onClick={closePanel} />
      )}

      {/* Do not use the sidebar semantic element here. The dashboard sidebar is intentionally
          styled through broad `.dash aside` selectors; reusing that element
          for this dialog makes those high-specificity layout rules turn the
          assistant into a second full-height sidebar when it opens. */}
      <section
        ref={panelRef}
        id="corvax-ai-panel"
        className="corvax-ai-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-hidden={!open}
      >
        <div className="corvax-ai-header">
          <div className="corvax-ai-brand">
            <span className="corvax-ai-brand__mark" aria-hidden="true">C</span>
            <span>
              <strong id={titleId}>{copy.title}</strong>
              <small>CORVAX AI Assistant</small>
            </span>
          </div>
          <div className="corvax-ai-header__actions">
            <span className="corvax-ai-readonly"><i />{copy.readonly}</span>
            <button type="button" className="corvax-ai-icon-button" aria-label={copy.close} onClick={closePanel}>×</button>
          </div>
        </div>

        <section className="corvax-ai-context" aria-label={locale === 'ar' ? 'سياق الاستعلام' : 'Query context'}>
          <div><span>{copy.company}</span><strong>{context.companyName}</strong></div>
          <div><span>{copy.screen}</span><strong>{context.module} · {context.screen}</strong></div>
          {context.documentReference && <span className="corvax-ai-context__document">#{context.documentReference}</span>}
        </section>

        <div className="corvax-ai-modes" role="group" aria-label={locale === 'ar' ? 'أوضاع المساعد' : 'Assistant modes'}>
          {(Object.keys(MODE_LABELS) as CorvaxAiMode[]).map((item) => (
            <button
              key={item}
              type="button"
              className={mode === item ? 'is-active' : ''}
              aria-pressed={mode === item}
              onClick={() => onModeChange(item)}
            >
              <strong>{MODE_LABELS[item][locale].title}</strong>
              <small>{MODE_LABELS[item][locale].sub}</small>
            </button>
          ))}
        </div>

        <div className="corvax-ai-mode-hint">{MODE_LABELS[mode][locale].hint}</div>

        <section className="corvax-ai-thread" aria-live="polite" aria-busy={busy}>
          {messages.map((message) => (
            <article key={message.id} className={`corvax-ai-message is-${message.role}`}>
              {message.role === 'assistant' && <span className="corvax-ai-avatar" aria-hidden="true">C</span>}
              <div className="corvax-ai-bubble">
                <p>{message.text}</p>
                {message.limitation && (
                  <div className="corvax-ai-limitation"><strong>{copy.limitation}:</strong> {message.limitation}</div>
                )}
                <SourceList message={message} locale={locale} />
                {message.role === 'assistant' && message.confidence && (
                  <span className={`corvax-ai-confidence is-${message.confidence}`}>
                    {copy.confidence}: {copy[message.confidence]}
                  </span>
                )}
              </div>
            </article>
          ))}
          {busy && <div className="corvax-ai-typing" role="status"><i /><i /><i /><span>{copy.checking}</span></div>}
        </section>

        <section className="corvax-ai-quick" aria-label={copy.suggested}>
          {QUICK_PROMPTS[mode][locale].map((prompt) => (
            <button key={prompt} type="button" onClick={() => onSend(prompt)}>{prompt}</button>
          ))}
        </section>

        <form className="corvax-ai-composer" onSubmit={submit}>
          <textarea
            ref={inputRef}
            rows={2}
            maxLength={2000}
            value={draft}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setDraft(event.target.value)}
            onKeyDown={handleComposerKey}
            placeholder={copy.placeholder}
            aria-label={copy.composerLabel}
          />
          <div className="corvax-ai-composer__footer">
            <span>{copy.disclaimer}</span>
            <button type="submit" disabled={!draft.trim() || busy}>{copy.send} <span aria-hidden="true">←</span></button>
          </div>
        </form>
      </section>
    </div>
  );

  // The launcher is mounted inside the sticky dashboard header. That header
  // uses backdrop-filter, which creates a containing block for fixed children
  // in Chromium. Without a portal the full-screen overlay is therefore clipped
  // to the header and the panel collapses into a thin strip. Mounting at body
  // level keeps the dialog viewport-fixed regardless of its visual trigger.
  return createPortal(assistant, document.body);
}

export default CorvaxAiAssistant;
