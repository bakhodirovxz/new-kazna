import { ru, type RuKey } from './ru';

export type MessageKey = RuKey;

const dictionary: Record<MessageKey, string> = ru;

/** `{name}` o'rniga parametr qo'yiladi; noma'lum joy-tutqich o'zgarmaydi. O'zbekcha — keyingi spec'da. */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const template = dictionary[key];
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    name in params ? String(params[name]) : placeholder,
  );
}
