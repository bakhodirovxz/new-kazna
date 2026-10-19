import { describe, expect, it } from 'vitest';
import { characterClasses, checkPassword, passwordProblemText } from './passwordRules';

describe('password rules', () => {
  it('counts character classes including Cyrillic letters', () => {
    expect(characterClasses('abc')).toBe(1);
    expect(characterClasses('Abc1')).toBe(3);
    expect(characterClasses('Пароль-2026')).toBe(4);
  });

  it('checks length, classes and the username', () => {
    expect(checkPassword('Short-1', 'admin')).toEqual({ length: false, classes: true, noUsername: true });
    expect(checkPassword('Yangi-Mustahkam-77', 'admin')).toEqual({ length: true, classes: true, noUsername: true });
    expect(checkPassword('MyAdmin-Parol-2026', 'admin').noUsername).toBe(false);
  });

  it('maps server policy codes to Russian texts', () => {
    expect(passwordProblemText('password_common')).toBe('Пароль слишком распространён или содержит запрещённое слово');
    expect(passwordProblemText('something_new')).toBe('Пароль не соответствует политике безопасности');
  });
});
