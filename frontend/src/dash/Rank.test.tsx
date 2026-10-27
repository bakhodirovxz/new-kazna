import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../test/axe';
import { renderWithProviders } from '../test/render';
import { Rank } from './Rank';

describe('Rank', () => {
  it('renders bars, shares and selectable rows', async () => {
    const onSelect = vi.fn();
    const { user, container } = renderWithProviders(
      <Rank label="Топ статей" items={[{ id: 1, name: 'Налоги', value: 300 }, { id: 2, name: 'ТМЦ', value: 100 }]} onSelect={onSelect} activeId={2} />,
    );
    expect(screen.getByText('75,0%')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Налоги/ }));
    expect(onSelect).toHaveBeenCalledWith(1);
    expect(screen.getByRole('button', { name: /ТМЦ/ })).toHaveAttribute('aria-pressed', 'true');
    await expectNoAxeViolations(container);
  });
});
