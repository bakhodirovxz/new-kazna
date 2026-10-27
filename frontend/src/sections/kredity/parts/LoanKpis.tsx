import type { LoanKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

function money(value: number | null): { value: string; unit?: string } {
  if (value === null) return { value: t('dash.noValue') };
  const parts = moneyParts(value);
  return { value: parts.value, unit: parts.unit };
}

/** Prototip `kpisCred`: портфель, ставка, валютная доля, обслуживание долга, ближайший платёж, пик. */
export function LoanKpis({ kpis }: { kpis: LoanKpisOut }) {
  const portfolio = money(kpis.portfolio);
  const service = money(kpis.service);
  const next = kpis.next_payment;
  const note = t('kredity.kpi.portfolioNote', { date: formatDate(kpis.as_of), count: kpis.loans });
  return (
    <KpiGrid>
      <KpiTile
        icon="card"
        label={t('kredity.kpi.portfolio')}
        value={portfolio.value}
        unit={portfolio.unit}
        delta={kpis.missing_fx.length ? <span className="neg">{t('kredity.kpi.noRate', { currencies: kpis.missing_fx.join(', ') })}</span> : note}
        hint={formula('portfolio')}
      />
      <KpiTile icon="pct" label={t('kredity.kpi.rate')} value={formatPct(kpis.rate, 2)} delta={t('kredity.kpi.rateNote')} hint={formula('loanRate')} />
      <KpiTile icon="coins" label={t('kredity.kpi.fxShare')} value={formatPct(kpis.fx_share, 1)} delta={t('kredity.kpi.fxShareNote')} hint={formula('fxShare')} />
      <KpiTile
        icon="check"
        label={t('kredity.kpi.service', { year: kpis.as_of.slice(0, 4) })}
        value={service.value}
        unit={service.unit}
        delta={t('kredity.kpi.serviceNote', { paid: formatMoney(kpis.paid), share: formatPct(kpis.paid_share, 0) })}
        hint={`${formula('debtService')}. ${formula('loanPaid')}`}
      />
      <KpiTile
        icon="cal"
        label={t('kredity.kpi.next')}
        value={next ? formatDate(next.day) : t('kredity.kpi.nextNone')}
        delta={next ? t('kredity.kpi.nextNote', { amount: formatMoney(next.total), creditor: next.creditor }) : undefined}
        hint={formula('nextPayment')}
      />
      <KpiTile
        icon="alert"
        label={t('kredity.kpi.peak')}
        value={kpis.peak_year === null ? '—' : String(kpis.peak_year)}
        delta={kpis.peak_amount === null ? undefined : t('kredity.kpi.peakNote', { amount: formatMoney(kpis.peak_amount) })}
        hint={formula('peakYear')}
      />
    </KpiGrid>
  );
}
