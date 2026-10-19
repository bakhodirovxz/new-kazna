import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { AlertRuleOut, AlertRuleUpdate } from '../api/types';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { sectionTitle } from '../shell/sectionMeta';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Checkbox, FormError, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { Select } from '../ui/Select';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useAlertRuleHistory, useAlertRules, useUpdateAlertRule } from './api';
import { formatDecimal, parseDecimal } from './numbers';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const VALUE_LIMIT = 1_000_000; // backend: AlertRuleUpdate.value ±1e6
type Op = '<' | '<=' | '>' | '>=';
type Level = 'critical' | 'warning';
const OPS: ReadonlyArray<{ value: Op; label: string }> = [
  { value: '<', label: t('alerts.op.lt') },
  { value: '<=', label: t('alerts.op.le') },
  { value: '>', label: t('alerts.op.gt') },
  { value: '>=', label: t('alerts.op.ge') },
];
const OP_SIGN: Record<Op, string> = { '<': '<', '<=': '≤', '>': '>', '>=': '≥' };

interface Threshold {
  metric: string;
  op: Op;
  value: number | null;
}

function readThreshold(rule: AlertRuleOut): Threshold {
  const raw = rule.threshold as Record<string, unknown>;
  const op = OPS.some((o) => o.value === raw.op) ? (raw.op as Op) : '<';
  return {
    metric: typeof raw.metric === 'string' ? raw.metric : rule.code,
    op,
    value: typeof raw.value === 'number' ? raw.value : null,
  };
}

function condition(rule: AlertRuleOut): string {
  const th = readThreshold(rule);
  return `${th.metric} ${OP_SIGN[th.op]} ${th.value === null ? '—' : formatDecimal(th.value)}`;
}

function levelBadge(level: string) {
  return level === 'critical' ? <Badge tone="neg">{t('alerts.level.critical')}</Badge> : <Badge tone="warn">{t('alerts.level.warning')}</Badge>;
}

function enabledBadge(enabled: boolean) {
  return <Badge tone={enabled ? 'ok' : 'neutral'}>{enabled ? t('common.yes') : t('common.no')}</Badge>;
}

export default function AlertRulesPage() {
  const rules = useAlertRules();
  const [editing, setEditing] = useState<AlertRuleOut | null>(null);

  const columns: Column<AlertRuleOut>[] = [
    {
      key: 'rule',
      header: t('alerts.col.rule'),
      align: 'left',
      wrap: true,
      sortValue: (r) => r.title,
      cell: (r) => (
        <span className="cell-main">
          <b>{r.title}</b>
          <small className="mono">{r.code}</small>
        </span>
      ),
    },
    { key: 'where', header: t('alerts.col.where'), align: 'left', sortValue: (r) => r.section, cell: (r) => `${sectionTitle(r.section)} / ${r.page}` },
    { key: 'condition', header: t('alerts.col.condition'), align: 'left', cell: (r) => <span className="mono">{condition(r)}</span> },
    { key: 'level', header: t('alerts.col.level'), align: 'left', sortValue: (r) => r.level, cell: (r) => levelBadge(r.level) },
    { key: 'enabled', header: t('alerts.col.enabled'), align: 'left', cell: (r) => enabledBadge(r.enabled) },
    { key: 'version', header: t('alerts.col.version'), sortValue: (r) => r.version, cell: (r) => r.version },
    { key: 'updated', header: t('alerts.col.updated'), sortValue: (r) => r.updated_at, cell: (r) => formatDateTime(r.updated_at) },
  ];

  if (rules.isError) return <ErrorBanner error={rules.error} lastSuccessAt={rules.dataUpdatedAt} onRetry={() => void rules.refetch()} />;
  if (rules.isPending) return <PageSkeleton />;

  return (
    <Card>
      <Table
        caption={t('admin.page.alerts')}
        columns={columns}
        rows={rules.data}
        rowKey={(r) => r.code}
        onRowClick={(r) => setEditing(r)}
        initialSort={{ key: 'where', dir: 'asc' }}
        free
      />
      {editing ? <AlertRuleDialog rule={editing} onClose={() => setEditing(null)} /> : null}
    </Card>
  );
}

