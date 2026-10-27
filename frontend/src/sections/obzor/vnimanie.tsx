import type { AlertsOut } from '../../api/types';
import { t } from '../../i18n';
import { navigate } from '../../router/store';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';

/** TZ 5: все сработавшие правила, критичные первыми; нажатие ведёт в раздел с теми же фильтрами. */
export default function ObzorVnimanie({ filters }: SectionPageProps) {
  const query = useSection<AlertsOut>('/obzor/vnimanie', filters);
  return (
    <SectionData query={query}>
      {(data) => (
        <Card
          sub={
            data.items.length
              ? t('obzor.alerts.sub', {
                  count: data.items.length,
                  scope: filters.br === null ? t('obzor.alerts.scopeAll') : t('obzor.alerts.scopeOne'),
                  period: data.period.label.toLowerCase(),
                })
              : undefined
          }
        >
          {data.items.length ? (
            <ul className="alert-list">
              {data.items.map((a) => (
                <li key={a.code}>
                  <button
                    type="button"
                    aria-label={`${a.level === 'critical' ? t('obzor.alerts.critical') : t('obzor.alerts.warning')}: ${a.title}. ${a.message}. ${t('obzor.alerts.open')}`}
                    onClick={() => navigate({ kind: 'section', section: a.section, page: a.page, br: filters.br, per: filters.per })}
                  >
                    <i className={a.level === 'critical' ? 'is-critical' : undefined} aria-hidden="true" />
                    <span>
                      <span className="at">{a.title}</span>
                      <span className="am">{a.message}</span>
                    </span>
                    <span className="ag" aria-hidden="true">
                      {t('obzor.alerts.open')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="note">{t('obzor.alerts.none')}</p>
          )}
          <p className="note">{t('obzor.alerts.checked', { count: data.checked.length })}</p>
        </Card>
      )}
    </SectionData>
  );
}
