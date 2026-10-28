import type { ReactNode } from 'react';
import type { FinBaseOut, FinmodelOut, FinSummaryOut } from '../../../api/types';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { EmptyState } from '../../../ui/EmptyState';
import { SectionData } from '../../SectionData';
import { useSection } from '../../useSection';
import { FinKpis } from './FinKpis';
import './finmodel.css';
import { ScenarioBar } from './ScenarioBar';
import { useScenario } from './scenario';

export type ReadyModel = FinmodelOut & { summary: FinSummaryOut; base: FinBaseOut };

/** Har sahifa: ssenariy almashtirgich (URL), so'rov, «по компании в целом», model yo'q holati, 6 KPI. */
export function FinmodelFrame({ filters, children }: { filters: FilterState; children(model: ReadyModel): ReactNode }) {
  const { scen, setScen } = useScenario();
  const query = useSection<FinmodelOut>('/finmodel/model', filters, { scen });
  return (
    <>
      <ScenarioBar current={scen} onChange={setScen} />
      <SectionData query={query}>
        {(data) =>
          !data.has_model || data.summary === null || data.base === null ? (
            <EmptyState icon="net" title={t('fm.noModel.title')} text={t('fm.noModel.text')} />
          ) : (
            <>
              {data.company_wide ? <p className="note fin-note">{t('fm.companyWide')}</p> : null}
              <FinKpis summary={data.summary} base={data.base} />
              {children({ ...data, summary: data.summary, base: data.base })}
            </>
          )
        }
      </SectionData>
    </>
  );
}
