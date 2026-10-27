import { ApiError } from '../api/client';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Drawer } from '../ui/Drawer';
import { EmptyState } from '../ui/EmptyState';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';
import { Badge } from '../ui/Badge';
import { useHistory, type EntryEntity, type EntryHistory } from './api';
import { toInput } from './fields';

type Version = EntryHistory['versions'][number];

function show(entity: EntryEntity, name: string, v: Version): string {
  const mask = v.masks[name];
  if (mask) return mask;
  const field = entity.fields.find((f) => f.name === name);
  const value = v.values[name];
  return field ? toInput(field, value) : String(value ?? '');
}

/** Oldingi versiyaga nisbatan o'zgargan maydonlar (sezgir maydon — faqat niqob). */
export function diffFields(entity: EntryEntity, now: Version, before: Version | undefined) {
  const names = entity.fields.map((f) => f.name).filter((n) => n in now.values || n in now.masks || (before && (n in before.values || n in before.masks)));
  return names
    .map((name) => ({
      name,
      title: entity.fields.find((f) => f.name === name)?.title ?? name,
      was: before ? show(entity, name, before) : null,
      now: show(entity, name, now),
    }))
    .filter((d) => d.was === null || d.was !== d.now);
}

export function HistoryDrawer({ entity, entryId, onClose }: { entity: EntryEntity; entryId: number; onClose(): void }) {
  const history = useHistory(entryId);
  const versions = history.data?.versions ?? [];
  return (
    <Drawer open onClose={onClose} title={t('entry.history')}>
      {history.isPending ? (
        <PageSkeleton />
      ) : history.error ? (
        <ErrorBanner error={history.error instanceof ApiError ? history.error : history.error} onRetry={() => void history.refetch()} />
      ) : versions.length === 0 ? (
        <EmptyState title={t('entry.history.empty')} />
      ) : (
        <ol className="entry-history">
          {versions.map((v, i) => (
            <li key={v.version}>
              <p className="entry-history__head">
                <b>№{v.version}</b> <Badge>{t(`entry.status.${v.batch_status}` as 'entry.status.draft')}</Badge>{' '}
                {t('entry.history.by', { who: v.created_by_name ?? '—', when: formatDateTime(v.created_at) })}
                {v.deleted ? ` · ${t('entry.record.deleted')}` : ''}
              </p>
              {v.reason ? <p>{t('entry.batch.reason', { reason: v.reason })}</p> : null}
              <ul>
                {diffFields(entity, v, versions[i + 1]).map((d) => (
                  <li key={d.name}>
                    <span>{d.title}: </span>
                    {d.was !== null ? (
                      <>
                        <span className="visually-hidden">{t('entry.was')} </span>
                        <del>{d.was || '—'}</del>{' '}
                        <span className="visually-hidden">{t('entry.became')} </span>
                      </>
                    ) : null}
                    <ins>{d.now || '—'}</ins>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </Drawer>
  );
}
