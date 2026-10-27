import { t } from '../../i18n';
import { useEntities } from '../../entry/api';
import { EntityPage } from '../../entry/EntityPage';
import { EmptyState } from '../../ui/EmptyState';
import { ErrorBanner } from '../../ui/ErrorBanner';
import { PageSkeleton } from '../../ui/Skeleton';
import type { SectionPageProps } from '../registry';

/** «Ввод данных»: obyekt sahifalari (`#vvod/kazna-balance`) -- metadata asosidagi umumiy sahifa. */
export default function VvodPage({ page, filters }: SectionPageProps) {
  const entities = useEntities();
  if (entities.isPending) return <PageSkeleton />;
  if (entities.error) return <ErrorBanner error={entities.error} onRetry={() => void entities.refetch()} />;
  const entity = entities.data.find((e) => e.id.replace('.', '-') === page);
  if (!entity) return <EmptyState title={t('entry.noEntity')} />;
  return <EntityPage entity={entity} filters={filters} />;
}
