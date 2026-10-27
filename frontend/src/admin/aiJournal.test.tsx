import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ME_ADMIN } from '../test/fixtures';
import { json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { AI_JOURNAL } from '../test/s5Fixtures';
import { allowedAdminPages } from './access';
import AiJournalPage from './AiJournalPage';

describe('Журнал AI-анализа', () => {
  it('lists requests with question or preset and status', async () => {
    mockApi({ 'GET /audit/ai-requests': json(AI_JOURNAL) });
    renderWithProviders(<AiJournalPage me={ME_ADMIN} />);
    const table = await screen.findByRole('table', { name: 'Журнал AI-анализа' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(1 + 2);
    expect(rows[1]).toHaveTextContent('Почему вырос долг?');
    expect(rows[2]).toHaveTextContent('Главные риски');
    expect(rows[2]).toHaveTextContent('таймаут');
    expect(screen.getByText('Журнал хранится 90 дней. Текст вопроса в журнал аудита не записывается.')).toBeInTheDocument();
  });

  it('is available with audit:read', () => {
    expect(allowedAdminPages(['audit:read']).map((p) => p.id)).toEqual(['audit', 'aijournal']);
  });
});
