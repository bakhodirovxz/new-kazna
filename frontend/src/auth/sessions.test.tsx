import { screen, waitFor, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { ME_ADMIN, MENU_FULL, shellRoutes } from '../test/fixtures';
import { json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { Routes } from '../app/Routes';
import { SessionsScreen } from './SessionsScreen';

const SESSIONS = [
  { id: 'a1', created_at: '2026-09-24T04:00:00Z', last_seen_at: '2026-09-24T05:30:00Z', ua_summary: 'Chrome · Windows', ip: '10.0.0.5', current: true },
  { id: 'b2', created_at: '2026-09-20T04:00:00Z', last_seen_at: '2026-09-21T06:00:00Z', ua_summary: 'Firefox · Linux', ip: null, current: false },
];

it('lists sessions, marks the current one and ends another after confirmation', async () => {
  let list = SESSIONS;
  const server = mockApi({
    ...shellRoutes(),
    'GET /auth/sessions': () => json(list),
    'DELETE /auth/sessions/b2': () => {
      list = SESSIONS.slice(0, 1);
      return { status: 204 };
    },
  });
  const { user } = renderWithProviders(<SessionsScreen me={ME_ADMIN} menu={MENU_FULL} />, { hash: '#account/sessions' });
  const table = await screen.findByRole('table', { name: 'Мои сеансы' });
  const rows = within(table).getAllByRole('row').slice(1);
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent('Chrome · Windows');
  expect(rows[0]).toHaveTextContent('Текущий сеанс');
  expect(within(rows[0] as HTMLElement).queryByRole('button', { name: 'Завершить' })).not.toBeInTheDocument();
  expect(rows[1]).toHaveTextContent('—');
  await user.click(within(rows[1] as HTMLElement).getByRole('button', { name: 'Завершить' }));
  const dialog = screen.getByRole('alertdialog', { name: 'Завершить сеанс?' });
  expect(dialog).toHaveTextContent('Firefox · Linux');
  await user.click(within(dialog).getByRole('button', { name: 'Завершить' }));
  expect(await screen.findByText('Сеанс завершён')).toBeInTheDocument();
  await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
  expect(server.calls.some((c) => c.method === 'DELETE' && c.path === '/auth/sessions/b2')).toBe(true);
  expect(screen.getByRole('link', { name: 'Сменить пароль' })).toHaveAttribute('href', '#password');
  await expectNoAxeViolations(document.body);
});

it('never offers to end the current session and routes #account/sessions', async () => {
  mockApi({ ...shellRoutes(), 'GET /auth/sessions': () => json(SESSIONS) });
  renderWithProviders(<Routes />, { hash: '#account/sessions' });
  const table = await screen.findByRole('table', { name: 'Мои сеансы' });
  expect(within(table).getAllByRole('button', { name: 'Завершить' })).toHaveLength(1);
});
