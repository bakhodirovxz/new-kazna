/** Backend OpenAPI sxemalari (src/api/schema.d.ts — `npm run gen:api` bilan generatsiya qilinadi). */
import type { components } from './schema';

type Schemas = components['schemas'];

export type MeOut = Schemas['MeOut'];
export type LoginIn = Schemas['LoginIn'];
export type LoginOut = Schemas['LoginOut'];
export type MfaIn = Schemas['MfaIn'];
export type MfaTokenIn = Schemas['MfaTokenIn'];
export type EnrollBeginIn = Schemas['EnrollBeginIn'];
export type EnrollFinishIn = Schemas['EnrollFinishIn'];
export type EnrollStartOut = Schemas['EnrollStartOut'];
export type EnrollConfirmOut = Schemas['EnrollConfirmOut'];
export type PasswordChangeIn = Schemas['PasswordChangeIn'];
export type SessionOut = Schemas['SessionOut'];

export type UserOut = Schemas['UserOut'];
export type UserCreate = Schemas['UserCreate'];
export type UserUpdate = Schemas['UserUpdate'];
export type UserCreated = Schemas['UserCreated'];
export type TemporaryPassword = Schemas['TemporaryPassword'];
export type PositionRef = Schemas['PositionRef'];
export type RoleOut = Schemas['RoleOut'];
export type RoleIn = Schemas['RoleIn'];
export type RoleUpdate = Schemas['RoleUpdate'];
export type PositionOut = Schemas['PositionOut'];
export type PositionIn = Schemas['PositionIn'];
export type PositionUpdate = Schemas['PositionUpdate'];
export type PermissionOut = Schemas['PermissionOut'];

export type AuditOut = Schemas['AuditOut'];
export type VerifyOut = Schemas['VerifyOut'];
export type KeyOut = Schemas['KeyOut'];
export type RotateOut = Schemas['RotateOut'];

export type BranchOut = Schemas['BranchOut'];
export type PeriodOut = Schemas['PeriodOut'];
export type PeriodsOut = Schemas['PeriodsOut'];
export type MenuOut = Schemas['MenuOut'];
export type MenuGroupOut = Schemas['MenuGroupOut'];
export type MenuSectionOut = Schemas['MenuSectionOut'];
export type MenuPageOut = Schemas['MenuPageOut'];
export type FreshnessOut = Schemas['FreshnessOut'];

export type EtlRunOut = Schemas['EtlRunOut'];
export type EtlStepOut = Schemas['EtlStepOut'];
export type EtlErrorOut = Schemas['EtlErrorOut'];
export type EtlRunDetail = Schemas['EtlRunDetail'];
export type EtlRunRequest = Schemas['EtlRunRequest'];
export type EtlRequestOut = Schemas['EtlRequestOut'];
export type BuildOut = Schemas['BuildOut'];
export type RollbackIn = Schemas['RollbackIn'];
export type AlertRuleOut = Schemas['AlertRuleOut'];
export type AlertRuleUpdate = Schemas['AlertRuleUpdate'];
export type FinAssumptionOut = Schemas['FinAssumptionOut'];
export type FinAssumptionItem = Schemas['FinAssumptionItem'];
export type FinAssumptionsUpdate = Schemas['FinAssumptionsUpdate'];
export type SettingOut = Schemas['SettingOut'];
export type SettingUpdate = Schemas['SettingUpdate'];
export type SettingVersionOut = Schemas['SettingVersionOut'];
export type SecretStatusOut = Schemas['SecretStatusOut'];
export type IntegrationCheckOut = Schemas['IntegrationCheckOut'];
export type IntegrationOut = Schemas['IntegrationOut'];
export type IntegrationUpdate = Schemas['IntegrationUpdate'];

