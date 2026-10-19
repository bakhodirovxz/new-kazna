import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { BuildOut, EtlRunDetail, EtlRunOut, KeyOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import BuildsPage from './BuildsPage';
import EtlPage from './EtlPage';
import KeysPage from './KeysPage';

const RUNS: EtlRunOut[] = [
  {
    id: 3, source: 'synthetic', mode: 'full', status: 'failed_quality',
    started_at: '2026-09-24T02:00:00Z', finished_at: '2026-09-24T02:04:05Z',
    window_from: '2024-01-01', window_to: '2026-09-24', rows_in: 120000, rows_upserted: 119500,
    build_id: null, triggered_by: null, error: 'Проверка качества не пройдена',
  },
  {
    id: 2, source: 'file', mode: 'incremental', status: 'success',
    started_at: '2026-09-23T10:00:00Z', finished_at: '2026-09-23T10:00:45Z',
    window_from: '2026-08-09', window_to: '2026-09-23', rows_in: 3000, rows_upserted: 2990,
    build_id: 11, triggered_by: 1, error: null,
  },
];

const DETAIL: EtlRunDetail = {
  run: RUNS[0] as EtlRunOut,
  steps: [
    { name: 'extract', status: 'success', started_at: '2026-09-24T02:00:00Z', finished_at: '2026-09-24T02:02:00Z', rows: 120000, detail: {} },
    { name: 'quality', status: 'failed', started_at: '2026-09-24T02:03:00Z', finished_at: '2026-09-24T02:04:05Z', rows: 0, detail: {} },
  ],
  errors: [
    { step: 'quality', severity: 'error', target: 'fact_balance', src_id: null, code: 'balance_mismatch', message: 'Остаток на конец месяца не сходится', created_at: '2026-09-24T02:04:00Z' },
  ],
};

describe('EtlPage', () => {
  it('lists runs with statuses and durations and opens the details', async () => {
    mockApi({ 'GET /admin/etl/runs': json({ items: RUNS, total: 2, page: 1, page_size: 50 }), 'GET /admin/etl/runs/3': json(DETAIL) });
    const { user } = renderWithProviders(<EtlPage />);
    const table = await screen.findByRole('table', { name: 'История загрузок' });
    expect(table).toHaveTextContent('Ошибка проверки качества');
    expect(table).toHaveTextContent('4 мин 05 с');
    expect(table).toHaveTextContent('Синтетические данные');
    await user.click(within(table).getByText('Ошибка проверки качества'));
    const dialog = screen.getByRole('dialog', { name: 'Загрузка №3' });
    expect(await within(dialog).findByText('Остаток на конец месяца не сходится')).toBeInTheDocument();
    expect(within(dialog).getByRole('table', { name: 'Шаги' })).toHaveTextContent('Проверки качества');
  });

  it('queues a run once and blocks a second start', async () => {
    const server = mockApi({
      'GET /admin/etl/runs': json({ items: [], total: 0, page: 1, page_size: 50 }),
      'POST /admin/etl/run': json({ request_id: 5, status: 'pending' }, 202),
    });
    const { user } = renderWithProviders(<EtlPage />);
    await user.selectOptions(await screen.findByLabelText('Режим'), 'full');
    await user.click(screen.getByRole('button', { name: 'Запустить' }));
    expect(await screen.findByText('Запрос №5 поставлен в очередь')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({ source: 'synthetic', mode: 'full' });
    expect(screen.getByRole('button', { name: 'Запустить' })).toBeDisabled();
    expect(screen.getByText(/Загрузка выполняется или поставлена в очередь/)).toBeInTheDocument();
  });

  it('blocks a start while a run is already running', async () => {
    mockApi({ 'GET /admin/etl/runs': json({ items: [{ ...(RUNS[0] as EtlRunOut), status: 'running', finished_at: null }], total: 1, page: 1, page_size: 50 }) });
    renderWithProviders(<EtlPage />);
    await screen.findByRole('table', { name: 'История загрузок' });
    expect(screen.getByRole('button', { name: 'Запустить' })).toBeDisabled();
  });

  it('offers only incremental mode for CSV files', async () => {
    const server = mockApi({
      'GET /admin/etl/runs': json({ items: [], total: 0, page: 1, page_size: 50 }),
      'POST /admin/etl/run': json({ request_id: 6, status: 'pending' }, 202),
    });
    const { user } = renderWithProviders(<EtlPage />);
    await user.selectOptions(await screen.findByLabelText('Режим'), 'full');
    await user.selectOptions(screen.getByLabelText('Источник'), 'file');
    expect(within(screen.getByLabelText('Режим')).queryByRole('option', { name: 'Полная' })).not.toBeInTheDocument();
    expect(screen.getByText(/--allow-full-replace/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Запустить' }));
    await screen.findByText('Запрос №6 поставлен в очередь');
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({ source: 'file', mode: 'incremental' });
  });

  it('shows server refusals', async () => {
    mockApi({
      'GET /admin/etl/runs': json({ items: [], total: 0, page: 1, page_size: 50 }),
      'POST /admin/etl/run': apiError(422, 'source_forbidden', 'Этот источник недоступен в рабочей среде'),
    });
    const { user } = renderWithProviders(<EtlPage />);
    await user.click(await screen.findByRole('button', { name: 'Запустить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Этот источник недоступен в рабочей среде');
    expect(screen.getByRole('button', { name: 'Запустить' })).toBeEnabled();
  });

  it('renders server error text as plain text, never as markup', async () => {
    const evil = '<img src=x onerror=alert(1)>';
    mockApi({
      'GET /admin/etl/runs': json({ items: RUNS, total: 2, page: 1, page_size: 50 }),
      'GET /admin/etl/runs/3': json({ ...DETAIL, run: { ...(RUNS[0] as EtlRunOut), error: evil } }),
    });
    const { user } = renderWithProviders(<EtlPage />);
    await user.click(await screen.findByText('Ошибка проверки качества'));
    const dialog = screen.getByRole('dialog', { name: 'Загрузка №3' });
    expect(await within(dialog).findByText(evil)).toBeInTheDocument();
    expect(dialog.querySelector('img')).toBeNull();
  });
});

const BUILDS: BuildOut[] = [
  { build_id: 12, created_at: '2026-09-24T02:05:00Z', status: 'published', load_id: 40, published_at: '2026-09-24T02:06:00Z', active: true },
  { build_id: 11, created_at: '2026-09-23T10:01:00Z', status: 'superseded', load_id: 39, published_at: '2026-09-23T10:02:00Z', active: false },
  { build_id: 10, created_at: '2026-09-22T02:05:00Z', status: 'failed', load_id: 38, published_at: null, active: false },
];

describe('BuildsPage', () => {
  it('makes an older build active after confirmation', async () => {
    const server = mockApi({
      'GET /admin/builds': json(BUILDS),
      'POST /admin/builds/rollback': json({ ...BUILDS[1], status: 'published', active: true }),
    });
    const { user } = renderWithProviders(<BuildsPage />);
    const table = await screen.findByRole('table', { name: 'Сборки витрины' });
    expect(within(table).getAllByRole('button', { name: 'Сделать активной' })).toHaveLength(1);
    expect(table).toHaveTextContent('Активная');
    await user.click(within(table).getByRole('button', { name: 'Сделать активной' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Сменить активную сборку?' });
    expect(dialog).toHaveTextContent('№11');
    await user.click(within(dialog).getByRole('button', { name: 'Сделать активной' }));
    expect(await screen.findByText('Активная сборка: №11')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({ build_id: 11 });
  });

  it('rolls back to the previous build by its explicit id and refreshes data freshness', async () => {
    const server = mockApi({
      'GET /admin/builds': json(BUILDS),
      'POST /admin/builds/rollback': json({ ...BUILDS[1], status: 'published', active: true }),
    });
    const { user, client } = renderWithProviders(<BuildsPage />);
    client.setQueryData(['meta', 'freshness'], { stale: true });
    await screen.findByRole('table', { name: 'Сборки витрины' });
    await user.click(screen.getByRole('button', { name: 'Откатить на предыдущую' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Сменить активную сборку?' });
    expect(dialog).toHaveTextContent('№11');
    await user.click(within(dialog).getByRole('button', { name: 'Сделать активной' }));
    await screen.findByText('Активная сборка: №11');
    expect(server.calls.find((c) => c.method === 'POST')?.body).toEqual({ build_id: 11 });
    expect(client.getQueryState(['meta', 'freshness'])?.isInvalidated).toBe(true);
  });

  it('shows a conflict inside the dialog and refetches the list', async () => {
    const server = mockApi({
      'GET /admin/builds': json(BUILDS),
      'POST /admin/builds/rollback': apiError(409, 'build_not_available', 'Сборка недоступна для активации'),
    });
    const { user } = renderWithProviders(<BuildsPage />);
    await user.click(within(await screen.findByRole('table', { name: 'Сборки витрины' })).getByRole('button', { name: 'Сделать активной' }));
    const dialog = screen.getByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: 'Сделать активной' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Сборка недоступна для активации');
    await waitFor(() => expect(server.calls.filter((c) => c.method === 'GET' && c.path === '/admin/builds')).toHaveLength(2));
  });
});

const KEYS: KeyOut[] = [
  { purpose: 'mfa', version: 2, status: 'active', created_at: '2026-09-20T00:00:00Z', retired_at: null },
  { purpose: 'mfa', version: 1, status: 'decrypt_only', created_at: '2026-09-01T00:00:00Z', retired_at: null },
  { purpose: 'pii', version: 1, status: 'active', created_at: '2026-09-01T00:00:00Z', retired_at: null },
  { purpose: 'audit_chain', version: 1, status: 'active', created_at: '2026-09-01T00:00:00Z', retired_at: null },
];

describe('KeysPage', () => {
  it('shows key versions and rotates a purpose', async () => {
    const server = mockApi({
      'GET /admin/keys': json(KEYS),
      'POST /admin/keys/mfa/rotate': json({ purpose: 'mfa', version: 3, reencrypted: 42 }),
    });
    const { user } = renderWithProviders(<KeysPage />);
    const table = await screen.findByRole('table', { name: 'Ключи шифрования' });
    expect(table).toHaveTextContent('Только расшифровка');
    expect(screen.getByText(/python -m app.cli retire-keys/)).toBeInTheDocument();
    expect(table).toHaveTextContent('Цепочка журнала аудита (HMAC)');
    const mfaRow = within(table).getAllByRole('row').find((r) => r.textContent?.includes('Секреты 2FA') && r.textContent.includes('Активный')) as HTMLElement;
    await user.click(within(mfaRow).getByRole('button', { name: 'Ротировать' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Ротировать ключ «Секреты 2FA»?' });
    await user.click(within(dialog).getByRole('button', { name: 'Ротировать' }));
    expect(await screen.findByText('«Секреты 2FA»: новая версия 3, перешифровано записей: 42')).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === 'POST' && c.path === '/admin/keys/mfa/rotate')).toBe(true);
  });
});

it('has no axe violations on ETL, builds and keys pages', async () => {
  mockApi({
    'GET /admin/etl/runs': json({ items: RUNS, total: 2, page: 1, page_size: 50 }),
    'GET /admin/builds': json(BUILDS),
    'GET /admin/keys': json(KEYS),
  });
  const { container } = renderWithProviders(
    <>
      <EtlPage />
      <BuildsPage />
      <KeysPage />
    </>,
  );
  await screen.findByRole('table', { name: 'История загрузок' });
  await screen.findByRole('table', { name: 'Сборки витрины' });
  await screen.findByRole('table', { name: 'Ключи шифрования' });
  await expectNoAxeViolations(container);
});
