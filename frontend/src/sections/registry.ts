import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { FilterState } from '../shell/useFilters';

/** Bo'lim sahifasi: src/sections/<bo'lim>/<sahifa>.tsx, default eksport. Reyestrni tahrirlash shart emas. */
export interface SectionPageProps {
  section: string;
  page: string;
  filters: FilterState;
}

export interface SectionPageModule {
  default: ComponentType<SectionPageProps>;
}

export type SectionPageLoader = () => Promise<SectionPageModule>;
export type SectionPageComponent = LazyExoticComponent<ComponentType<SectionPageProps>>;

export function createRegistry(modules: Record<string, SectionPageLoader>) {
  const cache = new Map<string, SectionPageComponent>();
  function resolve(section: string, page: string): SectionPageComponent | null {
    const key = `./${section}/${page}.tsx`;
    if (!Object.hasOwn(modules, key)) return null;
    const loader = modules[key];
    let component = cache.get(key);
    if (!component) {
      component = lazy(loader);
      cache.set(key, component);
    }
    return component;
  }
  /** «Повторить»: rad etilgan chunk keshda qolmasin, keyingi resolve qayta import qiladi. */
  resolve.reset = (section: string, page: string) => cache.delete(`./${section}/${page}.tsx`);
  return resolve;
}

export const resolveSectionPage = createRegistry(
  import.meta.glob<SectionPageModule>(['./*/*.tsx', '!./*/*.test.tsx']),
);
