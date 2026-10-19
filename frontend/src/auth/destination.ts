import type { MeOut } from '../api/types';
import { parseHash, safeNext, type Route } from '../router/hash';

export function destinationAfterSignIn(me: MeOut, returnTo: string | null): Route {
  if (me.must_change_password) return { kind: 'password' };
  const target = safeNext(returnTo);
  return target ? parseHash(target) : { kind: 'home' };
}
