import { allowedAdminPages } from '../admin/access';
import type { BranchOut, MenuOut, PeriodOut } from '../api/types';
import { t } from '../i18n';
import type { Route, SectionRoute } from '../router/hash';
import { flattenMenu } from './sectionMeta';

export type PaletteKind = 'section' | 'admin' | 'account' | 'branch' | 'period';

export interface PaletteItem {
  id: string;
  label: string;
  kind: PaletteKind;
  kindLabel: string;
  target: Route;
}

export interface PaletteInput {
  menu: MenuOut;
  permissions: readonly string[];
  branches: readonly BranchOut[];
  periods: readonly PeriodOut[];
  defaultPeriod: string;
  locked: boolean;
  route: Route;
}

/** TZ 6 «Быстрый переход»: bo'limlar, sahifalar, filiallar va davrlar (+ admin/akkaunt). */
export function buildPaletteItems(input: PaletteInput): PaletteItem[] {
  const sections = flattenMenu(input.menu);
  const current: SectionRoute | null = input.route.kind === 'section' ? input.route : null;
  const first = sections[0];
  const base: SectionRoute | null =
    current ?? (first ? { kind: 'section', section: first.id, page: first.pages[0]?.id ?? null, br: null, per: null } : null);
  const items: PaletteItem[] = [];

  for (const section of sections) {
    for (const page of section.pages) {
      items.push({
        id: `page:${section.id}/${page.id}`,
        label: `${section.title}: ${page.title}`,
        kind: 'section',
        kindLabel: t('palette.kind.section'),
        target: { kind: 'section', section: section.id, page: page.id, br: current?.br ?? null, per: current?.per ?? null },
      });
    }
  }
  for (const page of allowedAdminPages(input.permissions)) {
    items.push({
      id: `admin:${page.id}`,
      label: `${t('admin.title')}: ${t(page.titleKey)}`,
      kind: 'admin',
      kindLabel: t('palette.kind.admin'),
      target: { kind: 'admin', page: page.id },
    });
  }
  items.push(
    { id: 'account:sessions', label: t('user.sessions'), kind: 'account', kindLabel: t('palette.kind.account'), target: { kind: 'sessions' } },
    { id: 'account:password', label: t('user.password'), kind: 'account', kindLabel: t('palette.kind.account'), target: { kind: 'password' } },
  );
  if (base) {
    if (!input.locked) {
      items.push({ id: 'branch:all', label: t('filters.allBranches'), kind: 'branch', kindLabel: t('palette.kind.branch'), target: { ...base, br: null } });
      for (const branch of input.branches) {
        items.push({ id: `branch:${branch.id}`, label: branch.name, kind: 'branch', kindLabel: t('palette.kind.branch'), target: { ...base, br: branch.id } });
      }
    }
    for (const period of input.periods) {
      items.push({
        id: `period:${period.code}`,
        label: period.label,
        kind: 'period',
        kindLabel: t('palette.kind.period'),
        target: { ...base, per: period.code === input.defaultPeriod ? null : period.code },
      });
    }
  }
  return items;
}

function normalize(value: string): string {
  return value.toLocaleLowerCase('ru').replace(/ё/g, 'е').trim();
}

export function filterPalette(items: readonly PaletteItem[], query: string, limit = 50): PaletteItem[] {
  const q = normalize(query);
  const found = q ? items.filter((item) => normalize(item.label).includes(q)) : items;
  return found.slice(0, limit);
}
