import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { ApiError } from '../api/client';
import { t } from '../i18n';
import { cx } from './cx';
import { Icon } from './icons';
import './controls.css';

export interface FieldIds {
  id: string;
  describedBy: string | undefined;
  invalid: boolean;
}

export interface FieldProps {
  label: string;
  hint?: string | undefined;
  error?: string | null | undefined;
  required?: boolean | undefined;
  className?: string | undefined;
  hideLabel?: boolean | undefined;
  children(ids: FieldIds): ReactNode;
}

export function Field({ label, hint, error, required, className, hideLabel, children }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
  return (
    <div className={cx('field', className)}>
      <div className={cx('field__top', hideLabel && 'visually-hidden')}>
        <label className="field__label" htmlFor={id}>
          {label}
        </label>
        {required ? (
          <span className="field__req" aria-hidden="true">
            *
          </span>
        ) : null}
      </div>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="field__error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface TextInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  hint?: string;
  error?: string | null;
  hideLabel?: boolean;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput(
  { label, hint, error, hideLabel, className, required, ...rest },
  ref,
) {
  return (
    <Field label={label} hint={hint} error={error} required={required} className={className} hideLabel={hideLabel}>
      {({ id, describedBy, invalid }) => (
        <input
          ref={ref}
          id={id}
          className="input"
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          {...rest}
        />
      )}
    </Field>
  );
});

export const PasswordInput = forwardRef<HTMLInputElement, Omit<TextInputProps, 'type'>>(function PasswordInput(
  { label, hint, error, hideLabel, className, required, ...rest },
  ref,
) {
  const [visible, setVisible] = useState(false);
  return (
    <Field label={label} hint={hint} error={error} required={required} className={className} hideLabel={hideLabel}>
      {({ id, describedBy, invalid }) => (
        <div className="input-wrap">
          <input
            ref={ref}
            id={id}
            type={visible ? 'text' : 'password'}
            className="input"
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            required={required}
            spellCheck={false}
            {...rest}
          />
          <button
            type="button"
            className="iconbtn iconbtn--ghost"
            aria-label={t('field.showPassword')}
            aria-pressed={visible}
            onClick={() => setVisible((v) => !v)}
          >
            <Icon name={visible ? 'eyeOff' : 'eye'} />
          </button>
        </div>
      )}
    </Field>
  );
});

export interface CheckboxProps {
  label: ReactNode;
  checked: boolean;
  onChange(checked: boolean): void;
  hint?: string;
  disabled?: boolean;
  name?: string;
  className?: string;
}

export function Checkbox({ label, checked, onChange, hint, disabled, name, className }: CheckboxProps) {
  const id = useId();
  return (
    <div className={cx('check-field', className)}>
      <label className="check" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          name={name}
          checked={checked}
          disabled={disabled}
          aria-describedby={hint ? `${id}-hint` : undefined}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{label}</span>
      </label>
      {hint ? (
        <p id={`${id}-hint`} className="field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FormError({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : t('error.generic');
  return (
    <p className="form-error" role="alert">
      <Icon name="alert" />
      <span>{message}</span>
    </p>
  );
}
