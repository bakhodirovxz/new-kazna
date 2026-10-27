import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { IntegrationCheckOut, IntegrationOut, SecretStatusOut, SettingOut } from '../api/types';
import { EnrollLink } from '../auth/EnrollLink';
import { t, type MessageKey } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Checkbox, FormError, PasswordInput, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { OtpInput } from '../ui/OtpInput';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useIntegrationCheck, useIntegrations, useRequestCheck, useUpdateIntegration } from './api';
import { displaySetting, formatSetting, parseSetting } from './settingValue';
import { FieldEditor, SourceBadge } from './SettingsList';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const CODES = ['ok', 'auth_failed', 'tls_failed', 'timeout', 'connect_failed', 'protocol_error', 'http_error', 'not_configured', 'insecure_refused', 'not_supported', 'error'];

function checkText(check: IntegrationCheckOut): string {
  if (check.status === 'pending' || check.status === 'running') return t('integrations.checking');
  const code = check.code ?? 'error';
  return CODES.includes(code) ? t(`integrations.code.${code}` as MessageKey) : code;
}

function secretText(s: SecretStatusOut): string {
  if (s.state === 'panel') return t('integrations.secret.panel', { time: s.updated_at ? formatDateTime(s.updated_at) : '' });
  return s.state === 'env' ? t('integrations.secret.env') : t('integrations.secret.none');
}

export default function IntegrationsPage() {
  const list = useIntegrations();
  const [editing, setEditing] = useState<IntegrationOut | null>(null);
  if (list.isError) return <ErrorBanner error={list.error} lastSuccessAt={list.dataUpdatedAt} onRetry={() => void list.refetch()} />;
  if (list.isPending) return <PageSkeleton />;
  return (
    <>
      {list.data.map((integration) => (
        <IntegrationCard key={integration.name} integration={integration} onEdit={() => setEditing(integration)} />
      ))}
      {editing ? <IntegrationDialog integration={editing} onClose={() => setEditing(null)} /> : null}
    </>
  );
}

function IntegrationCard({ integration, onEdit }: { integration: IntegrationOut; onEdit(): void }) {
  const request = useRequestCheck();
  const [checkId, setCheckId] = useState<number | null>(null);
  const check = useIntegrationCheck(checkId);
  const status = check.data ?? integration.last_check;
  const fieldColumns: Column<SettingOut>[] = [
    { key: 'name', header: t('settings.col.name'), align: 'left', cell: (s) => s.title },
    { key: 'value', header: t('settings.col.value'), align: 'left', wrap: true, cell: (s) => <span className="mono">{displaySetting(s, s.value)}</span> },
    { key: 'source', header: t('settings.col.source'), align: 'left', cell: (s) => <SourceBadge source={s.source} /> },
  ];
  const secretColumns: Column<SecretStatusOut>[] = [
    { key: 'name', header: t('settings.col.name'), align: 'left', cell: (s) => s.title },
    { key: 'state', header: t('integrations.col.state'), align: 'left', cell: (s) => <Badge tone={s.state === 'none' ? 'neutral' : 'ok'}>{secretText(s)}</Badge> },
  ];
  return (
    <Card
      title={integration.title}
      actions={
        <>
          <Button variant="secondary" loading={request.isPending} onClick={() => request.mutate(integration.name, { onSuccess: (c) => setCheckId(c.id) })}>
            {t('integrations.check')}
          </Button>
          <Button onClick={onEdit}>{t('integrations.edit')}</Button>
        </>
      }
    >
      <Table caption={t('integrations.fields')} columns={fieldColumns} rows={integration.fields} rowKey={(s) => s.key} free />
      <Table caption={t('integrations.secrets')} columns={secretColumns} rows={integration.secrets} rowKey={(s) => s.name} free />
      <FormError error={request.error} />
      <p role="status">
        {status ? (
          <>
            <Badge tone={status.status === 'ok' ? 'ok' : status.status === 'failed' ? 'neg' : 'blue'}>{checkText(status)}</Badge>
            {status.finished_at ? ` ${formatDateTime(status.finished_at)}` : null}
          </>
        ) : null}
      </p>
    </Card>
  );
}

