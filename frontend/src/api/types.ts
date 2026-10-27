/** Backend OpenAPI sxemalari (src/api/schema.d.ts — `npm run gen:api` bilan generatsiya qilinadi). */
import type { components } from './schema';

type Schemas = components['schemas'];

export type MeOut = Schemas['MeOut'];
export type LoginIn = Schemas['LoginIn'];
export type LoginOut = Schemas['LoginOut'];
export type MfaIn = Schemas['MfaIn'];
export type MfaTokenIn = Schemas['MfaTokenIn'];
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
