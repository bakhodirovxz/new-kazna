import { describe, expect, it } from 'vitest';
import { buildHash, isPublicRoute, parseHash, safeNext, type Route } from './hash';

describe('parseHash', () => {
  it.each<[string, Route]>([
    ['', { kind: 'home' }],
    ['#', { kind: 'home' }],
    ['#kazna/svod?br=3&per=m05', { kind: 'section', section: 'kazna', page: 'svod', br: 3, per: 'm05' }],
    ['#kazna/svod?br=3&per=5', { kind: 'section', section: 'kazna', page: 'svod', br: 3, per: 'm05' }],
    ['#kazna/svod?per=12', { kind: 'section', section: 'kazna', page: 'svod', br: null, per: 'm12' }],
    ['#kazna/svod?per=13', { kind: 'section', section: 'kazna', page: 'svod', br: null, per: null }],
    ['#kazna/svod?per=0', { kind: 'section', section: 'kazna', page: 'svod', br: null, per: null }],
    ['#kazna', { kind: 'section', section: 'kazna', page: null, br: null, per: null }],
    ['#/obzor/vnimanie', { kind: 'section', section: 'obzor', page: 'vnimanie', br: null, per: null }],
    ['#kazna/svod?br=0&per=m13', { kind: 'section', section: 'kazna', page: 'svod', br: null, per: null }],
    ['#kazna/svod?br=3abc&per=YTD', { kind: 'section', section: 'kazna', page: 'svod', br: null, per: null }],
    ['#obzor/svod?per=q4&per=ytd', { kind: 'section', section: 'obzor', page: 'svod', br: null, per: 'q4' }],
    ['#2fa', { kind: 'mfa' }],
    ['#2fa/setup', { kind: 'mfaEnroll' }],
    ['#password', { kind: 'password' }],
    ['#account/sessions', { kind: 'sessions' }],
    ['#noaccess', { kind: 'noaccess' }],
    ['#admin', { kind: 'admin', page: null }],
    ['#admin/users', { kind: 'admin', page: 'users' }],
    ['#login', { kind: 'login', next: null }],
    ['#login?next=kazna%2Fsvod%3Fbr%3D3', { kind: 'login', next: 'kazna/svod?br=3' }],
    ['#login?next=https%3A%2F%2Fevil.example', { kind: 'login', next: null }],
    ['#KAZNA/svod', { kind: 'notfound' }],
    ['#a/b/c', { kind: 'notfound' }],
    ['#account', { kind: 'notfound' }],
    ['#2fa/other', { kind: 'notfound' }],
    ['#admin/Users', { kind: 'notfound' }],
  ])('%s', (hash, expected) => {
    expect(parseHash(hash)).toEqual(expected);
  });
});

describe('buildHash', () => {
  it('builds canonical hashes and omits empty filters', () => {
    expect(buildHash({ kind: 'section', section: 'kazna', page: 'svod', br: 3, per: 'm05' })).toBe(
      '#kazna/svod?br=3&per=m05',
    );
    expect(buildHash({ kind: 'section', section: 'kazna', page: null, br: null, per: null })).toBe('#kazna');
    expect(buildHash({ kind: 'login', next: 'kazna/svod?br=3' })).toBe('#login?next=kazna%2Fsvod%3Fbr%3D3');
    expect(buildHash({ kind: 'login', next: null })).toBe('#login');
    expect(buildHash({ kind: 'mfaEnroll' })).toBe('#2fa/setup');
    expect(buildHash({ kind: 'sessions' })).toBe('#account/sessions');
    expect(buildHash({ kind: 'admin', page: 'audit' })).toBe('#admin/audit');
    expect(buildHash({ kind: 'home' })).toBe('#');
    expect(buildHash({ kind: 'notfound' })).toBe('#');
  });

  it('round-trips through parseHash', () => {
    const route: Route = { kind: 'section', section: 'kadry', page: 'fot', br: 12, per: 'q2' };
    expect(parseHash(buildHash(route))).toEqual(route);
  });
});

describe('safeNext', () => {
  it('keeps only in-app destinations and canonicalises them', () => {
    expect(safeNext('kazna/svod?br=3&per=bad')).toBe('kazna/svod?br=3');
    expect(safeNext('#admin/users')).toBe('admin/users');
    expect(safeNext('account/sessions')).toBe('account/sessions');
  });

  it('rejects auth routes, garbage and absolute URLs', () => {
    expect(safeNext(null)).toBeNull();
    expect(safeNext('')).toBeNull();
    expect(safeNext('login?next=kazna')).toBeNull();
    expect(safeNext('2fa')).toBeNull();
    expect(safeNext('password')).toBeNull();
    expect(safeNext('javascript:alert(1)')).toBeNull();
    expect(safeNext('//evil.example/x')).toBeNull();
    expect(safeNext('https://evil.example')).toBeNull();
  });

  it.each([
    '\\\\evil.example',
    '/\\evil.example',
    '\\/evil.example',
    '%2F%2Fevil.example',
    'https:%2F%2Fevil.example',
    ' //evil.example',
    '\t//evil.example',
    'data:text/html,x',
    'JavaScript:alert(1)',
    'kazna/svod#x',
    'kazna/svod\\x',
    'kazna:80/svod',
    'user@evil.example',
  ])('rejects bypass attempt %j', (attempt) => {
    expect(safeNext(attempt)).toBeNull();
  });

  it('never yields a value that could leave the app', () => {
    // '//evil/x' degrades to the in-app route 'evil/x' (after '#' there is no host semantics).
    for (const attempt of ['//evil/x', '///kazna', '#//kazna/svod']) {
      const out = safeNext(attempt);
      expect(out).not.toBeNull();
      expect(out).not.toMatch(/^[/\\]|[:\\]/);
    }
  });
});

it('marks only sign-in routes as public', () => {
  expect(isPublicRoute({ kind: 'login', next: null })).toBe(true);
  expect(isPublicRoute({ kind: 'mfa' })).toBe(true);
  expect(isPublicRoute({ kind: 'mfaEnroll' })).toBe(true);
  expect(isPublicRoute({ kind: 'password' })).toBe(false);
  expect(isPublicRoute({ kind: 'home' })).toBe(false);
});

it('accepts the TZ alias per=05 as m05', () => {
  expect(parseHash('#kazna/svod?per=05')).toMatchObject({ per: 'm05' });
});
