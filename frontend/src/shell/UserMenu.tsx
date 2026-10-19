import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { allowedAdminPages } from '../admin/access';
import type { MeOut } from '../api/types';
import { useLogout } from '../auth/api';
import { t } from '../i18n';
import { navigate } from '../router/store';
import { Icon, type IconName } from '../ui/icons';

interface MenuAction {
  id: string;
  label: string;
  icon: IconName;
  run(): void;
}

function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

/** WAI-ARIA menu button: Enter/Space/↓ ochadi, ↑↓ Home End, Esc/Tab yopadi. */
export function UserMenu({ me }: { me: MeOut }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const logout = useLogout();
  const admin = allowedAdminPages(me.permissions);

  const actions: MenuAction[] = [
    { id: 'sessions', label: t('user.sessions'), icon: 'history', run: () => navigate({ kind: 'sessions' }) },
    { id: 'password', label: t('user.password'), icon: 'key', run: () => navigate({ kind: 'password' }) },
    ...(admin[0] ? [{ id: 'admin', label: t('user.admin'), icon: 'shield' as const, run: () => navigate({ kind: 'admin', page: admin[0]?.id ?? null }) }] : []),
    { id: 'logout', label: t('user.logout'), icon: 'logout', run: () => logout.mutate() },
  ];

  const items = () => Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  useEffect(() => {
    if (!open) return undefined;
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !buttonRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    return () => document.removeEventListener('mousedown', onPointer);
  }, [open]);

  const close = (focusButton: boolean) => {
    setOpen(false);
    if (focusButton) buttonRef.current?.focus();
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const list = items();
    const index = list.indexOf(document.activeElement as HTMLElement);
    if (event.key === 'ArrowDown') list[(index + 1) % list.length]?.focus();
    else if (event.key === 'ArrowUp') list[(index - 1 + list.length) % list.length]?.focus();
    else if (event.key === 'Home') list[0]?.focus();
    else if (event.key === 'End') list[list.length - 1]?.focus();
    else if (event.key === 'Escape') close(true);
    else if (event.key === 'Tab') close(false);
    else return;
    if (event.key !== 'Tab') event.preventDefault();
  };

  return (
    <div className="usermenu">
      <button
        ref={buttonRef}
        type="button"
        className="tool usermenu__btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={t('user.menu', { name: me.full_name })}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className="avatar" aria-hidden="true">
          {initials(me.full_name)}
        </span>
        <span className="usermenu__name" aria-hidden="true">
          {me.full_name}
        </span>
        <Icon name="chevronDown" />
      </button>
      {open ? (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          tabIndex={-1}
          aria-label={me.full_name}
          className="usermenu__list"
          onKeyDown={onMenuKeyDown}
        >
          <div className="usermenu__head" aria-hidden="true">
            <b>{me.full_name}</b>
            <span>{me.username}</span>
          </div>
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              role="menuitem"
              tabIndex={-1}
              className="usermenu__item"
              onClick={() => {
                close(false);
                action.run();
              }}
            >
              <Icon name={action.icon} />
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
