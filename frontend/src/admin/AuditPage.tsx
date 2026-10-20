import { useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { AuditOut } from '../api/types';
import { t } from '../i18n';
import { formatDateTime, formatNumber } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { FormError, TextInput } from '../ui/Field';
import { Icon } from '../ui/icons';
import { Modal } from '../ui/Modal';
import { Pagination } from '../ui/Pagination';
import { Select } from '../ui/Select';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import {
  AUDIT_EXPORT_LIMIT,
  AUDIT_PAGE_SIZE,
  EMPTY_AUDIT_FILTERS,
  useAudit,
  useExportAudit,
  useVerifyAudit,
  type AuditFilters,
} from './api';
import { auditResult } from './labels';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const ACTION_RE = /^[a-z_.]*$/;
const USER_ID_RE = /^[1-9]\d{0,8}$/; // backend: user_id > 0
const BAD_IDS_SHOWN = 50;

/** 429 — qayta urinish vaqti bilan; qolgan xatolarda faqat sanitarlangan `message`. */
function OpError({ error }: { error: unknown }) {
  if (!error) return null;
  if (!isApiError(error, 429)) return <FormError error={error} />;
  return (
    <p className="form-error" role="alert">
      <Icon name="alert" />
      <span>{t('error.rateLimited', { seconds: error.retryAfter ?? 60 })}</span>
    </p>
  );
}

/** Blob -> vaqtinchalik URL -> yuklab olish -> URL biroz kechikib bekor qilinadi. Fayl nomi mijozda yasaladi (serverga ishonilmaydi). */
function saveBlob(blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `audit_${new Date().toISOString().slice(0, 16).replace(/[-:]/g, '').replace('T', '_')}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000); // Firefox/Safari yuklashni darhol boshlamasligi mumkin
}

function objectText(row: AuditOut): string {
  if (!row.object_type && !row.object_id) return t('common.dash');
  return [row.object_type, row.object_id].filter(Boolean).join(':');
}

function userText(row: AuditOut): string {
  if (row.username) return row.username;
  return row.user_id === null ? t('common.dash') : `#${row.user_id}`;
}

export default function AuditPage() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_AUDIT_FILTERS);
  const [applied, setApplied] = useState<AuditFilters>(EMPTY_AUDIT_FILTERS);
  const [errors, setErrors] = useState<{ action?: string; userId?: string; to?: string }>({});
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<AuditOut | null>(null);
  const audit = useAudit(applied, page);
  const verify = useVerifyAudit();
  const exportCsv = useExportAudit();
  const [truncated, setTruncated] = useState(false);
  const formRef = useFocusFirstInvalid(errors);

  const set = <K extends keyof AuditFilters>(key: K, value: AuditFilters[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const apply = (event: FormEvent) => {
    event.preventDefault();
    const found: typeof errors = {};
    const action = draft.action.trim();
    if (!ACTION_RE.test(action)) found.action = t('audit.actionRule');
    if (draft.userId && !USER_ID_RE.test(draft.userId)) found.userId = t('audit.userIdRule');
    if (draft.from && draft.to && draft.from > draft.to) found.to = t('audit.dateOrder');
    setErrors(found);
    if (found.action || found.userId || found.to) return;
    setApplied({ ...draft, action });
    setPage(1);
  };

  const reset = () => {
    setDraft(EMPTY_AUDIT_FILTERS);
    setApplied(EMPTY_AUDIT_FILTERS);
    setErrors({});
    setPage(1);
  };

  const download = () =>
    exportCsv.mutate(applied, {
      onSuccess: ({ blob, truncated: cut }) => {
        setTruncated(cut);
        saveBlob(blob);
      },
    });

  const columns: Column<AuditOut>[] = [
    { key: 'time', header: t('audit.col.time'), align: 'left', cell: (r) => formatDateTime(r.ts) },
    { key: 'user', header: t('audit.col.user'), align: 'left', cell: userText },
    { key: 'action', header: t('audit.col.action'), align: 'left', cell: (r) => <span className="mono">{r.action}</span> },
    {
      key: 'result',
      header: t('audit.col.result'),
      align: 'left',
      cell: (r) => {
        const result = auditResult(r.result);
        return <Badge tone={result.tone}>{result.label}</Badge>;
      },
    },
    { key: 'object', header: t('audit.col.object'), align: 'left', cell: objectText },
    { key: 'ip', header: t('audit.col.ip'), align: 'left', cell: (r) => r.ip ?? t('common.dash') },
    { key: 'request', header: t('audit.col.request'), align: 'left', cell: (r) => <small className="mono">{r.request_id ?? t('common.dash')}</small> },
  ];

  const result = verify.data;

  return (
    <>
      <Card title={t('audit.filters')} sub={t('audit.defaultWindow')}>
        <form ref={formRef} className="toolbar" noValidate onSubmit={apply}>
          <TextInput type="date" label={t('audit.from')} value={draft.from} onChange={(e) => set('from', e.target.value)} />
          <TextInput type="date" label={t('audit.to')} value={draft.to} error={errors.to} onChange={(e) => set('to', e.target.value)} />
          <TextInput
            label={t('audit.userId')}
            inputMode="numeric"
            maxLength={9}
            value={draft.userId}
            error={errors.userId}
            onChange={(e) => set('userId', e.target.value.trim())}
          />
          <TextInput
            label={t('audit.action')}
            placeholder={t('audit.actionPlaceholder')}
            autoCapitalize="none"
            maxLength={64}
            spellCheck={false}
            value={draft.action}
            error={errors.action}
            onChange={(e) => set('action', e.target.value)}
          />
          <Select
            label={t('audit.result')}
            value={draft.result}
            options={[
              { value: '', label: t('audit.result.all') },
              { value: 'ok', label: t('audit.result.ok') },
              { value: 'fail', label: t('audit.result.fail') },
              { value: 'denied', label: t('audit.result.denied') },
            ]}
            onChange={(value) => set('result', value === 'ok' || value === 'fail' || value === 'denied' ? value : '')}
          />
          <Button type="submit" icon="filter">
            {t('audit.apply')}
          </Button>
          <Button variant="secondary" onClick={reset}>
            {t('audit.reset')}
          </Button>
        </form>
      </Card>
      <Card
        title={t('admin.page.audit')}
        actions={
          <>
            <Button variant="secondary" icon="download" loading={exportCsv.isPending} onClick={download}>
              {t('audit.export')}
            </Button>
            <Button variant="secondary" icon="shield" loading={verify.isPending} onClick={() => verify.mutate()}>
              {t('audit.verify')}
            </Button>
          </>
        }
      >
        <OpError error={verify.error} />
        <OpError error={exportCsv.error} />
        {truncated && exportCsv.isSuccess ? (
          <p className="note" role="status">
            {t('audit.exportTruncated', { count: formatNumber(AUDIT_EXPORT_LIMIT) })}
          </p>
        ) : null}
        {result ? (
          result.ok ? (
            <p className="result result--ok" role="status">
              <Icon name="check" />
              <span>{t('audit.verifyOk', { count: formatNumber(result.checked) })}</span>
            </p>
          ) : (
            <div className="result result--bad" role="alert">
              <Icon name="alert" />
              <div>
                <p>{t('audit.verifyBad', { id: result.first_bad_id ?? '—' })}</p>
                {result.bad_ids.length > 0 ? (
                  <p>
                    {t('audit.verifyBadIds', { ids: result.bad_ids.slice(0, BAD_IDS_SHOWN).join(', ') })}
                    {result.bad_ids.length > BAD_IDS_SHOWN
                      ? ` ${t('audit.verifyMore', { count: formatNumber(result.bad_ids.length - BAD_IDS_SHOWN) })}`
                      : ''}
                  </p>
                ) : null}
              </div>
            </div>
          )
        ) : null}
        {audit.isError ? (
          <ErrorBanner error={audit.error} lastSuccessAt={audit.dataUpdatedAt} onRetry={() => void audit.refetch()} />
        ) : audit.isPending ? (
          <PageSkeleton />
        ) : (
          <>
            <Table
              caption={t('admin.page.audit')}
              columns={columns}
              rows={audit.data.items}
              rowKey={(r) => r.id}
              onRowClick={(r) => setOpen(r)}
              empty={t('audit.empty')}
            />
            <Pagination page={page} pageSize={AUDIT_PAGE_SIZE} total={audit.data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {open ? (
        <Modal open onClose={() => setOpen(null)} title={t('audit.detailTitle', { id: open.id })} note={formatDateTime(open.ts)}>
          <dl className="dl">
            <dt>{t('audit.col.user')}</dt>
            <dd>{userText(open)}</dd>
            <dt>{t('audit.col.action')}</dt>
            <dd className="mono">{open.action}</dd>
            <dt>{t('audit.col.result')}</dt>
            <dd>{auditResult(open.result).label}</dd>
            <dt>{t('audit.col.object')}</dt>
            <dd>{objectText(open)}</dd>
            <dt>{t('audit.col.ip')}</dt>
            <dd>{open.ip ?? t('common.dash')}</dd>
            <dt>{t('audit.col.request')}</dt>
            <dd className="mono">{open.request_id ?? t('common.dash')}</dd>
          </dl>
          <h3>{t('audit.details')}</h3>
          <pre className="details">{JSON.stringify(open.details, null, 2)}</pre>
        </Modal>
      ) : null}
    </>
  );
}
