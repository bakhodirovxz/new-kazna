import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiBlob, postRaw } from '../api/client';
import type { components } from '../api/schema';

type S = components['schemas'];
export type EntryEntity = S['EntityOut'];
export type EntryField = S['FieldOut'];
export type EntryRecord = S['RecordOut'];
export type EntryBatch = S['BatchOut'];
export type EntryBatchDetail = S['BatchDetailOut'];
export type EntryHistory = S['HistoryOut'];
export type EntryOption = S['OptionOut'];
export type EntryItem = S['ItemIn'];
export interface EntryPage<T> {
  items: T[];
  total: number;
  page: number;
}

export const entryKeys = {
  entities: ['entry', 'entities'] as const,
  records: ['entry', 'records'] as const,
  batches: ['entry', 'batches'] as const,
};

export interface RecordFilters {
  br: number | null;
  per: string;
  status?: 'active' | 'pending' | 'deleted';
}

export function useEntities() {
  return useQuery({
    queryKey: entryKeys.entities,
    queryFn: ({ signal }) => api<EntryEntity[]>('/data/entities', { signal }),
    staleTime: 5 * 60_000,
  });
}

export function useRecords(entity: string, filters: RecordFilters, page = 1) {
  return useQuery({
    queryKey: [...entryKeys.records, entity, filters, page],
    queryFn: ({ signal }) =>
      api<EntryPage<EntryRecord>>(`/data/entities/${entity}/records`, {
        signal,
        query: { br: filters.br, per: filters.per, status: filters.status, page },
      }),
  });
}

export function useOptions(entity: string, field: string, q: string, br: number | null, enabled = true) {
  return useQuery({
    queryKey: ['entry', 'options', entity, field, q, br],
    queryFn: ({ signal }) =>
      api<EntryOption[]>(`/data/entities/${entity}/options/${field}`, { signal, query: { q, br } }),
    enabled,
    staleTime: 30_000,
  });
}

export function useHistory(entryId: number | null) {
  return useQuery({
    queryKey: ['entry', 'history', entryId],
    queryFn: ({ signal }) => api<EntryHistory>(`/data/records/${entryId}/history`, { signal }),
    enabled: entryId !== null,
  });
}

export function useBatches(
  box: 'mine' | 'inbox',
  status?: string,
  opts: { background?: boolean; enabled?: boolean } = {},
) {
  return useQuery({
    enabled: opts.enabled ?? true,
    refetchInterval: opts.background ? 60_000 : false,
    queryKey: [...entryKeys.batches, 'list', box, status ?? null],
    queryFn: ({ signal }) =>
      api<EntryPage<EntryBatch>>('/data/batches', { signal, query: { box, status }, background: opts.background }),
  });
}

export function useBatch(id: number | null, opts: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: [...entryKeys.batches, 'one', id],
    queryFn: ({ signal }) => api<EntryBatchDetail>(`/data/batches/${id}`, { signal, background: opts.poll }),
    enabled: id !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.publication?.status;
      return opts.poll && (status === 'queued' || status === 'running') ? 5000 : false;
    },
  });
}

function useInvalidate() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: entryKeys.records }),
      client.invalidateQueries({ queryKey: entryKeys.batches }),
      client.invalidateQueries({ queryKey: ['entry', 'history'] }),
    ]);
}

export const IMPORT_TYPES: Record<string, string> = {
  csv: 'text/csv',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};
export const IMPORT_MAX_BYTES = 1_048_576;

export function downloadTemplate(entity: string, kind: 'csv' | 'xlsx') {
  return apiBlob(`/data/entities/${entity}/template.${kind}`);
}

/** Fayl -> draft paket (xom tana, CSRF `api()` ichida); gcTime: 0 -- fayl mazmuni keshda qolmasin. */
export function useImportFile() {
  const invalidate = useInvalidate();
  return useMutation({
    gcTime: 0,
    mutationFn: (v: { entity: string; branch_id: number; file: File; type: string }) =>
      postRaw<EntryBatch>(`/data/entities/${v.entity}/import`, v.file, v.type, {
        query: { branch_id: v.branch_id },
        headers: { 'X-File-Name': encodeURIComponent(v.file.name) },
      }),
    onSuccess: invalidate,
  });
}

export interface CreateBatchIn {
  entity: string;
  branch_id: number;
  origin: 'form' | 'grid';
  items: EntryItem[];
  submit?: boolean;
  reason?: string | null;
}

/** gcTime: 0 -- `variables` (bank hisob raqami ochiq matnda) MutationCache'da qolmasin. */
export function useCreateBatch() {
  const invalidate = useInvalidate();
  return useMutation({
    gcTime: 0,
    mutationFn: (body: CreateBatchIn) => api<EntryBatch>('/data/batches', { method: 'POST', body }),
    onSuccess: invalidate,
  });
}

export function useUpdateBatch() {
  const invalidate = useInvalidate();
  return useMutation({
    gcTime: 0,
    mutationFn: (v: { id: number; expected_version: number; items: EntryItem[] }) =>
      api<EntryBatch>(`/data/batches/${v.id}`, {
        method: 'PUT',
        body: { expected_version: v.expected_version, items: v.items },
      }),
    onSuccess: invalidate,
  });
}

function batchAction<V extends { id: number; expected_version: number }>(action: string, extra: (v: V) => object) {
  return function useAction() {
    const invalidate = useInvalidate();
    return useMutation({
      mutationFn: (v: V) =>
        api<EntryBatch>(`/data/batches/${v.id}/${action}`, {
          method: 'POST',
          body: { expected_version: v.expected_version, ...extra(v) },
        }),
      onSuccess: invalidate,
    });
  };
}

export const useSubmitBatch = batchAction<{ id: number; expected_version: number; reason?: string | null }>(
  'submit',
  (v) => ({ reason: v.reason ?? null }),
);
export const useWithdrawBatch = batchAction<{ id: number; expected_version: number }>('withdraw', () => ({}));
export const useApproveBatch = batchAction<{ id: number; expected_version: number; comment?: string | null }>(
  'approve',
  (v) => ({ comment: v.comment ?? null }),
);
export const useRejectBatch = batchAction<{ id: number; expected_version: number; comment: string }>(
  'reject',
  (v) => ({ comment: v.comment }),
);
