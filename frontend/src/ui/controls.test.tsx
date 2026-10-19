import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import { expectNoAxeViolations } from '../test/axe';
import { Button, IconButton } from './Button';
import { Combobox, type ComboOption } from './Combobox';
import { Checkbox, FormError, PasswordInput, TextInput } from './Field';
import { OtpInput } from './OtpInput';
import { Select } from './Select';

describe('Button', () => {
  it('is disabled and busy while loading', async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Сохранить</Button>);
    const button = screen.getByRole('button', { name: 'Сохранить' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(button).toHaveAttribute('type', 'button');
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('names icon-only buttons with their label', () => {
    render(<IconButton icon="close" label="Закрыть" />);
    expect(screen.getByRole('button', { name: 'Закрыть' })).toBeInTheDocument();
  });
});

describe('TextInput', () => {
  it('links label, hint and error to the input', () => {
    render(<TextInput label="Логин" hint="латиница" error="Обязательное поле" />);
    const input = screen.getByLabelText('Логин');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('латиница Обязательное поле');
  });
});

describe('PasswordInput', () => {
  it('toggles visibility with a pressed button', async () => {
    render(<PasswordInput label="Пароль" />);
    const input = screen.getByLabelText('Пароль');
    expect(input).toHaveAttribute('type', 'password');
    const toggle = screen.getByRole('button', { name: 'Показать пароль' });
    await userEvent.click(toggle);
    expect(input).toHaveAttribute('type', 'text');
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('Checkbox', () => {
  it('reports the checked state', async () => {
    const onChange = vi.fn();
    render(<Checkbox label="Я сохранил коды" checked={false} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText('Я сохранил коды'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('FormError', () => {
  it('shows the server message as an alert', () => {
    render(<FormError error={new ApiError(409, 'last_admin', 'Нельзя оставить систему без администратора')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Нельзя оставить систему без администратора');
  });

  it('renders nothing without an error', () => {
    const { container } = render(<FormError error={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

function Otp({ onComplete, mode = 'totp' }: { onComplete(v: string): void; mode?: 'totp' | 'backup' }) {
  const [value, setValue] = useState('');
  return <OtpInput label="Код" value={value} onChange={setValue} onComplete={onComplete} mode={mode} />;
}

describe('OtpInput', () => {
  it('keeps digits only and completes once at six digits', async () => {
    const onComplete = vi.fn();
    render(<Otp onComplete={onComplete} />);
    const input = screen.getByLabelText('Код');
    expect(input).toHaveAttribute('inputmode', 'numeric');
    expect(input).toHaveAttribute('autocomplete', 'one-time-code');
    await userEvent.type(input, '12 3-45a67');
    expect(input).toHaveValue('123456');
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith('123456');
  });

  it('does not submit the form again on Enter after auto-completion', async () => {
    const onSubmit = vi.fn((e: { preventDefault(): void }) => e.preventDefault());
    const onComplete = vi.fn();
    function Form() {
      const [value, setValue] = useState('');
      return (
        <form aria-label="2FA" onSubmit={onSubmit}>
          <OtpInput label="Код" value={value} onChange={setValue} onComplete={onComplete} />
          <button type="submit">Войти</button>
        </form>
      );
    }
    render(<Form />);
    await userEvent.type(screen.getByLabelText('Код'), '123456{Enter}');
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('accepts pasted backup codes in upper case', async () => {
    const onComplete = vi.fn();
    render(<Otp onComplete={onComplete} mode="backup" />);
    const input = screen.getByLabelText('Код');
    await userEvent.click(input);
    await userEvent.paste('abcd-efgh-2345!');
    expect(input).toHaveValue('ABCD-EFGH-2345');
    expect(onComplete).not.toHaveBeenCalled();
  });
});

describe('Select', () => {
  it('reports the chosen value', async () => {
    const onChange = vi.fn();
    render(
      <Select
        label="Период"
        value="ytd"
        options={[
          { value: 'ytd', label: 'С начала года' },
          { value: 'q1', label: 'I квартал' },
        ]}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText('Период'), 'q1');
    expect(onChange).toHaveBeenCalledWith('q1');
  });
});

const POSITIONS: ComboOption[] = [
  { value: '1', label: 'Администратор' },
  { value: '2', label: 'Экономист филиала', hint: 'economist_filiala' },
  { value: '3', label: 'Специалист казначейства' },
];

function Combo({ onChange }: { onChange(v: string | null): void }) {
  const [value, setValue] = useState<string | null>('1');
  return (
    <Combobox
      label="Должность"
      options={POSITIONS}
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange(v);
      }}
    />
  );
}

describe('Combobox', () => {
  it('filters by typing and selects with the keyboard', async () => {
    const onChange = vi.fn();
    render(<Combo onChange={onChange} />);
    const input = screen.getByRole('combobox', { name: 'Должность' });
    expect(input).toHaveValue('Администратор');
    await userEvent.clear(input);
    await userEvent.type(input, 'кон');
    expect(screen.getAllByRole('option')).toHaveLength(1);
    await userEvent.keyboard('{ArrowDown}{Enter}');
    expect(onChange).toHaveBeenCalledWith('2');
    expect(input).toHaveValue('Экономист филиала');
    expect(input).toHaveAttribute('aria-expanded', 'false');
  });

  it('restores the selected label on Escape', async () => {
    render(<Combo onChange={vi.fn()} />);
    const input = screen.getByRole('combobox', { name: 'Должность' });
    await userEvent.clear(input);
    await userEvent.type(input, 'xyz');
    expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(input).toHaveValue('Администратор');
  });
});

it('has no axe violations in a typical form', async () => {
  const { container } = render(
    <form aria-label="Тест">
      <TextInput label="Логин" required />
      <PasswordInput label="Пароль" error="Неверный пароль" />
      <Select label="Период" value="a" options={[{ value: 'a', label: 'A' }]} onChange={vi.fn()} />
      <Combobox label="Должность" options={POSITIONS} value={null} onChange={vi.fn()} />
      <Checkbox label="Запомнить" checked={false} onChange={vi.fn()} />
      <OtpInput label="Код" value="" onChange={vi.fn()} />
      <Button type="submit">Войти</Button>
    </form>,
  );
  await expectNoAxeViolations(container);
});
