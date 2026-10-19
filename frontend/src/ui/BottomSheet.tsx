import { useId, type ReactNode } from 'react';
import { t } from '../i18n';
import { IconButton } from './Button';
import { Overlay } from './Overlay';

export interface BottomSheetProps {
  open: boolean;
  onClose(): void;
  title: string;
  footer?: ReactNode;
  children: ReactNode;
}

export function BottomSheet({ open, onClose, title, footer, children }: BottomSheetProps) {
  const titleId = useId();
  return (
    <Overlay open={open} onClose={onClose} variant="sheet" labelledBy={titleId}>
      <div className="sheet__grip" aria-hidden="true" />
      <header className="dh">
        <h2 id={titleId}>{title}</h2>
        <IconButton icon="close" label={t('overlay.close')} variant="ghost" onClick={onClose} />
      </header>
      <div className="db">{children}</div>
      {footer ? <footer className="df">{footer}</footer> : null}
    </Overlay>
  );
}
