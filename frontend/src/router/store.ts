import { useMemo, useSyncExternalStore } from 'react';
import { buildHash, parseHash, type Route } from './hash';

type Listener = () => void;
const listeners = new Set<Listener>();

function emit(): void {
  listeners.forEach((listener) => listener());
}

if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', emit);
  window.addEventListener('popstate', emit);
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function snapshot(): string {
  return window.location.hash;
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, snapshot, snapshot);
  return useMemo(() => parseHash(hash), [hash]);
}

export function currentPath(): string {
  return window.location.hash.replace(/^#/, '');
}

/** pushState/replaceState + qo'lda xabar: hashchange'ni kutmasdan, sinxron yangilanadi. */
export function navigate(to: Route | string, options: { replace?: boolean } = {}): void {
  const target = typeof to === 'string' ? (to.startsWith('#') ? to : `#${to}`) : buildHash(to);
  const normalized = target === '#' ? '' : target;
  if (normalized === window.location.hash) return;
  const url = `${window.location.pathname}${window.location.search}${target}`;
  if (options.replace) window.history.replaceState(window.history.state, '', url);
  else window.history.pushState(null, '', url);
  emit();
}
