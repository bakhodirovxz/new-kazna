"""Sifat tekshiruvlari (spec 5.3, TZ 3). Istalgan buzilish → failed_quality, publish yo'q.

1. control_totals   — fact_cashflow oylik summasi = manba nazorat summasi (5110/5210/5530) ±0,1%
2. balance_identity — konechniy = nachalniy + ЧДП + Разница, |Разница| ≤ 1% oborot
3. mandatory_dims   — filial majburiy (statyasiz → «Прочие» + ogohlantirish, xato emas)
4. capacity_limit   — sutkalik ishlab chiqarish (BARCHA hujjatlar yig'indisi) ≤ quvvat × 24
5. dangling_refs    — mavjud bo'lmagan o'lchovga havola yo'q (FK + etl_error hisoboti)

Fix round 1 (task-7-findings-r1.md):
- I2: `core.etl_error`ga yozish `app/etl/merge.py`da ERROR_LIMIT bilan cheklangan — shu sabab
  `mandatory_dims`/`dangling_refs` detail'idagi sonlar XOM (staging bosqichidagi) emas, balki
  YOZILGAN (cheklangan) qatorlar soni — kalit nomlari shuni aks ettirish uchun ataylab
  `logged_errors`/`logged_warnings` deb nomlangan (haqiqiy `log_capped` bayrog'i uchun
  `MergeStats` qayerdadir saqlanishi kerak edi — bu reja doirasida saqlanmaydi, shuning uchun
  hujjatlashtirish + nomlash orqali hal qilingan, controller ruling'iga muvofiq). Bloklovchi
  kodlar (`missing_branch`, `missing_dim`) cheklov ostida ham HAR DOIM birinchi navbatda
  yoziladi (`merge.py`dagi ORDER BY ustuvorligi) — shu sababli ular hech qachon "yo'qolib
  ketmaydi", faqat ularning umumiy soni cheklangan bo'lishi mumkin.
- M2/M3: `run_checks` chaqiruvchi konteksti (RLS scope, build/run mosligi) haqida qat'iy
  taxminlar qiladi — noto'g'ri chaqirilsa jim noto'g'ri "ok" qaytarish o'rniga yiqiladi.

Fix round 2 (task-7-findings-r2.md):
- R2-1: `_UNVERIFIABLE_SQL`ning oy chegaralari endi HAQIQIY TAKVIM oyi bo'yicha (har doim
  1-kundan) hisoblanadi — `window.date_from` oy o'rtasida bo'lsa ham (Task-8 inkremental
  oynasi: `min(watermark−45kun, joriy oy 1-kuni)`), aks holda `date_from`dan OLDIN, lekin
  oy ICHIDA (1-kundan keyin) yotgan yozuvlar noto'g'ri "avvalgi qoldiq mavjud" deb
  hisoblanardi.
- R2-2: `_UNVERIFIABLE_SQL` N×oy `before_month` JOIN o'rniga har `(branch_id, bank_id)` uchun
  BITTA `min(date_id)` (hisobning birinchi-yozuvi) hisoblaydi — "hisobning birinchi yozuvi
  M oyiga tushadi" ⇔ "M oyi shu filial uchun tekshirib bo'lmaydi", xuddi avvalgisi kabi,
  lekin ancha arzon (join o'lchami endi hisoblar soniga proportsional, hisoblar×oylarga emas).
- R2-3: `mandatory_dims` endi branch kaliti BUTUNLAY yo'q/NULL bo'lgan rad etilgan qatorlarni
  ham hisoblaydi: `missing_branch` KODI BILAN BIRGA, `missing_value` KODI VA `message` USTUNI
  (core.etl_error'da alohida "field" ustuni yo'q — haqiqiy maydon nomi shu yerda saqlanadi)
  `'branch_code'`ga teng bo'lgan qatorlar ham hisobga olinadi. Diagnostika (ushbu tuzatish
  paytida tekshirildi): hozirgi `app/etl/merge.py` mantig'ida `branch_code IS NULL` allaqachon
  `missing_branch` (branch — nullable=False lookup, LEFT JOIN hech qachon mos kelmaydi) beradi,
  hech qachon `missing_value`ni EMAS (chunki `branch_code` hech qaysi maqsadning `t.columns`
  a'zosi emas — u har doim Lookup, to'g'ridan-to'g'ri ustun emas) — shuning uchun ikkinchi
  shart HOZIRGI sxemada amalda ishlamaydi, lekin ruling talabiga muvofiq va kelajakdagi maqsad
  o'zgarishlariga qarshi himoya sifatida qo'shilgan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import sysconfig
from app.etl.types import ControlTotals, Window

CHECK_CODES = ("control_totals", "balance_identity", "mandatory_dims", "capacity_limit",
               "dangling_refs")
SAMPLE = 50


@dataclass(frozen=True, slots=True)
class CheckResult:
    code: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


def tolerances(conn: Connection) -> tuple[Decimal, Decimal]:
    """(nazorat jami nisbiy dopuski, balans dopuski) — paneldan, keyingi yuklashdan."""
    return (Decimal(str(sysconfig.current(conn, "quality.control_tolerance"))),
            Decimal(str(sysconfig.current(conn, "quality.balance_tolerance"))))


def failed(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.ok]


def _control_totals(conn: Connection, source: str, window: Window,
                    totals: ControlTotals | None, tolerance: Decimal) -> CheckResult:
    if totals is None:
        return CheckResult("control_totals", True, {"skipped": True})
    ours = {
        int(m): Decimal(v)
        for m, v in conn.execute(
            text("SELECT d.month_id, sum(f.amount) FROM dwh.fact_cashflow f "
                 "JOIN dwh.dim_date d ON d.date_id = f.date_id "
                 "WHERE f.src_system = :s AND f.date_id BETWEEN :f AND :t GROUP BY d.month_id"),
            {"s": source, "f": window.from_id, "t": window.to_id},
        ).all()
    }
    # M5: oynadan tashqaridagi manba oylari e'tiborsiz qoldiriladi (mos kelmaslikka
    # hisoblanmaydi) — ular alohida `ignored_months`da ro'yxatga olinadi.
    valid_months = set(window.month_ids())
    ignored_months = sorted(m for m in totals.cashflow_by_month if m not in valid_months)
    mismatches = []
    for month in sorted((set(ours) | set(totals.cashflow_by_month)) & valid_months):
        expected = Decimal(totals.cashflow_by_month.get(month, Decimal(0)))
        actual = ours.get(month, Decimal(0))
        if abs(actual - expected) > abs(expected) * tolerance:
            mismatches.append({"month": month, "source": str(expected), "dwh": str(actual)})
    return CheckResult("control_totals", not mismatches,
                       {"mismatches": mismatches[:SAMPLE], "ignored_months": ignored_months})


# M1 (opening completeness, reviewer ruling): agar biror hisob oy ichida BIRINCHI MARTA
# ko'rinsa (oy boshidan OLDIN unga tegishli hech qanday qoldiq yozuvi yo'q), o'sha
# filial-oy uchun "nachalniy qoldiq" TO'LIQ emas (yangi hisob ulushi tushib qoladi) — bunday
# filial-oylar tekshirib bo'lmaydi (`unverifiable`) va `violations`dan chiqarib tashlanadi.
# Bu Task-6 agregatlarini o'zgartirmaydi — bevosita `dwh.balance_effective`ga so'rov beriladi.
#
# R2-1: oy chegaralari `date_trunc('month', :date_from)`dan (HAQIQIY TAKVIM oyi, 1-kundan)
# hisoblanadi, xom `:date_from`dan emas — aks holda `:date_from` oy o'rtasida bo'lganda
# (inkremental oyna) oyning 1-kundan `:date_from`gacha bo'lgan haqiqiy yozuvlar noto'g'ri
# "oydan OLDIN" deb hisoblanib, yangi hisob YASHIRIN qolib ketardi.
#
# R2-2: N×oy `before_month` JOIN o'rniga — har `(branch_id, bank_id)` juftligi uchun BITTA
# `min(date_id)` (hisobning BIRINCHI-YOZUVI): "birinchi yozuv M oyiga tushadi" ⇔ "M oyi shu
# hisob uchun tekshirib bo'lmaydi" (agar birinchi yozuv M oyidan OLDINGI biror oyga tushsa,
# M oyi uchun "avvalgi qoldiq" har doim mavjud — hech qanday keyingi oy tekshirib
# bo'lmasligiga sabab bo'lolmaydi, chunki min(date_id) ANIQ BIR marta, ANIQ BIR oyga tushadi).
_UNVERIFIABLE_SQL = text(
    "WITH months AS (\n"
    "  SELECT month_id, min(date_id) AS first_id, max(date_id) AS end_id\n"
    "  FROM dwh.dim_date\n"
    "  WHERE date BETWEEN date_trunc('month', CAST(:date_from AS date))::date\n"
    "    AND CAST(:date_to AS date)\n"
    "  GROUP BY month_id),\n"
    "first_ever AS (\n"
    "  SELECT branch_id, bank_id, min(date_id) AS first_date_id\n"
    "  FROM dwh.balance_effective GROUP BY branch_id, bank_id)\n"
    "SELECT DISTINCT fe.branch_id, m.month_id\n"
    "FROM first_ever fe\n"
    "JOIN months m ON fe.first_date_id BETWEEN m.first_id AND m.end_id\n"
    "ORDER BY m.month_id, fe.branch_id"
)


# «Ввод данных»: filial-oyning kiruvchi YOKI chiquvchi qoldig'ini bergan qator `manual` bo'lsa,
# 1C talabnomalari bilan "Разница" -- manbalararo solishtirish, yuklash nuqsoni emas
# (`unverifiable`, sabab `manual_balance`). Qoldiq tanlash agregatdagi lateral bilan bir xil:
# har hisob uchun oydan oldingi / oy oxirigacha OXIRGI yozuv.
_MANUAL_BALANCE_SQL = text(
    "WITH months AS (\n"
    "  SELECT month_id, min(date_id) AS first_id, max(date_id) AS end_id\n"
    "  FROM dwh.dim_date\n"
    "  WHERE date BETWEEN date_trunc('month', CAST(:date_from AS date))::date\n"
    "    AND CAST(:date_to AS date)\n"
    "  GROUP BY month_id),\n"
    "accounts AS (SELECT DISTINCT branch_id, bank_id FROM dwh.balance_effective)\n"
    "SELECT DISTINCT a.branch_id, m.month_id\n"
    "FROM accounts a CROSS JOIN months m\n"
    "WHERE 'manual' IN (\n"
    "  (SELECT fb.src_system FROM dwh.balance_effective fb WHERE fb.branch_id = a.branch_id\n"
    "     AND fb.bank_id = a.bank_id AND fb.date_id < m.first_id\n"
    "     ORDER BY fb.date_id DESC LIMIT 1),\n"
    "  (SELECT fb.src_system FROM dwh.balance_effective fb WHERE fb.branch_id = a.branch_id\n"
    "     AND fb.bank_id = a.bank_id AND fb.date_id <= m.end_id\n"
    "     ORDER BY fb.date_id DESC LIMIT 1))\n"
    "ORDER BY m.month_id, a.branch_id"
)


def _unverifiable(conn: Connection, window: Window) -> list[dict[str, Any]]:
    params = {"date_from": window.date_from, "date_to": window.date_to}
    found: dict[tuple[int, int], dict[str, Any]] = {
        (r.branch_id, r.month_id): {"branch_id": r.branch_id, "month_id": r.month_id}
        for r in conn.execute(_UNVERIFIABLE_SQL, params).all()
    }
    for r in conn.execute(_MANUAL_BALANCE_SQL, params).all():
        entry = found.setdefault((r.branch_id, r.month_id),
                                 {"branch_id": r.branch_id, "month_id": r.month_id})
        entry["reason"] = "manual_balance"
    return [found[k] for k in sorted(found, key=lambda k: (k[1], k[0]))]


def _balance_identity(conn: Connection, build_id: int, window: Window,
                      tolerance: Decimal) -> CheckResult:
    months = window.month_ids()
    unverifiable = _unverifiable(conn, window)
    skip = {(u["branch_id"], u["month_id"]) for u in unverifiable}
    rows = conn.execute(
        text("SELECT branch_id, month_id, diff, inflow + outflow AS turnover "
             "FROM mart.agg_cash_month WHERE build_id = :b AND item_id = 0 AND branch_id <> 0 "
             "AND month_id BETWEEN :mf AND :mt AND opening_balance IS NOT NULL "
             "AND closing_balance IS NOT NULL "
             "AND abs(diff) > greatest(:tol * (inflow + outflow), 0.01) "
             "ORDER BY month_id, branch_id"),
        {"b": build_id, "mf": months[0], "mt": months[-1], "tol": tolerance},
    ).all()
    violations = [{"branch_id": r.branch_id, "month_id": r.month_id, "diff": str(r.diff),
                   "turnover": str(r.turnover)} for r in rows
                  if (r.branch_id, r.month_id) not in skip]
    return CheckResult("balance_identity", not violations,
                       {"violations": violations[:SAMPLE], "unverifiable": unverifiable[:SAMPLE]})


def _error_counts(conn: Connection, run_id: int) -> dict[str, int]:
    # M4: faqat bloklovchi ('error') darajadagi kodlar — 'warning' bu yerda YO'Q, ularni
    # `_warning_counts` alohida hisoblaydi (bitta severity aralashmasin).
    return {
        code: int(n)
        for code, n in conn.execute(
            text("SELECT code, count(*) FROM core.etl_error "
                 "WHERE run_id = :r AND severity = 'error' GROUP BY code"),
            {"r": run_id},
        ).all()
    }


def _warning_counts(conn: Connection, run_id: int) -> dict[str, int]:
    return {
        code: int(n)
        for code, n in conn.execute(
            text("SELECT code, count(*) FROM core.etl_error "
                 "WHERE run_id = :r AND severity = 'warning' GROUP BY code"),
            {"r": run_id},
        ).all()
    }


def _missing_branch_count(conn: Connection, run_id: int) -> int:
    # R2-3: `missing_branch` kodiga QO'SHIMCHA, branch kaliti BUTUNLAY yo'q/NULL bo'lgani
    # sabab rad etilgan qatorlar `missing_value` kodi bilan yozilgan bo'lishi ham mumkin —
    # `core.etl_error`da alohida "field" ustuni yo'q, haqiqiy maydon nomi `message`da
    # saqlanadi (`app/etl/merge.py`dagi `early_branches`: `missing_value` xabari ANIQ ustun
    # nomi, masalan "branch_code").
    return int(conn.execute(
        text("SELECT count(*) FROM core.etl_error WHERE run_id = :r AND severity = 'error' "
             "AND (code = 'missing_branch' "
             "OR (code = 'missing_value' AND message = 'branch_code'))"),
        {"r": run_id},
    ).scalar_one())


def _capacity(conn: Connection, window: Window) -> CheckResult:
    # I1: sutkalik chegara BITTA hujjatga emas, filial+sana+manba KESIMIDAGI YIG'INDIGA
    # nisbatan tekshiriladi (bir nechta hujjat alohida limitdan past, jamida oshib ketishi
    # mumkin) — har bir manba (`src_system`) alohida hisoblanadi (bir branch-kunga ikki xil
    # manba qo'sh hisoblanmasin). generation — mln kVt·soat; ×1000 = MVt·soat;
    # chegara capacity_mw × 24.
    rows = conn.execute(
        text("WITH daily AS (\n"
             "  SELECT g.branch_id, g.date_id, g.src_system, sum(g.generation) AS generation\n"
             "  FROM dwh.fact_generation g\n"  # manual-ok: faqat fakt qatorlari (reja emas)
             "  WHERE g.date_id BETWEEN :f AND :t\n"
             "  GROUP BY g.branch_id, g.date_id, g.src_system)\n"
             "SELECT d.branch_id, d.date_id, d.generation, v.capacity_mw\n"
             "FROM daily d\n"
             "JOIN dwh.dim_date dt ON dt.date_id = d.date_id\n"
             "JOIN dwh.dim_branch_version v ON v.branch_id = d.branch_id\n"
             "  AND dt.date >= v.valid_from AND (v.valid_to IS NULL OR dt.date <= v.valid_to)\n"
             "WHERE v.capacity_mw IS NOT NULL AND d.generation * 1000 > v.capacity_mw * 24\n"
             "ORDER BY d.date_id, d.branch_id\n"
             "LIMIT :n"),
        {"f": window.from_id, "t": window.to_id, "n": SAMPLE},
    ).all()
    violations = [{"branch_id": r.branch_id, "date_id": r.date_id,
                   "generation": str(r.generation), "capacity_mw": str(r.capacity_mw)}
                  for r in rows]
    return CheckResult("capacity_limit", not violations, {"violations": violations})


def run_checks(conn: Connection, *, run_id: int, build_id: int, source: str, window: Window,
               totals: ControlTotals | None) -> list[CheckResult]:
    # M2: RLS ostida "hamma narsa toza" degan noto'g'ri signal berish o'rniga — agar bu
    # tranzaksiya `ugk_etl`ning `app.scope_all = 'on'` doirasida bo'lmasa (masalan, oddiy
    # `ugk_app` yoki filial-cheklangan ulanish), tekshiruvlar filiallarga bo'lingan ma'lumotni
    # QISMAN ko'rishi mumkin va bu jimgina "ok" deb noto'g'ri hisobot berardi — shu sabab
    # fail-closed.
    scope = conn.execute(
        text("SELECT current_setting('app.scope_all', true)")).scalar_one_or_none()
    if scope != "on":
        raise RuntimeError(
            "run_checks: 'app.scope_all' = 'on' kutilgan edi (RLS ostida to'liq ko'rinish "
            "kerak) — noto'g'ri konteksitda chaqirilgan")
    # M3: `build_id` aynan shu `run_id` yuklashiga tegishli va hali nashr qilinmagan
    # ('building' yoki 'ready') bo'lishi kerak — aks holda (masalan, boshqa yuklashning
    # build'i yoki allaqachon 'published'/'superseded'/'failed') tekshiruv natijasi
    # ma'nosiz yoki chalg'ituvchi bo'ladi.
    build = conn.execute(
        text("SELECT load_id, status FROM core.builds WHERE build_id = :b"),
        {"b": build_id}).one_or_none()
    if build is None or build.load_id != run_id or build.status not in ("building", "ready"):
        raise ValueError(
            f"run_checks: build {build_id} run_id={run_id}ga tegishli emas yoki holati "
            "'building'/'ready' emas")

    errors = _error_counts(conn, run_id)
    warnings = _warning_counts(conn, run_id)
    missing_branch = _missing_branch_count(conn, run_id)
    missing_dim = errors.get("missing_dim", 0)
    missing_item = warnings.get("missing_item", 0)
    control_tol, balance_tol = tolerances(conn)
    return [
        _control_totals(conn, source, window, totals, control_tol),
        _balance_identity(conn, build_id, window, balance_tol),
        CheckResult("mandatory_dims", missing_branch == 0,
                    {"logged_errors": missing_branch, "logged_warnings": missing_item}),
        _capacity(conn, window),
        # FK'lar DEFERRABLE — noto'g'ri havola commit'ga yetib bormaydi; merge ularni
        # etl_error'ga yozib o'tkazib yuboradi. Shu yerda hisobot bo'yicha yuklash yiqiladi.
        CheckResult("dangling_refs", missing_dim == 0, {"logged_errors": missing_dim}),
    ]
