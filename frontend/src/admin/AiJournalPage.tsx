import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/client';
import type { AiRequestOut, Page } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { formatDateTime, formatNumber } from '../i18n/format';
import { Badge, type BadgeTone } from '../ui/Badge';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Pagination } from '../ui/Pagination';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import type { AdminPageProps } from './registry';

const PAGE_SIZE = 50;
const PRESET_KEYS: Record<string, MessageKey> = {
  yoy: 'ai.preset.yoy', risks: 'ai.preset.risks', priorities: 'ai.preset.priorities', plan: 'ai.preset.plan',
};
const STATUS_KEYS: Record<string, MessageKey> = {
  ok: 'aij.status.ok', running: 'aij.status.running', error: 'aij.status.error', timeout: 'aij.status.timeout',
  cancelled: 'aij.status.cancelled', refused: 'aij.status.refused',
};

function tone(status: string): BadgeTone {
  return status === 'ok' ? 'ok' : status === 'running' ? 'blue' : 'warn';
}

/** TZ 7 «Журнал»: дата, пользователь, раздел, фильтры, вопрос, длина ответа (90 kun). `audit:read`. */
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- admin sahifa shartnomasi (me), bu sahifada kerak emas
export default function AiJournalPage(_props: AdminPageProps) {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['admin', 'ai-requests', page],
    queryFn: ({ signal }) => api<Page<AiRequestOut>>('/audit/ai-requests', { signal, query: { page, page_size: PAGE_SIZE } }),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
  if (query.isError) return <ErrorBanner error={query.error} lastSuccessAt={query.dataUpdatedAt} onRetry={() => void query.refetch()} />;
  if (query.isPending) return <PageSkeleton />;
  const title = t('admin.page.aijournal');
  const columns: Column<AiRequestOut>[] = [
    { key: 'time', header: t('aij.col.time'), cell: (r) => formatDateTime(r.created_at) },
    { key: 'user', header: t('aij.col.user'), cell: (r) => r.username },
    { key: 'page', header: t('aij.col.page'), cell: (r) => `${r.section} / ${r.page}` },
    {
      key: 'question',
      header: t('aij.col.question'),
      cell: (r) => r.question ?? (r.preset && PRESET_KEYS[r.preset] ? t(PRESET_KEYS[r.preset]) : t('ai.run')),
      wrap: true,
    },
    { key: 'status', header: t('aij.col.status'), cell: (r) => <Badge tone={tone(r.status)}>{t(STATUS_KEYS[r.status] ?? 'aij.status.error')}</Badge> },
    { key: 'answer', header: t('aij.col.answer'), cell: (r) => formatNumber(r.answer_chars), align: 'right' },
    { key: 'model', header: t('aij.col.model'), cell: (r) => r.model },
  ];
  return (
    <Card title={title}>
      <p className="note">{t('aij.hint')}</p>
      <Table caption={title} columns={columns} rows={query.data.items} rowKey={(r) => r.id} free />
      <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPage={setPage} />
    </Card>
  );
}
