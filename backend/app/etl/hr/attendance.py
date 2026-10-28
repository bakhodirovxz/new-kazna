"""Kunlik davomat (HR API `/directory/attendance`): filial x holat bo'yicha agregatlar ->
dwh.fact_attendance. Runner/build'siz (jonli quvvat kabi): bugun - har 10 daqiqada, kecha -
tunda bir marta qayta. Sozlanmagan (kalit/manzil yo'q) bo'lsa job jim o'tkazib yuboriladi.

`items` (F.I.Sh.) umuman o'qilmaydi (models.parse_attendance oq ro'yxati); log'ga faqat
sonlar yoziladi. Filial - `hr.orgs[].hr_id` bo'yicha; moslashtirilmaganlar o'tkaziladi.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import integrations, sysconfig
from app.core.config import ConfigError, Settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.dwh.dates import today_tashkent
from app.etl.db import etl_transaction
from app.etl.hr.client import HrApiClient, HrApiError, ca_context
from app.etl.hr.models import AttendanceReport
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrApiSource
from app.etl.types import ConnectorUnavailableError

KEEP_DAYS = 400
log = get_logger("ugekazna.hr.attendance")


@dataclass(frozen=True, slots=True)
class StoreResult:
    stored: int
    skipped_branches: int


def store(conn: Connection, report: AttendanceReport, orgs: list[HrOrg]) -> StoreResult:
    """Bir filialga bog'langan bir nechta HR tashkiloti yig'iladi; kunning eski qatorlari (qayta
    moslashtirilgan/yo'qolgan tashkilot, sintetik demo) o'chirilib, yig'indi yoziladi."""
    codes = {o.hr_id: o.branch_code for o in orgs if o.hr_id is not None}
    ids: dict[str, int] = {r.code: r.branch_id for r in conn.execute(
        text("SELECT code, branch_id FROM dwh.dim_branch WHERE code = ANY(:c)"),
        {"c": list(codes.values()) or [""]})}
    meta = {s.code: s for s in report.statuses}
    headcount: dict[int, int] = defaultdict(int)
    cells: dict[tuple[int, str], list[int]] = {}
    skipped = 0
    for branch in report.branches:
        branch_id = ids.get(codes.get(branch.hr_id, ""))
        if branch_id is None:
            skipped += 1
            continue
        headcount[branch_id] += branch.employees
        for code, (days, employees) in branch.by_status.items():
            cell = cells.setdefault((branch_id, code), [0, 0])
            cell[0] += days
            cell[1] += employees
    if not cells and report.branches:
        return StoreResult(0, skipped)  # hech narsa moslashmadi - mavjud ma'lumotni o'chirmaymiz
    conn.execute(text("DELETE FROM dwh.fact_attendance WHERE att_date = :d"), {"d": report.day})
    for (branch_id, code), (days, employees) in cells.items():
        st = meta.get(code)
        conn.execute(text(
            "INSERT INTO dwh.fact_attendance (att_date, branch_id, status_code, status_label, "
            "status_kind, employees, person_days, branch_employees, generated_at) "
            "VALUES (:d, :b, :c, :l, :k, :e, :p, :n, :g)"),
            {"d": report.day, "b": branch_id, "c": code, "l": st.label if st else code,
             "k": st.kind if st else "other", "e": employees, "p": days,
             "n": headcount[branch_id], "g": report.generated_at})
    return StoreResult(len(cells), skipped)


def poll_attendance(settings: Settings, day: date, *,
                    client: HrApiClient | None = None) -> StoreResult:
    with etl_transaction() as conn:
        orgs = [HrOrg.model_validate(o) for o in sysconfig.current(conn, "hr.orgs")]
        base_url = str(sysconfig.current(conn, "hr.base_url"))
        api_key = integrations.secret(conn, "hr.api_key")
    own = client is None
    http = client or HrApiClient(base_url, api_key, verify=ca_context(settings.hr_ca_file),
                                 proxy=settings.egress_proxy)
    try:
        report = HrApiSource(http).attendance(day)
    finally:
        if own:
            http.close()
    with etl_transaction() as conn:
        result = store(conn, report, orgs)
        conn.execute(text("DELETE FROM dwh.fact_attendance WHERE att_date < :cut"),
                     {"cut": day - timedelta(days=KEEP_DAYS)})
    if result.stored == 0 and report.branches:  # masalan hr.orgs da hr_id yo'q
        log.warning("hr_attendance_unmapped", branches=len(report.branches),
                    ids=[b.hr_id for b in report.branches][:30])
    return result


def _seed_demo() -> None:
    from app.etl.synthetic import SyntheticConnector
    from app.etl.synthetic.families.attendance import seed_attendance

    today = today_tashkent()
    with etl_transaction() as conn:
        result = seed_attendance(conn, SyntheticConnector(as_of=today).model, today, days=1)
    log.info("hr_attendance_demo", stored=result.stored)


def attendance_job(settings: Settings, days_back: int = 0) -> None:
    """Worker jobi (U5: shartsiz qo'shiladi); xato ko'tarilmaydi - oxirgi ma'lumot qoladi."""
    with get_engine("app").connect() as conn:
        ready = integrations.configured(conn, "hr")
    if not ready:
        if settings.env == "dev" and days_back == 0:  # demo: HR yo'q - sintetik davomat yangilanadi
            _seed_demo()
            return
        log.info("hr_attendance_skipped", reason="not_configured")
        return
    day = today_tashkent() - timedelta(days=days_back)
    try:
        result = poll_attendance(settings, day)
    except ConnectorUnavailableError as exc:
        log.warning("hr_attendance_unavailable", error=str(exc))
        return
    except (HrApiError, ConfigError) as exc:
        log.error("hr_attendance_failed", error=str(exc))
        return
    log.info("hr_attendance_polled", day=day.isoformat(), stored=result.stored,
             skipped_branches=result.skipped_branches)
