import { Suspense, useEffect, useMemo, type ReactNode } from 'react';
import type { MeOut, MenuOut } from '../api/types';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import type { SectionRoute } from '../router/hash';
import { navigate } from '../router/store';
import { resolveSectionPage, type SectionPageProps } from '../sections/registry';
import { SectionPlaceholder } from '../sections/SectionPlaceholder';
import { ErrorBanner } from '../ui/ErrorBanner';
import { PageSkeleton } from '../ui/Skeleton';
import { AppFrame } from './AppFrame';
import { activeFilterCount, FilterChips } from './FilterChips';
import { FilterControls } from './FilterControls';
import { PageBoundary } from './PageBoundary';
import { PageHeader } from './PageHeader';
import { flattenMenu, isKnownSection, pageIcon, sectionDesc, sectionIcon } from './sectionMeta';
import type { SideModel } from './SideMenu';
import { StatusScreen } from './StatusScreen';
import { useFilters } from './useFilters';

export interface SectionScreenProps {
  me: MeOut;
  menu: MenuOut;
  route: SectionRoute;
  tools?: ReactNode;
}

/** Har renderda reyestrdan oladi: boundary reset'idan keyin yangi lazy komponent ishlatiladi. */
function PageView(props: SectionPageProps) {
  const Page = resolveSectionPage(props.section, props.page);
  return Page ? <Page {...props} /> : null;
}

export function SectionScreen({ me, menu, route, tools }: SectionScreenProps) {
  const sections = useMemo(() => flattenMenu(menu), [menu]);
  const section = sections.find((s) => s.id === route.section);
  const page = section ? (section.pages.find((p) => p.id === route.page) ?? section.pages[0]) : undefined;
  const filters = useFilters(route, me);

  useEffect(() => {
    if (section && page && route.page !== page.id) navigate({ ...route, page: page.id }, { replace: true });
  }, [section, page, route]);

  useDocumentTitle(section && page ? `${page.title} | ${section.title}` : null);

  if (!section || !page) {
    return <StatusScreen kind={isKnownSection(route.section) ? 'noaccess' : 'notfound'} menu={menu} tools={tools} />;
  }

  const title = page.id === 'svod' ? t('shell.svodTitle', { section: section.title }) : page.title;
  const side: SideModel = {
    title: section.title,
    desc: sectionDesc(section.id),
    icon: sectionIcon(section.id),
    activeId: page.id,
    items: section.pages.map((p) => ({ id: p.id, label: p.title, icon: pageIcon(p.id), href: filters.hrefFor(section.id, p.id) })),
  };
  const hasPage = resolveSectionPage(section.id, page.id) !== null;
  const navQuery = { br: filters.state.br, per: filters.state.per === filters.defaultPeriod ? null : filters.state.per };

  return (
    <AppFrame menu={menu} activeSection={section.id} side={side} navQuery={navQuery} tools={tools}>
      <PageHeader
        crumb={section.title}
        title={title}
        sub={filters.ready ? `${filters.branchLabel}, ${filters.periodLabel.toLowerCase()}` : undefined}
        filters={<FilterControls filters={filters} />}
        filterCount={activeFilterCount(filters)}
      />
      <FilterChips filters={filters} />
      <div id="view" className="view">
        {filters.error && !filters.ready ? (
          <ErrorBanner error={filters.error} title={t('filters.loadFailed')} onRetry={filters.retry} />
        ) : !filters.ready ? (
          <PageSkeleton />
        ) : hasPage ? (
          <PageBoundary onRetry={() => resolveSectionPage.reset(section.id, page.id)}>
            <Suspense fallback={<PageSkeleton />}>
              <PageView section={section.id} page={page.id} filters={filters.state} />
            </Suspense>
          </PageBoundary>
        ) : (
          <SectionPlaceholder title={page.title} />
        )}
      </div>
    </AppFrame>
  );
}
