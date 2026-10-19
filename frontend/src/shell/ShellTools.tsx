import { useCallback, useEffect, useMemo, useState } from 'react';
import type { MeOut, MenuOut } from '../api/types';
import { t } from '../i18n';
import type { Route } from '../router/hash';
import { navigate } from '../router/store';
import { Icon } from '../ui/icons';
import { useToast } from '../ui/Toast';
import { CommandPalette } from './CommandPalette';
import { Freshness } from './Freshness';
import { flattenMenu } from './sectionMeta';
import { UserMenu } from './UserMenu';
import { useSectionHotkeys } from './useSectionHotkeys';

export interface ShellToolsProps {
  me: MeOut;
  menu: MenuOut;
  route: Route;
}

/** Clipboard API bo'lmasa (http, ruxsat yo'q): vaqtinchalik textarea + execCommand. */
async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.className = 'sr-copy';
    document.body.appendChild(area);
    area.select();
    try {
      return document.execCommand('copy');
    } catch {
      return false;
    } finally {
      area.remove();
      previous?.focus();
    }
  }
}

export function ShellTools({ me, menu, route }: ShellToolsProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [copy, setCopy] = useState<'idle' | 'ok' | 'fail'>('idle');
  const toast = useToast();
  const sections = useMemo(() => flattenMenu(menu), [menu]);
  const ids = useMemo(() => sections.map((s) => s.id), [sections]);
  const activeSection = route.kind === 'section' ? route.section : null;

  const goSection = useCallback(
    (id: string) => {
      const target = sections.find((s) => s.id === id);
      if (!target) return;
      const fromNav = document.activeElement instanceof HTMLElement && document.activeElement.closest('.sections') !== null;
      navigate({
        kind: 'section',
        section: id,
        page: target.pages[0]?.id ?? null,
        br: route.kind === 'section' ? route.br : null,
        per: route.kind === 'section' ? route.per : null,
      });
      if (fromNav) {
        window.requestAnimationFrame(() => document.querySelector<HTMLElement>('.sections [aria-current="page"]')?.focus());
      }
    },
    [sections, route],
  );

  useSectionHotkeys(ids, activeSection, goSection, route.kind === 'section');

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
      // RU maketda key = 'л', shuning uchun fizik tugma (code) ham tekshiriladi.
      if (event.code !== 'KeyK' && event.key.toLowerCase() !== 'k') return;
      // Parol / OTP maydonida palitra ochilmaydi.
      const target = event.target;
      if (target instanceof HTMLInputElement && (target.type === 'password' || target.autocomplete === 'one-time-code')) return;
      event.preventDefault();
      setPaletteOpen(true);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (copy === 'idle') return undefined;
    const timer = window.setTimeout(() => setCopy('idle'), 1500);
    return () => window.clearTimeout(timer);
  }, [copy]);

  const copyLink = async () => {
    const ok = await writeClipboard(window.location.href);
    setCopy(ok ? 'ok' : 'fail');
    if (!ok) toast.show(t('common.copyFailed'), 'error');
  };

  const linkLabel = copy === 'ok' ? t('common.copied') : copy === 'fail' ? t('common.copyFailed') : t('tools.link');

  return (
    <>
      <button type="button" className="tool" title={t('tools.searchTitle')} aria-keyshortcuts="Control+K Meta+K" onClick={() => setPaletteOpen(true)}>
        <Icon name="search" />
        <span className="tool__label">{t('tools.search')}</span>
      </button>
      <button type="button" className="tool" title={t('tools.linkTitle')} onClick={() => void copyLink()}>
        <Icon name="link" />
        <span className="tool__label" aria-live="polite">
          {linkLabel}
        </span>
      </button>
      <button type="button" className="tool" title={t('tools.printTitle')} onClick={() => window.print()}>
        <Icon name="print" />
        <span className="tool__label">{t('tools.print')}</span>
      </button>
      <Freshness />
      <UserMenu me={me} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} me={me} menu={menu} route={route} />
    </>
  );
}
