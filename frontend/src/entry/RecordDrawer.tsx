import { useMemo, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import { t } from '../i18n';
import { useBranches } from '../meta/api';
import { Button } from '../ui/Button';
import { Combobox } from '../ui/Combobox';
import { Drawer } from '../ui/Drawer';
import { FormError, TextInput } from '../ui/Field';
import { Select } from '../ui/Select';
import { useToast } from '../ui/Toast';
import { useFocusFirstInvalid } from '../admin/useFocusFirstInvalid';
import { useCreateBatch, useOptions, type EntryBatch, type EntryEntity, type EntryField, type EntryRecord } from './api';
import { fromInput, serverErrorText, toInput, unitLabel } from './fields';

export interface RecordDrawerProps {
  entity: EntryEntity;
  record: EntryRecord | null;
  /** Tanlangan filial id (filtr) — yangi yozuv uchun boshlang'ich qiymat. */
  branch: number | null;
  onClose(): void;
  /** Saqlash/yuborish muvaffaqiyatli: sahifa doimiy tasdiq xabarini ko'rsatadi. */
  onSaved?(batch: EntryBatch, sent: boolean): void;
  onOpenExisting(entryId: number): void;
}

type Errors = Record<string, string>;

function RefField({ entity, field, value, onChange, error, branch }: {
  entity: EntryEntity;
  field: EntryField;
  value: string;
  onChange(value: string): void;
  error: string | undefined;
  branch: number | null;
}) {
  const options = useOptions(entity.id, field.name, '', branch);
  const list = useMemo(() => {
    const base = (options.data ?? []).map((o) => ({ value: o.code, label: o.title, hint: o.code }));
    return value && !base.some((o) => o.value === value) ? [{ value, label: value }, ...base] : base;
  }, [options.data, value]);
  return (
    <Combobox
      label={field.title}
      options={list}
      value={value || null}
      onChange={(v) => onChange(v ?? '')}
      error={error ?? null}
      required={field.required}
    />
  );
}

function BranchField({ value, onChange, error }: { value: string; onChange(v: string): void; error: string | undefined }) {
  const branches = useBranches();
  const list = branches.data ?? [];
  const options = [{ value: '', label: '—' }, ...list.map((b) => ({ value: b.code, label: b.name }))];
  return (
    <Select
      label={t('entry.branch')}
      value={value}
      options={options}
      onChange={onChange}
      error={error ?? null}
      required
      disabled={list.length <= 1}
    />
  );
}

export function RecordDrawer({ entity, record, branch, onClose, onSaved, onOpenExisting }: RecordDrawerProps) {
  const toast = useToast();
  const branches = useBranches();
  const create = useCreateBatch();
  const editing = record !== null;
  const initial = (): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const f of entity.fields) {
      if (f.kind === 'secret') out[f.name] = '';
      else out[f.name] = record ? toInput(f, record.values[f.name]) : '';
    }
    return out;
  };
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [reason, setReason] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [conflict, setConflict] = useState<{ code: string; entryId: number | null } | null>(null);
  const formRef = useFocusFirstInvalid<HTMLFormElement>(errors);

  // Filial: yozuvniki > filtrdagi > yagona ruxsat etilgan (qulflangan foydalanuvchi)
  const defaultBranch = record
    ? String(record.values.branch_code ?? '')
    : (branches.data?.find((b) => b.id === branch)?.code ?? (branches.data?.length === 1 ? (branches.data[0]?.code ?? '') : ''));
  const branchCode = values.branch_code || defaultBranch;
  const branchRow = branches.data?.find((b) => b.code === branchCode);
  const set = (name: string) => (value: string) => setValues((v) => ({ ...v, [name]: value }));

  const submit = (send: boolean) => {
    const next: Errors = {};
    const payload: Record<string, string> = {};
    for (const f of entity.fields) {
      const raw = f.name === 'branch_code' ? branchCode : (values[f.name] ?? '');
      if (f.kind === 'secret' && editing && raw.trim() === '') continue; // write-only: bo'sh = o'zgarmaydi
      const res = fromInput(f, raw);
      if ('error' in res) next[f.name] = t(res.error, { n: res.n ?? 0 });
      else if (res.value !== null) payload[f.name] = res.value;
    }
    if (editing && reason.trim().length < 5) next.reason = serverErrorText('reason_required');
    if (!branchRow && !editing) next.branch_code = next.branch_code ?? t('entry.err.required');
    setErrors(next);
    setConflict(null);
    if (Object.keys(next).length > 0) return;
    const branchId = editing ? record.branch_id : (branchRow?.id as number);
    create.mutate(
      {
        entity: entity.id,
        branch_id: branchId,
        origin: 'form',
        submit: send,
        reason: editing ? reason.trim() : null,
        items: [
          {
            entry_id: record?.entry_id ?? null,
            expected_version: record?.version ?? null,
            values: payload,
            delete: false,
          },
        ],
      },
      {
        onSuccess: (batch) => {
          toast.show(send ? t('entry.submitted') : t('entry.saved'), 'success');
          onSaved?.(batch, send);
          onClose();
        },
        onError: (error) => {
          if (!isApiError(error)) return;
          const params = error.params;
          if (error.status === 409) {
            setConflict({ code: error.code, entryId: typeof params.entry_id === 'number' ? params.entry_id : null });
            return;
          }
          const fieldErrors: Errors = {};
          const rows = Array.isArray(params.rows) ? (params.rows as Array<{ field: string; code: string }>) : [];
          for (const r of rows) fieldErrors[r.field] = serverErrorText(r.code);
          const fields = Array.isArray(params.fields) ? (params.fields as string[]) : [];
          for (const name of fields) fieldErrors[name] ??= serverErrorText(error.code);
          if (Object.keys(fieldErrors).length > 0) setErrors(fieldErrors);
        },
      },
    );
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(true);
  };

  const title = editing ? t('entry.edit') : t('entry.add');
  const failure = create.error && !(isApiError(create.error) && (create.error.status === 409 || create.error.status === 422));
  return (
    <Drawer open onClose={onClose} title={`${title}: ${entity.title}`}>
      <form ref={formRef} onSubmit={onSubmit} noValidate className="entry-form">
        {conflict ? (
          <div className="entry-banner" role="alert">
            <p>{serverErrorText(conflict.code)}</p>
            {conflict.code === 'duplicate_record' && conflict.entryId !== null ? (
              <Button variant="secondary" onClick={() => onOpenExisting(conflict.entryId as number)}>
                {t('entry.openExisting')}
              </Button>
            ) : (
              <Button variant="secondary" icon="refresh" onClick={onClose}>
                {t('entry.refresh')}
              </Button>
            )}
          </div>
        ) : null}
        {entity.fields.map((f) => {
          const err = errors[f.name];
          if (f.name === 'branch_code') {
            return <BranchField key={f.name} value={branchCode} onChange={set(f.name)} error={err} />;
          }
          if (f.kind === 'ref') {
            return (
              <RefField key={f.name} entity={entity} field={f} value={values[f.name] ?? ''} onChange={set(f.name)} error={err} branch={branchRow?.id ?? branch} />
            );
          }
          if (f.kind === 'enum') {
            return (
              <Select
                key={f.name}
                label={f.title}
                value={values[f.name] ?? ''}
                options={[{ value: '', label: '—' }, ...(f.options ?? []).map((o) => ({ value: o.code, label: o.title }))]}
                onChange={set(f.name)}
                error={err ?? null}
                required={f.required}
              />
            );
          }
          if (f.kind === 'secret') {
            const mask = record?.masks[f.name];
            return (
              <TextInput
                key={f.name}
                label={f.title}
                type="password"
                autoComplete="off"
                value={values[f.name] ?? ''}
                onChange={(e) => set(f.name)(e.target.value)}
                hint={mask ? t('entry.secretKeep', { mask }) : t('entry.secretHint')}
                error={err ?? null}
                required={f.required && !editing}
              />
            );
          }
          const unit = unitLabel(f);
          return (
            <TextInput
              key={f.name}
              label={unit ? `${f.title}, ${unit}` : f.title}
              type={f.kind === 'date' ? 'date' : f.kind === 'month' ? 'month' : 'text'}
              inputMode={f.kind === 'money' || f.kind === 'volume' || f.kind === 'decimal' || f.kind === 'pct' ? 'decimal' : undefined}
              value={values[f.name] ?? ''}
              onChange={(e) => set(f.name)(e.target.value)}
              error={err ?? null}
              required={f.required}
            />
          );
        })}
        {editing ? (
          <TextInput
            label={t('entry.reason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={errors.reason ?? null}
            required
          />
        ) : null}
        {failure ? <FormError error={create.error} /> : null}
        <div className="entry-form__actions">
          <Button type="button" variant="secondary" loading={create.isPending} onClick={() => submit(false)}>
            {t('entry.saveDraft')}
          </Button>
          <Button type="submit" loading={create.isPending}>
            {t('entry.submit')}
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
