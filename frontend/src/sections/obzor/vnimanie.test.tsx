import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { ALERTS } from '../../test/s1Fixtures';
import ObzorVnimanie from './vnimanie';

describe('Обзор / Требует внимания', () => {
  it('lists fired rules critical first and navigates with the same filters', async () => {
    mockApi({ 'GET /obzor/vnimanie': json(ALERTS) });
    const { user, container } = renderWithProviders(<ObzorVnimanie section="obzor" page="vnimanie" filters={{ br: 3, per: 'm08' }} onBranch={vi.fn()} />, { hash: '#obzor/vnimanie?br=3&per=m08' });
    const buttons = await screen.findAllByRole('button', { name: /Открыть/ });
    expect(buttons[0]).toHaveAccessibleName(/Критично.*Просроченные договоры/);
    expect(screen.getByText('Проверено правил: 2')).toBeInTheDocument();
    await expectNoAxeViolations(container);
    await user.click(buttons[1] as HTMLElement);
    expect(window.location.hash).toBe('#kazna/platezhi?br=3&per=m08');
  });

  it('says that nothing fired', async () => {
    mockApi({ 'GET /obzor/vnimanie': json({ ...ALERTS, items: [] }) });
    renderWithProviders(<ObzorVnimanie section="obzor" page="vnimanie" filters={{ br: null, per: 'ytd' }} onBranch={vi.fn()} />);
    expect(await screen.findByText('Отклонений не обнаружено: проверенные правила не сработали.')).toBeInTheDocument();
  });
});
