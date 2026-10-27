import raw from './uz-geo.json';

export interface UzRegion {
  n: string;
  d: string;
  x?: number;
  y?: number;
  city?: boolean;
}

export interface UzGeo {
  W: number;
  H: number;
  reg: UzRegion[];
  ins: string[];
  inset: [number, number, number, number];
  main: [number, number, number, number, number];
  insp: [number, number, number, number, number, number];
}

export const UZ_GEO = raw as unknown as UzGeo;

/** Prototip `mXY`: asosiy xarita proyeksiyasi. */
export function mainXY(lon: number, lat: number): [number, number] {
  const [l0, a0, c, k, pd] = UZ_GEO.main;
  return [(lon - l0) * c * k + pd, (a0 - lat) * k + pd];
}

/** Prototip `iXY`: Toshkent viloyati kattalashtirilgan ramkasi. */
export function insetXY(lon: number, lat: number): [number, number] {
  const [l0, a0, c, k, ix, iy] = UZ_GEO.insp;
  return [ix + (lon - l0) * c * k, iy + (a0 - lat) * k];
}

export function inInset(lon: number, lat: number): boolean {
  return lon >= 68.95 && lon <= 70.15 && lat >= 40.95 && lat <= 41.75;
}

export const HIDDEN_LABELS = ['г. Ташкент', 'Хорезм', 'Андижан', 'Ташкентская'];

export const LABEL_SIDE: Record<string, 'l' | 'r' | 't' | 'b'> = {
  'UGE-01': 'r', 'UGE-02': 't', 'UGE-03': 'l', 'UGE-04': 't', 'UGE-05': 'l', 'UGE-06': 'b', 'UGE-07': 'l', 'UGE-08': 'b',
  'UGE-09': 'b', 'UGE-10': 'r', 'UGE-11': 'l', 'UGE-12': 'r', 'UGE-13': 'r', 'UGE-14': 'b', 'UGE-15': 'r', 'UGE-16': 'r',
};

export function markerRadius(capacity: number | null, inset: boolean, hq: boolean): number {
  const cap = capacity ?? 40;
  if (inset) return hq ? 6 : 3.5 + Math.sqrt(cap) * 0.33;
  return 4 + Math.sqrt(cap) * 0.55;
}
