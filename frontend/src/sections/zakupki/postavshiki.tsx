import type { ZakPostavshikiOut } from '../../api/types';
import { t } from '../../i18n';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NamedRankCard } from './parts/NamedRankCard';
import { ZakBranchesTable } from './parts/ZakBranchesTable';
import { ZakKpis } from './parts/ZakKpis';

export default function ZakupkiPostavshiki({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ZakPostavshikiOut>('/zakupki/postavshiki', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <NamedRankCard className="c6" title={t('zak.suppliers.title')} sub={t('zak.suppliers.sub')} rows={data.suppliers} />
            <NamedRankCard className="c6" title={t('zak.subjects.title')} sub={t('zak.subjects.sub')} rows={data.subjects} />
            <ZakBranchesTable className="c12" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
