import { useRef, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { MeOut } from '../api/types';
import { useDocumentTitle } from '../app/useDocumentTitle';
import { t } from '../i18n';
import { navigate } from '../router/store';
import { Button } from '../ui/Button';
import { FormError, PasswordInput } from '../ui/Field';
import { Icon } from '../ui/icons';
import { useToast } from '../ui/Toast';
import { useChangePassword, useLogout } from './api';
import { AuthLayout } from './AuthLayout';
import { useAuthFlow } from './AuthFlow';
import { destinationAfterSignIn } from './destination';
import { checkPassword, passwordProblemText } from './passwordRules';

interface Errors {
  current?: string;
  next?: string;
  repeat?: string;
}

function Rule({ id, ok, text }: { id: string; ok: boolean; text: string }) {
  return (
    <li data-rule={id} data-ok={ok}>
      <Icon name={ok ? 'check' : 'info'} />
      <span>{text}</span>
      <span className="visually-hidden">{` — ${ok ? t('password.rule.ok') : t('password.rule.notOk')}`}</span>
    </li>
  );
}

export function PasswordChangePage({ me }: { me: MeOut }) {
  const forced = me.must_change_password;
  const change = useChangePassword();
  const logout = useLogout();
  const flow = useAuthFlow();
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [problems, setProblems] = useState<string[]>([]);
  const [otherError, setOtherError] = useState<unknown>(null);
  const refs = { current: useRef<HTMLInputElement>(null), next: useRef<HTMLInputElement>(null), repeat: useRef<HTMLInputElement>(null) };
  const rules = checkPassword(next, me.username);
  useDocumentTitle(t('password.docTitle'));

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const found: Errors = {};
    if (!current) found.current = t('field.required');
    if (!rules.length || !rules.classes || !rules.noUsername) found.next = t('password.rulesNotMet');
    else if (next === current) found.next = t('password.sameAsCurrent');
    if (next !== repeat) found.repeat = t('password.mismatch');
    setErrors(found);
    setProblems([]);
    setOtherError(null);
    if (found.current || found.next || found.repeat) {
      (found.current ? refs.current : found.next ? refs.next : refs.repeat).current?.focus();
      return;
    }
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          change.reset();
          toast.show(t('password.changed'), 'success');
          const returnTo = flow.returnTo;
          flow.clear();
          navigate(destinationAfterSignIn({ ...me, must_change_password: false }, returnTo), { replace: true });
        },
        onError: (error) => {
          change.reset(); // parollar kuzatuvchida qolmasin
          if (isApiError(error, 422, 'invalid_current_password')) {
            setErrors({ current: error.message });
            refs.current.current?.focus();
          } else if (isApiError(error, 422, 'password_policy')) {
            const raw = error.params.problems;
            const list = Array.isArray(raw) ? raw.filter((p): p is string => typeof p === 'string') : [];
            setProblems(list.length > 0 ? list : ['unknown']);
            refs.next.current?.focus();
          } else {
            setOtherError(error);
          }
        },
      },
    );
  };

  return (
    <AuthLayout>
      <h1>{forced ? t('password.forcedTitle') : t('password.title')}</h1>
      <p className="auth__lead">{forced ? t('password.forcedLead') : t('password.lead')}</p>
      <form className="auth__form" noValidate onSubmit={onSubmit}>
        {problems.length > 0 ? (
          <div className="form-error" role="alert">
            <Icon name="alert" />
            <div>
              <b>{t('password.policyFailed')}</b>
              <ul className="form-error__list">
                {problems.map((code) => (
                  <li key={code}>{passwordProblemText(code)}</li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
        <FormError error={otherError} />
        <input
          type="text"
          className="visually-hidden"
          name="username"
          autoComplete="username"
          value={me.username}
          readOnly
          tabIndex={-1}
          aria-hidden="true"
        />
        <PasswordInput
          label={t('password.current')}
          ref={refs.current}
          autoComplete="current-password"
          value={current}
          error={errors.current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <PasswordInput
          label={t('password.new')}
          ref={refs.next}
          autoComplete="new-password"
          value={next}
          error={errors.next}
          onChange={(e) => setNext(e.target.value)}
        />
        <ul className="rules" aria-label={t('password.rulesTitle')}>
          <Rule id="length" ok={rules.length} text={t('password.rule.length')} />
          <Rule id="classes" ok={rules.classes} text={t('password.rule.classes')} />
          <Rule id="username" ok={next.length > 0 && rules.noUsername} text={t('password.rule.username')} />
          <Rule id="match" ok={next.length > 0 && next === repeat} text={t('password.rule.match')} />
        </ul>
        <PasswordInput
          label={t('password.repeat')}
          ref={refs.repeat}
          autoComplete="new-password"
          value={repeat}
          error={errors.repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
        <Button type="submit" block loading={change.isPending}>
          {t('password.submit')}
        </Button>
      </form>
      <div className="auth__links">
        {forced ? (
          <button type="button" className="linkbtn" onClick={() => logout.mutate()}>
            {t('user.logout')}
          </button>
        ) : (
          <button type="button" className="linkbtn" onClick={() => navigate({ kind: 'home' })}>
            {t('common.back')}
          </button>
        )}
      </div>
    </AuthLayout>
  );
}
