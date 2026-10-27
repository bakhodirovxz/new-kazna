import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { json, mockApi } from '../test/mockApi';
import { createTestClient, Providers } from '../test/render';
import { SVOD } from '../test/s1Fixtures';
import { sectionQuery, toggleBranch, useSection } from './useSection';

describe('useSection', () => {
  it('sends br and per and returns data', async () => {
    const { calls } = mockApi({ 'GET /obzor/svod': json(SVOD) });
    const client = createTestClient();
    const wrapper = ({ children }: { children: ReactNode }) => <Providers client={client}>{children}</Providers>;
    const { result } = renderHook(() => useSection('/obzor/svod', { br: 3, per: 'm08' }), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(SVOD));
    expect(calls[0]?.url.searchParams.get('br')).toBe('3');
    expect(calls[0]?.url.searchParams.get('per')).toBe('m08');
  });

  it('omits empty branch and toggles selection', () => {
    expect(sectionQuery({ br: null, per: 'ytd' })).toEqual({ br: undefined, per: 'ytd' });
    const onBranch = vi.fn();
    toggleBranch({ br: 3, per: 'ytd' }, 3, onBranch);
    toggleBranch({ br: null, per: 'ytd' }, 5, onBranch);
    expect(onBranch.mock.calls).toEqual([[null], [5]]);
  });
});
