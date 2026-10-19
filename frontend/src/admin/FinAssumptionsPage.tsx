import { useMemo, useState } from 'react';
import type { FinAssumptionItem, FinAssumptionOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { FormError } from '../ui/Field';
import { Icon } from '../ui/icons';
import { PageSkeleton } from '../ui/Skeleton';
import { Tabs } from '../ui/Tabs';
import { useToast } from '../ui/Toast';
import { useFinAssumptions, useUpdateFinAssumptions } from './api';
import { formatDecimal, parseDecimal } from './numbers';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

type Scenario = FinAssumptionItem['scenario'];

const SCENARIOS: ReadonlyArray<{ id: Scenario; titleKey: MessageKey }> = [
  { id: 'base', titleKey: 'fin.scenario.base' },
  { id: 'water', titleKey: 'fin.scenario.water' },
  { id: 'tariff', titleKey: 'fin.scenario.tariff' },
  { id: 'fx', titleKey: 'fin.scenario.fx' },
];

const KEY_TITLES: Record<string, MessageKey> = {
  tariff_growth: 'fin.key.tariff_growth',
  generation_factor: 'fin.key.generation_factor',
  fx_rate_factor: 'fin.key.fx_rate_factor',
  opex_index: 'fin.key.opex_index',
  tax_rate: 'fin.key.tax_rate',
  kium: 'fin.key.kium',
};

function keyTitle(key: string): string {
  return Object.hasOwn(KEY_TITLES, key) ? t(KEY_TITLES[key] as MessageKey) : key;
}

// numeric(18,6): DB aniqligiga yaxlitlab solishtiramiz, aks holda bir xil qiymat uchun yangi versiya yaratiladi.
const round6 = (v: number) => Math.round(v * 1e6) / 1e6;
const inRange = (v: number | null): v is number => v !== null && v >= -10 && v <= 10;

function cellId(scenario: string, year: number, key: string): string {
  return `${scenario}|${year}|${key}`;
}

export default function FinAssumptionsPage() {
  const data = useFinAssumptions();
  const update = useUpdateFinAssumptions();
  const toast = useToast();
  const [scenario, setScenario] = useState<Scenario>('base');
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [attempt, setAttempt] = useState({}); // har «Сохранить» — yangi obyekt: fokus faqat bosilganda
  const [attempted, setAttempted] = useState(false);

  const index = useMemo(() => {
    const map = new Map<string, FinAssumptionOut>();
    for (const row of data.data ?? []) map.set(cellId(row.scenario, row.year, row.key), row);
    return map;
  }, [data.data]);
  const years = useMemo(() => [...new Set((data.data ?? []).map((r) => r.year))].sort((a, b) => a - b), [data.data]);
  const keys = useMemo(() => {
    const present = new Set((data.data ?? []).map((r) => r.key));
    return [...Object.keys(KEY_TITLES).filter((k) => present.has(k)), ...[...present].filter((k) => !Object.hasOwn(KEY_TITLES, k))];
  }, [data.data]);

  const changed = Object.entries(draft).filter(([id, text]) => {
    const original = index.get(id);
    const parsed = parseDecimal(text);
    return original === undefined || parsed === null || round6(parsed) !== original.value;
  });

  const scenarioTitle = (id: string) => t(SCENARIOS.find((s) => s.id === id)?.titleKey ?? 'fin.scenario.base');
  const parts = (id: string) => id.split('|') as [Scenario, string, string];

  // Noto'g'ri kataklar «Сохранить» bosilgandan keyin jonli hisoblanadi: to'g'rilangani xabardan ketadi.
  const badIds = attempted ? changed.filter(([, text]) => !inRange(parseDecimal(text))).map(([id]) => id) : [];
  const badSet = new Set(badIds);
  const invalidLabels = badIds.map((id) => {
    const [sc, year, key] = parts(id);
    return `${scenarioTitle(sc)} · ${keyTitle(key)} · ${year}`;
  });
  const gridRef = useFocusFirstInvalid<HTMLDivElement>(attempt);

  const save = () => {
    const items: FinAssumptionItem[] = [];
    let firstBad: Scenario | null = null;
    for (const [id, text] of changed) {
      const [sc, yearText, key] = parts(id);
      const value = parseDecimal(text);
      if (!inRange(value)) firstBad ??= sc;
      else items.push({ scenario: sc, year: Number(yearText), key, value: round6(value) });
    }
    setAttempted(true);
    setAttempt({});
    if (firstBad) setScenario(firstBad); // noto'g'ri katak ko'rinadigan varaqqa o'tamiz
    if (firstBad || items.length === 0) return;
    update.mutate(items, {
      onSuccess: () => {
        toast.show(t('fin.saved'), 'success');
        setDraft({});
        setAttempted(false);
      },
    });
  };

  if (data.isError) return <ErrorBanner error={data.error} lastSuccessAt={data.dataUpdatedAt} onRetry={() => void data.refetch()} />;
  if (data.isPending) return <PageSkeleton />;

  return (
    <Card>
      <Tabs
        label={t('fin.scenarios')}
        tabs={SCENARIOS.map((s) => ({ id: s.id, label: t(s.titleKey) }))}
        value={scenario}
        onChange={(id) => setScenario(SCENARIOS.find((s) => s.id === id)?.id ?? 'base')}
      >
        <p className="note">{t('fin.hint')}</p>
        <div ref={gridRef} className="tw tw--free">
          <table className="table matrix">
            <caption className="visually-hidden">{t(SCENARIOS.find((s) => s.id === scenario)?.titleKey ?? 'fin.scenario.base')}</caption>
            <thead>
              <tr>
                <th scope="col" className="l">
                  {t('fin.col.key')}
                </th>
                {years.map((year) => (
                  <th key={year} scope="col">
                    {year}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key}>
                  <th scope="row" className="l">
                    {keyTitle(key)}
                  </th>
                  {years.map((year) => {
                    const id = cellId(scenario, year, key);
                    const original = index.get(id);
                    if (!original) return <td key={year}>{t('common.dash')}</td>;
                    return (
                      <td key={year}>
                        <input
                          className="input"
                          inputMode="decimal"
                          aria-label={`${keyTitle(key)}, ${year}`}
                          aria-invalid={badSet.has(id) || undefined}
                          value={draft[id] ?? formatDecimal(original.value)}
                          onChange={(e) => setDraft((d) => ({ ...d, [id]: e.target.value }))}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Tabs>
      {invalidLabels.length > 0 ? (
        <p className="form-error" role="alert">
          <Icon name="alert" />
          <span>{t('fin.invalid', { cells: invalidLabels.join('; ') })}</span>
        </p>
      ) : null}
      <FormError error={update.error} />
      <div className="toolbar">
        <span className="note">{t('fin.changed', { count: changed.length })}</span>
        <span className="toolbar__grow" />
        <Button variant="secondary" disabled={changed.length === 0} onClick={() => {
            setDraft({});
            setAttempted(false);
          }}>
          {t('fin.reset')}
        </Button>
        <Button disabled={changed.length === 0} loading={update.isPending} onClick={save}>
          {t('fin.save')}
        </Button>
      </div>
    </Card>
  );
}
