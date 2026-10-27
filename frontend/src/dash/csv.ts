/** TZ 6: таблица в CSV с BOM (корректная кириллица в Excel). Разделитель «;», десятичная запятая. */
export interface CsvTable {
  headers: string[];
  rows: Array<Array<string | number | null>>;
}

const BOM = String.fromCharCode(0xfeff);
const FORMULA = /^[\s\xa0]*[=+\-@\t\r\n]/;

function cell(value: string | number | null): string {
  if (value === null) return '';
  let text = typeof value === 'number' ? String(value).replace('.', ',') : value;
  if (typeof value === 'string' && FORMULA.test(text)) text = `'${text}`;
  if (/[";\r\n]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function toCsv(table: CsvTable): string {
  return `${BOM}${[table.headers, ...table.rows].map((row) => row.map(cell).join(';')).join('\r\n')}`;
}
