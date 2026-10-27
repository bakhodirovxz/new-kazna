/** S4 «Инвестиции»: qo'lda yozilgan tiplar (backend 11-vazifa Pydantic sxemalari bilan 1:1). Integratsiyada generatsiya qilingan tiplarga almashtiriladi. */
import type { ReportPeriodOut } from './types';

export interface InvKpisOut {
  has_objects: boolean;
  objects: number;
  total_cost: number;
  program: number;
  plan_to_date: number;
  fact_ytd: number;
  execution: number | null;
  fact_period: number;
  lagging: number;
  threatened: number;
  commissioning: number;
  year: number;
}
export interface InvObjectOut {
  object_id: number;
  object_code: string;
  name: string;
  program_code: string | null;
  work_type: string;
  source_name: string;
  commissioning_year: number | null;
  total_cost: number | null;
  branch_id: number;
  branch_name: string;
  plan_year: number;
  plan_to_date: number;
  fact_ytd: number;
  fact_period: number;
  execution: number | null;
  status: string | null;
  financial: number | null;
  physical: number | null;
  gap_pp: number | null;
  advance: number;
  advance_days: number | null;
}
export interface InvCumOut { month_id: number; plan: number; fact: number | null }
export interface InvSourceOut { name: string; plan_year: number; fact_ytd: number; share: number | null }
export interface InvStageOut {
  stage_no: number;
  name: string;
  /** ISO sana (date). */
  plan_date: string;
  fact_date: string | null;
  done: boolean;
  late: boolean;
}
export interface InvObjectStagesOut { object_id: number; name: string; branch_id: number; late: number; stages: InvStageOut[] }
export interface InvSvodOut { period: ReportPeriodOut; kpis: InvKpisOut; cumulative: InvCumOut[]; sources: InvSourceOut[]; objects: InvObjectOut[] }
export interface InvObektyOut { period: ReportPeriodOut; kpis: InvKpisOut; objects: InvObjectOut[] }
export interface InvIstochnikiOut { period: ReportPeriodOut; kpis: InvKpisOut; sources: InvSourceOut[]; objects: InvObjectOut[]; cumulative: InvCumOut[] }
export interface InvRiskiOut {
  period: ReportPeriodOut;
  kpis: InvKpisOut;
  lagging: InvObjectOut[];
  gaps: InvObjectOut[];
  stages: InvObjectStagesOut[];
  advances: InvObjectOut[];
}
