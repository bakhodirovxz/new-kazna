import type { KaznaDogovoryOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { DebtBranchCard } from './parts/DebtBranchCard';
import { DebtCard } from './parts/DebtCard';
import { KaznaKpis } from './parts/KaznaKpis';

export default function KaznaDogovory({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KaznaDogovoryOut>('/kazna/dogovory', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <KaznaKpis kpis={data.kpis} />
          <div className="grid">
            <DebtCard className="c12" contracts={data.contracts} hasData={data.kpis.payable !== null || data.kpis.receivable !== null} ctx={ctx} />
            <DebtBranchCard className="c12" rows={data.by_branch} date={data.kpis.balance_date} filters={filters} onBranch={onBranch} ctx={ctx} />
          </div>
        </>
      )}
    </SectionData>
  );
}
