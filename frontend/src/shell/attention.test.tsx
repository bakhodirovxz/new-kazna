import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from '../app/App';
import { json, mockApi } from '../test/mockApi';
import { shellRoutes } from '../test/fixtures';
import { renderWithProviders } from '../test/render';
import { ALERTS, SVOD } from '../test/s1Fixtures';

describe('attention counter', () => {
  it('shows the rule count next to «Требует внимания» in the Обзор menu', async () => {
    mockApi({ ...shellRoutes(), 'GET /obzor/svod': json(SVOD), 'GET /obzor/vnimanie/count': json({ count: 2, critical: 1 }), 'GET /obzor/vnimanie': json(ALERTS) });
    renderWithProviders(<App />, { hash: '#obzor/svod' });
    const side = await screen.findByRole('complementary', { name: 'Обзор' });
    const link = await within(side).findByRole('link', { name: /Требует внимания/ });
    expect(await within(link).findByText('2')).toBeInTheDocument();
  });

  it('hides the counter when nothing fired', async () => {
    mockApi({ ...shellRoutes(), 'GET /obzor/svod': json(SVOD), 'GET /obzor/vnimanie/count': json({ count: 0, critical: 0 }) });
    renderWithProviders(<App />, { hash: '#obzor/svod' });
    const side = await screen.findByRole('complementary', { name: 'Обзор' });
    const link = await within(side).findByRole('link', { name: /Требует внимания/ });
    expect(within(link).queryByText('0')).toBeNull();
  });
});
