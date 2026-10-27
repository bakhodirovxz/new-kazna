/**
 * «Склад» API turlari — S3-reja 8-vazifa Pydantic sxemalariga (`stock_schemas.py`) qo'lda moslangan.
 * Backend birlashtirilgach integrator buni `Schemas[...]` (generatsiya) bilan almashtiradi. Pul — mln so'm.
 */
import type { ReportPeriodOut } from './types';

/** S2 `loan_schemas.NamedAmountOut` (S2 bu bazada yo'q). */
export interface NamedAmountOut {
  name: string;
  amount: number;
}

export interface StockKpisOut {
  as_of: string;
  has_data: boolean;
  value: number;
  turnover_days: number | null;
  positions: number;
  below_min: number;
  has_minimum: boolean;
  idle_value: number;
  idle_share: number | null;
  has_age: boolean;
  inflow: number;
  outflow: number;
}

export interface StockMonthOut {
  month_id: number;
  inflow: number;
  outflow: number;
}

export interface StockBranchOut {
  branch_id: number;
  name: string;
  value: number;
  positions: number;
  below_min: number;
  idle_value: number;
}

export interface StockPositionOut {
  branch_id: number;
  branch_name: string;
  warehouse: string;
  nom_code: string;
  name: string;
  category: string;
  unit: string;
  qty: number;
  min_qty: number | null;
  coverage: number | null;
  value: number;
  age_days: number | null;
}

export interface AgeBucketOut {
  key: string;
  value: number;
}

export interface SkladSvodOut {
  period: ReportPeriodOut;
  kpis: StockKpisOut;
  months: StockMonthOut[];
  categories: NamedAmountOut[];
  below: StockPositionOut[];
}

export interface SkladOstatkiOut {
  period: ReportPeriodOut;
  kpis: StockKpisOut;
  branches: StockBranchOut[];
  categories: NamedAmountOut[];
}

export interface SkladMinimumOut {
  period: ReportPeriodOut;
  kpis: StockKpisOut;
  below: StockPositionOut[];
}

export interface SkladNelikvidOut {
  period: ReportPeriodOut;
  kpis: StockKpisOut;
  ages: AgeBucketOut[];
  illiquid: StockPositionOut[];
}
