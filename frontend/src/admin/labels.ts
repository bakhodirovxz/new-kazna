import type { UserOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { formatDateTime } from '../i18n/format';
import type { BadgeTone } from '../ui/Badge';

export function userStatus(user: UserOut, now = Date.now()): { tone: BadgeTone; label: string } {
  if (!user.is_active) return { tone: 'neg', label: t('users.status.blocked') };
  if (user.locked_until && Date.parse(user.locked_until) > now) {
    return { tone: 'warn', label: t('users.status.locked', { time: formatDateTime(user.locked_until) }) };
  }
  return { tone: 'ok', label: t('users.status.active') };
}

type Tone = { tone: BadgeTone; label: string };

/** Object.hasOwn: server qiymati "constructor" kabi bo'lsa prototip funksiyasi qaytmasin. */
function pick(map: Record<string, [BadgeTone, MessageKey]>, key: string): Tone {
  const entry = Object.hasOwn(map, key) ? map[key] : undefined;
  return entry ? { tone: entry[0], label: t(entry[1]) } : { tone: 'neutral', label: key };
}

function text(map: Record<string, MessageKey>, key: string): string {
  const entry = Object.hasOwn(map, key) ? map[key] : undefined;
  return entry ? t(entry) : key;
}

export function runStatus(status: string): Tone {
  return pick(
    {
      running: ['blue', 'etl.status.running'],
      success: ['ok', 'etl.status.success'],
      failed: ['neg', 'etl.status.failed'],
      failed_quality: ['neg', 'etl.status.failed_quality'],
    },
    status,
  );
}

export function buildStatus(status: string): Tone {
  return pick(
    {
      building: ['blue', 'builds.status.building'],
      ready: ['neutral', 'builds.status.ready'],
      published: ['ok', 'builds.status.published'],
      superseded: ['neutral', 'builds.status.superseded'],
      failed: ['neg', 'builds.status.failed'],
    },
    status,
  );
}

export function keyStatus(status: string): Tone {
  return pick(
    {
      active: ['ok', 'keys.status.active'],
      decrypt_only: ['warn', 'keys.status.decrypt_only'],
      retired: ['neutral', 'keys.status.retired'],
    },
    status,
  );
}

export function auditResult(result: string): Tone {
  return pick(
    { ok: ['ok', 'audit.result.ok'], fail: ['neg', 'audit.result.fail'], denied: ['warn', 'audit.result.denied'] },
    result,
  );
}

export function stepLabel(name: string): string {
  return text(
    {
      extract: 'etl.step.extract',
      dims: 'etl.step.dims',
      facts: 'etl.step.facts',
      aggregates: 'etl.step.aggregates',
      quality: 'etl.step.quality',
      publish: 'etl.step.publish',
    },
    name,
  );
}

export function sourceLabel(source: string): string {
  return text({ synthetic: 'etl.source.synthetic', file: 'etl.source.file' }, source);
}

export function modeLabel(mode: string): string {
  return text({ full: 'etl.mode.full', incremental: 'etl.mode.incremental' }, mode);
}

export function severityLabel(severity: string): string {
  return text({ error: 'etl.severity.error', warning: 'etl.severity.warning' }, severity);
}

export function purposeLabel(purpose: string): string {
  return text(
    {
      pii: 'keys.purpose.pii',
      bank: 'keys.purpose.bank',
      mfa: 'keys.purpose.mfa',
      integration_creds: 'keys.purpose.integration_creds',
      audit_meta: 'keys.purpose.audit_meta',
      audit_chain: 'keys.purpose.audit_chain',
    },
    purpose,
  );
}
