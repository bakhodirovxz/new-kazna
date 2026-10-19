import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import { t } from '../i18n';
import { expectNoAxeViolations } from '../test/axe';
import css from './display.css?raw';
import { Badge } from './Badge';
import { Card } from './Card';
import { Chip } from './Chip';
import { EmptyState } from './EmptyState';
import { ErrorBanner } from './ErrorBanner';
import { KpiGrid, KpiTile } from './KpiTile';
import { PageSkeleton } from './Skeleton';
import { Tabs } from './Tabs';
import { Tooltip } from './Tooltip';

describe('Card', () => {
  it('is a region named by its title', () => {
    render(
      <Card title="Остатки по банкам" sub="На 24.09.2026">
        <p>тело</p>
      </Card>,
    );
    expect(screen.getByRole('region', { name: 'Остатки по банкам' })).toHaveTextContent('На 24.09.2026');
  });
});

describe('Chip', () => {
  it('removes itself with a labelled button', async () => {
    const onRemove = vi.fn();
    render(<Chip label="Филиал" value="Чарвакская ГЭС" onRemove={onRemove} />);
    await userEvent.click(screen.getByRole('button', { name: 'Сбросить: Филиал' }));
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it('has no remove button when locked', () => {
    render(<Chip label="Филиал" value="Чирчик" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('KpiTile', () => {
  it('shows value, unit, delta and a formula tooltip', async () => {
    render(
      <KpiGrid>
        <KpiTile icon="coins" label="Поступления" value="1 234,5" unit="млрд" delta="−3,2% к 2025" deltaDown hint="Все зачисления на счета" />
      </KpiGrid>,
    );
    expect(screen.getByText('1 234,5')).toBeInTheDocument();
    expect(screen.getByText('млрд')).toBeInTheDocument();
    const trigger = screen.getByRole('button', { name: 'Как считается: Поступления' });
    expect(trigger).toHaveAccessibleDescription('Все зачисления на счета');
  });
});

describe('KpiTile without data', () => {
  it('shows a dash with the reason', () => {
    render(<KpiTile icon="coins" label="План" value={t('common.dash')} delta={t('common.noData')} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('нет данных в источнике')).toBeInTheDocument();
  });
});

describe('Tooltip (WCAG 1.4.13)', () => {
  const setup = () => {
    render(<Tooltip content="Подсказка">{(p) => <button type="button" {...p}>?</button>}</Tooltip>);
    return screen.getByRole('button', { name: '?' });
  };

  it('is dismissed with Escape while only hovered', async () => {
    const trigger = setup();
    await userEvent.hover(trigger);
    await userEvent.keyboard('{Escape}');
    expect(trigger.parentElement).toHaveClass('is-dismissed');
    await userEvent.unhover(trigger);
    expect(trigger.parentElement).not.toHaveClass('is-dismissed');
  });

  it('does not listen on document when hidden and cleans up on unmount', async () => {
    const add = vi.spyOn(document, 'addEventListener');
    const remove = vi.spyOn(document, 'removeEventListener');
    const trigger = setup();
    expect(add).not.toHaveBeenCalledWith('keydown', expect.anything());
    await userEvent.hover(trigger);
    expect(add).toHaveBeenCalledWith('keydown', expect.any(Function));
    cleanup();
    expect(remove).toHaveBeenCalledWith('keydown', expect.any(Function));
  });
});

describe('Tooltip', () => {
  it('is dismissed with Escape and comes back after blur', async () => {
    render(<Tooltip content="Подсказка">{(p) => <button type="button" {...p}>?</button>}</Tooltip>);
    const trigger = screen.getByRole('button', { name: '?' });
    await userEvent.tab();
    expect(trigger).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(trigger.parentElement).toHaveClass('is-dismissed');
    await userEvent.tab();
    expect(trigger.parentElement).not.toHaveClass('is-dismissed');
  });
});

function TabsHarness() {
  const [value, setValue] = useState('pos');
  return (
    <Tabs
      label="Справочники"
      tabs={[
        { id: 'pos', label: 'Должности' },
        { id: 'roles', label: 'Роли' },
      ]}
      value={value}
      onChange={setValue}
    >
      <p>панель {value}</p>
    </Tabs>
  );
}

describe('Tabs', () => {
  it('moves selection with arrow keys (roving tabindex)', async () => {
    render(<TabsHarness />);
    const first = screen.getByRole('tab', { name: 'Должности' });
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('панель pos');
    first.focus();
    await userEvent.keyboard('{ArrowRight}');
    const second = screen.getByRole('tab', { name: 'Роли' });
    expect(second).toHaveAttribute('aria-selected', 'true');
    expect(second).toHaveFocus();
    expect(first).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('tabpanel', { name: 'Роли' })).toHaveTextContent('панель roles');
  });
});

describe('Tabs edge cases', () => {
  it('keeps the tablist reachable when value matches no tab', () => {
    render(
      <Tabs label="x" tabs={[{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }]} value="zzz" onChange={vi.fn()}>
        <p>p</p>
      </Tabs>,
    );
    expect(screen.getByRole('tab', { name: 'A' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'B' })).toHaveAttribute('tabindex', '-1');
  });

  it('does not clip the focus ring (no overflow:hidden on .tabs__list)', () => {
    const rule = /\.tabs__list\s*\{[^}]*\}/.exec(css)?.[0] ?? '';
    expect(rule).not.toBe('');
    expect(rule).not.toMatch(/overflow\s*:\s*hidden/);
  });
});

describe('ErrorBanner', () => {
  it('shows message, last success time, request id and retries', async () => {
    const onRetry = vi.fn();
    render(
      <ErrorBanner
        error={new ApiError(503, 'unavailable', 'Сервис недоступен', 'abc123')}
        lastSuccessAt={Date.parse('2026-09-24T05:07:00Z')}
        onRetry={onRetry}
      />,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Сервис недоступен');
    expect(alert).toHaveTextContent('Последняя успешная загрузка: 24.09.2026 10:07');
    expect(alert).toHaveTextContent('Код запроса: abc123');
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('uses the network text for non-API errors and hides empty metadata', () => {
    render(<ErrorBanner error={new ApiError(0, 'network', 'Нет связи с сервером.')} lastSuccessAt={0} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Нет связи с сервером.');
    expect(screen.queryByText(/Последняя успешная/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

it('announces loading skeletons politely', () => {
  render(<PageSkeleton />);
  expect(screen.getByRole('status')).toHaveTextContent('Загрузка…');
});

it('has no axe violations', async () => {
  const { container } = render(
    <main>
      <Card title="Карточка" actions={<Badge tone="ok">Активен</Badge>}>
        <EmptyState icon="clock" title="Раздел в разработке" text="Страница появится позже." />
      </Card>
      <Badge tone="neg">Заблокирован</Badge>
      <Chip label="Период" value="I квартал 2026" onRemove={vi.fn()} />
      <TabsHarness />
      <ErrorBanner error={new Error('x')} onRetry={vi.fn()} />
    </main>,
  );
  await expectNoAxeViolations(container);
});
