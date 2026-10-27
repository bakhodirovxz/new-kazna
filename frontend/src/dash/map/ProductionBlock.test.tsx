import { screen } from '@testing-library/react';
import type { MapStationOut } from '../../api/types';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '../../test/render';
import { MAP } from '../../test/s3Fixtures';
import { ProductionBlock } from './ProductionBlock';

describe('ProductionBlock', () => {
  it('shows KIUM, generation vs plan and payment level with thresholds', () => {
    const chirchik = MAP[2] as MapStationOut;
    const { container } = renderWithProviders(<ProductionBlock capacity={chirchik.capacity_mw} production={chirchik.production} />);
    expect(screen.getByText('57,0%')).toBeInTheDocument();
    expect(screen.getByText('80% плана')).toHaveClass('neg');
    expect(screen.getByText('72,7%')).toHaveClass('neg');
    expect(container.querySelector('.gp-bar i.is-low')).not.toBeNull();
  });

  it('explains missing production data', () => {
    renderWithProviders(<ProductionBlock capacity={666} production={null} />);
    expect(screen.getByText('Нет данных о выработке за период.')).toBeInTheDocument();
  });
});
