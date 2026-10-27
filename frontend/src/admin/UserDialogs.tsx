import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { MeOut, PositionOut, UserOut } from '../api/types';
import { t } from '../i18n';
import { Button } from '../ui/Button';
import { Combobox } from '../ui/Combobox';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { FormError, TextInput } from '../ui/Field';
import { Icon } from '../ui/icons';
import { Modal } from '../ui/Modal';
import { useToast } from '../ui/Toast';
import { useCreateUser, useResetUserMfa, useResetUserPassword, useSetUserActive, useUpdateUser } from './api';
import { useStepUp } from './StepUp';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const USERNAME_RE = /^[a-z0-9._-]{3,64}$/;

function positionOptions(positions: readonly PositionOut[], keepId?: number) {
  return positions
    .filter((p) => p.is_active || p.id === keepId)
    .map((p) => ({ value: String(p.id), label: p.name, hint: p.role_code }));
}

interface CreateProps {
  positions: readonly PositionOut[];
  positionsFailed?: boolean;
  onClose(): void;
  onCreated(user: UserOut, temporaryPassword: string): void;
}

export function UserCreateDialog({ positions, positionsFailed, onClose, onCreated }: CreateProps) {
  const formId = useId();
  const create = useCreateUser();
  const stepUp = useStepUp();
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [positionId, setPositionId] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ username?: string; fullName?: string; position?: string }>({});
  const formRef = useFocusFirstInvalid(errors);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const login = username.trim().toLowerCase();
    const found: typeof errors = {};
    if (!USERNAME_RE.test(login)) found.username = t('users.usernameRule');
    if (!fullName.trim()) found.fullName = t('field.required');
    if (!positionId) found.position = t('field.required');
    setErrors(found);
    if (found.username || found.fullName || found.position) return;
    create.mutate(
      { username: login, full_name: fullName.trim(), position_id: Number(positionId), ...stepUp.body },
      {
        onSuccess: (result) => {
          const password = result.temporary_password;
          create.reset(); // parol mutatsiya holatida qolmasin
          onCreated(result.user, password);
        },
        onError: (error) => {
          if (stepUp.onError(error)) return;
          if (isApiError(error, 409, 'username_taken')) setErrors({ username: error.message });
          else if (isApiError(error, 422)) {
            const fields = Array.isArray(error.params.fields) ? error.params.fields : [];
            const mapped: typeof errors = {};
            if (fields.includes('username')) mapped.username = error.message;
            if (fields.includes('full_name')) mapped.fullName = error.message;
            if (fields.includes('position_id')) mapped.position = error.message;
            setErrors(mapped);
          }
        },
      },
    );
  };

  const handled = stepUp.isStepUp(create.error) || isApiError(create.error, 409, 'username_taken') || (isApiError(create.error, 422) && Object.keys(errors).length > 0);
  const otherError = create.error && !handled ? create.error : null;

  return (
    <Modal
      open
      onClose={onClose}
      title={t('users.createTitle')}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form={formId} loading={create.isPending}>
            {t('common.create')}
          </Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit}>
        <div className="span-2">
          <FormError error={otherError} />
          {positionsFailed ? <p className="note">{t('users.positionsFailed')}</p> : null}
        </div>
        {stepUp.field}
        <TextInput
          label={t('users.username')}
          hint={t('users.usernameRule')}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={64}
          value={username}
          error={errors.username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <TextInput label={t('users.fullName')} required maxLength={200} value={fullName} error={errors.fullName} onChange={(e) => setFullName(e.target.value)} />
        <div className="span-2">
          <Combobox
            label={t('users.position')}
            options={positionOptions(positions)}
            value={positionId}
            onChange={setPositionId}
            error={errors.position}
            required
          />
        </div>
        <p className="span-2 note">{t('users.createNote')}</p>
      </form>
    </Modal>
  );
}

type Danger = 'block' | 'unblock' | 'password' | 'mfa';

interface EditProps {
  me: MeOut;
  user: UserOut;
  positions: readonly PositionOut[];
  positionsFailed?: boolean;
  onClose(): void;
  onTemporaryPassword(username: string, password: string): void;
}

