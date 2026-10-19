import { useEffect, useRef } from 'react';
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
  const size = Math.max(1, Math.floor(pageSize) || 1);
  const pages = Math.max(1, Math.ceil(total / size));
  const current = Math.min(pages, Math.max(1, Math.floor(page) || 1));
  const from = total === 0 ? 0 : (current - 1) * size + 1;
  const to = Math.min(total, current * size);
  const prevRef = useRef<HTMLButtonElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const pending = useRef<'prev' | 'next' | null>(null);

  // Bosilgan tugma chekkada o'chsa, fokus tushib ketmasin — qarama-qarshi tugmaga o'tadi.
  useEffect(() => {
    const was = pending.current;
    pending.current = null;
    if (was === 'prev' && prevRef.current?.disabled) nextRef.current?.focus();
    if (was === 'next' && nextRef.current?.disabled) prevRef.current?.focus();
  }, [current]);

  return (
    <nav className="pager" aria-label={t('table.pagination')}>
      <span aria-live="polite">
        {t('table.range', { from: formatNumber(from), to: formatNumber(to), total: formatNumber(total) })}
      </span>
      <IconButton
        ref={prevRef}
        icon="chevronLeft"
        label={t('table.prev')}
        disabled={current <= 1}
        onClick={() => {
          pending.current = 'prev';
          onPage(current - 1);
        }}
      />
      <span>{t('table.pageOf', { page: formatNumber(current), pages: formatNumber(pages) })}</span>
      <IconButton
        ref={nextRef}
        icon="chevronRight"
        label={t('table.next')}
        disabled={current >= pages}
        onClick={() => {
          pending.current = 'next';
          onPage(current + 1);
        }}
      />
    </nav>
  );
}
