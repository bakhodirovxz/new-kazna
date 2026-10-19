import { useEffect, useState, type FormEvent } from 'react';
import type { EtlErrorOut, EtlRunOut, EtlStepOut } from '../api/types';
import { t } from '../i18n';
import { formatDate, formatDateTime, formatDuration, formatNumber } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { FormError } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { Pagination } from '../ui/Pagination';
import { Select } from '../ui/Select';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { ETL_PAGE_SIZE, useEtlRun, useEtlRuns, useRequestEtlRun } from './api';
import { modeLabel, runStatus, severityLabel, sourceLabel, stepLabel } from './labels';

type Mode = 'full' | 'incremental';

const QUEUED_LOCK_MS = 60_000;

function duration(started: string, finished: string | null): string {
  if (!finished) return t('etl.inProgress');
  return formatDuration(Date.parse(finished) - Date.parse(started));
}

/** Takrorlanishi mumkin bo'lgan qatorlar uchun barqaror kalit: obyekt -> tartib raqami. */
function indexKeys<T extends object>(rows: readonly T[]): (row: T) => number {
  const index = new Map<T, number>(rows.map((row, i) => [row, i]));
  return (row) => index.get(row) ?? -1;
}

export default function EtlPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [queuedAt, setQueuedAt] = useState<number | null>(null);
  const runs = useEtlRuns(page, queuedAt !== null);
  const request = useRequestEtlRun();
  const [source, setSource] = useState('synthetic');
  const [mode, setMode] = useState<Mode>('incremental');
  const [openId, setOpenId] = useState<number | null>(null);
  const running = runs.data?.items.some((r) => r.status === 'running') ?? false;
  const blocked = running || queuedAt !== null;

  // Navbatdagi so'rovning run qatori hali yo'q: faqat mijoz tomonida 60 s qulf (takroriy so'rovlarga qarshi).
  useEffect(() => {
    if (queuedAt === null) return undefined;
    const id = window.setTimeout(() => setQueuedAt(null), QUEUED_LOCK_MS);
    return () => window.clearTimeout(id);
  }, [queuedAt]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (blocked) return;
    request.mutate(
      { source, mode },
      {
        onSuccess: (result) => {
          setQueuedAt(Date.now());
          toast.show(t('etl.queued', { id: result.request_id }), 'success');
        },
      },
    );
  };

  const columns: Column<EtlRunOut>[] = [
    { key: 'id', header: t('etl.col.id'), sortValue: (r) => r.id, cell: (r) => r.id },
    { key: 'source', header: t('etl.col.source'), align: 'left', cell: (r) => sourceLabel(r.source) },
    { key: 'mode', header: t('etl.col.mode'), align: 'left', cell: (r) => modeLabel(r.mode) },
    {
      key: 'status',
      header: t('etl.col.status'),
      align: 'left',
      cell: (r) => {
        const status = runStatus(r.status);
        return <Badge tone={status.tone}>{status.label}</Badge>;
      },
    },
    { key: 'started', header: t('etl.col.started'), sortValue: (r) => r.started_at, cell: (r) => formatDateTime(r.started_at) },
    { key: 'duration', header: t('etl.col.duration'), cell: (r) => duration(r.started_at, r.finished_at) },
    { key: 'rows', header: t('etl.col.rows'), cell: (r) => `${formatNumber(r.rows_in)} / ${formatNumber(r.rows_upserted)}` },
    { key: 'build', header: t('etl.col.build'), cell: (r) => (r.build_id === null ? t('common.dash') : `№${r.build_id}`) },
  ];

  return (
    <>
      <Card title={t('etl.runTitle')} sub={t('etl.runSub')}>
        <form className="toolbar" onSubmit={submit}>
          <Select
            label={t('etl.source')}
            value={source}
            options={[
              { value: 'synthetic', label: t('etl.source.synthetic') },
              { value: 'file', label: t('etl.source.file') },
            ]}
            onChange={(value) => {
              setSource(value);
              if (value === 'file') setMode('incremental'); // file + full API qabul qiladi, lekin worker rad etadi (A16.1)
            }}
          />
          <Select
            label={t('etl.mode')}
            value={mode}
            options={
              source === 'file'
                ? [{ value: 'incremental', label: t('etl.mode.incremental') }]
                : [
                    { value: 'incremental', label: t('etl.mode.incremental') },
                    { value: 'full', label: t('etl.mode.full') },
                  ]
            }
            hint={source === 'file' ? t('etl.fileFullHint') : undefined}
            onChange={(value) => setMode(value === 'full' ? 'full' : 'incremental')}
          />
          <Button type="submit" icon="refresh" loading={request.isPending} disabled={blocked}>
            {t('etl.start')}
          </Button>
        </form>
        {blocked ? <p className="note">{t('etl.busy')}</p> : null}
        <FormError error={request.error} />
      </Card>
      <Card title={t('etl.historyTitle')}>
        {runs.isError ? (
          <ErrorBanner error={runs.error} lastSuccessAt={runs.dataUpdatedAt} onRetry={() => void runs.refetch()} />
        ) : runs.isPending ? (
          <PageSkeleton />
        ) : (
          <>
            <Table
              caption={t('etl.historyTitle')}
              columns={columns}
              rows={runs.data.items}
              rowKey={(r) => r.id}
              onRowClick={(r) => setOpenId(r.id)}
            />
            <Pagination page={page} pageSize={ETL_PAGE_SIZE} total={runs.data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {openId !== null ? <RunDialog id={openId} onClose={() => setOpenId(null)} /> : null}
    </>
  );
}

function RunDialog({ id, onClose }: { id: number; onClose(): void }) {
  const detail = useEtlRun(id);
  const stepColumns: Column<EtlStepOut>[] = [
    { key: 'name', header: t('etl.col.step'), align: 'left', cell: (s) => stepLabel(s.name) },
    {
      key: 'status',
      header: t('etl.col.status'),
      align: 'left',
      cell: (s) => {
        const status = runStatus(s.status);
        return <Badge tone={status.tone}>{status.label}</Badge>;
      },
    },
    { key: 'started', header: t('etl.col.started'), cell: (s) => formatDateTime(s.started_at) },
    { key: 'duration', header: t('etl.col.duration'), cell: (s) => duration(s.started_at, s.finished_at) },
    { key: 'rows', header: t('etl.col.rows'), cell: (s) => formatNumber(s.rows) },
  ];
  const errorColumns: Column<EtlErrorOut>[] = [
    { key: 'step', header: t('etl.col.step'), align: 'left', cell: (e) => stepLabel(e.step) },
    {
      key: 'severity',
      header: t('etl.col.severity'),
      align: 'left',
      cell: (e) => <Badge tone={e.severity === 'error' ? 'neg' : 'warn'}>{severityLabel(e.severity)}</Badge>,
    },
    { key: 'object', header: t('etl.col.object'), align: 'left', cell: (e) => [e.target, e.src_id].filter(Boolean).join(' · ') || t('common.dash') },
    { key: 'code', header: t('etl.col.code'), align: 'left', cell: (e) => <span className="mono">{e.code}</span> },
    { key: 'message', header: t('etl.col.message'), align: 'left', wrap: true, cell: (e) => e.message },
  ];
  const run = detail.data?.run;

  return (
    <Modal open onClose={onClose} title={t('etl.detailTitle', { id })}>
      {detail.isError ? <ErrorBanner error={detail.error} onRetry={() => void detail.refetch()} /> : null}
      {detail.isPending && !detail.isError ? <PageSkeleton /> : null}
      {run && detail.data ? (
        <>
          <dl className="dl">
            <dt>{t('etl.col.source')}</dt>
            <dd>{sourceLabel(run.source)}</dd>
            <dt>{t('etl.col.mode')}</dt>
            <dd>{modeLabel(run.mode)}</dd>
            <dt>{t('etl.col.status')}</dt>
            <dd>{runStatus(run.status).label}</dd>
            <dt>{t('etl.window')}</dt>
            <dd>{run.window_from && run.window_to ? `${formatDate(run.window_from)} – ${formatDate(run.window_to)}` : t('common.dash')}</dd>
            {run.error ? (
              <>
                <dt>{t('etl.error')}</dt>
                <dd>{run.error}</dd>
              </>
            ) : null}
          </dl>
          <Table caption={t('etl.steps')} captionHidden={false} columns={stepColumns} rows={detail.data.steps} rowKey={indexKeys(detail.data.steps)} mobile="scroll" free />
          <Table
            caption={t('etl.errors')}
            captionHidden={false}
            columns={errorColumns}
            rows={detail.data.errors}
            rowKey={indexKeys(detail.data.errors)}
            empty={t('etl.noErrors')}
            mobile="scroll"
            free
          />
        </>
      ) : null}
    </Modal>
  );
}
