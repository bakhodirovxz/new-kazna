import { useEffect, useMemo, useRef } from 'react';
import type { MenuOut } from '../api/types';
import type { Route } from '../router/hash';
import { navigate } from '../router/store';
import { flattenMenu } from '../shell/sectionMeta';
import { stopScreen, useScreenState } from './store';

/** TZ 6: Обзор → Казначейство → Производство → Инвестиции → Финмодель → Склад, har 60 soniyada. */
export const WALL_ROUTE = ['obzor', 'kazna', 'proizvodstvo', 'investicii', 'finmodel', 'sklad'] as const;
export const ROTATE_MS = 60_000;

export function wallSections(menu: MenuOut): string[] {
  const allowed = new Set(flattenMenu(menu).map((s) => s.id));
  return WALL_ROUTE.filter((id) => allowed.has(id));
}

export function useScreenRotation(menu: MenuOut, route: Route): string[] {
  const { active } = useScreenState();
  const sections = useMemo(() => wallSections(menu), [menu]);
  const routeRef = useRef(route);
  routeRef.current = route;

  useEffect(() => {
    if (!active || sections.length === 0) return undefined;
    let index = 0;
    const show = () => {
      const current = routeRef.current;
      navigate({
        kind: 'section',
        section: sections[index % sections.length] ?? 'obzor',
        page: 'svod',
        br: current.kind === 'section' ? current.br : null,
        per: current.kind === 'section' ? current.per : null,
      });
    };
    show();
    const timer = window.setInterval(() => {
      index += 1;
      show();
    }, ROTATE_MS);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') stopScreen();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('keydown', onKey);
    };
  }, [active, sections]);

  return sections;
}