function AlertRuleDialog({ rule, onClose }: { rule: AlertRuleOut; onClose(): void }) {
  const formId = useId();
  const toast = useToast();
  const update = useUpdateAlertRule();
  const history = useAlertRuleHistory(rule.code);
  const initial = readThreshold(rule);
  const [value, setValue] = useState(initial.value === null ? '' : formatDecimal(initial.value));
  const [op, setOp] = useState<Op>(initial.op);
  const [level, setLevel] = useState<Level>(rule.level === 'critical' ? 'critical' : 'warning');
  const [enabled, setEnabled] = useState(rule.enabled);
  const [errors, setErrors] = useState<{ value?: string }>({}); // har setErrors yangi obyekt: fokus faqat xato qo'yilganda
  const formRef = useFocusFirstInvalid(errors);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parseDecimal(value);
    if (parsed === null || Math.abs(parsed) > VALUE_LIMIT) {
      setErrors({ value: parsed === null ? t('alerts.valueInvalid') : t('alerts.valueRange') });
      return;
    }
    setErrors({});
    const body: AlertRuleUpdate = { value: parsed, op, level, enabled };
    update.mutate(
      { code: rule.code, body },
      {
        onSuccess: () => {
          toast.show(t('alerts.saved'), 'success');
          onClose();
        },
        onError: (error) => {
          if (isApiError(error, 422) && Array.isArray(error.params.fields) && error.params.fields.includes('value')) {
            setErrors({ value: error.message });
          }
        },
      },
    );
  };

  const historyColumns: Column<AlertRuleOut>[] = [
    { key: 'version', header: t('alerts.col.version'), cell: (r) => r.version },
    { key: 'condition', header: t('alerts.col.condition'), align: 'left', cell: (r) => <span className="mono">{condition(r)}</span> },
    { key: 'level', header: t('alerts.col.level'), align: 'left', cell: (r) => levelBadge(r.level) },
    { key: 'enabled', header: t('alerts.col.enabled'), align: 'left', cell: (r) => enabledBadge(r.enabled) },
    { key: 'updated', header: t('alerts.col.updated'), cell: (r) => formatDateTime(r.updated_at) },
  ];

  return (
    <Modal
      open
      onClose={onClose}
      title={t('alerts.editTitle', { title: rule.title })}
      note={`${sectionTitle(rule.section)} / ${rule.page} · ${initial.metric}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form={formId} loading={update.isPending}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit}>
        <div className="span-2">
          <FormError error={update.error && !errors.value ? update.error : null} />
        </div>
        <Select label={t('alerts.op')} value={op} options={OPS} onChange={(v) => setOp(OPS.find((o) => o.value === v)?.value ?? '<')} />
        <TextInput
          label={t('alerts.value')}
          hint={t('alerts.valueHint')}
          inputMode="decimal"
          value={value}
          error={errors.value}
          onChange={(e) => setValue(e.target.value)}
        />
        <Select
          label={t('alerts.level')}
          value={level}
          options={[
            { value: 'critical', label: t('alerts.level.critical') },
            { value: 'warning', label: t('alerts.level.warning') },
          ]}
          onChange={(v) => setLevel(v === 'critical' ? 'critical' : 'warning')}
        />
        <div className="span-2">
          <Checkbox label={t('alerts.enabled')} checked={enabled} onChange={setEnabled} />
        </div>
      </form>
      <section aria-label={t('alerts.history')}>
        {history.data ? (
          <Table
            caption={t('alerts.history')}
            columns={historyColumns}
            rows={history.data}
            rowKey={(r) => r.version}
            initialSort={{ key: 'version', dir: 'desc' }}
            mobile="scroll"
          />
        ) : null}
      </section>
    </Modal>
  );
}
