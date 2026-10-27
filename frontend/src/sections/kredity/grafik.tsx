import type { KredityGrafikOut } from '../../api/types';
import { t } from '../../i18n';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NoLoans } from './parts/NoLoans';
import { ScheduleCard } from './parts/ScheduleCard';
import { UpcomingCard } from './parts/UpcomingCard';

export default function KredityGrafik({ section, page, filters }: SectionPageProps) {
  const query = useSection<KredityGrafikOut>('/kredity/grafik', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_loans ? (
          <div className="grid">
            <ScheduleCard className="c12" years={data.schedule} ctx={ctx} />
            <UpcomingCard className="c12" payments={data.upcoming} title={t('kredity.upcoming.title')} sub={t('kredity.upcoming.sub')} ctx={ctx} />
          </div>
        ) : (
          <NoLoans />
        )
      }
    </SectionData>
  );
}
