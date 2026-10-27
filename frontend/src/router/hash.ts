/** TZ 5: "#<раздел>/<страница>" + filtrlar parametrlarda. Marshrutlar qat'iy ro'yxat; qolgani — notfound. */
export type Route =
  | { kind: 'home' }
  | { kind: 'login'; next: string | null }
  | { kind: 'mfa' }
  | { kind: 'mfaEnroll' }
  | { kind: 'password' }
  | { kind: 'sessions' }
  | { kind: 'noaccess' }
  | { kind: 'notfound' }
  | { kind: 'admin'; page: string | null }
  | { kind: 'section'; section: string; page: string | null; br: number | null; per: string | null };

export type SectionRoute = Extract<Route, { kind: 'section' }>;

const ID_RE = /^[a-z][a-z0-9_-]{0,31}$/;
const PER_RE = /^(?:ytd|q[1-4]|m(?:0[1-9]|1[0-2]))$/;
const BR_RE = /^[1-9]\d{0,4}$/;
const NOT_FOUND: Route = { kind: 'notfound' };

export function parseHash(raw: string): Route {
  const hash = raw.startsWith('#') ? raw.slice(1) : raw;
  const q = hash.indexOf('?');
  const path = q >= 0 ? hash.slice(0, q) : hash;
  const params = new URLSearchParams(q >= 0 ? hash.slice(q + 1) : '');
  const parts = path.split('/').filter((part) => part !== '');
  if (parts.length === 0) return { kind: 'home' };
  if (parts.length > 2) return NOT_FOUND;
  const [first, second] = parts as [string, string | undefined];

  switch (first) {
    case 'login':
      return second === undefined ? { kind: 'login', next: safeNext(params.get('next')) } : NOT_FOUND;
    case '2fa':
      if (second === undefined) return { kind: 'mfa' };
      return second === 'setup' ? { kind: 'mfaEnroll' } : NOT_FOUND;
    case 'password':
      return second === undefined ? { kind: 'password' } : NOT_FOUND;
    case 'account':
      return second === 'sessions' ? { kind: 'sessions' } : NOT_FOUND;
    case 'noaccess':
      return second === undefined ? { kind: 'noaccess' } : NOT_FOUND;
    case 'admin':
      if (second === undefined) return { kind: 'admin', page: null };
      return ID_RE.test(second) ? { kind: 'admin', page: second } : NOT_FOUND;
  }

  if (!ID_RE.test(first) || (second !== undefined && !ID_RE.test(second))) return NOT_FOUND;
  const br = params.get('br');
  // TZ'dagi `per=5` shakli `m05` ga keltiriladi (R1/A3.1).
  const perRaw = params.get('per');
  const per = perRaw !== null && /^(?:0?[1-9]|1[0-2])$/.test(perRaw) ? `m${perRaw.padStart(2, '0')}` : perRaw;
  return {
    kind: 'section',
    section: first,
    page: second ?? null,
    br: br !== null && BR_RE.test(br) ? Number(br) : null,
    per: per !== null && PER_RE.test(per) ? per : null,
  };
}

export function buildHash(route: Route): string {
  switch (route.kind) {
    case 'home':
    case 'notfound':
      return '#';
    case 'login':
      return route.next ? `#login?next=${encodeURIComponent(route.next)}` : '#login';
    case 'mfa':
      return '#2fa';
    case 'mfaEnroll':
      return '#2fa/setup';
    case 'password':
      return '#password';
    case 'sessions':
      return '#account/sessions';
    case 'noaccess':
      return '#noaccess';
    case 'admin':
      return route.page ? `#admin/${route.page}` : '#admin';
    case 'section': {
      const params = new URLSearchParams();
      if (route.br !== null) params.set('br', String(route.br));
      if (route.per !== null) params.set('per', route.per);
      const query = params.toString();
      return `#${route.section}${route.page ? `/${route.page}` : ''}${query ? `?${query}` : ''}`;
    }
  }
}

/** Login'dan keyin qaytiladigan joy: faqat ilova ichidagi sahifa, kanonik ko'rinishda (open redirect yo'q). */
export function safeNext(next: string | null): string | null {
  if (!next) return null;
  const route = parseHash(next);
  if (route.kind !== 'section' && route.kind !== 'admin' && route.kind !== 'sessions') return null;
  return buildHash(route).slice(1);
}

export function isPublicRoute(route: Route): boolean {
  return route.kind === 'login' || route.kind === 'mfa' || route.kind === 'mfaEnroll';
}
