import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from '../api/client';
import type {
  AlertRuleOut,
  AlertRuleUpdate,
  FinAssumptionItem,
  FinAssumptionOut,
  Page,
  PermissionOut,
  PositionIn,
  PositionOut,
  PositionUpdate,
  RoleIn,
  RoleOut,
  RoleUpdate,
  TemporaryPassword,
  UserCreate,
  UserCreated,
  UserOut,
  UserUpdate,
} from '../api/types';

export const USERS_PAGE_SIZE = 50;

export const adminKeys = {
  users: ['admin', 'users'] as const,
  positions: ['admin', 'positions'] as const,
  roles: ['admin', 'roles'] as const,
  permissions: ['admin', 'permissions'] as const,
  alertRules: ['admin', 'alert-rules'] as const,
  finAssumptions: ['admin', 'fin-assumptions'] as const,
  etlRuns: ['admin', 'etl-runs'] as const,
  builds: ['admin', 'builds'] as const,
  audit: ['admin', 'audit'] as const,
  keys: ['admin', 'keys'] as const,
};

export function useUsers(q: string, page: number) {
  return useQuery({
    queryKey: [...adminKeys.users, q, page],
    queryFn: ({ signal }) =>
      api<Page<UserOut>>('/admin/users', { signal, query: { q: q || undefined, page, page_size: USERS_PAGE_SIZE } }),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
}

export function usePositions() {
  return useQuery({
    queryKey: adminKeys.positions,
    queryFn: ({ signal }) => api<PositionOut[]>('/admin/positions', { signal }),
    staleTime: 0,
    meta: { silent: true }, // admin:users bilan 403 mumkin: dialog ichida xabar, global «Нет доступа» emas
  });
}

function useInvalidate(key: readonly string[]) {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: key });
}

/** Parallel tahrir (409) yoki o'chirilgan yozuv (404): ro'yxat qayta yuklanadi, xabar dialogda qoladi. */
function useRefetchOnConflict(key: readonly string[]) {
  const invalidate = useInvalidate(key);
  return (error: unknown) => {
    if (isApiError(error, 409) || isApiError(error, 404)) void invalidate();
  };
}

export function useCreateUser() {
  const invalidate = useInvalidate(adminKeys.users);
  const onError = useRefetchOnConflict(adminKeys.users);
  return useMutation({
    gcTime: 0, // vaqtinchalik parol keshda qolmasin
    mutationFn: (body: UserCreate) => api<UserCreated>('/admin/users', { method: 'POST', body }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true }, // xato dialog ichida, takroriy toast yo'q
  });
}

export function useUpdateUser() {
  const invalidate = useInvalidate(adminKeys.users);
  const onError = useRefetchOnConflict(adminKeys.users);
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: UserUpdate }) =>
      api<UserOut>(`/admin/users/${id}`, { method: 'PATCH', body }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true }, // xato dialog ichida, takroriy toast yo'q
  });
}

export function useSetUserActive() {
  const invalidate = useInvalidate(adminKeys.users);
  const onError = useRefetchOnConflict(adminKeys.users);
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api<UserOut>(`/admin/users/${id}/${active ? 'unblock' : 'block'}`, { method: 'POST' }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true }, // xato dialog ichida, takroriy toast yo'q
  });
}

export function useResetUserPassword() {
  const invalidate = useInvalidate(adminKeys.users);
  const onError = useRefetchOnConflict(adminKeys.users);
  return useMutation({
    gcTime: 0, // vaqtinchalik parol keshda qolmasin
    mutationFn: (id: number) => api<TemporaryPassword>(`/admin/users/${id}/reset-password`, { method: 'POST' }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true }, // xato dialog ichida, takroriy toast yo'q
  });
}

