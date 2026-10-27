/** `StationOut` (backend app.sections.schemas). Reja 15-vazifasi OpenAPI tiplarini generatsiya qilgach `api/types.ts` ga o'tadi. */
export interface StationOut {
  branch_id: number;
  code: string;
  name: string;
  short_name: string;
  kind: string;
  capacity_mw: number | null;
  lat: number | null;
  lon: number | null;
  inflow: number;
  outflow: number;
  closing: number | null;
  receivable: number | null;
  payable: number | null;
  overdue_payable: number | null;
  production?: Record<string, number> | null;
}
