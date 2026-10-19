import { act, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { MeOut, MenuOut } from '../api/types';
import { useRoute } from '../router/store';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN, ME_BRANCH, MENU_BRANCH, MENU_FULL, shellRoutes } from '../test/fixtures';
import { apiError, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { setViewport } from '../test/viewport';
import { SectionScreen } from './SectionScreen';

function Harness({ me = ME_ADMIN, menu = MENU_FULL }: { me?: MeOut; menu?: MenuOut }) {
  const route = useRoute();
  if (route.kind !== 'section') return <p>route:{route.kind}</p>;
  return <SectionScreen me={me} menu={menu} route={route} />;
}

describe('SectionScreen', () => {
  it('renders section navigation, the side menu and the placeholder page with filters', async () => {
    mockApi(shellRoutes());
    renderWithProviders(<Harness />, { hash: '#kazna/platezhi?br=2&per=q1' });
    expect(await screen.findByRole('heading', { level: 1, name: 'Исполнение платежей' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Разделы' });
    expect(within(nav).getAllByRole('link')).toHaveLength(9);
    expect(within(nav).getByRole('link', { name: 'Казначейство' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Кредиты' })).toHaveAttribute('href', '#kredity/svod?br=2&per=q1');
    const side = screen.getByRole('complementary', { name: 'Казначейство' });
    expect(within(side).getByRole('link', { name: 'Исполнение платежей' })).toHaveAttribute('aria-current', 'page');
    expect(within(side).getByRole('link', { name: 'Платёжный календарь' })).toHaveAttribute(
      'href',
      '#kazna/calendar?br=2&per=q1',
    );
    expect(await screen.findByText('Раздел в разработке')).toBeInTheDocument();
    const chips = screen.getByRole('group', { name: 'Активные фильтры' });
    expect(chips).toHaveTextContent('Филиал: Чарвакская ГЭС');
    expect(chips).toHaveTextContent('Период: I квартал 2026');
    expect(within(chips).getByRole('button', { name: 'Сбросить всё' })).toBeInTheDocument();
    expect(document.title).toBe('Исполнение платежей | Казначейство | UGEKAZNA');
  });

  it('fills in the first page when the page is missing or unknown', async () => {
    mockApi(shellRoutes());
    renderWithProviders(<Harness />, { hash: '#kazna' });
    await waitFor(() => expect(window.location.hash).toBe('#kazna/svod'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Казначейство: сводка' })).toBeInTheDocument();
  });

  it('normalizes unknown branch and period in the URL', async () => {
    mockApi(shellRoutes());
    renderWithProviders(<Harness />, { hash: '#obzor/svod?br=99&per=m12' });
    await waitFor(() => expect(window.location.hash).toBe('#obzor/svod'));
    expect(screen.queryByRole('group', { name: 'Активные фильтры' })).not.toBeInTheDocument();
  });

  it('drops the default period from the URL', async () => {
    mockApi(shellRoutes());
    renderWithProviders(<Harness />, { hash: '#obzor/svod?per=ytd' });
    await waitFor(() => expect(window.location.hash).toBe('#obzor/svod'));
  });

  it('shows no-access for a forbidden section and not-found for an unknown one', async () => {
    mockApi(shellRoutes(ME_BRANCH, MENU_BRANCH));
    const { unmount } = renderWithProviders(<Harness me={ME_BRANCH} menu={MENU_BRANCH} />, { hash: '#kredity/svod' });
    expect(await screen.findByRole('heading', { name: 'Нет доступа' })).toBeInTheDocument();
    unmount();
    renderWithProviders(<Harness me={ME_BRANCH} menu={MENU_BRANCH} />, { hash: '#foo/bar' });
    expect(await screen.findByRole('heading', { name: 'Страница не найдена' })).toBeInTheDocument();
  });

  it('locks the branch filter for a single-branch user', async () => {
    mockApi(shellRoutes(ME_BRANCH, MENU_BRANCH));
    renderWithProviders(<Harness me={ME_BRANCH} menu={MENU_BRANCH} />, { hash: '#obzor/svod?br=2' });
    await waitFor(() => expect(window.location.hash).toBe('#obzor/svod?br=3'));
    const select = await screen.findByLabelText('Филиал');
    await waitFor(() => expect(select).toHaveDisplayValue('Каскад Чирчикских ГЭС'));
    expect(select).toBeDisabled();
    expect(screen.getByText('Доступны только данные вашего филиала')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Сбросить: Филиал' })).not.toBeInTheDocument();
  });

  it('writes filter changes to the URL and resets them', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    const period = await screen.findByLabelText('Период');
    await waitFor(() => expect(period).toBeEnabled());
    await user.selectOptions(period, 'q2');
    expect(window.location.hash).toBe('#obzor/svod?per=q2');
    await user.selectOptions(screen.getByLabelText('Филиал'), '4');
    expect(window.location.hash).toBe('#obzor/svod?br=4&per=q2');
    await user.click(screen.getByRole('button', { name: 'Сбросить: Период' }));
    expect(window.location.hash).toBe('#obzor/svod?br=4');
    await user.selectOptions(screen.getByLabelText('Период'), 'm05');
    await user.click(screen.getByRole('button', { name: 'Сбросить всё' }));
    expect(window.location.hash).toBe('#obzor/svod');
  });

  it('shows an error banner with retry when filter dictionaries fail', async () => {
    mockApi({ ...shellRoutes(), 'GET /meta/branches': apiError(500, 'internal_error', 'Внутренняя ошибка сервера') });
    renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Не удалось загрузить справочники фильтров');
    expect(within(alert).getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
  });

  it('mobile: side menu opens in a drawer and filters in a bottom sheet', async () => {
    setViewport(390);
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#kazna/svod' });
    await screen.findByRole('heading', { level: 1, name: 'Казначейство: сводка' });
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Меню раздела' }));
    const drawer = screen.getByRole('dialog', { name: 'Казначейство' });
    await user.click(within(drawer).getByRole('link', { name: 'Платёжный календарь' }));
    await waitFor(() => expect(window.location.hash).toBe('#kazna/calendar'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Фильтры' }));
    const sheet = screen.getByRole('dialog', { name: 'Фильтры' });
    expect(within(sheet).getByLabelText('Период')).toBeInTheDocument();
    await user.click(within(sheet).getByRole('button', { name: 'Готово' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('tablet: the side menu collapses and expands', async () => {
    setViewport(1024);
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#kazna/svod' });
    const toggle = await screen.findByRole('button', { name: 'Меню раздела' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('complementary', { name: 'Казначейство' })).toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    act(() => setViewport(1440));
    expect(screen.queryByRole('button', { name: 'Меню раздела' })).not.toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Казначейство' })).toBeInTheDocument();
  });

  it('has no axe violations on desktop', async () => {
    mockApi(shellRoutes());
    const { container } = renderWithProviders(<Harness />, { hash: '#kazna/svod?br=2' });
    await screen.findByText('Раздел в разработке');
    await expectNoAxeViolations(container);
  });
});