export function useResetUserMfa() {
  const invalidate = useInvalidate(adminKeys.users);
  const onError = useRefetchOnConflict(adminKeys.users);
  return useMutation({
    mutationFn: (id: number) => api<undefined>(`/admin/users/${id}/reset-2fa`, { method: 'POST' }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true }, // xato dialog ichida, takroriy toast yo'q
  });
}

export function useRoles() {
  return useQuery({
    queryKey: adminKeys.roles,
    queryFn: ({ signal }) => api<RoleOut[]>('/admin/roles', { signal }),
    staleTime: 0,
  });
}

export function usePermissions() {
  return useQuery({
    queryKey: adminKeys.permissions,
    queryFn: ({ signal }) => api<PermissionOut[]>('/admin/permissions', { signal }),
    staleTime: 30 * 60_000,
  });
}

export type SaveRoleInput = { id: null; body: RoleIn } | { id: number; body: RoleUpdate };

export function useSaveRole() {
  const client = useQueryClient();
  const onError = useRefetchOnConflict(adminKeys.roles);
  return useMutation({
    mutationFn: (input: SaveRoleInput) =>
      input.id === null
        ? api<RoleOut>('/admin/roles', { method: 'POST', body: input.body })
        : api<RoleOut>(`/admin/roles/${input.id}`, { method: 'PATCH', body: input.body }),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: adminKeys.roles }),
        client.invalidateQueries({ queryKey: adminKeys.positions }),
      ]),
    onError,
    meta: { inline: true }, // xato dialog ichida, takroriy toast yo'q
  });
}

export type SavePositionInput = { id: null; body: PositionIn } | { id: number; body: PositionUpdate };

export function useSavePosition() {
  const invalidate = useInvalidate(adminKeys.positions);
  const onError = useRefetchOnConflict(adminKeys.positions);
  return useMutation({
    mutationFn: (input: SavePositionInput) =>
      input.id === null
        ? api<PositionOut>('/admin/positions', { method: 'POST', body: input.body })
        : api<PositionOut>(`/admin/positions/${input.id}`, { method: 'PATCH', body: input.body }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true },
  });
}

export function useAlertRules() {
  return useQuery({
    queryKey: adminKeys.alertRules,
    queryFn: ({ signal }) => api<AlertRuleOut[]>('/admin/alert-rules', { signal }),
    staleTime: 0,
  });
}

export function useAlertRuleHistory(code: string | null) {
  return useQuery({
    queryKey: [...adminKeys.alertRules, 'history', code],
    queryFn: ({ signal }) => api<AlertRuleOut[]>(`/admin/alert-rules/${encodeURIComponent(code ?? '')}/history`, { signal }),
    enabled: code !== null,
    staleTime: 0,
  });
}

export function useUpdateAlertRule() {
  const invalidate = useInvalidate(adminKeys.alertRules); // tarix ham shu prefiksda
  const onError = useRefetchOnConflict(adminKeys.alertRules);
  return useMutation({
    mutationFn: ({ code, body }: { code: string; body: AlertRuleUpdate }) =>
      api<AlertRuleOut>(`/admin/alert-rules/${encodeURIComponent(code)}`, { method: 'PATCH', body }),
    onSuccess: invalidate,
    onError, // 409 conflict_modified: xabar dialogda, ro'yxat/tarix qayta yuklanadi
    meta: { inline: true },
  });
}

export function useFinAssumptions() {
  return useQuery({
    queryKey: adminKeys.finAssumptions,
    queryFn: ({ signal }) => api<FinAssumptionOut[]>('/admin/fin-assumptions', { signal }),
    staleTime: 0,
  });
}

export function useUpdateFinAssumptions() {
  const invalidate = useInvalidate(adminKeys.finAssumptions);
  const onError = useRefetchOnConflict(adminKeys.finAssumptions);
  return useMutation({
    mutationFn: (items: FinAssumptionItem[]) =>
      api<FinAssumptionOut[]>('/admin/fin-assumptions', { method: 'PUT', body: { items } }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true },
  });
}
