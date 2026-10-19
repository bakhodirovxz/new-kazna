import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type {
  EnrollConfirmOut,
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
    onSuccess: () => client.invalidateQueries({ queryKey: sessionsKey }),
  });
}
