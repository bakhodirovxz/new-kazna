import { t } from '../i18n';
import { formatNumber } from '../i18n/format';
import { IconButton } from './Button';
import './table.css';

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPage(page: number): void;
}

export function Pagination({ page, pageSize, total, onPage }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="pager" aria-label={t('table.pagination')}>
      <span aria-live="polite">
        {t('table.range', { from: formatNumber(from), to: formatNumber(to), total: formatNumber(total) })}
      </span>
      <IconButton icon="chevronLeft" label={t('table.prev')} disabled={page <= 1} onClick={() => onPage(page - 1)} />
      <span>{t('table.pageOf', { page, pages })}</span>
      <IconButton icon="chevronRight" label={t('table.next')} disabled={page >= pages} onClick={() => onPage(page + 1)} />
    </nav>
  );
}
