import type { ReactNode } from 'react';
import { Icon, type IconName } from './icons';
import './display.css';

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  text?: string;
  action?: ReactNode;
}

export function EmptyState({ icon = 'info', title, text, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="empty-state__ic">
        <Icon name={icon} />
      </span>
      <h2>{title}</h2>
      {text ? <p>{text}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}
