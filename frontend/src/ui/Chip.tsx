import { t } from '../i18n';
import { cx } from './cx';
import './display.css';

export interface ChipProps {
  label: string;
  value: string;
  onRemove?(): void;
}

export function Chip({ label, value, onRemove }: ChipProps) {
  return (
    <span className={cx('chip', !onRemove && 'chip--static')}>
      <span>
        {label}: <b>{value}</b>
      </span>
      {onRemove ? (
        <button type="button" aria-label={t('chip.remove', { name: label })} onClick={onRemove}>
          ×
        </button>
      ) : null}
    </span>
  );
}
