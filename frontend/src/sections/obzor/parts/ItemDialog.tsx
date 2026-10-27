import type { ItemAmountOut, ItemBranchesOut } from '../../../api/types';
import { Rank } from '../../../dash/Rank';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { ErrorBanner } from '../../../ui/ErrorBanner';
import { Modal } from '../../../ui/Modal';
import { Skeleton } from '../../../ui/Skeleton';
import { useSection } from '../../useSection';

/** Prototip `openList`: statya → filiallar (reja bilan) — «Обзор» va «Исполнение платежей». */
export function ItemDialog({ path, filters, onClose }: { path: string; filters: FilterState; onClose(): void }) {
  const query = useSection<ItemBranchesOut>(path, filters);
  const data = query.data;
  const out = data?.item.direction === 'out';
  const max = Math.max(1, ...(data?.rows.map((r) => r.fact) ?? [1]));
  return (
    <Modal
      open
      onClose={onClose}
      title={data?.item.name ?? '…'}
      note={data ? t('obzor.item.note', { direction: out ? t('obzor.item.out') : t('obzor.item.in'), period: data.period.label.toLowerCase() }) : undefined}
    >
      {query.isError ? <ErrorBanner error={query.error} onRetry={() => void query.refetch()} /> : null}
      {!data ? (
        <Skeleton variant="card" />
      ) : data.rows.length === 0 ? (
        <p className="note">{t('obzor.item.empty')}</p>
      ) : (
        <>
          <p className="bigline">
            <b>{formatMoney(data.total, 2)}</b>
          </p>
          <table className="cmp">
            <caption className="visually-hidden">{data.item.name}</caption>
            <thead>
              <tr>
                <th scope="col">{t('dash.branch')}</th>
                {out ? <th scope="col">{t('dash.plan')}</th> : null}
                <th scope="col">{t('dash.fact')}</th>
                <th scope="col">{t('dash.share')}</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.branch_id}>
                  <th scope="row">{r.name}</th>
                  {out ? <td>{formatMoney(r.plan)}</td> : null}
                  <td>{formatMoney(r.fact)}</td>
                  <td>
                    {formatPct(data.total ? r.fact / data.total : null)}
                    <span className="mini" aria-hidden="true">
                      <i style={{ width: `${(r.fact / max) * 100}%` }} />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Modal>
  );
}

export function AllItemsDialog({ title, items, onPick, onClose }: { title: string; items: ItemAmountOut[]; onPick(id: number): void; onClose(): void }) {
  return (
    <Modal open onClose={onClose} title={title} note={t('obzor.top.sub')}>
      <Rank label={title} items={items.map((i) => ({ id: i.item_id, name: i.name, value: i.amount }))} onSelect={(id) => onPick(Number(id))} />
    </Modal>
  );
}
