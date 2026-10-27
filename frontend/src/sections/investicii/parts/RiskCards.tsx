import type { InvObjectOut, InvObjectStagesOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { formatDays, formatPp } from '../../../dash/people';
import { Rank } from '../../../dash/Rank';
import '../../../dash/s4.css';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

interface ListProps {
  rows: InvObjectOut[];
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

function select(rows: InvObjectOut[], filters: FilterState, onBranch: (br: number | null) => void) {
  const byId = new Map(rows.map((o) => [o.object_id, o]));
  return (id: string | number) => {
    const o = byId.get(Number(id));
    if (o) toggleBranch(filters, o.branch_id, onBranch);
  };
}

/** Prototip «Объекты с отставанием»: исполнение графика ниже 90%, черта — план на дату. */
export function LaggingCard({ rows, filters, onBranch, className }: ListProps) {
  const title = t('inv.risk.lagTitle');
  return (
    <Card className={className} title={title} sub={t('inv.risk.lagSub')}>
      {rows.length ? (
        <Rank
          label={title}
          items={rows.map((o) => ({ id: o.object_id, name: o.name, value: o.fact_ytd, mark: o.plan_to_date, note: t('inv.risk.lagNote', { pct: formatPct(o.execution, 0) }), negative: o.status === 'risk' }))}
          onSelect={select(rows, filters, onBranch)}
        />
      ) : (
        <p className="note">{t('inv.risk.lagNone')}</p>
      )}
    </Card>
  );
}

/** Prototip «Разрыв финансирования и физического выполнения» (> 20 п.п.). */
export function GapsCard({ rows, filters, onBranch, className }: ListProps) {
  const title = t('inv.risk.gapTitle');
  return (
    <Card className={className} title={title} sub={t('inv.risk.gapSub')}>
      <div title={formula('finGap')}>
        {rows.length ? (
          <Rank
            label={title}
            items={rows.map((o) => ({ id: o.object_id, name: o.name, value: o.gap_pp ?? 0, note: t('inv.risk.gapNote', { fin: formatPct(o.financial, 0), phys: formatPct(o.physical, 0) }), negative: true }))}
            format={(v) => formatPp(v)}
            onSelect={select(rows, filters, onBranch)}
          />
        ) : (
          <p className="note">{t('inv.risk.gapNone')}</p>
        )}
      </div>
    </Card>
  );
}

/** Prototip `stageCard`: пройденные этапы (лента) и отклонения по срокам. */
export function StagesCard({ stages, className }: { stages: InvObjectStagesOut[]; className?: string }) {
  return (
    <Card className={className} title={t('inv.risk.stageTitle')} sub={t('inv.risk.stageSub')}>
      {stages.length ? (
        stages.map((s) => {
          const done = s.stages.filter((x) => x.done).length;
          const next = s.stages.find((x) => !x.done);
          return (
            <div className="prog" key={s.object_id}>
              <div className="prog__h">
                <span>{s.name}</span>
                <b className={s.late ? 'neg' : undefined}>{t('inv.risk.stageDone', { done, total: s.stages.length })}</b>
              </div>
              <div className="stg" aria-hidden="true">
                {s.stages.map((x) => (
                  <span
                    key={x.stage_no}
                    className={x.done ? (x.late ? 'is-late' : 'is-done') : undefined}
                    title={x.fact_date ? t('inv.risk.stageTip', { name: x.name, date: formatDate(x.fact_date) }) : t('inv.risk.stageTipOpen', { name: x.name })}
                  />
                ))}
              </div>
              <div className="prog__f">
                <span>{next ? next.name : t('inv.risk.stageAll')}</span>
                <span>{s.late ? t('inv.risk.stageLate', { count: s.late }) : t('inv.risk.stageOk')}</span>
              </div>
            </div>
          );
        })
      ) : (
        <p className="note">{t('inv.risk.stageNone')}</p>
      )}
    </Card>
  );
}

/** Prototip «Незакрытые авансы»: авансы старше 90 дней. */
export function AdvancesCard({ rows, className }: { rows: InvObjectOut[]; className?: string }) {
  const title = t('inv.risk.advTitle');
  const columns: Column<InvObjectOut>[] = [
    { key: 'name', header: t('inv.col.object'), cell: (o) => o.name, wrap: true },
    { key: 'amount', header: t('inv.risk.advAmount'), cell: (o) => <b>{formatMoney(o.advance)}</b>, align: 'right' },
    { key: 'days', header: t('inv.risk.advDays'), cell: (o) => <Badge tone="neg">{formatDays(o.advance_days)}</Badge> },
  ];
  return (
    <Card className={className} title={title} sub={t('inv.risk.advSub')}>
      <div title={formula('advances')}>
        {rows.length ? <Table caption={title} columns={columns} rows={rows} rowKey={(o) => o.object_id} free /> : <p className="note">{t('inv.risk.advNone')}</p>}
      </div>
    </Card>
  );
}
