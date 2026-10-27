import type { StationOut } from './types';

/** Reja 15-vazifasi `SVOD.stations` fixture'ining nusxasi (u kelguncha xarita testlari uchun). */
export const STATIONS: StationOut[] = [
  { branch_id: 1, code: 'UGE-01', name: 'АО «Узбекгидроэнерго»', short_name: 'Узбекгидроэнерго', kind: 'head', capacity_mw: null, lat: 41.3111, lon: 69.2797, inflow: 0, outflow: 0, closing: 5000, receivable: null, payable: null, overdue_payable: null, production: null },
  { branch_id: 2, code: 'UGE-02', name: 'Чарвакская ГЭС', short_name: 'Чарвак', kind: 'ges', capacity_mw: 666, lat: 41.626, lon: 70.029, inflow: 70, outflow: 30, closing: 640, receivable: 20, payable: 50, overdue_payable: 15, production: null },
  { branch_id: 6, code: 'UGE-06', name: 'Туямуюнская ГЭС', short_name: 'Туямуюн', kind: 'ges', capacity_mw: 150, lat: 41.24, lon: 61.41, inflow: 5, outflow: 3, closing: 90, receivable: null, payable: null, overdue_payable: null, production: null },
];
