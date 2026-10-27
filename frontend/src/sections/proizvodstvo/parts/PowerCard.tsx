import type { PowerOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { formatMw } from '../../../dash/energy';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatDateTime } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { SectionData } from '../../SectionData';
import { useSection } from '../../useSection';

function PowerBody({ data }: { data: PowerOut }) {
  return (
    <>
      <div className="bigline" title={formula('currentPower')}>
        <b>{formatMw(data.total_mw, 1)}</b>
        <span>{t('proizv.power.asOf', { time: data.snap_at ? formatDateTime(data.snap_at) : '—' })}</span>
      </div>
      {data.stale ? <Badge tone="neg">{t('proizv.power.stale')}</Badge> : null}
      <p className="note">{t('proizv.power.units', { working: data.units_working, reserve: data.units_reserve, repair: data.units_repair })}</p>
      <Rank
        label={t('proizv.power.stations')}
        items={data.stations.map((s) => ({ id: s.station, name: s.station_name, value: s.power_mw, note: s.branch_name }))}
        format={(v) => formatMw(v, 1)}
      />
    </>
  );
}

/** «Текущая мощность» (S3 spec 3.2): онлайн-мониторинг, не суточная выработка; свой запрос. */
export function PowerCard({ filters, className }: { filters: FilterState; className?: string }) {
  const query = useSection<PowerOut>('/proizvodstvo/moshchnost', filters);
  return (
    <Card className={className} title={t('proizv.power.title')} sub={t('proizv.power.sub')}>
      <SectionData query={query}>{(data) => (data.has_source ? <PowerBody data={data} /> : <NoData kind="source" source={t('proizv.power.source')} />)}</SectionData>
    </Card>
  );
}
