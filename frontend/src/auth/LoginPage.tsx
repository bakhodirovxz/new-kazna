import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { navigate } from '../router/store';
import { Button } from '../ui/Button';
import { PasswordInput, TextInput } from '../ui/Field';
import { meKey, useLogin } from './api';
import { AuthAlert, AuthLayout } from './AuthLayout';
import { useAuthFlow } from './AuthFlow';
import { destinationAfterSignIn } from './destination';
import { authErrorText } from './errors';

export function LoginPage({ next }: { next: string | null }) {
  const login = useLogin();
  const client = useQueryClient();
  const flow = useAuthFlow();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const userRef = useRef<HTMLInputElement>(null);
  const passRef = useRef<HTMLInputElement>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  useDocumentTitle(t('login.docTitle'));
  useEffect(() => userRef.current?.focus(), []); // masalan, sessiya tugab yo'naltirilganda

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const name = username.trim();
    const found: { username?: string; password?: string } = {};
    if (!name) found.username = t('login.required.username');
    if (!password) found.password = t('login.required.password');
    setErrors(found);
    setServerError(null);
    if (found.username || found.password) {
      (found.username ? userRef : passRef).current?.focus();
      return;
    }
    login.mutate(
      { username: name, password },
      {
        onSuccess: (result) => {
          login.reset(); // parol/token kuzatuvchida qolmasin
          setPassword('');
          if (result.next === 'done' && result.user) {
            // 2FA majburiy emas va ulanmagan: sessiya allaqachon ochiq (cookie), 2FA bosqichi yo'q.
            client.clear(); // oldingi foydalanuvchi keshi yangisiga o'tmasin
            client.setQueryData(meKey, result.user);
            navigate(destinationAfterSignIn(result.user, next), { replace: true });
            return;
          }
          if (!result.mfa_token || result.next === 'done') return;
          flow.begin({ mfaToken: result.mfa_token, step: result.next, username: name, returnTo: next });
          navigate({ kind: result.next === 'mfa_enroll' ? 'mfaEnroll' : 'mfa' });
        },
        onError: (err) => {
          setServerError(authErrorText(err));
          setPassword('');
          login.reset(); // parol kuzatuvchi/MutationCache'da qolmasin
          passRef.current?.focus();
        },
      },
    );
  };

  return (
    <AuthLayout>
      <h1>{t('login.title')}</h1>
      <p className="auth__lead">{t('login.lead')}</p>
      <form className="auth__form" noValidate onSubmit={onSubmit}>
        {serverError ? <AuthAlert message={serverError} /> : null}
        <TextInput
          label={t('login.username')}
          name="username"
          ref={userRef}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={username}
          error={errors.username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <PasswordInput
          label={t('login.password')}
          name="password"
          ref={passRef}
          autoComplete="current-password"
          value={password}
          error={errors.password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" block loading={login.isPending}>
          {t('login.submit')}
        </Button>
      </form>
      <p className="auth__note">{t('login.forgot')}</p>
    </AuthLayout>
  );
}
