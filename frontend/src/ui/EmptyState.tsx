import type { ReactNode } from 'react';
import { Icon, type IconName } from './icons';
import './display.css';

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  text?: string;
  action?: ReactNode;
  /** Sarlavhali Card ichida sarlavha darajasi buzilmasin (Plan 3 carry). */
  headingLevel?: 2 | 3 | 4;
}

export function EmptyState({ icon = 'info', title, text, action, headingLevel = 2 }: EmptyStateProps) {
  const Heading = `h${headingLevel}` as const;
  return (
    <div className="empty-state">
      <span className="empty-state__ic">
        <Icon name={icon} />
      </span>
      <Heading>{title}</Heading>
      {text ? <p>{text}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}
