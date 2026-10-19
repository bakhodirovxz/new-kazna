import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { expect, it } from 'vitest';
import { json, mockApi } from '../test/mockApi';
import { BRANCHES, FRESH_OK, MENU_FULL, PERIODS } from '../test/fixtures';
import { createTestClient, Providers } from '../test/render';
import { useBranches, useFreshness, useMenu, usePeriods } from './api';

it('loads menu, branches, periods and freshness', async () => {
  mockApi({
    'GET /meta/menu': json(MENU_FULL),
    'GET /meta/branches': json(BRANCHES),
    'GET /meta/periods': json(PERIODS),
    'GET /meta/freshness': json(FRESH_OK),
  });
  const client = createTestClient();
  const wrapper = ({ children }: { children: ReactNode }) => <Providers client={client}>{children}</Providers>;
  const { result } = renderHook(() => ({ menu: useMenu(), branches: useBranches(), periods: usePeriods(), fresh: useFreshness() }), { wrapper });
  await waitFor(() => {
    expect(result.current.menu.data?.groups).toHaveLength(5);
    expect(result.current.branches.data).toHaveLength(4);
    expect(result.current.periods.data?.default).toBe('ytd');
    expect(result.current.fresh.data?.stale).toBe(false);
  });
});

it('does not request the menu while disabled', () => {
  const server = mockApi({});
  const client = createTestClient();
  const wrapper = ({ children }: { children: ReactNode }) => <Providers client={client}>{children}</Providers>;
  renderHook(() => useMenu(false), { wrapper });
  expect(server.calls).toHaveLength(0);
});
