import type { QueryClient } from '@tanstack/react-query';
import type { MeOut } from '../api/types';
import { createQueryClient } from '../api/queryClient';
import { meKey } from '../auth/api';
import { isPublicRoute, parseHash, safeNext } from '../router/hash';
import { currentPath, navigate } from '../router/store';

/** Sessiya tugadi: kesh va AuthFlow tozalanadi, joriy kanonik yo'l `next` bilan login'ga. Idempotent:
 *  login/2FA marshrutida hech narsa qilmaydi, shuning uchun N ta parallel 401 — bitta o'tish. */
export function endSession(client: QueryClient, clearFlow: () => void): void {
  if (isPublicRoute(parseHash(window.location.hash))) return;
  const next = safeNext(currentPath());
  clearFlow();
  navigate({ kind: 'login', next }, { replace: true });
  queueMicrotask(() => client.clear());
}

/** Spec 8 xato siyosatini router bilan bog'laydi. */
export function makeQueryClient(
  notify: (message: string) => void,
  clearFlow: () => void = () => undefined,
  remember: (path: string | null) => void = () => undefined,
): QueryClient {
  const client: QueryClient = createQueryClient({
    onUnauthenticated: () => endSession(client, clearFlow),
    onPasswordChange: () => {
      remember(safeNext(currentPath()));
      client.setQueryData<MeOut>(meKey, (old) => (old ? { ...old, must_change_password: true } : old)); // majburiy rejim
      navigate({ kind: 'password' }, { replace: true });
    },
    onForbidden: () => navigate({ kind: 'noaccess' }, { replace: true }),
    notify,
  });
  return client;
}
