import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { BranchOut, PositionOut, RoleOut } from '../api/types';
import { t } from '../i18n';
import { Button } from '../ui/Button';
import { Checkbox, FormError, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { Select } from '../ui/Select';
import { useToast } from '../ui/Toast';
import { useSavePosition } from './api';
import { useStepUp } from './StepUp';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

export const CODE_RE = /^[a-z][a-z0-9_]{1,63}$/;

interface Props {
  position: PositionOut | null;
  roles: readonly RoleOut[];
  branches: readonly BranchOut[];
  onClose(): void;
}

export function PositionDialog({ position, roles, branches, onClose }: Props) {
  const formId = useId();
  const toast = useToast();
  const save = useSavePosition();
  const stepUp = useStepUp();
  const [code, setCode] = useState(position?.code ?? '');
  const [name, setName] = useState(position?.name ?? '');
  const [roleId, setRoleId] = useState(position ? String(position.role_id) : '');
  const [branchIds, setBranchIds] = useState<number[]>(position?.branch_ids ?? []);
  const [active, setActive] = useState(position?.is_active ?? true);
  const [errors, setErrors] = useState<{ code?: string; name?: string; role?: string }>({});
  const formRef = useFocusFirstInvalid(errors);
  const role = roles.find((r) => String(r.id) === roleId);
  const scopeAll = role?.scope_all ?? false;

  const toggleBranch = (id: number, checked: boolean) =>
    setBranchIds((list) => (checked ? [...list, id].sort((a, b) => a - b) : list.filter((b) => b !== id)));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const found: typeof errors = {};
    if (!position && !CODE_RE.test(code.trim())) found.code = t('roles.codeRule');
    if (!name.trim()) found.name = t('field.required');
    if (!role) found.role = t('field.required'); // rol bo'sh bo'lsa hech qachon role_id=0 yubormaymiz
    setErrors(found);
    if (found.code || found.name || found.role) return;
    const input =
      position === null
        ? ({ id: null, body: { code: code.trim(), name: name.trim(), role_id: Number(roleId), branch_ids: branchIds, ...stepUp.body } } as const)
        : ({ id: position.id, body: { name: name.trim(), role_id: Number(roleId), branch_ids: branchIds, is_active: active, ...stepUp.body } } as const);
    save.mutate(input, {
      onSuccess: () => {
        toast.show(t('roles.saved'), 'success');
        onClose();
      },
      onError: (error) => {
        if (stepUp.onError(error)) return;
        if (isApiError(error, 409, 'code_taken')) setErrors({ code: error.message });
        else if (isApiError(error, 422) && Array.isArray(error.params.fields)) {
          const mapped: typeof errors = {};
          if (error.params.fields.includes('code')) mapped.code = error.message;
          if (error.params.fields.includes('name')) mapped.name = error.message;
          if (error.params.fields.includes('role_id')) mapped.role = error.message;
          setErrors(mapped);
        }
      },
    });
  };

  const handled = stepUp.isStepUp(save.error) || isApiError(save.error, 409, 'code_taken') || (isApiError(save.error, 422) && Object.keys(errors).length > 0);
  const otherError = save.error && !handled ? save.error : null;

  return (
    <Modal
      open
      onClose={onClose}
      title={position ? t('roles.positionEdit', { name: position.name }) : t('roles.positionCreate')}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form={formId} loading={save.isPending}>
            {position ? t('common.save') : t('common.create')}
          </Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit}>
        <div className="span-2">
          <FormError error={otherError} />
        </div>
        {stepUp.field}
        {position ? null : (
          <TextInput
            label={t('roles.code')}
            hint={t('roles.codeRule')}
            className="mono"
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
          <Select
            label={t('roles.role')}
            value={roleId}
            required
            error={errors.role}
            options={[{ value: '', label: t('roles.rolePlaceholder') }, ...roles.map((r) => ({ value: String(r.id), label: r.name }))]}
            onChange={setRoleId}
          />
        </div>
        <fieldset className="fieldset span-2">
          <legend>{t('roles.branches')}</legend>
          {scopeAll ? <p className="note">{t('roles.branchesByRole')}</p> : null}
          {!scopeAll && branchIds.length === 0 ? <p className="note">{t('roles.noBranchesWarn')}</p> : null}
          <div className="checklist">
            {branches.map((branch) => (
              <Checkbox
                key={branch.id}
                label={branch.name}
                checked={branchIds.includes(branch.id)}
                disabled={scopeAll}
                onChange={(checked) => toggleBranch(branch.id, checked)}
              />
            ))}
          </div>
        </fieldset>
        {position ? (
          <div className="span-2">
            <Checkbox label={t('roles.positionActive')} checked={active} onChange={setActive} />
          </div>
        ) : null}
      </form>
    </Modal>
  );
}
