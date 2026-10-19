import type { MenuOut, MenuPageOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import type { IconName } from '../ui/icons';

/** Backend Section enum'i (TZ 5). Ikonkalar va tavsiflar — prototip SECT jadvalidan. */
export const SECTION_IDS = ['obzor', 'kazna', 'kredity', 'finmodel', 'zakupki', 'sklad', 'proizvodstvo', 'investicii', 'kadry'] as const;

interface SectionMeta {
  icon: IconName;
  titleKey: MessageKey;
  descKey: MessageKey;
}

const SECTION_META: Record<string, SectionMeta> = {
  obzor: { icon: 'grid', titleKey: 'section.obzor.title', descKey: 'section.obzor.desc' },
  kazna: { icon: 'bank', titleKey: 'section.kazna.title', descKey: 'section.kazna.desc' },
  kredity: { icon: 'card', titleKey: 'section.kredity.title', descKey: 'section.kredity.desc' },
  finmodel: { icon: 'net', titleKey: 'section.finmodel.title', descKey: 'section.finmodel.desc' },
  zakupki: { icon: 'cart', titleKey: 'section.zakupki.title', descKey: 'section.zakupki.desc' },
  sklad: { icon: 'box', titleKey: 'section.sklad.title', descKey: 'section.sklad.desc' },
  proizvodstvo: { icon: 'bolt', titleKey: 'section.proizvodstvo.title', descKey: 'section.proizvodstvo.desc' },
  investicii: { icon: 'target', titleKey: 'section.investicii.title', descKey: 'section.investicii.desc' },
  kadry: { icon: 'people', titleKey: 'section.kadry.title', descKey: 'section.kadry.desc' },
};

const PAGE_ICONS: Record<string, IconName> = {
  svod: 'grid',
  vnimanie: 'alert',
  postup: 'in',
  rasxod: 'out',
  excel: 'table',
  platezhi: 'pct',
  calendar: 'cal',
  dogovory: 'doc',
  celevye: 'target',
  reestr: 'list',
  grafik: 'cal',
  dohody: 'coins',
  dolg: 'card',
  scenarii: 'alert',
  loty: 'list',
  postavshiki: 'doc',
  ekonomiya: 'pct',
  ostatki: 'list',
  minimum: 'alert',
  nelikvid: 'clock',
  stancii: 'factory',
  realiz: 'coins',
  obekty: 'list',
  istochniki: 'coins',
  riski: 'alert',
  chislennost: 'list',
  fot: 'coins',
  dvizhenie: 'net',
};

/** «Требует внимания» — chap menyuda hisoblagich joyi. */
export const ATTENTION_PAGE = 'vnimanie';

export function isKnownSection(id: string): boolean {
  return Object.hasOwn(SECTION_META, id);
}

export function sectionIcon(id: string): IconName {
  return isKnownSection(id) ? SECTION_META[id].icon : 'grid';
}

export function sectionTitle(id: string): string {
  return isKnownSection(id) ? t(SECTION_META[id].titleKey) : id;
}

export function sectionDesc(id: string): string {
  return isKnownSection(id) ? t(SECTION_META[id].descKey) : '';
}

export function pageIcon(id: string): IconName {
  return Object.hasOwn(PAGE_ICONS, id) ? PAGE_ICONS[id] : 'list';
}

export interface FlatSection {
  id: string;
  title: string;
  group: string | null;
  pages: MenuPageOut[];
}

export function flattenMenu(menu: MenuOut): FlatSection[] {
  return menu.groups.flatMap((group) =>
    group.sections.map((section) => ({ id: section.id, title: section.title, group: group.title ?? null, pages: section.pages })),
  );
}
