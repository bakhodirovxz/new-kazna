import { useState } from 'react';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { useBranches } from '../meta/api';
import { Badge, type BadgeTone } from '../ui/Badge';
import { EmptyState } from '../ui/EmptyState';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useBatches, useEntities, type EntryBatch } from './api';
import { BatchPage } from './BatchPage';
import './entry.css';

const TONE: Record<string, BadgeTone> = { draft: 'neutral', submitted: 'warn', approved: 'ok', rejected: 'neg', withdrawn: 'neutral', failed: 'neg' };

/** «На согласовании» (inbox) va «Мои пакеты» (mine): ro'yxat, qatorni bosish — paket sahifasi. */
export function BatchList({ box }: { box: 'inbox' | 'mine' }) {
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const list = useBatches(box, box === 'inbox' ? 'submitted' : status || undefined);
  const entities = useEntities();
  const branches = useBranches();

  if (selected !== null) return <BatchPage id={selected} onBack={() => setSelected(null)} />;
  if (list.isPending) return <PageSkeleton />;
  if (list.error) return <ErrorBanner error={list.error} onRetry={() => void list.refetch()} />;

  const entityTitle = (id: string) => entities.data?.find((e) => e.id === id)?.title ?? id;
  const branchName = (id: number) => branches.data?.find((b) => b.id === id)?.short_name ?? String(id);
  const columns: Column<EntryBatch>[] = [
    { key: 'id', header: '№', cell: (b) => b.batch_id, sortValue: (b) => b.batch_id },
    { key: 'entity', header: t('entry.batch.col.entity'), cell: (b) => entityTitle(b.entity) },
    { key: 'branch', header: t('entry.branch'), cell: (b) => branchName(b.branch_id) },
    { key: 'rows', header: t('entry.batch.col.rows'), cell: (b) => b.rows, align: 'right' },
    { key: 'status', header: t('entry.status'), cell: (b) => (
      <>
        <Badge tone={TONE[b.status] ?? 'neutral'}>{t(`entry.status.${b.status}` as 'entry.status.draft')}</Badge>
        {b.publish_error ? <div className="entry-hint">{b.publish_error}</div> : null}
      </>
    ) },
    { key: 'when', header: t('entry.batch.col.when'), cell: (b) => (b.submitted_at ? formatDateTime(b.submitted_at) : '—') },
    { key: 'open', header: t('entry.actions'), cell: (b) => (
      <button type="button" className="btn btn--ghost" onClick={() => setSelected(b.batch_id)}>
        <span>{t('entry.batch.title', { id: b.batch_id })}</span>
      </button>
    ) },
  ];
  return (
    <div className="entry">
      {box === 'mine' ? (
        <label className="entry-filter">
          <span>{t('entry.status')}: </span>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="select">
            <option value="">{t('entry.filter.all')}</option>
            {['draft', 'submitted', 'approved', 'rejected', 'withdrawn', 'failed'].map((s) => (
              <option key={s} value={s}>{t(`entry.status.${s}` as 'entry.status.draft')}</option>
            ))}
          </select>
        </label>
      ) : null}
      <Table
        caption={box === 'inbox' ? t('entry.inbox.title') : t('entry.batches.title')}
        columns={columns}
        rows={list.data.items}
        rowKey={(b) => b.batch_id}
        onRowClick={(b) => setSelected(b.batch_id)}
        empty={<EmptyState title={box === 'inbox' ? t('entry.inbox.empty') : t('entry.batches.empty')} />}
      />
    </div>
  );
}
