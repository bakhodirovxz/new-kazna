# UGEKAZNA S3-reja: «Производство» + «Склад» + АСКУЭ (ГЭС) + 1C ombori — implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TZ 3-bosqichi: «Производство» (3 sahifa) va «Склад» (4 sahifa) витрина агрегатлари ustida, 4 ta qoida, ishlab chiqarish ko'rsatkichlari bilan ГЭС xaritasi, АСКУЭ kunlik eksporti konnektori, treplex.uz jonli quvvat vidjeti va 1C `hs/sklad` ombor konnektori.

**Architecture:** Backend 2-reja freymvorkiga 4 ta `mart` agregatini qo'shadi (`agg_generation_month`, `agg_energy_sales_month`, `agg_stock_month`, `agg_stock_positions`); `/proizvodstvo/*` va `/sklad/*` endpointlari S1 bo'lim qatlami (`SQ`, `BranchSel`, `Cache.respond`) va `app/sections/queries/{production,stock,power}.py` orqali ishlaydi; qoidalar S1 `app/alerts` reyestriga. Manbalar 2-reja `SourceConnector` protokolida: `AskueConnector` (kanonik CSV, `AskueExport` interfeysi), `OneCSkladConnector` (S1 `OneCClient`), sintetik oilalar; jonli quvvat esa Runner'siz poller (`app.etl.askue.live.poll_power`, `GesLiveClient`) → `dwh.fact_power_snapshot` → `pub.power_latest`. Frontend S1 `src/dash` bloklari bilan `src/sections/{proizvodstvo,sklad}/*.tsx`; ГЭС xaritasi `src/dash/map/` ga ko'chiriladi va ikkala bo'limda ishlatiladi.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (sync) + psycopg 3, PostgreSQL 16, Redis 7, httpx, pydantic 2, APScheduler 3, pytest; React 18 + TypeScript strict, TanStack Query 5, Chart.js 4, Vitest + Testing Library + axe, Playwright 1.49.1.

**Spec:** [docs/superpowers/specs/2026-09-25-s3-proizvodstvo-sklad-design.md](../specs/2026-09-25-s3-proizvodstvo-sklad-design.md). Asos: 1-reja [2026-09-24-01-backend-yadro.md](2026-09-24-01-backend-yadro.md) (`Ctx`, `require_perm`, `AuditAction`, `record`, `Section`, `section_perm`), 2-reja [2026-09-24-02-vitrina-etl.md](2026-09-24-02-vitrina-etl.md) (`TARGETS`, `merge_*`, `register(Aggregate)`, `_MONTHS`, `BuildParams`, `builds`, `Runner`, `compute_window`, `run_checks` — `capacity_limit`, `ALERT_RULES` seed'lari, `SyntheticConnector`, `FAMILIES`, `SynthModel`, `FileConnector`, `make_connector`, `KNOWN_SOURCES`, `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `current_setting`, `_cron`, `Notification`, `tests.etl_helpers`, `published_synthetic`, worker), 3-reja [2026-09-24-03-frontend.md](2026-09-24-03-frontend.md) (qobiq, `SectionPageProps`, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Badge`, `EmptyState`, `mockApi`, `renderWithProviders`, E2E fixture'lari), 4-reja [2026-09-25-04-ops-security.md](2026-09-25-04-ops-security.md) (`compose.prod.yml`, `egress`, `prod_config.sh`, `host-hardening.md`), S1-reja [2026-09-25-05-s1-obzor-kazna.md](2026-09-25-05-s1-obzor-kazna.md) (`SQ`, `SectionQuery`, `BranchSel`, `ReportPeriod`, `resolve_period`, `fmt_*`, `plural`, `schemas._Out/period_out/StationOut`, `obzor.stations`, `app.alerts` reyestri, `tests.s1_helpers.rebuild/SCENARIO_PARAMS`, `OneCClient`, `verify_setting`, `OrgMap`, `stable_code`, `to_mln`, `onec.models.parse`, `onec.orgs`, `src/dash/*`, `GesMap`, `StationPanel`, `useSection`, `SectionData`, `toggleBranch`), S2-reja [2026-09-25-06-s2-kredity-banki.md](2026-09-25-06-s2-kredity-banki.md) (`ReportingSink`, `DbStagingSink.error`, `notify_bank_errors`, `Settings.egress_proxy`, `NamedAmountOut`, `banks.admin._put`, `tests.s2_helpers.put_setting/put_rule`). 1–4-rejalar, S1 va S2 bajarilgan deb hisoblanadi (oxirgi migratsiya — `0012`).

## Global Constraints

- 1–4-rejalar, S1 va S2 rejalarining barcha Global Constraints'lari amal qiladi (Python `>=3.12`, hash bilan qulflangan bog'liqliklar, sirlar faqat Docker secrets, UTC, `/api/v1`, xato formati `{"error": {code, message, request_id, params?}}`, ruscha UI matnlari, o'zbekcha reja prozasi va izohlar).
- Backend testlari: `TEST="docker compose -f deploy/compose.test.yml run --rm test"`, keyin `$TEST pytest …` — haqiqiy PostgreSQL 16 va Redis; DB mock qilinmaydi. Frontend: `NODE="docker compose -f deploy/compose.frontend.yml run --rm node"`, keyin `$NODE npm …`; host Node ishlatilmaydi. Git Bash'da bind-mount'li `docker run` oldidan `MSYS_NO_PATHCONV=1`.
- Birliklar: ishlab chiqarish (`generation`, `own_needs`, `supply`, `plan`) — **mln kVt·soat** (`numeric(20,3)`); quvvat — MVt; pul — mln so'm `numeric(20,2)`; `date_id` = `YYYYMMDD`, `month_id` = `YYYYMM`; АСКУЭ CSV — MVt·soat (÷ 1000).
- Formulalar — spec 4-bo'lim (TZ 4) aynan: Отпуск = выработка − собственные нужды; КИУМ = выработка × 1000 / Σ(мощность × часы); Оборачиваемость = стоимость / (расход за период / число дней). Stansiya = `dim_branch.kind ∈ ('ges', 'cascade')`.
- UI faqat `pub.*` view'larni o'qiydi (TZ 9). Yangi `mart` jadvali: `build_id → core.builds ON DELETE CASCADE`, `month_id` ustuni, `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `core.rls_branch_ok(branch_id)`; `pub` view `security_invoker = true`, faqat aktiv build (jonli snapshot view'idan tashqari).
- Bo'lim endpointi: `GET`, `SQ` (`br ≥ 1 | None`, `per`), router darajasida `require_perm(section:<id>:view)`, `cache.respond("<bo'lim>.<sahifa>", filters, loader)`; har yangi route `tests/test_route_guards.py` `EXPECTED_ROUTES` ga, prefiks `PREFIX_PERMS` ga.
- Migratsiyalar: `0013_mart_production` (`down_revision = "0012"`), `0014_mart_stock` (`"0013"`), `0015_power_snapshot` (`"0014"`).
- «Требует внимания» chegaralari faqat `core.alert_rules` dan; ma'lumot yo'q bo'lsa qoida `None` qaytaradi.
- Tashqi HTTP (treplex.uz) va 1C — faqat `worker`, `httpx` (`trust_env=False`, `follow_redirects=False`, TLS tekshiruvi, javob hajmi chegarasi), treplex uchun ixtiyoriy `EGRESS_PROXY`; testlarda faqat `httpx.MockTransport`, tarmoqqa chiqish yo'q. treplex.uz va 1C'ga jonli so'rov (qo'lda ham) reja ijrosida yuborilmaydi.
- 1C ombor hisobi — alohida sirlar `onec_sklad_username`, `onec_sklad_password` (faqat `worker`); qiymati log/xato matni/auditga yozilmaydi.
- Credential fayllari (`1C.1/secrets.php`, `auth.php`, `auth.js`, `apache-proxy.conf`, `gazna_bot/config.py`, `.env`, `deploy/secrets/`) ochilmaydi va hech qayerga ko'chirilmaydi.
- Frontend: `src/sections/<bo'lim>/*.tsx` — faqat sahifalar, yordamchilar `src/sections/<bo'lim>/parts/` va `src/dash/`; barcha matnlar `t()` orqali (`src/i18n/ru.ts` oxiriga); CSP o'zgarmaydi (inline `<style>` yo'q).
- Commit xabari oxirida bo'sh qatordan keyin: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Spec'dan ongli chetlanishlar yo'q; S3 qarorlari — spec 11-bo'lim.

## Review Focus

1. **Yopilmagan oy tanlangan (`m09`, 24-sentabr)** — reja 24/30 ulushi bilan, o'tgan yil 1–24-sentabr 2025 bo'yicha, КИУМ 24 kunlik soatlar bilan; kutiladi: bajarilish yolg'on past chiqmaydi — 5-vazifa `test_open_month_prorates_plan_and_compares_same_days`.
2. **Bosh tashkilot (HQ) yoki stansiyasi yo'q filial tanlangan** — kutiladi: `has_stations = false`, nolga bo'lish yo'q, sahifa tushuntirish chiqaradi, ishlab chiqarish qoidalari yonmaydi — 7-vazifa `test_hq_has_no_stations`, 9-vazifa `test_production_rules_skip_without_data`, 16-vazifa `HQ selected shows the no-stations message`.
3. **АСКУЭ fayli buzilgan** (BOM, noto'g'ri sarlavha, manfiy son, noma'lum stansiya, sutkalik ishlab chiqarish > quvvat × 24) — kutiladi: yaroqli qatorlar yuklanadi, xatolar `core.etl_error` + bitta xabar; quvvatdan oshsa sifat tekshiruvi 4 publish'ni to'xtatadi — 10-vazifa `test_row_errors_do_not_stop_parsing`, 11-vazifa `test_bad_rows_are_reported_not_fatal`, `test_unknown_station_is_reported`, `test_runner_rejects_generation_above_capacity`.
4. **Jonli manba ishlamaydi yoki eskirgan** — kutiladi: oxirgi snapshot o'chmaydi, vidjet «устарело» ko'rsatadi, sahifa xatoga tushmaydi; manba sozlanmagan — «Источник не подключён» — 12-vazifa `test_poll_failure_keeps_last_snapshot`, `test_moshchnost_stale_and_empty`, 16-vazifa `PowerCard shows stale and missing source`.
5. **1C ombori faqat subschyot qoldiqlarini beradi** (minimum va oxirgi harakat sanasi yo'q — prod'dagi haqiqiy holat) — kutiladi: minimum/неликвид qoidalari yolg'on yonmaydi, UI «Источник не подключён», qiymat va oborot ko'rinadi — 9-vazifa `test_stock_rules_skip_without_min_or_age`, 13-vazifa `test_current_shape_loads_account_level_stock`, 17-vazifa `Минимальный запас: coverage bar and missing minimum data`.

---

## Fayl tuzilishi

```
backend/app/core/config.py                    askue_*, onec_sklad_* sozlamalari, problems()
backend/app/dwh/reference.py                  S3 sozlamalari (askue.*, onec.sklad_months, etl.*_cron)
backend/app/etl/notify.py                     Kind += askue_rows_rejected
backend/migrations/versions/0013_mart_production.py, 0014_mart_stock.py, 0015_power_snapshot.py
backend/app/dwh/production_aggregates.py      agg_generation_month, agg_energy_sales_month
backend/app/dwh/stock_aggregates.py           agg_stock_month, agg_stock_positions
backend/app/dwh/aggregates.py                 oxirida importlar
backend/app/etl/synthetic/families/production.py, stock.py (+ families/__init__.py)
backend/app/sections/queries/production.py, stock.py, power.py
backend/app/sections/production_schemas.py, stock_schemas.py, proizvodstvo.py, sklad.py
backend/app/sections/schemas.py, obzor.py     StationProductionOut, xarita uchun ishlab chiqarish
backend/app/alerts/production.py, stock.py (+ __init__.py)
backend/app/etl/askue/                        registry, canonical, export, connector, live, admin
backend/app/etl/onec/sklad_models.py, sklad.py
backend/app/etl/runner.py                     connector.lookback_months
backend/app/etl/connectors.py, app/worker.py, app/cli.py, app/main.py
backend/tests/s3_helpers.py, tests/fixtures/askue/*, tests/fixtures/onec_sklad/*
deploy/compose.prod.yml, deploy/prod.env.example, deploy/secrets.example/README.md, scripts/prod_config.sh
docs/integration/askue-format.md, askue-connector.md, proizvodstvo-fayl.md, 1c-sorov-s3.md; docs/ops/host-hardening.md
frontend/src/api/types.ts, openapi.json, src/api/schema.d.ts
frontend/src/dash/chart.tsx, energy.ts, formulas.ts, map/ (S1 obzor/map'dan ko'chiriladi)
frontend/src/i18n/ru.ts, src/test/s3Fixtures.ts
frontend/src/sections/obzor/svod.tsx, obzor/map/StationPanel.tsx
frontend/src/sections/proizvodstvo/{svod,stancii,realiz}.tsx, proizvodstvo/parts/*
frontend/src/sections/sklad/{svod,ostatki,minimum,nelikvid}.tsx, sklad/parts/*
frontend/e2e/specs/proizvodstvo-sklad.spec.ts
```

Vazifalar tartibi: 1 (sozlamalar) → 2 (sintetik) → 3–4 (agregatlar) → 5–6 (so'rovlar) → 7–8 (API) → 9 (qoidalar) → 10–11 (АСКУЭ) → 12 (jonli quvvat) → 13 (1C ombor) → 14 (ekspluatatsiya, hujjatlar) → 15 (frontend asoslari, xarita) → 16–17 (sahifalar) → 18 (E2E).

---
### Task 1: S3 sozlamalari, konfiguratsiya, stansiyalar moslashtirishi modeli, xabarnoma turi

**Files:**
- Create: `backend/app/etl/askue/__init__.py`, `backend/app/etl/askue/registry.py`
- Modify: `backend/app/core/config.py`, `backend/app/dwh/reference.py`, `backend/app/etl/notify.py` (`Kind`), `backend/tests/test_reference.py` (kutilgan kalitlar)
- Test: `backend/tests/test_s3_prereq.py`

**Interfaces:**
- Consumes: `Settings`, `ConfigError`, `SecretStr`, `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `_cron`, `Notification`.
- Produces:
  - `app.etl.askue.registry`: `STATION_KINDS = ("ges", "cascade")`, `normalize_name(text) -> str` (bo'shliqlar siqiladi, `casefold`, apostrof variantlari `'` ga), `AskueStation` (pydantic, frozen: `code` `^[A-Za-z0-9_.-]{1,40}$`, `name` 1–200, `branch_code` 1–32), `validate_stations(value: list[AskueStation]) -> list[dict[str, str]]` (kod va normallashtirilgan nom takrorlanmaydi).
  - `Settings`: `askue_inbox_dir = "/data/import/askue"`, `askue_live_url = ""`, `onec_sklad_base_url = ""`, `onec_sklad_username: SecretStr`, `onec_sklad_password: SecretStr`; `problems()` — `ASKUE_LIVE_URL` `https://` bilan boshlanmasa xato.
  - Sozlamalar: `askue.stations = []`, `askue.inbox_days = 7`, `askue.live_cron = "*/10 * * * *"`, `askue.live_keep_days = 35`, `askue.live_stale_minutes = 30`, `etl.askue_cron = "15 7 * * *"`, `onec.sklad_months = 13`, `etl.onec_sklad_full_cron = "30 3 * * *"`, `etl.onec_sklad_incremental_cron = "30 10,13,16 * * *"`.
  - `Notification.kind` += `"askue_rows_rejected"`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_s3_prereq.py`:
```python
from typing import Any

import pytest

from app.core.config import get_settings
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.etl.askue.registry import STATION_KINDS, AskueStation, normalize_name
from app.etl.notify import Notification

ST = {"code": "CHARVAK-1", "name": "Chorvoq GES", "branch_code": "UGE-02"}


def test_s3_settings_defaults() -> None:
    assert DEFAULT_SETTINGS["askue.stations"] == []
    assert DEFAULT_SETTINGS["askue.inbox_days"] == 7
    assert DEFAULT_SETTINGS["askue.live_keep_days"] == 35
    assert DEFAULT_SETTINGS["askue.live_stale_minutes"] == 30
    assert DEFAULT_SETTINGS["onec.sklad_months"] == 13
    for key, cron in (("askue.live_cron", "*/10 * * * *"), ("etl.askue_cron", "15 7 * * *"),
                      ("etl.onec_sklad_full_cron", "30 3 * * *"),
                      ("etl.onec_sklad_incremental_cron", "30 10,13,16 * * *")):
        assert DEFAULT_SETTINGS[key] == cron
        assert validate_setting(key, cron) == cron
    assert STATION_KINDS == ("ges", "cascade")


def test_s3_settings_validation() -> None:
    other = {"code": "CHARVAK-2", "name": "Chorvoq GES-2", "branch_code": "UGE-02"}
    assert validate_setting("askue.stations", [ST, other]) == [ST, other]
    bad: list[tuple[str, Any]] = [
        ("askue.stations", [ST, ST]),
        ("askue.stations", [ST, {**other, "name": "  chorvoq   ges "}]),  # nom takrori
        ("askue.stations", [{**ST, "code": "bad code"}]),
        ("askue.stations", [{**ST, "extra": 1}]),
        ("askue.stations", [{**ST, "branch_code": ""}]),
        ("askue.inbox_days", 0),
        ("askue.inbox_days", 61),
        ("askue.live_keep_days", 0),
        ("askue.live_stale_minutes", 1),
        ("onec.sklad_months", 0),
        ("onec.sklad_months", 37),
        ("etl.askue_cron", "daily"),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_station_model_and_normalization() -> None:
    station = AskueStation.model_validate(ST)
    assert (station.code, station.branch_code) == ("CHARVAK-1", "UGE-02")
    assert normalize_name("  To\u2018polang   GES ") == normalize_name("to'polang ges")
    assert normalize_name("Qodiriya\u00a0GESlari") == "qodiriya geslari"


def test_s3_config_and_notification_kind() -> None:
    base = get_settings()
    assert base.askue_inbox_dir == "/data/import/askue" and base.askue_live_url == ""
    assert base.onec_sklad_base_url == ""
    assert base.onec_sklad_username.get_secret_value() == ""
    plain = base.model_copy(update={"askue_live_url": "http://treplex.test/api/cascades/ges"})
    assert any("ASKUE_LIVE_URL" in p for p in plain.problems())
    good = base.model_copy(update={"askue_live_url": "https://treplex.test/api/cascades/ges"})
    assert not any("ASKUE_LIVE_URL" in p for p in good.problems())
    assert Notification("askue_rows_rejected", "s", "b").kind == "askue_rows_rejected"
```

`backend/tests/test_reference.py` — `test_settings_defaults_and_validation` dagi `assert set(DEFAULT_SETTINGS) == {…}` to'plamiga quyidagi 9 kalitni qo'shing (qolganlari o'zgarmaydi):
```python
        "askue.stations", "askue.inbox_days", "askue.live_cron", "askue.live_keep_days",
        "askue.live_stale_minutes", "etl.askue_cron", "onec.sklad_months",
        "etl.onec_sklad_full_cron", "etl.onec_sklad_incremental_cron",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_s3_prereq.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.askue'`.

- [ ] **Step 3: Stansiyalar moslashtirishi modeli**

`backend/app/etl/askue/__init__.py`:
```python
"""АСКУЭ integratsiyasi: kunlik eksport (kanonik CSV) va jonli quvvat (S3 spec 3.1–3.2)."""
```

`backend/app/etl/askue/registry.py`:
```python
"""АСКУЭ stansiyalari ↔ filiallar moslashtirishi (`askue.stations`) — sof konstantalar va model.

`code` — kunlik eksportdagi stansiya kodi, `name` — jonli manba (treplex.uz `ges`) nomi.
Bir filialga (kaskad) bir nechta stansiya bog'lanishi mumkin (S3 spec 3.1).
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

STATION_KINDS: tuple[str, ...] = ("ges", "cascade")
_APOSTROPHES = re.compile(r"[\u2018\u2019\u02bb\u02bc`\u00b4]")


def normalize_name(text: str) -> str:
    """Nomlarni solishtirish uchun: apostrof variantlari, bo'shliqlar, registr."""
    return " ".join(_APOSTROPHES.sub("'", text).split()).casefold()


class AskueStation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    code: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,40}$")]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]


def validate_stations(value: list[AskueStation]) -> list[dict[str, str]]:
    codes = [s.code for s in value]
    names = [normalize_name(s.name) for s in value]
    if len(set(codes)) != len(codes):
        raise ValueError("askue.stations: stansiya kodi takrorlangan")
    if len(set(names)) != len(names) or not all(names):
        raise ValueError("askue.stations: stansiya nomi bo'sh yoki takrorlangan")
    return [s.model_dump() for s in value]
```

- [ ] **Step 4: Sozlamalar**

`backend/app/dwh/reference.py` — importlarga qo'shing:
```python
from app.etl.askue.registry import AskueStation, validate_stations
```
`DEFAULT_SETTINGS` lug'ati oxiriga qo'shing:
```python
    "askue.stations": [],
    "askue.inbox_days": 7,
    "askue.live_cron": "*/10 * * * *",
    "askue.live_keep_days": 35,
    "askue.live_stale_minutes": 30,
    "etl.askue_cron": "15 7 * * *",
    "onec.sklad_months": 13,
    "etl.onec_sklad_full_cron": "30 3 * * *",
    "etl.onec_sklad_incremental_cron": "30 10,13,16 * * *",
```
`SETTING_TYPES` lug'ati oxiriga qo'shing:
```python
    "askue.stations": TypeAdapter(
        Annotated[list[AskueStation], AfterValidator(validate_stations)]),
    "askue.inbox_days": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=60)]),
    "askue.live_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "askue.live_keep_days": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=400)]),
    "askue.live_stale_minutes": TypeAdapter(Annotated[int, Field(strict=True, ge=5, le=1440)]),
    "etl.askue_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "onec.sklad_months": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=36)]),
    "etl.onec_sklad_full_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "etl.onec_sklad_incremental_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
```

- [ ] **Step 5: Konfiguratsiya va xabarnoma turi**

`backend/app/core/config.py` — `Settings` sinfida S2'ning `telegram_api_base` qatoridan keyin qo'shing:
```python
    # S3 (spec 3.1–3.3): АСКУЭ kunlik eksporti inbox'i (worker'da faqat o'qish), jonli quvvat
    # manbasi (treplex.uz, faqat https) va 1C ombor servisi (hs/sklad) — alohida Basic hisob
    # (Docker secrets onec_sklad_username, onec_sklad_password).
    askue_inbox_dir: str = "/data/import/askue"
    askue_live_url: str = ""
    onec_sklad_base_url: str = ""
    onec_sklad_username: SecretStr = SecretStr("")
    onec_sklad_password: SecretStr = SecretStr("")
```
`problems()` ichida oxirgi `return out` qatoridan OLDIN qo'shing:
```python
        if self.askue_live_url and not self.askue_live_url.startswith("https://"):
            out.append("ASKUE_LIVE_URL https:// bilan boshlanishi kerak")
```

`backend/app/etl/notify.py` — `Kind` qatorini almashtiring:
```python
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data", "bank_rows_rejected",
               "askue_rows_rejected"]
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_s3_prereq.py tests/test_reference.py tests/test_config.py tests/test_notify.py -v`
Expected: barcha testlar passed. `$TEST ruff check app tests` va `$TEST mypy app` — xatosiz.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(s3): АСКУЭ stansiyalari modeli, S3 sozlamalari, 1C ombor va jonli manba konfiguratsiyasi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 2: `SyntheticConnector` — ishlab chiqarish, realizatsiya va ombor oilalari

**Files:**
- Create: `backend/app/etl/synthetic/families/production.py`, `backend/app/etl/synthetic/families/stock.py`
- Modify: `backend/app/etl/synthetic/families/__init__.py` (`FAMILIES`), `backend/tests/test_synthetic.py` (maqsadlar to'plami)
- Test: `backend/tests/test_synthetic_s3.py`

**Interfaces:**
- Consumes: `SynthModel` (`seed`, `as_of`, `months()`, `period_end(month)`), `BRANCHES`, `BranchRef`, `HQ_ID`, `NOMENCLATURE`, `STOCK_CATEGORIES`, `rnd`, `money`, `date_id`, `month_id`, `StagingSink`, `Window`.
- Produces:
  - `families.production`: `CF` (12 oylik КИУМ), `GEN_YEAR`, `BUYERS = (("CP-013", 0.85), ("CP-014", 0.15))`, `PLAN_DOC = "generation_plan"`, `DAILY_DOC = "synthetic_daily"`, `tariff(day) -> float`, `vol(x) -> Decimal` (3 kasr), `stations() -> list[BranchRef]` (15 ta, HQ'siz), `daily(model, branch, day) -> tuple[float, float, float]` (ishlab chiqarish, o'z ehtiyoji — mln kVt·soat, ish soatlari), `monthly_plan(model, branch, month) -> float`, `generate(model, window, sink) -> {"fact_generation": n, "fact_energy_sales": n}`. `src_id`: `GEN-{branch:02d}-{YYYYMMDD}`, `PLAN-{branch:02d}-{YYYYMM}`, `ES-{branch:02d}-{cp}-{YYYYMM}`.
  - `families.stock`: `UNIT_QTY`, `MOVE_DAY = 15`, `Position(nom, name, category, unit, price, typical, minimum)`, `warehouse(branch) -> str`, `pool(model, branch) -> list[Position]` (10 ta, HQ — 6), `generate(model, window, sink) -> {"fact_stock": n, "fact_stock_move": n}`. `src_id` oy bilan: `ST-{branch:02d}-{nom:03d}-{YYYYMM}` (partitsiyalangan faktda `src_id` sanadan mustaqil bo'lsa, 2-reja `_moved_sql` oldingi oylarni o'chirib yuboradi), `SM-{branch:02d}-{nom:03d}-{YYYYMM}-{in|out}`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_synthetic_s3.py`:
```python
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from app.etl.synthetic import SyntheticConnector
from app.etl.synthetic.families import production, stock
from app.etl.synthetic.model import SynthModel
from app.etl.synthetic.reference import BRANCHES, HQ_ID
from app.etl.types import Window
from tests.etl_helpers import TEST_AS_OF


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


WINDOW = Window(date(2026, 8, 1), TEST_AS_OF)
CAPACITY = {b.code: b.capacity for b in BRANCHES}
HQ_CODE = BRANCHES[HQ_ID - 1].code


def _collect(family: Any) -> list[tuple[str, dict[str, Any]]]:
    sink = CollectSink()
    family.generate(SynthModel(7, TEST_AS_OF), WINDOW, sink)
    return sink.rows


def test_generation_within_capacity_hq_excluded_plan_monthly() -> None:
    rows = _collect(production)
    gen = [r for t, r in rows if t == "fact_generation"]
    daily = [r for r in gen if r["doc_type"] == production.DAILY_DOC]
    plans = [r for r in gen if r["doc_type"] == production.PLAN_DOC]
    assert len(production.stations()) == 15
    assert HQ_CODE not in {r["branch_code"] for r in gen}
    for r in daily:
        cap = CAPACITY[r["branch_code"]]
        assert cap is not None and r["generation"] * 1000 <= Decimal(cap * 24)
        assert Decimal(0) < r["own_needs"] < r["generation"] and r["plan"] is None
        assert WINDOW.contains_id(r["date_id"])
    assert len(daily) == 15 * (31 + 24)
    assert sorted({r["date_id"] for r in plans}) == [20260801, 20260901]
    assert all(r["generation"] == 0 and r["plan"] > 0 for r in plans)


def test_sales_split_between_buyers_and_dated_at_period_end() -> None:
    sales = [r for t, r in _collect(production) if t == "fact_energy_sales"]
    assert {r["cp_code"] for r in sales} == {"CP-013", "CP-014"}
    assert {r["date_id"] for r in sales} == {20260831, 20260924}
    assert len(sales) == 15 * 2 * 2
    for r in sales:
        assert r["accrued"] > 0 and r["paid"] <= r["accrued"] * Decimal("1.031")
        assert r["volume"] > 0


def test_stock_snapshots_and_moves() -> None:
    rows = _collect(stock)
    snaps = [r for t, r in rows if t == "fact_stock"]
    moves = [r for t, r in rows if t == "fact_stock_move"]
    assert {r["date_id"] for r in snaps} == {20260831, 20260924}
    per_branch = {b.code: sum(1 for r in snaps if r["branch_code"] == b.code and
                              r["date_id"] == 20260831) for b in BRANCHES}
    assert per_branch[HQ_CODE] == 6 and all(v == 10 for k, v in per_branch.items() if k != HQ_CODE)
    for r in snaps:
        assert r["src_id"].endswith(str(r["date_id"] // 100))  # oy src_id ichida
        assert r["last_move_date_id"] < r["date_id"] and r["min_qty"] is not None
        assert r["value"] >= 0 and r["warehouse"]
    assert {r["direction"] for r in moves} == {"in", "out"}
    assert all(WINDOW.contains_id(r["date_id"]) and r["value"] > 0 for r in moves)
    assert {r["date_id"] for r in moves} == {20260815, 20260915}


def test_families_are_deterministic() -> None:
    assert _collect(production) == _collect(production)
    assert _collect(stock) == _collect(stock)


def test_extract_reports_s3_targets() -> None:
    sink = CollectSink()
    stats = SyntheticConnector(seed=7, as_of=TEST_AS_OF).extract(WINDOW, sink)
    for target in ("fact_generation", "fact_energy_sales", "fact_stock", "fact_stock_move"):
        assert stats.by_target[target] == sum(1 for t, _ in sink.rows if t == target), target
```

`backend/tests/test_synthetic.py` — `test_extract_respects_window_and_reports_all_targets` ichida `assert set(stats.by_target) == {` ni `assert set(stats.by_target) >= {` ga almashtiring (keyingi rejalar yangi maqsad qo'shadi; S1/S2 ijrosida allaqachon almashtirilgan bo'lsa — o'zgarishsiz qoldiring) va shu assert'dan keyin qo'shing:
```python
    assert {"fact_generation", "fact_energy_sales", "fact_stock",
            "fact_stock_move"} <= set(stats.by_target)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_synthetic_s3.py -v`
Expected: FAIL — `ImportError: cannot import name 'production' from 'app.etl.synthetic.families'`.

- [ ] **Step 3: Implementatsiya — ishlab chiqarish va realizatsiya**

`backend/app/etl/synthetic/families/production.py`:
```python
"""fact_generation (stansiya × sutka; oylik reja — oyning 1-kuni) va fact_energy_sales
(filial × xaridor × oy) — prototip «production data»: quvvat × 24 × oylik КИУМ × tebranish.

Birliklar: mln kVt·soat; realizatsiya — mln so'm (mln kVt·soat × so'm/kVt·soat).
Sutkalik ishlab chiqarish har doim ≤ quvvat × 24 (sifat tekshiruvi 4): 0,62 × 1,08 × 1,1 < 1.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, BranchRef
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

# Oylik КИУМ: prototip CF (yanvar…sentabr) + kuzgi kam suvli oylar.
CF = (0.28, 0.27, 0.33, 0.42, 0.55, 0.62, 0.60, 0.52, 0.40, 0.33, 0.30, 0.29)
GEN_YEAR = {2024: 0.88, 2025: 0.93}  # 2026 = 1,0 (prototip gen25 ≈ rejaning 0,82–1,0)
BUYERS = (("CP-013", 0.85), ("CP-014", 0.15))
PLAN_DOC = "generation_plan"
DAILY_DOC = "synthetic_daily"


def tariff(day: date) -> float:
    """So'm / kVt·soat (prototip TARIFF: 1-yarim yil 655, keyin 705; oldingi yillar arzonroq)."""
    base = 655.0 if day.month <= 6 else 705.0
    return base * {2024: 0.8, 2025: 0.9}.get(day.year, 1.0)


def vol(value: float) -> Decimal:
    return Decimal(f"{value:.3f}")


def stations() -> list[BranchRef]:
    return [b for b in BRANCHES if b.kind in ("ges", "cascade") and b.capacity]


def daily(model: SynthModel, branch: BranchRef, day: date) -> tuple[float, float, float]:
    capacity = branch.capacity or 0
    eff = rnd(model.seed, "eff", branch.id).uniform(0.9, 1.08)
    r = rnd(model.seed, "gen", branch.id, date_id(day))
    gen = (capacity * 24 * CF[day.month - 1] * eff * GEN_YEAR.get(day.year, 1.0)
           * r.uniform(0.9, 1.1) / 1000)
    return gen, gen * r.uniform(0.012, 0.02), 24 * r.uniform(0.85, 1.0)


def monthly_plan(model: SynthModel, branch: BranchRef, month: date) -> float:
    days = calendar.monthrange(month.year, month.month)[1]
    r = rnd(model.seed, "genplan", branch.id, month_id(month))
    return ((branch.capacity or 0) * 24 * days * CF[month.month - 1]
            * GEN_YEAR.get(month.year, 1.0) * r.uniform(0.97, 1.04) / 1000)


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    gen_rows = sales_rows = 0
    for branch in stations():
        for month in model.months():
            end = model.period_end(month)
            supply = 0.0
            day = month
            while day <= end:
                gen, own, hours = daily(model, branch, day)
                supply += gen - own
                if window.contains(day):
                    sink.add("fact_generation", {
                        "doc_type": DAILY_DOC, "src_id": f"GEN-{branch.id:02d}-{date_id(day)}",
                        "date_id": date_id(day), "branch_code": branch.code,
                        "generation": vol(gen), "own_needs": vol(own), "supply": vol(gen - own),
                        "plan": None, "work_hours": Decimal(f"{hours:.2f}")})
                    gen_rows += 1
                day += timedelta(days=1)
            if window.contains(month):
                # Oylik reja — oyning 1-kuni (spec 3.1); ochiq oyda agregat ulush bilan oladi.
                sink.add("fact_generation", {
                    "doc_type": PLAN_DOC, "src_id": f"PLAN-{branch.id:02d}-{month_id(month)}",
                    "date_id": date_id(month), "branch_code": branch.code,
                    "generation": Decimal("0.000"), "own_needs": Decimal("0.000"),
                    "supply": Decimal("0.000"), "plan": vol(monthly_plan(model, branch, month)),
                    "work_hours": None})
                gen_rows += 1
            if window.contains(end):
                accrued = supply * tariff(month)
                level = rnd(model.seed, "sales", branch.id, month_id(month)).uniform(0.8, 1.03)
                for cp, share in BUYERS:
                    sink.add("fact_energy_sales", {
                        "doc_type": "energy_sales",
                        "src_id": f"ES-{branch.id:02d}-{cp}-{month_id(month)}",
                        "date_id": date_id(end), "branch_code": branch.code, "cp_code": cp,
                        "accrued": money(accrued * share), "paid": money(accrued * share * level),
                        "volume": vol(supply * share)})
                    sales_rows += 1
    return {"fact_generation": gen_rows, "fact_energy_sales": sales_rows}
```

- [ ] **Step 4: Implementatsiya — ombor**

`backend/app/etl/synthetic/families/stock.py`:
```python
"""fact_stock (oy oxiri / as_of qoldig'i: nomenklatura × ombor) va fact_stock_move (oylik prixod
va rasxod) — prototip «warehouse data»: har filialda 10 (HQ — 6) pozitsiya, minimum ~9% hollarda
buziladi, harakatsiz kunlar 18% hollarda > 180.

`src_id` ichida oy bor: partitsiyalangan faktda bir xil `src_id` boshqa sanada kelsa, 2-reja merge
eski nusxani o'chiradi (hujjat sanasi o'zgargan deb) — oy bilan har oy o'z snapshot'ini saqlaydi.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import timedelta

from app.dwh.dates import date_id, month_id
from app.etl.synthetic.families.production import vol
from app.etl.synthetic.model import SynthModel, money
from app.etl.synthetic.reference import BRANCHES, HQ_ID, NOMENCLATURE, STOCK_CATEGORIES, BranchRef
from app.etl.synthetic.rng import rnd
from app.etl.types import StagingSink, Window

UNIT_QTY: dict[str, tuple[int, int]] = {
    "шт": (5, 80), "м": (200, 4000), "л": (500, 20000), "кг": (500, 15000),
    "компл": (20, 150), "пар": (30, 300),
}
MOVE_DAY = 15


@dataclass(frozen=True, slots=True)
class Position:
    nom: int  # NOMENCLATURE indeksi + 1 (kod NOM-001…)
    name: str
    category: str
    unit: str
    price: float  # mln so'm / birlik
    typical: float
    minimum: int


def warehouse(branch: BranchRef) -> str:
    return "Центральный склад" if branch.id == HQ_ID else f"Склад {branch.short}"


def pool(model: SynthModel, branch: BranchRef) -> list[Position]:
    hq = branch.id == HQ_ID
    picked = sorted(rnd(model.seed, "pool", branch.id).sample(range(len(NOMENCLATURE)),
                                                              6 if hq else 10))
    out: list[Position] = []
    for n in picked:
        name, cat, unit, price = NOMENCLATURE[n]
        r = rnd(model.seed, "typ", branch.id, n)
        lo, hi = UNIT_QTY[unit]
        typical = r.uniform(lo, hi) * (0.5 if hq else branch.weight)
        out.append(Position(n + 1, name, STOCK_CATEGORIES[cat], unit, price, typical,
                            round(typical * r.uniform(0.35, 0.7))))
    return out


def generate(model: SynthModel, window: Window, sink: StagingSink) -> dict[str, int]:
    stock_rows = move_rows = 0
    for branch in BRANCHES:
        wh = warehouse(branch)
        for pos in pool(model, branch):
            code = f"NOM-{pos.nom:03d}"
            for month in model.months():
                end = model.period_end(month)
                ym = month_id(month)
                r = rnd(model.seed, "stock", branch.id, pos.nom, ym)
                if r.random() < 0.09:
                    qty = round(pos.minimum * r.uniform(0.15, 0.9))
                else:
                    qty = round(pos.typical * r.uniform(0.8, 1.6))
                roll = r.random()
                age = (r.randint(181, 720) if roll < 0.18
                       else r.randint(91, 180) if roll < 0.43 else r.randint(1, 90))
                value = qty * pos.price
                if window.contains(end):
                    sink.add("fact_stock", {
                        "doc_type": "stock_snapshot",
                        "src_id": f"ST-{branch.id:02d}-{pos.nom:03d}-{ym}",
                        "date_id": date_id(end), "branch_code": branch.code, "nom_code": code,
                        "warehouse": wh, "qty": vol(qty), "value": money(value),
                        "min_qty": vol(pos.minimum),
                        "last_move_date_id": date_id(end - timedelta(days=age))})
                    stock_rows += 1
                day = min(month.replace(day=MOVE_DAY), end)
                part = end.day / calendar.monthrange(month.year, month.month)[1]
                if not window.contains(day):
                    continue
                for direction, lo, hi in (("in", 0.12, 0.22), ("out", 0.13, 0.21)):
                    amount = value * r.uniform(lo, hi) * part
                    if amount < 0.01:
                        continue
                    sink.add("fact_stock_move", {
                        "doc_type": "stock_move",
                        "src_id": f"SM-{branch.id:02d}-{pos.nom:03d}-{ym}-{direction}",
                        "date_id": date_id(day), "branch_code": branch.code, "nom_code": code,
                        "direction": direction, "qty": vol(amount / pos.price),
                        "value": money(amount)})
                    move_rows += 1
    return {"fact_stock": stock_rows, "fact_stock_move": move_rows}
```

- [ ] **Step 5: Reyestr**

`backend/app/etl/synthetic/families/__init__.py` — import qatoriga `production, stock` ni qo'shing (S1'dan keyingi holat):
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
    production,
    stock,
)
```
va `FAMILIES` ro'yxati oxiriga qo'shing:
```python
    ("production", production.generate),
    ("stock", stock.generate),
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_synthetic_s3.py tests/test_synthetic.py tests/test_synthetic_s1.py -v`
Expected: barcha testlar passed — 2-rejaning `test_full_synthetic_pipeline` sifat tekshiruvlari (jumladan `capacity_limit`, `mandatory_dims`) yangi qatorlar bilan ham `ok`, `test_incremental_rerun_changes_nothing` — `rows_upserted == 0` (oilalar deterministik).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(etl): sintetik ishlab chiqarish, realizatsiya va ombor oilalari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 3: Ishlab chiqarish agregatlari (0013) — oy × stansiya, quvvat SCD-2, reja ulushi, realizatsiya

**Files:**
- Create: `backend/migrations/versions/0013_mart_production.py`, `backend/app/dwh/production_aggregates.py`, `backend/tests/s3_helpers.py`
- Modify: `backend/app/dwh/aggregates.py` (oxirida import)
- Test: `backend/tests/test_production_aggregates.py`

**Interfaces:**
- Consumes: `_MONTHS` (`months(month_id, first_id, end_id, days)`), `register`, `Aggregate`, `BuildParams.bind` (`:build_id, :from_id, :as_of_id, :cmp_day`), `builds`, `tests.etl_helpers.*` (`branch_row`, `stage`, `merge_all`, `open_run`, `new_tag`, `new_source`, `purge_source`), `tests.s1_helpers.rebuild` (`SCENARIO_PARAMS`: as_of 2026-09-24, date_from 2025-01-01).
- Produces:
  - `mart|pub.agg_generation_month (branch_id ≥ 0, month_id, days_in_period, days_in_month, stations, capacity_mw, capacity_hours, generation, generation_cmp, own_needs, plan, plan_full)` — har stansiya (`kind ∈ ges|cascade`) × oy (ishlab chiqarishsiz ham) + fakti bor boshqa filiallar; `capacity_mw` — oy snapshot sanasida (`end_id`) `dim_branch_version` dan; `capacity_hours = capacity_mw × days_in_period × 24`; `plan = plan_full × days_in_period / days_in_month`; `branch_id = 0` — jami.
  - `mart|pub.agg_energy_sales_month (branch_id ≥ 0, month_id, accrued, paid, volume)`.
  - `app.dwh.production_aggregates`: `GENERATION_MONTH`, `ENERGY_SALES_MONTH`.
  - `tests.s3_helpers`: `ProdScenario(source, tag, branch_id, branch_code, hq_id, run_id, build_id)`, `production_rows(tag)`, `production_scenario(source, *, publish=False) -> ProdScenario`.

Ssenariy (as_of = 2026-09-24; mln kVt·soat; filial `T-<tag>` — ГЭС 100 MVt, `T-<tag>H` — `kind=head`) — 5, 7, 9-vazifa testlari shu qiymatlardan:

| Fakt | Qatorlar |
|---|---|
| `fact_generation` (`askue_daily`) | 2026-08-10: 1,0 / СН 0,02; 2026-08-20: 0,8 / 0,02; 2026-09-05: 0,6 / 0,01; 2026-09-20: 0,4 / 0,01; 2025-08-15: 1,5 / 0,03; 2025-09-10: 0,5 / 0,01; 2025-09-28: 0,7 / 0,01 |
| `fact_generation` (`generation_plan`) | 2026-08-01: 2,0; 2026-09-01: 1,5; 2025-09-01: 1,2 |
| `fact_energy_sales` | 2026-08-31: начислено 1200, оплачено 900; 2026-09-24: 500 / 450 (mln so'm) |

Kutilgan: `m08` — ishlab chiqarish 1,8, o'tgan yil 1,5, reja 2,0 (bajarilish 0,9), quvvat-soat 100 × 31 × 24 = 74 400 (КИУМ 1800 / 74 400), СН 0,04, to'lov darajasi 0,75; `m09` (ochiq) — 1,0, o'tgan yil faqat 1–24-sentabr 2025 = 0,5, reja 1,5 × 24 / 30 = 1,2 (bajarilish 0,833), quvvat-soat 100 × 24 × 24 = 57 600, to'lov 0,9.

- [ ] **Step 1: Test yordamchisi — ssenariy**

`backend/tests/s3_helpers.py`:
```python
"""S3 testlari uchun qo'lda hisoblanadigan ssenariylar (jadvallar — rejaning 3–4-vazifalarida)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.etl.db import etl_transaction
from tests.etl_helpers import branch_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild


@dataclass(frozen=True, slots=True)
class ProdScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    hq_id: int
    run_id: int
    build_id: int


def production_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    station = branch_row(tag, capacity_mw=100)
    hq = branch_row(f"{tag}H", name=f"Тестовая головная {tag}", kind="head", capacity_mw=None)
    code = station["code"]
    buyer = f"CPB-{tag}"

    def gen(src_id: str, day: int, value: float, own: float) -> dict[str, Any]:
        return {"doc_type": "askue_daily", "src_id": src_id, "date_id": day, "branch_code": code,
                "generation": value, "own_needs": own, "supply": round(value - own, 3),
                "plan": None, "work_hours": 24}

    def plan(src_id: str, day: int, value: float) -> dict[str, Any]:
        return {"doc_type": "generation_plan", "src_id": src_id, "date_id": day,
                "branch_code": code, "generation": 0, "own_needs": 0, "supply": 0,
                "plan": value, "work_hours": None}

    def sale(src_id: str, day: int, accrued: float, paid: float) -> dict[str, Any]:
        return {"doc_type": "energy_sales", "src_id": src_id, "date_id": day,
                "branch_code": code, "cp_code": buyer, "accrued": accrued, "paid": paid,
                "volume": 1}

    return {
        "dim_branch": [station, hq],
        "dim_counterparty": [{"code": buyer, "name": f"Тест покупатель {tag}", "kind": "buyer",
                              "inn": "301234567"}],
        "fact_generation": [
            gen("g1", 20260810, 1.0, 0.02), gen("g2", 20260820, 0.8, 0.02),
            gen("g3", 20260905, 0.6, 0.01), gen("g4", 20260920, 0.4, 0.01),
            gen("p1", 20250815, 1.5, 0.03), gen("p2", 20250910, 0.5, 0.01),
            gen("p3", 20250928, 0.7, 0.01),
            plan("pl1", 20260801, 2.0), plan("pl2", 20260901, 1.5), plan("pl3", 20250901, 1.2),
        ],
        "fact_energy_sales": [sale("s1", 20260831, 1200, 900), sale("s2", 20260924, 500, 450)],
    }


def production_scenario(source: str, *, publish: bool = False) -> ProdScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, production_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        ids = dict(conn.execute(text(
            "SELECT code, branch_id FROM dwh.dim_branch WHERE code IN (:a, :b)"),
            {"a": f"T-{tag}", "b": f"T-{tag}H"}).all())
    return ProdScenario(source, tag, int(ids[f"T-{tag}"]), f"T-{tag}", int(ids[f"T-{tag}H"]),
                        run_id, build_id)
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_production_aggregates.py`:
```python
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import merge_all, new_source, open_run, purge_source, stage
from tests.s1_helpers import rebuild
from tests.s3_helpers import ProdScenario, production_rows, production_scenario

TABLES = ("agg_generation_month", "agg_energy_sales_month")
COLS = ("days_in_period", "days_in_month", "stations", "capacity_mw", "capacity_hours",
        "generation", "generation_cmp", "own_needs", "plan", "plan_full")


@pytest.fixture
def sc() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _gen(build_id: int, branch_id: int) -> dict[int, tuple[float | None, ...]]:
    rows = _rows(f"SELECT month_id, {', '.join(COLS)} FROM mart.agg_generation_month "
                 "WHERE build_id = :b AND branch_id = :br", b=build_id, br=branch_id)
    return {r["month_id"]: tuple(None if r[c] is None else float(r[c]) for c in COLS)
            for r in rows}


def test_generation_month_rows(sc: ProdScenario) -> None:
    got = _gen(sc.build_id, sc.branch_id)
    assert got[202608] == (31, 31, 1, 100.0, 74400.0, 1.8, 1.8, 0.04, 2.0, 2.0)
    assert got[202609] == (24, 30, 1, 100.0, 57600.0, 1.0, 1.0, 0.02, 1.2, 1.5)
    assert got[202509] == (30, 30, 1, 100.0, 72000.0, 1.2, 0.5, 0.02, 1.2, 1.2)
    assert got[202508] == (31, 31, 1, 100.0, 74400.0, 1.5, 1.5, 0.03, 0.0, 0.0)
    # Ishlab chiqarishsiz oy ham bor — КИУМ maxrajida soatlar hisobga olinadi.
    assert got[202607] == (31, 31, 1, 100.0, 74400.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert min(got) == 202501 and max(got) == 202609
    assert _gen(sc.build_id, sc.hq_id) == {}
    total = _gen(sc.build_id, 0)[202608]
    assert total[2] >= 1 and total[5] >= 1.8


def test_energy_sales_rows(sc: ProdScenario) -> None:
    rows = _rows("SELECT month_id, accrued, paid, volume FROM mart.agg_energy_sales_month "
                 "WHERE build_id = :b AND branch_id = :br ORDER BY month_id",
                 b=sc.build_id, br=sc.branch_id)
    assert [(r["month_id"], float(r["accrued"]), float(r["paid"]), float(r["volume"]))
            for r in rows] == [(202608, 1200.0, 900.0, 1.0), (202609, 500.0, 450.0, 1.0)]


def test_capacity_version_applies_per_month(sc: ProdScenario) -> None:
    run = open_run(sc.source)
    stage(run, sc.source, {"dim_branch": [{**production_rows(sc.tag)["dim_branch"][0],
                                           "capacity_mw": 120}]})
    merge_all(run, sc.source, as_of=date(2026, 9, 1))
    build_id = rebuild(run)
    got = _gen(build_id, sc.branch_id)
    assert (got[202608][3], got[202608][4]) == (100.0, 74400.0)
    assert (got[202609][3], got[202609][4]) == (120.0, 69120.0)


def test_rls_and_failed_build(sc: ProdScenario) -> None:
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

Run: `$TEST pytest tests/test_production_aggregates.py -v`
Expected: FAIL — `relation "mart.agg_generation_month" does not exist`.

- [ ] **Step 4: 0013 migratsiyasi**

`backend/migrations/versions/0013_mart_production.py`:
```python
"""S3: ishlab chiqarish — oy × stansiya (quvvat, soatlar, reja) va realizatsiya

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-25
"""

from alembic import op

revision = "0013"
down_revision = "0012"  # `alembic heads` boshqa bo'lsa — shu qiymatni joriy head'ga moslang
branch_labels = None
depends_on = None

VOLUME = "numeric(20,3) NOT NULL DEFAULT 0"
MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_generation_month", "agg_energy_sales_month")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_generation_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      days_in_period smallint NOT NULL,
      days_in_month smallint NOT NULL,
      stations integer NOT NULL DEFAULT 0,
      capacity_mw numeric(12,2),
      capacity_hours numeric(16,2) NOT NULL DEFAULT 0,
      generation {VOLUME},
      generation_cmp {VOLUME},
      own_needs {VOLUME},
      plan {VOLUME},
      plan_full {VOLUME},
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_energy_sales_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      accrued {MONEY},
      paid {MONEY},
      volume {VOLUME},
      PRIMARY KEY (build_id, branch_id, month_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_generation_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.days_in_period, a.days_in_month, a.stations,
           a.capacity_mw, a.capacity_hours, a.generation, a.generation_cmp, a.own_needs, a.plan,
           a.plan_full
    FROM mart.agg_generation_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_energy_sales_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.accrued, a.paid, a.volume
    FROM mart.agg_energy_sales_month a WHERE a.build_id = {ACTIVE}
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

`backend/app/dwh/production_aggregates.py`:
```python
"""S3 ishlab chiqarish agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Stansiya = dim_branch.kind ∈ (ges, cascade): har stansiya × oy uchun qator (ishlab chiqarish
bo'lmasa ham) — КИУМ maxraji (quvvat × soat) davrning barcha oylarini qamraydi. Quvvat — oy
snapshot sanasida (end_id: oy oxiri yoki as_of) amalda bo'lgan dim_branch_version (SCD-2,
valid_to inklyuziv). Reja oylik (1-kun): ochiq oyda plan = plan_full × o'tgan kunlar / oy kunlari.
generation_cmp — oyning 1..cmp_day kunlari (o'tgan yil bilan bir xil kunlar, TZ 4).
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

_GENERATION = f"""
INSERT INTO mart.agg_generation_month (build_id, branch_id, month_id, days_in_period,
                                       days_in_month, stations, capacity_mw, capacity_hours,
                                       generation, generation_cmp, own_needs, plan, plan_full)
WITH {_MONTHS},
full_days AS (
  SELECT d.month_id, count(*)::smallint AS n FROM dwh.dim_date d
  WHERE d.month_id IN (SELECT month_id FROM months) GROUP BY d.month_id),
facts AS (
  SELECT g.branch_id, d.month_id, sum(g.generation) AS gen,
         coalesce(sum(g.generation) FILTER (WHERE d.day <= :cmp_day), 0) AS gen_cmp,
         sum(g.own_needs) AS own, coalesce(sum(g.plan), 0) AS plan_full
  FROM dwh.fact_generation g
  JOIN dwh.dim_date d ON d.date_id = g.date_id
  JOIN months m ON m.month_id = d.month_id
  WHERE g.date_id BETWEEN :from_id AND :as_of_id
  GROUP BY g.branch_id, d.month_id),
cap AS (
  SELECT b.branch_id, m.month_id, v.capacity_mw
  FROM dwh.dim_branch b
  CROSS JOIN months m
  JOIN dwh.dim_date sd ON sd.date_id = m.end_id
  LEFT JOIN dwh.dim_branch_version v ON v.branch_id = b.branch_id
       AND v.valid_from <= sd.date AND (v.valid_to IS NULL OR v.valid_to >= sd.date)
  WHERE b.kind IN ('ges', 'cascade')),
j AS (
  SELECT coalesce(c.branch_id, f.branch_id) AS branch_id,
         coalesce(c.month_id, f.month_id) AS month_id, c.capacity_mw,
         coalesce(f.gen, 0) AS gen, coalesce(f.gen_cmp, 0) AS gen_cmp,
         coalesce(f.own, 0) AS own, coalesce(f.plan_full, 0) AS plan_full
  FROM cap c FULL JOIN facts f ON f.branch_id = c.branch_id AND f.month_id = c.month_id)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, max(m.days), max(fd.n),
       count(j.capacity_mw), sum(j.capacity_mw),
       coalesce(sum(j.capacity_mw * m.days * 24), 0), sum(j.gen), sum(j.gen_cmp), sum(j.own),
       round(sum(j.plan_full) * max(m.days) / max(fd.n), 3), sum(j.plan_full)
FROM j
JOIN months m ON m.month_id = j.month_id
JOIN full_days fd ON fd.month_id = j.month_id
GROUP BY GROUPING SETS ((j.branch_id, j.month_id), (j.month_id))
"""

_ENERGY_SALES = f"""
INSERT INTO mart.agg_energy_sales_month (build_id, branch_id, month_id, accrued, paid, volume)
WITH {_MONTHS}
SELECT :build_id, coalesce(s.branch_id, 0), d.month_id, sum(s.accrued), sum(s.paid),
       sum(s.volume)
FROM dwh.fact_energy_sales s
JOIN dwh.dim_date d ON d.date_id = s.date_id
JOIN months m ON m.month_id = d.month_id
WHERE s.date_id BETWEEN :from_id AND :as_of_id
GROUP BY GROUPING SETS ((s.branch_id, d.month_id), (d.month_id))
"""

GENERATION_MONTH = register(Aggregate("agg_generation_month", (_GENERATION,)))
ENERGY_SALES_MONTH = register(Aggregate("agg_energy_sales_month", (_ENERGY_SALES,)))
```

`backend/app/dwh/aggregates.py` — fayl OXIRIGA (S2'ning `loan_aggregates` importidan keyin) qo'shing:
```python
from app.dwh import production_aggregates  # noqa: E402, F401
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_production_aggregates.py tests/test_aggregates_builds.py tests/test_loan_aggregates.py -v`
Expected: barcha testlar passed.
Run: `$TEST pytest tests/test_synthetic.py tests/test_etl_runner.py -v`
Expected: passed (sintetik ishlab chiqarish agregatlarga tushadi).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(dwh): ishlab chiqarish agregatlari — oy × stansiya, quvvat SCD-2, reja ulushi, realizatsiya

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 4: Ombor agregatlari (0014) — oy snapshot'i, kategoriyalar, yosh, minimum, belgilangan pozitsiyalar

**Files:**
- Create: `backend/migrations/versions/0014_mart_stock.py`, `backend/app/dwh/stock_aggregates.py`
- Modify: `backend/app/dwh/aggregates.py` (oxirgi import), `backend/tests/s3_helpers.py` (ombor ssenariysi)
- Test: `backend/tests/test_stock_aggregates.py`

**Interfaces:**
- Consumes: `_MONTHS`, `register`, `Aggregate`, `BuildParams.bind`, `builds`, `tests.etl_helpers.*`, `tests.s1_helpers.rebuild`.
- Produces:
  - `mart|pub.agg_stock_month (branch_id ≥ 0, month_id, category, snap_date_id, positions, value, below_min, min_known, idle_value, age_le90, age_91_180, age_181_365, age_gt365, age_unknown, inflow, outflow)` — snapshot: filial × oy ichidagi eng oxirgi `fact_stock` sanasi (shu sanadagi qatorlar; oydagi oldingi sanalar tashlanadi); yosh = snapshot sanasi − `last_move_date_id` (kun), `NULL` → `age_unknown`; oborotlar — `fact_stock_move` oy bo'yicha, nomenklatura kategoriyasi kesimida.
  - `mart|pub.agg_stock_positions (branch_id > 0, month_id, nom_id, warehouse, snap_date_id, nom_code, name, category, unit, qty, min_qty, value, last_move_date_id, age_days, below_min, idle)` — faqat `qty < min_qty` yoki `age_days > 180` bo'lgan pozitsiyalar.
  - `app.dwh.stock_aggregates`: `STOCK_MONTH`, `STOCK_POSITIONS`, `IDLE_DAYS = 180`.
  - `tests.s3_helpers`: `StockScenario(source, tag, branch_id, branch_code, run_id, build_id, noms: dict[str, int])`, `stock_rows(tag)`, `stock_scenario(source, *, publish=False) -> StockScenario`.

Ssenariy (filial `T-<tag>`; mln so'm; `N1`, `N3` — «Запасные части», `N2` — «Масла и ГСМ»):

| Sana | N1 (Склад А) | N2 (Склад А) | N3 (Склад Б) |
|---|---|---|---|
| 2026-08-15 | 20 шт / 80 / min 10 (oyning oxirgi snapshot'i emas — tashlanadi) | — | — |
| 2026-08-31 | 4 шт / 40 / min 10 / oxirgi harakat 2026-08-20 (11 kun) | 500 л / 20 / min 100 / 2026-01-10 (233 kun) | 2 шт / 60 / min yo'q / 2025-06-01 (456 kun) |
| 2026-09-24 | 12 / 48 / min 10 / 2026-09-15 (9) | 480 / 19,2 / min 100 / 2026-01-10 (257) | 2 / 60 / min yo'q / sana yo'q |

`fact_stock_move`: 2026-08-05 N1 prixod 100; 2026-08-20 N1 rasxod 140; 2026-09-12 N1 prixod 16; 2026-09-15 N1 rasxod 8; 2026-09-10 N2 rasxod 0,8.
Kutilgan (filial jami): `m08` — qiymat 120, pozitsiyalar 3, minimumdan past 1 (minimum ma'lum 2), неликвид 80, yosh ≤90: 40 / 181–365: 20 / >365: 60, prixod 100, rasxod 140 (oborot 120 / (140 / 31) = 26,6 kun); `m09` — 127,2, past 0, неликвид 19,2, yoshi noma'lum 60, prixod 16, rasxod 8,8.

- [ ] **Step 1: Test yordamchisi — ombor ssenariysi**

`backend/tests/s3_helpers.py` — fayl oxiriga qo'shing:
```python
@dataclass(frozen=True, slots=True)
class StockScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    run_id: int
    build_id: int
    noms: dict[str, int]  # "N1" → nom_id


def stock_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    code = branch["code"]

    def nom(key: str, name: str, category: str, unit: str) -> dict[str, Any]:
        return {"code": f"{key}-{tag}", "name": name, "category": category, "unit": unit,
                "enbt_code": None}

    def snap(src_id: str, day: int, key: str, wh: str, qty: float, value: float,
             min_qty: float | None, last: int | None) -> dict[str, Any]:
        return {"doc_type": "stock_snapshot", "src_id": src_id, "date_id": day,
                "branch_code": code, "nom_code": f"{key}-{tag}", "warehouse": wh, "qty": qty,
                "value": value, "min_qty": min_qty, "last_move_date_id": last}

    def move(src_id: str, day: int, key: str, direction: str, value: float) -> dict[str, Any]:
        return {"doc_type": "stock_move", "src_id": src_id, "date_id": day, "branch_code": code,
                "nom_code": f"{key}-{tag}", "direction": direction, "qty": 1, "value": value}

    return {
        "dim_branch": [branch],
        "dim_nomenclature": [nom("N1", "Подшипник тестовый", "Запасные части", "шт"),
                             nom("N2", "Масло тестовое", "Масла и ГСМ", "л"),
                             nom("N3", "Задвижка тестовая", "Запасные части", "шт")],
        "fact_stock": [
            snap("a1", 20260815, "N1", "Склад А", 20, 80, 10, 20260810),
            snap("a2", 20260831, "N1", "Склад А", 4, 40, 10, 20260820),
            snap("a3", 20260831, "N2", "Склад А", 500, 20, 100, 20260110),
            snap("a4", 20260831, "N3", "Склад Б", 2, 60, None, 20250601),
            snap("b1", 20260924, "N1", "Склад А", 12, 48, 10, 20260915),
            snap("b2", 20260924, "N2", "Склад А", 480, 19.2, 100, 20260110),
            snap("b3", 20260924, "N3", "Склад Б", 2, 60, None, None),
        ],
        "fact_stock_move": [
            move("m1", 20260805, "N1", "in", 100), move("m2", 20260820, "N1", "out", 140),
            move("m3", 20260912, "N1", "in", 16), move("m4", 20260915, "N1", "out", 8),
            move("m5", 20260910, "N2", "out", 0.8),
        ],
    }


def stock_scenario(source: str, *, publish: bool = False) -> StockScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, stock_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": f"T-{tag}"}).scalar_one())
        noms = {str(code).split("-")[0]: int(nom_id) for code, nom_id in conn.execute(text(
            "SELECT code, nom_id FROM dwh.dim_nomenclature WHERE code LIKE :p"),
            {"p": f"N_-{tag}"}).all()}
    return StockScenario(source, tag, branch_id, f"T-{tag}", run_id, build_id, noms)
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_stock_aggregates.py`:
```python
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from tests.etl_helpers import new_source, purge_source
from tests.s3_helpers import StockScenario, stock_scenario

TABLES = ("agg_stock_month", "agg_stock_positions")
COLS = ("positions", "value", "below_min", "min_known", "idle_value", "age_le90", "age_91_180",
        "age_181_365", "age_gt365", "age_unknown", "inflow", "outflow")
SPARE = "Запасные части"
OIL = "Масла и ГСМ"


@pytest.fixture
def sc() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def test_stock_month_by_category(sc: StockScenario) -> None:
    rows = _rows(f"SELECT month_id, category, snap_date_id, {', '.join(COLS)} "
                 "FROM mart.agg_stock_month WHERE build_id = :b AND branch_id = :br",
                 b=sc.build_id, br=sc.branch_id)
    got = {(r["month_id"], r["category"]): tuple(float(r[c]) for c in COLS) for r in rows}
    assert got == {
        (202608, SPARE): (2, 100, 1, 1, 60, 40, 0, 0, 60, 0, 100, 140),
        (202608, OIL): (1, 20, 0, 1, 20, 0, 0, 20, 0, 0, 0, 0),
        (202609, SPARE): (2, 108, 0, 1, 0, 48, 0, 0, 0, 60, 16, 8),
        (202609, OIL): (1, 19.2, 0, 1, 19.2, 0, 0, 19.2, 0, 0, 0, 0.8),
    }
    snaps = {(r["month_id"], r["category"]): r["snap_date_id"] for r in rows}
    assert snaps[(202608, SPARE)] == 20260831 and snaps[(202609, OIL)] == 20260924


def test_flagged_positions(sc: StockScenario) -> None:
    rows = _rows("SELECT month_id, nom_id, warehouse, qty, min_qty, value, age_days, below_min, "
                 "idle, unit FROM mart.agg_stock_positions WHERE build_id = :b AND branch_id = :br "
                 "ORDER BY month_id, nom_id", b=sc.build_id, br=sc.branch_id)
    n1, n2, n3 = sc.noms["N1"], sc.noms["N2"], sc.noms["N3"]
    got = [(r["month_id"], r["nom_id"], r["warehouse"], float(r["qty"]), r["age_days"],
            r["below_min"], r["idle"]) for r in rows]
    assert got == sorted([
        (202608, n1, "Склад А", 4.0, 11, True, False),
        (202608, n2, "Склад А", 500.0, 233, False, True),
        (202608, n3, "Склад Б", 2.0, 456, False, True),
        (202609, n2, "Склад А", 480.0, 257, False, True),
    ], key=lambda x: (x[0], x[1]))
    units = {r["nom_id"]: r["unit"] for r in rows}
    assert (units[n1], units[n2]) == ("шт", "л")


def test_branch_zero_totals_include_branch(sc: StockScenario) -> None:
    rows = _rows("SELECT sum(value) AS v, sum(below_min) AS b FROM mart.agg_stock_month "
                 "WHERE build_id = :b AND branch_id = 0 AND month_id = 202608",
                 b=sc.build_id)
    assert float(rows[0]["v"]) >= 120 and int(rows[0]["b"]) >= 1


def test_rls_and_failed_build(sc: StockScenario) -> None:
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

Run: `$TEST pytest tests/test_stock_aggregates.py -v`
Expected: FAIL — `relation "mart.agg_stock_month" does not exist`.

- [ ] **Step 4: 0014 migratsiyasi**

`backend/migrations/versions/0014_mart_stock.py`:
```python
"""S3: ombor — oy × kategoriya snapshot'i (qiymat, minimum, yosh, oborot), belgilangan pozitsiyalar

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-25
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_stock_month", "agg_stock_positions")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_stock_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id >= 0),
      month_id integer NOT NULL,
      category varchar(100) NOT NULL,
      snap_date_id integer,
      positions integer NOT NULL DEFAULT 0,
      value {MONEY},
      below_min integer NOT NULL DEFAULT 0,
      min_known integer NOT NULL DEFAULT 0,
      idle_value {MONEY},
      age_le90 {MONEY},
      age_91_180 {MONEY},
      age_181_365 {MONEY},
      age_gt365 {MONEY},
      age_unknown {MONEY},
      inflow {MONEY},
      outflow {MONEY},
      PRIMARY KEY (build_id, branch_id, month_id, category)
    )
    """,
    f"""
    CREATE TABLE mart.agg_stock_positions (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      nom_id integer NOT NULL,
      warehouse varchar(100) NOT NULL,
      snap_date_id integer NOT NULL,
      nom_code varchar(32) NOT NULL,
      name varchar(300) NOT NULL,
      category varchar(100) NOT NULL,
      unit varchar(16) NOT NULL,
      qty numeric(20,3) NOT NULL,
      min_qty numeric(20,3),
      value numeric(20,2) NOT NULL,
      last_move_date_id integer,
      age_days integer,
      below_min boolean NOT NULL,
      idle boolean NOT NULL,
      PRIMARY KEY (build_id, branch_id, month_id, nom_id, warehouse)
    )
    """,
    f"""
    CREATE VIEW pub.agg_stock_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.category, a.snap_date_id, a.positions, a.value,
           a.below_min, a.min_known, a.idle_value, a.age_le90, a.age_91_180, a.age_181_365,
           a.age_gt365, a.age_unknown, a.inflow, a.outflow
    FROM mart.agg_stock_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_stock_positions WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.nom_id, a.warehouse, a.snap_date_id, a.nom_code, a.name,
           a.category, a.unit, a.qty, a.min_qty, a.value, a.last_move_date_id, a.age_days,
           a.below_min, a.idle
    FROM mart.agg_stock_positions a WHERE a.build_id = {ACTIVE}
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

`backend/app/dwh/stock_aggregates.py`:
```python
"""S3 ombor agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

Oy snapshot'i: filial × oy ichidagi eng oxirgi fact_stock sanasi va faqat shu sanadagi qatorlar
(oy davomidagi oldingi snapshot'lar tashlanadi — pozitsiya yo'qolgan bo'lsa, qayta sanalmaydi).
Bir xil pozitsiya (nomenklatura × ombor) bir nechta manbadan kelsa — yig'indi.
Yosh = snapshot sanasi − oxirgi harakat sanasi; ma'lum emas → age_unknown (TZ 4 «возраст запасов»).
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

IDLE_DAYS = 180  # TZ 4: неликвиды — без движения более 180 дней

_POSITIONS_CTE = f"""{_MONTHS},
last_snap AS (
  SELECT s.branch_id, m.month_id, max(s.date_id) AS snap_id
  FROM dwh.fact_stock s JOIN months m ON s.date_id BETWEEN m.first_id AND m.end_id
  GROUP BY s.branch_id, m.month_id),
snap AS (
  SELECT s.branch_id, l.month_id, s.nom_id, s.warehouse, l.snap_id, sum(s.qty) AS qty,
         sum(s.value) AS value, max(s.min_qty) AS min_qty,
         max(s.last_move_date_id) AS last_move_date_id
  FROM dwh.fact_stock s
  JOIN last_snap l ON l.branch_id = s.branch_id AND s.date_id = l.snap_id
  GROUP BY s.branch_id, l.month_id, s.nom_id, s.warehouse, l.snap_id),
pos AS (
  SELECT sn.branch_id, sn.month_id, sn.nom_id, sn.warehouse, sn.snap_id, sn.qty, sn.value,
         sn.min_qty, sn.last_move_date_id, n.code AS nom_code, n.name, n.category, n.unit,
         (sd.date - lm.date) AS age_days
  FROM snap sn
  JOIN dwh.dim_nomenclature n ON n.nom_id = sn.nom_id
  JOIN dwh.dim_date sd ON sd.date_id = sn.snap_id
  LEFT JOIN dwh.dim_date lm ON lm.date_id = sn.last_move_date_id)"""

_STOCK_MONTH = f"""
INSERT INTO mart.agg_stock_month (build_id, branch_id, month_id, category, snap_date_id,
                                  positions, value, below_min, min_known, idle_value, age_le90,
                                  age_91_180, age_181_365, age_gt365, age_unknown, inflow,
                                  outflow)
WITH {_POSITIONS_CTE},
st AS (
  SELECT branch_id, month_id, category, max(snap_id) AS snap_id,
         count(*) FILTER (WHERE qty > 0 OR value > 0) AS positions, sum(value) AS value,
         count(*) FILTER (WHERE min_qty IS NOT NULL AND qty < min_qty) AS below_min,
         count(*) FILTER (WHERE min_qty IS NOT NULL) AS min_known,
         coalesce(sum(value) FILTER (WHERE age_days > {IDLE_DAYS}), 0) AS idle_value,
         coalesce(sum(value) FILTER (WHERE age_days <= 90), 0) AS a1,
         coalesce(sum(value) FILTER (WHERE age_days BETWEEN 91 AND 180), 0) AS a2,
         coalesce(sum(value) FILTER (WHERE age_days BETWEEN 181 AND 365), 0) AS a3,
         coalesce(sum(value) FILTER (WHERE age_days > 365), 0) AS a4,
         coalesce(sum(value) FILTER (WHERE age_days IS NULL), 0) AS a0
  FROM pos GROUP BY branch_id, month_id, category),
mv AS (
  SELECT f.branch_id, d.month_id, n.category,
         coalesce(sum(f.value) FILTER (WHERE f.direction = 'in'), 0) AS inflow,
         coalesce(sum(f.value) FILTER (WHERE f.direction = 'out'), 0) AS outflow
  FROM dwh.fact_stock_move f
  JOIN dwh.dim_date d ON d.date_id = f.date_id
  JOIN months m ON m.month_id = d.month_id
  JOIN dwh.dim_nomenclature n ON n.nom_id = f.nom_id
  WHERE f.date_id BETWEEN :from_id AND :as_of_id
  GROUP BY f.branch_id, d.month_id, n.category),
j AS (
  SELECT coalesce(st.branch_id, mv.branch_id) AS branch_id,
         coalesce(st.month_id, mv.month_id) AS month_id,
         coalesce(st.category, mv.category) AS category, st.snap_id,
         coalesce(st.positions, 0) AS positions, coalesce(st.value, 0) AS value,
         coalesce(st.below_min, 0) AS below_min, coalesce(st.min_known, 0) AS min_known,
         coalesce(st.idle_value, 0) AS idle_value, coalesce(st.a1, 0) AS a1,
         coalesce(st.a2, 0) AS a2, coalesce(st.a3, 0) AS a3, coalesce(st.a4, 0) AS a4,
         coalesce(st.a0, 0) AS a0, coalesce(mv.inflow, 0) AS inflow,
         coalesce(mv.outflow, 0) AS outflow
  FROM st FULL JOIN mv ON mv.branch_id = st.branch_id AND mv.month_id = st.month_id
                      AND mv.category = st.category)
SELECT :build_id, coalesce(j.branch_id, 0), j.month_id, j.category, max(j.snap_id),
       sum(j.positions), sum(j.value), sum(j.below_min), sum(j.min_known), sum(j.idle_value),
       sum(j.a1), sum(j.a2), sum(j.a3), sum(j.a4), sum(j.a0), sum(j.inflow), sum(j.outflow)
FROM j
GROUP BY GROUPING SETS ((j.branch_id, j.month_id, j.category), (j.month_id, j.category))
"""

_STOCK_POSITIONS = f"""
INSERT INTO mart.agg_stock_positions (build_id, branch_id, month_id, nom_id, warehouse,
                                      snap_date_id, nom_code, name, category, unit, qty,
                                      min_qty, value, last_move_date_id, age_days, below_min,
                                      idle)
WITH {_POSITIONS_CTE}
SELECT :build_id, branch_id, month_id, nom_id, warehouse, snap_id, nom_code, name, category,
       unit, qty, min_qty, value, last_move_date_id, age_days,
       coalesce(min_qty IS NOT NULL AND qty < min_qty, false),
       coalesce(age_days > {IDLE_DAYS}, false)
FROM pos
WHERE (min_qty IS NOT NULL AND qty < min_qty) OR age_days > {IDLE_DAYS}
"""

STOCK_MONTH = register(Aggregate("agg_stock_month", (_STOCK_MONTH,)))
STOCK_POSITIONS = register(Aggregate("agg_stock_positions", (_STOCK_POSITIONS,)))
```

`backend/app/dwh/aggregates.py` — 3-vazifada qo'shilgan oxirgi import qatorini almashtiring:
```python
from app.dwh import production_aggregates, stock_aggregates  # noqa: E402, F401
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_stock_aggregates.py tests/test_production_aggregates.py tests/test_aggregates_builds.py -v`
Expected: barcha testlar passed.
Run: `$TEST pytest tests/test_synthetic.py tests/test_etl_runner.py -v`
Expected: passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(dwh): ombor agregatlari — oy snapshot'i, kategoriyalar, yosh, minimum, belgilangan pozitsiyalar

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 5: Ishlab chiqarish so'rovlari — выработка, YoY, reja, КИУМ, СН, отпуск, to'lov darajasi

**Files:**
- Create: `backend/app/sections/queries/production.py`
- Test: `backend/tests/test_sections_production.py`

**Interfaces:**
- Consumes: `pub.agg_generation_month`, `pub.agg_energy_sales_month`, `pub.branches`, `BranchSel.total/rows`, `ReportPeriod` (`months`, `prev_months`, `open_last`, `last_month`), `resolve_period`, `queries.cash.num/opt`, `month_id`, `tests.s3_helpers.production_scenario`.
- Produces (`app.sections.queries.production`):
  - `STATION_KINDS_SQL = "('ges', 'cascade')"`.
  - `GenFigures(generation, generation_prev, plan, own_needs, capacity_mw, capacity_hours, stations, accrued, paid, branch_id=0, name="", short_name="")` + `.supply` (= выработка − СН), `.execution`, `.kium` (= выработка × 1000 / quvvat-soat), `.own_share`, `.payment_level`, `.has_data` — maxraj 0 bo'lsa `None`.
  - `GenMonth(month_id, generation, plan, generation_prev, accrued, paid)`.
  - `has_stations(db, sel) -> bool`, `totals(db, sel, period) -> GenFigures`, `stations(db, sel, period) -> list[GenFigures]` (faqat stansiyalar, `sort_order` bo'yicha), `station_map(db, sel, period) -> dict[int, GenFigures]`, `monthly(db, sel, today) -> list[GenMonth]` (joriy yil yanvar…joriy oy; o'tgan yil joriy oy uchun `generation_cmp`).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sections_production.py`:
```python
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import production
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s3_helpers import ProdScenario, production_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _totals(db: Session, branch_id: int, per: str) -> production.GenFigures:
    return production.totals(db, BranchSel(branch_id, all_scope=True),
                             resolve_period(per, TEST_AS_OF))


def test_closed_month_totals(sc: ProdScenario, db: Session) -> None:
    t = _totals(db, sc.branch_id, "m08")
    assert (t.generation, t.generation_prev, t.plan, t.own_needs) == (1.8, 1.5, 2.0, 0.04)
    assert (t.capacity_mw, t.stations, t.capacity_hours) == (100.0, 1, 74400.0)
    assert t.supply == 1.76 and t.execution == 0.9
    assert t.kium == 0.024194 and t.own_share == 0.022222
    assert (t.accrued, t.paid, t.payment_level) == (1200.0, 900.0, 0.75)
    assert t.has_data


def test_open_month_prorates_plan_and_compares_same_days(sc: ProdScenario, db: Session) -> None:
    t = _totals(db, sc.branch_id, "m09")
    # Reja 1,5 × 24/30; o'tgan yil — faqat 1–24-sentabr 2025 (28-sentabrdagi 0,7 kirmaydi).
    assert (t.generation, t.generation_prev, t.plan) == (1.0, 0.5, 1.2)
    assert t.execution == 0.833333 and t.capacity_hours == 57600.0 and t.kium == 0.017361
    assert t.payment_level == 0.9


def test_quarter_sums_months(sc: ProdScenario, db: Session) -> None:
    t = _totals(db, sc.branch_id, "q3")
    assert (t.generation, t.generation_prev, t.plan) == (2.8, 2.0, 3.2)
    assert t.capacity_hours == 206400.0 and t.capacity_mw == 100.0


def test_station_rows_and_map(sc: ProdScenario, db: Session) -> None:
    sel = BranchSel(sc.branch_id, all_scope=True)
    rows = production.stations(db, sel, resolve_period("m08", TEST_AS_OF))
    assert [(r.branch_id, r.name, r.generation, r.plan, r.accrued) for r in rows] == [
        (sc.branch_id, f"Тестовая ГЭС {sc.tag}", 1.8, 2.0, 1200.0)]
    every = production.station_map(db, BranchSel(None, True), resolve_period("m08", TEST_AS_OF))
    assert every[sc.branch_id].execution == 0.9 and sc.hq_id not in every


def test_hq_has_no_stations(sc: ProdScenario, db: Session) -> None:
    assert production.has_stations(db, BranchSel(sc.branch_id, True)) is True
    assert production.has_stations(db, BranchSel(sc.hq_id, True)) is False
    assert production.has_stations(db, BranchSel(None, True)) is True
    t = _totals(db, sc.hq_id, "m08")
    assert not t.has_data and t.generation == 0.0 and t.capacity_mw is None
    assert (t.execution, t.kium, t.own_share, t.payment_level) == (None, None, None, None)


def test_monthly_series(sc: ProdScenario, db: Session) -> None:
    months = production.monthly(db, BranchSel(sc.branch_id, True), TEST_AS_OF)
    assert [m.month_id for m in months] == list(range(202601, 202610))
    by = {m.month_id: (m.generation, m.plan, m.generation_prev, m.accrued, m.paid)
          for m in months}
    assert by[202608] == (1.8, 2.0, 1.5, 1200.0, 900.0)
    assert by[202609] == (1.0, 1.2, 0.5, 500.0, 450.0)
    assert by[202601] == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_limited_scope_sums_own_rows(sc: ProdScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = production.totals(s, BranchSel(None, all_scope=False),
                              resolve_period("m08", TEST_AS_OF))
        assert production.has_stations(s, BranchSel(None, all_scope=False)) is True
    assert (t.generation, t.plan, t.accrued) == (1.8, 2.0, 1200.0)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sections_production.py -v`
Expected: FAIL — `ImportError: cannot import name 'production' from 'app.sections.queries'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/sections/queries/production.py`:
```python
"""Ishlab chiqarish (TZ 4 «Производство») — faqat pub.agg_generation_month,
pub.agg_energy_sales_month va pub.branches dan.

YoY (TZ 4): o'tgan yilning yopiq oylari to'liq, davrning ochiq oyiga mos oy — generation_cmp
(1..as_of kunlari). Reja agregatda ochiq oy uchun ulushlangan. Maxraj 0 → None («нет данных»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num, opt
from app.sections.scope import BranchSel

STATION_KINDS_SQL = "('ges', 'cascade')"
_NONE_MONTH = [0]  # bo'sh ro'yxat o'rniga (ANY('{}') turini PG aniqlay olmaydi)


def _ratio(a: float, b: float) -> float | None:
    return None if b <= 0 else round(a / b, 6)


@dataclass(frozen=True, slots=True)
class GenFigures:
    generation: float
    generation_prev: float
    plan: float
    own_needs: float
    capacity_mw: float | None
    capacity_hours: float
    stations: int
    accrued: float
    paid: float
    branch_id: int = 0
    name: str = ""
    short_name: str = ""

    @property
    def supply(self) -> float:
        """Отпуск в сеть = выработка − собственные нужды (TZ 4)."""
        return round(self.generation - self.own_needs, 3)

    @property
    def execution(self) -> float | None:
        return _ratio(self.generation, self.plan)

    @property
    def kium(self) -> float | None:
        """КИУМ = выработка (mln kVt·soat × 1000 = MVt·soat) / Σ(quvvat × soat)."""
        if self.capacity_hours <= 0:
            return None
        return round(self.generation * 1000 / self.capacity_hours, 6)

    @property
    def own_share(self) -> float | None:
        return _ratio(self.own_needs, self.generation)

    @property
    def payment_level(self) -> float | None:
        return _ratio(self.paid, self.accrued)

    @property
    def has_data(self) -> bool:
        return self.generation > 0 or self.plan > 0 or self.accrued > 0


@dataclass(frozen=True, slots=True)
class GenMonth:
    month_id: int
    generation: float
    plan: float
    generation_prev: float
    accrued: float
    paid: float


_GEN_SUMS = (
    "coalesce(sum(g.generation) FILTER (WHERE g.month_id = ANY(:months)), 0) AS gen, "
    "coalesce(sum(g.generation) FILTER (WHERE g.month_id = ANY(:prev_full)), 0) "
    "+ coalesce(sum(g.generation_cmp) FILTER (WHERE g.month_id = ANY(:prev_cmp)), 0) AS prev, "
    "coalesce(sum(g.plan) FILTER (WHERE g.month_id = ANY(:months)), 0) AS plan, "
    "coalesce(sum(g.own_needs) FILTER (WHERE g.month_id = ANY(:months)), 0) AS own, "
    "coalesce(sum(g.capacity_hours) FILTER (WHERE g.month_id = ANY(:months)), 0) AS ch, "
    "sum(g.capacity_mw) FILTER (WHERE g.month_id = :last) AS cap, "
    "coalesce(sum(g.stations) FILTER (WHERE g.month_id = :last), 0) AS st"
)
_SALES_SUMS = "coalesce(sum(s.accrued), 0) AS acc, coalesce(sum(s.paid), 0) AS paid"


def _bind(period: ReportPeriod) -> dict[str, Any]:
    prev = list(period.prev_months)
    full, cmp = (prev[:-1], prev[-1:]) if period.open_last else (prev, [])
    return {"months": list(period.months), "prev_full": full or _NONE_MONTH,
            "prev_cmp": cmp or _NONE_MONTH, "last": period.last_month,
            "all": [*period.months, *prev]}


def _figures(g: Any, s: Any, **ident: Any) -> GenFigures:
    return GenFigures(
        generation=num(g.gen), generation_prev=num(g.prev), plan=num(g.plan),
        own_needs=num(g.own), capacity_mw=opt(g.cap), capacity_hours=num(g.ch),
        stations=int(g.st), accrued=num(s.acc) if s is not None else 0.0,
        paid=num(s.paid) if s is not None else 0.0, **ident)


def has_stations(db: Session, sel: BranchSel) -> bool:
    where, params = sel.rows("branch_id")
    return bool(db.execute(text(
        f"SELECT EXISTS (SELECT 1 FROM pub.branches WHERE kind IN {STATION_KINDS_SQL} "
        f"AND {where})"), params).scalar_one())


def totals(db: Session, sel: BranchSel, period: ReportPeriod) -> GenFigures:
    bind = _bind(period)
    where, params = sel.total("g.branch_id")
    g = db.execute(text(
        f"SELECT {_GEN_SUMS} FROM pub.agg_generation_month g "
        f"WHERE {where} AND g.month_id = ANY(:all)"), {**params, **bind}).one()
    s_where, s_params = sel.total("s.branch_id")
    s = db.execute(text(
        f"SELECT {_SALES_SUMS} FROM pub.agg_energy_sales_month s "
        f"WHERE {s_where} AND s.month_id = ANY(:months)"),
        {**s_params, "months": bind["months"]}).one()
    return _figures(g, s)


def stations(db: Session, sel: BranchSel, period: ReportPeriod) -> list[GenFigures]:
    bind = _bind(period)
    where, params = sel.rows("g.branch_id")
    rows = db.execute(text(
        f"SELECT g.branch_id, b.name, b.short_name, {_GEN_SUMS} "
        "FROM pub.agg_generation_month g JOIN pub.branches b ON b.branch_id = g.branch_id "
        f"WHERE {where} AND b.kind IN {STATION_KINDS_SQL} AND g.month_id = ANY(:all) "
        "GROUP BY g.branch_id, b.name, b.short_name, b.sort_order "
        "ORDER BY b.sort_order, g.branch_id"), {**params, **bind}).all()
    s_where, s_params = sel.rows("s.branch_id")
    sales = {int(r.branch_id): r for r in db.execute(text(
        f"SELECT s.branch_id, {_SALES_SUMS} FROM pub.agg_energy_sales_month s "
        f"WHERE {s_where} AND s.month_id = ANY(:months) GROUP BY s.branch_id"),
        {**s_params, "months": bind["months"]}).all()}
    return [_figures(r, sales.get(int(r.branch_id)), branch_id=int(r.branch_id), name=r.name,
                     short_name=r.short_name) for r in rows]


def station_map(db: Session, sel: BranchSel, period: ReportPeriod) -> dict[int, GenFigures]:
    return {s.branch_id: s for s in stations(db, sel, period)}


def monthly(db: Session, sel: BranchSel, today: date) -> list[GenMonth]:
    """Joriy yil yanvaridan joriy oygacha; o'tgan yil — joriy oy uchun shuncha kun."""
    current = month_id(today)
    months = [today.year * 100 + m for m in range(1, today.month + 1)]
    where, params = sel.total("g.branch_id")
    gen = {int(r.month_id): r for r in db.execute(text(
        "SELECT g.month_id, sum(g.generation) AS gen, sum(g.generation_cmp) AS cmp, "
        "sum(g.plan) AS plan FROM pub.agg_generation_month g "
        f"WHERE {where} AND g.month_id = ANY(:m) GROUP BY g.month_id"),
        {**params, "m": months + [m - 100 for m in months]}).all()}
    s_where, s_params = sel.total("s.branch_id")
    sales = {int(r.month_id): r for r in db.execute(text(
        f"SELECT s.month_id, {_SALES_SUMS} FROM pub.agg_energy_sales_month s "
        f"WHERE {s_where} AND s.month_id = ANY(:m) GROUP BY s.month_id"),
        {**s_params, "m": months}).all()}
    out: list[GenMonth] = []
    for m in months:
        cur, prev, sale = gen.get(m), gen.get(m - 100), sales.get(m)
        prev_value = 0.0
        if prev is not None:
            prev_value = num(prev.cmp if m == current else prev.gen)
        out.append(GenMonth(
            month_id=m, generation=num(cur.gen) if cur else 0.0,
            plan=num(cur.plan) if cur else 0.0, generation_prev=prev_value,
            accrued=num(sale.acc) if sale else 0.0, paid=num(sale.paid) if sale else 0.0))
    return out
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sections_production.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(sections): ishlab chiqarish ko'rsatkichlari — YoY, reja, КИУМ, отпуск, to'lov darajasi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 6: Ombor so'rovlari — qiymat, oborot kunlari, minimum, неликвид, yosh, kategoriyalar, filiallar

**Files:**
- Create: `backend/app/sections/queries/stock.py`
- Test: `backend/tests/test_sections_stock.py`

**Interfaces:**
- Consumes: `pub.agg_stock_month`, `pub.agg_stock_positions`, `pub.branches`, `BranchSel`, `ReportPeriod` (`months`, `last_month`, `date_from`, `date_to`), `from_date_id`, `month_id`, `queries.cash.num`, `tests.s3_helpers.stock_scenario`.
- Produces (`app.sections.queries.stock`):
  - `AGE_KEYS = ("le90", "d91_180", "d181_365", "gt365", "unknown")`, `POSITIONS_LIMIT = 500`.
  - `StockFigures(as_of, value, positions, below_min, min_known, idle_value, age_known_value, inflow, outflow, days)` + `.turnover_days` (= qiymat / (rasxod / kunlar), 1 kasr; rasxod 0 → `None`), `.idle_share` (yosh ma'lumoti yo'q → `None`), `.has_data`, `.has_minimum`, `.has_age`.
  - `NamedValue(name, value)`, `AgeBucket(key, value)`, `StockBranch(branch_id, name, value, positions, below_min, idle_value)`, `StockPosition(branch_id, branch_name, warehouse, nom_code, name, category, unit, qty, min_qty, value, age_days)` + `.coverage`, `StockMonth(month_id, inflow, outflow)`.
  - `totals(db, sel, period) -> StockFigures`, `categories(db, sel, month) -> list[NamedValue]`, `by_branch(db, sel, period) -> list[StockBranch]`, `ages(db, sel, month) -> list[AgeBucket]`, `positions(db, sel, month, kind: "below" | "idle", limit=POSITIONS_LIMIT) -> list[StockPosition]` (below — obespechennost o'sishi bo'yicha, idle — qiymat kamayishi bo'yicha), `flows(db, sel, today) -> list[StockMonth]`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sections_stock.py`:
```python
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import stock
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s3_helpers import StockScenario, stock_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _sel(sc: StockScenario) -> BranchSel:
    return BranchSel(sc.branch_id, all_scope=True)


def test_closed_month_totals(sc: StockScenario, db: Session) -> None:
    t = stock.totals(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert t.as_of == date(2026, 8, 31) and t.days == 31
    assert (t.value, t.positions, t.below_min, t.min_known) == (120.0, 3, 1, 2)
    assert (t.idle_value, t.age_known_value, t.inflow, t.outflow) == (80.0, 120.0, 100.0, 140.0)
    assert t.turnover_days == 26.6 and t.idle_share == 0.666667
    assert t.has_data and t.has_minimum and t.has_age


def test_open_month_and_quarter(sc: StockScenario, db: Session) -> None:
    t = stock.totals(db, _sel(sc), resolve_period("m09", TEST_AS_OF))
    assert t.as_of == TEST_AS_OF and (t.value, t.below_min, t.idle_value) == (127.2, 0, 19.2)
    assert (t.inflow, t.outflow, t.days) == (16.0, 8.8, 24)
    assert t.turnover_days == 346.9 and t.idle_share == 0.150943
    q = stock.totals(db, _sel(sc), resolve_period("q3", TEST_AS_OF))
    # Qiymat — davr oxiridagi snapshot; oborot — 3 oy; kunlar 1.07–24.09 = 86.
    assert (q.value, q.inflow, q.outflow, q.days) == (127.2, 116.0, 148.8, 86)
    assert q.turnover_days == 73.5


def test_categories_ages_and_branches(sc: StockScenario, db: Session) -> None:
    assert [(c.name, c.value) for c in stock.categories(db, _sel(sc), 202608)] == [
        ("Запасные части", 100.0), ("Масла и ГСМ", 20.0)]
    assert [(a.key, a.value) for a in stock.ages(db, _sel(sc), 202608)] == [
        ("le90", 40.0), ("d91_180", 0.0), ("d181_365", 20.0), ("gt365", 60.0), ("unknown", 0.0)]
    assert [(a.key, a.value) for a in stock.ages(db, _sel(sc), 202609)][-1] == ("unknown", 60.0)
    rows = stock.by_branch(db, _sel(sc), resolve_period("m08", TEST_AS_OF))
    assert [(r.branch_id, r.value, r.positions, r.below_min, r.idle_value) for r in rows] == [
        (sc.branch_id, 120.0, 3, 1, 80.0)]


def test_below_and_idle_positions(sc: StockScenario, db: Session) -> None:
    below = stock.positions(db, _sel(sc), 202608, "below")
    assert [(p.nom_code, p.warehouse, p.qty, p.min_qty, p.coverage) for p in below] == [
        (f"N1-{sc.tag}", "Склад А", 4.0, 10.0, 0.4)]
    assert below[0].branch_name == f"Тестовая ГЭС {sc.tag}" and below[0].unit == "шт"
    idle = stock.positions(db, _sel(sc), 202608, "idle")
    assert [(p.nom_code, p.value, p.age_days) for p in idle] == [
        (f"N3-{sc.tag}", 60.0, 456), (f"N2-{sc.tag}", 20.0, 233)]
    assert [p.nom_code for p in stock.positions(db, _sel(sc), 202609, "idle")] == [
        f"N2-{sc.tag}"]


def test_flows_series(sc: StockScenario, db: Session) -> None:
    months = stock.flows(db, _sel(sc), TEST_AS_OF)
    assert [m.month_id for m in months] == list(range(202601, 202610))
    by = {m.month_id: (m.inflow, m.outflow) for m in months}
    assert by[202608] == (100.0, 140.0) and by[202609] == (16.0, 8.8) and by[202601] == (0.0, 0.0)


def test_limited_scope_and_empty_branch(sc: StockScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        t = stock.totals(s, BranchSel(None, all_scope=False), resolve_period("m08", TEST_AS_OF))
    assert t.value == 120.0
    with new_session() as s:
        apply_rls(s, None)
        empty = stock.totals(s, BranchSel(999_999, True), resolve_period("m08", TEST_AS_OF))
    assert not empty.has_data and empty.turnover_days is None and empty.idle_share is None
    assert empty.as_of == date(2026, 8, 31)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sections_stock.py -v`
Expected: FAIL — `ImportError: cannot import name 'stock' from 'app.sections.queries'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/sections/queries/stock.py`:
```python
"""Ombor (TZ 4 «Склад») — faqat pub.agg_stock_month, pub.agg_stock_positions va pub.branches dan.

Qiymat, minimum, неликвид va yosh — davr oxirgi oyining snapshot'idan; prixod/rasxod — davr
oylari yig'indisi; оборачиваемость = qiymat / (rasxod / davr kunlari), kunlarda.
Minimum yoki oxirgi harakat sanasi manbada yo'q bo'lsa — tegishli ko'rsatkich None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id, month_id
from app.sections.period import ReportPeriod
from app.sections.queries.cash import num
from app.sections.scope import BranchSel

AGE_KEYS = ("le90", "d91_180", "d181_365", "gt365", "unknown")
_AGE_COLS = {"le90": "age_le90", "d91_180": "age_91_180", "d181_365": "age_181_365",
             "gt365": "age_gt365", "unknown": "age_unknown"}
POSITIONS_LIMIT = 500


@dataclass(frozen=True, slots=True)
class StockFigures:
    as_of: date
    value: float
    positions: int
    below_min: int
    min_known: int
    idle_value: float
    age_known_value: float
    inflow: float
    outflow: float
    days: int

    @property
    def turnover_days(self) -> float | None:
        """Оборачиваемость = стоимость запасов / (расход за период / число дней)."""
        if self.outflow <= 0 or self.days <= 0:
            return None
        return round(self.value / (self.outflow / self.days), 1)

    @property
    def idle_share(self) -> float | None:
        if self.value <= 0 or self.age_known_value <= 0:
            return None
        return round(self.idle_value / self.value, 6)

    @property
    def has_data(self) -> bool:
        return self.positions > 0 or self.inflow > 0 or self.outflow > 0

    @property
    def has_minimum(self) -> bool:
        return self.min_known > 0

    @property
    def has_age(self) -> bool:
        return self.age_known_value > 0


@dataclass(frozen=True, slots=True)
class NamedValue:
    name: str
    value: float


@dataclass(frozen=True, slots=True)
class AgeBucket:
    key: str
    value: float


@dataclass(frozen=True, slots=True)
class StockBranch:
    branch_id: int
    name: str
    value: float
    positions: int
    below_min: int
    idle_value: float


@dataclass(frozen=True, slots=True)
class StockPosition:
    branch_id: int
    branch_name: str
    warehouse: str
    nom_code: str
    name: str
    category: str
    unit: str
    qty: float
    min_qty: float | None
    value: float
    age_days: int | None

    @property
    def coverage(self) -> float | None:
        """Обеспеченность = количество / минимум."""
        if self.min_qty is None or self.min_qty <= 0:
            return None
        return round(self.qty / self.min_qty, 6)


@dataclass(frozen=True, slots=True)
class StockMonth:
    month_id: int
    inflow: float
    outflow: float


def totals(db: Session, sel: BranchSel, period: ReportPeriod) -> StockFigures:
    where, params = sel.total("a.branch_id")
    snap = db.execute(text(
        "SELECT max(a.snap_date_id) AS snap, coalesce(sum(a.positions), 0) AS pos, "
        "coalesce(sum(a.value), 0) AS value, coalesce(sum(a.below_min), 0) AS below, "
        "coalesce(sum(a.min_known), 0) AS known, coalesce(sum(a.idle_value), 0) AS idle, "
        "coalesce(sum(a.age_le90 + a.age_91_180 + a.age_181_365 + a.age_gt365), 0) AS aged "
        f"FROM pub.agg_stock_month a WHERE {where} AND a.month_id = :last"),
        {**params, "last": period.last_month}).one()
    flow = db.execute(text(
        "SELECT coalesce(sum(a.inflow), 0) AS i, coalesce(sum(a.outflow), 0) AS o "
        f"FROM pub.agg_stock_month a WHERE {where} AND a.month_id = ANY(:months)"),
        {**params, "months": list(period.months)}).one()
    as_of = from_date_id(int(snap.snap)) if snap.snap is not None else period.date_to
    return StockFigures(
        as_of=as_of, value=num(snap.value), positions=int(snap.pos), below_min=int(snap.below),
        min_known=int(snap.known), idle_value=num(snap.idle), age_known_value=num(snap.aged),
        inflow=num(flow.i), outflow=num(flow.o),
        days=(period.date_to - period.date_from).days + 1)


def categories(db: Session, sel: BranchSel, month: int) -> list[NamedValue]:
    where, params = sel.total("a.branch_id")
    rows = db.execute(text(
        "SELECT a.category, sum(a.value) AS v FROM pub.agg_stock_month a "
        f"WHERE {where} AND a.month_id = :m GROUP BY a.category HAVING sum(a.value) > 0 "
        "ORDER BY v DESC, a.category"), {**params, "m": month}).all()
    return [NamedValue(r.category, num(r.v)) for r in rows]


def ages(db: Session, sel: BranchSel, month: int) -> list[AgeBucket]:
    where, params = sel.total("a.branch_id")
    cols = ", ".join(f"coalesce(sum(a.{col}), 0) AS {key}" for key, col in _AGE_COLS.items())
    row = db.execute(text(f"SELECT {cols} FROM pub.agg_stock_month a "
                          f"WHERE {where} AND a.month_id = :m"), {**params, "m": month}).one()
    return [AgeBucket(key, num(getattr(row, key))) for key in AGE_KEYS]


def by_branch(db: Session, sel: BranchSel, period: ReportPeriod) -> list[StockBranch]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.branch_id, b.name, sum(a.value) AS v, sum(a.positions) AS pos, "
        "sum(a.below_min) AS below, sum(a.idle_value) AS idle "
        "FROM pub.agg_stock_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE {where} AND a.month_id = :m GROUP BY a.branch_id, b.name "
        "HAVING sum(a.positions) > 0 ORDER BY v DESC, b.name"),
        {**params, "m": period.last_month}).all()
    return [StockBranch(int(r.branch_id), r.name, num(r.v), int(r.pos), int(r.below),
                        num(r.idle)) for r in rows]


_ORDER = {"below": "p.qty / nullif(p.min_qty, 0), p.value DESC, p.name",
          "idle": "p.value DESC, p.name"}


def positions(db: Session, sel: BranchSel, month: int, kind: Literal["below", "idle"],
              limit: int = POSITIONS_LIMIT) -> list[StockPosition]:
    where, params = sel.rows("p.branch_id")
    flag = "p.below_min" if kind == "below" else "p.idle"
    rows = db.execute(text(
        "SELECT p.branch_id, b.name AS branch_name, p.warehouse, p.nom_code, p.name, p.category, "
        "p.unit, p.qty, p.min_qty, p.value, p.age_days "
        "FROM pub.agg_stock_positions p JOIN pub.branches b ON b.branch_id = p.branch_id "
        f"WHERE {where} AND p.month_id = :m AND {flag} ORDER BY {_ORDER[kind]} LIMIT :limit"),
        {**params, "m": month, "limit": limit}).all()
    return [_position(r) for r in rows]


def _position(r: Any) -> StockPosition:
    return StockPosition(
        branch_id=int(r.branch_id), branch_name=r.branch_name, warehouse=r.warehouse,
        nom_code=r.nom_code, name=r.name, category=r.category, unit=r.unit, qty=num(r.qty),
        min_qty=None if r.min_qty is None else num(r.min_qty), value=num(r.value),
        age_days=None if r.age_days is None else int(r.age_days))


def flows(db: Session, sel: BranchSel, today: date) -> list[StockMonth]:
    months = [today.year * 100 + m for m in range(1, month_id(today) % 100 + 1)]
    where, params = sel.total("a.branch_id")
    by = {int(r.month_id): r for r in db.execute(text(
        "SELECT a.month_id, sum(a.inflow) AS i, sum(a.outflow) AS o FROM pub.agg_stock_month a "
        f"WHERE {where} AND a.month_id = ANY(:m) GROUP BY a.month_id"),
        {**params, "m": months}).all()}
    return [StockMonth(m, num(by[m].i) if m in by else 0.0, num(by[m].o) if m in by else 0.0)
            for m in months]
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sections_stock.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(sections): ombor ko'rsatkichlari — qiymat, oborot, minimum, неликвид, yosh

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 7: «Производство» API — Сводка, Выработка по станциям, Реализация; Обзор xaritasiga ishlab chiqarish

**Files:**
- Create: `backend/app/sections/production_schemas.py`, `backend/app/sections/proizvodstvo.py`
- Modify: `backend/app/sections/schemas.py` (`StationProductionOut`, `StationOut.production`), `backend/app/sections/obzor.py` (`stations`), `backend/app/main.py` (router), `backend/tests/test_route_guards.py`, `backend/tests/test_obzor_api.py` (`test_svod_shape_and_etag`)
- Test: `backend/tests/test_proizvodstvo_api.py`

**Interfaces:**
- Consumes: `SQ`/`SectionQuery`, `get_today`, `Cache`, `get_db`, `require_perm`, `section_perm`, `Section.PROIZVODSTVO`, `schemas._Out`, `ReportPeriodOut`, `period_out`, `queries.production.*`, `queries.cash.opt`, `BranchSel`, `tests.s3_helpers.production_scenario`, `published_synthetic`, `tests.helpers.login`, `make_user`.
- Produces:
  - `app.sections.schemas`: `StationProductionOut(generation, plan, execution, kium, payment_level)`; `StationOut.production: StationProductionOut | None` (S1'dagi `dict[str, float] | None` o'rniga).
  - `app.sections.production_schemas`: `ProdKpisOut(has_data, generation, generation_prev, plan, execution, capacity_mw, stations, kium, own_needs, own_share, supply, accrued, paid, payment_level)`, `GenMonthOut(month_id, generation, plan, generation_prev)`, `SalesMonthOut(month_id, accrued, paid)`, `StationGenOut(branch_id, name, short_name, capacity_mw, generation, generation_prev, plan, execution, kium, supply, own_share, accrued, paid, payment_level)`, `MapStationOut(branch_id, code, name, short_name, kind, capacity_mw, lat, lon, production)`, `ProizvSvodOut(period, has_stations, kpis, months, stations, map)`, `ProizvStanciiOut(period, has_stations, kpis, stations)`, `ProizvRealizOut(period, has_stations, kpis, months, stations)`; konvertorlar `kpis_out`, `station_out`, `production_out(GenFigures | None) -> StationProductionOut | None`.
  - `app.sections.proizvodstvo`: `router` (`/proizvodstvo`), `SVOD_STATIONS = 8`, `DB`, `build_svod`, `build_stancii`, `build_realiz`, `map_stations(db, q, period)`. HTTP: `GET /proizvodstvo/svod`, `/proizvodstvo/stancii`, `/proizvodstvo/realiz`.
  - `obzor.stations` — `StationOut.production` stansiya ma'lumoti bo'lsa to'ldiriladi (TZ 6: xarita tooltip'i — ishlab chiqarish va reja %).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_proizvodstvo_api.py`:
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
from tests.s3_helpers import ProdScenario, production_scenario

PAGES = ("svod", "stancii", "realiz")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source, publish=True)
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


def test_svod_numbers_map_and_etag(sc: ProdScenario, app_factory: Callable[[], TestClient],
                                   make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/proizvodstvo/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert body["has_stations"] is True and body["period"]["code"] == "m08"
    assert (k["generation"], k["generation_prev"], k["plan"], k["execution"]) == (1.8, 1.5, 2.0,
                                                                                 0.9)
    assert (k["capacity_mw"], k["stations"], k["kium"]) == (100.0, 1, 0.024194)
    assert (k["supply"], k["own_share"], k["payment_level"]) == (1.76, 0.022222, 0.75)
    assert [m["month_id"] for m in body["months"]] == list(range(202601, 202610))
    assert body["months"][7] == {"month_id": 202608, "generation": 1.8, "plan": 2.0,
                                 "generation_prev": 1.5}
    assert [s["branch_id"] for s in body["stations"]] == [sc.branch_id]
    by_map = {s["branch_id"]: s for s in body["map"]}
    assert by_map[sc.branch_id]["production"]["execution"] == 0.9
    assert by_map[sc.hq_id]["production"] is None and by_map[sc.hq_id]["kind"] == "head"
    again = client.get("/api/v1/proizvodstvo/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_stancii_and_realiz(sc: ProdScenario, app_factory: Callable[[], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m09", "br": sc.branch_id}
    st = client.get("/api/v1/proizvodstvo/stancii", params=params).json()
    row = st["stations"][0]
    assert (row["generation"], row["plan"], row["execution"], row["kium"]) == (1.0, 1.2, 0.833333,
                                                                              0.017361)
    assert (row["capacity_mw"], row["supply"], row["name"]) == (100.0, 0.98,
                                                                f"Тестовая ГЭС {sc.tag}")
    realiz = client.get("/api/v1/proizvodstvo/realiz", params={"per": "m08",
                                                               "br": sc.branch_id}).json()
    assert realiz["months"][7] == {"month_id": 202608, "accrued": 1200.0, "paid": 900.0}
    assert realiz["stations"][0]["payment_level"] == 0.75


def test_hq_has_no_stations(sc: ProdScenario, app_factory: Callable[[], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    for page in PAGES:
        body = client.get(f"/api/v1/proizvodstvo/{page}",
                          params={"per": "m08", "br": sc.hq_id}).json()
        assert body["has_stations"] is False and body["stations"] == [], page
        assert body["kpis"]["has_data"] is False and body["kpis"]["execution"] is None, page


def test_permission_and_branch_scope(sc: ProdScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    kazna = _as(app_factory, make_user("spec_kazna"))
    for page in PAGES:
        assert kazna.get(f"/api/v1/proizvodstvo/{page}").status_code == 403, page
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = econ.get(f"/api/v1/proizvodstvo/{page}", params={"br": sc.hq_id})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = econ.get("/api/v1/proizvodstvo/stancii", params={"per": "m08"}).json()
    assert {s["branch_id"] for s in own["stations"]} == {sc.branch_id}
    assert own["kpis"]["generation"] == 1.8
    svod = econ.get("/api/v1/proizvodstvo/svod", params={"per": "m08"}).json()
    assert {s["branch_id"] for s in svod["map"]} == {sc.branch_id}


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/proizvodstvo/svod", params={"per": "m12"}).status_code == 422


def test_synthetic_stations(published_synthetic: int, app_factory: Callable[[], TestClient],
                            make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/proizvodstvo/stancii", params={"per": "m08"}).json()
    synthetic = [s for s in body["stations"] if s["branch_id"] <= 16]
    assert len(synthetic) == 15
    assert all(s["execution"] is not None and 0 < s["kium"] < 1 for s in synthetic)
    assert body["kpis"]["payment_level"] is not None
    obzor = client.get("/api/v1/obzor/svod", params={"per": "m08"}).json()
    prod = {s["branch_id"]: s["production"] for s in obzor["stations"]}
    assert prod[1] is None and prod[2] is not None and prod[2]["generation"] > 0


def test_pub_views_rls_direct_sql(sc: ProdScenario) -> None:
    for view in ("agg_generation_month", "agg_energy_sales_month"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
```

`backend/tests/test_obzor_api.py` — `test_svod_shape_and_etag` ichidagi qatorni almashtiring:
```python
    assert all(s["production"] is None for s in body["stations"])
```
yangisi (sintetik ma'lumotda stansiyalar ishlab chiqaradi, HQ — yo'q):
```python
    prod = {s["branch_id"]: s["production"] for s in body["stations"]}
    assert prod[1] is None and prod[2] is not None and prod[2]["execution"] is not None
```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga qo'shing:
```python
    ("GET", "/api/v1/proizvodstvo/svod"),
    ("GET", "/api/v1/proizvodstvo/stancii"),
    ("GET", "/api/v1/proizvodstvo/realiz"),
```
`PREFIX_PERMS` ga qo'shing:
```python
    "/api/v1/proizvodstvo": "section:proizvodstvo:view",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_proizvodstvo_api.py tests/test_route_guards.py -v`
Expected: FAIL — `404 Not Found` (router yo'q) va `test_route_table_matches_expected_set` yiqiladi.

- [ ] **Step 3: Xarita sxemasi (S1 `schemas.py`)**

`backend/app/sections/schemas.py` — `class StationOut(_Out):` dan OLDIN qo'shing:
```python
class StationProductionOut(_Out):
    """Xarita va stansiya paneli uchun ishlab chiqarish (S3): mln kVt·soat, ulushlar 0..1."""

    generation: float
    plan: float
    execution: float | None
    kium: float | None
    payment_level: float | None
```
`StationOut` ichidagi ikki qatorni:
```python
    # Ishlab chiqarish ko'rsatkichlari (выработка, план, КИУМ) — 3-bosqich rejasi to'ldiradi.
    production: dict[str, float] | None = None
```
quyidagiga almashtiring:
```python
    # Ishlab chiqarish (S3): stansiyada davr uchun ma'lumot bo'lmasa (yoki HQ) — None.
    production: StationProductionOut | None = None
```

- [ ] **Step 4: Javob sxemalari**

`backend/app/sections/production_schemas.py`:
```python
"""«Производство» API javoblari (OpenAPI komponent nomlari noyob). Ishlab chiqarish — mln kVt·soat,
pul — mln so'm, quvvat — MVt, ulushlar 0..1; None — maxraj 0 yoki ma'lumot yo'q."""

from __future__ import annotations

from app.sections.queries.production import GenFigures, GenMonth
from app.sections.schemas import ReportPeriodOut, StationProductionOut, _Out


class ProdKpisOut(_Out):
    has_data: bool
    generation: float
    generation_prev: float
    plan: float
    execution: float | None
    capacity_mw: float | None
    stations: int
    kium: float | None
    own_needs: float
    own_share: float | None
    supply: float
    accrued: float
    paid: float
    payment_level: float | None


class GenMonthOut(_Out):
    month_id: int
    generation: float
    plan: float
    generation_prev: float


class SalesMonthOut(_Out):
    month_id: int
    accrued: float
    paid: float


class StationGenOut(_Out):
    branch_id: int
    name: str
    short_name: str
    capacity_mw: float | None
    generation: float
    generation_prev: float
    plan: float
    execution: float | None
    kium: float | None
    supply: float
    own_share: float | None
    accrued: float
    paid: float
    payment_level: float | None


class MapStationOut(_Out):
    branch_id: int
    code: str
    name: str
    short_name: str
    kind: str
    capacity_mw: float | None
    lat: float | None
    lon: float | None
    production: StationProductionOut | None


class ProizvSvodOut(_Out):
    period: ReportPeriodOut
    has_stations: bool
    kpis: ProdKpisOut
    months: list[GenMonthOut]
    stations: list[StationGenOut]
    map: list[MapStationOut]


class ProizvStanciiOut(_Out):
    period: ReportPeriodOut
    has_stations: bool
    kpis: ProdKpisOut
    stations: list[StationGenOut]


class ProizvRealizOut(_Out):
    period: ReportPeriodOut
    has_stations: bool
    kpis: ProdKpisOut
    months: list[SalesMonthOut]
    stations: list[StationGenOut]


def kpis_out(t: GenFigures) -> ProdKpisOut:
    return ProdKpisOut(
        has_data=t.has_data, generation=t.generation, generation_prev=t.generation_prev,
        plan=t.plan, execution=t.execution, capacity_mw=t.capacity_mw, stations=t.stations,
        kium=t.kium, own_needs=t.own_needs, own_share=t.own_share, supply=t.supply,
        accrued=t.accrued, paid=t.paid, payment_level=t.payment_level)


def station_out(s: GenFigures) -> StationGenOut:
    return StationGenOut(
        branch_id=s.branch_id, name=s.name, short_name=s.short_name, capacity_mw=s.capacity_mw,
        generation=s.generation, generation_prev=s.generation_prev, plan=s.plan,
        execution=s.execution, kium=s.kium, supply=s.supply, own_share=s.own_share,
        accrued=s.accrued, paid=s.paid, payment_level=s.payment_level)


def gen_month_out(m: GenMonth) -> GenMonthOut:
    return GenMonthOut(month_id=m.month_id, generation=m.generation, plan=m.plan,
                       generation_prev=m.generation_prev)


def sales_month_out(m: GenMonth) -> SalesMonthOut:
    return SalesMonthOut(month_id=m.month_id, accrued=m.accrued, paid=m.paid)


def production_out(s: GenFigures | None) -> StationProductionOut | None:
    if s is None or not s.has_data:
        return None
    return StationProductionOut(generation=s.generation, plan=s.plan, execution=s.execution,
                                kium=s.kium, payment_level=s.payment_level)
```

- [ ] **Step 5: Router**

`backend/app/sections/proizvodstvo.py`:
```python
"""«Производство» (TZ 5): Сводка, Выработка по станциям, Реализация.

Zanjir: router → queries.production (pub view'lar) → Cache.respond (Redis + ETag).
HQ (stansiyasiz filial) tanlansa — has_stations = false, UI tushuntirish chiqaradi (TZ 5).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.context import require_perm
from app.auth.permissions import Section, section_perm
from app.core.cache import Cache
from app.core.db import get_db
from app.sections.deps import SQ, SectionQuery
from app.sections.period import ReportPeriod
from app.sections.production_schemas import (
    MapStationOut,
    ProizvRealizOut,
    ProizvStanciiOut,
    ProizvSvodOut,
    gen_month_out,
    kpis_out,
    production_out,
    sales_month_out,
    station_out,
)
from app.sections.queries import production
from app.sections.queries.cash import opt
from app.sections.schemas import period_out
from app.sections.scope import BranchSel

router = APIRouter(prefix="/proizvodstvo", tags=["proizvodstvo"],
                   dependencies=[Depends(require_perm(section_perm(Section.PROIZVODSTVO)))])
DB = Annotated[Session, Depends(get_db)]
SVOD_STATIONS = 8  # prototip: «Выработка по станциям» — 8 ta, «Все станции» tugmasi


def map_stations(db: Session, q: SectionQuery, period: ReportPeriod) -> list[MapStationOut]:
    """Foydalanuvchiga ko'rinadigan barcha filiallar (br tanlovidan qat'i nazar — tanlov UI'da)."""
    every = BranchSel(None, q.branch_ids is None)
    prod = production.station_map(db, every, period)
    rows = db.execute(text(
        "SELECT branch_id, code, name, short_name, kind, capacity_mw, lat, lon FROM pub.branches "
        "ORDER BY sort_order, branch_id")).all()
    return [MapStationOut(branch_id=b.branch_id, code=b.code, name=b.name,
                          short_name=b.short_name, kind=b.kind, capacity_mw=opt(b.capacity_mw),
                          lat=opt(b.lat), lon=opt(b.lon),
                          production=production_out(prod.get(b.branch_id))) for b in rows]


def build_svod(db: Session, q: SectionQuery) -> ProizvSvodOut:
    period, sel = q.period(), q.sel()
    has = production.has_stations(db, sel)
    rows = production.stations(db, sel, period) if has else []
    top = sorted(rows, key=lambda s: (-s.generation, s.name))[:SVOD_STATIONS]
    return ProizvSvodOut(
        period=period_out(period), has_stations=has,
        kpis=kpis_out(production.totals(db, sel, period)),
        months=[gen_month_out(m) for m in production.monthly(db, sel, q.today)],
        stations=[station_out(s) for s in top], map=map_stations(db, q, period))


def build_stancii(db: Session, q: SectionQuery) -> ProizvStanciiOut:
    period, sel = q.period(), q.sel()
    has = production.has_stations(db, sel)
    rows = production.stations(db, sel, period) if has else []
    rows.sort(key=lambda s: (-(s.capacity_mw or 0), s.name))  # prototip: quvvat bo'yicha
    return ProizvStanciiOut(period=period_out(period), has_stations=has,
                            kpis=kpis_out(production.totals(db, sel, period)),
                            stations=[station_out(s) for s in rows])


def build_realiz(db: Session, q: SectionQuery) -> ProizvRealizOut:
    period, sel = q.period(), q.sel()
    has = production.has_stations(db, sel)
    rows = [s for s in production.stations(db, sel, period) if s.accrued > 0] if has else []
    rows.sort(key=lambda s: (s.payment_level if s.payment_level is not None else 9.0, s.name))
    return ProizvRealizOut(
        period=period_out(period), has_stations=has,
        kpis=kpis_out(production.totals(db, sel, period)),
        months=[sales_month_out(m) for m in production.monthly(db, sel, q.today)],
        stations=[station_out(s) for s in rows])


@router.get("/svod", response_model=ProizvSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("proizvodstvo.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/stancii", response_model=ProizvStanciiOut)
def stancii(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("proizvodstvo.stancii", q.cache_filters, lambda: build_stancii(db, q))


@router.get("/realiz", response_model=ProizvRealizOut)
def realiz(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("proizvodstvo.realiz", q.cache_filters, lambda: build_realiz(db, q))
```

`backend/app/main.py` — import va `include_router` (S2'ning `kredity_router` qatoridan keyin):
```python
from app.sections.proizvodstvo import router as proizvodstvo_router
```
```python
    app.include_router(proizvodstvo_router, prefix=API_PREFIX)
```

- [ ] **Step 6: Обзор xaritasi — ishlab chiqarish**

`backend/app/sections/obzor.py` — importlarga qo'shing:
```python
from app.sections.production_schemas import production_out
from app.sections.queries import production
```
`stations()` ichida `debts = {…}` qatoridan keyin qo'shing:
```python
    prod = production.station_map(db, every, period)
```
va `StationOut(...)` chaqiruvining oxirgi qatorini
```python
            overdue_payable=d.overdue_payable if d else None))
```
quyidagiga almashtiring:
```python
            overdue_payable=d.overdue_payable if d else None,
            production=production_out(prod.get(b.branch_id))))
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_proizvodstvo_api.py tests/test_route_guards.py tests/test_obzor_api.py -v`
Expected: barcha testlar passed.

- [ ] **Step 8: Commit**

```bash
git add backend
git commit -m "feat(proizvodstvo): Сводка, Выработка по станциям, Реализация API; Обзор xaritasida ishlab chiqarish

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 8: «Склад» API — Сводка, Остатки по складам, Минимальный запас, Неликвиды

**Files:**
- Create: `backend/app/sections/stock_schemas.py`, `backend/app/sections/sklad.py`
- Modify: `backend/app/main.py` (router), `backend/tests/test_route_guards.py`
- Test: `backend/tests/test_sklad_api.py`

**Interfaces:**
- Consumes: `SQ`/`SectionQuery`, `Cache`, `get_db`, `require_perm`, `section_perm`, `Section.SKLAD`, `schemas._Out`, `ReportPeriodOut`, `period_out`, `loan_schemas.NamedAmountOut` (S2), `queries.stock.*`, `tests.s3_helpers.stock_scenario`, `published_synthetic`, `login`, `make_user`.
- Produces:
  - `app.sections.stock_schemas`: `StockKpisOut(as_of, has_data, value, turnover_days, positions, below_min, has_minimum, idle_value, idle_share, has_age, inflow, outflow)`, `StockMonthOut(month_id, inflow, outflow)`, `StockBranchOut(branch_id, name, value, positions, below_min, idle_value)`, `StockPositionOut(branch_id, branch_name, warehouse, nom_code, name, category, unit, qty, min_qty, coverage, value, age_days)`, `AgeBucketOut(key, value)`, `SkladSvodOut(period, kpis, months, categories, below)`, `SkladOstatkiOut(period, kpis, branches, categories)`, `SkladMinimumOut(period, kpis, below)`, `SkladNelikvidOut(period, kpis, ages, illiquid)`; konvertorlar `stock_kpis_out`, `position_out`.
  - `app.sections.sklad`: `router` (`/sklad`), `SVOD_BELOW = 5`, `build_svod`, `build_ostatki`, `build_minimum`, `build_nelikvid`. HTTP: `GET /sklad/svod`, `/sklad/ostatki`, `/sklad/minimum`, `/sklad/nelikvid`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sklad_api.py`:
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
from tests.s3_helpers import StockScenario, stock_scenario

PAGES = ("svod", "ostatki", "minimum", "nelikvid")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source, publish=True)
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


def test_svod_numbers_and_etag(sc: StockScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/sklad/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert (k["as_of"], k["value"], k["turnover_days"], k["positions"]) == ("2026-08-31", 120.0,
                                                                             26.6, 3)
    assert (k["below_min"], k["has_minimum"], k["idle_value"], k["idle_share"]) == (
        1, True, 80.0, 0.666667)
    assert (k["inflow"], k["outflow"], k["has_age"], k["has_data"]) == (100.0, 140.0, True, True)
    assert body["months"][7] == {"month_id": 202608, "inflow": 100.0, "outflow": 140.0}
    assert body["categories"] == [{"name": "Запасные части", "amount": 100.0},
                                  {"name": "Масла и ГСМ", "amount": 20.0}]
    assert [p["nom_code"] for p in body["below"]] == [f"N1-{sc.tag}"]
    assert body["below"][0]["coverage"] == 0.4
    again = client.get("/api/v1/sklad/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_ostatki_minimum_nelikvid(sc: StockScenario, app_factory: Callable[[], TestClient],
                                  make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("nach_otdela"))
    params = {"per": "m08", "br": sc.branch_id}
    ost = client.get("/api/v1/sklad/ostatki", params=params).json()
    assert ost["branches"] == [{"branch_id": sc.branch_id, "name": f"Тестовая ГЭС {sc.tag}",
                                "value": 120.0, "positions": 3, "below_min": 1,
                                "idle_value": 80.0}]
    mn = client.get("/api/v1/sklad/minimum", params=params).json()
    assert [(p["warehouse"], p["qty"], p["min_qty"], p["unit"]) for p in mn["below"]] == [
        ("Склад А", 4.0, 10.0, "шт")]
    nel = client.get("/api/v1/sklad/nelikvid", params=params).json()
    assert [a["key"] for a in nel["ages"]] == ["le90", "d91_180", "d181_365", "gt365", "unknown"]
    assert [(p["nom_code"], p["age_days"]) for p in nel["illiquid"]] == [
        (f"N3-{sc.tag}", 456), (f"N2-{sc.tag}", 233)]
    sep = client.get("/api/v1/sklad/nelikvid", params={"per": "m09", "br": sc.branch_id}).json()
    assert sep["ages"][-1] == {"key": "unknown", "value": 60.0}


def test_permission_and_branch_scope(sc: StockScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    kazna = _as(app_factory, make_user("spec_kazna"))
    for page in PAGES:
        assert kazna.get(f"/api/v1/sklad/{page}").status_code == 403, page
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = econ.get(f"/api/v1/sklad/{page}", params={"br": 1})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = econ.get("/api/v1/sklad/ostatki", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in own["branches"]} == {sc.branch_id}
    assert own["kpis"]["value"] == 120.0


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/sklad/svod", params={"per": "q4"}).status_code == 422


def test_synthetic_warehouses(published_synthetic: int, app_factory: Callable[[], TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/sklad/ostatki", params={"per": "m08"}).json()
    assert {b["branch_id"] for b in body["branches"]} >= set(range(1, 17))
    k = body["kpis"]
    assert k["value"] > 0 and k["has_minimum"] and k["has_age"] and k["turnover_days"] > 0
    assert len(body["categories"]) == 7


def test_pub_views_rls_direct_sql(sc: StockScenario) -> None:
    for view in ("agg_stock_month", "agg_stock_positions"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga qo'shing:
```python
    ("GET", "/api/v1/sklad/svod"),
    ("GET", "/api/v1/sklad/ostatki"),
    ("GET", "/api/v1/sklad/minimum"),
    ("GET", "/api/v1/sklad/nelikvid"),
```
`PREFIX_PERMS` ga qo'shing:
```python
    "/api/v1/sklad": "section:sklad:view",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sklad_api.py tests/test_route_guards.py -v`
Expected: FAIL — `404 Not Found` va `test_route_table_matches_expected_set`.

- [ ] **Step 3: Javob sxemalari**

`backend/app/sections/stock_schemas.py`:
```python
"""«Склад» API javoblari. Qiymatlar mln so'm, oborot — kunlarda, ulushlar 0..1;
has_minimum / has_age = false — manbada minimum yoki oxirgi harakat sanasi yo'q
(UI «Источник не подключён»)."""

from __future__ import annotations

from datetime import date

from app.sections.loan_schemas import NamedAmountOut
from app.sections.queries.stock import NamedValue, StockFigures, StockPosition
from app.sections.schemas import ReportPeriodOut, _Out


class StockKpisOut(_Out):
    as_of: date
    has_data: bool
    value: float
    turnover_days: float | None
    positions: int
    below_min: int
    has_minimum: bool
    idle_value: float
    idle_share: float | None
    has_age: bool
    inflow: float
    outflow: float


class StockMonthOut(_Out):
    month_id: int
    inflow: float
    outflow: float


class StockBranchOut(_Out):
    branch_id: int
    name: str
    value: float
    positions: int
    below_min: int
    idle_value: float


class StockPositionOut(_Out):
    branch_id: int
    branch_name: str
    warehouse: str
    nom_code: str
    name: str
    category: str
    unit: str
    qty: float
    min_qty: float | None
    coverage: float | None
    value: float
    age_days: int | None


class AgeBucketOut(_Out):
    key: str
    value: float


class SkladSvodOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    months: list[StockMonthOut]
    categories: list[NamedAmountOut]
    below: list[StockPositionOut]


class SkladOstatkiOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    branches: list[StockBranchOut]
    categories: list[NamedAmountOut]


class SkladMinimumOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    below: list[StockPositionOut]


class SkladNelikvidOut(_Out):
    period: ReportPeriodOut
    kpis: StockKpisOut
    ages: list[AgeBucketOut]
    illiquid: list[StockPositionOut]


def stock_kpis_out(t: StockFigures) -> StockKpisOut:
    return StockKpisOut(
        as_of=t.as_of, has_data=t.has_data, value=t.value, turnover_days=t.turnover_days,
        positions=t.positions, below_min=t.below_min, has_minimum=t.has_minimum,
        idle_value=t.idle_value, idle_share=t.idle_share, has_age=t.has_age, inflow=t.inflow,
        outflow=t.outflow)


def position_out(p: StockPosition) -> StockPositionOut:
    return StockPositionOut(
        branch_id=p.branch_id, branch_name=p.branch_name, warehouse=p.warehouse,
        nom_code=p.nom_code, name=p.name, category=p.category, unit=p.unit, qty=p.qty,
        min_qty=p.min_qty, coverage=p.coverage, value=p.value, age_days=p.age_days)


def named_values_out(items: list[NamedValue]) -> list[NamedAmountOut]:
    return [NamedAmountOut(name=i.name, amount=i.value) for i in items]
```

- [ ] **Step 4: Router**

`backend/app/sections/sklad.py`:
```python
"""«Склад» (TZ 5): Сводка, Остатки по складам, Минимальный запас, Неликвиды.

Zanjir: router → queries.stock (pub view'lar) → Cache.respond (Redis + ETag).
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
from app.sections.queries import stock
from app.sections.schemas import period_out
from app.sections.stock_schemas import (
    AgeBucketOut,
    SkladMinimumOut,
    SkladNelikvidOut,
    SkladOstatkiOut,
    SkladSvodOut,
    StockBranchOut,
    StockMonthOut,
    named_values_out,
    position_out,
    stock_kpis_out,
)

router = APIRouter(prefix="/sklad", tags=["sklad"],
                   dependencies=[Depends(require_perm(section_perm(Section.SKLAD)))])
DB = Annotated[Session, Depends(get_db)]
SVOD_BELOW = 5  # prototip: «Самые дефицитные позиции» — 5 ta, «Все позиции»


def build_svod(db: Session, q: SectionQuery) -> SkladSvodOut:
    period, sel = q.period(), q.sel()
    return SkladSvodOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        months=[StockMonthOut(month_id=m.month_id, inflow=m.inflow, outflow=m.outflow)
                for m in stock.flows(db, sel, q.today)],
        categories=named_values_out(stock.categories(db, sel, period.last_month)),
        below=[position_out(p) for p in stock.positions(db, sel, period.last_month, "below",
                                                        limit=SVOD_BELOW)])


def build_ostatki(db: Session, q: SectionQuery) -> SkladOstatkiOut:
    period, sel = q.period(), q.sel()
    return SkladOstatkiOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        branches=[StockBranchOut(branch_id=b.branch_id, name=b.name, value=b.value,
                                 positions=b.positions, below_min=b.below_min,
                                 idle_value=b.idle_value)
                  for b in stock.by_branch(db, sel, period)],
        categories=named_values_out(stock.categories(db, sel, period.last_month)))


def build_minimum(db: Session, q: SectionQuery) -> SkladMinimumOut:
    period, sel = q.period(), q.sel()
    return SkladMinimumOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        below=[position_out(p) for p in stock.positions(db, sel, period.last_month, "below")])


def build_nelikvid(db: Session, q: SectionQuery) -> SkladNelikvidOut:
    period, sel = q.period(), q.sel()
    return SkladNelikvidOut(
        period=period_out(period), kpis=stock_kpis_out(stock.totals(db, sel, period)),
        ages=[AgeBucketOut(key=a.key, value=a.value)
              for a in stock.ages(db, sel, period.last_month)],
        illiquid=[position_out(p) for p in stock.positions(db, sel, period.last_month, "idle")])


@router.get("/svod", response_model=SkladSvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/ostatki", response_model=SkladOstatkiOut)
def ostatki(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.ostatki", q.cache_filters, lambda: build_ostatki(db, q))


@router.get("/minimum", response_model=SkladMinimumOut)
def minimum(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.minimum", q.cache_filters, lambda: build_minimum(db, q))


@router.get("/nelikvid", response_model=SkladNelikvidOut)
def nelikvid(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("sklad.nelikvid", q.cache_filters, lambda: build_nelikvid(db, q))
```

`backend/app/main.py` — import va `include_router` (`proizvodstvo_router` dan keyin):
```python
from app.sections.sklad import router as sklad_router
```
```python
    app.include_router(sklad_router, prefix=API_PREFIX)
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sklad_api.py tests/test_route_guards.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(sklad): Сводка, Остатки по складам, Минимальный запас, Неликвиды API

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 9: «Требует внимания» — ishlab chiqarish va ombor qoidalari

**Files:**
- Create: `backend/app/alerts/production.py`, `backend/app/alerts/stock.py`
- Modify: `backend/app/alerts/__init__.py`
- Test: `backend/tests/test_alerts_s3.py`

**Interfaces:**
- Consumes: `evaluator`, `breached`, `hit`, `RuleConfig`, `AlertHit`, `evaluate`, `load_rules`, `REGISTRY`, `queries.production.{has_stations, stations, totals}`, `queries.stock.{totals, positions}`, `fmt_money`, `fmt_pct`, `plural`, `ALERT_RULES` seed'lari (`generation_plan`: `{"op": "<", "value": 0.95, "per": "station"}`, `proizvodstvo/stancii`; `energy_payment_level`: `<` 0.85, `proizvodstvo/realiz`; `stock_below_minimum`: `>` 5, critical, `sklad/minimum`; `illiquid_stock_share`: `>` 0.2, `sklad/nelikvid`), `tests.s3_helpers.{production_scenario, stock_scenario}`, `tests.s2_helpers.put_rule`, `tests.s1_helpers.rebuild`.
- Produces: `app.alerts.production.generation_plan`, `app.alerts.production.energy_payment_level`, `app.alerts.stock.stock_below_minimum`, `app.alerts.stock.illiquid_stock_share` (reyestrga yozilgan). Ma'lumot yo'q (stansiya yo'q, reja yo'q, realizatsiya yo'q, minimum yo'q, yosh noma'lum) — `None`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_alerts_s3.py`:
```python
from collections.abc import Iterator

import pytest
import redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate, load_rules
from app.alerts.types import REGISTRY
from app.core.config import get_settings
from app.core.db import apply_rls, new_session
from app.etl.db import etl_transaction
from app.sections.deps import SectionQuery
from tests.etl_helpers import (
    TEST_AS_OF,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s1_helpers import rebuild
from tests.s2_helpers import put_rule
from tests.s3_helpers import ProdScenario, StockScenario, production_scenario, stock_scenario

PROD = frozenset({"section:proizvodstvo:view"})
SKLAD = frozenset({"section:sklad:view"})


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def prod() -> Iterator[ProdScenario]:
    source = new_source()
    yield production_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture(scope="module")
def stk() -> Iterator[StockScenario]:
    source = new_source()
    yield stock_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture(scope="module")
def bare_branch() -> Iterator[int]:
    """1C'ning joriy shakli kabi: qiymat bor, minimum va oxirgi harakat sanasi yo'q."""
    source = new_source()
    tag = new_tag()
    run = open_run(source)
    stage(run, source, {
        "dim_branch": [branch_row(tag)],
        "dim_nomenclature": [{"code": f"ACC-{tag}", "name": "Материалы (10.1)",
                              "category": "Сырьё и материалы", "unit": "—", "enbt_code": None}],
        "fact_stock": [{"doc_type": "onec_stock", "src_id": "x1", "date_id": 20260831,
                        "branch_code": f"T-{tag}", "nom_code": f"ACC-{tag}",
                        "warehouse": "Основной склад", "qty": 0, "value": 50,
                        "min_qty": None, "last_move_date_id": None}],
    })
    merge_all(run, source)
    rebuild(run, publish=True)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": f"T-{tag}"}).scalar_one())
    yield branch_id
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str) -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def test_registry_has_s3_rules() -> None:
    assert {"generation_plan", "energy_payment_level", "stock_below_minimum",
            "illiquid_stock_share"} <= set(REGISTRY)


def test_production_rules_fire(prod: ProdScenario, db: Session) -> None:
    hits, checked = evaluate(db, _q(prod.branch_id, "m08"), PROD)
    assert [h.code for h in hits] == ["generation_plan", "energy_payment_level"]
    plan, pay = hits
    # Stansiya qisqa nomi — tests.etl_helpers.branch_row'dagi short_name.
    assert plan.message.startswith("1 ГЭС не выполняет план выработки: ")
    assert plan.message.endswith(f"{prod.tag} 90%")
    assert (plan.section, plan.page, plan.level, plan.value) == ("proizvodstvo", "stancii",
                                                                  "warning", 1.0)
    assert pay.message == "75,0%: оплачено 900,0 млн из 1,2 млрд" and pay.value == 0.75
    assert pay.page == "realiz"
    assert checked == ["Выполнение плана выработки", "Уровень оплаты за энергию"]
    # m09: bajarilish 83% (reja ulushlangan), to'lov darajasi 90% — faqat reja qoidasi.
    assert [h.code for h in evaluate(db, _q(prod.branch_id, "m09"), PROD)[0]] == [
        "generation_plan"]


def test_production_thresholds_from_db(prod: ProdScenario, db: Session) -> None:
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("generation_plan", threshold={**rules["generation_plan"].threshold,
                                               "value": 0.85})
        put_rule("energy_payment_level", threshold={**rules["energy_payment_level"].threshold,
                                                    "value": 0.7})
        assert evaluate(db, _q(prod.branch_id, "m08"), PROD)[0] == []
    finally:
        put_rule("generation_plan", threshold=rules["generation_plan"].threshold)
        put_rule("energy_payment_level", threshold=rules["energy_payment_level"].threshold)


def test_production_rules_skip_without_data(prod: ProdScenario, db: Session) -> None:
    assert evaluate(db, _q(prod.hq_id, "m08"), PROD)[0] == []
    assert evaluate(db, _q(prod.branch_id, "m01"), PROD)[0] == []  # reja va realizatsiya yo'q
    assert evaluate(db, _q(prod.branch_id, "m08"), SKLAD)[0] == []


def test_stock_rules(stk: StockScenario, db: Session) -> None:
    hits = evaluate(db, _q(stk.branch_id, "m08"), SKLAD)[0]
    assert [h.code for h in hits] == ["illiquid_stock_share"]
    assert hits[0].message == "66,7% стоимости запасов без движения более 180 дней: 80,0 млн"
    assert hits[0].page == "nelikvid" and hits[0].value == pytest.approx(0.666667)
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("stock_below_minimum", threshold={**rules["stock_below_minimum"].threshold,
                                                   "value": 0})
        below = evaluate(db, _q(stk.branch_id, "m08"), SKLAD)[0][0]
        assert below.code == "stock_below_minimum" and below.level == "critical"
        assert below.message == "1 позиция ниже минимального запаса: Подшипник тестовый"
        assert evaluate(db, _q(stk.branch_id, "m09"), SKLAD)[0] == []  # m09: past yo'q, 15%
    finally:
        put_rule("stock_below_minimum", threshold=rules["stock_below_minimum"].threshold)


def test_stock_rules_skip_without_min_or_age(bare_branch: int, db: Session) -> None:
    rules = {r.code: r for r in load_rules(db)}
    try:
        for code in ("stock_below_minimum", "illiquid_stock_share"):
            put_rule(code, threshold={**rules[code].threshold, "value": -1})
        assert evaluate(db, _q(bare_branch, "m08"), SKLAD)[0] == []
    finally:
        for code in ("stock_below_minimum", "illiquid_stock_share"):
            put_rule(code, threshold=rules[code].threshold)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_alerts_s3.py -v`
Expected: FAIL — `test_registry_has_s3_rules` (`generation_plan` reyestrda yo'q).

- [ ] **Step 3: Implementatsiya**

`backend/app/alerts/production.py`:
```python
"""TZ 4 «Требует внимания» — ishlab chiqarish qoidalari (chegaralar — core.alert_rules, S3 spec 7).

generation_plan — stansiya bo'yicha (seed: per=station): reja > 0 bo'lgan stansiyalardan bajarilishi
chegaradan past bo'lganlar soni. energy_payment_level — tanlov jamida оплачено / начислено.
Stansiya, reja yoki realizatsiya bo'lmasa — None (yolg'on signal yo'q).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import production


@evaluator("generation_plan")
def generation_plan(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    sel = q.sel()
    if not production.has_stations(db, sel):
        return None
    low = sorted((s for s in production.stations(db, sel, q.period())
                  if s.execution is not None and breached(s.execution, rule)),
                 key=lambda s: (s.execution or 0.0, s.name))
    if not low:
        return None
    n = len(low)
    verb = plural(n, "ГЭС не выполняет", "ГЭС не выполняют", "ГЭС не выполняют")
    names = ", ".join(f"{s.short_name} {fmt_pct(s.execution or 0.0, 0)}" for s in low[:3])
    return hit(rule, f"{n} {verb} план выработки: {names}", float(n))


@evaluator("energy_payment_level")
def energy_payment_level(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    totals = production.totals(db, q.sel(), q.period())
    level = totals.payment_level
    if level is None or not breached(level, rule):
        return None
    return hit(rule, f"{fmt_pct(level)}: оплачено {fmt_money(totals.paid)} "
                     f"из {fmt_money(totals.accrued)}", level)
```

`backend/app/alerts/stock.py`:
```python
"""TZ 4 «Требует внимания» — ombor qoidalari (S3 spec 7).

Minimum (min_qty) yoki oxirgi harakat sanasi manbada bo'lmasa (1C'ning joriy javobi) qoida
o'tkazib yuboriladi — nol «past pozitsiya» yoki nol «неликвид» deb hisoblanmaydi.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import stock


@evaluator("stock_below_minimum")
def stock_below_minimum(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    period, sel = q.period(), q.sel()
    totals = stock.totals(db, sel, period)
    if not totals.has_minimum or not breached(float(totals.below_min), rule):
        return None
    top = stock.positions(db, sel, period.last_month, "below", limit=2)
    word = plural(totals.below_min, "позиция", "позиции", "позиций")
    names = ", ".join(p.name for p in top)
    return hit(rule, f"{totals.below_min} {word} ниже минимального запаса: {names}",
               float(totals.below_min))


@evaluator("illiquid_stock_share")
def illiquid_stock_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    totals = stock.totals(db, q.sel(), q.period())
    share = totals.idle_share
    if share is None or not breached(share, rule):
        return None
    return hit(rule, f"{fmt_pct(share)} стоимости запасов без движения более 180 дней: "
                     f"{fmt_money(totals.idle_value)}", share)
```

`backend/app/alerts/__init__.py` — import qatorini almashtiring:
```python
from app.alerts import loans, production, stock, treasury  # noqa: F401
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_alerts_s3.py tests/test_alerts.py tests/test_alerts_loans.py -v`
Expected: barcha testlar passed (S1 `test_vnimanie_endpoints` S1 ssenariysi filialida — ishlab chiqarish/ombor fakti yo'q, yangi qoidalar yonmaydi).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(alerts): ishlab chiqarish rejasi, to'lov darajasi, minimum zaxira va неликвид qoidalari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 10: АСКУЭ — kanonik CSV parseri va eksport manbalari interfeysi (katalog, API stub'i)

**Files:**
- Create: `backend/app/etl/askue/canonical.py`, `backend/app/etl/askue/export.py`, `backend/tests/fixtures/askue/askue_2026-09-23.csv`
- Test: `backend/tests/test_askue_canonical.py`

**Interfaces:**
- Consumes: `ConfigError`, `ConnectorUnavailableError`, `HealthResult`, `Window`.
- Produces:
  - `app.etl.askue.canonical`: `COLUMNS = ("station", "date", "generation_mwh", "own_needs_mwh", "supply_mwh", "work_hours")`, `MAX_ROWS = 100_000`, `AskueFileError(code, message)` (`ValueError`; kodlar `bad_encoding`, `bad_header`, `too_many_rows`), `AskueRow(line, station, day, generation, own_needs, supply, work_hours)` (MVt·soat, `Decimal`; `supply`/`work_hours` — `None` bo'lishi mumkin), `RowError(line, code, message)` (kodlar `bad_row`, `negative`, `own_gt_generation`, `bad_hours`, `future_date`, `duplicate_row`), `ParsedAskue(rows, errors)`, `parse_canonical(data: bytes, *, today: date) -> ParsedAskue`.
  - `app.etl.askue.export`: `MAX_BYTES = 20 MiB`, `MIN_AGE_SECONDS = 60.0`, `ASKUE_API_MESSAGE`, `ExportFile(name, data, error=None)`, `AskueExport` (Protocol: `name`, `healthcheck() -> HealthResult`, `files(window) -> Iterator[ExportFile]`), `DirectoryExport(inbox, *, max_age_days=7, min_age=60.0, max_bytes=MAX_BYTES, now=time.time)`, `AskueNotConfigured(ConfigError)`, `AskueApiExport()` (yaratishda `AskueNotConfigured`).

- [ ] **Step 1: Namunaviy fayl (hujjatdagi misol bilan bir xil)**

`backend/tests/fixtures/askue/askue_2026-09-23.csv`:
```
station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours
CHARVAK-1;2026-09-22;4810.6;72.2;4738.4;24
CHARVAK-1;2026-09-23;4702;70.4;;23.5
CHIRCHIQ-7;2026-09-23;1320.25;20.1;1300.15;24
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_askue_canonical.py`:
```python
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.etl.askue import canonical
from app.etl.askue.canonical import AskueFileError, parse_canonical
from app.etl.askue.export import (
    AskueApiExport,
    AskueNotConfigured,
    DirectoryExport,
)
from app.etl.types import ConnectorUnavailableError, Window

FIXTURE = Path(__file__).parent / "fixtures" / "askue" / "askue_2026-09-23.csv"
TODAY = date(2026, 9, 24)
HEADER = "station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours"
WINDOW = Window(date(2026, 9, 1), TODAY)


def _parse(*lines: str) -> canonical.ParsedAskue:
    return parse_canonical("\n".join((HEADER, *lines)).encode("utf-8"), today=TODAY)


def test_fixture_parses_with_optional_fields() -> None:
    parsed = parse_canonical(FIXTURE.read_bytes(), today=TODAY)
    assert parsed.errors == ()
    first, second, third = parsed.rows
    assert (first.station, first.day, first.generation, first.own_needs, first.supply,
            first.work_hours) == ("CHARVAK-1", date(2026, 9, 22), Decimal("4810.6"),
                                  Decimal("72.2"), Decimal("4738.4"), Decimal("24"))
    assert second.supply is None and second.work_hours == Decimal("23.5")
    assert third.line == 4 and third.generation == Decimal("1320.25")


def test_bom_and_blank_lines_are_accepted() -> None:
    data = ("\ufeff" + HEADER + "\n\nA-1;2026-09-20;10;1;;\n").encode("utf-8")
    parsed = parse_canonical(data, today=TODAY)
    assert [r.station for r in parsed.rows] == ["A-1"] and parsed.errors == ()


@pytest.mark.parametrize(("data", "code"), [
    ("station;date;generation;own;supply;hours\nA;2026-09-20;1;0;;".encode(), "bad_header"),
    (f"{HEADER}\nСтанция;2026-09-20;1;0;;".encode("cp1251"), "bad_encoding"),
    (b"", "bad_header"),
])
def test_file_level_errors(data: bytes, code: str) -> None:
    with pytest.raises(AskueFileError) as exc:
        parse_canonical(data, today=TODAY)
    assert exc.value.code == code


def test_row_errors_do_not_stop_parsing() -> None:
    parsed = _parse(
        "A-1;2026-09-20;100;2;98;24",
        "A-1;2026-09-20;100;2;98;24",  # takror
        "A-2;20.09.2026;100;2;;",  # sana formati
        "A-3;2026-09-20;1 000;2;;",  # razryad ajratkichi
        "A-4;2026-09-20;-5;0;;",
        "A-5;2026-09-20;10;12;;",
        "A-6;2026-09-20;10;1;;25",
        "A-7;2026-09-25;10;1;;",
        "bad code;2026-09-20;10;1;;",
        "A-8;2026-09-20;10;1",
        "A-9;2026-09-21;10,5;1;;",
    )
    assert [r.station for r in parsed.rows] == ["A-1"]
    assert [(e.line, e.code) for e in parsed.errors] == [
        (3, "duplicate_row"), (4, "bad_row"), (5, "bad_row"), (6, "negative"),
        (7, "own_gt_generation"), (8, "bad_hours"), (9, "future_date"), (10, "bad_row"),
        (11, "bad_row"), (12, "bad_row")]


def test_too_many_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canonical, "MAX_ROWS", 2)
    with pytest.raises(AskueFileError) as exc:
        _parse("A-1;2026-09-20;1;0;;", "A-1;2026-09-21;1;0;;", "A-1;2026-09-22;1;0;;")
    assert exc.value.code == "too_many_rows"


def test_directory_export_filters_files(tmp_path: Path) -> None:
    now = 1_790_000_000.0
    files = {"ok.csv": now - 3600, "fresh.csv": now - 10, "old.csv": now - 9 * 86400,
             "note.txt": now - 3600, "big.csv": now - 3600}
    for name, mtime in files.items():
        path = tmp_path / name
        path.write_bytes(b"x" * (2000 if name == "big.csv" else 10))
        os.utime(path, (mtime, mtime))
    (tmp_path / "link.csv").symlink_to(tmp_path / "ok.csv")
    export = DirectoryExport(tmp_path, max_age_days=7, max_bytes=1000, now=lambda: now)
    got = {(f.name, f.error) for f in export.files(WINDOW)}
    assert got == {("ok.csv", None), ("big.csv", "too_large")}
    assert export.healthcheck().ok is True
    missing = DirectoryExport(tmp_path / "nope")
    assert missing.healthcheck().ok is False
    with pytest.raises(ConnectorUnavailableError):
        list(missing.files(WINDOW))


def test_api_export_is_not_configured() -> None:
    with pytest.raises(AskueNotConfigured, match="АСКУЭ API не настроен"):
        AskueApiExport()
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_askue_canonical.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.askue.canonical'`.

- [ ] **Step 4: Implementatsiya — kanonik CSV**

`backend/app/etl/askue/canonical.py`:
```python
"""АСКУЭ kunlik eksportining kanonik CSV formati (docs/integration/askue-format.md;
TZ 8 «Общие правила обмена»: UTF-8, «;», ISO sanalar, nuqta, razryad ajratkichsiz).

station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours — stansiya × sutka, MVt·soat.
Fayl darajasidagi xato (kodlash, sarlavha, hajm) — AskueFileError; qator xatolari yig'iladi,
yaroqli qatorlar qaytariladi. Xato matnlarida faqat qator raqami va qisqa maydon qiymati.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

COLUMNS = ("station", "date", "generation_mwh", "own_needs_mwh", "supply_mwh", "work_hours")
MAX_ROWS = 100_000
_NUM = re.compile(r"^\d{1,9}(\.\d{1,3})?$")
_NEG = re.compile(r"^-\d")
_HOURS = re.compile(r"^\d{1,2}(\.\d{1,2})?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STATION = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class AskueFileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AskueRow:
    line: int
    station: str
    day: date
    generation: Decimal  # MVt·soat
    own_needs: Decimal
    supply: Decimal | None
    work_hours: Decimal | None


@dataclass(frozen=True, slots=True)
class RowError:
    line: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ParsedAskue:
    rows: tuple[AskueRow, ...]
    errors: tuple[RowError, ...]


class _Problem(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _amount(value: str, field: str) -> Decimal:
    if _NEG.match(value):
        raise _Problem("negative", f"{field}: отрицательное значение")
    if not _NUM.fullmatch(value):
        raise _Problem("bad_row", f"{field}: ожидается число с точкой, без разделителей")
    return Decimal(value)


def _row(line: int, fields: list[str], today: date) -> AskueRow:
    station, day_s, gen_s, own_s, sup_s, hrs_s = (f.strip() for f in fields)
    if not _STATION.fullmatch(station):
        raise _Problem("bad_row", f"код станции «{station[:40]}» недопустим")
    try:
        if not _DATE.fullmatch(day_s):
            raise ValueError(day_s)
        day = date.fromisoformat(day_s)
    except ValueError as exc:
        raise _Problem("bad_row", f"дата «{day_s[:20]}»: нужен формат ГГГГ-ММ-ДД") from exc
    if day > today:
        raise _Problem("future_date", f"дата {day:%d.%m.%Y} в будущем")
    generation = _amount(gen_s, "generation_mwh")
    own = _amount(own_s, "own_needs_mwh")
    if own > generation:
        raise _Problem("own_gt_generation", "собственные нужды больше выработки")
    supply = _amount(sup_s, "supply_mwh") if sup_s else None
    hours: Decimal | None = None
    if hrs_s:
        if not _HOURS.fullmatch(hrs_s) or Decimal(hrs_s) > 24:
            raise _Problem("bad_hours", "work_hours: от 0 до 24")
        hours = Decimal(hrs_s)
    return AskueRow(line, station, day, generation, own, supply, hours)


def parse_canonical(data: bytes, *, today: date) -> ParsedAskue:
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AskueFileError("bad_encoding", "файл не в кодировке UTF-8") from exc
    reader = csv.reader(io.StringIO(content, newline=""), delimiter=";")
    header = next(reader, None)
    if header is None or tuple(h.strip().lower() for h in header) != COLUMNS:
        raise AskueFileError("bad_header", f"заголовок должен быть «{';'.join(COLUMNS)}»")
    rows: list[AskueRow] = []
    errors: list[RowError] = []
    seen: set[tuple[str, date]] = set()
    for line, raw in enumerate(reader, start=2):
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if len(rows) + len(errors) >= MAX_ROWS:
            raise AskueFileError("too_many_rows", f"в файле больше {MAX_ROWS} строк")
        if len(raw) != len(COLUMNS):
            errors.append(RowError(line, "bad_row", "неверное число полей"))
            continue
        try:
            row = _row(line, raw, today)
        except _Problem as problem:
            errors.append(RowError(line, problem.code, problem.message))
            continue
        key = (row.station, row.day)
        if key in seen:
            errors.append(RowError(line, "duplicate_row",
                                   f"{row.station} {row.day:%d.%m.%Y}: повтор строки"))
            continue
        seen.add(key)
        rows.append(row)
    return ParsedAskue(tuple(rows), tuple(errors))
```

- [ ] **Step 5: Implementatsiya — eksport manbalari**

`backend/app/etl/askue/export.py`:
```python
"""АСКУЭ eksporti manbalari (S3 spec 3.1). Transport mijoz bilan kelishilmagan (TZ 8: «выгрузка
по расписанию или API»), shuning uchun protokol: DirectoryExport — worker'ga faqat o'qish uchun
ulangan katalog (/data/import/askue); AskueApiExport — «не настроен» stub'i.

Katalogdan oxirgi `max_age_days` kun ichida o'zgargan va yoshi ≥ `min_age` s bo'lgan *.csv
fayllar har yugurishda qayta o'qiladi: yuklash upsert (stansiya:sana kaliti) — idempotent, jurnal
va arxiv kerak emas; eski fayllarni host cron o'chiradi (docs/integration/askue-connector.md).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import ConfigError
from app.etl.types import ConnectorUnavailableError, HealthResult, Window

MAX_BYTES = 20 * 1024 * 1024
MIN_AGE_SECONDS = 60.0
ASKUE_API_MESSAGE = ("АСКУЭ API не настроен: формат и доступ не согласованы с заказчиком — "
                     "используйте выгрузку файлов в каталог /data/import/askue")


@dataclass(frozen=True, slots=True)
class ExportFile:
    name: str
    data: bytes
    error: str | None = None  # "too_large" — fayl o'qilmadi


class AskueExport(Protocol):
    name: str

    def healthcheck(self) -> HealthResult: ...

    def files(self, window: Window) -> Iterator[ExportFile]: ...


class DirectoryExport:
    name = "files"

    def __init__(self, inbox: Path, *, max_age_days: int = 7, min_age: float = MIN_AGE_SECONDS,
                 max_bytes: int = MAX_BYTES, now: Callable[[], float] = time.time) -> None:
        self.inbox = inbox
        self.max_age_days = max_age_days
        self.min_age = min_age
        self.max_bytes = max_bytes
        self.now = now

    def healthcheck(self) -> HealthResult:
        if self.inbox.is_dir():
            return HealthResult(True, f"АСКУЭ: каталог {self.inbox}")
        return HealthResult(False, f"АСКУЭ: каталог {self.inbox} не найден")

    def files(self, window: Window) -> Iterator[ExportFile]:
        if not self.inbox.is_dir():
            raise ConnectorUnavailableError(f"АСКУЭ: каталог {self.inbox} недоступен")
        now = self.now()
        oldest = now - self.max_age_days * 86400
        for path in sorted(self.inbox.iterdir()):
            if path.suffix.lower() != ".csv" or path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            if stat.st_mtime > now - self.min_age or stat.st_mtime < oldest:
                continue
            if stat.st_size > self.max_bytes:
                yield ExportFile(path.name, b"", "too_large")
                continue
            yield ExportFile(path.name, path.read_bytes())


class AskueNotConfigured(ConfigError):
    """АСКУЭ API hali kelishilmagan (spec 12, ochiq savol 1)."""


class AskueApiExport:
    name = "api"

    def __init__(self) -> None:
        raise AskueNotConfigured(ASKUE_API_MESSAGE)

    def healthcheck(self) -> HealthResult:
        raise AskueNotConfigured(ASKUE_API_MESSAGE)

    def files(self, window: Window) -> Iterator[ExportFile]:
        raise AskueNotConfigured(ASKUE_API_MESSAGE)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_askue_canonical.py -v`
Expected: 9 passed (parametrize bilan). `$TEST ruff check app tests` va `$TEST mypy app` — xatosiz.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(askue): kanonik CSV parseri, katalog eksporti va API stub'i

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 11: `AskueConnector` — stansiyalar moslashtirishi, xatolar jurnali, manbalar reyestri, CLI va worker jadvali

**Files:**
- Create: `backend/app/etl/askue/connector.py`, `backend/app/etl/askue/admin.py`
- Modify: `backend/app/etl/connectors.py`, `backend/app/cli.py`, `backend/app/worker.py` (`notify_rejected_rows`, `notify_bank_errors`, `notify_askue_errors`, `run_askue_job`, `build_scheduler`), `backend/tests/test_worker.py`
- Test: `backend/tests/test_askue_connector.py`

**Interfaces:**
- Consumes: `AskueExport`, `ExportFile`, `DirectoryExport`, `parse_canonical`, `AskueFileError`, `AskueStation`, `STATION_KINDS`, `ReportingSink` (S2), `DbStagingSink`, `ExtractStats`, `HealthResult`, `Watermark`, `Window`, `date_id`, `today_tashkent`, `Runner`, `Mode`, `current_setting`, `validate_setting`, `record`, `AuditAction.SETTING_UPDATED`, `banks.admin._put`, `run_etl_job`, `Notification`, `Kind`, `RecordingNotifier`, `tests.etl_helpers.*`.
- Produces:
  - `app.etl.askue.connector`: `SOURCE = "askue"`, `DOC_TYPE = "askue_daily"`, `ERROR_TARGET = "askue_file"`, `ERROR_LIMIT = 1000`, `to_mln_kwh(mwh: Decimal) -> Decimal` (÷ 1000, 3 kasr, ROUND_HALF_EVEN), `AskueConnector(export, stations, *, source=SOURCE, today=today_tashkent, now=...)` — `SourceConnector`; `extract` `ReportingSink` talab qiladi, `ExtractStats(rows, {})` qaytaradi (maqsadlar «to'liq» emas — upsert). Qator kaliti `src_id = "<station>:<YYYYMMDD>"`; oynadan tashqari qatorlar o'tkaziladi; `supply` bo'sh bo'lsa `generation − own_needs`. Xato kodlari: parser kodlari + `too_large`, `unknown_station`, `too_many_errors`.
  - `app.etl.askue.admin`: `askue_stations_command(file: Path | None, out) -> int` (0 / 1; stansiya bog'lanadigan filial `kind ∈ ges|cascade` bo'lishi shart; audit `admin.setting.updated` `via=cli`).
  - `KNOWN_SOURCES` += `"askue"`; `make_connector("askue")` (`askue.stations` bo'sh → `ConfigError`).
  - Worker: `notify_rejected_rows(run_id, notifier, *, target, kind, subject, hint) -> int`, `notify_bank_errors` (S2 xulqi o'zgarmaydi, umumiy funksiya orqali), `notify_askue_errors(run_id, notifier) -> int`, `run_askue_job(notifier) -> RunResult | None`; job `etl_askue` (`etl.askue_cron`) — faqat `askue_inbox_dir` mavjud bo'lsa.
  - CLI: `python -m app.cli askue-stations [--file stations.json]`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_askue_connector.py`:
```python
import json
import os
import time
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.dwh import builds
from app.dwh.reference import current_setting
from app.etl.askue.connector import AskueConnector, to_mln_kwh
from app.etl.askue.export import ExportFile
from app.etl.askue.registry import AskueStation
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
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

FIXTURE = Path(__file__).parent / "fixtures" / "askue" / "askue_2026-09-23.csv"
WINDOW = Window(date(2026, 9, 1), TEST_AS_OF)
STATIONS = [AskueStation(code="CHARVAK-1", name="Chorvoq GES", branch_code="UGE-02"),
            AskueStation(code="CHIRCHIQ-7", name="Chirchiq GES-7", branch_code="UGE-03")]


class ReportSink:
    def __init__(self) -> None:
        self.load_id = 0
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[tuple[str, str, str]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append((target, code, message))


class ListExport:
    name = "list"

    def __init__(self, *files: ExportFile) -> None:
        self._files = files

    def healthcheck(self) -> HealthResult:
        return HealthResult(True, "list")

    def files(self, window: Window) -> Iterator[ExportFile]:
        yield from self._files


def _extract(*files: ExportFile, stations: list[AskueStation] = STATIONS,
             window: Window = WINDOW) -> ReportSink:
    sink = ReportSink()
    AskueConnector(ListExport(*files), stations, today=lambda: TEST_AS_OF).extract(window, sink)
    return sink


def test_units_and_mapping() -> None:
    assert to_mln_kwh(Decimal("4810.6")) == Decimal("4.811")
    sink = _extract(ExportFile("a.csv", FIXTURE.read_bytes()))
    assert sink.errors == []
    rows = [r for _, r in sink.rows]
    assert [(r["src_id"], r["branch_code"], r["generation"], r["own_needs"], r["supply"])
            for r in rows] == [
        ("CHARVAK-1:20260922", "UGE-02", Decimal("4.811"), Decimal("0.072"), Decimal("4.738")),
        ("CHARVAK-1:20260923", "UGE-02", Decimal("4.702"), Decimal("0.070"), Decimal("4.632")),
        ("CHIRCHIQ-7:20260923", "UGE-03", Decimal("1.320"), Decimal("0.020"), Decimal("1.300")),
    ]
    assert all(r["doc_type"] == "askue_daily" and r["plan"] is None for r in rows)
    assert rows[1]["work_hours"] == Decimal("23.5") and rows[0]["date_id"] == 20260922


def test_unknown_station_is_reported() -> None:
    sink = _extract(ExportFile("a.csv", FIXTURE.read_bytes()), stations=STATIONS[:1])
    assert len(sink.rows) == 2
    assert [(t, c) for t, c, _ in sink.errors] == [("askue_file", "unknown_station")]
    assert "a.csv:4" in sink.errors[0][2] and "CHIRCHIQ-7" in sink.errors[0][2]


def test_bad_rows_are_reported_not_fatal() -> None:
    header = b"station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours\n"
    sink = _extract(ExportFile("bad.csv", b"not;a;header\n1;2;3"),
                    ExportFile("big.csv", b"", "too_large"),
                    ExportFile("rows.csv", header + b"CHARVAK-1;2026-09-20;-1;0;;\n"
                                                    b"CHARVAK-1;2026-09-21;100;1;;\n"))
    assert [c for _, c, _ in sink.errors] == ["bad_header", "too_large", "negative"]
    assert [r["src_id"] for _, r in sink.rows] == ["CHARVAK-1:20260921"]
    assert all(msg.startswith(("bad.csv", "big.csv", "rows.csv:2")) for _, _, msg in sink.errors)


def test_rows_outside_window_are_skipped() -> None:
    sink = _extract(ExportFile("a.csv", FIXTURE.read_bytes()),
                    window=Window(date(2026, 9, 23), TEST_AS_OF))
    assert [r["date_id"] for _, r in sink.rows] == [20260923, 20260923]


def test_requires_reporting_sink() -> None:
    class Plain:
        def add(self, target: str, row: Mapping[str, Any]) -> None: ...

    with pytest.raises(TypeError):
        AskueConnector(ListExport(), STATIONS).extract(WINDOW, Plain())


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def _inbox(tmp_path: Path, content: bytes) -> Path:
    inbox = tmp_path / "askue"
    inbox.mkdir()
    path = inbox / "askue_2026-09-23.csv"
    path.write_bytes(content)
    old = time.time() - 3600
    os.utime(path, (old, old))
    return inbox


def _test_branches(source: str, capacity: float) -> tuple[str, str]:
    tag = new_tag()
    a, b = branch_row(tag, capacity_mw=capacity), branch_row(f"{tag}B", capacity_mw=capacity)
    run = open_run(source)
    stage(run, source, {"dim_branch": [a, b]})
    merge_all(run, source)
    return a["code"], b["code"]


def _stations(a: str, b: str) -> list[AskueStation]:
    return [AskueStation(code="CHARVAK-1", name="Chorvoq GES", branch_code=a),
            AskueStation(code="CHIRCHIQ-7", name="Chirchiq GES-7", branch_code=b)]


def test_runner_loads_idempotently(source: str, tmp_path: Path) -> None:
    from app.etl.askue.export import DirectoryExport

    a, b = _test_branches(source, capacity=300)  # 300 × 24 = 7200 MVt·soat ≥ 4810,6
    inbox = _inbox(tmp_path, FIXTURE.read_bytes())
    for _ in range(2):
        connector = AskueConnector(DirectoryExport(inbox), _stations(a, b), source=source,
                                   today=lambda: TEST_AS_OF)
        result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                        sleep=lambda _: None).run()
        assert result.status == "success", result
    with etl_transaction() as conn:
        rows = conn.execute(text("SELECT src_id, generation FROM dwh.fact_generation "
                                 "WHERE src_system = :s ORDER BY src_id"), {"s": source}).all()
    assert [(r.src_id, r.generation) for r in rows] == [
        ("CHARVAK-1:20260922", Decimal("4.811")), ("CHARVAK-1:20260923", Decimal("4.702")),
        ("CHIRCHIQ-7:20260923", Decimal("1.320"))]


def test_runner_rejects_generation_above_capacity(source: str, tmp_path: Path) -> None:
    from app.etl.askue.export import DirectoryExport

    a, b = _test_branches(source, capacity=100)  # 100 × 24 = 2400 MVt·soat < 4810,6
    with etl_transaction() as conn:
        before = builds.active_build(conn)
    connector = AskueConnector(DirectoryExport(_inbox(tmp_path, FIXTURE.read_bytes())),
                               _stations(a, b), source=source, today=lambda: TEST_AS_OF)
    result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                    sleep=lambda _: None).run()
    assert result.status == "failed_quality"
    with etl_transaction() as conn:
        assert builds.active_build(conn) == before
        detail = conn.execute(text("SELECT detail FROM core.etl_step WHERE run_id = :r "
                                   "AND name = 'quality'"), {"r": result.run_id}).scalar_one()
    assert detail["capacity_limit"]["ok"] is False


@pytest.fixture
def stations_setting() -> Iterator[None]:
    yield
    put_setting("askue.stations", [])


def test_askue_stations_cli_and_make_connector(tmp_path: Path, stations_setting: None,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "stations.json"
    good.write_text(json.dumps([s.model_dump() for s in STATIONS], ensure_ascii=False),
                    encoding="utf-8")
    assert cli.main(["askue-stations", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        assert current_setting(conn, "askue.stations") == [s.model_dump() for s in STATIONS]
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["stations"] == 2
    assert cli.main(["askue-stations"]) == 0
    hq = tmp_path / "hq.json"
    hq.write_text(json.dumps([{"code": "X-1", "name": "X", "branch_code": "UGE-01"}]),
                  encoding="utf-8")
    assert cli.main(["askue-stations", "--file", str(hq)]) == 1
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps([{"code": "X-1", "name": "X", "branch_code": "NOPE"}]),
                       encoding="utf-8")
    assert cli.main(["askue-stations", "--file", str(unknown)]) == 1
    out = capsys.readouterr().out
    assert "CHARVAK-1" in out and "UGE-01" in out and "NOPE" in out
    assert "askue" in KNOWN_SOURCES
    made = make_connector("askue", get_settings().model_copy(
        update={"askue_inbox_dir": str(tmp_path)}))
    assert isinstance(made, AskueConnector) and [s.code for s in made.stations] == [
        "CHARVAK-1", "CHIRCHIQ-7"]
    put_setting("askue.stations", [])
    with pytest.raises(ConfigError, match="askue.stations"):
        make_connector("askue", get_settings())


def test_notify_askue_errors() -> None:
    source = new_source()
    run = open_run(source)
    notifier = RecordingNotifier()
    assert worker.notify_askue_errors(run, notifier) == 0 and notifier.items == []
    with etl_transaction() as conn:
        sink = DbStagingSink(conn, run, source)
        for code in ("unknown_station", "negative", "negative"):
            sink.error(target="askue_file", code=code, message="m")
    assert worker.notify_askue_errors(run, notifier) == 3
    assert notifier.kinds == ["askue_rows_rejected"]
    body = notifier.items[0].body
    assert "negative: 2" in body and "unknown_station: 1" in body
    assert worker.notify_bank_errors(run, notifier) == 0  # boshqa target — sanalmaydi
```

`backend/tests/test_worker.py` — oxiriga qo'shing:
```python
def test_scheduler_adds_askue_job_when_inbox_exists(tmp_path: Path) -> None:
    settings = get_settings().model_copy(update={"askue_inbox_dir": str(tmp_path)})
    jobs = {j.id: j for j in worker.build_scheduler(settings, RecordingNotifier()).get_jobs()}
    assert jobs["etl_askue"].func is worker.run_askue_job
    missing = get_settings().model_copy(update={"askue_inbox_dir": str(tmp_path / "nope")})
    ids = {j.id for j in worker.build_scheduler(missing, RecordingNotifier()).get_jobs()}
    assert "etl_askue" not in ids
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_askue_connector.py tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.askue.connector'`.

- [ ] **Step 3: Implementatsiya — konnektor**

`backend/app/etl/askue/connector.py`:
```python
"""AskueConnector — SourceConnector (S3 spec 3.1): AskueExport fayllari → kanonik CSV →
fact_generation (stansiya × sutka, MVt·soat ÷ 1000 = mln kVt·soat).

Stansiya kodi → filial `askue.stations` orqali; moslashtirilmagan stansiya, buzilgan qator yoki
fayl → core.etl_error (ReportingSink, step extract, target askue_file), yaroqli qatorlar yuklanadi.
Maqsadlar «to'liq» deb belgilanmaydi (upsert, kalit stansiya:sana): fayllar inkremental.
Sutkalik ishlab chiqarish > quvvat × 24 → 2-reja sifat tekshiruvi 4 publish'ni to'xtatadi.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from app.core.logging import get_logger
from app.dwh.dates import date_id, today_tashkent
from app.etl.askue.canonical import AskueFileError, parse_canonical
from app.etl.askue.export import AskueExport
from app.etl.askue.registry import AskueStation
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "askue"
DOC_TYPE = "askue_daily"
ERROR_TARGET = "askue_file"
ERROR_LIMIT = 1000
_MWH_IN_MLN_KWH = Decimal(1000)
_VOLUME = Decimal("0.001")
log = get_logger("ugekazna.askue")


def to_mln_kwh(mwh: Decimal) -> Decimal:
    return (mwh / _MWH_IN_MLN_KWH).quantize(_VOLUME, rounding=ROUND_HALF_EVEN)


class AskueConnector:
    def __init__(self, export: AskueExport, stations: Sequence[AskueStation], *,
                 source: str = SOURCE, today: Callable[[], date] = today_tashkent,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.export = export
        self.stations = list(stations)
        self.today = today
        self.now = now

    def healthcheck(self) -> HealthResult:
        return self.export.healthcheck()

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("AskueConnector xatolarni yozish uchun ReportingSink talab qiladi")
        by_code = {s.code: s for s in self.stations}
        today = self.today()
        rows = errors = skipped = 0

        def report(code: str, message: str) -> None:
            nonlocal errors
            errors += 1
            if errors <= ERROR_LIMIT:
                sink.error(target=ERROR_TARGET, code=code, message=message[:500])

        for export_file in self.export.files(window):
            name = export_file.name[:120]
            if export_file.error:
                report(export_file.error, f"{name}: файл больше допустимого размера")
                continue
            try:
                parsed = parse_canonical(export_file.data, today=today)
            except AskueFileError as exc:
                report(exc.code, f"{name}: {exc.message}")
                continue
            for err in parsed.errors:
                report(err.code, f"{name}:{err.line}: {err.message}")
            for row in parsed.rows:
                station = by_code.get(row.station)
                if station is None:
                    report("unknown_station", f"{name}:{row.line}: станция «{row.station}» не "
                                              "сопоставлена с филиалом (askue.stations)")
                    continue
                if not window.contains(row.day):
                    skipped += 1
                    continue
                generation = to_mln_kwh(row.generation)
                own = to_mln_kwh(row.own_needs)
                supply = to_mln_kwh(row.supply) if row.supply is not None else generation - own
                sink.add("fact_generation", {
                    "doc_type": DOC_TYPE, "src_id": f"{row.station}:{date_id(row.day)}",
                    "date_id": date_id(row.day), "branch_code": station.branch_code,
                    "generation": generation, "own_needs": own, "supply": supply,
                    "plan": None, "work_hours": row.work_hours})
                rows += 1
        if errors > ERROR_LIMIT:
            sink.error(target=ERROR_TARGET, code="too_many_errors",
                       message=f"ещё {errors - ERROR_LIMIT} ошибок не записано")
        if skipped:
            log.info("askue_rows_outside_window", skipped=skipped)
        return ExtractStats(rows, {})
```

- [ ] **Step 4: Implementatsiya — operator buyrug'i**

`backend/app/etl/askue/admin.py`:
```python
"""Operator CLI: АСКУЭ stansiyalari ↔ filiallar moslashtirishi (`askue.stations`).

Stansiya faqat ГЭС/kaskad filialiga bog'lanadi (HQ — yo'q). Yangi versiya + audit (via=cli).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, record
from app.core.db import get_engine
from app.dwh.reference import current_setting, validate_setting
from app.etl.askue.registry import STATION_KINDS
from app.etl.banks.admin import _put
from app.etl.db import etl_transaction

Out = Callable[[str], None]


def _show(stations: list[dict[str, str]], out: Out) -> None:
    for s in stations:
        out(f"{s['code']:<20} {s['branch_code']:<10} {s['name']}")


def askue_stations_command(file: Path | None, out: Out) -> int:
    if file is None:
        with get_engine("app").connect() as conn:
            current = list(current_setting(conn, "askue.stations"))
        _show(current, out)
        out(f"askue.stations: {len(current)} ta stansiya")
        return 0
    try:
        value = validate_setting("askue.stations", json.loads(file.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        out(f"Xato: {exc}")
        return 1
    with etl_transaction() as conn:
        kinds = dict(conn.execute(text("SELECT code, kind FROM dwh.dim_branch")).all())
    missing = sorted({s["branch_code"] for s in value} - set(kinds))
    if missing:
        out(f"Xato: noma'lum filial kodlari: {', '.join(missing)}")
        return 1
    not_station = sorted({s["branch_code"] for s in value if kinds[s["branch_code"]]
                          not in STATION_KINDS})
    if not_station:
        out(f"Xato: stansiya emas (kind ≠ ges/cascade): {', '.join(not_station)}")
        return 1
    version = _put("askue.stations", value)
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="askue.stations",
                      details={"via": "cli", "version": version, "stations": len(value)}))
    _show(value, out)
    out(f"askue.stations: versiya {version}, {len(value)} ta stansiya")
    return 0
```

- [ ] **Step 5: Manbalar reyestri, worker, CLI**

`backend/app/etl/connectors.py` — importlarga:
```python
from app.etl.askue.connector import AskueConnector
from app.etl.askue.export import DirectoryExport
from app.etl.askue.registry import AskueStation
```
`KNOWN_SOURCES` kortejining oxiriga `"askue"` qo'shing (S2'dan keyin):
```python
KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank", "askue")
```
`cbu_connector` dan keyin qo'shing:
```python
def _askue(settings: Settings) -> AskueConnector:
    with get_engine("etl").connect() as conn:
        stations = current_setting(conn, "askue.stations")
        days = int(current_setting(conn, "askue.inbox_days"))
    if not stations:
        raise ConfigError("askue.stations bo'sh: `python -m app.cli askue-stations --file …` "
                          "bilan sozlang")
    return AskueConnector(DirectoryExport(Path(settings.askue_inbox_dir), max_age_days=days),
                          [AskueStation.model_validate(s) for s in stations])
```
`make_connector` ichida `if source == "banks":` dan oldin:
```python
    if source == "askue":
        return _askue(settings)
```

`backend/app/worker.py` — importlarga `from app.etl.notify import Kind` qo'shing (mavjud `Notification`, `Notifier` importi yoniga). S2'ning `notify_bank_errors` funksiyasini to'liq almashtiring:
```python
def notify_rejected_rows(run_id: int, notifier: Notifier, *, target: str, kind: Kind,
                         subject: str, hint: str) -> int:
    """Manba fayllaridagi rad etilgan qator/fayllar haqida bitta xabar (S2 3.2, S3 3.1)."""
    with etl_transaction() as conn:
        rows = conn.execute(text(
            "SELECT code, count(*) AS n FROM core.etl_error WHERE run_id = :r "
            "AND step = 'extract' AND target = :t GROUP BY code ORDER BY code"),
            {"r": run_id, "t": target}).all()
    total = sum(int(r.n) for r in rows)
    if total:
        parts = ", ".join(f"{r.code}: {r.n}" for r in rows)
        notifier.notify(Notification(kind, subject,
                                     f"Запуск №{run_id}: отклонено {total} ({parts}). {hint}"))
    return total


def notify_bank_errors(run_id: int, notifier: Notifier) -> int:
    return notify_rejected_rows(
        run_id, notifier, target="bank_file", kind="bank_rows_rejected",
        subject="Строки банковских выписок отклонены",
        hint="Подробности — «Состояние обменов» или `python -m app.cli bank-files`.")


def notify_askue_errors(run_id: int, notifier: Notifier) -> int:
    return notify_rejected_rows(
        run_id, notifier, target="askue_file", kind="askue_rows_rejected",
        subject="Строки выгрузки АСКУЭ отклонены",
        hint="Подробности — «Состояние обменов» и docs/integration/askue-format.md.")


def run_askue_job(notifier: Notifier) -> RunResult | None:
    result = run_etl_job("askue", Mode.INCREMENTAL, notifier)
    if result is not None and result.run_id is not None:
        notify_askue_errors(result.run_id, notifier)
    return result
```
`build_scheduler` ichida (`etl_cbu` blokidan keyin) qo'shing:
```python
    if Path(settings.askue_inbox_dir).is_dir():
        with get_engine("app").connect() as conn:
            askue_cron = str(current_setting(conn, "etl.askue_cron"))
        # TZ 8: АСКУЭ — ежесуточно; inbox'dagi oxirgi askue.inbox_days kun fayllari qayta o'qiladi.
        scheduler.add_job(run_askue_job, CronTrigger.from_crontab(askue_cron, timezone=TASHKENT),
                          args=(notifier,), id="etl_askue", **opts)
```

`backend/app/cli.py` — importlarga:
```python
from app.etl.askue.admin import askue_stations_command
```
`main` ichida (oxirgi `sub.add_parser(...)` blokidan keyin):
```python
    p = sub.add_parser("askue-stations")
    p.add_argument("--file", type=Path, default=None)
```
dispatch'da (oxirgi zaxira `return …` dan oldin):
```python
    if args.command == "askue-stations":
        return askue_stations_command(args.file, _out)
```
Modul docstring'idagi buyruqlar ro'yxatiga:
```
askue-stations — АСКУЭ stansiyalari ↔ filiallar (JSON fayldan; faylsiz — ko'rsatish)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_askue_connector.py tests/test_worker.py tests/test_bank_ops.py -v`
Expected: barcha testlar passed (S2 `test_notify_bank_errors` o'zgarishsiz o'tadi).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(askue): AskueConnector, stansiyalar moslashtirishi CLI, worker jadvali va rad etilgan qatorlar xabari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 12: Jonli quvvat (treplex.uz) — `GesLiveClient` + `poll_power`, snapshot jadvali (0015) va «Текущая мощность» API

**Files:**
- Create: `backend/migrations/versions/0015_power_snapshot.py`, `backend/app/etl/askue/live.py`, `backend/app/sections/queries/power.py`, `backend/tests/fixtures/askue/live_ok.json`
- Modify: `backend/app/sections/production_schemas.py` (`PowerStationOut`, `PowerOut`), `backend/app/sections/proizvodstvo.py` (`get_now`, `/moshchnost`), `backend/app/worker.py` (`askue_live` jobi), `backend/app/cli.py` (`askue-live-check`), `backend/tests/test_route_guards.py`
- Test: `backend/tests/test_askue_live.py`

**Interfaces:**
- Consumes: `Settings.askue_live_url/egress_proxy`, `ConfigError`, `ConnectorUnavailableError`, `AskueStation`, `normalize_name`, `current_setting`, `etl_transaction`, `get_engine`, `get_logger`, `SQ`, `Cache`, `BranchSel.rows`, `pub.branches`, `tests.s2_helpers.put_setting`.
- Produces:
  - `dwh.fact_power_snapshot (snap_at, station, station_name, cascade_name, branch_id, power_mw, units_working, units_reserve, units_repair, source_date, loaded_at)`, PK `(station, snap_at)`, RLS; `pub.power_latest` (`security_invoker`, foydalanuvchiga ko'rinadigan eng oxirgi `snap_at` qatorlari).
  - `app.etl.askue.live`: `TIMEOUT`, `MAX_BYTES = 1 MiB`, `LiveError(ValueError)`, `LiveStation(ges, power, agg)`, `LiveCascade(name, stations)`, `LiveResponse(date, cascades)`, `GesLiveClient(url, *, proxy="", transport=None, timeout=TIMEOUT, max_bytes=MAX_BYTES)` + `.fetch() -> LiveResponse`, `.http`, `.close()`; `Snapshot(station, station_name, cascade_name, branch_code, power_mw, units_working, units_reserve, units_repair)`, `map_snapshot(resp, stations) -> tuple[list[Snapshot], list[str]]`, `store(conn, snap_at, source_date, snaps) -> int`, `prune(conn, now, keep_days) -> int`, `PollResult(snap_at, stored, unmapped, pruned)`, `poll_power(settings, *, client=None, now=None) -> PollResult`, `poll_power_job(settings) -> None` (xatolarni log qiladi, ko'tarmaydi), `askue_live_check_command(settings, out, *, client=None) -> int` (0 / 1 — manba xatosi / 2 — sozlanmagan).
  - `app.sections.queries.power`: `PowerStation(...)`, `PowerReport(snap_at, source_date, stale, stations)` + `.has_source`, `.total_mw`, `.units_working`, `.units_reserve`, `.units_repair`; `latest_at(db) -> datetime | None`, `load(db, sel, *, now, stale_minutes) -> PowerReport`.
  - `production_schemas`: `PowerStationOut(branch_id, branch_name, station, station_name, cascade_name, power_mw, units_working, units_reserve, units_repair)`, `PowerOut(has_source, snap_at, source_date, stale, total_mw, units_working, units_reserve, units_repair, stations)`, `power_out(report)`.
  - `app.sections.proizvodstvo`: `get_now() -> datetime` (testlarda almashtiriladi), `GET /proizvodstvo/moshchnost` — kesh kalitiga oxirgi `snap_at` va `stale` kiradi.
  - Worker job `askue_live` (`askue.live_cron`) — faqat `ASKUE_LIVE_URL` berilgan bo'lsa; CLI `python -m app.cli askue-live-check`.

- [ ] **Step 1: Yozib olingan javob (eski dashboard `sections567.jsx` shakli)**

`backend/tests/fixtures/askue/live_ok.json`:
```json
{
  "date": "25.09.2026 10:40",
  "cascades": [
    {
      "name": "Chirchiq-Bo'zsuv GESlar kaskadi",
      "all-power": "412.5",
      "all-agg": "5/3/1",
      "stations": [
        {"ges": "Chorvoq GES", "power": "380.5", "agg": "3/1/0"},
        {"ges": "Chirchiq GES-7", "power": 32, "agg": "2/0/1"},
        {"ges": "Yangi GES", "power": "0", "agg": "0/2/0"}
      ]
    }
  ]
}
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_askue_live.py`:
```python
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import worker
from app.core.config import ConfigError, get_settings
from app.etl.askue import live
from app.etl.askue.live import GesLiveClient, LiveError, map_snapshot, poll_power
from app.etl.askue.registry import AskueStation
from app.etl.db import etl_transaction
from app.etl.types import ConnectorUnavailableError
from app.main import create_app
from app.sections.deps import get_today
from app.sections.proizvodstvo import get_now
from tests.etl_helpers import TEST_AS_OF, RecordingNotifier
from tests.helpers import SeedUser, login
from tests.s2_helpers import put_setting

FIXTURE = (Path(__file__).parent / "fixtures" / "askue" / "live_ok.json").read_bytes()
URL = "https://treplex.test/api/cascades/ges"
T1 = datetime(2026, 9, 25, 5, 40, tzinfo=UTC)
STATIONS = [AskueStation(code="CHARVAK-1", name="Chorvoq  GES", branch_code="UGE-02"),
            AskueStation(code="CHIRCHIQ-7", name="chirchiq ges-7", branch_code="UGE-03")]


def fake(response: httpx.Response | Callable[[httpx.Request], httpx.Response]) -> GesLiveClient:
    handler = response if callable(response) else (lambda _r: response)
    return GesLiveClient(URL, transport=httpx.MockTransport(handler))


def ok_client() -> GesLiveClient:
    return fake(httpx.Response(200, content=FIXTURE))


def test_parse_fixture() -> None:
    client = ok_client()
    resp = client.fetch()
    assert client.http.trust_env is False and client.http.follow_redirects is False
    assert resp.date == "25.09.2026 10:40" and len(resp.cascades) == 1
    st = resp.cascades[0].stations
    assert [(s.ges, s.power, s.agg) for s in st] == [
        ("Chorvoq GES", Decimal("380.5"), (3, 1, 0)), ("Chirchiq GES-7", Decimal("32"), (2, 0, 1)),
        ("Yangi GES", Decimal("0"), (0, 2, 0))]


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>Ошибка</html>"),
    httpx.Response(200, json={"cascades": "x"}),
    httpx.Response(200, json={"cascades": [{"name": "K", "stations": [
        {"ges": "A", "power": "-5"}]}]}),
    httpx.Response(200, json={"cascades": [{"name": "K", "stations": [
        {"ges": "A", "power": "1", "agg": "a/b"}]}]}),
    httpx.Response(302, headers={"location": "https://evil.test/"}),
    httpx.Response(404),
])
def test_bad_responses_are_not_retryable(response: httpx.Response) -> None:
    with pytest.raises(LiveError) as exc:
        fake(response).fetch()
    assert not isinstance(exc.value, ConnectorUnavailableError)


def test_transient_errors_are_retryable_and_size_capped() -> None:
    with pytest.raises(ConnectorUnavailableError, match="503"):
        fake(httpx.Response(503)).fetch()

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ConnectorUnavailableError, match="тайм-аут"):
        fake(timeout).fetch()
    big = GesLiveClient(URL, max_bytes=100,
                        transport=httpx.MockTransport(lambda _r: httpx.Response(200,
                                                                               content=FIXTURE)))
    with pytest.raises(LiveError, match="больше"):
        big.fetch()
    with pytest.raises(ConfigError):
        GesLiveClient("http://treplex.test/api/cascades/ges")


def test_map_snapshot_normalizes_names() -> None:
    snaps, unmapped = map_snapshot(ok_client().fetch(), STATIONS)
    assert [(s.station, s.branch_code, s.power_mw, s.units_working, s.units_repair)
            for s in snaps] == [("CHARVAK-1", "UGE-02", Decimal("380.5"), 3, 0),
                                ("CHIRCHIQ-7", "UGE-03", Decimal("32"), 2, 1)]
    assert unmapped == ["Yangi GES"]
    assert snaps[0].cascade_name == "Chirchiq-Bo'zsuv GESlar kaskadi"


def _clear() -> None:
    with etl_transaction() as conn:
        conn.execute(text("DELETE FROM dwh.fact_power_snapshot WHERE station = ANY(:s)"),
                     {"s": [s.code for s in STATIONS]})


@pytest.fixture
def stations() -> Iterator[None]:
    _clear()
    put_setting("askue.stations", [s.model_dump() for s in STATIONS])
    yield
    put_setting("askue.stations", [])
    _clear()


def _count() -> int:
    with etl_transaction() as conn:
        return int(conn.execute(text("SELECT count(*) FROM dwh.fact_power_snapshot "
                                     "WHERE station = ANY(:s)"),
                                {"s": [s.code for s in STATIONS]}).scalar_one())


def test_poll_stores_and_prunes(stations: None) -> None:
    settings = get_settings().model_copy(update={"askue_live_url": URL})
    first = poll_power(settings, client=ok_client(), now=T1 - timedelta(days=40))
    assert (first.stored, first.unmapped) == (2, ["Yangi GES"])
    result = poll_power(settings, client=ok_client(), now=T1 + timedelta(seconds=37))
    assert result.snap_at == T1 and result.stored == 2 and result.pruned == 2
    with etl_transaction() as conn:
        rows = conn.execute(text("SELECT station, snap_at, power_mw, source_date "
                                 "FROM dwh.fact_power_snapshot WHERE station = ANY(:s) "
                                 "ORDER BY station"), {"s": [s.code for s in STATIONS]}).all()
    assert [(r.station, r.snap_at, r.power_mw) for r in rows] == [
        ("CHARVAK-1", T1, Decimal("380.5000")), ("CHIRCHIQ-7", T1, Decimal("32.0000"))]
    assert rows[0].source_date == "25.09.2026 10:40"


def test_poll_failure_keeps_last_snapshot(stations: None,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"askue_live_url": URL})
    poll_power(settings, client=ok_client(), now=T1)
    with pytest.raises(ConnectorUnavailableError):
        poll_power(settings, client=fake(httpx.Response(503)), now=T1 + timedelta(minutes=10))
    monkeypatch.setattr(live, "GesLiveClient", lambda *a, **k: fake(httpx.Response(502)))
    live.poll_power_job(settings)  # xatoni log qiladi, ko'tarmaydi
    assert _count() == 2


@pytest.fixture
def app_factory() -> Iterator[Callable[[datetime], TestClient]]:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)
    clients: list[TestClient] = []

    def make(now: datetime) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_today] = lambda: TEST_AS_OF
        app.dependency_overrides[get_now] = lambda: now
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def test_moshchnost_stale_and_empty(stations: None, app_factory: Callable[[datetime], TestClient],
                                    make_user: Callable[..., SeedUser]) -> None:
    boss = make_user("rukovodstvo")
    empty = login(app_factory(T1), boss).get("/api/v1/proizvodstvo/moshchnost")
    assert empty.status_code == 200, empty.text
    assert empty.json()["has_source"] is False and empty.json()["stations"] == []
    poll_power(get_settings().model_copy(update={"askue_live_url": URL}), client=ok_client(),
               now=T1)
    fresh = login(app_factory(T1 + timedelta(minutes=5)), boss).get(
        "/api/v1/proizvodstvo/moshchnost").json()
    assert (fresh["has_source"], fresh["stale"], fresh["total_mw"]) == (True, False, 412.5)
    assert (fresh["units_working"], fresh["units_reserve"], fresh["units_repair"]) == (5, 1, 1)
    assert fresh["snap_at"].startswith("2026-09-25T05:40") and fresh["source_date"]
    assert [s["station"] for s in fresh["stations"]] == ["CHARVAK-1", "CHIRCHIQ-7"]
    old = login(app_factory(T1 + timedelta(hours=2)), boss).get(
        "/api/v1/proizvodstvo/moshchnost").json()
    assert old["stale"] is True and old["total_mw"] == 412.5
    econ = login(app_factory(T1), make_user("economist_filiala", branch_ids=(3,)))
    own = econ.get("/api/v1/proizvodstvo/moshchnost").json()
    assert [s["station"] for s in own["stations"]] == ["CHIRCHIQ-7"] and own["total_mw"] == 32.0
    assert econ.get("/api/v1/proizvodstvo/moshchnost", params={"br": 2}).status_code == 403
    kazna = login(app_factory(T1), make_user("spec_kazna"))
    assert kazna.get("/api/v1/proizvodstvo/moshchnost").status_code == 403


def test_live_check_cli(stations: None) -> None:
    out: list[str] = []
    settings = get_settings().model_copy(update={"askue_live_url": ""})
    assert live.askue_live_check_command(settings, out.append) == 2
    assert live.askue_live_check_command(settings, out.append, client=ok_client()) == 0
    assert any("CHARVAK-1" in line for line in out) and any("Yangi GES" in line for line in out)
    assert live.askue_live_check_command(settings, out.append,
                                         client=fake(httpx.Response(503))) == 1


def test_scheduler_adds_live_job_only_with_url() -> None:
    on = get_settings().model_copy(update={"askue_live_url": URL})
    jobs = {j.id: j for j in worker.build_scheduler(on, RecordingNotifier()).get_jobs()}
    assert jobs["askue_live"].func is live.poll_power_job
    off = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "askue_live" not in off

```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga qo'shing:
```python
    ("GET", "/api/v1/proizvodstvo/moshchnost"),
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_askue_live.py -v`
Expected: FAIL — `ImportError: cannot import name 'live' from 'app.etl.askue'`.

- [ ] **Step 4: 0015 migratsiyasi**

`backend/migrations/versions/0015_power_snapshot.py`:
```python
"""S3: jonli quvvat snapshot'lari (treplex.uz) va pub.power_latest

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-25

Runner/build'dan tashqarida (spec 3.2, qaror 4): har 10 daqiqada worker yozadi, UI eng oxirgi
snapshot'ni o'qiydi. RLS — filial bo'yicha, view security_invoker.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE dwh.fact_power_snapshot (
      snap_at timestamptz NOT NULL,
      station varchar(40) NOT NULL,
      station_name varchar(200) NOT NULL,
      cascade_name varchar(200) NOT NULL,
      branch_id integer NOT NULL REFERENCES dwh.dim_branch (branch_id),
      power_mw numeric(10,4) NOT NULL CHECK (power_mw >= 0),
      units_working smallint NOT NULL DEFAULT 0 CHECK (units_working >= 0),
      units_reserve smallint NOT NULL DEFAULT 0 CHECK (units_reserve >= 0),
      units_repair smallint NOT NULL DEFAULT 0 CHECK (units_repair >= 0),
      source_date varchar(40),
      loaded_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (station, snap_at)
    )
    """,
    "CREATE INDEX fact_power_snapshot_snap_idx ON dwh.fact_power_snapshot (snap_at DESC)",
    "CREATE INDEX fact_power_snapshot_branch_idx ON dwh.fact_power_snapshot "
    "(branch_id, snap_at DESC)",
    "ALTER TABLE dwh.fact_power_snapshot ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE dwh.fact_power_snapshot FORCE ROW LEVEL SECURITY",
    "CREATE POLICY branch_scope ON dwh.fact_power_snapshot USING (core.rls_branch_ok(branch_id)) "
    "WITH CHECK (core.rls_branch_ok(branch_id))",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON dwh.fact_power_snapshot TO ugk_etl",
    "GRANT SELECT ON dwh.fact_power_snapshot TO ugk_app",
    """
    CREATE VIEW pub.power_latest WITH (security_invoker = true) AS
    SELECT p.snap_at, p.station, p.station_name, p.cascade_name, p.branch_id, p.power_mw,
           p.units_working, p.units_reserve, p.units_repair, p.source_date
    FROM dwh.fact_power_snapshot p
    WHERE p.snap_at = (SELECT max(x.snap_at) FROM dwh.fact_power_snapshot x)
    """,
    "GRANT SELECT ON pub.power_latest TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW pub.power_latest")
    op.execute("DROP TABLE dwh.fact_power_snapshot")
```

- [ ] **Step 5: Implementatsiya — mijoz, moslashtirish, yozish**

`backend/app/etl/askue/live.py`:
```python
"""Jonli quvvat (treplex.uz, eski dashboard: GET /api/cascades/ges, auth yo'q) — «Текущая мощность»
(S3 spec 3.2). Javob:
{date, cascades:[{name, "all-power", "all-agg", stations:[{ges, power, agg}]}]};
power — MVt (son yoki satr), agg — "ishda/zaxira/ta'mir". Bu kunlik energiya EMAS.

Runner/build'siz (qaror 4): har so'rovning moslashtirilgan stansiyalari bitta snap_at (UTC,
daqiqagacha) bilan dwh.fact_power_snapshot ga; manba ishlamasa oxirgi snapshot saqlanadi.
Tarmoq: faqat worker, https, trust_env=False, redirect yo'q, ≤ 1 MiB, ixtiyoriy EGRESS_PROXY.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import ConfigError, Settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.dwh.reference import current_setting
from app.etl.askue.registry import AskueStation, normalize_name
from app.etl.db import etl_transaction
from app.etl.types import ConnectorUnavailableError

TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
MAX_BYTES = 1024 * 1024
_POWER = re.compile(r"^\d{1,5}(\.\d{1,4})?$")
_AGG = re.compile(r"^\d{1,3}/\d{1,3}/\d{1,3}$")
WHERE = "АСКУЭ (онлайн)"
log = get_logger("ugekazna.askue.live")


class LiveError(ValueError):
    """Qayta urinilmaydigan jonli manba xatosi (format, 4xx, redirect, hajm)."""


def _power(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("power: son kerak")
    if isinstance(value, int | float | Decimal):
        raw = str(value)
    elif isinstance(value, str):
        raw = value.strip().replace(",", ".")
    else:
        raise ValueError("power: son kerak")
    if not _POWER.fullmatch(raw):
        raise ValueError("power: 0…99999 MVt")
    return Decimal(raw)


def _agg(value: Any) -> tuple[int, int, int]:
    if value is None or value == "":
        return (0, 0, 0)
    if not isinstance(value, str) or not _AGG.fullmatch(value.strip()):
        raise ValueError("agg: «ishda/zaxira/ta'mir» kerak")
    working, reserve, repair = (int(x) for x in value.strip().split("/"))
    return (working, reserve, repair)


class LiveStation(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    ges: Annotated[str, Field(min_length=1, max_length=200)]
    power: Annotated[Decimal, BeforeValidator(_power)]
    agg: Annotated[tuple[int, int, int], BeforeValidator(_agg)] = (0, 0, 0)


class LiveCascade(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    stations: list[LiveStation]


class LiveResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    date: Annotated[str | None, Field(max_length=40)] = None
    cascades: list[LiveCascade]


class GesLiveClient:
    def __init__(self, url: str, *, proxy: str = "",
                 transport: httpx.BaseTransport | None = None, timeout: httpx.Timeout = TIMEOUT,
                 max_bytes: int = MAX_BYTES) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigError("ASKUE_LIVE_URL https:// manzil bo'lishi kerak")
        self.url = url
        self.max_bytes = max_bytes
        self.http = httpx.Client(timeout=timeout, verify=True, trust_env=False,
                                 follow_redirects=False, proxy=proxy or None, transport=transport,
                                 headers={"Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def fetch(self) -> LiveResponse:
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream("GET", self.url) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise LiveError(f"{WHERE}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{WHERE}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{WHERE}: {type(exc).__name__}") from exc
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{WHERE}: HTTP {status}")
        if status != 200:
            raise LiveError(f"{WHERE}: HTTP {status}")
        try:
            data = json.loads(b"".join(chunks).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LiveError(f"{WHERE}: ответ не JSON") from exc
        try:
            return LiveResponse.model_validate(data)
        except PydanticValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise LiveError(f"{WHERE}: неожиданная структура ответа ({loc} — {first['msg']})") \
                from exc


@dataclass(frozen=True, slots=True)
class Snapshot:
    station: str  # AskueStation.code
    station_name: str
    cascade_name: str
    branch_code: str
    power_mw: Decimal
    units_working: int
    units_reserve: int
    units_repair: int


def map_snapshot(resp: LiveResponse,
                 stations: list[AskueStation]) -> tuple[list[Snapshot], list[str]]:
    by_name = {normalize_name(s.name): s for s in stations}
    out: list[Snapshot] = []
    unmapped: list[str] = []
    seen: set[str] = set()
    for cascade in resp.cascades:
        for item in cascade.stations:
            key = normalize_name(item.ges)
            station = by_name.get(key)
            if station is None:
                unmapped.append(item.ges.strip()[:200])
                continue
            if key in seen:
                continue
            seen.add(key)
            working, reserve, repair = item.agg
            out.append(Snapshot(station.code, item.ges.strip()[:200], cascade.name.strip()[:200],
                                station.branch_code, item.power, working, reserve, repair))
    return out, unmapped


def store(conn: Connection, snap_at: datetime, source_date: str | None,
          snaps: list[Snapshot]) -> int:
    ids = dict(conn.execute(text("SELECT code, branch_id FROM dwh.dim_branch WHERE code = ANY(:c)"),
                            {"c": [s.branch_code for s in snaps] or [""]}).all())
    stored = 0
    for s in snaps:
        branch_id = ids.get(s.branch_code)
        if branch_id is None:
            log.warning("askue_live_unknown_branch", branch=s.branch_code, station=s.station)
            continue
        conn.execute(text(
            "INSERT INTO dwh.fact_power_snapshot (snap_at, station, station_name, cascade_name, "
            "branch_id, power_mw, units_working, units_reserve, units_repair, source_date) "
            "VALUES (:t, :st, :sn, :cn, :b, :p, :w, :r, :x, :d) "
            "ON CONFLICT (station, snap_at) DO UPDATE SET power_mw = EXCLUDED.power_mw, "
            "units_working = EXCLUDED.units_working, units_reserve = EXCLUDED.units_reserve, "
            "units_repair = EXCLUDED.units_repair, source_date = EXCLUDED.source_date, "
            "loaded_at = now()"),
            {"t": snap_at, "st": s.station, "sn": s.station_name, "cn": s.cascade_name,
             "b": branch_id, "p": s.power_mw, "w": s.units_working, "r": s.units_reserve,
             "x": s.units_repair, "d": source_date})
        stored += 1
    return stored


def prune(conn: Connection, now: datetime, keep_days: int) -> int:
    return conn.execute(text("DELETE FROM dwh.fact_power_snapshot WHERE snap_at < :cut"),
                        {"cut": now - timedelta(days=keep_days)}).rowcount


@dataclass(frozen=True, slots=True)
class PollResult:
    snap_at: datetime
    stored: int
    unmapped: list[str]
    pruned: int


def poll_power(settings: Settings, *, client: GesLiveClient | None = None,
               now: datetime | None = None) -> PollResult:
    moment = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    with etl_transaction() as conn:
        stations = [AskueStation.model_validate(s)
                    for s in current_setting(conn, "askue.stations")]
        keep = int(current_setting(conn, "askue.live_keep_days"))
    own = client is None
    live_client = client or GesLiveClient(settings.askue_live_url, proxy=settings.egress_proxy)
    try:
        resp = live_client.fetch()
    finally:
        if own:
            live_client.close()
    snaps, unmapped = map_snapshot(resp, stations)
    if unmapped:
        log.warning("askue_live_unmapped", count=len(unmapped), names=unmapped[:10])
    with etl_transaction() as conn:
        stored = store(conn, moment, resp.date, snaps)
        pruned = prune(conn, moment, keep)
    return PollResult(moment, stored, unmapped, pruned)


def poll_power_job(settings: Settings) -> None:
    """Worker jobi: xato ko'tarilmaydi (keyingi so'rov 10 daqiqadan keyin), snapshot qoladi."""
    try:
        result = poll_power(settings)
    except ConnectorUnavailableError as exc:
        log.warning("askue_live_unavailable", error=str(exc))
        return
    except (LiveError, ConfigError) as exc:
        log.error("askue_live_failed", error=str(exc))
        return
    log.info("askue_live_polled", stored=result.stored, unmapped=len(result.unmapped),
             pruned=result.pruned)


def askue_live_check_command(settings: Settings, out: Callable[[str], None], *,
                             client: GesLiveClient | None = None) -> int:
    """Operator tekshiruvi: manba javobi va askue.stations bilan moslashtirish (yozuvsiz)."""
    if client is None and not settings.askue_live_url:
        out("ASKUE_LIVE_URL berilmagan — jonli quvvat o'chiq")
        return 2
    try:
        live_client = client or GesLiveClient(settings.askue_live_url,
                                              proxy=settings.egress_proxy)
    except ConfigError as exc:
        out(f"Konfiguratsiya xatosi: {exc}")
        return 2
    try:
        resp = live_client.fetch()
    except (ConnectorUnavailableError, LiveError) as exc:
        out(f"XATO: {exc}")
        return 1
    finally:
        if client is None:
            live_client.close()
    with get_engine("app").connect() as conn:
        stations = [AskueStation.model_validate(s)
                    for s in current_setting(conn, "askue.stations")]
    snaps, unmapped = map_snapshot(resp, stations)
    for s in snaps:
        out(f"OK   {s.station:<20} {s.branch_code:<10} {s.power_mw} МВт  {s.station_name}")
    for name in unmapped:
        out(f"---  {name} (askue.stations'da yo'q)")
    out(f"Stansiyalar: {len(snaps)} moslashtirilgan, {len(unmapped)} moslashtirilmagan; "
        f"manba sanasi: {resp.date or '—'}")
    return 0
```

- [ ] **Step 6: Implementatsiya — so'rov, sxema, endpoint**

`backend/app/sections/queries/power.py`:
```python
"""«Текущая мощность» — pub.power_latest (foydalanuvchi ko'ra oladigan eng oxirgi snapshot).

Eskirganlik: hozir − snap_at > askue.live_stale_minutes. Snapshot yo'q — manba ulanmagan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sections.queries.cash import num
from app.sections.scope import BranchSel


@dataclass(frozen=True, slots=True)
class PowerStation:
    branch_id: int
    branch_name: str
    station: str
    station_name: str
    cascade_name: str
    power_mw: float
    units_working: int
    units_reserve: int
    units_repair: int


@dataclass(frozen=True, slots=True)
class PowerReport:
    snap_at: datetime | None
    source_date: str | None
    stale: bool
    stations: list[PowerStation]

    @property
    def has_source(self) -> bool:
        return self.snap_at is not None

    @property
    def total_mw(self) -> float:
        return round(sum(s.power_mw for s in self.stations), 4)

    @property
    def units_working(self) -> int:
        return sum(s.units_working for s in self.stations)

    @property
    def units_reserve(self) -> int:
        return sum(s.units_reserve for s in self.stations)

    @property
    def units_repair(self) -> int:
        return sum(s.units_repair for s in self.stations)


def latest_at(db: Session) -> datetime | None:
    value = db.execute(text("SELECT max(snap_at) FROM pub.power_latest")).scalar_one()
    return value if isinstance(value, datetime) else None


def load(db: Session, sel: BranchSel, *, now: datetime, stale_minutes: int) -> PowerReport:
    latest = latest_at(db)
    if latest is None:
        return PowerReport(None, None, False, [])
    where, params = sel.rows("p.branch_id")
    rows = db.execute(text(
        "SELECT p.branch_id, b.name AS branch_name, p.station, p.station_name, p.cascade_name, "
        "p.power_mw, p.units_working, p.units_reserve, p.units_repair, p.source_date "
        "FROM pub.power_latest p JOIN pub.branches b ON b.branch_id = p.branch_id "
        f"WHERE {where} ORDER BY p.power_mw DESC, p.station"), params).all()
    return PowerReport(
        snap_at=latest, source_date=rows[0].source_date if rows else None,
        stale=now - latest > timedelta(minutes=stale_minutes),
        stations=[PowerStation(int(r.branch_id), r.branch_name, r.station, r.station_name,
                               r.cascade_name, num(r.power_mw), int(r.units_working),
                               int(r.units_reserve), int(r.units_repair)) for r in rows])
```

`backend/app/sections/production_schemas.py` — `from datetime import datetime` importini qo'shing, `from app.sections.queries.power import PowerReport` importini qo'shing va fayl oxiriga:
```python
class PowerStationOut(_Out):
    branch_id: int
    branch_name: str
    station: str
    station_name: str
    cascade_name: str
    power_mw: float
    units_working: int
    units_reserve: int
    units_repair: int


class PowerOut(_Out):
    has_source: bool
    snap_at: datetime | None
    source_date: str | None
    stale: bool
    total_mw: float
    units_working: int
    units_reserve: int
    units_repair: int
    stations: list[PowerStationOut]


def power_out(r: PowerReport) -> PowerOut:
    return PowerOut(
        has_source=r.has_source, snap_at=r.snap_at, source_date=r.source_date, stale=r.stale,
        total_mw=r.total_mw, units_working=r.units_working, units_reserve=r.units_reserve,
        units_repair=r.units_repair,
        stations=[PowerStationOut(branch_id=s.branch_id, branch_name=s.branch_name,
                                  station=s.station, station_name=s.station_name,
                                  cascade_name=s.cascade_name, power_mw=s.power_mw,
                                  units_working=s.units_working, units_reserve=s.units_reserve,
                                  units_repair=s.units_repair) for s in r.stations])
```

`backend/app/sections/proizvodstvo.py` — importlarga qo'shing:
```python
from datetime import UTC, datetime, timedelta

from app.dwh.reference import current_setting
from app.sections.production_schemas import PowerOut, power_out
from app.sections.queries import power
```
`DB = …` qatoridan keyin qo'shing:
```python
def get_now() -> datetime:
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(get_now)]
```
fayl oxiriga qo'shing:
```python
@router.get("/moshchnost", response_model=PowerOut)
def moshchnost(cache: Cache, db: DB, q: SQ, now: Now) -> Response:
    """Jonli quvvat (treplex.uz): build'ga bog'liq emas — kesh kalitiga oxirgi snapshot vaqti va
    eskirganlik kiradi (yangi snapshot yoki eskirish — yangi javob)."""
    stale_minutes = int(current_setting(db.connection(), "askue.live_stale_minutes"))
    latest = power.latest_at(db)
    stale = latest is not None and now - latest > timedelta(minutes=stale_minutes)
    filters = {**q.cache_filters, "snap": latest.isoformat() if latest else None, "stale": stale}
    return cache.respond("proizvodstvo.moshchnost", filters, lambda: power_out(
        power.load(db, q.sel(), now=now, stale_minutes=stale_minutes)))
```

- [ ] **Step 7: Worker va CLI**

`backend/app/worker.py` — importlarga `from app.etl.askue.live import poll_power_job` qo'shing; `build_scheduler` ichida (`etl_askue` blokidan keyin):
```python
    if settings.askue_live_url:
        with get_engine("app").connect() as conn:
            live_cron = str(current_setting(conn, "askue.live_cron"))
        # Jonli quvvat — Runner'siz (ETL lock'ini band qilmaydi), xato ko'tarmaydi.
        scheduler.add_job(poll_power_job, CronTrigger.from_crontab(live_cron, timezone=TASHKENT),
                          args=(settings,), id="askue_live", **opts)
```

`backend/app/cli.py` — importlarga `from app.etl.askue.live import askue_live_check_command`; `main` ichida:
```python
    sub.add_parser("askue-live-check")
```
dispatch'da:
```python
    if args.command == "askue-live-check":
        return askue_live_check_command(get_settings(), _out)
```
Docstring ro'yxatiga:
```
askue-live-check — jonli quvvat manbasi javobi va stansiyalar moslashtirishi (yozuvsiz)
```

- [ ] **Step 8: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_askue_live.py tests/test_worker.py tests/test_route_guards.py tests/test_proizvodstvo_api.py -v`
Expected: barcha testlar passed (tarmoqqa chiqish yo'q — faqat `MockTransport`).

- [ ] **Step 9: Commit**

```bash
git add backend
git commit -m "feat(askue): jonli quvvat snapshot'lari (treplex.uz), «Текущая мощность» API, worker jobi va tekshiruv CLI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 13: 1C ombori — `OneCSkladConnector` (`hs/sklad/materials`), Runner oynasi cheklovi, reyestr, worker va CLI

**Files:**
- Create: `backend/app/etl/onec/sklad_models.py`, `backend/app/etl/onec/sklad.py`, `backend/tests/fixtures/onec_sklad/materials_current.json`, `backend/tests/fixtures/onec_sklad/materials_extended.json`
- Modify: `backend/app/etl/runner.py` (`_run_locked` — `connector.lookback_months`), `backend/app/etl/connectors.py`, `backend/app/worker.py`, `backend/app/cli.py` (`onec-sklad-check`)
- Test: `backend/tests/test_onec_sklad.py`

**Interfaces:**
- Consumes: `OneCClient`, `OneCError`, `OneCFormatError`, `verify_setting`, `onec.models.parse`, `OrgMap`, `stable_code`, `to_mln`, `ExtractStats`, `HealthResult`, `Watermark`, `StagingSink`, `Window`, `date_id`, `month_id`, `month_start`, `month_end`, `add_months`, `today_tashkent`, `Runner`, `compute_window`, `Mode`, `current_setting` (`onec.orgs`, `onec.sklad_months`, `etl.onec_sklad_*_cron`), `Settings.onec_sklad_*`, `onec_ca_file`, `onec_allow_http`, `onec_max_bytes`, `run_etl_job`.
- Produces:
  - `app.etl.onec.sklad_models`: `MaterialRow` (camelCase va snake_case: `account_code`, `account_name`, `is_total`, `opening`, `closing` — majburiy/asosiy; ixtiyoriy `nomenclature_code`, `nomenclature_name`, `unit`, `warehouse_name`, `closing_qty`, `min_qty`, `last_move_date`, `debit_sum`, `credit_sum`), `MaterialsResponse(data)`, `parse_materials(data) -> MaterialsResponse` (`{"success": false}` → `OneCError`, tuzilma xatosi → `OneCFormatError`).
  - `app.etl.onec.sklad`: `SOURCE = "onec_sklad"`, `PATH = "/materials"`, `TOTAL_ACCOUNT = "1000"`, `DEFAULT_WAREHOUSE = "Основной склад"`, `periods(window) -> list[tuple[date, date]]` (to'liq oylar: oy boshi … min(oy oxiri, oyna oxiri)), `OneCSkladConnector(client, orgs, *, months=13, source=SOURCE, now=...)` — `SourceConnector` + `lookback_months`; `extract` → `ExtractStats(n, {"fact_stock", "fact_stock_move", "dim_nomenclature"})` (oyna ichida to'liq — almashtirish). `src_id` = `"{org_uid}:{nom_code}:{sha256(ombor)[:10]}:{YYYYMM}"` (+ `:in|:out` harakatlar uchun).
  - `Runner`: `getattr(connector, "lookback_months", None)` berilsa oyna boshi `max(oyna boshi, joriy oy − (N − 1))` ga cheklanadi (almashtirish ham shu oyna ichida).
  - `KNOWN_SOURCES` += `"onec_sklad"`; `make_connector("onec_sklad")` (`ONEC_SKLAD_BASE_URL` yoki sirlar yoki `onec.orgs` bo'sh → `ConfigError`).
  - Worker job'lar `etl_onec_sklad_full` (`etl.onec_sklad_full_cron`, FULL) va `etl_onec_sklad_incremental` (`etl.onec_sklad_incremental_cron`) — faqat `ONEC_SKLAD_BASE_URL` berilgan bo'lsa; CLI `python -m app.cli onec-sklad-check` (0 / 1 / 2).

- [ ] **Step 1: Yozib olingan javoblar**

Joriy shakl — eski dashboard (`1C.1/panels.jsx`, `sections234.jsx`, `budget-api.js`) ishlatgan maydonlar: `data[]` ichida `accountCode`, `accountName`, `isTotal`, `openingSum`, `closingSum` (so'm; `1000` — jami qatori). Kengaytirilgan shakl — `docs/integration/1c-sorov-s3.md` da so'raladigan maydonlar.

`backend/tests/fixtures/onec_sklad/materials_current.json`:
```json
{
  "success": true,
  "data": [
    {"accountCode": "1000", "accountName": "Материалы (итого)", "isTotal": true, "openingSum": 1500000000, "closingSum": 1700000000},
    {"accountCode": 1010, "accountName": "Сырьё и материалы", "isTotal": false, "openingSum": 400000000, "closingSum": 450000000},
    {"accountCode": "1050", "accountName": "Запасные части", "isTotal": false, "openingSum": 1100000000, "closingSum": 1250000000},
    {"accountCode": "1060", "accountName": "Топливо", "isTotal": false, "openingSum": 0, "closingSum": 0}
  ]
}
```

`backend/tests/fixtures/onec_sklad/materials_extended.json`:
```json
{
  "data": [
    {"account_code": "1050", "account_name": "Запасные части", "is_total": false, "opening_sum": 48000000, "closing_sum": 96000000,
     "nomenclature_code": "00-00012345", "nomenclature_name": "Подшипник SKF 23140", "unit": "шт", "warehouse_name": "Центральный склад",
     "closing_qty": 2, "min_qty": 4, "last_move_date": "2026-09-10", "debit_sum": 48000000, "credit_sum": 0},
    {"account_code": "1010", "account_name": "Сырьё и материалы", "is_total": false, "opening_sum": 0, "closing_sum": 12345678,
     "nomenclature_name": "Электроды МР-3", "unit": "кг", "closing_qty": 350.5, "credit_sum": 2000000},
    {"account_code": "1010", "account_name": "Сырьё и материалы", "is_total": false, "opening_sum": 0, "closing_sum": -5000000,
     "nomenclature_name": "Сторно", "unit": "кг"}
  ]
}
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_onec_sklad.py`:
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

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.onec.client import OneCClient, OneCError, OneCFormatError
from app.etl.onec.connector import OrgMap, stable_code
from app.etl.onec.sklad import OneCSkladConnector, periods
from app.etl.onec.sklad_models import parse_materials
from app.etl.runner import Runner
from app.etl.types import Mode, Window
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

FIXTURES = Path(__file__).parent / "fixtures" / "onec_sklad"
BASE = "https://1c.test/con2026/hs/sklad"
ORG = OrgMap(branch_code="UGE-02", org_uid="uid-02", org_name="Чорвоқ ГЭС")


def body(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


def fake_client(payload: bytes | httpx.Response, seen: list[dict[str, Any]] | None = None,
                ) -> OneCClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append({"path": request.url.path, **json.loads(request.content)})
        return payload if isinstance(payload, httpx.Response) else httpx.Response(
            200, content=payload)

    return OneCClient(BASE, "u", "p", transport=httpx.MockTransport(handler))


def test_periods_cover_full_months() -> None:
    assert periods(Window(date(2026, 8, 10), TEST_AS_OF)) == [
        (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), TEST_AS_OF)]


def test_current_shape_loads_account_level_stock() -> None:
    seen: list[dict[str, Any]] = []
    connector = OneCSkladConnector(fake_client(body("materials_current.json"), seen), [ORG])
    sink = CollectSink()
    stats = connector.extract(Window(date(2026, 9, 1), TEST_AS_OF), sink)
    assert seen == [{"path": "/con2026/hs/sklad/materials", "date_from": "2026-09-01",
                     "date_to": "2026-09-24", "org_uid": "uid-02"}]
    stock = [r for t, r in sink.rows if t == "fact_stock"]
    assert [(r["nom_code"], r["value"], r["qty"], r["min_qty"], r["last_move_date_id"],
             r["warehouse"], r["date_id"]) for r in stock] == [
        ("1C-ACC-1010", Decimal("450.00"), Decimal("0.000"), None, None, "Основной склад",
         20260924),
        ("1C-ACC-1050", Decimal("1250.00"), Decimal("0.000"), None, None, "Основной склад",
         20260924)]
    assert all(r["src_id"].startswith("uid-02:1C-ACC-") and r["src_id"].endswith(":202609")
               for r in stock)
    noms = {r["code"]: r for t, r in sink.rows if t == "dim_nomenclature"}
    acc = noms["1C-ACC-1050"]
    assert acc["category"] == "Запасные части" and acc["unit"] == "—"
    assert [t for t, _ in sink.rows].count("fact_stock_move") == 0
    assert set(stats.by_target) == {"fact_stock", "fact_stock_move", "dim_nomenclature"}
    assert stats.by_target["fact_stock"] == 2


def test_extended_shape_loads_nomenclature_minimum_and_moves() -> None:
    sink = CollectSink()
    OneCSkladConnector(fake_client(body("materials_extended.json")), [ORG]).extract(
        Window(date(2026, 9, 1), TEST_AS_OF), sink)
    bearing = stable_code("1C-N-", "00-00012345", "шт")
    electrodes = stable_code("1C-N-", "Электроды МР-3", "кг")
    stock = {r["nom_code"]: r for t, r in sink.rows if t == "fact_stock"}
    assert set(stock) == {bearing, electrodes}  # manfiy (сторно) qoldiq o'tkazildi
    b = stock[bearing]
    assert (b["qty"], b["min_qty"], b["value"], b["last_move_date_id"], b["warehouse"]) == (
        Decimal("2.000"), Decimal("4"), Decimal("96.00"), 20260910, "Центральный склад")
    assert stock[electrodes]["value"] == Decimal("12.35")
    moves = sorted((r["nom_code"], r["direction"], r["value"]) for t, r in sink.rows
                   if t == "fact_stock_move")
    assert moves == sorted([(bearing, "in", Decimal("48.00")),
                            (electrodes, "out", Decimal("2.00"))])
    noms = {r["code"]: r for t, r in sink.rows if t == "dim_nomenclature"}
    assert noms[bearing]["name"] == "Подшипник SKF 23140" and noms[bearing]["unit"] == "шт"


@pytest.mark.parametrize(("payload", "error"), [
    (json.dumps({"success": False, "code": "E42", "error": "нет прав"}).encode(), OneCError),
    (b"\xef\xbb\xbf<html>Ошибка 1С</html>", OneCFormatError),
    (json.dumps({"items": []}).encode(), OneCFormatError),
    (json.dumps({"data": [{"accountName": "x", "closingSum": 1}]}).encode(), OneCFormatError),
])
def test_service_errors_are_not_retryable(payload: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        OneCSkladConnector(fake_client(payload), [ORG]).extract(
            Window(date(2026, 9, 1), TEST_AS_OF), CollectSink())


def test_parse_accepts_numeric_account_codes() -> None:
    data = parse_materials(json.loads(body("materials_current.json")))
    assert [r.account_code for r in data.data] == ["1000", "1010", "1050", "1060"]
    assert data.data[0].is_total is True and data.data[1].closing == Decimal("450000000")


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_clamps_window_and_replaces_vanished_accounts(source: str) -> None:
    tag = new_tag()
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch_row(tag)]})
    merge_all(run, source)
    org = OrgMap(branch_code=f"T-{tag}", org_uid=f"uid-{tag}", org_name="Тест")
    full = body("materials_current.json")
    one = json.dumps({"data": [{"accountCode": "1010", "accountName": "Сырьё и материалы",
                                "isTotal": False, "openingSum": 1, "closingSum": 7000000}]})
    for payload, expected in ((full, {"1C-ACC-1010", "1C-ACC-1050"}), (one.encode(),
                                                                         {"1C-ACC-1010"})):
        connector = OneCSkladConnector(fake_client(payload), [org], months=2, source=source)
        result = Runner(connector, mode=Mode.FULL, today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            window_from = conn.execute(text("SELECT window_from FROM core.etl_run WHERE id = :r"),
                                       {"r": result.run_id}).scalar_one()
            codes = set(conn.execute(text(
                "SELECT n.code FROM dwh.fact_stock s JOIN dwh.dim_nomenclature n "
                "ON n.nom_id = s.nom_id WHERE s.src_system = :s AND s.date_id = 20260924"),
                {"s": source}).scalars())
        assert window_from == date(2026, 8, 1)
        assert codes == expected


@pytest.fixture
def orgs_setting() -> Iterator[None]:
    put_setting("onec.orgs", [{"branch_code": "UGE-02", "org_uid": "uid-02",
                               "org_name": "Чорвоқ ГЭС"}])
    yield
    put_setting("onec.orgs", [])


def test_make_connector_worker_and_cli(orgs_setting: None,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    from pydantic import SecretStr

    assert "onec_sklad" in KNOWN_SOURCES
    with pytest.raises(ConfigError, match="ONEC_SKLAD_BASE_URL"):
        make_connector("onec_sklad", get_settings())
    no_secret = get_settings().model_copy(update={"onec_sklad_base_url": BASE})
    with pytest.raises(ConfigError, match="onec_sklad_username"):
        make_connector("onec_sklad", no_secret)
    ready = no_secret.model_copy(update={"onec_sklad_username": SecretStr("u"),
                                         "onec_sklad_password": SecretStr("p")})
    made = make_connector("onec_sklad", ready)
    assert isinstance(made, OneCSkladConnector) and made.lookback_months == 13
    assert made.orgs == [ORG]
    jobs = {j.id: j for j in worker.build_scheduler(ready, RecordingNotifier()).get_jobs()}
    assert jobs["etl_onec_sklad_full"].args[:2] == ("onec_sklad", Mode.FULL)
    assert jobs["etl_onec_sklad_incremental"].args[:2] == ("onec_sklad", Mode.INCREMENTAL)
    off = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "etl_onec_sklad_full" not in off
    assert cli.main(["onec-sklad-check"]) == 2
    assert "ONEC_SKLAD_BASE_URL" in capsys.readouterr().out
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_onec_sklad.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.onec.sklad'`.

- [ ] **Step 4: Implementatsiya — javob modeli**

`backend/app/etl/onec/sklad_models.py`:
```python
"""1C `hs/sklad/materials` javobi (S3 spec 3.3). Joriy shakl (eski dashboard): data[] —
accountCode, accountName, isTotal, openingSum, closingSum (so'm). Ixtiyoriy maydonlar —
1C dasturchilaridan so'ralgan kengaytma (docs/integration/1c-sorov-s3.md, G1–G5); snake_case va
camelCase ikkalasi qabul qilinadi. {"success": false, "code", "error"} — xizmat xatosi.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.etl.onec.client import OneCError
from app.etl.onec.models import parse


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class MaterialRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, coerce_numbers_to_str=True)
    account_code: str = Field(validation_alias=_alias("accountCode", "account_code"),
                              pattern=r"^\d{2,8}$")
    account_name: str = Field(validation_alias=_alias("accountName", "account_name"),
                              min_length=1, max_length=300)
    is_total: bool = Field(False, validation_alias=_alias("isTotal", "is_total"))
    opening: Decimal = Field(Decimal(0),
                             validation_alias=_alias("openingSum", "opening_sum", "opening"))
    closing: Decimal = Field(validation_alias=_alias("closingSum", "closing_sum", "closing"))
    nomenclature_code: str | None = Field(
        None, validation_alias=_alias("nomenclature_code", "nomenclatureCode"), max_length=100)
    nomenclature_name: str | None = Field(
        None, validation_alias=_alias("nomenclature_name", "nomenclatureName"), max_length=300)
    unit: str | None = Field(None, validation_alias=_alias("unit"), max_length=16)
    warehouse_name: str | None = Field(
        None, validation_alias=_alias("warehouse_name", "warehouseName"), max_length=100)
    closing_qty: Decimal | None = Field(None,
                                        validation_alias=_alias("closing_qty", "closingQty"))
    min_qty: Decimal | None = Field(None, validation_alias=_alias("min_qty", "minQty"))
    last_move_date: date | None = Field(
        None, validation_alias=_alias("last_move_date", "lastMoveDate"))
    debit_sum: Decimal | None = Field(None, validation_alias=_alias("debit_sum", "debitSum"))
    credit_sum: Decimal | None = Field(None, validation_alias=_alias("credit_sum", "creditSum"))


class MaterialsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    data: list[MaterialRow]


def parse_materials(data: Any) -> MaterialsResponse:
    if isinstance(data, dict) and data.get("success") is False:
        code = str(data.get("code", ""))[:40]
        error = str(data.get("error", ""))[:200]
        raise OneCError(f"1С /materials: ошибка сервиса {code} {error}".strip())
    return parse(MaterialsResponse, data, "/materials")
```

- [ ] **Step 5: Implementatsiya — konnektor**

`backend/app/etl/onec/sklad.py`:
```python
"""OneCSkladConnector — SourceConnector 1C `hs/sklad/materials` ustida (S3 spec 3.3).

Har tashkilot (onec.orgs) × har oy: {date_from: oy boshi, date_to: min(oy oxiri, oyna oxiri),
org_uid} → oy oxiri (ochiq oyda — bugun) snapshot'i: fact_stock (value = closing / 10⁶),
kengaytirilgan javobda — fact_stock_move (debit → prixod, credit → rasxod). `isTotal`/`1000`
jami qatorlari tashlanadi (ikki marta sanalmaydi); manfiy qoldiq (сторно) — log, yuklanmaydi.
Oyna — oxirgi `months` oy (Runner `lookback_months`), maqsadlar oyna ichida to'liq almashtiriladi.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.logging import get_logger
from app.dwh.dates import add_months, date_id, month_end, month_id, month_start, today_tashkent
from app.etl.onec.client import OneCClient
from app.etl.onec.connector import OrgMap, stable_code, to_mln
from app.etl.onec.sklad_models import MaterialRow, parse_materials
from app.etl.types import (
    ConnectorUnavailableError,
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "onec_sklad"
PATH = "/materials"
TOTAL_ACCOUNT = "1000"
DEFAULT_WAREHOUSE = "Основной склад"
_QTY = Decimal("0.001")
log = get_logger("ugekazna.onec.sklad")


def periods(window: Window) -> list[tuple[date, date]]:
    """To'liq oylar (oborotlar oy bo'yicha to'liq bo'lsin), oxirgisi oyna oxirida kesiladi."""
    out: list[tuple[date, date]] = []
    cur = month_start(window.date_from)
    while cur <= window.date_to:
        out.append((cur, min(month_end(cur), window.date_to)))
        cur = add_months(cur, 1)
    return out


class OneCSkladConnector:
    def __init__(self, client: OneCClient, orgs: Sequence[OrgMap], *, months: int = 13,
                 source: str = SOURCE,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.source = source
        self.client = client
        self.orgs = list(orgs)
        self.lookback_months = months
        self.now = now

    def healthcheck(self) -> HealthResult:
        today = today_tashkent().isoformat()
        try:
            self.client.post(PATH, {"date_from": today, "date_to": today,
                                    "org_uid": self.orgs[0].org_uid})
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "1С (склад) доступна")

    def watermark(self) -> Watermark:
        return Watermark(self.now())

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        counts: Counter[str] = Counter({"fact_stock": 0, "fact_stock_move": 0})
        noms: dict[str, dict[str, Any]] = {}
        for org in self.orgs:
            for start, end in periods(window):
                data = self.client.post(PATH, {"date_from": start.isoformat(),
                                               "date_to": end.isoformat(),
                                               "org_uid": org.org_uid})
                for row in parse_materials(data).data:
                    self._row(org, end, row, sink, counts, noms)
        for nom in noms.values():
            sink.add("dim_nomenclature", nom)
        counts["dim_nomenclature"] = len(noms)
        return ExtractStats(sum(counts.values()), dict(counts))

    @staticmethod
    def _row(org: OrgMap, end: date, row: MaterialRow, sink: StagingSink,
             counts: Counter[str], noms: dict[str, dict[str, Any]]) -> None:
        if row.is_total or row.account_code == TOTAL_ACCOUNT:
            return
        if row.closing < 0:
            log.warning("onec_sklad_negative_balance", branch=org.branch_code,
                        account=row.account_code)
            return
        if row.nomenclature_code or row.nomenclature_name:
            nom_code = stable_code("1C-N-", row.nomenclature_code or row.nomenclature_name or "",
                                   row.unit or "")
            name = row.nomenclature_name or row.account_name
        else:
            nom_code = f"1C-ACC-{row.account_code}"
            name = row.account_name
        noms.setdefault(nom_code, {"code": nom_code, "name": name[:300],
                                   "category": row.account_name[:100],
                                   "unit": (row.unit or "—")[:16], "enbt_code": None})
        warehouse = (row.warehouse_name or DEFAULT_WAREHOUSE).strip()[:100] or DEFAULT_WAREHOUSE
        wh_key = hashlib.sha256(warehouse.encode()).hexdigest()[:10]
        key = f"{org.org_uid}:{nom_code}:{wh_key}:{month_id(end)}"
        value = to_mln(row.closing)
        qty = (row.closing_qty or Decimal(0)).quantize(_QTY)
        base = {"date_id": date_id(end), "branch_code": org.branch_code, "nom_code": nom_code}
        if value > 0 or qty > 0:
            sink.add("fact_stock", {
                **base, "doc_type": "onec_stock", "src_id": key, "warehouse": warehouse,
                "qty": qty, "value": value, "min_qty": row.min_qty,
                "last_move_date_id": date_id(row.last_move_date) if row.last_move_date else None})
            counts["fact_stock"] += 1
        for direction, amount in (("in", row.debit_sum), ("out", row.credit_sum)):
            if amount is not None and amount > 0:
                sink.add("fact_stock_move", {
                    **base, "doc_type": "onec_stock_move", "src_id": f"{key}:{direction}",
                    "direction": direction, "qty": Decimal("0.000"), "value": to_mln(amount)})
                counts["fact_stock_move"] += 1
```

- [ ] **Step 6: Runner oynasi cheklovi**

`backend/app/etl/runner.py` — `_run_locked` ichida `window = compute_window(...)` chaqiruvidan KEYIN qo'shing:
```python
            # S3: manba o'z oynasini cheklashi mumkin (1C ombori — oxirgi N oy snapshot'lari;
            # to'liq tarixni har kecha so'rash 180 s × oylar × tashkilotlar). Almashtirish (replace)
            # ham shu qisqa oyna ichida — undan eski qatorlar saqlanadi.
            lookback = getattr(self.connector, "lookback_months", None)
            if isinstance(lookback, int) and lookback > 0:
                floor = add_months(month_start(self.today), -(lookback - 1))
                window = Window(max(window.date_from, floor), window.date_to)
```
(`Window`, `add_months`, `month_start` runner'da allaqachon import qilingan; bo'lmasa — `from app.etl.types import Window`, `from app.dwh.dates import add_months, month_start`.)

- [ ] **Step 7: Reyestr, worker, CLI**

`backend/app/etl/connectors.py` — importlarga:
```python
from app.etl.onec.sklad import OneCSkladConnector
```
`KNOWN_SOURCES` oxiriga `"onec_sklad"` qo'shing:
```python
KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank", "askue", "onec_sklad")
```
`_askue` dan keyin qo'shing:
```python
def _onec_sklad(settings: Settings) -> OneCSkladConnector:
    if not settings.onec_sklad_base_url:
        raise ConfigError("ONEC_SKLAD_BASE_URL berilmagan — 1C ombor konnektori o'chiq")
    username = settings.onec_sklad_username.get_secret_value()
    password = settings.onec_sklad_password.get_secret_value()
    if not username or not password:
        raise ConfigError("onec_sklad_username/onec_sklad_password sirlari bo'sh")
    with get_engine("etl").connect() as conn:
        orgs = current_setting(conn, "onec.orgs")
        months = int(current_setting(conn, "onec.sklad_months"))
    if not orgs:
        raise ConfigError("onec.orgs bo'sh: `python -m app.cli onec-orgs --file …` bilan sozlang")
    client = OneCClient(settings.onec_sklad_base_url, username, password,
                        verify=verify_setting(settings.onec_ca_file),
                        allow_http=settings.onec_allow_http, max_bytes=settings.onec_max_bytes)
    return OneCSkladConnector(client, [OrgMap(**org) for org in orgs], months=months)
```
`make_connector` ichida `if source == "askue":` dan oldin:
```python
    if source == "onec_sklad":
        return _onec_sklad(settings)
```

`backend/app/worker.py` — `build_scheduler` ichida (`askue_live` blokidan keyin):
```python
    if settings.onec_sklad_base_url:
        with get_engine("app").connect() as conn:
            sklad_full = str(current_setting(conn, "etl.onec_sklad_full_cron"))
            sklad_incr = str(current_setting(conn, "etl.onec_sklad_incremental_cron"))
        # TZ 8: 1C — kechasi to'liq (oxirgi onec.sklad_months oy), kunduzi inkremental 3 marta.
        scheduler.add_job(run_etl_job, CronTrigger.from_crontab(sklad_full, timezone=TASHKENT),
                          args=("onec_sklad", Mode.FULL, notifier), id="etl_onec_sklad_full",
                          **opts)
        scheduler.add_job(run_etl_job, CronTrigger.from_crontab(sklad_incr, timezone=TASHKENT),
                          args=("onec_sklad", Mode.INCREMENTAL, notifier),
                          id="etl_onec_sklad_incremental", **opts)
```

`backend/app/cli.py` — `_onec_check` dan keyin qo'shing:
```python
def _onec_sklad_check() -> int:
    from app.etl.connectors import make_connector

    try:
        connector = make_connector("onec_sklad")
    except ConfigError as exc:
        _out(f"Konfiguratsiya xatosi: {exc}")
        return 2
    health = connector.healthcheck()
    _out(f"1C (sklad): {'OK' if health.ok else 'XATO'} — {health.detail}")
    return 0 if health.ok else 1
```
`main` ichida:
```python
    sub.add_parser("onec-sklad-check")
```
dispatch'da:
```python
    if args.command == "onec-sklad-check":
        return _onec_sklad_check()
```
Docstring ro'yxatiga:
```
onec-sklad-check — 1C ombor servisiga (hs/sklad) ulanishni tekshirish
```

- [ ] **Step 8: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_onec_sklad.py tests/test_worker.py tests/test_etl_runner.py tests/test_onec_connector.py -v`
Expected: barcha testlar passed (2-reja runner testlari o'zgarmaydi — `lookback_months` yo'q konnektorlarda oyna avvalgidek).

- [ ] **Step 9: Commit**

```bash
git add backend
git commit -m "feat(onec): 1C ombor konnektori (hs/sklad/materials), Runner oynasi cheklovi, worker va CLI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 14: Ekspluatatsiya — prod compose (АСКУЭ inbox, 1C ombor sirlari, egress), hujjatlar va 1C'ga so'rov xati

**Files:**
- Create: `docs/integration/askue-format.md`, `docs/integration/askue-connector.md`, `docs/integration/proizvodstvo-fayl.md`, `docs/integration/1c-sorov-s3.md`, `backend/tests/ops/test_s3_ops.py`, `backend/tests/test_s3_file_templates.py`
- Modify: `deploy/compose.prod.yml`, `deploy/prod.env.example`, `deploy/secrets.example/README.md`, `scripts/prod_config.sh`, `docs/ops/host-hardening.md`
- Test: `backend/tests/ops/test_s3_ops.py`, `backend/tests/test_s3_file_templates.py`

**Interfaces:**
- Consumes: 4-reja `compose.prod.yml` (`worker` — `backend` + `egress`, `x-backend-env`), S2 worker sirlari va hajmlari ro'yxati, `tests.ops.repo.repo_path`, `scripts/prod_config.sh`, `FileConnector`, `Runner`, 1–13-vazifalar sozlamalari (`ASKUE_INBOX_DIR` = `/data/import/askue`, `ASKUE_LIVE_URL`, `ONEC_SKLAD_BASE_URL`, sirlar `onec_sklad_username`, `onec_sklad_password`).
- Produces: hajm `askue_inbox` (worker'da `:ro`, host bind `${UGK_ASKUE_INBOX:-/srv/ugekazna/askue/inbox}`); sirlar `onec_sklad_username`, `onec_sklad_password` — faqat `worker`; `worker` muhiti `ONEC_SKLAD_BASE_URL`, `ASKUE_LIVE_URL`; 4 ta hujjat (ruscha — mijoz, АСКУЭ yetkazuvchisi va 1C dasturchilari uchun); egress qoidasi (treplex.uz). Hujjatdagi CSV shablonlari test bilan tekshiriladi.

- [ ] **Step 1: Yiqiladigan testlarni yozish**

`backend/tests/ops/test_s3_ops.py`:
```python
from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

SKLAD = {"onec_sklad_username", "onec_sklad_password"}
DOCS = {
    "docs/integration/askue-format.md": (
        "station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours", "UTF-8",
        "ГГГГ-ММ-ДД", "МВт·ч", "unknown_station", "CHARVAK-1;2026-09-22;4810.6"),
    "docs/integration/askue-connector.md": (
        "askue-stations", "/srv/ugekazna/askue/inbox", "askue-live-check", "ASKUE_LIVE_URL",
        "askue.live_stale_minutes", "askue.inbox_days"),
    "docs/integration/proizvodstvo-fayl.md": (
        "fact_generation.csv", "generation_plan", "fact_energy_sales.csv", "etl-run",
        "dim_counterparty.csv"),
    "docs/integration/1c-sorov-s3.md": (
        "/materials", "nomenclature_code", "warehouse_name", "min_qty", "last_move_date",
        "debit_sum", "credit_sum", "HTTPS", "onec_sklad_username"),
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_askue_inbox_volume(compose: dict[str, Any]) -> None:
    worker = compose["services"]["worker"]
    assert "askue_inbox:/data/import/askue:ro" in worker["volumes"]
    opts = compose["volumes"]["askue_inbox"]["driver_opts"]
    assert (opts["type"], opts["o"]) == ("none", "bind")
    assert "/srv/ugekazna/askue/inbox" in opts["device"]
    for service, svc in compose["services"].items():
        if service != "worker":
            assert not any("askue" in v for v in svc.get("volumes", [])), service


def test_sklad_secrets_and_env_only_in_worker(compose: dict[str, Any]) -> None:
    assert SKLAD <= set(compose["secrets"])
    for service, svc in compose["services"].items():
        granted = SKLAD & set(svc.get("secrets", []))
        assert granted == (SKLAD if service == "worker" else set()), service
    env = compose["services"]["worker"]["environment"]
    assert env["ONEC_SKLAD_BASE_URL"] == "${ONEC_SKLAD_BASE_URL:-}"
    assert env["ASKUE_LIVE_URL"] == "${ASKUE_LIVE_URL:-}"
    api_env = compose["services"]["api"].get("environment", {})
    assert "ASKUE_LIVE_URL" not in api_env and "ONEC_SKLAD_BASE_URL" not in api_env


def test_docs_mention_required_facts() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "treplex.uz" in hardening
    secrets = repo_path("deploy/secrets.example/README.md").read_text(encoding="utf-8")
    assert "onec_sklad_username" in secrets and "onec_sklad_password" in secrets
    script = repo_path("scripts/prod_config.sh").read_text(encoding="utf-8")
    assert "onec_sklad_username onec_sklad_password" in script
```

`backend/tests/test_s3_file_templates.py` (hujjatdagi CSV shablonlari haqiqatda yuklanadi):
```python
from pathlib import Path

from sqlalchemy import text

from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from tests.etl_helpers import TEST_AS_OF, new_source, new_tag, purge_source


def test_plan_and_sales_templates_load(tmp_path: Path) -> None:
    source = new_source()
    tag = new_tag()
    code = f"T-{tag}"
    try:
        (tmp_path / "dim_branch.csv").write_text(
            "code;name;short_name;kind;capacity_mw;sort_order\n"
            f"{code};Тестовая ГЭС;Т;ges;100;99\n", encoding="utf-8")
        (tmp_path / "dim_counterparty.csv").write_text(
            "code;name;kind;inn\n"
            f"CPB-{tag};АО «Национальные электрические сети Узбекистана»;buyer;301234567\n",
            encoding="utf-8")
        (tmp_path / "fact_generation.csv").write_text(
            "doc_type;src_id;date;branch_code;generation;own_needs;supply;plan;work_hours\n"
            f"generation_plan;PLAN-{tag}-202609;2026-09-01;{code};0;0;0;1.5;\n",
            encoding="utf-8")
        (tmp_path / "fact_energy_sales.csv").write_text(
            "doc_type;src_id;date;branch_code;cp_code;accrued;paid;volume\n"
            f"energy_sales;ES-{tag}-202608;2026-08-31;{code};CPB-{tag};1200.00;900.00;1.760\n",
            encoding="utf-8")
        result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                        today=TEST_AS_OF, sleep=lambda _: None).run()
        assert result.status == "success", result
        with etl_transaction() as conn:
            branch_id = conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": code}).scalar_one()
            plan = conn.execute(text(
                "SELECT plan, plan_full FROM mart.agg_generation_month WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202609"),
                {"b": result.build_id, "br": branch_id}).one()
            sales = conn.execute(text(
                "SELECT accrued, paid FROM mart.agg_energy_sales_month WHERE build_id = :b "
                "AND branch_id = :br AND month_id = 202608"),
                {"b": result.build_id, "br": branch_id}).one()
        assert (float(plan.plan), float(plan.plan_full)) == (1.2, 1.5)
        assert (float(sales.accrued), float(sales.paid)) == (1200.0, 900.0)
    finally:
        purge_source(source)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/ops/test_s3_ops.py tests/test_s3_file_templates.py -v`
Expected: `test_s3_ops.py` — FAIL (`askue_inbox:/data/import/askue:ro` yo'q, hujjatlar yo'q); `test_s3_file_templates.py` — PASS (1–13-vazifalar kodi shablonni allaqachon qo'llaydi; hujjat shu test bilan bir xil yoziladi).

- [ ] **Step 3: Compose, env namunasi, sirlar**

`deploy/compose.prod.yml` — top-level `secrets:` ga qo'shing:
```yaml
  onec_sklad_username: {file: "${UGK_SECRETS_DIR:-./secrets}/onec_sklad_username"}
  onec_sklad_password: {file: "${UGK_SECRETS_DIR:-./secrets}/onec_sklad_password"}
```
`worker.environment` ga qo'shing:
```yaml
      ONEC_SKLAD_BASE_URL: ${ONEC_SKLAD_BASE_URL:-}
      ASKUE_LIVE_URL: ${ASKUE_LIVE_URL:-}
```
`worker.secrets` ro'yxatini almashtiring (S2 ro'yxati + 1C ombor):
```yaml
    secrets: [db_app_password, db_etl_password, redis_password, master_kek, blind_index_key,
              session_pepper, smtp_password, tls_cert, onec_username, onec_password,
              onec_ca_bundle, telegram_bot_token, telegram_chat_ids, onec_sklad_username,
              onec_sklad_password]
```
`worker.volumes` ro'yxati oxiriga qo'shing:
```yaml
      # АСКУЭ kunlik eksporti: faqat o'qish (yetkazuvchi/SFTP tomoni yozadi, host cron tozalaydi).
      - askue_inbox:/data/import/askue:ro
```
top-level `volumes:` ga qo'shing:
```yaml
  askue_inbox:
    driver: local
    driver_opts: {type: none, o: bind, device: "${UGK_ASKUE_INBOX:-/srv/ugekazna/askue/inbox}"}
```

`deploy/prod.env.example` — oxiriga:
```bash
# 1C ombor servisi (hs/sklad), masalan https://1c.uzbekhydro.local/con2026/hs/sklad
# (bo'sh — konnektor o'chiq). Login/parol — sirlar onec_sklad_username / onec_sklad_password.
ONEC_SKLAD_BASE_URL=
# Jonli quvvat manbasi (faqat https), masalan https://treplex.uz/api/cascades/ges.
# Bo'sh — «Текущая мощность» «Источник не подключён». Egress kerak (EGRESS_PROXY).
ASKUE_LIVE_URL=
# АСКУЭ kunlik eksporti host katalogi (worker ichida /data/import/askue, faqat o'qish).
UGK_ASKUE_INBOX=/srv/ugekazna/askue/inbox
```

`deploy/secrets.example/README.md` — jadval oxiriga:
```markdown
| onec_sklad_username | 1C ombor servisi (hs/sklad) login'i — faqat o'qish huquqli alohida hisob; bo'sh — o'chiq. Faqat worker |
| onec_sklad_password | 1C ombor servisi paroli; bo'sh — o'chiq. Faqat worker |
```

`scripts/prod_config.sh` — `for name in …` ro'yxati oxiriga (`telegram_bot_token telegram_chat_ids` dan keyin) qo'shing:
```bash
            onec_sklad_username onec_sklad_password \
```
(ya'ni `… telegram_bot_token telegram_chat_ids \` / `onec_sklad_username onec_sklad_password; do`.)

- [ ] **Step 4: Host egress qoidasi**

`docs/ops/host-hardening.md` — S2'da qo'shilgan «Выход в интернет для курсов ЦБ и Telegram» abzasidan keyin qo'shing:
````markdown
**Онлайн-мощность ГЭС (раздел S3).** Если задан `ASKUE_LIVE_URL` (например,
`https://treplex.uz/api/cascades/ges`), `worker` раз в 10 минут обращается к `treplex.uz:443`.
При работе через корпоративный прокси (`EGRESS_PROXY`) домен `treplex.uz` добавляется в список
разрешённых на прокси; без прокси в `DOCKER-USER` разрешается адрес `treplex.uz` на порт 443
(перед правилом `-o ens18 -j DROP`). Сервис 1С `hs/sklad` находится во внутренней сети и
разрешается тем же правилом, что и `hs/aiassistant` (раздел S1).
````

- [ ] **Step 5: АСКУЭ formati hujjati (yetkazuvchi uchun, ruscha)**

`docs/integration/askue-format.md`:
````markdown
# Формат суточной выгрузки АСКУЭ — UGEKAZNA

Документ для поставщика АСКУЭ и службы ИТ. Выгрузка — один или несколько CSV-файлов в сутки;
каждая строка — одна станция за одни сутки.

## Общие правила (ТЗ, раздел 8)

- Кодировка UTF-8 (BOM допускается), разделитель `;`, первая строка — заголовок.
- Даты — `ГГГГ-ММ-ДД`; числа — с точкой, без разделителей разрядов (`4810.6`, не `4 810,6`).
- Единицы — МВт·ч (мегаватт-часы) за сутки, часы работы — от 0 до 24.
- Файл кладётся во входной каталог сначала с расширением `.tmp`, затем переименовывается в `.csv`
  (файл моложе 60 секунд не читается). Размер файла — не более 20 МБ, строк — не более 100 000.
- Повторная выгрузка тех же суток допустима: строка «станция + дата» заменяет предыдущую.

## Колонки

| Колонка | Обязательна | Описание |
|---|---|---|
| `station` | да | код станции в АСКУЭ (латиница, цифры, `_ . -`, до 40 символов) |
| `date` | да | сутки выработки, не позже текущей даты |
| `generation_mwh` | да | выработка брутто, МВт·ч |
| `own_needs_mwh` | да | собственные нужды, МВт·ч (не больше выработки) |
| `supply_mwh` | нет | отпуск в сеть, МВт·ч (пусто — выработка минус собственные нужды) |
| `work_hours` | нет | часы работы станции за сутки |

## Пример

```
station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours
CHARVAK-1;2026-09-22;4810.6;72.2;4738.4;24
CHARVAK-1;2026-09-23;4702;70.4;;23.5
CHIRCHIQ-7;2026-09-23;1320.25;20.1;1300.15;24
```

## Ошибки

Ошибка в заголовке, кодировке или размере — файл не загружается целиком. Ошибочные строки
пропускаются, остальные загружаются; администратор получает уведомление с числом ошибок по кодам:

| Код | Причина |
|---|---|
| `bad_header`, `bad_encoding`, `too_large`, `too_many_rows` | файл не соответствует формату |
| `bad_row` | неверный код станции, дата или число, неверное число полей |
| `negative` | отрицательное значение |
| `own_gt_generation` | собственные нужды больше выработки |
| `bad_hours` | часы работы вне 0–24 |
| `future_date` | дата позже текущей |
| `duplicate_row` | повтор станции и даты в одном файле |
| `unknown_station` | код станции не сопоставлен с филиалом (настройка `askue.stations`) |

Суточная выработка больше установленной мощности × 24 останавливает публикацию данных
(проверка качества 4) до исправления выгрузки.
````

- [ ] **Step 6: Administrator yo'riqnomasi (ruscha)**

`docs/integration/askue-connector.md`:
````markdown
# АСКУЭ и онлайн-мощность ГЭС — инструкция администратора

## Суточная выгрузка (раздел «Производство»)

1. Каталог на сервере: `/srv/ugekazna/askue/inbox` (переменная `UGK_ASKUE_INBOX`), в контейнере
   `worker` — `/data/import/askue` только для чтения. Запись в каталог — у поставщика АСКУЭ
   (SFTP или общий ресурс).
2. Сопоставление станций и филиалов — JSON-файл и команда:
   ```bash
   docker compose -f deploy/compose.prod.yml exec worker \
     python -m app.cli askue-stations --file /data/inbox/stations.json
   ```
   ```json
   [{"code": "CHARVAK-1", "name": "Chorvoq GES", "branch_code": "UGE-02"},
    {"code": "CHIRCHIQ-7", "name": "Chirchiq GES-7", "branch_code": "UGE-03"}]
   ```
   `code` — код станции в выгрузке, `name` — название станции в онлайн-источнике, `branch_code` —
   код филиала-станции (ГЭС или каскад; головной организации станции не назначаются). Каждое
   изменение сохраняется новой версией и пишется в журнал аудита. Без аргумента `--file`
   команда показывает текущее сопоставление.
3. Загрузка — ежедневно в 07:15 (настройка `etl.askue_cron`). Каждый запуск перечитывает файлы
   за последние `askue.inbox_days` (7) дней; повторная загрузка не создаёт дублей.
4. Очистка каталога — на хосте (cron):
   `find /srv/ugekazna/askue/inbox -name '*.csv' -mtime +14 -delete`.
5. Ошибки строк — уведомление «Строки выгрузки АСКУЭ отклонены» и раздел администрирования
   «Состояние обменов». Формат файла — `docs/integration/askue-format.md`.
6. API АСКУЭ пока не настроен (формат не согласован); при согласовании добавляется адаптер
   источника без изменения витрины.

## План выработки и реализация

Пока 1С не выдаёт эти данные, они загружаются файлами — `docs/integration/proizvodstvo-fayl.md`.

## Онлайн-мощность («Текущая мощность»)

- Источник задаётся `ASKUE_LIVE_URL` в `prod.env` (только `https://`), выход в интернет — через
  `EGRESS_PROXY` (см. `docs/ops/host-hardening.md`). Пустое значение — карточка показывает
  «Источник не подключён».
- Опрос — каждые 10 минут (`askue.live_cron`), хранение снимков — `askue.live_keep_days` (35) дней,
  данные старше `askue.live_stale_minutes` (30) минут помечаются как устаревшие.
- Станции сопоставляются по полю `name` той же настройки `askue.stations`; несопоставленные
  станции не сохраняются (предупреждение в журнале worker).
- Проверка без записи в базу:
  ```bash
  docker compose -f deploy/compose.prod.yml exec worker python -m app.cli askue-live-check
  ```
  Код выхода 0 — источник ответил, 1 — ошибка источника, 2 — `ASKUE_LIVE_URL` не задан.
- Это мгновенная мощность (МВт), а не суточная выработка: в отчёты и расчёт КИУМ она не входит.

## 1С: склад

`ONEC_SKLAD_BASE_URL` (например, `https://…/con2026/hs/sklad`) и секреты `onec_sklad_username`,
`onec_sklad_password`; организации — та же настройка `onec.orgs` (команда `onec-orgs`).
Проверка: `python -m app.cli onec-sklad-check`. Загружаются последние `onec.sklad_months` (13)
месяцев: ночью полностью, днём трижды инкрементально.
````

- [ ] **Step 7: Reja va realizatsiya fayl shablonlari (ruscha)**

`docs/integration/proizvodstvo-fayl.md`:
````markdown
# Производство: план выработки и реализация электроэнергии из файлов

До подключения источника в 1С (запрос — `docs/integration/1c-sorov-s3.md`, пункты G7–G8) план
выработки и реализация загружаются CSV-файлами через файловый коннектор. Правила — как для
остальных файлов: UTF-8, `;`, даты `ГГГГ-ММ-ДД`, числа с точкой. Файлы кладутся в каталог
файлового коннектора (`/data/inbox` в контейнере `worker`).

## fact_generation.csv — план выработки (помесячно)

План — одна строка на станцию и месяц, дата — первое число месяца, `generation`, `own_needs`,
`supply` — нули, `plan` — план месяца в млн кВт·ч. В текущем месяце план сравнивается
пропорционально прошедшим дням.

```
doc_type;src_id;date;branch_code;generation;own_needs;supply;plan;work_hours
generation_plan;PLAN-UGE-02-202609;2026-09-01;UGE-02;0;0;0;1.5;
```

## dim_counterparty.csv — покупатели электроэнергии

```
code;name;kind;inn
CPB-NES;АО «Национальные электрические сети Узбекистана»;buyer;301234567
```

## fact_energy_sales.csv — реализация (покупатель × месяц)

Дата — последний день месяца (для текущего месяца — дата выгрузки), суммы — млн сум,
объём — млн кВт·ч.

```
doc_type;src_id;date;branch_code;cp_code;accrued;paid;volume
energy_sales;ES-UGE-02-202608;2026-08-31;UGE-02;CPB-NES;1200.00;900.00;1.760
```

## Загрузка

```bash
docker compose -f deploy/compose.prod.yml exec worker \
  python -m app.cli etl-run --source file --mode full
```
Файловый коннектор полностью заменяет свои строки в окне загрузки: файл должен содержать все
месяцы окна, а не только изменения.
````

- [ ] **Step 8: 1C dasturchilariga so'rov xati (ruscha)**

`docs/integration/1c-sorov-s3.md`:
````markdown
# Запрос к разработчикам 1С: данные склада и производства для UGEKAZNA (этап 3)

Сервис `hs/sklad/materials` (POST, `{"date_from":"ГГГГ-ММ-ДД","date_to":"ГГГГ-ММ-ДД","org_uid":…}`)
сейчас возвращает остатки по субсчетам счёта 10: `accountCode`, `accountName`, `isTotal`,
`openingSum`, `closingSum`. Этого достаточно для стоимости запасов по категориям, но не для
разделов «Минимальный запас», «Неликвиды» и оборачиваемости (ТЗ, раздел 4 «Склад»). Просим
добавить поля (имена — ровно такие; номенклатуру, склад, `closing_qty`, `min_qty`,
`last_move_date`, `debit_sum` и `credit_sum` система уже читает, остальные подключаются без
изменения формата):

| № | Что нужно | Поля в ответе `/materials` |
|---|---|---|
| G1 | Разрез по номенклатуре и складу | `nomenclature_code` (УИД), `nomenclature_name`, `unit`, `warehouse_code`, `warehouse_name` |
| G2 | Количество | `opening_qty`, `closing_qty` |
| G3 | Обороты за период | `debit_sum`, `credit_sum` (приход и расход, сум), `debit_qty`, `credit_qty` |
| G4 | Дата последнего движения позиции | `last_move_date` (ГГГГ-ММ-ДД) |
| G5 | Минимальный (нормативный) запас | `min_qty` — если ведётся в 1С; иначе укажите, где он ведётся |
| G6 | Документация ответа | признак `success`, коды ошибок, фильтр `org_uid` (без него — все организации?) |
| G7 | Реализация электроэнергии | новый метод: филиал × покупатель (УИД, ИНН) × месяц — начислено, оплачено, объём кВт·ч |
| G8 | План выработки | новый метод: станция × месяц — план выработки, кВт·ч (если ведётся в 1С) |
| G9 | Безопасность | публикация `hs/sklad` по HTTPS и отдельная учётная запись только на чтение для UGEKAZNA (секреты `onec_sklad_username` / `onec_sklad_password`); смену пароля прежней учётной записи |

Пример строки ответа после доработки:
```json
{"account_code": "1050", "account_name": "Запасные части", "is_total": false,
 "opening_sum": 48000000, "closing_sum": 96000000,
 "nomenclature_code": "00-00012345", "nomenclature_name": "Подшипник SKF 23140", "unit": "шт",
 "warehouse_code": "000000012", "warehouse_name": "Центральный склад",
 "opening_qty": 1, "closing_qty": 2, "min_qty": 4, "last_move_date": "2026-09-10",
 "debit_sum": 48000000, "credit_sum": 0, "debit_qty": 1, "credit_qty": 0}
```

Пока поля G1–G5 отсутствуют, в разделе «Склад» показатели «Ниже минимального запаса»,
«Неликвиды» и «Возраст запасов» выводятся как «Источник не подключён», правила панели
«Требует внимания» по складу не срабатывают. Без G7–G8 план выработки и реализация
загружаются из файлов (`docs/integration/proizvodstvo-fayl.md`).
````

- [ ] **Step 9: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/ops/test_s3_ops.py tests/test_s3_file_templates.py tests/ops -v`
Expected: barcha testlar passed. `./scripts/prod_config.sh` — `prod-config: OK` (sirlar namunasi yangilangan).

- [ ] **Step 10: Commit**

```bash
git add deploy scripts docs backend/tests
git commit -m "docs(s3): АСКУЭ formati va yo'riqnoma, reja/realizatsiya shablonlari, 1C'ga so'rov xati; prod compose

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 15: Frontend asoslari — tiplar, fixture'lar, matnlar, energiya formati, grafik formati; xarita `src/dash/map/` ga

**Files:**
- Create: `frontend/src/dash/energy.ts`, `frontend/src/dash/map/ProductionBlock.tsx`, `frontend/src/test/s3Fixtures.ts`
- Move (`git mv`): `frontend/src/sections/obzor/map/{GesMap.tsx,GesMap.test.tsx,geo.ts,geo.test.ts,uz-geo.json,map.css}` → `frontend/src/dash/map/`
- Modify: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (generatsiya), `frontend/src/api/types.ts`, `frontend/src/dash/chart.tsx` (`format`, `dashed`), `frontend/src/dash/formulas.ts` (`IndicatorKey`), `frontend/src/i18n/ru.ts`, `frontend/src/dash/map/GesMap.tsx` (umumiy `tip`), `frontend/src/dash/map/GesMap.test.tsx`, `frontend/src/dash/map/map.css`, `frontend/src/sections/obzor/svod.tsx`, `frontend/src/sections/obzor/map/StationPanel.tsx`, `frontend/src/sections/obzor/map/StationPanel.test.tsx`
- Test: `frontend/src/dash/energy.test.ts`, `frontend/src/dash/map/GesMap.test.tsx`, `frontend/src/dash/map/ProductionBlock.test.tsx`, `frontend/src/sections/obzor/map/StationPanel.test.tsx`

**Interfaces:**
- Consumes: 7, 8, 12-vazifa sxemalari (OpenAPI), S1 `chart.tsx` (`barConfig`, `ChartCanvas`, `Series`), `formatMoney`, `formatPct`, `formatNumber`, `t`, `MessageKey`, S1 `GesMap`/`geo`/`StationPanel`, `SVOD` (s1Fixtures), `renderWithProviders`, `expectNoAxeViolations`.
- Produces:
  - `src/api/types.ts`: `StationProductionOut, ProdKpisOut, GenMonthOut, SalesMonthOut, StationGenOut, MapStationOut, ProizvSvodOut, ProizvStanciiOut, ProizvRealizOut, PowerStationOut, PowerOut, StockKpisOut, StockMonthOut, StockBranchOut, StockPositionOut, AgeBucketOut, SkladSvodOut, SkladOstatkiOut, SkladMinimumOut, SkladNelikvidOut`.
  - `src/dash/energy.ts`: `kwhParts(mln, digits = 1) -> { value; unit }` (≥ 1000 — «млрд кВт·ч»), `formatKwh(mln | null | undefined, digits = 1) -> string`, `formatMw(mw | null | undefined, digits = 0) -> string`.
  - `chart.tsx`: `Series.dashed?: boolean` (chiziq — uzuk-uzuk, nuqtasiz), `barConfig({ …, format? })`, `ChartCanvasProps.format?` — `(value: number, digits: number) => string`, standart `formatMoney`.
  - `IndicatorKey` += `'generation' | 'genPlan' | 'capacity' | 'kium' | 'ownNeeds' | 'supply' | 'paymentLevel' | 'currentPower' | 'stockValue' | 'turnover' | 'belowMin' | 'illiquid' | 'stockAge' | 'stockFlow'`.
  - `src/dash/map/GesMap.tsx`: `MapPoint` (= `StationOut` va `MapStationOut` umumiy maydonlari), `productionTip(s: MapPoint) -> string` (TZ 6: nom, quvvat, ishlab chiqarish, reja %), `GesMap<T extends MapPoint>({ stations, selected, onSelect, tip? })`.
  - `src/dash/map/ProductionBlock.tsx`: `ProductionBlock({ capacity: number | null; production: StationProductionOut | null })` — quvvat, КИУМ, ishlab chiqarish va reja chizig'i (< 95% qizil), reja, to'lov darajasi (< 85% qizil); ma'lumot yo'q — «Нет данных о выработке за период.».
  - `src/test/s3Fixtures.ts`: `PERIOD_M08_S3, PROD_KPIS, STATIONS, GEN_MONTHS, SALES_MONTHS, MAP, PROIZV_SVOD, PROIZV_STANCII, PROIZV_REALIZ, PROIZV_HQ, POWER, POWER_STALE, POWER_NONE, STOCK_KPIS, STOCK_MONTHS, CATEGORIES, BELOW, IDLE, STOCK_BRANCHES, AGES, SKLAD_SVOD, SKLAD_OSTATKI, SKLAD_MINIMUM, SKLAD_NELIKVID, SKLAD_NO_MIN, SKLAD_NO_AGE`.
  - i18n: `unit.*`, `map.*`, `formula.*` (S3), `proizv.*`, `sklad.*` — 16–17-vazifalar shu kalitlardan foydalanadi.

- [ ] **Step 1: OpenAPI snapshot va tiplar**

Dev stack (1–14-vazifalar bilan) ishlayotgan bo'lsin: `docker compose -f deploy/compose.yml up -d --build`.
```bash
curl -skf https://localhost:8443/api/v1/openapi.json -o frontend/openapi.json
$NODE npm run gen:api
grep -c "ProizvSvodOut\|SkladSvodOut\|PowerOut\|StationProductionOut" frontend/src/api/schema.d.ts
```
Expected: `grep` > 0.

`frontend/src/api/types.ts` — oxiriga qo'shing:
```ts
export type StationProductionOut = Schemas['StationProductionOut'];
export type ProdKpisOut = Schemas['ProdKpisOut'];
export type GenMonthOut = Schemas['GenMonthOut'];
export type SalesMonthOut = Schemas['SalesMonthOut'];
export type StationGenOut = Schemas['StationGenOut'];
export type MapStationOut = Schemas['MapStationOut'];
export type ProizvSvodOut = Schemas['ProizvSvodOut'];
export type ProizvStanciiOut = Schemas['ProizvStanciiOut'];
export type ProizvRealizOut = Schemas['ProizvRealizOut'];
export type PowerStationOut = Schemas['PowerStationOut'];
export type PowerOut = Schemas['PowerOut'];
export type StockKpisOut = Schemas['StockKpisOut'];
export type StockMonthOut = Schemas['StockMonthOut'];
export type StockBranchOut = Schemas['StockBranchOut'];
export type StockPositionOut = Schemas['StockPositionOut'];
export type AgeBucketOut = Schemas['AgeBucketOut'];
export type SkladSvodOut = Schemas['SkladSvodOut'];
export type SkladOstatkiOut = Schemas['SkladOstatkiOut'];
export type SkladMinimumOut = Schemas['SkladMinimumOut'];
export type SkladNelikvidOut = Schemas['SkladNelikvidOut'];
```

- [ ] **Step 2: Formulalar va lug'at kalitlari**

`frontend/src/dash/formulas.ts` — `IndicatorKey` turining oxirgi qatoridagi `| 'dscr';` ni quyidagiga almashtiring (tur shu qator bilan tugaydi):
```ts
  | 'dscr'
  | 'generation' | 'genPlan' | 'capacity' | 'kium' | 'ownNeeds' | 'supply' | 'paymentLevel' | 'currentPower'
  | 'stockValue' | 'turnover' | 'belowMin' | 'illiquid' | 'stockAge' | 'stockFlow';
```

`frontend/src/i18n/ru.ts` — `} as const satisfies …` dan oldin qo'shing:
```ts
  'unit.mlnKwh': 'млн кВт·ч',
  'unit.bnKwh': 'млрд кВт·ч',
  'unit.mw': 'МВт',
  'unit.days': 'дней',
  'map.tipStation': '{name}: {capacity} МВт',
  'map.tipProduction': '{name}: {capacity} МВт, выработка {generation}, {plan} плана',
  'map.capacity': 'Установленная мощность',
  'map.mw': 'МВт',
  'map.kium': 'КИУМ',
  'map.generation': 'Выработка',
  'map.ofPlan': '{pct} плана',
  'map.plan': 'План выработки',
  'map.paymentLevel': 'Уровень оплаты',
  'map.noProduction': 'Нет данных о выработке за период.',
  'formula.generation': 'Выработка — сумма выработки станций за период, брутто (АСКУЭ)',
  'formula.genPlan': 'Выполнение плана выработки = факт / план; в незакрытом месяце план пропорционален прошедшим дням',
  'formula.capacity': 'Установленная мощность — сумма мощностей станций выборки на конец периода',
  'formula.kium': 'КИУМ = выработка / (установленная мощность × часы периода)',
  'formula.ownNeeds': 'Собственные нужды = собственные нужды / выработка',
  'formula.supply': 'Отпуск в сеть = выработка − собственные нужды',
  'formula.paymentLevel': 'Уровень оплаты = оплачено / начислено за отпущенную энергию',
  'formula.currentPower': 'Текущая мощность — мгновенная мощность станций по онлайн-мониторингу, МВт (не суточная выработка)',
  'formula.stockValue': 'Стоимость запасов = сумма (количество × цена) на дату',
  'formula.turnover': 'Оборачиваемость = стоимость запасов / (расход за период / число дней)',
  'formula.belowMin': 'Ниже минимального запаса — позиции, где количество меньше минимума; обеспеченность = количество / минимум',
  'formula.illiquid': 'Неликвиды — стоимость позиций без движения более 180 дней и их доля в стоимости запасов',
  'formula.stockAge': 'Возраст запасов — распределение стоимости по срокам без движения',
  'formula.stockFlow': 'Поступление и списание запасов за период',
  'proizv.kpi.generation': 'Выработка электроэнергии',
  'proizv.kpi.period': 'за период',
  'proizv.kpi.execution': 'Выполнение плана выработки',
  'proizv.kpi.executionNote': 'план {plan}',
  'proizv.kpi.capacity': 'Установленная мощность',
  'proizv.kpi.capacityNote': 'станций: {count}',
  'proizv.kpi.kium': 'КИУМ',
  'proizv.kpi.kiumNote': 'коэффициент использования мощности',
  'proizv.kpi.supply': 'Отпуск в сеть',
  'proizv.kpi.supplyNote': 'собственные нужды {share}',
  'proizv.kpi.payment': 'Уровень оплаты',
  'proizv.kpi.paymentNote': 'оплачено {paid} из {accrued}',
  'proizv.months.title': 'Выработка по месяцам',
  'proizv.months.sub': 'Факт и план, кВт·ч. Текущий месяц — по прошедшим дням',
  'proizv.months.fact': 'Факт',
  'proizv.months.plan': 'План',
  'proizv.months.prev': 'Прошлый год',
  'proizv.months.month': 'Месяц',
  'proizv.rank.title': 'Выработка по станциям',
  'proizv.rank.sub': 'Черта показывает план. Нажмите для выбора станции',
  'proizv.rank.ofPlan': '{pct} плана',
  'proizv.rank.all': 'Все станции',
  'proizv.map.title': 'ГЭС на карте Узбекистана',
  'proizv.map.sub': 'Размер отметки — установленная мощность; красная отметка — выполнение плана ниже 95%',
  'proizv.panel.all': 'Все станции',
  'proizv.panel.allNote': 'Станций: {count}. Нажмите на станцию на карте или в списке',
  'proizv.panel.open': 'Открыть данные станции',
  'proizv.panel.hq': 'Головная организация не эксплуатирует станции.',
  'proizv.table.title': 'Станции',
  'proizv.table.sub': 'Нажмите на строку, чтобы выбрать станцию',
  'proizv.table.station': 'Станция',
  'proizv.table.capacity': 'Мощность, МВт',
  'proizv.table.plan': 'План',
  'proizv.table.fact': 'Факт',
  'proizv.table.execution': 'Выполнение',
  'proizv.table.kium': 'КИУМ',
  'proizv.table.supply': 'Отпуск в сеть',
  'proizv.table.total': 'Итого',
  'proizv.sales.title': 'Реализация электроэнергии по месяцам',
  'proizv.sales.sub': 'Начислено за отпущенную энергию и оплачено покупателем',
  'proizv.sales.accrued': 'Начислено',
  'proizv.sales.paid': 'Оплачено',
  'proizv.pay.title': 'Уровень оплаты по станциям',
  'proizv.pay.sub': 'Оплачено от начисленного за период',
  'proizv.pay.note': '{pct} оплаты',
  'proizv.power.title': 'Текущая мощность',
  'proizv.power.sub': 'Онлайн-мониторинг станций',
  'proizv.power.asOf': 'по данным на {time}',
  'proizv.power.stale': 'Данные устарели',
  'proizv.power.units': 'Агрегаты: в работе {working}, в резерве {reserve}, в ремонте {repair}',
  'proizv.power.source': 'онлайн-мониторинг ГЭС',
  'proizv.power.stations': 'Мощность по станциям',
  'proizv.none.title': 'Нет станций',
  'proizv.none.text': 'Головная организация не эксплуатирует станции. Выберите «Все филиалы» или конкретную ГЭС.',
  'sklad.kpi.value': 'Стоимость запасов',
  'sklad.kpi.valueNote': 'на {date}',
  'sklad.kpi.turnover': 'Оборачиваемость',
  'sklad.kpi.turnoverNote': 'запас в днях списания',
  'sklad.kpi.below': 'Ниже минимального запаса',
  'sklad.kpi.belowNote': 'из {count} позиций',
  'sklad.kpi.illiquid': 'Неликвиды',
  'sklad.kpi.illiquidNote': '{amount}, без движения более 180 дней',
  'sklad.kpi.inflow': 'Поступило на склады',
  'sklad.kpi.outflow': 'Списано в производство',
  'sklad.kpi.period': 'за период',
  'sklad.kpi.noSource': 'нет данных в 1С',
  'sklad.flow.title': 'Движение запасов по месяцам',
  'sklad.flow.sub': 'Поступление и списание. Текущий месяц — по прошедшим дням',
  'sklad.flow.in': 'Поступило',
  'sklad.flow.out': 'Списано',
  'sklad.flow.month': 'Месяц',
  'sklad.cat.title': 'Запасы по категориям',
  'sklad.cat.sub': 'Стоимость на {date}',
  'sklad.below.title': 'Ниже минимального запаса',
  'sklad.below.subTop': 'Самые дефицитные позиции',
  'sklad.below.subAll': 'Отсортировано по обеспеченности, самые дефицитные сверху',
  'sklad.below.all': 'Все позиции',
  'sklad.below.none': 'Все позиции выше минимального запаса.',
  'sklad.below.source': 'минимальный запас (1С)',
  'sklad.col.position': 'Позиция',
  'sklad.col.warehouse': 'Склад',
  'sklad.col.qty': 'Остаток',
  'sklad.col.min': 'Минимум',
  'sklad.col.coverage': 'Обеспеченность',
  'sklad.col.value': 'Стоимость',
  'sklad.col.age': 'Без движения',
  'sklad.col.days': '{days} дн.',
  'sklad.col.count': 'Количество',
  'sklad.branches.title': 'Склады',
  'sklad.branches.sub': 'Нажмите на строку, чтобы выбрать филиал',
  'sklad.branches.positions': 'Позиций',
  'sklad.branches.below': 'Ниже минимума',
  'sklad.branches.idle': 'Неликвиды',
  'sklad.age.title': 'Возраст запасов',
  'sklad.age.sub': 'Стоимость по сроку без движения',
  'sklad.age.le90': 'до 90 дней',
  'sklad.age.d91_180': '91–180 дней',
  'sklad.age.d181_365': '181–365 дней',
  'sklad.age.gt365': 'более 365 дней',
  'sklad.age.unknown': 'нет даты движения',
  'sklad.age.source': 'дата последнего движения (1С)',
  'sklad.idle.title': 'Без движения более 180 дней',
  'sklad.idle.sub': 'Отсортировано по стоимости',
  'sklad.idle.none': 'Неликвидных запасов нет.',
```
S1'dagi kalit qiymatini almashtiring (3-bosqich keldi):
```ts
  'obzor.station.noProduction': 'Нет данных о выработке за период.',
```

- [ ] **Step 3: Test fixture'lari**

`frontend/src/test/s3Fixtures.ts`:
```ts
import type {
  AgeBucketOut,
  GenMonthOut,
  MapStationOut,
  PowerOut,
  ProdKpisOut,
  ProizvRealizOut,
  ProizvStanciiOut,
  ProizvSvodOut,
  ReportPeriodOut,
  SalesMonthOut,
  SkladMinimumOut,
  SkladNelikvidOut,
  SkladOstatkiOut,
  SkladSvodOut,
  StationGenOut,
  StockBranchOut,
  StockKpisOut,
  StockMonthOut,
  StockPositionOut,
} from '../api/types';

export const PERIOD_M08_S3: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

export const PROD_KPIS: ProdKpisOut = {
  has_data: true, generation: 2400.5, generation_prev: 2200, plan: 2500, execution: 0.9602, capacity_mw: 2027, stations: 15,
  kium: 0.52, own_needs: 36, own_share: 0.015, supply: 2364.5, accrued: 1650000, paid: 1320000, payment_level: 0.8,
};

function station(id: number, name: string, short: string, capacity: number, generation: number, plan: number, accrued: number, paid: number): StationGenOut {
  return {
    branch_id: id, name, short_name: short, capacity_mw: capacity, generation, generation_prev: generation * 0.9, plan,
    execution: generation / plan, kium: (generation * 1000) / (capacity * 744), supply: generation * 0.985, own_share: 0.015,
    accrued, paid, payment_level: paid / accrued,
  };
}

export const STATIONS: StationGenOut[] = [
  station(2, 'Чарвакская ГЭС', 'Чарвак', 666, 310, 300, 210000, 190000),
  station(3, 'Каскад Чирчикских ГЭС', 'Чирчик', 190, 80, 100, 55000, 40000),
  station(4, 'Андижанская ГЭС', 'Андижан', 190, 95, 98, 60000, 57000),
];

export const GEN_MONTHS: GenMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, generation: 200 + i * 20, plan: 210 + i * 20, generation_prev: 190 + i * 18 }));
export const SALES_MONTHS: SalesMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, accrued: 150000 + i * 5000, paid: 120000 + i * 4000 }));

export const MAP: MapStationOut[] = [
  { branch_id: 1, code: 'UGE-01', name: 'АО «Узбекгидроэнерго»', short_name: 'Узбекгидроэнерго', kind: 'head', capacity_mw: null, lat: 41.3111, lon: 69.2797, production: null },
  { branch_id: 2, code: 'UGE-02', name: 'Чарвакская ГЭС', short_name: 'Чарвак', kind: 'ges', capacity_mw: 666, lat: 41.626, lon: 70.029, production: { generation: 310, plan: 300, execution: 310 / 300, kium: 0.63, payment_level: 0.905 } },
  { branch_id: 3, code: 'UGE-03', name: 'Каскад Чирчикских ГЭС', short_name: 'Чирчик', kind: 'cascade', capacity_mw: 190, lat: 41.47, lon: 69.58, production: { generation: 80, plan: 100, execution: 0.8, kium: 0.57, payment_level: 0.727 } },
];

export const PROIZV_SVOD: ProizvSvodOut = { period: PERIOD_M08_S3, has_stations: true, kpis: PROD_KPIS, months: GEN_MONTHS, stations: STATIONS, map: MAP };
export const PROIZV_STANCII: ProizvStanciiOut = { period: PERIOD_M08_S3, has_stations: true, kpis: PROD_KPIS, stations: STATIONS };
export const PROIZV_REALIZ: ProizvRealizOut = {
  period: PERIOD_M08_S3, has_stations: true, kpis: PROD_KPIS, months: SALES_MONTHS,
  stations: [STATIONS[1], STATIONS[0], STATIONS[2]].filter((s): s is StationGenOut => s !== undefined),
};
export const PROIZV_HQ: ProizvStanciiOut = { period: PERIOD_M08_S3, has_stations: false, kpis: { ...PROD_KPIS, has_data: false }, stations: [] };

export const POWER: PowerOut = {
  has_source: true, snap_at: '2026-09-25T05:40:00Z', source_date: '25.09.2026 10:40', stale: false, total_mw: 412.5,
  units_working: 5, units_reserve: 1, units_repair: 1,
  stations: [
    { branch_id: 2, branch_name: 'Чарвакская ГЭС', station: 'CHARVAK-1', station_name: 'Chorvoq GES', cascade_name: 'Чирчик-Бозсу', power_mw: 380.5, units_working: 3, units_reserve: 1, units_repair: 0 },
    { branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС', station: 'CHIRCHIQ-7', station_name: 'Chirchiq GES-7', cascade_name: 'Чирчик-Бозсу', power_mw: 32, units_working: 2, units_reserve: 0, units_repair: 1 },
  ],
};
export const POWER_STALE: PowerOut = { ...POWER, stale: true };
export const POWER_NONE: PowerOut = { has_source: false, snap_at: null, source_date: null, stale: false, total_mw: 0, units_working: 0, units_reserve: 0, units_repair: 0, stations: [] };

export const STOCK_KPIS: StockKpisOut = {
  as_of: '2026-08-31', has_data: true, value: 120, turnover_days: 26.6, positions: 3, below_min: 1, has_minimum: true,
  idle_value: 80, idle_share: 0.6667, has_age: true, inflow: 100, outflow: 140,
};
export const STOCK_MONTHS: StockMonthOut[] = Array.from({ length: 9 }, (_, i) => ({ month_id: 202601 + i, inflow: 90 + i, outflow: 95 + i }));
export const CATEGORIES = [{ name: 'Запасные части', amount: 100 }, { name: 'Масла и ГСМ', amount: 20 }];

function position(nom: string, name: string, unit: string, qty: number, min: number | null, value: number, age: number | null, branchId = 3): StockPositionOut {
  return {
    branch_id: branchId, branch_name: branchId === 3 ? 'Каскад Чирчикских ГЭС' : 'Чарвакская ГЭС', warehouse: 'Склад Чирчик', nom_code: nom, name,
    category: 'Запасные части', unit, qty, min_qty: min, coverage: min ? qty / min : null, value, age_days: age,
  };
}

export const BELOW: StockPositionOut[] = [position('NOM-001', 'Подшипник SKF 23140', 'шт', 4, 10, 192, 11)];
export const IDLE: StockPositionOut[] = [
  position('NOM-004', 'Задвижка DN200', 'шт', 2, null, 56, 456, 2),
  position('NOM-010', 'Трансформаторное масло ГК', 'л', 500, 100, 19, 233),
];
export const STOCK_BRANCHES: StockBranchOut[] = [
  { branch_id: 2, name: 'Чарвакская ГЭС', value: 80, positions: 10, below_min: 2, idle_value: 30 },
  { branch_id: 3, name: 'Каскад Чирчикских ГЭС', value: 40, positions: 8, below_min: 0, idle_value: 5 },
];
export const AGES: AgeBucketOut[] = [
  { key: 'le90', value: 40 }, { key: 'd91_180', value: 0 }, { key: 'd181_365', value: 20 }, { key: 'gt365', value: 60 }, { key: 'unknown', value: 0 },
];

export const SKLAD_SVOD: SkladSvodOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, months: STOCK_MONTHS, categories: CATEGORIES, below: BELOW };
export const SKLAD_OSTATKI: SkladOstatkiOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, branches: STOCK_BRANCHES, categories: CATEGORIES };
export const SKLAD_MINIMUM: SkladMinimumOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, below: BELOW };
export const SKLAD_NELIKVID: SkladNelikvidOut = { period: PERIOD_M08_S3, kpis: STOCK_KPIS, ages: AGES, illiquid: IDLE };
const NO_SOURCE_KPIS: StockKpisOut = { ...STOCK_KPIS, below_min: 0, has_minimum: false, idle_value: 0, idle_share: null, has_age: false };
export const SKLAD_NO_MIN: SkladMinimumOut = { period: PERIOD_M08_S3, kpis: NO_SOURCE_KPIS, below: [] };
export const SKLAD_NO_AGE: SkladNelikvidOut = {
  period: PERIOD_M08_S3, kpis: NO_SOURCE_KPIS, ages: AGES.map((a) => ({ ...a, value: a.key === 'unknown' ? 120 : 0 })), illiquid: [],
};
```

- [ ] **Step 4: Xaritani `src/dash/map/` ga ko'chirish**

```bash
mkdir -p frontend/src/dash/map
for f in GesMap.tsx GesMap.test.tsx geo.ts geo.test.ts uz-geo.json map.css; do
  git mv "frontend/src/sections/obzor/map/$f" "frontend/src/dash/map/$f"
done
# geo.test.ts faqat ./geo ni import qiladi; qolgan nisbiy yo'llar keyingi qadamlarda yoziladi.
grep -rn "obzor/map/GesMap\|obzor/map/geo\|obzor/map/map.css" frontend/src || echo "eski yo'llar yo'q"
```
`frontend/scripts/extract-geo.mjs` o'zgarmaydi (chiqish yo'li argument); geometriyani qayta ajratish kerak bo'lsa — `frontend/src/dash/map/uz-geo.json` ga yoziladi.

- [ ] **Step 5: Testlarni yozish**

`frontend/src/dash/energy.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { t } from '../i18n';
import { formatKwh, formatMw, kwhParts } from './energy';

describe('energy format', () => {
  it('switches to billions of kWh from 1000 mln', () => {
    expect(formatKwh(1.8)).toBe('1,8 млн кВт·ч');
    expect(formatKwh(2400.5)).toBe('2,4 млрд кВт·ч');
    expect(kwhParts(310)).toEqual({ value: '310,0', unit: 'млн кВт·ч' });
    expect(formatKwh(null)).toBe(t('dash.noValue'));
  });

  it('formats megawatts', () => {
    expect(formatMw(412.5, 1)).toBe('412,5 МВт');
    expect(formatMw(undefined)).toBe(t('dash.noValue'));
  });
});
```

`frontend/src/dash/map/GesMap.test.tsx` (ko'chirilgan faylni to'liq almashtiring):
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { SVOD } from '../../test/s1Fixtures';
import { MAP } from '../../test/s3Fixtures';
import { GesMap, productionTip } from './GesMap';

describe('GesMap', () => {
  it('renders stations as toggle buttons with the TZ tooltip', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { container, rerender } = render(<GesMap stations={MAP} selected={null} onSelect={onSelect} />);
    expect(screen.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(container.querySelector('rect.ges__dot--hq')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: /Чарвакская ГЭС: 666 МВт, выработка 310,0 млн кВт·ч, 103% плана/ }));
    expect(onSelect).toHaveBeenLastCalledWith(2);
    rerender(<GesMap stations={MAP} selected={2} onSelect={onSelect} />);
    const charvak = screen.getByRole('button', { name: /Чарвакская ГЭС/ });
    expect(charvak).toHaveAttribute('aria-pressed', 'true');
    charvak.focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith(null);
    await expectNoAxeViolations(container);
  });

  it('marks stations below 95% of plan and accepts a custom tooltip', () => {
    const { container } = render(<GesMap stations={SVOD.stations} selected={null} onSelect={() => undefined} tip={(s) => `T:${s.short_name}`} />);
    expect(screen.getByRole('button', { name: 'T:Чарвак' })).toBeInTheDocument();
    expect(container.querySelector('.ges__dot.is-low')).toBeNull();
    render(<GesMap stations={MAP} selected={null} onSelect={() => undefined} />);
    expect(document.querySelectorAll('.ges__dot.is-low')).toHaveLength(1);
  });

  it('skips stations without coordinates; tooltip without production shows capacity only', () => {
    const noCoords = MAP.map((s) => (s.branch_id === 3 ? { ...s, lat: null, lon: null } : s));
    render(<GesMap stations={noCoords} selected={null} onSelect={() => undefined} />);
    expect(screen.getAllByRole('button')).toHaveLength(2);
    expect(productionTip({ ...MAP[1]!, production: null })).toBe('Чарвакская ГЭС: 666 МВт');
  });
});
```

`frontend/src/dash/map/ProductionBlock.test.tsx`:
```tsx
import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '../../test/render';
import { MAP } from '../../test/s3Fixtures';
import { ProductionBlock } from './ProductionBlock';

describe('ProductionBlock', () => {
  it('shows KIUM, generation vs plan and payment level with thresholds', () => {
    const chirchik = MAP[2]!;
    const { container } = renderWithProviders(<ProductionBlock capacity={chirchik.capacity_mw} production={chirchik.production} />);
    expect(screen.getByText('57,0%')).toBeInTheDocument();
    expect(screen.getByText('80% плана')).toHaveClass('neg');
    expect(screen.getByText('72,7%')).toHaveClass('neg');
    expect(container.querySelector('.gp-bar i.is-low')).not.toBeNull();
  });

  it('explains missing production data', () => {
    renderWithProviders(<ProductionBlock capacity={666} production={null} />);
    expect(screen.getByText('Нет данных о выработке за период.')).toBeInTheDocument();
  });
});
```

`frontend/src/sections/obzor/map/StationPanel.test.tsx` — ikkinchi testdagi qatorni:
```tsx
    expect(screen.getByText('Выработка, план и КИУМ появятся после подключения АСКУЭ (этап 3).')).toBeInTheDocument();
```
quyidagiga almashtiring (S1 `SVOD` stansiyalarida ishlab chiqarish yo'q):
```tsx
    expect(screen.getByText('Нет данных о выработке за период.')).toBeInTheDocument();
```

- [ ] **Step 6: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/dash/energy.test.ts src/dash/map src/sections/obzor/map`
Expected: FAIL — `Failed to resolve import "./energy"` / `"./ProductionBlock"`, `productionTip` eksport qilinmagan.

- [ ] **Step 7: Implementatsiya — energiya formati va grafik formati**

`frontend/src/dash/energy.ts`:
```ts
import { t } from '../i18n';
import { formatNumber } from '../i18n/format';

/** Prototip `kwh`: backend mln kVt·soat beradi; 1000 va undan ko'p — «млрд кВт·ч». */
export function kwhParts(mln: number, digits = 1): { value: string; unit: string } {
  if (Math.abs(mln) >= 1000) return { value: formatNumber(mln / 1000, digits), unit: t('unit.bnKwh') };
  return { value: formatNumber(mln, digits), unit: t('unit.mlnKwh') };
}

export function formatKwh(mln: number | null | undefined, digits = 1): string {
  if (mln === null || mln === undefined) return t('dash.noValue');
  const parts = kwhParts(mln, digits);
  return `${parts.value} ${parts.unit}`;
}

export function formatMw(mw: number | null | undefined, digits = 0): string {
  if (mw === null || mw === undefined) return t('dash.noValue');
  return `${formatNumber(mw, digits)} ${t('unit.mw')}`;
}
```

`frontend/src/dash/chart.tsx` — o'zgarishlar:
1. `Series` interfeysiga maydon qo'shing:
```ts
  /** Reja chizig'i kabi — uzuk-uzuk, nuqtasiz (prototip genCard). */
  dashed?: boolean;
```
2. `barConfig` imzosini almashtiring:
```ts
export function barConfig({
  labels,
  series,
  stacked = false,
  format = formatMoney,
}: {
  labels: Array<string | string[]>;
  series: Series[];
  stacked?: boolean;
  format?: (value: number, digits: number) => string;
}): AnyChartConfig {
```
3. `barConfig` ichida chiziq datasetini almashtiring:
```ts
          ? { type: 'line' as const, label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color, borderWidth: s.dashed ? 2 : 3, borderDash: s.dashed ? [6, 5] : [], pointRadius: s.dashed ? 0 : 3, tension: 0.25, order: 0 }
```
4. `barConfig` ichida `formatMoney(item.parsed.y, 2)` → `format(item.parsed.y, 2)` va `formatMoney(Number(value), 0)` → `format(Number(value), 0)`.
5. `ChartCanvasProps` ga qo'shing:
```ts
  format?: (value: number, digits: number) => string;
```
`ChartCanvas` destrukturizatsiyasiga `format = formatMoney` qo'shing va yashirin jadvaldagi `formatMoney(value, 2)` ni `format(value, 2)` ga almashtiring.

- [ ] **Step 8: Implementatsiya — umumiy xarita va ishlab chiqarish bloki**

`frontend/src/dash/map/GesMap.tsx` (ko'chirilgan faylni to'liq almashtiring — S1 xulqi saqlanadi, tooltip TZ 6 bo'yicha va tashqaridan beriladi):
```tsx
import { useId, type KeyboardEvent } from 'react';
import type { StationOut } from '../../api/types';
import { t } from '../../i18n';
import { formatNumber } from '../../i18n/format';
import { cx } from '../../ui/cx';
import { formatKwh } from '../energy';
import { formatPct } from '../money';
import { HIDDEN_LABELS, inInset, insetXY, LABEL_SIDE, mainXY, markerRadius, UZ_GEO } from './geo';
import './map.css';

/** Обзор (`StationOut`) va Производство (`MapStationOut`) xaritalari uchun umumiy maydonlar. */
export type MapPoint = Pick<StationOut, 'branch_id' | 'code' | 'name' | 'short_name' | 'kind' | 'capacity_mw' | 'lat' | 'lon' | 'production'>;

/** TZ 6: «Всплывающая подсказка: название, мощность, выработка, процент плана». */
export function productionTip(s: MapPoint): string {
  const capacity = formatNumber(s.capacity_mw ?? 0);
  const p = s.production;
  if (!p) return t('map.tipStation', { name: s.name, capacity });
  return t('map.tipProduction', { name: s.name, capacity, generation: formatKwh(p.generation), plan: formatPct(p.execution, 0) });
}

export interface GesMapProps<T extends MapPoint> {
  stations: readonly T[];
  selected: number | null;
  onSelect(id: number | null): void;
  tip?: (s: T) => string;
}

function lowPlan(s: MapPoint): boolean {
  const execution = s.production?.execution;
  return execution !== undefined && execution !== null && execution < 0.95;
}

function Marker({ s, text, x, y, r, on, onSelect }: { s: MapPoint; text: string; x: number; y: number; r: number; on: boolean; onSelect(id: number | null): void }) {
  const hq = s.kind === 'head';
  const side = LABEL_SIDE[s.code] ?? 'r';
  const off = r + 5;
  const lx = side === 'l' ? x - off : side === 'r' ? x + off : x;
  const ly = side === 't' ? y - off - 2 : side === 'b' ? y + off + 11 : y + 4.5;
  const anchor = side === 'l' ? 'end' : side === 'r' ? 'start' : 'middle';
  const toggle = () => onSelect(on ? null : s.branch_id);
  const onKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggle();
    }
  };
  return (
    <g className={cx('ges', on && 'is-on')} role="button" tabIndex={0} aria-pressed={on} aria-label={text} onClick={toggle} onKeyDown={onKeyDown}>
      <title>{text}</title>
      {on ? <circle className="ges__sel" cx={x} cy={y} r={r + 6} /> : null}
      <circle className="ges__ring" cx={x} cy={y} r={r + 3} />
      {hq ? (
        <rect className="ges__dot ges__dot--hq" x={x - r} y={y - r} width={2 * r} height={2 * r} rx={3} />
      ) : (
        <circle className={cx('ges__dot', lowPlan(s) && 'is-low')} cx={x} cy={y} r={r} />
      )}
      <text x={lx} y={ly} textAnchor={anchor}>
        {s.short_name}
      </text>
    </g>
  );
}

/** TZ 6 «Карта ГЭС»: stansiyalar koordinatalar bo'yicha, Toshkent viloyati — alohida ramkada. */
export function GesMap<T extends MapPoint>({ stations, selected, onSelect, tip }: GesMapProps<T>) {
  const clipId = `ins${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const [ix, iy, iw, ih] = UZ_GEO.inset;
  const [bx0, by0] = mainXY(68.95, 41.75);
  const [bx1, by1] = mainXY(70.15, 40.95);
  const placed = stations.filter((s) => s.lat !== null && s.lon !== null);
  const anyLow = placed.some(lowPlan);
  const tooltip = (s: T): string => (tip ? tip(s) : productionTip(s));
  return (
    <div className="mapwrap">
      <svg viewBox={`0 0 ${UZ_GEO.W} ${UZ_GEO.H}`} role="group" aria-label={t('obzor.map.aria')}>
        <defs>
          <clipPath id={clipId}>
            <rect x={ix} y={iy} width={iw} height={ih} rx={8} />
          </clipPath>
        </defs>
        {UZ_GEO.reg.map((r) => (
          <path key={r.n} className={cx('reg', r.city && 'reg--city')} d={r.d} />
        ))}
        {UZ_GEO.reg
          .filter((r) => r.x !== undefined && !HIDDEN_LABELS.includes(r.n))
          .map((r) => (
            <text key={`l-${r.n}`} className="regl" x={r.x} y={r.y}>
              {r.n}
            </text>
          ))}
        <rect className="map__box" x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} />
        <path className="map__box" d={`M${bx1},${by0} L${ix},${iy + ih}`} />
        {placed
          .filter((s) => inInset(s.lon ?? 0, s.lat ?? 0))
          .map((s) => {
            const [x, y] = mainXY(s.lon ?? 0, s.lat ?? 0);
            return <circle key={`c-${s.branch_id}`} className="map__cluster" cx={x} cy={y} r={2.6} />;
          })}
        <rect className="map__inset" x={ix} y={iy} width={iw} height={ih} rx={8} />
        <g clipPath={`url(#${clipId})`}>
          {UZ_GEO.ins.map((d, i) => (
            <path key={`i-${i}`} className={cx('reg', UZ_GEO.reg[i]?.city && 'reg--city')} d={d} />
          ))}
        </g>
        <text className="regl regl--start" x={ix + 8} y={iy + ih - 8}>
          {t('obzor.map.inset')}
        </text>
        {placed.map((s) => {
          const lon = s.lon ?? 0;
          const lat = s.lat ?? 0;
          const inset = inInset(lon, lat);
          const [x, y] = inset ? insetXY(lon, lat) : mainXY(lon, lat);
          return (
            <Marker
              key={s.branch_id}
              s={s}
              text={tooltip(s)}
              x={x}
              y={y}
              r={markerRadius(s.capacity_mw, inset, s.kind === 'head')}
              on={selected === s.branch_id}
              onSelect={onSelect}
            />
          );
        })}
      </svg>
      <div className="maplegend">
        <span>
          <i className="maplegend__ok" />
          {t('obzor.map.legendOk')}
        </span>
        {anyLow ? (
          <span>
            <i className="maplegend__low" />
            {t('obzor.map.legendLow')}
          </span>
        ) : null}
        <span>
          <i className="maplegend__hq" />
          {t('obzor.map.legendHq')}
        </span>
      </div>
    </div>
  );
}
```

`frontend/src/dash/map/ProductionBlock.tsx`:
```tsx
import type { StationProductionOut } from '../../api/types';
import { t } from '../../i18n';
import { formatNumber } from '../../i18n/format';
import { cx } from '../../ui/cx';
import { formatKwh } from '../energy';
import { formula } from '../formulas';
import { formatPct } from '../money';

const LOW_PLAN = 0.95; // TZ 6: qizil — reja bajarilishi 95% dan past
const LOW_PAYMENT = 0.85; // TZ 4 qoidasi «Уровень оплаты за энергию < 85%»

/** Prototip `gesPanel` ishlab chiqarish qismi: quvvat, КИУМ, ishlab chiqarish va reja, to'lov darajasi. */
export function ProductionBlock({ capacity, production }: { capacity: number | null; production: StationProductionOut | null }) {
  const execution = production?.execution ?? null;
  const low = execution !== null && execution < LOW_PLAN;
  const payment = production?.payment_level ?? null;
  return (
    <>
      <div className="gp-grid">
        <div title={formula('capacity')}>
          <span>{t('map.capacity')}</span>
          <b>
            {formatNumber(capacity ?? 0)}
            <small>{t('map.mw')}</small>
          </b>
        </div>
        <div title={formula('kium')}>
          <span>{t('map.kium')}</span>
          <b>{formatPct(production?.kium ?? null, 1)}</b>
        </div>
      </div>
      {production ? (
        <>
          <div className="gp-line" title={formula('genPlan')}>
            <span>{t('map.generation')}</span>
            <b>
              {formatKwh(production.generation)} <span className={low ? 'neg' : 'muted'}>{t('map.ofPlan', { pct: formatPct(execution, 0) })}</span>
            </b>
          </div>
          <div className="gp-bar" aria-hidden="true">
            <i className={cx(low && 'is-low')} style={{ width: `${Math.min(100, Math.max(0, (execution ?? 0) * 100))}%` }} />
          </div>
          <ul className="gp-rows">
            <li>
              <span>{t('map.plan')}</span>
              <b>{formatKwh(production.plan)}</b>
            </li>
            <li title={formula('paymentLevel')}>
              <span>{t('map.paymentLevel')}</span>
              <b className={payment !== null && payment < LOW_PAYMENT ? 'neg' : undefined}>{formatPct(payment, 1)}</b>
            </li>
          </ul>
        </>
      ) : (
        <p className="note">{t('map.noProduction')}</p>
      )}
    </>
  );
}
```

`frontend/src/dash/map/map.css` — oxiriga qo'shing:
```css
.gp-line { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
.gp-bar { height: 0.45rem; border-radius: 0.3rem; background: var(--soft); overflow: hidden; }
.gp-bar i { display: block; height: 100%; background: var(--brand2); }
.gp-bar i.is-low { background: var(--neg); }
```

`frontend/src/sections/obzor/map/StationPanel.tsx` — importlarda `import './map.css';` ni `import '../../../dash/map/map.css';` ga almashtiring, qo'shing:
```tsx
import { ProductionBlock } from '../../../dash/map/ProductionBlock';
```
va stansiya tarmog'idagi (`hq` bo'lmagan) blokni:
```tsx
        <>
          <div className="gp-grid">
            <div>
              <span>{t('obzor.station.capacity')}</span>
              <b>
                {formatNumber(station.capacity_mw ?? 0)}
                <small>{t('obzor.station.mw')}</small>
              </b>
            </div>
          </div>
          <p className="note">{t('obzor.station.noProduction')}</p>
        </>
```
quyidagiga almashtiring:
```tsx
        <ProductionBlock capacity={station.capacity_mw} production={station.production ?? null} />
```
(`formatNumber` importi boshqa joyda ishlatilmasa — olib tashlang, eslint `no-unused-vars`.)

`frontend/src/sections/obzor/svod.tsx` — importni almashtiring:
```tsx
import { GesMap } from './map/GesMap';
```
→
```tsx
import { GesMap, productionTip } from '../../dash/map/GesMap';
import { formatMoney } from '../../dash/money';
```
va `<GesMap … />` chaqiruvini:
```tsx
                <GesMap
                  stations={data.stations}
                  selected={mapSel ?? filters.br}
                  onSelect={setMapSel}
                  tip={(s) => (s.kind === 'head' ? t('obzor.map.tipHq', { name: s.name, balance: formatMoney(s.closing) }) : productionTip(s))}
                />
```

- [ ] **Step 9: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/dash src/sections/obzor` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: barcha testlar passed (S1 `obzor` sahifa testlari o'zgarishsiz); tsc va eslint xatosiz; `grep -rn "sections/obzor/map/GesMap" frontend/src` — bo'sh.

- [ ] **Step 10: Commit**

```bash
git add frontend
git commit -m "feat(frontend): S3 tiplari va matnlari, energiya formati, grafik formati; ГЭС xaritasi src/dash/map ga, TZ tooltip va ishlab chiqarish bloki

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 16: Frontend — «Производство»: Сводка (xarita, «Текущая мощность»), Выработка по станциям, Реализация

**Files:**
- Create: `frontend/src/sections/proizvodstvo/parts/ProdKpis.tsx`, `parts/GenMonthsCard.tsx`, `parts/StationsRank.tsx`, `parts/StationsTable.tsx`, `parts/SalesMonthsCard.tsx`, `parts/PaymentRank.tsx`, `parts/ProductionPanel.tsx`, `parts/PowerCard.tsx`, `parts/NoStations.tsx`, `frontend/src/sections/proizvodstvo/svod.tsx`, `stancii.tsx`, `realiz.tsx`
- Test: `frontend/src/sections/proizvodstvo/proizvodstvo.test.tsx`

**Interfaces:**
- Consumes: `useSection`, `SectionData`, `SectionPageProps`, `toggleBranch`, `buildHash`, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Column`, `Badge`, `Button`, `EmptyState`, `cx`, `Rank`, `ChartCanvas`, `barConfig`, `COLORS`, `ChartHandle`, `CardExport`, `ExportContext`, `NoData`, `formula`, `formatMoney`, `formatPct`, `formatDelta`, `yoyRatio`, `monthShort`, `formatNumber`, `formatDateTime`, `kwhParts`, `formatKwh`, `formatMw`, `GesMap`, `ProductionBlock`, fixture'lar (`PROIZV_*`, `POWER*`, `MAP`), `mockApi`, `json`, `renderWithProviders`, `expectNoAxeViolations`, `ME_ADMIN`.
- Produces:
  - Kartalar: `ProdKpis({ kpis, period })`, `GenMonthsCard({ months, ctx, className? })`, `StationsRank({ stations, filters, onBranch, className? })`, `StationsTable({ stations, kpis, ctx, filters, onBranch, className? })`, `SalesMonthsCard({ months, ctx, className? })`, `PaymentRank({ stations, filters, onBranch, className? })`, `ProductionPanel({ stations: MapStationOut[]; selected; onSelect; filters; onBranch })`, `PowerCard({ filters, className? })` (o'z so'rovi `/proizvodstvo/moshchnost`), `NoStations()`.
  - Sahifalar `#proizvodstvo/svod`, `#proizvodstvo/stancii`, `#proizvodstvo/realiz` (3-reja reyestri glob orqali ulaydi).

UI prototip `proizv` bo'limi va TZ 5 bo'yicha; «Текущая мощность» kartasi prototipda yo'q — Refero'dagi monitoring vidjetlari (OneSoil: «последнее обновление» sarlavhasi va metrika kartalari; Enode: holat kartalari) asosida prototip primitivlaridan tuzilgan: katta raqam (МВт) + «по данным на …», eskirganlikda `Badge tone="neg"`, agregatlar holati bir qatorda, stansiyalar `Rank`da — yangi vizual tokenlar yo'q.

- [ ] **Step 1: Testlarni yozish**

`frontend/src/sections/proizvodstvo/proizvodstvo.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { POWER, POWER_NONE, POWER_STALE, PROIZV_HQ, PROIZV_REALIZ, PROIZV_STANCII, PROIZV_SVOD } from '../../test/s3Fixtures';
import { PowerCard } from './parts/PowerCard';
import ProizvodstvoRealiz from './realiz';
import ProizvodstvoStancii from './stancii';
import ProizvodstvoSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Производство', () => {
  it('Сводка: KPIs, months chart, station rank, map with panel and current power', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /proizvodstvo/svod': json(PROIZV_SVOD), 'GET /proizvodstvo/moshchnost': json(POWER), 'GET /auth/me': json(ME_ADMIN) });
    const { container, user } = renderWithProviders(<ProizvodstvoSvod section="proizvodstvo" page="svod" filters={filters} onBranch={onBranch} />);
    expect(await screen.findByText('Выработка электроэнергии')).toBeInTheDocument();
    expect(screen.getByText('96,0%')).toBeInTheDocument();
    expect(screen.getByText('52,0%')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Выработка по месяцам' })).toBeInTheDocument();
    const rank = screen.getByRole('list', { name: 'Выработка по станциям' });
    await user.click(within(rank).getByText('Чарвакская ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(2);
    expect(screen.getByRole('link', { name: 'Все станции' }).getAttribute('href')).toContain('proizvodstvo/stancii');
    expect(screen.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeInTheDocument();
    expect(await screen.findByText('412,5 МВт')).toBeInTheDocument();
    expect(screen.getByText('по данным на 25.09.2026 10:40')).toBeInTheDocument();
    expect(screen.getByText('Агрегаты: в работе 5, в резерве 1, в ремонте 1')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('Сводка: selecting a station on the map shows its production and opens its data', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /proizvodstvo/svod': json(PROIZV_SVOD), 'GET /proizvodstvo/moshchnost': json(POWER), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ProizvodstvoSvod section="proizvodstvo" page="svod" filters={filters} onBranch={onBranch} />);
    await user.click(await screen.findByRole('button', { name: /Каскад Чирчикских ГЭС: 190 МВт, выработка 80,0 млн кВт·ч, 80% плана/ }));
    const panel = screen.getByRole('heading', { name: 'Каскад Чирчикских ГЭС' }).closest('.gp');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getByText('80% плана')).toHaveClass('neg');
    await user.click(screen.getByRole('button', { name: 'Открыть данные станции' }));
    expect(onBranch).toHaveBeenCalledWith(3);
  });

  it('HQ selected shows the no-stations message instead of cards', async () => {
    mockApi({ 'GET /proizvodstvo/svod': json({ ...PROIZV_SVOD, has_stations: false, stations: [] }), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ProizvodstvoSvod section="proizvodstvo" page="svod" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText(/Головная организация не эксплуатирует станции/)).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Выработка по месяцам' })).toBeNull();
    mockApi({ 'GET /proizvodstvo/stancii': json(PROIZV_HQ), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ProizvodstvoStancii section="proizvodstvo" page="stancii" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(/Головная организация не эксплуатирует станции/)).toHaveLength(2);
  });

  it('Выработка по станциям: table with totals, low execution in red, row click selects the branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /proizvodstvo/stancii': json(PROIZV_STANCII), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<ProizvodstvoStancii section="proizvodstvo" page="stancii" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Станции' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 3 + 1);
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    expect(within(table).getByText('80%').closest('.exec')).toHaveClass('neg');
    await user.click(within(table).getByText('Каскад Чирчикских ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(3);
    expect(await screen.findByRole('button', { name: 'Выгрузить таблицу «Станции» в CSV' })).toBeInTheDocument();
  });

  it('Реализация: sales chart and stations by payment level', async () => {
    mockApi({ 'GET /proizvodstvo/realiz': json(PROIZV_REALIZ), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<ProizvodstvoRealiz section="proizvodstvo" page="realiz" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByRole('img', { name: 'Реализация электроэнергии по месяцам' })).toBeInTheDocument();
    const rank = screen.getByRole('list', { name: 'Уровень оплаты по станциям' });
    const first = within(rank).getAllByRole('listitem')[0];
    expect(first).toHaveTextContent('Каскад Чирчикских ГЭС');
    expect(first).toHaveTextContent('73% оплаты');
  });

  it('PowerCard shows stale and missing source', async () => {
    mockApi({ 'GET /proizvodstvo/moshchnost': json(POWER_STALE), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<PowerCard filters={filters} />);
    expect(await screen.findByText('Данные устарели')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /proizvodstvo/moshchnost': json(POWER_NONE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<PowerCard filters={filters} />);
    expect(await screen.findByText(/Источник данных не подключён: онлайн-мониторинг ГЭС/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/proizvodstvo`
Expected: FAIL — `Failed to resolve import "./parts/PowerCard"`.

- [ ] **Step 3: Implementatsiya — KPI va grafiklar**

`frontend/src/sections/proizvodstvo/parts/ProdKpis.tsx`:
```tsx
import type { ProdKpisOut, ReportPeriodOut } from '../../../api/types';
import { formatKwh, kwhParts } from '../../../dash/energy';
import { formula } from '../../../dash/formulas';
import { formatDelta, formatMoney, formatPct, yoyRatio } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

const LOW_PLAN = 0.95;
const LOW_PAYMENT = 0.85;

/** Prototip `kpisProd`: выработка (к прошлому году), план, мощность, КИУМ, отпуск, уровень оплаты. */
export function ProdKpis({ kpis, period }: { kpis: ProdKpisOut; period: ReportPeriodOut }) {
  const generation = kwhParts(kpis.generation);
  const supply = kwhParts(kpis.supply);
  const ratio = yoyRatio(kpis.generation, kpis.generation_prev);
  const year = Number(period.date_from.slice(0, 4)) - 1;
  const yoy = ratio === null ? null : t('dash.yoy', { year, delta: formatDelta(ratio) });
  return (
    <KpiGrid>
      <KpiTile
        icon="bolt"
        label={t('proizv.kpi.generation')}
        value={generation.value}
        unit={generation.unit}
        delta={yoy ? `${t('proizv.kpi.period')} · ${yoy}` : t('proizv.kpi.period')}
        deltaDown={ratio !== null && ratio < 0}
        hint={`${formula('generation')}. ${formula('yoy')}`}
      />
      <KpiTile
        icon="pct"
        label={t('proizv.kpi.execution')}
        value={formatPct(kpis.execution, 1)}
        negative={kpis.execution !== null && kpis.execution < LOW_PLAN}
        delta={t('proizv.kpi.executionNote', { plan: formatKwh(kpis.plan) })}
        hint={formula('genPlan')}
      />
      <KpiTile
        icon="factory"
        label={t('proizv.kpi.capacity')}
        value={formatNumber(kpis.capacity_mw ?? 0)}
        unit={t('unit.mw')}
        delta={t('proizv.kpi.capacityNote', { count: kpis.stations })}
        hint={formula('capacity')}
      />
      <KpiTile icon="clock" label={t('proizv.kpi.kium')} value={formatPct(kpis.kium, 1)} delta={t('proizv.kpi.kiumNote')} hint={formula('kium')} />
      <KpiTile
        icon="plug"
        label={t('proizv.kpi.supply')}
        value={supply.value}
        unit={supply.unit}
        delta={t('proizv.kpi.supplyNote', { share: formatPct(kpis.own_share, 1) })}
        hint={`${formula('supply')}. ${formula('ownNeeds')}`}
      />
      <KpiTile
        icon="coins"
        label={t('proizv.kpi.payment')}
        value={formatPct(kpis.payment_level, 1)}
        negative={kpis.payment_level !== null && kpis.payment_level < LOW_PAYMENT}
        delta={t('proizv.kpi.paymentNote', { paid: formatMoney(kpis.paid), accrued: formatMoney(kpis.accrued) })}
        hint={formula('paymentLevel')}
      />
    </KpiGrid>
  );
}
```

`frontend/src/sections/proizvodstvo/parts/GenMonthsCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { GenMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import { formatKwh } from '../../../dash/energy';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `genCard`: факт — ustun, план — uzuk-uzuk chiziq; CSV'da o'tgan yil ham. */
export function GenMonthsCard({ months, ctx, className }: { months: GenMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('proizv.months.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const fact = COLORS.in();
  const plan = COLORS.bal();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('proizv.months.fact'), data: months.map((m) => m.generation), color: fact },
          { label: t('proizv.months.plan'), data: months.map((m) => m.plan), color: plan, type: 'line', dashed: true },
        ],
        format: formatKwh,
      }),
    [months, fact, plan],
  );
  const table = {
    headers: [t('proizv.months.month'), t('proizv.months.fact'), t('proizv.months.plan'), t('proizv.months.prev')],
    rows: months.map((m) => [monthShort(m.month_id), m.generation, m.plan, m.generation_prev]),
  };
  return (
    <Card className={className} title={title} sub={t('proizv.months.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('genPlan')}>
        <span>
          <i style={{ background: fact }} />
          {t('proizv.months.fact')}
        </span>
        <span>
          <i className="dash" style={{ background: plan }} />
          {t('proizv.months.plan')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} format={formatKwh} />
    </Card>
  );
}
```

`frontend/src/sections/proizvodstvo/parts/SalesMonthsCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { SalesMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `salesCard`: начислено за отпущенную энергию и оплачено покупателем по месяцам. */
export function SalesMonthsCard({ months, ctx, className }: { months: SalesMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('proizv.sales.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const accrued = COLORS.out();
  const paid = COLORS.in();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('proizv.sales.accrued'), data: months.map((m) => m.accrued), color: accrued },
          { label: t('proizv.sales.paid'), data: months.map((m) => m.paid), color: paid },
        ],
      }),
    [months, accrued, paid],
  );
  const table = {
    headers: [t('proizv.months.month'), t('proizv.sales.accrued'), t('proizv.sales.paid')],
    rows: months.map((m) => [monthShort(m.month_id), m.accrued, m.paid]),
  };
  return (
    <Card className={className} title={title} sub={t('proizv.sales.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('paymentLevel')}>
        <span>
          <i style={{ background: accrued }} />
          {t('proizv.sales.accrued')}
        </span>
        <span>
          <i style={{ background: paid }} />
          {t('proizv.sales.paid')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
```

- [ ] **Step 4: Implementatsiya — stansiyalar ro'yxatlari va jadvali**

`frontend/src/sections/proizvodstvo/parts/StationsRank.tsx`:
```tsx
import type { StationGenOut } from '../../../api/types';
import { formatKwh } from '../../../dash/energy';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { buildHash } from '../../../router/hash';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

/** Prototip `stItems`: выработка по станциям, черта — план, < 95% — qizil; bosish — filial tanlash. */
export function StationsRank({ stations, filters, onBranch, className }: { stations: StationGenOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('proizv.rank.title');
  return (
    <Card className={className} title={title} sub={t('proizv.rank.sub')}>
      <Rank
        label={title}
        items={stations.map((s) => ({
          id: s.branch_id,
          name: s.name,
          value: s.generation,
          mark: s.plan,
          note: t('proizv.rank.ofPlan', { pct: formatPct(s.execution, 0) }),
          negative: s.execution !== null && s.execution < 0.95,
        }))}
        format={(v) => formatKwh(v)}
        onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
        activeId={filters.br}
      />
      {filters.br === null ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'proizvodstvo', page: 'stancii', br: null, per: filters.per })}>
          {t('proizv.rank.all')}
        </a>
      ) : null}
    </Card>
  );
}
```

`frontend/src/sections/proizvodstvo/parts/PaymentRank.tsx`:
```tsx
import type { StationGenOut } from '../../../api/types';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { toggleBranch } from '../../useSection';

/** Prototip «Уровень оплаты по станциям»: tartib serverdan (eng pasti birinchi), < 85% — qizil. */
export function PaymentRank({ stations, filters, onBranch, className }: { stations: StationGenOut[]; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('proizv.pay.title');
  return (
    <Card className={className} title={title} sub={t('proizv.pay.sub')}>
      <Rank
        label={title}
        items={stations.map((s) => ({
          id: s.branch_id,
          name: s.name,
          value: s.paid,
          note: t('proizv.pay.note', { pct: formatPct(s.payment_level, 0) }),
          negative: s.payment_level !== null && s.payment_level < 0.85,
        }))}
        onSelect={(id) => toggleBranch(filters, Number(id), onBranch)}
        activeId={filters.br}
      />
    </Card>
  );
}
```

`frontend/src/sections/proizvodstvo/parts/StationsTable.tsx`:
```tsx
import type { ProdKpisOut, StationGenOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { formatKwh } from '../../../dash/energy';
import type { ExportContext } from '../../../dash/exportLog';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

function Exec({ value }: { value: number | null }) {
  const low = value !== null && value < 0.95;
  return (
    <span className={cx('exec', low && 'neg')}>
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

export interface StationsTableProps {
  stations: StationGenOut[];
  kpis: ProdKpisOut;
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** Prototip `stTable` (TZ 5 «таблица станций с КИУМ»): quvvat, reja, fakt, bajarilish, КИУМ, отпуск. */
export function StationsTable({ stations, kpis, ctx, filters, onBranch, className }: StationsTableProps) {
  const title = t('proizv.table.title');
  const headers = [
    t('proizv.table.station'), t('proizv.table.capacity'), t('proizv.table.plan'), t('proizv.table.fact'),
    t('proizv.table.execution'), t('proizv.table.kium'), t('proizv.table.supply'),
  ];
  const columns: Column<StationGenOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (s) => s.name, sortValue: (s) => s.name, wrap: true },
    { key: 'capacity', header: headers[1] ?? '', cell: (s) => formatNumber(s.capacity_mw ?? 0), sortValue: (s) => s.capacity_mw, align: 'right' },
    { key: 'plan', header: headers[2] ?? '', cell: (s) => formatKwh(s.plan), sortValue: (s) => s.plan, align: 'right' },
    { key: 'fact', header: headers[3] ?? '', cell: (s) => <b>{formatKwh(s.generation)}</b>, sortValue: (s) => s.generation, align: 'right' },
    { key: 'execution', header: headers[4] ?? '', cell: (s) => <Exec value={s.execution} />, sortValue: (s) => s.execution, align: 'right' },
    { key: 'kium', header: headers[5] ?? '', cell: (s) => formatPct(s.kium, 1), sortValue: (s) => s.kium, align: 'right' },
    { key: 'supply', header: headers[6] ?? '', cell: (s) => formatKwh(s.supply), sortValue: (s) => s.supply, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('proizv.table.sub')}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers,
            rows: stations.map((s) => [s.name, s.capacity_mw, s.plan, s.generation, s.execution === null ? null : Math.round(s.execution * 1000) / 10, s.kium === null ? null : Math.round(s.kium * 1000) / 10, s.supply]),
          })}
        />
      }
    >
      <Table
        caption={title}
        columns={columns}
        rows={stations}
        rowKey={(s) => s.branch_id}
        onRowClick={(s) => toggleBranch(filters, s.branch_id, onBranch)}
        free
        footer={
          <tr>
            <td>{t('proizv.table.total')}</td>
            <td>{formatNumber(kpis.capacity_mw ?? 0)}</td>
            <td>{formatKwh(kpis.plan)}</td>
            <td>{formatKwh(kpis.generation)}</td>
            <td>{formatPct(kpis.execution, 0)}</td>
            <td>{formatPct(kpis.kium, 1)}</td>
            <td>{formatKwh(kpis.supply)}</td>
          </tr>
        }
      />
    </Card>
  );
}
```

- [ ] **Step 5: Implementatsiya — xarita paneli, «Текущая мощность», bo'sh holat**

`frontend/src/sections/proizvodstvo/parts/ProductionPanel.tsx`:
```tsx
import type { MapStationOut } from '../../../api/types';
import { formatKwh } from '../../../dash/energy';
import { ProductionBlock } from '../../../dash/map/ProductionBlock';
import '../../../dash/map/map.css';
import { formatPct } from '../../../dash/money';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Button } from '../../../ui/Button';

export interface ProductionPanelProps {
  stations: readonly MapStationOut[];
  selected: number | null;
  onSelect(id: number | null): void;
  filters: FilterState;
  onBranch(br: number | null): void;
}

/** Prototip `gesPanel` (ishlab chiqarish qismi): tanlanmagan — stansiyalar ro'yxati, tanlangan — ko'rsatkichlar. */
export function ProductionPanel({ stations, selected, onSelect, filters, onBranch }: ProductionPanelProps) {
  const station = stations.find((s) => s.branch_id === selected);
  if (!station) {
    const list = stations
      .filter((s) => s.kind !== 'head' && s.production !== null)
      .sort((a, b) => (b.production?.generation ?? 0) - (a.production?.generation ?? 0));
    return (
      <div className="gp">
        <div className="gp-h">
          <div>
            <h2>{t('proizv.panel.all')}</h2>
            <p className="note">{t('proizv.panel.allNote', { count: list.length })}</p>
          </div>
        </div>
        <Rank
          label={t('proizv.panel.all')}
          items={list.map((s) => ({
            id: s.branch_id,
            name: s.name,
            value: s.production?.generation ?? 0,
            note: t('proizv.rank.ofPlan', { pct: formatPct(s.production?.execution ?? null, 0) }),
            negative: (s.production?.execution ?? 1) < 0.95,
          }))}
          format={(v) => formatKwh(v)}
          onSelect={(id) => onSelect(Number(id))}
        />
      </div>
    );
  }
  const hq = station.kind === 'head';
  return (
    <div className="gp">
      <div className="gp-h">
        <h2>{station.name}</h2>
        <button type="button" className="gp-x" onClick={() => onSelect(null)}>
          {t('proizv.panel.all')}
        </button>
      </div>
      {hq ? <p className="note">{t('proizv.panel.hq')}</p> : <ProductionBlock capacity={station.capacity_mw} production={station.production} />}
      {hq || filters.br === station.branch_id ? null : (
        <Button variant="secondary" onClick={() => onBranch(station.branch_id)}>
          {t('proizv.panel.open')}
        </Button>
      )}
    </div>
  );
}
```

`frontend/src/sections/proizvodstvo/parts/PowerCard.tsx`:
```tsx
import type { PowerOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { formatMw } from '../../../dash/energy';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatDateTime } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { SectionData } from '../../SectionData';
import { useSection } from '../../useSection';

function PowerBody({ data }: { data: PowerOut }) {
  return (
    <>
      <div className="bigline" title={formula('currentPower')}>
        <b>{formatMw(data.total_mw, 1)}</b>
        <span>{t('proizv.power.asOf', { time: data.snap_at ? formatDateTime(data.snap_at) : '—' })}</span>
      </div>
      {data.stale ? <Badge tone="neg">{t('proizv.power.stale')}</Badge> : null}
      <p className="note">{t('proizv.power.units', { working: data.units_working, reserve: data.units_reserve, repair: data.units_repair })}</p>
      <Rank
        label={t('proizv.power.stations')}
        items={data.stations.map((s) => ({ id: s.station, name: s.station_name, value: s.power_mw, note: s.branch_name }))}
        format={(v) => formatMw(v, 1)}
      />
    </>
  );
}

/** «Текущая мощность» (S3 spec 3.2): онлайн-мониторинг, не суточная выработка; свой запрос. */
export function PowerCard({ filters, className }: { filters: FilterState; className?: string }) {
  const query = useSection<PowerOut>('/proizvodstvo/moshchnost', filters);
  return (
    <Card className={className} title={t('proizv.power.title')} sub={t('proizv.power.sub')}>
      <SectionData query={query}>{(data) => (data.has_source ? <PowerBody data={data} /> : <NoData kind="source" source={t('proizv.power.source')} />)}</SectionData>
    </Card>
  );
}
```

`frontend/src/sections/proizvodstvo/parts/NoStations.tsx`:
```tsx
import { t } from '../../../i18n';
import { EmptyState } from '../../../ui/EmptyState';

/** TZ 5: «При выборе головной организации выводится сообщение, что станций у неё нет». */
export function NoStations() {
  return <EmptyState icon="factory" title={t('proizv.none.title')} text={t('proizv.none.text')} />;
}
```

- [ ] **Step 6: Implementatsiya — sahifalar**

`frontend/src/sections/proizvodstvo/svod.tsx`:
```tsx
import { useState } from 'react';
import type { ProizvSvodOut } from '../../api/types';
import { NoData } from '../../dash/DataState';
import { GesMap } from '../../dash/map/GesMap';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { GenMonthsCard } from './parts/GenMonthsCard';
import { NoStations } from './parts/NoStations';
import { PowerCard } from './parts/PowerCard';
import { ProdKpis } from './parts/ProdKpis';
import { ProductionPanel } from './parts/ProductionPanel';
import { StationsRank } from './parts/StationsRank';

export default function ProizvodstvoSvod({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ProizvSvodOut>('/proizvodstvo/svod', filters);
  const [mapSel, setMapSel] = useState<number | null>(null);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_stations ? (
          <>
            <ProdKpis kpis={data.kpis} period={data.period} />
            {data.kpis.has_data ? null : (
              <Card>
                <NoData kind="period" />
              </Card>
            )}
            <div className="grid">
              <GenMonthsCard className="c8" months={data.months} ctx={ctx} />
              <StationsRank className="c4" stations={data.stations} filters={filters} onBranch={onBranch} />
            </div>
            <div className="grid">
              <Card className="c8 wide" title={t('proizv.map.title')} sub={t('proizv.map.sub')}>
                <GesMap stations={data.map} selected={mapSel ?? filters.br} onSelect={setMapSel} />
              </Card>
              <Card className="c4 wide">
                <ProductionPanel stations={data.map} selected={mapSel ?? filters.br} onSelect={setMapSel} filters={filters} onBranch={onBranch} />
              </Card>
              <PowerCard className="c12" filters={filters} />
            </div>
          </>
        ) : (
          <NoStations />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/proizvodstvo/stancii.tsx`:
```tsx
import type { ProizvStanciiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NoStations } from './parts/NoStations';
import { ProdKpis } from './parts/ProdKpis';
import { StationsTable } from './parts/StationsTable';

export default function ProizvodstvoStancii({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ProizvStanciiOut>('/proizvodstvo/stancii', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_stations ? (
          <>
            <ProdKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <StationsTable className="c12" stations={data.stations} kpis={data.kpis} ctx={ctx} filters={filters} onBranch={onBranch} />
            </div>
          </>
        ) : (
          <NoStations />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/proizvodstvo/realiz.tsx`:
```tsx
import type { ProizvRealizOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NoStations } from './parts/NoStations';
import { PaymentRank } from './parts/PaymentRank';
import { ProdKpis } from './parts/ProdKpis';
import { SalesMonthsCard } from './parts/SalesMonthsCard';

export default function ProizvodstvoRealiz({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<ProizvRealizOut>('/proizvodstvo/realiz', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_stations ? (
          <>
            <ProdKpis kpis={data.kpis} period={data.period} />
            <div className="grid">
              <SalesMonthsCard className="c8" months={data.months} ctx={ctx} />
              <PaymentRank className="c4" stations={data.stations} filters={filters} onBranch={onBranch} />
            </div>
          </>
        ) : (
          <NoStations />
        )
      }
    </SectionData>
  );
}
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/proizvodstvo` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: 6 test passed; tsc va eslint xatosiz.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Производство» — Сводка (xarita, текущая мощность), Выработка по станциям, Реализация

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 17: Frontend — «Склад»: Сводка, Остатки по складам, Минимальный запас, Неликвиды

**Files:**
- Create: `frontend/src/sections/sklad/parts/StockKpis.tsx`, `parts/StockFlowCard.tsx`, `parts/CategoriesCard.tsx`, `parts/BelowMinCard.tsx`, `parts/StockBranchesTable.tsx`, `parts/AgesCard.tsx`, `parts/IlliquidCard.tsx`, `frontend/src/sections/sklad/svod.tsx`, `ostatki.tsx`, `minimum.tsx`, `nelikvid.tsx`
- Test: `frontend/src/sections/sklad/sklad.test.tsx`

**Interfaces:**
- Consumes: `useSection`, `SectionData`, `SectionPageProps`, `toggleBranch`, `buildHash`, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Column`, `Badge`, `cx`, `Rank`, `ChartCanvas`, `barConfig`, `COLORS`, `ChartHandle`, `CardExport`, `ExportContext`, `NoData`, `formula`, `formatMoney`, `moneyParts`, `formatPct`, `monthShort`, `formatNumber`, `formatDate`, fixture'lar (`SKLAD_*`, `STOCK_*`, `BELOW`, `IDLE`, `AGES`), `mockApi`, `json`, `renderWithProviders`, `expectNoAxeViolations`, `ME_ADMIN`.
- Produces:
  - Kartalar: `StockKpis({ kpis })`, `StockFlowCard({ months, ctx, className? })`, `CategoriesCard({ categories, asOf, className? })`, `BelowMinCard({ rows, hasMinimum, title, sub, ctx, more?, className? })`, `StockBranchesTable({ rows, ctx, filters, onBranch, className? })`, `AgesCard({ ages, hasAge, className? })`, `IlliquidCard({ rows, hasAge, ctx, className? })`. Minimum/yosh ma'lumoti yo'q — `NoData kind="source"` (kartaning sarlavhasi saqlanadi).
  - Sahifalar `#sklad/svod`, `#sklad/ostatki`, `#sklad/minimum`, `#sklad/nelikvid`.

- [ ] **Step 1: Testlarni yozish**

`frontend/src/sections/sklad/sklad.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { SKLAD_MINIMUM, SKLAD_NELIKVID, SKLAD_NO_AGE, SKLAD_NO_MIN, SKLAD_OSTATKI, SKLAD_SVOD } from '../../test/s3Fixtures';
import SkladMinimum from './minimum';
import SkladNelikvid from './nelikvid';
import SkladOstatki from './ostatki';
import SkladSvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Склад', () => {
  it('Сводка: KPIs, movement chart, categories and top deficit positions', async () => {
    mockApi({ 'GET /sklad/svod': json(SKLAD_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<SkladSvod section="sklad" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Стоимость запасов')).toBeInTheDocument();
    expect(screen.getByText('27')).toBeInTheDocument();
    expect(screen.getByText('66,7%')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Движение запасов по месяцам' })).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Запасы по категориям' })).getByText('Запасные части')).toBeInTheDocument();
    const below = screen.getByRole('table', { name: 'Ниже минимального запаса' });
    expect(within(below).getAllByRole('row')).toHaveLength(1 + 1);
    expect(screen.getByRole('link', { name: 'Все позиции' }).getAttribute('href')).toContain('sklad/minimum');
    await expectNoAxeViolations(container);
  });

  it('Остатки по складам: branches table selects a branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /sklad/ostatki': json(SKLAD_OSTATKI), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<SkladOstatki section="sklad" page="ostatki" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Склады' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 2);
    await user.click(within(table).getByText('Каскад Чирчикских ГЭС'));
    expect(onBranch).toHaveBeenCalledWith(3);
    expect(screen.getByRole('list', { name: 'Запасы по категориям' })).toBeInTheDocument();
  });

  it('Минимальный запас: coverage bar and missing minimum data', async () => {
    mockApi({ 'GET /sklad/minimum': json(SKLAD_MINIMUM), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<SkladMinimum section="sklad" page="minimum" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Ниже минимального запаса' });
    expect(within(table).getByText('40%').closest('.exec')).toHaveClass('neg');
    expect(within(table).getByText('4 шт')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /sklad/minimum': json(SKLAD_NO_MIN), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<SkladMinimum section="sklad" page="minimum" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText(/Источник данных не подключён: минимальный запас \(1С\)/)).toBeInTheDocument();
    expect(screen.getAllByText('нет данных в 1С').length).toBeGreaterThan(0);
  });

  it('Неликвиды: age buckets, idle list and missing movement dates', async () => {
    mockApi({ 'GET /sklad/nelikvid': json(SKLAD_NELIKVID), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<SkladNelikvid section="sklad" page="nelikvid" filters={filters} onBranch={vi.fn()} />);
    const ages = await screen.findByRole('list', { name: 'Возраст запасов' });
    expect(within(ages).getByText('более 365 дней')).toBeInTheDocument();
    expect(within(ages).queryByText('нет даты движения')).toBeNull();
    const table = screen.getByRole('table', { name: 'Без движения более 180 дней' });
    expect(within(table).getByText('456 дн.')).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /sklad/nelikvid': json(SKLAD_NO_AGE), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<SkladNelikvid section="sklad" page="nelikvid" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findAllByText(/Источник данных не подключён: дата последнего движения \(1С\)/)).toHaveLength(2);
  });
});
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/sklad`
Expected: FAIL — `Failed to resolve import "./minimum"`.

- [ ] **Step 3: Implementatsiya — KPI, grafik, kategoriyalar, yosh**

`frontend/src/sections/sklad/parts/StockKpis.tsx`:
```tsx
import type { StockKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate, formatNumber } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

/** Prototip `kpisWh`: стоимость, оборачиваемость, ниже минимума, неликвиды, приход, расход. */
export function StockKpis({ kpis }: { kpis: StockKpisOut }) {
  const value = moneyParts(kpis.value);
  const inflow = moneyParts(kpis.inflow);
  const outflow = moneyParts(kpis.outflow);
  const noSource = t('sklad.kpi.noSource');
  return (
    <KpiGrid>
      <KpiTile icon="box" label={t('sklad.kpi.value')} value={value.value} unit={value.unit} delta={t('sklad.kpi.valueNote', { date: formatDate(kpis.as_of) })} hint={formula('stockValue')} />
      <KpiTile
        icon="clock"
        label={t('sklad.kpi.turnover')}
        value={kpis.turnover_days === null ? t('dash.noValue') : formatNumber(kpis.turnover_days, 0)}
        unit={kpis.turnover_days === null ? undefined : t('unit.days')}
        delta={t('sklad.kpi.turnoverNote')}
        hint={formula('turnover')}
      />
      <KpiTile
        icon="alert"
        label={t('sklad.kpi.below')}
        value={kpis.has_minimum ? String(kpis.below_min) : t('dash.noValue')}
        negative={kpis.has_minimum && kpis.below_min > 5}
        delta={kpis.has_minimum ? t('sklad.kpi.belowNote', { count: kpis.positions }) : noSource}
        hint={formula('belowMin')}
      />
      <KpiTile
        icon="pct"
        label={t('sklad.kpi.illiquid')}
        value={kpis.has_age ? formatPct(kpis.idle_share, 1) : t('dash.noValue')}
        negative={kpis.idle_share !== null && kpis.idle_share > 0.2}
        delta={kpis.has_age ? t('sklad.kpi.illiquidNote', { amount: formatMoney(kpis.idle_value) }) : noSource}
        hint={formula('illiquid')}
      />
      <KpiTile icon="in" label={t('sklad.kpi.inflow')} value={inflow.value} unit={inflow.unit} delta={t('sklad.kpi.period')} hint={formula('stockFlow')} />
      <KpiTile icon="out" label={t('sklad.kpi.outflow')} value={outflow.value} unit={outflow.unit} delta={t('sklad.kpi.period')} hint={formula('stockFlow')} />
    </KpiGrid>
  );
}
```

`frontend/src/sections/sklad/parts/StockFlowCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { StockMonthOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, COLORS, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { monthShort } from '../../../dash/months';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

/** Prototip `whFlowCard`: поступление и списание запасов по месяцам. */
export function StockFlowCard({ months, ctx, className }: { months: StockMonthOut[]; ctx: ExportContext; className?: string }) {
  const title = t('sklad.flow.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const inColor = COLORS.in();
  const outColor = COLORS.out();
  const config = useMemo(
    () =>
      barConfig({
        labels: months.map((m) => monthShort(m.month_id)),
        series: [
          { label: t('sklad.flow.in'), data: months.map((m) => m.inflow), color: inColor },
          { label: t('sklad.flow.out'), data: months.map((m) => m.outflow), color: outColor },
        ],
      }),
    [months, inColor, outColor],
  );
  const table = {
    headers: [t('sklad.flow.month'), t('sklad.flow.in'), t('sklad.flow.out')],
    rows: months.map((m) => [monthShort(m.month_id), m.inflow, m.outflow]),
  };
  return (
    <Card className={className} title={title} sub={t('sklad.flow.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('stockFlow')}>
        <span>
          <i style={{ background: inColor }} />
          {t('sklad.flow.in')}
        </span>
        <span>
          <i style={{ background: outColor }} />
          {t('sklad.flow.out')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
```

`frontend/src/sections/sklad/parts/CategoriesCard.tsx`:
```tsx
import type { NamedAmountOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { Rank } from '../../../dash/Rank';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

export function CategoriesCard({ categories, asOf, className }: { categories: NamedAmountOut[]; asOf: string; className?: string }) {
  const title = t('sklad.cat.title');
  return (
    <Card className={className} title={title} sub={t('sklad.cat.sub', { date: formatDate(asOf) })}>
      {categories.length ? <Rank label={title} items={categories.map((c) => ({ id: c.name, name: c.name, value: c.amount }))} /> : <NoData kind="period" />}
    </Card>
  );
}
```

`frontend/src/sections/sklad/parts/AgesCard.tsx`:
```tsx
import type { AgeBucketOut } from '../../../api/types';
import { NoData } from '../../../dash/DataState';
import { formula } from '../../../dash/formulas';
import { Rank } from '../../../dash/Rank';
import { t, type MessageKey } from '../../../i18n';
import { Card } from '../../../ui/Card';

const OLD = new Set(['d181_365', 'gt365']);

/** TZ 4 «Возраст запасов»: до 90, 91–180, 181–365, более 365 дней; «нет даты движения» — только если есть. */
export function AgesCard({ ages, hasAge, className }: { ages: AgeBucketOut[]; hasAge: boolean; className?: string }) {
  const title = t('sklad.age.title');
  const items = ages
    .filter((a) => a.key !== 'unknown' || a.value > 0)
    .map((a) => ({ id: a.key, name: t(`sklad.age.${a.key}` as MessageKey), value: a.value, negative: OLD.has(a.key) }));
  return (
    <Card className={className} title={title} sub={t('sklad.age.sub')}>
      {hasAge ? (
        <div title={formula('stockAge')}>
          <Rank label={title} items={items} />
        </div>
      ) : (
        <NoData kind="source" source={t('sklad.age.source')} />
      )}
    </Card>
  );
}
```

- [ ] **Step 4: Implementatsiya — jadvallar**

`frontend/src/sections/sklad/parts/BelowMinCard.tsx`:
```tsx
import type { StockPositionOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { buildHash } from '../../../router/hash';
import { Card } from '../../../ui/Card';
import { cx } from '../../../ui/cx';
import { Table, type Column } from '../../../ui/Table';

function qty(value: number | null, unit: string): string {
  return value === null ? t('dash.noValue') : `${formatNumber(value, 0)} ${unit}`;
}

function Coverage({ value }: { value: number | null }) {
  return (
    <span className={cx('exec', value !== null && value < 0.5 && 'neg')}>
      {formatPct(value, 0)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (value ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

export interface BelowMinCardProps {
  rows: StockPositionOut[];
  hasMinimum: boolean;
  title: string;
  sub: string;
  ctx: ExportContext;
  more?: boolean;
  className?: string;
}

/** Prototip `belowTable`: позиции ниже минимума с обеспеченностью (< 50% — qizil); tartib serverdan. */
export function BelowMinCard({ rows, hasMinimum, title, sub, ctx, more = false, className }: BelowMinCardProps) {
  const headers = [t('sklad.col.position'), t('sklad.col.warehouse'), t('sklad.col.qty'), t('sklad.col.min'), t('sklad.col.coverage')];
  const columns: Column<StockPositionOut>[] = [
    {
      key: 'name',
      header: headers[0] ?? '',
      cell: (p) => (
        <>
          {p.name}
          <br />
          <span className="note">{p.category}</span>
        </>
      ),
      sortValue: (p) => p.name,
      wrap: true,
    },
    {
      key: 'warehouse',
      header: headers[1] ?? '',
      cell: (p) => (
        <>
          {p.branch_name}
          <br />
          <span className="note">{p.warehouse}</span>
        </>
      ),
      sortValue: (p) => p.branch_name,
      wrap: true,
    },
    { key: 'qty', header: headers[2] ?? '', cell: (p) => qty(p.qty, p.unit), sortValue: (p) => p.qty, align: 'right' },
    { key: 'min', header: headers[3] ?? '', cell: (p) => qty(p.min_qty, p.unit), sortValue: (p) => p.min_qty, align: 'right' },
    { key: 'coverage', header: headers[4] ?? '', cell: (p) => <Coverage value={p.coverage} />, sortValue: (p) => p.coverage, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={sub}
      exportSlot={
        hasMinimum && rows.length ? (
          <CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((p) => [p.name, p.warehouse, p.qty, p.min_qty, p.coverage === null ? null : Math.round(p.coverage * 100)]) })} />
        ) : undefined
      }
    >
      {hasMinimum ? (
        <Table caption={title} columns={columns} rows={rows} rowKey={(p) => `${p.branch_id}-${p.nom_code}-${p.warehouse}`} free empty={<p className="note">{t('sklad.below.none')}</p>} />
      ) : (
        <NoData kind="source" source={t('sklad.below.source')} />
      )}
      {more ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'sklad', page: 'minimum', br: ctx.br, per: ctx.per })}>
          {t('sklad.below.all')}
        </a>
      ) : null}
    </Card>
  );
}
```

`frontend/src/sections/sklad/parts/IlliquidCard.tsx`:
```tsx
import type { StockPositionOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { NoData } from '../../../dash/DataState';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

/** Prototip `idleTable`: без движения более 180 дней, по стоимости; > 365 дней — qizil belgi. */
export function IlliquidCard({ rows, hasAge, ctx, className }: { rows: StockPositionOut[]; hasAge: boolean; ctx: ExportContext; className?: string }) {
  const title = t('sklad.idle.title');
  const headers = [t('sklad.col.position'), t('sklad.col.warehouse'), t('sklad.col.count'), t('sklad.col.value'), t('sklad.col.age')];
  const columns: Column<StockPositionOut>[] = [
    {
      key: 'name',
      header: headers[0] ?? '',
      cell: (p) => (
        <>
          {p.name}
          <br />
          <span className="note">{p.category}</span>
        </>
      ),
      sortValue: (p) => p.name,
      wrap: true,
    },
    { key: 'warehouse', header: headers[1] ?? '', cell: (p) => p.branch_name, sortValue: (p) => p.branch_name, wrap: true },
    { key: 'qty', header: headers[2] ?? '', cell: (p) => `${formatNumber(p.qty, 0)} ${p.unit}`, sortValue: (p) => p.qty, align: 'right' },
    { key: 'value', header: headers[3] ?? '', cell: (p) => <b>{formatMoney(p.value)}</b>, sortValue: (p) => p.value, align: 'right' },
    {
      key: 'age',
      header: headers[4] ?? '',
      cell: (p) => (p.age_days === null ? t('dash.noValue') : <Badge tone={p.age_days > 365 ? 'neg' : 'neutral'}>{t('sklad.col.days', { days: p.age_days })}</Badge>),
      sortValue: (p) => p.age_days,
    },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('sklad.idle.sub')}
      exportSlot={hasAge && rows.length ? <CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((p) => [p.name, p.branch_name, p.qty, p.value, p.age_days]) })} /> : undefined}
    >
      {hasAge ? (
        <Table caption={title} columns={columns} rows={rows} rowKey={(p) => `${p.branch_id}-${p.nom_code}-${p.warehouse}`} free empty={<p className="note">{t('sklad.idle.none')}</p>} />
      ) : (
        <NoData kind="source" source={t('sklad.age.source')} />
      )}
    </Card>
  );
}
```

`frontend/src/sections/sklad/parts/StockBranchesTable.tsx`:
```tsx
import type { StockBranchOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import type { FilterState } from '../../../shell/useFilters';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

/** Prototip `whBrTable` (TZ 5 «склады филиалов»): bosish — filial tanlash (TZ 6). */
export function StockBranchesTable({ rows, ctx, filters, onBranch, className }: { rows: StockBranchOut[]; ctx: ExportContext; filters: FilterState; onBranch(br: number | null): void; className?: string }) {
  const title = t('sklad.branches.title');
  const headers = [t('sklad.col.warehouse'), t('sklad.col.value'), t('sklad.branches.positions'), t('sklad.branches.below'), t('sklad.branches.idle')];
  const columns: Column<StockBranchOut>[] = [
    { key: 'name', header: headers[0] ?? '', cell: (r) => r.name, sortValue: (r) => r.name, wrap: true },
    { key: 'value', header: headers[1] ?? '', cell: (r) => formatMoney(r.value), sortValue: (r) => r.value, align: 'right' },
    { key: 'positions', header: headers[2] ?? '', cell: (r) => String(r.positions), sortValue: (r) => r.positions, align: 'right' },
    { key: 'below', header: headers[3] ?? '', cell: (r) => <span className={r.below_min > 1 ? 'neg' : undefined}>{r.below_min}</span>, sortValue: (r) => r.below_min, align: 'right' },
    { key: 'idle', header: headers[4] ?? '', cell: (r) => formatMoney(r.idle_value), sortValue: (r) => r.idle_value, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('sklad.branches.sub')}
      exportSlot={<CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: rows.map((r) => [r.name, r.value, r.positions, r.below_min, r.idle_value]) })} />}
    >
      <Table caption={title} columns={columns} rows={rows} rowKey={(r) => r.branch_id} onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)} free />
    </Card>
  );
}
```

- [ ] **Step 5: Implementatsiya — sahifalar**

`frontend/src/sections/sklad/svod.tsx`:
```tsx
import type { SkladSvodOut } from '../../api/types';
import { NoData } from '../../dash/DataState';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { BelowMinCard } from './parts/BelowMinCard';
import { CategoriesCard } from './parts/CategoriesCard';
import { StockFlowCard } from './parts/StockFlowCard';
import { StockKpis } from './parts/StockKpis';

export default function SkladSvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<SkladSvodOut>('/sklad/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          {data.kpis.has_data ? null : (
            <Card>
              <NoData kind="period" />
            </Card>
          )}
          <div className="grid">
            <StockFlowCard className="c8" months={data.months} ctx={ctx} />
            <CategoriesCard className="c4" categories={data.categories} asOf={data.kpis.as_of} />
            <BelowMinCard className="c12" rows={data.below} hasMinimum={data.kpis.has_minimum} title={t('sklad.below.title')} sub={t('sklad.below.subTop')} ctx={ctx} more />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/sklad/ostatki.tsx`:
```tsx
import type { SkladOstatkiOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { CategoriesCard } from './parts/CategoriesCard';
import { StockBranchesTable } from './parts/StockBranchesTable';
import { StockKpis } from './parts/StockKpis';

export default function SkladOstatki({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<SkladOstatkiOut>('/sklad/ostatki', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          <div className="grid">
            <StockBranchesTable className="c8" rows={data.branches} ctx={ctx} filters={filters} onBranch={onBranch} />
            <CategoriesCard className="c4" categories={data.categories} asOf={data.kpis.as_of} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/sklad/minimum.tsx`:
```tsx
import type { SkladMinimumOut } from '../../api/types';
import { t } from '../../i18n';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { BelowMinCard } from './parts/BelowMinCard';
import { StockKpis } from './parts/StockKpis';

export default function SkladMinimum({ section, page, filters }: SectionPageProps) {
  const query = useSection<SkladMinimumOut>('/sklad/minimum', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          <div className="grid">
            <BelowMinCard className="c12" rows={data.below} hasMinimum={data.kpis.has_minimum} title={t('sklad.below.title')} sub={t('sklad.below.subAll')} ctx={ctx} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

`frontend/src/sections/sklad/nelikvid.tsx`:
```tsx
import type { SkladNelikvidOut } from '../../api/types';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { AgesCard } from './parts/AgesCard';
import { IlliquidCard } from './parts/IlliquidCard';
import { StockKpis } from './parts/StockKpis';

export default function SkladNelikvid({ section, page, filters }: SectionPageProps) {
  const query = useSection<SkladNelikvidOut>('/sklad/nelikvid', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) => (
        <>
          <StockKpis kpis={data.kpis} />
          <div className="grid">
            <AgesCard className="c4" ages={data.ages} hasAge={data.kpis.has_age} />
            <IlliquidCard className="c8" rows={data.illiquid} hasAge={data.kpis.has_age} ctx={ctx} />
          </div>
        </>
      )}
    </SectionData>
  );
}
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/sklad` va `$NODE npm run check`
Expected: 4 test passed; `check` (tsc, eslint, vitest, build) — xatosiz; 3-reja `SectionScreen` testlari «Производство» va «Склад» uchun endi sahifa komponentlarini topadi (placeholder emas).

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Склад» — Сводка, Остатки по складам, Минимальный запас, Неликвиды

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
### Task 18: E2E — «Производство» va «Склад», filial doirasi va CSP; to'liq tekshiruv, spec holati

**Files:**
- Create: `frontend/e2e/specs/proizvodstvo-sklad.spec.ts`
- Modify: `docs/superpowers/specs/2026-09-25-s3-proizvodstvo-sklad-design.md` (holat)
- Test: `frontend/e2e/specs/proizvodstvo-sklad.spec.ts`

**Interfaces:**
- Consumes: 3-reja E2E (`signIn`, `adminFor`, `expectNoHorizontalScroll`, `e2e_branch` — `economist_filiala`, filial 3 «Каскад Чирчикских ГЭС»; loyihalar `mobile-390`, `tablet-1024`, `desktop-1440`), S1 `scripts/e2e.sh` (sintetik to'liq yuklash — endi ishlab chiqarish, realizatsiya va ombor ham); dev stack'da `ASKUE_LIVE_URL` bo'sh (jonli quvvat — «Источник не подключён»).
- Produces: E2E ssenariylari.

- [ ] **Step 1: E2E ssenariysini yozish**

`frontend/e2e/specs/proizvodstvo-sklad.spec.ts`:
```ts
import { expect, test, type Page } from '@playwright/test';
import { adminFor, expectNoHorizontalScroll, signIn } from '../fixtures';

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

test('Производство: сводка с картой, станции, реализация, головная организация', async ({ page }, info) => {
  const csp = watchCsp(page);
  await page.goto('/#proizvodstvo/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Производство: сводка' })).toBeVisible();
  await expect(page.getByText('Выработка электроэнергии')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Выработка по месяцам' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Карта Узбекистана с расположением ГЭС' })).toBeVisible();
  await expect(page.getByText('Источник данных не подключён: онлайн-мониторинг ГЭС')).toBeVisible();
  await expectNoHorizontalScroll(page);

  await open(page, '#proizvodstvo/stancii', 'Выработка по станциям');
  if (info.project.name === 'desktop-1440') {
    await expect(page.getByRole('table', { name: 'Станции' }).locator('tbody tr')).toHaveCount(15);
  }
  await open(page, '#proizvodstvo/realiz', 'Реализация');
  await expect(page.getByRole('img', { name: 'Реализация электроэнергии по месяцам' })).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.goto('/#proizvodstvo/svod?br=1');
  await expect(page.getByText(/Головная организация не эксплуатирует станции/)).toBeVisible();
  expect(csp).toEqual([]);
});

test('Склад: сводка, остатки, минимальный запас, неликвиды', async ({ page }, info) => {
  const csp = watchCsp(page);
  await page.goto('/#sklad/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Склад: сводка' })).toBeVisible();
  await expect(page.getByText('Стоимость запасов')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Движение запасов по месяцам' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await open(page, '#sklad/ostatki', 'Остатки по складам');
  await expect(page.getByRole('table', { name: 'Склады' })).toBeVisible();
  await open(page, '#sklad/minimum', 'Минимальный запас');
  await expect(page.getByRole('table', { name: 'Ниже минимального запаса' })).toBeVisible();
  await open(page, '#sklad/nelikvid', 'Неликвиды');
  await expect(page.getByRole('list', { name: 'Возраст запасов' })).toBeVisible();
  await expectNoHorizontalScroll(page);
  expect(csp).toEqual([]);
});

test('Экономист филиала видит только свой филиал', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'bitta kenglik yetarli');
  await page.goto('/#sklad/ostatki');
  await signIn(page, 'e2e_branch');
  const table = page.getByRole('table', { name: 'Склады' });
  await expect(table).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.getByText('Каскад Чирчикских ГЭС')).toBeVisible();
  const denied = await page.request.get('/api/v1/proizvodstvo/stancii?br=2');
  expect(denied.status()).toBe(403);
  const own = await page.request.get('/api/v1/sklad/ostatki');
  expect(own.status()).toBe(200);
  const body = (await own.json()) as { branches: Array<{ branch_id: number }> };
  expect(body.branches.map((b) => b.branch_id)).toEqual([3]);
  const stations = (await (await page.request.get('/api/v1/proizvodstvo/stancii')).json()) as { stations: Array<{ branch_id: number }> };
  expect(stations.stations.map((s) => s.branch_id)).toEqual([3]);
});
```
(Sahifa sarlavhasi — 3-reja `SectionScreen`: «Сводка» uchun `«<bo'lim>: сводка»`, qolganlari — menyudagi nom. `e2e_branch` — `economist_filiala` (TZ 1: «Производство» va «Склад» ochiq, `scope_all = false`).)

- [ ] **Step 2: To'liq tekshiruv**

```bash
docker compose -f deploy/compose.yml up -d --build
$TEST pytest -q
$TEST ruff check app tests && $TEST mypy app
$NODE npm run check
./scripts/e2e.sh
./scripts/prod_config.sh
```
Expected: backend testlari passed (qamrov darvozasi 4-rejadagidek); frontend `check` passed; Playwright — 3 loyihada `proizvodstvo-sklad.spec.ts`, S1 `sections.spec.ts` va S2 `kredity.spec.ts` passed (filial testi faqat 1440 da), CSP buzilishi yo'q; `prod-config: OK`. Tarmoqqa (treplex.uz, 1C) chiqish yo'q — `grep -rn "treplex.uz" backend/tests` faqat hujjat/izohlarda, testlar `treplex.test` va `1c.test` domenlarini `MockTransport` bilan ishlatadi.

- [ ] **Step 3: Spec holati**

`docs/superpowers/specs/2026-09-25-s3-proizvodstvo-sklad-design.md` — `- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)` qatorini almashtiring:
```markdown
- Holat: amalga oshirilgan (S3-reja: docs/superpowers/plans/2026-09-25-07-s3-proizvodstvo-sklad.md); ochiq savollar 1–6 (АСКУЭ formati, treplex.uz, reja/realizatsiya manbai, 1C ombor kengaytmasi) mijozda
```

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e docs/superpowers/specs
git commit -m "test(e2e): «Производство» va «Склад» sahifalari, filial doirasi va CSP; S3 spec holati

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
