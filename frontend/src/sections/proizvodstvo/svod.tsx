import { useState } from 'react';
import type { ProizvSvodOut } from '../../api/types';
import { NoData } from '../../dash/DataState';
import { GesMap } from '../../dash/map/GesMap';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { GenMonthsCard } from './parts/GenMonthsCard';
import { NoStations } from './parts/NoStations';
import { PowerCard } from './parts/PowerCard';
import { ProdKpis } from './parts/ProdKpis';
import { ProductionPanel } from './parts/ProductionPanel';
import { StationsRank } from './parts/StationsRank';

export default function ProizvodstvoSvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ProizvSvodOut>('/proizvodstvo/svod', filters);
  const [mapSel, setMapSel] = useState<number | null>(null);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_stations ? (
          <>
            <ProdKpis kpis={data.kpis} period={data.period} />
            {data.kpis.has_data ? null : (
              <Card>
                <NoData kind="period" />
              </Card>
            )}
            <div className="grid">
              <GenMonthsCard className="c8" months={data.months} ctx={ctx} />
              <StationsRank className="c4" stations={data.stations} filters={filters} onBranch={onBranch} />
            </div>
            <div className="grid">
              <Card className="c8 wide" title={t('proizv.map.title')} sub={t('proizv.map.sub')}>
                <GesMap stations={data.map} selected={mapSel ?? filters.br} onSelect={setMapSel} />
              </Card>
              <Card className="c4 wide">
                <ProductionPanel stations={data.map} selected={mapSel ?? filters.br} onSelect={setMapSel} filters={filters} onBranch={onBranch} />
              </Card>
              <PowerCard className="c12" filters={filters} />
            </div>
          </>
        ) : (
          <NoStations />
        )
      }
    </SectionData>
  );
}