/** `app.admin.schemas.Page[T]` — generik; generatsiya nomlariga (`Page_UserOut_`) bog'lanmaymiz. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export type ReportPeriodOut = Schemas['ReportPeriodOut'];
export type CashKpisOut = Schemas['CashKpisOut'];
export type MonthPointOut = Schemas['MonthPointOut'];
export type ItemAmountOut = Schemas['ItemAmountOut'];
export type ActivityAmountOut = Schemas['ActivityAmountOut'];
export type BranchCashOut = Schemas['BranchCashOut'];
export type BranchAmountOut = Schemas['BranchAmountOut'];
export type BankAmountOut = Schemas['BankAmountOut'];
export type StationOut = Schemas['StationOut'];
export type SeriesOut = Schemas['SeriesOut'];
export type DetailRowOut = Schemas['DetailRowOut'];
export type ItemInfoOut = Schemas['ItemInfoOut'];
export type ItemBranchRowOut = Schemas['ItemBranchRowOut'];
export type ObzorSvodOut = Schemas['ObzorSvodOut'];
export type ObzorFlowOut = Schemas['ObzorFlowOut'];
export type ObzorExcelOut = Schemas['ObzorExcelOut'];
export type ItemBranchesOut = Schemas['ItemBranchesOut'];
export type KaznaKpisOut = Schemas['KaznaKpisOut'];
export type PlanFactRowOut = Schemas['PlanFactRowOut'];
export type OrderStatusOut = Schemas['OrderStatusOut'];
export type CalendarDayOut = Schemas['CalendarDayOut'];
export type CalendarOut = Schemas['CalendarOut'];
export type BankBalanceOut = Schemas['BankBalanceOut'];
export type ContractRowOut = Schemas['ContractRowOut'];
export type DebtBranchRowOut = Schemas['DebtBranchRowOut'];
export type FundRowOut = Schemas['FundRowOut'];
export type RequestsRowOut = Schemas['RequestsRowOut'];
export type KaznaSvodOut = Schemas['KaznaSvodOut'];
export type KaznaPlatezhiOut = Schemas['KaznaPlatezhiOut'];
export type KaznaCalendarOut = Schemas['KaznaCalendarOut'];
export type KaznaDogovoryOut = Schemas['KaznaDogovoryOut'];
export type KaznaCelevyeOut = Schemas['KaznaCelevyeOut'];
export type AlertOut = Schemas['AlertOut'];
export type AlertsOut = Schemas['AlertsOut'];
export type AlertCountOut = Schemas['AlertCountOut'];

/*
 * S2 «Кредиты»: qo'lda yozilgan javob turlari (backend app.sections.loan_schemas bilan bir xil nom/nullability).
 * Backend birlashgach OpenAPI generatsiyasi bilan almashtiriladi: butun blok shu yerda — faqat shu faylni o'zgartirish yetadi.
 * Summalar — mln so'm; `*_cur` — kredit valyutasida (mln birlik); null — ma'lumot yoki kurs yo'q. Sanalar — ISO.
 */
export interface LoanPaymentOut {
  day: string;
  loan_id: number;
  creditor: string;
  project: string;
  branch_name: string;
  principal: number | null;
  interest: number | null;
  total: number | null;
}
export interface LoanKpisOut {
  as_of: string;
  loans: number;
  portfolio: number | null;
  rate: number | null;
  fx_share: number | null;
  service: number;
  paid: number;
  paid_share: number | null;
  next_payment: LoanPaymentOut | null;
  peak_year: number | null;
  peak_amount: number | null;
  missing_fx: string[];
  /** DSCR — Финмодель (S5) ulanmaguncha null. */
  dscr: number | null;
}
export interface LoanYearOut {
  year: number;
  principal: number;
  interest: number;
}
export interface NamedAmountOut {
  name: string;
  amount: number;
}
export interface LoanRowOut {
  loan_id: number;
  loan_code: string;
  creditor: string;
  project: string;
  branch_id: number;
  branch_name: string;
  currency: string;
  rate: number;
  outstanding: number | null;
  outstanding_cur: number;
  original_cur: number;
  repaid_share: number | null;
  grace_until: string | null;
  in_grace: boolean;
  maturity: string;
}
export interface KreditySvodOut {
  period: ReportPeriodOut;
  has_loans: boolean;
  kpis: LoanKpisOut;
  schedule: LoanYearOut[];
  currencies: NamedAmountOut[];
  upcoming: LoanPaymentOut[];
}
export interface KredityReestrOut {
  period: ReportPeriodOut;
  has_loans: boolean;
  kpis: LoanKpisOut;
  loans: LoanRowOut[];
  creditors: NamedAmountOut[];
  currencies: NamedAmountOut[];
}
export interface KredityGrafikOut {
  period: ReportPeriodOut;
  has_loans: boolean;
  schedule: LoanYearOut[];
  upcoming: LoanPaymentOut[];
}


// S4: backend hali shu shoxda yo'q — qo'lda yozilgan tiplar (bo'lim bo'yicha bitta fayl). Integratsiyada
// quyidagi 3 qatorni `Schemas['…']` aliaslariga almashtiring (nomlar o'sha).
export type {
  ZakKpisOut, ZakMonthOut, ZakMethodOut, ZakLotOut, ZakNamedOut, ZakBranchOut, ZakSvodOut, ZakLotyOut, ZakPostavshikiOut, ZakEkonomiyaOut,
} from './types.zakupki';
export type {
  InvKpisOut, InvObjectOut, InvCumOut, InvSourceOut, InvStageOut, InvObjectStagesOut, InvSvodOut, InvObektyOut, InvIstochnikiOut, InvRiskiOut,
} from './types.investicii';
export type {
  HrKpisOut, HrMonthOut, HrCategoryOut, HrBranchOut, KadrySvodOut, KadryChislennostOut, KadryFotOut, KadryDvizhenieOut,
} from './types.kadry';


/** S5 AI-анализ (backend `app.ai.schemas`). */
export interface AiStatusOut {
  enabled: boolean;
  reason: 'disabled' | 'not_configured' | null;
  user_per_hour: number;
  org_per_day: number;
  used_last_hour: number;
}

export interface AiRequestOut {
  id: number;
  created_at: string;
  finished_at: string | null;
  username: string;
  section: string;
  page: string;
  filters: Record<string, unknown>;
  preset: string | null;
  question: string | null;
  status: string;
  error_code: string | null;
  context_chars: number;
  answer_chars: number;
  model: string;
  duration_ms: number | null;
}
