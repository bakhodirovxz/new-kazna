import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { FLOW_IN, FLOW_OUT } from '../../test/s1Fixtures';
import ObzorPostup from './postup';
import ObzorRasxod from './rasxod';

describe('Обзор / Поступления и Расходование', () => {
  it('renders inflow series, banks and toggles a branch row', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /obzor/postup': json(FLOW_IN), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ObzorPostup section="obzor" page="postup" filters={{ br: 2, per: 'm08' }} onBranch={onBranch} />);
    expect(await screen.findByRole('img', { name: 'Поступления по месяцам' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Поступления по банкам' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Поступления по филиалам' });
    await user.click(within(table).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(null);
  });

  it('renders outflow by activity', async () => {
    mockApi({ 'GET /obzor/rasxod': json(FLOW_OUT), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ObzorRasxod section="obzor" page="rasxod" filters={{ br: null, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByRole('img', { name: 'Расходование по месяцам' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Расходы по видам деятельности' })).toBeInTheDocument();
    expect(screen.getAllByText('Централизованная').length).toBeGreaterThan(0);
  });
});
