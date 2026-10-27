import { NoData } from '../../../dash/DataState';
import { formula } from '../../../dash/formulas';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** TZ 4: DSCR = EBITDA / обслуживание долга — из финмодели (S5); до этого «источник не подключён». */
export function DscrCard({ dscr, className }: { dscr: number | null; className?: string }) {
  return (
    <Card className={className} title={t('kredity.dscr.title')} sub={t('kredity.dscr.sub')}>
      {dscr === null ? (
        <NoData kind="source" source={t('kredity.dscr.source')} />
      ) : (
        <div className="bigline" title={formula('dscr')}>
          <b>{formatNumber(dscr, 2)}</b>
        </div>
      )}
    </Card>
  );
}
