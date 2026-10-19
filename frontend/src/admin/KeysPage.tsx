import { useState } from 'react';
import type { KeyOut } from '../api/types';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Icon } from '../ui/icons';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useKeys, useRotateKey } from './api';
import { keyStatus, purposeLabel } from './labels';

/** Faqat holat va rotatsiya; eski versiyalarni o'chirish va KEK almashtirish — CLI (1-reja chetlanishi). */
export default function KeysPage() {
  const toast = useToast();
  const keys = useKeys();
  const rotate = useRotateKey();
  const [purpose, setPurpose] = useState<string | null>(null);

  const close = () => {
    setPurpose(null);
    rotate.reset();
  };

  const confirm = () => {
    if (!purpose) return;
    rotate.mutate(purpose, {
      onSuccess: (result) => {
        toast.show(
          t('keys.rotated', { purpose: purposeLabel(result.purpose), version: result.version, count: result.reencrypted }),
          'success',
        );
        close();
      },
    });
  };

  const columns: Column<KeyOut>[] = [
    {
      key: 'purpose',
      header: t('keys.col.purpose'),
      align: 'left',
      sortValue: (k) => `${k.purpose}:${String(999 - k.version).padStart(3, '0')}`,
      cell: (k) => (
        <span className="cell-main">
          <b>{purposeLabel(k.purpose)}</b>
          <small className="mono">{k.purpose}</small>
        </span>
      ),
    },
    { key: 'version', header: t('keys.col.version'), cell: (k) => k.version },
    {
      key: 'status',
      header: t('keys.col.status'),
      align: 'left',
      cell: (k) => {
        const status = keyStatus(k.status);
        return <Badge tone={status.tone}>{status.label}</Badge>;
      },
    },
    { key: 'created', header: t('keys.col.created'), cell: (k) => formatDateTime(k.created_at) },
    { key: 'retired', header: t('keys.col.retired'), cell: (k) => (k.retired_at ? formatDateTime(k.retired_at) : t('common.dash')) },
    {
      key: 'action',
      header: t('keys.col.action'),
      cell: (k) =>
        k.status === 'active' ? (
          <Button variant="secondary" icon="refresh" onClick={() => setPurpose(k.purpose)}>
            {t('keys.rotate')}
          </Button>
        ) : null,
    },
  ];

  if (keys.isError) return <ErrorBanner error={keys.error} lastSuccessAt={keys.dataUpdatedAt} onRetry={() => void keys.refetch()} />;
  if (keys.isPending) return <PageSkeleton />;

  return (
    <Card>
      <p className="note">
        <Icon name="info" /> {t('keys.note')}
      </p>
      <Table
        caption={t('admin.page.keys')}
        columns={columns}
        rows={keys.data}
        rowKey={(k) => `${k.purpose}:${k.version}`}
        initialSort={{ key: 'purpose', dir: 'asc' }}
        free
      />
      <ConfirmDialog
        open={purpose !== null}
        title={t('keys.confirmTitle', { purpose: purposeLabel(purpose ?? '') })}
        message={t('keys.confirmText')}
        confirmLabel={t('keys.rotate')}
        danger
        busy={rotate.isPending}
        error={rotate.error}
        onCancel={close}
        onConfirm={confirm}
      />
    </Card>
  );
}
