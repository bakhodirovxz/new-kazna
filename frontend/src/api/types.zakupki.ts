/** S4 «Закупки»: qo'lda yozilgan tiplar (backend 10-vazifa Pydantic sxemalari bilan 1:1). Integratsiyada generatsiya qilingan tiplarga almashtiriladi. */
import type { ReportPeriodOut } from './types';

export interface ZakKpisOut {
  has_data: boolean;
  contracted: number;
  contracts: number;
  start_contracted: number;
  savings: number;
  savings_share: number | null;
  ytd: number;
  plan: number;
  plan_execution: number | null;
  in_work: number;
  in_work_start: number;
  overdue: number;
  overdue_start: number;
  direct: number;
  direct_share: number | null;
  avg_days: number | null;
  cancelled: number;
  cancelled_start: number;
}
export interface ZakMonthOut { month_id: number; contracted: number }
export interface ZakMethodOut {
  method: string;
  title: string;
  lots: number;
  start: number;
  contracted: number;
  savings: number;
  savings_share: number | null;
  avg_days: number | null;
  norm_days: number | null;
}
export interface ZakLotOut {
  lot_no: string;
  branch_id: number;
  branch_name: string;
  /** ISO sana (date). */
  date: string;
  method: string;
  method_title: string;
  subject: string;
  status: string;
  kind: string;
  start_price: number;
  contract_price: number | null;
  days: number | null;
  norm_days: number | null;
  overdue: boolean;
  supplier: string | null;
}
export interface ZakNamedOut { name: string; amount: number; count: number }
export interface ZakBranchOut { branch_id: number; name: string; plan: number; ytd: number; execution: number | null; savings: number }
export interface ZakSvodOut { period: ReportPeriodOut; kpis: ZakKpisOut; months: ZakMonthOut[]; methods: ZakMethodOut[]; lots: ZakLotOut[] }
export interface ZakLotyOut { period: ReportPeriodOut; kpis: ZakKpisOut; lots: ZakLotOut[]; truncated: boolean }
export interface ZakPostavshikiOut { period: ReportPeriodOut; kpis: ZakKpisOut; suppliers: ZakNamedOut[]; subjects: ZakNamedOut[]; branches: ZakBranchOut[] }
export interface ZakEkonomiyaOut { period: ReportPeriodOut; kpis: ZakKpisOut; methods: ZakMethodOut[]; cancelled: ZakLotOut[] }
