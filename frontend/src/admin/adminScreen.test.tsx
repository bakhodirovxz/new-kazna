import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { MeOut, MenuOut } from '../api/types';
import { useRoute } from '../router/store';
import { ME_ADMIN, ME_AUDITOR, MENU_AUDITOR, MENU_FULL, shellRoutes } from '../test/fixtures';
import { json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { AdminScreen } from './AdminScreen';

function Harness({ me, menu }: { me: MeOut; menu: MenuOut }) {
  const route = useRoute();
  if (route.kind !== 'admin') return <p>route:{route.kind}</p>;
  return <AdminScreen me={me} menu={menu} route={route} />;
}

describe('AdminScreen', () => {
  it('shows the admin side menu filtered by permissions and the users page', async () => {
    mockApi({
      ...shellRoutes(),
      'GET /admin/users': json({ items: [], total: 0, page: 1, page_size: 50 }),
      'GET /admin/positions': json([]),
    });
    renderWithProviders(<Harness me={ME_ADMIN} menu={MENU_FULL} />, { hash: '#admin/users' });
    const side = await screen.findByRole('complementary', { name: 'Администрирование' });
    expect(within(side).getAllByRole('link')).toHaveLength(8);
    expect(within(side).getByRole('link', { name: 'Пользователи' })).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { level: 1, name: 'Пользователи' })).toBeInTheDocument();
    expect(document.title).toBe('Пользователи | Администрирование | UGEKAZNA');
  });

  it('opens the first allowed page for #admin', async () => {
    mockApi(shellRoutes(ME_AUDITOR, MENU_AUDITOR));
    renderWithProviders(<Harness me={ME_AUDITOR} menu={MENU_AUDITOR} />, { hash: '#admin' });
    await waitFor(() => expect(window.location.hash).toBe('#admin/audit'));
    const side = await screen.findByRole('complementary', { name: 'Администрирование' });
    expect(within(side).getAllByRole('link').map((l) => l.textContent)).toEqual(['Журнал аудита']);
  });

  it('shows no access for a known admin page without permission', async () => {
    mockApi(shellRoutes(ME_AUDITOR, MENU_AUDITOR));
    renderWithProviders(<Harness me={ME_AUDITOR} menu={MENU_AUDITOR} />, { hash: '#admin/users' });
    expect(await screen.findByRole('heading', { name: 'Нет доступа' })).toBeInTheDocument();
  });
});
