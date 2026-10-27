import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from '../api/client';
import type {
  EnrollBeginIn,
  EnrollConfirmOut,
  EnrollFinishIn,
  EnrollStartOut,
  LoginIn,
  LoginOut,
  MeOut,
  MfaIn,
  MfaTokenIn,
  PasswordChangeIn,
  SessionOut,
} from '../api/types';
import { navigate } from '../router/store';
import { useAuthFlow } from './AuthFlow';

export const meKey = ['auth', 'me'] as const;
export const sessionsKey = ['auth', 'sessions'] as const;

export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: ({ signal }) => api<MeOut>('/auth/me', { signal }),
    retry: false,
    meta: { silent: true }, // 401 = «не вошёл»: RequireAuth o'zi yo'naltiradi, global redirect emas
    staleTime: 60_000,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: (body: LoginIn) => api<LoginOut>('/auth/login', { method: 'POST', body }),
    meta: { silent: true },
    gcTime: 0, // sir (parol/kod/token) MutationCache'da qolmasin
  });
}

export function useVerifyMfa() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: MfaIn) => api<MeOut>('/auth/2fa/verify', { method: 'POST', body }),
    meta: { silent: true },
    gcTime: 0, // sir (parol/kod/token) MutationCache'da qolmasin
    onSuccess: (me) => {
      client.clear(); // oldingi foydalanuvchi keshi yangisiga o'tmasin
      client.setQueryData(meKey, me);
    },
  });
}

/** Kirgan foydalanuvchi 2FA'ni keyin ulaydi: ulash sahifasiga sessiya rejimida o'tadi (token yo'q;
 *  parol sahifada so'raladi, challenge serverda sessiyaga bog'langan). */
export function useStartEnrollment() {
  const flow = useAuthFlow();
  const me = useMe();
  return () => {
    flow.begin({ mfaToken: '', step: 'session_enroll', username: me.data?.username ?? '', returnTo: null });
    navigate({ kind: 'mfaEnroll' });
  };
}

export function useEnrollBegin() {
  return useMutation({
    mutationFn: (body: EnrollBeginIn) => api<EnrollStartOut>('/auth/2fa/enroll/begin', { method: 'POST', body }),
    meta: { inline: true }, // 422/429 formada
    gcTime: 0, // parol va sir MutationCache'da qolmasin
  });
}

export function useEnrollFinish() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: EnrollFinishIn) => api<EnrollConfirmOut>('/auth/2fa/enroll/finish', { method: 'POST', body }),
    meta: { silent: true },
    gcTime: 0,
    onSuccess: (result) => {
      client.clear();
      client.setQueryData(meKey, result.user);
    },
  });
}

export function useDismissMfaOffer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<undefined>('/auth/2fa/offer/dismiss', { method: 'POST' }),
    onSuccess: () => client.setQueryData<MeOut>(meKey, (old) => (old ? { ...old, mfa_offer: false } : old)),
  });
}

export function useEnrollStart() {
  return useMutation({
    mutationFn: (body: MfaTokenIn) => api<EnrollStartOut>('/auth/2fa/enroll/start', { method: 'POST', body }),
    meta: { silent: true },
    gcTime: 0, // sir (parol/kod/token) MutationCache'da qolmasin
  });
}

export function useEnrollConfirm() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: MfaIn) => api<EnrollConfirmOut>('/auth/2fa/enroll/confirm', { method: 'POST', body }),
    meta: { silent: true },
    gcTime: 0, // sir (parol/kod/token) MutationCache'da qolmasin
    onSuccess: (result) => {
      client.clear();
      client.setQueryData(meKey, result.user);
    },
  });
}

/** 422 (joriy parol / siyosat) formada ko'rsatiladi; 401 global ishlovga ketadi.
 *  Muvaffaqiyatda keshdagi `must_change_password` darhol false — RequireAuth qayta #password ga qaytarmasin. */
export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PasswordChangeIn) => api<undefined>('/auth/password/change', { method: 'POST', body }),
    meta: { inline: true }, // 422/429 formada ko'rsatiladi; 401 va password_change_required global
    gcTime: 0,
    onSuccess: async () => {
      client.setQueryData<MeOut>(meKey, (old) => (old ? { ...old, must_change_password: false } : old));
      await client.invalidateQueries({ queryKey: meKey });
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  const flow = useAuthFlow();
  return useMutation({
    mutationFn: () => api<undefined>('/auth/logout', { method: 'POST' }),
    meta: { silent: true },
    onSettled: () => {
      flow.clear();
      navigate({ kind: 'login', next: null }, { replace: true });
      queueMicrotask(() => client.clear());
    },
  });
}

export function useSessions() {
  return useQuery({
    queryKey: sessionsKey,
    queryFn: ({ signal }) => api<SessionOut[]>('/auth/sessions', { signal }),
    staleTime: 0,
  });
}

export function useRevokeSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<undefined>(`/auth/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    meta: { inline: true }, // 429 ConfirmDialog ichida ko'rsatiladi (ikki marta toast emas)
    onSuccess: () => client.invalidateQueries({ queryKey: sessionsKey }),
    onError: (err) => {
      if (isApiError(err, 404)) void client.invalidateQueries({ queryKey: sessionsKey }); // sessiya allaqachon yo'q
    },
  });
}
