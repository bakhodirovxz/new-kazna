import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { KAZNA_CELEVYE, KAZNA_DOGOVORY } from '../../test/s1Fixtures';
import KaznaCelevye from './celevye';
import KaznaDogovory from './dogovory';

describe('Казначейство / Договоры и Целевые средства', () => {
  it('lists contracts and branch debt; clicking a branch selects it', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kazna/dogovory': json(KAZNA_DOGOVORY), 'GET /auth/me': json(ME_ADMIN) });
    const { user, container } = renderWithProviders(<KaznaDogovory section="kazna" page="dogovory" filters={{ br: null, per: 'm08' }} onBranch={onBranch} />);
    const branches = await screen.findByRole('table', { name: 'Задолженность по филиалам' });
    expect(within(branches).getByText('30,0 млн')).toHaveClass('neg');
    await user.click(within(branches).getByText('Каскад Чирчикских ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(3);
    await user.click(within(screen.getByRole('group', { name: 'Тип задолженности' })).getByRole('button', { name: 'Кредиторская' })); // в заголовке таблицы филиалов есть такая же кнопка сортировки
    const debt = screen.getByRole('table', { name: 'Задолженность по договорам' });
    expect(within(debt).getByText('ООО «Гидромонтаж»')).toBeInTheDocument();
    expect(within(debt).queryByText('ООО «Тест Поставщик»')).toBeNull();
    await expectNoAxeViolations(container);
  });

  it('shows target funds by source and branch', async () => {
    mockApi({ 'GET /kazna/celevye': json(KAZNA_CELEVYE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KaznaCelevye section="kazna" page="celevye" filters={{ br: null, per: 'q3' }} onBranch={vi.fn()} />);
    expect(await screen.findByText('Бюджетные средства на капитальные вложения')).toBeInTheDocument();
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0);
    expect(screen.getByText('50% от выделенного')).toBeInTheDocument();
  });

  it('shows the source note when funds are not loaded', async () => {
    mockApi({ 'GET /kazna/celevye': json({ ...KAZNA_CELEVYE, sources: [], branches: [] }), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KaznaCelevye section="kazna" page="celevye" filters={{ br: null, per: 'q3' }} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(/Источник данных не подключён: целевые средства/)).toHaveLength(2); // обе карточки
  });
});
