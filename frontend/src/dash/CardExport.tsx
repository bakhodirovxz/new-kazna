import { useState, type MutableRefObject } from 'react';
import { isApiError } from '../api/client';
import { useMe } from '../auth/api';
import { t } from '../i18n';
import { useToast } from '../ui/Toast';
import type { ChartHandle } from './chart';
import { toCsv, type CsvTable } from './csv';
import { safeFileName, saveBlob } from './download';
import { logExport, type ExportContext } from './exportLog';

export interface CardExportProps {
  title: string;
  ctx: ExportContext;
  csv?: () => CsvTable;
  chartRef?: MutableRefObject<ChartHandle | null>;
}

/** TZ 6 «Экспорт»: на каждой карточке при наведении — график в PNG, таблица в CSV с BOM. */
export function CardExport({ title, ctx, csv, chartRef }: CardExportProps) {
  const me = useMe();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  if (!me.data?.permissions.includes('export:csv')) return null;

  async function run(kind: 'csv' | 'png') {
    setBusy(true);
    try {
      if (kind === 'csv' && csv) {
        const table = csv();
        await logExport('csv', title, ctx, table.rows.length);
        saveBlob(new Blob([toCsv(table)], { type: 'text/csv;charset=utf-8' }), `${safeFileName(title)}.csv`);
      } else if (kind === 'png' && chartRef?.current) {
        const blob = await chartRef.current.toPng();
        if (!blob) return;
        await logExport('png', title, ctx);
        saveBlob(blob, `${safeFileName(title)}.png`);
      }
    } catch (error) {
      toast.show(t('dash.export.failed', { message: isApiError(error) ? error.message : String(error) }), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="exp-group">
      {chartRef ? (
        <button type="button" className="exp" disabled={busy} aria-label={t('dash.export.pngLabel', { title })} onClick={() => void run('png')}>
          {t('dash.export.png')}
        </button>
      ) : null}
      {csv ? (
        <button type="button" className="exp" disabled={busy} aria-label={t('dash.export.csvLabel', { title })} onClick={() => void run('csv')}>
          {t('dash.export.csv')}
        </button>
      ) : null}
    </span>
  );
}
