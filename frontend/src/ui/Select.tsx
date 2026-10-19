import { cx } from './cx';
import { Field } from './Field';
import { Icon, type IconName } from './icons';
import './controls.css';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  label: string;
  value: string;
  options: readonly SelectOption[];
  onChange(value: string): void;
  hint?: string;
  error?: string | null;
  disabled?: boolean;
  icon?: IconName;
  hideLabel?: boolean;
  className?: string;
  required?: boolean;
  name?: string;
}

export function Select({
  label,
  value,
  options,
  onChange,
  hint,
  error,
  disabled,
  icon,
  hideLabel,
  className,
  required,
  name,
}: SelectProps) {
  return (
    <Field label={label} hint={hint} error={error} required={required} className={className} hideLabel={hideLabel}>
      {({ id, describedBy, invalid }) => (
        <div className={cx('select-wrap', icon && 'select-wrap--icon')}>
          {icon ? <Icon name={icon} /> : null}
          <select
            id={id}
            className="select"
            value={value}
            name={name}
            disabled={disabled}
            required={required}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            onChange={(e) => onChange(e.target.value)}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}
    </Field>
  );
}