export function UserEditDialog({ me, user, positions, positionsFailed, onClose, onTemporaryPassword }: EditProps) {
  const formId = useId();
  const toast = useToast();
  const update = useUpdateUser();
  const stepUp = useStepUp();
  const setActive = useSetUserActive();
  const resetPassword = useResetUserPassword();
  const resetMfa = useResetUserMfa();
  const [fullName, setFullName] = useState(user.full_name);
  const [positionId, setPositionId] = useState<string | null>(String(user.position.id));
  const [errors, setErrors] = useState<{ name?: string }>({}); // har setErrors yangi obyekt: fokus faqat xato qo'yilganda
  const nameError = errors.name ?? null;
  const formRef = useFocusFirstInvalid(errors);
  const [danger, setDanger] = useState<Danger | null>(null);
  const self = user.id === me.id;

  const save = (event: FormEvent) => {
    event.preventDefault();
    if (!fullName.trim()) {
      setErrors({ name: t('field.required') });
      return;
    }
    setErrors({});
    update.mutate(
      { id: user.id, body: { full_name: fullName.trim(), position_id: Number(positionId ?? user.position.id), ...stepUp.body } },
      {
        onSuccess: () => {
          toast.show(t('users.saved'), 'success');
          onClose();
        },
        onError: (error) => {
          if (stepUp.onError(error)) return;
          if (isApiError(error, 422) && Array.isArray(error.params.fields) && error.params.fields.includes('full_name')) {
            setErrors({ name: error.message });
          }
        },
      },
    );
  };

  const busy = setActive.isPending || resetPassword.isPending || resetMfa.isPending;
  const dangerError = setActive.error ?? resetPassword.error ?? resetMfa.error;

  const closeDanger = () => {
    setDanger(null);
    setActive.reset();
    resetPassword.reset();
    resetMfa.reset();
  };

  const runDanger = () => {
    if (danger === 'block' || danger === 'unblock') {
      setActive.mutate(
        { id: user.id, active: danger === 'unblock' },
        {
          onSuccess: () => {
            toast.show(danger === 'block' ? t('users.blocked') : t('users.unblocked'), 'success');
            closeDanger();
            onClose();
          },
        },
      );
    } else if (danger === 'password') {
      resetPassword.mutate(user.id, {
        onSuccess: (result) => {
          const password = result.temporary_password;
          closeDanger(); // resetPassword.reset() ham shu yerda
          onTemporaryPassword(user.username, password);
        },
      });
    } else if (danger === 'mfa') {
      resetMfa.mutate(user.id, {
        onSuccess: () => {
          toast.show(t('users.mfaReset'), 'success');
          closeDanger();
          onClose();
        },
      });
    }
  };

  const confirmTexts: Record<Danger, { title: string; text: string; label: string }> = {
    block: { title: t('users.confirm.block.title'), text: t('users.confirm.block.text', { name: user.full_name }), label: t('users.block') },
    unblock: { title: t('users.confirm.unblock.title'), text: t('users.confirm.unblock.text', { name: user.full_name }), label: t('users.unblock') },
    password: { title: t('users.confirm.password.title'), text: t('users.confirm.password.text', { name: user.full_name }), label: t('users.resetPassword') },
    mfa: { title: t('users.confirm.mfa.title'), text: t('users.confirm.mfa.text', { name: user.full_name }), label: t('users.resetMfa') },
  };
  const current = danger ? confirmTexts[danger] : null;

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={user.full_name}
        note={t('users.editNote', { username: user.username, role: user.role_code })}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" form={formId} loading={update.isPending}>
              {t('common.save')}
            </Button>
          </>
        }
      >
        <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={save}>
          <div className="span-2">
            <FormError error={update.error && !nameError && !stepUp.isStepUp(update.error) ? update.error : null} />
            {positionsFailed ? <p className="note">{t('users.positionsFailed')}</p> : null}
          </div>
          {stepUp.field}
          <div className="span-2">
            <TextInput label={t('users.fullName')} required maxLength={200} value={fullName} error={nameError} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="span-2">
            <Combobox label={t('users.position')} options={positionOptions(positions, user.position.id)} value={positionId} onChange={setPositionId} disabled={self} />
          </div>
        </form>
        <section className="danger-zone" aria-labelledby={`${formId}-danger`}>
          <h3 id={`${formId}-danger`}>{t('users.actions')}</h3>
          {self ? (
            <p className="note">
              <Icon name="info" /> {t('users.selfNote')}
            </p>
          ) : null}
          <div className="row-actions">
            {user.is_active ? (
              <Button variant="danger" icon="lock" disabled={self} onClick={() => setDanger('block')}>
                {t('users.block')}
              </Button>
            ) : (
              <Button variant="secondary" icon="check" disabled={self} onClick={() => setDanger('unblock')}>
                {t('users.unblock')}
              </Button>
            )}
            <Button variant="secondary" icon="key" disabled={self} onClick={() => setDanger('password')}>
              {t('users.resetPassword')}
            </Button>
            <Button variant="secondary" icon="shield" disabled={self} onClick={() => setDanger('mfa')}>
              {t('users.resetMfa')}
            </Button>
          </div>
        </section>
      </Modal>
      <ConfirmDialog
        open={current !== null}
        title={current?.title ?? ''}
        message={current?.text ?? ''}
        confirmLabel={current?.label ?? ''}
        danger={danger !== 'unblock'}
        busy={busy}
        error={dangerError}
        onCancel={closeDanger}
        onConfirm={runDanger}
      />
    </>
  );
}

export function TemporaryPasswordDialog({ username, password, onClose }: { username: string; password: string; onClose(): void }) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      setCopied(false);
      toast.show(t('users.copyFailed'), 'error');
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={t('users.tempTitle')}
      note={t('users.tempFor', { username })}
      size="sm"
      dismissible={false} // bir martalik sir Esc/fon bosilishi bilan yo'qolmasin
      footer={<Button onClick={onClose}>{t('common.close')}</Button>}
    >
      <p className="notice">
        <Icon name="alert" />
        <span>{t('users.tempNote')}</span>
      </p>
      <div className="secret-box">
        <code className="mono" data-testid="temp-password">
          {password}
        </code>
        <Button variant="secondary" icon="copy" onClick={() => void copy()}>
          {copied ? t('common.copied') : t('common.copy')}
        </Button>
      </div>
    </Modal>
  );
}
