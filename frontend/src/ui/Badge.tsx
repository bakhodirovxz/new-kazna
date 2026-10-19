import type { ReactNode } from 'react';
import './display.css';

export type BadgeTone = 'neutral' | 'blue' | 'ok' | 'warn' | 'neg';

export function Badge({ tone = 'neutral', children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
