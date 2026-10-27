import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../../test/render';
import { STATIONS } from './testStations';
import { StationPanel } from './StationPanel';

const filters = { br: null, per: 'm08' };

describe('StationPanel', () => {
  it('lists stations when nothing is selected', async () => {
    const onSelect = vi.fn();
    const { user } = renderWithProviders(<StationPanel stations={STATIONS} selected={null} onSelect={onSelect} filters={filters} onBranch={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Все станции' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Чарвакская ГЭС/ }));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it('shows finance of the selected station and opens its data', async () => {
    const onBranch = vi.fn();
    const { user } = renderWithProviders(<StationPanel stations={STATIONS} selected={2} onSelect={vi.fn()} filters={filters} onBranch={onBranch} />);
    expect(screen.getByRole('heading', { name: 'Чарвакская ГЭС' })).toBeInTheDocument();
    expect(screen.getByText('640,0 млн')).toBeInTheDocument();
    expect(screen.getByText('15,0 млн')).toHaveClass('neg');
    expect(screen.getByText('Выработка, план и КИУМ появятся после подключения АСКУЭ (этап 3).')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Открыть данные станции' }));
    expect(onBranch).toHaveBeenCalledWith(2);
  });

  it('explains that the head office has no stations', () => {
    renderWithProviders(<StationPanel stations={STATIONS} selected={1} onSelect={vi.fn()} filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(screen.getByText('Головная организация не эксплуатирует станции. Финансовые показатели:')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Открыть данные головной организации' })).toBeNull();
  });
});
