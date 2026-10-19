/** Admin formalarida o'nlik sonlar: "0,08" va "0.08" ikkalasi qabul qilinadi. */
export function parseDecimal(text: string): number | null {
  const normalized = text.trim().replace(/\s/g, '').replace('−', '-').replace(',', '.');
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

export function formatDecimal(value: number): string {
  return String(Number(value.toPrecision(12))).replace('.', ',');
}
