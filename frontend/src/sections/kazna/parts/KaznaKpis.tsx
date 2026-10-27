import type { KaznaKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

function money(value: number | null): { value: string; unit?: string } {
  if (value === null) return { value: t('dash.noValue') };
  const parts = moneyParts(value);
  return { value: parts.value, unit: parts.unit };
}

export function KaznaKpis({ kpis }: { kpis: KaznaKpisOut }) {
  const date = formatDate(kpis.balance_date);
  const balance = money(kpis.balance);
  const receivable = money(kpis.receivable);
  const payable = money(kpis.payable);
  return (
    <KpiGrid>
      <KpiTile icon="bank" label={t('kazna.kpi.balance')} value={balance.value} unit={balance.unit} delta={kpis.balance === null ? t('kazna.kpi.noBalance') : t('kazna.kpi.balanceNote', { date, banks: kpis.banks })} hint={formula('balance')} />
      <KpiTile
        icon="pct"
        label={t('kazna.kpi.execution')}
        value={kpis.execution === null ? t('dash.noValue') : formatNumber(kpis.execution * 100, 1)}
        unit={kpis.execution === null ? undefined : '%'}
        delta={kpis.execution === null ? t('kazna.kpi.noPlan') : t('kazna.kpi.executionNote', { fact: formatMoney(kpis.fact), plan: formatMoney(kpis.plan) })}
        hint={`${formula('planExecution')}. ${formula('deviation')}`}
      />
      <KpiTile icon="doc" label={t('kazna.kpi.orders')} value={formatNumber(kpis.orders_count)} delta={t('kazna.kpi.ordersNote', { amount: formatMoney(kpis.orders_amount) })} hint={formula('orders')} />
      <KpiTile icon="clock" label={t('kazna.kpi.requests')} value={formatNumber(kpis.requests_count)} delta={t('kazna.kpi.requestsNote', { amount: formatMoney(kpis.requests_amount) })} hint={formula('requests')} />
      <KpiTile icon="in" label={t('kazna.kpi.receivable')} value={receivable.value} unit={receivable.unit} delta={kpis.receivable === null ? t('kazna.kpi.noDebt') : t('kazna.kpi.at', { date })} hint={formula('receivable')} />
      <KpiTile
        icon="out"
        label={t('kazna.kpi.payable')}
        value={payable.value}
        unit={payable.unit}
        delta={kpis.payable === null ? t('kazna.kpi.noDebt') : kpis.overdue_payable ? <span className="neg">{t('kazna.kpi.overdue', { amount: formatMoney(kpis.overdue_payable) })}</span> : t('kazna.kpi.at', { date })}
        hint={`${formula('payable')}. ${formula('overdue')}`}
      />
    </KpiGrid>
  );
}
