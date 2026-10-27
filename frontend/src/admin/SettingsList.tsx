import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { SettingOut, SettingVersionOut } from '../api/types';
import { EnrollLink } from '../auth/EnrollLink';
import { t, type MessageKey } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Checkbox, Field, FormError, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { OtpInput } from '../ui/OtpInput';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useSettingHistory, useSettings, useUpdateSetting } from './api';
import { displaySetting, formatSetting, parseSetting, rangeHint } from './settingValue';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const CATEGORIES: Record<string, MessageKey> = {
  data: 'settings.category.data',
  etl: 'settings.category.etl',
  quality: 'settings.category.quality',
  retention: 'settings.category.retention',
  notify: 'settings.category.notify',
  security: 'settings.category.security',
  ops: 'settings.category.ops',
};
const ORDER = Object.keys(CATEGORIES);

/** S1–S5 kategoriyalari (kazna, banks, …) lug'atda bo'lmasa — kalit nomi. */
function categoryTitle(category: string): string {
  return Object.hasOwn(CATEGORIES, category) ? t(CATEGORIES[category] as MessageKey) : category;
}

export function SourceBadge({ source }: { source: string }) {
  if (source === 'panel') return <Badge tone="blue">{t('settings.source.panel')}</Badge>;
  if (source === 'env') return <Badge tone="warn">{t('settings.source.env')}</Badge>;
  return <Badge tone="neutral">{t('settings.source.default')}</Badge>;
}

export interface FieldEditorProps {
  setting: SettingOut;
  value: string;
  onChange(value: string): void;
  error?: string | undefined;
}

