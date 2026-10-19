import type { ReactNode } from 'react';
import { t } from '../i18n';
import { cx } from './cx';
import { Icon, type IconName } from './icons';
import { Tooltip } from './Tooltip';
import './display.css';

export interface KpiTileProps {
  icon: IconName;
  label: string;
  value: ReactNode;
  unit?: string;
  delta?: ReactNode;
  deltaDown?: boolean;
  negative?: boolean;
  /** TZ 6: har ko'rsatkichda formula bilan qalqib chiquvchi izoh. */
  hint?: string;
}

export function KpiTile({ icon, label, value, unit, delta, deltaDown, negative, hint }: KpiTileProps) {
  return (
    <div className="kpi">
      <div className="kpi__top">
        <span className="kpi__ic">
          <Icon name={icon} />
        </span>
        <span className="kpi__label">{label}</span>
        {hint ? (
          <Tooltip content={hint}>
            {(trigger) => (
              <button type="button" className="kpi__hint" aria-label={t('kpi.hint', { label })} {...trigger}>
                <Icon name="info" />
              </button>
            )}
          </Tooltip>
        ) : null}
      </div>
      <div className={cx('kpi__value', negative && 'kpi__value--neg')}>
        {value}
        {unit ? <small>{unit}</small> : null}
      </div>
      {delta ? <div className={cx('kpi__delta', deltaDown && 'kpi__delta--down')}>{delta}</div> : null}
    </div>
  );
}

export function KpiGrid({ children }: { children: ReactNode }) {
  return <section className="kpis">{children}</section>;
}
