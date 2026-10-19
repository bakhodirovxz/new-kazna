import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, apiUrl, isApiError, toApiError, type Query } from '../api/client';
import { t } from '../i18n';
import { dayStartIso } from '../i18n/format';
import type {
  AlertRuleOut,
  AuditOut,
  BuildOut,
  EtlRequestOut,
  EtlRunDetail,
  EtlRunOut,
  EtlRunRequest,
  KeyOut,
  RotateOut,
  VerifyOut,
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

export const ETL_PAGE_SIZE = 50;
export const AUDIT_PAGE_SIZE = 100;
export const AUDIT_EXPORT_LIMIT = 50_000; // backend EXPORT_LIMIT

/** poll — so'rov navbatga qo'yilgandan keyin (run qatori hali yo'q) tarixni vaqti-vaqti bilan yangilaydi. */
export function useEtlRuns(page: number, poll = false) {
  return useQuery({
    queryKey: [...adminKeys.etlRuns, page],
    queryFn: ({ signal }) => api<Page<EtlRunOut>>('/admin/etl/runs', { signal, query: { page, page_size: ETL_PAGE_SIZE } }),
    placeholderData: keepPreviousData,
    staleTime: 0,
    refetchInterval: (query) => (poll || query.state.data?.items.some((run) => run.status === 'running') ? 15_000 : false),
  });
}

export function useEtlRun(id: number | null) {
  return useQuery({
    queryKey: [...adminKeys.etlRuns, 'detail', id],
    queryFn: ({ signal }) => api<EtlRunDetail>(`/admin/etl/runs/${id ?? 0}`, { signal }),
    enabled: id !== null,
    staleTime: 0,
  });
}

export function useRequestEtlRun() {
  const invalidate = useInvalidate(adminKeys.etlRuns);
  return useMutation({
    mutationFn: (body: EtlRunRequest) => api<EtlRequestOut>('/admin/etl/run', { method: 'POST', body }),
    onSuccess: invalidate,
    meta: { inline: true },
  });
}

export function useBuilds() {
  return useQuery({
    queryKey: adminKeys.builds,
    queryFn: ({ signal }) => api<BuildOut[]>('/admin/builds', { signal }),
    staleTime: 0,
  });
}

export function useRollbackBuild() {
  const client = useQueryClient();
  const onError = useRefetchOnConflict(adminKeys.builds);
  return useMutation({
    mutationFn: (buildId: number | null) => api<BuildOut>('/admin/builds/rollback', { method: 'POST', body: { build_id: buildId } }),
    // Aktiv build o'zgardi: yuqori panel/.srcbar yangilanish vaqti eski build'ni 5 daqiqagacha ko'rsatmasin (A16.4).
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: adminKeys.builds }),
        client.invalidateQueries({ queryKey: ['meta', 'freshness'] }),
      ]),
    onError,
    meta: { inline: true },
  });
}

export interface AuditFilters {
  from: string;
  to: string;
  userId: string;
  action: string;
  result: '' | 'ok' | 'fail' | 'denied';
}

export const EMPTY_AUDIT_FILTERS: AuditFilters = { from: '', to: '', userId: '', action: '', result: '' };

/** Sana — Toshkent kuni; "По" kuni ham kiradi (to_ts — keyingi kun boshi, qat'iy "<"). */
export function auditQuery(filters: AuditFilters): Query {
  return {
    from_ts: filters.from ? dayStartIso(filters.from) : undefined,
    to_ts: filters.to ? dayStartIso(filters.to, 1) : undefined,
    user_id: filters.userId || undefined,
    action: filters.action || undefined,
    result: filters.result || undefined,
  };
}

export function useAudit(filters: AuditFilters, page: number) {
  return useQuery({
    queryKey: [...adminKeys.audit, filters, page],
    queryFn: ({ signal }) =>
      api<Page<AuditOut>>('/audit', { signal, query: { ...auditQuery(filters), page, page_size: AUDIT_PAGE_SIZE } }),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
}

export function useVerifyAudit() {
  return useMutation({
    mutationFn: () => api<VerifyOut>('/audit/verify', { method: 'POST' }),
    meta: { inline: true }, // 429 formada qayta urinish vaqti bilan
  });
}

/** CSV: fetch -> Blob (URL'da ma'lumot yo'q, uchinchi tomon yo'q). `page` yuborilmaydi — server butun tanlovni beradi. */
export function useExportAudit() {
  return useMutation({
    mutationFn: async (filters: AuditFilters) => {
      let response: Response;
      try {
        response = await fetch(apiUrl('/audit/export.csv', auditQuery(filters)), {
          credentials: 'same-origin',
          headers: { Accept: 'text/csv' },
        });
      } catch {
        throw new ApiError(0, 'network', t('error.network'));
      }
      if (!response.ok) throw toApiError(response, await response.json().catch(() => null));
      return { blob: await response.blob(), truncated: response.headers.get('X-Export-Truncated') === 'true' };
    },
    meta: { inline: true },
  });
}

export function useKeys() {
  return useQuery({
    queryKey: adminKeys.keys,
    queryFn: ({ signal }) => api<KeyOut[]>('/admin/keys', { signal }),
    staleTime: 0,
  });
}

export function useRotateKey() {
  const invalidate = useInvalidate(adminKeys.keys);
  return useMutation({
    mutationFn: (purpose: string) => api<RotateOut>(`/admin/keys/${encodeURIComponent(purpose)}/rotate`, { method: 'POST' }),
    onSuccess: invalidate,
    onError: invalidate, // muvaffaqiyatsiz rotatsiyadan keyin ham holat serverdan qayta o'qiladi
    meta: { inline: true },
  });
}
