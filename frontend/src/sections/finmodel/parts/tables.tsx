/* Явные роли в футере: в карточном режиме таблицы Safari/VoiceOver теряют семантику (как в ui/Table). */
/* eslint-disable jsx-a11y/no-interactive-element-to-noninteractive-role */
import type { ReactNode } from 'react';
import type { FinSummaryOut, FinYearOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import type { ReadyModel } from './FinmodelFrame';
import { isScenario, SCENARIO_NOTE_KEYS } from './scenario';

function Neg({ bad, children }: { bad: boolean; children: ReactNode }) {
  return <span className={bad ? 'neg' : undefined}>{children}</span>;
}

const dscrText = (v: number | null) => (v === null ? t('dash.noValue') : formatNumber(v, 2));
const sum = (years: FinYearOut[], pick: (y: FinYearOut) => number) => years.reduce((s, y) => s + pick(y), 0);

/** Model yillar bo'yicha + «Итого». */
export function ModelTable({ model, ctx, className }: { model: ReadyModel; ctx: ExportContext; className?: string }) {
  const title = t('fm.table.title');
  const { years, summary, base } = model;
  const headers = [t('fm.col.year'), t('fm.col.capacity'), t('fm.col.generation'), t('fm.col.tariff'), t('fm.col.revenue'), t('fm.col.ebitda'), t('fm.col.margin'), t('fm.col.capex'), t('fm.col.debt'), t('fm.col.net'), t('fm.col.balance'), t('fm.col.dscr')];
  const columns: Column<FinYearOut>[] = [
    { key: 'year', header: headers[0] ?? '', cell: (y) => y.year, align: 'left' },
    { key: 'cap', header: headers[1] ?? '', cell: (y) => formatNumber(y.capacity_mw, 0) },
    { key: 'gen', header: headers[2] ?? '', cell: (y) => formatNumber(y.generation, 0) },
    { key: 'tariff', header: headers[3] ?? '', cell: (y) => formatNumber(y.tariff, 0) },
    { key: 'rev', header: headers[4] ?? '', cell: (y) => <b>{formatMoney(y.revenue)}</b> },
    { key: 'ebitda', header: headers[5] ?? '', cell: (y) => formatMoney(y.ebitda) },
    { key: 'margin', header: headers[6] ?? '', cell: (y) => formatPct(y.margin, 1) },
    { key: 'capex', header: headers[7] ?? '', cell: (y) => formatMoney(y.capex) },
    { key: 'debt', header: headers[8] ?? '', cell: (y) => formatMoney(y.debt_service) },
    { key: 'net', header: headers[9] ?? '', cell: (y) => <Neg bad={y.net_flow < 0}>{formatMoney(y.net_flow)}</Neg> },
    { key: 'bal', header: headers[10] ?? '', cell: (y) => <Neg bad={y.balance < 0}>{formatMoney(y.balance)}</Neg> },
    { key: 'dscr', header: headers[11] ?? '', cell: (y) => <Neg bad={y.dscr !== null && y.dscr < base.covenant}>{dscrText(y.dscr)}</Neg> },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('fm.table.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: years.map((y) => [y.year, y.capacity_mw, y.generation, y.tariff, y.revenue, y.ebitda, y.margin, y.capex, y.debt_service, y.net_flow, y.balance, y.dscr]) })} />}
    >
      <div title={formula('finRevenue')}>
        <Table
          bare
          free
          caption={title}
          columns={columns}
          rows={years}
          rowKey={(y) => y.year}
          footer={
            <tr role="row">
              <td role="cell" className="l">{t('fm.total')}</td>
              <td role="cell" colSpan={3} />
              <td role="cell">{formatMoney(sum(years, (y) => y.revenue))}</td>
              <td role="cell">{formatMoney(summary.ebitda_total)}</td>
              <td role="cell">{formatPct(summary.margin_avg, 1)}</td>
              <td role="cell">{formatMoney(summary.capex_total)}</td>
              <td role="cell">{formatMoney(summary.debt_service_total)}</td>
              <td role="cell">{formatMoney(summary.cum_flow)}</td>
              <td role="cell" />
              <td role="cell">{dscrText(summary.dscr_min)}</td>
            </tr>
          }
        />
      </div>
    </Card>
  );
}

/** Себестоимость и тариф на 1 кВт·ч отпущенной энергии. */
export function CostTariffTable({ years, className }: { years: FinYearOut[]; className?: string }) {
  const title = t('fm.cost.title');
  const columns: Column<FinYearOut>[] = [
    { key: 'year', header: t('fm.col.year'), cell: (y) => y.year, align: 'left' },
    { key: 'tariff', header: t('fm.col.tariff'), cell: (y) => formatNumber(y.tariff, 0) },
    { key: 'cost', header: t('fm.col.cost'), cell: (y) => (y.unit_cost === null ? t('dash.noValue') : formatNumber(y.unit_cost, 0)) },
    {
      key: 'margin',
      header: t('fm.col.kwhMargin'),
      cell: (y) => (y.unit_cost === null ? t('dash.noValue') : <Neg bad={y.tariff - y.unit_cost < 0}>{formatNumber(y.tariff - y.unit_cost, 0)}</Neg>),
    },
  ];
  return (
    <Card className={className} title={title} sub={t('fm.cost.sub')}>
      <div title={formula('finUnitCost')}>
        <Table bare free caption={title} columns={columns} rows={years} rowKey={(y) => y.year} />
      </div>
    </Card>
  );
}

/** Инвестиции и долговая нагрузка по годам. */
export function DebtTable({ years, covenant, className }: { years: FinYearOut[]; covenant: number; className?: string }) {
  const title = t('fm.debt.title');
  const columns: Column<FinYearOut>[] = [
    { key: 'year', header: t('fm.col.year'), cell: (y) => y.year, align: 'left' },
    { key: 'capex', header: t('fm.col.capex'), cell: (y) => formatMoney(y.capex) },
    { key: 'principal', header: t('fm.col.principal'), cell: (y) => formatMoney(y.principal) },
    { key: 'interest', header: t('fm.col.interest'), cell: (y) => formatMoney(y.interest) },
    { key: 'debt', header: t('fm.col.debt'), cell: (y) => formatMoney(y.debt_service) },
    { key: 'ebitda', header: t('fm.col.ebitda'), cell: (y) => formatMoney(y.ebitda) },
    { key: 'dscr', header: t('fm.col.dscr'), cell: (y) => <Neg bad={y.dscr !== null && y.dscr < covenant}>{dscrText(y.dscr)}</Neg> },
    { key: 'free', header: t('fm.col.free'), cell: (y) => <Neg bad={y.net_flow < 0}>{formatMoney(y.net_flow)}</Neg> },
  ];
  return (
    <Card className={className} title={title}>
      <Table bare free caption={title} columns={columns} rows={years} rowKey={(y) => y.year} />
    </Card>
  );
}

const noteOf = (s: FinSummaryOut) => (isScenario(s.scenario) ? t(SCENARIO_NOTE_KEYS[s.scenario]) : s.note);

/** To'rt ssenariy, tanlangani ajratilgan, xulosa belgisi. */
export function ScenarioTable({ model, className }: { model: ReadyModel; className?: string }) {
  const title = t('fm.scenTable.title');
  const covenant = model.base.covenant;
  const columns: Column<FinSummaryOut>[] = [
    {
      key: 'scenario',
      header: t('fm.scenTable.scenario'),
      align: 'left',
      wrap: true,
      cell: (s) => (
        <>
          {s.title}
          <br />
          <span className="note">{noteOf(s)}</span>
        </>
      ),
    },
    { key: 'revenue', header: t('fm.scenTable.revenue'), cell: (s) => formatMoney(s.revenue_last) },
    { key: 'ebitda', header: t('fm.scenTable.ebitda'), cell: (s) => formatMoney(s.ebitda_total) },
    { key: 'margin', header: t('fm.col.margin'), cell: (s) => formatPct(s.margin_avg, 1) },
    { key: 'dscr', header: t('fm.kpi.dscr'), cell: (s) => <Neg bad={s.dscr_min !== null && s.dscr_min < covenant}>{dscrText(s.dscr_min)}</Neg> },
    { key: 'cum', header: t('fm.scenTable.cum'), cell: (s) => <Neg bad={s.cum_flow < 0}>{formatMoney(s.cum_flow)}</Neg> },
    {
      key: 'verdict',
      header: t('fm.scenTable.verdict'),
      align: 'left',
      cell: (s) => <Badge tone={s.verdict === 'funded' ? 'blue' : 'neg'}>{t(s.verdict === 'funded' ? 'fm.verdict.funded' : 'fm.verdict.needs_financing')}</Badge>,
    },
  ];
  return (
    <Card className={className} title={title} sub={t('fm.scenTable.sub')}>
      <Table bare free caption={title} columns={columns} rows={model.scenarios} rowKey={(s) => s.scenario} activeKey={model.scenario} />
    </Card>
  );
}
