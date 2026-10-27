import type { KredityReestrOut } from '../../api/types';
import { Rank } from '../../dash/Rank';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { currencyName } from './parts/currency';
import { LoanKpis } from './parts/LoanKpis';
import { LoanRegistry } from './parts/LoanRegistry';
import { NoLoans } from './parts/NoLoans';

export default function KredityReestr({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KredityReestrOut>('/kredity/reestr', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_loans ? (
          <>
            <LoanKpis kpis={data.kpis} />
            <div className="grid">
              <LoanRegistry className="c12" loans={data.loans} asOf={data.kpis.as_of} ctx={ctx} filters={filters} onBranch={onBranch} />
              <Card className="c6" title={t('kredity.creditors.title')} sub={t('kredity.creditors.sub')}>
                <Rank label={t('kredity.creditors.title')} items={data.creditors.map((c) => ({ id: c.name, name: c.name, value: c.amount }))} />
              </Card>
              <Card className="c6" title={t('kredity.currency.title')} sub={t('kredity.currency.sub')}>
                <Rank label={t('kredity.currency.title')} items={data.currencies.map((c) => ({ id: c.name, name: currencyName(c.name), value: c.amount }))} />
              </Card>
            </div>
          </>
        ) : (
          <NoLoans />
        )
      }
    </SectionData>
  );
}