export function FieldEditor({ setting, value, onChange, error }: FieldEditorProps) {
  const label = setting.title;
  if (setting.kind === 'bool') {
    return <Checkbox label={label} checked={value === 'true'} onChange={(v) => onChange(String(v))} />;
  }
  if (setting.kind === 'list' || setting.kind === 'json') {
    return (
      <Field label={label} hint={setting.kind === 'list' ? t('settings.listHint') : undefined} error={error}>
        {({ id, describedBy, invalid }) => (
          <textarea id={id} className="input" rows={6} spellCheck={false} aria-describedby={describedBy} aria-invalid={invalid || undefined} value={value} onChange={(e) => onChange(e.target.value)} />
        )}
      </Field>
    );
  }
  const numeric = setting.kind === 'int' || setting.kind === 'float';
  return (
    <TextInput
      label={label}
      hint={numeric && !error ? rangeHint(setting) : undefined /* xato bo'lsa oraliq matni xatoda — takrorlanmasin */}
      inputMode={numeric ? 'decimal' : undefined}
      spellCheck={false}
      value={value}
      error={error}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function SettingsList({ perm }: { perm: string }) {
  const settings = useSettings();
  const [editingKey, setEditingKey] = useState<string | null>(null);
  if (settings.isError) return <ErrorBanner error={settings.error} lastSuccessAt={settings.dataUpdatedAt} onRetry={() => void settings.refetch()} />;
  if (settings.isPending) return <PageSkeleton />;
  const rows = settings.data.filter((s) => s.perm === perm);
  // Jonli obyekt: 409 dan keyin ro'yxat qayta yuklanadi va dialog yangi versiya bilan qayta urinadi.
  const editing = rows.find((s) => s.key === editingKey) ?? null;
  if (!rows.length) return <EmptyState title={t('settings.empty')} />;
  const rank = (c: string) => (ORDER.includes(c) ? ORDER.indexOf(c) : ORDER.length);
  const categories = [...new Set(rows.map((s) => s.category))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  const columns: Column<SettingOut>[] = [
    { key: 'name', header: t('settings.col.name'), align: 'left', wrap: true, cell: (s) => (<span className="cell-main"><b>{s.title}</b><small className="mono">{s.key}</small></span>) },
    { key: 'value', header: t('settings.col.value'), align: 'left', wrap: true, cell: (s) => <span className="mono">{displaySetting(s, s.value)}</span> },
    { key: 'source', header: t('settings.col.source'), align: 'left', cell: (s) => <SourceBadge source={s.source} /> },
    { key: 'version', header: t('settings.col.version'), cell: (s) => s.version || '—' },
    { key: 'updated', header: t('settings.col.updated'), cell: (s) => (s.updated_at ? formatDateTime(s.updated_at) : '—') },
  ];
  return (
    <>
      {categories.map((category) => (
        <Card key={category} title={categoryTitle(category)}>
          <Table caption={categoryTitle(category)} captionHidden columns={columns} rows={rows.filter((s) => s.category === category)} rowKey={(s) => s.key} onRowClick={(s) => setEditingKey(s.key)} free />
        </Card>
      ))}
      {editing ? <SettingDialog setting={editing} onClose={() => setEditingKey(null)} /> : null}
    </>
  );
}

type Errors = { value?: string; reason?: string; otp?: string };

function SettingDialog({ setting, onClose }: { setting: SettingOut; onClose(): void }) {
  const formId = useId();
  const toast = useToast();
  const update = useUpdateSetting();
  const history = useSettingHistory(setting.key);
  const [raw, setRaw] = useState(() => formatSetting(setting, setting.value));
  const [reason, setReason] = useState('');
  const [otp, setOtp] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const formRef = useFocusFirstInvalid(errors);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parseSetting(setting, raw);
    const next: Errors = {};
    if (!parsed.ok) next.value = parsed.error;
    if (setting.guarded && reason.trim().length < 5) next.reason = t('settings.reasonRequired');
    if (setting.step_up && !/^\d{6}$/.test(otp)) next.otp = t('settings.otpRequired');
    setErrors(next);
    if (!parsed.ok || Object.keys(next).length) return;
    update.mutate(
      {
        key: setting.key,
        body: {
          value: parsed.value,
          expected_version: setting.version,
          ...(setting.guarded ? { reason: reason.trim() } : {}),
          ...(setting.step_up ? { otp } : {}),
        },
      },
      {
        onSuccess: () => {
          toast.show(t('settings.saved'), 'success');
          onClose();
        },
        onError: (error) => {
          if (isApiError(error, 422) && Array.isArray(error.params.fields)) {
            const fields = error.params.fields as string[];
            setErrors({
              ...(fields.includes('value') ? { value: error.message } : {}),
              ...(fields.includes('reason') ? { reason: error.message } : {}),
              ...(fields.includes('otp') ? { otp: error.message } : {}),
            });
          }
        },
      },
    );
  };

  const inline = Boolean(errors.value || errors.reason || errors.otp);
  const historyColumns: Column<SettingVersionOut>[] = [
    { key: 'version', header: t('settings.col.version'), cell: (r) => r.version },
    { key: 'value', header: t('settings.col.value'), align: 'left', wrap: true, cell: (r) => <span className="mono">{displaySetting(setting, r.value)}</span> },
    { key: 'updated', header: t('settings.col.updated'), cell: (r) => formatDateTime(r.updated_at) },
  ];
  return (
    <Modal
      open
      onClose={onClose}
      title={t('settings.editTitle', { title: setting.title })}
      note={`${setting.key} · ${t('settings.defaultValue', { value: displaySetting(setting, setting.default) })}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form={formId} loading={update.isPending}>{t('common.save')}</Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit}>
        <div className="span-2"><FormError error={update.error && !inline ? update.error : null} /></div>
        {isApiError(update.error, 403, 'step_up_unavailable') ? <div className="span-2"><EnrollLink /></div> : null}
        <div className="span-2">
          <FieldEditor setting={{ ...setting, title: t('settings.value') }} value={raw} onChange={setRaw} error={errors.value} />
          <p className="field__hint">{setting.apply === 'next_run' ? t('settings.applyNextRun') : t('settings.applyLive')}</p>
        </div>
        {setting.guarded ? (
          <div className="span-2">
            <TextInput label={t('settings.reason')} hint={t('settings.reasonHint')} maxLength={500} value={reason} error={errors.reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        ) : null}
        {setting.step_up ? (
          <div className="span-2">
            <OtpInput label={t('settings.otp')} hint={t('settings.otpHint')} value={otp} onChange={setOtp} error={errors.otp} />
          </div>
        ) : null}
      </form>
      <section aria-label={t('settings.history')}>
        {history.isError ? (
          <ErrorBanner error={history.error} onRetry={() => void history.refetch()} />
        ) : history.data && history.data.length ? (
          <Table caption={t('settings.history')} columns={historyColumns} rows={history.data} rowKey={(r) => r.version} mobile="scroll" />
        ) : null}
      </section>
    </Modal>
  );
}
