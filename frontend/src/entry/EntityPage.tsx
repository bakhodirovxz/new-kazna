import { useState } from 'react';
import { isApiError } from '../api/client';
import { t } from '../i18n';
import type { FilterState } from '../shell/useFilters';
import { Badge, type BadgeTone } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { EmptyState } from '../ui/EmptyState';
import { ErrorBanner } from '../ui/ErrorBanner';
import { TextInput } from '../ui/Field';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useCreateBatch, useRecords, type EntryEntity, type EntryRecord } from './api';
import { displayValue } from './fields';
import { HistoryDrawer } from './HistoryDrawer';
import { ImportDialog } from './ImportDialog';
import { RecordDrawer } from './RecordDrawer';
import './entry.css';

const TONE: Record<EntryRecord['status'], BadgeTone> = { active: 'ok', pending: 'warn', deleted: 'neutral' };

function cellText(entity: EntryEntity, record: EntryRecord, name: string): string {
  const mask = record.masks[name];
  if (mask) return mask;
  const field = entity.fields.find((f) => f.name === name);
  return field ? displayValue(field, record.values[name]) : '';
}

interface Props {
  entity: EntryEntity;
  filters: FilterState;
}

export function EntityPage({ entity, filters }: Props) {
  const toast = useToast();
  const records = useRecords(entity.id, { br: filters.br, per: filters.per });
  const remove = useCreateBatch();
  const [drawer, setDrawer] = useState<{ record: EntryRecord | null } | null>(null);
  const [history, setHistory] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<{ batchId: number; sent: boolean } | null>(null);
  const [deleting, setDeleting] = useState<EntryRecord | null>(null);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);

  const rows = records.data?.items ?? [];
  // Yuborilgan paket yozuvi ro'yxatda yo'q -- davr (yoki filial) filtri yashirgan.
  const hidden =
    notice?.sent === true && entity.kind === 'fact' && !records.isFetching && records.isSuccess &&
    !rows.some((r) => r.pending_batch_id === notice.batchId);
  const openExisting = (entryId: number) => {
    const found = rows.find((r) => r.entry_id === entryId) ?? null;
    setDrawer(found ? { record: found } : null);
  };

  const columns: Column<EntryRecord>[] = [
    ...entity.fields
      .filter((f) => f.name !== 'branch_code')
      .map((f) => ({
        key: f.name,
        header: f.unit ? `${f.title}, ${f.unit}` : f.title,
        cell: (r: EntryRecord) => cellText(entity, r, f.name) || '—',
        align: f.kind === 'money' || f.kind === 'volume' || f.kind === 'decimal' ? ('right' as const) : ('left' as const),
      })),
    {
      key: 'status',
      header: t('entry.status'),
      cell: (r) => <Badge tone={TONE[r.status]}>{t(`entry.record.${r.status}` as 'entry.record.active')}</Badge>,
    },
    {
      key: 'actions',
      header: t('entry.actions'),
      cell: (r) => (
        <span className="entry-actions">
          {entity.can_write && r.status === 'active' ? (
            <>
              <Button variant="ghost" onClick={() => setDrawer({ record: r })}>
                {t('entry.edit')}
              </Button>
              <Button variant="ghost" onClick={() => { setReason(''); setReasonError(null); setDeleting(r); }}>
                {t('entry.delete')}
              </Button>
            </>
          ) : null}
          <Button variant="ghost" onClick={() => setHistory(r.entry_id)}>
            {t('entry.history')}
          </Button>
        </span>
      ),
    },
  ];

  const confirmDelete = () => {
    if (!deleting) return;
    if (reason.trim().length < 5) {
      setReasonError(t('entry.err.reason_required'));
      return;
    }
    remove.mutate(
      {
        entity: entity.id,
        branch_id: deleting.branch_id,
        origin: 'form',
        submit: true,
        reason: reason.trim(),
        items: [{ entry_id: deleting.entry_id, expected_version: deleting.version, delete: true, values: {} }],
      },
      {
        onSuccess: (batch) => {
          toast.show(t('entry.submitted'), 'success');
          setNotice({ batchId: batch.batch_id, sent: true });
          setDeleting(null);
        },
      },
    );
  };

  return (
    <div className="entry">
      <p className="srcbar">
        <span>{t('entry.srcbar')}</span>
      </p>
      {entity.can_write ? (
        <div className="entry-toolbar">
          <Button icon="plus" onClick={() => { setNotice(null); setDrawer({ record: null }); }}>
            {t('entry.add')}
          </Button>
          <Button variant="secondary" onClick={() => setImporting(true)}>
            {t('entry.import')}
          </Button>
        </div>
      ) : null}
      {notice ? (
        <p className="entry-banner" role="status">
          <span>{t(notice.sent ? 'entry.notice.sent' : 'entry.notice.saved', { id: notice.batchId })}</span>
          <a href="#vvod/batches">{t('entry.notice.open')}</a>
          {hidden ? <span>{t('entry.notice.hidden')}</span> : null}
        </p>
      ) : null}
      {records.isPending ? (
        <PageSkeleton />
      ) : records.error ? (
        <ErrorBanner error={records.error} onRetry={() => void records.refetch()} lastSuccessAt={records.dataUpdatedAt} />
      ) : (
        <Table
          caption={entity.title}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.entry_id}
          empty={<EmptyState title={t('entry.empty')} text={entity.can_write ? t('entry.emptyText') : undefined} />}
        />
      )}
      {drawer ? (
        <RecordDrawer
          key={drawer.record?.entry_id ?? 'new'}
          entity={entity}
          record={drawer.record}
          branch={filters.br}
          onClose={() => setDrawer(null)}
          onSaved={(batch, sent) => setNotice({ batchId: batch.batch_id, sent })}
          onOpenExisting={openExisting}
        />
      ) : null}
      {importing ? <ImportDialog entity={entity} branch={filters.br} onClose={() => setImporting(false)} /> : null}
      {history !== null ? <HistoryDrawer entity={entity} entryId={history} onClose={() => setHistory(null)} /> : null}
      <ConfirmDialog
        open={deleting !== null}
        title={t('entry.delete')}
        message={
          <TextInput
            label={t('entry.reason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={reasonError}
            required
          />
        }
        confirmLabel={t('entry.submit')}
        danger
        busy={remove.isPending}
        error={isApiError(remove.error) ? remove.error : undefined}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
