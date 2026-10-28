import { formatMoney } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';
import type { ReadyModel } from './FinmodelFrame';

/** Jamg'arilgan oqimning bazaviy ssenariyga nisbatan o'zgarishi. */
export function SensitivityCard({ model, className }: { model: ReadyModel; className?: string }) {
  const title = t('fm.sens.title');
  const items = model.sensitivity.map((x) => ({
    id: x.scenario,
    name: x.title,
    value: Math.abs(x.delta_cum),
    negative: x.delta_cum < 0,
    note: t('fm.sens.note', { sign: x.delta_cum < 0 ? '−' : '+', amount: formatMoney(Math.abs(x.delta_cum)), dscr: x.dscr_min === null ? t('dash.noValue') : formatNumber(x.dscr_min, 2) }),
  }));
  return (
    <Card className={className} title={title} sub={t('fm.sens.sub')}>
      <Rank label={title} items={items} />
    </Card>
  );
}
