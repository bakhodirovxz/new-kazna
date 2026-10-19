import { useEffect } from 'react';
import type { MenuOut } from '../api/types';
import { navigate } from '../router/store';
import { flattenMenu } from './sectionMeta';
import { ShellSkeleton } from './ShellSkeleton';

/** `#` → rolga ruxsat etilgan birinchi bo'limning birinchi sahifasi. */
export function HomeRedirect({ menu }: { menu: MenuOut }) {
  useEffect(() => {
    const first = flattenMenu(menu)[0];
    if (first) {
      navigate({ kind: 'section', section: first.id, page: first.pages[0]?.id ?? null, br: null, per: null }, { replace: true });
    } else {
      navigate({ kind: 'noaccess' }, { replace: true });
    }
  }, [menu]);
  return <ShellSkeleton />;
}
