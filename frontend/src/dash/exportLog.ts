import { api } from '../api/client';

export interface ExportContext {
  section: string;
  page: string;
  br: number | null;
  per: string;
}

/** TZ 9 «Аудит»: выгрузки журналируются (кто, что, когда) — до сохранения файла. */
export async function logExport(kind: 'csv' | 'png', card: string, ctx: ExportContext, rows?: number): Promise<void> {
  await api<undefined>('/exports/log', {
    method: 'POST',
    body: { kind, section: ctx.section, page: ctx.page, card: card.slice(0, 120), br: ctx.br, per: ctx.per, ...(rows === undefined ? {} : { rows }) },
  });
}
