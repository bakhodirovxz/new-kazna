import { t } from '../i18n';
import { ErrorBanner } from '../ui/ErrorBanner';
import '../auth/auth.css';

export function FullPageError({ error, onRetry }: { error: unknown; onRetry(): void }) {
  return (
    <div className="auth">
      <main className="auth__card auth__card--wide">
        <ErrorBanner error={error} title={t('app.loadFailed')} onRetry={onRetry} />
      </main>
    </div>
  );
}
