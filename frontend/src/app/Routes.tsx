import { LoginPage } from '../auth/LoginPage';
import { MfaVerifyPage } from '../auth/MfaVerifyPage';
import { useRoute } from '../router/store';
import { RequireAuth } from './RequireAuth';

export function Routes() {
  const route = useRoute();
  switch (route.kind) {
    case 'login':
      return <LoginPage next={route.next} />;
    case 'mfa':
      return <MfaVerifyPage />;
    default:
      return <RequireAuth route={route} />;
  }
}
