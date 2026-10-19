import type { ReactNode } from 'react';
import { t } from '../i18n';
import { Button } from './Button';
import { FormError } from './Field';
import { Modal } from './Modal';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel: string;
  onConfirm(): void;
  onCancel(): void;
  danger?: boolean;
  busy?: boolean;
  error?: unknown;
}

export function ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onCancel, danger, busy, error }: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} loading={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="confirm">
        <div className="confirm__text">{message}</div>
        <FormError error={error} />
      </div>
    </Modal>
  );
}
