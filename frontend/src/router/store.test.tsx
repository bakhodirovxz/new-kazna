import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { currentPath, navigate, useRoute } from './store';

describe('router store', () => {
  it('pushes a new history entry and updates useRoute', () => {
    const { result } = renderHook(() => useRoute());
    expect(result.current).toEqual({ kind: 'home' });
    const before = window.history.length;
    act(() => navigate({ kind: 'section', section: 'kazna', page: 'svod', br: 3, per: null }));
    expect(window.location.hash).toBe('#kazna/svod?br=3');
    expect(window.history.length).toBe(before + 1);
    expect(result.current).toEqual({ kind: 'section', section: 'kazna', page: 'svod', br: 3, per: null });
    expect(currentPath()).toBe('kazna/svod?br=3');
  });

  it('replaces the current entry when asked', () => {
    const { result } = renderHook(() => useRoute());
    act(() => navigate('#admin/users'));
    const before = window.history.length;
    act(() => navigate('admin/audit', { replace: true }));
    expect(window.history.length).toBe(before);
    expect(result.current).toEqual({ kind: 'admin', page: 'audit' });
  });

  it('does nothing when the target equals the current hash', () => {
    act(() => navigate('#obzor/svod'));
    const before = window.history.length;
    act(() => navigate({ kind: 'section', section: 'obzor', page: 'svod', br: null, per: null }));
    expect(window.history.length).toBe(before);
  });

  it('reacts to hashchange events from the browser', () => {
    const { result } = renderHook(() => useRoute());
    act(() => {
      window.history.replaceState(null, '', '#2fa');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(result.current).toEqual({ kind: 'mfa' });
  });
});
