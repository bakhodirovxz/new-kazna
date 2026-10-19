import { screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ME_ADMIN, MENU_FULL, shellRoutes } from '../test/fixtures';
import { mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { useRoute } from '../router/store';
import type * as Registry from '../sections/registry';
import { SectionScreen } from './SectionScreen';

const state = vi.hoisted(() => ({ attempts: 0 }));
vi.mock('../sections/registry', async () => {
  const actual = await vi.importActual<typeof Registry>('../sections/registry');
  return {
    resolveSectionPage: actual.createRegistry({
      './kazna/svod.tsx': () => {
        state.attempts += 1;
        return state.attempts === 1 ? Promise.reject(new Error('chunk')) : Promise.resolve({ default: () => <p>loaded page</p> });
      },
    }),
  };
});

function Harness() {
  const route = useRoute();
  return route.kind === 'section' ? <SectionScreen me={ME_ADMIN} menu={MENU_FULL} route={route} /> : null;
}

it('keeps the shell and retries when a lazy page chunk fails', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  mockApi(shellRoutes());
  const { user } = renderWithProviders(<Harness />, { hash: '#kazna/svod' });
  const alert = await screen.findByText('Не удалось загрузить страницу');
  expect(alert).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Разделы' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('loaded page')).toBeInTheDocument();
});
