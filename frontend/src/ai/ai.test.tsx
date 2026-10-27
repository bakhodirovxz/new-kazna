import { screen, waitFor, within } from '@testing-library/react';
import type userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { Route } from '../router/hash';
import { expectNoAxeViolations } from '../test/axe';
import { MENU_FULL, shellRoutes } from '../test/fixtures';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { AI_STATUS_OFF, AI_STATUS_ON } from '../test/s5Fixtures';
import { sseController, sseResponse } from '../test/sse';
import { AiButton } from './AiButton';

const route: Route = { kind: 'section', section: 'kazna', page: 'svod', br: null, per: null };

async function openDrawer(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'AI-анализ' }));
  return screen.findByRole('dialog', { name: 'AI-анализ' });
}

describe('AI-анализ', () => {
  it('is hidden while the feature is disabled', async () => {
    const { calls } = mockApi({ ...shellRoutes(), 'GET /ai/status': json(AI_STATUS_OFF) });
    renderWithProviders(<AiButton menu={MENU_FULL} route={route} />);
    await waitFor(() => expect(calls.some((c) => c.path === '/ai/status')).toBe(true));
    expect(screen.queryByRole('button', { name: 'AI-анализ' })).toBeNull();
  });

  it('streams the answer with headings, allows cancel while streaming and shows the disclaimer', async () => {
    const ctrl = sseController();
    const { calls } = mockApi({ ...shellRoutes(), 'GET /ai/status': json(AI_STATUS_ON), 'POST /ai/analyze': sseResponse(ctrl) });
    const { user, container } = renderWithProviders(<AiButton menu={MENU_FULL} route={route} />);
    const dialog = await openDrawer(user);
    await user.click(within(dialog).getByRole('button', { name: 'Проанализировать' }));
    expect(await within(dialog).findByText('Claude анализирует данные страницы…')).toBeInTheDocument();
    ctrl.send('start', { request_id: 9 });
    ctrl.send('delta', { text: '## Что важно заметить\n- Портфель **4,2 трлн сум**\n' });
    expect(await within(dialog).findByRole('heading', { name: 'Что важно заметить' })).toBeInTheDocument();
    expect(within(dialog).getByText('4,2 трлн сум').tagName).toBe('B');
    expect(within(dialog).getByRole('button', { name: 'Отменить' })).toBeInTheDocument();
    ctrl.send('done', { length: 40 });
    ctrl.close();
    await waitFor(() => expect(within(dialog).queryByRole('button', { name: 'Отменить' })).toBeNull());
    expect(within(dialog).getByText('Ответ носит рекомендательный характер и не заменяет решение ответственного лица.')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ section: 'kazna', page: 'svod', br: null, per: 'ytd' });
    await expectNoAxeViolations(container.ownerDocument.body);
  });

  it('shows provider errors and drops the partial text', async () => {
    const ctrl = sseController();
    mockApi({ ...shellRoutes(), 'GET /ai/status': json(AI_STATUS_ON), 'POST /ai/analyze': sseResponse(ctrl) });
    const { user } = renderWithProviders(<AiButton menu={MENU_FULL} route={route} />);
    const dialog = await openDrawer(user);
    await user.click(within(dialog).getByRole('button', { name: 'Проанализировать' }));
    ctrl.send('delta', { text: 'Частичный ответ' });
    ctrl.send('error', { code: 'ai_refused', message: 'Модель отказалась отвечать на этот запрос.' });
    ctrl.close();
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Модель отказалась отвечать на этот запрос.');
    expect(within(dialog).queryByText('Частичный ответ')).toBeNull();
  });

  it('explains the limit with the next attempt time and the organisation scope', async () => {
    mockApi({
      ...shellRoutes(),
      'GET /ai/status': json(AI_STATUS_ON),
      'POST /ai/analyze': apiError(429, 'ai_limit', 'Лимит', { retry_after: 600, scope: 'org' }, { 'Retry-After': '600' }),
    });
    const { user } = renderWithProviders(<AiButton menu={MENU_FULL} route={route} />);
    const dialog = await openDrawer(user);
    await user.click(within(dialog).getByRole('button', { name: 'Главные риски' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/Лимит запросов организации исчерпан \(300 в сутки\)\. Следующая попытка — в \d{2}:\d{2}\./);
  });

  it('cancel aborts the stream and keeps the drawer usable', async () => {
    const ctrl = sseController();
    const { calls } = mockApi({ ...shellRoutes(), 'GET /ai/status': json(AI_STATUS_ON), 'POST /ai/analyze': sseResponse(ctrl) });
    const { user } = renderWithProviders(<AiButton menu={MENU_FULL} route={route} />);
    const dialog = await openDrawer(user);
    await user.type(within(dialog).getByRole('searchbox', { name: 'Свой вопрос по данным страницы' }), 'Почему вырос долг?');
    await user.click(within(dialog).getByRole('button', { name: 'Спросить' }));
    ctrl.send('start', { request_id: 3 });
    await user.click(await within(dialog).findByRole('button', { name: 'Отменить' }));
    expect(await within(dialog).findByText('Запрос отменён.')).toBeInTheDocument();
    expect(ctrl.cancelled()).toBe(true);
    expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({ question: 'Почему вырос долг?' });
    expect(within(dialog).getByRole('button', { name: 'Проанализировать' })).toBeEnabled();
  });

  it('reports a feature switched off during the session', async () => {
    mockApi({ ...shellRoutes(), 'GET /ai/status': json(AI_STATUS_ON), 'POST /ai/analyze': apiError(404, 'ai_disabled', 'AI-анализ отключён') });
    const { user } = renderWithProviders(<AiButton menu={MENU_FULL} route={route} />);
    const dialog = await openDrawer(user);
    await user.click(within(dialog).getByRole('button', { name: 'Проанализировать' }));
    expect(await within(dialog).findByText('AI-анализ отключён администратором.')).toBeInTheDocument();
  });
});
