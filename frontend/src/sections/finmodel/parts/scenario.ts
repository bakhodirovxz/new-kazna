import type { MessageKey } from '../../../i18n';
import { SCENARIO_IDS } from '../../../router/hash';
import { navigate, useRoute } from '../../../router/store';

export type Scenario = (typeof SCENARIO_IDS)[number];

export function isScenario(value: unknown): value is Scenario {
  return typeof value === 'string' && (SCENARIO_IDS as readonly string[]).includes(value);
}

export const SCENARIO_TITLE_KEYS: Record<Scenario, MessageKey> = {
  base: 'fm.scen.base', water: 'fm.scen.water', tariff: 'fm.scen.tariff', fx: 'fm.scen.fx',
};

export const SCENARIO_NOTE_KEYS: Record<Scenario, MessageKey> = {
  base: 'fm.scen.note.base', water: 'fm.scen.note.water', tariff: 'fm.scen.note.tariff', fx: 'fm.scen.note.fx',
};

/** TZ 5: ssenariy har sahifada; URL'da `scen` (bazaviy — parametrsiz), boshqa filtrlar saqlanadi. */
export function useScenario(): { scen: Scenario; setScen(next: Scenario): void } {
  const route = useRoute();
  const scen: Scenario = route.kind === 'section' && isScenario(route.scen) ? route.scen : 'base';
  return {
    scen,
    setScen: (next) => {
      if (route.kind === 'section') navigate({ ...route, scen: next === 'base' ? null : next });
    },
  };
}
