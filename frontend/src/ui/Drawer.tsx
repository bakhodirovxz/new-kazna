import { useId, type ReactNode } from 'react';
import { t } from '../i18n';
import { IconButton } from './Button';
import { Overlay } from './Overlay';

export interface DrawerProps {
  open: boolean;
  onClose(): void;
  title: string;
  children: ReactNode;
}

export function Drawer({ open, onClose, title, children }: DrawerProps) {
  const titleId = useId();
  return (
    <Overlay open={open} onClose={onClose} variant="drawer" labelledBy={titleId}>
      <header className="dh">
        <h2 id={titleId}>{title}</h2>
        <IconButton icon="close" label={t('overlay.close')} variant="ghost" onClick={onClose} />
      </header>
      <div className="db db--flush">{children}</div>
    </Overlay>
  );
}
