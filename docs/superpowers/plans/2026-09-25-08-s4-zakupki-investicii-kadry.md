# UGEKAZNA S4-reja: «Закупки» + «Инвестиции» (Адреса/АИП) + «Кадры» — implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TZ 4-bosqichi: «Закупки», «Инвестиции», «Кадры» (har biri 4 sahifa) витрина агрегатлари ustida, 9 ta qoida, xarid portali/1C reja/АИП/HR API manbalari (shaxsiy ma'lumotsiz).

**Architecture:** Backend 2-reja freymvorkiga 5 ta `mart` agregatini qo'shadi (`agg_procurement_lots`, `agg_procurement_plan`, `agg_investment_month`, `agg_object_stages`, `agg_hr_month`) va bitta yangi faktni (`dwh.fact_object_stage`); `/zakupki/*`, `/investicii/*`, `/kadry/*` endpointlari S1 bo'lim qatlami (`SQ`, `BranchSel`, `Cache.respond`) va `app/sections/queries/{procurement,investment,hr}.py` orqali ishlaydi; qoidalar S1 `app/alerts` reyestriga. Manbalar 2-reja `SourceConnector` protokolida: `ProcurementConnector` (`ProcurementPortal` adapteri, xarid stub'i), `OneCPurchasePlanConnector` (S1 `OneCClient`), `HrConnector` (`HrApiSource` — token faqat xotirada, `MehnatSource` stub'i), АИП — 2-reja `FileConnector` kanonik CSV (adreska importi emas — spec 11.1), sintetik oilalar. Frontend S1 `src/dash` bloklari bilan `src/sections/{zakupki,investicii,kadry}/*.tsx`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (sync) + psycopg 3, PostgreSQL 16, Redis 7, httpx, pydantic 2, APScheduler 3, pytest; React 18 + TypeScript strict, TanStack Query 5, Chart.js 4, Vitest + Testing Library + axe, Playwright 1.49.1.

**Spec:** [docs/superpowers/specs/2026-09-25-s4-zakupki-investicii-kadry-design.md](../specs/2026-09-25-s4-zakupki-investicii-kadry-design.md). Asos: 1-reja [2026-09-24-01-backend-yadro.md](2026-09-24-01-backend-yadro.md) (`Ctx`, `require_perm`, `AuditAction`, `record`, `Section`, `section_perm`, `tests.helpers.login/create_user`), 2-reja [2026-09-24-02-vitrina-etl.md](2026-09-24-02-vitrina-etl.md) (`TARGETS`, `_fact`, `Lookup`, `merge_*`, `register(Aggregate)`, `BuildParams`, `builds`, `Runner`, `ALERT_RULES` seed'lari, `SyntheticConnector`, `FAMILIES`, `SynthModel`, `money`, `rnd`, `BRANCHES`, `OBJECTS`, `FUNDS`, `POSITIONS`, `SUPPLIER_CODES`, `FileConnector`, `make_connector`, `KNOWN_SOURCES`, `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `current_setting`, `_cron`, `Notification`, `tests.etl_helpers`, `published_synthetic`, worker), 3-reja [2026-09-24-03-frontend.md](2026-09-24-03-frontend.md) (qobiq, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Badge`, `EmptyState`, `mockApi`, `renderWithProviders`, E2E fixture'lari), 4-reja [2026-09-25-04-ops-security.md](2026-09-25-04-ops-security.md) (`compose.prod.yml`, `egress`, `prod_config.sh`, `host-hardening.md`), S1-reja [2026-09-25-05-s1-obzor-kazna.md](2026-09-25-05-s1-obzor-kazna.md) (`SQ`, `SectionQuery`, `BranchSel`, `ReportPeriod` — `months`, `last_month`, `open_last`, `month_equivalents`, `date_from`, `date_to`, `resolve_period`, `fmt_*`, `plural`, `schemas._Out/ReportPeriodOut/period_out`, `queries.cash.num/opt`, `app.alerts` — `evaluator`, `breached`, `hit`, `RuleConfig`, `AlertHit`, `evaluate`, `load_rules`, `REGISTRY`, `tests.s1_helpers.rebuild`, `OneCClient`, `verify_setting`, `OrgMap`, `stable_code`, `to_mln`, `unmapped_branch`, `onec.models.parse`, `kazna.calendar_kinds`, `src/dash/*`, `useSection`, `SectionData`, `toggleBranch`, `Rank`, `barConfig`, `ChartCanvas`, `CardExport`, `NoData`), S2-reja [2026-09-25-06-s2-kredity-banki.md](2026-09-25-06-s2-kredity-banki.md) (`ReportingSink`, `DbStagingSink.error`, `Settings.egress_proxy`, `NamedAmountOut`, `banks.admin._put`, `tests.s2_helpers.put_setting/put_rule`), S3-reja [2026-09-25-07-s3-proizvodstvo-sklad.md](2026-09-25-07-s3-proizvodstvo-sklad.md) (`askue.registry.normalize_name`, `worker.notify_rejected_rows`, `Series.dashed`, `barConfig({format})`, `formatKwh`-uslubidagi formatlar). 1–4-rejalar, S1, S2 va S3 bajarilgan deb hisoblanadi (oxirgi migratsiya — `0015`).

## Global Constraints

- 1–4-rejalar, S1, S2 va S3 rejalarining barcha Global Constraints'lari amal qiladi (Python `>=3.12`, hash bilan qulflangan bog'liqliklar, sirlar faqat Docker secrets, UTC, `/api/v1`, xato formati `{"error": {code, message, request_id, params?}}`, ruscha UI matnlari, o'zbekcha reja prozasi va izohlar).
- Backend testlari: `TEST="docker compose -f deploy/compose.test.yml run --rm test"`, keyin `$TEST pytest …` — haqiqiy PostgreSQL 16 va Redis; DB mock qilinmaydi. Frontend: `NODE="docker compose -f deploy/compose.frontend.yml run --rm node"`, keyin `$NODE npm …`; host Node ishlatilmaydi. Git Bash'da bind-mount'li `docker run` oldidan `MSYS_NO_PATHCONV=1`.
- Birliklar: pul — mln so'm `numeric(20,2)`; odamlar — butun son (`headcount_*` `numeric(10,1)`); soatlar `numeric(12,1)`; ulushlar 0..1; `date_id` = `YYYYMMDD`, `month_id` = `YYYYMM`; manbalardagi so'm → mln (`to_mln`).
- Formulalar — spec 4-bo'lim (TZ 4) aynan. Kechikish: `дни процедуры > норматив способа + 10` (`LATE_MARGIN_DAYS = 10`). Obyekt holati: `≥ 0.9` — по графику, `0.75–0.9` — отстаёт, `< 0.75` — под угрозой. Qo'nimsizlik yilga qayta hisoblanmaydi.
- Xarid holatlari aynan: `объявлен`, `на оценке`, `договор заключён`, `отменён`, `план`; usullar: `eshop`, `contest`, `tender`, `exchange`, `direct`, `other`, `plan` (`app.etl.zakupki.codes`).
- UI faqat `pub.*` view'larni o'qiydi (TZ 9). Yangi `mart` jadvali: `build_id → core.builds ON DELETE CASCADE`, `month_id` ustuni, `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `core.rls_branch_ok(branch_id)`; `pub` view `security_invoker = true`, faqat aktiv build. Obyekt nomlari mart'ga denormalizatsiya qilinadi (`pub.objects` view'i YO'Q — boshqa filial obyekti ko'rinmasin).
- Bo'lim endpointi: `GET`, `SQ` (`br ≥ 1 | None`, `per`), router darajasida `require_perm(section:<id>:view)`, `cache.respond("<bo'lim>.<sahifa>", q.cache_filters, loader)`; har yangi route `tests/test_route_guards.py` `EXPECTED_ROUTES` ga, prefiks `PREFIX_PERMS` ga.
- Migratsiyalar: `0016_dwh_s4` (`down_revision = "0015"`), `0017_mart_procurement` (`"0016"`), `0018_mart_investment` (`"0017"`), `0019_mart_hr` (`"0018"`).
- «Требует внимания» chegaralari faqat `core.alert_rules` dan; ma'lumot yo'q yoki maxraj 0 — qoida `None` qaytaradi.
- **Shaxsiy ma'lumot yo'q (TZ 9):** HR manbalaridan faqat oq ro'yxatdagi kalitlar o'qiladi; ФИО, ПИНФЛ, pasport, telefon hech qaysi jadval, view, javob, log yoki xato matniga tushmaydi; `/purchaseRequests` (`responsible_name`) yuklanmaydi; jismoniy shaxs yetkazib beruvchi — `CP-FL` «Физическое лицо».
- Tashqi HTTP (HR API) va 1C — faqat `worker`, `httpx` (`trust_env=False`, `follow_redirects=False`, TLS tekshiruvi, javob hajmi chegarasi), HR uchun ixtiyoriy `EGRESS_PROXY`; testlarda faqat `httpx.MockTransport`, tarmoqqa chiqish yo'q. HR API, 1C va xarid portaliga jonli so'rov (qo'lda ham) reja ijrosida yuborilmaydi. HR token va parol hech qayerga (log, xato matni, audit) yozilmaydi.
- HR hisobi — sirlar `hr_username`, `hr_password` (ixtiyoriy `hr_ca_bundle`) — faqat `worker`.
- Credential fayllari (`1C.1/secrets.php`, `auth.php`, `auth.js`, `apache-proxy.conf`, `gazna_bot/config.py`, har qanday `.env` jumladan `adreska/.env`, `deploy/secrets/`) ochilmaydi va hech qayerga ko'chirilmaydi.
- Frontend: `src/sections/<bo'lim>/*.tsx` — faqat sahifalar, yordamchilar `src/sections/<bo'lim>/parts/` va `src/dash/`; barcha matnlar `t()` orqali (`src/i18n/ru.ts` oxiriga); CSP o'zgarmaydi (inline `<style>` yo'q). Yangi vizual naqsh yo'q — barcha bloklar prototipda bor (Refero kerak emas).
- Commit xabari oxirida bo'sh qatordan keyin: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Spec'dan ongli chetlanishlar yo'q; S4 qarorlari — spec 11-bo'lim.

## Review Focus

1. **Yopilmagan oy tanlangan (`m09`, 24-sentabr)** — АИП rejasi 24/30 ulushi bilan (grafik bajarilishi yolg'on past chiqmaydi), o'rtacha ish haqi 0,8 oy bilan, xarid yil boshidan 1-yanvar…24-sentabr — 8-vazifa `test_open_month_prorates_schedule`, 9-vazifa `test_open_month_uses_month_equivalents`, 7-vazifa `test_open_month_and_quarter`.
2. **Obyekti yo'q filial, HQ yoki HR ma'lumoti yo'q davr** — kutiladi: `has_objects = false`/`has_data = false`, nolga bo'lish yo'q, sahifa tushuntirish chiqaradi, qoidalar yonmaydi — 8-vazifa `test_branch_without_objects`, 9-vazifa `test_period_without_hr_data`, 13-vazifa `test_rules_skip_without_data`, 20-vazifa `Сводка: branch without objects shows the explanation`.
3. **HR API javobida shaxsiy maydonlar, tashkilot kesimi yo'q yoki token eskirgan** — kutiladi: maydonlar tashlanadi va log'ga tushmaydi, `fact_hr` yozilmaydi (ogohlantirish), token bir marta yangilanadi — 15-vazifa `test_token_cached_and_refreshed_on_expiry_and_401`, `test_parse_main_and_breakdown_shapes`, 16-vazifa `test_no_org_breakdown_is_a_warning`, `test_org_breakdown_is_mapped_to_fact_hr` (log va chiqishda ФИО yo'q), 12-vazifa `test_no_personal_fields_anywhere`.
4. **Xarid fayli noma'lum usul/holat bilan yoki normativ o'zgartirilgan** — kutiladi: `CHECK` faylni rad etadi (run `failed`, eski build aktiv), normativ keyingi build'da qo'llanadi — 1-vazifa `test_procurement_checks_reject_unknown_codes`, 4-vazifa `test_norm_change_applies_on_next_build`, 17-vazifa `test_bad_method_rejects_file`.
5. **Filial doirasidagi foydalanuvchi** — `economist_filiala` «Кадры»da faqat o'z filialini ko'radi, «Закупки»/«Инвестиции» — 403; boshqa filial `br` — 403 `scope_violation`; `pub` view'lar to'g'ridan-to'g'ri SQL'da ham cheklangan — 10/11/12-vazifalar `test_permission_and_branch_scope`, `test_pub_views_rls_direct_sql` / `test_pub_view_rls_direct_sql`, 22-vazifa E2E.

---

## Fayl tuzilishi

```
backend/app/core/config.py                    hr_* sozlamalari, problems()
backend/app/dwh/reference.py                  S4 sozlamalari (zakupki.method_norms, hr.*, etl.*_cron)
backend/app/dwh/targets.py                    fact_object_stage, fact_investment forward
backend/app/etl/notify.py                     Kind += hr_rows_rejected
backend/migrations/versions/0016_dwh_s4.py, 0017_mart_procurement.py, 0018_mart_investment.py, 0019_mart_hr.py
backend/app/dwh/procurement_aggregates.py, investment_aggregates.py, hr_aggregates.py (+ aggregates.py importi)
backend/app/etl/synthetic/reference.py        PROCUREMENT_SUBJECTS, METHOD_PROFILES
backend/app/etl/synthetic/families/dims.py    predmetlar (PS-01…07)
backend/app/etl/synthetic/families/procurement.py, investment.py, hr.py (+ families/__init__.py)
backend/app/etl/zakupki/                      codes, portal, connector, onec_plan
backend/app/etl/hr/                           registry, models, client, source, connector, admin
backend/app/sections/queries/procurement.py, investment.py, hr.py
backend/app/sections/zakupki_schemas.py, zakupki.py, investicii_schemas.py, investicii.py, kadry_schemas.py, kadry.py
backend/app/alerts/procurement.py, investment.py, hr.py (+ __init__.py)
backend/app/etl/connectors.py, app/worker.py, app/cli.py, app/main.py
backend/tests/s4_helpers.py, tests/fixtures/hr/*, tests/fixtures/onec/purchase_plan_2026.json
deploy/compose.prod.yml, deploy/prod.env.example, deploy/secrets.example/README.md, scripts/prod_config.sh
docs/integration/zakupki-format.md, aip-format.md, kadry-fayl.md, hr-connector.md, hr-sorov-s4.md, 1c-sorov-s4.md; docs/ops/host-hardening.md
frontend/src/api/types.ts, openapi.json, src/api/schema.d.ts
frontend/src/dash/chart.tsx (o'ng o'q), people.ts, s4.css, formulas.ts
frontend/src/i18n/ru.ts, src/test/s4Fixtures.ts
frontend/src/sections/zakupki/{svod,loty,postavshiki,ekonomiya}.tsx, zakupki/parts/*
frontend/src/sections/investicii/{svod,obekty,istochniki,riski}.tsx, investicii/parts/*
frontend/src/sections/kadry/{svod,chislennost,fot,dvizhenie}.tsx, kadry/parts/*
frontend/e2e/specs/zakupki-investicii-kadry.spec.ts
```

Vazifalar tartibi: 1 (sozlamalar, 0016) → 2–3 (sintetik) → 4–6 (agregatlar) → 7–9 (so'rovlar) → 10–12 (API) → 13 (qoidalar) → 14 (xarid manbalari) → 15–16 (HR) → 17 (ekspluatatsiya, hujjatlar) → 18 (frontend asoslari) → 19–21 (sahifalar) → 22 (E2E).

---
### Task 1: S4 sozlamalari, kodlar, konfiguratsiya, `fact_object_stage` (0016) va xarid cheklovlari

**Files:**
- Create: `backend/app/etl/zakupki/__init__.py`, `backend/app/etl/zakupki/codes.py`, `backend/app/etl/hr/__init__.py`, `backend/app/etl/hr/registry.py`, `backend/migrations/versions/0016_dwh_s4.py`
- Modify: `backend/app/core/config.py`, `backend/app/dwh/reference.py`, `backend/app/dwh/targets.py`, `backend/app/etl/notify.py` (`Kind`), `backend/tests/test_reference.py` (kutilgan kalitlar), `backend/tests/test_dwh_facts.py` (`FACTS`), `backend/tests/etl_helpers.py` (`_PURGE_ORDER`)
- Test: `backend/tests/test_s4_prereq.py`

**Interfaces:**
- Consumes: `Settings`, `SecretStr`, `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `_cron`, `Notification`, `_fact`, `Lookup`, `BRANCH`, `TARGETS`, `askue.registry.normalize_name`, `tests.etl_helpers.*`.
- Produces:
  - `app.etl.zakupki.codes`: `IN_WORK = ("объявлен", "на оценке")`, `DONE = "договор заключён"`, `CANCELLED = "отменён"`, `PLAN_STATUS = "план"`, `STATUSES`, `METHODS = ("eshop", "contest", "tender", "exchange", "direct", "other")`, `PLAN_METHOD = "plan"`, `DIRECT = "direct"`, `PLAN_DOC = "procurement_plan"`, `METHOD_TITLES: dict[str, str]`, `DEFAULT_METHOD_NORMS`, `LATE_MARGIN_DAYS = 10`, `INDIVIDUAL_CP = "CP-FL"`, `INDIVIDUAL_NAME = "Физическое лицо"`.
  - `app.etl.hr.registry`: `HrOrg` (pydantic, frozen: `org` 1–200, `branch_code` 1–32), `validate_orgs(value: list[HrOrg]) -> list[dict[str, str]]` (normallashtirilgan nom takrorlanmaydi).
  - `Settings`: `hr_base_url = ""`, `hr_username: SecretStr`, `hr_password: SecretStr`, `hr_ca_file = "/run/secrets/hr_ca_bundle"`; `problems()` — `HR_BASE_URL` `https://` bilan boshlanmasa xato.
  - Sozlamalar: `zakupki.method_norms` (barcha 6 usul, 1–365 kun), `hr.orgs = []`, `hr.breakdown_path = "/dashboard/employees-by-category"`, `etl.hr_cron = "30 6 * * *"`, `etl.onec_zakupki_cron = "40 2 * * *"`.
  - `Notification.kind` += `"hr_rows_rejected"`.
  - `dwh.fact_object_stage (date_id — rejadagi tugash, branch_id, object_id, stage_no, stage_name, fact_date_id, load_id, src_system, doc_type, src_id, updated_at)` + RLS; `TARGETS["fact_object_stage"]` (`forward=True`, lookup `object_code`), `TARGETS["fact_investment"].forward = True`.
  - `dwh.fact_procurement` cheklovlari: `fact_procurement_status_ck`, `fact_procurement_method_ck`, `fact_procurement_amounts_ck`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_s4_prereq.py`:
```python
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.dwh.targets import TARGETS
from app.etl.db import etl_transaction
from app.etl.notify import Notification
from app.etl.zakupki import codes
from tests.etl_helpers import (
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)

NORMS = {"eshop": 15, "contest": 40, "tender": 70, "exchange": 20, "direct": 12, "other": 40}


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_s4_settings_defaults() -> None:
    assert DEFAULT_SETTINGS["zakupki.method_norms"] == NORMS == codes.DEFAULT_METHOD_NORMS
    assert DEFAULT_SETTINGS["hr.orgs"] == []
    assert DEFAULT_SETTINGS["hr.breakdown_path"] == "/dashboard/employees-by-category"
    for key, cron in (("etl.hr_cron", "30 6 * * *"), ("etl.onec_zakupki_cron", "40 2 * * *")):
        assert DEFAULT_SETTINGS[key] == cron and validate_setting(key, cron) == cron
    assert set(codes.METHOD_TITLES) == {*codes.METHODS, codes.PLAN_METHOD}
    assert codes.STATUSES == ("объявлен", "на оценке", "договор заключён", "отменён", "план")


def test_s4_settings_validation() -> None:
    orgs = [{"org": "Чорвоқ ГЭС", "branch_code": "UGE-02"},
            {"org": "Фарҳод ГЭС", "branch_code": "UGE-05"}]
    assert validate_setting("hr.orgs", orgs) == orgs
    assert validate_setting("zakupki.method_norms", {**NORMS, "tender": 60})["tender"] == 60
    bad: list[tuple[str, Any]] = [
        ("zakupki.method_norms", {k: v for k, v in NORMS.items() if k != "direct"}),
        ("zakupki.method_norms", {**NORMS, "auction": 10}),
        ("zakupki.method_norms", {**NORMS, "eshop": 0}),
        ("zakupki.method_norms", {**NORMS, "eshop": "15"}),
        ("hr.orgs", orgs + [{"org": "  чорвоқ   гэс ", "branch_code": "UGE-03"}]),
        ("hr.orgs", [{"org": "", "branch_code": "UGE-02"}]),
        ("hr.orgs", [{"org": "X", "branch_code": "UGE-02", "extra": 1}]),
        ("hr.breakdown_path", "dashboard/x"),
        ("hr.breakdown_path", "/dash?x=1"),
        ("etl.hr_cron", "daily"),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_s4_config_and_notification_kind() -> None:
    base = get_settings()
    assert base.hr_base_url == "" and base.hr_username.get_secret_value() == ""
    assert base.hr_ca_file == "/run/secrets/hr_ca_bundle"
    plain = base.model_copy(update={"hr_base_url": "http://hr.test"})
    assert any("HR_BASE_URL" in p for p in plain.problems())
    good = base.model_copy(update={"hr_base_url": "https://hr.test"})
    assert not any("HR_BASE_URL" in p for p in good.problems())
    assert Notification("hr_rows_rejected", "s", "b").kind == "hr_rows_rejected"


def test_targets_forward_and_stage_table() -> None:
    assert TARGETS["fact_investment"].forward and TARGETS["fact_object_stage"].forward
    assert not TARGETS["fact_procurement"].forward and not TARGETS["fact_hr"].forward
    with etl_transaction() as conn:
        row = conn.execute(text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'dwh' AND c.relname = 'fact_object_stage'")).one()
    assert row.relrowsecurity and row.relforcerowsecurity


def _lot(status: str, method: str) -> dict[str, Any]:
    return {"d": 20260810, "s": "test_s4_ck", "st": status, "m": method}


@pytest.mark.parametrize(("status", "method"), [("в работе", "eshop"), ("объявлен", "auction")])
def test_procurement_checks_reject_unknown_codes(status: str, method: str) -> None:
    with pytest.raises(IntegrityError), etl_transaction() as conn:
        conn.execute(text(
            "INSERT INTO dwh.fact_procurement (date_id, branch_id, lot_no, method, status, "
            "start_price, load_id, src_system, doc_type, src_id) "
            "VALUES (:d, 2, 'L-1', :m, :st, 10, 0, :s, 'portal_lot', 'ck-1')"),
            _lot(status, method))


def test_stage_rows_merge_with_future_dates(source: str) -> None:
    tag = new_tag()
    branch = branch_row(tag)
    obj = {"code": f"O-{tag}", "name": "Тестовый объект", "program_code": None,
           "work_type": "new", "commissioning_year": 2027, "total_cost": 100,
           "source_code": None}

    def stage_row(n: int, day: int, fact: int | None) -> dict[str, Any]:
        return {"doc_type": "aip_stage", "src_id": f"S-{tag}-{n}", "date_id": day,
                "branch_code": branch["code"], "object_code": obj["code"], "stage_no": n,
                "stage_name": f"Этап {n}", "fact_date_id": fact}

    run = open_run(source)
    stage(run, source, {"dim_branch": [branch], "dim_object": [obj],
                        "fact_object_stage": [stage_row(1, 20260315, 20260320),
                                              stage_row(2, 20271215, None)]})
    merge_all(run, source, complete={"fact_object_stage"})
    with etl_transaction() as conn:
        got = conn.execute(text(
            "SELECT stage_no, date_id, fact_date_id FROM dwh.fact_object_stage "
            "WHERE src_system = :s ORDER BY stage_no"), {"s": source}).all()
    assert [tuple(r) for r in got] == [(1, 20260315, 20260320), (2, 20271215, None)]
```

`backend/tests/test_reference.py` — `test_settings_defaults_and_validation` dagi `assert set(DEFAULT_SETTINGS) == {…}` to'plamiga quyidagi 5 kalitni qo'shing (qolganlari o'zgarmaydi):
```python
        "zakupki.method_norms", "hr.orgs", "hr.breakdown_path", "etl.hr_cron",
        "etl.onec_zakupki_cron",
```

`backend/tests/test_dwh_facts.py` — `FACTS` kortejining oxiriga `"fact_object_stage",` qo'shing.

`backend/tests/etl_helpers.py` — `_PURGE_ORDER` kortejida `"fact_investment",` dan OLDIN `"fact_object_stage",` qo'shing (bosqichlar `dim_object` dan oldin o'chiriladi).

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_s4_prereq.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.zakupki'`.

- [ ] **Step 3: Kodlar va HR tashkilotlari modeli**

`backend/app/etl/zakupki/__init__.py`:
```python
"""Xaridlar integratsiyasi: portal adapteri, 1C xarid rejasi, kodlar (S4 spec 3.1)."""
```

`backend/app/etl/zakupki/codes.py`:
```python
"""Xarid holatlari va usullari — yagona manba (migratsiya 0016 CHECK'lari shu qiymatlar bilan).

Holatlar TZ 3-bo'lim/4-bo'lim so'zlari bilan (ruscha, kichik harf); usullar — barqaror kodlar,
ekrandagi nomi METHOD_TITLES dan. Normativ kunlar — core.settings `zakupki.method_norms`.
"""

from __future__ import annotations

IN_WORK: tuple[str, ...] = ("объявлен", "на оценке")
DONE = "договор заключён"
CANCELLED = "отменён"
PLAN_STATUS = "план"
STATUSES: tuple[str, ...] = (*IN_WORK, DONE, CANCELLED, PLAN_STATUS)

METHODS: tuple[str, ...] = ("eshop", "contest", "tender", "exchange", "direct", "other")
PLAN_METHOD = "plan"
DIRECT = "direct"
PLAN_DOC = "procurement_plan"

METHOD_TITLES: dict[str, str] = {
    "eshop": "Электронный магазин",
    "contest": "Электронный конкурс",
    "tender": "Тендер",
    "exchange": "Биржевые торги",
    "direct": "Прямой договор",
    "other": "Прочие способы",
    "plan": "План закупок",
}

# Vaqtinchalik normativlar (prototip PMETH davomiyliklari yuqori chegarasi) — mijoz tasdiqlaydi
# (spec 12, 2-savol); admin API orqali versiyalanib o'zgartiriladi.
DEFAULT_METHOD_NORMS: dict[str, int] = {
    "eshop": 15, "contest": 40, "tender": 70, "exchange": 20, "direct": 12, "other": 40,
}
LATE_MARGIN_DAYS = 10  # TZ 4: «превышают норматив способа более чем на 10»

INDIVIDUAL_CP = "CP-FL"  # jismoniy shaxs / YaTT yetkazib beruvchi — nom saqlanmaydi (TZ 9)
INDIVIDUAL_NAME = "Физическое лицо"
```

`backend/app/etl/hr/__init__.py`:
```python
"""Kadrlar integratsiyasi: HR API, mehnat.uz stub'i — faqat agregatlar (TZ 9)."""
```

`backend/app/etl/hr/registry.py`:
```python
"""HR manbasidagi tashkilot ↔ filial moslashtirishi (`hr.orgs`) — sof model.

Tashkilot nomi normallashtirilib solishtiriladi (apostrof variantlari, bo'shliqlar, registr).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.etl.askue.registry import normalize_name


class HrOrg(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    org: Annotated[str, Field(min_length=1, max_length=200)]
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]


def validate_orgs(value: list[HrOrg]) -> list[dict[str, str]]:
    names = [normalize_name(o.org) for o in value]
    if not all(names) or len(set(names)) != len(names):
        raise ValueError("hr.orgs: tashkilot nomi bo'sh yoki takrorlangan")
    return [o.model_dump() for o in value]
```

- [ ] **Step 4: Sozlamalar va konfiguratsiya**

`backend/app/dwh/reference.py` — importlarga qo'shing:
```python
from app.etl.hr.registry import HrOrg, validate_orgs
from app.etl.zakupki.codes import DEFAULT_METHOD_NORMS, METHODS
```
`DEFAULT_SETTINGS` dan OLDIN qo'shing:
```python
def _method_norms(value: dict[str, int]) -> dict[str, int]:
    if set(value) != set(METHODS):
        raise ValueError("zakupki.method_norms: barcha usullar uchun normativ kerak")
    return dict(value)
```
`DEFAULT_SETTINGS` lug'ati oxiriga qo'shing:
```python
    "zakupki.method_norms": dict(DEFAULT_METHOD_NORMS),
    "hr.orgs": [],
    "hr.breakdown_path": "/dashboard/employees-by-category",
    "etl.hr_cron": "30 6 * * *",
    "etl.onec_zakupki_cron": "40 2 * * *",
```
`SETTING_TYPES` lug'ati oxiriga qo'shing:
```python
    "zakupki.method_norms": TypeAdapter(Annotated[
        dict[str, Annotated[int, Field(strict=True, ge=1, le=365)]],
        AfterValidator(_method_norms)]),
    "hr.orgs": TypeAdapter(Annotated[list[HrOrg], AfterValidator(validate_orgs)]),
    "hr.breakdown_path": TypeAdapter(
        Annotated[str, Field(pattern=r"^/[A-Za-z0-9/_-]{1,100}$")]),
    "etl.hr_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "etl.onec_zakupki_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
```

`backend/app/core/config.py` — `Settings` sinfida S3'ning `onec_sklad_password` qatoridan keyin qo'shing:
```python
    # S4 (spec 3.3): HR API (server tomonida login, token faqat xotirada). Login/parol —
    # Docker secrets hr_username, hr_password; ixtiyoriy korporativ CA — hr_ca_bundle.
    hr_base_url: str = ""
    hr_username: SecretStr = SecretStr("")
    hr_password: SecretStr = SecretStr("")
    hr_ca_file: str = "/run/secrets/hr_ca_bundle"
```
`problems()` ichida oxirgi `return out` qatoridan OLDIN qo'shing:
```python
        if self.hr_base_url and not self.hr_base_url.startswith("https://"):
            out.append("HR_BASE_URL https:// bilan boshlanishi kerak")
```

`backend/app/etl/notify.py` — `Kind` qatorini almashtiring:
```python
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data", "bank_rows_rejected",
               "askue_rows_rejected", "hr_rows_rejected"]
```

- [ ] **Step 5: 0016 migratsiyasi**

`backend/migrations/versions/0016_dwh_s4.py`:
```python
"""S4: obyekt bosqichlari fakti (fact_object_stage) va fact_procurement holat/usul cheklovlari

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-25

Holat va usul qiymatlari app/etl/zakupki/codes.py bilan bir xil (test tekshiradi); migratsiya
ilova kodini import qilmaydi.
"""

from alembic import op

revision = "0016"
down_revision = "0015"  # `alembic heads` boshqa bo'lsa — shu qiymatni joriy head'ga moslang
branch_labels = None
depends_on = None

STATUSES = "'объявлен', 'на оценке', 'договор заключён', 'отменён', 'план'"
METHODS = "'eshop', 'contest', 'tender', 'exchange', 'direct', 'other', 'plan'"
FK = "DEFERRABLE INITIALLY DEFERRED"

STAGE_TABLE = f"""
CREATE TABLE dwh.fact_object_stage (
  date_id integer NOT NULL REFERENCES dwh.dim_date (date_id) {FK},
  branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id) {FK},
  object_id integer NOT NULL REFERENCES dwh.dim_object (object_id) {FK},
  stage_no smallint NOT NULL CHECK (stage_no BETWEEN 1 AND 30),
  stage_name varchar(200) NOT NULL,
  fact_date_id integer,
  load_id bigint NOT NULL,
  src_system varchar(32) NOT NULL,
  doc_type varchar(32) NOT NULL,
  src_id varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fact_object_stage_src_uq UNIQUE (src_system, doc_type, src_id)
)
"""


def upgrade() -> None:
    op.execute(STAGE_TABLE)
    op.execute("CREATE INDEX fact_object_stage_date_id_branch_id_idx "
               "ON dwh.fact_object_stage (date_id, branch_id)")
    op.execute("CREATE INDEX fact_object_stage_branch_id_idx ON dwh.fact_object_stage (branch_id)")
    op.execute("CREATE INDEX fact_object_stage_object_id_idx ON dwh.fact_object_stage (object_id)")
    op.execute("ALTER TABLE dwh.fact_object_stage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dwh.fact_object_stage FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY branch_scope ON dwh.fact_object_stage "
               "USING (core.rls_branch_ok(branch_id)) WITH CHECK (core.rls_branch_ok(branch_id))")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.fact_object_stage TO ugk_etl")
    op.execute(f"ALTER TABLE dwh.fact_procurement ADD CONSTRAINT fact_procurement_status_ck "
               f"CHECK (status IN ({STATUSES}))")
    op.execute(f"ALTER TABLE dwh.fact_procurement ADD CONSTRAINT fact_procurement_method_ck "
               f"CHECK (method IN ({METHODS}))")
    op.execute("ALTER TABLE dwh.fact_procurement ADD CONSTRAINT fact_procurement_amounts_ck "
               "CHECK (start_price >= 0 AND (contract_price IS NULL OR contract_price >= 0) "
               "AND (procedure_days IS NULL OR procedure_days >= 0))")


def downgrade() -> None:
    for name in ("amounts", "method", "status"):
        op.execute(f"ALTER TABLE dwh.fact_procurement DROP CONSTRAINT fact_procurement_{name}_ck")
    op.execute("DROP TABLE dwh.fact_object_stage")
```

- [ ] **Step 6: Staging maqsadlari**

`backend/app/dwh/targets.py` — `_ALL` ichidagi `fact_investment` yozuvini almashtiring:
```python
    _fact("fact_investment", ("plan", "fact", "physical_pct", "advance", "advance_date_id"),
          (BRANCH, Lookup("object_id", "dim_object"),
           Lookup("source_id", "dim_source", nullable=True)), forward=True),
    # S4: obyekt bosqichlari — sana = rejadagi tugash (kelajak bo'lishi mumkin).
    _fact("fact_object_stage", ("stage_no", "stage_name", "fact_date_id"),
          (BRANCH, Lookup("object_id", "dim_object")), forward=True),
```
(2-reja `test_targets`/`test_merge` da `FACT_TARGETS` aniq to'plam bilan solishtirilsa — o'sha to'plamga `"fact_object_stage"` ni qo'shing; `DIM_TARGETS` o'zgarmaydi.)

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$TEST alembic upgrade head` va `$TEST pytest tests/test_s4_prereq.py tests/test_reference.py tests/test_config.py tests/test_notify.py tests/test_dwh_facts.py tests/test_rls_structure.py tests/test_s1_prereq.py -v`
Expected: barcha testlar passed (RLS strukturaviy testi yangi jadvalni avtomatik qamraydi). `$TEST ruff check app tests` va `$TEST mypy app` — xatosiz.

- [ ] **Step 8: Commit**

```bash
git add backend
git commit -m "feat(s4): xarid kodlari va normativlari, HR sozlamalari, obyekt bosqichlari fakti (0016)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 2: `SyntheticConnector` — xaridlar oilasi (lotlar, yillik reja, predmetlar)

**Files:**
- Create: `backend/app/etl/synthetic/families/procurement.py`
- Modify: `backend/app/etl/synthetic/reference.py` (`METHOD_PROFILES`, `PROCUREMENT_SUBJECTS`), `backend/app/etl/synthetic/families/dims.py` (predmetlar), `backend/app/etl/synthetic/families/__init__.py` (`FAMILIES`), `backend/tests/test_synthetic.py`
- Test: `backend/tests/test_synthetic_s4.py`

**Interfaces:**
- Consumes: `SynthModel` (`seed`, `as_of`, `history_start`, `months()`, `period_end(month)`), `BRANCHES`, `BranchRef`, `HQ_ID`, `EXPENSE_ITEMS`, `SUPPLIER_CODES`, `share`, `rnd`, `money`, `date_id`, `month_id`, `month_end`, `add_months`, `StagingSink`, `Window`, `codes.*`.
- Produces:
  - `reference`: `METHOD_PROFILES: tuple[tuple[str, float, tuple[float, float], tuple[int, int]], ...]` (kod, og'irlik, tejash, davomiylik — prototip PMETH), `PROCUREMENT_SUBJECTS` (7, prototip PCAT); `dim_nomenclature` += `PS-01…PS-07` (nom = kategoriya = predmet, birlik `—`).
  - `families.procurement`: `LOT_DOC = "synthetic_lot"`, `Lot(branch_id, month, n, method, subject, announce, start, final, dur, cancelled, stuck, evaluating, supplier)`, `lots_for(model, branch, month) -> list[Lot]` (as_of'ga bog'liq emas), `lot_state(lot, as_of) -> tuple[str, date] | None` (holat va qator sanasi; e'lon as_of'dan keyin — `None`), `year_plan(model, branch, year) -> float` (yil lotlari boshlang'ich narxi × 1,4), `generate(model, window, sink) -> {"fact_procurement": n}`. `src_id`: `LOT-{branch:02d}-{YYYYMM}-{n}`, `PLAN-{branch:02d}-{YYYY}`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_synthetic_s4.py`:
```python
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families import procurement
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES, PROCUREMENT_SUBJECTS
from app.etl.types import Window
from app.etl.zakupki import codes
from tests.etl_helpers import TEST_AS_OF


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


YEAR = Window(date(2026, 1, 1), TEST_AS_OF)
MODEL = SynthModel(7, TEST_AS_OF)


def _collect(family: Any, window: Window = YEAR) -> list[dict[str, Any]]:
    sink = CollectSink()
    family.generate(MODEL, window, sink)
    return [r for _, r in sink.rows]


def test_lot_rows_use_codes_and_consistent_amounts() -> None:
    rows = [r for r in _collect(procurement) if r["doc_type"] == procurement.LOT_DOC]
    assert rows and {r["status"] for r in rows} <= set(codes.STATUSES) - {codes.PLAN_STATUS}
    assert {r["method"] for r in rows} <= set(codes.METHODS)
    for r in rows:
        assert YEAR.contains_id(r["date_id"])
        assert r["nom_code"].startswith("PS-") and r["start_price"] > 0
        if r["status"] == codes.DONE:
            assert r["contract_price"] is not None and r["contract_price"] <= r["start_price"]
            assert r["cp_code"].startswith("CP-") and r["procedure_days"] >= 3
        else:
            assert r["contract_price"] is None and r["cp_code"] is None
            assert r["procedure_days"] is None


def test_in_work_lots_include_overdue_ones() -> None:
    rows = [r for r in _collect(procurement) if r["status"] in codes.IN_WORK]
    assert rows
    overdue = [r for r in rows
               if (TEST_AS_OF - date(r["date_id"] // 10000, r["date_id"] // 100 % 100,
                                     r["date_id"] % 100)).days
               > codes.DEFAULT_METHOD_NORMS[r["method"]] + codes.LATE_MARGIN_DAYS]
    assert overdue, "sintetik ma'lumotda kechikkan lotlar bo'lishi kerak (qoida demosi)"


def test_year_plan_rows() -> None:
    plans = [r for r in _collect(procurement) if r["doc_type"] == codes.PLAN_DOC]
    assert len(plans) == len(BRANCHES)
    assert {r["date_id"] for r in plans} == {20260101}
    for r in plans:
        assert (r["status"], r["method"], r["contract_price"]) == (codes.PLAN_STATUS,
                                                                   codes.PLAN_METHOD, None)
    branch = BRANCHES[1]
    expected = procurement.year_plan(MODEL, branch, 2026)
    got = next(r for r in plans if r["branch_code"] == branch.code)["start_price"]
    assert got == Decimal(f"{expected:.2f}")
    # Reja butun yil lotlaridan (kelajak oylar ham) — as_of'ga bog'liq emas.
    assert expected == procurement.year_plan(SynthModel(7, date(2026, 12, 31)), branch, 2026)


def test_lot_state_rules() -> None:
    branch = BRANCHES[1]
    lots = [lot for m in MODEL.months() for lot in procurement.lots_for(MODEL, branch, m)]
    for lot in lots:
        state = procurement.lot_state(lot, TEST_AS_OF)
        if lot.announce > TEST_AS_OF:
            assert state is None
            continue
        assert state is not None
        status, day = state
        assert day <= TEST_AS_OF
        if status == codes.DONE:
            assert day == lot.contract_day
        else:
            assert day == lot.announce


def test_subject_dims_and_determinism() -> None:
    sink = CollectSink()
    SyntheticConnector(seed=7, as_of=TEST_AS_OF).extract(YEAR, sink)
    subjects = {r["code"]: r for t, r in sink.rows
                if t == "dim_nomenclature" and r["code"].startswith("PS-")}
    assert [subjects[f"PS-{i:02d}"]["category"] for i in range(1, 8)] == list(
        PROCUREMENT_SUBJECTS)
    assert _collect(procurement) == _collect(procurement)
```

`backend/tests/test_synthetic.py` — `test_extract_respects_window_and_reports_all_targets` ichida (S3 qo'shgan assert'dan keyin) qo'shing:
```python
    assert "fact_procurement" in stats.by_target
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_synthetic_s4.py -v`
Expected: FAIL — `ImportError: cannot import name 'procurement' from 'app.etl.synthetic.families'`.

- [ ] **Step 3: Ma'lumotnoma**

`backend/app/etl/synthetic/reference.py` — fayl oxiriga (`share` funksiyasidan OLDIN) qo'shing:
```python
# Prototip «procurement data» PMETH: (usul kodi, og'irlik, tejash diapazoni, davomiylik kunlari).
METHOD_PROFILES: tuple[tuple[str, float, tuple[float, float], tuple[int, int]], ...] = (
    ("eshop", 0.35, (0.03, 0.12), (5, 15)),
    ("contest", 0.20, (0.04, 0.14), (20, 40)),
    ("tender", 0.12, (0.05, 0.18), (35, 70)),
    ("exchange", 0.13, (0.02, 0.08), (7, 20)),
    ("direct", 0.20, (0.0, 0.02), (3, 12)),
)
# Prototip PCAT — xarid predmetlari (dim_nomenclature PS-01…07, kategoriya = nom).
PROCUREMENT_SUBJECTS: tuple[str, ...] = (
    "Запасные части", "Ремонтные услуги", "Строительно-монтажные работы",
    "Электротехническое оборудование", "ГСМ и масла", "ИТ и связь", "Спецодежда и СИЗ",
)
```

`backend/app/etl/synthetic/families/dims.py` — importdagi ro'yxatga `PROCUREMENT_SUBJECTS` qo'shing va `emit("dim_nomenclature", [...])` chaqiruvini to'liq almashtiring:
```python
    emit("dim_nomenclature", [
        *({"code": f"NOM-{n:03d}", "name": name, "category": STOCK_CATEGORIES[cat],
           "unit": unit, "enbt_code": f"ЕНБТ-{cat + 1:02d}-{n:03d}"}
          for n, (name, cat, unit, _price) in enumerate(NOMENCLATURE, start=1)),
        # S4: xarid predmetlari (fact_procurement.nom_code).
        *({"code": f"PS-{n:02d}", "name": subject, "category": subject, "unit": "—",
           "enbt_code": None}
          for n, subject in enumerate(PROCUREMENT_SUBJECTS, start=1)),
    ])
```

- [ ] **Step 4: Implementatsiya — xaridlar oilasi**

`backend/app/etl/synthetic/families/procurement.py`:
```python
"""fact_procurement (lot; yillik reja — 1-yanvar) — prototip «procurement data».

Lot parametrlari (usul, predmet, e'lon kuni, narx, tejash, davomiylik, taqdir) as_of'ga bog'liq
emas; holat as_of bo'yicha: bekor qilingan (6%), tuzilgan (e'lon + davomiylik ≤ as_of), aks holda
«в работе». Oxirgi 75 kundagi lotlarning 30% i «tiqilib qolgan» — kechikkan lotlar demosi.
Yillik reja = yilning barcha lotlari boshlang'ich narxi × 1,4 (prototip `zPlan`).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import (
    BRANCHES,
    EXPENSE_ITEMS,
    HQ_ID,
    METHOD_PROFILES,
    PROCUREMENT_SUBJECTS,
    SUPPLIER_CODES,
    BranchRef,
    share,
)
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window
from app.etl.zakupki.codes import CANCELLED, DONE, IN_WORK, PLAN_DOC, PLAN_METHOD, PLAN_STATUS

LOT_DOC = "synthetic_lot"
_SCALE_ITEMS = ("PKM54-O01", "PKM54-O02", "PKM54-O06", "PKM54-O07")  # prototip exc[0,1,5,6]
_STUCK_DAYS = 75


@dataclass(frozen=True, slots=True)
class Lot:
    branch_id: int
    month: date
    n: int
    method: str
    subject: int
    announce: date
    start: float
    final: float
    dur: int
    cancelled: bool
    stuck: bool
    evaluating: bool
    supplier: str

    @property
    def contract_day(self) -> date:
        return self.announce + timedelta(days=self.dur)


def _scale(branch: BranchRef) -> float:
    return sum(e.base * share(branch, e.hq_share) for e in EXPENSE_ITEMS if e.code in _SCALE_ITEMS)


def lots_for(model: SynthModel, branch: BranchRef, month: date) -> list[Lot]:
    ym = month_id(month)
    r = rnd(model.seed, "lots", branch.id, ym)
    count = r.randint(2, 4) if branch.id == HQ_ID else r.randint(1, 3)
    days = calendar.monthrange(month.year, month.month)[1]
    out: list[Lot] = []
    for n in range(1, count + 1):
        lr = rnd(model.seed, "lot", branch.id, ym, n)
        pick, method = lr.random(), METHOD_PROFILES[-1]
        for profile in METHOD_PROFILES:  # og'irlik bo'yicha tanlash (prototip PMETH)
            if pick < profile[1]:
                method = profile
                break
            pick -= profile[1]
        code, _weight, eco, dur = method
        subject = lr.randrange(len(PROCUREMENT_SUBJECTS))
        start = _scale(branch) * lr.uniform(0.05, 0.45) * (1.8 if subject == 2 else 1.0)
        out.append(Lot(
            branch_id=branch.id, month=month, n=n, method=code, subject=subject,
            announce=month + timedelta(days=lr.randrange(days)), start=start,
            final=start * (1 - lr.uniform(*eco)), dur=lr.randint(*dur),
            cancelled=lr.random() < 0.06, stuck=lr.random() < 0.3,
            evaluating=lr.random() < 0.5, supplier=lr.choice(SUPPLIER_CODES)))
    return out


def lot_state(lot: Lot, as_of: date) -> tuple[str, date] | None:
    if lot.announce > as_of:
        return None
    in_work = IN_WORK[1] if lot.evaluating else IN_WORK[0]
    if lot.cancelled:
        return (CANCELLED, lot.announce) if lot.announce + timedelta(days=5) <= as_of else (
            in_work, lot.announce)
    if lot.stuck and lot.announce >= as_of - timedelta(days=_STUCK_DAYS):
        return in_work, lot.announce
    if lot.contract_day <= as_of:
        return DONE, lot.contract_day
    return in_work, lot.announce


def year_plan(model: SynthModel, branch: BranchRef, year: int) -> float:
    return sum(lot.start for m in range(1, 13)
               for lot in lots_for(model, branch, date(year, m, 1))) * 1.4


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for branch in BRANCHES:
        for year in range(model.history_start.year, model.as_of.year + 1):
            jan = date(year, 1, 1)
            if window.contains(jan):
                sink.add("fact_procurement", {
                    "doc_type": PLAN_DOC, "src_id": f"PLAN-{branch.id:02d}-{year}",
                    "date_id": date_id(jan), "branch_code": branch.code, "nom_code": None,
                    "cp_code": None, "lot_no": f"ПЛАН-{year}", "method": PLAN_METHOD,
                    "status": PLAN_STATUS, "start_price": money(year_plan(model, branch, year)),
                    "contract_price": None, "procedure_days": None})
                count += 1
        for month in model.months():
            for lot in lots_for(model, branch, month):
                state = lot_state(lot, model.as_of)
                if state is None or not window.contains(state[1]):
                    continue
                status, day = state
                done = status == DONE
                sink.add("fact_procurement", {
                    "doc_type": LOT_DOC,
                    "src_id": f"LOT-{branch.id:02d}-{month_id(month)}-{lot.n}",
                    "date_id": date_id(day), "branch_code": branch.code,
                    "nom_code": f"PS-{lot.subject + 1:02d}",
                    "cp_code": lot.supplier if done else None,
                    "lot_no": f"{month.year}-{branch.id:02d}{month.month:02d}{lot.n}",
                    "method": lot.method, "status": status, "start_price": money(lot.start),
                    "contract_price": money(lot.final) if done else None,
                    "procedure_days": lot.dur if done else None})
                count += 1
    return {"fact_procurement": count}
```

- [ ] **Step 5: Reyestr**

`backend/app/etl/synthetic/families/__init__.py` — import qatoriga `procurement` ni qo'shing (S3'dan keyingi holat, alifbo tartibida):
```python
from app.etl.synthetic.families import (
    calendar,
    cash,
    debt,
    dims,
    funds,
    fx,
    loans,
    payments,
    procurement,
    production,
    stock,
)
```
va `FAMILIES` ro'yxati oxiriga qo'shing:
```python
    ("procurement", procurement.generate),
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_synthetic_s4.py tests/test_synthetic.py tests/test_synthetic_s3.py -v`
Expected: barcha testlar passed — `test_full_synthetic_pipeline` (0016 CHECK'lari bilan) `success`, `test_incremental_rerun_changes_nothing` — `rows_upserted == 0`.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(etl): sintetik xaridlar — lotlar, yillik reja, predmetlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 3: `SyntheticConnector` — АИП (obyektlar, oylik reja/fakt, КС-2, avanslar, bosqichlar) va kadrlar oilalari

**Files:**
- Create: `backend/app/etl/synthetic/families/investment.py`, `backend/app/etl/synthetic/families/hr.py`
- Modify: `backend/app/etl/synthetic/families/__init__.py`, `backend/tests/test_synthetic.py`
- Test: `backend/tests/test_synthetic_s4.py` (davomi)

**Interfaces:**
- Consumes: `SynthModel`, `BRANCHES`, `HQ_ID`, `OBJECTS`, `FUNDS`, `POSITIONS`, `rnd`, `money`, `date_id`, `month_id`, `month_end`, `StagingSink`, `Window`.
- Produces:
  - `families.investment`: `MONTH_DOC = "aip_month"`, `OPEN_DOC = "aip_opening"`, `STAGE_DOC = "aip_stage"`, `STAGES` (7, prototip), `YEAR_SHARE = {2025: 0.8, 2026: 1.0}`, `annual_plan(n, year) -> float` (mln), `monthly_plan(n, month) -> float`, `opening(model, n) -> float`, `generate(model, window, sink) -> {"fact_investment": n, "fact_object_stage": n}`. `fact_investment` sanasi — oyning 1-kuni (joriy yil dekabrigacha; forward: `date ≥ window.date_from`), `src_id` `INV-{n:02d}-{YYYYMM}`, `OPEN-{n:02d}`; bosqich `STG-{n:02d}-{k}`.
  - `families.hr`: `HR_DOC = "hr_month"`, `SHARES = (0.08, 0.22, 0.42, 0.28)`, `staff(model, branch) -> tuple[int, int]` (штат, факт), `split(total) -> list[int]` (toifalar, qoldiq oxirgisiga), `generate(model, window, sink) -> {"fact_hr": n}`. Sana — oy oxiri (ochiq oyda as_of), `src_id` `HR-{branch:02d}-{pos}-{YYYYMM}`, `payroll = 0` (ФОТ pul oqimidan).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_synthetic_s4.py` — importlarga `investment, hr` ni qo'shing (`from app.etl.synthetic.families import hr, investment, procurement`) va `from app.etl.synthetic.reference import BRANCHES, HQ_ID, OBJECTS, POSITIONS, PROCUREMENT_SUBJECTS`; fayl oxiriga:
```python
FULL = Window(date(2024, 1, 1), TEST_AS_OF)


def _by_target(family: Any, window: Window) -> dict[str, list[dict[str, Any]]]:
    sink = CollectSink()
    family.generate(MODEL, window, sink)
    out: dict[str, list[dict[str, Any]]] = {}
    for target, row in sink.rows:
        out.setdefault(target, []).append(row)
    return out


def test_investment_rows_cover_year_and_stay_within_cost() -> None:
    rows = _by_target(investment, FULL)
    inv = rows["fact_investment"]
    months = [r for r in inv if r["doc_type"] == investment.MONTH_DOC]
    assert {r["date_id"] // 100 for r in months} == {
        y * 100 + m for y in (2025, 2026) for m in range(1, 13)}
    assert all(r["date_id"] % 100 == 1 for r in months)  # oyning 1-kuni
    future = [r for r in months if r["date_id"] > 20260924]
    assert future and all(r["fact"] == 0 and r["physical_pct"] is None for r in future)
    openings = [r for r in inv if r["doc_type"] == investment.OPEN_DOC]
    assert len(openings) == len(OBJECTS) and {r["date_id"] for r in openings} == {20240101}
    for n, obj in enumerate(OBJECTS, start=1):
        total = Decimal(obj[4] * 1000)
        spent = sum(r["fact"] for r in inv if r["object_code"] == f"OBJ-{n:02d}")
        assert Decimal(0) < spent < total, n
        plan26 = sum(r["plan"] for r in months if r["object_code"] == f"OBJ-{n:02d}"
                     and r["date_id"] // 10000 == 2026)
        assert abs(plan26 - Decimal(obj[5] * 1000)) < Decimal("0.1"), n
        assert all(r["branch_code"] == BRANCHES[obj[1]].code for r in inv
                   if r["object_code"] == f"OBJ-{n:02d}")
    phys = [r["physical_pct"] for r in months if r["physical_pct"] is not None]
    assert phys and all(Decimal(0) < p <= Decimal("0.98") for p in phys)
    adv = [r for r in months if r["advance"] > 0]
    assert adv and all(r["advance_date_id"] is not None for r in adv)


def test_investment_forward_emission_and_stages() -> None:
    inc = _by_target(investment, Window(date(2026, 8, 1), TEST_AS_OF))
    dates = {r["date_id"] for r in inc["fact_investment"]}
    assert min(dates) == 20260801 and max(dates) == 20261201
    stages = _by_target(investment, FULL)["fact_object_stage"]
    assert len(stages) == len(OBJECTS) * len(investment.STAGES)
    for r in stages:
        assert 1 <= r["stage_no"] <= 7 and r["stage_name"] in investment.STAGES
        if r["fact_date_id"] is not None:
            assert r["fact_date_id"] <= 20260924


def test_hr_rows() -> None:
    rows = _by_target(hr, Window(date(2026, 8, 1), TEST_AS_OF))["fact_hr"]
    assert {r["date_id"] for r in rows} == {20260831, 20260924}
    assert len(rows) == len(BRANCHES) * len(POSITIONS) * 2
    hq = [r for r in rows if r["branch_code"] == BRANCHES[HQ_ID - 1].code
          and r["date_id"] == 20260831]
    assert sum(r["headcount_plan"] for r in hq) == 182
    for r in rows:
        assert Decimal(0) <= r["headcount_fact"] <= r["headcount_plan"] + 1
        assert r["hired"] >= 0 and r["fired"] >= 0 and r["overtime_hours"] >= 0
        assert r["payroll"] == 0 and r["pos_code"] in {p[0] for p in POSITIONS}
    assert hr.split(100) == [8, 22, 42, 28] and sum(hr.split(97)) == 97


def test_s4_families_deterministic() -> None:
    assert _by_target(investment, FULL) == _by_target(investment, FULL)
    assert _by_target(hr, FULL) == _by_target(hr, FULL)
```

`backend/tests/test_synthetic.py` — 2-vazifada qo'shilgan qatordan keyin:
```python
    assert {"fact_investment", "fact_object_stage", "fact_hr"} <= set(stats.by_target)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_synthetic_s4.py -v`
Expected: FAIL — `ImportError: cannot import name 'hr' from 'app.etl.synthetic.families'`.

- [ ] **Step 3: Implementatsiya — АИП**

`backend/app/etl/synthetic/families/investment.py`:
```python
"""fact_investment (obyekt × oy, sana — oyning 1-kuni) va fact_object_stage — prototip «investments
(Адреса)»: 14 obyekt, yillik reja 2025 — 0,8 × 2026 rejasi, oylik og'irliklar 0,6 + 0,08 × oy,
fakt = reja × obyekt koeffitsienti (0,62–1,05) × tebranish, joriy oy — o'tgan kunlar ulushi.

Ochilish (OPEN_DOC, tarix boshi) — obyektning 2025 yilgacha to'plangan moliyalashtirishi, umumiy
qiymatdan oshmasligi uchun cheklangan. КС-2 foizi = min(0,98; moliyaviy bajarilish × koeff).
Avans: 2026 yil mart–avgustda berilib, 60–200 kundan keyin yopiladi (qoldiq oy oxirida).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, FUNDS, OBJECTS
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

MONTH_DOC = "aip_month"
OPEN_DOC = "aip_opening"
STAGE_DOC = "aip_stage"
STAGES = ("Проектно-сметная документация", "Экспертиза", "Тендер и договор",
          "Строительно-монтажные работы", "Поставка оборудования", "Пусконаладка",
          "Ввод в эксплуатацию")
YEAR_SHARE = {2025: 0.8, 2026: 1.0}
_WEIGHTS = [0.6 + m * 0.08 for m in range(12)]
_PCT = Decimal("0.0001")


def annual_plan(n: int, year: int) -> float:
    return OBJECTS[n - 1][5] * 1000 * YEAR_SHARE.get(year, 0.0)


def monthly_plan(n: int, month: date) -> float:
    return annual_plan(n, month.year) * _WEIGHTS[month.month - 1] / sum(_WEIGHTS)


def opening(model: SynthModel, n: int) -> float:
    total, plan = OBJECTS[n - 1][4] * 1000, OBJECTS[n - 1][5] * 1000
    cap = total - 1.2 * 1.8 * plan  # 2025–2026 faktining yuqori chegarasi
    return max(0.0, min(total * rnd(model.seed, "invopen", n).uniform(0.1, 0.3), cap))


def _fact(model: SynthModel, n: int, month: date) -> float:
    if month > model.as_of:
        return 0.0
    ratio = rnd(model.seed, "invratio", n).uniform(0.62, 1.05)
    value = monthly_plan(n, month) * ratio * rnd(model.seed, "invfact", n,
                                                  month_id(month)).uniform(0.88, 1.12)
    if (month.year, month.month) == (model.as_of.year, model.as_of.month):
        value *= model.as_of.day / calendar.monthrange(month.year, month.month)[1]
    return value


def _months(model: SynthModel) -> list[date]:
    return [date(y, m, 1) for y in sorted(YEAR_SHARE) if y <= model.as_of.year
            for m in range(1, 13)]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    inv = stages = 0
    for n, (_name, b, _kind, src, total_bn, _plan, _deadline) in enumerate(OBJECTS, start=1):
        code, branch, total = f"OBJ-{n:02d}", BRANCHES[b].code, total_bn * 1000
        base = {"branch_code": branch, "object_code": code, "source_code": FUNDS[src][0]}
        start = opening(model, n)
        if model.history_start >= window.date_from:
            sink.add("fact_investment", {
                **base, "doc_type": OPEN_DOC, "src_id": f"OPEN-{n:02d}",
                "date_id": date_id(model.history_start), "plan": money(0), "fact": money(start),
                "physical_pct": None, "advance": money(0), "advance_date_id": None})
            inv += 1
        ar = rnd(model.seed, "adv", n)
        issued = date(2026, ar.randint(3, 8), ar.randint(1, 28))
        amount = annual_plan(n, 2026) * ar.uniform(0.0, 0.08)
        closed = issued + timedelta(days=ar.randint(60, 200))
        phys_k = rnd(model.seed, "phys", n).uniform(0.72, 1.02)
        cumulative = start
        for month in _months(model):
            fact = _fact(model, n, month)
            cumulative += fact
            elapsed = month <= model.as_of
            end = model.period_end(month) if elapsed else month
            open_adv = elapsed and issued <= end < closed and amount >= 0.01
            if month < window.date_from.replace(day=1):
                continue
            phys = (Decimal(str(min(0.98, cumulative / total * phys_k))).quantize(_PCT)
                    if elapsed else None)
            sink.add("fact_investment", {
                **base, "doc_type": MONTH_DOC, "src_id": f"INV-{n:02d}-{month_id(month)}",
                "date_id": date_id(month), "plan": money(monthly_plan(n, month)),
                "fact": money(fact), "physical_pct": phys,
                "advance": money(amount if open_adv else 0),
                "advance_date_id": date_id(issued) if open_adv else None})
            inv += 1
        sr = rnd(model.seed, "stages", n)
        done_upto = int(sr.uniform(2.2, 6.4))
        for k, stage_name in enumerate(STAGES):
            planned = date(2026, min(12, k + 2), 15)
            actual = planned + timedelta(days=sr.randint(-10, 40))
            done = k <= done_upto and actual <= model.as_of
            if planned < window.date_from:
                continue
            sink.add("fact_object_stage", {
                "doc_type": STAGE_DOC, "src_id": f"STG-{n:02d}-{k + 1}",
                "date_id": date_id(planned), "branch_code": branch, "object_code": code,
                "stage_no": k + 1, "stage_name": stage_name,
                "fact_date_id": date_id(actual) if done else None})
            stages += 1
    return {"fact_investment": inv, "fact_object_stage": stages}
```

- [ ] **Step 4: Implementatsiya — kadrlar**

`backend/app/etl/synthetic/families/hr.py`:
```python
"""fact_hr (filial × toifa × oy; sana — oy oxiri yoki as_of) — prototip «HR data».

Штат: HQ 182, stansiyalar 40 + quvvat / 5 + vazn × 45; fakt = штат × (0,86–1,0); toifalar ulushi
prototip HSH. Qabul/bo'shatish/ish vaqtidan tashqari soatlar oylik, joriy oyda o'tgan kunlar ulushi.
ФОТ bu yerda 0 — ko'rsatkich pul oqimidan (PKM54-O05) olinadi (S4 spec 3.3). ФИО yo'q.
"""

from __future__ import annotations

import calendar
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES, HQ_ID, POSITIONS, BranchRef
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

HR_DOC = "hr_month"
SHARES = (0.08, 0.22, 0.42, 0.28)


def staff(model: SynthModel, branch: BranchRef) -> tuple[int, int]:
    plan = 182 if branch.id == HQ_ID else round(40 + (branch.capacity or 60) / 5
                                                 + branch.weight * 45)
    return plan, round(plan * rnd(model.seed, "hrfill", branch.id).uniform(0.86, 1.0))


def split(total: int) -> list[int]:
    parts = [round(total * s) for s in SHARES[:-1]]
    return [*parts, total - sum(parts)]


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    count = 0
    for branch in BRANCHES:
        plan, fact = staff(model, branch)
        plans, facts = split(plan), split(fact)
        for month in model.months():
            end = model.period_end(month)
            if not window.contains(end):
                continue
            part = end.day / calendar.monthrange(month.year, month.month)[1]
            for i, (pos, _cat, _dep) in enumerate(POSITIONS):
                r = rnd(model.seed, "hr", branch.id, i, month_id(month))
                people = facts[i]
                sink.add("fact_hr", {
                    "doc_type": HR_DOC, "src_id": f"HR-{branch.id:02d}-{i + 1}-{month_id(month)}",
                    "date_id": date_id(end), "branch_code": branch.code, "pos_code": pos,
                    "headcount_plan": Decimal(plans[i]), "headcount_fact": Decimal(people),
                    "payroll": Decimal("0.00"),
                    "hired": round(r.uniform(0, people * 0.012) * part),
                    "fired": round(r.uniform(0, people * 0.014) * part),
                    "overtime_hours": Decimal(f"{people * r.uniform(0.4, 1.8) * part:.1f}")})
                count += 1
    return {"fact_hr": count}
```

- [ ] **Step 5: Reyestr**

`backend/app/etl/synthetic/families/__init__.py` — import ro'yxatiga `hr` (`fx` dan keyin) va `investment` (`hr` dan keyin) ni qo'shing, `FAMILIES` oxiriga:
```python
    ("investment", investment.generate),
    ("hr", hr.generate),
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_synthetic_s4.py tests/test_synthetic.py -v`
Expected: barcha testlar passed — to'liq sintetik yuklash `success` (forward `fact_investment`/`fact_object_stage` kelajak qatorlari bilan), qayta inkremental yuklash `rows_upserted == 0`.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(etl): sintetik АИП (reja/fakt, КС-2, avanslar, bosqichlar) va kadrlar oilalari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 4: Xarid agregatlari (0017) — lotlar reyestri (kunlar, normativ, kechikish) va yillik reja

**Files:**
- Create: `backend/migrations/versions/0017_mart_procurement.py`, `backend/app/dwh/procurement_aggregates.py`, `backend/tests/s4_helpers.py`
- Modify: `backend/app/dwh/aggregates.py` (oxirida import)
- Test: `backend/tests/test_procurement_aggregates.py`

**Interfaces:**
- Consumes: `register`, `Aggregate`, `BuildParams.bind` (`:build_id, :as_of, :from_id, :as_of_id`), `builds`, `codes.*`, `core.settings` (`zakupki.method_norms`, `is_current`), `tests.etl_helpers.*` (`branch_row`, `stage`, `merge_all`, `open_run`, `new_tag`), `tests.s1_helpers.rebuild`, `tests.s2_helpers.put_setting`.
- Produces:
  - `mart|pub.agg_procurement_lots (branch_id > 0, month_id, lot_src, date_id, lot_no, method, status, start_price, contract_price, days, norm_days, overdue, subject, supplier)` — `procurement_plan` qatorlaridan tashqari barcha lotlar (`from_id … as_of_id`); `days`: «в работе» — `as_of − sana`, qolganlari — `procedure_days`; `norm_days` — build vaqtidagi `zakupki.method_norms` (yo'q bo'lsa `DEFAULT_METHOD_NORMS`); `overdue = в работе AND days > norm_days + 10`; `subject` — `dim_nomenclature.category` yoki `—`; `supplier` — `dim_counterparty.name`.
  - `mart|pub.agg_procurement_plan (branch_id ≥ 0, month_id = YYYY01, plan)`.
  - `app.dwh.procurement_aggregates`: `PROCUREMENT_LOTS`, `PROCUREMENT_PLAN`.
  - `tests.s4_helpers`: `ProcScenario(source, tag, branch_id, branch_code, run_id, build_id)`, `procurement_rows(tag)`, `procurement_scenario(source, *, publish=False) -> ProcScenario`.

Ssenariy (as_of = 2026-09-24; mln so'm; filial `T-<tag>`; normativlar standart) — 7, 10, 13-vazifa testlari shu qiymatlardan:

| Lot | Usul | Holat | Sana | Нач. цена | Договор | Kun | Поставщик | Predmet |
|---|---|---|---|---|---|---|---|---|
| L1 | eshop | договор заключён | 2026-08-10 | 100 | 90 | 12 | S1 | Запасные части |
| L2 | direct | договор заключён | 2026-08-20 | 50 | 50 | 5 | S2 | Ремонтные услуги |
| L3 | tender | договор заключён | 2026-09-05 | 200 | 170 | 60 | S1 | Строительно-монтажные работы |
| L4 | contest | объявлен | 2026-07-01 | 80 | — | (85) | — | Строительно-монтажные работы |
| L5 | eshop | на оценке | 2026-09-10 | 30 | — | (14) | — | Запасные части |
| L6 | exchange | отменён | 2026-08-15 | 40 | — | — | — | Запасные части |
| L7 | eshop | договор заключён | 2026-02-10 | 60 | 57 | 10 | S2 | Запасные части |
| L8 | direct | договор заключён | 2025-08-12 | 20 | 20 | 4 | S2 | Ремонтные услуги |
Reja: 2026-01-01 — 1000, 2025-01-01 — 500. L4 kechikkan (85 > 40 + 10), L5 — yo'q (14 ≤ 25).

- [ ] **Step 1: Test yordamchisi — xarid ssenariysi**

`backend/tests/s4_helpers.py`:
```python
"""S4 testlari uchun qo'lda hisoblanadigan ssenariylar (jadvallar — rejaning 4–6-vazifalarida)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.etl.db import etl_transaction
from tests.etl_helpers import branch_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild

DONE, ANNOUNCED, EVAL, CANCELLED = "договор заключён", "объявлен", "на оценке", "отменён"


def _branch_id(code: str) -> int:
    with etl_transaction() as conn:
        return int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                {"c": code}).scalar_one())


@dataclass(frozen=True, slots=True)
class ProcScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int


def procurement_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]

    def nom(key: str, subject: str) -> dict[str, Any]:
        return {"code": f"{key}-{tag}", "name": subject, "category": subject, "unit": "—",
                "enbt_code": None}

    def lot(src: str, day: int, method: str, status: str, start: float,
            contract: float | None, days: int | None, sup: str | None,
            subj: str) -> dict[str, Any]:
        return {"doc_type": "portal_lot", "src_id": src, "date_id": day, "branch_code": code,
                "nom_code": f"{subj}-{tag}", "cp_code": f"{sup}-{tag}" if sup else None,
                "lot_no": src.upper(), "method": method, "status": status,
                "start_price": start, "contract_price": contract, "procedure_days": days}

    def plan(src: str, day: int, amount: float) -> dict[str, Any]:
        return {"doc_type": "procurement_plan", "src_id": src, "date_id": day,
                "branch_code": code, "nom_code": None, "cp_code": None, "lot_no": "ПЛАН",
                "method": "plan", "status": "план", "start_price": amount,
                "contract_price": None, "procedure_days": None}

    return {
        "dim_branch": [branch],
        "dim_nomenclature": [nom("SP1", "Запасные части"), nom("SP2", "Ремонтные услуги"),
                             nom("SP3", "Строительно-монтажные работы")],
        "dim_counterparty": [
            {"code": f"S1-{tag}", "name": f"ООО «Поставщик-1 {tag}»", "kind": "supplier",
             "inn": "301111111"},
            {"code": f"S2-{tag}", "name": f"ООО «Поставщик-2 {tag}»", "kind": "supplier",
             "inn": "301111112"}],
        "fact_procurement": [
            lot("l1", 20260810, "eshop", DONE, 100, 90, 12, "S1", "SP1"),
            lot("l2", 20260820, "direct", DONE, 50, 50, 5, "S2", "SP2"),
            lot("l3", 20260905, "tender", DONE, 200, 170, 60, "S1", "SP3"),
            lot("l4", 20260701, "contest", ANNOUNCED, 80, None, None, None, "SP3"),
            lot("l5", 20260910, "eshop", EVAL, 30, None, None, None, "SP1"),
            lot("l6", 20260815, "exchange", CANCELLED, 40, None, None, None, "SP1"),
            lot("l7", 20260210, "eshop", DONE, 60, 57, 10, "S2", "SP1"),
            lot("l8", 20250812, "direct", DONE, 20, 20, 4, "S2", "SP2"),
            plan("p26", 20260101, 1000), plan("p25", 20250101, 500),
        ],
    }


def procurement_scenario(source: str, *, publish: bool = False) -> ProcScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, procurement_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    return ProcScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id)
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_procurement_aggregates.py`:
```python
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from app.etl.zakupki.codes import DEFAULT_METHOD_NORMS
from tests.etl_helpers import new_source, purge_source
from tests.s1_helpers import rebuild
from tests.s2_helpers import put_setting
from tests.s4_helpers import ProcScenario, procurement_scenario

TABLES = ("agg_procurement_lots", "agg_procurement_plan")


@pytest.fixture
def sc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _lots(build_id: int, branch_id: int) -> dict[str, dict[str, Any]]:
    rows = _rows("SELECT * FROM mart.agg_procurement_lots "
                 "WHERE build_id = :b AND branch_id = :br", b=build_id, br=branch_id)
    return {r["lot_no"]: r for r in rows}


def test_lot_registry(sc: ProcScenario) -> None:
    lots = _lots(sc.build_id, sc.branch_id)
    assert set(lots) == {f"L{i}" for i in range(1, 9)}  # reja qatorlari reyestrga kirmaydi
    l4, l5, l1 = lots["L4"], lots["L5"], lots["L1"]
    assert (l4["days"], l4["norm_days"], l4["overdue"], l4["month_id"]) == (85, 40, True, 202607)
    assert (l5["days"], l5["norm_days"], l5["overdue"]) == (14, 15, False)
    assert (l1["days"], l1["overdue"], float(l1["contract_price"])) == (12, False, 90.0)
    assert l1["supplier"] == f"ООО «Поставщик-1 {sc.tag}»" and l1["subject"] == "Запасные части"
    assert lots["L6"]["days"] is None and lots["L6"]["supplier"] is None
    assert lots["L8"]["month_id"] == 202508 and lots["L3"]["date_id"] == 20260905


def test_year_plan(sc: ProcScenario) -> None:
    rows = _rows("SELECT month_id, plan FROM mart.agg_procurement_plan WHERE build_id = :b "
                 "AND branch_id = :br ORDER BY month_id", b=sc.build_id, br=sc.branch_id)
    assert [(r["month_id"], float(r["plan"])) for r in rows] == [(202501, 500.0),
                                                                 (202601, 1000.0)]
    total = _rows("SELECT plan FROM mart.agg_procurement_plan WHERE build_id = :b "
                  "AND branch_id = 0 AND month_id = 202601", b=sc.build_id)
    assert float(total[0]["plan"]) >= 1000.0


def test_norm_change_applies_on_next_build(sc: ProcScenario) -> None:
    try:
        put_setting("zakupki.method_norms", {**DEFAULT_METHOD_NORMS, "contest": 80})
        build_id = rebuild(sc.run_id)
        l4 = _lots(build_id, sc.branch_id)["L4"]
        assert (l4["norm_days"], l4["overdue"]) == (80, False)  # 85 ≤ 80 + 10
        assert _lots(sc.build_id, sc.branch_id)["L4"]["overdue"] is True  # eski build o'zgarmaydi
    finally:
        put_setting("zakupki.method_norms", DEFAULT_METHOD_NORMS)


def test_rls_and_failed_build(sc: ProcScenario) -> None:
    for table in TABLES:
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM mart.{table} "
                                      "WHERE build_id = :b"), {"b": sc.build_id}).scalars())
        assert seen == {sc.branch_id}, table
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
        for table in TABLES:
            count = conn.execute(text(f"SELECT count(*) FROM mart.{table} WHERE build_id = :b"),
                                 {"b": sc.build_id}).scalar_one()
            assert count == 0, table
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_procurement_aggregates.py -v`
Expected: FAIL — `relation "mart.agg_procurement_lots" does not exist`.

- [ ] **Step 4: 0017 migratsiyasi**

`backend/migrations/versions/0017_mart_procurement.py`:
```python
"""S4: xaridlar — lotlar reyestri snapshot'i va yillik reja

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-25
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_procurement_lots", "agg_procurement_plan")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_procurement_lots (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      lot_src varchar(200) NOT NULL,
      date_id integer NOT NULL,
      lot_no varchar(64) NOT NULL,
      method varchar(32) NOT NULL,
      status varchar(32) NOT NULL,
      start_price {MONEY},
      contract_price numeric(20,2),
      days integer,
      norm_days integer,
      overdue boolean NOT NULL DEFAULT false,
      subject varchar(100) NOT NULL,
      supplier varchar(300),
      PRIMARY KEY (build_id, branch_id, lot_src)
    )
    """,
    "CREATE INDEX agg_procurement_lots_month_idx ON mart.agg_procurement_lots (build_id, month_id)",
    f"""
    CREATE TABLE mart.agg_procurement_plan (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      plan {MONEY},
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_procurement_lots WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.lot_src, a.date_id, a.lot_no, a.method, a.status,
           a.start_price, a.contract_price, a.days, a.norm_days, a.overdue, a.subject, a.supplier
    FROM mart.agg_procurement_lots a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_procurement_plan WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.plan
    FROM mart.agg_procurement_plan a WHERE a.build_id = {ACTIVE}
    """,
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        op.execute(f"ALTER TABLE mart.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE mart.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY branch_scope ON mart.{table} USING (core.rls_branch_ok(branch_id)) "
                   "WITH CHECK (core.rls_branch_ok(branch_id))")
        op.execute(f"GRANT SELECT ON mart.{table} TO ugk_app")
        op.execute(f"GRANT SELECT, INSERT, DELETE ON mart.{table} TO ugk_etl")
        op.execute(f"GRANT SELECT ON pub.{table} TO ugk_app")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP VIEW pub.{table}")
        op.execute(f"DROP TABLE mart.{table}")
```

- [ ] **Step 5: Implementatsiya — agregatlar**

`backend/app/dwh/procurement_aggregates.py`:
```python
"""S4 xarid agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Lotlar reyestri — barcha KPI'lar manbai (bitta snapshot): «в работе» kunlari build sanasiga
(as_of − e'lon sanasi), normativ — build vaqtidagi core.settings `zakupki.method_norms` (joriy
versiya; yo'q bo'lsa standart). Kechikish TZ 4: kunlar > normativ + 10. Normativ o'zgarsa —
keyingi build'dan (eski build'lar reproduksiya qilinadigan bo'lib qoladi).
"""

from __future__ import annotations

import json

from app.dwh.aggregates import Aggregate, register
from app.etl.zakupki.codes import DEFAULT_METHOD_NORMS, IN_WORK, LATE_MARGIN_DAYS, PLAN_DOC

# Faqat kod ichidagi konstantalar (int qiymatli lug'at) — SQL literal sifatida xavfsiz.
_DEFAULT_NORMS = json.dumps(DEFAULT_METHOD_NORMS)
_IN_WORK = ", ".join(f"'{s}'" for s in IN_WORK)

_LOTS = f"""
INSERT INTO mart.agg_procurement_lots (build_id, branch_id, month_id, lot_src, date_id, lot_no,
                                       method, status, start_price, contract_price, days,
                                       norm_days, overdue, subject, supplier)
WITH norms AS (
  SELECT coalesce((SELECT s.value FROM core.settings s
                   WHERE s.key = 'zakupki.method_norms' AND s.is_current),
                  CAST('{_DEFAULT_NORMS}' AS jsonb)) AS v),
lots AS (
  SELECT p.*, d.month_id,
         CASE WHEN p.status IN ({_IN_WORK}) THEN CAST(:as_of AS date) - d.date
              ELSE p.procedure_days END AS days,
         CAST(nr.v ->> p.method AS integer) AS norm_days
  FROM dwh.fact_procurement p
  JOIN dwh.dim_date d ON d.date_id = p.date_id
  CROSS JOIN norms nr
  WHERE p.doc_type <> '{PLAN_DOC}' AND p.date_id BETWEEN :from_id AND :as_of_id)
SELECT :build_id, l.branch_id, l.month_id,
       l.src_system || ':' || l.doc_type || ':' || l.src_id, l.date_id, l.lot_no, l.method,
       l.status, l.start_price, l.contract_price, l.days, l.norm_days,
       coalesce(l.status IN ({_IN_WORK}) AND l.days > l.norm_days + {LATE_MARGIN_DAYS}, false),
       coalesce(n.category, '—'), c.name
FROM lots l
LEFT JOIN dwh.dim_nomenclature n ON n.nom_id = l.nom_id
LEFT JOIN dwh.dim_counterparty c ON c.cp_id = l.cp_id
"""

_PLAN = f"""
INSERT INTO mart.agg_procurement_plan (build_id, branch_id, month_id, plan)
SELECT :build_id, coalesce(p.branch_id, 0), d.year * 100 + 1, sum(p.start_price)
FROM dwh.fact_procurement p
JOIN dwh.dim_date d ON d.date_id = p.date_id
WHERE p.doc_type = '{PLAN_DOC}' AND p.date_id BETWEEN :from_id AND :as_of_id
GROUP BY GROUPING SETS ((p.branch_id, d.year), (d.year))
"""

PROCUREMENT_LOTS = register(Aggregate("agg_procurement_lots", (_LOTS,)))
PROCUREMENT_PLAN = register(Aggregate("agg_procurement_plan", (_PLAN,)))
```

`backend/app/dwh/aggregates.py` — fayl OXIRIDAGI S3 import qatorini almashtiring:
```python
from app.dwh import (  # noqa: E402, F401
    procurement_aggregates,
    production_aggregates,
    stock_aggregates,
)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_procurement_aggregates.py tests/test_aggregates_builds.py -v`
Expected: barcha testlar passed. Run: `$TEST pytest tests/test_synthetic.py -v` — passed (sintetik lotlar agregatga tushadi).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(dwh): xarid agregatlari — lotlar reyestri, normativ va kechikish, yillik reja

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 5: АИП agregatlari (0018) — obyekt × oy (reja, fakt, ochilish, КС-2 va avans oldinga to'ldiriladi), bosqichlar

**Files:**
- Create: `backend/migrations/versions/0018_mart_investment.py`, `backend/app/dwh/investment_aggregates.py`
- Modify: `backend/app/dwh/aggregates.py` (oxirgi import), `backend/tests/s4_helpers.py` (АИП ssenariysi)
- Test: `backend/tests/test_investment_aggregates.py`

**Interfaces:**
- Consumes: `register`, `Aggregate`, `BuildParams.bind` (`:build_id, :date_from, :as_of, :as_of_id`), `builds`, `tests.etl_helpers.*`, `tests.s1_helpers.rebuild`.
- Produces:
  - `mart|pub.agg_investment_month (branch_id > 0, month_id, object_id, object_code, name, program_code, work_type, source_name, commissioning_year, total_cost, plan, fact, opening, physical_pct, advance, advance_date_id)` — `date_from` oyidan joriy yil dekabrigacha; obyekt birinchi qator oyidan boshlab har oy (qatorsiz oylar ham); `fact` — `aip_opening` siz, `opening` — faqat u; `physical_pct` — oxirgi ma'lum qiymat, `advance`/`advance_date_id` — oxirgi qatordagi qiymat (oldinga to'ldiriladi) — faqat `as_of` oyigacha, keyingi oylarda `NULL`.
  - `mart|pub.agg_object_stages (branch_id > 0, month_id = as_of oyi, object_id, stage_no, stage_name, plan_date_id, fact_date_id, done, late)`; `late = fakt > reja` yoki (fakt yo'q va reja < as_of).
  - `app.dwh.investment_aggregates`: `OPEN_DOC = "aip_opening"`, `INVESTMENT_MONTH`, `OBJECT_STAGES`.
  - `tests.s4_helpers`: `InvScenario(source, tag, branch_id, branch_code, run_id, build_id, obj_a, obj_b)`, `investment_rows(tag)`, `investment_scenario(source, *, publish=False) -> InvScenario`.

Ssenariy (as_of = 2026-09-24; mln so'm; filial `T-<tag>`; sana — oyning 1-kuni):

| Obyekt | Atributlar | Qatorlar (oy: reja / fakt / КС-2 / avans, berilgan sana) |
|---|---|---|
| A `OA-<tag>` | модернизация, ввод 2026, стоимость 1000, источник SA (бюджет) | ochilish 2025-01: 300; 2025-10: 100 / 100; 2026-07: 60 / 50 / 0,40 / 30, 2026-06-01; 2026-08: 60 / 40 / — / 30, 2026-06-01; 2026-09: 60 / 20 / 0,45 / 0; 2026-10: 60 / 0 |
| B `OB-<tag>` | реконструкция, ввод 2027, стоимость 500, источник SB (МФИ) | ochilish 2025-01: 100; 2026-08: 100 / 90 / 0,05 / 20, 2026-05-10; 2026-09: 100 / 30 / — / 20, 2026-05-10 |
Bosqichlar (A): 1 «ПСД» reja 2026-03-15, fakt 03-10; 2 «Тендер» reja 06-15, fakt 07-20; 3 «СМР» reja 09-15, fakt yo'q; 4 «Ввод» reja 12-15, fakt yo'q.
Kutilgan (8, 11, 13-vazifalar): `m08` — A: reja yil 240, grafik bo'yicha 120, fakt yil boshidan 90 (0,75 — отстаёт), avval 400, moliyaviy 0,49, jismoniy 0,40, uzilish 9 p.p., avans 30 / 91 kun; B: 200, 100, 90 (0,9 — по графику), avval 100, 0,38, 0,05, 33 p.p., avans 20 / 113 kun. Jami: dastur 440, grafik 220, fakt 180 (0,818182), davr 130. `m09` (24/30): A — grafik 168, fakt 110 (0,654762, под угрозой), jismoniy 0,45, avans yo'q; B — 180, 120 (0,666667), jismoniy 0,05, avans 137 kun; jami 348 / 230 (0,660920).

- [ ] **Step 1: Test yordamchisi — АИП ssenariysi**

`backend/tests/s4_helpers.py` — fayl oxiriga qo'shing:
```python
@dataclass(frozen=True, slots=True)
class InvScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int
    obj_a: int
    obj_b: int


def investment_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]
    a, b, sa, sb = f"OA-{tag}", f"OB-{tag}", f"SA-{tag}", f"SB-{tag}"

    def row(src: str, obj: str, day: int, plan: float, fact: float,
            phys: float | None = None, adv: float = 0, adv_date: int | None = None,
            doc: str = "aip_month") -> dict[str, Any]:
        return {"doc_type": doc, "src_id": src, "date_id": day, "branch_code": code,
                "object_code": obj, "source_code": sa if obj == a else sb, "plan": plan,
                "fact": fact, "physical_pct": phys, "advance": adv, "advance_date_id": adv_date}

    def stg(n: int, name: str, day: int, fact: int | None) -> dict[str, Any]:
        return {"doc_type": "aip_stage", "src_id": f"st{n}", "date_id": day,
                "branch_code": code, "object_code": a, "stage_no": n, "stage_name": name,
                "fact_date_id": fact}

    return {
        "dim_branch": [branch],
        "dim_source": [{"code": sa, "name": f"Бюджет тест {tag}", "kind": "budget"},
                       {"code": sb, "name": f"МФИ тест {tag}", "kind": "ifi"}],
        "dim_object": [
            {"code": a, "name": f"Объект А {tag}", "program_code": "АИП-Т-1",
             "work_type": "modernization", "commissioning_year": 2026, "total_cost": 1000,
             "source_code": sa},
            {"code": b, "name": f"Объект Б {tag}", "program_code": "АИП-Т-2",
             "work_type": "reconstruction", "commissioning_year": 2027, "total_cost": 500,
             "source_code": sb}],
        "fact_investment": [
            row("a0", a, 20250101, 0, 300, doc="aip_opening"),
            row("a1", a, 20251001, 100, 100),
            row("a7", a, 20260701, 60, 50, 0.40, 30, 20260601),
            row("a8", a, 20260801, 60, 40, None, 30, 20260601),
            row("a9", a, 20260901, 60, 20, 0.45, 0, None),
            row("a10", a, 20261001, 60, 0),
            row("b0", b, 20250101, 0, 100, doc="aip_opening"),
            row("b8", b, 20260801, 100, 90, 0.05, 20, 20260510),
            row("b9", b, 20260901, 100, 30, None, 20, 20260510),
        ],
        "fact_object_stage": [
            stg(1, "Проектно-сметная документация", 20260315, 20260310),
            stg(2, "Тендер и договор", 20260615, 20260720),
            stg(3, "Строительно-монтажные работы", 20260915, None),
            stg(4, "Ввод в эксплуатацию", 20261215, None),
        ],
    }


def investment_scenario(source: str, *, publish: bool = False) -> InvScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, investment_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        objs = dict(conn.execute(text(
            "SELECT code, object_id FROM dwh.dim_object WHERE code IN (:a, :b)"),
            {"a": f"OA-{tag}", "b": f"OB-{tag}"}).all())
    return InvScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id,
                       int(objs[f"OA-{tag}"]), int(objs[f"OB-{tag}"]))
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_investment_aggregates.py`:
```python
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s4_helpers import InvScenario, investment_scenario

TABLES = ("agg_investment_month", "agg_object_stages")
COLS = ("plan", "fact", "opening", "physical_pct", "advance", "advance_date_id")


@pytest.fixture
def sc() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _months(sc: InvScenario, obj: int) -> dict[int, tuple[Any, ...]]:
    rows = _rows(f"SELECT month_id, {', '.join(COLS)} FROM mart.agg_investment_month "
                 "WHERE build_id = :b AND object_id = :o", b=sc.build_id, o=obj)
    return {r["month_id"]: tuple(None if r[c] is None else
                                 (int(r[c]) if c == "advance_date_id" else float(r[c]))
                                 for c in COLS) for r in rows}


def test_object_months_with_forward_fill(sc: InvScenario) -> None:
    a = _months(sc, sc.obj_a)
    assert min(a) == 202501 and max(a) == 202612 and len(a) == 24
    assert a[202501] == (0.0, 0.0, 300.0, None, 0.0, None)
    assert a[202510] == (100.0, 100.0, 0.0, None, 0.0, None)
    assert a[202606] == (0.0, 0.0, 0.0, None, 0.0, None)
    assert a[202607] == (60.0, 50.0, 0.0, 0.4, 30.0, 20260601)
    assert a[202608] == (60.0, 40.0, 0.0, 0.4, 30.0, 20260601)  # КС-2 oldinga to'ldirildi
    assert a[202609] == (60.0, 20.0, 0.0, 0.45, 0.0, None)  # avans yopildi
    assert a[202610] == (60.0, 0.0, 0.0, None, None, None)  # as_of dan keyin — NULL
    b = _months(sc, sc.obj_b)
    assert b[202609] == (100.0, 30.0, 0.0, 0.05, 20.0, 20260510)
    assert b[202607] == (0.0, 0.0, 0.0, None, 0.0, None)


def test_object_attributes_denormalized(sc: InvScenario) -> None:
    row = _rows("SELECT object_code, name, work_type, source_name, commissioning_year, "
                "total_cost FROM mart.agg_investment_month WHERE build_id = :b "
                "AND object_id = :o AND month_id = 202608", b=sc.build_id, o=sc.obj_b)[0]
    assert (row["object_code"], row["name"], row["work_type"], row["source_name"],
            row["commissioning_year"], float(row["total_cost"])) == (
        f"OB-{sc.tag}", f"Объект Б {sc.tag}", "reconstruction", f"МФИ тест {sc.tag}", 2027,
        500.0)


def test_stages_snapshot(sc: InvScenario) -> None:
    rows = _rows("SELECT month_id, stage_no, plan_date_id, fact_date_id, done, late "
                 "FROM mart.agg_object_stages WHERE build_id = :b AND object_id = :o "
                 "ORDER BY stage_no", b=sc.build_id, o=sc.obj_a)
    assert [(r["month_id"], r["stage_no"], r["done"], r["late"]) for r in rows] == [
        (202609, 1, True, False), (202609, 2, True, True), (202609, 3, False, True),
        (202609, 4, False, False)]


def test_rls_and_failed_build(sc: InvScenario) -> None:
    for table in TABLES:
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM mart.{table} "
                                      "WHERE build_id = :b"), {"b": sc.build_id}).scalars())
        assert seen == {sc.branch_id}, table
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
        for table in TABLES:
            count = conn.execute(text(f"SELECT count(*) FROM mart.{table} WHERE build_id = :b"),
                                 {"b": sc.build_id}).scalar_one()
            assert count == 0, table
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_investment_aggregates.py -v`
Expected: FAIL — `relation "mart.agg_investment_month" does not exist`.

- [ ] **Step 4: 0018 migratsiyasi**

`backend/migrations/versions/0018_mart_investment.py`:
```python
"""S4: АИП — obyekt × oy (reja, fakt, ochilish, КС-2, avans) va bosqichlar snapshot'i

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_investment_month", "agg_object_stages")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_investment_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      object_id integer NOT NULL,
      object_code varchar(32) NOT NULL,
      name varchar(300) NOT NULL,
      program_code varchar(32),
      work_type varchar(16) NOT NULL,
      source_name varchar(200) NOT NULL,
      commissioning_year smallint,
      total_cost numeric(20,2),
      plan {MONEY},
      fact {MONEY},
      opening {MONEY},
      physical_pct numeric(7,4),
      advance numeric(20,2),
      advance_date_id integer,
      PRIMARY KEY (build_id, branch_id, month_id, object_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_object_stages (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      object_id integer NOT NULL,
      stage_no smallint NOT NULL,
      stage_name varchar(200) NOT NULL,
      plan_date_id integer NOT NULL,
      fact_date_id integer,
      done boolean NOT NULL,
      late boolean NOT NULL,
      PRIMARY KEY (build_id, branch_id, month_id, object_id, stage_no)
    )
    """,
    f"""
    CREATE VIEW pub.agg_investment_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.object_id, a.object_code, a.name, a.program_code,
           a.work_type, a.source_name, a.commissioning_year, a.total_cost, a.plan, a.fact,
           a.opening, a.physical_pct, a.advance, a.advance_date_id
    FROM mart.agg_investment_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_object_stages WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.object_id, a.stage_no, a.stage_name, a.plan_date_id,
           a.fact_date_id, a.done, a.late
    FROM mart.agg_object_stages a WHERE a.build_id = {ACTIVE}
    """,
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        op.execute(f"ALTER TABLE mart.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE mart.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY branch_scope ON mart.{table} USING (core.rls_branch_ok(branch_id)) "
                   "WITH CHECK (core.rls_branch_ok(branch_id))")
        op.execute(f"GRANT SELECT ON mart.{table} TO ugk_app")
        op.execute(f"GRANT SELECT, INSERT, DELETE ON mart.{table} TO ugk_etl")
        op.execute(f"GRANT SELECT ON pub.{table} TO ugk_app")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP VIEW pub.{table}")
        op.execute(f"DROP TABLE mart.{table}")
```

- [ ] **Step 5: Implementatsiya — agregatlar**

`backend/app/dwh/investment_aggregates.py`:
```python
"""S4 АИП agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Oylar: date_from … joriy yil dekabri (reja kelajak oylar uchun ham kerak — «Программа года»).
Har obyekt birinchi qatori bor oydan boshlab har oy qator oladi (qatorsiz oylar — nol): КС-2
foizi oxirgi ma'lum qiymat bilan, avans — oxirgi mavjud qator qiymati bilan oldinga to'ldiriladi
(faqat as_of oyigacha; keyingi oylarda NULL). «aip_opening» (tarixdan oldingi to'plangan
moliyalashtirish) oylik faktga emas, `opening` ga tushadi — «освоено ранее» (TZ 4).
Obyekt atributlari denormalizatsiya qilinadi — pub'da obyektlar ro'yxati alohida ochilmaydi.
"""

from __future__ import annotations

from app.dwh.aggregates import Aggregate, register

OPEN_DOC = "aip_opening"
_AS_MONTH = "CAST(:as_of_id AS integer) / 100"

_INVESTMENT = f"""
INSERT INTO mart.agg_investment_month (build_id, branch_id, month_id, object_id, object_code,
                                       name, program_code, work_type, source_name,
                                       commissioning_year, total_cost, plan, fact, opening,
                                       physical_pct, advance, advance_date_id)
WITH months AS (
  SELECT month_id FROM dwh.dim_date
  WHERE date BETWEEN CAST(:date_from AS date)
                 AND make_date(CAST(extract(year FROM CAST(:as_of AS date)) AS integer), 12, 31)
  GROUP BY month_id),
f AS (
  SELECT i.branch_id, i.object_id, d.month_id, sum(i.plan) AS plan,
         coalesce(sum(i.fact) FILTER (WHERE i.doc_type <> '{OPEN_DOC}'), 0) AS fact,
         coalesce(sum(i.fact) FILTER (WHERE i.doc_type = '{OPEN_DOC}'), 0) AS opening,
         (array_agg(i.physical_pct ORDER BY i.date_id DESC)
            FILTER (WHERE i.physical_pct IS NOT NULL))[1] AS phys,
         sum(i.advance) AS adv,
         min(i.advance_date_id) FILTER (WHERE i.advance > 0) AS adv_date
  FROM dwh.fact_investment i
  JOIN dwh.dim_date d ON d.date_id = i.date_id
  JOIN months m ON m.month_id = d.month_id
  GROUP BY i.branch_id, i.object_id, d.month_id),
grid AS (
  SELECT o.branch_id, o.object_id, m.month_id
  FROM (SELECT branch_id, object_id, min(month_id) AS first_m FROM f
        GROUP BY branch_id, object_id) o
  JOIN months m ON m.month_id >= o.first_m),
j AS (
  SELECT g.branch_id, g.object_id, g.month_id, coalesce(f.plan, 0) AS plan,
         coalesce(f.fact, 0) AS fact, coalesce(f.opening, 0) AS opening, f.phys, f.adv,
         f.adv_date,
         count(f.phys) OVER w AS phys_grp,
         count(f.month_id) OVER w AS row_grp
  FROM grid g
  LEFT JOIN f ON f.branch_id = g.branch_id AND f.object_id = g.object_id
             AND f.month_id = g.month_id
  WINDOW w AS (PARTITION BY g.branch_id, g.object_id ORDER BY g.month_id)),
k AS (
  SELECT j.*,
         first_value(j.phys) OVER (PARTITION BY j.branch_id, j.object_id, j.phys_grp
                                   ORDER BY j.month_id) AS phys_ff,
         first_value(j.adv) OVER (PARTITION BY j.branch_id, j.object_id, j.row_grp
                                  ORDER BY j.month_id) AS adv_ff,
         first_value(j.adv_date) OVER (PARTITION BY j.branch_id, j.object_id, j.row_grp
                                       ORDER BY j.month_id) AS adv_date_ff
  FROM j)
SELECT :build_id, k.branch_id, k.month_id, k.object_id, o.code, o.name, o.program_code,
       o.work_type, coalesce(s.name, '—'), o.commissioning_year, o.total_cost, k.plan, k.fact,
       k.opening,
       CASE WHEN k.month_id <= {_AS_MONTH} THEN k.phys_ff END,
       CASE WHEN k.month_id <= {_AS_MONTH} THEN coalesce(k.adv_ff, 0) END,
       CASE WHEN k.month_id <= {_AS_MONTH} THEN k.adv_date_ff END
FROM k
JOIN dwh.dim_object o ON o.object_id = k.object_id
LEFT JOIN dwh.dim_source s ON s.source_id = o.source_id
"""

_STAGES = f"""
INSERT INTO mart.agg_object_stages (build_id, branch_id, month_id, object_id, stage_no,
                                    stage_name, plan_date_id, fact_date_id, done, late)
SELECT :build_id, s.branch_id, {_AS_MONTH}, s.object_id, s.stage_no, max(s.stage_name),
       max(s.date_id), max(s.fact_date_id), max(s.fact_date_id) IS NOT NULL,
       coalesce(max(s.fact_date_id) > max(s.date_id), max(s.date_id) < :as_of_id)
FROM dwh.fact_object_stage s
GROUP BY s.branch_id, s.object_id, s.stage_no
"""

INVESTMENT_MONTH = register(Aggregate("agg_investment_month", (_INVESTMENT,)))
OBJECT_STAGES = register(Aggregate("agg_object_stages", (_STAGES,)))
```

`backend/app/dwh/aggregates.py` — oxirgi import blokiga `investment_aggregates` ni qo'shing:
```python
from app.dwh import (  # noqa: E402, F401
    investment_aggregates,
    procurement_aggregates,
    production_aggregates,
    stock_aggregates,
)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_investment_aggregates.py tests/test_procurement_aggregates.py tests/test_aggregates_builds.py tests/test_synthetic.py -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(dwh): АИП agregatlari — obyekt × oy, КС-2 va avans oldinga to'ldiriladi, bosqichlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 6: Kadrlar agregati (0019) — filial × oy × toifa: штат, факт (oy oxirgi snapshot'i), oqimlar

**Files:**
- Create: `backend/migrations/versions/0019_mart_hr.py`, `backend/app/dwh/hr_aggregates.py`
- Modify: `backend/app/dwh/aggregates.py` (oxirgi import), `backend/tests/s4_helpers.py` (kadrlar ssenariysi)
- Test: `backend/tests/test_hr_aggregates.py`

**Interfaces:**
- Consumes: `_MONTHS`, `register`, `Aggregate`, `BuildParams.bind`, `builds`, `tests.etl_helpers.*` (`cash_row`), `tests.s1_helpers.rebuild`.
- Produces:
  - `mart|pub.agg_hr_month (branch_id ≥ 0, month_id, category, headcount_plan, headcount_fact, hired, fired, overtime_hours)` — штат/факт — filial × lavozim bo'yicha oydagi eng oxirgi sana qatorlari; oqimlar — oy yig'indisi; `branch_id = 0` — jami.
  - `app.dwh.hr_aggregates`: `HR_MONTH`.
  - `tests.s4_helpers`: `HrScenario(source, tag, branch_id, branch_code, run_id, build_id, salary_code)`, `hr_rows(tag)`, `hr_scenario(source, *, publish=False) -> HrScenario`.

Ssenariy (filial `T-<tag>`; toifalar «Руководители» (HP1), «Оперативный персонал» (HP2); `fact_hr` sanasi — oy oxiri; ФОТ statyasi `SAL-<tag>`):

| Sana | HP1 штат / факт / принято / уволено / сверхурочные | HP2 |
|---|---|---|
| 2026-07-31 | 10 / 9 / 0 / 1 / 15 | 90 / 82 / 1 / 1 / 300 |
| 2026-08-15 | — | 90 / 85 / 0 / 0 / 0 (oyning oxirgi snapshot'i emas) |
| 2026-08-31 | 10 / 9 / 1 / 0 / 20 | 90 / 81 / 2 / 3 / 400 |
| 2026-09-24 | 10 / 10 / 1 / 0 / 10 | 90 / 80 / 1 / 2 / 200 |
`fact_cashflow` (out): `SAL` 2026-07-15 170, 2026-08-15 180, 2026-09-10 150; `PKM54-O09` 2026-08-20 420, 2026-09-12 100.
Kutilgan (9, 12, 13-vazifalar): `m08` — штат 100, факт 90, вакансии 10 (0,1), ФОТ 180 из 600 (0,3), o'rtacha 2,0, принято 3, уволено 3, qo'nimsizlik 0,033333, сверхурочные 420 (4,666667 на чел.); `m09` — 100 / 90, ФОТ 150 из 250 (0,6), o'rtacha 150 / 90 / 0,8 = 2,083333, 2 / 2 (0,022222), 210 (2,333333); `q3` — ФОТ 500 из 1020 (0,490196), o'rtacha 500 / 90 / 2,8 = 1,984127, принято 6, уволено 7 (0,077778), сверхурочные 945 (10,5).

- [ ] **Step 1: Test yordamchisi — kadrlar ssenariysi**

`backend/tests/s4_helpers.py` — importni `from tests.etl_helpers import branch_row, cash_row, merge_all, new_tag, open_run, stage` ga almashtiring va fayl oxiriga qo'shing:
```python
@dataclass(frozen=True, slots=True)
class HrScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int
    salary_code: str


def hr_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]
    salary = f"SAL-{tag}"

    def hr(src: str, day: int, pos: str, plan: int, fact: int, hired: int, fired: int,
           overtime: float) -> dict[str, Any]:
        return {"doc_type": "hr_month", "src_id": src, "date_id": day, "branch_code": code,
                "pos_code": f"{pos}-{tag}", "headcount_plan": plan, "headcount_fact": fact,
                "payroll": 0, "hired": hired, "fired": fired, "overtime_hours": overtime}

    return {
        "dim_branch": [branch],
        "dim_position": [{"code": f"HP1-{tag}", "category": "Руководители", "department": "—"},
                         {"code": f"HP2-{tag}", "category": "Оперативный персонал",
                          "department": "—"}],
        "dim_item": [{"code": salary, "name": f"Заработная плата тест {tag}",
                      "activity": "operating", "direction": "out", "sort_order": 999}],
        "fact_hr": [
            hr("h71", 20260731, "HP1", 10, 9, 0, 1, 15),
            hr("h72", 20260731, "HP2", 90, 82, 1, 1, 300),
            hr("hx", 20260815, "HP2", 90, 85, 0, 0, 0),
            hr("h81", 20260831, "HP1", 10, 9, 1, 0, 20),
            hr("h82", 20260831, "HP2", 90, 81, 2, 3, 400),
            hr("h91", 20260924, "HP1", 10, 10, 1, 0, 10),
            hr("h92", 20260924, "HP2", 90, 80, 1, 2, 200),
        ],
        "fact_cashflow": [
            cash_row("c1", 20260715, code, 170, item_code=salary),
            cash_row("c2", 20260815, code, 180, item_code=salary),
            cash_row("c3", 20260910, code, 150, item_code=salary),
            cash_row("c4", 20260820, code, 420),
            cash_row("c5", 20260912, code, 100),
        ],
    }


def hr_scenario(source: str, *, publish: bool = False) -> HrScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, hr_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    return HrScenario(source, tag, _branch_id(f"T-{tag}"), f"T-{tag}", run_id, build_id,
                      f"SAL-{tag}")
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_hr_aggregates.py`:
```python
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s4_helpers import HrScenario, hr_scenario

COLS = ("headcount_plan", "headcount_fact", "hired", "fired", "overtime_hours")
LEAD, OPER = "Руководители", "Оперативный персонал"


@pytest.fixture
def sc() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def test_hr_month_snapshot_and_flows(sc: HrScenario) -> None:
    rows = _rows(f"SELECT month_id, category, {', '.join(COLS)} FROM mart.agg_hr_month "
                 "WHERE build_id = :b AND branch_id = :br", b=sc.build_id, br=sc.branch_id)
    got = {(r["month_id"], r["category"]): tuple(float(r[c]) for c in COLS) for r in rows}
    assert got == {
        (202607, LEAD): (10, 9, 0, 1, 15), (202607, OPER): (90, 82, 1, 1, 300),
        (202608, LEAD): (10, 9, 1, 0, 20), (202608, OPER): (90, 81, 2, 3, 400),
        (202609, LEAD): (10, 10, 1, 0, 10), (202609, OPER): (90, 80, 1, 2, 200),
    }
    total = _rows("SELECT sum(headcount_fact) AS f FROM mart.agg_hr_month WHERE build_id = :b "
                  "AND branch_id = 0 AND month_id = 202608", b=sc.build_id)
    assert float(total[0]["f"]) >= 90


def test_rls_and_failed_build(sc: HrScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        seen = set(s.execute(text("SELECT DISTINCT branch_id FROM mart.agg_hr_month "
                                  "WHERE build_id = :b"), {"b": sc.build_id}).scalars())
    assert seen == {sc.branch_id}
    with etl_transaction() as conn:
        builds.mark_failed(conn, sc.build_id)
        count = conn.execute(text("SELECT count(*) FROM mart.agg_hr_month WHERE build_id = :b"),
                             {"b": sc.build_id}).scalar_one()
    assert count == 0
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_hr_aggregates.py -v`
Expected: FAIL — `relation "mart.agg_hr_month" does not exist`.

- [ ] **Step 4: 0019 migratsiyasi**

`backend/migrations/versions/0019_mart_hr.py`:
```python
"""S4: kadrlar — filial × oy × toifa (штат, факт, qabul, bo'shatish, ish vaqtidan tashqari soatlar)

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-25

Faqat agregatlar — ФИО va boshqa shaxsiy ma'lumot ustunlari yo'q (TZ 9).
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"


def upgrade() -> None:
    op.execute(f"""
    CREATE TABLE mart.agg_hr_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      category varchar(100) NOT NULL,
      headcount_plan numeric(10,1) NOT NULL DEFAULT 0,
      headcount_fact numeric(10,1) NOT NULL DEFAULT 0,
      hired integer NOT NULL DEFAULT 0,
      fired integer NOT NULL DEFAULT 0,
      overtime_hours numeric(12,1) NOT NULL DEFAULT 0,
      PRIMARY KEY (build_id, branch_id, month_id, category)
    )
    """)
    op.execute(f"""
    CREATE VIEW pub.agg_hr_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.category, a.headcount_plan, a.headcount_fact, a.hired,
           a.fired, a.overtime_hours
    FROM mart.agg_hr_month a WHERE a.build_id = {ACTIVE}
    """)
    op.execute("ALTER TABLE mart.agg_hr_month ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mart.agg_hr_month FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY branch_scope ON mart.agg_hr_month USING (core.rls_branch_ok(branch_id)) "
               "WITH CHECK (core.rls_branch_ok(branch_id))")
    op.execute("GRANT SELECT ON mart.agg_hr_month TO ugk_app")
    op.execute("GRANT SELECT, INSERT, DELETE ON mart.agg_hr_month TO ugk_etl")
    op.execute("GRANT SELECT ON pub.agg_hr_month TO ugk_app")


def downgrade() -> None:
    op.execute("DROP VIEW pub.agg_hr_month")
    op.execute("DROP TABLE mart.agg_hr_month")
```

- [ ] **Step 5: Implementatsiya — agregat**

`backend/app/dwh/hr_aggregates.py`:
```python
"""S4 kadrlar agregati (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

fact_hr — filial × lavozim × oy snapshot'i (TZ 3): штат/факт — oydagi eng oxirgi sana qatorlari
(oy ichidagi oldingi snapshot'lar tashlanadi), qabul/bo'shatish/soatlar — oy yig'indisi.
Toifa = dim_position.category. Shaxsiy ma'lumot yo'q.
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

_HR = f"""
INSERT INTO mart.agg_hr_month (build_id, branch_id, month_id, category, headcount_plan,
                               headcount_fact, hired, fired, overtime_hours)
WITH {_MONTHS},
last AS (
  SELECT h.branch_id, h.pos_id, m.month_id, max(h.date_id) AS snap_id
  FROM dwh.fact_hr h JOIN months m ON h.date_id BETWEEN m.first_id AND m.end_id
  GROUP BY h.branch_id, h.pos_id, m.month_id),
snap AS (
  SELECT l.branch_id, l.month_id, p.category, sum(h.headcount_plan) AS plan,
         sum(h.headcount_fact) AS fact
  FROM last l
  JOIN dwh.fact_hr h ON h.branch_id = l.branch_id AND h.pos_id = l.pos_id
                    AND h.date_id = l.snap_id
  JOIN dwh.dim_position p ON p.pos_id = l.pos_id
  GROUP BY l.branch_id, l.month_id, p.category),
flow AS (
  SELECT h.branch_id, m.month_id, p.category, sum(h.hired) AS hired, sum(h.fired) AS fired,
         sum(h.overtime_hours) AS ot
  FROM dwh.fact_hr h
  JOIN months m ON h.date_id BETWEEN m.first_id AND m.end_id
  JOIN dwh.dim_position p ON p.pos_id = h.pos_id
  GROUP BY h.branch_id, m.month_id, p.category),
j AS (
  SELECT s.branch_id, s.month_id, s.category, s.plan, s.fact, f.hired, f.fired, f.ot
  FROM snap s
  JOIN flow f ON f.branch_id = s.branch_id AND f.month_id = s.month_id
             AND f.category = s.category)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, j.category, sum(j.plan), sum(j.fact),
       sum(j.hired), sum(j.fired), sum(j.ot)
FROM j
GROUP BY GROUPING SETS ((j.branch_id, j.month_id, j.category), (j.month_id, j.category))
"""

HR_MONTH = register(Aggregate("agg_hr_month", (_HR,)))
```
(`snap` va `flow` bir xil (filial, oy, toifa) kalitlaridan iborat — har `fact_hr` qatori ikkalasiga ham tushadi, shuning uchun ichki JOIN yetarli.)

`backend/app/dwh/aggregates.py` — oxirgi import blokiga `hr_aggregates` ni qo'shing:
```python
from app.dwh import (  # noqa: E402, F401
    hr_aggregates,
    investment_aggregates,
    procurement_aggregates,
    production_aggregates,
    stock_aggregates,
)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_hr_aggregates.py tests/test_investment_aggregates.py tests/test_procurement_aggregates.py tests/test_aggregates_builds.py tests/test_synthetic.py tests/test_rls_structure.py -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(dwh): kadrlar agregati — штат/факт snapshot'i, qabul, bo'shatish, soatlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 7: Xarid so'rovlari — shartnomalar, tejash, reja bajarilishi, lotlar, usullar, yetkazib beruvchilar

**Files:**
- Create: `backend/app/sections/queries/procurement.py`
- Test: `backend/tests/test_sections_procurement.py`

**Interfaces:**
- Consumes: `pub.agg_procurement_lots`, `pub.agg_procurement_plan`, `pub.branches`, `BranchSel.rows/total`, `ReportPeriod` (`months`, `last_month`, `date_to`), `resolve_period`, `queries.cash.num`, `date_id`, `codes.*`, `tests.s4_helpers.procurement_scenario`.
- Produces (`app.sections.queries.procurement`):
  - `LOTS_LIMIT = 1000`, `ratio(a, b) -> float | None` (b ≤ 0 → None, 6 kasr).
  - `ProcFigures(contracted, contracts, start_contracted, direct, days_sum, days_n, ytd, plan, in_work, in_work_start, overdue, overdue_start, cancelled, cancelled_start)` + `.savings`, `.savings_share`, `.plan_execution`, `.direct_share`, `.avg_days` (1 kasr), `.has_data`.
  - `ProcMonth(month_id, contracted)`, `MethodRow(method, title, lots, start, contracted, days_sum, days_n, norm_days)` + `.savings`, `.savings_share`, `.avg_days`; `LotRow(lot_no, branch_id, branch_name, date_id, method, method_title, subject, status, start_price, contract_price, days, norm_days, overdue, supplier)` + `.kind` (`work | done | cancelled`); `NamedCount(name, amount, count)`; `ProcBranch(branch_id, name, plan, ytd, savings)` + `.execution`.
  - `totals(db, sel, period)`, `monthly(db, sel, today)`, `by_method(db, sel, period)`, `lots(db, sel, period, limit=LOTS_LIMIT)` (davrda tuzilgan/bekor qilingan + davr oxirigacha e'lon qilingan «в работе»; kechikkanlar, keyin narx bo'yicha), `cancelled(db, sel, period)`, `suppliers(db, sel, period)`, `subjects(db, sel, period)`, `by_branch(db, sel, period)`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sections_procurement.py`:
```python
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import procurement
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s4_helpers import ProcScenario, procurement_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _sel(sc: ProcScenario) -> BranchSel:
    return BranchSel(sc.branch_id, all_scope=True)


def _totals(db: Session, sc: ProcScenario, per: str) -> procurement.ProcFigures:
    return procurement.totals(db, _sel(sc), resolve_period(per, TEST_AS_OF))


def test_closed_month_totals(sc: ProcScenario, db: Session) -> None:
    t = _totals(db, sc, "m08")
    assert (t.contracted, t.contracts, t.start_contracted, t.savings) == (140.0, 2, 150.0, 10.0)
    assert t.savings_share == 0.066667 and t.direct_share == 0.357143
    assert (t.ytd, t.plan, t.plan_execution, t.avg_days) == (197.0, 1000.0, 0.197, 8.5)
    assert (t.in_work, t.in_work_start, t.overdue, t.overdue_start) == (1, 80.0, 1, 80.0)
    assert (t.cancelled, t.cancelled_start) == (1, 40.0) and t.has_data


def test_open_month_and_quarter(sc: ProcScenario, db: Session) -> None:
    t = _totals(db, sc, "m09")
    assert (t.contracted, t.savings, t.savings_share, t.direct_share) == (170.0, 30.0, 0.15, 0.0)
    assert (t.ytd, t.plan_execution, t.avg_days) == (367.0, 0.367, 60.0)
    assert (t.in_work, t.in_work_start, t.overdue, t.cancelled) == (2, 110.0, 1, 0)
    q = _totals(db, sc, "q3")
    assert (q.contracted, q.contracts, q.savings, q.direct_share, q.avg_days) == (
        310.0, 3, 40.0, 0.16129, 25.7)


def test_monthly_and_methods(sc: ProcScenario, db: Session) -> None:
    months = procurement.monthly(db, _sel(sc), TEST_AS_OF)
    assert [m.month_id for m in months] == list(range(202601, 202610))
    assert {m.month_id: m.contracted for m in months if m.contracted} == {
        202602: 57.0, 202608: 140.0, 202609: 170.0}
    rows = procurement.by_method(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.method, r.title, r.lots, r.start, r.contracted, r.savings, r.savings_share,
             r.avg_days, r.norm_days) for r in rows] == [
        ("eshop", "Электронный магазин", 1, 100.0, 90.0, 10.0, 0.1, 12.0, 15),
        ("direct", "Прямой договор", 1, 50.0, 50.0, 0.0, 0.0, 5.0, 12)]


def test_lot_registry_order_and_kinds(sc: ProcScenario, db: Session) -> None:
    rows = procurement.lots(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.lot_no, r.kind, r.overdue) for r in rows] == [
        ("L4", "work", True), ("L1", "done", False), ("L2", "done", False),
        ("L6", "cancelled", False)]
    first = rows[0]
    assert (first.days, first.norm_days, first.method_title, first.subject) == (
        85, 40, "Электронный конкурс", "Строительно-монтажные работы")
    assert first.branch_name == f"Тестовая ГЭС {sc.tag}" and first.date_id == 20260701
    assert [r.lot_no for r in procurement.lots(db, _sel(sc), resolve_period("m08", TEST_AS_OF),
                                               limit=2)] == ["L4", "L1"]
    assert [r.lot_no for r in procurement.cancelled(db, _sel(sc),
                                                    resolve_period("m08", TEST_AS_OF))] == ["L6"]


def test_suppliers_subjects_branches(sc: ProcScenario, db: Session) -> None:
    period = resolve_period("m08", TEST_AS_OF)
    assert [(s.name, s.amount, s.count) for s in procurement.suppliers(db, _sel(sc), period)] == [
        (f"ООО «Поставщик-1 {sc.tag}»", 90.0, 1), (f"ООО «Поставщик-2 {sc.tag}»", 50.0, 1)]
    assert [(s.name, s.amount) for s in procurement.subjects(db, _sel(sc), period)] == [
        ("Запасные части", 90.0), ("Ремонтные услуги", 50.0)]
    branches = procurement.by_branch(db, _sel(sc), period)
    assert [(b.branch_id, b.plan, b.ytd, b.execution, b.savings) for b in branches] == [
        (sc.branch_id, 1000.0, 197.0, 0.197, 10.0)]


def test_empty_selection_and_limited_scope(sc: ProcScenario) -> None:
    with new_session() as s:
        apply_rls(s, None)
        empty = procurement.totals(s, BranchSel(999_999, True), resolve_period("m08", TEST_AS_OF))
    assert not empty.has_data and empty.plan_execution is None and empty.avg_days is None
    assert empty.direct_share is None and empty.savings_share is None
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        own = procurement.totals(s, BranchSel(None, all_scope=False),
                                 resolve_period("m08", TEST_AS_OF))
    assert (own.contracted, own.plan) == (140.0, 1000.0)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sections_procurement.py -v`
Expected: FAIL — `ImportError: cannot import name 'procurement' from 'app.sections.queries'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/sections/queries/procurement.py`:
```python
"""Xaridlar (TZ 4 «Закупки») — faqat pub.agg_procurement_lots, pub.agg_procurement_plan va
pub.branches dan.

Davr ko'rsatkichlari — sanasi davr oylariga tushgan tuzilgan/bekor qilingan lotlar; «в работе» va
«просроченные» — joriy holat, davr oxirigacha e'lon qilinganlar (S4 spec 11.2). Yillik reja
bajarilishi — davr yili 1-yanvaridan davr oxirigacha tuzilgan shartnomalar / yillik reja.
Maxraj 0 → None («нет данных»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import date_id, month_id
from app.etl.zakupki.codes import CANCELLED, DIRECT, DONE, IN_WORK, METHOD_TITLES, METHODS
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.scope import BranchSel

LOTS_LIMIT = 1000
_IN_WORK = ", ".join(f"'{s}'" for s in IN_WORK)  # kod konstantalari — whitelist
_DONE = "l.status = :done"
_PERIOD = "l.month_id = ANY(:months)"


def ratio(a: float, b: float) -> float | None:
    return None if b <= 0 else round(a / b, 6)


@dataclass(frozen=True, slots=True)
class ProcFigures:
    contracted: float
    contracts: int
    start_contracted: float
    direct: float
    days_sum: float
    days_n: int
    ytd: float
    plan: float
    in_work: int
    in_work_start: float
    overdue: int
    overdue_start: float
    cancelled: int
    cancelled_start: float

    @property
    def savings(self) -> float:
        """Экономия = начальная цена − цена договора (TZ 4)."""
        return round(self.start_contracted - self.contracted, 2)

    @property
    def savings_share(self) -> float | None:
        return ratio(self.savings, self.start_contracted)

    @property
    def plan_execution(self) -> float | None:
        return ratio(self.ytd, self.plan)

    @property
    def direct_share(self) -> float | None:
        return ratio(self.direct, self.contracted)

    @property
    def avg_days(self) -> float | None:
        return None if self.days_n <= 0 else round(self.days_sum / self.days_n, 1)

    @property
    def has_data(self) -> bool:
        return self.contracts > 0 or self.in_work > 0 or self.plan > 0 or self.cancelled > 0


@dataclass(frozen=True, slots=True)
class ProcMonth:
    month_id: int
    contracted: float


@dataclass(frozen=True, slots=True)
class MethodRow:
    method: str
    title: str
    lots: int
    start: float
    contracted: float
    days_sum: float
    days_n: int
    norm_days: int | None

    @property
    def savings(self) -> float:
        return round(self.start - self.contracted, 2)

    @property
    def savings_share(self) -> float | None:
        return ratio(self.savings, self.start)

    @property
    def avg_days(self) -> float | None:
        return None if self.days_n <= 0 else round(self.days_sum / self.days_n, 1)


@dataclass(frozen=True, slots=True)
class LotRow:
    lot_no: str
    branch_id: int
    branch_name: str
    date_id: int
    method: str
    method_title: str
    subject: str
    status: str
    start_price: float
    contract_price: float | None
    days: int | None
    norm_days: int | None
    overdue: bool
    supplier: str | None

    @property
    def kind(self) -> str:
        if self.status == DONE:
            return "done"
        return "cancelled" if self.status == CANCELLED else "work"


@dataclass(frozen=True, slots=True)
class NamedCount:
    name: str
    amount: float
    count: int


@dataclass(frozen=True, slots=True)
class ProcBranch:
    branch_id: int
    name: str
    plan: float
    ytd: float
    savings: float

    @property
    def execution(self) -> float | None:
        return ratio(self.ytd, self.plan)


def _ytd(period: ReportPeriod) -> list[int]:
    year = period.last_month // 100
    return [year * 100 + m for m in range(1, period.last_month % 100 + 1)]


def _bind(period: ReportPeriod) -> dict[str, Any]:
    return {"months": list(period.months), "ytd": _ytd(period), "end_id": date_id(period.date_to),
            "done": DONE, "cancelled": CANCELLED, "direct": DIRECT}


def totals(db: Session, sel: BranchSel, period: ReportPeriod) -> ProcFigures:
    where, params = sel.rows("l.branch_id")
    work = f"l.status IN ({_IN_WORK}) AND l.date_id <= :end_id"
    r = db.execute(text(
        "SELECT "
        f"coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) AS contracted, "
        f"count(*) FILTER (WHERE {_DONE} AND {_PERIOD}) AS contracts, "
        f"coalesce(sum(l.start_price) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) AS start_c, "
        f"coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} AND {_PERIOD} "
        "AND l.method = :direct), 0) AS direct, "
        f"coalesce(sum(l.days) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) AS days_sum, "
        f"count(l.days) FILTER (WHERE {_DONE} AND {_PERIOD}) AS days_n, "
        f"coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} AND l.month_id = ANY(:ytd)), 0) "
        "AS ytd, "
        f"count(*) FILTER (WHERE {work}) AS in_work, "
        f"coalesce(sum(l.start_price) FILTER (WHERE {work}), 0) AS in_work_start, "
        "count(*) FILTER (WHERE l.overdue AND l.date_id <= :end_id) AS overdue, "
        "coalesce(sum(l.start_price) FILTER (WHERE l.overdue AND l.date_id <= :end_id), 0) "
        "AS overdue_start, "
        f"count(*) FILTER (WHERE l.status = :cancelled AND {_PERIOD}) AS cancelled, "
        f"coalesce(sum(l.start_price) FILTER (WHERE l.status = :cancelled AND {_PERIOD}), 0) "
        "AS cancelled_start "
        f"FROM pub.agg_procurement_lots l WHERE {where}"), {**params, **_bind(period)}).one()
    p_where, p_params = sel.total("p.branch_id")
    plan = db.execute(text(
        f"SELECT coalesce(sum(p.plan), 0) FROM pub.agg_procurement_plan p WHERE {p_where} "
        "AND p.month_id = :year01"),
        {**p_params, "year01": period.last_month // 100 * 100 + 1}).scalar_one()
    return ProcFigures(
        contracted=num(r.contracted), contracts=int(r.contracts), start_contracted=num(r.start_c),
        direct=num(r.direct), days_sum=num(r.days_sum), days_n=int(r.days_n), ytd=num(r.ytd),
        plan=num(plan), in_work=int(r.in_work), in_work_start=num(r.in_work_start),
        overdue=int(r.overdue), overdue_start=num(r.overdue_start), cancelled=int(r.cancelled),
        cancelled_start=num(r.cancelled_start))


def monthly(db: Session, sel: BranchSel, today: date) -> list[ProcMonth]:
    months = [today.year * 100 + m for m in range(1, month_id(today) % 100 + 1)]
    where, params = sel.rows("l.branch_id")
    by = dict(db.execute(text(
        "SELECT l.month_id, sum(l.contract_price) FROM pub.agg_procurement_lots l "
        f"WHERE {where} AND {_DONE} AND l.month_id = ANY(:months) GROUP BY l.month_id"),
        {**params, "months": months, "done": DONE}).all())
    return [ProcMonth(m, num(by.get(m))) for m in months]


def by_method(db: Session, sel: BranchSel, period: ReportPeriod) -> list[MethodRow]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        "SELECT l.method, count(*) AS n, sum(l.start_price) AS s, sum(l.contract_price) AS c, "
        "coalesce(sum(l.days), 0) AS ds, count(l.days) AS dn, max(l.norm_days) AS norm "
        f"FROM pub.agg_procurement_lots l WHERE {where} AND {_DONE} AND {_PERIOD} "
        "GROUP BY l.method ORDER BY c DESC, l.method"), {**params, **_bind(period)}).all()
    return [MethodRow(r.method, METHOD_TITLES.get(r.method, r.method), int(r.n), num(r.s),
                      num(r.c), num(r.ds), int(r.dn),
                      None if r.norm is None else int(r.norm)) for r in rows
            if r.method in METHODS]


_LOT_COLS = ("l.lot_no, l.branch_id, b.name AS branch_name, l.date_id, l.method, l.subject, "
             "l.status, l.start_price, l.contract_price, l.days, l.norm_days, l.overdue, "
             "l.supplier")


def _lot(r: Any) -> LotRow:
    return LotRow(
        lot_no=r.lot_no, branch_id=int(r.branch_id), branch_name=r.branch_name,
        date_id=int(r.date_id), method=r.method,
        method_title=METHOD_TITLES.get(r.method, r.method), subject=r.subject, status=r.status,
        start_price=num(r.start_price),
        contract_price=None if r.contract_price is None else num(r.contract_price),
        days=None if r.days is None else int(r.days),
        norm_days=None if r.norm_days is None else int(r.norm_days), overdue=bool(r.overdue),
        supplier=r.supplier)


def lots(db: Session, sel: BranchSel, period: ReportPeriod,
         limit: int = LOTS_LIMIT) -> list[LotRow]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        f"SELECT {_LOT_COLS} FROM pub.agg_procurement_lots l "
        "JOIN pub.branches b ON b.branch_id = l.branch_id "
        f"WHERE {where} AND ((l.status IN (:done, :cancelled) AND {_PERIOD}) "
        f"OR (l.status IN ({_IN_WORK}) AND l.date_id <= :end_id)) "
        "ORDER BY l.overdue DESC, l.start_price DESC, l.lot_no LIMIT :limit"),
        {**params, **_bind(period), "limit": limit}).all()
    return [_lot(r) for r in rows]


def cancelled(db: Session, sel: BranchSel, period: ReportPeriod) -> list[LotRow]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        f"SELECT {_LOT_COLS} FROM pub.agg_procurement_lots l "
        "JOIN pub.branches b ON b.branch_id = l.branch_id "
        f"WHERE {where} AND l.status = :cancelled AND {_PERIOD} "
        "ORDER BY l.start_price DESC, l.lot_no LIMIT :limit"),
        {**params, **_bind(period), "limit": LOTS_LIMIT}).all()
    return [_lot(r) for r in rows]


def _grouped(db: Session, sel: BranchSel, period: ReportPeriod, column: str) -> list[NamedCount]:
    where, params = sel.rows("l.branch_id")
    rows = db.execute(text(
        f"SELECT coalesce(l.{column}, '—') AS name, sum(l.contract_price) AS a, count(*) AS n "
        f"FROM pub.agg_procurement_lots l WHERE {where} AND {_DONE} AND {_PERIOD} "
        "GROUP BY 1 ORDER BY a DESC, name"), {**params, **_bind(period)}).all()
    return [NamedCount(r.name, num(r.a), int(r.n)) for r in rows]


def suppliers(db: Session, sel: BranchSel, period: ReportPeriod) -> list[NamedCount]:
    return _grouped(db, sel, period, "supplier")


def subjects(db: Session, sel: BranchSel, period: ReportPeriod) -> list[NamedCount]:
    return _grouped(db, sel, period, "subject")


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod) -> list[ProcBranch]:
    where, params = sel.rows("l.branch_id")
    lots_by = {int(r.branch_id): r for r in db.execute(text(
        f"SELECT l.branch_id, coalesce(sum(l.contract_price) FILTER (WHERE {_DONE} "
        "AND l.month_id = ANY(:ytd)), 0) AS ytd, "
        f"coalesce(sum(l.start_price - l.contract_price) FILTER (WHERE {_DONE} AND {_PERIOD}), 0) "
        f"AS savings FROM pub.agg_procurement_lots l WHERE {where} GROUP BY l.branch_id"),
        {**params, **_bind(period)}).all()}
    p_where, p_params = sel.rows("p.branch_id")
    plans = dict(db.execute(text(
        f"SELECT p.branch_id, sum(p.plan) FROM pub.agg_procurement_plan p WHERE {p_where} "
        "AND p.month_id = :year01 GROUP BY p.branch_id"),
        {**p_params, "year01": period.last_month // 100 * 100 + 1}).all())
    ids = sorted(set(lots_by) | {int(b) for b in plans})
    if not ids:
        return []
    names = dict(db.execute(text("SELECT branch_id, name FROM pub.branches "
                                 "WHERE branch_id = ANY(:ids)"), {"ids": ids}).all())
    out = [ProcBranch(i, names.get(i, str(i)), num(plans.get(i)),
                      num(lots_by[i].ytd) if i in lots_by else 0.0,
                      round(num(lots_by[i].savings), 2) if i in lots_by else 0.0) for i in ids]
    return sorted(out, key=lambda b: (-b.ytd, b.name))
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sections_procurement.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(sections): xarid ko'rsatkichlari — shartnomalar, tejash, reja, lotlar, usullar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 8: АИП so'rovlari — dastur, grafik bajarilishi, moliyaviy/jismoniy, uzilish, avanslar, manbalar, bosqichlar

**Files:**
- Create: `backend/app/sections/queries/investment.py`
- Test: `backend/tests/test_sections_investment.py`

**Interfaces:**
- Consumes: `pub.agg_investment_month`, `pub.agg_object_stages`, `pub.branches`, `BranchSel.rows`, `ReportPeriod` (`months`, `last_month`, `open_last`, `date_to`), `from_date_id`, `num`, `opt`, `procurement.ratio`, `tests.s4_helpers.investment_scenario`.
- Produces (`app.sections.queries.investment`):
  - `ON_TRACK = 0.9`, `THREAT = 0.75`, `GAP_PP = 20.0` (UI belgilari uchun), `ADVANCE_DAYS = 90`.
  - `InvObject(object_id, object_code, name, program_code, work_type, source_name, commissioning_year, total_cost, branch_id, branch_name, plan_year, plan_to_date, fact_ytd, fact_period, prior, physical, advance, advance_days)` + `.execution`, `.status` (`ok | lag | risk | None`), `.financial`, `.gap_pp`.
  - `InvTotals(objects, total_cost, program, plan_to_date, fact_ytd, fact_period, lagging, threatened, commissioning, year)` + `.execution`, `.has_objects`.
  - `CumPoint(month_id, plan, fact: float | None)`, `SourceRow(name, plan_year, fact_ytd)` + `.share`, `StageRow(object_id, stage_no, name, plan_date, fact_date, done, late)`.
  - `objects(db, sel, period) -> list[InvObject]` (yil rejasi yoki fakti bor obyektlar, reja bo'yicha kamayish), `totals(objects, period) -> InvTotals`, `cumulative(db, sel, year, today) -> list[CumPoint]` (12 oy; fakt — joriy oygacha), `sources(objects) -> list[SourceRow]`, `stages(db, sel) -> dict[int, list[StageRow]]` (oxirgi snapshot).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sections_investment.py`:
```python
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import investment
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s4_helpers import InvScenario, investment_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _objects(db: Session, sc: InvScenario, per: str) -> dict[int, investment.InvObject]:
    rows = investment.objects(db, BranchSel(sc.branch_id, True), resolve_period(per, TEST_AS_OF))
    return {o.object_id: o for o in rows}


def test_closed_month_objects(sc: InvScenario, db: Session) -> None:
    objs = _objects(db, sc, "m08")
    a, b = objs[sc.obj_a], objs[sc.obj_b]
    assert (a.plan_year, a.plan_to_date, a.fact_ytd, a.fact_period, a.prior) == (
        240.0, 120.0, 90.0, 40.0, 400.0)
    assert (a.execution, a.status, a.financial, a.physical, a.gap_pp) == (
        0.75, "lag", 0.49, 0.4, 9.0)
    assert (a.advance, a.advance_days) == (30.0, 91)
    assert (b.execution, b.status, b.financial, b.physical, b.gap_pp) == (
        0.9, "ok", 0.38, 0.05, 33.0)
    assert (b.advance, b.advance_days, b.source_name) == (20.0, 113, f"МФИ тест {sc.tag}")
    assert list(objs) == [sc.obj_a, sc.obj_b]  # yil rejasi bo'yicha kamayish


def test_totals(sc: InvScenario, db: Session) -> None:
    period = resolve_period("m08", TEST_AS_OF)
    t = investment.totals(list(_objects(db, sc, "m08").values()), period)
    assert (t.program, t.plan_to_date, t.fact_ytd, t.execution, t.fact_period) == (
        440.0, 220.0, 180.0, 0.818182, 130.0)
    assert (t.lagging, t.threatened, t.commissioning, t.total_cost, t.year) == (
        1, 0, 1, 1500.0, 2026)
    assert t.has_objects and len(t.objects) == 2


def test_open_month_prorates_schedule(sc: InvScenario, db: Session) -> None:
    objs = _objects(db, sc, "m09")
    a, b = objs[sc.obj_a], objs[sc.obj_b]
    assert (a.plan_to_date, a.fact_ytd, a.execution, a.status) == (168.0, 110.0, 0.654762, "risk")
    assert (a.physical, a.gap_pp, a.advance, a.advance_days) == (0.45, 6.0, 0.0, None)
    assert (b.plan_to_date, b.fact_ytd, b.execution, b.physical, b.gap_pp) == (
        180.0, 120.0, 0.666667, 0.05, 39.0)
    assert b.advance_days == 137
    t = investment.totals(list(objs.values()), resolve_period("m09", TEST_AS_OF))
    assert (t.plan_to_date, t.fact_ytd, t.execution, t.threatened) == (348.0, 230.0, 0.66092, 2)


def test_cumulative_sources_stages(sc: InvScenario, db: Session) -> None:
    sel = BranchSel(sc.branch_id, True)
    cum = {p.month_id: (p.plan, p.fact) for p in investment.cumulative(db, sel, 2026,
                                                                       TEST_AS_OF)}
    assert len(cum) == 12 and cum[202606] == (0.0, 0.0)
    assert (cum[202607], cum[202608], cum[202609]) == ((60.0, 50.0), (220.0, 180.0),
                                                       (380.0, 230.0))
    assert cum[202610] == (440.0, None) and cum[202612] == (440.0, None)
    src = investment.sources(list(_objects(db, sc, "m08").values()))
    assert [(s.name, s.plan_year, s.fact_ytd, s.share) for s in src] == [
        (f"Бюджет тест {sc.tag}", 240.0, 90.0, 0.375), (f"МФИ тест {sc.tag}", 200.0, 90.0, 0.45)]
    stages = investment.stages(db, sel)[sc.obj_a]
    assert [(s.stage_no, s.done, s.late) for s in stages] == [
        (1, True, False), (2, True, True), (3, False, True), (4, False, False)]
    assert stages[1].fact_date == date(2026, 7, 20) and stages[2].fact_date is None


def test_branch_without_objects(sc: InvScenario) -> None:
    with new_session() as s:
        apply_rls(s, None)
        rows = investment.objects(s, BranchSel(999_999, True), resolve_period("m08", TEST_AS_OF))
    t = investment.totals(rows, resolve_period("m08", TEST_AS_OF))
    assert rows == [] and not t.has_objects and t.execution is None and t.program == 0.0
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        own = investment.objects(s, BranchSel(None, False), resolve_period("m08", TEST_AS_OF))
    assert {o.object_id for o in own} == {sc.obj_a, sc.obj_b}
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sections_investment.py -v`
Expected: FAIL — `ImportError: cannot import name 'investment' from 'app.sections.queries'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/sections/queries/investment.py`:
```python
"""Адресная инвестиционная программа (TZ 4 «Инвестиции (Адреса)») — faqat pub.agg_investment_month,
pub.agg_object_stages va pub.branches dan.

Davr yili = davr oxirgi oyining yili. План на отчётную дату = yil boshidan oldingi oylar rejasi +
oxirgi oy rejasi (ochiq oyda — o'tgan kunlar ulushi). Освоено ранее = yil boshigacha bo'lgan fakt
va ochilish qoldig'i. КС-2 va avans — davr oxirigacha oxirgi ma'lum qiymat (agregatda to'ldirilgan).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id, month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num, opt
from app.sections.queries.procurement import ratio
from app.sections.scope import BranchSel

ON_TRACK = 0.9  # TZ 4: «по графику ≥ 90%, отстаёт 75–90%, под угрозой < 75%»
THREAT = 0.75
GAP_PP = 20.0
ADVANCE_DAYS = 90


@dataclass(frozen=True, slots=True)
class InvObject:
    object_id: int
    object_code: str
    name: str
    program_code: str | None
    work_type: str
    source_name: str
    commissioning_year: int | None
    total_cost: float | None
    branch_id: int
    branch_name: str
    plan_year: float
    plan_to_date: float
    fact_ytd: float
    fact_period: float
    prior: float
    physical: float | None
    advance: float
    advance_days: int | None

    @property
    def execution(self) -> float | None:
        """Исполнение графика = факт / план на отчётную дату."""
        return ratio(self.fact_ytd, self.plan_to_date)

    @property
    def status(self) -> str | None:
        e = self.execution
        if e is None:
            return None
        return "ok" if e >= ON_TRACK else "lag" if e >= THREAT else "risk"

    @property
    def financial(self) -> float | None:
        """(освоено ранее + освоено в году) / общая стоимость объекта."""
        return ratio(self.prior + self.fact_ytd, self.total_cost or 0.0)

    @property
    def gap_pp(self) -> float | None:
        if self.financial is None or self.physical is None:
            return None
        return round((self.financial - self.physical) * 100, 1)


@dataclass(frozen=True, slots=True)
class InvTotals:
    objects: tuple[InvObject, ...]
    total_cost: float
    program: float
    plan_to_date: float
    fact_ytd: float
    fact_period: float
    lagging: int
    threatened: int
    commissioning: int
    year: int

    @property
    def execution(self) -> float | None:
        return ratio(self.fact_ytd, self.plan_to_date)

    @property
    def has_objects(self) -> bool:
        return bool(self.objects)


@dataclass(frozen=True, slots=True)
class CumPoint:
    month_id: int
    plan: float
    fact: float | None


@dataclass(frozen=True, slots=True)
class SourceRow:
    name: str
    plan_year: float
    fact_ytd: float

    @property
    def share(self) -> float | None:
        return ratio(self.fact_ytd, self.plan_year)


@dataclass(frozen=True, slots=True)
class StageRow:
    object_id: int
    stage_no: int
    name: str
    plan_date: date
    fact_date: date | None
    done: bool
    late: bool


def _fraction(period: ReportPeriod) -> float:
    if not period.open_last:
        return 1.0
    end = period.date_to
    return end.day / calendar.monthrange(end.year, end.month)[1]


def objects(db: Session, sel: BranchSel, period: ReportPeriod) -> list[InvObject]:
    last = period.last_month
    y01, y12 = last // 100 * 100 + 1, last // 100 * 100 + 12
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name AS branch_name, a.object_id, a.object_code, a.name, "
        "a.program_code, a.work_type, a.source_name, a.commissioning_year, a.total_cost, "
        "coalesce(sum(a.plan) FILTER (WHERE a.month_id BETWEEN :y01 AND :y12), 0) AS plan_year, "
        "coalesce(sum(a.plan) FILTER (WHERE a.month_id >= :y01 AND a.month_id < :last), 0) "
        "AS plan_before, "
        "coalesce(sum(a.plan) FILTER (WHERE a.month_id = :last), 0) AS plan_last, "
        "coalesce(sum(a.fact) FILTER (WHERE a.month_id BETWEEN :y01 AND :last), 0) AS fact_ytd, "
        "coalesce(sum(a.fact) FILTER (WHERE a.month_id = ANY(:months)), 0) AS fact_period, "
        "coalesce(sum(a.fact) FILTER (WHERE a.month_id < :y01), 0) "
        "+ coalesce(sum(a.opening) FILTER (WHERE a.month_id <= :last), 0) AS prior, "
        "(array_agg(a.physical_pct ORDER BY a.month_id DESC) FILTER (WHERE a.month_id <= :last "
        "AND a.physical_pct IS NOT NULL))[1] AS phys, "
        "(array_agg(a.advance ORDER BY a.month_id DESC) FILTER (WHERE a.month_id <= :last "
        "AND a.advance IS NOT NULL))[1] AS adv, "
        "(array_agg(a.advance_date_id ORDER BY a.month_id DESC) FILTER (WHERE a.month_id <= :last "
        "AND a.advance IS NOT NULL))[1] AS adv_date "
        "FROM pub.agg_investment_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} GROUP BY a.branch_id, b.name, a.object_id, a.object_code, a.name, "
        "a.program_code, a.work_type, a.source_name, a.commissioning_year, a.total_cost"),
        {**params, "y01": y01, "y12": y12, "last": last, "months": list(period.months)}).all()
    frac = _fraction(period)
    out: list[InvObject] = []
    for r in rows:
        plan_year, fact_ytd = num(r.plan_year), num(r.fact_ytd)
        if plan_year <= 0 and fact_ytd <= 0:
            continue
        advance = num(r.adv)
        days = None
        if advance > 0 and r.adv_date is not None:
            days = (period.date_to - from_date_id(int(r.adv_date))).days
        out.append(InvObject(
            object_id=int(r.object_id), object_code=r.object_code, name=r.name,
            program_code=r.program_code, work_type=r.work_type, source_name=r.source_name,
            commissioning_year=None if r.commissioning_year is None else int(r.commissioning_year),
            total_cost=opt(r.total_cost), branch_id=int(r.branch_id), branch_name=r.branch_name,
            plan_year=plan_year,
            plan_to_date=round(num(r.plan_before) + num(r.plan_last) * frac, 2),
            fact_ytd=fact_ytd, fact_period=num(r.fact_period), prior=num(r.prior),
            physical=opt(r.phys), advance=advance, advance_days=days))
    return sorted(out, key=lambda o: (-o.plan_year, o.name))


def totals(rows: list[InvObject], period: ReportPeriod) -> InvTotals:
    year = period.last_month // 100
    return InvTotals(
        objects=tuple(rows), total_cost=round(sum(o.total_cost or 0.0 for o in rows), 2),
        program=round(sum(o.plan_year for o in rows), 2),
        plan_to_date=round(sum(o.plan_to_date for o in rows), 2),
        fact_ytd=round(sum(o.fact_ytd for o in rows), 2),
        fact_period=round(sum(o.fact_period for o in rows), 2),
        lagging=sum(1 for o in rows if o.status in ("lag", "risk")),
        threatened=sum(1 for o in rows if o.status == "risk"),
        commissioning=sum(1 for o in rows if o.commissioning_year == year), year=year)


def cumulative(db: Session, sel: BranchSel, year: int, today: date) -> list[CumPoint]:
    months = [year * 100 + m for m in range(1, 13)]
    where, params = sel.rows("a.branch_id")
    by: dict[int, Any] = {int(r.month_id): r for r in db.execute(text(
        "SELECT a.month_id, sum(a.plan) AS plan, sum(a.fact) AS fact "
        f"FROM pub.agg_investment_month a WHERE {where} AND a.month_id = ANY(:m) "
        "GROUP BY a.month_id"), {**params, "m": months}).all()}
    current = month_id(today)
    out: list[CumPoint] = []
    plan = fact = 0.0
    for m in months:
        plan += num(by[m].plan) if m in by else 0.0
        fact += num(by[m].fact) if m in by else 0.0
        out.append(CumPoint(m, round(plan, 2), round(fact, 2) if m <= current else None))
    return out


def sources(rows: list[InvObject]) -> list[SourceRow]:
    plan: dict[str, float] = defaultdict(float)
    fact: dict[str, float] = defaultdict(float)
    for o in rows:
        plan[o.source_name] += o.plan_year
        fact[o.source_name] += o.fact_ytd
    out = [SourceRow(name, round(plan[name], 2), round(fact[name], 2)) for name in plan]
    return sorted(out, key=lambda s: (-s.plan_year, s.name))


def stages(db: Session, sel: BranchSel) -> dict[int, list[StageRow]]:
    where, params = sel.rows("s.branch_id")
    rows = db.execute(text(
        "SELECT s.object_id, s.stage_no, s.stage_name, s.plan_date_id, s.fact_date_id, s.done, "
        f"s.late FROM pub.agg_object_stages s WHERE {where} AND s.month_id = "
        f"(SELECT max(x.month_id) FROM pub.agg_object_stages x) "
        "ORDER BY s.object_id, s.stage_no"), params).all()
    out: dict[int, list[StageRow]] = defaultdict(list)
    for r in rows:
        out[int(r.object_id)].append(StageRow(
            object_id=int(r.object_id), stage_no=int(r.stage_no), name=r.stage_name,
            plan_date=from_date_id(int(r.plan_date_id)),
            fact_date=None if r.fact_date_id is None else from_date_id(int(r.fact_date_id)),
            done=bool(r.done), late=bool(r.late)))
    return dict(out)
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sections_investment.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(sections): АИП ko'rsatkichlari — grafik bajarilishi, moliyaviy/jismoniy, avanslar, bosqichlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 9: Kadrlar so'rovlari — штат/факт, вакансии, ФОТ (pul oqimidan), o'rtacha ish haqi, qo'nimsizlik, soatlar

**Files:**
- Create: `backend/app/sections/queries/hr.py`
- Test: `backend/tests/test_sections_hr.py`

**Interfaces:**
- Consumes: `pub.agg_hr_month`, `pub.agg_cash_month`, `pub.items`, `pub.branches`, `BranchSel.total/rows`, `ReportPeriod` (`months`, `last_month`, `month_equivalents`, `today`), `month_id`, `num`, `procurement.ratio`, `tests.s4_helpers.hr_scenario`.
- Produces (`app.sections.queries.hr`):
  - `HrFigures(snap_month, plan, fact, payroll, outflow, hired, fired, overtime, months)` + `.vacancies` (штат 0 → None), `.vacancy_share`, `.fill`, `.payroll_share`, `.avg_salary`, `.turnover`, `.overtime_per_employee`, `.has_data`.
  - `HrBranch(branch_id, name, plan, fact, payroll, hired, fired, overtime, months)` + xuddi shu xossalar (`vacancies`, `fill`, `avg_salary`, `turnover`, `overtime_per_employee`).
  - `HrMonth(month_id, payroll, fact, avg_salary, hired, fired, overtime)`, `NamedValue(name, value)`.
  - `totals(db, sel, period, salary_codes)`, `categories(db, sel, period) -> list[NamedValue]`, `by_branch(db, sel, period, salary_codes)`, `monthly(db, sel, today, salary_codes)`. Штат/факт — davr oxirgi oyidan kechmagan eng oxirgi ma'lumotli oy.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sections_hr.py`:
```python
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import hr
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s4_helpers import HrScenario, hr_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _totals(db: Session, sc: HrScenario, per: str) -> hr.HrFigures:
    return hr.totals(db, BranchSel(sc.branch_id, True), resolve_period(per, TEST_AS_OF),
                     [sc.salary_code])


def test_closed_month_totals(sc: HrScenario, db: Session) -> None:
    t = _totals(db, sc, "m08")
    assert (t.snap_month, t.plan, t.fact, t.vacancies, t.vacancy_share, t.fill) == (
        202608, 100.0, 90.0, 10.0, 0.1, 0.9)
    assert (t.payroll, t.outflow, t.payroll_share, t.avg_salary) == (180.0, 600.0, 0.3, 2.0)
    assert (t.hired, t.fired, t.turnover) == (3, 3, 0.033333)
    assert (t.overtime, t.overtime_per_employee) == (420.0, 4.666667) and t.has_data


def test_open_month_uses_month_equivalents(sc: HrScenario, db: Session) -> None:
    t = _totals(db, sc, "m09")
    assert (t.snap_month, t.fact, t.payroll, t.payroll_share, t.months) == (
        202609, 90.0, 150.0, 0.6, 0.8)
    assert (t.avg_salary, t.turnover, t.overtime_per_employee) == (2.083333, 0.022222, 2.333333)
    q = _totals(db, sc, "q3")
    assert (q.payroll, q.outflow, q.payroll_share, q.avg_salary) == (500.0, 1020.0, 0.490196,
                                                                      1.984127)
    assert (q.hired, q.fired, q.turnover, q.overtime, q.overtime_per_employee) == (
        6, 7, 0.077778, 945.0, 10.5)


def test_categories_branches_months(sc: HrScenario, db: Session) -> None:
    sel = BranchSel(sc.branch_id, True)
    period = resolve_period("m08", TEST_AS_OF)
    assert [(c.name, c.value) for c in hr.categories(db, sel, period)] == [
        ("Оперативный персонал", 81.0), ("Руководители", 9.0)]
    rows = hr.by_branch(db, sel, period, [sc.salary_code])
    assert [(r.branch_id, r.plan, r.fact, r.vacancies, r.payroll, r.avg_salary, r.turnover)
            for r in rows] == [(sc.branch_id, 100.0, 90.0, 10.0, 180.0, 2.0, 0.033333)]
    months = {m.month_id: m for m in hr.monthly(db, sel, TEST_AS_OF, [sc.salary_code])}
    assert list(months) == list(range(202601, 202610))
    assert (months[202607].payroll, months[202607].fact, months[202607].avg_salary) == (
        170.0, 91.0, 1.868132)
    assert (months[202609].avg_salary, months[202609].hired, months[202609].fired) == (
        2.083333, 2, 2)
    assert months[202601].avg_salary is None and months[202601].payroll == 0.0


def test_period_without_hr_data(sc: HrScenario, db: Session) -> None:
    t = _totals(db, sc, "m06")
    assert not t.has_data and t.snap_month is None
    assert (t.vacancies, t.avg_salary, t.turnover, t.overtime_per_employee) == (
        None, None, None, None)
    no_codes = hr.totals(db, BranchSel(sc.branch_id, True), resolve_period("m08", TEST_AS_OF), [])
    assert no_codes.payroll == 0.0 and no_codes.outflow == 600.0


def test_limited_scope(sc: HrScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = hr.totals(s, BranchSel(None, all_scope=False), resolve_period("m08", TEST_AS_OF),
                      [sc.salary_code])
    assert (t.plan, t.fact, t.payroll) == (100.0, 90.0, 180.0)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sections_hr.py -v`
Expected: FAIL — `ImportError: cannot import name 'hr' from 'app.sections.queries'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/sections/queries/hr.py`:
```python
"""Kadrlar (TZ 4 «Кадры») — faqat pub.agg_hr_month, pub.agg_cash_month/pub.items va pub.branches.

Штат/факт — davr oxirgi oyidan kechmagan eng oxirgi ma'lumotli oy (oylik fayl hali kelmagan joriy
oyda nol ko'rsatilmasin). ФОТ — pul oqimidan: `kazna.calendar_kinds.salary` statyalari rasxodi
(TZ formulasi); доля — ФОТ / tanlovning barcha rasxodi. O'rtacha ish haqi = ФОТ / численность /
oylar (ochiq oy — o'tgan kunlar ulushi). Qo'nimsizlik = уволено / численность (yilga
hisoblanmaydi). Faqat agregatlar — ФИО yo'q (TZ 9).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.queries.procurement import ratio
from app.sections.scope import BranchSel

_NO_CODE = ["—"]  # bo'sh ro'yxat o'rniga (ANY('{}') turini PG aniqlay olmaydi)


def _codes(salary_codes: list[str]) -> list[str]:
    return list(salary_codes) or _NO_CODE


class _Derived:
    """Filial va jami uchun umumiy hosila xossalar (maydonlar — voris dataclass'larda)."""

    __slots__ = ()
    plan: float
    fact: float
    payroll: float
    fired: int
    overtime: float
    months: float

    @property
    def vacancies(self) -> float | None:
        return None if self.plan <= 0 else round(self.plan - self.fact, 1)

    @property
    def vacancy_share(self) -> float | None:
        return None if self.vacancies is None else ratio(self.vacancies, self.plan)

    @property
    def fill(self) -> float | None:
        return ratio(self.fact, self.plan)

    @property
    def avg_salary(self) -> float | None:
        """Средняя зарплата = ФОТ / численность / число месяцев периода."""
        if self.fact <= 0 or self.months <= 0:
            return None
        return round(self.payroll / self.fact / self.months, 6)

    @property
    def turnover(self) -> float | None:
        return ratio(float(self.fired), self.fact)

    @property
    def overtime_per_employee(self) -> float | None:
        return ratio(self.overtime, self.fact)


@dataclass(frozen=True, slots=True)
class HrFigures(_Derived):
    snap_month: int | None
    plan: float
    fact: float
    payroll: float
    outflow: float
    hired: int
    fired: int
    overtime: float
    months: float

    @property
    def payroll_share(self) -> float | None:
        return ratio(self.payroll, self.outflow)

    @property
    def has_data(self) -> bool:
        return self.fact > 0 or self.plan > 0


@dataclass(frozen=True, slots=True)
class HrBranch(_Derived):
    branch_id: int
    name: str
    plan: float
    fact: float
    payroll: float
    hired: int
    fired: int
    overtime: float
    months: float


@dataclass(frozen=True, slots=True)
class HrMonth:
    month_id: int
    payroll: float
    fact: float
    avg_salary: float | None
    hired: int
    fired: int
    overtime: float


@dataclass(frozen=True, slots=True)
class NamedValue:
    name: str
    value: float


def _snap_month(db: Session, where: str, params: dict[str, Any], last: int) -> int | None:
    value = db.execute(text(
        f"SELECT max(h.month_id) FROM pub.agg_hr_month h WHERE {where} AND h.month_id <= :last "
        "AND (h.headcount_fact > 0 OR h.headcount_plan > 0)"), {**params, "last": last}).scalar()
    return None if value is None else int(value)


def _payroll(db: Session, where: str, params: dict[str, Any], months: list[int],
             codes: list[str]) -> tuple[float, float]:
    row = db.execute(text(
        "SELECT coalesce(sum(c.outflow) FILTER (WHERE i.code = ANY(:codes)), 0) AS pay, "
        "coalesce(sum(c.outflow), 0) AS total FROM pub.agg_cash_month c "
        f"JOIN pub.items i ON i.item_id = c.item_id WHERE {where} AND c.month_id = ANY(:months)"),
        {**params, "codes": _codes(codes), "months": months}).one()
    return num(row.pay), num(row.total)


def totals(db: Session, sel: BranchSel, period: ReportPeriod,
           salary_codes: list[str]) -> HrFigures:
    where, params = sel.total("h.branch_id")
    snap = _snap_month(db, where, params, period.last_month)
    head = db.execute(text(
        "SELECT coalesce(sum(h.headcount_plan), 0) AS plan, "
        "coalesce(sum(h.headcount_fact), 0) AS fact FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = :snap"), {**params, "snap": snap or 0}).one()
    flow = db.execute(text(
        "SELECT coalesce(sum(h.hired), 0) AS hired, coalesce(sum(h.fired), 0) AS fired, "
        "coalesce(sum(h.overtime_hours), 0) AS ot FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = ANY(:months)"),
        {**params, "months": list(period.months)}).one()
    c_where, c_params = sel.total("c.branch_id")
    payroll, outflow = _payroll(db, c_where, c_params, list(period.months), salary_codes)
    return HrFigures(
        snap_month=snap, plan=num(head.plan), fact=num(head.fact), payroll=payroll,
        outflow=outflow, hired=int(flow.hired), fired=int(flow.fired), overtime=num(flow.ot),
        months=round(period.month_equivalents, 6))


def categories(db: Session, sel: BranchSel, period: ReportPeriod) -> list[NamedValue]:
    where, params = sel.total("h.branch_id")
    snap = _snap_month(db, where, params, period.last_month)
    rows = db.execute(text(
        "SELECT h.category, sum(h.headcount_fact) AS v FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = :snap GROUP BY h.category "
        "HAVING sum(h.headcount_fact) > 0 ORDER BY v DESC, h.category"),
        {**params, "snap": snap or 0}).all()
    return [NamedValue(r.category, num(r.v)) for r in rows]


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod,
              salary_codes: list[str]) -> list[HrBranch]:
    where, params = sel.rows("h.branch_id")
    x_where, _ = sel.rows("x.branch_id")
    head = {int(r.branch_id): r for r in db.execute(text(
        "SELECT h.branch_id, sum(h.headcount_plan) AS plan, sum(h.headcount_fact) AS fact "
        "FROM pub.agg_hr_month h JOIN (SELECT x.branch_id, max(x.month_id) AS m "
        f"FROM pub.agg_hr_month x WHERE {x_where} AND x.month_id <= :last "
        "GROUP BY x.branch_id) s ON s.branch_id = h.branch_id AND s.m = h.month_id "
        "GROUP BY h.branch_id"), {**params, "last": period.last_month}).all()}
    flow = {int(r.branch_id): r for r in db.execute(text(
        "SELECT h.branch_id, sum(h.hired) AS hired, sum(h.fired) AS fired, "
        "sum(h.overtime_hours) AS ot FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = ANY(:months) GROUP BY h.branch_id"),
        {**params, "months": list(period.months)}).all()}
    c_where, c_params = sel.rows("c.branch_id")
    pay = dict(db.execute(text(
        "SELECT c.branch_id, sum(c.outflow) FROM pub.agg_cash_month c "
        f"JOIN pub.items i ON i.item_id = c.item_id WHERE {c_where} "
        "AND c.month_id = ANY(:months) AND i.code = ANY(:codes) GROUP BY c.branch_id"),
        {**c_params, "months": list(period.months), "codes": _codes(salary_codes)}).all())
    ids = sorted(set(head) | set(flow))
    if not ids:
        return []
    names = dict(db.execute(text("SELECT branch_id, name FROM pub.branches "
                                 "WHERE branch_id = ANY(:ids)"), {"ids": ids}).all())
    months = round(period.month_equivalents, 6)
    out = [HrBranch(
        branch_id=i, name=names.get(i, str(i)),
        plan=num(head[i].plan) if i in head else 0.0, fact=num(head[i].fact) if i in head else 0.0,
        payroll=num(pay.get(i)), hired=int(flow[i].hired) if i in flow else 0,
        fired=int(flow[i].fired) if i in flow else 0,
        overtime=num(flow[i].ot) if i in flow else 0.0, months=months) for i in ids]
    return sorted(out, key=lambda b: (-b.fact, b.name))


def monthly(db: Session, sel: BranchSel, today: date,
            salary_codes: list[str]) -> list[HrMonth]:
    months = [today.year * 100 + m for m in range(1, month_id(today) % 100 + 1)]
    where, params = sel.total("h.branch_id")
    by = {int(r.month_id): r for r in db.execute(text(
        "SELECT h.month_id, sum(h.headcount_fact) AS fact, sum(h.hired) AS hired, "
        "sum(h.fired) AS fired, sum(h.overtime_hours) AS ot FROM pub.agg_hr_month h "
        f"WHERE {where} AND h.month_id = ANY(:m) GROUP BY h.month_id"),
        {**params, "m": months}).all()}
    c_where, c_params = sel.total("c.branch_id")
    pay = dict(db.execute(text(
        "SELECT c.month_id, sum(c.outflow) FROM pub.agg_cash_month c "
        f"JOIN pub.items i ON i.item_id = c.item_id WHERE {c_where} "
        "AND c.month_id = ANY(:m) AND i.code = ANY(:codes) GROUP BY c.month_id"),
        {**c_params, "m": months, "codes": _codes(salary_codes)}).all())
    current = month_id(today)
    part = today.day / calendar.monthrange(today.year, today.month)[1]
    out: list[HrMonth] = []
    for m in months:
        row = by.get(m)
        fact = num(row.fact) if row else 0.0
        payroll = num(pay.get(m))
        share = part if m == current else 1.0
        avg = None if fact <= 0 else round(payroll / fact / share, 6)
        out.append(HrMonth(m, payroll, fact, avg, int(row.hired) if row else 0,
                           int(row.fired) if row else 0, num(row.ot) if row else 0.0))
    return out
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sections_hr.py -v` va `$TEST mypy app`
Expected: 5 passed; mypy xatosiz.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(sections): kadrlar ko'rsatkichlari — штат/факт, вакансии, ФОТ, o'rtacha ish haqi, qo'nimsizlik

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 10: «Закупки» API — Сводка, Лоты, Договоры и поставщики, Экономия

**Files:**
- Create: `backend/app/sections/zakupki_schemas.py`, `backend/app/sections/zakupki.py`
- Modify: `backend/app/main.py` (router), `backend/tests/test_route_guards.py`, `backend/tests/s4_helpers.py` (`section_branch_role`)
- Test: `backend/tests/test_zakupki_api.py`

**Interfaces:**
- Consumes: `SQ`/`SectionQuery`, `get_today`, `Cache`, `get_db`, `require_perm`, `section_perm`, `Section.ZAKUPKI`, `schemas._Out`, `ReportPeriodOut`, `period_out`, `queries.procurement.*`, `from_date_id`, `Role`, `RolePermission`, `new_session`, `tests.s4_helpers.procurement_scenario`, `published_synthetic`, `tests.helpers.login`, `make_user`.
- Produces:
  - `app.sections.zakupki_schemas`: `ZakKpisOut(has_data, contracted, contracts, start_contracted, savings, savings_share, ytd, plan, plan_execution, in_work, in_work_start, overdue, overdue_start, direct, direct_share, avg_days, cancelled, cancelled_start)`, `ZakMonthOut(month_id, contracted)`, `ZakMethodOut(method, title, lots, start, contracted, savings, savings_share, avg_days, norm_days)`, `ZakLotOut(lot_no, branch_id, branch_name, date, method, method_title, subject, status, kind, start_price, contract_price, days, norm_days, overdue, supplier)`, `ZakNamedOut(name, amount, count)`, `ZakBranchOut(branch_id, name, plan, ytd, execution, savings)`, `ZakSvodOut(period, kpis, months, methods, lots)`, `ZakLotyOut(period, kpis, lots, truncated)`, `ZakPostavshikiOut(period, kpis, suppliers, subjects, branches)`, `ZakEkonomiyaOut(period, kpis, methods, cancelled)`; konvertorlar `zak_kpis_out`, `lot_out`, `method_out`.
  - `app.sections.zakupki`: `router` (`/zakupki`), `SVOD_LOTS = 8`, `build_svod`, `build_loty`, `build_postavshiki`, `build_ekonomiya`. HTTP: `GET /zakupki/svod`, `/zakupki/loty`, `/zakupki/postavshiki`, `/zakupki/ekonomiya`.
  - `tests.s4_helpers.section_branch_role(section: str) -> str` — `scope_all = false` va faqat `section:<section>:view` ruxsatli test roli (`t_<section>_branch`).

- [ ] **Step 1: Test yordamchisi — filial doirasidagi rol**

`backend/tests/s4_helpers.py` — importlarni to'ldiring:
```python
from sqlalchemy import select, text

from app.auth.models import Role, RolePermission
from app.core.db import new_session
```
va fayl oxiriga qo'shing:
```python
def section_branch_role(section: str) -> str:
    """Filial doirasidagi (scope_all = false) va faqat bitta bo'limni ko'radigan test roli —
    seed rollarida «Закупки»/«Инвестиции» uchun bunday rol yo'q."""
    code = f"t_{section}_branch"
    with new_session() as s:
        exists = s.execute(select(Role.id).where(Role.code == code)).scalar()
        if exists is None:
            role = Role(code=code, name=f"Тест: {section} филиала", scope_all=False)
            s.add(role)
            s.flush()
            s.add(RolePermission(role_id=role.id, permission_code=f"section:{section}:view"))
            s.commit()
    return code
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_zakupki_api.py`:
```python
from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.helpers import SeedUser, login
from tests.s4_helpers import ProcScenario, procurement_scenario, section_branch_role

PAGES = ("svod", "loty", "postavshiki", "ekonomiya")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def app_factory() -> Iterator[Callable[[], TestClient]]:
    clients: list[TestClient] = []

    def make() -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _as(app_factory: Callable[[], TestClient], user: SeedUser) -> TestClient:
    return login(app_factory(), user)


def test_svod_numbers_and_etag(sc: ProcScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/zakupki/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["contracted"], k["contracts"], k["savings"], k["savings_share"]) == (
        140.0, 2, 10.0, 0.066667)
    assert (k["plan_execution"], k["in_work"], k["overdue"], k["direct_share"]) == (
        0.197, 1, 1, 0.357143)
    assert k["avg_days"] == 8.5 and body["period"]["code"] == "m08"
    assert body["months"][7] == {"month_id": 202608, "contracted": 140.0}
    assert [m["method"] for m in body["methods"]] == ["eshop", "direct"]
    lot = body["lots"][0]
    assert (lot["lot_no"], lot["kind"], lot["overdue"], lot["date"], lot["days"]) == (
        "L4", "work", True, "2026-07-01", 85)
    again = client.get("/api/v1/zakupki/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_loty_postavshiki_ekonomiya(sc: ProcScenario, app_factory: Callable[[], TestClient],
                                    make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    loty = client.get("/api/v1/zakupki/loty", params=params).json()
    assert [x["lot_no"] for x in loty["lots"]] == ["L4", "L1", "L2", "L6"]
    assert loty["truncated"] is False and loty["lots"][1]["supplier"] == (
        f"ООО «Поставщик-1 {sc.tag}»")
    post = client.get("/api/v1/zakupki/postavshiki", params=params).json()
    assert [(s["name"], s["amount"], s["count"]) for s in post["subjects"]] == [
        ("Запасные части", 90.0, 1), ("Ремонтные услуги", 50.0, 1)]
    assert post["branches"] == [{"branch_id": sc.branch_id, "name": f"Тестовая ГЭС {sc.tag}",
                                 "plan": 1000.0, "ytd": 197.0, "execution": 0.197,
                                 "savings": 10.0}]
    eco = client.get("/api/v1/zakupki/ekonomiya", params=params).json()
    assert eco["methods"][0] == {"method": "eshop", "title": "Электронный магазин", "lots": 1,
                                 "start": 100.0, "contracted": 90.0, "savings": 10.0,
                                 "savings_share": 0.1, "avg_days": 12.0, "norm_days": 15}
    assert [c["lot_no"] for c in eco["cancelled"]] == ["L6"]


def test_permission_and_branch_scope(sc: ProcScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    for role in ("spec_kazna", "economist_filiala"):
        client = _as(app_factory, make_user(role, branch_ids=(sc.branch_id,)))
        for page in PAGES:
            assert client.get(f"/api/v1/zakupki/{page}").status_code == 403, (role, page)
    scoped = _as(app_factory, make_user(section_branch_role("zakupki"),
                                        branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = scoped.get(f"/api/v1/zakupki/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = scoped.get("/api/v1/zakupki/postavshiki", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in own["branches"]} == {sc.branch_id}
    assert own["kpis"]["plan"] == 1000.0 and own["kpis"]["contracted"] == 140.0


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/zakupki/svod", params={"per": "m12"}).status_code == 422


def test_synthetic_procurement(published_synthetic: int, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/zakupki/loty", params={"per": "ytd"}).json()
    kinds = {x["kind"] for x in body["lots"]}
    assert {"work", "done"} <= kinds and body["kpis"]["overdue"] >= 1
    assert 0 < body["kpis"]["plan_execution"] < 1.5


def test_pub_views_rls_direct_sql(sc: ProcScenario) -> None:
    for view in ("agg_procurement_lots", "agg_procurement_plan"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga qo'shing:
```python
    ("GET", "/api/v1/zakupki/svod"),
    ("GET", "/api/v1/zakupki/loty"),
    ("GET", "/api/v1/zakupki/postavshiki"),
    ("GET", "/api/v1/zakupki/ekonomiya"),
```
`PREFIX_PERMS` ga qo'shing:
```python
    "/api/v1/zakupki": "section:zakupki:view",
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_zakupki_api.py tests/test_route_guards.py -v`
Expected: FAIL — `404 Not Found` (router yo'q) va `test_route_table_matches_expected_set` yiqiladi.

- [ ] **Step 4: Javob sxemalari**

`backend/app/sections/zakupki_schemas.py`:
```python
"""«Закупки» API javoblari (OpenAPI komponent nomlari noyob — `Zak` prefiksi). Pul — mln so'm,
ulushlar 0..1, kunlar — butun; None — maxraj 0 yoki ma'lumot yo'q."""

from __future__ import annotations

from datetime import date

from app.dwh.dates import from_date_id
from app.sections.queries.procurement import LotRow, MethodRow, ProcFigures
from app.sections.schemas import ReportPeriodOut, _Out


class ZakKpisOut(_Out):
    has_data: bool
    contracted: float
    contracts: int
    start_contracted: float
    savings: float
    savings_share: float | None
    ytd: float
    plan: float
    plan_execution: float | None
    in_work: int
    in_work_start: float
    overdue: int
    overdue_start: float
    direct: float
    direct_share: float | None
    avg_days: float | None
    cancelled: int
    cancelled_start: float


class ZakMonthOut(_Out):
    month_id: int
    contracted: float


class ZakMethodOut(_Out):
    method: str
    title: str
    lots: int
    start: float
    contracted: float
    savings: float
    savings_share: float | None
    avg_days: float | None
    norm_days: int | None


class ZakLotOut(_Out):
    lot_no: str
    branch_id: int
    branch_name: str
    date: date
    method: str
    method_title: str
    subject: str
    status: str
    kind: str
    start_price: float
    contract_price: float | None
    days: int | None
    norm_days: int | None
    overdue: bool
    supplier: str | None


class ZakNamedOut(_Out):
    name: str
    amount: float
    count: int


class ZakBranchOut(_Out):
    branch_id: int
    name: str
    plan: float
    ytd: float
    execution: float | None
    savings: float


class ZakSvodOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    months: list[ZakMonthOut]
    methods: list[ZakMethodOut]
    lots: list[ZakLotOut]


class ZakLotyOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    lots: list[ZakLotOut]
    truncated: bool


class ZakPostavshikiOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    suppliers: list[ZakNamedOut]
    subjects: list[ZakNamedOut]
    branches: list[ZakBranchOut]


class ZakEkonomiyaOut(_Out):
    period: ReportPeriodOut
    kpis: ZakKpisOut
    methods: list[ZakMethodOut]
    cancelled: list[ZakLotOut]


def zak_kpis_out(t: ProcFigures) -> ZakKpisOut:
    return ZakKpisOut(
        has_data=t.has_data, contracted=t.contracted, contracts=t.contracts,
        start_contracted=t.start_contracted, savings=t.savings, savings_share=t.savings_share,
        ytd=t.ytd, plan=t.plan, plan_execution=t.plan_execution, in_work=t.in_work,
        in_work_start=t.in_work_start, overdue=t.overdue, overdue_start=t.overdue_start,
        direct=t.direct, direct_share=t.direct_share, avg_days=t.avg_days,
        cancelled=t.cancelled, cancelled_start=t.cancelled_start)


def method_out(m: MethodRow) -> ZakMethodOut:
    return ZakMethodOut(method=m.method, title=m.title, lots=m.lots, start=m.start,
                        contracted=m.contracted, savings=m.savings,
                        savings_share=m.savings_share, avg_days=m.avg_days,
                        norm_days=m.norm_days)


def lot_out(r: LotRow) -> ZakLotOut:
    return ZakLotOut(
        lot_no=r.lot_no, branch_id=r.branch_id, branch_name=r.branch_name,
        date=from_date_id(r.date_id), method=r.method, method_title=r.method_title,
        subject=r.subject, status=r.status, kind=r.kind, start_price=r.start_price,
        contract_price=r.contract_price, days=r.days, norm_days=r.norm_days, overdue=r.overdue,
        supplier=r.supplier)
```

- [ ] **Step 5: Router**

`backend/app/sections/zakupki.py`:
```python
"""«Закупки» (TZ 5): Сводка, Лоты, Договоры и поставщики, Экономия.

Zanjir: router → queries.procurement (pub view'lar) → Cache.respond (Redis + ETag).
Lotlar filtri («все, в работе, просроченные, заключённые») — klientda, `kind`/`overdue` bo'yicha.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import get_db
from app.sections.deps import SQ, SectionQuery
from app.sections.queries import procurement
from app.sections.schemas import period_out
from app.sections.zakupki_schemas import (
    ZakBranchOut,
    ZakEkonomiyaOut,
    ZakLotyOut,
    ZakMonthOut,
    ZakNamedOut,
    ZakPostavshikiOut,
    ZakSvodOut,
    lot_out,
    method_out,
    zak_kpis_out,
)

router = APIRouter(prefix="/zakupki", tags=["zakupki"],
                   dependencies=[Depends(require_perm(section_perm(Section.ZAKUPKI)))])
DB = Annotated[Session, Depends(get_db)]
SVOD_LOTS = 8  # prototip: «Лоты» kartasida 8 ta + «Все лоты»


def _named(rows: list[procurement.NamedCount]) -> list[ZakNamedOut]:
    return [ZakNamedOut(name=r.name, amount=r.amount, count=r.count) for r in rows]


def build_svod(db: Session, q: SectionQuery) -> ZakSvodOut:
    period, sel = q.period(), q.sel()
    return ZakSvodOut(
        period=period_out(period), kpis=zak_kpis_out(procurement.totals(db, sel, period)),
        months=[ZakMonthOut(month_id=m.month_id, contracted=m.contracted)
                for m in procurement.monthly(db, sel, q.today)],
        methods=[method_out(m) for m in procurement.by_method(db, sel, period)],
        lots=[lot_out(r) for r in procurement.lots(db, sel, period, limit=SVOD_LOTS)])


def build_loty(db: Session, q: SectionQuery) -> ZakLotyOut:
    period, sel = q.period(), q.sel()
    rows = procurement.lots(db, sel, period, limit=procurement.LOTS_LIMIT + 1)
    return ZakLotyOut(period=period_out(period),
                      kpis=zak_kpis_out(procurement.totals(db, sel, period)),
                      lots=[lot_out(r) for r in rows[:procurement.LOTS_LIMIT]],
                      truncated=len(rows) > procurement.LOTS_LIMIT)


def build_postavshiki(db: Session, q: SectionQuery) -> ZakPostavshikiOut:
    period, sel = q.period(), q.sel()
    return ZakPostavshikiOut(
        period=period_out(period), kpis=zak_kpis_out(procurement.totals(db, sel, period)),
        suppliers=_named(procurement.suppliers(db, sel, period)),
        subjects=_named(procurement.subjects(db, sel, period)),
        branches=[ZakBranchOut(branch_id=b.branch_id, name=b.name, plan=b.plan, ytd=b.ytd,
                               execution=b.execution, savings=b.savings)
                  for b in procurement.by_branch(db, sel, period)])


def build_ekonomiya(db: Session, q: SectionQuery) -> ZakEkonomiyaOut:
    period, sel = q.period(), q.sel()
    return ZakEkonomiyaOut(
        period=period_out(period), kpis=zak_kpis_out(procurement.totals(db, sel, period)),
        methods=[method_out(m) for m in procurement.by_method(db, sel, period)],
        cancelled=[lot_out(r) for r in procurement.cancelled(db, sel, period)])


@router.get("/svod", response_model=ZakSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/loty", response_model=ZakLotyOut)
def loty(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.loty", q.cache_filters, lambda: build_loty(db, q))


@router.get("/postavshiki", response_model=ZakPostavshikiOut)
def postavshiki(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.postavshiki", q.cache_filters,
                         lambda: build_postavshiki(db, q))


@router.get("/ekonomiya", response_model=ZakEkonomiyaOut)
def ekonomiya(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("zakupki.ekonomiya", q.cache_filters, lambda: build_ekonomiya(db, q))
```

`backend/app/main.py` — import va `include_router` (S3'ning `sklad_router` qatoridan keyin):
```python
from app.sections.zakupki import router as zakupki_router
```
```python
    app.include_router(zakupki_router, prefix=API_PREFIX)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_zakupki_api.py tests/test_route_guards.py -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(zakupki): Сводка, Лоты, Договоры и поставщики, Экономия API

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 11: «Инвестиции» API — Сводка, Объекты, Источники и освоение, Сроки и риски

**Files:**
- Create: `backend/app/sections/investicii_schemas.py`, `backend/app/sections/investicii.py`
- Modify: `backend/app/main.py` (router), `backend/tests/test_route_guards.py`
- Test: `backend/tests/test_investicii_api.py`

**Interfaces:**
- Consumes: `SQ`/`SectionQuery`, `Cache`, `get_db`, `require_perm`, `Section.INVESTICII`, `_Out`, `ReportPeriodOut`, `period_out`, `queries.investment.*`, `tests.s4_helpers.investment_scenario`, `section_branch_role`, `published_synthetic`, `login`, `make_user`.
- Produces:
  - `app.sections.investicii_schemas`: `InvKpisOut(has_objects, objects, total_cost, program, plan_to_date, fact_ytd, execution, fact_period, lagging, threatened, commissioning, year)`, `InvObjectOut(object_id, object_code, name, program_code, work_type, source_name, commissioning_year, total_cost, branch_id, branch_name, plan_year, plan_to_date, fact_ytd, fact_period, execution, status, financial, physical, gap_pp, advance, advance_days)`, `InvCumOut(month_id, plan, fact)`, `InvSourceOut(name, plan_year, fact_ytd, share)`, `InvStageOut(stage_no, name, plan_date, fact_date, done, late)`, `InvObjectStagesOut(object_id, name, branch_id, late, stages)`, `InvSvodOut(period, kpis, cumulative, sources, objects)`, `InvObektyOut(period, kpis, objects)`, `InvIstochnikiOut(period, kpis, sources, objects, cumulative)`, `InvRiskiOut(period, kpis, lagging, gaps, stages, advances)`; `inv_kpis_out`, `object_out`.
  - `app.sections.investicii`: `router` (`/investicii`), `SVOD_OBJECTS = 6`, `RISK_STAGES = 8`, `build_svod`, `build_obekty`, `build_istochniki`, `build_riski`. Obyektsiz tanlov — `kpis.has_objects = false`, ro'yxatlar bo'sh.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_investicii_api.py`:
```python
from collections.abc import Callable, Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.helpers import SeedUser, login
from tests.s4_helpers import InvScenario, investment_scenario, section_branch_role

PAGES = ("svod", "obekty", "istochniki", "riski")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def app_factory() -> Iterator[Callable[[], TestClient]]:
    clients: list[TestClient] = []

    def make() -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _as(app_factory: Callable[[], TestClient], user: SeedUser) -> TestClient:
    return login(app_factory(), user)


def test_svod_and_obekty(sc: InvScenario, app_factory: Callable[[], TestClient],
                         make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/investicii/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["has_objects"], k["objects"], k["program"], k["plan_to_date"], k["fact_ytd"]) == (
        True, 2, 440.0, 220.0, 180.0)
    assert (k["execution"], k["fact_period"], k["lagging"], k["commissioning"], k["year"]) == (
        0.818182, 130.0, 1, 1, 2026)
    assert len(body["cumulative"]) == 12 and body["cumulative"][7] == {
        "month_id": 202608, "plan": 220.0, "fact": 180.0}
    assert body["cumulative"][9]["fact"] is None
    assert [s["share"] for s in body["sources"]] == [0.375, 0.45]
    first = body["objects"][0]
    assert (first["object_code"], first["status"], first["gap_pp"], first["advance_days"]) == (
        f"OA-{sc.tag}", "lag", 9.0, 91)
    obekty = client.get("/api/v1/investicii/obekty", params=params).json()
    assert [o["object_code"] for o in obekty["objects"]] == [f"OA-{sc.tag}", f"OB-{sc.tag}"]
    again = client.get("/api/v1/investicii/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_istochniki_and_riski(sc: InvScenario, app_factory: Callable[[], TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    ist = client.get("/api/v1/investicii/istochniki", params=params).json()
    assert [s["name"] for s in ist["sources"]] == [f"Бюджет тест {sc.tag}",
                                                   f"МФИ тест {sc.tag}"]
    assert len(ist["cumulative"]) == 12
    riski = client.get("/api/v1/investicii/riski", params=params).json()
    assert [o["object_code"] for o in riski["lagging"]] == [f"OA-{sc.tag}"]
    assert [(o["object_code"], o["gap_pp"]) for o in riski["gaps"]] == [(f"OB-{sc.tag}", 33.0)]
    assert [(o["object_code"], o["advance"], o["advance_days"]) for o in riski["advances"]] == [
        (f"OA-{sc.tag}", 30.0, 91), (f"OB-{sc.tag}", 20.0, 113)]
    stages = riski["stages"][0]
    assert stages["object_id"] == sc.obj_a and stages["late"] == 2
    assert [(s["stage_no"], s["done"], s["late"]) for s in stages["stages"]] == [
        (1, True, False), (2, True, True), (3, False, True), (4, False, False)]
    assert stages["stages"][0]["plan_date"] == "2026-03-15"


def test_branch_without_objects(sc: InvScenario, app_factory: Callable[[], TestClient],
                                make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    for page in PAGES:
        body = client.get(f"/api/v1/investicii/{page}", params={"per": "m08", "br": 1}).json()
        assert body["kpis"]["has_objects"] is False and body["kpis"]["execution"] is None, page


def test_permission_and_branch_scope(sc: InvScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    for role in ("spec_kazna", "economist_filiala"):
        client = _as(app_factory, make_user(role, branch_ids=(sc.branch_id,)))
        for page in PAGES:
            assert client.get(f"/api/v1/investicii/{page}").status_code == 403, (role, page)
    scoped = _as(app_factory, make_user(section_branch_role("investicii"),
                                        branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = scoped.get(f"/api/v1/investicii/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = scoped.get("/api/v1/investicii/obekty", params={"per": "m08"}).json()
    assert {o["branch_id"] for o in own["objects"]} == {sc.branch_id}


def test_synthetic_program(published_synthetic: int, app_factory: Callable[[], TestClient],
                           make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/investicii/obekty", params={"per": "m08"}).json()
    synthetic = [o for o in body["objects"] if o["object_code"].startswith("OBJ-")]
    assert len(synthetic) == 14
    assert all(o["execution"] is not None and 0 < o["financial"] < 1 for o in synthetic)


def test_pub_views_rls_direct_sql(sc: InvScenario) -> None:
    for view in ("agg_investment_month", "agg_object_stages"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga qo'shing:
```python
    ("GET", "/api/v1/investicii/svod"),
    ("GET", "/api/v1/investicii/obekty"),
    ("GET", "/api/v1/investicii/istochniki"),
    ("GET", "/api/v1/investicii/riski"),
```
`PREFIX_PERMS` ga qo'shing:
```python
    "/api/v1/investicii": "section:investicii:view",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_investicii_api.py tests/test_route_guards.py -v`
Expected: FAIL — `404 Not Found`, `test_route_table_matches_expected_set` yiqiladi.

- [ ] **Step 3: Javob sxemalari**

`backend/app/sections/investicii_schemas.py`:
```python
"""«Инвестиции» API javoblari (`Inv` prefiksi). Pul — mln so'm, ulushlar 0..1, uzilish —
foiz punktlari; status: ok | lag | risk | None."""

from __future__ import annotations

from datetime import date

from app.sections.queries.investment import InvObject, InvTotals
from app.sections.schemas import ReportPeriodOut, _Out


class InvKpisOut(_Out):
    has_objects: bool
    objects: int
    total_cost: float
    program: float
    plan_to_date: float
    fact_ytd: float
    execution: float | None
    fact_period: float
    lagging: int
    threatened: int
    commissioning: int
    year: int


class InvObjectOut(_Out):
    object_id: int
    object_code: str
    name: str
    program_code: str | None
    work_type: str
    source_name: str
    commissioning_year: int | None
    total_cost: float | None
    branch_id: int
    branch_name: str
    plan_year: float
    plan_to_date: float
    fact_ytd: float
    fact_period: float
    execution: float | None
    status: str | None
    financial: float | None
    physical: float | None
    gap_pp: float | None
    advance: float
    advance_days: int | None


class InvCumOut(_Out):
    month_id: int
    plan: float
    fact: float | None


class InvSourceOut(_Out):
    name: str
    plan_year: float
    fact_ytd: float
    share: float | None


class InvStageOut(_Out):
    stage_no: int
    name: str
    plan_date: date
    fact_date: date | None
    done: bool
    late: bool


class InvObjectStagesOut(_Out):
    object_id: int
    name: str
    branch_id: int
    late: int
    stages: list[InvStageOut]


class InvSvodOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    cumulative: list[InvCumOut]
    sources: list[InvSourceOut]
    objects: list[InvObjectOut]


class InvObektyOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    objects: list[InvObjectOut]


class InvIstochnikiOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    sources: list[InvSourceOut]
    objects: list[InvObjectOut]
    cumulative: list[InvCumOut]


class InvRiskiOut(_Out):
    period: ReportPeriodOut
    kpis: InvKpisOut
    lagging: list[InvObjectOut]
    gaps: list[InvObjectOut]
    stages: list[InvObjectStagesOut]
    advances: list[InvObjectOut]


def inv_kpis_out(t: InvTotals) -> InvKpisOut:
    return InvKpisOut(
        has_objects=t.has_objects, objects=len(t.objects), total_cost=t.total_cost,
        program=t.program, plan_to_date=t.plan_to_date, fact_ytd=t.fact_ytd,
        execution=t.execution, fact_period=t.fact_period, lagging=t.lagging,
        threatened=t.threatened, commissioning=t.commissioning, year=t.year)


def object_out(o: InvObject) -> InvObjectOut:
    return InvObjectOut(
        object_id=o.object_id, object_code=o.object_code, name=o.name,
        program_code=o.program_code, work_type=o.work_type, source_name=o.source_name,
        commissioning_year=o.commissioning_year, total_cost=o.total_cost, branch_id=o.branch_id,
        branch_name=o.branch_name, plan_year=o.plan_year, plan_to_date=o.plan_to_date,
        fact_ytd=o.fact_ytd, fact_period=o.fact_period, execution=o.execution, status=o.status,
        financial=o.financial, physical=o.physical, gap_pp=o.gap_pp, advance=o.advance,
        advance_days=o.advance_days)
```

- [ ] **Step 4: Router**

`backend/app/sections/investicii.py`:
```python
"""«Инвестиции» (TZ 5): Сводка, Объекты, Источники и освоение, Сроки и риски.

Zanjir: router → queries.investment (pub view'lar) → Cache.respond. Obyektsiz filial — has_objects
false, UI: «У выбранного филиала нет объектов адресной программы».
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import get_db
from app.sections.deps import SQ, SectionQuery
from app.sections.investicii_schemas import (
    InvCumOut,
    InvIstochnikiOut,
    InvObektyOut,
    InvObjectStagesOut,
    InvRiskiOut,
    InvSourceOut,
    InvStageOut,
    InvSvodOut,
    inv_kpis_out,
    object_out,
)
from app.sections.period import ReportPeriod
from app.sections.queries import investment
from app.sections.schemas import period_out
from app.sections.scope import BranchSel

router = APIRouter(prefix="/investicii", tags=["investicii"],
                   dependencies=[Depends(require_perm(section_perm(Section.INVESTICII)))])
DB = Annotated[Session, Depends(get_db)]
SVOD_OBJECTS = 6  # prototip: «Объекты программы» — 6 ta + «Все объекты»
RISK_STAGES = 8  # prototip stageCard — 8 ta


def _load(db: Session, q: SectionQuery) -> tuple[ReportPeriod, BranchSel,
                                                 list[investment.InvObject],
                                                 investment.InvTotals]:
    period, sel = q.period(), q.sel()
    rows = investment.objects(db, sel, period)
    return period, sel, rows, investment.totals(rows, period)


def _cum(db: Session, sel: BranchSel, q: SectionQuery, year: int) -> list[InvCumOut]:
    return [InvCumOut(month_id=p.month_id, plan=p.plan, fact=p.fact)
            for p in investment.cumulative(db, sel, year, q.today)]


def _sources(rows: list[investment.InvObject]) -> list[InvSourceOut]:
    return [InvSourceOut(name=s.name, plan_year=s.plan_year, fact_ytd=s.fact_ytd, share=s.share)
            for s in investment.sources(rows)]


def build_svod(db: Session, q: SectionQuery) -> InvSvodOut:
    period, sel, rows, t = _load(db, q)
    return InvSvodOut(period=period_out(period), kpis=inv_kpis_out(t),
                      cumulative=_cum(db, sel, q, t.year), sources=_sources(rows),
                      objects=[object_out(o) for o in rows[:SVOD_OBJECTS]])


def build_obekty(db: Session, q: SectionQuery) -> InvObektyOut:
    period, _sel, rows, t = _load(db, q)
    return InvObektyOut(period=period_out(period), kpis=inv_kpis_out(t),
                        objects=[object_out(o) for o in rows])


def build_istochniki(db: Session, q: SectionQuery) -> InvIstochnikiOut:
    period, sel, rows, t = _load(db, q)
    by_fact = sorted(rows, key=lambda o: (-o.fact_ytd, o.name))
    return InvIstochnikiOut(period=period_out(period), kpis=inv_kpis_out(t),
                            sources=_sources(rows), objects=[object_out(o) for o in by_fact],
                            cumulative=_cum(db, sel, q, t.year))


def build_riski(db: Session, q: SectionQuery) -> InvRiskiOut:
    period, sel, rows, t = _load(db, q)
    lagging = sorted((o for o in rows if o.status in ("lag", "risk")),
                     key=lambda o: (o.execution or 0.0, o.name))
    gaps = sorted((o for o in rows if o.gap_pp is not None and o.gap_pp > investment.GAP_PP),
                  key=lambda o: (-(o.gap_pp or 0.0), o.name))
    advances = sorted((o for o in rows if o.advance > 0 and o.advance_days is not None
                       and o.advance_days > investment.ADVANCE_DAYS),
                      key=lambda o: (-o.advance, o.name))
    by_obj = {o.object_id: o for o in rows}
    stage_rows = [
        InvObjectStagesOut(
            object_id=oid, name=by_obj[oid].name, branch_id=by_obj[oid].branch_id,
            late=sum(1 for s in items if s.late),
            stages=[InvStageOut(stage_no=s.stage_no, name=s.name, plan_date=s.plan_date,
                                fact_date=s.fact_date, done=s.done, late=s.late)
                    for s in items])
        for oid, items in investment.stages(db, sel).items() if oid in by_obj]
    stage_rows.sort(key=lambda s: (-s.late, -by_obj[s.object_id].plan_year, s.name))
    return InvRiskiOut(period=period_out(period), kpis=inv_kpis_out(t),
                       lagging=[object_out(o) for o in lagging],
                       gaps=[object_out(o) for o in gaps], stages=stage_rows[:RISK_STAGES],
                       advances=[object_out(o) for o in advances])


@router.get("/svod", response_model=InvSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/obekty", response_model=InvObektyOut)
def obekty(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.obekty", q.cache_filters, lambda: build_obekty(db, q))


@router.get("/istochniki", response_model=InvIstochnikiOut)
def istochniki(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.istochniki", q.cache_filters,
                         lambda: build_istochniki(db, q))


@router.get("/riski", response_model=InvRiskiOut)
def riski(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("investicii.riski", q.cache_filters, lambda: build_riski(db, q))
```

`backend/app/main.py` — import va `include_router` (`zakupki_router` dan keyin):
```python
from app.sections.investicii import router as investicii_router
```
```python
    app.include_router(investicii_router, prefix=API_PREFIX)
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_investicii_api.py tests/test_route_guards.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(investicii): Сводка, Объекты, Источники и освоение, Сроки и риски API

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 12: «Кадры» API — Сводка, Численность, Оплата труда, Движение кадров; shaxsiy ma'lumot testi

**Files:**
- Create: `backend/app/sections/kadry_schemas.py`, `backend/app/sections/kadry.py`
- Modify: `backend/app/main.py` (router), `backend/tests/test_route_guards.py`
- Test: `backend/tests/test_kadry_api.py`, `backend/tests/test_kadry_synthetic.py`

**Interfaces:**
- Consumes: `SQ`/`SectionQuery`, `Cache`, `get_db`, `require_perm`, `Section.KADRY`, `_Out`, `ReportPeriodOut`, `period_out`, `queries.hr.*`, `current_setting` (`kazna.calendar_kinds`), `tests.s4_helpers.hr_scenario`, `tests.s2_helpers.put_setting`, `get_engine`, `published_synthetic`, `login`, `make_user`.
- Produces:
  - `app.sections.kadry_schemas`: `HrKpisOut(has_data, snap_month, plan, fact, vacancies, vacancy_share, fill, payroll, outflow, payroll_share, avg_salary, hired, fired, turnover, overtime, overtime_per_employee)`, `HrMonthOut(month_id, payroll, fact, avg_salary, hired, fired, overtime)`, `HrCategoryOut(name, value)`, `HrBranchOut(branch_id, name, plan, fact, vacancies, fill, payroll, avg_salary, hired, fired, turnover, overtime, overtime_per_employee)`, `KadrySvodOut(period, kpis, months, categories, branches)`, `KadryChislennostOut(period, kpis, branches, categories)`, `KadryFotOut(period, kpis, months, branches)`, `KadryDvizhenieOut(period, kpis, months, branches)`; `hr_kpis_out`, `hr_branch_out`.
  - `app.sections.kadry`: `router` (`/kadry`), `salary_codes(db) -> list[str]`, `build_svod`, `build_chislennost`, `build_fot`, `build_dvizhenie`. `FORBIDDEN_KEY` — test regex (ФИО/ПИНФЛ/pasport/telefon kalitlari).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_kadry_api.py`:
```python
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.dwh.reference import current_setting
from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.helpers import SeedUser, login
from tests.s2_helpers import put_setting
from tests.s4_helpers import HrScenario, hr_scenario

PAGES = ("svod", "chislennost", "fot", "dvizhenie")
FORBIDDEN_KEY = re.compile(
    r"^(.*_)?(fio|full_?name|first_?name|last_?name|middle_?name|surname|patronymic|pinfl|"
    r"passport|birth(day|_?date)?|phone|email|address|tabel|employee_?id)(_.*)?$", re.I)


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[HrScenario]:
    source = new_source()
    scenario = hr_scenario(source, publish=True)
    with get_engine("app").connect() as conn:
        kinds = dict(current_setting(conn, "kazna.calendar_kinds"))
    put_setting("kazna.calendar_kinds", {**kinds, "salary": [scenario.salary_code]})
    yield scenario
    put_setting("kazna.calendar_kinds", kinds)
    purge_source(source)


@pytest.fixture
def app_factory() -> Iterator[Callable[[], TestClient]]:
    clients: list[TestClient] = []

    def make() -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _as(app_factory: Callable[[], TestClient], user: SeedUser) -> TestClient:
    return login(app_factory(), user)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_svod_numbers_and_etag(sc: HrScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/kadry/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["plan"], k["fact"], k["vacancies"], k["vacancy_share"], k["fill"]) == (
        100.0, 90.0, 10.0, 0.1, 0.9)
    assert (k["payroll"], k["payroll_share"], k["avg_salary"], k["turnover"]) == (
        180.0, 0.3, 2.0, 0.033333)
    assert (k["overtime_per_employee"], k["snap_month"]) == (4.666667, 202608)
    assert [c["name"] for c in body["categories"]] == ["Оперативный персонал", "Руководители"]
    assert body["months"][6] == {"month_id": 202607, "payroll": 170.0, "fact": 91.0,
                                 "avg_salary": 1.868132, "hired": 1, "fired": 2,
                                 "overtime": 315.0}
    again = client.get("/api/v1/kadry/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_other_pages(sc: HrScenario, app_factory: Callable[[], TestClient],
                     make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "q3", "br": sc.branch_id}
    fot = client.get("/api/v1/kadry/fot", params=params).json()
    assert (fot["kpis"]["payroll"], fot["kpis"]["avg_salary"]) == (500.0, 1.984127)
    assert fot["branches"][0]["payroll"] == 500.0
    dv = client.get("/api/v1/kadry/dvizhenie", params=params).json()
    assert (dv["kpis"]["hired"], dv["kpis"]["fired"], dv["kpis"]["turnover"]) == (6, 7, 0.077778)
    assert dv["branches"][0]["overtime_per_employee"] == 10.5
    ch = client.get("/api/v1/kadry/chislennost", params=params).json()
    assert ch["branches"][0]["vacancies"] == 10.0


def test_permission_and_branch_scope(sc: HrScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    kazna = _as(app_factory, make_user("spec_kazna"))
    for page in PAGES:
        assert kazna.get(f"/api/v1/kadry/{page}").status_code == 403, page
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = econ.get(f"/api/v1/kadry/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = econ.get("/api/v1/kadry/chislennost", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in own["branches"]} == {sc.branch_id}
    assert own["kpis"]["fact"] == 90.0


def test_no_personal_fields_anywhere(sc: HrScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser],
                                     published_synthetic: int) -> None:
    """TZ 9: «Кадры» — faqat agregatlar, ФИО hech qayerda saqlanmaydi va ko'rsatilmaydi."""
    with get_engine("migrator").connect() as conn:
        columns = conn.execute(text(
            "SELECT table_schema || '.' || table_name AS t, column_name FROM "
            "information_schema.columns WHERE (table_schema, table_name) IN "
            "(('dwh', 'fact_hr'), ('dwh', 'dim_position'), ('mart', 'agg_hr_month'), "
            "('pub', 'agg_hr_month'))")).all()
    assert {r.t for r in columns} == {"dwh.fact_hr", "dwh.dim_position", "mart.agg_hr_month",
                                      "pub.agg_hr_month"}
    assert [r for r in columns if FORBIDDEN_KEY.match(r.column_name)] == []
    client = _as(app_factory, make_user("rukovodstvo"))
    for page in PAGES:
        for params in ({"per": "ytd"}, {"per": "m08", "br": sc.branch_id}):
            body = client.get(f"/api/v1/kadry/{page}", params=params).json()
            bad = {k for k in _keys(body) if FORBIDDEN_KEY.match(k)}
            assert bad == set(), (page, bad)


def test_pub_view_rls_direct_sql(sc: HrScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        seen = set(s.execute(text("SELECT DISTINCT branch_id FROM pub.agg_hr_month")).scalars())
    assert seen <= {sc.branch_id}
    with new_session() as s:
        assert s.execute(text("SELECT count(*) FROM pub.agg_hr_month")).scalar_one() == 0
```
Sintetik ma'lumot testi alohida faylda — `sc` modul fixture'i `kazna.calendar_kinds.salary` ni ssenariy statyasiga almashtiradi, sintetik ФОТ esa standart `PKM54-O05` bilan tekshiriladi: `backend/tests/test_kadry_synthetic.py` (modul fixture'i `sc` yo'q, standart sozlama amal qiladi):
```python
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.sections.deps import get_today
from tests.etl_helpers import TEST_AS_OF
from tests.helpers import SeedUser, login


@pytest.fixture
def client_for() -> Iterator[Callable[[SeedUser], TestClient]]:
    clients: list[TestClient] = []

    def make(user: SeedUser) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return login(client, user)

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_synthetic_staff(published_synthetic: int, client_for: Callable[[SeedUser], TestClient],
                         make_user: Callable[..., SeedUser]) -> None:
    client = client_for(make_user("rukovodstvo"))
    body = client.get("/api/v1/kadry/chislennost", params={"per": "m08"}).json()
    synthetic = [b for b in body["branches"] if b["branch_id"] <= 16]
    assert len(synthetic) == 16 and all(b["fact"] <= b["plan"] + 4 for b in synthetic)
    fot = client.get("/api/v1/kadry/fot", params={"per": "m08"}).json()
    assert fot["kpis"]["payroll"] > 0  # PKM54-O05 (sintetik) — standart ФОТ statyasi
```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga qo'shing:
```python
    ("GET", "/api/v1/kadry/svod"),
    ("GET", "/api/v1/kadry/chislennost"),
    ("GET", "/api/v1/kadry/fot"),
    ("GET", "/api/v1/kadry/dvizhenie"),
```
`PREFIX_PERMS` ga qo'shing:
```python
    "/api/v1/kadry": "section:kadry:view",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_kadry_api.py tests/test_kadry_synthetic.py tests/test_route_guards.py -v`
Expected: FAIL — `404 Not Found`, `test_route_table_matches_expected_set` yiqiladi.

- [ ] **Step 3: Javob sxemalari**

`backend/app/sections/kadry_schemas.py`:
```python
"""«Кадры» API javoblari (`Hr`/`Kadry` prefiksi). Faqat agregatlar: odamlar soni, mln so'm,
soatlar, ulushlar 0..1 — ФИО yoki shaxsga oid kalit yo'q
(TZ 9, test_no_personal_fields_anywhere)."""

from __future__ import annotations

from app.sections.queries.hr import HrBranch, HrFigures
from app.sections.schemas import ReportPeriodOut, _Out


class HrKpisOut(_Out):
    has_data: bool
    snap_month: int | None
    plan: float
    fact: float
    vacancies: float | None
    vacancy_share: float | None
    fill: float | None
    payroll: float
    outflow: float
    payroll_share: float | None
    avg_salary: float | None
    hired: int
    fired: int
    turnover: float | None
    overtime: float
    overtime_per_employee: float | None


class HrMonthOut(_Out):
    month_id: int
    payroll: float
    fact: float
    avg_salary: float | None
    hired: int
    fired: int
    overtime: float


class HrCategoryOut(_Out):
    name: str
    value: float


class HrBranchOut(_Out):
    branch_id: int
    name: str
    plan: float
    fact: float
    vacancies: float | None
    fill: float | None
    payroll: float
    avg_salary: float | None
    hired: int
    fired: int
    turnover: float | None
    overtime: float
    overtime_per_employee: float | None


class KadrySvodOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    months: list[HrMonthOut]
    categories: list[HrCategoryOut]
    branches: list[HrBranchOut]


class KadryChislennostOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    branches: list[HrBranchOut]
    categories: list[HrCategoryOut]


class KadryFotOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    months: list[HrMonthOut]
    branches: list[HrBranchOut]


class KadryDvizhenieOut(_Out):
    period: ReportPeriodOut
    kpis: HrKpisOut
    months: list[HrMonthOut]
    branches: list[HrBranchOut]


def hr_kpis_out(t: HrFigures) -> HrKpisOut:
    return HrKpisOut(
        has_data=t.has_data, snap_month=t.snap_month, plan=t.plan, fact=t.fact,
        vacancies=t.vacancies, vacancy_share=t.vacancy_share, fill=t.fill, payroll=t.payroll,
        outflow=t.outflow, payroll_share=t.payroll_share, avg_salary=t.avg_salary,
        hired=t.hired, fired=t.fired, turnover=t.turnover, overtime=t.overtime,
        overtime_per_employee=t.overtime_per_employee)


def hr_branch_out(b: HrBranch) -> HrBranchOut:
    return HrBranchOut(
        branch_id=b.branch_id, name=b.name, plan=b.plan, fact=b.fact, vacancies=b.vacancies,
        fill=b.fill, payroll=b.payroll, avg_salary=b.avg_salary, hired=b.hired, fired=b.fired,
        turnover=b.turnover, overtime=b.overtime, overtime_per_employee=b.overtime_per_employee)
```

- [ ] **Step 4: Router**

`backend/app/sections/kadry.py`:
```python
"""«Кадры» (TZ 5): Сводка, Численность, Оплата труда, Движение кадров.

ФОТ statyalari — S1 `kazna.calendar_kinds.salary` (bir joyda sozlanadi). Sozlama o'zgarsa kesh
keyingi ma'lumot versiyasida yangilanadi (S1 kalendari bilan bir xil xulq).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import get_db
from app.dwh.reference import current_setting
from app.sections.deps import SQ, SectionQuery
from app.sections.kadry_schemas import (
    HrCategoryOut,
    HrMonthOut,
    KadryChislennostOut,
    KadryDvizhenieOut,
    KadryFotOut,
    KadrySvodOut,
    hr_branch_out,
    hr_kpis_out,
)
from app.sections.queries import hr
from app.sections.schemas import period_out

router = APIRouter(prefix="/kadry", tags=["kadry"],
                   dependencies=[Depends(require_perm(section_perm(Section.KADRY)))])
DB = Annotated[Session, Depends(get_db)]


def salary_codes(db: Session) -> list[str]:
    kinds = current_setting(db.connection(), "kazna.calendar_kinds")
    return [str(code) for code in kinds.get("salary", [])]


def _months(db: Session, q: SectionQuery, codes: list[str]) -> list[HrMonthOut]:
    return [HrMonthOut(month_id=m.month_id, payroll=m.payroll, fact=m.fact,
                       avg_salary=m.avg_salary, hired=m.hired, fired=m.fired,
                       overtime=m.overtime) for m in hr.monthly(db, q.sel(), q.today, codes)]


def _categories(db: Session, q: SectionQuery) -> list[HrCategoryOut]:
    return [HrCategoryOut(name=c.name, value=c.value)
            for c in hr.categories(db, q.sel(), q.period())]


def build_svod(db: Session, q: SectionQuery) -> KadrySvodOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    return KadrySvodOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        months=_months(db, q, codes), categories=_categories(db, q),
        branches=[hr_branch_out(b) for b in hr.by_branch(db, sel, period, codes)])


def build_chislennost(db: Session, q: SectionQuery) -> KadryChislennostOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    return KadryChislennostOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        branches=[hr_branch_out(b) for b in hr.by_branch(db, sel, period, codes)],
        categories=_categories(db, q))


def build_fot(db: Session, q: SectionQuery) -> KadryFotOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    rows = sorted(hr.by_branch(db, sel, period, codes), key=lambda b: (-b.payroll, b.name))
    return KadryFotOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        months=_months(db, q, codes), branches=[hr_branch_out(b) for b in rows])


def build_dvizhenie(db: Session, q: SectionQuery) -> KadryDvizhenieOut:
    period, sel, codes = q.period(), q.sel(), salary_codes(db)
    rows = sorted(hr.by_branch(db, sel, period, codes),
                  key=lambda b: (-(b.turnover or 0.0), b.name))
    return KadryDvizhenieOut(
        period=period_out(period), kpis=hr_kpis_out(hr.totals(db, sel, period, codes)),
        months=_months(db, q, codes), branches=[hr_branch_out(b) for b in rows])


@router.get("/svod", response_model=KadrySvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/chislennost", response_model=KadryChislennostOut)
def chislennost(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.chislennost", q.cache_filters,
                         lambda: build_chislennost(db, q))


@router.get("/fot", response_model=KadryFotOut)
def fot(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.fot", q.cache_filters, lambda: build_fot(db, q))


@router.get("/dvizhenie", response_model=KadryDvizhenieOut)
def dvizhenie(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kadry.dvizhenie", q.cache_filters, lambda: build_dvizhenie(db, q))
```

`backend/app/main.py` — import va `include_router` (`investicii_router` dan keyin):
```python
from app.sections.kadry import router as kadry_router
```
```python
    app.include_router(kadry_router, prefix=API_PREFIX)
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_kadry_api.py tests/test_kadry_synthetic.py tests/test_route_guards.py -v`
Expected: barcha testlar passed (shaxsiy ma'lumot testi — ustunlar va javob kalitlari toza).

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(kadry): Сводка, Численность, Оплата труда, Движение кадров API; shaxsiy ma'lumot testi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 13: «Требует внимания» — xarid, АИП va kadrlar qoidalari (9 ta)

**Files:**
- Create: `backend/app/alerts/procurement.py`, `backend/app/alerts/investment.py`, `backend/app/alerts/hr.py`
- Modify: `backend/app/alerts/__init__.py`
- Test: `backend/tests/test_alerts_s4.py`

**Interfaces:**
- Consumes: `evaluator`, `breached`, `hit`, `RuleConfig` (`.value`), `AlertHit`, `evaluate`, `load_rules`, `REGISTRY`, `queries.procurement.totals`, `queries.investment.objects/totals`, `queries.hr.totals`, `fmt_money`, `fmt_pct`, `fmt_num`, `plural`, `ALERT_RULES` seed'lari (spec 7 jadvali), `tests.s4_helpers.*`, `tests.s2_helpers.put_rule`.
- Produces: `app.alerts.procurement.{procurement_overdue_lots, direct_contracts_share, procurement_plan}`, `app.alerts.investment.{investment_schedule, fin_phys_gap, advances_90d}`, `app.alerts.hr.{vacancies_share, turnover, overtime}` (reyestrga yozilgan). Ma'lumot yo'q yoki maxraj 0 — `None`. `fin_phys_gap`/`advances_90d` — obyekt bo'yicha (qiymat = obyektlar soni).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_alerts_s4.py`:
```python
from collections.abc import Iterator

import pytest
import redis
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate, load_rules
from app.alerts.types import REGISTRY
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.sections.deps import SectionQuery
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s2_helpers import put_rule
from tests.s4_helpers import (
    HrScenario,
    InvScenario,
    ProcScenario,
    hr_scenario,
    investment_scenario,
    procurement_scenario,
)

ZAK = frozenset({"section:zakupki:view"})
INV = frozenset({"section:investicii:view"})
HR = frozenset({"section:kadry:view"})
S4_RULES = {"procurement_overdue_lots", "direct_contracts_share", "procurement_plan",
            "investment_schedule", "fin_phys_gap", "advances_90d", "vacancies_share",
            "turnover", "overtime"}


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def proc() -> Iterator[ProcScenario]:
    source = new_source()
    yield procurement_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture(scope="module")
def inv() -> Iterator[InvScenario]:
    source = new_source()
    yield investment_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture(scope="module")
def staff() -> Iterator[HrScenario]:
    source = new_source()
    yield hr_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str) -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def test_registry_has_s4_rules() -> None:
    assert S4_RULES <= set(REGISTRY)


def test_procurement_rules(proc: ProcScenario, db: Session) -> None:
    hits = {h.code: h for h in evaluate(db, _q(proc.branch_id, "m08"), ZAK)[0]}
    assert set(hits) == {"direct_contracts_share", "procurement_plan"}
    assert hits["direct_contracts_share"].message == (
        "35,7% суммы договоров заключено без конкурса: 50,0 млн")
    assert hits["procurement_plan"].message == (
        "Исполнено 19,7%: 197,0 млн из 1,0 млрд с начала года")
    assert hits["procurement_plan"].page == "svod"
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("procurement_overdue_lots",
                 threshold={**rules["procurement_overdue_lots"].threshold, "value": 0})
        found = evaluate(db, _q(proc.branch_id, "m08"), ZAK)[0]
        assert found[0].code == "procurement_overdue_lots" and found[0].level == "critical"
        assert found[0].message == (
            "1 лот закупки просрочен: начальная цена 80,0 млн, дольше норматива на 10+ дней")
        assert (found[0].page, found[0].value) == ("loty", 1.0)
    finally:
        put_rule("procurement_overdue_lots",
                 threshold=rules["procurement_overdue_lots"].threshold)


def test_investment_rules(inv: InvScenario, db: Session) -> None:
    hits = {h.code: h for h in evaluate(db, _q(inv.branch_id, "m08"), INV)[0]}
    assert set(hits) == {"investment_schedule", "fin_phys_gap", "advances_90d"}
    assert hits["investment_schedule"].message == (
        "Исполнение графика 81,8%: освоено 180,0 млн из 220,0 млн")
    assert hits["fin_phys_gap"].message == (
        f"1 объект: финансирование опережает физическое выполнение, наибольший разрыв — "
        f"Объект Б {inv.tag} 33 п.п.")
    assert hits["advances_90d"].message == "2 незакрытых аванса старше 90 дней на сумму 50,0 млн"
    assert (hits["advances_90d"].value, hits["fin_phys_gap"].page) == (2.0, "riski")


def test_hr_rules(staff: HrScenario, db: Session) -> None:
    assert evaluate(db, _q(staff.branch_id, "m08"), HR)[0] == []  # 10% — «> 10%» emas
    rules = {r.code: r for r in load_rules(db)}
    changes = {"vacancies_share": 0.05, "turnover": 0.01, "overtime": 4}
    try:
        for code, value in changes.items():
            put_rule(code, threshold={**rules[code].threshold, "value": value})
        hits = {h.code: h for h in evaluate(db, _q(staff.branch_id, "m08"), HR)[0]}
        assert hits["vacancies_share"].message == "10,0% штата не занято: 10 вакансий из 100"
        assert hits["turnover"].message == "Текучесть 3,3%: уволено 3 из 90 работников за период"
        assert hits["overtime"].message == (
            "4,7 ч сверхурочных на работника: всего 420 ч за период")
        assert hits["overtime"].page == "dvizhenie" and hits["vacancies_share"].page == (
            "chislennost")
    finally:
        for code in changes:
            put_rule(code, threshold=rules[code].threshold)


def test_rules_skip_without_data(proc: ProcScenario, inv: InvScenario, staff: HrScenario,
                                 db: Session) -> None:
    every = ZAK | INV | HR
    assert evaluate(db, _q(999_999, "m08"), every)[0] == []
    assert evaluate(db, _q(staff.branch_id, "m06"), HR)[0] == []
    assert evaluate(db, _q(inv.branch_id, "m08"), ZAK | HR)[0] == []  # obyekt filiali
    assert evaluate(db, _q(proc.branch_id, "m08"), HR)[0] == []
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_alerts_s4.py -v`
Expected: FAIL — `test_registry_has_s4_rules` (`procurement_overdue_lots` reyestrda yo'q).

- [ ] **Step 3: Implementatsiya**

`backend/app/alerts/procurement.py`:
```python
"""TZ 4 «Требует внимания» — xarid qoidalari (chegaralar — core.alert_rules, S4 spec 7).

Lotlar/shartnomalar/reja bo'lmasa qoida o'tkazib yuboriladi (yolg'on signal yo'q).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import procurement


@evaluator("procurement_overdue_lots")
def procurement_overdue_lots(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = procurement.totals(db, q.sel(), q.period())
    if t.in_work == 0 or not breached(float(t.overdue), rule):
        return None
    word = plural(t.overdue, "лот закупки просрочен", "лота закупки просрочены",
                  "лотов закупки просрочены")
    return hit(rule, f"{t.overdue} {word}: начальная цена {fmt_money(t.overdue_start)}, "
                     "дольше норматива на 10+ дней", float(t.overdue))


@evaluator("direct_contracts_share")
def direct_contracts_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = procurement.totals(db, q.sel(), q.period())
    share = t.direct_share
    if share is None or not breached(share, rule):
        return None
    return hit(rule, f"{fmt_pct(share)} суммы договоров заключено без конкурса: "
                     f"{fmt_money(t.direct)}", share)


@evaluator("procurement_plan")
def procurement_plan(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = procurement.totals(db, q.sel(), q.period())
    execution = t.plan_execution
    if execution is None or not breached(execution, rule):
        return None
    return hit(rule, f"Исполнено {fmt_pct(execution)}: {fmt_money(t.ytd)} из "
                     f"{fmt_money(t.plan)} с начала года", execution)
```

`backend/app/alerts/investment.py`:
```python
"""TZ 4 «Требует внимания» — АИП qoidalari (S4 spec 7).

investment_schedule — tanlov jamida; fin_phys_gap va advances_90d — obyekt bo'yicha (chegara
p.p. / kun), qiymat — chegaradan o'tgan obyektlar soni. Obyekt yo'q — None.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_num, fmt_pct, plural
from app.sections.queries import investment


@evaluator("investment_schedule")
def investment_schedule(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    period = q.period()
    t = investment.totals(investment.objects(db, q.sel(), period), period)
    execution = t.execution
    if execution is None or not breached(execution, rule):
        return None
    return hit(rule, f"Исполнение графика {fmt_pct(execution)}: освоено {fmt_money(t.fact_ytd)} "
                     f"из {fmt_money(t.plan_to_date)}", execution)


@evaluator("fin_phys_gap")
def fin_phys_gap(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    rows = [o for o in investment.objects(db, q.sel(), q.period())
            if o.gap_pp is not None and breached(o.gap_pp, rule)]
    if not rows:
        return None
    top = max(rows, key=lambda o: o.gap_pp or 0.0)
    n = len(rows)
    word = plural(n, "объект", "объекта", "объектов")
    return hit(rule, f"{n} {word}: финансирование опережает физическое выполнение, наибольший "
                     f"разрыв — {top.name} {fmt_num(top.gap_pp or 0.0, 0)} п.п.", float(n))


@evaluator("advances_90d")
def advances_90d(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    rows = [o for o in investment.objects(db, q.sel(), q.period())
            if o.advance > 0 and o.advance_days is not None
            and breached(float(o.advance_days), rule)]
    if not rows:
        return None
    n = len(rows)
    word = plural(n, "незакрытый аванс", "незакрытых аванса", "незакрытых авансов")
    total = sum(o.advance for o in rows)
    return hit(rule, f"{n} {word} старше {fmt_num(rule.value, 0)} дней на сумму "
                     f"{fmt_money(total)}", float(n))
```

`backend/app/alerts/hr.py`:
```python
"""TZ 4 «Требует внимания» — kadrlar qoidalari (S4 spec 7). Faqat agregatlar.

Штат yoki численность ma'lumoti yo'q — None. ФОТ kerak emas (statya ro'yxati bo'sh beriladi).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_num, fmt_pct, plural
from app.sections.queries import hr


def _totals(db: Session, q: SectionQuery) -> hr.HrFigures:
    return hr.totals(db, q.sel(), q.period(), [])


@evaluator("vacancies_share")
def vacancies_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = _totals(db, q)
    share, vacancies = t.vacancy_share, t.vacancies
    if share is None or vacancies is None or not breached(share, rule):
        return None
    n = round(vacancies)
    word = plural(n, "вакансия", "вакансии", "вакансий")
    return hit(rule, f"{fmt_pct(share)} штата не занято: {fmt_num(vacancies, 0)} {word} из "
                     f"{fmt_num(t.plan, 0)}", share)


@evaluator("turnover")
def turnover(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = _totals(db, q)
    value = t.turnover
    if value is None or not breached(value, rule):
        return None
    return hit(rule, f"Текучесть {fmt_pct(value)}: уволено {t.fired} из {fmt_num(t.fact, 0)} "
                     "работников за период", value)


@evaluator("overtime")
def overtime(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    t = _totals(db, q)
    value = t.overtime_per_employee
    if value is None or not breached(value, rule):
        return None
    return hit(rule, f"{fmt_num(value)} ч сверхурочных на работника: всего "
                     f"{fmt_num(t.overtime, 0)} ч за период", value)
```

`backend/app/alerts/__init__.py` — import qatorini almashtiring:
```python
from app.alerts import (  # noqa: F401
    hr,
    investment,
    loans,
    procurement,
    production,
    stock,
    treasury,
)
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_alerts_s4.py tests/test_alerts.py tests/test_alerts_s3.py tests/test_alerts_loans.py -v`
Expected: barcha testlar passed (S1 `test_vnimanie_endpoints` S1 ssenariysi filialida — S4 fakti yo'q, yangi qoidalar yonmaydi).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(alerts): xarid, АИП va kadrlar qoidalari — kechikkan lotlar, reja, uzilish, avanslar, вакансии, qo'nimsizlik, soatlar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 14: Xarid manbalari — portal adapteri interfeysi va `ProcurementConnector`, `XaridPortal` stub'i, 1C `/purchasePlan` konnektori, reyestr va worker

**Files:**
- Create: `backend/app/etl/zakupki/portal.py`, `backend/app/etl/zakupki/connector.py`, `backend/app/etl/zakupki/onec_plan.py`, `backend/tests/fixtures/onec/purchase_plan_2026.json`
- Modify: `backend/app/etl/connectors.py` (`KNOWN_SOURCES`, `make_connector`), `backend/app/worker.py` (`build_scheduler`)
- Test: `backend/tests/test_procurement_sources.py`

**Interfaces:**
- Consumes: `ReportingSink`, `ExtractStats`, `HealthResult`, `Watermark`, `StagingSink`, `Window`, `ConfigError`, `ConnectorUnavailableError`, `date_id`, `today_tashkent`, `normalize_name`, `codes.*`, `OneCClient`, `verify_setting`, `OrgMap`, `stable_code`, `to_mln`, `unmapped_branch`, `onec.models.parse`, `current_setting` (`onec.orgs`, `etl.onec_zakupki_cron`), `Runner`, `Mode`, `run_etl_job`, `tests.etl_helpers.*`.
- Produces:
  - `app.etl.zakupki.portal`: `PortalLot(lot_no, customer_inn, method, status, announce_date, contract_date, start_price_uzs, contract_price_uzs, supplier_inn, supplier_name, subject)`, `ProcurementPortal` (Protocol: `name`, `healthcheck()`, `lots(window) -> Iterator[PortalLot]`), `PORTAL_MESSAGE`, `PortalNotConfigured(ConfigError)`, `XaridPortal()` (yaratishda `PortalNotConfigured`), `method_code(name) -> str | None`, `status_code(name) -> str | None`.
  - `app.etl.zakupki.connector`: `SOURCE = "xarid"`, `DOC_TYPE = "portal_lot"`, `ERROR_TARGET = "procurement_portal"`, `ProcurementConnector(portal, branches: Mapping[str, str], *, source=SOURCE, now=...)` — `SourceConnector`; `extract` `ReportingSink` talab qiladi, `ExtractStats(rows, {})` (upsert). Xato kodlari: `unknown_customer`, `unknown_status`, `bad_row`; ogohlantirish `unknown_method` (usul → `other`). 14 xonali INN → `CP-FL` «Физическое лицо», nom saqlanmaydi.
  - `app.etl.zakupki.onec_plan`: `SOURCE = "onec_zakupki"`, `PATH = "/purchasePlan"`, `PurchasePlanRow`, `PurchasePlanResponse`, `OneCPurchasePlanConnector(client, orgs, *, source=SOURCE, now=...)` — oyna yillari bo'yicha `{"Year": Y}`, tashkilot nomi bo'yicha `OrgMap` (normallashtirilgan), moslashtirilmagan → `unmapped_branch(org_name)` (S1 xulqi — publish to'xtaydi), (filial, nomenklatura) bo'yicha yig'indi, 0 va manfiy o'tkaziladi; `ExtractStats(n, {"fact_procurement": n})`.
  - `KNOWN_SOURCES` += `"xarid"`, `"onec_zakupki"`; `make_connector("xarid")` → `PortalNotConfigured`; `make_connector("onec_zakupki")` (`ONEC_BASE_URL` yoki `onec.orgs` bo'sh → `ConfigError`).
  - Worker: `ONEC_BASE_URL` berilgan bo'lsa job `etl_onec_zakupki` (`etl.onec_zakupki_cron`, `Mode.FULL`).

- [ ] **Step 1: Yozib olingan javob**

`backend/tests/fixtures/onec/purchase_plan_2026.json` (eski dashboard `budget-api.js` `fetchPurchasePlan` va `1c_api.md` §4 shakli):
```json
{"items": [
  {"org_name": "Чорвоқ ГЭС", "nomenclature_name": "Подшипник SKF 23140", "quantity_incoming": 4, "sum_incoming": 192000000},
  {"org_name": "Чорвоқ  ГЭС", "nomenclature_name": "Подшипник SKF 23140", "quantity_incoming": 1, "sum_incoming": "48000000.5"},
  {"org_name": "Чорвоқ ГЭС", "nomenclature_name": "Кабель АВБбШв 4×120", "quantity_incoming": 500, "sum_incoming": 210000000},
  {"org_name": "Неизвестная организация", "nomenclature_name": "Бумага", "quantity_incoming": 10, "sum_incoming": 1000000},
  {"org_name": "Чорвоқ ГЭС", "nomenclature_name": "Сторно", "quantity_incoming": 0, "sum_incoming": 0}
]}
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_procurement_sources.py`:
```python
import json
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app import worker
from app.core.config import ConfigError, get_settings
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.onec.client import OneCClient
from app.etl.onec.connector import OrgMap, stable_code
from app.etl.runner import Runner
from app.etl.types import HealthResult, Mode, Window
from app.etl.zakupki import codes
from app.etl.zakupki.connector import ProcurementConnector
from app.etl.zakupki.onec_plan import OneCPurchasePlanConnector
from app.etl.zakupki.portal import PortalLot, PortalNotConfigured, XaridPortal, method_code
from tests.etl_helpers import (
    TEST_AS_OF,
    RecordingNotifier,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s2_helpers import put_setting

FIXTURE = Path(__file__).parent / "fixtures" / "onec" / "purchase_plan_2026.json"
BASE = "https://1c.test/con2026/hs/aiassistant"
SEPT = Window(date(2026, 9, 1), TEST_AS_OF)
ORG = OrgMap(branch_code="UGE-02", org_uid="uid-02", org_name="Чорвоқ ГЭС")


class ReportSink:
    def __init__(self) -> None:
        self.load_id = 0
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, str, str, str]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append((target, code, message, severity))


class ListPortal:
    name = "list"

    def __init__(self, *lots: PortalLot) -> None:
        self._lots = lots

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "list")

    def lots(self, window: Window) -> Iterator[PortalLot]:
        yield from self._lots


def _lot(no: str, **kw: Any) -> PortalLot:
    base: dict[str, Any] = {
        "lot_no": no, "customer_inn": "201100002", "method": "Электронный магазин",
        "status": "Объявлен", "announce_date": date(2026, 9, 1), "contract_date": None,
        "start_price_uzs": Decimal("120000000"), "contract_price_uzs": None,
        "supplier_inn": None, "supplier_name": None, "subject": "Запасные части"}
    return PortalLot(**{**base, **kw})


def _extract(*lots: PortalLot) -> ReportSink:
    sink = ReportSink()
    ProcurementConnector(ListPortal(*lots), {"201100002": "UGE-02"}).extract(SEPT, sink)
    return sink


def test_portal_lots_are_mapped_to_canonical_rows() -> None:
    sink = _extract(
        _lot("X-1", status="Заключен договор", contract_date=date(2026, 9, 10),
             contract_price_uzs=Decimal("100000000"), supplier_inn="305555555",
             supplier_name="ООО «Альфа»"),
        _lot("X-2", method="Прямой договор", status="Договор заключён",
             announce_date=date(2026, 9, 5), contract_date=date(2026, 9, 6),
             contract_price_uzs=Decimal("50000000"), supplier_inn="12345678901234",
             supplier_name="Иванов Иван Иванович"),
        _lot("X-3", method="Аукцион", announce_date=date(2026, 9, 15)),
        _lot("X-4", customer_inn="999999999"),
        _lot("X-5", status="Приостановлен"),
        _lot("X-6", status="Договор заключён"),
        _lot("X-7", announce_date=date(2026, 7, 1)),
    )
    facts = {r["src_id"]: r for t, r in sink.rows if t == "fact_procurement"}
    assert set(facts) == {"X-1", "X-2", "X-3"}
    x1, x2, x3 = facts["X-1"], facts["X-2"], facts["X-3"]
    assert (x1["status"], x1["method"], x1["date_id"], x1["procedure_days"]) == (
        codes.DONE, "eshop", 20260910, 9)
    assert (x1["start_price"], x1["contract_price"], x1["branch_code"]) == (
        Decimal("120.00"), Decimal("100.00"), "UGE-02")
    assert x1["cp_code"] == stable_code("XR-CP-", "305555555")
    assert x2["cp_code"] == codes.INDIVIDUAL_CP and x2["method"] == "direct"
    assert (x3["method"], x3["status"], x3["cp_code"], x3["date_id"]) == (
        "other", codes.IN_WORK[0], None, 20260915)
    cps = {r["code"]: r for t, r in sink.rows if t == "dim_counterparty"}
    assert cps[codes.INDIVIDUAL_CP]["name"] == codes.INDIVIDUAL_NAME
    assert cps[codes.INDIVIDUAL_CP]["inn"] is None
    assert "Иванов" not in json.dumps(sink.rows, ensure_ascii=False, default=str)
    assert "Иванов" not in json.dumps(sink.errors, ensure_ascii=False)
    noms = [r for t, r in sink.rows if t == "dim_nomenclature"]
    assert [n["category"] for n in noms] == ["Запасные части"]
    assert [(c, s) for _, c, _, s in sink.errors] == [
        ("unknown_method", "warning"), ("unknown_customer", "error"),
        ("unknown_status", "error"), ("bad_row", "error")]
    assert method_code("  электронный   МАГАЗИН ") == "eshop"


def test_portal_requires_reporting_sink_and_stub_is_not_configured() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        ProcurementConnector(ListPortal(), {}).extract(SEPT, Plain())
    with pytest.raises(PortalNotConfigured, match="Портал закупок не настроен"):
        XaridPortal()
    assert {"xarid", "onec_zakupki"} <= set(KNOWN_SOURCES)
    with pytest.raises(ConfigError, match="Портал закупок не настроен"):
        make_connector("xarid", get_settings())


def fake_client(handler_body: dict[int, bytes], seen: list[dict[str, Any]]) -> OneCClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"path": request.url.path, **body})
        return httpx.Response(200, content=handler_body.get(body["Year"], b'{"items": []}'))

    return OneCClient(BASE, "u", "p", transport=httpx.MockTransport(handler))


def test_purchase_plan_mapping() -> None:
    seen: list[dict[str, Any]] = []
    connector = OneCPurchasePlanConnector(fake_client({2026: FIXTURE.read_bytes()}, seen), [ORG])
    sink = ReportSink()
    stats = connector.extract(SEPT, sink)
    assert seen == [{"path": "/con2026/hs/aiassistant/purchasePlan", "Year": 2026}]
    rows = sorted((r for t, r in sink.rows if t == "fact_procurement"),
                  key=lambda r: r["start_price"])
    assert [(r["branch_code"], r["start_price"]) for r in rows] == [
        ("1C:Неизвестная организация", Decimal("1.00")), ("UGE-02", Decimal("210.00")),
        ("UGE-02", Decimal("240.00"))]
    for r in rows:
        assert (r["doc_type"], r["status"], r["method"], r["date_id"]) == (
            codes.PLAN_DOC, codes.PLAN_STATUS, codes.PLAN_METHOD, 20260101)
        assert r["nom_code"] is None and r["cp_code"] is None and r["contract_price"] is None
    assert stats.by_target == {"fact_procurement": 3}


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_purchase_plan_runner_full_load(source: str) -> None:
    tag = new_tag()
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch_row(tag)]})
    merge_all(run, source)
    org = OrgMap(branch_code=f"T-{tag}", org_uid=f"uid-{tag}", org_name="Тестовая организация")
    payload = json.dumps({"items": [
        {"org_name": "Тестовая организация", "nomenclature_name": "А", "sum_incoming": 300000000},
        {"org_name": "Тестовая организация", "nomenclature_name": "Б", "sum_incoming": 150000000},
    ]}).encode()
    seen: list[dict[str, Any]] = []
    connector = OneCPurchasePlanConnector(fake_client({2026: payload}, seen), [org],
                                          source=source)
    result = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, sleep=lambda _: None).run()
    assert result.status == "success", result
    assert sorted({s["Year"] for s in seen}) == [2024, 2025, 2026]
    with etl_transaction() as conn:
        branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                 {"c": f"T-{tag}"}).scalar_one()
        plan = conn.execute(text(
            "SELECT plan FROM mart.agg_procurement_plan WHERE build_id = :b AND branch_id = :br "
            "AND month_id = 202601"), {"b": result.build_id, "br": branch_id}).scalar_one()
    assert float(plan) == 450.0


@pytest.fixture
def orgs_setting() -> Iterator[None]:
    put_setting("onec.orgs", [{"branch_code": "UGE-02", "org_uid": "uid-02",
                               "org_name": "Чорвоқ ГЭС"}])
    yield
    put_setting("onec.orgs", [])


def test_make_connector_and_worker(orgs_setting: None) -> None:
    from pydantic import SecretStr

    with pytest.raises(ConfigError, match="ONEC_BASE_URL"):
        make_connector("onec_zakupki", get_settings())
    ready = get_settings().model_copy(update={
        "onec_base_url": BASE, "onec_username": SecretStr("u"), "onec_password": SecretStr("p")})
    made = make_connector("onec_zakupki", ready)
    assert isinstance(made, OneCPurchasePlanConnector) and made.orgs == [ORG]
    jobs = {j.id: j for j in worker.build_scheduler(ready, RecordingNotifier()).get_jobs()}
    assert jobs["etl_onec_zakupki"].args[:2] == ("onec_zakupki", Mode.FULL)
    off = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "etl_onec_zakupki" not in off
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_procurement_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.zakupki.connector'`.

- [ ] **Step 4: Implementatsiya — portal interfeysi**

`backend/app/etl/zakupki/portal.py`:
```python
"""Xarid portali adapteri interfeysi (S4 spec 3.1). xarid.uzex.uz / davlat xaridlari portali
formati mijoz bilan kelishilmagan (TZ 8: «API портала или реестровая выгрузка», 2-bosqich),
shuning uchun protokol + «не настроен» stub'i; kanonik qatorlarga xaritalash —
ProcurementConnector'da (adapter faqat PortalLot beradi).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.core.config import ConfigError
from app.etl.askue.registry import normalize_name
from app.etl.types import HealthResult, Window
from app.etl.zakupki.codes import CANCELLED, DONE, IN_WORK

PORTAL_MESSAGE = ("Портал закупок не настроен: формат выгрузки xarid.uzex.uz не согласован — "
                  "загружайте лоты CSV-файлом (docs/integration/zakupki-format.md)")


@dataclass(frozen=True, slots=True)
class PortalLot:
    lot_no: str
    customer_inn: str
    method: str
    status: str
    announce_date: date
    contract_date: date | None
    start_price_uzs: Decimal
    contract_price_uzs: Decimal | None
    supplier_inn: str | None
    supplier_name: str | None
    subject: str


class ProcurementPortal(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def lots(self, window: Window) -> Iterator[PortalLot]: ...


class PortalNotConfigured(ConfigError):
    """Portal formati hali kelishilmagan (spec 12, 1-savol)."""


class XaridPortal:
    name = "xarid"

    def __init__(self) -> None:
        raise PortalNotConfigured(PORTAL_MESSAGE)

    def healthcheck(self) -> HealthResult:
        raise PortalNotConfigured(PORTAL_MESSAGE)

    def lots(self, window: Window) -> Iterator[PortalLot]:
        raise PortalNotConfigured(PORTAL_MESSAGE)


def _key(name: str) -> str:
    return normalize_name(name).replace("ё", "е")


_METHODS = {_key(k): v for k, v in {
    "Электронный магазин": "eshop", "Elektron do'kon": "eshop",
    "Электронный конкурс": "contest", "Конкурс": "contest", "Tanlov": "contest",
    "Тендер": "tender", "Tender": "tender",
    "Биржевые торги": "exchange", "Биржа": "exchange", "Birja savdolari": "exchange",
    "Прямой договор": "direct", "To'g'ridan-to'g'ri shartnoma": "direct",
}.items()}
_STATUSES = {_key(k): v for k, v in {
    "Объявлен": IN_WORK[0], "Опубликован": IN_WORK[0], "На оценке": IN_WORK[1],
    "Рассмотрение предложений": IN_WORK[1], "Договор заключён": DONE,
    "Заключен договор": DONE, "Отменён": CANCELLED, "Аннулирован": CANCELLED,
}.items()}


def method_code(name: str) -> str | None:
    return _METHODS.get(_key(name))


def status_code(name: str) -> str | None:
    return _STATUSES.get(_key(name))
```

- [ ] **Step 5: Implementatsiya — portal konnektori**

`backend/app/etl/zakupki/connector.py`:
```python
"""ProcurementConnector — SourceConnector (S4 spec 3.1): ProcurementPortal lotlari → kanonik
fact_procurement qatorlari (+ dim_counterparty, dim_nomenclature).

Buyurtmachi INN → filial (dim_branch.inn xaritasi, make_connector to'ldiradi); usul nomi → kod
(noma'lum → «other» + ogohlantirish); holat nomi → kod (noma'lum → xato, qator o'tkaziladi).
Qator sanasi: tuzilgan — shartnoma sanasi, qolganlari — e'lon sanasi. Jismoniy shaxs/YaTT
(14 xonali INN) — CP-FL «Физическое лицо», ismi hech qayerga yozilmaydi (TZ 9). Upsert.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from app.etl.askue.registry import normalize_name
from app.etl.onec.connector import stable_code, to_mln
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)
from app.etl.zakupki.codes import DONE, INDIVIDUAL_CP, INDIVIDUAL_NAME
from app.etl.zakupki.portal import PortalLot, ProcurementPortal, method_code, status_code

SOURCE = "xarid"
DOC_TYPE = "portal_lot"
ERROR_TARGET = "procurement_portal"
_PINFL = re.compile(r"^\d{14}$")


class ProcurementConnector:
    def __init__(self, portal: ProcurementPortal, branches: Mapping[str, str], *,
                 source: str = SOURCE,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.portal = portal
        self.branches = dict(branches)
        self.now = now

    def healthcheck(self) -> HealthResult:
        return self.portal.healthcheck()

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("ProcurementConnector uchun ReportingSink kerak (xatolar jurnali)")
        cps: dict[str, dict[str, Any]] = {}
        noms: dict[str, dict[str, Any]] = {}
        rows = 0
        for lot in self.portal.lots(window):
            row = self._row(lot, sink, cps, noms)
            if row is None or not window.contains_id(int(row["date_id"])):
                continue
            sink.add("fact_procurement", row)
            rows += 1
        for cp in cps.values():
            sink.add("dim_counterparty", cp)
        for nom in noms.values():
            sink.add("dim_nomenclature", nom)
        return ExtractStats(rows, {})

    def _row(self, lot: PortalLot, sink: ReportingSink, cps: dict[str, dict[str, Any]],
             noms: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        no = lot.lot_no[:64]
        branch = self.branches.get(lot.customer_inn)
        if branch is None:
            sink.error(target=ERROR_TARGET, code="unknown_customer", src_id=no,
                       message=f"лот {no}: заказчик (ИНН) не сопоставлен с филиалом")
            return None
        status = status_code(lot.status)
        if status is None:
            sink.error(target=ERROR_TARGET, code="unknown_status", src_id=no,
                       message=f"лот {no}: неизвестный статус «{lot.status[:40]}»")
            return None
        method = method_code(lot.method)
        if method is None:
            sink.error(target=ERROR_TARGET, code="unknown_method", src_id=no, severity="warning",
                       message=f"лот {no}: способ «{lot.method[:40]}» учтён как «прочие»")
            method = "other"
        done = status == DONE
        if done and (lot.contract_date is None or lot.contract_price_uzs is None):
            sink.error(target=ERROR_TARGET, code="bad_row", src_id=no,
                       message=f"лот {no}: для заключённого договора нужны дата и цена договора")
            return None
        day = lot.contract_date if done and lot.contract_date else lot.announce_date
        cp_code = self._supplier(lot, cps) if done else None
        subject = lot.subject.strip()[:300] or "—"
        nom_code = stable_code("XR-S-", normalize_name(subject))
        noms.setdefault(nom_code, {"code": nom_code, "name": subject,
                                   "category": subject[:100], "unit": "—", "enbt_code": None})
        return {
            "doc_type": DOC_TYPE, "src_id": no, "date_id": int(day.strftime("%Y%m%d")),
            "branch_code": branch, "nom_code": nom_code, "cp_code": cp_code, "lot_no": no,
            "method": method, "status": status, "start_price": to_mln(lot.start_price_uzs),
            "contract_price": to_mln(lot.contract_price_uzs) if done and lot.contract_price_uzs
            is not None else None,
            "procedure_days": (day - lot.announce_date).days if done else None}

    @staticmethod
    def _supplier(lot: PortalLot, cps: dict[str, dict[str, Any]]) -> str | None:
        inn = (lot.supplier_inn or "").strip()
        if not inn:
            return None
        if _PINFL.fullmatch(inn):  # jismoniy shaxs / YaTT — shaxsiy ma'lumot saqlanmaydi
            cps.setdefault(INDIVIDUAL_CP, {"code": INDIVIDUAL_CP, "name": INDIVIDUAL_NAME,
                                           "kind": "supplier", "inn": None})
            return INDIVIDUAL_CP
        code = stable_code("XR-CP-", inn)
        name = (lot.supplier_name or inn).strip()[:300]
        cps.setdefault(code, {"code": code, "name": name, "kind": "supplier", "inn": inn})
        return code
```

- [ ] **Step 6: Implementatsiya — 1C xarid rejasi**

`backend/app/etl/zakupki/onec_plan.py`:
```python
"""OneCPurchasePlanConnector — 1C `hs/aiassistant/purchasePlan` (РегистрНакопления.ПланыЗакупок)
→ yillik xarid rejasi (S4 spec 3.1). S1 hisobi va OneCClient qayta ishlatiladi.

Javob: {"items": [{org_name, nomenclature_name, quantity_incoming, sum_incoming}]} (so'm).
Tashkilot → filial `onec.orgs` nomi bo'yicha (normallashtirilgan); moslashtirilmagan —
unmapped_branch (S1 qarori: publish to'xtaydi, jim yo'qotish yo'q). (Filial, nomenklatura) bo'yicha
yig'indi; sana — yilning 1-yanvari; oyna yillari to'liq qayta beriladi (maqsad «to'liq»).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.dwh.dates import date_id, today_tashkent
from app.etl.askue.registry import normalize_name
from app.etl.onec.client import OneCClient
from app.etl.onec.connector import OrgMap, to_mln, unmapped_branch
from app.etl.onec.models import parse
from app.etl.types import (
    ConnectorUnavailableError,
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)
from app.etl.zakupki.codes import PLAN_DOC, PLAN_METHOD, PLAN_STATUS

SOURCE = "onec_zakupki"
PATH = "/purchasePlan"


class PurchasePlanRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, coerce_numbers_to_str=True)
    org_name: str = Field(min_length=1, max_length=300)
    nomenclature_name: str | None = Field(None, max_length=300)
    sum_incoming: Decimal


class PurchasePlanResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    items: list[PurchasePlanRow]


def _hash(text: str) -> str:
    return hashlib.sha256(normalize_name(text).encode()).hexdigest()[:12]


class OneCPurchasePlanConnector:
    def __init__(self, client: OneCClient, orgs: Sequence[OrgMap], *, source: str = SOURCE,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.client = client
        self.orgs = list(orgs)
        self.now = now

    def healthcheck(self) -> HealthResult:
        try:
            self.client.post(PATH, {"Year": today_tashkent().year})
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "1С (план закупок) доступна")

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        by_name = {normalize_name(o.org_name): o for o in self.orgs}
        sums: dict[tuple[str, str, str, int], Decimal] = defaultdict(Decimal)
        for year in range(window.date_from.year, window.date_to.year + 1):
            data = parse(PurchasePlanResponse, self.client.post(PATH, {"Year": year}), PATH)
            for row in data.items:
                org = by_name.get(normalize_name(row.org_name))
                branch = org.branch_code if org else unmapped_branch(row.org_name)
                org_key = org.org_uid if org else f"1C:{_hash(row.org_name)}"
                sums[(branch, org_key, _hash(row.nomenclature_name or "—"), year)] += (
                    row.sum_incoming)
        count = 0
        for (branch, org_key, nom_key, year), amount in sorted(sums.items()):
            if amount <= 0:
                continue
            sink.add("fact_procurement", self._plan_row(branch, org_key, nom_key, year, amount))
            count += 1
        return ExtractStats(count, {"fact_procurement": count})

    @staticmethod
    def _plan_row(branch: str, org_key: str, nom_key: str, year: int,
                  amount: Decimal) -> dict[str, Any]:
        return {"doc_type": PLAN_DOC, "src_id": f"{org_key}:{nom_key}:{year}",
                "date_id": date_id(date(year, 1, 1)), "branch_code": branch, "nom_code": None,
                "cp_code": None, "lot_no": f"ПЛАН-{year}", "method": PLAN_METHOD,
                "status": PLAN_STATUS, "start_price": to_mln(amount), "contract_price": None,
                "procedure_days": None}
```

- [ ] **Step 7: Reyestr va worker**

`backend/app/etl/connectors.py` — importlarga:
```python
from sqlalchemy import text

from app.etl.zakupki.connector import ProcurementConnector
from app.etl.zakupki.onec_plan import OneCPurchasePlanConnector
from app.etl.zakupki.portal import XaridPortal
```
`KNOWN_SOURCES` ni almashtiring (S3'dan keyin):
```python
KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank", "askue", "onec_sklad",
                 "xarid", "onec_zakupki")
```
`_onec_sklad` dan keyin qo'shing:
```python
def _xarid(settings: Settings) -> ProcurementConnector:
    portal = XaridPortal()  # hozircha PortalNotConfigured (spec 12, 1-savol)
    with get_engine("etl").connect() as conn:
        branches = {str(inn): str(code) for code, inn in conn.execute(text(
            "SELECT code, inn FROM dwh.dim_branch WHERE inn IS NOT NULL")).all()}
    return ProcurementConnector(portal, branches)


def _onec_zakupki(settings: Settings) -> OneCPurchasePlanConnector:
    if not settings.onec_base_url:
        raise ConfigError("ONEC_BASE_URL berilmagan — 1C xarid rejasi konnektori o'chiq")
    with get_engine("etl").connect() as conn:
        orgs = current_setting(conn, "onec.orgs")
    if not orgs:
        raise ConfigError("onec.orgs bo'sh: `python -m app.cli onec-orgs --file …` bilan sozlang")
    client = OneCClient(
        settings.onec_base_url, settings.onec_username.get_secret_value(),
        settings.onec_password.get_secret_value(), verify=verify_setting(settings.onec_ca_file),
        allow_http=settings.onec_allow_http, max_bytes=settings.onec_max_bytes)
    return OneCPurchasePlanConnector(client, [OrgMap(**org) for org in orgs])
```
`make_connector` ichida `if source == "onec_sklad":` dan oldin:
```python
    if source == "xarid":
        return _xarid(settings)
    if source == "onec_zakupki":
        return _onec_zakupki(settings)
```

`backend/app/worker.py` — `build_scheduler` ichida (`etl_onec` S1 blokidan keyin, xuddi shu `if settings.onec_base_url:` sharti ostida yoki yangi blok sifatida):
```python
    if settings.onec_base_url:
        with get_engine("app").connect() as conn:
            zakupki_cron = str(current_setting(conn, "etl.onec_zakupki_cron"))
        # S4: 1C xarid rejasi — kechasi to'liq (yillik reja kam o'zgaradi, bitta so'rov/yil).
        scheduler.add_job(run_etl_job, CronTrigger.from_crontab(zakupki_cron, timezone=TASHKENT),
                          args=("onec_zakupki", Mode.FULL, notifier), id="etl_onec_zakupki",
                          **opts)
```

- [ ] **Step 8: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_procurement_sources.py tests/test_worker.py tests/test_onec_connector.py -v`
Expected: barcha testlar passed.

- [ ] **Step 9: Commit**

```bash
git add backend
git commit -m "feat(zakupki): portal adapteri interfeysi va konnektori, xarid stub'i, 1C xarid rejasi konnektori

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 15: HR API — mijoz (server tomonida login, token faqat xotirada), oq ro'yxatli javob modeli, `HrSource` (HR API va mehnat.uz stub'i)

**Files:**
- Create: `backend/app/etl/hr/client.py`, `backend/app/etl/hr/models.py`, `backend/app/etl/hr/source.py`, `backend/tests/fixtures/hr/main.json`, `backend/tests/fixtures/hr/by_category.json`, `backend/tests/fixtures/hr/by_org.json`
- Test: `backend/tests/test_hr_api_client.py`

**Interfaces:**
- Consumes: `ConfigError`, `ConnectorUnavailableError`, `HealthResult`.
- Produces:
  - `app.etl.hr.client`: `TIMEOUT` (connect 5 s, read 60 s), `MAX_BYTES = 8 MiB`, `LOGIN_PATH = "/auth/login"`, `HrApiError(ValueError)` (qayta urinilmaydi), `HrApiClient(base_url, username, password, *, verify=True, proxy="", transport=None, timeout=TIMEOUT, max_bytes=MAX_BYTES, clock=time.monotonic)` + `.get(path) -> Any`, `.close()`. Login — `POST /auth/login` form-urlencoded (`username`, `password`) → `access_token`, `expires_in` (yo'q/noto'g'ri → 3600); token muddati tugashidan 60 s oldin yoki 401 da bir marta yangilanadi. Faqat `https://`; `trust_env=False`, redirect yo'q. Xato matnlarida javob tanasi, token va parol yo'q.
  - `app.etl.hr.models`: `HrFormatError(HrApiError)`, `BreakdownRow(organization, category, employees, staff, hired, fired, overtime)`, `parse_main(data) -> int | None` (`total_employees_count` yoki `total_count`), `parse_breakdown(data) -> list[BreakdownRow]` (ro'yxat; `{"data"|"items"|"results": [...]}`; `{toifa: son}`) — faqat oq ro'yxatdagi kalitlar o'qiladi, qolganlari (jumladan ФИО) tashlanadi.
  - `app.etl.hr.source`: `MAIN_PATH = "/dashboard/main"`, `HrSnapshot(as_of, rows, total)`, `HrSource` (Protocol: `name`, `healthcheck()`, `snapshot(today) -> HrSnapshot`), `HrApiSource(client, breakdown_path)`, `MEHNAT_MESSAGE`, `MehnatNotConfigured(ConfigError)`, `MehnatSource()` (yaratishda xato).

- [ ] **Step 1: Yozib olingan javoblar**

Eski dashboard (`1C.1/sections567.jsx`, `api.js`) `/dashboard/main` dan `total_employees_count`, `present_employees_count`, `absent_employees_count`, `vacation_count` ni o'qigan; `/dashboard/employees-by-category` shakli hujjatlanmagan — quyidagi fixture'lar konnektor qabul qiladigan shakllar (kengaytirilgan — `hr-sorov-s4.md` da so'raladigan maydonlar; `manager_full_name` va `pinfl` — oq ro'yxat testini tekshirish uchun).

`backend/tests/fixtures/hr/main.json`:
```json
{"total_employees_count": 100, "present_employees_count": 80, "absent_employees_count": 12, "vacation_count": 8}
```
`backend/tests/fixtures/hr/by_category.json`:
```json
[{"category": "Руководители", "count": 12}, {"category": "Специалисты", "count": 88}]
```
`backend/tests/fixtures/hr/by_org.json`:
```json
{"data": [
  {"organization": "Чорвоқ ГЭС", "category": "Руководители", "employees_count": 9, "staff_units": 10, "hired": 1, "fired": 0, "overtime_hours": 20, "manager_full_name": "Иванов Иван Иванович", "pinfl": "12345678901234"},
  {"organization": "Чорвоқ ГЭС", "category": "Оперативный персонал", "employees_count": 81, "staff_units": 90, "hired": 2, "fired": 3, "overtime_hours": 400},
  {"organization": "Фарҳод ГЭС", "category": "Руководители", "employees_count": 5},
  {"organization": "Неизвестный филиал", "category": "Руководители", "employees_count": 3}
]}
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_hr_api_client.py`:
```python
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import ConfigError
from app.etl.hr.client import HrApiClient, HrApiError
from app.etl.hr.models import HrFormatError, parse_breakdown, parse_main
from app.etl.hr.source import HrApiSource, MehnatNotConfigured, MehnatSource
from app.etl.types import ConnectorUnavailableError

FIXTURES = Path(__file__).parent / "fixtures" / "hr"
BASE = "https://hr.test"
SECRET = "p@ss-не-логировать"
TOKEN = "tok-secret-123"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _server(log: list[str], *, get_status: list[int] | None = None,
            login_status: int = 200, body: bytes | None = None,
            expires_in: Any = 600) -> Callable[[httpx.Request], httpx.Response]:
    statuses = list(get_status or [])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            log.append("login")
            assert request.headers["content-type"] == "application/x-www-form-urlencoded"
            assert parse_qs(request.content.decode()) == {"username": ["u"],
                                                          "password": [SECRET]}
            if login_status != 200:
                return httpx.Response(login_status, json={"detail": SECRET})
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": expires_in,
                                             "token_type": "bearer"})
        log.append(f"GET {request.url.path} {request.headers.get('authorization')}")
        status = statuses.pop(0) if statuses else 200
        return httpx.Response(status, content=body if body is not None else b'{"ok": true}')

    return handler


def _client(handler: Callable[[httpx.Request], httpx.Response], clock: Clock | None = None,
            **kw: Any) -> HrApiClient:
    return HrApiClient(BASE, "u", SECRET, transport=httpx.MockTransport(handler),
                       clock=clock or Clock(), **kw)


def test_login_once_and_bearer_reused() -> None:
    log: list[str] = []
    client = _client(_server(log))
    assert client.get("/dashboard/main") == {"ok": True}
    client.get("/dashboard/main")
    assert log == ["login", f"GET /dashboard/main Bearer {TOKEN}",
                   f"GET /dashboard/main Bearer {TOKEN}"]
    assert TOKEN not in repr(client) and SECRET not in repr(client)


def test_token_cached_and_refreshed_on_expiry_and_401() -> None:
    log: list[str] = []
    clock = Clock()
    client = _client(_server(log, get_status=[200, 401, 200]), clock)
    client.get("/a")
    clock.now += 600 - 60 + 1  # muddatdan 60 s oldin yangilanadi
    client.get("/b")  # 401 → qayta login → takror
    assert [x for x in log if x == "login"] == ["login", "login", "login"]
    assert log[-1] == f"GET /b Bearer {TOKEN}"


def test_errors_are_classified_and_sanitized() -> None:
    with pytest.raises(HrApiError) as exc:
        _client(_server([], login_status=403)).get("/a")
    assert "учётную запись" in str(exc.value) and SECRET not in str(exc.value)
    with pytest.raises(ConnectorUnavailableError):
        _client(_server([], login_status=503)).get("/a")
    with pytest.raises(ConnectorUnavailableError):
        _client(_server([], get_status=[502])).get("/a")
    with pytest.raises(HrApiError) as twice:
        _client(_server([], get_status=[401, 401])).get("/a")
    assert TOKEN not in str(twice.value)
    with pytest.raises(HrApiError, match="байт"):
        _client(_server([], body=b"x" * 2048), max_bytes=1024).get("/a")
    with pytest.raises(HrApiError, match="JSON"):
        _client(_server([], body=b"<html>")).get("/a")
    log: list[str] = []
    _client(_server(log, expires_in="soon")).get("/a")  # noto'g'ri expires_in → 3600
    with pytest.raises(ConfigError, match="https"):
        HrApiClient("http://hr.test", "u", "p")
    with pytest.raises(ConfigError, match="hr_username"):
        HrApiClient(BASE, "", "p")


def test_parse_main_and_breakdown_shapes() -> None:
    assert parse_main(json.loads((FIXTURES / "main.json").read_text(encoding="utf-8"))) == 100
    assert parse_main({"total_count": 7}) == 7 and parse_main({"x": 1}) is None
    plain = parse_breakdown(json.loads((FIXTURES / "by_category.json").read_text("utf-8")))
    assert [(r.organization, r.category, r.employees) for r in plain] == [
        (None, "Руководители", 12), (None, "Специалисты", 88)]
    assert [r.category for r in parse_breakdown({"Руководители": 3, "Специалисты": 4})] == [
        "Руководители", "Специалисты"]
    rows = parse_breakdown(json.loads((FIXTURES / "by_org.json").read_text(encoding="utf-8")))
    first = rows[0]
    assert (first.organization, first.category, first.employees, first.staff, first.hired,
            first.fired, first.overtime) == ("Чорвоқ ГЭС", "Руководители", 9, 10, 1, 0, 20)
    assert rows[2].staff is None and rows[2].hired is None
    assert "Иванов" not in repr(rows) and "12345678901234" not in repr(rows)
    for bad in ({"data": [{"count": 1}]}, [{"category": "X", "count": -1}], "text",
                [{"category": "X", "count": "много"}]):
        with pytest.raises(HrFormatError):
            parse_breakdown(bad)


def test_api_source_and_mehnat_stub() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 600})
        name = "main.json" if request.url.path == "/dashboard/main" else "by_org.json"
        return httpx.Response(200, content=(FIXTURES / name).read_bytes())

    source = HrApiSource(_client(handler), "/dashboard/employees-by-category")
    snap = source.snapshot(date(2026, 9, 24))
    assert snap.as_of == date(2026, 9, 24) and snap.total == 100 and len(snap.rows) == 4
    assert source.healthcheck().ok is True
    down = HrApiSource(_client(_server([], login_status=503)), "/x")
    assert down.healthcheck().ok is False
    with pytest.raises(MehnatNotConfigured, match="mehnat.uz"):
        MehnatSource()
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_hr_api_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.hr.client'`.

- [ ] **Step 4: Implementatsiya — mijoz**

`backend/app/etl/hr/client.py`:
```python
"""HR API mijozi (S4 spec 3.3): server tomonida login, token faqat shu obyekt xotirasida.

Eski dashboard (proxy.php `hr_token`) bilan bir xil oqim: POST /auth/login (form-urlencoded) →
access_token + expires_in; so'rovlarga `Authorization: Bearer`. Token muddati tugashidan 60 s
oldin yoki 401 javobida bir marta yangilanadi. Faqat https, TLS tekshiruvi (ixtiyoriy
korporativ CA), trust_env=False, redirect yo'q, javob hajmi chegarasi. Xato matnlariga javob
tanasi, token yoki parol yozilmaydi.
"""

from __future__ import annotations

import json
import ssl
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import ConfigError
from app.etl.types import ConnectorUnavailableError

TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
MAX_BYTES = 8 * 1024 * 1024
LOGIN_PATH = "/auth/login"
_DEFAULT_TTL = 3600
WHERE = "HR API"


class HrApiError(ValueError):
    """Qayta urinilmaydigan xato (hisob, format, 4xx)."""


class HrApiClient:
    def __init__(self, base_url: str, username: str, password: str, *,
                 verify: ssl.SSLContext | bool = True, proxy: str = "",
                 transport: httpx.BaseTransport | None = None, timeout: httpx.Timeout = TIMEOUT,
                 max_bytes: int = MAX_BYTES, clock: Callable[[], float] = time.monotonic) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigError("HR_BASE_URL https:// manzil bo'lishi kerak")
        if not username or not password:
            raise ConfigError("hr_username/hr_password sirlari bo'sh")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._expires = 0.0
        self._clock = clock
        self.max_bytes = max_bytes
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, verify=verify, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport,
            headers={"Accept": "application/json"})

    def __repr__(self) -> str:
        return f"HrApiClient({self.http.base_url!s})"

    def close(self) -> None:
        self.http.close()

    def _read(self, method: str, path: str, **kw: Any) -> tuple[int, bytes]:
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream(method, path, **kw) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise HrApiError(f"{WHERE} {path}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{WHERE} {path}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{WHERE} {path}: {type(exc).__name__}") from exc
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{WHERE} {path}: HTTP {status}")
        return status, b"".join(chunks)

    @staticmethod
    def _json(raw: bytes, path: str) -> Any:
        try:
            return json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HrApiError(f"{WHERE} {path}: ответ не JSON") from exc

    def _login(self) -> None:
        status, raw = self._read("POST", LOGIN_PATH,
                                 data={"username": self._username, "password": self._password})
        if status != 200:
            raise HrApiError(f"{WHERE}: вход не выполнен (HTTP {status}), "
                             "проверьте учётную запись hr_username/hr_password")
        data = self._json(raw, LOGIN_PATH)
        token = data.get("access_token") if isinstance(data, Mapping) else None
        if not isinstance(token, str) or not token:
            raise HrApiError(f"{WHERE}: ответ входа без access_token")
        try:
            ttl = int(data.get("expires_in", _DEFAULT_TTL))
        except (TypeError, ValueError):
            ttl = _DEFAULT_TTL
        self._token = token
        self._expires = self._clock() + max(60, ttl - 60)

    def _authorized(self, path: str) -> tuple[int, bytes]:
        if self._token is None or self._clock() >= self._expires:
            self._login()
        return self._read("GET", path, headers={"Authorization": f"Bearer {self._token}"})

    def get(self, path: str) -> Any:
        status, raw = self._authorized(path)
        if status == 401:  # token muddatidan oldin bekor qilingan — bir marta qayta kirish
            self._token = None
            status, raw = self._authorized(path)
        if status == 401:
            raise HrApiError(f"{WHERE} {path}: доступ запрещён после повторного входа")
        if not 200 <= status < 300:
            raise HrApiError(f"{WHERE} {path}: HTTP {status}")
        return self._json(raw, path)
```

- [ ] **Step 5: Implementatsiya — javob modeli (oq ro'yxat)**

`backend/app/etl/hr/models.py`:
```python
"""HR API javoblari — faqat agregatlar (TZ 9). Har qator faqat oq ro'yxatdagi kalitlardan
o'qiladi; boshqa kalitlar (ФИО, ПИНФЛ, tabel raqami va h.k.) umuman o'qilmaydi, saqlanmaydi,
log'ga yozilmaydi. `name` kaliti toifa sifatida QABUL QILINMAYDI — xodimlar ro'yxatidagi ism
toifa deb adashib saqlanmasin.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.etl.hr.client import HrApiError

_LIST_KEYS = ("data", "items", "results")
_ORG = ("organization", "organization_name", "org_name", "org")
_CATEGORY = ("category", "category_name", "position_category")
_EMPLOYEES = ("employees_count", "employee_count", "count", "total")
_STAFF = ("staff_units", "staff_count")
_HIRED = ("hired", "hired_count")
_FIRED = ("fired", "fired_count", "dismissed")
_OVERTIME = ("overtime_hours",)


class HrFormatError(HrApiError):
    """Javob tuzilmasi kutilganidek emas (qiymatlar xato matniga yozilmaydi)."""


@dataclass(frozen=True, slots=True)
class BreakdownRow:
    organization: str | None
    category: str
    employees: int
    staff: Decimal | None
    hired: int | None
    fired: int | None
    overtime: Decimal | None


def _first(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _number(value: Any, line: int) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise HrFormatError(f"строка {line}: ожидается число")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise HrFormatError(f"строка {line}: ожидается число") from exc
    if not number.is_finite() or number < 0:
        raise HrFormatError(f"строка {line}: отрицательное или недопустимое число")
    return number


def _int(value: Any, line: int) -> int | None:
    number = _number(value, line)
    return None if number is None else int(number)


def parse_main(data: Any) -> int | None:
    if not isinstance(data, Mapping):
        return None
    value = _first(data, ("total_employees_count", "total_count"))
    try:
        return _int(value, 0)
    except HrFormatError:
        return None


def _items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                return list(data[key])
        if data and all(isinstance(v, int | float) and not isinstance(v, bool)
                        for v in data.values()):
            return [{"category": k, "count": v} for k, v in data.items()]
    raise HrFormatError("HR API: неожиданная структура ответа (ожидается список агрегатов)")


def parse_breakdown(data: Any) -> list[BreakdownRow]:
    rows: list[BreakdownRow] = []
    for line, item in enumerate(_items(data), start=1):
        if not isinstance(item, Mapping):
            raise HrFormatError(f"строка {line}: ожидается объект")
        category = _first(item, _CATEGORY)
        employees = _int(_first(item, _EMPLOYEES), line)
        if not isinstance(category, str) or not category.strip() or employees is None:
            raise HrFormatError(f"строка {line}: нет категории или численности")
        org = _first(item, _ORG)
        rows.append(BreakdownRow(
            organization=org.strip()[:200] if isinstance(org, str) and org.strip() else None,
            category=category.strip()[:100], employees=employees,
            staff=_number(_first(item, _STAFF), line), hired=_int(_first(item, _HIRED), line),
            fired=_int(_first(item, _FIRED), line),
            overtime=_number(_first(item, _OVERTIME), line)))
    return rows
```

- [ ] **Step 6: Implementatsiya — manbalar**

`backend/app/etl/hr/source.py`:
```python
"""Kadrlar manbalari (S4 spec 3.3): HrSource protokoli — HR API (hr-api.uzgidro.uz) va
mehnat.uz (TZ 8: 3-bosqich — faqat interfeys, «не настроен»)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.config import ConfigError
from app.etl.hr.client import HrApiClient
from app.etl.hr.models import BreakdownRow, parse_breakdown, parse_main
from app.etl.types import ConnectorUnavailableError, HealthResult

MAIN_PATH = "/dashboard/main"
MEHNAT_MESSAGE = "mehnat.uz не подключён: интеграция предусмотрена этапом 3 ТЗ (раздел 8)"


@dataclass(frozen=True, slots=True)
class HrSnapshot:
    as_of: date
    rows: tuple[BreakdownRow, ...]
    total: int | None


class HrSource(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def snapshot(self, today: date) -> HrSnapshot: ...


class HrApiSource:
    name = "hr_api"

    def __init__(self, client: HrApiClient, breakdown_path: str) -> None:
        self.client = client
        self.breakdown_path = breakdown_path

    def healthcheck(self) -> HealthResult:
        try:
            self.client.get(MAIN_PATH)
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "HR API доступен")

    def snapshot(self, today: date) -> HrSnapshot:
        total = parse_main(self.client.get(MAIN_PATH))
        rows = parse_breakdown(self.client.get(self.breakdown_path))
        return HrSnapshot(today, tuple(rows), total)


class MehnatNotConfigured(ConfigError):
    """mehnat.uz — TZ 8 bo'yicha 3-bosqich (spec 2, «Kirmaydi»)."""


class MehnatSource:
    name = "mehnat"

    def __init__(self) -> None:
        raise MehnatNotConfigured(MEHNAT_MESSAGE)

    def healthcheck(self) -> HealthResult:
        raise MehnatNotConfigured(MEHNAT_MESSAGE)

    def snapshot(self, today: date) -> HrSnapshot:
        raise MehnatNotConfigured(MEHNAT_MESSAGE)
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_hr_api_client.py -v`
Expected: 5 passed. `$TEST ruff check app tests` va `$TEST mypy app` — xatosiz.

- [ ] **Step 8: Commit**

```bash
git add backend
git commit -m "feat(hr): HR API mijozi (token faqat xotirada), oq ro'yxatli javob modeli, HR va mehnat.uz manbalari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 16: `HrConnector` — tashkilotlar moslashtirishi, nazorat jami, `hr-orgs`/`hr-check` CLI, reyestr va worker jadvali

**Files:**
- Create: `backend/app/etl/hr/connector.py`, `backend/app/etl/hr/admin.py`
- Modify: `backend/app/etl/connectors.py`, `backend/app/cli.py`, `backend/app/worker.py` (`run_hr_job`, `build_scheduler`), `backend/tests/test_worker.py`
- Test: `backend/tests/test_hr_connector.py`

**Interfaces:**
- Consumes: `HrSource`, `HrSnapshot`, `BreakdownRow`, `HrApiClient`, `HrApiSource`, `MehnatSource`, `HrOrg`, `normalize_name`, `stable_code`, `ReportingSink`, `ExtractStats`, `date_id`, `month_id`, `today_tashkent`, `verify_setting`, `Settings.hr_*`, `Settings.egress_proxy`, `current_setting` (`hr.orgs`, `hr.breakdown_path`, `etl.hr_cron`), `validate_setting`, `banks.admin._put`, `record`, `AuditAction.SETTING_UPDATED`, `run_etl_job`, `notify_rejected_rows`, `Runner`, `Mode`, `tests.etl_helpers.*`.
- Produces:
  - `app.etl.hr.connector`: `SOURCE = "hr"`, `DOC_TYPE = "hr_snapshot"`, `ERROR_TARGET = "hr_api"`, `TOTAL_TOLERANCE = 0.01`, `position_code(category) -> str` (`HR-P-` + xesh), `HrConnector(source, orgs, *, source_name=SOURCE, today=today_tashkent, now=...)` — `SourceConnector`; `extract` `ReportingSink` talab qiladi, `ExtractStats(rows, {})` (upsert). Qator: `src_id = "<filial>:<lavozim>:<YYYYMM>"`, sana — bugun, `headcount_plan = staff | 0`, `payroll = 0`. Xato/ogohlantirish kodlari: `no_branch_breakdown` (warning), `unmapped_org`, `no_org`, `total_mismatch` (warning).
  - `app.etl.hr.admin`: `hr_orgs_command(file: Path | None, out) -> int` (0 / 1; audit `admin.setting.updated` `via=cli`).
  - `KNOWN_SOURCES` += `"hr"`, `"mehnat"`; `make_connector("hr")` (`HR_BASE_URL` yoki sirlar bo'sh → `ConfigError`), `make_connector("mehnat")` → `MehnatNotConfigured`.
  - Worker: `run_hr_job(notifier) -> RunResult | None` (faqat `severity = 'error'` qatorlar bo'lsa `hr_rows_rejected` xabari); job `etl_hr` (`etl.hr_cron`) — faqat `HR_BASE_URL` berilgan bo'lsa. CLI: `hr-orgs [--file]`, `hr-check` (0 / 1 / 2).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_hr_connector.py`:
```python
import json
import logging
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.hr.connector import HrConnector, position_code
from app.etl.hr.models import parse_breakdown
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrSnapshot
from app.etl.runner import Runner
from app.etl.staging import DbStagingSink
from app.etl.types import HealthResult, Mode, Window
from tests.etl_helpers import (
    TEST_AS_OF,
    RecordingNotifier,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s2_helpers import put_setting

FIXTURES = Path(__file__).parent / "fixtures" / "hr"
WINDOW = Window(date(2026, 9, 1), TEST_AS_OF)
ORGS = [HrOrg(org="Чорвоқ ГЭС", branch_code="UGE-02"), HrOrg(org="Фарҳод ГЭС",
                                                                branch_code="UGE-05")]


class ReportSink:
    def __init__(self) -> None:
        self.load_id = 0
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, str, str, str]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append((target, code, message, severity))


class FakeSource:
    name = "fake"

    def __init__(self, fixture: str, total: int | None = 100) -> None:
        data = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
        self.rows = tuple(parse_breakdown(data))
        self.total = total

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "fake")

    def snapshot(self, today: date) -> HrSnapshot:
        return HrSnapshot(today, self.rows, self.total)


def _extract(source: FakeSource, orgs: list[HrOrg] = ORGS) -> ReportSink:
    sink = ReportSink()
    HrConnector(source, orgs, today=lambda: TEST_AS_OF).extract(WINDOW, sink)
    return sink


def test_org_breakdown_is_mapped_to_fact_hr(caplog: pytest.LogCaptureFixture,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    caplog.set_level(logging.DEBUG)
    sink = _extract(FakeSource("by_org.json"))
    facts = {r["src_id"]: r for t, r in sink.rows if t == "fact_hr"}
    lead, oper = position_code("Руководители"), position_code("Оперативный персонал")
    assert set(facts) == {f"UGE-02:{lead}:202609", f"UGE-02:{oper}:202609",
                          f"UGE-05:{lead}:202609"}
    row = facts[f"UGE-02:{oper}:202609"]
    assert (row["date_id"], row["headcount_plan"], row["headcount_fact"], row["hired"],
            row["fired"], row["overtime_hours"], row["payroll"]) == (
        20260924, 90, 81, 2, 3, 400, 0)
    assert facts[f"UGE-05:{lead}:202609"]["headcount_plan"] == 0  # штат noma'lum
    positions = {r["code"]: r for t, r in sink.rows if t == "dim_position"}
    assert positions[lead] == {"code": lead, "category": "Руководители", "department": "—"}
    assert [(c, s) for _, c, _, s in sink.errors] == [("unmapped_org", "error"),
                                                      ("total_mismatch", "warning")]
    everything = json.dumps([sink.rows, sink.errors], ensure_ascii=False, default=str)
    captured = capsys.readouterr()
    for secret in ("Иванов", "12345678901234"):
        assert secret not in everything and secret not in caplog.text
        assert secret not in captured.out and secret not in captured.err


def test_no_org_breakdown_is_a_warning() -> None:
    sink = _extract(FakeSource("by_category.json"))
    assert [t for t, _ in sink.rows] == []
    assert [(c, s) for _, c, _, s in sink.errors] == [("no_branch_breakdown", "warning")]


def test_requires_reporting_sink() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        HrConnector(FakeSource("by_org.json"), ORGS).extract(WINDOW, Plain())


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_loads_idempotently(source: str) -> None:
    tag = new_tag()
    a, b = branch_row(tag), branch_row(f"{tag}B")
    run = open_run(source)
    stage(run, source, {"dim_branch": [a, b]})
    merge_all(run, source)
    orgs = [HrOrg(org="Чорвоқ ГЭС", branch_code=a["code"]),
            HrOrg(org="Фарҳод ГЭС", branch_code=b["code"]),
            HrOrg(org="Неизвестный филиал", branch_code=b["code"])]
    for _ in range(2):
        connector = HrConnector(FakeSource("by_org.json", total=98), orgs, source_name=source,
                                today=lambda: TEST_AS_OF)
        result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                        sleep=lambda _: None).run()
        assert result.status == "success", result
    with etl_transaction() as conn:
        count = conn.execute(text("SELECT count(*) FROM dwh.fact_hr WHERE src_system = :s"),
                             {"s": source}).scalar_one()
        branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                 {"c": a["code"]}).scalar_one()
        fact = conn.execute(text(
            "SELECT sum(headcount_fact) FROM mart.agg_hr_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202609"),
            {"b": result.build_id, "br": branch_id}).scalar_one()
    assert count == 3 and float(fact) == 90.0


@pytest.fixture
def orgs_setting() -> Iterator[None]:
    yield
    put_setting("hr.orgs", [])


def test_hr_orgs_cli_make_connector_and_worker(tmp_path: Path, orgs_setting: None,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    from pydantic import SecretStr

    good = tmp_path / "orgs.json"
    good.write_text(json.dumps([o.model_dump() for o in ORGS], ensure_ascii=False),
                    encoding="utf-8")
    assert cli.main(["hr-orgs", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "hr.orgs") == [o.model_dump() for o in ORGS]
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["orgs"] == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"org": "X", "branch_code": "NOPE"}]), encoding="utf-8")
    assert cli.main(["hr-orgs", "--file", str(bad)]) == 1
    assert cli.main(["hr-orgs"]) == 0
    assert "NOPE" in capsys.readouterr().out
    assert {"hr", "mehnat"} <= set(KNOWN_SOURCES)
    with pytest.raises(ConfigError, match="HR_BASE_URL"):
        make_connector("hr", get_settings())
    no_secret = get_settings().model_copy(update={"hr_base_url": "https://hr.test"})
    with pytest.raises(ConfigError, match="hr_username"):
        make_connector("hr", no_secret)
    ready = no_secret.model_copy(update={"hr_username": SecretStr("u"),
                                         "hr_password": SecretStr("p")})
    made = make_connector("hr", ready)
    assert isinstance(made, HrConnector) and [o.org for o in made.orgs] == [o.org for o in ORGS]
    with pytest.raises(ConfigError, match="mehnat.uz"):
        make_connector("mehnat", ready)
    jobs = {j.id: j for j in worker.build_scheduler(ready, RecordingNotifier()).get_jobs()}
    assert jobs["etl_hr"].func is worker.run_hr_job
    off = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "etl_hr" not in off
    assert cli.main(["hr-check"]) == 2


def test_hr_notification_only_for_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.etl.runner import RunResult

    source = new_source()
    run = open_run(source)
    monkeypatch.setattr(worker, "run_etl_job", lambda *_a: RunResult(run, "success", None))
    notifier = RecordingNotifier()
    with etl_transaction() as conn:
        DbStagingSink(conn, run, source).error(target="hr_api", code="no_branch_breakdown",
                                               message="m", severity="warning")
    worker.run_hr_job(notifier)
    assert notifier.kinds == []
    with etl_transaction() as conn:
        DbStagingSink(conn, run, source).error(target="hr_api", code="unmapped_org",
                                               message="m")
    worker.run_hr_job(notifier)
    assert notifier.kinds == ["hr_rows_rejected"]
```

`backend/tests/test_worker.py` — oxiriga qo'shing:
```python
def test_scheduler_adds_hr_job_only_with_base_url() -> None:
    ids = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "etl_hr" not in ids
    ready = get_settings().model_copy(update={"hr_base_url": "https://hr.test"})
    jobs = {j.id: j for j in worker.build_scheduler(ready, RecordingNotifier()).get_jobs()}
    assert jobs["etl_hr"].func is worker.run_hr_job
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_hr_connector.py tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.hr.connector'`.

- [ ] **Step 3: Implementatsiya — konnektor**

`backend/app/etl/hr/connector.py`:
```python
"""HrConnector — SourceConnector (S4 spec 3.3): HrSource snapshot'i → fact_hr (filial × toifa ×
joriy oy) va dim_position (toifa).

Tashkilot → filial `hr.orgs` (normallashtirilgan nom). Tashkilot kesimi umuman yo'q —
`no_branch_breakdown` ogohlantirishi, fact_hr yozilmaydi (spec 11.6). Moslashtirilmagan
tashkilot — `unmapped_org` (xato, qatorlari o'tkaziladi). Yuklangan jami `/dashboard/main`
jamidan 1% dan ko'p farq qilsa — `total_mismatch` ogohlantirishi. Upsert: oy ichida kalit bir
xil (sana — bugun, oxirgi snapshot qoladi). Shaxsiy ma'lumot modelga kirmaydi (models.py).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.dwh.dates import date_id, month_id, today_tashkent
from app.etl.askue.registry import normalize_name
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrSource
from app.etl.onec.connector import stable_code
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "hr"
DOC_TYPE = "hr_snapshot"
ERROR_TARGET = "hr_api"
TOTAL_TOLERANCE = 0.01


def position_code(category: str) -> str:
    return stable_code("HR-P-", normalize_name(category))


class HrConnector:
    def __init__(self, source: HrSource, orgs: Sequence[HrOrg], *, source_name: str = SOURCE,
                 today: Callable[[], date] = today_tashkent,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source_name
        self.hr = source
        self.orgs = list(orgs)
        self.today = today
        self.now = now

    def healthcheck(self) -> HealthResult:
        return self.hr.healthcheck()

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("HrConnector xatolarni yozish uchun ReportingSink talab qiladi")
        snap = self.hr.snapshot(self.today())
        if not any(r.organization for r in snap.rows):
            sink.error(target=ERROR_TARGET, code="no_branch_breakdown", severity="warning",
                       message="HR API не даёт разреза по организациям — численность филиалов "
                               "не загружена (docs/integration/hr-sorov-s4.md)")
            return ExtractStats(0, {})
        by_org = {normalize_name(o.org): o.branch_code for o in self.orgs}
        sums: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal))
        categories: dict[str, str] = {}
        unmapped: set[str] = set()
        loaded = 0
        for row in snap.rows:
            if row.organization is None:
                unmapped.add("")
                continue
            branch = by_org.get(normalize_name(row.organization))
            if branch is None:
                unmapped.add(row.organization)
                continue
            pos = position_code(row.category)
            categories.setdefault(pos, row.category)
            acc = sums[(branch, pos)]
            acc["plan"] += row.staff or Decimal(0)
            acc["fact"] += Decimal(row.employees)
            acc["hired"] += Decimal(row.hired or 0)
            acc["fired"] += Decimal(row.fired or 0)
            acc["overtime"] += row.overtime or Decimal(0)
            loaded += row.employees
        for org in sorted(unmapped):
            if org:
                sink.error(target=ERROR_TARGET, code="unmapped_org",
                           message=f"организация «{org[:80]}» не сопоставлена с филиалом "
                                   "(hr.orgs)")
            else:
                sink.error(target=ERROR_TARGET, code="no_org",
                           message="строки без организации пропущены")
        for pos, category in categories.items():
            sink.add("dim_position", {"code": pos, "category": category, "department": "—"})
        ym = month_id(snap.as_of)
        for (branch, pos), acc in sorted(sums.items()):
            sink.add("fact_hr", self._fact(branch, pos, ym, snap.as_of, acc))
        if snap.total and abs(loaded - snap.total) > snap.total * TOTAL_TOLERANCE:
            sink.error(target=ERROR_TARGET, code="total_mismatch", severity="warning",
                       message=f"сумма по филиалам {loaded} не совпадает с общей численностью "
                               f"{snap.total}")
        return ExtractStats(len(sums), {})

    @staticmethod
    def _fact(branch: str, pos: str, ym: int, day: date,
              acc: dict[str, Decimal]) -> dict[str, Any]:
        return {"doc_type": DOC_TYPE, "src_id": f"{branch}:{pos}:{ym}", "date_id": date_id(day),
                "branch_code": branch, "pos_code": pos, "headcount_plan": acc["plan"],
                "headcount_fact": acc["fact"], "payroll": Decimal(0), "hired": int(acc["hired"]),
                "fired": int(acc["fired"]), "overtime_hours": acc["overtime"]}
```

- [ ] **Step 4: Implementatsiya — operator buyrug'i**

`backend/app/etl/hr/admin.py`:
```python
"""Operator CLI: HR tashkilotlari ↔ filiallar moslashtirishi (`hr.orgs`). Yangi versiya + audit."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, record
from app.core.db import get_engine
from app.dwh.reference import current_setting, validate_setting
from app.etl.banks.admin import _put
from app.etl.db import etl_transaction

Out = Callable[[str], None]


def _show(orgs: list[dict[str, str]], out: Out) -> None:
    for o in orgs:
        out(f"{o['branch_code']:<10} {o['org']}")


def hr_orgs_command(file: Path | None, out: Out) -> int:
    if file is None:
        with get_engine("app").connect() as conn:
            current = list(current_setting(conn, "hr.orgs"))
        _show(current, out)
        out(f"hr.orgs: {len(current)} ta tashkilot")
        return 0
    try:
        value = validate_setting("hr.orgs", json.loads(file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        out(f"Xato: {exc}")
        return 1
    with etl_transaction() as conn:
        known = set(conn.execute(text("SELECT code FROM dwh.dim_branch")).scalars())
    missing = sorted({o["branch_code"] for o in value} - known)
    if missing:
        out(f"Xato: noma'lum filial kodlari: {', '.join(missing)}")
        return 1
    version = _put("hr.orgs", value)
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="hr.orgs",
                      details={"via": "cli", "version": version, "orgs": len(value)}))
    _show(value, out)
    out(f"hr.orgs: versiya {version}, {len(value)} ta tashkilot")
    return 0
```

- [ ] **Step 5: Reyestr, worker, CLI**

`backend/app/etl/connectors.py` — importlarga:
```python
from app.etl.hr.client import HrApiClient
from app.etl.hr.connector import HrConnector
from app.etl.hr.registry import HrOrg
from app.etl.hr.source import HrApiSource, MehnatSource
```
`KNOWN_SOURCES` ni almashtiring:
```python
KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank", "askue", "onec_sklad",
                 "xarid", "onec_zakupki", "hr", "mehnat")
```
`_onec_zakupki` dan keyin qo'shing:
```python
def _hr(settings: Settings) -> HrConnector:
    if not settings.hr_base_url:
        raise ConfigError("HR_BASE_URL berilmagan — HR API konnektori o'chiq")
    username = settings.hr_username.get_secret_value()
    password = settings.hr_password.get_secret_value()
    if not username or not password:
        raise ConfigError("hr_username/hr_password sirlari bo'sh")
    with get_engine("etl").connect() as conn:
        orgs = current_setting(conn, "hr.orgs")
        path = str(current_setting(conn, "hr.breakdown_path"))
    client = HrApiClient(settings.hr_base_url, username, password,
                         verify=verify_setting(settings.hr_ca_file), proxy=settings.egress_proxy)
    return HrConnector(HrApiSource(client, path), [HrOrg.model_validate(o) for o in orgs])
```
`make_connector` ichida `if source == "xarid":` dan oldin:
```python
    if source == "hr":
        return _hr(settings)
    if source == "mehnat":
        MehnatSource()  # TZ 8: 3-bosqich — har doim MehnatNotConfigured (ConfigError)
        raise ConfigError("mehnat.uz")  # pragma: no cover — erishib bo'lmaydi (mypy uchun)
```

`backend/app/worker.py` — `notify_askue_errors` dan keyin qo'shing:
```python
def run_hr_job(notifier: Notifier) -> RunResult | None:
    """HR API yuklash; faqat xato (warning emas) qatorlar bo'lsa xabar — tashkilot kesimi
    kelmaguncha kundalik ogohlantirish bilan administratorni bezovta qilmaslik uchun."""
    result = run_etl_job("hr", Mode.INCREMENTAL, notifier)
    if result is None or result.run_id is None:
        return result
    with etl_transaction() as conn:
        errors = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM core.etl_error WHERE run_id = :r AND target = 'hr_api' "
            "AND severity = 'error')"), {"r": result.run_id}).scalar_one()
    if errors:
        notify_rejected_rows(
            result.run_id, notifier, target="hr_api", kind="hr_rows_rejected",
            subject="Данные HR API отклонены",
            hint="Сопоставление организаций — `python -m app.cli hr-orgs`, запрос к "
                 "разработчикам HR — docs/integration/hr-sorov-s4.md.")
    return result
```
`build_scheduler` ichida (`etl_onec_zakupki` blokidan keyin):
```python
    if settings.hr_base_url:
        with get_engine("app").connect() as conn:
            hr_cron = str(current_setting(conn, "etl.hr_cron"))
        # S4: HR API — kuniga bir marta joriy oy snapshot'i (TZ 8: mehnat.uz — oyiga, 3-bosqich).
        scheduler.add_job(run_hr_job, CronTrigger.from_crontab(hr_cron, timezone=TASHKENT),
                          args=(notifier,), id="etl_hr", **opts)
```

`backend/app/cli.py` — importlarga:
```python
from app.etl.hr.admin import hr_orgs_command
```
`_onec_sklad_check` dan keyin qo'shing:
```python
def _hr_check() -> int:
    from app.etl.connectors import make_connector

    try:
        connector = make_connector("hr")
    except ConfigError as exc:
        _out(f"Konfiguratsiya xatosi: {exc}")
        return 2
    health = connector.healthcheck()
    _out(f"HR API: {'OK' if health.ok else 'XATO'} — {health.detail}")
    return 0 if health.ok else 1
```
`main` ichida:
```python
    p = sub.add_parser("hr-orgs")
    p.add_argument("--file", type=Path, default=None)
    sub.add_parser("hr-check")
```
dispatch'da:
```python
    if args.command == "hr-orgs":
        return hr_orgs_command(args.file, _out)
    if args.command == "hr-check":
        return _hr_check()
```
Docstring ro'yxatiga:
```
hr-orgs — HR tashkilotlari ↔ filiallar (JSON fayldan; faylsiz — ko'rsatish)
hr-check — HR API'ga ulanishni tekshirish (0 — OK, 1 — xato, 2 — konfiguratsiya)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_hr_connector.py tests/test_hr_api_client.py tests/test_worker.py tests/test_askue_connector.py -v`
Expected: barcha testlar passed (runner: qayta yuklash dublikat bermaydi — 3 qator; `Неизвестный филиал` bu testda ikkinchi filialga bog'langan va «Фарҳод» bilan bitta qatorga yig'iladi).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(hr): HrConnector — tashkilotlar moslashtirishi, nazorat jami, hr-orgs/hr-check CLI, worker jadvali

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 17: Ekspluatatsiya — prod compose (HR sirlari va muhiti), kanonik fayl formatlari (xarid, АИП, kadrlar), HR yo'riqnomasi, so'rov xatlari

**Files:**
- Create: `docs/integration/zakupki-format.md`, `docs/integration/aip-format.md`, `docs/integration/kadry-fayl.md`, `docs/integration/hr-connector.md`, `docs/integration/hr-sorov-s4.md`, `docs/integration/1c-sorov-s4.md`, `backend/tests/ops/test_s4_ops.py`, `backend/tests/test_s4_file_templates.py`
- Modify: `deploy/compose.prod.yml`, `deploy/prod.env.example`, `deploy/secrets.example/README.md`, `scripts/prod_config.sh`, `docs/ops/host-hardening.md`
- Test: `backend/tests/ops/test_s4_ops.py`, `backend/tests/test_s4_file_templates.py`

**Interfaces:**
- Consumes: 4-reja `compose.prod.yml` (`worker` — `backend` + `egress`), S3 worker sirlari ro'yxati, `tests.ops.repo.repo_path`, `scripts/prod_config.sh`, `FileConnector`, `Runner`, `builds.active_build`, 1–16-vazifalar kodlari va sozlamalari (`HR_BASE_URL`, sirlar `hr_username`, `hr_password`, `hr_ca_bundle`).
- Produces: sirlar `hr_username`, `hr_password`, `hr_ca_bundle` — faqat `worker`; `worker` muhiti `HR_BASE_URL`; 6 ta hujjat (ruscha — mijoz, xarid/ПТО/HR bo'limlari, 1C va HR dasturchilari uchun); egress qoidasi (`hr-api.uzgidro.uz`). Hujjatdagi CSV shablonlari test bilan haqiqatda yuklanadi; noma'lum usul — fayl rad etiladi.

- [ ] **Step 1: Yiqiladigan testlarni yozish**

`backend/tests/ops/test_s4_ops.py`:
```python
from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

HR = {"hr_username", "hr_password", "hr_ca_bundle"}
DOCS = {
    "docs/integration/zakupki-format.md": (
        "fact_procurement.csv", "договор заключён", "на оценке", "eshop", "direct",
        "zakupki.method_norms", "procurement_plan", "CP-FL", "UTF-8"),
    "docs/integration/aip-format.md": (
        "fact_investment.csv", "fact_object_stage.csv", "dim_object.csv", "aip_opening",
        "physical_pct", "advance_date_id", "adreska", "responsible_person"),
    "docs/integration/kadry-fayl.md": (
        "fact_hr.csv", "dim_position.csv", "headcount_plan", "overtime_hours",
        "kazna.calendar_kinds", "ФИО"),
    "docs/integration/hr-connector.md": (
        "HR_BASE_URL", "hr_username", "hr-orgs", "hr-check", "extra_hosts",
        "hr.breakdown_path", "no_branch_breakdown"),
    "docs/integration/hr-sorov-s4.md": (
        "organization", "staff_units", "hired", "fired", "overtime_hours",
        "персональных данных", "только чтение"),
    "docs/integration/1c-sorov-s4.md": (
        "/purchasePlan", "org_uid", "purchase_method_name", "/purchaseRequests",
        "responsible_name", "КС-2"),
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_hr_secrets_and_env_only_in_worker(compose: dict[str, Any]) -> None:
    assert HR <= set(compose["secrets"])
    for service, svc in compose["services"].items():
        granted = HR & set(svc.get("secrets", []))
        assert granted == (HR if service == "worker" else set()), service
    env = compose["services"]["worker"]["environment"]
    assert env["HR_BASE_URL"] == "${HR_BASE_URL:-}"
    assert "HR_BASE_URL" not in compose["services"]["api"].get("environment", {})


def test_docs_mention_required_facts() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "hr-api.uzgidro.uz" in hardening
    secrets = repo_path("deploy/secrets.example/README.md").read_text(encoding="utf-8")
    assert all(name in secrets for name in HR)
    script = repo_path("scripts/prod_config.sh").read_text(encoding="utf-8")
    assert "hr_username hr_password hr_ca_bundle" in script
```

`backend/tests/test_s4_file_templates.py` (hujjatdagi CSV shablonlari haqiqatda yuklanadi):
```python
from pathlib import Path

from sqlalchemy import text

from app.dwh import builds
from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from tests.etl_helpers import TEST_AS_OF, new_source, new_tag, purge_source


def _write(folder: Path, name: str, *lines: str) -> None:
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _templates(folder: Path, tag: str, method: str = "eshop") -> None:
    code = f"T-{tag}"
    _write(folder, "dim_branch.csv", "code;name;short_name;kind;capacity_mw;sort_order",
           f"{code};Тестовая ГЭС;Т;ges;100;99")
    _write(folder, "dim_nomenclature.csv", "code;name;category;unit;enbt_code",
           f"PS-{tag};Запасные части;Запасные части;—;")
    _write(folder, "dim_counterparty.csv", "code;name;kind;inn",
           f"S-{tag};ООО «Гидромонтаж Сервис»;supplier;301234567")
    _write(folder, "fact_procurement.csv",
           "doc_type;src_id;date;branch_code;nom_code;cp_code;lot_no;method;status;"
           "start_price;contract_price;procedure_days",
           f"procurement_plan;PLAN-{tag}-2026;2026-01-01;{code};;;ПЛАН-2026;plan;план;"
           "1000.00;;",
           f"portal_lot;LOT-{tag}-1;2026-08-10;{code};PS-{tag};S-{tag};2026-0101;{method};"
           "договор заключён;100.00;90.00;12",
           f"portal_lot;LOT-{tag}-2;2026-07-01;{code};PS-{tag};;2026-0102;contest;объявлен;"
           "80.00;;")
    _write(folder, "dim_source.csv", "code;name;kind", f"SRC-{tag};Бюджетные средства;budget")
    _write(folder, "dim_object.csv",
           "code;name;program_code;work_type;commissioning_year;total_cost;source_code",
           f"OBJ-{tag};Модернизация гидроагрегатов;АИП-2026-01;modernization;2026;1000.00;"
           f"SRC-{tag}")
    _write(folder, "fact_investment.csv",
           "doc_type;src_id;date;branch_code;object_code;source_code;plan;fact;physical_pct;"
           "advance;advance_date_id",
           f"aip_opening;OPEN-{tag};2025-01-01;{code};OBJ-{tag};SRC-{tag};0;300.00;;0;",
           f"aip_month;INV-{tag}-202608;2026-08-01;{code};OBJ-{tag};SRC-{tag};60.00;40.00;"
           "0.4000;30.00;20260601",
           f"aip_month;INV-{tag}-202612;2026-12-01;{code};OBJ-{tag};SRC-{tag};60.00;0;;0;")
    _write(folder, "fact_object_stage.csv",
           "doc_type;src_id;date;branch_code;object_code;stage_no;stage_name;fact_date_id",
           f"aip_stage;STG-{tag}-1;2026-03-15;{code};OBJ-{tag};1;"
           "Проектно-сметная документация;20260310")
    _write(folder, "dim_position.csv", "code;category;department",
           f"POS-{tag};Оперативный персонал;Производственные подразделения")
    _write(folder, "fact_hr.csv",
           "doc_type;src_id;date;branch_code;pos_code;headcount_plan;headcount_fact;payroll;"
           "hired;fired;overtime_hours",
           f"hr_month;HR-{tag}-202608;2026-08-31;{code};POS-{tag};90;81;0;2;3;400.0")


def test_s4_templates_load(tmp_path: Path) -> None:
    source = new_source()
    tag = new_tag()
    try:
        _templates(tmp_path, tag)
        result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                        today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": f"T-{tag}"}).scalar_one()
            params = {"b": result.build_id, "br": branch_id}
            lots = conn.execute(text(
                "SELECT lot_no, overdue FROM mart.agg_procurement_lots WHERE build_id = :b "
                "AND branch_id = :br ORDER BY lot_no"), params).all()
            plan = conn.execute(text(
                "SELECT plan FROM mart.agg_procurement_plan WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202601"), params).scalar_one()
            inv = conn.execute(text(
                "SELECT month_id, plan, physical_pct, advance FROM mart.agg_investment_month "
                "WHERE build_id = :b AND branch_id = :br AND month_id IN (202608, 202612) "
                "ORDER BY month_id"), params).all()
            stage = conn.execute(text(
                "SELECT done FROM mart.agg_object_stages WHERE build_id = :b "
                "AND branch_id = :br"), params).scalar_one()
            hr = conn.execute(text(
                "SELECT headcount_fact FROM mart.agg_hr_month WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202608"), params).scalar_one()
        assert [(r.lot_no, r.overdue) for r in lots] == [("2026-0101", False),
                                                         ("2026-0102", True)]
        assert float(plan) == 1000.0 and float(hr) == 81.0 and stage is True
        assert [(r.month_id, float(r.plan)) for r in inv] == [(202608, 60.0), (202612, 60.0)]
        assert (float(inv[0].physical_pct), float(inv[0].advance)) == (0.4, 30.0)
    finally:
        purge_source(source)


def test_bad_method_rejects_file(tmp_path: Path) -> None:
    source = new_source()
    try:
        _templates(tmp_path, new_tag(), method="auction")
        with etl_transaction() as conn:
            before = builds.active_build(conn)
        result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                        today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "failed" and "fact_procurement_method_ck" in (result.error or "")
        with etl_transaction() as conn:
            assert builds.active_build(conn) == before
    finally:
        purge_source(source)
```
(`RunResult.error` — 2-reja `_describe(exc)`: `"<tur>: <xabar>"[:400]`; PostgreSQL `CheckViolation` xabari cheklov nomini birinchi qatorda beradi.)

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/ops/test_s4_ops.py tests/test_s4_file_templates.py -v`
Expected: `test_s4_ops.py` — FAIL (HR sirlari va hujjatlar yo'q); `test_s4_file_templates.py` — PASS (1–16-vazifalar kodi shablonlarni allaqachon qo'llaydi; hujjatlar shu test bilan bir xil yoziladi).

- [ ] **Step 3: Compose, env namunasi, sirlar**

`deploy/compose.prod.yml` — top-level `secrets:` ga qo'shing:
```yaml
  hr_username: {file: "${UGK_SECRETS_DIR:-./secrets}/hr_username"}
  hr_password: {file: "${UGK_SECRETS_DIR:-./secrets}/hr_password"}
  hr_ca_bundle: {file: "${UGK_SECRETS_DIR:-./secrets}/hr_ca_bundle"}
```
`worker.environment` ga qo'shing:
```yaml
      HR_BASE_URL: ${HR_BASE_URL:-}
```
`worker.secrets` ro'yxatini almashtiring (S3 ro'yxati + HR):
```yaml
    secrets: [db_app_password, db_etl_password, redis_password, master_kek, blind_index_key,
              session_pepper, smtp_password, tls_cert, onec_username, onec_password,
              onec_ca_bundle, telegram_bot_token, telegram_chat_ids, onec_sklad_username,
              onec_sklad_password, hr_username, hr_password, hr_ca_bundle]
```

`deploy/prod.env.example` — oxiriga:
```bash
# HR API (kadrlar agregatlari), masalan https://hr-api.uzgidro.uz. Bo'sh — konnektor o'chiq.
# Login/parol — sirlar hr_username / hr_password; korporativ CA — hr_ca_bundle (bo'sh — tizim CA).
# DNS bo'lmasa — docs/integration/hr-connector.md (compose override, extra_hosts).
HR_BASE_URL=
```

`deploy/secrets.example/README.md` — jadval oxiriga:
```markdown
| hr_username | HR API login'i — faqat o'qish huquqli servis hisobi; bo'sh — o'chiq. Faqat worker |
| hr_password | HR API paroli; bo'sh — o'chiq. Faqat worker |
| hr_ca_bundle | HR API sertifikatini tekshirish uchun korporativ CA (PEM); bo'sh — tizim CA. Faqat worker |
```

`scripts/prod_config.sh` — `for name in …` ro'yxati oxiriga (`onec_sklad_username onec_sklad_password` dan keyin) qo'shing:
```bash
            hr_username hr_password hr_ca_bundle \
```
(ya'ni `… onec_sklad_username onec_sklad_password \` / `hr_username hr_password hr_ca_bundle; do`.)

- [ ] **Step 4: Host egress qoidasi**

`docs/ops/host-hardening.md` — S3'da qo'shilgan «Онлайн-мощность ГЭС» abzasidan keyin qo'shing:
````markdown
**HR API (раздел S4).** Если задан `HR_BASE_URL` (например, `https://hr-api.uzgidro.uz`), `worker`
раз в сутки обращается к `hr-api.uzgidro.uz:443`. При работе через корпоративный прокси
(`EGRESS_PROXY`) домен добавляется в список разрешённых на прокси; без прокси в `DOCKER-USER`
разрешается адрес сервиса на порт 443 (перед правилом `-o ens18 -j DROP`). Сертификат проверяется
всегда (при необходимости — корпоративный CA в секрете `hr_ca_bundle`).
````

- [ ] **Step 5: Xarid formati (ruscha)**

`docs/integration/zakupki-format.md`:
````markdown
# Закупки: формат файла лотов и годового плана — UGEKAZNA

До подключения портала закупок (xarid.uzex.uz / портал госзакупок — формат не согласован) лоты
загружаются CSV-файлами через файловый коннектор. Годовой план закупок дополнительно приходит из
1С (`/purchasePlan`, если настроен `ONEC_BASE_URL`).

## Общие правила (ТЗ, раздел 8)

- Кодировка UTF-8, разделитель `;`, первая строка — заголовок; даты `ГГГГ-ММ-ДД`; суммы — млн сум
  с точкой, без разделителей разрядов.
- Файлы кладутся в каталог файлового коннектора (`/data/inbox` в контейнере `worker`), загрузка —
  `python -m app.cli etl-run --source file --mode full`. Коннектор полностью заменяет свои строки в
  окне загрузки: файл содержит все лоты окна.

## fact_procurement.csv — лоты

```
doc_type;src_id;date;branch_code;nom_code;cp_code;lot_no;method;status;start_price;contract_price;procedure_days
procurement_plan;PLAN-UGE-02-2026;2026-01-01;UGE-02;;;ПЛАН-2026;plan;план;1000.00;;
portal_lot;LOT-2026-0101;2026-08-10;UGE-02;PS-01;CP-001;2026-0101;eshop;договор заключён;100.00;90.00;12
portal_lot;LOT-2026-0102;2026-07-01;UGE-02;PS-03;;2026-0102;contest;объявлен;80.00;;
```

| Колонка | Значение |
|---|---|
| `doc_type` | `portal_lot` — лот; `procurement_plan` — строка годового плана |
| `src_id` | уникальный ключ лота (повторная загрузка заменяет строку) |
| `date` | «договор заключён» — дата договора; «объявлен», «на оценке», «отменён» — дата объявления; план — 1 января |
| `method` | `eshop` (электронный магазин), `contest` (электронный конкурс), `tender`, `exchange` (биржевые торги), `direct` (прямой договор), `other`; план — `plan` |
| `status` | ровно: `объявлен`, `на оценке`, `договор заключён`, `отменён`; план — `план` |
| `start_price`, `contract_price` | начальная цена и цена договора, млн сум |
| `procedure_days` | для заключённых договоров — дней от объявления до договора |
| `nom_code` | предмет закупки — код из `dim_nomenclature.csv` (категория = предмет) |
| `cp_code` | поставщик — код из `dim_counterparty.csv` (`kind` = `supplier`) |

Неизвестный способ или статус отклоняет весь файл (проверка базы `fact_procurement_method_ck`,
`fact_procurement_status_ck`) — предыдущие данные остаются опубликованными.

Поставщик — физическое лицо или ИП (ПИНФЛ из 14 цифр): указывается общий код `CP-FL`
«Физическое лицо», имя не передаётся (ТЗ, раздел 9).

## Нормативы сроков

Лот «в работе» просрочен, если дней с объявления больше норматива способа + 10 (ТЗ, раздел 4).
Нормативы — настройка `zakupki.method_norms` (дни: eshop 15, contest 40, tender 70, exchange 20,
direct 12, other 40 — предварительно, подлежат утверждению); изменение через администрирование
(`PUT /api/v1/admin/settings/zakupki.method_norms`) сохраняется новой версией с записью в аудит и
применяется со следующей загрузки.
````

- [ ] **Step 6: АИП formati va adreska moslik jadvali (ruscha)**

`docs/integration/aip-format.md`:
````markdown
# Адресная инвестиционная программа (АИП): формат файлов — UGEKAZNA

Источник АИП — канонические CSV-файлы файлового коннектора (решение S4: без прямой интеграции
с модулем adreska). Файлы готовит ПТО/отдел инвестиций или выгрузка из adreska по таблице ниже.
Правила — как для остальных файлов: UTF-8, `;`, даты `ГГГГ-ММ-ДД`, суммы — млн сум с точкой.

## dim_source.csv, dim_object.csv

```
code;name;kind
SRC-1;Бюджетные средства на капитальные вложения;budget
```
`kind`: `budget`, `ifi` (МФИ), `bank`, `own`.

```
code;name;program_code;work_type;commissioning_year;total_cost;source_code
OBJ-01;Модернизация гидроагрегатов Чарвакской ГЭС;АИП-2028-01;modernization;2028;2400000.00;SRC-1
```
`work_type`: `new`, `reconstruction`, `modernization`; `total_cost` — общая стоимость, млн сум.

## fact_investment.csv — объект × месяц

```
doc_type;src_id;date;branch_code;object_code;source_code;plan;fact;physical_pct;advance;advance_date_id
aip_opening;OPEN-01;2025-01-01;UGE-02;OBJ-01;SRC-1;0;300.00;;0;
aip_month;INV-01-202608;2026-08-01;UGE-02;OBJ-01;SRC-1;60.00;40.00;0.4000;30.00;20260601
```
- `date` — первое число месяца; план указывается на все месяцы года, включая будущие.
- `plan` — график финансирования месяца; `fact` — профинансировано (освоено) за месяц.
- `physical_pct` — выполнено по КС-2 нарастающим итогом / сметная стоимость, доля 0…1; пусто —
  без изменений (берётся последнее значение).
- `advance` — остаток незакрытого аванса на конец месяца; `advance_date_id` — дата выдачи самого
  раннего незакрытого аванса (ГГГГММДД).
- `aip_opening` — одна строка на объект: профинансировано до начала истории (входит в «освоено
  ранее», в помесячный факт не входит).

## fact_object_stage.csv — этапы

```
doc_type;src_id;date;branch_code;object_code;stage_no;stage_name;fact_date_id
aip_stage;STG-01-1;2026-03-15;UGE-02;OBJ-01;1;Проектно-сметная документация;20260310
```
`date` — плановое окончание этапа, `fact_date_id` — фактическое (ГГГГММДД, пусто — не завершён).

## Соответствие полям модуля adreska

| Каноническая колонка | adreska |
|---|---|
| `dim_object.code`, `name` | `projects.project_code`, `project_name` |
| `work_type` | `project_type`: `yangi_qurilish` → `new`, `rekonstruksiya` → `reconstruction`, `modernizatsiya` → `modernization` |
| `commissioning_year` | год `projects.end_date` |
| `total_cost` | `projects.total_budget` (сум → млн сум) |
| `source_code` / `dim_source.kind` | `financing_sources.source_type`: `davlat_byudjeti` → `budget`, `xorij_krediti` → `ifi`, `bank_krediti` → `bank`, `oz_mablagi`, `grant`, `investor` → `own` |
| `branch_code` | `projects.branch_id` → `branches.code` (сопоставить с кодами UGE-xx) |
| `plan` | `budget_limits` (месячные; квартальные и годовые — равными долями по месяцам) |
| `fact` | `payments.payment_amount` по месяцу `payment_date` |
| `advance`, `advance_date_id` | `payments` с `payment_type = avans` за вычетом зачтённых (зачёт авансов в adreska не ведётся — рассчитывается при выгрузке) |
| `physical_pct` | `work_forms` (КС-2) нарастающим итогом / `total_budget` (или `completion_pct`) |
| `fact_object_stage` | `project_stages`: `stage_kind`, `planned_end`, `actual_end` |

Не выгружаются (персональные данные, ТЗ раздел 9): `responsible_person`, `chief_engineer`,
`signed_by`, `contractor_tin` физических лиц.
````

- [ ] **Step 7: Kadrlar fayli (ruscha)**

`docs/integration/kadry-fayl.md`:
````markdown
# Кадры: формат файла численности — UGEKAZNA

Пока HR API не даёт разреза по организациям (запрос — `docs/integration/hr-sorov-s4.md`),
численность загружается CSV-файлами файлового коннектора. Только агрегаты: ФИО, ПИНФЛ, табельные
номера и другие персональные данные в файлы не включаются (ТЗ, раздел 9).

## dim_position.csv — категории персонала

```
code;category;department
POS-3;Оперативный персонал;Производственные подразделения
```

## fact_hr.csv — филиал × категория × месяц

```
doc_type;src_id;date;branch_code;pos_code;headcount_plan;headcount_fact;payroll;hired;fired;overtime_hours
hr_month;HR-UGE-02-3-202608;2026-08-31;UGE-02;POS-3;90;81;0;2;3;400.0
```
- `date` — последний день месяца (текущий месяц — дата выгрузки); `headcount_plan` — штат,
  `headcount_fact` — фактическая численность на дату; `hired`, `fired` — принято и уволено за
  месяц; `overtime_hours` — часы сверхурочной работы за месяц.
- `payroll` — 0: фонд оплаты труда берётся из платежей по статьям зарплаты (настройка
  `kazna.calendar_kinds`, ключ `salary`).
````

- [ ] **Step 8: HR konnektori yo'riqnomasi (ruscha)**

`docs/integration/hr-connector.md`:
````markdown
# HR API — инструкция администратора

1. `HR_BASE_URL` в `prod.env` (только `https://`), секреты `hr_username`, `hr_password` — служебная
   учётная запись только на чтение; при корпоративном сертификате — `hr_ca_bundle` (PEM).
   Токен получается сервером (`POST /auth/login`), хранится только в памяти процесса загрузки и
   обновляется по сроку `expires_in`; в браузер, журналы и базу не попадает.
2. Если имя `hr-api.uzgidro.uz` не разрешается DNS внутри сети, адрес закрепляется файлом
   `deploy/compose.override.yml` (сертификат по-прежнему проверяется по имени):
   ```yaml
   services:
     worker:
       extra_hosts: ["hr-api.uzgidro.uz:10.0.0.10"]
   ```
3. Сопоставление организаций HR и филиалов:
   ```bash
   docker compose -f deploy/compose.prod.yml exec worker \
     python -m app.cli hr-orgs --file /data/inbox/hr_orgs.json
   ```
   ```json
   [{"org": "Чорвоқ ГЭС", "branch_code": "UGE-02"}]
   ```
   Без `--file` — показать текущее сопоставление. Каждое изменение — новая версия и запись аудита.
4. Проверка: `python -m app.cli hr-check` (0 — доступен, 1 — ошибка, 2 — не настроен).
5. Загрузка — ежедневно в 06:30 (`etl.hr_cron`): численность по категориям на текущий месяц из
   `hr.breakdown_path` (по умолчанию `/dashboard/employees-by-category`) и общая численность из
   `/dashboard/main` для сверки (расхождение > 1% — предупреждение `total_mismatch`).
6. Пока ответ HR API не содержит организации, данные филиалов не загружаются (предупреждение
   `no_branch_breakdown`), численность — из файлов (`docs/integration/kadry-fayl.md`).
   Несопоставленная организация — ошибка `unmapped_org` и уведомление «Данные HR API отклонены».
7. Из ответа читаются только агрегаты (категория, численность, организация, штат, приём,
   увольнение, сверхурочные); любые другие поля, включая ФИО, отбрасываются.
8. mehnat.uz — этап 3 ТЗ: источник `mehnat` пока «не настроен».
````

- [ ] **Step 9: HR dasturchilariga so'rov xati (ruscha)**

`docs/integration/hr-sorov-s4.md`:
````markdown
# Запрос к разработчикам HR API (hr-api.uzgidro.uz): агрегаты для UGEKAZNA (этап 4)

Сейчас UGEKAZNA получает из HR API только общие счётчики (`/dashboard/main`:
`total_employees_count`, `present_employees_count`, `absent_employees_count`, `vacation_count`)
и численность по категориям без разреза по организациям. Для раздела «Кадры» (ТЗ, разделы 4–5)
нужны агрегаты по филиалам. Просим добавить в `/dashboard/employees-by-category` (или новый метод
с параметром `month=ГГГГ-ММ`) строки вида:

```json
{"data": [{"organization_id": "…", "organization": "Чорвоқ ГЭС", "category": "Оперативный персонал",
           "employees_count": 81, "staff_units": 90, "hired": 2, "fired": 3, "overtime_hours": 400}]}
```

| № | Что нужно | Поле |
|---|---|---|
| H1 | Разрез по организациям (филиалам) | `organization_id`, `organization` |
| H2 | Штатная численность (штатное расписание) | `staff_units` |
| H3 | Фактическая численность на дату | `employees_count` |
| H4 | Принято и уволено за месяц | `hired`, `fired` |
| H5 | Сверхурочные часы за месяц | `overtime_hours` |
| H6 | История помесячно | параметр `month=ГГГГ-ММ` |
| H7 | Начисленный ФОТ (для сверки, необязательно) | `payroll_accrued`, сум |
| H8 | Доступ | отдельная служебная учётная запись только чтение, срок токена, адрес и цепочка сертификата |

Ответ не должен содержать персональных данных (ФИО, ПИНФЛ, паспорт, телефоны, табельные номера):
UGEKAZNA использует только агрегаты (ТЗ, раздел 9) и отбрасывает любые другие поля.
````

- [ ] **Step 10: 1C dasturchilariga so'rov xati (ruscha)**

`docs/integration/1c-sorov-s4.md`:
````markdown
# Запрос к разработчикам 1С: закупки, АИП и кадры для UGEKAZNA (этап 4)

Сервис `hs/aiassistant` уже отдаёт `/purchasePlan` (`{"Year": ГГГГ}` → `org_name`,
`nomenclature_name`, `quantity_incoming`, `sum_incoming`) — UGEKAZNA загружает его как годовой план
закупок. Для разделов «Закупки», «Инвестиции», «Кадры» (ТЗ, разделы 4–5) просим:

| № | Что нужно | Поля |
|---|---|---|
| G1 | `/purchasePlan`: идентификатор организации и группа номенклатуры | `org_uid`, `nomenclature_code`, `nomenclature_group` |
| G2 | Способ закупки (продолжение запроса XARID_TURI_API_SOROV) | `purchase_method_uid`, `purchase_method_name` |
| G3 | Реестр лотов и договоров, если ведётся в 1С | `lot_no`, `org_uid`, способ, статус, дата объявления, дата договора, начальная цена, цена договора, ИНН поставщика, предмет |
| G4 | АИП, если ведётся в 1С: объекты, помесячные лимиты, финансирование | `object_code`, месяц, `plan`, `fact`, источник |
| G5 | Выполнение по КС-2 нарастающим итогом и сметная стоимость | `ks2_total`, `estimate_total` |
| G6 | Авансы: выдано, зачтено, остаток, дата выдачи | `advance_issued`, `advance_offset`, `advance_date` |
| G7 | Кадры из 1С:ЗУП как альтернатива HR API: штат и факт по организации и категории, приём, увольнение | без персональных данных |

`/purchaseRequests` (служебные записки) UGEKAZNA не загружает: это не лоты, а в ответе есть
`responsible_name` (ФИО). Просим не добавлять персональные поля в новые методы.
````

- [ ] **Step 11: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/ops/test_s4_ops.py tests/test_s4_file_templates.py tests/ops -v`
Expected: barcha testlar passed. `./scripts/prod_config.sh` — `prod-config: OK` (sirlar namunasi yangilangan; `hr_ca_bundle` bo'sh fayl bo'lishi mumkin).

- [ ] **Step 12: Commit**

```bash
git add deploy scripts docs backend/tests
git commit -m "docs(s4): xarid, АИП va kadrlar fayl formatlari, HR yo'riqnomasi, HR va 1C'ga so'rov xatlari; prod compose

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 18: Frontend asoslari — tiplar, fixture'lar, matnlar va formulalar, odam/kun/soat formatlari, S4 uslublari

**Files:**
- Create: `frontend/src/dash/people.ts`, `frontend/src/dash/s4.css`, `frontend/src/test/s4Fixtures.ts`
- Modify: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (generatsiya), `frontend/src/api/types.ts`, `frontend/src/dash/formulas.ts` (`IndicatorKey`), `frontend/src/dash/chart.tsx` (`Series.axis`, `barConfig({ rightFormat })`), `frontend/src/i18n/ru.ts`
- Test: `frontend/src/dash/people.test.ts`, `frontend/src/dash/chart.s4.test.ts`

**Interfaces:**
- Consumes: 10–12-vazifa sxemalari (OpenAPI), `formatNumber`, `t`, `MessageKey`, `IndicatorKey`, S1 `dash.css` klasslari (`prog`, `split`, `vt`, `exec`, `bigline`, `seg`, `toolbar`, `rank`).
- Produces:
  - `src/api/types.ts`: `ZakKpisOut, ZakMonthOut, ZakMethodOut, ZakLotOut, ZakNamedOut, ZakBranchOut, ZakSvodOut, ZakLotyOut, ZakPostavshikiOut, ZakEkonomiyaOut, InvKpisOut, InvObjectOut, InvCumOut, InvSourceOut, InvStageOut, InvObjectStagesOut, InvSvodOut, InvObektyOut, InvIstochnikiOut, InvRiskiOut, HrKpisOut, HrMonthOut, HrCategoryOut, HrBranchOut, KadrySvodOut, KadryChislennostOut, KadryFotOut, KadryDvizhenieOut`.
  - `src/dash/people.ts`: `formatPeople(n)`, `formatDays(n)`, `formatHours(n, digits = 0)`, `formatPp(n)` — `null`/`undefined` → `t('dash.noValue')`.
  - `src/dash/s4.css`: `.fp` (moliyaviy polosa + jismoniy belgi), `.stg` (bosqichlar lentasi).
  - `chart.tsx`: `Series.axis?: 'right'` (chiziq o'ng o'qda, `yAxisID: 'y1'`), `barConfig({ …, rightFormat? })` — o'ng o'q faqat shunday seriya bo'lsa qo'shiladi (prototip `fotCard`: ФОТ va o'rtacha ish haqi).
  - `IndicatorKey` += `'contracted' | 'savings' | 'planExec' | 'lotsInWork' | 'lotsOverdue' | 'directShare' | 'avgProcDays' | 'program' | 'invYtd' | 'schedule' | 'finExec' | 'physExec' | 'finGap' | 'advances' | 'objStatus' | 'headcount' | 'vacancies' | 'payroll' | 'avgSalary' | 'staffTurnover' | 'overtime'` (S3'ning `turnover` kaliti — ombor oboroti, shuning uchun kadrlar uchun alohida kalit).
  - i18n: `unit.*` (S4), `formula.*` (S4), `zak.*`, `inv.*`, `kad.*` — 19–21-vazifalar shu kalitlardan foydalanadi.
  - `src/test/s4Fixtures.ts`: `PERIOD_M08_S4, ZAK_KPIS, ZAK_MONTHS, ZAK_METHODS, LOTS, ZAK_SVOD, ZAK_LOTY, ZAK_POSTAVSHIKI, ZAK_EKONOMIYA, INV_KPIS, INV_OBJECTS, INV_CUM, INV_SOURCES, INV_STAGES, INV_SVOD, INV_OBEKTY, INV_ISTOCHNIKI, INV_RISKI, INV_NONE, HR_KPIS, HR_MONTHS, HR_CATEGORIES, HR_BRANCHES, KADRY_SVOD, KADRY_CHISL, KADRY_FOT, KADRY_DVIZH, KADRY_EMPTY`.

- [ ] **Step 1: OpenAPI snapshot va tiplar**

Dev stack (1–17-vazifalar bilan) ishlayotgan bo'lsin: `docker compose -f deploy/compose.yml up -d --build`.
```bash
curl -skf https://localhost:8443/api/v1/openapi.json -o frontend/openapi.json
$NODE npm run gen:api
grep -c "ZakSvodOut\|InvRiskiOut\|KadrySvodOut\|HrBranchOut" frontend/src/api/schema.d.ts
```
Expected: `grep` > 0.

`frontend/src/api/types.ts` — oxiriga qo'shing:
```ts
export type ZakKpisOut = Schemas['ZakKpisOut'];
export type ZakMonthOut = Schemas['ZakMonthOut'];
export type ZakMethodOut = Schemas['ZakMethodOut'];
export type ZakLotOut = Schemas['ZakLotOut'];
export type ZakNamedOut = Schemas['ZakNamedOut'];
export type ZakBranchOut = Schemas['ZakBranchOut'];
export type ZakSvodOut = Schemas['ZakSvodOut'];
export type ZakLotyOut = Schemas['ZakLotyOut'];
export type ZakPostavshikiOut = Schemas['ZakPostavshikiOut'];
export type ZakEkonomiyaOut = Schemas['ZakEkonomiyaOut'];
export type InvKpisOut = Schemas['InvKpisOut'];
export type InvObjectOut = Schemas['InvObjectOut'];
export type InvCumOut = Schemas['InvCumOut'];
export type InvSourceOut = Schemas['InvSourceOut'];
export type InvStageOut = Schemas['InvStageOut'];
export type InvObjectStagesOut = Schemas['InvObjectStagesOut'];
export type InvSvodOut = Schemas['InvSvodOut'];
export type InvObektyOut = Schemas['InvObektyOut'];
export type InvIstochnikiOut = Schemas['InvIstochnikiOut'];
export type InvRiskiOut = Schemas['InvRiskiOut'];
export type HrKpisOut = Schemas['HrKpisOut'];
export type HrMonthOut = Schemas['HrMonthOut'];
export type HrCategoryOut = Schemas['HrCategoryOut'];
export type HrBranchOut = Schemas['HrBranchOut'];
export type KadrySvodOut = Schemas['KadrySvodOut'];
export type KadryChislennostOut = Schemas['KadryChislennostOut'];
export type KadryFotOut = Schemas['KadryFotOut'];
export type KadryDvizhenieOut = Schemas['KadryDvizhenieOut'];
```

`frontend/src/dash/chart.tsx` — `Series` interfeysiga (S3 `dashed` dan keyin) qo'shing:
```ts
  /** O'ng o'qdagi chiziq (masalan, o'rtacha ish haqi ФОТ ustunlari ustida). */
  axis?: 'right';
```
va `barConfig` funksiyasini to'liq almashtiring (S1 va S3 o'zgarishlari saqlanadi):
```ts
export function barConfig({
  labels,
  series,
  stacked = false,
  format = formatMoney,
  rightFormat,
}: {
  labels: Array<string | string[]>;
  series: Series[];
  stacked?: boolean;
  format?: (value: number, digits: number) => string;
  rightFormat?: (value: number, digits: number) => string;
}): AnyChartConfig {
  const right = rightFormat ?? format;
  const hasRight = series.some((s) => s.axis === 'right');
  return {
    type: 'bar',
    data: {
      labels,
      datasets: series.map((s) =>
        s.type === 'line'
          ? { type: 'line' as const, label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color, borderWidth: s.dashed ? 2 : 3, borderDash: s.dashed ? [6, 5] : [], pointRadius: s.dashed ? 0 : 3, tension: 0.25, order: 0, yAxisID: s.axis === 'right' ? 'y1' : 'y' }
          : { type: 'bar' as const, label: s.label, data: s.data, backgroundColor: s.color, borderRadius: 3, maxBarThickness: 36, order: 1, yAxisID: 'y' },
      ),
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (item) => `${item.dataset.label ?? ''}: ${(item.dataset.yAxisID === 'y1' ? right : format)(item.parsed.y, 2)}` } },
      },
      scales: {
        x: { stacked, grid: { display: false } },
        y: { stacked, beginAtZero: true, ticks: { maxTicksLimit: 6, callback: (value) => format(Number(value), 0) } },
        ...(hasRight
          ? { y1: { position: 'right' as const, beginAtZero: true, grid: { display: false }, ticks: { maxTicksLimit: 6, callback: (value: string | number) => right(Number(value), 1) } } }
          : {}),
      },
    },
    plugins: [whiteBackground],
  };
}
```

- [ ] **Step 2: Formulalar va lug'at kalitlari**

`frontend/src/dash/formulas.ts` — `IndicatorKey` turining oxirgi qatoridagi (S3) `| 'stockValue' | 'turnover' | 'belowMin' | 'illiquid' | 'stockAge' | 'stockFlow';` ni quyidagiga almashtiring (S3 `turnover` — ombor oborot kunlari, kadrlar uchun `staffTurnover`):
```ts
  | 'stockValue' | 'turnover' | 'belowMin' | 'illiquid' | 'stockAge' | 'stockFlow'
  | 'contracted' | 'savings' | 'planExec' | 'lotsInWork' | 'lotsOverdue' | 'directShare' | 'avgProcDays'
  | 'program' | 'invYtd' | 'schedule' | 'finExec' | 'physExec' | 'finGap' | 'advances' | 'objStatus'
  | 'headcount' | 'vacancies' | 'payroll' | 'avgSalary' | 'staffTurnover' | 'overtime';
```

`frontend/src/i18n/ru.ts` — `} as const satisfies …` dan oldin qo'shing:
```ts
  'unit.peopleShort': 'чел.',
  'unit.dayShort': 'дн.',
  'unit.hourShort': 'ч',
  'unit.pp': 'п.п.',
  'formula.contracted': 'Заключено договоров — сумма договоров по лотам со статусом «договор заключён» за период',
  'formula.savings': 'Экономия = начальная цена − цена договора; доля = экономия / начальная цена',
  'formula.planExec': 'Исполнение годового плана = заключено с начала года / годовой план закупок',
  'formula.lotsInWork': 'Лоты в работе — количество лотов в статусах «объявлен» и «на оценке»',
  'formula.lotsOverdue': 'Просроченные лоты — лоты в работе, где дни процедуры превышают норматив способа более чем на 10',
  'formula.directShare': 'Доля прямых договоров = сумма прямых договоров / сумма всех договоров',
  'formula.avgProcDays': 'Средний срок закупки — среднее число дней от объявления до заключения договора',
  'formula.program': 'Программа года — сумма годовых лимитов объектов',
  'formula.invYtd': 'Освоено с начала года — факт финансирования с 1 января',
  'formula.schedule': 'Исполнение графика = факт / план на отчётную дату',
  'formula.finExec': 'Финансовое выполнение = (освоено ранее + освоено в году) / общая стоимость объекта',
  'formula.physExec': 'Физическое выполнение = объём выполненных работ по КС-2 / общий объём по смете',
  'formula.finGap': 'Разрыв = финансовое − физическое выполнение, в процентных пунктах',
  'formula.advances': 'Незакрытые авансы — остаток аванса и число дней с даты выдачи',
  'formula.objStatus': 'Статус объекта: по графику ≥ 90%, отстаёт 75–90%, под угрозой < 75%',
  'formula.headcount': 'Штатная и фактическая численность — по штатному расписанию и по кадровым документам',
  'formula.vacancies': 'Вакансии = штат − факт; доля = вакансии / штат',
  'formula.payroll': 'Фонд оплаты труда — выплаты по статье «Заработная плата и приравненные платежи»',
  'formula.avgSalary': 'Средняя зарплата = ФОТ / численность / число месяцев периода',
  'formula.staffTurnover': 'Текучесть = уволено за период / численность',
  'formula.overtime': 'Сверхурочные = часы сверх нормы / численность',
  'zak.kpi.contracted': 'Заключено договоров',
  'zak.kpi.contractedNote': '{count} договоров за период',
  'zak.kpi.plan': 'Исполнение годового плана',
  'zak.kpi.planNote': '{ytd} из {plan} с начала года',
  'zak.kpi.savings': 'Экономия',
  'zak.kpi.savingsNote': '{share} от начальной цены',
  'zak.kpi.inWork': 'Лоты в работе',
  'zak.kpi.inWorkNote': 'на {amount} начальной цены',
  'zak.kpi.overdue': 'Просроченные лоты',
  'zak.kpi.overdueNote': 'дольше нормативного срока на 10+ дней',
  'zak.kpi.overdueNone': 'все в пределах срока',
  'zak.kpi.direct': 'Прямые договоры',
  'zak.kpi.directNote': '{amount} от суммы договоров',
  'zak.months.title': 'Заключённые договоры по месяцам',
  'zak.months.sub': 'Сумма договоров по дате заключения',
  'zak.months.month': 'Месяц',
  'zak.months.value': 'Сумма договоров',
  'zak.methods.title': 'Способы закупки',
  'zak.methods.sub': 'Сумма заключённых договоров',
  'zak.methods.lots': 'лотов: {count}',
  'zak.lots.title': 'Лоты',
  'zak.lots.sub': 'Просроченные показаны первыми',
  'zak.lots.filter': 'Фильтр лотов',
  'zak.lots.all': 'Все',
  'zak.lots.work': 'В работе',
  'zak.lots.late': 'Просроченные',
  'zak.lots.done': 'Заключённые',
  'zak.lots.more': 'Все лоты',
  'zak.lots.none': 'Лотов с такими условиями нет.',
  'zak.lots.truncated': 'Показаны первые 1000 лотов — уточните период или филиал.',
  'zak.col.lot': 'Лот',
  'zak.col.subject': 'Предмет',
  'zak.col.branch': 'Филиал',
  'zak.col.method': 'Способ',
  'zak.col.start': 'Нач. цена',
  'zak.col.contract': 'Цена договора',
  'zak.col.status': 'Статус',
  'zak.col.days': 'Срок',
  'zak.col.daysOf': '{days} дн. из {norm}',
  'zak.col.daysDone': '{days} дн.',
  'zak.status.announced': 'Объявлен',
  'zak.status.evaluation': 'На оценке',
  'zak.status.done': 'Договор заключён',
  'zak.status.cancelled': 'Отменён',
  'zak.suppliers.title': 'Поставщики',
  'zak.suppliers.sub': 'Сумма договоров за период',
  'zak.suppliers.count': 'договоров: {count}',
  'zak.subjects.title': 'Предметы закупок',
  'zak.subjects.sub': 'Сумма договоров за период',
  'zak.branches.title': 'Закупки по филиалам',
  'zak.branches.sub': 'Нажмите на строку, чтобы выбрать филиал',
  'zak.branches.plan': 'Годовой план',
  'zak.branches.ytd': 'Заключено с начала года',
  'zak.branches.exec': 'Исполнение',
  'zak.branches.savings': 'Экономия',
  'zak.eco.title': 'Экономия по способам закупки',
  'zak.eco.sub': 'Разница между начальной ценой и ценой договора',
  'zak.eco.lots': 'Лотов',
  'zak.eco.contracts': 'Цена договоров',
  'zak.eco.share': 'Доля экономии',
  'zak.cancelled.title': 'Отменённые лоты',
  'zak.cancelled.sub': 'Лоты, снятые с процедуры в выбранном периоде',
  'zak.cancelled.none': 'Отменённых лотов нет.',
  'zak.days.title': 'Средний срок закупки',
  'zak.days.sub': 'От объявления до заключения договора',
  'zak.days.avg': 'в среднем по заключённым договорам',
  'zak.days.norm': 'норматив {norm} дн.',
  'inv.kpi.program': 'Программа {year}',
  'inv.kpi.programNote': 'объектов: {count}, общая стоимость {cost}',
  'inv.kpi.ytd': 'Освоено с начала года',
  'inv.kpi.ytdNote': '{pct} годовой программы',
  'inv.kpi.schedule': 'Исполнение графика',
  'inv.kpi.scheduleNote': 'план на {date} — {amount}',
  'inv.kpi.period': 'Освоено за период',
  'inv.kpi.lagging': 'Объекты с отставанием',
  'inv.kpi.laggingNote': 'из них под угрозой {count}',
  'inv.kpi.laggingNone': 'все по графику',
  'inv.kpi.commissioning': 'Ввод в {year} году',
  'inv.kpi.commissioningNote': 'объектов по плану ввода',
  'inv.cum.title': 'Освоение нарастающим итогом',
  'inv.cum.sub': 'План и факт финансирования с начала года',
  'inv.cum.plan': 'План',
  'inv.cum.fact': 'Факт',
  'inv.cum.month': 'Месяц',
  'inv.src.title': 'Источники финансирования',
  'inv.src.sub': 'Годовой лимит и освоение с начала года',
  'inv.src.done': 'освоено {amount}',
  'inv.src.limit': 'лимит {amount}',
  'inv.obj.title': 'Объекты программы',
  'inv.obj.titleAll': 'Реестр объектов',
  'inv.obj.sub': 'Нажмите на строку, чтобы выбрать филиал',
  'inv.obj.subAll': 'Финансовое исполнение показано полосой, метка на полосе — физическое выполнение',
  'inv.obj.more': 'Все объекты',
  'inv.col.object': 'Объект',
  'inv.col.branch': 'Филиал',
  'inv.col.cost': 'Общая стоимость',
  'inv.col.plan': 'План года',
  'inv.col.fact': 'Освоено',
  'inv.col.schedule': 'Исполнение графика',
  'inv.col.finphys': 'Финансовое / физическое',
  'inv.col.deadline': 'Срок',
  'inv.col.phys': 'физ. {pct}',
  'inv.status.ok': 'по графику',
  'inv.status.lag': 'отстаёт',
  'inv.status.risk': 'под угрозой',
  'inv.work.new': 'Новое строительство',
  'inv.work.reconstruction': 'Реконструкция',
  'inv.work.modernization': 'Модернизация',
  'inv.rank.title': 'Освоение по объектам',
  'inv.rank.sub': 'С начала года, черта — годовой план',
  'inv.rank.note': '{pct} годового плана',
  'inv.risk.lagTitle': 'Объекты с отставанием',
  'inv.risk.lagSub': 'Исполнение графика финансирования ниже 90%',
  'inv.risk.lagNote': '{pct} графика',
  'inv.risk.lagNone': 'Все объекты идут по графику.',
  'inv.risk.gapTitle': 'Разрыв финансирования и физического выполнения',
  'inv.risk.gapSub': 'Разница больше 20 процентных пунктов — риск неосвоенных авансов',
  'inv.risk.gapNote': 'фин. {fin}, физ. {phys}',
  'inv.risk.gapNone': 'Существенных разрывов нет.',
  'inv.risk.stageTitle': 'Этапы и сроки',
  'inv.risk.stageSub': 'Пройденные этапы и отклонения по срокам',
  'inv.risk.stageDone': '{done} из {total} этапов',
  'inv.risk.stageLate': 'этапов с отставанием: {count}',
  'inv.risk.stageOk': 'без отставаний',
  'inv.risk.stageAll': 'Все этапы пройдены',
  'inv.risk.stageTip': '{name}: {date}',
  'inv.risk.stageTipOpen': '{name}: не выполнен',
  'inv.risk.stageNone': 'Этапы объектов не загружены.',
  'inv.risk.advTitle': 'Незакрытые авансы',
  'inv.risk.advSub': 'Авансы старше 90 дней',
  'inv.risk.advNone': 'Незакрытых авансов старше 90 дней нет.',
  'inv.risk.advAmount': 'Сумма',
  'inv.risk.advDays': 'Срок',
  'inv.none.title': 'Нет объектов',
  'inv.none.text': 'У выбранного филиала нет объектов адресной программы.',
  'kad.kpi.plan': 'Штатная численность',
  'kad.kpi.planNote': 'по штатному расписанию',
  'kad.kpi.fact': 'Фактическая численность',
  'kad.kpi.factNote': 'укомплектованность {pct}',
  'kad.kpi.vacancies': 'Вакансии',
  'kad.kpi.vacanciesNote': '{pct} штата не занято',
  'kad.kpi.payroll': 'Фонд оплаты труда',
  'kad.kpi.payrollNote': 'за период, {pct} расходования',
  'kad.kpi.avg': 'Средняя зарплата',
  'kad.kpi.avgNote': 'в месяц, с налогами и отчислениями',
  'kad.kpi.avgUnit': 'млн сум',
  'kad.kpi.turnover': 'Текучесть кадров',
  'kad.kpi.turnoverNote': 'принято {hired}, уволено {fired} за период',
  'kad.kpi.noStaff': 'штат не загружен',
  'kad.fot.title': 'Фонд оплаты труда по месяцам',
  'kad.fot.sub': 'Выплаты и средняя зарплата на одного работника',
  'kad.fot.payroll': 'Фонд оплаты труда',
  'kad.fot.avg': 'Средняя зарплата, млн сум',
  'kad.fot.avgRight': 'Средняя зарплата, правая шкала',
  'kad.fot.month': 'Месяц',
  'kad.cat.title': 'Структура персонала',
  'kad.cat.sub': 'Категории работников, фактическая численность',
  'kad.cat.share': '{pct} персонала',
  'kad.br.title': 'Численность по филиалам',
  'kad.br.sub': 'Нажмите на строку, чтобы выбрать филиал',
  'kad.br.branch': 'Филиал',
  'kad.br.plan': 'Штат',
  'kad.br.fact': 'Факт',
  'kad.br.vac': 'Вакансии',
  'kad.br.fill': 'Укомплектованность',
  'kad.br.payroll': 'ФОТ за период',
  'kad.br.avg': 'Средняя зарплата',
  'kad.br.total': 'Итого',
  'kad.vac.title': 'Вакансии по филиалам',
  'kad.vac.sub': 'Незанятые штатные единицы',
  'kad.vac.note': '{pct} штата',
  'kad.share.title': 'Доля ФОТ в расходовании',
  'kad.share.sub': 'За выбранный период',
  'kad.share.of': '{payroll} из {total}',
  'kad.avg.title': 'Средняя зарплата по филиалам',
  'kad.avg.sub': 'Млн сум в месяц, с налогами и отчислениями',
  'kad.pay.title': 'ФОТ по филиалам',
  'kad.pay.sub': 'Выплаты за период',
  'kad.mov.title': 'Приём и увольнение по месяцам',
  'kad.mov.sub': 'Количество работников',
  'kad.mov.hired': 'Принято',
  'kad.mov.fired': 'Уволено',
  'kad.ot.title': 'Сверхурочные часы',
  'kad.ot.sub': 'За период',
  'kad.ot.per': '{hours} ч на работника',
  'kad.ot.perBranch': '{hours} ч на чел.',
  'kad.turn.title': 'Текучесть по филиалам',
  'kad.turn.sub': 'Уволено за период к фактической численности',
  'kad.turn.hired': 'Принято',
  'kad.turn.fired': 'Уволено',
  'kad.turn.rate': 'Текучесть',
  'kad.turn.fact': 'Факт. численность',
  'kad.none.source': 'кадровые данные (HR API или файл численности)',
  'kad.money.mln': '{value} млн',
```

- [ ] **Step 3: Test fixture'lari**

`frontend/src/test/s4Fixtures.ts`:
```ts
import type {
  HrBranchOut,
  HrCategoryOut,
  HrKpisOut,
  HrMonthOut,
  InvCumOut,
  InvKpisOut,
  InvObjectOut,
  InvObjectStagesOut,
  InvSourceOut,
  KadryChislennostOut,
  KadryDvizhenieOut,
  KadryFotOut,
  KadrySvodOut,
  ReportPeriodOut,
  InvIstochnikiOut,
  InvObektyOut,
  InvRiskiOut,
  InvSvodOut,
  ZakEkonomiyaOut,
  ZakKpisOut,
  ZakLotOut,
  ZakLotyOut,
  ZakMethodOut,
  ZakMonthOut,
  ZakPostavshikiOut,
  ZakSvodOut,
} from '../api/types';

export const PERIOD_M08_S4: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

export const ZAK_KPIS: ZakKpisOut = {
  has_data: true, contracted: 140, contracts: 2, start_contracted: 150, savings: 10, savings_share: 0.066667, ytd: 197, plan: 1000,
  plan_execution: 0.197, in_work: 2, in_work_start: 110, overdue: 1, overdue_start: 80, direct: 50, direct_share: 0.357143,
  avg_days: 8.5, cancelled: 1, cancelled_start: 40,
};
export const ZAK_MONTHS: ZakMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, contracted: i === 7 ? 140 : 20 + i }));
export const ZAK_METHODS: ZakMethodOut[] = [
  { method: 'eshop', title: 'Электронный магазин', lots: 1, start: 100, contracted: 90, savings: 10, savings_share: 0.1, avg_days: 12, norm_days: 15 },
  { method: 'direct', title: 'Прямой договор', lots: 1, start: 50, contracted: 50, savings: 0, savings_share: 0, avg_days: 5, norm_days: 12 },
];

function lot(no: string, kind: 'work' | 'done' | 'cancelled', extra: Partial<ZakLotOut>): ZakLotOut {
  const status = kind === 'done' ? 'договор заключён' : kind === 'cancelled' ? 'отменён' : 'объявлен';
  return {
    lot_no: no, branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', date: '2026-08-10', method: 'eshop', method_title: 'Электронный магазин',
    subject: 'Запасные части', status, kind, start_price: 100, contract_price: kind === 'done' ? 90 : null, days: 12, norm_days: 15,
    overdue: false, supplier: kind === 'done' ? 'ООО «Гидромонтаж Сервис»' : null, ...extra,
  };
}

export const LOTS: ZakLotOut[] = [
  lot('2026-0102', 'work', { method: 'contest', method_title: 'Электронный конкурс', start_price: 80, days: 85, norm_days: 40, overdue: true, date: '2026-07-01' }),
  lot('2026-0101', 'done', {}),
  lot('2026-0103', 'done', { method: 'direct', method_title: 'Прямой договор', start_price: 50, contract_price: 50, days: 5, norm_days: 12, branch_id: 2, branch_name: 'Чарвакская ГЭС' }),
  lot('2026-0104', 'work', { status: 'на оценке', start_price: 30, days: 14 }),
  lot('2026-0105', 'cancelled', { method: 'exchange', method_title: 'Биржевые торги', start_price: 40, days: null, norm_days: 20 }),
];

export const ZAK_SVOD: ZakSvodOut = { period: PERIOD_M08_S4, kpis: ZAK_KPIS, months: ZAK_MONTHS, methods: ZAK_METHODS, lots: LOTS };
export const ZAK_LOTY: ZakLotyOut = { period: PERIOD_M08_S4, kpis: ZAK_KPIS, lots: LOTS, truncated: false };
export const ZAK_POSTAVSHIKI: ZakPostavshikiOut = {
  period: PERIOD_M08_S4, kpis: ZAK_KPIS,
  suppliers: [{ name: 'ООО «Гидромонтаж Сервис»', amount: 90, count: 1 }, { name: 'ООО «Энерго Проект»', amount: 50, count: 1 }],
  subjects: [{ name: 'Запасные части', amount: 90, count: 1 }, { name: 'Ремонтные услуги', amount: 50, count: 1 }],
  branches: [
    { branch_id: 3, name: 'Каскад Чирчикских ГЭС', plan: 1000, ytd: 197, execution: 0.197, savings: 10 },
    { branch_id: 2, name: 'Чарвакская ГЭС', plan: 500, ytd: 400, execution: 0.8, savings: 25 },
  ],
};
export const ZAK_EKONOMIYA: ZakEkonomiyaOut = { period: PERIOD_M08_S4, kpis: ZAK_KPIS, methods: ZAK_METHODS, cancelled: [LOTS[4]].filter((x): x is ZakLotOut => x !== undefined) };

export const INV_KPIS: InvKpisOut = {
  has_objects: true, objects: 2, total_cost: 1500, program: 440, plan_to_date: 220, fact_ytd: 180, execution: 0.818182, fact_period: 130,
  lagging: 1, threatened: 0, commissioning: 1, year: 2026,
};

function obj(id: number, code: string, name: string, extra: Partial<InvObjectOut>): InvObjectOut {
  return {
    object_id: id, object_code: code, name, program_code: 'АИП-2026-01', work_type: 'modernization', source_name: 'Бюджетные средства',
    commissioning_year: 2026, total_cost: 1000, branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', plan_year: 240, plan_to_date: 120,
    fact_ytd: 90, fact_period: 40, execution: 0.75, status: 'lag', financial: 0.49, physical: 0.4, gap_pp: 9, advance: 30, advance_days: 91, ...extra,
  };
}

export const INV_OBJECTS: InvObjectOut[] = [
  obj(11, 'OBJ-01', 'Модернизация гидроагрегатов', {}),
  obj(12, 'OBJ-02', 'Реконструкция водоприёмника', {
    work_type: 'reconstruction', source_name: 'Кредиты МФИ', commissioning_year: 2027, total_cost: 500, plan_year: 200, plan_to_date: 100,
    fact_ytd: 90, fact_period: 90, execution: 0.9, status: 'ok', financial: 0.38, physical: 0.05, gap_pp: 33, advance: 20, advance_days: 113,
  }),
];
export const INV_CUM: InvCumOut[] = Array.from({ length: 12 }, (_, i) => ({ month_id: 202601 + i, plan: [0, 0, 0, 0, 0, 0, 60, 220, 380, 440, 440, 440][i] ?? 0, fact: i < 9 ? [0, 0, 0, 0, 0, 0, 50, 180, 230][i] ?? 0 : null }));
export const INV_SOURCES: InvSourceOut[] = [
  { name: 'Бюджетные средства', plan_year: 240, fact_ytd: 90, share: 0.375 },
  { name: 'Кредиты МФИ', plan_year: 200, fact_ytd: 90, share: 0.45 },
];
export const INV_STAGES: InvObjectStagesOut[] = [{
  object_id: 11, name: 'Модернизация гидроагрегатов', branch_id: 3, late: 2,
  stages: [
    { stage_no: 1, name: 'Проектно-сметная документация', plan_date: '2026-03-15', fact_date: '2026-03-10', done: true, late: false },
    { stage_no: 2, name: 'Тендер и договор', plan_date: '2026-06-15', fact_date: '2026-07-20', done: true, late: true },
    { stage_no: 3, name: 'Строительно-монтажные работы', plan_date: '2026-09-15', fact_date: null, done: false, late: true },
    { stage_no: 4, name: 'Ввод в эксплуатацию', plan_date: '2026-12-15', fact_date: null, done: false, late: false },
  ],
}];
export const INV_SVOD: InvSvodOut = { period: PERIOD_M08_S4, kpis: INV_KPIS, cumulative: INV_CUM, sources: INV_SOURCES, objects: INV_OBJECTS };
export const INV_OBEKTY: InvObektyOut = { period: PERIOD_M08_S4, kpis: INV_KPIS, objects: INV_OBJECTS };
export const INV_ISTOCHNIKI: InvIstochnikiOut = { period: PERIOD_M08_S4, kpis: INV_KPIS, sources: INV_SOURCES, objects: INV_OBJECTS, cumulative: INV_CUM };
export const INV_RISKI: InvRiskiOut = {
  period: PERIOD_M08_S4, kpis: INV_KPIS, lagging: INV_OBJECTS.slice(0, 1), gaps: INV_OBJECTS.slice(1), stages: INV_STAGES, advances: INV_OBJECTS,
};
const NO_OBJECTS: InvKpisOut = { ...INV_KPIS, has_objects: false, objects: 0, program: 0, plan_to_date: 0, fact_ytd: 0, execution: null, fact_period: 0, lagging: 0, commissioning: 0, total_cost: 0 };
export const INV_NONE: InvSvodOut = { period: PERIOD_M08_S4, kpis: NO_OBJECTS, cumulative: INV_CUM.map((p) => ({ ...p, plan: 0, fact: p.fact === null ? null : 0 })), sources: [], objects: [] };

export const HR_KPIS: HrKpisOut = {
  has_data: true, snap_month: 202608, plan: 100, fact: 90, vacancies: 10, vacancy_share: 0.1, fill: 0.9, payroll: 180, outflow: 600,
  payroll_share: 0.3, avg_salary: 2, hired: 3, fired: 3, turnover: 0.033333, overtime: 420, overtime_per_employee: 4.666667,
};
export const HR_MONTHS: HrMonthOut[] = Array.from({ length: 9 }, (_, i) => ({
  month_id: 202601 + i, payroll: 160 + i * 3, fact: 90, avg_salary: (160 + i * 3) / 90, hired: i % 3, fired: (i + 1) % 3, overtime: 300 + i * 10,
}));
export const HR_CATEGORIES: HrCategoryOut[] = [{ name: 'Оперативный персонал', value: 81 }, { name: 'Руководители', value: 9 }];
export const HR_BRANCHES: HrBranchOut[] = [
  { branch_id: 3, name: 'Каскад Чирчикских ГЭС', plan: 100, fact: 90, vacancies: 10, fill: 0.9, payroll: 180, avg_salary: 2, hired: 3, fired: 3, turnover: 0.033333, overtime: 420, overtime_per_employee: 4.666667 },
  { branch_id: 2, name: 'Чарвакская ГЭС', plan: 150, fact: 120, vacancies: 30, fill: 0.8, payroll: 250, avg_salary: 2.083333, hired: 1, fired: 12, turnover: 0.1, overtime: 3000, overtime_per_employee: 25 },
];
export const KADRY_SVOD: KadrySvodOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, months: HR_MONTHS, categories: HR_CATEGORIES, branches: HR_BRANCHES };
export const KADRY_CHISL: KadryChislennostOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, branches: HR_BRANCHES, categories: HR_CATEGORIES };
export const KADRY_FOT: KadryFotOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, months: HR_MONTHS, branches: HR_BRANCHES };
export const KADRY_DVIZH: KadryDvizhenieOut = { period: PERIOD_M08_S4, kpis: HR_KPIS, months: HR_MONTHS, branches: [...HR_BRANCHES].reverse() };
const NO_STAFF: HrKpisOut = {
  ...HR_KPIS, has_data: false, snap_month: null, plan: 0, fact: 0, vacancies: null, vacancy_share: null, fill: null, avg_salary: null,
  turnover: null, overtime_per_employee: null,
};
export const KADRY_EMPTY: KadrySvodOut = { period: PERIOD_M08_S4, kpis: NO_STAFF, months: HR_MONTHS, categories: [], branches: [] };
```

- [ ] **Step 4: Testni yozish**

`frontend/src/dash/people.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { t } from '../i18n';
import { formatNumber } from '../i18n/format';
import { formatDays, formatHours, formatPeople, formatPp } from './people';

describe('people, days, hours formats', () => {
  it('formats counts with units and handles missing values', () => {
    expect(formatPeople(1250)).toBe(`${formatNumber(1250)} чел.`);
    expect(formatDays(85)).toBe('85 дн.');
    expect(formatHours(420)).toBe('420 ч');
    expect(formatHours(4.666667, 1)).toBe('4,7 ч');
    expect(formatPp(33)).toBe('33 п.п.');
    expect(formatPeople(null)).toBe(t('dash.noValue'));
    expect(formatDays(undefined)).toBe(t('dash.noValue'));
  });
});
```

`frontend/src/dash/chart.s4.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { barConfig } from './chart';

describe('barConfig right axis', () => {
  it('puts series marked axis right on y1 and adds the axis only when needed', () => {
    const cfg = barConfig({
      labels: ['Янв'],
      series: [{ label: 'ФОТ', data: [180], color: '#1d6df2' }, { label: 'Средняя', data: [2], color: '#0b4fa8', type: 'line', axis: 'right' }],
      rightFormat: (v) => `${v} млн`,
    });
    expect(cfg.options?.scales?.y1).toBeDefined();
    expect((cfg.data.datasets[1] as { yAxisID?: string }).yAxisID).toBe('y1');
    expect((cfg.data.datasets[0] as { yAxisID?: string }).yAxisID).toBe('y');
    const plain = barConfig({ labels: ['Янв'], series: [{ label: 'ФОТ', data: [180], color: '#1d6df2' }] });
    expect(plain.options?.scales?.y1).toBeUndefined();
  });
});
```

- [ ] **Step 5: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/dash/people.test.ts src/dash/chart.s4.test.ts`
Expected: FAIL — `Failed to resolve import "./people"`; `axis` xossasi `Series` da yo'q (tsc/vitest).

- [ ] **Step 6: Implementatsiya — formatlar va uslublar**

`frontend/src/dash/people.ts`:
```ts
import { t } from '../i18n';
import { formatNumber } from '../i18n/format';

function unit(value: number | null | undefined, digits: number, key: 'unit.peopleShort' | 'unit.dayShort' | 'unit.hourShort' | 'unit.pp'): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return t('dash.noValue');
  return `${formatNumber(value, digits)} ${t(key)}`;
}

/** Odamlar soni (S4 «Кадры»): «1 250 чел.». */
export function formatPeople(value: number | null | undefined): string {
  return unit(value, 0, 'unit.peopleShort');
}

/** Kunlar (xarid muddati, avans yoshi): «85 дн.». */
export function formatDays(value: number | null | undefined): string {
  return unit(value, 0, 'unit.dayShort');
}

/** Soatlar (ish vaqtidan tashqari): «420 ч». */
export function formatHours(value: number | null | undefined, digits = 0): string {
  return unit(value, digits, 'unit.hourShort');
}

/** Foiz punktlari (moliyaviy/jismoniy uzilish): «33 п.п.». */
export function formatPp(value: number | null | undefined): string {
  return unit(value, 0, 'unit.pp');
}
```

`frontend/src/dash/s4.css`:
```css
/* S4: АИП obyekti — moliyaviy bajarilish polosasi va jismoniy bajarilish belgisi (prototip objTable). */
.fp { width: 13rem; max-width: 100%; }
.fp__h { display: flex; justify-content: space-between; gap: 0.8rem; font-size: 0.9rem; margin-bottom: 0.2rem; }
.fp__t { position: relative; height: 0.55rem; border-radius: 0.3rem; background: #e9f1fb; }
.fp__t i { display: block; height: 100%; border-radius: 0.3rem; background: linear-gradient(90deg, #2f8ef5, #1d6df2); }
.fp__t u { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--ink); }
/* Bosqichlar lentasi (prototip stageCard). */
.stg { display: flex; gap: 3px; margin: 0.45rem 0 0.25rem; }
.stg span { flex: 1; height: 0.55rem; border-radius: 0.2rem; background: var(--soft); }
.stg span.is-done { background: var(--brand2); }
.stg span.is-late { background: var(--neg); }
.obj-note { display: block; color: var(--muted); font-size: 0.85rem; }
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/dash src/sections` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: yangi 2 test passed, S1–S3 grafik va sahifa testlari o'zgarishsiz passed; tsc (fixture'lar OpenAPI tiplariga mos) va eslint xatosiz.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): S4 tiplari, fixture'lar, matnlar va formulalar, odam/kun/soat formatlari, grafik o'ng o'qi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 19: Frontend — «Закупки»: Сводка, Лоты, Договоры и поставщики, Экономия

**Files:**
- Create: `frontend/src/sections/zakupki/parts/ZakKpis.tsx`, `parts/ZakMonthsCard.tsx`, `parts/MethodsCard.tsx`, `parts/LotsTable.tsx`, `parts/NamedRankCard.tsx`, `parts/ZakBranchesTable.tsx`, `parts/EconomyCards.tsx`, `frontend/src/sections/zakupki/svod.tsx`, `loty.tsx`, `postavshiki.tsx`, `ekonomiya.tsx`
- Test: `frontend/src/sections/zakupki/zakupki.test.tsx`

**Interfaces:**
- Consumes: `useSection`, `SectionData`, `SectionPageProps`, `toggleBranch`, `buildHash`, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Column`, `Badge`, `BadgeTone`, `cx`, `Rank`, `ChartCanvas`, `barConfig`, `COLORS`, `ChartHandle`, `CardExport`, `ExportContext`, `NoData`, `formula`, `formatMoney`, `formatPct`, `moneyParts`, `monthShort`, `formatNumber`, `formatDate`, `formatDays`, fixture'lar (`ZAK_*`, `LOTS`), `mockApi`, `json`, `renderWithProviders`, `expectNoAxeViolations`, `ME_ADMIN`.
- Produces:
  - Kartalar: `ZakKpis({ kpis })`, `ZakMonthsCard({ months, ctx, className? })`, `MethodsCard({ methods, className? })`, `LotsTable({ lots, ctx, filters, limit?, truncated?, className? })` (segment filtri `all | work | late | done`, kechikkan — `badge--neg`), `NamedRankCard({ title, sub, rows, className? })`, `ZakBranchesTable({ rows, ctx, filters, onBranch, className? })`, `EconomyTable({ methods, ctx, className? })`, `CancelledCard({ lots, className? })`, `AvgDaysCard({ kpis, methods, className? })`; `lotStatusLabel(status) -> string`.
  - Sahifalar `#zakupki/svod`, `#zakupki/loty`, `#zakupki/postavshiki`, `#zakupki/ekonomiya` (3-reja reyestri glob orqali ulaydi).

- [ ] **Step 1: Testlarni yozish**

`frontend/src/sections/zakupki/zakupki.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { ZAK_EKONOMIYA, ZAK_LOTY, ZAK_POSTAVSHIKI, ZAK_SVOD } from '../../test/s4Fixtures';
import ZakupkiEkonomiya from './ekonomiya';
import ZakupkiLoty from './loty';
import ZakupkiPostavshiki from './postavshiki';
import ZakupkiSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Закупки', () => {
  it('Сводка: KPIs, months chart, methods and top lots with the overdue first', async () => {
    mockApi({ 'GET /zakupki/svod': json(ZAK_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<ZakupkiSvod section="zakupki" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Заключено договоров')).toBeInTheDocument();
    expect(screen.getByText('19,7%')).toHaveClass('neg');
    expect(screen.getByText('35,7%')).toHaveClass('neg');
    expect(screen.getByRole('img', { name: 'Заключённые договоры по месяцам' })).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Способы закупки' })).getAllByRole('listitem')).toHaveLength(2);
    const table = screen.getByRole('table', { name: 'Лоты' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    expect(within(table).getByText('85 дн. из 40')).toHaveClass('badge--neg');
    expect(screen.getByRole('link', { name: 'Все лоты' }).getAttribute('href')).toContain('zakupki/loty');
    await expectNoAxeViolations(container);
  });

  it('Лоты: segment filter by work, overdue and concluded', async () => {
    mockApi({ 'GET /zakupki/loty': json(ZAK_LOTY), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ZakupkiLoty section="zakupki" page="loty" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Лоты' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    await user.click(screen.getByRole('button', { name: 'Просроченные' }));
    expect(screen.getByRole('button', { name: 'Просроченные' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(screen.getByRole('table', { name: 'Лоты' })).getAllByRole('row')).toHaveLength(1 + 1);
    await user.click(screen.getByRole('button', { name: 'В работе' }));
    expect(within(screen.getByRole('table', { name: 'Лоты' })).getAllByRole('row')).toHaveLength(1 + 2);
    await user.click(screen.getByRole('button', { name: 'Заключённые' }));
    const done = screen.getByRole('table', { name: 'Лоты' });
    expect(within(done).getAllByRole('row')).toHaveLength(1 + 2);
    expect(within(done).getAllByText('Договор заключён')).toHaveLength(2);
    expect(screen.queryByRole('link', { name: 'Все лоты' })).toBeNull();
  });

  it('Договоры и поставщики: suppliers, subjects and branch table selects a branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /zakupki/postavshiki': json(ZAK_POSTAVSHIKI), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ZakupkiPostavshiki section="zakupki" page="postavshiki" filters={filters} onBranch={onBranch} />);
    const suppliers = await screen.findByRole('list', { name: 'Поставщики' });
    expect(within(suppliers).getAllByRole('listitem')[0]).toHaveTextContent('ООО «Гидромонтаж Сервис»');
    expect(screen.getByRole('list', { name: 'Предметы закупок' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Закупки по филиалам' });
    await user.click(within(table).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
  });

  it('Экономия: savings by method, cancelled lots and average duration', async () => {
    mockApi({ 'GET /zakupki/ekonomiya': json(ZAK_EKONOMIYA), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ZakupkiEkonomiya section="zakupki" page="ekonomiya" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Экономия по способам закупки' });
    expect(within(table).getByText('Электронный магазин')).toBeInTheDocument();
    expect(within(table).getByText('10,0%')).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: 'Отменённые лоты' })).getByText('2026-0105')).toBeInTheDocument();
    expect(screen.getByText('8,5 дн.')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Средний срок закупки' })).getAllByRole('listitem')).toHaveLength(2);
  });
});
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/zakupki`
Expected: FAIL — `Failed to resolve import "./ekonomiya"`.

- [ ] **Step 3: Implementatsiya — KPI, grafik, usullar**

`frontend/src/sections/zakupki/parts/ZakKpis.tsx`:
```tsx
import type { ZakKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const PLAN_LOW = 0.6; // TZ 4 qoidasi «План закупок освоено < 60%»
const DIRECT_HIGH = 0.25; // TZ 4 qoidasi «Доля прямых договоров > 25%»

/** Prototip `kpisZak`: договоры, план, экономия, лоты в работе, просроченные, прямые договоры. */
export function ZakKpis({ kpis }: { kpis: ZakKpisOut }) {
  const contracted = moneyParts(kpis.contracted);
  const savings = moneyParts(kpis.savings);
  return (
    <KpiGrid>
      <KpiTile icon="cart" label={t('zak.kpi.contracted')} value={contracted.value} unit={contracted.unit} delta={t('zak.kpi.contractedNote', { count: kpis.contracts })} hint={formula('contracted')} />
      <KpiTile
        icon="pct"
        label={t('zak.kpi.plan')}
        value={<span className={kpis.plan_execution !== null && kpis.plan_execution < PLAN_LOW ? 'neg' : undefined}>{formatPct(kpis.plan_execution, 1)}</span>}
        delta={t('zak.kpi.planNote', { ytd: formatMoney(kpis.ytd), plan: formatMoney(kpis.plan) })}
        hint={formula('planExec')}
      />
      <KpiTile icon="coins" label={t('zak.kpi.savings')} value={savings.value} unit={savings.unit} delta={t('zak.kpi.savingsNote', { share: formatPct(kpis.savings_share, 1) })} hint={formula('savings')} />
      <KpiTile icon="clock" label={t('zak.kpi.inWork')} value={formatNumber(kpis.in_work)} delta={t('zak.kpi.inWorkNote', { amount: formatMoney(kpis.in_work_start) })} hint={formula('lotsInWork')} />
      <KpiTile
        icon="alert"
        label={t('zak.kpi.overdue')}
        value={<span className={kpis.overdue > 0 ? 'neg' : undefined}>{formatNumber(kpis.overdue)}</span>}
        delta={kpis.overdue > 0 ? t('zak.kpi.overdueNote') : t('zak.kpi.overdueNone')}
        hint={formula('lotsOverdue')}
      />
      <KpiTile
        icon="doc"
        label={t('zak.kpi.direct')}
        value={<span className={kpis.direct_share !== null && kpis.direct_share > DIRECT_HIGH ? 'neg' : undefined}>{formatPct(kpis.direct_share, 1)}</span>}
        delta={t('zak.kpi.directNote', { amount: formatMoney(kpis.direct) })}
        hint={formula('directShare')}
      />
    </KpiGrid>
  );
}
```

`frontend/src/sections/zakupki/parts/ZakMonthsCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { ZakMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `zakMonthly`: сумма договоров по дате заключения. */
export function ZakMonthsCard({ months, ctx, className }: { months: ZakMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('zak.months.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const color = COLORS.in();
  const config = useMemo(
    () => barConfig({ labels: months.map((m) => monthShort(m.month_id)), series: [{ label: t('zak.months.value'), data: months.map((m) => m.contracted), color }] }),
    [months, color],
  );
  const table = { headers: [t('zak.months.month'), t('zak.months.value')], rows: months.map((m) => [monthShort(m.month_id), m.contracted]) };
  return (
    <Card className={className} title={title} sub={t('zak.months.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
```

`frontend/src/sections/zakupki/parts/MethodsCard.tsx`:
```tsx
import type { ZakMethodOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip «Способы закупки»: сумма заключённых договоров по способам. */
export function MethodsCard({ methods, className }: { methods: ZakMethodOut[]; className?: string }) {
  const title = t('zak.methods.title');
  return (
    <Card className={className} title={title} sub={t('zak.methods.sub')}>
      <div title={formula('contracted')}>
        <Rank label={title} items={methods.filter((m) => m.contracted > 0).map((m) => ({ id: m.method, name: m.title, value: m.contracted, note: t('zak.methods.lots', { count: m.lots }) }))} />
      </div>
    </Card>
  );
}
```

`frontend/src/sections/zakupki/parts/NamedRankCard.tsx`:
```tsx
import type { ZakNamedOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip «Поставщики» / «Предметы закупок»: сумма договоров за период. */
export function NamedRankCard({ title, sub, rows, className }: { title: string; sub: string; rows: ZakNamedOut[]; className?: string }) {
  return (
    <Card className={className} title={title} sub={sub}>
      {rows.length ? (
        <Rank label={title} items={rows.map((r) => ({ id: r.name, name: r.name, value: r.amount, note: t('zak.suppliers.count', { count: r.count }) }))} />
      ) : (
        <NoData kind="period" />
      )}
    </Card>
  );
}
```

- [ ] **Step 4: Implementatsiya — lotlar jadvali (segment filtri)**

`frontend/src/sections/zakupki/parts/LotsTable.tsx`:
```tsx
import { useState } from 'react';
import type { ZakLotOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t, type MessageKey } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import type { FilterState } from '../../../shell/useFilters';
import { Badge, type BadgeTone } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

type LotFilter = 'all' | 'work' | 'late' | 'done';
const FILTERS: LotFilter[] = ['all', 'work', 'late', 'done'];
const STATUS_KEYS: Record<string, MessageKey> = {
  'объявлен': 'zak.status.announced',
  'на оценке': 'zak.status.evaluation',
  'договор заключён': 'zak.status.done',
  'отменён': 'zak.status.cancelled',
};
const STATUS_TONE: Record<string, BadgeTone> = { work: 'blue', done: 'ok', cancelled: 'neutral' };

export function lotStatusLabel(status: string): string {
  const key = STATUS_KEYS[status];
  return key ? t(key) : status;
}

function matches(lot: ZakLotOut, filter: LotFilter): boolean {
  if (filter === 'work') return lot.kind === 'work';
  if (filter === 'late') return lot.overdue;
  if (filter === 'done') return lot.kind === 'done';
  return true;
}

function Days({ lot }: { lot: ZakLotOut }) {
  if (lot.days === null) return <>—</>;
  if (lot.kind === 'work') {
    return <Badge tone={lot.overdue ? 'neg' : 'neutral'}>{t('zak.col.daysOf', { days: lot.days, norm: lot.norm_days ?? '—' })}</Badge>;
  }
  return <Badge>{t('zak.col.daysDone', { days: lot.days })}</Badge>;
}

export interface LotsTableProps {
  lots: ZakLotOut[];
  ctx: ExportContext;
  filters: FilterState;
  limit?: number;
  truncated?: boolean;
  className?: string;
}

/** Prototip `lotTable`: реестр лотов с фильтром «все, в работе, просроченные, заключённые». */
export function LotsTable({ lots, ctx, filters, limit, truncated, className }: LotsTableProps) {
  const [filter, setFilter] = useState<LotFilter>('all');
  const title = t('zak.lots.title');
  const shown = lots.filter((l) => matches(l, filter)).slice(0, limit ?? lots.length);
  const headers = [t('zak.col.lot'), t('zak.col.subject'), t('zak.col.branch'), t('zak.col.method'), t('zak.col.start'), t('zak.col.contract'), t('zak.col.status'), t('zak.col.days')];
  const columns: Column<ZakLotOut>[] = [
    { key: 'lot', header: headers[0] ?? '', cell: (l) => l.lot_no, sortValue: (l) => l.lot_no },
    { key: 'subject', header: headers[1] ?? '', cell: (l) => l.subject, sortValue: (l) => l.subject, wrap: true },
    { key: 'branch', header: headers[2] ?? '', cell: (l) => l.branch_name, sortValue: (l) => l.branch_name, wrap: true },
    { key: 'method', header: headers[3] ?? '', cell: (l) => l.method_title, sortValue: (l) => l.method_title, wrap: true },
    { key: 'start', header: headers[4] ?? '', cell: (l) => formatMoney(l.start_price), sortValue: (l) => l.start_price, align: 'right' },
    { key: 'contract', header: headers[5] ?? '', cell: (l) => (l.contract_price === null ? '—' : <b>{formatMoney(l.contract_price)}</b>), sortValue: (l) => l.contract_price, align: 'right' },
    { key: 'status', header: headers[6] ?? '', cell: (l) => <Badge tone={STATUS_TONE[l.kind] ?? 'neutral'}>{lotStatusLabel(l.status)}</Badge>, sortValue: (l) => l.status },
    { key: 'days', header: headers[7] ?? '', cell: (l) => <Days lot={l} />, sortValue: (l) => l.days },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('zak.lots.sub')}
      actions={
        <div className="seg" role="group" aria-label={t('zak.lots.filter')}>
          {FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {t(`zak.lots.${f}` as MessageKey)}
            </button>
          ))}
        </div>
      }
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({ headers, rows: shown.map((l) => [l.lot_no, l.subject, l.branch_name, l.method_title, l.start_price, l.contract_price, lotStatusLabel(l.status), l.days]) })}
        />
      }
    >
      {shown.length ? <Table caption={title} columns={columns} rows={shown} rowKey={(l) => `${l.branch_id}:${l.lot_no}`} free={limit !== undefined} /> : <p className="note">{t('zak.lots.none')}</p>}
      {truncated ? <p className="note">{t('zak.lots.truncated')}</p> : null}
      {limit !== undefined ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'zakupki', page: 'loty', br: filters.br, per: filters.per })}>
          {t('zak.lots.more')}
        </a>
      ) : null}
    </Card>
  );
}
```

- [ ] **Step 5: Implementatsiya — filiallar va tejash kartalari**

`frontend/src/sections/zakupki/parts/ZakBranchesTable.tsx`:
```tsx
import type { ZakBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

function Exec({ value }: { value: number | null }) {
  return (
    <span className="exec">
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

/** Prototip «Закупки по филиалам»: годовой план, заключено с начала года, исполнение, экономия. */
export function ZakBranchesTable({ rows, ctx, filters, onBranch, className }: { rows: ZakBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('zak.branches.title');
  const headers = [t('zak.col.branch'), t('zak.branches.plan'), t('zak.branches.ytd'), t('zak.branches.exec'), t('zak.branches.savings')];
  const columns: Column<ZakBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'plan', header: headers[1] ?? '', cell: (b) => formatMoney(b.plan), sortValue: (b) => b.plan, align: 'right' },
    { key: 'ytd', header: headers[2] ?? '', cell: (b) => formatMoney(b.ytd), sortValue: (b) => b.ytd, align: 'right' },
    { key: 'exec', header: headers[3] ?? '', cell: (b) => <Exec value={b.execution} />, sortValue: (b) => b.execution, align: 'right' },
    { key: 'savings', header: headers[4] ?? '', cell: (b) => formatMoney(b.savings), sortValue: (b) => b.savings, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('zak.branches.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.plan, b.ytd, b.execution === null ? null : Math.round(b.execution * 1000) / 10, b.savings]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(b) => b.branch_id} onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)} free />
    </Card>
  );
}
```

`frontend/src/sections/zakupki/parts/EconomyCards.tsx`:
```tsx
import type { ZakKpisOut, ZakLotOut, ZakMethodOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { formatDays } from '../../../dash/people';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

/** Prototip `ecoTable`: экономия по способам закупки. */
export function EconomyTable({ methods, ctx, className }: { methods: ZakMethodOut[]; ctx: ExportContext; className?: string }) {
  const title = t('zak.eco.title');
  const headers = [t('zak.col.method'), t('zak.eco.lots'), t('zak.col.start'), t('zak.eco.contracts'), t('zak.kpi.savings'), t('zak.eco.share')];
  const columns: Column<ZakMethodOut>[] = [
    { key: 'title', header: headers[0] ?? '', cell: (m) => m.title, sortValue: (m) => m.title },
    { key: 'lots', header: headers[1] ?? '', cell: (m) => formatNumber(m.lots), sortValue: (m) => m.lots, align: 'right' },
    { key: 'start', header: headers[2] ?? '', cell: (m) => formatMoney(m.start), sortValue: (m) => m.start, align: 'right' },
    { key: 'contracted', header: headers[3] ?? '', cell: (m) => formatMoney(m.contracted), sortValue: (m) => m.contracted, align: 'right' },
    { key: 'savings', header: headers[4] ?? '', cell: (m) => <b>{formatMoney(m.savings)}</b>, sortValue: (m) => m.savings, align: 'right' },
    { key: 'share', header: headers[5] ?? '', cell: (m) => formatPct(m.savings_share, 1), sortValue: (m) => m.savings_share, align: 'right' },
  ];
  return (
    <Card className={className} title={title} sub={t('zak.eco.sub')} exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: methods.map((m) => [m.title, m.lots, m.start, m.contracted, m.savings, m.savings_share]) })} />}>
      <div title={formula('savings')}>
        <Table caption={title} columns={columns} rows={methods} rowKey={(m) => m.method} free />
      </div>
    </Card>
  );
}

/** Prototip «Отменённые лоты». */
export function CancelledCard({ lots, className }: { lots: ZakLotOut[]; className?: string }) {
  const title = t('zak.cancelled.title');
  const columns: Column<ZakLotOut>[] = [
    { key: 'lot', header: t('zak.col.lot'), cell: (l) => l.lot_no },
    { key: 'subject', header: t('zak.col.subject'), cell: (l) => l.subject, wrap: true },
    { key: 'branch', header: t('zak.col.branch'), cell: (l) => l.branch_name, wrap: true },
    { key: 'start', header: t('zak.col.start'), cell: (l) => formatMoney(l.start_price), align: 'right' },
  ];
  return (
    <Card className={className} title={title} sub={t('zak.cancelled.sub')}>
      {lots.length ? <Table caption={title} columns={columns} rows={lots} rowKey={(l) => `${l.branch_id}:${l.lot_no}`} free /> : <p className="note">{t('zak.cancelled.none')}</p>}
    </Card>
  );
}

/** Prototip «Средний срок закупки»: среднее по договорам и по способам (норматив — в подписи). */
export function AvgDaysCard({ kpis, methods, className }: { kpis: ZakKpisOut; methods: ZakMethodOut[]; className?: string }) {
  const title = t('zak.days.title');
  const avg = kpis.avg_days;
  return (
    <Card className={className} title={title} sub={t('zak.days.sub')}>
      <div className="bigline" title={formula('avgProcDays')}>
        <b>{avg === null ? t('dash.noValue') : `${formatNumber(avg, 1)} ${t('unit.dayShort')}`}</b>
        <span>{t('zak.days.avg')}</span>
      </div>
      <Rank
        label={title}
        items={methods.filter((m) => m.avg_days !== null).map((m) => ({ id: m.method, name: m.title, value: m.avg_days ?? 0, ...(m.norm_days === null ? {} : { note: t('zak.days.norm', { norm: m.norm_days }) }) }))}
        format={(v) => formatDays(v)}
      />
    </Card>
  );
}
```

- [ ] **Step 6: Implementatsiya — sahifalar**

`frontend/src/sections/zakupki/svod.tsx`:
```tsx
import type { ZakSvodOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { LotsTable } from './parts/LotsTable';
import { MethodsCard } from './parts/MethodsCard';
import { ZakKpis } from './parts/ZakKpis';
import { ZakMonthsCard } from './parts/ZakMonthsCard';

export default function ZakupkiSvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<ZakSvodOut>('/zakupki/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <ZakMonthsCard className="c8" months={data.months} ctx={ctx} />
            <MethodsCard className="c4" methods={data.methods} />
            <LotsTable className="c12" lots={data.lots} ctx={ctx} filters={filters} limit={8} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/zakupki/loty.tsx`:
```tsx
import type { ZakLotyOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { LotsTable } from './parts/LotsTable';
import { ZakKpis } from './parts/ZakKpis';

export default function ZakupkiLoty({ section, page, filters }: SectionPageProps) {
  const query = useSection<ZakLotyOut>('/zakupki/loty', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <LotsTable className="c12" lots={data.lots} ctx={ctx} filters={filters} truncated={data.truncated} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/zakupki/postavshiki.tsx`:
```tsx
import type { ZakPostavshikiOut } from '../../api/types';
import { t } from '../../i18n';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NamedRankCard } from './parts/NamedRankCard';
import { ZakBranchesTable } from './parts/ZakBranchesTable';
import { ZakKpis } from './parts/ZakKpis';

export default function ZakupkiPostavshiki({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ZakPostavshikiOut>('/zakupki/postavshiki', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <NamedRankCard className="c6" title={t('zak.suppliers.title')} sub={t('zak.suppliers.sub')} rows={data.suppliers} />
            <NamedRankCard className="c6" title={t('zak.subjects.title')} sub={t('zak.subjects.sub')} rows={data.subjects} />
            <ZakBranchesTable className="c12" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/zakupki/ekonomiya.tsx`:
```tsx
import type { ZakEkonomiyaOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { AvgDaysCard, CancelledCard, EconomyTable } from './parts/EconomyCards';
import { ZakKpis } from './parts/ZakKpis';

export default function ZakupkiEkonomiya({ section, page, filters }: SectionPageProps) {
  const query = useSection<ZakEkonomiyaOut>('/zakupki/ekonomiya', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <ZakKpis kpis={data.kpis} />
          <div className="grid">
            <EconomyTable className="c12" methods={data.methods} ctx={ctx} />
            <CancelledCard className="c6" lots={data.cancelled} />
            <AvgDaysCard className="c6" kpis={data.kpis} methods={data.methods} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/zakupki` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: 4 test passed; tsc va eslint xatosiz.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Закупки» — Сводка, Лоты (filtr), Договоры и поставщики, Экономия

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 20: Frontend — «Инвестиции»: Сводка, Объекты, Источники и освоение, Сроки и риски

**Files:**
- Create: `frontend/src/sections/investicii/parts/InvKpis.tsx`, `parts/CumCard.tsx`, `parts/SourcesCard.tsx`, `parts/ObjectsTable.tsx`, `parts/ObjectsRank.tsx`, `parts/RiskCards.tsx`, `parts/NoObjects.tsx`, `frontend/src/sections/investicii/svod.tsx`, `obekty.tsx`, `istochniki.tsx`, `riski.tsx`
- Test: `frontend/src/sections/investicii/investicii.test.tsx`

**Interfaces:**
- Consumes: `useSection`, `SectionData`, `SectionPageProps`, `toggleBranch`, `buildHash`, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Column`, `Badge`, `BadgeTone`, `EmptyState`, `Rank`, `ChartCanvas`, `barConfig` (`Series.dashed` — S3), `COLORS`, `ChartHandle`, `CardExport`, `ExportContext`, `formula`, `formatMoney`, `formatPct`, `moneyParts`, `monthShort`, `formatNumber`, `formatDate`, `formatDays`, `formatPp`, `s4.css` (`.fp`, `.stg`, `.obj-note`), fixture'lar (`INV_*`), `mockApi`, `json`, `renderWithProviders`, `expectNoAxeViolations`, `ME_ADMIN`.
- Produces:
  - Kartalar: `InvKpis({ kpis, period })`, `CumCard({ points, ctx, className? })` (reja — uzuk-uzuk chiziq, fakt — joriy oygacha), `SourcesCard({ sources, className? })`, `ObjectsTable({ objects, ctx, filters, onBranch, limit?, className? })` (holat — `Badge`: risk `neg`, lag `warn`, ok `blue`; moliyaviy polosa + jismoniy belgi, uzilish > 20 p.p. — qizil), `ObjectsRank({ objects, filters, onBranch, className? })`, `LaggingCard`, `GapsCard`, `StagesCard`, `AdvancesCard`, `NoObjects()`; `statusLabel(status)`, `workLabel(workType)`.
  - Sahifalar `#investicii/svod`, `#investicii/obekty`, `#investicii/istochniki`, `#investicii/riski`; `kpis.has_objects = false` — `NoObjects`.

- [ ] **Step 1: Testlarni yozish**

`frontend/src/sections/investicii/investicii.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { INV_ISTOCHNIKI, INV_NONE, INV_OBEKTY, INV_RISKI, INV_SVOD } from '../../test/s4Fixtures';
import InvesticiiIstochniki from './istochniki';
import InvesticiiObekty from './obekty';
import InvesticiiRiski from './riski';
import InvesticiiSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Инвестиции', () => {
  it('Сводка: KPIs, cumulative chart, sources and the object registry', async () => {
    mockApi({ 'GET /investicii/svod': json(INV_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<InvesticiiSvod section="investicii" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Программа 2026')).toBeInTheDocument();
    expect(screen.getByText('81,8%')).toHaveClass('neg');
    expect(screen.getByRole('img', { name: 'Освоение нарастающим итогом' })).toBeInTheDocument();
    expect(screen.getByText('Кредиты МФИ')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Объекты программы' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2);
    expect(within(table).getByText('75%, отстаёт')).toHaveClass('badge--warn');
    expect(within(table).getByText('физ. 5%')).toHaveClass('neg');
    expect(screen.getByRole('link', { name: 'Все объекты' }).getAttribute('href')).toContain('investicii/obekty');
    await expectNoAxeViolations(container);
  });

  it('Сводка: branch without objects shows the explanation', async () => {
    mockApi({ 'GET /investicii/svod': json(INV_NONE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<InvesticiiSvod section="investicii" page="svod" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText('У выбранного филиала нет объектов адресной программы.')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Освоение нарастающим итогом' })).toBeNull();
  });

  it('Объекты: full registry, row click selects the branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /investicii/obekty': json(INV_OBEKTY), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<InvesticiiObekty section="investicii" page="obekty" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Реестр объектов' });
    await user.click(within(table).getByText('Реконструкция водоприёмника'));
    expect(onBranch).toHaveBeenCalledWith(3);
    expect(screen.queryByRole('link', { name: 'Все объекты' })).toBeNull();
  });

  it('Источники и освоение: sources, objects rank with plan mark, cumulative chart', async () => {
    mockApi({ 'GET /investicii/istochniki': json(INV_ISTOCHNIKI), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<InvesticiiIstochniki section="investicii" page="istochniki" filters={filters} onBranch={vi.fn()} />);
    const rank = await screen.findByRole('list', { name: 'Освоение по объектам' });
    const items = within(rank).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('38% годового плана');
    expect(screen.getByRole('img', { name: 'Освоение нарастающим итогом' })).toBeInTheDocument();
  });

  it('Сроки и риски: lagging, gaps, stages strip and old advances', async () => {
    mockApi({ 'GET /investicii/riski': json(INV_RISKI), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<InvesticiiRiski section="investicii" page="riski" filters={filters} onBranch={vi.fn()} />);
    const lagging = await screen.findByRole('list', { name: 'Объекты с отставанием' });
    expect(within(lagging).getByText('75% графика')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Разрыв финансирования и физического выполнения' })).getByText('33 п.п.')).toBeInTheDocument();
    expect(container.querySelectorAll('.stg span')).toHaveLength(4);
    expect(container.querySelectorAll('.stg span.is-late')).toHaveLength(1);
    expect(screen.getByText('этапов с отставанием: 2')).toBeInTheDocument();
    expect(screen.getByText('Строительно-монтажные работы')).toBeInTheDocument();
    const advances = screen.getByRole('table', { name: 'Незакрытые авансы' });
    expect(within(advances).getAllByRole('row')).toHaveLength(1 + 2);
    expect(within(advances).getByText('113 дн.')).toHaveClass('badge--neg');
    await expectNoAxeViolations(container);
  });
});
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/investicii`
Expected: FAIL — `Failed to resolve import "./istochniki"`.

- [ ] **Step 3: Implementatsiya — KPI, grafik, manbalar, bo'sh holat**

`frontend/src/sections/investicii/parts/InvKpis.tsx`:
```tsx
import type { InvKpisOut, ReportPeriodOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const ON_TRACK = 0.9; // TZ 4 qoidasi «Адресная программа: исполнение графика < 90%»

/** Prototip `kpisInv`: программа, освоено, исполнение графика, за период, отстающие, ввод. */
export function InvKpis({ kpis, period }: { kpis: InvKpisOut; period: ReportPeriodOut }) {
  const program = moneyParts(kpis.program);
  const ytd = moneyParts(kpis.fact_ytd);
  const perPeriod = moneyParts(kpis.fact_period);
  const share = kpis.program > 0 ? kpis.fact_ytd / kpis.program : null;
  const low = kpis.execution !== null && kpis.execution < ON_TRACK;
  return (
    <KpiGrid>
      <KpiTile icon="target" label={t('inv.kpi.program', { year: kpis.year })} value={program.value} unit={program.unit} delta={t('inv.kpi.programNote', { count: kpis.objects, cost: formatMoney(kpis.total_cost) })} hint={formula('program')} />
      <KpiTile icon="coins" label={t('inv.kpi.ytd')} value={ytd.value} unit={ytd.unit} delta={t('inv.kpi.ytdNote', { pct: formatPct(share, 1) })} hint={formula('invYtd')} />
      <KpiTile
        icon="pct"
        label={t('inv.kpi.schedule')}
        value={<span className={low ? 'neg' : undefined}>{formatPct(kpis.execution, 1)}</span>}
        delta={t('inv.kpi.scheduleNote', { date: formatDate(period.date_to), amount: formatMoney(kpis.plan_to_date) })}
        hint={formula('schedule')}
      />
      <KpiTile icon="net" label={t('inv.kpi.period')} value={perPeriod.value} unit={perPeriod.unit} delta={period.label} hint={formula('invYtd')} />
      <KpiTile
        icon="alert"
        label={t('inv.kpi.lagging')}
        value={<span className={kpis.lagging ? 'neg' : undefined}>{formatNumber(kpis.lagging)}</span>}
        delta={kpis.lagging ? t('inv.kpi.laggingNote', { count: kpis.threatened }) : t('inv.kpi.laggingNone')}
        hint={formula('objStatus')}
      />
      <KpiTile icon="check" label={t('inv.kpi.commissioning', { year: kpis.year })} value={formatNumber(kpis.commissioning)} delta={t('inv.kpi.commissioningNote')} />
    </KpiGrid>
  );
}
```

`frontend/src/sections/investicii/parts/CumCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { InvCumOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `invCum`: план (uzuk-uzuk) va факт нарастающим итогом; fakt — joriy oygacha. */
export function CumCard({ points, ctx, className }: { points: InvCumOut[]; ctx: ExportContext; className?: string }) {
  const title = t('inv.cum.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const plan = COLORS.bal();
  const fact = COLORS.in();
  const config = useMemo(
    () =>
      barConfig({
        labels: points.map((p) => monthShort(p.month_id)),
        series: [
          { label: t('inv.cum.plan'), data: points.map((p) => p.plan), color: plan, type: 'line', dashed: true },
          { label: t('inv.cum.fact'), data: points.map((p) => p.fact ?? Number.NaN), color: fact, type: 'line' },
        ],
      }),
    [points, plan, fact],
  );
  const table = { headers: [t('inv.cum.month'), t('inv.cum.plan'), t('inv.cum.fact')], rows: points.map((p) => [monthShort(p.month_id), p.plan, p.fact]) };
  return (
    <Card className={className} title={title} sub={t('inv.cum.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('schedule')}>
        <span>
          <i className="dash" style={{ background: plan }} />
          {t('inv.cum.plan')}
        </span>
        <span>
          <i style={{ background: fact }} />
          {t('inv.cum.fact')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
```

`frontend/src/sections/investicii/parts/SourcesCard.tsx`:
```tsx
import type { InvSourceOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `srcCard`: годовой лимит и освоение по источникам финансирования. */
export function SourcesCard({ sources, className }: { sources: InvSourceOut[]; className?: string }) {
  return (
    <Card className={className} title={t('inv.src.title')} sub={t('inv.src.sub')}>
      <div title={formula('invYtd')}>
        {sources.map((s) => (
          <div className="prog" key={s.name}>
            <div className="prog__h">
              <span>{s.name}</span>
              <b>{formatPct(s.share, 0)}</b>
            </div>
            <div className="prog__t" aria-hidden="true">
              <i style={{ width: `${Math.min(100, Math.max(0, (s.share ?? 0) * 100))}%` }} />
            </div>
            <div className="prog__f">
              <span>{t('inv.src.done', { amount: formatMoney(s.fact_ytd) })}</span>
              <span>{t('inv.src.limit', { amount: formatMoney(s.plan_year) })}</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
```

`frontend/src/sections/investicii/parts/NoObjects.tsx`:
```tsx
import { t } from '../../../i18n';
import { EmptyState } from '../../../ui/EmptyState';

/** Prototip `noData('У выбранного филиала нет объектов адресной программы.')`. */
export function NoObjects() {
  return <EmptyState icon="target" title={t('inv.none.title')} text={t('inv.none.text')} />;
}
```

- [ ] **Step 4: Implementatsiya — obyektlar reyestri va Rank**

`frontend/src/sections/investicii/parts/ObjectsTable.tsx`:
```tsx
import type { InvObjectOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import '../../../dash/s4.css';
import { t, type MessageKey } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import type { FilterState } from '../../../shell/useFilters';
import { Badge, type BadgeTone } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

const GAP_PP = 20; // TZ 4: «Разрыв финансового и физического выполнения > 20 п.п.»
const TONES: Record<string, BadgeTone> = { risk: 'neg', lag: 'warn', ok: 'blue' };

export function statusLabel(status: string | null): string {
  return status ? t(`inv.status.${status}` as MessageKey) : t('dash.noValue');
}

export function workLabel(workType: string): string {
  return t(`inv.work.${workType}` as MessageKey);
}

export function FinPhys({ o }: { o: InvObjectOut }) {
  const high = o.gap_pp !== null && o.gap_pp > GAP_PP;
  return (
    <div className="fp" title={`${formula('finExec')}. ${formula('physExec')}`}>
      <div className="fp__h">
        <span>{formatPct(o.financial, 0)}</span>
        <span className={high ? 'neg' : undefined}>{t('inv.col.phys', { pct: formatPct(o.physical, 0) })}</span>
      </div>
      <div className="fp__t" aria-hidden="true">
        <i style={{ width: `${Math.min(100, Math.max(0, (o.financial ?? 0) * 100))}%` }} />
        {o.physical !== null ? <u style={{ left: `${Math.min(100, Math.max(0, o.physical * 100))}%` }} /> : null}
      </div>
    </div>
  );
}

export interface ObjectsTableProps {
  objects: InvObjectOut[];
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  limit?: number;
  className?: string;
}

/** Prototip `objTable`: reestr — стоимость, план года, освоено, график (статус), фин./физ. на одной полосе. */
export function ObjectsTable({ objects, ctx, filters, onBranch, limit, className }: ObjectsTableProps) {
  const title = limit ? t('inv.obj.title') : t('inv.obj.titleAll');
  const rows = objects.slice(0, limit ?? objects.length);
  const headers = [t('inv.col.object'), t('inv.col.branch'), t('inv.col.cost'), t('inv.col.plan'), t('inv.col.fact'), t('inv.col.schedule'), t('inv.col.finphys'), t('inv.col.deadline')];
  const columns: Column<InvObjectOut>[] = [
    {
      key: 'name',
      header: headers[0] ?? '',
      cell: (o) => (
        <>
          {o.name}
          <span className="obj-note">{`${o.object_code}, ${workLabel(o.work_type)}, ${o.source_name}`}</span>
        </>
      ),
      sortValue: (o) => o.name,
      wrap: true,
    },
    { key: 'branch', header: headers[1] ?? '', cell: (o) => o.branch_name, sortValue: (o) => o.branch_name, wrap: true },
    { key: 'cost', header: headers[2] ?? '', cell: (o) => formatMoney(o.total_cost), sortValue: (o) => o.total_cost, align: 'right' },
    { key: 'plan', header: headers[3] ?? '', cell: (o) => formatMoney(o.plan_year), sortValue: (o) => o.plan_year, align: 'right' },
    { key: 'fact', header: headers[4] ?? '', cell: (o) => <b>{formatMoney(o.fact_ytd)}</b>, sortValue: (o) => o.fact_ytd, align: 'right' },
    {
      key: 'schedule',
      header: headers[5] ?? '',
      cell: (o) => <Badge tone={TONES[o.status ?? ''] ?? 'neutral'}>{`${formatPct(o.execution, 0)}, ${statusLabel(o.status)}`}</Badge>,
      sortValue: (o) => o.execution,
    },
    { key: 'fp', header: headers[6] ?? '', cell: (o) => <FinPhys o={o} />, sortValue: (o) => o.gap_pp },
    { key: 'deadline', header: headers[7] ?? '', cell: (o) => (o.commissioning_year === null ? '—' : String(o.commissioning_year)), sortValue: (o) => o.commissioning_year, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={limit ? t('inv.obj.sub') : t('inv.obj.subAll')}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers,
            rows: objects.map((o) => [o.name, o.branch_name, o.total_cost, o.plan_year, o.fact_ytd, o.execution === null ? null : Math.round(o.execution * 1000) / 10, o.financial === null ? null : Math.round(o.financial * 1000) / 10, o.commissioning_year]),
          })}
        />
      }
    >
      <div title={formula('objStatus')}>
        <Table caption={title} columns={columns} rows={rows} rowKey={(o) => o.object_id} onRowClick={(o) => toggleBranch(filters, o.branch_id, onBranch)} free={limit !== undefined} />
      </div>
      {limit !== undefined ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'investicii', page: 'obekty', br: filters.br, per: filters.per })}>
          {t('inv.obj.more')}
        </a>
      ) : null}
    </Card>
  );
}
```

`frontend/src/sections/investicii/parts/ObjectsRank.tsx`:
```tsx
import type { InvObjectOut } from '../../../api/types';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

/** Prototip «Освоение по объектам»: освоено с начала года, черта — годовой план. */
export function ObjectsRank({ objects, filters, onBranch, className }: { objects: InvObjectOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('inv.rank.title');
  const byId = new Map(objects.map((o) => [o.object_id, o]));
  return (
    <Card className={className} title={title} sub={t('inv.rank.sub')}>
      <Rank
        label={title}
        items={objects.map((o) => ({ id: o.object_id, name: o.name, value: o.fact_ytd, mark: o.plan_year, note: t('inv.rank.note', { pct: formatPct(o.plan_year > 0 ? o.fact_ytd / o.plan_year : null, 0) }) }))}
        onSelect={(id) => {
          const o = byId.get(Number(id));
          if (o) toggleBranch(filters, o.branch_id, onBranch);
        }}
        activeId={null}
      />
    </Card>
  );
}
```

- [ ] **Step 5: Implementatsiya — xavf kartalari**

`frontend/src/sections/investicii/parts/RiskCards.tsx`:
```tsx
import type { InvObjectOut, InvObjectStagesOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { formatDays, formatPp } from '../../../dash/people';
import { Rank } from '../../../dash/Rank';
import '../../../dash/s4.css';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

interface ListProps {
  rows: InvObjectOut[];
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

function select(rows: InvObjectOut[], filters: FilterState, onBranch: (br: number | null) => void) {
  const byId = new Map(rows.map((o) => [o.object_id, o]));
  return (id: string | number) => {
    const o = byId.get(Number(id));
    if (o) toggleBranch(filters, o.branch_id, onBranch);
  };
}

/** Prototip «Объекты с отставанием»: исполнение графика ниже 90%, черта — план на дату. */
export function LaggingCard({ rows, filters, onBranch, className }: ListProps) {
  const title = t('inv.risk.lagTitle');
  return (
    <Card className={className} title={title} sub={t('inv.risk.lagSub')}>
      {rows.length ? (
        <Rank
          label={title}
          items={rows.map((o) => ({ id: o.object_id, name: o.name, value: o.fact_ytd, mark: o.plan_to_date, note: t('inv.risk.lagNote', { pct: formatPct(o.execution, 0) }), negative: o.status === 'risk' }))}
          onSelect={select(rows, filters, onBranch)}
        />
      ) : (
        <p className="note">{t('inv.risk.lagNone')}</p>
      )}
    </Card>
  );
}

/** Prototip «Разрыв финансирования и физического выполнения» (> 20 п.п.). */
export function GapsCard({ rows, filters, onBranch, className }: ListProps) {
  const title = t('inv.risk.gapTitle');
  return (
    <Card className={className} title={title} sub={t('inv.risk.gapSub')}>
      <div title={formula('finGap')}>
        {rows.length ? (
          <Rank
            label={title}
            items={rows.map((o) => ({ id: o.object_id, name: o.name, value: o.gap_pp ?? 0, note: t('inv.risk.gapNote', { fin: formatPct(o.financial, 0), phys: formatPct(o.physical, 0) }), negative: true }))}
            format={(v) => formatPp(v)}
            onSelect={select(rows, filters, onBranch)}
          />
        ) : (
          <p className="note">{t('inv.risk.gapNone')}</p>
        )}
      </div>
    </Card>
  );
}

/** Prototip `stageCard`: пройденные этапы (лента) и отклонения по срокам. */
export function StagesCard({ stages, className }: { stages: InvObjectStagesOut[]; className?: string }) {
  return (
    <Card className={className} title={t('inv.risk.stageTitle')} sub={t('inv.risk.stageSub')}>
      {stages.length ? (
        stages.map((s) => {
          const done = s.stages.filter((x) => x.done).length;
          const next = s.stages.find((x) => !x.done);
          return (
            <div className="prog" key={s.object_id}>
              <div className="prog__h">
                <span>{s.name}</span>
                <b className={s.late ? 'neg' : undefined}>{t('inv.risk.stageDone', { done, total: s.stages.length })}</b>
              </div>
              <div className="stg" aria-hidden="true">
                {s.stages.map((x) => (
                  <span
                    key={x.stage_no}
                    className={x.done ? (x.late ? 'is-late' : 'is-done') : undefined}
                    title={x.fact_date ? t('inv.risk.stageTip', { name: x.name, date: formatDate(x.fact_date) }) : t('inv.risk.stageTipOpen', { name: x.name })}
                  />
                ))}
              </div>
              <div className="prog__f">
                <span>{next ? next.name : t('inv.risk.stageAll')}</span>
                <span>{s.late ? t('inv.risk.stageLate', { count: s.late }) : t('inv.risk.stageOk')}</span>
              </div>
            </div>
          );
        })
      ) : (
        <p className="note">{t('inv.risk.stageNone')}</p>
      )}
    </Card>
  );
}

/** Prototip «Незакрытые авансы»: авансы старше 90 дней. */
export function AdvancesCard({ rows, className }: { rows: InvObjectOut[]; className?: string }) {
  const title = t('inv.risk.advTitle');
  const columns: Column<InvObjectOut>[] = [
    { key: 'name', header: t('inv.col.object'), cell: (o) => o.name, wrap: true },
    { key: 'amount', header: t('inv.risk.advAmount'), cell: (o) => <b>{formatMoney(o.advance)}</b>, align: 'right' },
    { key: 'days', header: t('inv.risk.advDays'), cell: (o) => <Badge tone="neg">{formatDays(o.advance_days)}</Badge> },
  ];
  return (
    <Card className={className} title={title} sub={t('inv.risk.advSub')}>
      <div title={formula('advances')}>
        {rows.length ? <Table caption={title} columns={columns} rows={rows} rowKey={(o) => o.object_id} free /> : <p className="note">{t('inv.risk.advNone')}</p>}
      </div>
    </Card>
  );
}
```

- [ ] **Step 6: Implementatsiya — sahifalar**

`frontend/src/sections/investicii/svod.tsx`:
```tsx
import type { InvSvodOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CumCard } from './parts/CumCard';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { ObjectsTable } from './parts/ObjectsTable';
import { SourcesCard } from './parts/SourcesCard';

export default function InvesticiiSvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<InvSvodOut>('/investicii/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <CumCard className="c8" points={data.cumulative} ctx={ctx} />
              <SourcesCard className="c4" sources={data.sources} />
              <ObjectsTable className="c12" objects={data.objects} ctx={ctx} filters={filters} onBranch={onBranch} limit={6} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/investicii/obekty.tsx`:
```tsx
import type { InvObektyOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { ObjectsTable } from './parts/ObjectsTable';

export default function InvesticiiObekty({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<InvObektyOut>('/investicii/obekty', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <ObjectsTable className="c12" objects={data.objects} ctx={ctx} filters={filters} onBranch={onBranch} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/investicii/istochniki.tsx`:
```tsx
import type { InvIstochnikiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CumCard } from './parts/CumCard';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { ObjectsRank } from './parts/ObjectsRank';
import { SourcesCard } from './parts/SourcesCard';

export default function InvesticiiIstochniki({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<InvIstochnikiOut>('/investicii/istochniki', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <SourcesCard className="c5" sources={data.sources} />
              <ObjectsRank className="c7" objects={data.objects} filters={filters} onBranch={onBranch} />
              <CumCard className="c12" points={data.cumulative} ctx={ctx} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/investicii/riski.tsx`:
```tsx
import type { InvRiskiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { InvKpis } from './parts/InvKpis';
import { NoObjects } from './parts/NoObjects';
import { AdvancesCard, GapsCard, LaggingCard, StagesCard } from './parts/RiskCards';

export default function InvesticiiRiski({ filters, onBranch }: SectionPageProps) {
  const query = useSection<InvRiskiOut>('/investicii/riski', filters);
  return (
    <SectionData query={query}>
      {(data) =>
        data.kpis.has_objects ? (
          <>
            <InvKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <LaggingCard className="c6" rows={data.lagging} filters={filters} onBranch={onBranch} />
              <GapsCard className="c6" rows={data.gaps} filters={filters} onBranch={onBranch} />
              <StagesCard className="c7" stages={data.stages} />
              <AdvancesCard className="c5" rows={data.advances} />
            </div>
          </>
        ) : (
          <NoObjects />
        )
      }
    </SectionData>
  );
}
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/investicii` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: 5 test passed; tsc va eslint xatosiz.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Инвестиции» — Сводка, Объекты, Источники и освоение, Сроки и риски

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 21: Frontend — «Кадры»: Сводка, Численность, Оплата труда, Движение кадров

**Files:**
- Create: `frontend/src/sections/kadry/parts/HrKpis.tsx`, `parts/FotCard.tsx`, `parts/CategoriesCard.tsx`, `parts/HrBranchesTable.tsx`, `parts/HrRanks.tsx`, `parts/MovesCard.tsx`, `parts/TurnoverTable.tsx`, `parts/NoStaff.tsx`, `frontend/src/sections/kadry/svod.tsx`, `chislennost.tsx`, `fot.tsx`, `dvizhenie.tsx`
- Test: `frontend/src/sections/kadry/kadry.test.tsx`

**Interfaces:**
- Consumes: `useSection`, `SectionData`, `SectionPageProps`, `toggleBranch`, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Column`, `NoData`, `Rank`, `ChartCanvas`, `barConfig` (`axis: 'right'`, `rightFormat` — 18-vazifa), `COLORS`, `ChartHandle`, `CardExport`, `ExportContext`, `formula`, `formatMoney`, `formatPct`, `moneyParts`, `monthShort`, `formatNumber`, `formatPeople`, `formatHours`, fixture'lar (`HR_*`, `KADRY_*`), `mockApi`, `json`, `renderWithProviders`, `expectNoAxeViolations`, `ME_ADMIN`.
- Produces:
  - Kartalar: `HrKpis({ kpis })` (ma'lumot yo'q — «—» va «штат не загружен»), `FotCard({ months, ctx, className? })` (ФОТ ustunlari + o'rtacha ish haqi o'ng o'qda), `CategoriesCard({ categories, className? })`, `HrBranchesTable({ rows, kpis, ctx, filters, onBranch, className? })` («Итого» qatori bilan), `VacancyRank`, `AvgSalaryRank`, `PayrollRank`, `PayrollShareCard`, `OvertimeCard` (`HrRanks.tsx`), `MovesCard({ months, ctx, className? })`, `TurnoverTable({ rows, ctx, filters, onBranch, className? })`, `NoStaff()` (`NoData kind="source"`).
  - Sahifalar `#kadry/svod`, `#kadry/chislennost`, `#kadry/fot`, `#kadry/dvizhenie`. Hech qaysi komponent shaxsga oid ma'lumot kutmaydi va ko'rsatmaydi (faqat agregatlar).

- [ ] **Step 1: Testlarni yozish**

`frontend/src/sections/kadry/kadry.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { KADRY_CHISL, KADRY_DVIZH, KADRY_EMPTY, KADRY_FOT, KADRY_SVOD } from '../../test/s4Fixtures';
import KadryChislennost from './chislennost';
import KadryDvizhenie from './dvizhenie';
import KadryFot from './fot';
import KadrySvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Кадры', () => {
  it('Сводка: KPIs, payroll chart, staff structure and branch table', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kadry/svod': json(KADRY_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container, user } = renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={onBranch} />);
    expect(await screen.findByText('Штатная численность')).toBeInTheDocument();
    expect(screen.getByText('укомплектованность 90,0%')).toBeInTheDocument();
    expect(screen.getByText('за период, 30,0% расходования')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Фонд оплаты труда по месяцам' })).toBeInTheDocument();
    expect(screen.getByText('90,0% персонала')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Численность по филиалам' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2 + 1);
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    await user.click(within(table).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
    await expectNoAxeViolations(container);
  });

  it('Численность: vacancies by branch, largest first', async () => {
    mockApi({ 'GET /kadry/chislennost': json(KADRY_CHISL), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadryChislennost section="kadry" page="chislennost" filters={filters} onBranch={vi.fn()} />);
    const rank = await screen.findByRole('list', { name: 'Вакансии по филиалам' });
    const items = within(rank).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Чарвакская ГЭС');
    expect(items[0]).toHaveTextContent('30 чел.');
    expect(items[0]).toHaveTextContent('20,0% штата');
  });

  it('Оплата труда: payroll share, average salary and payroll by branch', async () => {
    mockApi({ 'GET /kadry/fot': json(KADRY_FOT), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadryFot section="kadry" page="fot" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('30,0%')).toBeInTheDocument();
    const avg = within(screen.getByRole('list', { name: 'Средняя зарплата по филиалам' })).getAllByRole('listitem');
    expect(avg[0]).toHaveTextContent('Чарвакская ГЭС');
    expect(avg[0]).toHaveTextContent('2,1 млн');
    expect(within(screen.getByRole('list', { name: 'ФОТ по филиалам' })).getAllByRole('listitem')).toHaveLength(2);
  });

  it('Движение кадров: hires and fires chart, overtime and turnover table', async () => {
    mockApi({ 'GET /kadry/dvizhenie': json(KADRY_DVIZH), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<KadryDvizhenie section="kadry" page="dvizhenie" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByRole('img', { name: 'Приём и увольнение по месяцам' })).toBeInTheDocument();
    expect(container.querySelector('.bigline b')).toHaveTextContent('420 ч');
    expect(screen.getByText('4,7 ч на работника')).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Текучесть по филиалам' });
    const first = within(table).getAllByRole('row')[1];
    expect(first).toHaveTextContent('Чарвакская ГЭС');
    expect(within(first as HTMLElement).getByText('10,0%').closest('.exec')).toHaveClass('neg');
  });

  it('No staff data: KPIs show dashes and the source message', async () => {
    mockApi({ 'GET /kadry/svod': json(KADRY_EMPTY), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KadrySvod section="kadry" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText(/кадровые данные \(HR API или файл численности\)/)).toBeInTheDocument();
    expect(screen.getAllByText('штат не загружен').length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/kadry`
Expected: FAIL — `Failed to resolve import "./chislennost"`.

- [ ] **Step 3: Implementatsiya — KPI, ФОТ grafigi, tuzilma, bo'sh holat**

`frontend/src/sections/kadry/parts/HrKpis.tsx`:
```tsx
import type { HrKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const VAC_HIGH = 0.1; // TZ 4 qoidasi «Вакансии > 10% штата»
const TURN_HIGH = 0.08; // TZ 4 qoidasi «Текучесть > 8%»

function num(value: number | null, digits = 0): string {
  return value === null ? t('dash.noValue') : formatNumber(value, digits);
}

/** Prototip `kpisHr`: штат, факт, вакансии, ФОТ, средняя зарплата, текучесть. Faqat agregatlar. */
export function HrKpis({ kpis }: { kpis: HrKpisOut }) {
  const payroll = moneyParts(kpis.payroll);
  const staff = kpis.has_data;
  return (
    <KpiGrid>
      <KpiTile icon="people" label={t('kad.kpi.plan')} value={staff ? num(kpis.plan) : t('dash.noValue')} unit={t('unit.peopleShort')} delta={staff ? t('kad.kpi.planNote') : t('kad.kpi.noStaff')} hint={formula('headcount')} />
      <KpiTile icon="people" label={t('kad.kpi.fact')} value={staff ? num(kpis.fact) : t('dash.noValue')} unit={t('unit.peopleShort')} delta={staff ? t('kad.kpi.factNote', { pct: formatPct(kpis.fill, 1) }) : t('kad.kpi.noStaff')} hint={formula('headcount')} />
      <KpiTile
        icon="alert"
        label={t('kad.kpi.vacancies')}
        value={<span className={kpis.vacancy_share !== null && kpis.vacancy_share > VAC_HIGH ? 'neg' : undefined}>{num(kpis.vacancies)}</span>}
        delta={t('kad.kpi.vacanciesNote', { pct: formatPct(kpis.vacancy_share, 1) })}
        hint={formula('vacancies')}
      />
      <KpiTile icon="coins" label={t('kad.kpi.payroll')} value={payroll.value} unit={payroll.unit} delta={t('kad.kpi.payrollNote', { pct: formatPct(kpis.payroll_share, 1) })} hint={formula('payroll')} />
      <KpiTile icon="card" label={t('kad.kpi.avg')} value={num(kpis.avg_salary, 1)} unit={t('kad.kpi.avgUnit')} delta={t('kad.kpi.avgNote')} hint={formula('avgSalary')} />
      <KpiTile
        icon="net"
        label={t('kad.kpi.turnover')}
        value={<span className={kpis.turnover !== null && kpis.turnover > TURN_HIGH ? 'neg' : undefined}>{formatPct(kpis.turnover, 1)}</span>}
        delta={t('kad.kpi.turnoverNote', { hired: kpis.hired, fired: kpis.fired })}
        hint={formula('staffTurnover')}
      />
    </KpiGrid>
  );
}
```

`frontend/src/sections/kadry/parts/FotCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { HrMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** Prototip `fotCard`: ФОТ — ustunlar, o'rtacha ish haqi — chiziq o'ng o'qda. */
export function FotCard({ months, ctx, className }: { months: HrMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('kad.fot.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const bar = COLORS.in();
  const line = COLORS.bal();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('kad.fot.payroll'), data: months.map((m) => m.payroll), color: bar },
          { label: t('kad.fot.avg'), data: months.map((m) => m.avg_salary ?? Number.NaN), color: line, type: 'line', axis: 'right' },
        ],
        rightFormat: (v, d) => formatNumber(v, d),
      }),
    [months, bar, line],
  );
  const table = { headers: [t('kad.fot.month'), t('kad.fot.payroll'), t('kad.fot.avg')], rows: months.map((m) => [monthShort(m.month_id), m.payroll, m.avg_salary]) };
  return (
    <Card className={className} title={title} sub={t('kad.fot.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={`${formula('payroll')}. ${formula('avgSalary')}`}>
        <span>
          <i style={{ background: bar }} />
          {t('kad.fot.payroll')}
        </span>
        <span>
          <i className="is-line" style={{ background: line }} />
          {t('kad.fot.avgRight')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
```

`frontend/src/sections/kadry/parts/CategoriesCard.tsx`:
```tsx
import type { HrCategoryOut } from '../../../api/types';
import { COLORS } from '../../../dash/chart';
import { formula } from '../../../dash/formulas';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** Prototip `catCard`: структура персонала по категориям (полоса + список). */
export function CategoriesCard({ categories, className }: { categories: HrCategoryOut[]; className?: string }) {
  const total = categories.reduce((s, c) => s + c.value, 0);
  const shades = [COLORS.v0(), COLORS.v1(), COLORS.v2(), COLORS.prev()];
  const color = (i: number): string => shades[i % shades.length] ?? COLORS.v0();
  return (
    <Card className={className} title={t('kad.cat.title')} sub={t('kad.cat.sub')}>
      <div title={formula('headcount')}>
        <div className="split" aria-hidden="true">
          {categories.map((c, i) => (
            <div key={c.name} style={{ flexGrow: c.value, background: color(i) }}>
              {total && c.value / total > 0.12 ? formatPct(c.value / total, 0) : ''}
            </div>
          ))}
        </div>
        <ul className="vt">
          {categories.map((c, i) => (
            <li key={c.name}>
              <i style={{ background: color(i) }} />
              <span>
                {c.name}
                <small>{t('kad.cat.share', { pct: formatPct(total ? c.value / total : null, 1) })}</small>
              </span>
              <b>{formatNumber(c.value)}</b>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
```

`frontend/src/sections/kadry/parts/NoStaff.tsx`:
```tsx
import { NoData } from '../../../dash/DataState';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Штат/численность manbasi hali ulanmagan (HR API tashkilot kesimisiz, fayl yuklanmagan). */
export function NoStaff() {
  return (
    <Card>
      <NoData kind="source" source={t('kad.none.source')} />
    </Card>
  );
}
```

- [ ] **Step 4: Implementatsiya — jadvallar va reytinglar**

`frontend/src/sections/kadry/parts/HrBranchesTable.tsx`:
```tsx
import type { HrBranchOut, HrKpisOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

const LOW_FILL = 0.9; // prototip: укомплектованность < 90% — qizil

function mln(value: number | null): string {
  return value === null ? t('dash.noValue') : t('kad.money.mln', { value: formatNumber(value, 1) });
}

function Fill({ value }: { value: number | null }) {
  return (
    <span className={cx('exec', value !== null && value < LOW_FILL && 'neg')}>
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

export interface HrBranchesTableProps {
  rows: HrBranchOut[];
  kpis: HrKpisOut;
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** Prototip `hrTable`: штат, факт, вакансии, укомплектованность, ФОТ, средняя зарплата; «Итого». */
export function HrBranchesTable({ rows, kpis, ctx, filters, onBranch, className }: HrBranchesTableProps) {
  const title = t('kad.br.title');
  const headers = [t('kad.br.branch'), t('kad.br.plan'), t('kad.br.fact'), t('kad.br.vac'), t('kad.br.fill'), t('kad.br.payroll'), t('kad.br.avg')];
  const columns: Column<HrBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'plan', header: headers[1] ?? '', cell: (b) => formatNumber(b.plan), sortValue: (b) => b.plan, align: 'right' },
    { key: 'fact', header: headers[2] ?? '', cell: (b) => <b>{formatNumber(b.fact)}</b>, sortValue: (b) => b.fact, align: 'right' },
    { key: 'vac', header: headers[3] ?? '', cell: (b) => <span className={b.fill !== null && b.fill < LOW_FILL ? 'neg' : undefined}>{b.vacancies === null ? t('dash.noValue') : formatNumber(b.vacancies)}</span>, sortValue: (b) => b.vacancies, align: 'right' },
    { key: 'fill', header: headers[4] ?? '', cell: (b) => <Fill value={b.fill} />, sortValue: (b) => b.fill, align: 'right' },
    { key: 'payroll', header: headers[5] ?? '', cell: (b) => formatMoney(b.payroll), sortValue: (b) => b.payroll, align: 'right' },
    { key: 'avg', header: headers[6] ?? '', cell: (b) => mln(b.avg_salary), sortValue: (b) => b.avg_salary, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('kad.br.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.plan, b.fact, b.vacancies, b.fill === null ? null : Math.round(b.fill * 1000) / 10, b.payroll, b.avg_salary]) })} />}
    >
      <Table
        caption={title}
        columns={columns}
        rows={rows}
        rowKey={(b) => b.branch_id}
        onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)}
        free
        footer={
          <tr>
            <td>{t('kad.br.total')}</td>
            <td>{formatNumber(kpis.plan)}</td>
            <td>{formatNumber(kpis.fact)}</td>
            <td>{kpis.vacancies === null ? t('dash.noValue') : formatNumber(kpis.vacancies)}</td>
            <td>{formatPct(kpis.fill, 0)}</td>
            <td>{formatMoney(kpis.payroll)}</td>
            <td>{mln(kpis.avg_salary)}</td>
          </tr>
        }
      />
    </Card>
  );
}
```

`frontend/src/sections/kadry/parts/HrRanks.tsx`:
```tsx
import type { HrBranchOut, HrKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct } from '../../../dash/money';
import { formatHours, formatPeople } from '../../../dash/people';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

interface RankProps {
  rows: HrBranchOut[];
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** Prototip «Вакансии по филиалам»: незанятые штатные единицы. */
export function VacancyRank({ rows, filters, onBranch, className }: RankProps) {
  const title = t('kad.vac.title');
  const items = rows
    .filter((b) => (b.vacancies ?? 0) > 0)
    .sort((a, b) => (b.vacancies ?? 0) - (a.vacancies ?? 0))
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.vacancies ?? 0, note: t('kad.vac.note', { pct: formatPct(b.fill === null ? null : 1 - b.fill, 1) }) }));
  return (
    <Card className={className} title={title} sub={t('kad.vac.sub')}>
      <div title={formula('vacancies')}>
        <Rank label={title} items={items} format={(v) => formatPeople(v)} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
      </div>
    </Card>
  );
}

/** Prototip «Средняя зарплата по филиалам» (млн сум в месяц). */
export function AvgSalaryRank({ rows, filters, onBranch, className }: RankProps) {
  const title = t('kad.avg.title');
  const items = rows
    .filter((b) => b.avg_salary !== null)
    .sort((a, b) => (b.avg_salary ?? 0) - (a.avg_salary ?? 0))
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.avg_salary ?? 0, note: formatPeople(b.fact) }));
  return (
    <Card className={className} title={title} sub={t('kad.avg.sub')}>
      <div title={formula('avgSalary')}>
        <Rank label={title} items={items} format={(v) => t('kad.money.mln', { value: formatNumber(v, 1) })} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
      </div>
    </Card>
  );
}

/** Prototip «ФОТ по филиалам»: выплаты за период. */
export function PayrollRank({ rows, filters, onBranch, className }: RankProps) {
  const title = t('kad.pay.title');
  const items = [...rows].sort((a, b) => b.payroll - a.payroll).map((b) => ({ id: b.branch_id, name: b.name, value: b.payroll }));
  return (
    <Card className={className} title={title} sub={t('kad.pay.sub')}>
      <Rank label={title} items={items} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
    </Card>
  );
}

/** Prototip «Доля ФОТ в расходовании». */
export function PayrollShareCard({ kpis, className }: { kpis: HrKpisOut; className?: string }) {
  const share = kpis.payroll_share;
  return (
    <Card className={className} title={t('kad.share.title')} sub={t('kad.share.sub')}>
      <div className="bigline" title={formula('payroll')}>
        <b>{formatPct(share, 1)}</b>
        <span>{t('kad.share.of', { payroll: formatMoney(kpis.payroll), total: formatMoney(kpis.outflow) })}</span>
      </div>
      <div className="prog__t" aria-hidden="true">
        <i style={{ width: `${Math.min(100, Math.max(0, (share ?? 0) * 100))}%` }} />
      </div>
    </Card>
  );
}

/** Prototip «Сверхурочные часы»: всего и на работника, по филиалам. */
export function OvertimeCard({ kpis, rows, filters, onBranch, className }: RankProps & { kpis: HrKpisOut }) {
  const title = t('kad.ot.title');
  const items = rows
    .filter((b) => b.overtime > 0)
    .sort((a, b) => b.overtime - a.overtime)
    .map((b) => ({ id: b.branch_id, name: b.name, value: b.overtime, note: t('kad.ot.perBranch', { hours: formatNumber(b.overtime_per_employee ?? 0, 1) }) }));
  return (
    <Card className={className} title={title} sub={t('kad.ot.sub')}>
      <div className="bigline" title={formula('overtime')}>
        <b>{formatHours(kpis.overtime)}</b>
        <span>{t('kad.ot.per', { hours: formatNumber(kpis.overtime_per_employee ?? 0, 1) })}</span>
      </div>
      <Rank label={title} items={items} format={(v) => formatHours(v)} onSelect={(id) => toggleBranch(filters, Number(id), onBranch)} activeId={filters.br} />
    </Card>
  );
}
```

`frontend/src/sections/kadry/parts/MovesCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { HrMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { formatPeople } from '../../../dash/people';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `movCard`: приём и увольнение по месяцам. */
export function MovesCard({ months, ctx, className }: { months: HrMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('kad.mov.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const hired = COLORS.in();
  const fired = COLORS.out();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('kad.mov.hired'), data: months.map((m) => m.hired), color: hired },
          { label: t('kad.mov.fired'), data: months.map((m) => m.fired), color: fired },
        ],
        format: (v) => formatPeople(v),
      }),
    [months, hired, fired],
  );
  const table = { headers: [t('kad.fot.month'), t('kad.mov.hired'), t('kad.mov.fired')], rows: months.map((m) => [monthShort(m.month_id), m.hired, m.fired]) };
  return (
    <Card className={className} title={title} sub={t('kad.mov.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('staffTurnover')}>
        <span>
          <i style={{ background: hired }} />
          {t('kad.mov.hired')}
        </span>
        <span>
          <i style={{ background: fired }} />
          {t('kad.mov.fired')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} format={(v) => formatPeople(v)} />
    </Card>
  );
}
```

`frontend/src/sections/kadry/parts/TurnoverTable.tsx`:
```tsx
import type { HrBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

const TURN_HIGH = 0.08; // TZ 4 qoidasi «Текучесть > 8%»

/** Prototip «Текучесть по филиалам»: принято, уволено, текучесть (без пересчёта на год — TZ). */
export function TurnoverTable({ rows, ctx, filters, onBranch, className }: { rows: HrBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('kad.turn.title');
  const headers = [t('kad.br.branch'), t('kad.turn.hired'), t('kad.turn.fired'), t('kad.turn.rate'), t('kad.turn.fact')];
  const columns: Column<HrBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (b) => b.name, sortValue: (b) => b.name, wrap: true },
    { key: 'hired', header: headers[1] ?? '', cell: (b) => formatNumber(b.hired), sortValue: (b) => b.hired, align: 'right' },
    { key: 'fired', header: headers[2] ?? '', cell: (b) => formatNumber(b.fired), sortValue: (b) => b.fired, align: 'right' },
    {
      key: 'rate',
      header: headers[3] ?? '',
      cell: (b) => (
        <span className={cx('exec', b.turnover !== null && b.turnover > TURN_HIGH && 'neg')}>
          {formatPct(b.turnover, 1)}
          <i aria-hidden="true">
            <b style={{ width: `${Math.min(100, Math.max(0, (b.turnover ?? 0) * 300))}%` }} />
          </i>
        </span>
      ),
      sortValue: (b) => b.turnover,
      align: 'right',
    },
    { key: 'fact', header: headers[4] ?? '', cell: (b) => formatNumber(b.fact), sortValue: (b) => b.fact, align: 'right' },
  ];
  return (
    <Card className={className} title={title} sub={t('kad.turn.sub')} exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((b) => [b.name, b.hired, b.fired, b.turnover === null ? null : Math.round(b.turnover * 1000) / 10, b.fact]) })} />}>
      <div title={formula('staffTurnover')}>
        <Table caption={title} columns={columns} rows={rows} rowKey={(b) => b.branch_id} onRowClick={(b) => toggleBranch(filters, b.branch_id, onBranch)} free />
      </div>
    </Card>
  );
}
```

- [ ] **Step 5: Implementatsiya — sahifalar**

`frontend/src/sections/kadry/svod.tsx`:
```tsx
import type { KadrySvodOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CategoriesCard } from './parts/CategoriesCard';
import { FotCard } from './parts/FotCard';
import { HrBranchesTable } from './parts/HrBranchesTable';
import { HrKpis } from './parts/HrKpis';
import { NoStaff } from './parts/NoStaff';

export default function KadrySvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadrySvodOut>('/kadry/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : <NoStaff />}
          <div className="grid">
            <FotCard className="c8" months={data.months} ctx={ctx} />
            <CategoriesCard className="c4" categories={data.categories} />
            <HrBranchesTable className="c12" rows={data.branches} kpis={data.kpis} ctx={ctx} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/kadry/chislennost.tsx`:
```tsx
import type { KadryChislennostOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CategoriesCard } from './parts/CategoriesCard';
import { HrBranchesTable } from './parts/HrBranchesTable';
import { HrKpis } from './parts/HrKpis';
import { VacancyRank } from './parts/HrRanks';
import { NoStaff } from './parts/NoStaff';

export default function KadryChislennost({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadryChislennostOut>('/kadry/chislennost', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : <NoStaff />}
          <div className="grid">
            <HrBranchesTable className="c12" rows={data.branches} kpis={data.kpis} ctx={ctx} filters={filters} onBranch={onBranch} />
            <CategoriesCard className="c6" categories={data.categories} />
            <VacancyRank className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/kadry/fot.tsx`:
```tsx
import type { KadryFotOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { FotCard } from './parts/FotCard';
import { HrKpis } from './parts/HrKpis';
import { AvgSalaryRank, PayrollRank, PayrollShareCard } from './parts/HrRanks';

export default function KadryFot({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadryFotOut>('/kadry/fot', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          <div className="grid">
            <FotCard className="c8" months={data.months} ctx={ctx} />
            <PayrollShareCard className="c4" kpis={data.kpis} />
            <AvgSalaryRank className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
            <PayrollRank className="c6" rows={data.branches} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/kadry/dvizhenie.tsx`:
```tsx
import type { KadryDvizhenieOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { HrKpis } from './parts/HrKpis';
import { OvertimeCard } from './parts/HrRanks';
import { MovesCard } from './parts/MovesCard';
import { NoStaff } from './parts/NoStaff';
import { TurnoverTable } from './parts/TurnoverTable';

export default function KadryDvizhenie({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KadryDvizhenieOut>('/kadry/dvizhenie', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <HrKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : <NoStaff />}
          <div className="grid">
            <MovesCard className="c8" months={data.months} ctx={ctx} />
            <OvertimeCard className="c4" kpis={data.kpis} rows={data.branches} filters={filters} onBranch={onBranch} />
            <TurnoverTable className="c12" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/kadry` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: 5 test passed; tsc va eslint xatosiz.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Кадры» — Сводка, Численность, Оплата труда, Движение кадров (faqat agregatlar)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 22: E2E — «Закупки», «Инвестиции», «Кадры», filial doirasi va CSP; to'liq tekshiruv, spec holati

**Files:**
- Create: `frontend/e2e/specs/zakupki-investicii-kadry.spec.ts`
- Modify: `docs/superpowers/specs/2026-09-25-s4-zakupki-investicii-kadry-design.md` (holat)
- Test: `frontend/e2e/specs/zakupki-investicii-kadry.spec.ts`

**Interfaces:**
- Consumes: 3-reja E2E (`signIn`, `adminFor`, `expectNoHorizontalScroll`, `e2e_branch` — `economist_filiala`, filial 3 «Каскад Чирчикских ГЭС»; loyihalar `mobile-390`, `tablet-1024`, `desktop-1440`), S1 `scripts/e2e.sh` (sintetik to'liq yuklash — endi xarid, АИП va kadrlar ham); dev stack'da `HR_BASE_URL` va `ONEC_BASE_URL` bo'sh.
- Produces: E2E ssenariylari.

- [ ] **Step 1: E2E ssenariysini yozish**

`frontend/e2e/specs/zakupki-investicii-kadry.spec.ts`:
```ts
import { expect, test, type Page } from '@playwright/test';
import { adminFor, expectNoHorizontalScroll, signIn } from '../fixtures';

const PERSONAL = /^(.*_)?(fio|full_?name|first_?name|last_?name|middle_?name|surname|pinfl|passport|phone|email)(_.*)?$/i;

function watchCsp(page: Page): string[] {
  const violations: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to/i.test(text)) violations.push(text);
  });
  return violations;
}

async function open(page: Page, hash: string, heading: string | RegExp): Promise<void> {
  await page.goto(`/${hash}`);
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
}

function keys(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(keys);
  if (value && typeof value === 'object') return Object.entries(value).flatMap(([k, v]) => [k, ...keys(v)]);
  return [];
}

test('Закупки: сводка, лоты с фильтром, поставщики, экономия', async ({ page }, info) => {
  const csp = watchCsp(page);
  await page.goto('/#zakupki/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Закупки: сводка' })).toBeVisible();
  await expect(page.getByText('Заключено договоров')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Заключённые договоры по месяцам' })).toBeVisible();
  await expectNoHorizontalScroll(page);

  await open(page, '#zakupki/loty?per=ytd', 'Лоты');
  await page.getByRole('button', { name: 'Просроченные' }).click();
  await expect(page.getByRole('table', { name: 'Лоты' }).locator('.badge--neg').first()).toBeVisible();
  await open(page, '#zakupki/postavshiki', 'Договоры и поставщики');
  await expect(page.getByRole('table', { name: 'Закупки по филиалам' })).toBeVisible();
  await open(page, '#zakupki/ekonomiya', 'Экономия');
  await expect(page.getByRole('table', { name: 'Экономия по способам закупки' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  expect(csp).toEqual([]);
});

test('Инвестиции: сводка, реестр объектов, источники, риски; филиал без объектов', async ({ page }, info) => {
  const csp = watchCsp(page);
  await page.goto('/#investicii/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Инвестиции: сводка' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Освоение нарастающим итогом' })).toBeVisible();
  await open(page, '#investicii/obekty', 'Объекты');
  if (info.project.name === 'desktop-1440') {
    await expect(page.getByRole('table', { name: 'Реестр объектов' }).locator('tbody tr')).toHaveCount(14);
  }
  await open(page, '#investicii/istochniki', 'Источники и освоение');
  await expect(page.getByRole('list', { name: 'Освоение по объектам' })).toBeVisible();
  await open(page, '#investicii/riski', 'Сроки и риски');
  await expect(page.getByText('Этапы и сроки')).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.goto('/#investicii/svod?br=1');
  await expect(page.getByText('У выбранного филиала нет объектов адресной программы.')).toBeVisible();
  expect(csp).toEqual([]);
});

test('Кадры: сводка, численность, оплата труда, движение', async ({ page }, info) => {
  const csp = watchCsp(page);
  await page.goto('/#kadry/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Кадры: сводка' })).toBeVisible();
  await expect(page.getByText('Штатная численность')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Фонд оплаты труда по месяцам' })).toBeVisible();
  await open(page, '#kadry/chislennost', 'Численность');
  await expect(page.getByRole('list', { name: 'Вакансии по филиалам' })).toBeVisible();
  await open(page, '#kadry/fot', 'Оплата труда');
  await expect(page.getByText('Доля ФОТ в расходовании')).toBeVisible();
  await open(page, '#kadry/dvizhenie', 'Движение кадров');
  await expect(page.getByRole('table', { name: 'Текучесть по филиалам' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  expect(csp).toEqual([]);
});

test('Экономист филиала: только свои кадры, без закупок и инвестиций, без персональных полей', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'bitta kenglik yetarli');
  await page.goto('/#kadry/chislennost');
  await signIn(page, 'e2e_branch');
  const table = page.getByRole('table', { name: 'Численность по филиалам' });
  await expect(table).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.getByText('Каскад Чирчикских ГЭС')).toBeVisible();
  expect((await page.request.get('/api/v1/zakupki/svod')).status()).toBe(403);
  expect((await page.request.get('/api/v1/investicii/svod')).status()).toBe(403);
  expect((await page.request.get('/api/v1/kadry/svod?br=2')).status()).toBe(403);
  const own = await page.request.get('/api/v1/kadry/chislennost');
  expect(own.status()).toBe(200);
  const body = (await own.json()) as { branches: Array<{ branch_id: number }> };
  expect(body.branches.map((b) => b.branch_id)).toEqual([3]);
  expect(keys(body).filter((k) => PERSONAL.test(k))).toEqual([]);
});
```
(Sahifa sarlavhasi — 3-reja `SectionScreen`: «Сводка» uchun `«<bo'lim>: сводка»`, qolganlari — menyudagi nom. `e2e_branch` — `economist_filiala` (TZ 1: «Кадры» ochiq, «Закупки»/«Инвестиции» — yo'q, `scope_all = false`).)

- [ ] **Step 2: To'liq tekshiruv**

```bash
docker compose -f deploy/compose.yml up -d --build
$TEST pytest -q
$TEST ruff check app tests && $TEST mypy app
$NODE npm run check
./scripts/e2e.sh
./scripts/prod_config.sh
grep -rn "hr-api.uzgidro.uz\|xarid.uzex.uz" backend/tests || echo "testlarda haqiqiy domen yo'q"
```
Expected: backend testlari passed (qamrov darvozasi 4-rejadagidek); frontend `check` passed; Playwright — 3 loyihada `zakupki-investicii-kadry.spec.ts` va S1–S3 spec'lari passed (filial testi faqat 1440 da), CSP buzilishi yo'q; `prod-config: OK`. Testlar faqat `hr.test`, `1c.test` va `httpx.MockTransport` bilan ishlaydi — tarmoqqa chiqish yo'q; `grep` — «testlarda haqiqiy domen yo'q».

- [ ] **Step 3: Spec holati**

`docs/superpowers/specs/2026-09-25-s4-zakupki-investicii-kadry-design.md` — `- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)` qatorini almashtiring:
```markdown
- Holat: amalga oshirilgan (S4-reja: docs/superpowers/plans/2026-09-25-08-s4-zakupki-investicii-kadry.md); ochiq savollar 1–6 (xarid portali formati, normativlar, АИП manbai, HR API kengaytmasi, chegaralar, ФОТ statyalari) mijozda
```

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e docs/superpowers/specs
git commit -m "test(e2e): «Закупки», «Инвестиции», «Кадры» sahifalari, filial doirasi, shaxsiy maydonlar va CSP; S4 spec holati

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
