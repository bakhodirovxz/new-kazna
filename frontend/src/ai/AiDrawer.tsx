import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, isApiError } from '../api/client';
import type { MenuOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { formatDateTime, periodInline } from '../i18n/format';
import { useBranches, usePeriods } from '../meta/api';
import type { SectionRoute } from '../router/hash';
import { flattenMenu } from '../shell/sectionMeta';
import { Button } from '../ui/Button';
import { Drawer } from '../ui/Drawer';
import { AiAnswer } from './answer';
import './ai.css';
import { streamAnalysis, type AiRequestBody } from './stream';

const CLIENT_TIMEOUT_MS = 65_000; // server 60 s + tarmoq zaxirasi
const PRESETS: ReadonlyArray<{ id: string; key: MessageKey }> = [
  { id: 'yoy', key: 'ai.preset.yoy' },
  { id: 'risks', key: 'ai.preset.risks' },
  { id: 'priorities', key: 'ai.preset.priorities' },
  { id: 'plan', key: 'ai.preset.plan' },
];

type Phase =
  | { kind: 'idle' }
  | { kind: 'streaming' }
  | { kind: 'done' }
  | { kind: 'error'; message: string }
  | { kind: 'limit'; message: string }
  | { kind: 'cancelled' }
  | { kind: 'disabled' };

function nextAttempt(seconds: number): string {
  return formatDateTime(new Date(Date.now() + seconds * 1000)).slice(-5);
}

export interface AiDrawerProps {
  menu: MenuOut;
  route: SectionRoute;
  onClose(): void;
}

export function AiDrawer({ menu, route, onClose }: AiDrawerProps) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [text, setText] = useState('');
  const [question, setQuestion] = useState('');
  const controllerRef = useRef<AbortController | null>(null);
  const timedOut = useRef(false);
  const periods = usePeriods();
  const branches = useBranches();

  useEffect(() => () => controllerRef.current?.abort(), []);

  const section = flattenMenu(menu).find((s) => s.id === route.section);
  const pageTitle = section?.pages.find((p) => p.id === route.page)?.title ?? '';
  const per = route.per ?? periods.data?.default ?? 'ytd';
  const branchName = route.br === null ? t('filters.allBranches') : (branches.data?.find((b) => b.id === route.br)?.name ?? String(route.br));
  const periodLabel = periods.data?.items.find((p) => p.code === per)?.label ?? per;
  const streaming = phase.kind === 'streaming';

  async function run(extra: { preset?: string; question?: string }) {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    timedOut.current = false;
    setText('');
    setPhase({ kind: 'streaming' });
    const body: AiRequestBody = {
      section: route.section,
      page: route.page ?? section?.pages[0]?.id ?? 'svod',
      br: route.br,
      per,
      ...extra,
    };
    const timer = window.setTimeout(() => {
      timedOut.current = true;
      controller.abort();
    }, CLIENT_TIMEOUT_MS);
    try {
      await streamAnalysis(
        body,
        (event) => {
          if (event.type === 'delta') setText((prev) => prev + event.text);
          else if (event.type === 'done') setPhase({ kind: 'done' });
          else if (event.type === 'error') {
            setText('');
            setPhase({ kind: 'error', message: event.message });
          }
        },
        controller.signal,
      );
      if (controller.signal.aborted) {
        setPhase(timedOut.current ? { kind: 'error', message: t('ai.error.timeout') } : { kind: 'cancelled' });
        return;
      }
      setPhase((p) => (p.kind === 'streaming' ? { kind: 'error', message: t('ai.error.interrupted') } : p));
    } catch (error) {
      if (controller.signal.aborted) {
        setPhase(timedOut.current ? { kind: 'error', message: t('ai.error.timeout') } : { kind: 'cancelled' });
      } else if (isApiError(error, 429)) {
        const key: MessageKey = error.params.scope === 'org' ? 'ai.limit.org' : 'ai.limit.user';
        setPhase({ kind: 'limit', message: t(key, { time: nextAttempt(error.retryAfter ?? 60) }) });
      } else if (isApiError(error, 404, 'ai_disabled')) {
        setPhase({ kind: 'disabled' });
      } else {
        setPhase({ kind: 'error', message: error instanceof ApiError ? error.message : t('error.generic') });
      }
    } finally {
      window.clearTimeout(timer);
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }

  const ask = (event: FormEvent) => {
    event.preventDefault();
    const q = question.trim();
    if (q) void run({ question: q });
  };

  return (
    <Drawer open onClose={onClose} title={t('ai.title')}>
      <div className="ai">
        <p className="note">{`${section?.title ?? ''}: ${pageTitle}. ${branchName}, ${periodInline(periodLabel)}`}</p>
        <div className="ai-out" aria-live="polite" aria-busy={streaming}>
          {phase.kind === 'idle' ? <p>{t('ai.intro')}</p> : null}
          {streaming && text === '' ? <p className="note">{t('ai.thinking')}</p> : null}
          {text ? <AiAnswer text={text} /> : null}
          {phase.kind === 'error' || phase.kind === 'limit' ? <p className="form-error" role="alert">{phase.message}</p> : null}
          {phase.kind === 'cancelled' ? <p className="note">{t('ai.cancelled')}</p> : null}
          {phase.kind === 'disabled' ? <p className="note">{t('ai.disabled')}</p> : null}
        </div>
        <div className="ai-presets" role="group" aria-label={t('ai.presets')}>
          {PRESETS.map((p) => (
            <button key={p.id} type="button" className="ai-chip" disabled={streaming} onClick={() => void run({ preset: p.id })}>
              {t(p.key)}
            </button>
          ))}
        </div>
        <form className="ai-ask" onSubmit={ask}>
          <input
            className="input"
            type="search"
            maxLength={500}
            aria-label={t('ai.question')}
            placeholder={t('ai.question')}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <Button type="submit" variant="secondary" disabled={streaming || question.trim() === ''}>
            {t('ai.ask')}
          </Button>
        </form>
        <div className="ai-actions">
          <Button onClick={() => void run({})} disabled={streaming}>
            {t('ai.run')}
          </Button>
          {streaming ? (
            <Button variant="secondary" onClick={() => controllerRef.current?.abort()}>
              {t('ai.cancel')}
            </Button>
          ) : null}
        </div>
        <p className="note ai-disclaimer">{t('ai.disclaimer')}</p>
      </div>
    </Drawer>
  );
}
