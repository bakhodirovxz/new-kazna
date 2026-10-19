import { Component, type ReactNode } from 'react';
import { t } from '../i18n';
import { ErrorBanner } from '../ui/ErrorBanner';

/** Lazy sahifa chunk'i yuklanmasa (eski hash, tarmoq) butun ilova emas, faqat sahifa o'rni xato ko'rsatadi. */
export class PageBoundary extends Component<{ children: ReactNode; onRetry?(): void }, { error: unknown }> {
  override state = { error: null as unknown };

  static getDerivedStateFromError(error: unknown) {
    return { error: error ?? new Error('page failed') };
  }

  override render() {
    if (this.state.error === null) return this.props.children;
    return <ErrorBanner error={this.state.error} title={t('section.loadFailed')} onRetry={() => {
          this.props.onRetry?.();
          this.setState({ error: null });
        }} />;
  }
}
