/**
 * «Производство» API turlari — S3-reja 7 va 12-vazifa Pydantic sxemalariga (`production_schemas.py`) qo'lda moslangan.
 * Backend birlashtirilgach integrator buni `Schemas[...]` (generatsiya) bilan almashtiradi. Birliklar: ishlab chiqarish —
 * mln kVt·soat, pul — mln so'm, quvvat — MVt, ulushlar 0..1.
 */
import type { ReportPeriodOut } from './types';

export interface StationProductionOut {
  generation: number;
  plan: number;
  execution: number | null;
  kium: number | null;
  payment_level: number | null;
}

export interface ProdKpisOut {
  has_data: boolean;
  generation: number;
  generation_prev: number;
  plan: number;
  execution: number | null;
  capacity_mw: number | null;
  stations: number;
  kium: number | null;
  own_needs: number;
  own_share: number | null;
  supply: number;
  accrued: number;
  paid: number;
  payment_level: number | null;
}

export interface GenMonthOut {
  month_id: number;
  generation: number;
  plan: number;
  generation_prev: number;
}

export interface SalesMonthOut {
  month_id: number;
  accrued: number;
  paid: number;
}

export interface StationGenOut {
  branch_id: number;
  name: string;
  short_name: string;
  capacity_mw: number | null;
  generation: number;
  generation_prev: number;
  plan: number;
  execution: number | null;
  kium: number | null;
  supply: number;
  own_share: number | null;
  accrued: number;
  paid: number;
  payment_level: number | null;
}

export interface MapStationOut {
  branch_id: number;
  code: string;
  name: string;
  short_name: string;
  kind: string;
  capacity_mw: number | null;
  lat: number | null;
  lon: number | null;
  production: StationProductionOut | null;
}

export interface ProizvSvodOut {
  period: ReportPeriodOut;
  has_stations: boolean;
  kpis: ProdKpisOut;
  months: GenMonthOut[];
  stations: StationGenOut[];
  map: MapStationOut[];
}

export interface ProizvStanciiOut {
  period: ReportPeriodOut;
  has_stations: boolean;
  kpis: ProdKpisOut;
  stations: StationGenOut[];
}

export interface ProizvRealizOut {
  period: ReportPeriodOut;
  has_stations: boolean;
  kpis: ProdKpisOut;
  months: SalesMonthOut[];
  stations: StationGenOut[];
}

export interface PowerStationOut {
  branch_id: number;
  branch_name: string;
  station: string;
  station_name: string;
  cascade_name: string;
  power_mw: number;
  units_working: number;
  units_reserve: number;
  units_repair: number;
}

export interface PowerOut {
  has_source: boolean;
  snap_at: string | null;
  source_date: string | null;
  stale: boolean;
  total_mw: number;
  units_working: number;
  units_reserve: number;
  units_repair: number;
  stations: PowerStationOut[];
}
