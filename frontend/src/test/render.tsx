import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement, ReactNode } from 'react';
import { AuthFlowProvider } from '../auth/AuthFlow';
import { ToastProvider } from '../ui/Toast';

export function createTestClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: 60_000 }, mutations: { retry: false } },
  });
}

export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <ToastProvider>
      <QueryClientProvider client={client}>
        <AuthFlowProvider>{children}</AuthFlowProvider>
      </QueryClientProvider>
    </ToastProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  options: { hash?: string; client?: QueryClient } = {},
): RenderResult & { user: ReturnType<typeof userEvent.setup>; client: QueryClient } {
  if (options.hash !== undefined) window.history.replaceState(null, '', options.hash || '/');
  const client = options.client ?? createTestClient();
  const user = userEvent.setup();
  const result = render(<Providers client={client}>{ui}</Providers>);
  return { ...result, user, client };
}
