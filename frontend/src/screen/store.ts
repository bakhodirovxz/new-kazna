import { useSyncExternalStore } from 'react';
import { setBackgroundMode } from '../api/client';

export interface ScreenState {
  active: boolean;
  ended: boolean;
}

let state: ScreenState = { active: false, ended: false };
const listeners = new Set<() => void>();

function apply(next: ScreenState): void {
  state = next;
  document.documentElement.classList.toggle('screen-mode', next.active);
  setBackgroundMode(next.active);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function startScreen(): void {
  apply({ active: true, ended: false });
}

export function stopScreen(): void {
  if (state.active) apply({ ...state, active: false });
}

/** Kiosk paytida sessiya tugadi (401) — rejim to'xtaydi, aniq qayta kirish ekrani ko'rsatiladi. */
export function markSessionEnded(): void {
  apply({ active: false, ended: true });
}

export function dismissEnded(): void {
  if (state.ended) apply({ ...state, ended: false });
}

export function isScreenActive(): boolean {
  return state.active;
}

export function getScreenState(): ScreenState {
  return state;
}

export function useScreenState(): ScreenState {
  return useSyncExternalStore(subscribe, getScreenState, getScreenState);
}
