import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';

/** TZ 6 «Состояния»: skelet (sakrashsiz), xato — «Повторить» va oxirgi muvaffaqiyatli yuklash vaqti. */
export function SectionData<T>({ query, children }: { query: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  const banner = query.isError ? (
    <ErrorBanner error={query.error} onRetry={() => void query.refetch()} lastSuccessAt={query.dataUpdatedAt || null} retrying={query.isFetching} />
  ) : null;
  if (query.data === undefined) return banner ?? <PageSkeleton />;
  return (
    <>
      {banner}
      {children(query.data)}
    </>
  );
}
