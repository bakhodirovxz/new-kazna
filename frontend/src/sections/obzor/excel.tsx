import { useEffect, useMemo, useState } from 'react';
import { apiUrl } from '../../api/client';
import type { BranchCashOut, DetailRowOut, ObzorExcelOut } from '../../api/types';
import { useMe } from '../../auth/api';
import { CardExport } from '../../dash/CardExport';
import { t, type MessageKey } from '../../i18n';
import { formatNumber } from '../../i18n/format';
import { Card } from '../../ui/Card';
import { Table, type Column } from '../../ui/Table';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { sectionQuery, toggleBranch, useSection } from '../useSection';
import { CashKpis } from './parts/CashKpis';

type Dir = 'all' | 'in' | 'out';
const m1 = (v: number | null) => (v === null ? '—' : formatNumber(v, 1));

function summaryColumns(): Column<BranchCashOut>[] {
  const num = (key: keyof BranchCashOut, header: string): Column<BranchCashOut> => ({
    key,
    header,
    align: 'right',
    sortValue: (r) => r[key] as number | null,
    cell: (r) => {
      const v = r[key] as number | null;
      return <span className={v !== null && v < 0 && (key === 'net' || key === 'diff') ? 'neg' : undefined}>{m1(v)}</span>;
    },
  });
  return [
    { key: 'name', header: t('dash.branch'), cell: (r) => r.name, sortValue: (r) => r.name, wrap: true, align: 'left' },
    num('opening', t('obzor.kpi.opening')),
    num('inflow', t('obzor.kpi.inflow')),
    num('outflow', t('obzor.kpi.outflow')),
    num('net', t('obzor.kpi.net')),
    num('closing', t('obzor.kpi.closing')),
    num('diff', t('obzor.kpi.diff')),
  ];
}

function detailColumns(): Column<DetailRowOut>[] {
  return [
    { key: 'branch', header: t('dash.branch'), cell: (r) => r.branch_name, sortValue: (r) => r.branch_name, wrap: true, align: 'left' },
    { key: 'dir', header: t('obzor.excel.direction'), cell: (r) => (r.direction === 'in' ? t('obzor.excel.dirInOne') : t('obzor.excel.dirOutOne')), sortValue: (r) => r.direction, align: 'left' },
    { key: 'item', header: t('dash.item'), cell: (r) => r.item_name, sortValue: (r) => r.item_name, wrap: true, align: 'left' },
    { key: 'activity', header: t('obzor.excel.activity'), cell: (r) => (r.direction === 'in' ? '–' : t(`dash.activity.${r.activity}` as MessageKey)), sortValue: (r) => r.activity, align: 'left' },
    { key: 'amount', header: t('obzor.excel.amount'), cell: (r) => m1(r.amount), sortValue: (r) => r.amount, align: 'right' },
  ];
}

function Detail({ rows, ctx }: { rows: DetailRowOut[]; ctx: { section: string; page: string; br: number | null; per: string } }) {
  const [dir, setDir] = useState<Dir>('all');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const id = window.setTimeout(() => setQ(text.trim().toLowerCase()), 250);
    return () => window.clearTimeout(id);
  }, [text]);
  const filtered = useMemo(
    () => rows.filter((r) => (dir === 'all' || r.direction === dir) && (!q || `${r.branch_name} ${r.item_name}`.toLowerCase().includes(q))),
    [rows, dir, q],
  );
  const saldo = filtered.reduce((s, r) => s + (r.direction === 'in' ? r.amount : -r.amount), 0);
  const title = t('obzor.excel.detail');
  const dirs: Array<[Dir, MessageKey]> = [['all', 'obzor.excel.dirAll'], ['in', 'obzor.excel.dirIn'], ['out', 'obzor.excel.dirOut']];
  return (
    <Card
      title={title}
      actions={
        <div className="dash-bar">
          <div className="seg" role="group" aria-label={t('obzor.excel.direction')}>
            {dirs.map(([value, key]) => (
              <button key={value} type="button" aria-pressed={dir === value} onClick={() => setDir(value)}>
                {t(key)}
              </button>
            ))}
          </div>
          <input className="search" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('obzor.excel.search')} aria-label={t('obzor.excel.search')} />
        </div>
      }
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers: [t('dash.branch'), t('obzor.excel.direction'), t('dash.item'), t('obzor.excel.activity'), t('obzor.excel.amount')],
            rows: filtered.map((r) => [r.branch_name, r.direction === 'in' ? t('obzor.excel.dirInOne') : t('obzor.excel.dirOutOne'), r.item_name, r.direction === 'in' ? '–' : t(`dash.activity.${r.activity}` as MessageKey), r.amount]),
          })}
        />
      }
    >
      <Table
        caption={title}
        columns={detailColumns()}
        rows={filtered}
        rowKey={(r) => `${r.branch_id}-${r.item_id}-${r.direction}`}
        initialSort={{ key: 'amount', dir: 'desc' }}
        empty={<p className="note">{rows.length === 0 ? t('obzor.excel.noDetail') : t('obzor.excel.nothing')}</p>}
        bare
        footer={
          <tr>
            <td colSpan={4} className="l">{t('obzor.excel.rows', { count: filtered.length })}</td>
            <td>{t('obzor.excel.saldo', { value: m1(saldo) })}</td>
          </tr>
        }
      />
    </Card>
  );
}

export default function ObzorExcel({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ObzorExcelOut>('/obzor/excel', filters);
  const me = useMe();
  const ctx = { section, page, br: filters.br, per: filters.per };
  const canXlsx = me.data?.permissions.includes('export:xlsx') ?? false;
  return (
    <SectionData query={query}>
      {(data) => {
        const title = t('obzor.excel.summary');
        const cols = summaryColumns();
        return (
          <>
            <CashKpis kpis={data.kpis} period={data.period} />
            <Card
              title={title}
              sub={t('obzor.excel.units', { period: data.period.label })}
              actions={
                canXlsx ? (
                  <a className="btn btn--secondary" href={apiUrl('/obzor/excel.xlsx', sectionQuery(filters))} download>
                    {t('obzor.excel.download')}
                  </a>
                ) : null
              }
              exportSlot={
                <CardExport
                  title={title}
                  ctx={ctx}
                  csv={() => ({
                    headers: cols.map((c) => c.header),
                    rows: [...data.branches, data.total].map((b) => [b.name, b.opening, b.inflow, b.outflow, b.net, b.closing, b.diff]),
                  })}
                />
              }
            >
              <Table
                caption={title}
                columns={cols}
                rows={data.branches}
                rowKey={(r) => r.branch_id}
                onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)}
                activeKey={filters.br}
                free
                bare
                footer={
                  <tr>
                    <td className="l">{data.total.name}</td>
                    <td data-label={t('obzor.kpi.opening')}>{m1(data.total.opening)}</td>
                    <td data-label={t('obzor.kpi.inflow')}>{m1(data.total.inflow)}</td>
                    <td data-label={t('obzor.kpi.outflow')}>{m1(data.total.outflow)}</td>
                    <td data-label={t('obzor.kpi.net')}>{m1(data.total.net)}</td>
                    <td data-label={t('obzor.kpi.closing')}>{m1(data.total.closing)}</td>
                    <td data-label={t('obzor.kpi.diff')} className={(data.total.diff ?? 0) < 0 ? 'neg' : undefined}>{m1(data.total.diff)}</td>
                  </tr>
                }
              />
            </Card>
            <Detail rows={data.detail} ctx={ctx} />
          </>
        );
      }}
    </SectionData>
  );
}
