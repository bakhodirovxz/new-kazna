import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { FilterState } from '../shell/useFilters';

/** Bo'lim sahifasi: src/sections/<bo'lim>/<sahifa>.tsx, default eksport. Reyestrni tahrirlash shart emas. */
export interface SectionPageProps {
  section: string;
  page: string;
  filters: FilterState;
  /** TZ 6: filial qatori bosilganda filtrni o'zgartirish (qulflangan foydalanuvchida — o'zgarmaydi). */
  onBranch(br: number | null): void;
}

export interface SectionPageModule {
  default: ComponentType<SectionPageProps>;
}

export type SectionPageLoader = () => Promise<SectionPageModule>;
export type SectionPageComponent = LazyExoticComponent<ComponentType<SectionPageProps>>;

export function createRegistry(modules: Record<string, SectionPageLoader>) {
  const cache = new Map<string, SectionPageComponent>();
  /** Sahifa fayli yo'q bo'lsa, bo'lim darajasidagi `_page.tsx` zaxirasi («Ввод данных»: obyekt sahifalari). */
  function keyFor(section: string, page: string): string | null {
    const key = `./${section}/${page}.tsx`;
    if (Object.hasOwn(modules, key)) return key;
    const fallback = `./${section}/_page.tsx`;
    return Object.hasOwn(modules, fallback) ? fallback : null;
  }
  function resolve(section: string, page: string): SectionPageComponent | null {
    const key = keyFor(section, page);
    if (key === null) return null;
    const loader = modules[key];
    let component = cache.get(key);
    if (!component) {
      component = lazy(loader);
      cache.set(key, component);
    }
    return component;
  }
  /** «Повторить»: rad etilgan chunk keshda qolmasin, keyingi resolve qayta import qiladi. */
  resolve.reset = (section: string, page: string) => {
    const key = keyFor(section, page);
    if (key !== null) cache.delete(key);
  };
  return resolve;
}

export const resolveSectionPage = createRegistry(
  import.meta.glob<SectionPageModule>(['./*/*.tsx', '!./*/*.test.tsx']),
);
