import { useState } from 'react';
import type { MenuOut } from '../api/types';
import { t } from '../i18n';
import type { Route } from '../router/hash';
import { Icon } from '../ui/icons';
import { AiDrawer } from './AiDrawer';
import { useAiStatus } from './api';

/** TZ 6/7: yuqori panel tugmasi — faqat bo'lim sahifasida va funksiya yoqilgan bo'lsa (standart — yo'q). */
export function AiButton({ menu, route }: { menu: MenuOut; route: Route }) {
  const status = useAiStatus(route.kind === 'section');
  const [open, setOpen] = useState(false);
  if (route.kind !== 'section' || !status.data?.enabled) return null;
  return (
    <>
      <button type="button" className="tool" title={t('ai.buttonTitle')} onClick={() => setOpen(true)}>
        <Icon name="spark" />
        <span className="tool__label">{t('ai.button')}</span>
      </button>
      {open ? <AiDrawer menu={menu} route={route} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
