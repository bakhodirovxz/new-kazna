import type { KreditySvodOut } from '../../api/types';
import { Rank } from '../../dash/Rank';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { currencyName } from './parts/currency';
import { DscrCard } from './parts/DscrCard';
import { LoanKpis } from './parts/LoanKpis';
import { NoLoans } from './parts/NoLoans';
import { ScheduleCard } from './parts/ScheduleCard';
import { UpcomingCard } from './parts/UpcomingCard';

export default function KreditySvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<KreditySvodOut>('/kredity/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_loans ? (
          <>
            <LoanKpis kpis={data.kpis} />
            <div className="grid">
              <ScheduleCard className="c8 wide" years={data.schedule} ctx={ctx} />
              <Card className="c4 wide" title={t('kredity.currency.title')} sub={t('kredity.currency.sub')}>
                <Rank label={t('kredity.currency.title')} items={data.currencies.map((c) => ({ id: c.name, name: currencyName(c.name), value: c.amount }))} />
              </Card>
              <UpcomingCard className="c8" payments={data.upcoming} title={t('kredity.upcoming.titleShort')} sub={t('kredity.upcoming.subShort')} ctx={ctx} more />
              <DscrCard className="c4" dscr={data.kpis.dscr} />
            </div>
          </>
        ) : (
          <NoLoans />
        )
      }
    </SectionData>
  );
}
