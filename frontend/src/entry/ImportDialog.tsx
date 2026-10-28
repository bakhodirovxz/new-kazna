import { useState, type ChangeEvent } from 'react';
import { isApiError } from '../api/client';
import { saveBlob } from '../dash/download';
import { t } from '../i18n';
import { plural } from '../i18n/format';
import { useBranches } from '../meta/api';
import { Button } from '../ui/Button';
import { FormError } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { Select } from '../ui/Select';
import { Table, type Column } from '../ui/Table';
import { downloadTemplate, IMPORT_MAX_BYTES, IMPORT_TYPES, useImportFile, type EntryBatch, type EntryEntity } from './api';
import { serverErrorText } from './fields';
import './entry.css';

interface RowError {
  row: number;
  field: string;
  code: string;
}

function rowErrors(error: unknown): RowError[] {
  if (!isApiError(error, 422, 'import_invalid') && !isApiError(error, 409, 'duplicate_record')) return [];
  const rows = error.params.rows;
  return Array.isArray(rows) ? (rows as RowError[]).slice(0, 200) : [];
}

interface Props {
  entity: EntryEntity;
  /** Tanlangan filial id (filtr) — boshlang'ich qiymat. */
  branch: number | null;
  onClose(): void;
}

/** Fayldan import: shablon yuklab olish, fayl tanlash, xatolar jadvali yoki «Создан черновик». */
export function ImportDialog({ entity, branch, onClose }: Props) {
  const branches = useBranches();
  const upload = useImportFile();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string>('');
  const [created, setCreated] = useState<EntryBatch | null>(null);
  const [templateError, setTemplateError] = useState<unknown>(null);

  const list = branches.data ?? [];
  const branchId = picked || (branch !== null ? String(branch) : list.length === 1 ? String(list[0]?.id) : '');
  const options = [{ value: '', label: '—' }, ...list.map((b) => ({ value: String(b.id), label: b.name }))];

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const next = e.target.files?.[0] ?? null;
    upload.reset();
    setFile(null);
    setFileError(null);
    if (!next) return;
    const ext = next.name.split('.').pop()?.toLowerCase() ?? '';
    if (!Object.hasOwn(IMPORT_TYPES, ext)) setFileError(t('entry.import.badType'));
    else if (next.size > IMPORT_MAX_BYTES) setFileError(t('entry.import.tooBig'));
    else setFile(next);
  };

  const submit = () => {
    if (!file) {
      setFileError(t('entry.import.noFile'));
      return;
    }
    if (!branchId) return;
    const type = IMPORT_TYPES[file.name.split('.').pop()?.toLowerCase() ?? ''] as string;
    upload.mutate({ entity: entity.id, branch_id: Number(branchId), file, type }, { onSuccess: setCreated });
  };

  const template = async (kind: 'csv' | 'xlsx') => {
    setTemplateError(null);
    try {
      saveBlob(await downloadTemplate(entity.id, kind), `${entity.id}.${kind}`);
    } catch (error) {
      setTemplateError(error);
    }
  };

  const errors = rowErrors(upload.error);
  const columns: Column<RowError>[] = [
    { key: 'row', header: t('entry.import.col.row'), cell: (r) => r.row, align: 'right' },
    {
      key: 'field',
      header: t('entry.import.col.field'),
      cell: (r) => entity.fields.find((f) => f.name === r.field)?.title ?? (r.field || '—'),
    },
    { key: 'reason', header: t('entry.import.col.reason'), cell: (r) => serverErrorText(r.code), wrap: true },
  ];

  return (
    <Modal
      open
      onClose={onClose}
      title={`${t('entry.import.title')}: ${entity.title}`}
      footer={
        created ? (
          <>
            <a className="btn btn--secondary" href="#vvod/batches" onClick={onClose}>
              <span>{t('entry.import.open')}</span>
            </a>
            <Button onClick={onClose}>{t('common.close')}</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button loading={upload.isPending} onClick={submit}>
              {t('entry.import.upload')}
            </Button>
          </>
        )
      }
    >
      {created ? (
        <p role="status">{t('entry.import.created', { n: created.rows, rows: plural(created.rows, [t('entry.rows.one'), t('entry.rows.few'), t('entry.rows.many')]) })}</p>
      ) : (
        <div className="entry-form">
          <div className="entry-toolbar">
            <Button variant="secondary" icon="download" onClick={() => void template('csv')}>
              {t('entry.import.templateCsv')}
            </Button>
            <Button variant="secondary" icon="download" onClick={() => void template('xlsx')}>
              {t('entry.import.templateXlsx')}
            </Button>
          </div>
          {templateError ? <FormError error={templateError} /> : null}
          <p className="entry-hint">{t('entry.import.hint')}</p>
          <Select label={t('entry.branch')} value={branchId} options={options} onChange={setPicked} required />
          <label className="entry-file">
            <span>{t('entry.import.file')}</span>
            <input type="file" accept=".csv,.xlsx" onChange={onFile} aria-invalid={fileError !== null} />
          </label>
          {fileError ? <p className="form-error" role="alert">{fileError}</p> : null}
          {errors.length > 0 ? (
            <Table caption={isApiError(upload.error, 409) ? t('entry.import.collisions') : t('entry.import.errors')} columns={columns} rows={errors} rowKey={(r) => `${r.row}:${r.field}:${r.code}`} />
          ) : upload.error ? (
            isApiError(upload.error) ? (
              <p className="form-error" role="alert">{serverErrorText(upload.error.code)}</p>
            ) : (
              <FormError error={upload.error} />
            )
          ) : null}
        </div>
      )}
    </Modal>
  );
}
