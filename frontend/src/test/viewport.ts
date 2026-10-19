/** jsdom'da matchMedia yo'q: oddiy min/max-width so'rovlarini window.innerWidth bo'yicha hisoblaymiz. */
type Listener = (event: MediaQueryListEvent) => void;

interface Entry {
  query: string;
  matches: boolean;
  listeners: Set<Listener>;
}

const entries = new Set<Entry>();

function evaluate(query: string): boolean {
  if (query.includes('prefers-reduced-motion') || query.includes('pointer')) return false;
  const width = window.innerWidth;
  const mins = [...query.matchAll(/min-width:\s*([\d.]+)px/g)].map((m) => Number(m[1]));
  const maxs = [...query.matchAll(/max-width:\s*([\d.]+)px/g)].map((m) => Number(m[1]));
  return mins.every((v) => width >= v) && maxs.every((v) => width <= v);
}

export function installMatchMedia(): void {
  window.matchMedia = (query: string): MediaQueryList => {
    const entry: Entry = { query, matches: evaluate(query), listeners: new Set() };
    entries.add(entry);
    const mql = {
      get matches() {
        return entry.matches;
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, listener: Listener) => entry.listeners.add(listener),
      removeEventListener: (_type: string, listener: Listener) => entry.listeners.delete(listener),
      addListener: (listener: Listener) => entry.listeners.add(listener),
      removeListener: (listener: Listener) => entry.listeners.delete(listener),
      dispatchEvent: () => true,
    };
    return mql as unknown as MediaQueryList;
  };
}

function setWidth(width: number): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width });
}

export function setViewport(width: number): void {
  setWidth(width);
  for (const entry of entries) {
    const next = evaluate(entry.query);
    if (next === entry.matches) continue;
    entry.matches = next;
    const event = { matches: next, media: entry.query } as MediaQueryListEvent;
    entry.listeners.forEach((listener) => listener(event));
  }
}

export function resetViewport(): void {
  entries.clear();
  setWidth(1440);
}
