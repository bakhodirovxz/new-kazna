import { useState } from 'react';
import { isApiError } from '../api/client';
import { useMe } from '../auth/api';
import { t } from '../i18n';
import { Badge, type BadgeTone } from '../ui/Badge';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { ErrorBanner } from '../ui/ErrorBanner';
import { FormError, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import {
  useApproveBatch,
  useBatch,
  useEntities,
  useRejectBatch,
  useSubmitBatch,
  useWithdrawBatch,
  type EntryBatchDetail,
  type EntryEntity,
} from './api';
import { displayValue, serverErrorText } from './fields';
import './entry.css';

type Change = EntryBatchDetail['items'][number];

const STATUS_TONE: Record<string, BadgeTone> = {
  draft: 'neutral', submitted: 'warn', approved: 'ok', rejected: 'neg', withdrawn: 'neutral', failed: 'neg',
};

function shown(entity: EntryEntity | undefined, name: string, value: unknown): string {
  if (value !== null && typeof value === 'object' && 'mask' in value) return String((value as { mask: string }).mask);
  const field = entity?.fields.find((f) => f.name === name);
  return field ? displayValue(field, value) : String(value ?? '');
}

/** Paket qatori o'zgarishi: matn belgisi bilan (rangga tayanmasdan). */
function ChangeText({ entity, change }: { entity: EntryEntity | undefined; change: Change }) {
  const names = [...new Set([...Object.keys(change.before ?? {}), ...Object.keys(change.after ?? {})])]
    .filter((n) => n !== 'branch_code');
  return (
    <ul className="entry-diff">
      {names.map((name) => {
        const was = change.before ? shown(entity, name, change.before[name]) : null;
        const now = change.after ? shown(entity, name, change.after[name]) : null;
        if (change.op === 'change' && was === now) return null;
        const title = entity?.fields.find((f) => f.name === name)?.title ?? name;
        return (
          <li key={name}>
            <span>{title}: </span>
            {was !== null && change.op !== 'add' ? (
              <>
                <span className="visually-hidden">{t('entry.was')} </span>
                <del>{was || '—'}</del>{' '}
              </>
            ) : null}
            {now !== null ? (
              <>
                <span className="visually-hidden">{t('entry.became')} </span>
                <ins>{now || '—'}</ins>
              </>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function publicationText(p: EntryBatchDetail['publication']): string | null {
  if (!p || p.status === 'none') return null;
  if (p.status === 'published') return t('entry.pub.published', { n: p.build_id ?? 0 });
  return t(`entry.pub.${p.status}` as 'entry.pub.queued');
}

export function BatchPage({ id, onBack }: { id: number; onBack(): void }) {
  const toast = useToast();
  const me = useMe();
  const entities = useEntities();
  const batch = useBatch(id, { poll: true });
  const approve = useApproveBatch();
  const reject = useRejectBatch();
  const submit = useSubmitBatch();
  const withdraw = useWithdrawBatch();
  const [rejecting, setRejecting] = useState(false);
  const [comment, setComment] = useState('');
  const [commentError, setCommentError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);

  if (batch.isPending) return <PageSkeleton />;
  if (batch.error) return <ErrorBanner error={batch.error} onRetry={() => void batch.refetch()} />;
  const data = batch.data;
  const entity = entities.data?.find((e) => e.id === data.entity);
  const own = me.data?.id === data.created_by;
  const pub = publicationText(data.publication);
  const needsReason = data.items.some((c) => c.op !== 'add');
  const mutationError = approve.error ?? reject.error ?? submit.error ?? withdraw.error;
  const done = (message: string) => ({ onSuccess: () => toast.show(message, 'success') });

  const columns: Column<Change>[] = [
    { key: 'op', header: t('entry.status'), cell: (c) => <span className="entry-diff__op">{t(`entry.op.${c.op}` as 'entry.op.add')}</span> },
    { key: 'id', header: '№', cell: (c) => c.entry_id },
    { key: 'diff', header: t('entry.history'), cell: (c) => <ChangeText entity={entity} change={c} />, wrap: true },
  ];

  const doReject = () => {
    if (comment.trim().length < 5) {
      setCommentError(serverErrorText('reason_required'));
      return;
    }
    reject.mutate(
      { id, expected_version: data.version, comment: comment.trim() },
      { onSuccess: () => { toast.show(t('entry.status.rejected'), 'success'); setRejecting(false); } },
    );
  };
  const doSubmit = () => {
    if (needsReason && reason.trim().length < 5) {
      setReasonError(serverErrorText('reason_required'));
      return;
    }
    submit.mutate({ id, expected_version: data.version, reason: reason.trim() || null }, done(t('entry.submitted')));
  };

  return (
    <div className="entry">
      <div className="entry-toolbar">
        <Button variant="ghost" icon="chevronLeft" onClick={onBack}>
          {t('entry.batch.back')}
        </Button>
      </div>
      <h2>{t('entry.batch.title', { id: data.batch_id })}</h2>
      <p>
        {entity?.title ?? data.entity}{' '}
        <Badge tone={STATUS_TONE[data.status] ?? 'neutral'}>{t(`entry.status.${data.status}` as 'entry.status.draft')}</Badge>
        {pub ? <> · <span role="status">{pub}</span></> : null}
      </p>
      {data.reason ? <p>{t('entry.batch.reason', { reason: data.reason })}</p> : null}
      {data.decision_comment ? <p>{data.decision_comment}</p> : null}
      {data.publish_error ? <p className="form-error" role="alert">{t('entry.batch.publishError', { error: data.publish_error })}</p> : null}
      {data.items.length === 0 ? (
        <EmptyState title={t('entry.empty')} />
      ) : (
        <Table caption={t('entry.batch.title', { id: data.batch_id })} columns={columns} rows={data.items} rowKey={(c) => c.entry_id} mobile="cards" />
      )}
      {mutationError && isApiError(mutationError) ? (
        <p className="form-error" role="alert">{serverErrorText(mutationError.code)}</p>
      ) : mutationError ? (
        <FormError error={mutationError} />
      ) : null}
      {data.status === 'submitted' ? (
        own ? (
          <>
            <p>{t('entry.batch.own')}</p>
            <div className="entry-toolbar">
              <Button variant="secondary" loading={withdraw.isPending}
                onClick={() => withdraw.mutate({ id, expected_version: data.version }, done(t('entry.status.withdrawn')))}>
                {t('entry.withdraw')}
              </Button>
            </div>
          </>
        ) : entity?.can_approve ? (
          <div className="entry-toolbar">
            <Button loading={approve.isPending}
              onClick={() => approve.mutate({ id, expected_version: data.version }, done(t('entry.status.approved')))}>
              {t('entry.approve')}
            </Button>
            <Button variant="danger" onClick={() => { setComment(''); setCommentError(null); setRejecting(true); }}>
              {t('entry.reject')}
            </Button>
          </div>
        ) : null
      ) : null}
      {data.status === 'draft' && own && entity?.can_write ? (
        <div className="entry-form">
          {needsReason ? (
            <TextInput label={t('entry.reason')} value={reason} onChange={(e) => setReason(e.target.value)} error={reasonError} required />
          ) : null}
          <div className="entry-toolbar">
            <Button loading={submit.isPending} onClick={doSubmit}>{t('entry.submit')}</Button>
            <Button variant="secondary" loading={withdraw.isPending}
              onClick={() => withdraw.mutate({ id, expected_version: data.version }, done(t('entry.status.withdrawn')))}>
              {t('entry.withdraw')}
            </Button>
          </div>
        </div>
      ) : null}
      <Modal open={rejecting} onClose={() => setRejecting(false)} title={t('entry.batch.rejectTitle')} size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejecting(false)}>{t('common.cancel')}</Button>
            <Button variant="danger" loading={reject.isPending} onClick={doReject}>{t('entry.reject')}</Button>
          </>
        }>
        <TextInput label={t('entry.comment')} value={comment} onChange={(e) => setComment(e.target.value)} error={commentError} required />
      </Modal>
    </div>
  );
}
