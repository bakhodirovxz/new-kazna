import { Component, type ReactNode } from 'react';
import { FullPageError } from './FullPageError';

/** Render istisnosi oq ekranga aylanmasin: butun ilova xatosi — to'liq sahifa xabari + qayta yuklash. */
export class RootBoundary extends Component<{ children: ReactNode }, { error: unknown }> {
  override state = { error: null as unknown };

  static getDerivedStateFromError(error: unknown) {
    return { error: error ?? new Error('app failed') };
  }

  override render() {
    if (this.state.error === null) return this.props.children;
    return <FullPageError error={this.state.error} onRetry={() => window.location.reload()} />;
  }
}
