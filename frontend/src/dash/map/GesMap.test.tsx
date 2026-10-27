import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { MapStationOut } from '../../api/types';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { SVOD } from '../../test/s1Fixtures';
import { MAP } from '../../test/s3Fixtures';
import { GesMap, productionTip } from './GesMap';

describe('GesMap', () => {
  it('renders stations as toggle buttons with the TZ tooltip', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { container, rerender } = render(<GesMap stations={MAP} selected={null} onSelect={onSelect} />);
    expect(screen.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(container.querySelector('rect.ges__dot--hq')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: /Чарвакская ГЭС: 666 МВт, выработка 310,0 млн кВт·ч, 103% плана/ }));
    expect(onSelect).toHaveBeenLastCalledWith(2);
    rerender(<GesMap stations={MAP} selected={2} onSelect={onSelect} />);
    const charvak = screen.getByRole('button', { name: /Чарвакская ГЭС/ });
    expect(charvak).toHaveAttribute('aria-pressed', 'true');
    charvak.focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith(null);
    await expectNoAxeViolations(container);
  });

  // WCAG 2.5.3 (S1 a11y tuzatishi): accessible name ko'rinadigan qisqa nom bilan boshlanadi.
  it('accessible name starts with the visible short name', () => {
    render(<GesMap stations={MAP} selected={null} onSelect={() => undefined} />);
    for (const s of MAP) {
      expect(screen.getByRole('button', { name: new RegExp(`^${s.short_name}[.] `) })).toBeInTheDocument();
    }
  });

  it('marks stations below 95% of plan and accepts a custom tooltip', () => {
    const { container } = render(<GesMap stations={SVOD.stations} selected={null} onSelect={() => undefined} tip={(s) => `T:${s.short_name}`} />);
    expect(screen.getByRole('button', { name: 'Чарвак. T:Чарвак' })).toBeInTheDocument();
    expect(container.querySelector('.ges__dot.is-low')).toBeNull();
    render(<GesMap stations={MAP} selected={null} onSelect={() => undefined} />);
    expect(document.querySelectorAll('.ges__dot.is-low')).toHaveLength(1);
  });

  it('skips stations without coordinates; tooltip without production shows capacity only', () => {
    const noCoords = MAP.map((s) => (s.branch_id === 3 ? { ...s, lat: null, lon: null } : s));
    render(<GesMap stations={noCoords} selected={null} onSelect={() => undefined} />);
    expect(screen.getAllByRole('button')).toHaveLength(2);
    expect(productionTip({ ...(MAP[1] as MapStationOut), production: null })).toBe('Чарвакская ГЭС: 666 МВт');
  });
});
