import { Fragment, useEffect, useRef } from 'react';
import type { MenuOut } from '../api/types';
import { t } from '../i18n';
import { buildHash } from '../router/hash';
import { Icon } from '../ui/icons';
import { sectionIcon } from './sectionMeta';

export interface NavQuery {
  br: number | null;
  per: string | null;
}

/** TZ 6: 9 bo'lim guruhlar bilan (Обзор · Финансы · Обеспечение · Производство · Персонал), filtrlar saqlanadi. */
export function SectionNav({ menu, activeSection, navQuery }: { menu: MenuOut; activeSection: string | null; navQuery?: NavQuery }) {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [activeSection]);

  return (
    <nav className="sections-nav" aria-label={t('shell.sections')}>
      <ul ref={listRef} className="sections">
        {menu.groups.map((group, index) => (
          <Fragment key={group.title ?? `group-${index}`}>
            {index > 0 ? <li className="sep" aria-hidden="true" /> : null}
            {group.sections.map((section) => (
              <li key={section.id}>
                <a
                  className="sec"
                  href={buildHash({
                    kind: 'section',
                    section: section.id,
                    page: section.pages[0]?.id ?? null,
                    br: navQuery?.br ?? null,
                    per: navQuery?.per ?? null,
                  })}
                  aria-current={section.id === activeSection ? 'page' : undefined}
                >
                  <Icon name={sectionIcon(section.id)} />
                  <span>{section.title}</span>
                </a>
              </li>
            ))}
          </Fragment>
        ))}
      </ul>
    </nav>
  );
}
