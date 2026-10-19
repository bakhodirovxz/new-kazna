import { useState, type ReactNode } from 'react';
import { t } from '../i18n';
import { BottomSheet } from '../ui/BottomSheet';
import { Button } from '../ui/Button';
import { useFrame } from './FrameContext';

export interface PageHeaderProps {
  crumb: string;
  title: string;
  sub?: string;
  filters?: ReactNode;
  filterCount?: number;
}

export function PageHeader({ crumb, title, sub, filters, filterCount = 0 }: PageHeaderProps) {
  const frame = useFrame();
  const [sheetOpen, setSheetOpen] = useState(false);
  const showMenuButton = frame.hasSide && (frame.isMobile || frame.isTablet);
  return (
    <div className="head">
      <div className="head__titles">
        {showMenuButton ? (
          <Button
            variant="secondary"
            icon="panel"
            className="head__menu"
            aria-expanded={frame.isMobile ? undefined : frame.sideVisible}
            aria-controls={frame.isMobile ? undefined : 'side'}
            onClick={frame.toggleSide}
          >
            {t('shell.sectionMenu')}
          </Button>
        ) : null}
        <div className="crumb">{crumb}</div>
        <h1>{title}</h1>
        {sub ? <p>{sub}</p> : null}
      </div>
      {filters && frame.isMobile ? (
        <>
          <Button variant="secondary" icon="filter" onClick={() => setSheetOpen(true)}>
            {filterCount > 0 ? `${t('filters.open')} (${filterCount})` : t('filters.open')}
          </Button>
          <BottomSheet
            open={sheetOpen}
            onClose={() => setSheetOpen(false)}
            title={t('filters.title')}
            footer={
              <Button block onClick={() => setSheetOpen(false)}>
                {t('filters.done')}
              </Button>
            }
          >
            <div className="filters filters--sheet">{filters}</div>
          </BottomSheet>
        </>
      ) : null}
      {filters && !frame.isMobile ? <div className="filters">{filters}</div> : null}
    </div>
  );
}
