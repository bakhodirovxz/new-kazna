import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../../test/axe';
import { STATIONS } from './testStations';
import type { StationOut } from './types';
import { GesMap } from './GesMap';

describe('GesMap', () => {
  it('renders selectable stations, the HQ square and toggles selection', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { container, rerender } = render(<GesMap stations={STATIONS} selected={null} onSelect={onSelect} />);
    expect(screen.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(container.querySelector('rect.ges__dot--hq')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: /Чарвакская ГЭС: 666 МВт/ }));
    expect(onSelect).toHaveBeenLastCalledWith(2);
    rerender(<GesMap stations={STATIONS} selected={2} onSelect={onSelect} />);
    const charvak = screen.getByRole('button', { name: /Чарвакская ГЭС/ });
    expect(charvak).toHaveAttribute('aria-pressed', 'true');
    charvak.focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith(null);
    expect(container.querySelector('.ges__dot.is-low')).toBeNull();
    await expectNoAxeViolations(container);
  });

  it('skips stations without coordinates and marks low plan execution', () => {
    const stations = [
      { ...(STATIONS[1] as StationOut), production: { execution: 0.9 } },
      { ...(STATIONS[2] as StationOut), lat: null, lon: null },
    ];
    const { container } = render(<GesMap stations={stations} selected={null} onSelect={() => undefined} />);
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(container.querySelector('.ges__dot.is-low')).not.toBeNull();
  });
});
