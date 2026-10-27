import type { InvKpisOut, ReportPeriodOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const ON_TRACK = 0.9; // TZ 4 qoidasi «Адресная программа: исполнение графика < 90%»

/** Prototip `kpisInv`: программа, освоено, исполнение графика, за период, отстающие, ввод. */
export function InvKpis({ kpis, period }: { kpis: InvKpisOut; period: ReportPeriodOut }) {
  const program = moneyParts(kpis.program);
  const ytd = moneyParts(kpis.fact_ytd);
  const perPeriod = moneyParts(kpis.fact_period);
  const share = kpis.program > 0 ? kpis.fact_ytd / kpis.program : null;
  const low = kpis.execution !== null && kpis.execution < ON_TRACK;
  return (
    <KpiGrid>
      <KpiTile icon="target" label={t('inv.kpi.program', { year: kpis.year })} value={program.value} unit={program.unit} delta={t('inv.kpi.programNote', { count: kpis.objects, cost: formatMoney(kpis.total_cost) })} hint={formula('program')} />
      <KpiTile icon="coins" label={t('inv.kpi.ytd')} value={ytd.value} unit={ytd.unit} delta={t('inv.kpi.ytdNote', { pct: formatPct(share, 1) })} hint={formula('invYtd')} />
      <KpiTile
        icon="pct"
        label={t('inv.kpi.schedule')}
        value={<span className={low ? 'neg' : undefined}>{formatPct(kpis.execution, 1)}</span>}
        delta={t('inv.kpi.scheduleNote', { date: formatDate(period.date_to), amount: formatMoney(kpis.plan_to_date) })}
        hint={formula('schedule')}
      />
      <KpiTile icon="net" label={t('inv.kpi.period')} value={perPeriod.value} unit={perPeriod.unit} delta={period.label} hint={formula('invYtd')} />
      <KpiTile
        icon="alert"
        label={t('inv.kpi.lagging')}
        value={<span className={kpis.lagging ? 'neg' : undefined}>{formatNumber(kpis.lagging)}</span>}
        delta={kpis.lagging ? t('inv.kpi.laggingNote', { count: kpis.threatened }) : t('inv.kpi.laggingNone')}
        hint={formula('objStatus')}
      />
      <KpiTile icon="check" label={t('inv.kpi.commissioning', { year: kpis.year })} value={formatNumber(kpis.commissioning)} delta={t('inv.kpi.commissioningNote')} />
    </KpiGrid>
  );
}
