import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { MeOut, MenuOut } from '../api/types';
import { useRoute } from '../router/store';
import { expectNoAxeViolations } from '../test/axe';
import { FRESH_STALE, ME_ADMIN, ME_BRANCH, MENU_BRANCH, MENU_FULL, shellRoutes } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { SectionScreen } from './SectionScreen';
import { ShellTools } from './ShellTools';

function Harness({ me = ME_ADMIN, menu = MENU_FULL }: { me?: MeOut; menu?: MenuOut }) {
  const route = useRoute();
  if (route.kind !== 'section') return <p>route:{route.kind}</p>;
  return <SectionScreen me={me} menu={menu} route={route} tools={<ShellTools me={me} menu={menu} route={route} />} />;
}

describe('command palette', () => {
  it('opens with Ctrl+K and navigates with the keyboard keeping filters', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod?br=2' });
    await screen.findByText('Раздел в разработке');
    await user.keyboard('{Control>}k{/Control}');
    const dialog = screen.getByRole('dialog', { name: 'Быстрый переход' });
    const input = within(dialog).getByRole('combobox');
    expect(input).toHaveFocus();
    await user.type(input, 'календ');
    expect(within(dialog).getAllByRole('option')[0]).toHaveTextContent('Казначейство: Платёжный календарь');
    await user.keyboard('{Enter}');
    expect(window.location.hash).toBe('#kazna/calendar?br=2');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('applies a branch from the palette', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await screen.findByText('Раздел в разработке');
    await user.click(screen.getByRole('button', { name: 'Поиск' }));
    await user.type(screen.getByRole('combobox', { name: 'Быстрый переход' }), 'Андижан');
    await user.click(within(screen.getByRole('dialog')).getByRole('option', { name: /Андижанская ГЭС/ }));
    expect(window.location.hash).toBe('#obzor/svod?br=4');
  });

  it('hides branch items for a locked user', async () => {
    mockApi(shellRoutes(ME_BRANCH, MENU_BRANCH));
    const { user } = renderWithProviders(<Harness me={ME_BRANCH} menu={MENU_BRANCH} />, { hash: '#obzor/svod' });
    await screen.findByText('Раздел в разработке');
    await user.click(screen.getByRole('button', { name: 'Поиск' }));
    await user.type(screen.getByRole('combobox', { name: 'Быстрый переход' }), 'Каскад');
    expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
  });

  it('ignores Ctrl+K inside a password field', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(
      <>
        <Harness />
        <input type="password" aria-label="pw" />
      </>,
      { hash: '#obzor/svod' },
    );
    await screen.findByText('Раздел в разработке');
    await user.click(screen.getByLabelText('pw'));
    await user.keyboard('{Control>}k{/Control}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('toolbar', () => {
  it('copies the link with filters and prints', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#kazna/svod?per=q2' });
    await screen.findByText('Раздел в разработке');
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined); // user-event ozining clipboard'ini o'rnatadi
    await user.click(screen.getByRole('button', { name: 'Ссылка' }));
    expect(write).toHaveBeenCalledWith('https://ugk.test/#kazna/svod?per=q2');
    expect(await screen.findByRole('button', { name: 'Скопировано' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Печать' }));
    expect(window.print).toHaveBeenCalledOnce();
  });

  it('shows data freshness and warns when stale', async () => {
    mockApi(shellRoutes());
    const { unmount } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    expect(await screen.findByText('Данные на 24.09.2026 10:10')).toBeInTheDocument();
    expect(document.querySelector('.srcbar.live')).not.toBeNull();
    expect(screen.queryByText('Данные устарели')).not.toBeInTheDocument();
    unmount();
    mockApi({ ...shellRoutes(), 'GET /meta/freshness': json(FRESH_STALE) });
    renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    expect(await screen.findByText('Данные устарели')).toBeInTheDocument();
    expect(document.querySelector('.srcbar.warn')).toHaveTextContent('обновление задерживается более чем на 6 ч');
  });
});

describe('user menu', () => {
  it('opens with the keyboard, lists actions and logs out', async () => {
    const server = mockApi({ ...shellRoutes(), 'POST /auth/logout': { status: 204 } });
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    const button = await screen.findByRole('button', { name: 'Меню пользователя: Азимов Бахтиёр' });
    button.focus();
    await user.keyboard('{Enter}');
    expect(button).toHaveAttribute('aria-expanded', 'true');
    const menu = screen.getByRole('menu');
    const items = within(menu).getAllByRole('menuitem').map((i) => i.textContent);
    expect(items).toEqual(['Мои сеансы', 'Сменить пароль', 'Администрирование', 'Выйти']);
    expect(within(menu).getByRole('menuitem', { name: 'Мои сеансы' })).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(within(menu).getByRole('menuitem', { name: 'Выйти' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(button).toHaveFocus();
    await user.click(button);
    await user.click(screen.getByRole('menuitem', { name: 'Выйти' }));
    await waitFor(() => expect(window.location.hash).toBe('#login'));
    expect(server.calls.some((c) => c.method === 'POST' && c.path === '/auth/logout')).toBe(true);
  });

  it('renders the avatar initials via data-initials (CSS ::before), not as text', async () => {
    mockApi(shellRoutes());
    renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    const button = await screen.findByRole('button', { name: 'Меню пользователя: Азимов Бахтиёр' });
    const avatar = button.querySelector('.avatar');
    expect(avatar).toHaveAttribute('data-initials', 'АБ');
    expect(avatar).toBeEmptyDOMElement();
  });

  it('has no admin entry without admin permissions', async () => {
    mockApi(shellRoutes(ME_BRANCH, MENU_BRANCH));
    const { user } = renderWithProviders(<Harness me={ME_BRANCH} menu={MENU_BRANCH} />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: 'Меню пользователя: Каримова Нилуфар' }));
    expect(screen.queryByRole('menuitem', { name: 'Администрирование' })).not.toBeInTheDocument();
  });

  it('opens the admin area from the menu', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await user.click(await screen.findByRole('button', { name: /Меню пользователя/ }));
    await user.click(screen.getByRole('menuitem', { name: 'Администрирование' }));
    expect(window.location.hash).toBe('#admin/users');
  });
});

describe('section hotkeys', () => {
  it('switches sections with arrows outside inputs and keeps filters', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/vnimanie?br=2' });
    await screen.findByText('Раздел в разработке');
    await user.keyboard('{ArrowRight}');
    expect(window.location.hash).toBe('#kazna/svod?br=2');
    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(window.location.hash).toBe('#kadry/svod?br=2');
    screen.getByLabelText('Период').focus();
    await user.keyboard('{ArrowRight}');
    expect(window.location.hash).toBe('#kadry/svod?br=2');
  });

  it('does not switch sections while a dialog is open', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await screen.findByText('Раздел в разработке');
    await user.keyboard('{Control>}k{/Control}');
    screen.getByRole('dialog').focus();
    await user.keyboard('{ArrowRight}');
    expect(window.location.hash).toBe('#obzor/svod');
  });
});

it('has no axe violations with the toolbar', async () => {
  mockApi(shellRoutes());
  const { container } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
  await screen.findByText('Данные на 24.09.2026 10:10');
  await expectNoAxeViolations(container);
});

describe('review round 1', () => {
  it('opens the palette on the Russian layout (key л, code KeyK) but not with Shift', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await screen.findByText('Раздел в разработке');
    await user.keyboard('{Control>}{Shift>}{KeyK}{/Shift}{/Control}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'л', code: 'KeyK', ctrlKey: true, bubbles: true, cancelable: true }));
    expect(await screen.findByRole('dialog', { name: 'Быстрый переход' })).toBeInTheDocument();
  });

  it('scrolls the active palette option into view', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await screen.findByText('Раздел в разработке');
    await user.keyboard('{Control>}k{/Control}');
    const spy = vi.mocked(Element.prototype.scrollIntoView);
    spy.mockClear();
    await user.keyboard('{ArrowDown}');
    expect(spy).toHaveBeenCalledWith({ block: 'nearest' });
  });

  it('restores focus after the clipboard fallback', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await screen.findByText('Раздел в разработке');
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'));
    document.execCommand = vi.fn(() => true);
    const button = screen.getByRole('button', { name: 'Ссылка' });
    await user.click(button);
    expect(document.execCommand).toHaveBeenCalledWith('copy');
    expect(button).toHaveFocus();
  });

  it('does not jump between sections on non-section routes', async () => {
    mockApi(shellRoutes());
    const { user } = renderWithProviders(<ShellTools me={ME_ADMIN} menu={MENU_FULL} route={{ kind: 'admin', page: null }} />, { hash: '#obzor/svod' });
    await screen.findByRole('button', { name: /Меню пользователя/ });
    await user.keyboard('{ArrowRight}');
    expect(window.location.hash).toBe('#obzor/svod');
  });

  it('shows an unknown-state when freshness fails', async () => {
    mockApi({ ...shellRoutes(), 'GET /meta/freshness': apiError(500, 'internal') });
    renderWithProviders(<Harness />, { hash: '#obzor/svod' });
    await screen.findAllByText('Состояние данных неизвестно');
    await waitFor(() => expect(screen.getAllByText('Состояние данных неизвестно')).toHaveLength(2));
  });
});
