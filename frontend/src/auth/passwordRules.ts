import { t } from '../i18n';

/** Backend siyosati (1-reja Global Constraints): ≥12 belgi, 4 turdan kamida 3 tasi, loginsiz. */
export const MIN_PASSWORD_LENGTH = 12;

export interface PasswordRules {
  length: boolean;
  classes: boolean;
  noUsername: boolean;
}

export function characterClasses(password: string): number {
  let count = 0;
  if (/\p{Ll}/u.test(password)) count += 1;
  if (/\p{Lu}/u.test(password)) count += 1;
  if (/\p{Nd}/u.test(password)) count += 1;
  if (/[^\p{L}\p{Nd}]/u.test(password)) count += 1;
  return count;
}

export function checkPassword(password: string, username: string): PasswordRules {
  const folded = password.toLocaleLowerCase();
  return {
    length: password.length >= MIN_PASSWORD_LENGTH,
    classes: characterClasses(password) >= 3,
    noUsername: !username || !folded.includes(username.toLocaleLowerCase()),
  };
}

export function passwordProblemText(code: string): string {
  switch (code) {
    case 'password_too_short':
      return t('password.problem.too_short');
    case 'password_too_simple':
      return t('password.problem.too_simple');
    case 'password_contains_username':
      return t('password.problem.contains_username');
    case 'password_common':
      return t('password.problem.common');
    case 'password_reused':
      return t('password.problem.reused');
    default:
      return t('password.problem.unknown');
  }
}
