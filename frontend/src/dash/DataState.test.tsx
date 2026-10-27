import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { renderWithProviders } from '../test/render';
import { NoData } from './DataState';

describe('NoData', () => {
  it('explains an empty period and an unconnected source', async () => {
    const { container, rerender } = renderWithProviders(<NoData kind="period" />);
    expect(screen.getByRole('heading', { level: 3, name: 'Нет данных' })).toBeInTheDocument();
    expect(screen.getByText(/Нет данных за выбранный период/)).toBeInTheDocument();
    await expectNoAxeViolations(container);
    rerender(<NoData kind="source" source="остатки по банковским выпискам" />);
    expect(screen.getByText(/Источник данных не подключён: остатки по банковским выпискам/)).toBeInTheDocument();
  });
});
