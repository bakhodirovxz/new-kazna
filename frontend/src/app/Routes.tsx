import { LoginPage } from '../auth/LoginPage';
import { MfaEnrollPage } from '../auth/MfaEnrollPage';
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
    case 'mfaEnroll':
      return <MfaEnrollPage />;
    default:
      return <RequireAuth route={route} />;
  }
}
