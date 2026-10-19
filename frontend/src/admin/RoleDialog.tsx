import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { PermissionOut, RoleOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { Button } from '../ui/Button';
import { Checkbox, FormError, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { useToast } from '../ui/Toast';
import { useSaveRole } from './api';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';
import { CODE_RE } from './PositionDialog';

type Group = 'sections' | 'export' | 'admin';
const GROUPS: ReadonlyArray<{ id: Group; titleKey: MessageKey }> = [
  { id: 'sections', titleKey: 'roles.permGroup.sections' },
  { id: 'export', titleKey: 'roles.permGroup.export' },
  { id: 'admin', titleKey: 'roles.permGroup.admin' },
];

function groupOf(code: string): Group {
  if (code.startsWith('section:')) return 'sections';
  if (code.startsWith('export:')) return 'export';
  return 'admin';
}

interface Props {
  role: RoleOut | null;
  permissions: readonly PermissionOut[];
  onClose(): void;
}

export function RoleDialog({ role, permissions, onClose }: Props) {
  const formId = useId();
  const toast = useToast();
  const save = useSaveRole();
  const [code, setCode] = useState(role?.code ?? '');
  const [name, setName] = useState(role?.name ?? '');
  const [scopeAll, setScopeAll] = useState(role?.scope_all ?? false);
  const [selected, setSelected] = useState<string[]>(role?.permissions ?? []);
  const [errors, setErrors] = useState<{ code?: string; name?: string }>({});

  const formRef = useFocusFirstInvalid(errors);
  const toggle = (perm: string, checked: boolean) =>
    setSelected((list) => (checked ? [...list, perm] : list.filter((p) => p !== perm)));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: typeof errors = {};
    if (!role && !CODE_RE.test(code.trim())) found.code = t('roles.codeRule');
    if (!name.trim()) found.name = t('field.required');
    setErrors(found);
    if (found.code || found.name) return;
    const permissionsSorted = [...selected].sort();
    const input =
      role === null
        ? ({ id: null, body: { code: code.trim(), name: name.trim(), scope_all: scopeAll, permissions: permissionsSorted } } as const)
        : ({ id: role.id, body: { name: name.trim(), scope_all: scopeAll, permissions: permissionsSorted } } as const);
    save.mutate(input, {
      onSuccess: () => {
        toast.show(t('roles.saved'), 'success');
        onClose();
      },
      onError: (error) => {
        if (isApiError(error, 409, 'code_taken')) setErrors({ code: error.message });
        else if (isApiError(error, 422) && Array.isArray(error.params.fields)) {
          const mapped: typeof errors = {};
          if (error.params.fields.includes('code')) mapped.code = error.message;
          if (error.params.fields.includes('name')) mapped.name = error.message;
          setErrors(mapped);
        }
      },
    });
  };

  const handled = isApiError(save.error, 409, 'code_taken') || (isApiError(save.error, 422) && Object.keys(errors).length > 0);
  const otherError = save.error && !handled ? save.error : null;

  return (
    <Modal
      open
      onClose={onClose}
      title={role ? t('roles.roleEdit', { name: role.name }) : t('roles.roleCreate')}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form={formId} loading={save.isPending}>
            {role ? t('common.save') : t('common.create')}
          </Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit}>
        <div className="span-2">
          <FormError error={otherError} />
        </div>
        {role ? (
          role.is_system ? (
            <p className="span-2 note">{t('roles.systemNote')}</p>
          ) : null
        ) : (
          <TextInput
            label={t('roles.code')}
            hint={t('roles.codeRule')}
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={64}
            value={code}
            error={errors.code}
            onChange={(e) => setCode(e.target.value)}
          />
        )}
        <TextInput label={t('roles.name')} required maxLength={200} value={name} error={errors.name} onChange={(e) => setName(e.target.value)} />
        <div className="span-2">
          <Checkbox label={t('roles.scopeAllLabel')} hint={t('roles.scopeAllHint')} checked={scopeAll} onChange={setScopeAll} />
        </div>
        {GROUPS.map((group) => {
          const items = permissions.filter((p) => groupOf(p.code) === group.id);
          if (items.length === 0) return null;
          return (
            <fieldset key={group.id} className="fieldset span-2">
              <legend>{t(group.titleKey)}</legend>
              <div className="checklist">
                {items.map((perm) => (
                  <Checkbox
                    key={perm.code}
                    label={perm.description}
                    checked={selected.includes(perm.code)}
                    onChange={(checked) => toggle(perm.code, checked)}
                  />
                ))}
              </div>
            </fieldset>
          );
        })}
      </form>
    </Modal>
  );
}
