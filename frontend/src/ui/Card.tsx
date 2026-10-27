import { useId, type ReactNode } from 'react';
import { cx } from './cx';
import './display.css';

export interface CardProps {
  title?: string;
  sub?: string;
  /** Sarlavha qatorining o'ng tomoni (filtr, tugma). */
  actions?: ReactNode;
  /** TZ 6: kartada hover'da chiqadigan eksport tugmasi joyi (PNG/CSV — keyingi rejalar). */
  exportSlot?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Card({ title, sub, actions, exportSlot, className, children }: CardProps) {
  const titleId = useId();
  return (
    <section className={cx('card', className)} aria-labelledby={title ? titleId : undefined}>
      {title || actions || exportSlot ? (
        <div className="card__head">
          <div>
            {title ? <h2 id={titleId}>{title}</h2> : null}
            {sub ? <p className="card__sub">{sub}</p> : null}
          </div>
          {actions || exportSlot ? (
            <div className="card__actions">
              {actions}
              {exportSlot ? <div className="card__exp">{exportSlot}</div> : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}
