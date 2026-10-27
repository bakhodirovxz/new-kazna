import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { MeOut } from '../api/types';
import type { AdminPageId } from './access';

export interface AdminPageProps {
  me: MeOut;
}

export type AdminPageComponent = LazyExoticComponent<ComponentType<AdminPageProps>>;

/** Har admin sahifasi alohida chunk. Sahifa hali yo'q bo'lsa AdminScreen «Раздел в разработке» ko'rsatadi. */
export const ADMIN_COMPONENTS: Partial<Record<AdminPageId, AdminPageComponent>> = {
  users: lazy(() => import('./UsersPage')),
  etl: lazy(() => import('./EtlPage')),
  builds: lazy(() => import('./BuildsPage')),
  audit: lazy(() => import('./AuditPage')),
  aijournal: lazy(() => import('./AiJournalPage')),
  keys: lazy(() => import('./KeysPage')),
  roles: lazy(() => import('./RolesPage')),
  alerts: lazy(() => import('./AlertRulesPage')),
  finmodel: lazy(() => import('./FinAssumptionsPage')),
  settings: lazy(() => import('./SettingsPage')),
  security: lazy(() => import('./SecurityPage')),
  integrations: lazy(() => import('./IntegrationsPage')),
};
