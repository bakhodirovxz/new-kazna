import type { KaznaCalendarOut } from '../../api/types';
import { Rank } from '../../dash/Rank';
import { formatMoney } from '../../dash/money';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { toggleBranch, useSection } from '../useSection';
import { BanksCard } from './parts/BanksCard';
import { CalendarCard } from './parts/CalendarCard';

export default function KaznaCalendar({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KaznaCalendarOut>('/kazna/calendar', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <div className="grid">
          <CalendarCard className="c8 wide" calendar={data.calendar} ctx={ctx} />
          <BanksCard className="c4 wide" banks={data.banks} date={data.period.date_to} />
          <Card className="c12" title={t('kazna.requests.title')} sub={t('kazna.requests.sub')}>
            <Rank
              label={t('kazna.requests.title')}
              items={data.requests.map((r) => ({ id: r.branch_id, name: r.name, value: r.amount, note: t('kazna.requests.note', { count: r.count }) }))}
              format={(v) => formatMoney(v)}
              onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
              activeId={filters.br}
            />
          </Card>
        </div>
      )}
    </SectionData>
  );
}