function IntegrationDialog({ integration, onClose }: { integration: IntegrationOut; onClose(): void }) {
  const formId = useId();
  const toast = useToast();
  const update = useUpdateIntegration();
  const initial = Object.fromEntries(integration.fields.map((f) => [f.key, formatSetting(f, f.value)]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [clear, setClear] = useState<Record<string, boolean>>({});
  const [reason, setReason] = useState('');
  const [otp, setOtp] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const formRef = useFocusFirstInvalid(errors);
  const bannerRef = useRef<HTMLDivElement>(null);
  const textFields = integration.fields.filter((f) => f.kind !== 'bool').map((f) => f.key);
  const bannerShown = Boolean(update.error) && !Object.keys(errors).length;
  useEffect(() => {
    if (bannerShown) bannerRef.current?.focus();
  }, [bannerShown, update.error]);
  const changed = integration.fields.filter((f) => values[f.key] !== initial[f.key]);
  const endpointChanged = changed.some((f) => integration.endpoint.includes(f.key));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    const body: { values: Record<string, unknown>; secrets: Record<string, string | null> } = { values: {}, secrets: {} };
    for (const f of changed) {
      const parsed = parseSetting(f, values[f.key] ?? '');
      if (parsed.ok) body.values[f.key] = parsed.value;
      else next[f.key] = parsed.error;
    }
    for (const s of integration.secrets) {
      if (clear[s.name]) body.secrets[s.name] = null;
      else if (secrets[s.name]) body.secrets[s.name] = secrets[s.name] ?? '';
    }
    if (reason.trim().length < 5) next.reason = t('settings.reasonRequired');
    if (!/^\d{6}$/.test(otp)) next.otp = t('settings.otpRequired');
    setErrors(next);
    if (Object.keys(next).length) return;
    update.mutate(
      { name: integration.name, body: { ...body, reason: reason.trim(), otp } },
      {
        onSuccess: () => {
          toast.show(t('integrations.saved'), 'success');
          onClose();
        },
        onError: (error) => {
          if (isApiError(error, 422) && Array.isArray(error.params.fields)) {
            // Faqat xatosi ko'rsatiladigan maydonlar (bool maydonda xato joyi yo'q) — qolgani umumiy xabarda.
            const shown = new Set([...textFields, ...integration.secrets.map((s) => s.name), 'reason', 'otp']);
            const fields = (error.params.fields as string[]).filter((f) => shown.has(f));
            setErrors(Object.fromEntries(fields.map((f) => [f, error.message])));
          }
        },
      },
    );
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={t('integrations.editTitle', { title: integration.title })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form={formId} loading={update.isPending}>{t('common.save')}</Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit} autoComplete="off">
        <div className="span-2" ref={bannerRef} tabIndex={-1}><FormError error={bannerShown ? update.error : null} />{bannerShown && isApiError(update.error, 403, 'step_up_unavailable') ? <EnrollLink /> : null}</div>
        {integration.fields.map((f) => (
          <div key={f.key} className="span-2">
            <FieldEditor setting={f} value={values[f.key] ?? ''} onChange={(v) => setValues((prev) => ({ ...prev, [f.key]: v }))} error={errors[f.key]} />
          </div>
        ))}
        {endpointChanged ? <p className="span-2 field__error" role="alert">{t('integrations.endpointWarning')}</p> : null}
        {integration.secrets.map((s) => (
          <div key={s.name} className="span-2">
            <PasswordInput
              label={s.title}
              hint={t('integrations.secretKeep')}
              autoComplete="new-password"
              value={secrets[s.name] ?? ''}
              disabled={clear[s.name] === true}
              error={errors[s.name]}
              onChange={(e) => setSecrets((prev) => ({ ...prev, [s.name]: e.target.value }))}
            />
            {s.state === 'panel' ? <Checkbox label={t('integrations.secretClear')} checked={clear[s.name] === true} onChange={(v) => setClear((prev) => ({ ...prev, [s.name]: v }))} /> : null}
          </div>
        ))}
        <div className="span-2">
          <TextInput label={t('settings.reason')} hint={t('settings.reasonHint')} maxLength={500} value={reason} error={errors.reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <div className="span-2">
          <OtpInput label={t('settings.otp')} hint={t('settings.otpHint')} value={otp} onChange={setOtp} error={errors.otp} />
        </div>
      </form>
    </Modal>
  );
}
