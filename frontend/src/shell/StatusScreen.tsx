import type { ReactNode } from 'react';
import type { MenuOut } from '../api/types';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { navigate } from '../router/store';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { AppFrame } from './AppFrame';

export function StatusScreen({ kind, menu, tools }: { kind: 'noaccess' | 'notfound'; menu: MenuOut; tools?: ReactNode }) {
  const title = kind === 'noaccess' ? t('status.noaccess.title') : t('status.notfound.title');
  useDocumentTitle(title);
  return (
    <AppFrame menu={menu} activeSection={null} side={null} tools={tools}>
      <Card>
        <EmptyState
          icon={kind === 'noaccess' ? 'lock' : 'search'}
          title={title}
          text={kind === 'noaccess' ? t('status.noaccess.text') : t('status.notfound.text')}
          action={
            <Button variant="secondary" onClick={() => navigate({ kind: 'home' })}>
              {t('status.home')}
            </Button>
          }
        />
      </Card>
    </AppFrame>
  );
}
