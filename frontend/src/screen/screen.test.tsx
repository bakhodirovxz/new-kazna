import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, backgroundHeaders } from '../api/client';
import { makeQueryClient } from '../app/queryClient';
import type { Route } from '../router/hash';
import { MENU_AUDITOR, MENU_FULL } from '../test/fixtures';
import { apiError, mockApi } from '../test/mockApi';
import { ScreenEnded } from './ScreenEnded';
import { ScreenMode } from './ScreenMode';
import { dismissEnded, getScreenState, startScreen, stopScreen } from './store';
import { ROTATE_MS, wallSections } from './useScreenRotation';

const route: Route = { kind: 'section', section: 'kazna', page: 'platezhi', br: 3, per: 'm08' };

function stubReducedMotion(reduce: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation((query: string) => ({
    matches: reduce && query.includes('prefers-reduced-motion'),
    media: query, onchange: null,
    addEventListener: () => undefined, removeEventListener: () => undefined,
    addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false,
  }));
}

beforeEach(() => {
  vi.useFakeTimers();
  window.history.replaceState(null, '', '#kazna/platezhi?br=3&per=m08');
});

afterEach(() => {
  act(() => stopScreen());
  dismissEnded();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Экран (kiosk)', () => {
  it('lists only permitted sections in the TZ order', () => {
    expect(wallSections(MENU_FULL)).toEqual(['obzor', 'kazna', 'proizvodstvo', 'investicii', 'finmodel', 'sklad']);
    expect(wallSections(MENU_AUDITOR)).toEqual(['obzor']);
  });

  it('rotates every 60 seconds keeping filters, marks requests as background and exits on Esc', () => {
    stubReducedMotion(false);
    render(<ScreenMode menu={MENU_FULL} route={route} />);
    fireEvent.click(screen.getByRole('button', { name: 'Экран' }));
    expect(document.documentElement).toHaveClass('screen-mode');
    expect(document.documentElement).toHaveClass('screen-motion');
    expect(backgroundHeaders()).toEqual({ 'X-UGK-Background': '1' });
    expect(window.location.hash).toBe('#obzor/svod?br=3&per=m08');
    act(() => vi.advanceTimersByTime(ROTATE_MS));
    expect(window.location.hash).toBe('#kazna/svod?br=3&per=m08');
    act(() => vi.advanceTimersByTime(ROTATE_MS * 5));
    expect(window.location.hash).toBe('#obzor/svod?br=3&per=m08');
    expect(screen.getByRole('status')).toHaveTextContent('Автопоказ: раздел меняется каждую минуту');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(document.documentElement).not.toHaveClass('screen-mode');
    expect(backgroundHeaders()).toEqual({});
    act(() => vi.advanceTimersByTime(ROTATE_MS));
    expect(window.location.hash).toBe('#obzor/svod?br=3&per=m08');
  });

  it('respects prefers-reduced-motion and exits with the wallbar button', () => {
    stubReducedMotion(true);
    render(<ScreenMode menu={MENU_AUDITOR} route={route} />);
    fireEvent.click(screen.getByRole('button', { name: 'Экран' }));
    expect(document.documentElement).toHaveClass('screen-mode');
    expect(document.documentElement).not.toHaveClass('screen-motion');
    act(() => vi.advanceTimersByTime(ROTATE_MS));
    expect(window.location.hash).toBe('#obzor/svod?br=3&per=m08');
    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(getScreenState().active).toBe(false);
  });

  it('shows a clear re-login screen when the session ends in kiosk mode', async () => {
    vi.useRealTimers();
    mockApi({ 'GET /obzor/svod': apiError(401, 'session_expired', 'Сеанс завершён, войдите снова') });
    const client = makeQueryClient(() => undefined);
    act(() => startScreen());
    await act(async () => {
      await client.fetchQuery({ queryKey: ['section', '/obzor/svod'], queryFn: () => api('/obzor/svod') }).catch(() => undefined);
    });
    expect(getScreenState()).toEqual({ active: false, ended: true });
    expect(window.location.hash.startsWith('#login')).toBe(true);
    render(<ScreenEnded />);
    expect(screen.getByRole('alertdialog', { name: 'Сеанс завершён' })).toHaveTextContent('30 минут');
    fireEvent.click(screen.getByRole('button', { name: 'Войти снова' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});
