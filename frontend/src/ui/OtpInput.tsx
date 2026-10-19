import { useEffect, useRef, type ChangeEvent, type KeyboardEvent } from 'react';
import { t } from '../i18n';
import { cx } from './cx';
import { Field } from './Field';

export interface OtpInputProps {
  label: string;
  value: string;
  onChange(value: string): void;
  /** 'totp' rejimida 6-raqam kiritilganda bir marta chaqiriladi (avto-yuborish). */
  onComplete?(value: string): void;
  mode?: 'totp' | 'backup';
  error?: string | null;
  hint?: string;
  disabled?: boolean;
  focusOnMount?: boolean;
  testId?: string;
}

function sanitize(raw: string, mode: 'totp' | 'backup'): string {
  if (mode === 'totp') return raw.replace(/\D/g, '').slice(0, 6);
  return raw.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 14);
}

/** Bitta maydon (6 katak emas): paste, parol menejeri va ekran o'quvchi uchun qulay (ledger). */
export function OtpInput({
  label,
  value,
  onChange,
  onComplete,
  mode = 'totp',
  error,
  hint,
  disabled,
  focusOnMount = false,
  testId,
}: OtpInputProps) {
  const ref = useRef<HTMLInputElement>(null);
  const completed = useRef<string | null>(null);

  useEffect(() => {
    if (focusOnMount) ref.current?.focus();
  }, [focusOnMount]);

  useEffect(() => {
    if (value.length < 6) completed.current = null;
  }, [value]);

  // Xato kelganda (masalan tarmoq) o'sha kodni qayta yuborishga ruxsat.
  useEffect(() => {
    completed.current = null;
  }, [error]);

  // Avto-yuborilgan kodda Enter formani ikkinchi marta yubormasin (TOTP bir marta ishlatiladi).
  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && mode === 'totp' && completed.current === value) event.preventDefault();
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const next = sanitize(event.target.value, mode);
    onChange(next);
    if (mode === 'totp' && onComplete && next.length === 6 && completed.current !== next) {
      completed.current = next;
      onComplete(next);
    }
  };

  return (
    <Field label={label} hint={hint ?? (mode === 'backup' ? t('otp.backupHint') : undefined)} error={error}>
      {({ id, describedBy, invalid }) => (
        <input
          ref={ref}
          id={id}
          className={cx('input', 'otp', mode === 'backup' && 'otp--backup')}
          inputMode={mode === 'totp' ? 'numeric' : 'text'}
          autoComplete="one-time-code"
          autoCapitalize="characters"
          spellCheck={false}
          value={value}
          disabled={disabled}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          data-testid={testId}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
        />
      )}
    </Field>
  );
}
