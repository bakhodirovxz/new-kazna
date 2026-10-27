/** S4 «Кадры»: qo'lda yozilgan tiplar (backend 12-vazifa Pydantic sxemalari bilan 1:1; faqat agregatlar). Integratsiyada generatsiya qilingan tiplarga almashtiriladi. */
import type { ReportPeriodOut } from './types';

export interface HrKpisOut {
  has_data: boolean;
  snap_month: number | null;
  plan: number;
  fact: number;
  vacancies: number | null;
  vacancy_share: number | null;
  fill: number | null;
  payroll: number;
  outflow: number;
  payroll_share: number | null;
  avg_salary: number | null;
  hired: number;
  fired: number;
  turnover: number | null;
  overtime: number;
  overtime_per_employee: number | null;
}
export interface HrMonthOut { month_id: number; payroll: number; fact: number; avg_salary: number | null; hired: number; fired: number; overtime: number }
export interface HrCategoryOut { name: string; value: number }
export interface HrBranchOut {
  branch_id: number;
  name: string;
  plan: number;
  fact: number;
  vacancies: number | null;
  fill: number | null;
  payroll: number;
  avg_salary: number | null;
  hired: number;
  fired: number;
  turnover: number | null;
  overtime: number;
  overtime_per_employee: number | null;
}
export interface KadrySvodOut { period: ReportPeriodOut; kpis: HrKpisOut; months: HrMonthOut[]; categories: HrCategoryOut[]; branches: HrBranchOut[] }
export interface KadryChislennostOut { period: ReportPeriodOut; kpis: HrKpisOut; branches: HrBranchOut[]; categories: HrCategoryOut[] }
export interface KadryFotOut { period: ReportPeriodOut; kpis: HrKpisOut; months: HrMonthOut[]; branches: HrBranchOut[] }
export interface KadryDvizhenieOut { period: ReportPeriodOut; kpis: HrKpisOut; months: HrMonthOut[]; branches: HrBranchOut[] }
