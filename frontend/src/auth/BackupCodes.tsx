import { useEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Button } from '../ui/Button';
import { Checkbox } from '../ui/Field';
import { Icon } from '../ui/icons';
import { useToast } from '../ui/Toast';

const EOL = String.fromCharCode(13, 10);

export function backupCodesFilename(username: string): string {
  return `ugekazna-backup-codes-${username}.txt`;
}

export function backupCodesText(codes: readonly string[], username: string, now: Date): string {
  const lines = [
    t('backup.fileTitle'),
    `${t('backup.fileUser')}: ${username}`,
    `${t('backup.fileCreated')}: ${formatDateTime(now)}`,
    t('backup.fileNote'),
    '',
    ...codes.map((code, index) => `${String(index + 1).padStart(2, ' ')}. ${code}`),
    '',
  ];
  return lines.join(EOL);
}

/** Mapbox/Chargetrip naqshi: ogohlantirish, 10 kod, yuklab olish/nusxalash, "saqladim" belgisi. */
export function BackupCodes({ codes, username, onContinue }: { codes: string[]; username: string; onContinue(): void }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const toast = useToast();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => heading.current?.focus(), []);

  useEffect(() => {
    if (saved) return undefined;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [saved]);

  const text = () => backupCodesText(codes, username, new Date());

  const download = () => {
    const url = URL.createObjectURL(new Blob([text()], { type: 'text/plain;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = backupCodesFilename(username);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text());
      setCopied(true);
    } catch {
      toast.show(t('common.copyFailed'), 'error');
    }
  };

  return (
    <>
      <p className="auth__step">{t('enroll.step', { n: 2, total: 2 })}</p>
      <h1 ref={heading} tabIndex={-1}>
        {t('backup.title')}
      </h1>
      <p className="notice">
        <Icon name="alert" />
        <span>{t('backup.warning')}</span>
      </p>
      <ol className="codes" data-testid="backup-codes" aria-label={t('backup.listLabel')}>
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ol>
      <div className="row-actions">
        <Button variant="secondary" icon="download" onClick={download}>
          {t('backup.download')}
        </Button>
        <Button variant="secondary" icon="copy" onClick={() => void copy()}>
          {copied ? t('common.copied') : t('common.copy')}
        </Button>
      </div>
      <Checkbox label={t('backup.confirm')} checked={saved} onChange={setSaved} />
      <Button block disabled={!saved} onClick={onContinue}>
        {t('backup.continue')}
      </Button>
    </>
  );
}
