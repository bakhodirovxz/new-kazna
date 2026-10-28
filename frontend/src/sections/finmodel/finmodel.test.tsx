import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { FIN_MODEL, FIN_MODEL_EMPTY, FIN_MODEL_STALE, FIN_MODEL_WATER } from '../../test/s5Fixtures';
import FinDohody from './dohody';
import FinDolg from './dolg';
import FinScenarii from './scenarii';
import FinSvod from './svod';

const filters = { br: null, per: 'ytd' };
const props = (page: string) => ({ section: 'finmodel', page, filters, onBranch: vi.fn() });

function mockModel() {
  return mockApi({
    'GET /auth/me': json(ME_ADMIN),
    'GET /finmodel/model': (req) => json(req.url.searchParams.get('scen') === 'water' ? FIN_MODEL_WATER : FIN_MODEL),
  });
}

describe('Финмодель', () => {
  it('Сводка: six KPIs, charts, model table and base inputs', async () => {
    mockModel();
    const { container } = renderWithProviders(<FinSvod {...props('svod')} />, { hash: '#finmodel/svod' });
    expect(await screen.findByText('Мощность к 2032 году')).toBeInTheDocument();
    expect(screen.getByText('ввод по программе +555 МВт')).toBeInTheDocument();
    expect(screen.getByText('в 2027 году, порог 1,20')).toBeInTheDocument();
    expect(screen.getByText('отрицательный остаток в 1 годах')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Выручка и EBITDA по годам' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Денежный поток по годам' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Модель по годам' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 7 + 1);
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    expect(screen.getByText('План АИП не загружен на 2029, 2030, 2031, 2032 — инвестиции этих лет приняты равными нулю.')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('switches the scenario through the URL and requests it', async () => {
    const { calls } = mockModel();
    const { user } = renderWithProviders(<FinSvod {...props('svod')} />, { hash: '#finmodel/svod' });
    const group = await screen.findByRole('group', { name: 'Сценарий модели' });
    expect(within(group).getByRole('button', { name: 'Базовый' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(within(group).getByRole('button', { name: 'Маловодье' }));
    await waitFor(() => expect(window.location.hash).toBe('#finmodel/svod?scen=water'));
    await waitFor(() => expect(calls.some((c) => c.url.searchParams.get('scen') === 'water')).toBe(true));
    expect(within(group).getByRole('button', { name: 'Маловодье' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByText('Выработка ниже нормы на 15% в 2027–2029 годах').length).toBeGreaterThan(0);
  });

  it('Доходы и расходы: revenue structure and cost per kWh', async () => {
    mockModel();
    renderWithProviders(<FinDohody {...props('dohody')} />, { hash: '#finmodel/dohody' });
    expect(await screen.findByRole('img', { name: 'Структура выручки по годам' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Себестоимость и тариф' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 7);
  });

  it('Инвестиции и долг: DSCR chart with the covenant and a highlighted breach', async () => {
    mockModel();
    renderWithProviders(<FinDolg {...props('dolg')} />, { hash: '#finmodel/dolg' });
    expect(await screen.findByRole('img', { name: 'Покрытие долга (DSCR)' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Инвестиции и долговая нагрузка по годам' });
    const row2027 = within(table).getAllByRole('row')[2] as HTMLElement;
    expect(within(row2027).getByText('1,10')).toHaveClass('neg');
  });

  it('Сценарии: comparison table and sensitivity sorted by impact', async () => {
    mockModel();
    renderWithProviders(<FinScenarii {...props('scenarii')} />, { hash: '#finmodel/scenarii?scen=water' });
    const table = await screen.findByRole('table', { name: 'Сравнение сценариев' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 4);
    expect(within(table).getByText('Маловодье').closest('tr')).toHaveClass('active');
    expect(within(table).getAllByText('требует привлечения финансирования')).toHaveLength(3);
    const items = within(screen.getByRole('list', { name: 'Чувствительность' })).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Маловодье');
  });

  it('shows stale assumptions and input warnings', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN), 'GET /finmodel/model': json(FIN_MODEL_STALE) });
    renderWithProviders(<FinSvod {...props('svod')} />, { hash: '#finmodel/svod?br=3' });
    expect(await screen.findByText(/Допущения изменены после расчёта/)).toBeInTheDocument();
    expect(screen.getByText('Финансовая модель строится по компании в целом — фильтр филиала на неё не влияет.')).toBeInTheDocument();
    expect(screen.getByText('Нет курса ЦБ для валют: XDR — эти кредиты не учтены в обслуживании долга.')).toBeInTheDocument();
    expect(screen.getByText('База расходов собрана за 7 мес. — история меньше года.')).toBeInTheDocument();
  });

  it('explains the company-level model when nothing is visible', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN), 'GET /finmodel/model': json(FIN_MODEL_EMPTY) });
    renderWithProviders(<FinSvod {...props('svod')} />, { hash: '#finmodel/svod' });
    expect(await screen.findByText('Модель ещё не рассчитана')).toBeInTheDocument();
    expect(screen.queryByText('Мощность к 2032 году')).toBeNull();
  });
});
