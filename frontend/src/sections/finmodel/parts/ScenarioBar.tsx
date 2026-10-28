import { t } from '../../../i18n';
import { SCENARIO_IDS } from '../../../router/hash';
import { SCENARIO_NOTE_KEYS, SCENARIO_TITLE_KEYS, type Scenario } from './scenario';

/** Prototip `scenBar`: to'rt ssenariy tugmasi va tanlangan ssenariy izohi. */
export function ScenarioBar({ current, onChange }: { current: Scenario; onChange(next: Scenario): void }) {
  return (
    <div className="fin-bar">
      <span className="note">{t('fm.scen.label')}</span>
      <div className="seg" role="group" aria-label={t('fm.scen.group')}>
        {SCENARIO_IDS.map((id) => (
          <button key={id} type="button" aria-pressed={id === current} onClick={() => onChange(id)}>
            {t(SCENARIO_TITLE_KEYS[id])}
          </button>
        ))}
      </div>
      <span className="note">{t(SCENARIO_NOTE_KEYS[current])}</span>
    </div>
  );
}
