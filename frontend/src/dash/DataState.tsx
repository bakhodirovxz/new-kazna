import { t } from '../i18n';
import { EmptyState } from '../ui/EmptyState';

/** TZ 6 «Состояния»: нет данных за период / источник не подключён (кнопка карты сохраняется). */
export function NoData({ kind, source, headingLevel = 3 }: { kind: 'period' | 'source'; source?: string; headingLevel?: 2 | 3 | 4 }) {
  return (
    <EmptyState
      headingLevel={headingLevel}
      icon={kind === 'source' ? 'plug' : 'filter'}
      title={t('dash.noData.title')}
      text={kind === 'source' ? t('dash.noData.source', { source: source ?? '' }) : t('dash.noData.period')}
    />
  );
}
