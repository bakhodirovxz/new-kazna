import { useId, type ReactNode, type RefObject } from 'react';
import { t } from '../i18n';
import { IconButton } from './Button';
import { Overlay } from './Overlay';

export interface ModalProps {
  open: boolean;
  onClose(): void;
  title: string;
  note?: string;
  footer?: ReactNode;
  size?: 'md' | 'sm';
  initialFocusRef?: RefObject<HTMLElement>;
  role?: 'dialog' | 'alertdialog';
  describedBy?: string;
  /** false: Esc, fon va X yopmaydi (X o'chiriladi). */
  dismissible?: boolean;
  children: ReactNode;
}

export function Modal({ open, onClose, title, note, footer, size = 'md', initialFocusRef, role, describedBy, dismissible = true, children }: ModalProps) {
  const titleId = useId();
  return (
    <Overlay
      open={open}
      onClose={onClose}
      variant="modal"
      labelledBy={titleId}
      initialFocusRef={initialFocusRef}
      role={role}
      describedBy={describedBy}
      dismissible={dismissible}
      className={size === 'sm' ? 'modal--sm' : undefined}
    >
      <header className="dh">
        <div>
          {note ? <p className="note">{note}</p> : null}
          <h2 id={titleId}>{title}</h2>
        </div>
        <IconButton icon="close" label={t('overlay.close')} variant="ghost" onClick={onClose} disabled={!dismissible} />
      </header>
      <div className="db">{children}</div>
      {footer ? <footer className="df">{footer}</footer> : null}
    </Overlay>
  );
}
