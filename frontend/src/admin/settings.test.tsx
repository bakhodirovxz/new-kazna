import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AlertRuleOut, FinAssumptionOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import AlertRulesPage from './AlertRulesPage';
import FinAssumptionsPage from './FinAssumptionsPage';

const RULE: AlertRuleOut = {
  code: 'cash_below_monthly_outflow',
  version: 1,
  title: 'Остаток ниже месячного расходования',
  section: 'kazna',
  page: 'svod',
  threshold: { metric: 'balance_to_avg_monthly_outflow', op: '<', value: 1 },
  level: 'critical',
  enabled: true,
  updated_by: null,
  updated_at: '2026-09-20T05:00:00Z',
};

describe('AlertRulesPage', () => {
  it('lists rules and saves an edited threshold with history', async () => {
    const server = mockApi({
      'GET /admin/alert-rules': json([RULE]),
      'GET /admin/alert-rules/cash_below_monthly_outflow/history': json([RULE]),
      'PATCH /admin/alert-rules/cash_below_monthly_outflow': json({ ...RULE, version: 2, enabled: false }),
    });
    const { user } = renderWithProviders(<AlertRulesPage />);
    const table = await screen.findByRole('table', { name: 'Пороги «Требует внимания»' });
    expect(table).toHaveTextContent('balance_to_avg_monthly_outflow < 1');
    expect(table).toHaveTextContent('Казначейство / svod');
    expect(table).toHaveTextContent('Критично');
    await user.click(within(table).getByText('Остаток ниже месячного расходования'));
    const dialog = screen.getByRole('dialog', { name: 'Порог: Остаток ниже месячного расходования' });
    expect(await within(dialog).findByRole('table', { name: 'История изменений' })).toBeInTheDocument();
    const value = within(dialog).getByLabelText('Пороговое значение');
    await user.clear(value);
    await user.type(value, 'abc');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText('Введите число')).toBeInTheDocument();
    await user.clear(value);
    await user.type(value, '0,8');
    await user.selectOptions(within(dialog).getByLabelText('Условие срабатывания'), '<=');
    await user.click(within(dialog).getByLabelText('Правило включено'));
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await screen.findByText('Порог сохранён. Изменение записано в журнал аудита.')).toBeInTheDocument();
    expect(server.calls.filter((c) => c.method === 'PATCH').map((c) => c.body)).toEqual([
      { value: 0.8, op: '<=', level: 'critical', enabled: false },
    ]);
  });
});

const FIN: FinAssumptionOut[] = [
  { scenario: 'base', year: 2026, key: 'tariff_growth', value: 0.08, version: 1, updated_by: null, updated_at: '2026-09-01T00:00:00Z' },
  { scenario: 'base', year: 2027, key: 'tariff_growth', value: 0.08, version: 1, updated_by: null, updated_at: '2026-09-01T00:00:00Z' },
  { scenario: 'base', year: 2026, key: 'kium', value: 0.45, version: 1, updated_by: null, updated_at: '2026-09-01T00:00:00Z' },
  { scenario: 'water', year: 2026, key: 'tariff_growth', value: 0.06, version: 1, updated_by: null, updated_at: '2026-09-01T00:00:00Z' },
];

describe('FinAssumptionsPage', () => {
  it('edits a scenario matrix and saves only changed values', async () => {
    const server = mockApi({ 'GET /admin/fin-assumptions': json(FIN), 'PUT /admin/fin-assumptions': json(FIN) });
    const { user } = renderWithProviders(<FinAssumptionsPage />);
    const cell = await screen.findByLabelText('Рост тарифа, 2027');
    expect(cell).toHaveValue('0,08');
    await user.clear(cell);
    await user.type(cell, '0,1');
    expect(screen.getByText('Изменено значений: 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    expect(await screen.findByText('Допущения сохранены. Изменение записано в журнал аудита.')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'PUT')?.body).toEqual({
      items: [{ scenario: 'base', year: 2027, key: 'tariff_growth', value: 0.1 }],
    });
  });

  it('switches scenarios and blocks out-of-range values', async () => {
    const server = mockApi({ 'GET /admin/fin-assumptions': json(FIN) });
    const { user } = renderWithProviders(<FinAssumptionsPage />);
    await user.click(await screen.findByRole('tab', { name: 'Маловодье' }));
    const cell = screen.getByLabelText('Рост тарифа, 2026');
    expect(cell).toHaveValue('0,06');
    await user.clear(cell);
    await user.type(cell, '99');
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Значение вне допустимого диапазона: Маловодье · Рост тарифа · 2026');
    expect(server.calls.some((c) => c.method === 'PUT')).toBe(false);
  });

  it('has no axe violations', async () => {
    mockApi({ 'GET /admin/fin-assumptions': json(FIN), 'GET /admin/alert-rules': json([RULE]) });
    const { container } = renderWithProviders(
      <>
        <FinAssumptionsPage />
        <AlertRulesPage />
      </>,
    );
    await screen.findByLabelText('Рост тарифа, 2027');
    await screen.findByRole('table', { name: 'Пороги «Требует внимания»' });
    await expectNoAxeViolations(container);
  });
});

describe('Task 15 review hardening', () => {
  const conflict = apiError(409, 'conflict_modified', 'Запись изменена другим пользователем, обновите страницу');

  it('shows the lost-race message and refetches the alert rules', async () => {
    const server = mockApi({
      'GET /admin/alert-rules': json([RULE]),
      'GET /admin/alert-rules/cash_below_monthly_outflow/history': json([RULE]),
      'PATCH /admin/alert-rules/cash_below_monthly_outflow': conflict,
    });
    const { user } = renderWithProviders(<AlertRulesPage />);
    await user.click(await screen.findByText('Остаток ниже месячного расходования'));
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Запись изменена другим пользователем, обновите страницу');
    await waitFor(() => expect(server.calls.filter((c) => c.method === 'GET' && c.path === '/admin/alert-rules').length).toBeGreaterThan(1));
  });

  it('focuses the invalid alert value and rejects out-of-range numbers', async () => {
    mockApi({ 'GET /admin/alert-rules': json([RULE]), 'GET /admin/alert-rules/cash_below_monthly_outflow/history': json([RULE]) });
    const { user } = renderWithProviders(<AlertRulesPage />);
    await user.click(await screen.findByText('Остаток ниже месячного расходования'));
    const dialog = screen.getByRole('dialog');
    const value = within(dialog).getByLabelText('Пороговое значение');
    await user.clear(value);
    await user.type(value, '2000000');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText('Значение должно быть числом от −1 000 000 до 1 000 000')).toBeInTheDocument();
    expect(value).toHaveFocus();
  });

  it('rounds to the DB precision: a 7th-decimal edit is not a change', async () => {
    mockApi({ 'GET /admin/fin-assumptions': json(FIN) });
    const { user } = renderWithProviders(<FinAssumptionsPage />);
    const cell = await screen.findByLabelText('Рост тарифа, 2027');
    await user.clear(cell);
    await user.type(cell, '0,08000001');
    expect(screen.getByText('Изменено значений: 0')).toBeInTheDocument();
  });

  it('focuses an invalid cell and clears the message once fixed; lost race resets the draft to the refetched values', async () => {
    const server = mockApi({ 'GET /admin/fin-assumptions': json(FIN), 'PUT /admin/fin-assumptions': conflict });
    const { user } = renderWithProviders(<FinAssumptionsPage />);
    const cell = await screen.findByLabelText('Рост тарифа, 2027');
    await user.clear(cell);
    await user.type(cell, '99');
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    expect(cell).toHaveFocus();
    expect(cell).toHaveAttribute('aria-invalid', 'true');
    await user.clear(cell);
    await user.type(cell, '0,2');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Запись изменена другим пользователем, обновите страницу');
    await waitFor(() => expect(screen.getByLabelText('Рост тарифа, 2027')).toHaveValue('0,08'));
    expect(screen.getByText('Изменено значений: 0')).toBeInTheDocument();
    await waitFor(() => expect(server.calls.filter((c) => c.method === 'GET').length).toBeGreaterThan(1));
  });
});

describe('Task 15 fix round 1', () => {
  it('prints negative thresholds with U+2212', async () => {
    mockApi({ 'GET /admin/alert-rules': json([{ ...RULE, threshold: { metric: 'm', op: '<', value: -0.25 } }]) });
    renderWithProviders(<AlertRulesPage />);
    expect(await screen.findByRole('table', { name: 'Пороги «Требует внимания»' })).toHaveTextContent('m < −0,25');
  });

  it('uses non-breaking spaces in the range message', async () => {
    mockApi({ 'GET /admin/alert-rules': json([RULE]), 'GET /admin/alert-rules/cash_below_monthly_outflow/history': json([RULE]) });
    const { user } = renderWithProviders(<AlertRulesPage />);
    await user.click(await screen.findByText('Остаток ниже месячного расходования'));
    const dialog = screen.getByRole('dialog');
    const value = within(dialog).getByLabelText('Пороговое значение');
    await user.clear(value);
    await user.type(value, '2000000');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText(/от −1\u00A0000\u00A0000 до 1\u00A0000\u00A0000/, { normalizer: (text) => text })).toBeInTheDocument(); // NBSP saqlansin
  });

  it('shows a retry banner when the history fails to load', async () => {
    mockApi({
      'GET /admin/alert-rules': json([RULE]),
      'GET /admin/alert-rules/cash_below_monthly_outflow/history': apiError(500, 'internal_error', 'Внутренняя ошибка сервера'),
    });
    const { user } = renderWithProviders(<AlertRulesPage />);
    await user.click(await screen.findByText('Остаток ниже месячного расходования'));
    const dialog = screen.getByRole('dialog');
    expect(await within(dialog).findByText('Внутренняя ошибка сервера')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });

  it('links an invalid fin cell to its error message', async () => {
    mockApi({ 'GET /admin/fin-assumptions': json(FIN) });
    const { user } = renderWithProviders(<FinAssumptionsPage />);
    const cell = await screen.findByLabelText('Рост тарифа, 2027');
    await user.clear(cell);
    await user.type(cell, '99');
    await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
    const alert = await screen.findByRole('alert');
    expect(alert.id).toBeTruthy();
    expect(cell.getAttribute('aria-describedby')).toBe(alert.id);
  });
});
