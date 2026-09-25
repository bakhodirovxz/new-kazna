# UGEKAZNA S2-reja: «Кредиты» + banklar (fayl / DirectBank) + ЦБ kurslari + Telegram — implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TZ 2-bosqichining qolgan qismi: «Кредиты» bo'limi (3 sahifa) витрина агрегатлари ustida, 2 ta kredit qoidasi, bank ko'chirmalari fayllaridan qoldiq/проводка/topshiriq holatlari (DirectBank interfeysi bilan), ЦБ РУз kurslari va Telegram orqali kundalik hisobot hamda ogohlantirishlar.

**Architecture:** Backend 2-reja freymvorkiga 2 ta `mart` agregatini (`agg_loan_month`, `agg_loan_schedule`) qo'shadi; `/kredity/*` endpointlari S1 bo'lim qatlami (`SQ`, `BranchSel`, `Cache.respond`) va `app/sections/queries/loans.py` orqali ishlaydi, qoidalar S1 `app/alerts` reyestriga qo'shiladi. Uchta yangi manba 2-reja `SourceConnector` protokolini amalga oshiradi va `Runner` orqali yuklanadi: `BankFileConnector` (kanonik CSV adapteri → `BankMapper` → staging; SHA-256 fayl jurnali, arxiv), `CbuRatesConnector` (httpx, fixture'lar bilan test), DirectBank — interfeys + «не настроен». 1C va bank oqimlari to'qnashmasligi uchun agregatlar `dwh.cashflow_effective` view'idan o'qiydi. `TelegramNotifier` 2-reja `Notifier` interfeysini amalga oshiradi; kundalik hisobot worker jobi. Frontend S1 `src/dash` bloklari bilan `src/sections/kredity/*.tsx`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (sync) + psycopg 3, PostgreSQL 16, Redis 7, httpx, pydantic 2, APScheduler 3, pytest; React 18 + TypeScript strict, TanStack Query 5, Chart.js 4, Vitest + Testing Library + axe, Playwright 1.49.1.

**Spec:** [docs/superpowers/specs/2026-09-25-s2-kredity-banki-design.md](../specs/2026-09-25-s2-kredity-banki-design.md). Asos: 1-reja [2026-09-24-01-backend-yadro.md](2026-09-24-01-backend-yadro.md) (`Ctx`, `require_perm`, `AuditAction`, `record`, `blind_index`, `Role`, `RolePermission`), 2-reja [2026-09-24-02-vitrina-etl.md](2026-09-24-02-vitrina-etl.md) (`TARGETS`, `merge_*`, `DbStagingSink`, `register(Aggregate)`, `_MONTHS`, `builds`, `Runner`, `run_checks`, `Notifier`, `build_notifier`, `FileConnector`, `make_connector`, `DEFAULT_SETTINGS`, `validate_setting`, `current_setting`, `tests.etl_helpers`, `published_synthetic`, worker), 3-reja [2026-09-24-03-frontend.md](2026-09-24-03-frontend.md) (qobiq, `SectionPageProps`, `Card`, `KpiTile`, `Table`, `Badge`, `EmptyState`, `mockApi`, `renderWithProviders`, E2E fixture'lari), 4-reja [2026-09-25-04-ops-security.md](2026-09-25-04-ops-security.md) (`compose.prod.yml`, `egress`, `prod_config.sh`, `host-hardening.md`), S1-reja [2026-09-25-05-s1-obzor-kazna.md](2026-09-25-05-s1-obzor-kazna.md) (`SQ`, `SectionQuery`, `BranchSel`, `resolve_period`, `fmt_*`, `plural`, `schemas._Out/period_out`, `app.alerts` reyestri, `queries.cash/calendar`, `tests.s1_helpers.rebuild`, `OneCConnector`, `src/dash/*`, `useSection`, `SectionData`, `toggleBranch`). 1–4-rejalar va S1-reja bajarilgan deb hisoblanadi (oxirgi migratsiya — `0010`).

## Global Constraints

- 1–4-rejalar va S1-rejaning barcha Global Constraints'lari amal qiladi (Python `>=3.12`, hash bilan qulflangan bog'liqliklar, sirlar faqat Docker secrets, UTC, `/api/v1`, xato formati `{"error": {code, message, request_id, params?}}`, ruscha UI matnlari, o'zbekcha reja prozasi va izohlar).
- Backend testlari: `TEST="docker compose -f deploy/compose.test.yml run --rm test"`, keyin `$TEST pytest …` — haqiqiy PostgreSQL 16 va Redis; DB mock qilinmaydi. Frontend: `NODE="docker compose -f deploy/compose.frontend.yml run --rm node"`, keyin `$NODE npm …`; host Node ishlatilmaydi. Git Bash'da bind-mount'li `docker run` oldidan `MSYS_NO_PATHCONV=1`.
- Summalar `numeric(20,2)` **mln so'm**; `fact_loan_schedule` summalari — kredit valyutasida (mln birlik); `fx_rate.rate` — 1 birlik valyuta uchun so'm; `date_id` = `YYYYMMDD`, `month_id` = `YYYYMM`.
- UI faqat `pub.*` view'larni o'qiydi (TZ 9). Yangi `mart` jadvali: `build_id → core.builds ON DELETE CASCADE`, `month_id` ustuni, `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `core.rls_branch_ok(branch_id)`; `pub` view `security_invoker = true`, faqat aktiv build.
- Bo'lim endpointi: `GET`, `SQ` (`br ≥ 1 | None`, `per`), router darajasida `require_perm(section:kredity:view)`, `cache.respond("kredity.<sahifa>", q.cache_filters, loader)`.
- Migratsiyalar: `0011_mart_loans` (`down_revision = "0010"`), `0012_banks_fx` (`down_revision = "0011"`).
- Kredit summalari hisobot sanasi `D` (= davr oxiri, ochiq davrda bugun) kursida; kursi yo'q valyuta — `missing_fx`, nol emas. Chegaralar faqat `core.alert_rules` dan.
- Bank hisob raqami **ochiq ko'rinishda** faqat staging'ga (u yerda darhol shifrlanadi) va xotiraga tushadi; loglar, `core.etl_error`, `core.bank_files`, arxiv fayl nomlari, `core.settings`, CLI chiqishi — faqat `BA-…` kodi yoki `…1234`.
- Tashqi HTTP (cbu.uz, api.telegram.org) — faqat `worker`, `httpx` (`trust_env=False`, `follow_redirects=False`, TLS tekshiruvi yoqilgan, javob hajmi chegarasi), ixtiyoriy `EGRESS_PROXY`; testlarda faqat `httpx.MockTransport`, tarmoqqa chiqish yo'q. Telegram tokeni hech qayerga (log, xato matni, audit) yozilmaydi.
- Telegram hisobotida shaxsiy ma'lumot, hisob raqami, kontragent nomi yo'q; summalar млрд/трлн сум.
- Credential fayllari (`1C.1/secrets.php`, `auth.php`, `auth.js`, `apache-proxy.conf`, `gazna_bot/config.py`, `.env`, `deploy/secrets/`) ochilmaydi va hech qayerga ko'chirilmaydi.
- Frontend: `src/sections/<bo'lim>/*.tsx` — faqat sahifalar, yordamchilar `src/sections/kredity/parts/`; barcha matnlar `t()` orqali (`src/i18n/ru.ts` oxiriga); CSP o'zgarmaydi.
- Commit xabari oxirida bo'sh qatordan keyin: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Spec'dan ongli chetlanishlar yo'q; S2 qarorlari — spec 12-bo'lim.

## Review Focus

1. **Kredit grafigi prod'da `FileConnector` orqali yuklanadi, kelajak qatorlari bilan** — 2-reja `FileConnector` fakt qatorlarini oyna (`… → bugun`) bo'yicha kesadi, `forward` maqsad esa oynadan keyingisini o'chiradi: 2027+ to'lovlari yuklanmaydi va ikkinchi yuklashda yo'qoladi. Kutiladi: ikki marta to'liq yuklashdan keyin ham kelajak qatorlari joyida — 2-vazifa `test_file_connector_keeps_future_loan_rows`.
2. **Bank fayli qayta yetkaziladi / ikkinchi fayl keladi / yugurish yiqiladi** — kutiladi: dublikat yo'q, birinchi faylning qatorlari o'chmaydi, muvaffaqiyatsiz yugurishdagi fayl keyingi safar qayta o'qiladi — 8-vazifa `test_redelivery_is_idempotent_and_second_file_keeps_first`, `test_failed_run_files_are_reprocessed`.
3. **Fayl nomi yoki buzilgan qatorda to'liq hisob raqami** — kutiladi: log, `etl_error`, `bank_files`, arxiv nomi, CLI chiqishida faqat `…1234` — 8-vazifa `test_account_number_never_leaks`, 9-vazifa `test_bank_accounts_cli`.
4. **Hisobot sanasida kredit valyutasining ЦБ kursi yo'q** (tarix to'ldirilmagan) — kutiladi: kredit portfelga nol bo'lib kirmaydi, `missing_fx` bilan belgilanadi, valyuta ulushi qoidasi yolg'on yonmaydi — 3-vazifa `test_missing_fx_is_flagged_not_zero`, 5-vazifa `test_no_loans_or_missing_rates_do_not_fire`.
5. **Telegram so'rovi xato bilan tugaydi** — `httpx` INFO logida URL (token bilan) chiqadi, istisno matnida URL bo'ladi; kutiladi: token hech bir logda va xato matnida yo'q — 11-vazifa `test_token_never_logged`.

---

## Fayl tuzilishi

```
backend/app/core/config.py                    egress/cbu/bank/telegram sozlamalari, telegram_chats, problems()
backend/app/dwh/reference.py                  S2 sozlamalari (banks.*, fx.*, etl.*_cron, telegram.summary_cron)
backend/app/etl/notify.py                     Kind += bank_rows_rejected; build_notifier → TelegramNotifier
backend/app/audit/service.py                  AuditAction.TELEGRAM_SUMMARY_SENT
backend/migrations/versions/0011_mart_loans.py, 0012_banks_fx.py
backend/app/dwh/loan_aggregates.py            agg_loan_month, agg_loan_schedule
backend/app/dwh/aggregates.py, treasury_aggregates.py   cashflow_effective'dan o'qish; loan_aggregates importi
backend/app/etl/file_connector.py             forward maqsad oynada kesilmaydi
backend/app/etl/quality.py                    balance_identity — manbalararo filiallar
backend/app/etl/types.py, staging.py          ReportingSink, DbStagingSink.error()
backend/app/sections/queries/loans.py, loan_schemas.py, kredity.py
backend/app/alerts/loans.py (+ __init__.py)
backend/app/etl/banks/                        registry, models, canonical, adapters, accounts, fx, ledger, mapper, connector, directbank, admin
backend/app/etl/cbu/                          client, connector
backend/app/etl/telegram.py                   TelegramClient, TelegramNotifier
backend/app/reports/daily.py                  kundalik hisobot
backend/app/etl/connectors.py, app/worker.py, app/cli.py, app/main.py
backend/tests/s2_helpers.py, tests/fixtures/cbu/*.json
deploy/compose.prod.yml, deploy/prod.env.example, deploy/secrets.example/README.md, scripts/prod_config.sh
docs/integration/banks-format.md, banks-connector.md, cbu-telegram.md, kredity-fayl.md; docs/ops/host-hardening.md
frontend/src/api/types.ts, openapi.json, src/api/schema.d.ts
frontend/src/dash/formulas.ts, src/i18n/ru.ts, src/test/s2Fixtures.ts
frontend/src/sections/kredity/{svod,reestr,grafik}.tsx, kredity/parts/*
frontend/e2e/specs/kredity.spec.ts
```

---

### Task 1: S2 sozlamalari, konfiguratsiya, xabarnoma turi va audit harakati

**Files:**
- Create: `backend/app/etl/banks/__init__.py`, `backend/app/etl/banks/registry.py`
- Modify: `backend/app/core/config.py`, `backend/app/dwh/reference.py`, `backend/app/etl/notify.py` (`Kind`), `backend/app/audit/service.py` (`AuditAction`), `backend/tests/test_reference.py` (kutilgan kalitlar)
- Test: `backend/tests/test_s2_prereq.py`

**Interfaces:**
- Consumes: `Settings`, `ConfigError`, `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `_cron`, `Notification`.
- Produces:
  - `app.etl.banks.registry`: `BANKS: dict[str, str]` (`sqb`, `nbu`, `asaka`, `ipoteka`, `xalq` → ruscha nom), `ADAPTER_NAMES = ("canonical",)`, `BankAccount` (pydantic, frozen: `code` `^BA-[0-9a-f]{16}$`, `bank_code ∈ BANKS`, `branch_code`, `currency` `^[A-Z]{3}$`, `gl_account` `^\d{4}$`, `last4` `^\d{4}$`).
  - `Settings`: `egress_proxy: str = ""`, `cbu_enabled: bool = False`, `cbu_base_url = "https://cbu.uz"`, `bank_inbox_dir = "/data/import/banks"`, `bank_archive_dir = "/data/archive/banks"`, `telegram_bot_token: SecretStr`, `telegram_chat_ids: SecretStr`, `telegram_api_base = "https://api.telegram.org"`, `telegram_chats -> list[int]` (noto'g'ri → `ConfigError`), `telegram_enabled -> bool`; `TELEGRAM_TOKEN_RE`; `problems()` telegram/proksi xatolarini qaytaradi.
  - Sozlamalar: `banks.accounts = []`, `banks.statement_branches = []`, `banks.formats = {bank: "canonical"}`, `etl.banks_cron = "30 9,12,15,18 * * *"`, `etl.cbu_cron = "0 8 * * *"`, `fx.currencies = ["USD", "EUR", "CNY", "RUB", "GBP", "JPY", "CHF", "KZT", "KRW"]`, `fx.lookback_days = 7`, `telegram.summary_cron = "30 8 * * *"`.
  - `Notification.kind` += `"bank_rows_rejected"`; `AuditAction.TELEGRAM_SUMMARY_SENT = "notify.telegram.summary"`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_s2_prereq.py`:
```python
from typing import Any

import pytest
from pydantic import SecretStr

from app.audit.service import AuditAction
from app.core.config import ConfigError, get_settings
from app.dwh.reference import DEFAULT_SETTINGS, validate_setting
from app.etl.banks.registry import ADAPTER_NAMES, BANKS, BankAccount
from app.etl.notify import Notification

ACC = {"code": "BA-0123456789abcdef", "bank_code": "sqb", "branch_code": "UGE-02",
       "currency": "UZS", "gl_account": "5110", "last4": "0001"}
TOKEN = "123456789:" + "A" * 35


def test_s2_settings_defaults() -> None:
    assert set(BANKS) == {"sqb", "nbu", "asaka", "ipoteka", "xalq"}
    assert ADAPTER_NAMES == ("canonical",)
    assert DEFAULT_SETTINGS["banks.accounts"] == []
    assert DEFAULT_SETTINGS["banks.statement_branches"] == []
    assert DEFAULT_SETTINGS["banks.formats"] == dict.fromkeys(BANKS, "canonical")
    assert DEFAULT_SETTINGS["fx.currencies"][:3] == ["USD", "EUR", "CNY"]
    assert DEFAULT_SETTINGS["fx.lookback_days"] == 7
    for key, cron in (("etl.banks_cron", "30 9,12,15,18 * * *"), ("etl.cbu_cron", "0 8 * * *"),
                      ("telegram.summary_cron", "30 8 * * *")):
        assert DEFAULT_SETTINGS[key] == cron
        assert validate_setting(key, cron) == cron


def test_s2_settings_validation() -> None:
    assert validate_setting("banks.accounts", [ACC]) == [ACC]
    assert validate_setting("banks.statement_branches", ["UGE-02"]) == ["UGE-02"]
    assert validate_setting("banks.formats", {"sqb": "canonical"}) == {"sqb": "canonical"}
    bad: list[tuple[str, Any]] = [
        ("banks.accounts", [ACC, ACC]),
        ("banks.accounts", [{**ACC, "code": "20210000900100000001"}]),  # ochiq raqam emas, kod
        ("banks.accounts", [{**ACC, "bank_code": "citi"}]),
        ("banks.accounts", [{**ACC, "extra": 1}]),
        ("banks.statement_branches", ["UGE-02", "UGE-02"]),
        ("banks.formats", {"citi": "canonical"}),
        ("banks.formats", {"sqb": "mt940"}),
        ("fx.currencies", ["usd"]),
        ("fx.currencies", ["UZS"]),
        ("fx.currencies", []),
        ("fx.lookback_days", 0),
        ("etl.cbu_cron", "daily"),
    ]
    for key, value in bad:
        with pytest.raises(ValueError):
            validate_setting(key, value)


def test_bank_account_model() -> None:
    account = BankAccount.model_validate(ACC)
    assert (account.code, account.last4) == ("BA-0123456789abcdef", "0001")


def test_telegram_settings() -> None:
    base = get_settings()
    off = base.model_copy(update={"telegram_bot_token": SecretStr(""),
                                  "telegram_chat_ids": SecretStr("")})
    assert off.telegram_enabled is False and off.telegram_chats == []
    on = base.model_copy(update={"telegram_bot_token": SecretStr(TOKEN),
                                 "telegram_chat_ids": SecretStr("-1001234567890, 42")})
    assert on.telegram_enabled is True and on.telegram_chats == [-1001234567890, 42]
    assert not any("telegram" in p for p in on.problems())
    bad = base.model_copy(update={"telegram_bot_token": SecretStr("nope"),
                                  "telegram_chat_ids": SecretStr("@channel")})
    with pytest.raises(ConfigError):
        _ = bad.telegram_chats
    problems = bad.problems()
    assert any("telegram_chat_ids" in p for p in problems)
    assert any("telegram_bot_token" in p for p in problems)
    assert TOKEN not in " ".join(problems) and "nope" not in " ".join(problems)
    proxy = base.model_copy(update={"egress_proxy": "socks5://10.0.0.1:1080"})
    assert any("EGRESS_PROXY" in p for p in proxy.problems())


def test_new_notification_kind_and_audit_action() -> None:
    assert Notification("bank_rows_rejected", "s", "b").kind == "bank_rows_rejected"
    assert AuditAction.TELEGRAM_SUMMARY_SENT.value == "notify.telegram.summary"
```

`backend/tests/test_reference.py` — `test_settings_defaults_and_validation` dagi `assert set(DEFAULT_SETTINGS) == {…}` to'plamiga quyidagi 8 kalitni qo'shing (qolganlari o'zgarmaydi):
```python
        "banks.accounts", "banks.statement_branches", "banks.formats", "etl.banks_cron",
        "etl.cbu_cron", "fx.currencies", "fx.lookback_days", "telegram.summary_cron",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_s2_prereq.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.banks'`.

- [ ] **Step 3: Banklar reyestri**

`backend/app/etl/banks/__init__.py`:
```python
"""Bank ko'chirmalari integratsiyasi (TZ 8 «Банки», S2 spec 3.2)."""
```

`backend/app/etl/banks/registry.py`:
```python
"""Banklar reyestri (TZ 8 «Банки») va hisob moslashtirishi modeli — sof konstantalar.

Katalog nomi = bank kodi: /data/import/banks/<kod>/. Hisob raqami bu yerda saqlanmaydi —
faqat `BA-<HMAC[:16]>` kodi va oxirgi 4 raqam (S2 spec 3.2).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

BANKS: dict[str, str] = {
    "sqb": "Узпромстройбанк",
    "nbu": "Национальный банк",
    "asaka": "Асакабанк",
    "ipoteka": "Ипотека-банк",
    "xalq": "Халк банк",
}
ADAPTER_NAMES: tuple[str, ...] = ("canonical",)
ACCOUNT_CODE_PATTERN = r"^BA-[0-9a-f]{16}$"


def _known_bank(code: str) -> str:
    if code not in BANKS:
        raise ValueError(f"noma'lum bank kodi: {code!r}")
    return code


class BankAccount(BaseModel):
    """Hisob ↔ (bank, filial, valyuta, 1C schyoti) moslashtirishi (`banks.accounts`)."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    code: Annotated[str, Field(pattern=ACCOUNT_CODE_PATTERN)]
    bank_code: Annotated[str, AfterValidator(_known_bank)]
    branch_code: Annotated[str, Field(min_length=1, max_length=32)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    gl_account: Annotated[str, Field(pattern=r"^\d{4}$")]
    last4: Annotated[str, Field(pattern=r"^\d{4}$")]
```

- [ ] **Step 4: Sozlamalar**

`backend/app/dwh/reference.py` — importlarga qo'shing (mavjudlari saqlanadi; `re` bo'lmasa — qo'shing):
```python
import re

from app.etl.banks.registry import ADAPTER_NAMES, BANKS, BankAccount
```
`DEFAULT_SETTINGS` dan OLDIN qo'shing:
```python
def _bank_accounts(value: list[BankAccount]) -> list[dict[str, str]]:
    codes = [a.code for a in value]
    if len(set(codes)) != len(codes):
        raise ValueError("banks.accounts: hisob kodi takrorlangan")
    return [a.model_dump() for a in value]


def _branch_codes(value: list[str]) -> list[str]:
    if len(set(value)) != len(value) or any(not c or len(c) > 32 for c in value):
        raise ValueError("filial kodlari bo'sh, uzun yoki takrorlangan")
    return list(value)


def _bank_formats(value: dict[str, str]) -> dict[str, str]:
    unknown = set(value) - set(BANKS)
    if unknown:
        raise ValueError(f"noma'lum bank: {sorted(unknown)}")
    bad = sorted({v for v in value.values() if v not in ADAPTER_NAMES})
    if bad:
        raise ValueError(f"noma'lum format adapteri: {bad}")
    return dict(value)


def _currencies(value: list[str]) -> list[str]:
    if not value or len(set(value)) != len(value) or "UZS" in value \
            or any(not re.fullmatch(r"[A-Z]{3}", c) for c in value):
        raise ValueError("fx.currencies: ISO 4217 kodlari (UZS emas), takrorsiz")
    return list(value)
```
`DEFAULT_SETTINGS` lug'ati oxiriga qo'shing:
```python
    "banks.accounts": [],
    "banks.statement_branches": [],
    "banks.formats": dict.fromkeys(BANKS, "canonical"),
    "etl.banks_cron": "30 9,12,15,18 * * *",
    "etl.cbu_cron": "0 8 * * *",
    "fx.currencies": ["USD", "EUR", "CNY", "RUB", "GBP", "JPY", "CHF", "KZT", "KRW"],
    "fx.lookback_days": 7,
    "telegram.summary_cron": "30 8 * * *",
```
`SETTING_TYPES` lug'ati oxiriga qo'shing:
```python
    "banks.accounts": TypeAdapter(
        Annotated[list[BankAccount], AfterValidator(_bank_accounts)]),
    "banks.statement_branches": TypeAdapter(
        Annotated[list[str], AfterValidator(_branch_codes)]),
    "banks.formats": TypeAdapter(Annotated[dict[str, str], AfterValidator(_bank_formats)]),
    "etl.banks_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "etl.cbu_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
    "fx.currencies": TypeAdapter(Annotated[list[str], AfterValidator(_currencies)]),
    "fx.lookback_days": TypeAdapter(Annotated[int, Field(strict=True, ge=1, le=31)]),
    "telegram.summary_cron": TypeAdapter(Annotated[str, AfterValidator(_cron)]),
```

- [ ] **Step 5: Konfiguratsiya, xabarnoma turi, audit harakati**

`backend/app/core/config.py` — importlarga `import re` qo'shing; `KEY_FIELDS = …` qatoridan keyin:
```python
# Telegram Bot API tokeni: "<bot id>:<35+ belgi>" — formati tekshiriladi,
# qiymati hech qayerga yozilmaydi.
TELEGRAM_TOKEN_RE = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,64}$")
_CHAT_ID_RE = re.compile(r"^-?\d{1,20}$")
```
`Settings` sinfida S1'ning `onec_max_bytes` qatoridan keyin qo'shing:
```python
    # S2 (spec 3, 9, 10): tashqi so'rovlar faqat worker'dan;
    # proksi — ixtiyoriy korporativ HTTP proksi.
    egress_proxy: str = ""
    cbu_enabled: bool = False
    cbu_base_url: str = "https://cbu.uz"
    bank_inbox_dir: str = "/data/import/banks"
    bank_archive_dir: str = "/data/archive/banks"
    # Docker secrets: telegram_bot_token, telegram_chat_ids (vergul bilan ajratilgan butun sonlar).
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_ids: SecretStr = SecretStr("")
    telegram_api_base: str = "https://api.telegram.org"
```
`redis_url` property'sidan keyin qo'shing:
```python
    @property
    def telegram_chats(self) -> list[int]:
        parts = [p for p in re.split(r"[\s,]+", self.telegram_chat_ids.get_secret_value()) if p]
        if any(not _CHAT_ID_RE.fullmatch(p) for p in parts):
            raise ConfigError("telegram_chat_ids: faqat butun sonlar, vergul bilan ajratilgan")
        return [int(p) for p in parts]

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token.get_secret_value()
                    and self.telegram_chat_ids.get_secret_value().strip())
```
`problems()` ichida oxirgi `return out` qatoridan OLDIN qo'shing:
```python
        if self.telegram_enabled:
            try:
                _ = self.telegram_chats
            except ConfigError as exc:
                out.append(str(exc))
            if not TELEGRAM_TOKEN_RE.fullmatch(self.telegram_bot_token.get_secret_value()):
                out.append("telegram_bot_token formati noto'g'ri")
        if self.egress_proxy and not self.egress_proxy.startswith(("http://", "https://")):
            out.append("EGRESS_PROXY http:// yoki https:// bilan boshlanishi kerak")
```

`backend/app/etl/notify.py` — `Kind` qatorini almashtiring:
```python
Kind = Literal["etl_failed", "etl_quality", "control_totals", "stale_data", "bank_rows_rejected"]
```

`backend/app/audit/service.py` — `AuditAction` ichida `RLS_VIOLATION` qatoridan oldin qo'shing:
```python
    TELEGRAM_SUMMARY_SENT = "notify.telegram.summary"
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_s2_prereq.py tests/test_reference.py tests/test_config.py tests/test_notify.py -v`
Expected: barcha testlar passed. `$TEST ruff check app tests` va `$TEST mypy app` — xatosiz.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(s2): banklar reyestri, S2 sozlamalari, Telegram/egress konfiguratsiyasi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Kredit agregatlari (0011) va `FileConnector` — kelajak grafigi

**Files:**
- Create: `backend/migrations/versions/0011_mart_loans.py`, `backend/app/dwh/loan_aggregates.py`, `backend/tests/s2_helpers.py`
- Modify: `backend/app/dwh/aggregates.py` (oxirida import), `backend/app/etl/file_connector.py` (`extract`)
- Test: `backend/tests/test_loan_aggregates.py`

**Interfaces:**
- Consumes: `_MONTHS`, `register`, `Aggregate`, `BuildParams.bind` (`:build_id, :date_from, :as_of, :from_id`), `Target.forward`, `builds`, `tests.etl_helpers.*`, `tests.s1_helpers.rebuild` (`SCENARIO_PARAMS`: as_of 2026-09-24, date_from 2025-01-01), `Runner`, `FileConnector`.
- Produces:
  - `mart|pub.agg_loan_month (branch_id > 0, month_id, loan_id, snap_date_id, loan_code, creditor, project, currency, rate, grace_until, maturity, fx_rate, original_cur, outstanding_cur, outstanding)`; `mart|pub.agg_loan_schedule (branch_id > 0, loan_id, month_id, date_id, principal_cur, interest_cur, balance_cur)`.
  - `app.dwh.loan_aggregates`: `LOAN_SCHEDULE`, `LOAN_MONTH` (ro'yxat tartibi shu).
  - `FileConnector.extract` — `forward` maqsad qatorlari oyna bo'yicha kesilmaydi.
  - `tests.s2_helpers`: `FX = "XTL"`, `LoanScenario(source, tag, branch_id, branch_code, empty_branch_id, run_id, build_id, loan_a, loan_b)`, `loan_rows(tag)`, `loan_scenario(source, *, publish=False) -> LoanScenario`, `put_setting(key, value)`, `put_rule(code, **changes)`, `kredity_branch_role() -> str`.

Ssenariy (as_of = 2026-09-24; summalar — kredit valyutasida, mln) — 3–5-vazifa testlari shu qiymatlardan:

| Kredit | Valyuta, stavka | Grafik (sana: asosiy qarz / foiz / qoldiq) |
|---|---|---|
| A `LA-<tag>` | `XTL`, 5%, imtiyoz 2026-01-01, muddat 2028-12-31 | 2026-03-15: 1 / 0,5 / 9; 2026-09-15: 1 / 0,46 / 8; 2027-03-15: 1 / 0,4 / 7; 2028-03-15: 7 / 0,35 / 0 |
| B `LB-<tag>` | `UZS`, 18%, imtiyozsiz, muddat 2027-12-31 | 2026-06-10: 100 / 30 / 400; 2026-10-10: 100 / 18 / 300; 2027-10-10: 300 / 18 / 0 |
| C `LC-<tag>` | `UZS`, grafik yo'q | — (agregatlarga tushmaydi) |

`fx_rate XTL`: 2026-08-01 — 1000, 2026-09-01 — 1100. Ikkinchi filial `T-<tag>E` — kreditsiz.
Kutilgan: `m08` (D = 31.08): A qoldiq 9 × 1000 = 9000, B 400 → portfel 9400; `m09` (D = 24.09): A 8 × 1100 = 8800; `m01`: XTL kursi yo'q → A `outstanding = NULL`, B 500.

- [ ] **Step 1: Test yordamchisi — ssenariy**

`backend/tests/s2_helpers.py`:
```python
"""S2 testlari uchun qo'lda hisoblanadigan kredit ssenariysi (jadval — rejaning 2-vazifasida)
va umumiy yordamchilar (sozlama/qoida versiyalari, filial doirasidagi «Кредиты» roli)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

from app.auth.models import Role, RolePermission
from app.core.db import get_engine, new_session
from app.etl.db import etl_transaction
from tests.etl_helpers import branch_row, merge_all, new_tag, open_run, stage
from tests.s1_helpers import rebuild

FX = "XTL"  # ISO 4217 da yo'q test kodi (S1 ssenariysidagi XTS bilan to'qnashmaydi)
KREDITY_BRANCH_ROLE = "t_kredity_branch"


@dataclass(frozen=True, slots=True)
class LoanScenario:
    source: str
    tag: str
    branch_id: int
    branch_code: str
    empty_branch_id: int
    run_id: int
    build_id: int
    loan_a: int
    loan_b: int


def loan_rows(tag: str) -> dict[str, list[dict[str, Any]]]:
    branch = branch_row(tag)
    empty = branch_row(f"{tag}E", name=f"Тестовая ГЭС без кредитов {tag}")
    code = branch["code"]
    a, b, c = f"LA-{tag}", f"LB-{tag}", f"LC-{tag}"

    def row(src_id: str, loan: str, day: int, principal: float, interest: float,
            balance: float) -> dict[str, Any]:
        return {"doc_type": "loan_schedule", "src_id": src_id, "date_id": day,
                "branch_code": code, "loan_code": loan, "principal": principal,
                "interest": interest, "balance": balance}

    return {
        "dim_branch": [branch, empty],
        "dim_loan": [
            {"code": a, "creditor": f"Тест кредитор А {tag}", "project": "Модернизация ГЭС",
             "currency": FX, "rate": 0.05, "grace_until": "2026-01-01",
             "maturity": "2028-12-31", "amount_uzs": 10000, "branch_code": code},
            {"code": b, "creditor": f"Тест кредитор Б {tag}", "project": "Оборотные средства",
             "currency": "UZS", "rate": 0.18, "grace_until": None, "maturity": "2027-12-31",
             "amount_uzs": 500, "branch_code": code},
            {"code": c, "creditor": f"Тест кредитор В {tag}", "project": "Без графика",
             "currency": "UZS", "rate": 0.1, "grace_until": None, "maturity": "2030-12-31",
             "amount_uzs": 50, "branch_code": code},
        ],
        "fx_rate": [{"currency": FX, "date_id": 20260801, "rate": 1000},
                    {"currency": FX, "date_id": 20260901, "rate": 1100}],
        "fact_loan_schedule": [
            row("a1", a, 20260315, 1, 0.5, 9), row("a2", a, 20260915, 1, 0.46, 8),
            row("a3", a, 20270315, 1, 0.4, 7), row("a4", a, 20280315, 7, 0.35, 0),
            row("b1", b, 20260610, 100, 30, 400), row("b2", b, 20261010, 100, 18, 300),
            row("b3", b, 20271010, 300, 18, 0),
        ],
    }


def loan_scenario(source: str, *, publish: bool = False) -> LoanScenario:
    tag = new_tag()
    run_id = open_run(source)
    stage(run_id, source, loan_rows(tag))
    merge_all(run_id, source)
    build_id = rebuild(run_id, publish=publish)
    with etl_transaction() as conn:
        branches = dict(conn.execute(text(
            "SELECT code, branch_id FROM dwh.dim_branch WHERE code IN (:a, :b)"),
            {"a": f"T-{tag}", "b": f"T-{tag}E"}).all())
        loans = dict(conn.execute(text(
            "SELECT code, loan_id FROM dwh.dim_loan WHERE code IN (:a, :b)"),
            {"a": f"LA-{tag}", "b": f"LB-{tag}"}).all())
    return LoanScenario(source, tag, int(branches[f"T-{tag}"]), f"T-{tag}",
                        int(branches[f"T-{tag}E"]), run_id, build_id, int(loans[f"LA-{tag}"]),
                        int(loans[f"LB-{tag}"]))


def put_setting(key: str, value: object) -> None:
    """core.settings ga yangi versiya (testlarda sozlamani vaqtincha o'zgartirish uchun)."""
    with get_engine("app").begin() as conn:
        version = conn.execute(text(
            "SELECT coalesce(max(version), 0) FROM core.settings WHERE key = :k"),
            {"k": key}).scalar_one()
        conn.execute(text("UPDATE core.settings SET is_current = false "
                          "WHERE key = :k AND is_current"), {"k": key})
        conn.execute(text("INSERT INTO core.settings (key, version, value) "
                          "VALUES (:k, :v, CAST(:val AS jsonb))"),
                     {"k": key, "v": version + 1, "val": json.dumps(value, ensure_ascii=False)})


def put_rule(code: str, **changes: Any) -> None:
    """core.alert_rules ga yangi versiya (S1 testidagi yordamchi bilan bir xil)."""
    with get_engine("app").begin() as conn:
        row = conn.execute(text("SELECT * FROM core.alert_rules WHERE code = :c AND is_current"),
                           {"c": code}).mappings().one()
        data = {**dict(row), **changes}
        conn.execute(text("UPDATE core.alert_rules SET is_current = false "
                          "WHERE code = :c AND is_current"), {"c": code})
        conn.execute(text(
            "INSERT INTO core.alert_rules (code, version, title, section, page, threshold, level, "
            "enabled) VALUES (:code, :v, :title, :section, :page, CAST(:th AS jsonb), :level, "
            ":en)"),
            {"code": code, "v": row["version"] + 1, "title": data["title"],
             "section": data["section"], "page": data["page"],
             "th": json.dumps(data["threshold"]), "level": data["level"],
             "en": data["enabled"]})


def kredity_branch_role() -> str:
    """Filial doirasidagi (scope_all = false) va «Кредиты»ni ko'ra oladigan test roli —
    seed rollarida bunday rol yo'q (spec_kazna hamma filialni ko'radi)."""
    with new_session() as s:
        exists = s.execute(select(Role.id).where(Role.code == KREDITY_BRANCH_ROLE)).scalar()
        if exists is None:
            role = Role(code=KREDITY_BRANCH_ROLE, name="Тест: кредиты филиала", scope_all=False)
            s.add(role)
            s.flush()
            s.add(RolePermission(role_id=role.id, permission_code="section:kredity:view"))
            s.commit()
    return KREDITY_BRANCH_ROLE
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_loan_aggregates.py`:
```python
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import apply_rls, new_session
from app.dwh import builds
from app.etl.db import etl_transaction
from app.etl.file_connector import FileConnector
from app.etl.runner import Runner
from app.etl.types import Mode
from tests.etl_helpers import (
    TEST_AS_OF,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s1_helpers import rebuild
from tests.s2_helpers import LoanScenario, loan_rows, loan_scenario

TABLES = ("agg_loan_month", "agg_loan_schedule")


@pytest.fixture
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source)
    purge_source(source)


def _rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _opt(value: Any) -> float | None:
    return None if value is None else float(value)


def test_loan_month_snapshots(sc: LoanScenario) -> None:
    rows = _rows("SELECT month_id, loan_id, snap_date_id, rate, fx_rate, original_cur, "
                 "outstanding_cur, outstanding FROM mart.agg_loan_month WHERE build_id = :b "
                 "AND branch_id = :br AND month_id IN (202601, 202608, 202609)",
                 b=sc.build_id, br=sc.branch_id)
    got = {(r["month_id"], r["loan_id"]): (r["snap_date_id"], float(r["rate"]), _opt(r["fx_rate"]),
                                           float(r["original_cur"]), float(r["outstanding_cur"]),
                                           _opt(r["outstanding"])) for r in rows}
    a, b = sc.loan_a, sc.loan_b
    assert got == {
        (202601, a): (20260131, 0.05, None, 10.0, 10.0, None),
        (202601, b): (20260131, 0.18, 1.0, 500.0, 500.0, 500.0),
        (202608, a): (20260831, 0.05, 1000.0, 10.0, 9.0, 9000.0),
        (202608, b): (20260831, 0.18, 1.0, 500.0, 400.0, 400.0),
        (202609, a): (20260924, 0.05, 1100.0, 10.0, 8.0, 8800.0),
        (202609, b): (20260924, 0.18, 1.0, 500.0, 400.0, 400.0),
    }
    meta = _rows("SELECT loan_code, creditor, currency, grace_until, maturity "
                 "FROM mart.agg_loan_month WHERE build_id = :b AND loan_id = :loan "
                 "AND month_id = 202608", b=sc.build_id, loan=a)[0]
    assert meta["loan_code"] == f"LA-{sc.tag}" and meta["currency"] == "XTL"
    assert meta["creditor"] == f"Тест кредитор А {sc.tag}"
    assert (meta["grace_until"], meta["maturity"]) == (date(2026, 1, 1), date(2028, 12, 31))


def test_loan_without_schedule_is_skipped(sc: LoanScenario) -> None:
    assert _rows("SELECT 1 FROM mart.agg_loan_month WHERE build_id = :b AND loan_code = :c",
                 b=sc.build_id, c=f"LC-{sc.tag}") == []


def test_schedule_rows_copied(sc: LoanScenario) -> None:
    rows = _rows("SELECT month_id, date_id, principal_cur, interest_cur, balance_cur "
                 "FROM mart.agg_loan_schedule WHERE build_id = :b AND branch_id = :br "
                 "ORDER BY date_id", b=sc.build_id, br=sc.branch_id)
    assert [(r["date_id"], float(r["principal_cur"]), float(r["interest_cur"]),
             float(r["balance_cur"])) for r in rows] == [
        (20260315, 1.0, 0.5, 9.0), (20260610, 100.0, 30.0, 400.0), (20260915, 1.0, 0.46, 8.0),
        (20261010, 100.0, 18.0, 300.0), (20270315, 1.0, 0.4, 7.0), (20271010, 300.0, 18.0, 0.0),
        (20280315, 7.0, 0.35, 0.0)]
    assert rows[-1]["month_id"] == 202803


def test_rate_version_applies_from_change_date(sc: LoanScenario) -> None:
    run = open_run(sc.source)
    changed = {**loan_rows(sc.tag)["dim_loan"][0], "rate": 0.06}
    stage(run, sc.source, {"dim_loan": [changed]})
    merge_all(run, sc.source, as_of=date(2026, 9, 1))
    build_id = rebuild(run)
    rows = _rows("SELECT month_id, rate FROM mart.agg_loan_month WHERE build_id = :b "
                 "AND loan_id = :loan AND month_id IN (202608, 202609)", b=build_id, loan=sc.loan_a)
    assert {r["month_id"]: float(r["rate"]) for r in rows} == {202608: 0.05, 202609: 0.06}


def test_rls_and_failed_build(sc: LoanScenario) -> None:
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


def test_file_connector_keeps_future_loan_rows(tmp_path: Path) -> None:
    source = new_source()
    tag = new_tag()
    try:
        (tmp_path / "dim_branch.csv").write_text(
            "code;name;short_name;kind;capacity_mw;sort_order\n"
            f"T-{tag};Тестовая ГЭС;Т;ges;10;99\n", encoding="utf-8")
        (tmp_path / "dim_loan.csv").write_text(
            "code;creditor;project;currency;rate;grace_until;maturity;amount_uzs;branch_code\n"
            f"LF-{tag};Банк;Проект;UZS;0.1;;2030-12-31;100;T-{tag}\n", encoding="utf-8")
        (tmp_path / "fact_loan_schedule.csv").write_text(
            "doc_type;src_id;date;branch_code;loan_code;principal;interest;balance\n"
            f"loan_schedule;f1;2026-03-15;T-{tag};LF-{tag};10;5;90\n"
            f"loan_schedule;f2;2029-03-15;T-{tag};LF-{tag};90;5;0\n", encoding="utf-8")
        # Ikkinchi to'liq yuklash ham kelajak qatorini o'chirmasligi kerak (forward almashtirish).
        for _ in range(2):
            result = Runner(FileConnector(tmp_path, source=source), mode=Mode.FULL,
                            today=TEST_AS_OF, sleep=lambda _: None).run()
            assert result.status == "success", result
        with etl_transaction() as conn:
            ids = set(conn.execute(text("SELECT src_id FROM dwh.fact_loan_schedule "
                                        "WHERE src_system = :s"), {"s": source}).scalars())
        assert ids == {"f1", "f2"}
    finally:
        purge_source(source)
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_loan_aggregates.py -v`
Expected: FAIL — `relation "mart.agg_loan_month" does not exist` (va `test_file_connector_keeps_future_loan_rows` — `{'f1'} != {'f1', 'f2'}`).

- [ ] **Step 4: 0011 migratsiyasi**

`backend/migrations/versions/0011_mart_loans.py`:
```python
"""S2: kreditlar — oy × kredit snapshot'i va to'lov grafigi (valyutada)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-25
"""

from alembic import op

revision = "0011"
down_revision = "0010"  # `alembic heads` boshqa bo'lsa — shu qiymatni joriy head'ga moslang
branch_labels = None
depends_on = None

MONEY = "numeric(20,2) NOT NULL DEFAULT 0"
ACTIVE = "(SELECT d.active_build_id FROM core.data_version d WHERE d.id = 1)"
BUILD = "build_id bigint NOT NULL REFERENCES core.builds (build_id) ON DELETE CASCADE"
TABLES = ("agg_loan_month", "agg_loan_schedule")

STATEMENTS = [
    f"""
    CREATE TABLE mart.agg_loan_month (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      month_id integer NOT NULL,
      loan_id integer NOT NULL,
      snap_date_id integer NOT NULL,
      loan_code varchar(32) NOT NULL,
      creditor varchar(200) NOT NULL,
      project varchar(300) NOT NULL,
      currency char(3) NOT NULL,
      rate numeric(8,5) NOT NULL,
      grace_until date,
      maturity date NOT NULL,
      fx_rate numeric(18,6),
      original_cur numeric(20,2) NOT NULL,
      outstanding_cur numeric(20,2) NOT NULL,
      outstanding numeric(20,2),
      PRIMARY KEY (build_id, branch_id, month_id, loan_id)
    )
    """,
    f"""
    CREATE TABLE mart.agg_loan_schedule (
      {BUILD},
      branch_id integer NOT NULL CHECK (branch_id > 0),
      loan_id integer NOT NULL,
      month_id integer NOT NULL,
      date_id integer NOT NULL,
      principal_cur {MONEY},
      interest_cur {MONEY},
      balance_cur {MONEY},
      PRIMARY KEY (build_id, branch_id, loan_id, date_id)
    )
    """,
    f"""
    CREATE VIEW pub.agg_loan_month WITH (security_invoker = true) AS
    SELECT a.branch_id, a.month_id, a.loan_id, a.snap_date_id, a.loan_code, a.creditor,
           a.project, a.currency, a.rate, a.grace_until, a.maturity, a.fx_rate, a.original_cur,
           a.outstanding_cur, a.outstanding
    FROM mart.agg_loan_month a WHERE a.build_id = {ACTIVE}
    """,
    f"""
    CREATE VIEW pub.agg_loan_schedule WITH (security_invoker = true) AS
    SELECT a.branch_id, a.loan_id, a.month_id, a.date_id, a.principal_cur, a.interest_cur,
           a.balance_cur
    FROM mart.agg_loan_schedule a WHERE a.build_id = {ACTIVE}
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

`backend/app/dwh/loan_aggregates.py`:
```python
"""S2 kredit agregatlari (spec 5) — 2-reja freymvorkida ro'yxatdan o'tadi.

`app.dwh.aggregates` oxirida (S1 treasury_aggregates'dan keyin) import qilinadi.
Summalar kredit valyutasida (mln birlik); `outstanding` = valyutadagi qoldiq × snapshot
sanasidagi ЦБ kursi (UZS = 1; kurs yo'q → NULL, spec 4).
"""

from __future__ import annotations

from app.dwh.aggregates import _MONTHS, Aggregate, register

# To'lov grafigi: kredit × sana (bir sanada bir nechta qator bo'lsa — yig'indi,
# qoldiq — eng kichigi).
# date_from dan keyingi hamma qatorlar (kelajak ham) — «График погашения» va yaqin to'lovlar uchun.
_LOAN_SCHEDULE = """
INSERT INTO mart.agg_loan_schedule (build_id, branch_id, loan_id, month_id, date_id, principal_cur,
                                    interest_cur, balance_cur)
SELECT :build_id, s.branch_id, s.loan_id, d.month_id, s.date_id, sum(s.principal),
       sum(s.interest), min(s.balance)
FROM dwh.fact_loan_schedule s
JOIN dwh.dim_date d ON d.date_id = s.date_id
WHERE s.date_id >= :from_id
GROUP BY s.branch_id, s.loan_id, d.month_id, s.date_id
"""

# Oy × kredit snapshot'i (snap = oyning as_of bilan kesilgan oxirgi kuni): qoldiq — snap
# gacha oxirgi
# grafik qatorining `balance`i, qator bo'lmasa boshlang'ich summa (birinchi qatorning balance +
# principal). Qator faqat qoldiq > 0 yoki o'sha yilda to'lov bo'lsa. Stavka — dim_loan_version
# (SCD-2) snap sanasida amaldagisi.
_LOAN_MONTH = f"""
INSERT INTO mart.agg_loan_month (build_id, branch_id, month_id, loan_id, snap_date_id, loan_code,
                                 creditor, project, currency, rate, grace_until, maturity, fx_rate,
                                 original_cur, outstanding_cur, outstanding)
WITH {_MONTHS},
sched AS (
  SELECT s.loan_id, s.branch_id, s.date_id, sum(s.principal) AS principal,
         min(s.balance) AS balance
  FROM dwh.fact_loan_schedule s
  GROUP BY s.loan_id, s.branch_id, s.date_id),
first_row AS (
  SELECT DISTINCT ON (loan_id) loan_id, branch_id, balance + principal AS original
  FROM sched ORDER BY loan_id, date_id),
snap AS (
  SELECT f.loan_id, f.branch_id, f.original, m.month_id, m.end_id,
         coalesce((SELECT x.balance FROM sched x
                   WHERE x.loan_id = f.loan_id AND x.date_id <= m.end_id
                   ORDER BY x.date_id DESC LIMIT 1), f.original) AS outstanding_cur,
         EXISTS (SELECT 1 FROM sched x WHERE x.loan_id = f.loan_id
                 AND x.date_id / 10000 = m.month_id / 100) AS active_year
  FROM first_row f CROSS JOIN months m)
SELECT :build_id, s.branch_id, s.month_id, l.loan_id, s.end_id, l.code, l.creditor, l.project,
       l.currency, coalesce(v.rate, l.rate), l.grace_until, l.maturity, fx.rate, s.original,
       s.outstanding_cur, round(s.outstanding_cur * fx.rate, 2)
FROM snap s
JOIN dwh.dim_loan l ON l.loan_id = s.loan_id
JOIN dwh.dim_date dd ON dd.date_id = s.end_id
LEFT JOIN LATERAL (
  SELECT lv.rate FROM dwh.dim_loan_version lv
  WHERE lv.loan_id = l.loan_id AND lv.rate IS NOT NULL AND lv.valid_from <= dd.date
    AND (lv.valid_to IS NULL OR lv.valid_to >= dd.date)
  ORDER BY lv.valid_from DESC LIMIT 1) v ON true
LEFT JOIN LATERAL (
  SELECT CASE WHEN l.currency = 'UZS' THEN 1::numeric ELSE (
    SELECT r.rate FROM dwh.fx_rate r
    WHERE r.currency = l.currency AND r.date_id <= s.end_id
    ORDER BY r.date_id DESC LIMIT 1) END AS rate) fx ON true
WHERE s.outstanding_cur > 0 OR s.active_year
"""

LOAN_SCHEDULE = register(Aggregate("agg_loan_schedule", (_LOAN_SCHEDULE,)))
LOAN_MONTH = register(Aggregate("agg_loan_month", (_LOAN_MONTH,)))
```

`backend/app/dwh/aggregates.py` — fayl OXIRIGA (S1'ning `treasury_aggregates` importidan keyin) qo'shing:
```python
from app.dwh import loan_aggregates  # noqa: E402, F401
```

- [ ] **Step 6: `FileConnector` — `forward` maqsadlar oynada kesilmaydi**

`backend/app/etl/file_connector.py` — `extract` ichidagi oyna shartini almashtiring:
```python
                # forward maqsad (reja, kredit grafigi) kelajak qatorlarini ham to'liq beradi —
                # oynadan keyingisini kesish ularni yo'qotadi (S2 spec 3.1).
                if target.kind == "fact" and not target.forward \
                        and row.get("date_id") is not None \
                        and not window.contains_id(int(row["date_id"])):
                    continue
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_loan_aggregates.py tests/test_aggregates_builds.py tests/test_file_connector.py tests/test_debt_calendar_aggregates.py -v`
Expected: barcha testlar passed.
Run: `$TEST pytest tests/test_synthetic.py tests/test_etl_runner.py -v`
Expected: passed (sintetik 8 kredit agregatlarga tushadi, sifat tekshiruvlari buzilmaydi).

- [ ] **Step 8: Commit**

```bash
git add backend
git commit -m "feat(dwh): kredit agregatlari (oy snapshot'i, grafik); FileConnector kelajak grafigini kesmaydi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Kredit so'rovlari va hisob-kitob — portfel, stavka, ulush, xizmat, grafik

**Files:**
- Create: `backend/app/sections/queries/loans.py`
- Test: `backend/tests/test_sections_loans.py`

**Interfaces:**
- Consumes: `pub.agg_loan_month`, `pub.agg_loan_schedule`, `pub.branches`, `BranchSel.rows`, `ReportPeriod` (`date_to`, `last_month`), `resolve_period`, `from_date_id`, `tests.s2_helpers.loan_scenario`.
- Produces (`app.sections.queries.loans`):
  - `UZS = "UZS"`, `HORIZON_YEARS = 10`.
  - `LoanSnap(loan_id, branch_id, branch_name, loan_code, creditor, project, currency, rate, grace_until, maturity, fx_rate, original_cur, outstanding_cur, outstanding)` + `.repaid_share -> float | None`, `.in_grace(day) -> bool`.
  - `LoanPayment(day, loan_id, creditor, project, branch_name, principal, interest)` + `.total -> float | None` (kursi yo'q — `None`).
  - `YearLoad(year, principal, interest)` + `.total`.
  - `LoanReport(as_of, loans, payments, portfolio, rate, fx_share, fx_amount, service, paid, missing_fx, years)` + `.has_loans`, `.paid_share`, `.upcoming`, `.next_payment`, `.peak`, `.by_currency() -> list[tuple[str, float]]`, `.by_creditor() -> list[tuple[str, float]]`.
  - `snapshots(db, sel, month) -> list[LoanSnap]` (qoldiq bo'yicha kamayish), `schedule(db, sel, month) -> list[LoanPayment]`, `compute_report(snaps, payments, as_of) -> LoanReport` (sof funksiya), `load_report(db, sel, period) -> LoanReport`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_sections_loans.py`:
```python
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.db import apply_rls, new_session
from app.sections.period import resolve_period
from app.sections.queries import loans
from app.sections.scope import BranchSel
from tests.etl_helpers import TEST_AS_OF, new_source, purge_source
from tests.s2_helpers import LoanScenario, loan_scenario


@pytest.fixture(scope="module")
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _report(db: Session, sc: LoanScenario, per: str) -> loans.LoanReport:
    return loans.load_report(db, BranchSel(sc.branch_id, all_scope=True),
                             resolve_period(per, TEST_AS_OF))


def test_closed_month_report(sc: LoanScenario, db: Session) -> None:
    r = _report(db, sc, "m08")
    assert r.as_of == date(2026, 8, 31) and r.has_loans
    assert [(x.loan_id, x.outstanding) for x in r.loans] == [(sc.loan_a, 9000.0),
                                                              (sc.loan_b, 400.0)]
    assert r.portfolio == 9400.0 and r.missing_fx == []
    assert r.rate == pytest.approx(522 / 9400)  # (9000 × 5% + 400 × 18%) / 9400
    assert r.fx_share == pytest.approx(9000 / 9400) and r.fx_amount == 9000.0
    assert (r.service, r.paid) == (3208.0, 1630.0)
    assert r.paid_share == pytest.approx(1630 / 3208)
    nxt = r.next_payment
    assert nxt is not None
    assert (nxt.day, nxt.principal, nxt.interest, nxt.total) == (date(2026, 9, 15), 1000.0,
                                                                  460.0, 1460.0)
    assert nxt.creditor == f"Тест кредитор А {sc.tag}"
    assert r.peak is not None and (r.peak.year, r.peak.total) == (2028, 7350.0)
    assert [(y.year, y.principal, y.interest) for y in r.years[:3]] == [
        (2026, 2200.0, 1008.0), (2027, 1300.0, 418.0), (2028, 7000.0, 350.0)]
    assert len(r.years) == 10 and r.years[-1].year == 2035 and r.years[-1].total == 0.0
    assert [(p.day, p.total) for p in r.upcoming] == [
        (date(2026, 9, 15), 1460.0), (date(2026, 10, 10), 118.0), (date(2027, 3, 15), 1400.0),
        (date(2027, 10, 10), 318.0), (date(2028, 3, 15), 7350.0)]
    assert r.by_currency() == [("XTL", 9000.0), ("UZS", 400.0)]
    assert r.by_creditor() == [(f"Тест кредитор А {sc.tag}", 9000.0),
                               (f"Тест кредитор Б {sc.tag}", 400.0)]
    a, b = r.loans
    assert a.repaid_share == pytest.approx(0.1) and b.repaid_share == pytest.approx(0.2)
    assert not a.in_grace(r.as_of) and a.in_grace(date(2025, 12, 31))


def test_open_month_uses_current_rate(sc: LoanScenario, db: Session) -> None:
    r = _report(db, sc, "m09")
    assert r.as_of == TEST_AS_OF and r.portfolio == 9200.0  # 8 × 1100 + 400
    assert (r.service, r.paid) == (3504.0, 3386.0)
    assert r.next_payment is not None and r.next_payment.day == date(2026, 10, 10)


def test_quarter_uses_period_end(sc: LoanScenario, db: Session) -> None:
    assert _report(db, sc, "q3").portfolio == _report(db, sc, "m09").portfolio


def test_missing_fx_is_flagged_not_zero(sc: LoanScenario, db: Session) -> None:
    r = _report(db, sc, "m01")
    assert r.missing_fx == ["XTL"]
    assert r.portfolio == 500.0 and r.fx_share == 0.0
    a = next(x for x in r.loans if x.loan_id == sc.loan_a)
    assert a.outstanding is None and a.outstanding_cur == 10.0
    # Kursi yo'q kreditning to'lovlari yig'indilarga kirmaydi, ro'yxatda summasiz ko'rinadi.
    assert (r.upcoming[0].day, r.upcoming[0].total) == (date(2026, 3, 15), None)
    assert r.service == 248.0


def test_branch_without_loans(sc: LoanScenario, db: Session) -> None:
    r = loans.load_report(db, BranchSel(sc.empty_branch_id, True),
                          resolve_period("m08", TEST_AS_OF))
    assert not r.has_loans and r.loans == [] and r.payments == []
    assert (r.portfolio, r.rate, r.fx_share, r.next_payment, r.peak) == (None, None, None,
                                                                         None, None)
    assert r.paid_share is None and r.service == 0.0


def test_limited_scope_sees_only_own_loans(sc: LoanScenario) -> None:
    with new_session() as s:
        apply_rls(s, frozenset({sc.branch_id}))
        r = loans.load_report(s, BranchSel(None, all_scope=False),
                              resolve_period("m08", TEST_AS_OF))
    assert {x.branch_id for x in r.loans} == {sc.branch_id} and r.portfolio == 9400.0
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sections_loans.py -v`
Expected: FAIL — `ImportError: cannot import name 'loans' from 'app.sections.queries'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/sections/queries/loans.py`:
```python
"""Kreditlar (TZ 4 «Кредиты») — faqat pub.agg_loan_month va pub.agg_loan_schedule dan.

Hisobot sanasi D = davr oxiri (ochiq davrda — bugun). Valyutadagi summalar D sanasi kursida
(snapshot'dagi fx_rate) so'mga o'giriladi; kursi yo'q kreditlar yig'indilarga kirmaydi va
`missing_fx` da qaytadi (S2 spec 4). Kreditlar soni kichik — yig'indilar Python'da.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dwh.dates import from_date_id
from app.sections.period import ReportPeriod
from app.sections.scope import BranchSel

UZS = "UZS"
HORIZON_YEARS = 10  # TZ 5: «График погашения 2026–2035»


def _opt(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def _convert(amount: Decimal, fx_rate: Decimal | None) -> float | None:
    return None if fx_rate is None else round(float(amount * fx_rate), 2)


@dataclass(frozen=True, slots=True)
class LoanSnap:
    loan_id: int
    branch_id: int
    branch_name: str
    loan_code: str
    creditor: str
    project: str
    currency: str
    rate: float
    grace_until: date | None
    maturity: date
    fx_rate: float | None
    original_cur: float
    outstanding_cur: float
    outstanding: float | None

    @property
    def repaid_share(self) -> float | None:
        """Доля погашения = 1 − qoldiq / boshlang'ich summa (kredit valyutasida)."""
        if self.original_cur <= 0:
            return None
        return round(1 - self.outstanding_cur / self.original_cur, 6)

    def in_grace(self, day: date) -> bool:
        return self.grace_until is not None and self.grace_until > day


@dataclass(frozen=True, slots=True)
class LoanPayment:
    day: date
    loan_id: int
    creditor: str
    project: str
    branch_name: str
    principal: float | None
    interest: float | None

    @property
    def total(self) -> float | None:
        if self.principal is None or self.interest is None:
            return None
        return round(self.principal + self.interest, 2)


@dataclass(frozen=True, slots=True)
class YearLoad:
    year: int
    principal: float
    interest: float

    @property
    def total(self) -> float:
        return round(self.principal + self.interest, 2)


@dataclass(frozen=True, slots=True)
class LoanReport:
    as_of: date
    loans: list[LoanSnap]
    payments: list[LoanPayment]
    portfolio: float | None
    rate: float | None
    fx_share: float | None
    fx_amount: float
    service: float
    paid: float
    missing_fx: list[str]
    years: list[YearLoad]

    @property
    def has_loans(self) -> bool:
        return bool(self.loans)

    @property
    def paid_share(self) -> float | None:
        return None if self.service <= 0 else self.paid / self.service

    @property
    def upcoming(self) -> list[LoanPayment]:
        return [p for p in self.payments if p.day > self.as_of]

    @property
    def next_payment(self) -> LoanPayment | None:
        upcoming = self.upcoming
        return upcoming[0] if upcoming else None

    @property
    def peak(self) -> YearLoad | None:
        best = max(self.years, key=lambda y: y.total, default=None)
        return best if best is not None and best.total > 0 else None

    def _group(self, key: str) -> list[tuple[str, float]]:
        totals: dict[str, float] = {}
        for loan in self.loans:
            if loan.outstanding is not None:
                name = loan.currency if key == "currency" else loan.creditor
                totals[name] = round(totals.get(name, 0.0) + loan.outstanding, 2)
        return sorted(totals.items(), key=lambda item: (-item[1], item[0]))

    def by_currency(self) -> list[tuple[str, float]]:
        return self._group("currency")

    def by_creditor(self) -> list[tuple[str, float]]:
        return self._group("creditor")


def snapshots(db: Session, sel: BranchSel, month: int) -> list[LoanSnap]:
    where, params = sel.rows("a.branch_id")
    rows = db.execute(text(
        "SELECT a.loan_id, a.branch_id, b.name AS branch_name, a.loan_code, a.creditor, "
        "a.project, a.currency, a.rate, a.grace_until, a.maturity, a.fx_rate, a.original_cur, "
        "a.outstanding_cur, a.outstanding "
        "FROM pub.agg_loan_month a JOIN pub.branches b ON b.branch_id = a.branch_id "
        f"WHERE a.month_id = :m AND {where} "
        "ORDER BY a.outstanding DESC NULLS LAST, a.loan_id"), {**params, "m": month}).all()
    return [LoanSnap(int(r.loan_id), int(r.branch_id), r.branch_name, r.loan_code, r.creditor,
                     r.project, str(r.currency).strip(), float(r.rate), r.grace_until,
                     r.maturity, _opt(r.fx_rate), float(r.original_cur),
                     float(r.outstanding_cur), _opt(r.outstanding)) for r in rows]


def schedule(db: Session, sel: BranchSel, month: int) -> list[LoanPayment]:
    """Grafik qatorlari shu oy snapshot'idagi kurs bilan (snapshot'i yo'q kreditlar — yo'q)."""
    where, params = sel.rows("s.branch_id")
    rows = db.execute(text(
        "SELECT s.date_id, s.loan_id, a.creditor, a.project, b.name AS branch_name, "
        "s.principal_cur, s.interest_cur, a.fx_rate "
        "FROM pub.agg_loan_schedule s "
        "JOIN pub.agg_loan_month a ON a.loan_id = s.loan_id AND a.branch_id = s.branch_id "
        "AND a.month_id = :m "
        "JOIN pub.branches b ON b.branch_id = s.branch_id "
        f"WHERE {where} ORDER BY s.date_id, s.loan_id"), {**params, "m": month}).all()
    return [LoanPayment(from_date_id(int(r.date_id)), int(r.loan_id), r.creditor, r.project,
                        r.branch_name, _convert(r.principal_cur, r.fx_rate),
                        _convert(r.interest_cur, r.fx_rate)) for r in rows]


def compute_report(snaps: list[LoanSnap], payments: list[LoanPayment], as_of: date) -> LoanReport:
    known = [(s, s.outstanding) for s in snaps if s.outstanding is not None]
    total = round(sum(value for _, value in known), 2)
    fx_amount = round(sum(value for s, value in known if s.currency != UZS), 2)
    weighted = sum(value * s.rate for s, value in known)
    year = as_of.year
    ordered = sorted(payments, key=lambda p: (p.day, -(p.total or 0.0), p.loan_id))
    in_year = [(p, t) for p in ordered if p.day.year == year for t in (p.total,) if t is not None]
    years: list[YearLoad] = []
    for y in range(year, year + HORIZON_YEARS):
        rows = [p for p in ordered if p.day.year == y]
        years.append(YearLoad(
            y,
            round(sum(v for v in (p.principal for p in rows) if v is not None), 2),
            round(sum(v for v in (p.interest for p in rows) if v is not None), 2)))
    return LoanReport(
        as_of=as_of,
        loans=list(snaps),
        payments=ordered,
        portfolio=total if known else None,
        rate=weighted / total if total > 0 else None,
        fx_share=fx_amount / total if total > 0 else None,
        fx_amount=fx_amount,
        service=round(sum(t for _, t in in_year), 2),
        paid=round(sum(t for p, t in in_year if p.day <= as_of), 2),
        missing_fx=sorted({s.currency for s in snaps if s.fx_rate is None}),
        years=years,
    )


def load_report(db: Session, sel: BranchSel, period: ReportPeriod) -> LoanReport:
    month = period.last_month
    return compute_report(snapshots(db, sel, month), schedule(db, sel, month), period.date_to)
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sections_loans.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(sections): kredit portfeli, stavka, valyuta ulushi, xizmat va grafik hisob-kitobi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: «Кредиты» API — Сводка, Реестр кредитов, График платежей

**Files:**
- Create: `backend/app/sections/loan_schemas.py`, `backend/app/sections/kredity.py`
- Modify: `backend/app/main.py` (router), `backend/tests/test_route_guards.py`
- Test: `backend/tests/test_kredity_api.py`

**Interfaces:**
- Consumes: `SQ`/`SectionQuery`, `get_today`, `Cache`, `get_db`, `require_perm`, `section_perm`, `Section.KREDITY`, `schemas._Out`, `ReportPeriodOut`, `period_out`, `queries.loans.*`, `tests.s2_helpers.{loan_scenario, kredity_branch_role}`, `published_synthetic`, `tests.helpers.login`, `make_user`.
- Produces:
  - `app.sections.loan_schemas`: `LoanPaymentOut(day, loan_id, creditor, project, branch_name, principal, interest, total)`, `LoanKpisOut(as_of, loans, portfolio, rate, fx_share, service, paid, paid_share, next_payment, peak_year, peak_amount, missing_fx, dscr)`, `LoanYearOut(year, principal, interest)`, `NamedAmountOut(name, amount)`, `LoanRowOut(loan_id, loan_code, creditor, project, branch_id, branch_name, currency, rate, outstanding, outstanding_cur, original_cur, repaid_share, grace_until, in_grace, maturity)`, `KreditySvodOut(period, has_loans, kpis, schedule, currencies, upcoming)`, `KredityReestrOut(period, has_loans, kpis, loans, creditors, currencies)`, `KredityGrafikOut(period, has_loans, schedule, upcoming)`.
  - `app.sections.kredity`: `router` (`/kredity`), `SVOD_UPCOMING = 5`, `GRAFIK_UPCOMING = 12`, `build_svod(db, q)`, `build_reestr(db, q)`, `build_grafik(db, q)`. HTTP: `GET /kredity/svod`, `GET /kredity/reestr`, `GET /kredity/grafik`.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_kredity_api.py`:
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
from tests.s2_helpers import LoanScenario, kredity_branch_role, loan_scenario

PAGES = ("svod", "reestr", "grafik")


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source, publish=True)
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


def test_svod_numbers_and_etag(sc: LoanScenario, app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    params = {"per": "m08", "br": sc.branch_id}
    r = client.get("/api/v1/kredity/svod", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    k = body["kpis"]
    assert body["has_loans"] is True and body["period"]["code"] == "m08"
    assert (k["as_of"], k["loans"], k["portfolio"]) == ("2026-08-31", 2, 9400.0)
    assert (k["service"], k["paid"]) == (3208.0, 1630.0)
    assert k["rate"] == pytest.approx(522 / 9400) and k["fx_share"] == pytest.approx(9000 / 9400)
    assert k["paid_share"] == pytest.approx(1630 / 3208)
    assert k["next_payment"]["day"] == "2026-09-15" and k["next_payment"]["total"] == 1460.0
    assert (k["peak_year"], k["peak_amount"]) == (2028, 7350.0)
    assert k["dscr"] is None and k["missing_fx"] == []
    assert [y["year"] for y in body["schedule"]] == list(range(2026, 2036))
    assert body["schedule"][0] == {"year": 2026, "principal": 2200.0, "interest": 1008.0}
    assert body["currencies"] == [{"name": "XTL", "amount": 9000.0},
                                  {"name": "UZS", "amount": 400.0}]
    assert len(body["upcoming"]) == 5
    again = client.get("/api/v1/kredity/svod", params=params,
                       headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304


def test_reestr_and_grafik(sc: LoanScenario, app_factory: Callable[[], TestClient],
                           make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("spec_kazna"))
    params = {"per": "m08", "br": sc.branch_id}
    reestr = client.get("/api/v1/kredity/reestr", params=params).json()
    rows = reestr["loans"]
    assert [x["loan_id"] for x in rows] == [sc.loan_a, sc.loan_b]
    a = rows[0]
    assert (a["loan_code"], a["currency"], a["outstanding"], a["outstanding_cur"]) == (
        f"LA-{sc.tag}", "XTL", 9000.0, 9.0)
    assert a["repaid_share"] == pytest.approx(0.1) and a["in_grace"] is False
    assert (a["grace_until"], a["maturity"], a["branch_id"]) == ("2026-01-01", "2028-12-31",
                                                                  sc.branch_id)
    assert reestr["creditors"][0] == {"name": f"Тест кредитор А {sc.tag}", "amount": 9000.0}
    grafik = client.get("/api/v1/kredity/grafik", params=params).json()
    assert [p["day"] for p in grafik["upcoming"]] == [
        "2026-09-15", "2026-10-10", "2027-03-15", "2027-10-10", "2028-03-15"]
    assert grafik["upcoming"][0]["creditor"] == f"Тест кредитор А {sc.tag}"
    assert len(grafik["schedule"]) == 10


def test_branch_without_loans(sc: LoanScenario, app_factory: Callable[[], TestClient],
                              make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/kredity/svod",
                      params={"per": "m08", "br": sc.empty_branch_id}).json()
    assert body["has_loans"] is False and body["kpis"]["portfolio"] is None
    assert body["kpis"]["next_payment"] is None and body["upcoming"] == []


def test_permission_and_branch_scope(sc: LoanScenario, app_factory: Callable[[], TestClient],
                                     make_user: Callable[..., SeedUser]) -> None:
    econ = _as(app_factory, make_user("economist_filiala", branch_ids=(3,)))
    for page in PAGES:
        assert econ.get(f"/api/v1/kredity/{page}").status_code == 403, page
    limited = _as(app_factory, make_user(kredity_branch_role(), branch_ids=(sc.branch_id,)))
    for page in PAGES:
        r = limited.get(f"/api/v1/kredity/{page}", params={"br": sc.empty_branch_id})
        assert r.status_code == 403 and r.json()["error"]["code"] == "scope_violation", page
    own = limited.get("/api/v1/kredity/reestr", params={"per": "m08"}).json()
    assert {x["branch_id"] for x in own["loans"]} == {sc.branch_id}
    assert own["kpis"]["portfolio"] == 9400.0


def test_invalid_period_is_422(app_factory: Callable[[], TestClient],
                               make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    assert client.get("/api/v1/kredity/svod", params={"per": "m12"}).status_code == 422


def test_synthetic_portfolio(published_synthetic: int, app_factory: Callable[[], TestClient],
                             make_user: Callable[..., SeedUser]) -> None:
    client = _as(app_factory, make_user("rukovodstvo"))
    body = client.get("/api/v1/kredity/reestr", params={"per": "m08"}).json()
    codes = {x["loan_code"] for x in body["loans"]}
    assert {f"LOAN-{n:02d}" for n in range(1, 9)} <= codes
    assert {"USD", "EUR", "CNY", "UZS"} <= {c["name"] for c in body["currencies"]}
    assert body["kpis"]["portfolio"] > 0 and body["kpis"]["missing_fx"] == []


def test_pub_views_rls_direct_sql(sc: LoanScenario) -> None:
    for view in ("agg_loan_month", "agg_loan_schedule"):
        with new_session() as s:
            apply_rls(s, frozenset({sc.branch_id}))
            seen = set(s.execute(text(f"SELECT DISTINCT branch_id FROM pub.{view}")).scalars())
        assert seen <= {sc.branch_id}, view
        with new_session() as s:
            assert s.execute(text(f"SELECT count(*) FROM pub.{view}")).scalar_one() == 0, view
```

`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` to'plamiga qo'shing:
```python
    ("GET", "/api/v1/kredity/svod"),
    ("GET", "/api/v1/kredity/reestr"),
    ("GET", "/api/v1/kredity/grafik"),
```
`PREFIX_PERMS` ga qo'shing:
```python
    "/api/v1/kredity": "section:kredity:view",
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_kredity_api.py tests/test_route_guards.py -v`
Expected: FAIL — `404 Not Found` (router yo'q) va `test_route_table_matches_expected_set` yiqiladi.

- [ ] **Step 3: Javob sxemalari**

`backend/app/sections/loan_schemas.py`:
```python
"""«Кредиты» API javoblari (OpenAPI komponent nomlari noyob). Summalar mln so'm (D kursida);
`*_cur` — kredit valyutasida (mln birlik); None — ma'lumot yoki kurs yo'q."""

from __future__ import annotations

from datetime import date

from app.sections.queries.loans import LoanPayment, LoanReport, LoanSnap
from app.sections.schemas import ReportPeriodOut, _Out


class LoanPaymentOut(_Out):
    day: date
    loan_id: int
    creditor: str
    project: str
    branch_name: str
    principal: float | None
    interest: float | None
    total: float | None


class LoanKpisOut(_Out):
    as_of: date
    loans: int
    portfolio: float | None
    rate: float | None
    fx_share: float | None
    service: float
    paid: float
    paid_share: float | None
    next_payment: LoanPaymentOut | None
    peak_year: int | None
    peak_amount: float | None
    missing_fx: list[str]
    # DSCR = EBITDA / обслуживание долга — Финмодель (S5) ulanmaguncha None («нет данных»).
    dscr: float | None


class LoanYearOut(_Out):
    year: int
    principal: float
    interest: float


class NamedAmountOut(_Out):
    name: str
    amount: float


class LoanRowOut(_Out):
    loan_id: int
    loan_code: str
    creditor: str
    project: str
    branch_id: int
    branch_name: str
    currency: str
    rate: float
    outstanding: float | None
    outstanding_cur: float
    original_cur: float
    repaid_share: float | None
    grace_until: date | None
    in_grace: bool
    maturity: date


class KreditySvodOut(_Out):
    period: ReportPeriodOut
    has_loans: bool
    kpis: LoanKpisOut
    schedule: list[LoanYearOut]
    currencies: list[NamedAmountOut]
    upcoming: list[LoanPaymentOut]


class KredityReestrOut(_Out):
    period: ReportPeriodOut
    has_loans: bool
    kpis: LoanKpisOut
    loans: list[LoanRowOut]
    creditors: list[NamedAmountOut]
    currencies: list[NamedAmountOut]


class KredityGrafikOut(_Out):
    period: ReportPeriodOut
    has_loans: bool
    schedule: list[LoanYearOut]
    upcoming: list[LoanPaymentOut]


def payment_out(p: LoanPayment) -> LoanPaymentOut:
    return LoanPaymentOut(day=p.day, loan_id=p.loan_id, creditor=p.creditor, project=p.project,
                          branch_name=p.branch_name, principal=p.principal,
                          interest=p.interest, total=p.total)


def kpis_out(r: LoanReport) -> LoanKpisOut:
    peak = r.peak
    nxt = r.next_payment
    return LoanKpisOut(
        as_of=r.as_of, loans=len(r.loans), portfolio=r.portfolio, rate=r.rate,
        fx_share=r.fx_share, service=r.service, paid=r.paid, paid_share=r.paid_share,
        next_payment=None if nxt is None else payment_out(nxt),
        peak_year=None if peak is None else peak.year,
        peak_amount=None if peak is None else peak.total,
        missing_fx=r.missing_fx, dscr=None)


def years_out(r: LoanReport) -> list[LoanYearOut]:
    return [LoanYearOut(year=y.year, principal=y.principal, interest=y.interest)
            for y in r.years]


def named_out(items: list[tuple[str, float]]) -> list[NamedAmountOut]:
    return [NamedAmountOut(name=name, amount=amount) for name, amount in items]


def loan_row_out(s: LoanSnap, as_of: date) -> LoanRowOut:
    return LoanRowOut(
        loan_id=s.loan_id, loan_code=s.loan_code, creditor=s.creditor, project=s.project,
        branch_id=s.branch_id, branch_name=s.branch_name, currency=s.currency, rate=s.rate,
        outstanding=s.outstanding, outstanding_cur=s.outstanding_cur,
        original_cur=s.original_cur, repaid_share=s.repaid_share, grace_until=s.grace_until,
        in_grace=s.in_grace(as_of), maturity=s.maturity)
```

- [ ] **Step 4: Router**

`backend/app/sections/kredity.py`:
```python
"""«Кредиты» (TZ 5): Сводка, Реестр кредитов, График платежей.

Zanjir: router → queries.loans (pub view'lar) → Cache.respond (Redis + ETag).
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
from app.sections.loan_schemas import (
    KredityGrafikOut,
    KredityReestrOut,
    KreditySvodOut,
    kpis_out,
    loan_row_out,
    named_out,
    payment_out,
    years_out,
)
from app.sections.queries import loans
from app.sections.schemas import period_out

router = APIRouter(prefix="/kredity", tags=["kredity"],
                   dependencies=[Depends(require_perm(section_perm(Section.KREDITY)))])
DB = Annotated[Session, Depends(get_db)]
SVOD_UPCOMING = 5  # prototip: «Пять следующих платежей»
GRAFIK_UPCOMING = 12  # TZ 5: «двенадцать ближайших платежей»


def build_svod(db: Session, q: SectionQuery) -> KreditySvodOut:
    period = q.period()
    r = loans.load_report(db, q.sel(), period)
    return KreditySvodOut(
        period=period_out(period), has_loans=r.has_loans, kpis=kpis_out(r),
        schedule=years_out(r), currencies=named_out(r.by_currency()),
        upcoming=[payment_out(p) for p in r.upcoming[:SVOD_UPCOMING]])


def build_reestr(db: Session, q: SectionQuery) -> KredityReestrOut:
    period = q.period()
    r = loans.load_report(db, q.sel(), period)
    return KredityReestrOut(
        period=period_out(period), has_loans=r.has_loans, kpis=kpis_out(r),
        loans=[loan_row_out(s, r.as_of) for s in r.loans],
        creditors=named_out(r.by_creditor()), currencies=named_out(r.by_currency()))


def build_grafik(db: Session, q: SectionQuery) -> KredityGrafikOut:
    period = q.period()
    r = loans.load_report(db, q.sel(), period)
    return KredityGrafikOut(
        period=period_out(period), has_loans=r.has_loans, schedule=years_out(r),
        upcoming=[payment_out(p) for p in r.upcoming[:GRAFIK_UPCOMING]])


@router.get("/svod", response_model=KreditySvodOut)
def svod(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kredity.svod", q.cache_filters, lambda: build_svod(db, q))


@router.get("/reestr", response_model=KredityReestrOut)
def reestr(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kredity.reestr", q.cache_filters, lambda: build_reestr(db, q))


@router.get("/grafik", response_model=KredityGrafikOut)
def grafik(cache: Cache, db: DB, q: SQ) -> Response:
    return cache.respond("kredity.grafik", q.cache_filters, lambda: build_grafik(db, q))
```

`backend/app/main.py` — import va `include_router` (S1'ning `kazna_router` qatoridan keyin):
```python
from app.sections.kredity import router as kredity_router
```
```python
    app.include_router(kredity_router, prefix=API_PREFIX)
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_kredity_api.py tests/test_route_guards.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(kredity): Сводка, Реестр кредитов, График платежей API

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: «Требует внимания» — kredit qoidalari

**Files:**
- Create: `backend/app/alerts/loans.py`
- Modify: `backend/app/alerts/__init__.py`, `backend/tests/test_alerts.py` (S1 `test_vnimanie_endpoints` — yangi qoidalar ham yonadi)
- Test: `backend/tests/test_alerts_loans.py`

**Interfaces:**
- Consumes: `evaluator`, `breached`, `hit`, `RuleConfig`, `AlertHit`, `evaluate`, `REGISTRY`, `load_report`, `fmt_money`, `fmt_pct`, `plural`, `ALERT_RULES` seed'lari (`loan_payments_30d`: `{"op": "<=", "value": 30}`, `kredity/grafik`, warning; `fx_loans_share`: `{"op": ">", "value": 0.85}`, `kredity/svod`, warning), `tests.s2_helpers.{loan_scenario, put_rule}`.
- Produces: `app.alerts.loans.loan_payments_30d`, `app.alerts.loans.fx_loans_share` (reyestrga yozilgan).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_alerts_loans.py`:
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
from tests.s2_helpers import LoanScenario, loan_scenario, put_rule

KRED = frozenset({"section:kredity:view"})


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    r = redis.Redis.from_url(get_settings().redis_url)
    for key in r.scan_iter("ugk:*"):
        r.delete(key)


@pytest.fixture(scope="module")
def sc() -> Iterator[LoanScenario]:
    source = new_source()
    yield loan_scenario(source, publish=True)
    purge_source(source)


@pytest.fixture
def db() -> Iterator[Session]:
    with new_session() as s:
        apply_rls(s, None)
        yield s


def _q(branch_id: int, per: str = "m08") -> SectionQuery:
    return SectionQuery(branch_id, per, TEST_AS_OF, None)


def test_registry_has_loan_rules() -> None:
    assert {"loan_payments_30d", "fx_loans_share"} <= set(REGISTRY)


def test_loan_rules_fire_on_scenario(sc: LoanScenario, db: Session) -> None:
    hits, checked = evaluate(db, _q(sc.branch_id), KRED)
    assert [h.code for h in hits] == ["loan_payments_30d", "fx_loans_share"]
    payments, share = hits
    assert payments.message == f"1 платёж на 1,5 млрд, первый 15.09.2026 — Тест кредитор А {sc.tag}"
    assert (payments.section, payments.page, payments.level, payments.value) == (
        "kredity", "grafik", "warning", 1.0)
    assert share.message == "95,7% портфеля в валюте: 9,0 млрд из 9,4 млрд"
    assert share.page == "svod" and share.value == pytest.approx(9000 / 9400)
    assert checked == ["Платежи по кредитам", "Доля валютных кредитов"]


def test_thresholds_come_from_db(sc: LoanScenario, db: Session) -> None:
    rules = {r.code: r for r in load_rules(db)}
    try:
        put_rule("loan_payments_30d", threshold={**rules["loan_payments_30d"].threshold,
                                                 "value": 10})
        put_rule("fx_loans_share", threshold={**rules["fx_loans_share"].threshold,
                                              "value": 0.99})
        assert evaluate(db, _q(sc.branch_id), KRED)[0] == []
        put_rule("loan_payments_30d", threshold={**rules["loan_payments_30d"].threshold,
                                                 "value": 45})
        hits = evaluate(db, _q(sc.branch_id), KRED)[0]
        assert hits[0].message.startswith("2 платежа на 1,6 млрд, первый 15.09.2026")
    finally:
        put_rule("loan_payments_30d", threshold=rules["loan_payments_30d"].threshold)
        put_rule("fx_loans_share", threshold=rules["fx_loans_share"].threshold)


def test_no_loans_or_missing_rates_do_not_fire(sc: LoanScenario, db: Session) -> None:
    assert evaluate(db, _q(sc.empty_branch_id), KRED)[0] == []
    # m01: XTL kursi yo'q — ulush faqat ma'lum (UZS) qism bo'yicha 0, to'lovlar 30 kundan uzoq.
    assert evaluate(db, _q(sc.branch_id, "m01"), KRED)[0] == []
    assert evaluate(db, _q(sc.branch_id), frozenset({"section:obzor:view"}))[0] == []
```
(45 kun: 15.09 — 1460 va 10.10 — 118 → 1578 → «1,6 млрд».)

`backend/tests/test_alerts.py` — `test_vnimanie_endpoints` ichida (S1 ssenariysining XTS krediti 2026-10-02 da to'lanadi — 8 kun, portfel 100% valyutada) ikki qatorni almashtiring:
```python
    assert [i["code"] for i in body["items"]] == ["contracts_overdue_90d",
                                                  "payment_plan_execution",
                                                  "overdue_payables_share",
                                                  "loan_payments_30d",
                                                  "fx_loans_share"]
```
```python
    assert boss.get("/api/v1/obzor/vnimanie/count", params=params).json() == {
        "count": 5, "critical": 1}
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_alerts_loans.py -v`
Expected: FAIL — `test_registry_has_loan_rules` (`loan_payments_30d` reyestrda yo'q).

- [ ] **Step 3: Implementatsiya**

`backend/app/alerts/loans.py`:
```python
"""TZ 4 «Требует внимания» — kredit qoidalari (chegaralar core.alert_rules dan, S2 spec 7).

Kredit yoki kurs bo'lmasa qoida None qaytaradi (yolg'on signal yo'q): kursi yo'q kreditlar
portfel va ulushga kirmaydi.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.alerts.types import AlertHit, RuleConfig, breached, evaluator, hit
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_money, fmt_pct, plural
from app.sections.queries import loans


@evaluator("loan_payments_30d")
def loan_payments_30d(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    report = loans.load_report(db, q.sel(), q.period())
    due = [p for p in report.upcoming if breached((p.day - report.as_of).days, rule)]
    if not due:
        return None
    n = len(due)
    total = round(sum(t for t in (p.total for p in due) if t is not None), 2)
    first = due[0]
    word = plural(n, "платёж", "платежа", "платежей")
    return hit(rule, f"{n} {word} на {fmt_money(total)}, первый {first.day:%d.%m.%Y} — "
                     f"{first.creditor}", float(n))


@evaluator("fx_loans_share")
def fx_loans_share(db: Session, q: SectionQuery, rule: RuleConfig) -> AlertHit | None:
    report = loans.load_report(db, q.sel(), q.period())
    if report.fx_share is None or report.portfolio is None:
        return None
    if not breached(report.fx_share, rule):
        return None
    return hit(rule, f"{fmt_pct(report.fx_share)} портфеля в валюте: "
                     f"{fmt_money(report.fx_amount)} из {fmt_money(report.portfolio)}",
               report.fx_share)
```

`backend/app/alerts/__init__.py` — import qatorini almashtiring:
```python
from app.alerts import loans, treasury  # noqa: F401
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_alerts_loans.py tests/test_alerts.py -v`
Expected: barcha testlar passed (S1 `test_default_rules_on_scenario_critical_first` o'zgarmaydi — u faqat obzor/kazna ruxsatlari bilan).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(alerts): kredit qoidalari — 30 kun ichidagi to'lovlar va valyuta ulushi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Bank ko'chirmasi ↔ 1C ustuvorligi, fayl jurnali jadvali, kurslar view'i, sink xatolari (0012)

**Files:**
- Create: `backend/migrations/versions/0012_banks_fx.py`
- Modify: `backend/app/dwh/aggregates.py` (`_CASH_ITEMS`, `_PAYMENTS`), `backend/app/dwh/treasury_aggregates.py` (`_CASH_BANK`), `backend/app/etl/quality.py` (`_balance_identity`), `backend/app/etl/types.py` (`ReportingSink`), `backend/app/etl/staging.py` (`DbStagingSink.error`)
- Test: `backend/tests/test_cashflow_precedence.py`

**Interfaces:**
- Consumes: `core.settings` (`banks.statement_branches`), `run_checks`, `DbStagingSink`, `tests.etl_helpers.*`, `tests.s1_helpers.rebuild`, `tests.s2_helpers.put_setting`.
- Produces:
  - `core.bank_files (sha256 PK, bank_code, file_name, size_bytes, kind ∈ statement|orders|unknown, status ∈ staged|rejected, run_id → core.etl_run, row_count, error_count, archive_path, first_seen_at, updated_at)` — `ugk_etl`: SELECT/INSERT/UPDATE, `ugk_app`: SELECT.
  - `dwh.statement_branches (branch_id)`, `dwh.cashflow_effective` (`fact_cashflow` ustunlari) — `ugk_etl` SELECT; agregatlar `agg_cash_month`, `agg_payments_month`, `agg_cash_bank_month` shu view'dan o'qiydi.
  - `pub.fx_rate_latest (currency, date_id, rate)` — `ugk_app` SELECT.
  - `quality._balance_identity`: bank qoldig'i (`doc_type = bank_balance`) bor, ammo `statement_branches` da bo'lmagan filial tekshirilmaydi.
  - `app.etl.types.ReportingSink` (runtime-checkable Protocol: `load_id`, `add`, `error(*, target, code, message, src_id=None, severity="error")`); `DbStagingSink.error(...)` → `core.etl_error` (step `extract`).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_cashflow_precedence.py`:
```python
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text

from app.core.db import new_session
from app.etl.db import etl_transaction
from app.etl.quality import run_checks
from app.etl.staging import DbStagingSink
from app.etl.types import ReportingSink, Window
from tests.etl_helpers import (
    TEST_AS_OF,
    branch_row,
    cash_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)
from tests.s1_helpers import rebuild
from tests.s2_helpers import put_setting


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


@pytest.fixture
def statement_branches() -> Iterator[Callable[[list[str]], None]]:
    def put(codes: list[str]) -> None:
        put_setting("banks.statement_branches", codes)

    yield put
    put([])


def _load(source: str, *, balances: bool = False) -> tuple[str, int, int]:
    tag = new_tag()
    branch = branch_row(tag)
    code = branch["code"]
    rows: dict[str, list[dict[str, Any]]] = {
        "dim_branch": [branch],
        "fact_cashflow": [
            cash_row("c1", 20260805, code, 50, doc_type="onec_payment"),
            cash_row("c2", 20260806, code, 45, doc_type="bank_statement"),
            cash_row("c3", 20260807, code, 5),  # boshqa manba (bank_entry) — doim hisobga olinadi
        ],
    }
    if balances:
        rows["dim_bank"] = [{"code": f"BA-{tag}", "bank_name": "Тест-банк",
                             "account_number": f"2021{tag}", "currency": "UZS"}]
        rows["fact_balance"] = [
            {"doc_type": "bank_balance", "src_id": "b1", "date_id": 20260731,
             "branch_code": code, "bank_code": f"BA-{tag}", "balance": 1000},
            {"doc_type": "bank_balance", "src_id": "b2", "date_id": 20260831,
             "branch_code": code, "bank_code": f"BA-{tag}", "balance": 500},
        ]
    run = open_run(source)
    stage(run, source, rows)
    merge_all(run, source)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": code}).scalar_one())
    return code, branch_id, run


def _outflows(build_id: int, branch_id: int) -> tuple[float, float, float]:
    with etl_transaction() as conn:
        cash = conn.execute(text(
            "SELECT outflow FROM mart.agg_cash_month WHERE build_id = :b AND branch_id = :br "
            "AND month_id = 202608 AND item_id = 0"), {"b": build_id, "br": branch_id}).scalar_one()
        fact = conn.execute(text(
            "SELECT sum(fact_amount) FROM mart.agg_payments_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202608"),
            {"b": build_id, "br": branch_id}).scalar_one()
        banks = conn.execute(text(
            "SELECT sum(outflow) FROM mart.agg_cash_bank_month WHERE build_id = :b "
            "AND branch_id = :br AND month_id = 202608"),
            {"b": build_id, "br": branch_id}).scalar_one()
    return float(cash), float(fact), float(banks)


def test_default_uses_onec_not_statement(source: str) -> None:
    _code, branch_id, run = _load(source)
    assert _outflows(rebuild(run), branch_id) == (55.0, 55.0, 55.0)


def test_statement_branch_uses_bank_lines_only(
        source: str, statement_branches: Callable[[list[str]], None]) -> None:
    code, branch_id, run = _load(source)
    statement_branches([code])
    assert _outflows(rebuild(run), branch_id) == (50.0, 50.0, 50.0)


def _identity_branches(run: int, build_id: int, source: str) -> set[int]:
    with etl_transaction() as conn:
        results = run_checks(conn, run_id=run, build_id=build_id, source=source,
                             window=Window(date(2026, 8, 1), TEST_AS_OF), totals=None)
    identity = next(r for r in results if r.code == "balance_identity")
    return {v["branch_id"] for v in identity.detail["violations"]}


def test_balance_identity_skipped_for_cross_source_branch(
        source: str, statement_branches: Callable[[list[str]], None]) -> None:
    code, branch_id, run = _load(source, balances=True)
    # Qoldiq 1000 → 500, oqim −55: «Разница» −445 (1C talabnomalari ↔ bank qoldig'i) — nuqson emas.
    assert branch_id not in _identity_branches(run, rebuild(run), source)
    statement_branches([code])
    assert branch_id in _identity_branches(run, rebuild(run), source)


def test_staging_sink_records_extract_errors(source: str) -> None:
    run = open_run(source)
    with etl_transaction() as conn:
        sink = DbStagingSink(conn, run, source)
        assert isinstance(sink, ReportingSink)
        sink.error(target="bank_file", code="bad_row", message="x" * 600, src_id="f.csv:3")
    with etl_transaction() as conn:
        row = conn.execute(text(
            "SELECT step, severity, target, code, length(message) AS n, src_id "
            "FROM core.etl_error WHERE run_id = :r"), {"r": run}).one()
    assert (row.step, row.severity, row.target, row.code, row.n, row.src_id) == (
        "extract", "error", "bank_file", "bad_row", 500, "f.csv:3")


def test_fx_rate_latest_view(source: str) -> None:
    run = open_run(source)
    stage(run, source, {"fx_rate": [{"currency": "XTQ", "date_id": 20260901, "rate": 10},
                                     {"currency": "XTQ", "date_id": 20260910, "rate": 11}]})
    merge_all(run, source)
    with new_session() as s:
        row = s.execute(text("SELECT date_id, rate FROM pub.fx_rate_latest "
                             "WHERE currency = 'XTQ'")).one()
    assert (row.date_id, float(row.rate)) == (20260910, 11.0)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_cashflow_precedence.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReportingSink' from 'app.etl.types'`.

- [ ] **Step 3: 0012 migratsiyasi**

`backend/migrations/versions/0012_banks_fx.py`:
```python
"""S2: bank fayllari jurnali, ko'chirma ↔ 1C ustuvorligi view'lari, oxirgi kurslar view'i

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-25
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE core.bank_files (
      sha256 char(64) PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
      bank_code varchar(16) NOT NULL,
      file_name varchar(255) NOT NULL,
      size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
      kind varchar(16) NOT NULL CHECK (kind IN ('statement', 'orders', 'unknown')),
      status varchar(16) NOT NULL CHECK (status IN ('staged', 'rejected')),
      run_id bigint REFERENCES core.etl_run (id) ON DELETE SET NULL,
      row_count integer NOT NULL DEFAULT 0,
      error_count integer NOT NULL DEFAULT 0,
      archive_path varchar(300),
      first_seen_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX bank_files_run_idx ON core.bank_files (run_id)",
    "GRANT SELECT, INSERT, UPDATE ON core.bank_files TO ugk_etl",
    "GRANT SELECT ON core.bank_files TO ugk_app",
    # S2 spec 3.4: oqimi bank ko'chirmasidan olinadigan filiallar (sozlama banks.statement_branches).
    """
    CREATE VIEW dwh.statement_branches WITH (security_invoker = true) AS
    SELECT b.branch_id FROM dwh.dim_branch b
    WHERE b.code IN (SELECT jsonb_array_elements_text(s.value) FROM core.settings s
                     WHERE s.key = 'banks.statement_branches' AND s.is_current)
    """,
    # Ko'chirma filialida — faqat bank проводкалари, qolganlarida — 1C; boshqa manbalar doim.
    """
    CREATE VIEW dwh.cashflow_effective WITH (security_invoker = true) AS
    SELECT f.* FROM dwh.fact_cashflow f
    WHERE CASE
      WHEN f.doc_type = 'bank_statement'
        THEN f.branch_id IN (SELECT sb.branch_id FROM dwh.statement_branches sb)
      WHEN left(f.doc_type, 5) = 'onec_'
        THEN f.branch_id NOT IN (SELECT sb.branch_id FROM dwh.statement_branches sb)
      ELSE true END
    """,
    "GRANT SELECT ON dwh.statement_branches, dwh.cashflow_effective TO ugk_etl",
    """
    CREATE VIEW pub.fx_rate_latest WITH (security_invoker = true) AS
    SELECT DISTINCT ON (r.currency) r.currency, r.date_id, r.rate
    FROM dwh.fx_rate r ORDER BY r.currency, r.date_id DESC
    """,
    "GRANT SELECT ON dwh.fx_rate TO ugk_app",
    "GRANT SELECT ON pub.fx_rate_latest TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP VIEW pub.fx_rate_latest")
    op.execute("REVOKE SELECT ON dwh.fx_rate FROM ugk_app")
    op.execute("DROP VIEW dwh.cashflow_effective")
    op.execute("DROP VIEW dwh.statement_branches")
    op.execute("DROP TABLE core.bank_files")
```

- [ ] **Step 4: Agregatlar va sifat tekshiruvi**

`backend/app/dwh/aggregates.py` — `_CASH_ITEMS` va `_PAYMENTS` (uning `fact AS (…)` CTE'si) ichidagi `  FROM dwh.fact_cashflow f` qatorini ikkala joyda almashtiring:
```python
  FROM dwh.cashflow_effective f
```
va `_CASH_ITEMS` dan oldin izoh qo'shing:
```python
# S2 spec 3.4: oqimlar dwh.cashflow_effective'dan — bank ko'chirmasi va 1C ikki marta sanalmaydi.
```
`backend/app/dwh/treasury_aggregates.py` — `_CASH_BANK` ning `flows AS (…)` CTE'sidagi `  FROM dwh.fact_cashflow f` qatorini xuddi shunday `  FROM dwh.cashflow_effective f` ga almashtiring. (`app/etl/quality.py` dagi `_control_totals` — manba bo'yicha, `fact_cashflow` da qoladi.)

`backend/app/etl/quality.py` — `_balance_identity` funksiyasini to'liq almashtiring:
```python
def _balance_identity(conn: Connection, build_id: int, window: Window) -> CheckResult:
    months = window.month_ids()
    # S2 spec 3.4: bank qoldig'i bor, lekin oqimi 1C'dan (ko'chirma rejimida emas) filialda
    # «Разница» — manbalararo solishtirish ko'rsatkichi, yuklash nuqsoni emas: tekshirilmaydi.
    rows = conn.execute(
        text("SELECT a.branch_id, a.month_id, a.diff, a.inflow + a.outflow AS turnover "
             "FROM mart.agg_cash_month a WHERE a.build_id = :b AND a.item_id = 0 "
             "AND a.branch_id <> 0 AND a.month_id BETWEEN :mf AND :mt "
             "AND a.opening_balance IS NOT NULL AND a.closing_balance IS NOT NULL "
             "AND abs(a.diff) > greatest(:tol * (a.inflow + a.outflow), 0.01) "
             "AND (a.branch_id IN (SELECT sb.branch_id FROM dwh.statement_branches sb) "
             "     OR NOT EXISTS (SELECT 1 FROM dwh.fact_balance fb "
             "                    WHERE fb.branch_id = a.branch_id "
             "                    AND fb.doc_type = 'bank_balance')) "
             "ORDER BY a.month_id, a.branch_id LIMIT :n"),
        {"b": build_id, "mf": months[0], "mt": months[-1], "tol": BALANCE_TOLERANCE, "n": SAMPLE},
    ).all()
    violations = [{"branch_id": r.branch_id, "month_id": r.month_id, "diff": str(r.diff),
                   "turnover": str(r.turnover)} for r in rows]
    return CheckResult("balance_identity", not violations, {"violations": violations})
```

- [ ] **Step 5: `ReportingSink` va `DbStagingSink.error`**

`backend/app/etl/types.py` — `from typing import Any, Protocol` ni `from typing import Any, Protocol, runtime_checkable` ga almashtiring va `StagingSink` sinfidan keyin qo'shing:
```python
@runtime_checkable
class ReportingSink(StagingSink, Protocol):
    """Qator/fayl xatolarini core.etl_error ga yoza oladigan sink (bank fayllari — S2 spec 3.2)."""

    load_id: int

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None: ...
```

`backend/app/etl/staging.py` — `DbStagingSink` sinfiga (`close` dan oldin) qo'shing:
```python
    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        """Konnektor darajasidagi xato (masalan, bank faylidagi buzilgan qator) — step "extract".
        Chaqiruvchi xabarda maxfiy qiymat (hisob raqami) bo'lmasligini ta'minlaydi."""
        self.conn.execute(
            text("INSERT INTO core.etl_error (run_id, step, severity, target, src_id, code, "
                 "message) VALUES (:r, 'extract', :sev, :t, :s, :c, :m)"),
            {"r": self.load_id, "sev": severity, "t": target[:64],
             "s": None if src_id is None else src_id[:128], "c": code[:32], "m": message[:500]},
        )
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_cashflow_precedence.py tests/test_aggregates_builds.py tests/test_treasury_aggregates.py tests/test_quality.py tests/test_sections_cash.py tests/test_etl_merge.py -v`
Expected: barcha testlar passed (ko'chirma/1C hujjatlari yo'q ma'lumotda view jadval bilan bir xil).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(dwh): bank ko'chirmasi ↔ 1C ustuvorligi, fayl jurnali, oxirgi kurslar view'i, sink xatolari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Kanonik bank CSV parseri va adapter interfeysi

**Files:**
- Create: `backend/app/etl/banks/models.py`, `backend/app/etl/banks/canonical.py`, `backend/app/etl/banks/adapters.py`
- Test: `backend/tests/test_bank_canonical.py`

**Interfaces:**
- Consumes: `ADAPTER_NAMES`.
- Produces:
  - `app.etl.banks.models`: `FileKind = Literal["statement", "orders"]`, `BankFileError(code, message)` (`ValueError`), `BalanceRow(line, account, day, kind: "OB"|"CB", amount: Decimal)`, `LineRow(line, account, day, doc_id, direction, amount, cp_inn, cp_name, item_code)`, `OrderRow(line, account, day, doc_id, status, status_day, amount, cp_inn, cp_name, item_code)`, `RowError(line, message)`, `ParsedFile(kind, balances, lines, orders, errors)`, `mask(text) -> str` (10+ raqamli ketma-ketlik → `…1234`), `normalize_account(value) -> str`.
  - `app.etl.banks.canonical`: `STATEMENT_COLUMNS`, `ORDER_COLUMNS`, `STATUSES` (`accepted|executed|rejected` → ruscha), `MAX_ROWS = 200_000`, `CanonicalCsvAdapter` (`name = "canonical"`, `parse(data, name) -> ParsedFile`).
  - `app.etl.banks.adapters`: `StatementAdapter` (Protocol: `name`, `parse`), `ADAPTERS: dict[str, StatementAdapter]` (kalitlar = `ADAPTER_NAMES`).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_bank_canonical.py`:
```python
import codecs
from datetime import date
from decimal import Decimal

import pytest

from app.etl.banks.adapters import ADAPTERS
from app.etl.banks.canonical import CanonicalCsvAdapter
from app.etl.banks.models import BankFileError, mask
from app.etl.banks.registry import ADAPTER_NAMES

ACC = "20210000900100000001"
HEAD = "row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code"
ORDERS = ("doc_id;account;date;status;status_date;amount;counterparty_inn;"
          "counterparty_name;item_code")


def csv_bytes(lines: list[str], *, bom: bool = False) -> bytes:
    return (codecs.BOM_UTF8 if bom else b"") + ("\n".join(lines) + "\n").encode("utf-8")


def test_statement_parsed_with_bom() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        HEAD,
        f"OB;{ACC};2026-09-22;;;1000000000.00;;;",
        f"L;{ACC};2026-09-22;D-1;in;250000000.00;301234567;ООО «Покупатель»;PKM54-I06",
        f"L;{ACC};2026-09-22;D-2;OUT;50000000.5;;Иванов Иван;",
        f"CB;{ACC};2026-09-22;;;1199999999.50;;;",
    ], bom=True), "sqb/v.csv")
    assert p.kind == "statement" and p.errors == []
    assert [(b.kind, b.amount) for b in p.balances] == [("OB", Decimal("1000000000.00")),
                                                        ("CB", Decimal("1199999999.50"))]
    one, two = p.lines
    assert (one.account, one.day, one.doc_id, one.direction, one.amount) == (
        ACC, date(2026, 9, 22), "D-1", "in", Decimal("250000000.00"))
    assert (one.cp_inn, one.cp_name, one.item_code) == ("301234567", "ООО «Покупатель»",
                                                         "PKM54-I06")
    assert (two.direction, two.cp_inn, two.cp_name, two.item_code, two.line) == (
        "out", None, "Иванов Иван", None, 4)


def test_columns_in_any_order_and_spaced_account() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        "account;row_type;date;amount;doc_id;direction;item_code;counterparty_name;"
        "counterparty_inn",
        "2021 0000 9001 0000 0001;CB;2026-09-22;5.00;;;;;",
    ]), "x.csv")
    assert p.errors == [] and p.balances[0].account == ACC


def test_orders_parsed() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        ORDERS,
        f"P-1;{ACC};2026-09-22;executed;2026-09-22;50000000.50;;;PKM54-O09",
        f"P-2;{ACC};2026-09-23;Rejected;;7000000;301234567;ООО «Покупатель»;",
        f"P-3;{ACC};2026-09-23;accepted;2026-09-24;1.00;;;",
    ]), "sqb/o.csv")
    assert p.kind == "orders" and p.errors == []
    assert [(o.doc_id, o.status, o.status_day) for o in p.orders] == [
        ("P-1", "исполнено", date(2026, 9, 22)), ("P-2", "отклонено", None),
        ("P-3", "отправлено в банк", date(2026, 9, 24))]


def test_malformed_rows_are_reported_not_fatal() -> None:
    p = CanonicalCsvAdapter().parse(csv_bytes([
        HEAD,
        f"L;{ACC};2026-09-22;D-1;in;10.00;;;",                     # 2 — to'g'ri
        f"L;{ACC};2026-09-22;D-2;in;10.00;;;;extra",               # 3 — ortiqcha maydon
        f"L;{ACC};24.09.2026;D-3;in;10.00;;;",                     # 4 — sana
        f"L;{ACC};2026-09-22;D-4;in;1 000.00;;;",                  # 5 — razryad ajratkichi
        f"L;{ACC};2026-09-22;D-5;in;10,50;;;",                     # 6 — vergulli kasr
        f"L;{ACC};2026-09-22;D-6;sideways;10.00;;;",               # 7 — yo'nalish
        f"L;{ACC};2026-09-22;D-7;out;0;;;",                        # 8 — nol summa
        f"L;{ACC[:-1]};2026-09-22;D-8;in;10.00;;;",                # 9 — 19 raqamli hisob
        f"X;{ACC};2026-09-22;D-9;in;10.00;;;",                     # 10 — row_type
        f"L;{ACC};2026-09-22;;in;10.00;;;",                        # 11 — doc_id bo'sh
        f"L;{ACC};2026-09-22;D-10;in;10.00;12345;;",               # 12 — INN formati
        "",                                                         # bo'sh qator — e'tiborsiz
        f"CB;{ACC};2026-09-22;;;-5.00;;;",                          # 14 — manfiy qoldiq mumkin
    ]), "sqb/bad.csv")
    assert [x.doc_id for x in p.lines] == ["D-1"]
    assert [b.amount for b in p.balances] == [Decimal("-5.00")]
    assert [e.line for e in p.errors] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    text = " | ".join(e.message for e in p.errors)
    for needle in ("полей", "дата", "разделител", "сумма", "direction", "больше нуля",
                   "20 цифр", "row_type", "doc_id", "counterparty_inn"):
        assert needle in text, needle
    assert ACC[:-1] not in text and ACC not in text


@pytest.mark.parametrize(("data", "code"), [
    (b"code;name\nT-1;x\n", "bad_header"),
    (f"{HEAD}\nL;{ACC};2026-09-22;D;in;1;;Тест;\n".encode("cp1251"), "bad_encoding"),
    (b"", "bad_header"),
    (b"a;b;c\n1;2;3\n", "bad_header"),
])
def test_file_level_errors(data: bytes, code: str) -> None:
    with pytest.raises(BankFileError) as exc:
        CanonicalCsvAdapter().parse(data, "sqb/f.csv")
    assert exc.value.code == code


def test_mask_and_registry() -> None:
    assert mask(f"выписка_{ACC}_0922.csv") == "выписка_…0001_0922.csv"
    assert mask("строка 12, сумма 1000") == "строка 12, сумма 1000"
    assert tuple(ADAPTERS) == ADAPTER_NAMES
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_bank_canonical.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.banks.adapters'`.

- [ ] **Step 3: Implementatsiya — modellar**

`backend/app/etl/banks/models.py`:
```python
"""Bank ma'lumotining manbadan mustaqil ko'rinishi: fayl adapterlari va DirectBank mijozi bir xil
`ParsedFile` qaytaradi, `BankMapper` uni staging'ga yozadi (S2 spec 3.2).

Hisob raqami bu obyektlarda ochiq (xotirada) — log/xato matnlariga faqat `mask()` orqali.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

FileKind = Literal["statement", "orders"]
Direction = Literal["in", "out"]
_LONG_DIGITS = re.compile(r"\d{10,}")


def mask(text: str) -> str:
    """10+ raqamli ketma-ketlik (hisob raqami) → «…1234»."""
    return _LONG_DIGITS.sub(lambda m: "…" + m.group()[-4:], text)


def normalize_account(value: str) -> str:
    return re.sub(r"[\s-]", "", value)


class BankFileError(ValueError):
    """Butun faylni rad etish sababi (kodlash, sarlavha, hajm)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BalanceRow:
    line: int
    account: str
    day: date
    kind: Literal["OB", "CB"]
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LineRow:
    line: int
    account: str
    day: date
    doc_id: str
    direction: Direction
    amount: Decimal
    cp_inn: str | None
    cp_name: str | None
    item_code: str | None


@dataclass(frozen=True, slots=True)
class OrderRow:
    line: int
    account: str
    day: date
    doc_id: str
    status: str
    status_day: date | None
    amount: Decimal
    cp_inn: str | None
    cp_name: str | None
    item_code: str | None


@dataclass(frozen=True, slots=True)
class RowError:
    line: int
    message: str


@dataclass
class ParsedFile:
    kind: FileKind
    balances: list[BalanceRow] = field(default_factory=list)
    lines: list[LineRow] = field(default_factory=list)
    orders: list[OrderRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
```

- [ ] **Step 4: Implementatsiya — kanonik CSV va adapterlar**

`backend/app/etl/banks/canonical.py`:
```python
"""Kanonik bank CSV (docs/integration/banks-format.md; TZ 8 «Общие правила обмена»):
UTF-8 (BOM ixtiyoriy), ';', sanalar ГГГГ-ММ-ДД, summalar nuqta bilan, razryad ajratkichsiz.
Sarlavha to'plami (tartibi erkin) fayl turini belgilaydi. Qator xatosi faylni to'xtatmaydi —
`ParsedFile.errors` ga yoziladi; kodlash/sarlavha xatosi — `BankFileError` (butun fayl).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal

from app.etl.banks.models import (
    BalanceRow,
    BankFileError,
    Direction,
    FileKind,
    LineRow,
    OrderRow,
    ParsedFile,
    RowError,
    mask,
    normalize_account,
)

STATEMENT_COLUMNS = ("row_type", "account", "date", "doc_id", "direction", "amount",
                     "counterparty_inn", "counterparty_name", "item_code")
ORDER_COLUMNS = ("doc_id", "account", "date", "status", "status_date", "amount",
                 "counterparty_inn", "counterparty_name", "item_code")
STATUSES = {"accepted": "отправлено в банк", "executed": "исполнено", "rejected": "отклонено"}
MAX_ROWS = 200_000
_AMOUNT = re.compile(r"^-?\d{1,15}(\.\d{1,2})?$")
_THOUSANDS = re.compile(r"^-?\d{1,3}([\s\xa0\N{NARROW NO-BREAK SPACE}']\d{3})+([.,]\d+)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ACCOUNT = re.compile(r"^\d{20}$")
_DOC_ID = re.compile(r"^[0-9A-Za-z._/-]{1,64}$")
_INN = re.compile(r"^(\d{9}|\d{14})$")
_ITEM = re.compile(r"^[0-9A-Za-z._-]{1,32}$")


def _day(value: str, name: str) -> date:
    if not _DATE.fullmatch(value):
        raise ValueError(f"{name}: неверная дата «{value[:12]}» (ожидается ГГГГ-ММ-ДД)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}: неверная дата «{value[:12]}»") from exc


def _amount(value: str) -> Decimal:
    if _THOUSANDS.fullmatch(value):
        raise ValueError(f"amount: разделитель разрядов в сумме «{value[:20]}» не допускается")
    if not _AMOUNT.fullmatch(value):
        raise ValueError(f"amount: неверная сумма «{value[:20]}» (точка, до 2 знаков)")
    return Decimal(value)


def _account(value: str) -> str:
    account = normalize_account(value)
    if not _ACCOUNT.fullmatch(account):
        # Qiymatning o'zi xabarga qo'yilmaydi (hisob raqami bo'lishi mumkin).
        raise ValueError("account: ожидается 20 цифр расчётного счёта")
    return account


def _optional(value: str, pattern: re.Pattern[str], name: str) -> str | None:
    if not value:
        return None
    if not pattern.fullmatch(value):
        raise ValueError(f"{name}: неверный формат")
    return value


def _doc_id(value: str) -> str:
    if not _DOC_ID.fullmatch(value):
        raise ValueError("doc_id: пусто или недопустимые символы (A-Z, 0-9, . _ / -)")
    return value


class CanonicalCsvAdapter:
    name = "canonical"

    def parse(self, data: bytes, name: str) -> ParsedFile:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BankFileError("bad_encoding", f"{name}: файл не в кодировке UTF-8") from exc
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
        header = next(reader, None)
        columns = [h.strip().lower() for h in header or []]
        kind: FileKind
        if sorted(columns) == sorted(STATEMENT_COLUMNS):
            kind = "statement"
        elif sorted(columns) == sorted(ORDER_COLUMNS):
            kind = "orders"
        else:
            raise BankFileError("bad_header",
                                f"{name}: заголовок не соответствует формату (см. banks-format)")
        out = ParsedFile(kind)
        for line, raw in enumerate(reader, start=2):
            if line > MAX_ROWS + 1:
                raise BankFileError("too_many_rows", f"{name}: более {MAX_ROWS} строк")
            if not any(cell.strip() for cell in raw):
                continue
            if len(raw) != len(columns):
                out.errors.append(RowError(line, f"ожидается {len(columns)} полей, "
                                                 f"получено {len(raw)}"))
                continue
            row = dict(zip(columns, (cell.strip() for cell in raw), strict=True))
            try:
                if kind == "statement":
                    self._statement(line, row, out)
                else:
                    self._order(line, row, out)
            except ValueError as exc:
                out.errors.append(RowError(line, mask(str(exc))))
        return out

    @staticmethod
    def _statement(line: int, row: dict[str, str], out: ParsedFile) -> None:
        row_type = row["row_type"].upper()
        if row_type not in ("OB", "CB", "L"):
            raise ValueError(f"row_type: ожидается OB, CB или L, получено «{row_type[:5]}»")
        account = _account(row["account"])
        day = _day(row["date"], "date")
        amount = _amount(row["amount"])
        if row_type == "OB":
            out.balances.append(BalanceRow(line, account, day, "OB", amount))
            return
        if row_type == "CB":
            out.balances.append(BalanceRow(line, account, day, "CB", amount))
            return
        doc_id = _doc_id(row["doc_id"])
        raw_direction = row["direction"].lower()
        if raw_direction not in ("in", "out"):
            raise ValueError("direction: ожидается in или out")
        direction: Direction = "in" if raw_direction == "in" else "out"
        if amount <= 0:
            raise ValueError("amount: сумма проводки должна быть больше нуля")
        out.lines.append(LineRow(
            line, account, day, doc_id, direction, amount,
            _optional(row["counterparty_inn"], _INN, "counterparty_inn"),
            row["counterparty_name"][:300] or None,
            _optional(row["item_code"], _ITEM, "item_code")))

    @staticmethod
    def _order(line: int, row: dict[str, str], out: ParsedFile) -> None:
        doc_id = _doc_id(row["doc_id"])
        account = _account(row["account"])
        day = _day(row["date"], "date")
        status = STATUSES.get(row["status"].lower())
        if status is None:
            raise ValueError("status: ожидается accepted, executed или rejected")
        status_day = _day(row["status_date"], "status_date") if row["status_date"] else None
        amount = _amount(row["amount"])
        if amount <= 0:
            raise ValueError("amount: сумма поручения должна быть больше нуля")
        out.orders.append(OrderRow(
            line, account, day, doc_id, status, status_day, amount,
            _optional(row["counterparty_inn"], _INN, "counterparty_inn"),
            row["counterparty_name"][:300] or None,
            _optional(row["item_code"], _ITEM, "item_code")))
```

`backend/app/etl/banks/adapters.py`:
```python
"""Bank fayl formatlari adapterlari. Yangi bank formati = yangi adapter sinfi + shu lug'atga
bitta qator + `ADAPTER_NAMES` (registry) ga nom; `banks.formats` sozlamasi bankka adapter beradi."""

from __future__ import annotations

from typing import Protocol

from app.etl.banks.canonical import CanonicalCsvAdapter
from app.etl.banks.models import ParsedFile


class StatementAdapter(Protocol):
    name: str

    def parse(self, data: bytes, name: str) -> ParsedFile: ...


ADAPTERS: dict[str, StatementAdapter] = {"canonical": CanonicalCsvAdapter()}
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_bank_canonical.py -v`
Expected: barcha testlar passed; `$TEST ruff check app/etl/banks tests/test_bank_canonical.py` — xatosiz.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(banks): kanonik bank CSV parseri va format adapterlari interfeysi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `BankFileConnector` — moslashtirish, balans tekshiruvi, kurs, fayl jurnali, arxiv; DirectBank stub'i

**Files:**
- Create: `backend/app/etl/banks/accounts.py`, `backend/app/etl/banks/fx.py`, `backend/app/etl/banks/ledger.py`, `backend/app/etl/banks/mapper.py`, `backend/app/etl/banks/connector.py`, `backend/app/etl/banks/directbank.py`
- Test: `backend/tests/test_bank_connector.py`

**Interfaces:**
- Consumes: `ParsedFile` va qatorlari, `mask`, `normalize_account`, `ADAPTERS`, `BankFileError`, `BANKS`, `BankAccount`, `blind_index`, `ReportingSink`, `Runner`, `ExtractStats`, `HealthResult`, `Watermark`, `etl_transaction`, `date_id`, `core.bank_files`, `dwh.fx_rate`, `ConfigError`.
- Produces:
  - `app.etl.banks.accounts`: `account_code(account, key=None) -> str` (`BA-` + blind index[:16]), `AccountIndex(accounts, key=None)` + `.resolve(account) -> BankAccount | None`.
  - `app.etl.banks.fx`: `MAX_FX_AGE_DAYS = 10`, `FxLookup` (Protocol: `rate(currency, day) -> Decimal | None`), `DbFxLookup`.
  - `app.etl.banks.ledger`: `FileEntry(sha256, bank_code, file_name, size_bytes, kind, status, run_id, row_count, error_count, archive_path)`, `LedgerRow(first_seen_at, bank_code, file_name, kind, status, run_id, row_count, error_count)`, `FileLedger` (Protocol: `done(sha256) -> bool`, `mark(entry)`), `DbFileLedger` (+ `.recent(limit) -> list[LedgerRow]`).
  - `app.etl.banks.mapper`: `ERROR_LIMIT = 1000`, `to_mln(amount, rate) -> Decimal`, `BankMapper(sink, accounts, fx, *, index_key)` + `.stage(bank_code, file, parsed) -> int`, `.report(where, code, message)`, `.errors: int`. Xato kodlari: `bad_row`, `unknown_account`, `wrong_bank`, `duplicate_doc`, `statement_mismatch`, `fx_rate_missing` (+ fayl darajasida `bad_encoding`, `bad_header`, `too_many_rows`, `too_large`).
  - `app.etl.banks.connector`: `MAX_BYTES = 50 MiB`, `MIN_AGE_SECONDS = 60.0`, `BankFileConnector(inbox, archive, accounts, *, formats=None, ledger=None, fx=None, source="banks", index_key=None, min_age=60.0, max_bytes=MAX_BYTES, now=time.time)` — `SourceConnector`; `extract` `ReportingSink` talab qiladi va `ExtractStats(rows, {})` qaytaradi (maqsadlar «to'liq» emas).
  - `app.etl.banks.directbank`: `DirectBankNotConfigured(ConfigError)`, `DIRECTBANK_MESSAGE`, `DirectBankClient` (Protocol: `statements(account_codes, day) -> ParsedFile`, `order_statuses(account_codes, day) -> ParsedFile`), `OneCDirectBankClient` (yaratishda `DirectBankNotConfigured`).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_bank_connector.py`:
```python
import logging
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import ConfigError, get_settings
from app.core.crypto import blind_index
from app.core.db import apply_rls, new_session
from app.etl.banks.accounts import account_code
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.directbank import DirectBankNotConfigured, OneCDirectBankClient
from app.etl.banks.registry import BankAccount
from app.etl.db import etl_transaction
from app.etl.runner import RunResult, Runner
from app.etl.types import Mode
from tests.etl_helpers import (
    FULL_WINDOW,
    TEST_AS_OF,
    branch_row,
    merge_all,
    new_source,
    new_tag,
    open_run,
    purge_source,
    stage,
)

HEAD = "row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code"
ORDERS = ("doc_id;account;date;status;status_date;amount;counterparty_inn;"
          "counterparty_name;item_code")


def new_account(prefix: str = "2021000090") -> str:
    return prefix + f"{uuid.uuid4().int % 10**10:010d}"


class CollectSink:
    """ReportingSink: staging qatorlari va xatolarni xotirada yig'adi."""

    def __init__(self, load_id: int) -> None:
        self.load_id = load_id
        self.rows: list[tuple[str, dict[str, Any]]] = []
        self.errors: list[dict[str, Any]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))

    def error(self, *, target: str, code: str, message: str, src_id: str | None = None,
              severity: str = "error") -> None:
        self.errors.append({"target": target, "code": code, "message": message, "src_id": src_id})

    def facts(self) -> list[dict[str, Any]]:
        return [row for target, row in self.rows if target.startswith("fact_")]


class PlainSink:
    def add(self, target: str, row: Mapping[str, Any]) -> None:
        raise AssertionError("chaqirilmasligi kerak")


@dataclass
class Env:
    source: str
    branch_code: str
    branch_id: int
    uzs: str  # ochiq hisob raqamlari faqat test ichida
    fx: str
    accounts: list[BankAccount]
    inbox: Path
    archive: Path

    def connector(self, **kw: Any) -> BankFileConnector:
        return BankFileConnector(self.inbox, self.archive, self.accounts, source=self.source,
                                 min_age=0, **kw)

    def run(self) -> RunResult:
        return Runner(self.connector(), mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                      sleep=lambda _: None).run()

    def write(self, bank: str, name: str, lines: list[str]) -> Path:
        path = self.inbox / bank / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def code(self, account: str) -> str:
        return account_code(account)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    source = new_source()
    branch = branch_row(new_tag())
    run = open_run(source)
    stage(run, source, {"dim_branch": [branch],
                        "fx_rate": [{"currency": "XTL", "date_id": 20260920, "rate": 12000}]})
    merge_all(run, source)
    with etl_transaction() as conn:
        branch_id = int(conn.execute(text("SELECT branch_id FROM dwh.dim_branch WHERE code = :c"),
                                     {"c": branch["code"]}).scalar_one())
    uzs, fx = new_account(), new_account("2020888090")
    accounts = [
        BankAccount(code=account_code(uzs), bank_code="sqb", branch_code=branch["code"],
                    currency="UZS", gl_account="5110", last4=uzs[-4:]),
        BankAccount(code=account_code(fx), bank_code="nbu", branch_code=branch["code"],
                    currency="XTL", gl_account="5210", last4=fx[-4:]),
    ]
    inbox, archive = tmp_path / "inbox", tmp_path / "archive"
    for folder in (inbox / "sqb", inbox / "nbu", archive):
        folder.mkdir(parents=True)
    yield Env(source, branch["code"], branch_id, uzs, fx, accounts, inbox, archive)
    purge_source(source)


def statement(account: str, day: str = "2026-09-22") -> list[str]:
    return [
        HEAD,
        f"OB;{account};{day};;;1000000000.00;;;",
        f"L;{account};{day};D-1;in;250000000.00;301234567;ООО «Покупатель»;PKM54-I06",
        f"L;{account};{day};D-2;out;50000000.50;;Иванов Иван;",
        f"CB;{account};{day};;;1199999999.50;;;",
    ]


def _errors(run_id: int) -> list[dict[str, Any]]:
    with etl_transaction() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT code, src_id, message FROM core.etl_error WHERE run_id = :r "
            "AND step = 'extract' ORDER BY id"), {"r": run_id}).mappings().all()]


def test_runner_loads_statement_orders_and_publishes(env: Env) -> None:
    env.write("sqb", "vypiska_0922.csv", statement(env.uzs))
    env.write("nbu", "fx_0922.csv", [HEAD, f"OB;{env.fx};2026-09-22;;;1010.00;;;",
                                     f"L;{env.fx};2026-09-22;F-1;out;10.00;;;",
                                     f"CB;{env.fx};2026-09-22;;;1000.00;;;"])
    env.write("sqb", "orders_0922.csv", [
        ORDERS, f"P-1;{env.uzs};2026-09-22;executed;2026-09-22;50000000.50;;;PKM54-O09",
        f"P-2;{env.uzs};2026-09-23;rejected;2026-09-23;7000000.00;301234567;ООО «Покупатель»;"])
    result = env.run()
    assert result.status == "success", result
    uzs, fx = env.code(env.uzs), env.code(env.fx)
    with etl_transaction() as conn:
        balances = {r.code: float(r.balance) for r in conn.execute(text(
            "SELECT b.code, f.balance FROM dwh.fact_balance f JOIN dwh.dim_bank b "
            "ON b.bank_id = f.bank_id WHERE f.src_system = :s"), {"s": env.source})}
        cash = {r.src_id: (r.direction, float(r.amount), r.gl_account, r.has_cp) for r in
                conn.execute(text(
                    "SELECT src_id, direction, amount, gl_account, cp_id IS NOT NULL AS has_cp "
                    "FROM dwh.fact_cashflow WHERE src_system = :s"), {"s": env.source})}
        orders = {r.src_id: (r.status, float(r.amount), r.status_date_id) for r in conn.execute(
            text("SELECT src_id, status, amount, status_date_id FROM dwh.fact_payment_order "
                 "WHERE src_system = :s"), {"s": env.source})}
        bank = conn.execute(text("SELECT bank_name, account_enc IS NOT NULL AS enc, account_bidx "
                                 "FROM dwh.dim_bank WHERE code = :c"), {"c": uzs}).one()
        ledger = conn.execute(text("SELECT kind, status, row_count FROM core.bank_files "
                                   "WHERE run_id = :r ORDER BY kind, row_count"),
                              {"r": result.run_id}).all()
    assert balances == {uzs: 1200.0, fx: 12.0}  # 1000 XTL × 12000 = 12 mln so'm
    assert cash == {f"{uzs}:D-1": ("in", 250.0, "5110", True),
                    f"{uzs}:D-2": ("out", 50.0, "5110", False),  # jismoniy shaxs — kontragentsiz
                    f"{fx}:F-1": ("out", 0.12, "5210", False)}
    assert orders == {f"{uzs}:P-1": ("исполнено", 50.0, 20260922),
                      f"{uzs}:P-2": ("отклонено", 7.0, 20260923)}
    key = get_settings().key_bytes("blind_index_key")
    assert (bank.bank_name, bank.enc) == ("Узпромстройбанк", True)
    assert bytes(bank.account_bidx) == blind_index(key, "account", env.uzs)
    assert [tuple(r) for r in ledger] == [("orders", "staged", 2), ("statement", "staged", 2),
                                          ("statement", "staged", 3)]
    archived = sorted(p.name for p in env.archive.rglob("*.csv"))
    assert len(archived) == 3 and all(len(n) == len("0" * 64 + ".csv") for n in archived)
    with new_session() as s:
        apply_rls(s, None)
        closing = dict(s.execute(text(
            "SELECT bank_name, closing_balance FROM pub.agg_cash_bank_month "
            "WHERE branch_id = :b AND month_id = 202609"), {"b": env.branch_id}).all())
    assert {k: float(v) for k, v in closing.items()} == {"Узпромстройбанк": 1200.0,
                                                         "Национальный банк": 12.0}


def test_redelivery_is_idempotent_and_second_file_keeps_first(env: Env) -> None:
    first = env.write("sqb", "a.csv", statement(env.uzs))
    assert env.run().status == "success"
    (env.inbox / "sqb" / "a_copy.csv").write_bytes(first.read_bytes())  # qayta yetkazish
    env.write("sqb", "b.csv", [HEAD, f"L;{env.uzs};2026-09-23;D-3;out;1000000.00;;;"])
    result = env.run()
    assert result.status == "success", result
    uzs = env.code(env.uzs)
    with etl_transaction() as conn:
        ids = sorted(conn.execute(text("SELECT src_id FROM dwh.fact_cashflow "
                                       "WHERE src_system = :s"), {"s": env.source}).scalars())
        staged = conn.execute(text("SELECT count(*) FROM core.bank_files WHERE run_id = :r"),
                              {"r": result.run_id}).scalar_one()
    assert ids == sorted([f"{uzs}:D-1", f"{uzs}:D-2", f"{uzs}:D-3"])
    assert staged == 1  # faqat b.csv; a_copy.csv — o'sha SHA-256, qayta o'qilmadi


def test_failed_run_files_are_reprocessed(env: Env) -> None:
    env.write("sqb", "a.csv", statement(env.uzs))
    first = CollectSink(open_run(env.source))
    env.connector().extract(FULL_WINDOW, first)
    assert len(first.facts()) == 3
    with etl_transaction() as conn:
        conn.execute(text("UPDATE core.etl_run SET status = 'failed' WHERE id = :r"),
                     {"r": first.load_id})
    second = CollectSink(open_run(env.source))
    env.connector().extract(FULL_WINDOW, second)
    assert len(second.facts()) == 3
    with etl_transaction() as conn:
        conn.execute(text("UPDATE core.etl_run SET status = 'success' WHERE id = :r"),
                     {"r": second.load_id})
    third = CollectSink(open_run(env.source))
    env.connector().extract(FULL_WINDOW, third)
    assert third.rows == []


def test_malformed_rows_are_reported_and_valid_rows_loaded(env: Env) -> None:
    other = new_account()
    env.write("sqb", "mixed.csv", [
        HEAD,
        f"L;{env.uzs};2026-09-22;D-1;in;10.00;;;",       # 2 — to'g'ri
        f"L;{env.uzs};2026-09-22;D-2;in;1 000.00;;;",    # 3 — bad_row
        f"L;{other};2026-09-22;D-3;in;10.00;;;",         # 4 — unknown_account
        f"L;{env.uzs};2026-09-22;D-1;in;10.00;;;",       # 5 — duplicate_doc
        f"OB;{env.uzs};2026-09-21;;;100.00;;;",          # 6
        f"L;{env.uzs};2026-09-21;D-4;out;10.00;;;",      # 7
        f"CB;{env.uzs};2026-09-21;;;95.00;;;",           # 8 — statement_mismatch (90 kutilgan)
    ])
    env.write("sqb", "wrong_bank.csv", [HEAD, f"CB;{env.fx};2026-09-22;;;5.00;;;"])
    env.write("nbu", "fx_old.csv", [HEAD, f"CB;{env.fx};2026-01-05;;;5.00;;;"])
    result = env.run()
    assert result.status == "success", result
    errors = _errors(result.run_id or 0)
    assert sorted(e["code"] for e in errors) == ["bad_row", "duplicate_doc", "fx_rate_missing",
                                                 "statement_mismatch", "unknown_account",
                                                 "wrong_bank"]
    assert any(e["src_id"] == "sqb/mixed.csv:3" for e in errors)
    with etl_transaction() as conn:
        ids = set(conn.execute(text("SELECT src_id FROM dwh.fact_cashflow WHERE src_system = :s"),
                               {"s": env.source}).scalars())
    assert ids == {f"{env.code(env.uzs)}:D-1"}  # D-4 — nomuvofiq ko'chirma, yuklanmaydi


def test_file_level_rejection_is_final(env: Env) -> None:
    (env.inbox / "sqb" / "cp1251.csv").write_bytes(
        f"{HEAD}\nL;{env.uzs};2026-09-22;D-1;in;1.00;;Тест;\n".encode("cp1251"))
    first = env.run()
    assert [e["code"] for e in _errors(first.run_id or 0)] == ["bad_encoding"]
    with etl_transaction() as conn:
        status = conn.execute(text("SELECT status FROM core.bank_files WHERE run_id = :r"),
                              {"r": first.run_id}).scalar_one()
    assert status == "rejected"
    second = env.run()
    assert _errors(second.run_id or 0) == []


def test_account_number_never_leaks(env: Env, caplog: pytest.LogCaptureFixture,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    caplog.set_level(logging.DEBUG)
    env.write("sqb", f"vypiska_{env.uzs}_0922.csv",
              [*statement(env.uzs), f"L;{env.uzs};2026-09-22;D-9;in;1 0;;;"])
    env.write("sqb", f"unknown_{env.uzs}.csv",
              [HEAD, f"L;{new_account()};2026-09-22;X-1;in;1.00;;;"])
    result = env.run()
    with etl_transaction() as conn:
        messages = " ".join(conn.execute(text(
            "SELECT coalesce(src_id, '') || ' ' || message FROM core.etl_error "
            "WHERE run_id = :r"), {"r": result.run_id}).scalars())
        ledger = " ".join(conn.execute(text(
            "SELECT file_name || ' ' || coalesce(archive_path, '') FROM core.bank_files "
            "WHERE run_id = :r"), {"r": result.run_id}).scalars())
    archived = " ".join(str(p) for p in env.archive.rglob("*"))
    out = capsys.readouterr()
    for place in (messages, ledger, archived, caplog.text, out.out, out.err):
        assert env.uzs not in place
    assert f"…{env.uzs[-4:]}" in ledger


def test_fresh_and_non_csv_files_are_ignored(env: Env) -> None:
    path = env.write("sqb", "fresh.csv", statement(env.uzs))
    (env.inbox / "sqb" / "upload.tmp").write_text("x", encoding="utf-8")
    moment = path.stat().st_mtime + 10
    sink = CollectSink(open_run(env.source))
    BankFileConnector(env.inbox, env.archive, env.accounts, source=env.source, min_age=60,
                      now=lambda: moment).extract(FULL_WINDOW, sink)
    assert sink.rows == [] and not list(env.archive.rglob("*.csv"))


def test_extract_requires_reporting_sink(env: Env) -> None:
    with pytest.raises(TypeError, match="ReportingSink"):
        env.connector().extract(FULL_WINDOW, PlainSink())


def test_healthcheck(env: Env, tmp_path: Path) -> None:
    assert env.connector().healthcheck().ok is True
    missing = BankFileConnector(tmp_path / "nope", env.archive, env.accounts)
    assert missing.healthcheck().ok is False


def test_directbank_stub_is_not_configured() -> None:
    with pytest.raises(DirectBankNotConfigured, match="DirectBank") as exc:
        OneCDirectBankClient()
    assert isinstance(exc.value, ConfigError)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_bank_connector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.banks.accounts'`.

- [ ] **Step 3: Hisob kodi, kurs va fayl jurnali**

`backend/app/etl/banks/accounts.py`:
```python
"""Hisob raqami → `banks.accounts` yozuvi. Kod — HMAC (blind_index_key, "account"): ochiq raqam
sozlamada ham, jurnalda ham saqlanmaydi; dim_bank.account_bidx bilan bir xil kalit va yorliq."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.config import get_settings
from app.core.crypto import blind_index
from app.etl.banks.models import normalize_account
from app.etl.banks.registry import BankAccount


def account_code(account: str, key: bytes | None = None) -> str:
    secret = key if key is not None else get_settings().key_bytes("blind_index_key")
    return "BA-" + blind_index(secret, "account", normalize_account(account)).hex()[:16]


class AccountIndex:
    def __init__(self, accounts: Sequence[BankAccount], key: bytes | None = None) -> None:
        self._by_code = {a.code: a for a in accounts}
        self._key = key if key is not None else get_settings().key_bytes("blind_index_key")

    def resolve(self, account: str) -> BankAccount | None:
        return self._by_code.get(account_code(account, self._key))
```

`backend/app/etl/banks/fx.py`:
```python
"""Valyuta hisoblari summalarini so'mga o'girish uchun ЦБ kursi (dwh.fx_rate, S2 spec 3.2).

Kurs `day` dan ko'pi bilan MAX_FX_AGE_DAYS kun eski bo'lishi kerak — eskirgan kurs jimgina
ishlatilmaydi (hisob-kun `fx_rate_missing` bilan rad etiladi).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import text

from app.dwh.dates import date_id
from app.etl.db import etl_transaction

MAX_FX_AGE_DAYS = 10


class FxLookup(Protocol):
    def rate(self, currency: str, day: date) -> Decimal | None: ...


class DbFxLookup:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], Decimal | None] = {}

    def rate(self, currency: str, day: date) -> Decimal | None:
        if currency == "UZS":
            return Decimal(1)
        key = (currency, date_id(day))
        if key not in self._cache:
            with etl_transaction() as conn:
                value = conn.execute(text(
                    "SELECT rate FROM dwh.fx_rate WHERE currency = :c AND date_id <= :d "
                    "AND date_id >= :lo ORDER BY date_id DESC LIMIT 1"),
                    {"c": currency, "d": date_id(day),
                     "lo": date_id(day - timedelta(days=MAX_FX_AGE_DAYS))}).scalar_one_or_none()
            self._cache[key] = None if value is None else Decimal(value)
        return self._cache[key]
```

`backend/app/etl/banks/ledger.py`:
```python
"""Bank fayllari jurnali (core.bank_files): SHA-256 bo'yicha — fayl qayta o'qilmaydi, agar u
rad etilgan (yakuniy) yoki muvaffaqiyatli tugagan ETL yugurishida staging'ga yozilgan bo'lsa.
Muvaffaqiyatsiz yugurishdagi fayl keyingi safar qayta o'qiladi (S2 spec 3.2).
Jurnal yozuvi alohida tranzaksiyada — yugurish natijasidan qat'i nazar saqlanadi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import text

from app.etl.db import etl_transaction


@dataclass(frozen=True, slots=True)
class FileEntry:
    sha256: str
    bank_code: str
    file_name: str  # maskalangan
    size_bytes: int
    kind: str  # statement | orders | unknown
    status: str  # staged | rejected
    run_id: int | None
    row_count: int
    error_count: int
    archive_path: str | None


@dataclass(frozen=True, slots=True)
class LedgerRow:
    first_seen_at: datetime
    bank_code: str
    file_name: str
    kind: str
    status: str
    run_id: int | None
    row_count: int
    error_count: int


class FileLedger(Protocol):
    def done(self, sha256: str) -> bool: ...

    def mark(self, entry: FileEntry) -> None: ...


class DbFileLedger:
    def done(self, sha256: str) -> bool:
        with etl_transaction() as conn:
            row = conn.execute(text(
                "SELECT f.status, r.status AS run_status FROM core.bank_files f "
                "LEFT JOIN core.etl_run r ON r.id = f.run_id WHERE f.sha256 = :h"),
                {"h": sha256}).one_or_none()
        if row is None:
            return False
        return row.status == "rejected" or row.run_status == "success"

    def mark(self, entry: FileEntry) -> None:
        with etl_transaction() as conn:
            conn.execute(text(
                "INSERT INTO core.bank_files (sha256, bank_code, file_name, size_bytes, kind, "
                "status, run_id, row_count, error_count, archive_path) VALUES (:sha, :bank, "
                ":name, :size, :kind, :status, :run, :rows, :errors, :archive) "
                "ON CONFLICT (sha256) DO UPDATE SET kind = EXCLUDED.kind, "
                "status = EXCLUDED.status, run_id = EXCLUDED.run_id, "
                "row_count = EXCLUDED.row_count, error_count = EXCLUDED.error_count, "
                "archive_path = EXCLUDED.archive_path, updated_at = now()"),
                {"sha": entry.sha256, "bank": entry.bank_code, "name": entry.file_name[:255],
                 "size": entry.size_bytes, "kind": entry.kind, "status": entry.status,
                 "run": entry.run_id, "rows": entry.row_count, "errors": entry.error_count,
                 "archive": entry.archive_path})

    def recent(self, limit: int) -> list[LedgerRow]:
        with etl_transaction() as conn:
            rows = conn.execute(text(
                "SELECT first_seen_at, bank_code, file_name, kind, status, run_id, row_count, "
                "error_count FROM core.bank_files ORDER BY first_seen_at DESC LIMIT :n"),
                {"n": max(1, min(limit, 1000))}).all()
        return [LedgerRow(r.first_seen_at, r.bank_code, r.file_name, r.kind, r.status,
                          r.run_id, r.row_count, r.error_count) for r in rows]
```

- [ ] **Step 4: `BankMapper`**

`backend/app/etl/banks/mapper.py`:
```python
"""ParsedFile → staging (S2 spec 3.2): hisob moslashtirish, ko'chirma balansi tekshiruvi,
valyuta kursi, kontragent (faqat yuridik shaxs), idempotentlik kalitlari (manba, hujjat turi,
tashqi id — TZ 8). Xatolar ReportingSink.error ga (hisob raqami maskalangan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from app.core.crypto import blind_index
from app.dwh.dates import date_id
from app.etl.banks.accounts import AccountIndex
from app.etl.banks.fx import FxLookup
from app.etl.banks.models import BalanceRow, LineRow, ParsedFile, mask
from app.etl.banks.registry import BANKS, BankAccount
from app.etl.types import ReportingSink

ERROR_LIMIT = 1000
MLN = Decimal(1_000_000)
CENT = Decimal("0.01")
TOLERANCE = Decimal("0.01")


def to_mln(amount: Decimal, rate: Decimal) -> Decimal:
    return (amount * rate / MLN).quantize(CENT, rounding=ROUND_HALF_EVEN)


@dataclass
class _Group:
    opening: BalanceRow | None = None
    closing: BalanceRow | None = None
    lines: list[LineRow] = field(default_factory=list)

    def first_line(self) -> int:
        marks = [x.line for x in self.lines]
        marks += [x.line for x in (self.opening, self.closing) if x is not None]
        return min(marks)


class BankMapper:
    def __init__(self, sink: ReportingSink, accounts: AccountIndex, fx: FxLookup, *,
                 index_key: bytes) -> None:
        self.sink = sink
        self.accounts = accounts
        self.fx = fx
        self.index_key = index_key
        self.errors = 0
        self._banks: set[str] = set()
        self._cps: set[str] = set()

    def report(self, where: str, code: str, message: str) -> None:
        self.errors += 1
        if self.errors <= ERROR_LIMIT:
            self.sink.error(target="bank_file", code=code, src_id=mask(where),
                            message=mask(f"{where}: {message}"))

    def stage(self, bank_code: str, file: str, parsed: ParsedFile) -> int:
        for err in parsed.errors:
            self.report(f"{file}:{err.line}", "bad_row", err.message)
        reported: set[str] = set()
        docs: set[tuple[str, str]] = set()
        if parsed.kind == "statement":
            return self._statement(bank_code, file, parsed, reported, docs)
        return self._orders(bank_code, file, parsed, reported, docs)

    # ── Yordamchilar ────────────────────────────────────────────────
    def _resolve(self, bank_code: str, where: str, account: str,
                 reported: set[str]) -> BankAccount | None:
        acc = self.accounts.resolve(account)
        if acc is None:
            if account not in reported:
                reported.add(account)
                self.report(where, "unknown_account",
                            f"счёт …{account[-4:]} не сопоставлен с филиалом (banks.accounts)")
            return None
        if acc.bank_code != bank_code:
            if account not in reported:
                reported.add(account)
                self.report(where, "wrong_bank",
                            f"счёт …{acc.last4} открыт в банке «{acc.bank_code}», "
                            f"файл — в каталоге «{bank_code}»")
            return None
        return acc

    def _rate(self, where: str, acc: BankAccount, day: date) -> Decimal | None:
        rate = self.fx.rate(acc.currency, day)
        if rate is None:
            self.report(where, "fx_rate_missing",
                        f"нет курса ЦБ {acc.currency} на {day:%d.%m.%Y} (счёт …{acc.last4})")
        return rate

    def _bank(self, acc: BankAccount, account: str) -> None:
        if acc.code not in self._banks:
            self._banks.add(acc.code)
            # account_number staging'da shifrlanadi (dim_bank.account_enc + account_bidx).
            self.sink.add("dim_bank", {"code": acc.code, "bank_name": BANKS[acc.bank_code],
                                       "account_number": account, "currency": acc.currency})

    def _counterparty(self, inn: str | None, name: str | None) -> str | None:
        # Faqat yuridik shaxs (9 xonali INN); jismoniy shaxs (ПИНФЛ, INN yo'q) — shaxsiy
        # ma'lumot saqlanmaydi (S2 spec 3.2).
        if inn is None or len(inn) != 9 or not name:
            return None
        code = "CP-" + blind_index(self.index_key, "inn", inn).hex()[:16]
        if code not in self._cps:
            self._cps.add(code)
            self.sink.add("dim_counterparty", {"code": code, "name": name, "kind": "other",
                                               "inn": inn})
        return code

    @staticmethod
    def _extras(row: dict[str, Any], item_code: str | None, cp_code: str | None) -> None:
        if item_code:
            row["item_code"] = item_code  # yo'q bo'lsa merge «Прочие» + ogohlantirish
        if cp_code:
            row["cp_code"] = cp_code

    def _statement(self, bank_code: str, file: str, parsed: ParsedFile, reported: set[str],
                   docs: set[tuple[str, str]]) -> int:
        groups: dict[tuple[str, date], _Group] = {}
        for b in parsed.balances:
            group = groups.setdefault((b.account, b.day), _Group())
            if b.kind == "OB":
                group.opening = b
            else:
                group.closing = b
        for ln in parsed.lines:
            groups.setdefault((ln.account, ln.day), _Group()).lines.append(ln)
        staged = 0
        for (account, day), g in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            where = f"{file}:{g.first_line()}"
            acc = self._resolve(bank_code, where, account, reported)
            if acc is None:
                continue
            if g.opening is not None and g.closing is not None:
                moved = sum((x.amount if x.direction == "in" else -x.amount for x in g.lines),
                            Decimal(0))
                if abs(g.opening.amount + moved - g.closing.amount) > TOLERANCE:
                    self.report(where, "statement_mismatch",
                                f"выписка по счёту …{acc.last4} за {day:%d.%m.%Y} не сходится: "
                                "входящий остаток + обороты ≠ исходящий остаток")
                    continue
            rate = self._rate(where, acc, day)
            if rate is None:
                continue
            self._bank(acc, account)
            if g.closing is not None:
                self.sink.add("fact_balance", {
                    "doc_type": "bank_balance", "src_id": f"{acc.code}:{date_id(day)}",
                    "date_id": date_id(day), "branch_code": acc.branch_code,
                    "bank_code": acc.code, "balance": to_mln(g.closing.amount, rate)})
                staged += 1
            for ln in g.lines:
                if (acc.code, ln.doc_id) in docs:
                    self.report(f"{file}:{ln.line}", "duplicate_doc",
                                f"повтор проводки {ln.doc_id}")
                    continue
                docs.add((acc.code, ln.doc_id))
                row: dict[str, Any] = {
                    "doc_type": "bank_statement", "src_id": f"{acc.code}:{ln.doc_id}",
                    "date_id": date_id(day), "branch_code": acc.branch_code,
                    "direction": ln.direction, "amount": to_mln(ln.amount, rate),
                    "gl_account": acc.gl_account, "bank_code": acc.code}
                self._extras(row, ln.item_code, self._counterparty(ln.cp_inn, ln.cp_name))
                self.sink.add("fact_cashflow", row)
                staged += 1
        return staged

    def _orders(self, bank_code: str, file: str, parsed: ParsedFile, reported: set[str],
                docs: set[tuple[str, str]]) -> int:
        staged = 0
        for o in parsed.orders:
            where = f"{file}:{o.line}"
            acc = self._resolve(bank_code, where, o.account, reported)
            if acc is None:
                continue
            if (acc.code, o.doc_id) in docs:
                self.report(where, "duplicate_doc", f"повтор поручения {o.doc_id}")
                continue
            docs.add((acc.code, o.doc_id))
            rate = self._rate(where, acc, o.day)
            if rate is None:
                continue
            self._bank(acc, o.account)
            row: dict[str, Any] = {
                "doc_type": "bank_payment_order", "src_id": f"{acc.code}:{o.doc_id}",
                "date_id": date_id(o.day), "branch_code": acc.branch_code,
                "bank_code": acc.code, "amount": to_mln(o.amount, rate), "status": o.status,
                "status_date_id": None if o.status_day is None else date_id(o.status_day)}
            self._extras(row, o.item_code, self._counterparty(o.cp_inn, o.cp_name))
            self.sink.add("fact_payment_order", row)
            staged += 1
        return staged
```

- [ ] **Step 5: Konnektor va DirectBank stub'i**

`backend/app/etl/banks/connector.py`:
```python
"""BankFileConnector — SourceConnector (S2 spec 3.2): /data/import/banks/<bank>/*.csv.

Inbox faqat o'qish uchun ulangan: fayl o'chirilmaydi, balki arxivga baytma-bayt nusxalanadi
(<archive>/<bank>/<YYYY-MM>/<sha256>.csv) va core.bank_files jurnaliga yoziladi. Faqat yoshi
≥ min_age va hajmi ≤ max_bytes bo'lgan `*.csv` o'qiladi (yuklanayotgan fayl o'qilmaydi).
Maqsadlar «to'liq berilgan» emas (by_target bo'sh): fayllar inkremental, oldingi ko'chirmalar
o'chirilmaydi — faqat idempotent upsert.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.etl.banks.accounts import AccountIndex
from app.etl.banks.adapters import ADAPTERS
from app.etl.banks.fx import DbFxLookup, FxLookup
from app.etl.banks.ledger import DbFileLedger, FileEntry, FileLedger
from app.etl.banks.mapper import BankMapper
from app.etl.banks.models import BankFileError, mask
from app.etl.banks.registry import BANKS, BankAccount
from app.etl.types import (
    ControlTotals,
    ExtractStats,
    HealthResult,
    ReportingSink,
    StagingSink,
    Watermark,
    Window,
)

MAX_BYTES = 50 * 1024 * 1024
MIN_AGE_SECONDS = 60.0
log = get_logger("ugekazna.banks")


class BankFileConnector:
    def __init__(self, inbox: Path, archive: Path, accounts: Sequence[BankAccount], *,
                 formats: Mapping[str, str] | None = None, ledger: FileLedger | None = None,
                 fx: FxLookup | None = None, source: str = "banks",
                 index_key: bytes | None = None, min_age: float = MIN_AGE_SECONDS,
                 max_bytes: int = MAX_BYTES, now: Callable[[], float] = time.time) -> None:
        self.source = source
        self.inbox = inbox
        self.archive = archive
        self.accounts = list(accounts)
        self.formats = dict(formats or {})
        self.ledger: FileLedger = ledger or DbFileLedger()
        self.fx: FxLookup = fx or DbFxLookup()
        self.index_key = index_key or get_settings().key_bytes("blind_index_key")
        self.min_age = min_age
        self.max_bytes = max_bytes
        self.now = now

    # ── Protokol ────────────────────────────────────────────────────
    def healthcheck(self) -> HealthResult:
        if not self.inbox.is_dir() or not os.access(self.inbox, os.R_OK | os.X_OK):
            return HealthResult(False, "каталог банковских выписок недоступен")
        if not self.archive.is_dir() or not os.access(self.archive, os.W_OK | os.X_OK):
            return HealthResult(False, "архив банковских выписок недоступен для записи")
        return HealthResult(True, "banks")

    def watermark(self) -> Watermark:
        return Watermark(datetime.now(UTC))

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None  # ko'chirma o'zini o'zi tekshiradi (OB + oborot = CB, mapper'da)

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        if not isinstance(sink, ReportingSink):
            raise TypeError("BankFileConnector: ReportingSink kerak (xatolar core.etl_error ga)")
        mapper = BankMapper(sink, AccountIndex(self.accounts, self.index_key), self.fx,
                            index_key=self.index_key)
        total = 0
        for bank_code, path in self._candidates():
            display = mask(f"{bank_code}/{path.name}")
            size = path.stat().st_size
            if size > self.max_bytes:
                mapper.report(display, "too_large",
                              f"файл больше {self.max_bytes // (1024 * 1024)} МБ — не обработан")
                continue
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if self.ledger.done(sha):
                continue
            archived = self._archive(bank_code, sha, data)
            adapter = ADAPTERS[self.formats.get(bank_code, "canonical")]
            before = mapper.errors
            try:
                parsed = adapter.parse(data, display)
            except BankFileError as exc:
                mapper.report(display, exc.code, str(exc))
                self.ledger.mark(FileEntry(sha, bank_code, display, len(data), "unknown",
                                           "rejected", sink.load_id, 0, 1, archived))
                continue
            staged = mapper.stage(bank_code, display, parsed)
            total += staged
            self.ledger.mark(FileEntry(sha, bank_code, display, len(data), parsed.kind, "staged",
                                       sink.load_id, staged, mapper.errors - before, archived))
            log.info("bank_file_staged", bank=bank_code, file=display, kind=parsed.kind,
                     rows=staged, errors=mapper.errors - before)
        return ExtractStats(total, {})

    # ── Yordamchilar ────────────────────────────────────────────────
    def _candidates(self) -> list[tuple[str, Path]]:
        found: list[tuple[float, str, str, Path]] = []
        for bank_code in sorted(BANKS):
            folder = self.inbox / bank_code
            if not folder.is_dir():
                continue
            for path in folder.glob("*.csv"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if path.is_file() and self.now() - stat.st_mtime >= self.min_age:
                    found.append((stat.st_mtime, path.name, bank_code, path))
        return [(bank, path) for _, _, bank, path in sorted(found)]

    def _archive(self, bank_code: str, sha: str, data: bytes) -> str:
        folder = self.archive / bank_code / datetime.now(UTC).strftime("%Y-%m")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{sha}.csv"
        if not target.exists():
            partial = folder / f"{sha}.part"
            partial.write_bytes(data)
            os.chmod(partial, 0o640)
            partial.replace(target)
        return str(target.relative_to(self.archive))
```

`backend/app/etl/banks/directbank.py`:
```python
"""DirectBank (1С) — interfeys va stub (S2 spec 3.2). Mijoz 1C konfiguratsiyasi, ochiladigan
ma'lumot va texnik hisob haqida javob berguncha ulanish yo'q; javobdan keyin DirectBankClient
amalga oshiriladi va BankMapper (fayl yo'li bilan umumiy) orqali staging'ga yoziladi."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.core.config import ConfigError
from app.etl.banks.models import ParsedFile

DIRECTBANK_MESSAGE = ("DirectBank (1С) не настроен: ожидается ответ заказчика по формату и "
                      "доступу; выписки загружаются файлами (docs/integration/banks-connector.md)")


class DirectBankNotConfigured(ConfigError):
    """DirectBank ulanishi sozlanmagan."""


class DirectBankClient(Protocol):
    def statements(self, account_codes: Sequence[str], day: date) -> ParsedFile: ...

    def order_statuses(self, account_codes: Sequence[str], day: date) -> ParsedFile: ...


class OneCDirectBankClient:
    """1С DirectBank mijozi — hozircha yaratib bo'lmaydi."""

    def __init__(self) -> None:
        raise DirectBankNotConfigured(DIRECTBANK_MESSAGE)

    def statements(self, account_codes: Sequence[str], day: date) -> ParsedFile:
        raise DirectBankNotConfigured(DIRECTBANK_MESSAGE)

    def order_statuses(self, account_codes: Sequence[str], day: date) -> ParsedFile:
        raise DirectBankNotConfigured(DIRECTBANK_MESSAGE)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_bank_connector.py tests/test_bank_canonical.py tests/test_cashflow_precedence.py -v`
Expected: barcha testlar passed. `$TEST ruff check app/etl/banks tests` va `$TEST mypy app` — xatosiz.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(banks): BankFileConnector — moslashtirish, balans tekshiruvi, kurs, fayl jurnali, arxiv; DirectBank stub

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Banklar — manbalar reyestri, operator CLI, worker jadvali va rad etilgan qatorlar xabari

**Files:**
- Create: `backend/app/etl/banks/admin.py`
- Modify: `backend/app/etl/connectors.py`, `backend/app/cli.py`, `backend/app/worker.py`, `backend/tests/test_worker.py`
- Test: `backend/tests/test_bank_ops.py`

**Interfaces:**
- Consumes: `BankFileConnector`, `BankAccount`, `DIRECTBANK_MESSAGE`, `account_code`, `DbFileLedger`, `FileEntry`, `current_setting`, `validate_setting`, `record`, `AuditAction.SETTING_UPDATED`, `run_etl_job`, `Notification`, `Notifier`, `RecordingNotifier`, `tests.s2_helpers.put_setting`.
- Produces:
  - `KNOWN_SOURCES` += `"banks"`, `"directbank"`; `make_connector("banks")` (`banks.accounts` bo'sh → `ConfigError`), `make_connector("directbank")` → `ConfigError(DIRECTBANK_MESSAGE)`.
  - `app.etl.banks.admin`: `ACCOUNT_COLUMNS`, `read_accounts(path, key) -> list[dict[str, str]]`, `bank_accounts_command(file, out) -> int`, `bank_files_command(limit, out) -> int`.
  - CLI: `python -m app.cli bank-accounts [--file accounts.csv]` (0 / 1), `python -m app.cli bank-files [--limit N]`.
  - Worker: `notify_bank_errors(run_id, notifier) -> int`, `run_banks_job(notifier) -> RunResult | None`; job `etl_banks` (`etl.banks_cron`) — faqat `bank_inbox_dir` katalogi mavjud bo'lsa.

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_bank_ops.py`:
```python
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import ConfigError, get_settings
from app.core.db import get_engine
from app.dwh.reference import current_setting
from app.etl.banks.accounts import account_code
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.ledger import DbFileLedger, FileEntry
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.staging import DbStagingSink
from tests.etl_helpers import RecordingNotifier, new_source, open_run
from tests.s2_helpers import put_setting

HEADER = "account;bank_code;branch_code;currency;gl_account"
ACC = "20210000900100000077"


@pytest.fixture
def accounts_setting() -> Iterator[None]:
    yield
    put_setting("banks.accounts", [])


def test_bank_accounts_cli(tmp_path: Path, accounts_setting: None,
                           capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "accounts.csv"
    good.write_text(f"{HEADER}\n{ACC[:4]} {ACC[4:]};sqb;UGE-02;uzs;5110\n", encoding="utf-8")
    assert cli.main(["bank-accounts", "--file", str(good)]) == 0
    with get_engine("app").connect() as conn:
        stored = current_setting(conn, "banks.accounts")
    assert stored == [{"code": account_code(ACC), "bank_code": "sqb", "branch_code": "UGE-02",
                       "currency": "UZS", "gl_account": "5110", "last4": "0077"}]
    assert ACC not in json.dumps(stored)
    with get_engine("migrator").connect() as conn:
        details = conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.setting.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert details["via"] == "cli" and details["accounts"] == 1
    assert cli.main(["bank-accounts"]) == 0
    bad = tmp_path / "bad.csv"
    bad.write_text(f"{HEADER}\n{ACC};sqb;NOPE;UZS;5110\n", encoding="utf-8")
    assert cli.main(["bank-accounts", "--file", str(bad)]) == 1
    short = tmp_path / "short.csv"
    short.write_text(f"{HEADER}\n{ACC[:-1]};sqb;UGE-02;UZS;5110\n", encoding="utf-8")
    assert cli.main(["bank-accounts", "--file", str(short)]) == 1
    out = capsys.readouterr().out
    assert "…0077" in out and "NOPE" in out
    assert ACC not in out and ACC[:-1] not in out


def test_make_connector_banks_and_directbank(tmp_path: Path, accounts_setting: None) -> None:
    settings = get_settings().model_copy(update={"bank_inbox_dir": str(tmp_path / "in"),
                                                 "bank_archive_dir": str(tmp_path / "ar")})
    assert {"banks", "directbank"} <= set(KNOWN_SOURCES)
    with pytest.raises(ConfigError, match="banks.accounts"):
        make_connector("banks", settings)
    put_setting("banks.accounts", [{"code": "BA-0123456789abcdef", "bank_code": "sqb",
                                    "branch_code": "UGE-02", "currency": "UZS",
                                    "gl_account": "5110", "last4": "0001"}])
    made = make_connector("banks", settings)
    assert isinstance(made, BankFileConnector) and made.inbox == tmp_path / "in"
    assert made.accounts[0].code == "BA-0123456789abcdef" and made.formats["sqb"] == "canonical"
    with pytest.raises(ConfigError, match="DirectBank"):
        make_connector("directbank", settings)


def test_bank_files_cli(capsys: pytest.CaptureFixture[str]) -> None:
    DbFileLedger().mark(FileEntry("a" * 64, "sqb", "sqb/…0001_x.csv", 10, "unknown", "rejected",
                                  None, 0, 1, None))
    assert cli.main(["bank-files", "--limit", "5"]) == 0
    assert "sqb/…0001_x.csv" in capsys.readouterr().out


def test_notify_bank_errors() -> None:
    source = new_source()
    run = open_run(source)
    notifier = RecordingNotifier()
    assert worker.notify_bank_errors(run, notifier) == 0 and notifier.items == []
    with etl_transaction() as conn:
        sink = DbStagingSink(conn, run, source)
        for code in ("bad_row", "bad_row", "unknown_account"):
            sink.error(target="bank_file", code=code, message="m")
    assert worker.notify_bank_errors(run, notifier) == 3
    assert notifier.kinds == ["bank_rows_rejected"]
    assert "bad_row: 2" in notifier.items[0].body
    assert "unknown_account: 1" in notifier.items[0].body
```

`backend/tests/test_worker.py` — oxiriga qo'shing:
```python
def test_scheduler_adds_bank_job_when_inbox_exists(tmp_path: Path) -> None:
    settings = get_settings().model_copy(update={"bank_inbox_dir": str(tmp_path)})
    jobs = {j.id: j for j in worker.build_scheduler(settings, RecordingNotifier()).get_jobs()}
    assert jobs["etl_banks"].func is worker.run_banks_job
    missing = get_settings().model_copy(update={"bank_inbox_dir": str(tmp_path / "nope")})
    ids = {j.id for j in worker.build_scheduler(missing, RecordingNotifier()).get_jobs()}
    assert "etl_banks" not in ids
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_bank_ops.py tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.banks.admin'` / `AttributeError: module 'app.worker' has no attribute 'notify_bank_errors'`.

- [ ] **Step 3: Operator buyruqlari**

`backend/app/etl/banks/admin.py`:
```python
"""Operator CLI: bank hisoblari moslashtirishi (`banks.accounts`) va fayl jurnali.

Hisob raqamlari faylda ochiq keladi, lekin sozlamaga faqat `BA-` kodi va oxirgi 4 raqam
yoziladi; chiqish va xato matnlarida — `…1234` (S2 spec 3.2).
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from app.audit.service import AuditAction, AuditEvent, record
from app.core.config import get_settings
from app.core.db import get_engine
from app.dwh.dates import TASHKENT
from app.dwh.reference import current_setting, validate_setting
from app.etl.banks.accounts import account_code
from app.etl.banks.ledger import DbFileLedger
from app.etl.banks.models import mask, normalize_account
from app.etl.db import etl_transaction

ACCOUNT_COLUMNS = ("account", "bank_code", "branch_code", "currency", "gl_account")
Out = Callable[[str], None]


def read_accounts(path: Path, key: bytes) -> list[dict[str, str]]:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path.name}: faylni o'qib bo'lmadi (UTF-8 CSV kerak)") from exc
    reader = csv.DictReader(io.StringIO(content, newline=""), delimiter=";")
    header = tuple(h.strip().lower() for h in reader.fieldnames or ())
    if header != ACCOUNT_COLUMNS:
        raise ValueError(f"{path.name}: sarlavha «{';'.join(ACCOUNT_COLUMNS)}» bo'lishi kerak")
    out: list[dict[str, str]] = []
    for line, raw in enumerate(reader, start=2):
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f"{path.name}:{line}: maydonlar soni noto'g'ri")
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        account = normalize_account(row["account"])
        if not re.fullmatch(r"\d{20}", account):
            raise ValueError(f"{path.name}:{line}: hisob raqami 20 raqamdan iborat bo'lishi kerak")
        out.append({"code": account_code(account, key), "bank_code": row["bank_code"],
                    "branch_code": row["branch_code"], "currency": row["currency"].upper(),
                    "gl_account": row["gl_account"], "last4": account[-4:]})
    return out


def _show(accounts: list[dict[str, str]], out: Out) -> None:
    for a in accounts:
        out(f"{a['code']}  {a['bank_code']:<8} {a['branch_code']:<10} {a['currency']} "
            f"{a['gl_account']}  …{a['last4']}")


def _put(key: str, value: object) -> int:
    with get_engine("app").begin() as conn:
        version = int(conn.execute(text(
            "SELECT coalesce(max(version), 0) FROM core.settings WHERE key = :k"),
            {"k": key}).scalar_one()) + 1
        conn.execute(text("UPDATE core.settings SET is_current = false "
                          "WHERE key = :k AND is_current"), {"k": key})
        conn.execute(text("INSERT INTO core.settings (key, version, value) "
                          "VALUES (:k, :v, CAST(:val AS jsonb))"),
                     {"k": key, "v": version, "val": json.dumps(value, ensure_ascii=False)})
    return version


def bank_accounts_command(file: Path | None, out: Out) -> int:
    if file is None:
        with get_engine("app").connect() as conn:
            current = list(current_setting(conn, "banks.accounts"))
        _show(current, out)
        out(f"banks.accounts: {len(current)} ta hisob")
        return 0
    try:
        value = validate_setting("banks.accounts",
                                 read_accounts(file, get_settings().key_bytes("blind_index_key")))
    except (KeyError, ValueError) as exc:
        out(f"Xato: {mask(str(exc))}")
        return 1
    with etl_transaction() as conn:
        known = set(conn.execute(text("SELECT code FROM dwh.dim_branch")).scalars())
    missing = sorted({a["branch_code"] for a in value} - known)
    if missing:
        out(f"Xato: noma'lum filial kodlari: {', '.join(missing)}")
        return 1
    version = _put("banks.accounts", value)
    record(AuditEvent(action=AuditAction.SETTING_UPDATED, object_type="setting",
                      object_id="banks.accounts",
                      details={"via": "cli", "version": version, "accounts": len(value)}))
    _show(value, out)
    out(f"banks.accounts: versiya {version}, {len(value)} ta hisob")
    return 0


def bank_files_command(limit: int, out: Out) -> int:
    rows = DbFileLedger().recent(limit)
    for r in rows:
        run = r.run_id if r.run_id is not None else "-"
        out(f"{r.first_seen_at.astimezone(TASHKENT):%d.%m.%Y %H:%M}  {r.bank_code:<8} "
            f"{r.status:<9} {r.kind:<9} run={run} строк={r.row_count} ошибок={r.error_count}  "
            f"{r.file_name}")
    out(f"Файлов: {len(rows)}")
    return 0
```

- [ ] **Step 4: Manbalar reyestri**

`backend/app/etl/connectors.py` — importlarga qo'shing:
```python
from app.etl.banks.connector import BankFileConnector
from app.etl.banks.directbank import DIRECTBANK_MESSAGE
from app.etl.banks.registry import BankAccount
```
`KNOWN_SOURCES` qatorini almashtiring:
```python
KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "directbank")
```
`_onec` funksiyasidan keyin qo'shing:
```python
def _banks(settings: Settings) -> BankFileConnector:
    with get_engine("etl").connect() as conn:
        accounts = current_setting(conn, "banks.accounts")
        formats = current_setting(conn, "banks.formats")
    if not accounts:
        raise ConfigError("banks.accounts bo'sh: `python -m app.cli bank-accounts --file …` "
                          "bilan sozlang")
    return BankFileConnector(Path(settings.bank_inbox_dir), Path(settings.bank_archive_dir),
                             [BankAccount.model_validate(a) for a in accounts],
                             formats=dict(formats))
```
`make_connector` ichida `raise ValueError(...)` dan oldin qo'shing:
```python
    if source == "banks":
        return _banks(settings)
    if source == "directbank":
        raise ConfigError(DIRECTBANK_MESSAGE)
```

- [ ] **Step 5: CLI va worker**

`backend/app/cli.py` — importlarga:
```python
from app.etl.banks.admin import bank_accounts_command, bank_files_command
```
`main` ichida — oxirgi `sub.add_parser(...)` blokidan keyin:
```python
    p = sub.add_parser("bank-accounts")
    p.add_argument("--file", type=Path, default=None)
    p = sub.add_parser("bank-files")
    p.add_argument("--limit", type=int, default=50)
```
dispatch'da (oxirgi zaxira `return …` dan oldin):
```python
    if args.command == "bank-accounts":
        return bank_accounts_command(args.file, _out)
    if args.command == "bank-files":
        return bank_files_command(args.limit, _out)
```
Modul docstring'idagi buyruqlar ro'yxatiga:
```
bank-accounts  — bank hisoblari ↔ filiallar (CSV fayldan; faylsiz — ko'rsatish, raqamlar maskalangan)
bank-files     — bank fayllari jurnali (oxirgi N ta)
```

`backend/app/worker.py` — `run_etl_job` funksiyasidan keyin qo'shing:
```python
def notify_bank_errors(run_id: int, notifier: Notifier) -> int:
    """Bank fayllaridagi rad etilgan qator/fayllar haqida bitta xabar (S2 spec 3.2)."""
    with etl_transaction() as conn:
        rows = conn.execute(text(
            "SELECT code, count(*) AS n FROM core.etl_error WHERE run_id = :r "
            "AND step = 'extract' AND target = 'bank_file' GROUP BY code ORDER BY code"),
            {"r": run_id}).all()
    total = sum(int(r.n) for r in rows)
    if total:
        parts = ", ".join(f"{r.code}: {r.n}" for r in rows)
        notifier.notify(Notification(
            "bank_rows_rejected", "Строки банковских выписок отклонены",
            f"Запуск №{run_id}: отклонено {total} ({parts}). "
            "Подробности — «Состояние обменов» или `python -m app.cli bank-files`."))
    return total


def run_banks_job(notifier: Notifier) -> RunResult | None:
    result = run_etl_job("banks", Mode.INCREMENTAL, notifier)
    if result is not None and result.run_id is not None:
        notify_bank_errors(result.run_id, notifier)
    return result
```
`build_scheduler` ichida (S1'ning `onec` bloki va `process_requests` jobi orasida) qo'shing:
```python
    if Path(settings.bank_inbox_dir).is_dir():
        with get_engine("app").connect() as conn:
            banks_cron = str(current_setting(conn, "etl.banks_cron"))
        # TZ 8: banklar — kuniga 4 marta; 1C inkremental (10, 13, 16) bilan to'qnashmaydi.
        scheduler.add_job(run_banks_job, CronTrigger.from_crontab(banks_cron, timezone=TASHKENT),
                          args=(notifier,), id="etl_banks", **opts)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_bank_ops.py tests/test_worker.py tests/test_file_connector.py tests/test_admin_dwh_api.py -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(banks): manbalar reyestri, bank-accounts/bank-files CLI, worker jadvali, rad etilgan qatorlar xabari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: ЦБ РУз kurslari — `CbuRatesConnector`, jadval va tarixni to'ldirish

**Files:**
- Create: `backend/app/etl/cbu/__init__.py`, `backend/app/etl/cbu/client.py`, `backend/app/etl/cbu/connector.py`, `backend/tests/fixtures/cbu/all_2026-09-24.json`, `backend/tests/fixtures/cbu/all_2026-09-01.json`
- Modify: `backend/app/etl/connectors.py`, `backend/app/worker.py`, `backend/app/cli.py`, `backend/tests/test_worker.py`
- Test: `backend/tests/test_cbu.py`

**Interfaces:**
- Consumes: `ConnectorUnavailableError`, `ConfigError`, `ExtractStats`, `HealthResult`, `Watermark`, `StagingSink`, `Window`, `date_id`, `today_tashkent`, `Runner`, `EtlBusyError`, `Mode`, `current_setting` (`fx.currencies`, `fx.lookback_days`, `etl.cbu_cron`), `Settings.cbu_enabled/cbu_base_url/egress_proxy`, `run_etl_job`.
- Produces:
  - `app.etl.cbu.client`: `RATES_PATH = "/ru/arkhiv-kursov-valyut/json/all/{day}/"`, `TIMEOUT`, `MAX_BYTES = 1 MiB`, `CbuError(ValueError)`, `CbuRate(ccy, rate, nominal, day)` + `.per_unit -> Decimal` (6 kasr), `CbuClient(base_url="https://cbu.uz", *, proxy="", transport=None, timeout=TIMEOUT, max_bytes=MAX_BYTES)` + `.rates(day) -> list[CbuRate]`, `.http`, `.close()`.
  - `app.etl.cbu.connector`: `SOURCE = "cbu"`, `MAX_BACKFILL_DAYS = 800`, `CbuRatesConnector(client, currencies, *, days=7, date_from=None, date_to=None, today=today_tashkent, sleep=time.sleep, pause=0.2, source="cbu")` + `.dates() -> list[date]` — `SourceConnector`; `fx_rate` qatori: `{"currency", "date_id" (so'ralgan kun), "rate" (Rate / Nominal)}`.
  - `KNOWN_SOURCES` += `"cbu"`; `cbu_connector(settings, *, date_from=None, date_to=None)`; `make_connector("cbu")` (`CBU_ENABLED=false` → `ConfigError`).
  - Worker job `etl_cbu` (`etl.cbu_cron`, faqat `cbu_enabled`); CLI `python -m app.cli cbu-backfill --from YYYY-MM-DD --to YYYY-MM-DD` (0 — success, 1 — xato/noto'g'ri oraliq, 2 — konfiguratsiya, 3 — band).

- [ ] **Step 1: Yozib olingan javoblar (fixture'lar)**

Javob shakli 2026-09-25 da `https://cbu.uz/ru/arkhiv-kursov-valyut/json/` va `…/json/all/2026-09-01/` dan tekshirilgan (75 valyuta; `Nominal` — satr, IDR/IRR/VND uchun `"10"`; dam olish kuni so'ralganda `Date` — oldingi o'rnatilgan kun). Fixture'lar — shu shakldagi qisqartirilgan nusxa.

`backend/tests/fixtures/cbu/all_2026-09-24.json`:
```json
[
  {"id": 68, "Code": "840", "Ccy": "USD", "CcyNm_RU": "Доллар США", "CcyNm_UZ": "AQSH dollari", "CcyNm_UZC": "АҚШ доллари", "CcyNm_EN": "US Dollar", "Nominal": "1", "Rate": "11814.05", "Diff": "12.82", "Date": "24.09.2026"},
  {"id": 20, "Code": "978", "Ccy": "EUR", "CcyNm_RU": "Евро", "CcyNm_UZ": "EVRO", "CcyNm_UZC": "ЕВРО", "CcyNm_EN": "Euro", "Nominal": "1", "Rate": "13482.19", "Diff": "-8.40", "Date": "24.09.2026"},
  {"id": 15, "Code": "156", "Ccy": "CNY", "CcyNm_RU": "Юань ренминби", "CcyNm_UZ": "Xitoy yuani", "CcyNm_UZC": "Хитой юани", "CcyNm_EN": "Yuan Renminbi", "Nominal": "1", "Rate": "1661.35", "Diff": "1.02", "Date": "24.09.2026"},
  {"id": 57, "Code": "643", "Ccy": "RUB", "CcyNm_RU": "Российский рубль", "CcyNm_UZ": "Rossiya rubli", "CcyNm_UZC": "Россия рубли", "CcyNm_EN": "Russian Ruble", "Nominal": "1", "Rate": "142.61", "Diff": "0.31", "Date": "24.09.2026"},
  {"id": 33, "Code": "360", "Ccy": "IDR", "CcyNm_RU": "Индонезийская рупия", "CcyNm_UZ": "Indoneziya rupiyasi", "CcyNm_UZC": "Индонезия рупияси", "CcyNm_EN": "Indonesian Rupiah", "Nominal": "10", "Rate": "6.66", "Diff": "0.01", "Date": "24.09.2026"}
]
```

`backend/tests/fixtures/cbu/all_2026-09-01.json` (1-sentabr — bayram, amaldagi kurs 28-avgustda o'rnatilgan):
```json
[
  {"id": 68, "Code": "840", "Ccy": "USD", "CcyNm_RU": "Доллар США", "CcyNm_UZ": "AQSH dollari", "CcyNm_UZC": "АҚШ доллари", "CcyNm_EN": "US Dollar", "Nominal": "1", "Rate": "11801.23", "Diff": "-22.46", "Date": "28.08.2026"}
]
```

- [ ] **Step 2: Testlarni yozish**

`backend/tests/test_cbu.py`:
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
from app.etl.cbu.client import CbuClient, CbuError
from app.etl.cbu.connector import CbuRatesConnector
from app.etl.connectors import KNOWN_SOURCES, make_connector
from app.etl.db import etl_transaction
from app.etl.runner import Runner
from app.etl.types import ConnectorUnavailableError, Mode, Window
from tests.etl_helpers import TEST_AS_OF, RecordingNotifier, new_source, purge_source

FIXTURES = Path(__file__).parent / "fixtures" / "cbu"
WINDOW = Window(date(2026, 9, 1), TEST_AS_OF)


class CollectSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def add(self, target: str, row: Mapping[str, Any]) -> None:
        self.rows.append((target, dict(row)))


def fake_cbu(bodies: Mapping[str, bytes | httpx.Response],
             seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        day = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        body = bodies.get(day)
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(200, content=body if body is not None else b"[]")

    return httpx.MockTransport(handler)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def client(bodies: Mapping[str, bytes | httpx.Response], **kw: Any) -> CbuClient:
    return CbuClient(transport=fake_cbu(bodies), **kw)


def test_parse_fixture_and_request_shape() -> None:
    seen: list[httpx.Request] = []
    c = CbuClient(transport=fake_cbu({"2026-09-24": fixture("all_2026-09-24.json")}, seen))
    rates = {r.ccy: r for r in c.rates(date(2026, 9, 24))}
    assert seen[0].url.path == "/ru/arkhiv-kursov-valyut/json/all/2026-09-24/"
    assert seen[0].method == "GET"
    assert rates["USD"].per_unit == Decimal("11814.050000")
    assert rates["USD"].day == date(2026, 9, 24)
    assert rates["IDR"].nominal == 10 and rates["IDR"].per_unit == Decimal("0.666000")
    assert c.http.trust_env is False and c.http.follow_redirects is False


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>Технические работы</html>"),
    httpx.Response(200, json={"rates": []}),
    httpx.Response(200, json=[{"Ccy": "USD", "Rate": "11 814,05", "Nominal": "1",
                               "Date": "24.09.2026"}]),
    httpx.Response(200, json=[{"Ccy": "USD", "Rate": "11814.05", "Nominal": "0",
                               "Date": "24.09.2026"}]),
    httpx.Response(302, headers={"location": "https://evil.test/"}),
    httpx.Response(404),
])
def test_bad_responses_are_not_retryable(response: httpx.Response) -> None:
    with pytest.raises(CbuError) as exc:
        client({"2026-09-24": response}).rates(date(2026, 9, 24))
    assert not isinstance(exc.value, ConnectorUnavailableError)


def test_transient_errors_are_retryable() -> None:
    with pytest.raises(ConnectorUnavailableError, match="503"):
        client({"2026-09-24": httpx.Response(503)}).rates(date(2026, 9, 24))

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(ConnectorUnavailableError, match="тайм-аут"):
        CbuClient(transport=httpx.MockTransport(timeout)).rates(date(2026, 9, 24))


def test_size_cap() -> None:
    big = httpx.Response(200, content=b"[" + b" " * 2000 + b"]")
    with pytest.raises(CbuError, match="больше"):
        client({"2026-09-24": big}, max_bytes=1000).rates(date(2026, 9, 24))


def test_connector_extract_dates_and_units() -> None:
    sleeps: list[float] = []
    connector = CbuRatesConnector(
        client({"2026-09-24": fixture("all_2026-09-24.json"),
                "2026-09-01": fixture("all_2026-09-01.json")}),
        ["USD", "EUR", "IDR"], date_from=date(2026, 9, 1), date_to=date(2026, 9, 2),
        sleep=sleeps.append)
    assert connector.dates() == [date(2026, 9, 1), date(2026, 9, 2)]
    sink = CollectSink()
    stats = connector.extract(WINDOW, sink)
    # 1-sentabr — 28-avgust kursi shu kun uchun saqlanadi; 2-sentabr — bo'sh javob (o'tkaziladi).
    assert [row for _, row in sink.rows] == [
        {"currency": "USD", "date_id": 20260901, "rate": Decimal("11801.230000")}]
    assert stats.rows == 1 and stats.by_target == {"fx_rate": 1} and sleeps == [0.2]


def test_default_dates_are_last_days() -> None:
    connector = CbuRatesConnector(client({}), ["USD"], days=3, today=lambda: date(2026, 9, 24))
    assert connector.dates() == [date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)]
    with pytest.raises(ValueError):
        CbuRatesConnector(client({}), ["USD"], date_from=date(2026, 9, 2), date_to=date(2026, 9, 1))
    with pytest.raises(ValueError):
        CbuRatesConnector(client({}), ["USD"], date_from=date(2024, 1, 1),
                          date_to=date(2026, 9, 24))


def test_rate_dated_after_request_is_error() -> None:
    body = json.dumps([{"Ccy": "USD", "Rate": "1.00", "Nominal": "1", "Date": "25.09.2026"}])
    connector = CbuRatesConnector(client({"2026-09-24": body.encode()}), ["USD"], days=1,
                                  today=lambda: date(2026, 9, 24))
    with pytest.raises(CbuError, match="позже"):
        connector.extract(WINDOW, CollectSink())


def test_healthcheck() -> None:
    ok = CbuRatesConnector(client({"2026-09-24": fixture("all_2026-09-24.json")}), ["USD"],
                           today=lambda: date(2026, 9, 24))
    assert ok.healthcheck().ok is True
    down = CbuRatesConnector(client({"2026-09-24": httpx.Response(502)}), ["USD"],
                             today=lambda: date(2026, 9, 24))
    assert down.healthcheck().ok is False


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    yield name
    purge_source(name)


def test_runner_loads_rates_idempotently(source: str) -> None:
    # Test valyutasi (XTB) — sintetik USD/EUR kurslariga tegmaslik uchun.
    body = json.dumps([{"Ccy": "XTB", "Rate": "250.50", "Nominal": "10", "Date": "24.09.2026"}])
    for _ in range(2):
        connector = CbuRatesConnector(client({"2026-09-24": body.encode()}), ["XTB"], days=1,
                                      today=lambda: date(2026, 9, 24), source=source)
        result = Runner(connector, mode=Mode.INCREMENTAL, today=TEST_AS_OF,
                        sleep=lambda _: None).run()
        assert result.status == "success", result
    with etl_transaction() as conn:
        rows = conn.execute(text("SELECT date_id, rate FROM dwh.fx_rate WHERE currency = 'XTB'")
                            ).all()
    assert [(r.date_id, r.rate) for r in rows] == [(20260924, Decimal("25.050000"))]


def test_make_connector_and_worker_job() -> None:
    assert "cbu" in KNOWN_SOURCES
    with pytest.raises(ConfigError, match="CBU_ENABLED"):
        make_connector("cbu", get_settings().model_copy(update={"cbu_enabled": False}))
    enabled = get_settings().model_copy(update={"cbu_enabled": True})
    made = make_connector("cbu", enabled)
    assert isinstance(made, CbuRatesConnector) and made.currencies[:2] == ["USD", "EUR"]
    assert len(made.dates()) == 7
    jobs = {j.id: j for j in worker.build_scheduler(enabled, RecordingNotifier()).get_jobs()}
    assert jobs["etl_cbu"].args[:2] == ("cbu", Mode.INCREMENTAL)
    off = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "etl_cbu" not in off


def test_cli_backfill_validates_range(capsys: pytest.CaptureFixture[str],
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli.main(["cbu-backfill", "--from", "2026-09-10", "--to", "2026-09-01"]) == 1
    assert cli.main(["cbu-backfill", "--from", "2020-01-01", "--to", "2026-09-01"]) == 1
    monkeypatch.setattr(cli, "get_settings",
                        lambda: get_settings().model_copy(update={"cbu_enabled": False}))
    assert cli.main(["cbu-backfill", "--from", "2026-09-01", "--to", "2026-09-02"]) == 2
    assert "800" in capsys.readouterr().out
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_cbu.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.cbu'`.

- [ ] **Step 4: Implementatsiya — mijoz**

`backend/app/etl/cbu/__init__.py`:
```python
"""ЦБ РУз valyuta kurslari (TZ 8: har kuni, tarix bilan; S2 spec 3.3)."""
```

`backend/app/etl/cbu/client.py`:
```python
"""cbu.uz JSON arxivi mijozi: GET /ru/arkhiv-kursov-valyut/json/all/<YYYY-MM-DD>/.

Javob: [{"Ccy": "USD", "Nominal": "1", "Rate": "11830.87", "Date": "25.09.2026", …}] (2026-09-25 da
tekshirilgan). Vaqtinchalik xatolar (tarmoq, tayм-aut, 5xx, 429) → ConnectorUnavailableError
(runner qayta urinadi); format/4xx/redirect → CbuError (qayta urinilmaydi).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from app.etl.types import ConnectorUnavailableError

RATES_PATH = "/ru/arkhiv-kursov-valyut/json/all/{day}/"
TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
MAX_BYTES = 1024 * 1024
_RATE_RE = re.compile(r"^\d{1,12}(\.\d{1,8})?$")
_DAY_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_SIX = Decimal("0.000001")


class CbuError(ValueError):
    """Qayta urinilmaydigan ЦБ javob xatosi."""


def _rate(value: Any) -> Decimal:
    if isinstance(value, str) and _RATE_RE.fullmatch(value) and Decimal(value) > 0:
        return Decimal(value)
    raise ValueError("Rate: musbat son satri kerak (nuqta bilan)")


def _nominal(value: Any) -> int:
    if isinstance(value, str | int) and not isinstance(value, bool) \
            and re.fullmatch(r"\d{1,6}", str(value)) and int(value) >= 1:
        return int(value)
    raise ValueError("Nominal: musbat butun son kerak")


def _day(value: Any) -> date:
    if isinstance(value, str) and _DAY_RE.fullmatch(value):
        return datetime.strptime(value, "%d.%m.%Y").date()
    raise ValueError("Date: ДД.ММ.ГГГГ kerak")


class CbuRate(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    ccy: Annotated[str, Field(alias="Ccy", pattern=r"^[A-Z]{3}$")]
    rate: Annotated[Decimal, BeforeValidator(_rate), Field(alias="Rate")]
    nominal: Annotated[int, BeforeValidator(_nominal), Field(alias="Nominal")]
    day: Annotated[date, BeforeValidator(_day), Field(alias="Date")]

    @property
    def per_unit(self) -> Decimal:
        """1 birlik valyuta uchun so'm (dwh.fx_rate.rate)."""
        return (self.rate / self.nominal).quantize(_SIX)


_RATES = TypeAdapter(list[CbuRate])


class CbuClient:
    def __init__(self, base_url: str = "https://cbu.uz", *, proxy: str = "",
                 transport: httpx.BaseTransport | None = None,
                 timeout: httpx.Timeout = TIMEOUT, max_bytes: int = MAX_BYTES) -> None:
        self.max_bytes = max_bytes
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout, verify=True, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport,
            headers={"Accept": "application/json"})

    def close(self) -> None:
        self.http.close()

    def rates(self, day: date) -> list[CbuRate]:
        path = RATES_PATH.format(day=day.isoformat())
        where = f"ЦБ {day:%d.%m.%Y}"
        chunks: list[bytes] = []
        size = 0
        try:
            with self.http.stream("GET", path) as response:
                status = response.status_code
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise CbuError(f"{where}: ответ больше {self.max_bytes} байт")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise ConnectorUnavailableError(f"{where}: тайм-аут") from exc
        except httpx.TransportError as exc:
            raise ConnectorUnavailableError(f"{where}: {type(exc).__name__}") from exc
        if status >= 500 or status == 429:
            raise ConnectorUnavailableError(f"{where}: HTTP {status}")
        if status != 200:
            raise CbuError(f"{where}: HTTP {status}")
        try:
            data = json.loads(b"".join(chunks).decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CbuError(f"{where}: ответ не JSON") from exc
        try:
            return _RATES.validate_python(data)
        except PydanticValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise CbuError(f"{where}: неожиданная структура ответа ({loc} — {first['msg']})") \
                from exc
```

- [ ] **Step 5: Implementatsiya — konnektor, reyestr, worker, CLI**

`backend/app/etl/cbu/connector.py`:
```python
"""CbuRatesConnector — SourceConnector (S2 spec 3.3): so'ralgan har kalendar kun uchun shu kuni
amalda bo'lgan kurs dwh.fx_rate ga (currency, date_id) kaliti bilan — idempotent.
Kuniga oxirgi `days` kun (o'tkazib yuborilganlar to'ldiriladi); tarix — date_from/date_to.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

from app.core.logging import get_logger
from app.dwh.dates import date_id, today_tashkent
from app.etl.cbu.client import CbuClient, CbuError
from app.etl.types import (
    ConnectorUnavailableError,
    ControlTotals,
    ExtractStats,
    HealthResult,
    StagingSink,
    Watermark,
    Window,
)

SOURCE = "cbu"
MAX_BACKFILL_DAYS = 800
log = get_logger("ugekazna.cbu")


class CbuRatesConnector:
    def __init__(self, client: CbuClient, currencies: Sequence[str], *, days: int = 7,
                 date_from: date | None = None, date_to: date | None = None,
                 today: Callable[[], date] = today_tashkent,
                 sleep: Callable[[float], None] = time.sleep, pause: float = 0.2,
                 source: str = SOURCE) -> None:
        if (date_from is None) != (date_to is None):
            raise ValueError("date_from va date_to birga beriladi")
        if date_from is not None and date_to is not None:
            if date_to < date_from:
                raise ValueError("date_to date_from dan oldin")
            if (date_to - date_from).days + 1 > MAX_BACKFILL_DAYS:
                raise ValueError(f"bir martada ko'pi bilan {MAX_BACKFILL_DAYS} kun")
        self.source = source
        self.client = client
        self.currencies = list(currencies)
        self.days = days
        self.date_from = date_from
        self.date_to = date_to
        self.today = today
        self.sleep = sleep
        self.pause = pause

    def dates(self) -> list[date]:
        if self.date_from is not None and self.date_to is not None:
            start, end = self.date_from, self.date_to
        else:
            end = self.today()
            start = end - timedelta(days=self.days - 1)
        return [start + timedelta(days=n) for n in range((end - start).days + 1)]

    def healthcheck(self) -> HealthResult:
        try:
            self.client.rates(self.today())
        except ConnectorUnavailableError as exc:
            return HealthResult(False, str(exc))
        return HealthResult(True, "cbu.uz")

    def watermark(self) -> Watermark:
        return Watermark(datetime.now(UTC))

    def control_totals(self, window: Window) -> ControlTotals | None:
        return None

    def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
        wanted = set(self.currencies)
        count = 0
        for n, day in enumerate(self.dates()):
            if n:
                self.sleep(self.pause)
            rates = self.client.rates(day)
            if not rates:
                log.warning("cbu_empty_response", day=day.isoformat())
                continue
            found: set[str] = set()
            for r in rates:
                if r.ccy not in wanted:
                    continue
                if r.day > day:
                    raise CbuError(f"ЦБ {day:%d.%m.%Y}: курс {r.ccy} датирован "
                                   f"{r.day:%d.%m.%Y} — позже запрошенной даты")
                sink.add("fx_rate", {"currency": r.ccy, "date_id": date_id(day),
                                     "rate": r.per_unit})
                found.add(r.ccy)
                count += 1
            if wanted - found:
                log.warning("cbu_missing_currencies", day=day.isoformat(),
                            currencies=sorted(wanted - found))
        return ExtractStats(count, {"fx_rate": count})
```

`backend/app/etl/connectors.py` — importlarga:
```python
from datetime import date

from app.etl.cbu.client import CbuClient
from app.etl.cbu.connector import CbuRatesConnector
```
`KNOWN_SOURCES` ni almashtiring:
```python
KNOWN_SOURCES = ("synthetic", "file", "onec", "banks", "cbu", "directbank")
```
`_banks` dan keyin qo'shing:
```python
def cbu_connector(settings: Settings, *, date_from: date | None = None,
                  date_to: date | None = None) -> CbuRatesConnector:
    if not settings.cbu_enabled:
        raise ConfigError("CBU_ENABLED=false — ЦБ kurslari yuklanmaydi")
    with get_engine("etl").connect() as conn:
        currencies = list(current_setting(conn, "fx.currencies"))
        days = int(current_setting(conn, "fx.lookback_days"))
    client = CbuClient(settings.cbu_base_url, proxy=settings.egress_proxy)
    return CbuRatesConnector(client, currencies, days=days, date_from=date_from, date_to=date_to)
```
`make_connector` ichida `if source == "banks":` dan oldin:
```python
    if source == "cbu":
        return cbu_connector(settings)
```

`backend/app/worker.py` — `build_scheduler` ichida (`etl_banks` blokidan keyin):
```python
    if settings.cbu_enabled:
        with get_engine("app").connect() as conn:
            cbu_cron = str(current_setting(conn, "etl.cbu_cron"))
        # TZ 8: ЦБ kurslari har kuni; oxirgi fx.lookback_days kun qayta so'raladi.
        scheduler.add_job(run_etl_job, CronTrigger.from_crontab(cbu_cron, timezone=TASHKENT),
                          args=("cbu", Mode.INCREMENTAL, notifier), id="etl_cbu", **opts)
```

`backend/app/cli.py` — importlarga (`date` — `datetime` importiga qo'shing: `from datetime import UTC, date, datetime, timedelta`):
```python
from app.etl.connectors import cbu_connector
from app.etl.runner import EtlBusyError, Runner
from app.etl.types import Mode
```
(2-reja `etl-run` buyrug'i uchun bu importlar allaqachon bo'lsa — takrorlamang.) funksiya (`main` dan oldin):
```python
def _cbu_backfill(date_from: date, date_to: date) -> int:
    """ЦБ kurslari tarixini to'ldirish (S2 spec 3.3): ko'pi bilan 800 kun, bitta yuklash."""
    if date_to < date_from or (date_to - date_from).days + 1 > 800:
        _out("Xato: oraliq noto'g'ri yoki 800 kundan uzun")
        return 1
    try:
        connector = cbu_connector(get_settings(), date_from=date_from, date_to=date_to)
    except ConfigError as exc:
        _out(f"Konfiguratsiya xatosi: {exc}")
        return 2
    try:
        result = Runner(connector, mode=Mode.FULL).run()
    except EtlBusyError:
        _out("Boshqa yuklash bajarilmoqda — keyinroq qayta urining")
        return 3
    _out(f"cbu-backfill: status={result.status} run={result.run_id}")
    return 0 if result.status == "success" else 1
```
`main` ichida (oxirgi `sub.add_parser(...)` blokidan keyin):
```python
    p = sub.add_parser("cbu-backfill")
    p.add_argument("--from", dest="date_from", type=date.fromisoformat, required=True)
    p.add_argument("--to", dest="date_to", type=date.fromisoformat, required=True)
```
dispatch'da (oxirgi zaxira `return …` dan oldin):
```python
    if args.command == "cbu-backfill":
        return _cbu_backfill(args.date_from, args.date_to)
```
Docstring ro'yxatiga:
```
cbu-backfill   — ЦБ kurslari tarixini to'ldirish (--from/--to, ≤ 800 kun)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_cbu.py tests/test_worker.py -v`
Expected: barcha testlar passed (tarmoqqa so'rov yo'q — faqat `MockTransport`).

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(cbu): ЦБ РУз kurslari konnektori, kunlik jadval va cbu-backfill CLI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Telegram — `TelegramClient` va `TelegramNotifier`

**Files:**
- Create: `backend/app/etl/telegram.py`
- Modify: `backend/app/etl/notify.py` (`build_notifier`)
- Test: `backend/tests/test_telegram.py`

**Interfaces:**
- Consumes: `Notification`, `Notifier`, `CompositeNotifier`, `LogNotifier`, `build_notifier`, `Settings.telegram_*`, `Settings.egress_proxy`, `TELEGRAM_TOKEN_RE`, `ConfigError`.
- Produces (`app.etl.telegram`):
  - `MAX_TEXT = 4096`, `MAX_RETRY_AFTER = 30`, `TelegramError(Exception)` (matnida token/URL yo'q).
  - `TelegramClient(token, *, api_base="https://api.telegram.org", proxy="", transport=None, sleep=time.sleep)` + `.send(chat_id, text)`, `.http`, `.close()` — noto'g'ri token → `ConfigError`; `httpx` logger darajasi WARNING.
  - `TelegramNotifier(client, chats)` — `Notifier`; bitta chat xatosi qolganlarini to'xtatmaydi.
  - `build_notifier(settings)` — `telegram_enabled` bo'lsa `TelegramNotifier` qo'shiladi (konfiguratsiya xatosi — log, ETL to'xtamaydi).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_telegram.py`:
```python
import json
import logging
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import ConfigError, get_settings
from app.etl.notify import CompositeNotifier, Notification, build_notifier
from app.etl.telegram import MAX_TEXT, TelegramClient, TelegramError, TelegramNotifier

TOKEN = "123456789:" + "A" * 35


def _client(handler: Callable[[httpx.Request], httpx.Response],
            sleeps: list[float] | None = None) -> TelegramClient:
    return TelegramClient(TOKEN, transport=httpx.MockTransport(handler),
                          sleep=(sleeps if sleeps is not None else []).append)


def test_send_posts_plain_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    _client(handler).send(42, "Привет" + "x" * 5000)
    request = seen[0]
    assert request.url.path == f"/bot{TOKEN}/sendMessage" and request.method == "POST"
    body = json.loads(request.content)
    assert body["chat_id"] == 42 and body["disable_web_page_preview"] is True
    assert len(body["text"]) == MAX_TEXT and body["text"].startswith("Привет")
    assert "parse_mode" not in body


def test_429_waits_retry_after_once() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "error_code": 429,
                                             "parameters": {"retry_after": 3}})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    _client(handler, sleeps).send(1, "t")
    assert sleeps == [3.0] and len(calls) == 2
    always = _client(lambda r: httpx.Response(429, json={"parameters": {"retry_after": 999}}),
                     sleeps)
    with pytest.raises(TelegramError, match="429"):
        always.send(1, "t")
    assert sleeps[-1] == 30.0


def test_server_error_retried_once_then_fails() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(502)

    with pytest.raises(TelegramError, match="502"):
        _client(handler).send(1, "t")
    assert len(calls) == 2
    with pytest.raises(TelegramError, match="403"):
        _client(lambda r: httpx.Response(403, json={"ok": False})).send(1, "t")


def test_token_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {request.url}", request=request)

    with pytest.raises(TelegramError) as exc:
        _client(refused).send(1, "t")
    _client(lambda r: httpx.Response(200, json={"ok": True})).send(1, "t")
    assert TOKEN not in str(exc.value) and TOKEN not in repr(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert TOKEN not in caplog.text
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_invalid_token_is_config_error() -> None:
    with pytest.raises(ConfigError) as exc:
        TelegramClient("12345:short")
    assert "12345:short" not in str(exc.value)
    assert TelegramClient(TOKEN, proxy="http://10.0.0.1:3128").http.trust_env is False


def test_notifier_sends_to_all_chats_and_survives_failure() -> None:
    chats: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chat = json.loads(request.content)["chat_id"]
        chats.append(chat)
        return httpx.Response(400 if chat == 1 else 200, json={"ok": chat != 1})

    notifier = TelegramNotifier(_client(handler), [1, 2])
    notifier.notify(Notification("etl_failed", "Загрузка «onec» завершилась ошибкой", "тело"))
    assert chats == [1, 2]


def test_build_notifier_adds_telegram_only_when_valid() -> None:
    base = get_settings()
    on = base.model_copy(update={"telegram_bot_token": SecretStr(TOKEN),
                                 "telegram_chat_ids": SecretStr("-100500, 7")})
    notifier = build_notifier(on)
    assert isinstance(notifier, CompositeNotifier)
    assert any(isinstance(n, TelegramNotifier) for n in notifier.notifiers)
    bad = base.model_copy(update={"telegram_bot_token": SecretStr(TOKEN),
                                  "telegram_chat_ids": SecretStr("@chan")})
    plain = build_notifier(bad)
    assert isinstance(plain, CompositeNotifier)
    assert not any(isinstance(n, TelegramNotifier) for n in plain.notifiers)
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_telegram.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.etl.telegram'`.

- [ ] **Step 3: Implementatsiya**

`backend/app/etl/telegram.py`:
```python
"""Telegram Bot API — faqat chiquvchi xabarlar (TZ 8 «Телеграм-бот», S2 spec 9).

Token URL yo'lida (`/bot<token>/sendMessage`) bo'ladi, shuning uchun: httpx logger'i WARNING
darajasiga tushiriladi (INFO so'rov logida URL bor), istisnolar `from None` bilan va faqat
HTTP kodi yoki xato turi bilan qayta ko'tariladi — token hech qayerga yozilmaydi.
Matn — oddiy (parse_mode yo'q: markup in'ektsiyasi yo'q), 4096 belgigacha.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence

import httpx

from app.core.config import TELEGRAM_TOKEN_RE, ConfigError
from app.core.logging import get_logger
from app.etl.notify import Notification

MAX_TEXT = 4096
MAX_RETRY_AFTER = 30
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
log = get_logger("ugekazna.telegram")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class TelegramError(Exception):
    """Xabar yuborilmadi (matnda token ham, URL ham yo'q)."""


def _retry_after(response: httpx.Response) -> float:
    try:
        value = float(response.json()["parameters"]["retry_after"])
    except (ValueError, KeyError, TypeError):
        value = 1.0
    return max(0.0, min(value, float(MAX_RETRY_AFTER)))


class TelegramClient:
    def __init__(self, token: str, *, api_base: str = "https://api.telegram.org",
                 proxy: str = "", transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not TELEGRAM_TOKEN_RE.fullmatch(token):
            raise ConfigError("telegram_bot_token formati noto'g'ri")
        self._path = f"/bot{token}/sendMessage"
        self.sleep = sleep
        self.http = httpx.Client(
            base_url=api_base.rstrip("/"), timeout=TIMEOUT, verify=True, trust_env=False,
            follow_redirects=False, proxy=proxy or None, transport=transport)

    def close(self) -> None:
        self.http.close()

    def send(self, chat_id: int, text: str) -> None:
        body = {"chat_id": chat_id, "text": text[:MAX_TEXT], "disable_web_page_preview": True}
        status = 0
        for attempt in range(2):
            try:
                response = self.http.post(self._path, json=body)
            except httpx.HTTPError as exc:
                raise TelegramError(f"Telegram: {type(exc).__name__}") from None
            status = response.status_code
            if status == 200:
                return
            if attempt == 0 and status == 429:
                self.sleep(_retry_after(response))
                continue
            if attempt == 0 and status >= 500:
                self.sleep(2.0)
                continue
            break
        raise TelegramError(f"Telegram: HTTP {status}")


class TelegramNotifier:
    """2-reja Notifier: ETL xatolari va ogohlantirishlarini chat'larga yuboradi."""

    def __init__(self, client: TelegramClient, chats: Sequence[int]) -> None:
        self.client = client
        self.chats = list(chats)

    def notify(self, notification: Notification) -> None:
        text = f"UGEKAZNA: {notification.subject}\n\n{notification.body}"
        for chat in self.chats:
            try:
                self.client.send(chat, text)
            except TelegramError as exc:
                log.error("telegram_notify_failed", kind=notification.kind, error=str(exc))
```

`backend/app/etl/notify.py` — `build_notifier` ichida `return CompositeNotifier(notifiers)` qatoridan OLDIN qo'shing:
```python
    if settings.telegram_enabled:
        # Aylanma importdan qochish: telegram moduli Notification'ni shu fayldan oladi.
        from app.etl.telegram import TelegramClient, TelegramNotifier

        try:
            client = TelegramClient(settings.telegram_bot_token.get_secret_value(),
                                    api_base=settings.telegram_api_base,
                                    proxy=settings.egress_proxy)
            notifiers.append(TelegramNotifier(client, settings.telegram_chats))
        except ConfigError as exc:
            log.error("telegram_config_invalid", error=str(exc))
```
va importni `from app.core.config import Settings` → `from app.core.config import ConfigError, Settings` ga almashtiring.

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_telegram.py tests/test_notify.py -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(telegram): Bot API mijozi (token logsiz) va TelegramNotifier

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Kundalik Telegram hisoboti (08:30) — agregatlar, kritik qoidalar, audit

**Files:**
- Create: `backend/app/reports/__init__.py`, `backend/app/reports/daily.py`
- Modify: `backend/app/worker.py` (job), `backend/app/cli.py` (`telegram-test`), `backend/tests/test_worker.py`
- Test: `backend/tests/test_daily_summary.py`

**Interfaces:**
- Consumes: `SectionQuery`, `queries.cash.cash_totals`, `queries.calendar.calendar` (`CalendarBlock.total/balance/coverage`), `queries.loans.load_report`, `alerts.engine.evaluate`, `freshness(conn, now)` (`last_success_at`, `stale`), `pub.fx_rate_latest`, `fmt_num`, `fmt_pct`, `Section`, `section_perm`, `TelegramClient`, `TelegramError`, `record`, `AuditAction.TELEGRAM_SUMMARY_SENT`, `AuditResult`, `new_session`, `apply_rls`, `TASHKENT`, `published_synthetic`.
- Produces (`app.reports.daily`):
  - `ALL_SECTIONS: frozenset[str]`, `fmt_bln(mln) -> str` («… млрд сум» / «… трлн сум» / «нет данных»), `Summary(text, critical, warning)`, `build_summary(db, *, today, now, base_url) -> Summary`, `send_daily_summary(settings, *, client=None, now=None) -> int` (yuborilgan chat'lar soni; audit `notify.telegram.summary`).
  - Worker job `telegram_summary` (`telegram.summary_cron`, faqat `telegram_enabled`); CLI `python -m app.cli telegram-test [--summary]` (0 — hammasi yuborildi, 1 — xato, 2 — sozlanmagan).

- [ ] **Step 1: Testlarni yozish**

`backend/tests/test_daily_summary.py`:
```python
import re
from datetime import UTC, date, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app import cli, worker
from app.core.config import Settings, get_settings
from app.core.db import apply_rls, get_engine, new_session
from app.etl.telegram import TelegramError
from app.reports.daily import build_summary, fmt_bln, send_daily_summary
from tests.etl_helpers import RecordingNotifier

TOKEN = "123456789:" + "A" * 35
NOW = datetime(2026, 9, 24, 3, 30, tzinfo=UTC)  # 08:30 Toshkent


class FakeClient:
    def __init__(self, fail_for: frozenset[int] = frozenset()) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail_for = fail_for

    def send(self, chat_id: int, text: str) -> None:
        if chat_id in self.fail_for:
            raise TelegramError("Telegram: HTTP 403")
        self.sent.append((chat_id, text))


def _settings(chats: str = "1, 2") -> Settings:
    return get_settings().model_copy(update={"telegram_bot_token": SecretStr(TOKEN),
                                             "telegram_chat_ids": SecretStr(chats),
                                             "base_url": "https://ugekazna.test"})


def test_fmt_bln() -> None:
    assert fmt_bln(1234.5) == "1,2 млрд сум"
    assert fmt_bln(12) == "0,01 млрд сум"
    assert fmt_bln(2_500_000) == "2,50 трлн сум"
    assert fmt_bln(None) == "нет данных"


def test_summary_text_has_aggregates_and_no_personal_data(published_synthetic: int) -> None:
    with new_session() as s:
        apply_rls(s, None)
        summary = build_summary(s, today=date(2026, 9, 24), now=NOW,
                                base_url="https://ugekazna.test")
    body = summary.text
    assert body.startswith("UGEKAZNA — сводка на 24.09.2026")
    for needle in ("Денежные средства", "Остаток на счетах:", "С начала месяца:",
                   "Платежи на 14 дней:", "Кредиты", "Портфель:", "Требует внимания: критично",
                   "https://ugekazna.test/#obzor/vnimanie"):
        assert needle in body, needle
    assert "сум" in body and "млн" not in body
    assert not re.search(r"\d{10,}", body)  # hisob raqamlari / INN yo'q
    assert "ООО" not in body and "«" not in body  # kontragent nomlari yo'q
    tail = body.split("Требует внимания:", 1)[1]
    assert summary.critical == sum(1 for line in tail.splitlines() if line.startswith("• "))


def test_send_daily_summary_audits(published_synthetic: int) -> None:
    fake = FakeClient()
    assert send_daily_summary(_settings(), client=fake, now=NOW) == 2
    assert [chat for chat, _ in fake.sent] == [1, 2]
    with get_engine("migrator").connect() as conn:
        row = conn.execute(text(
            "SELECT result, details FROM core.audit_log WHERE action = 'notify.telegram.summary' "
            "ORDER BY id DESC LIMIT 1")).one()
    assert row.result == "ok" and row.details["chats"] == 2 and row.details["sent"] == 2
    partial = FakeClient(frozenset({2}))
    assert send_daily_summary(_settings(), client=partial, now=NOW) == 1
    with get_engine("migrator").connect() as conn:
        result = conn.execute(text(
            "SELECT result FROM core.audit_log WHERE action = 'notify.telegram.summary' "
            "ORDER BY id DESC LIMIT 1")).scalar_one()
    assert result == "fail"


def test_worker_job_and_cli_without_config(capsys: pytest.CaptureFixture[str]) -> None:
    jobs = {j.id for j in worker.build_scheduler(_settings(), RecordingNotifier()).get_jobs()}
    assert "telegram_summary" in jobs
    plain = {j.id for j in worker.build_scheduler(get_settings(), RecordingNotifier()).get_jobs()}
    assert "telegram_summary" not in plain
    assert cli.main(["telegram-test"]) == 2  # test muhitida token yo'q
    assert "Telegram" in capsys.readouterr().out
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_daily_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports'`.

- [ ] **Step 3: Implementatsiya — hisobot**

`backend/app/reports/__init__.py`:
```python
"""Tashqi kanallarga yuboriladigan hisobotlar (S2: kundalik Telegram hisoboti)."""
```

`backend/app/reports/daily.py`:
```python
"""Kundalik Telegram hisoboti (TZ 7 «Второй этап», TZ 8 «Телеграм-бот» — 08:30; S2 spec 9).

Faqat agregatlar (pub view'lar) va KRITIK qoidalar SARLAVHALARI: qoida xabarlarida kontragent
nomi bo'lishi mumkin — ular yuborilmaydi. Shaxsiy ma'lumot, hisob raqami, INN yo'q. Summalar
млрд/трлн сум. Har yuborish auditga yoziladi (tashqi servisga ma'lumot uzatish).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.alerts.engine import evaluate
from app.audit.service import AuditAction, AuditEvent, AuditResult, record
from app.auth.permissions import Section, section_perm
from app.core.config import Settings
from app.core.db import apply_rls, new_session
from app.core.logging import get_logger
from app.dwh.dates import TASHKENT
from app.dwh.freshness import freshness
from app.etl.telegram import TelegramClient, TelegramError
from app.sections.deps import SectionQuery
from app.sections.fmt import fmt_num, fmt_pct
from app.sections.queries import calendar, cash, loans

ALL_SECTIONS = frozenset(section_perm(s) for s in Section)
log = get_logger("ugekazna.daily")


class Sender(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class Summary:
    text: str
    critical: int
    warning: int


def fmt_bln(mln: float | None) -> str:
    if mln is None:
        return "нет данных"
    if abs(mln) >= 1_000_000:
        return f"{fmt_num(mln / 1_000_000, 2)} трлн сум"
    return f"{fmt_num(mln / 1_000, 1 if abs(mln) >= 1_000 else 2)} млрд сум"


def build_summary(db: Session, *, today: date, now: datetime, base_url: str) -> Summary:
    q = SectionQuery(None, f"m{today.month:02d}", today, None)
    period, sel = q.period(), q.sel()
    totals = cash.cash_totals(db, sel, period)
    block = calendar.calendar(db, sel)
    report = loans.load_report(db, sel, period)
    hits, _ = evaluate(db, q, ALL_SECTIONS)
    state = freshness(db.connection(), now)
    rates = {str(r.currency).strip(): float(r.rate) for r in db.execute(text(
        "SELECT currency, rate FROM pub.fx_rate_latest WHERE currency IN ('USD', 'EUR')")).all()}

    last = "никогда" if state.last_success_at is None else \
        state.last_success_at.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M")
    lines = [f"UGEKAZNA — сводка на {today:%d.%m.%Y}",
             f"Данные загружены: {last}" + (" — ДАННЫЕ УСТАРЕЛИ" if state.stale else ""),
             "", "Денежные средства",
             f"• Остаток на счетах: {fmt_bln(totals.closing)}",
             f"• С начала месяца: поступления {fmt_bln(totals.inflow)}, "
             f"расходование {fmt_bln(totals.outflow)}"]
    if block.total > 0:
        cover = "" if block.coverage is None else \
            f", остаток покрывает в {fmt_num(block.coverage, 1)} раза"
        lines.append(f"• Платежи на 14 дней: {fmt_bln(block.total)}{cover}")
    else:
        lines.append("• Платежи на 14 дней: нет данных")
    lines += ["", "Кредиты"]
    if report.has_loans:
        share = "нет данных" if report.fx_share is None else fmt_pct(report.fx_share)
        lines.append(f"• Портфель: {fmt_bln(report.portfolio)}, доля валютных {share}")
        nxt = report.next_payment
        if nxt is not None:
            lines.append(f"• Ближайший платёж: {nxt.day:%d.%m.%Y} — {fmt_bln(nxt.total)}")
    else:
        lines.append("• Кредитов нет")
    if rates:
        lines += ["", "Курсы ЦБ: " + ", ".join(
            f"{c} {fmt_num(rates[c], 2)}" for c in ("USD", "EUR") if c in rates)]
    critical = [h for h in hits if h.level == "critical"]
    warning = len(hits) - len(critical)
    lines += ["", f"Требует внимания: критично {len(critical)}, внимание {warning}"]
    lines += [f"• {h.title}" for h in critical]
    lines.append(f"Подробнее: {base_url.rstrip('/')}/#obzor/vnimanie")
    return Summary("\n".join(lines), len(critical), warning)


def send_daily_summary(settings: Settings, *, client: Sender | None = None,
                       now: datetime | None = None) -> int:
    chats = settings.telegram_chats
    sender: Sender = client or TelegramClient(settings.telegram_bot_token.get_secret_value(),
                                              api_base=settings.telegram_api_base,
                                              proxy=settings.egress_proxy)
    moment = now or datetime.now(UTC)
    with new_session() as s:
        apply_rls(s, None)
        summary = build_summary(s, today=moment.astimezone(TASHKENT).date(), now=moment,
                                base_url=settings.base_url)
    sent = 0
    for chat in chats:
        try:
            sender.send(chat, summary.text)
            sent += 1
        except TelegramError as exc:
            log.error("telegram_summary_failed", error=str(exc))
    result: AuditResult = "ok" if sent == len(chats) else "fail"
    record(AuditEvent(action=AuditAction.TELEGRAM_SUMMARY_SENT, result=result,
                      object_type="telegram",
                      details={"chats": len(chats), "sent": sent, "critical": summary.critical,
                               "chars": len(summary.text)}))
    return sent
```

- [ ] **Step 4: Worker jobi va CLI**

`backend/app/worker.py` — importlarga:
```python
from app.reports.daily import send_daily_summary
```
`build_scheduler` ichida (`etl_cbu` blokidan keyin):
```python
    if settings.telegram_enabled:
        with get_engine("app").connect() as conn:
            summary_cron = str(current_setting(conn, "telegram.summary_cron"))
        # TZ 8: kundalik hisobot 08:30 (Toshkent), bitta nusxa (advisory lock).
        scheduler.add_job(_guarded("telegram_summary", lambda: send_daily_summary(settings)),
                          CronTrigger.from_crontab(summary_cron, timezone=TASHKENT),
                          id="telegram_summary", **opts)
```

`backend/app/cli.py` — importlarga:
```python
from app.etl.telegram import TelegramClient, TelegramError
from app.reports.daily import send_daily_summary
```
funksiya (`main` dan oldin):
```python
def _telegram_test(summary: bool) -> int:
    """Telegram ulanishini tekshirish: sinov xabari yoki (--summary) kundalik hisobot hozir."""
    settings = get_settings()
    if not settings.telegram_enabled:
        _out("Telegram sozlanmagan: telegram_bot_token / telegram_chat_ids sirlari bo'sh")
        return 2
    try:
        chats = settings.telegram_chats
        if summary:
            sent = send_daily_summary(settings)
        else:
            client = TelegramClient(settings.telegram_bot_token.get_secret_value(),
                                    api_base=settings.telegram_api_base,
                                    proxy=settings.egress_proxy)
            sent = 0
            for chat in chats:
                try:
                    client.send(chat, "UGEKAZNA: проверка связи с Telegram")
                    sent += 1
                except TelegramError as exc:
                    _out(f"Xato: {exc}")
    except ConfigError as exc:
        _out(f"Konfiguratsiya xatosi: {exc}")
        return 2
    _out(f"Telegram: yuborildi {sent} / {len(chats)}")
    return 0 if sent == len(chats) else 1
```
`main` ichida:
```python
    p = sub.add_parser("telegram-test")
    p.add_argument("--summary", action="store_true")
```
dispatch'da:
```python
    if args.command == "telegram-test":
        return _telegram_test(args.summary)
```
Docstring ro'yxatiga:
```
telegram-test  — Telegram sinov xabari (--summary — kundalik hisobotni hozir yuborish)
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_daily_summary.py tests/test_worker.py tests/test_telegram.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(telegram): kundalik hisobot 08:30 (agregatlar, kritik qoidalar), audit, telegram-test CLI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Ekspluatatsiya — prod compose (bank hajmlari, Telegram sirlari, egress), hujjatlar

**Files:**
- Create: `docs/integration/banks-format.md`, `docs/integration/banks-connector.md`, `docs/integration/cbu-telegram.md`, `docs/integration/kredity-fayl.md`, `backend/tests/ops/test_s2_ops.py`
- Modify: `deploy/compose.prod.yml`, `deploy/prod.env.example`, `deploy/secrets.example/README.md`, `scripts/prod_config.sh`, `docs/ops/host-hardening.md`
- Test: `backend/tests/ops/test_s2_ops.py`

**Interfaces:**
- Consumes: 4-reja `compose.prod.yml` (`worker` — `backend` + `egress`, `x-backend-env`, `etl_inbox`), S1 worker sirlari ro'yxati, `tests.ops.repo.repo_path`, `scripts/prod_config.sh`, 8–12-vazifalar sozlamalari (`BANK_INBOX_DIR` = `/data/import/banks`, `BANK_ARCHIVE_DIR` = `/data/archive/banks`, `CBU_ENABLED`, `EGRESS_PROXY`, sirlar `telegram_bot_token`, `telegram_chat_ids`).
- Produces: hajmlar `bank_inbox` (worker'da `:ro`), `bank_archive` (rw) — host kataloglariga bind; sirlar `telegram_bot_token`, `telegram_chat_ids` — faqat `worker`; `worker` muhiti `CBU_ENABLED`, `EGRESS_PROXY`; 4 ta hujjat; host egress qoidalari.

- [ ] **Step 1: Yiqiladigan testni yozish**

`backend/tests/ops/test_s2_ops.py`:
```python
from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

TELEGRAM = {"telegram_bot_token", "telegram_chat_ids"}
DOCS = {
    "docs/integration/banks-format.md": ("row_type", "OB", "CB", "accepted", "executed",
                                         "rejected", "UTF-8", "ГГГГ-ММ-ДД"),
    "docs/integration/banks-connector.md": ("bank-accounts", "banks.statement_branches",
                                            "bank-files", "/srv/ugekazna/banks", "DirectBank"),
    "docs/integration/cbu-telegram.md": ("CBU_ENABLED", "cbu-backfill", "EGRESS_PROXY",
                                         "telegram-test", "telegram_chat_ids"),
    "docs/integration/kredity-fayl.md": ("dim_loan.csv", "fact_loan_schedule.csv", "etl-run",
                                         "balance"),
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(repo_path("deploy/compose.prod.yml").read_text(encoding="utf-8"))


def test_bank_volumes(compose: dict[str, Any]) -> None:
    worker = compose["services"]["worker"]
    assert "bank_inbox:/data/import/banks:ro" in worker["volumes"]
    assert "bank_archive:/data/archive/banks" in worker["volumes"]
    for name, default in (("bank_inbox", "/srv/ugekazna/banks/inbox"),
                          ("bank_archive", "/srv/ugekazna/banks/archive")):
        opts = compose["volumes"][name]["driver_opts"]
        assert (opts["type"], opts["o"]) == ("none", "bind")
        assert default in opts["device"]
    for service, svc in compose["services"].items():
        if service != "worker":
            assert not any("bank_" in v for v in svc.get("volumes", [])), service


def test_telegram_secrets_only_in_worker(compose: dict[str, Any]) -> None:
    assert TELEGRAM <= set(compose["secrets"])
    for service, svc in compose["services"].items():
        granted = TELEGRAM & set(svc.get("secrets", []))
        assert granted == (TELEGRAM if service == "worker" else set()), service
    env = compose["services"]["worker"]["environment"]
    assert env["CBU_ENABLED"] == "${CBU_ENABLED:-false}"
    assert env["EGRESS_PROXY"] == "${EGRESS_PROXY:-}"
    assert not any("TELEGRAM" in key for key in env)
    assert "egress" in compose["services"]["worker"]["networks"]


def test_docs_mention_required_facts() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "api.telegram.org" in hardening and "cbu.uz" in hardening
```

- [ ] **Step 2: Testni yiqilishini tekshirish**

Run: `$TEST pytest tests/ops/test_s2_ops.py -v`
Expected: FAIL — `KeyError: 'bank_inbox'` / `test_telegram_secrets_only_in_worker`.

- [ ] **Step 3: Compose, env namunasi, sirlar**

`deploy/compose.prod.yml` — top-level `secrets:` ga qo'shing:
```yaml
  telegram_bot_token: {file: "${UGK_SECRETS_DIR:-./secrets}/telegram_bot_token"}
  telegram_chat_ids: {file: "${UGK_SECRETS_DIR:-./secrets}/telegram_chat_ids"}
```
`worker.environment` ga qo'shing:
```yaml
      CBU_ENABLED: ${CBU_ENABLED:-false}
      EGRESS_PROXY: ${EGRESS_PROXY:-}
```
`worker.secrets` ro'yxatini almashtiring (S1 ro'yxati + Telegram):
```yaml
    secrets: [db_app_password, db_etl_password, redis_password, master_kek, blind_index_key,
              session_pepper, smtp_password, tls_cert, onec_username, onec_password,
              onec_ca_bundle, telegram_bot_token, telegram_chat_ids]
```
`worker.volumes` ni almashtiring:
```yaml
    volumes:
      - etl_inbox:/data/inbox:ro
      # Bank ko'chirmalari: inbox — faqat o'qish (bank/SFTP tomoni yozadi), arxiv — worker yozadi.
      - bank_inbox:/data/import/banks:ro
      - bank_archive:/data/archive/banks
```
top-level `volumes:` ga qo'shing:
```yaml
  bank_inbox:
    driver: local
    driver_opts: {type: none, o: bind, device: "${UGK_BANK_INBOX:-/srv/ugekazna/banks/inbox}"}
  bank_archive:
    driver: local
    driver_opts: {type: none, o: bind, device: "${UGK_BANK_ARCHIVE:-/srv/ugekazna/banks/archive}"}
```

`deploy/prod.env.example` — oxiriga:
```bash
# ЦБ РУз kurslari (cbu.uz): true — worker har kuni 08:00 da oxirgi 7 kunni yuklaydi (egress kerak).
CBU_ENABLED=false
# Tashqi so'rovlar (cbu.uz, api.telegram.org) uchun korporativ HTTP proksi, masalan
# http://10.20.0.30:3128 (login/parolsiz, IP bo'yicha ruxsat). Bo'sh — to'g'ridan-to'g'ri.
EGRESS_PROXY=
# Bank ko'chirmalari host kataloglari (worker ichida /data/import/banks va /data/archive/banks).
UGK_BANK_INBOX=/srv/ugekazna/banks/inbox
UGK_BANK_ARCHIVE=/srv/ugekazna/banks/archive
```

`deploy/secrets.example/README.md` — jadval oxiriga:
```markdown
| telegram_bot_token | Telegram bot tokeni (@BotFather); bo'sh fayl — Telegram o'chiq. Faqat worker |
| telegram_chat_ids | chat id'lar vergul bilan (masalan `-1001234567890`); bo'sh — o'chiq. Faqat worker |
```

`scripts/prod_config.sh` — `for name in …` ro'yxati oxiriga (`onec_ca_bundle.pem` dan keyin) qo'shing:
```bash
            telegram_bot_token telegram_chat_ids \
```
(ya'ni `… tls_cert.pem tls_key.pem onec_username onec_password onec_ca_bundle.pem \` / `telegram_bot_token telegram_chat_ids; do`.)

- [ ] **Step 4: Host egress qoidalari**

`docs/ops/host-hardening.md` — «3. Межсетевой экран» bo'limida «После подключения коннектора 1С добавляется разрешение на его адрес и порт.» jumlasidan keyin qo'shing:
````markdown
**Выход в интернет для курсов ЦБ и Telegram (раздел S2).** Наружу обращается только `worker`
(сеть `egress`): `cbu.uz:443` (курсы валют) и `api.telegram.org:443` (дневная сводка и оповещения).
IP-адреса этих сервисов меняются, поэтому рекомендуемый путь — корпоративный HTTP-прокси с
разрешёнными доменами: в `prod.env` задаётся `EGRESS_PROXY=http://10.20.0.30:3128`, а в
`DOCKER-USER` разрешается только прокси (строка до `-o ens18 -j DROP`):
```
-A DOCKER-USER -o ens18 -d 10.20.0.30 -p tcp --dport 3128 -j RETURN
```
Без прокси разрешаются адреса `cbu.uz` и `api.telegram.org` на порт 443 (списки IP нужно
сопровождать). Если оба сервиса не используются (`CBU_ENABLED=false`, секреты Telegram пустые),
правило не добавляется.
````

- [ ] **Step 5: Bank formati hujjati (banklar va IT uchun)**

`docs/integration/banks-format.md`:
````markdown
# Формат обмена выписками с банками (канонический CSV) — UGEKAZNA

**Кому:** банкам (Узпромстройбанк, Национальный банк, Асакабанк, Ипотека-банк, Халк банк) и службе ИТ
АО «Узбекгидроэнерго». **Основание:** ТЗ, раздел 8 «Интеграции» — «Общие правила обмена».

## Общие правила
- Кодировка UTF-8 (BOM допускается), разделитель полей — `;`, первая строка — заголовок
  (порядок столбцов любой, названия — как ниже, регистр не важен).
- Даты — ГГГГ-ММ-ДД. Суммы — число с точкой, не более 2 знаков после точки, **без разделителей
  разрядов** (`1250000.50`, не `1 250 000,50`). Суммы — в валюте счёта.
- Счёт — 20 цифр (пробелы и дефисы допускаются и игнорируются).
- Файл кладётся в каталог своего банка: `sqb/`, `nbu/`, `asaka/`, `ipoteka/`, `xalq/`.
  Запись — во временный файл `*.tmp` и затем переименование в `*.csv` (файл младше 60 секунд
  не читается). Размер файла — не более 50 МБ.
- Повторная передача того же файла или той же проводки дублей не создаёт: ключ — счёт и
  идентификатор документа банка (`doc_id`, до 64 символов `A-Z a-z 0-9 . _ / -`).

## 1. Выписка
Заголовок: `row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code`

| row_type | Значение | Обязательные поля |
|---|---|---|
| `OB` | входящий остаток счёта на дату | account, date, amount (может быть отрицательным) |
| `L` | проводка | account, date, doc_id, direction (`in` — зачисление, `out` — списание), amount > 0 |
| `CB` | исходящий остаток счёта на дату | account, date, amount |

`counterparty_inn` — ИНН (9 цифр) или ПИНФЛ (14 цифр); для физических лиц данные контрагента в
системе не сохраняются. `item_code` — код статьи по ПКМ № 54, если известен (иначе статья «Прочие»).
Если по счёту за день есть и `OB`, и `CB`, проверяется: `OB + сумма(in) − сумма(out) = CB`
(допуск 0,01); при расхождении выписка за этот день не загружается.

Пример:
```
row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code
OB;20210000900100000001;2026-09-22;;;1000000000.00;;;
L;20210000900100000001;2026-09-22;D-1;in;250000000.00;301234567;ООО «Покупатель»;PKM54-I06
L;20210000900100000001;2026-09-22;D-2;out;50000000.50;;;
CB;20210000900100000001;2026-09-22;;;1199999999.50;;;
```

## 2. Статусы платёжных поручений
Заголовок: `doc_id;account;date;status;status_date;amount;counterparty_inn;counterparty_name;item_code`

`status`: `accepted` — принято банком («отправлено в банк»), `executed` — исполнено,
`rejected` — отклонено. `date` — дата документа, `status_date` — дата статуса (необязательно).

Пример:
```
doc_id;account;date;status;status_date;amount;counterparty_inn;counterparty_name;item_code
P-1;20210000900100000001;2026-09-22;executed;2026-09-22;50000000.50;;;PKM54-O09
```

## Ошибки
Строка с ошибкой не загружается, остальные строки файла загружаются; ошибки видны администратору
(«Состояние обменов», `python -m app.cli bank-files`) и приходят оповещением. Файл в другой
кодировке или с другим заголовком отклоняется целиком — исправленный файл кладётся под новым именем.
Если выгрузка клиент-банка в этом формате невозможна (например, только 1CClientBankExchange),
сообщите формат — для него добавляется адаптер без изменения остального обмена.
````

- [ ] **Step 6: Administrator yo'riqnomalari**

`docs/integration/banks-connector.md`:
````markdown
# Банковские выписки — инструкция администратора

## Как это работает
Worker 4 раза в день (`etl.banks_cron`, по умолчанию 09:30, 12:30, 15:30, 18:30) читает новые файлы
`/data/import/banks/<банк>/*.csv` (формат — `banks-format.md`), загружает остатки (`fact_balance`),
проводки (`fact_cashflow`) и статусы платёжных поручений (`fact_payment_order`) и публикует витрину.
Каждый файл копируется в архив и регистрируется в журнале по SHA-256 — повторно не читается.
Каталог выписок подключён к worker **только на чтение**; удаляет обработанные файлы хост.

## Настройка
1. Каталоги на хосте (владелец данных — uid 10001, пользователь SFTP банка пишет в inbox):
   ```bash
   install -d -o sftp-banks -g 10001 -m 2750 /srv/ugekazna/banks/inbox/{sqb,nbu,asaka,ipoteka,xalq}
   install -d -o 10001 -g 10001 -m 0750 /srv/ugekazna/banks/archive
   ```
   Пути задаются в `prod.env`: `UGK_BANK_INBOX`, `UGK_BANK_ARCHIVE`. Диск — под LUKS (в архиве
   номера счетов).
2. Сопоставление счетов и филиалов — файл `accounts.csv` (UTF-8, `;`):
   ```
   account;bank_code;branch_code;currency;gl_account
   20210000900100000001;sqb;UGE-02;UZS;5110
   20208840900100000002;nbu;UGE-01;USD;5210
   ```
   ```bash
   docker compose -f deploy/compose.prod.yml --env-file deploy/prod.env --env-file deploy/release.env \
     run --rm -v "$PWD/accounts.csv:/tmp/accounts.csv:ro" worker \
     python -m app.cli bank-accounts --file /tmp/accounts.csv
   ```
   В настройку `banks.accounts` записываются только код `BA-…` (HMAC) и последние 4 цифры;
   сам номер счёта хранится только зашифрованным в витрине. После загрузки удалите `accounts.csv`.
   Без `--file` команда показывает текущее сопоставление.
3. Перезапустить `worker` — появится задание `etl_banks` (только если каталог inbox существует).
4. Очистка inbox на хосте (обработанные файлы уже в архиве):
   ```
   # /etc/cron.d/ugekazna-banks
   15 3 * * * root find /srv/ugekazna/banks/inbox -type f -name '*.csv' -mtime +7 -delete
   ```
   Перед удалением проверьте журнал: `… run --rm worker python -m app.cli bank-files --limit 100`.

## Выписки и данные 1С
Расходование из 1С (`/payments`) и проводки банка попадают в одну таблицу. Чтобы не считать
дважды, для филиала выбирается один источник: настройка `banks.statement_branches` (список кодов
филиалов) — для этих филиалов движение берётся **только** из выписок, для остальных — из 1С.
Остатки из выписок используются для всех филиалов; для филиалов без выписок «Разница» показывает
расхождение 1С и банка (проверка качества 2 для них не применяется). Включайте филиал, когда в
систему поступают выписки по **всем** его счетам. Страницы настроек в интерфейсе пока нет —
значение меняется через API администратора (право `admin:settings`, изменение версионируется и
пишется в аудит):
```
PUT /api/v1/admin/settings/banks.statement_branches   {"value": ["UGE-02", "UGE-05"]}
```
Изменение действует со следующей загрузки (пересборки витрины).

## Ошибки
| Код в «Состояние обменов» | Причина | Действие |
|---|---|---|
| `bad_row` | строка не по формату (дата, сумма, лишние поля) | исправить выгрузку банка, передать строку заново |
| `unknown_account` | счёт `…1234` не сопоставлен | добавить его в `accounts.csv`, выполнить `bank-accounts` |
| `wrong_bank` | файл счёта лежит в каталоге другого банка | переложить файл |
| `statement_mismatch` | входящий остаток + обороты ≠ исходящий | запросить у банка полную выписку за день |
| `fx_rate_missing` | нет курса ЦБ на дату валютной операции | проверить загрузку курсов (`cbu-telegram.md`) |
| `duplicate_doc` | повтор идентификатора документа в файле | исправить выгрузку |
| `bad_encoding`, `bad_header`, `too_large` | файл отклонён целиком | исправить и положить под новым именем |

## DirectBank (1С)
Подключение через DirectBank ожидает ответа заказчика (конфигурация 1С, состав данных, учётная
запись). До этого `etl-run --source directbank` завершается ошибкой «DirectBank (1С) не настроен»,
выписки загружаются файлами. Интерфейс обмена уже заложен: данные DirectBank будут проходить те же
проверки и попадать в те же таблицы.
````

`docs/integration/cbu-telegram.md`:
````markdown
# Курсы ЦБ РУз и Telegram-бот — инструкция администратора

## Курсы ЦБ (cbu.uz)
- Источник: `https://cbu.uz/ru/arkhiv-kursov-valyut/json/all/<ГГГГ-ММ-ДД>/` — курс, действующий в
  этот день (в выходные — установленный ранее). Хранится по каждому календарному дню (`dwh.fx_rate`).
- Включение: `CBU_ENABLED=true` в `prod.env`, при необходимости `EGRESS_PROXY` (см.
  `docs/ops/host-hardening.md`). Задание `etl_cbu` — ежедневно в 08:00 (`etl.cbu_cron`), каждый раз
  запрашиваются последние `fx.lookback_days` (7) дней, пропуски заполняются сами.
- Валюты: настройка `fx.currencies` (по умолчанию USD, EUR, CNY, RUB, GBP, JPY, CHF, KZT, KRW).
- История (один раз, до 800 дней за запуск):
  ```bash
  … run --rm worker python -m app.cli cbu-backfill --from 2024-01-01 --to 2026-03-10
  … run --rm worker python -m app.cli cbu-backfill --from 2026-03-11 --to 2026-09-25
  ```
- Курс нужен: кредитному портфелю (сумовой эквивалент на отчётную дату) и валютным счетам в
  выписках. Если курса нет, кредит помечается «нет курса ЦБ», валютная выписка не загружается.

## Telegram-бот (исходящие сообщения)
1. Создать бота у @BotFather, добавить его в рабочую группу, узнать id чата (для групп — отрицательное).
2. Секреты: `secrets/telegram_bot_token` — токен, `secrets/telegram_chat_ids` — id через запятую.
   Пустые файлы — Telegram выключен. Токен не попадает ни в журналы, ни в сообщения об ошибках.
3. Перезапустить `worker`, проверить: `… run --rm worker python -m app.cli telegram-test`
   (0 — отправлено во все чаты, 1 — ошибка отправки, 2 — не настроено);
   `telegram-test --summary` — отправить дневную сводку сейчас.
4. Что приходит:
   - ежедневно в 08:30 (`telegram.summary_cron`) — сводка: остаток, поступления и расходование с
     начала месяца, платежи на 14 дней и покрытие, кредитный портфель и ближайший платёж, курсы
     USD/EUR, число сработавших правил «Требует внимания» и названия критичных. Суммы — в млрд/трлн
     сум. Персональных данных, номеров счетов и наименований контрагентов нет. Каждая отправка
     записывается в журнал аудита (`notify.telegram.summary`).
   - сразу — ошибки загрузок, непройденные проверки качества, расхождение контрольных сумм,
     устаревание данных более 6 часов, отклонённые строки банковских выписок.
5. Передача сводки во внешний сервис согласуется со службой информационной безопасности
   (открытый вопрос спецификации S2).
````

`docs/integration/kredity-fayl.md`:
````markdown
# Кредиты: загрузка реестра и графиков платежей из файла

1С пока не отдаёт кредитный портфель, поэтому реестр кредитов и графики платежей загружаются
файлами через файловый коннектор (`/data/inbox`, ТЗ 8 «Общие правила обмена»: UTF-8, `;`,
даты ГГГГ-ММ-ДД, числа с точкой без разделителей разрядов).

## dim_loan.csv — реестр
```
code;creditor;project;currency;rate;grace_until;maturity;amount_uzs;branch_code
ADB-2019-01;Азиатский банк развития;Модернизация Чарвакской ГЭС;USD;0.039;2027-01-01;2040-12-31;1850000;UGE-02
```
`rate` — годовая ставка долей (3,9 % = `0.039`); изменение ставки сохраняется с историей (новое
значение действует с даты загрузки). `amount_uzs` — сумма кредита в сумовом эквиваленте, млн сум.

## fact_loan_schedule.csv — график платежей
```
doc_type;src_id;date;branch_code;loan_code;principal;interest;balance
loan_schedule;ADB-2019-01:2026-03-15;2026-03-15;UGE-02;ADB-2019-01;0;1.8;148
```
Суммы — **в валюте кредита, млн единиц**; `balance` — остаток основного долга после платежа.
Портфель и платежи пересчитываются в сумы по курсу ЦБ на отчётную дату.

## Загрузка
Файлы кладутся в каталог `/data/inbox` (том `etl_inbox`) целиком — **полный график, включая
будущие годы**: при каждой загрузке график заменяется полностью.
```bash
… run --rm worker python -m app.cli etl-run --source file --mode full
```
Результат — в «Состояние обменов». Когда 1С начнёт отдавать кредиты (регистр кредитов и графики),
файловая загрузка заменяется коннектором 1С без изменения интерфейса.
````

- [ ] **Step 7: Testlar va konfiguratsiya tekshiruvi**

Run: `$TEST pytest tests/ops -v` va `./scripts/prod_config.sh`
Expected: testlar passed (4-reja `test_no_source_bind_mounts` ham — yangi hajmlar compose `volumes` ro'yxatida); `prod-config: OK`.

- [ ] **Step 8: Commit**

```bash
git add deploy scripts docs/integration docs/ops backend/tests/ops
git commit -m "ops(s2): bank hajmlari, Telegram sirlari, egress; banklar, ЦБ, Telegram, kreditlar hujjatlari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Frontend — «Кредиты» tiplari, fixture'lar, matnlar va kartalar

**Files:**
- Create: `frontend/src/test/s2Fixtures.ts`, `frontend/src/sections/kredity/parts/currency.ts`, `frontend/src/sections/kredity/parts/LoanKpis.tsx`, `frontend/src/sections/kredity/parts/ScheduleCard.tsx`, `frontend/src/sections/kredity/parts/UpcomingCard.tsx`, `frontend/src/sections/kredity/parts/LoanRegistry.tsx`, `frontend/src/sections/kredity/parts/DscrCard.tsx`, `frontend/src/sections/kredity/parts/NoLoans.tsx`
- Modify: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (generatsiya), `frontend/src/api/types.ts`, `frontend/src/dash/formulas.ts` (`IndicatorKey`), `frontend/src/i18n/ru.ts`
- Test: `frontend/src/sections/kredity/parts/parts.test.tsx`

**Interfaces:**
- Consumes: 4-vazifa endpointlari va sxemalari, `Card`, `KpiGrid`, `KpiTile`, `Table`, `Column`, `Badge`, `EmptyState`, `ChartCanvas`, `barConfig`, `ChartHandle`, `CardExport`, `ExportContext`, `NoData`, `formula`, `formatMoney`, `formatPct`, `moneyParts`, `formatDate`, `formatNumber`, `buildHash`, `toggleBranch`, `FilterState`, `mockApi`, `json`, `renderWithProviders`, `expectNoAxeViolations`, `ME_ADMIN`.
- Produces:
  - `src/api/types.ts`: `LoanPaymentOut, LoanKpisOut, LoanYearOut, NamedAmountOut, LoanRowOut, KreditySvodOut, KredityReestrOut, KredityGrafikOut`.
  - `IndicatorKey` += `'portfolio' | 'loanRate' | 'fxShare' | 'debtService' | 'loanPaid' | 'nextPayment' | 'peakYear' | 'dscr'`.
  - `src/test/s2Fixtures.ts`: `PERIOD_M08_KR`, `UPCOMING`, `SCHEDULE`, `LOAN_KPIS`, `LOAN_ROWS`, `KREDITY_SVOD`, `KREDITY_REESTR`, `KREDITY_GRAFIK`, `KREDITY_EMPTY_GRAFIK`.
  - Kartalar: `currencyName(code) -> string`, `LoanKpis({ kpis })`, `ScheduleCard({ years, ctx, className? })`, `UpcomingCard({ payments, title, sub, ctx, className?, more? })`, `LoanRegistry({ loans, asOf, ctx, filters, onBranch, className? })`, `DscrCard({ dscr, className? })`, `NoLoans()`.

- [ ] **Step 1: OpenAPI snapshot va tiplar**

Dev stack (1–13-vazifalar bilan) ishlayotgan bo'lsin: `docker compose -f deploy/compose.yml up -d --build`.
```bash
curl -skf https://localhost:8443/api/v1/openapi.json -o frontend/openapi.json
$NODE npm run gen:api
grep -c "KreditySvodOut\|KredityReestrOut\|LoanKpisOut" frontend/src/api/schema.d.ts
```
Expected: `grep` > 0.

`frontend/src/api/types.ts` — oxiriga qo'shing:
```ts
export type LoanPaymentOut = Schemas['LoanPaymentOut'];
export type LoanKpisOut = Schemas['LoanKpisOut'];
export type LoanYearOut = Schemas['LoanYearOut'];
export type NamedAmountOut = Schemas['NamedAmountOut'];
export type LoanRowOut = Schemas['LoanRowOut'];
export type KreditySvodOut = Schemas['KreditySvodOut'];
export type KredityReestrOut = Schemas['KredityReestrOut'];
export type KredityGrafikOut = Schemas['KredityGrafikOut'];
```

- [ ] **Step 2: Formulalar va lug'at kalitlari**

`frontend/src/dash/formulas.ts` — `IndicatorKey` turining oxirgi qatoriga (`| 'calendar' | 'coverage' | 'targetUse' | 'balance'`) davom qo'shing:
```ts
  | 'portfolio' | 'loanRate' | 'fxShare' | 'debtService' | 'loanPaid' | 'nextPayment' | 'peakYear' | 'dscr';
```
(ya'ni oldingi qatordagi `;` olib tashlanadi, tur shu qator bilan tugaydi.)

`frontend/src/i18n/ru.ts` — `} as const satisfies …` dan oldin qo'shing:
```ts
  'formula.portfolio': 'Кредитный портфель — остаток основного долга в сумовом эквиваленте по курсу ЦБ на отчётную дату',
  'formula.loanRate': 'Средневзвешенная ставка = сумма (остаток × ставка) / сумма остатков',
  'formula.fxShare': 'Доля валютных кредитов = остаток в валюте / весь портфель',
  'formula.debtService': 'Обслуживание долга года = основной долг + проценты по графику года',
  'formula.loanPaid': 'Оплачено — платежи по графику с датой не позже отчётной',
  'formula.nextPayment': 'Ближайший платёж — первый платёж по графику после отчётной даты',
  'formula.peakYear': 'Год пиковой нагрузки — год с наибольшей суммой основного долга и процентов по графику',
  'formula.dscr': 'DSCR = EBITDA года / обслуживание долга года (из финансовой модели)',
  'kredity.kpi.portfolio': 'Кредитный портфель',
  'kredity.kpi.portfolioNote': 'на {date}, кредитов: {count}',
  'kredity.kpi.noRate': 'нет курса ЦБ: {currencies}',
  'kredity.kpi.rate': 'Средневзвешенная ставка',
  'kredity.kpi.rateNote': 'по остатку долга',
  'kredity.kpi.fxShare': 'Доля валютных кредитов',
  'kredity.kpi.fxShareNote': 'кредиты не в сумах',
  'kredity.kpi.service': 'Обслуживание долга {year}',
  'kredity.kpi.serviceNote': 'оплачено {paid} ({share})',
  'kredity.kpi.next': 'Ближайший платёж',
  'kredity.kpi.nextNone': 'нет',
  'kredity.kpi.nextNote': '{amount}, {creditor}',
  'kredity.kpi.peak': 'Пик нагрузки',
  'kredity.kpi.peakNote': '{amount} основного долга и процентов',
  'kredity.schedule.title': 'График погашения',
  'kredity.schedule.sub': 'Основной долг и проценты по годам, в сумовом эквиваленте',
  'kredity.schedule.principal': 'Основной долг',
  'kredity.schedule.interest': 'Проценты',
  'kredity.schedule.year': 'Год',
  'kredity.currency.title': 'Валютная структура',
  'kredity.currency.sub': 'Остаток долга по валютам',
  'kredity.currency.USD': 'Доллар США (USD)',
  'kredity.currency.EUR': 'Евро (EUR)',
  'kredity.currency.CNY': 'Юань (CNY)',
  'kredity.currency.UZS': 'Сум (UZS)',
  'kredity.upcoming.titleShort': 'Ближайшие платежи',
  'kredity.upcoming.subShort': 'Пять следующих платежей по графику',
  'kredity.upcoming.title': 'Предстоящие платежи',
  'kredity.upcoming.sub': 'Двенадцать ближайших платежей',
  'kredity.upcoming.date': 'Дата',
  'kredity.upcoming.creditor': 'Кредитор',
  'kredity.upcoming.total': 'Итого',
  'kredity.upcoming.none': 'Предстоящих платежей нет.',
  'kredity.upcoming.all': 'Весь график',
  'kredity.upcoming.noRate': 'нет курса',
  'kredity.registry.title': 'Кредиты',
  'kredity.registry.sub': 'Остатки на {date}',
  'kredity.registry.creditor': 'Кредитор',
  'kredity.registry.project': 'Проект',
  'kredity.registry.currency': 'Валюта',
  'kredity.registry.rate': 'Ставка',
  'kredity.registry.outstanding': 'Остаток',
  'kredity.registry.repaid': 'Погашено',
  'kredity.registry.grace': 'Льготный период',
  'kredity.registry.graceUntil': 'до {year} года',
  'kredity.registry.graceDone': 'завершён',
  'kredity.registry.maturity': 'Срок погашения',
  'kredity.registry.total': 'Итого',
  'kredity.creditors.title': 'Остаток по кредиторам',
  'kredity.creditors.sub': 'В сумовом эквиваленте',
  'kredity.dscr.title': 'Покрытие обслуживания долга (DSCR)',
  'kredity.dscr.sub': 'EBITDA года / обслуживание долга года',
  'kredity.dscr.source': 'финансовая модель (раздел «Финмодель»)',
  'kredity.none.title': 'Нет кредитов',
  'kredity.none.text': 'У выбранного филиала нет кредитов. Выберите другой филиал в фильтрах.',
```

- [ ] **Step 3: Test fixture'lari (backend ssenariysiga yaqin raqamlar)**

`frontend/src/test/s2Fixtures.ts`:
```ts
import type {
  KredityGrafikOut,
  KredityReestrOut,
  KreditySvodOut,
  LoanKpisOut,
  LoanPaymentOut,
  LoanRowOut,
  LoanYearOut,
  ReportPeriodOut,
} from '../api/types';

export const PERIOD_M08_KR: ReportPeriodOut = { code: 'm08', label: 'Август 2026', date_from: '2026-08-01', date_to: '2026-08-31', open_last: false };

function payment(day: string, loanId: number, creditor: string, project: string, principal: number | null, interest: number | null): LoanPaymentOut {
  return {
    day,
    loan_id: loanId,
    creditor,
    project,
    branch_name: loanId === 1 ? 'Чарвакская ГЭС' : 'Каскад Чирчикских ГЭС',
    principal,
    interest,
    total: principal === null || interest === null ? null : principal + interest,
  };
}

const ADB = 'Азиатский банк развития';
const NBU = 'Национальный банк';

export const UPCOMING: LoanPaymentOut[] = [
  payment('2026-09-15', 1, ADB, 'Модернизация Чарвакской ГЭС', 1000, 460),
  payment('2026-10-10', 2, NBU, 'Оборотные средства', 100, 18),
  payment('2027-03-15', 1, ADB, 'Модернизация Чарвакской ГЭС', 1000, 400),
  payment('2027-10-10', 2, NBU, 'Оборотные средства', 300, 18),
  payment('2028-03-15', 1, ADB, 'Модернизация Чарвакской ГЭС', null, null),
];

export const SCHEDULE: LoanYearOut[] = Array.from({ length: 10 }, (_, i) => ({
  year: 2026 + i,
  principal: [2200, 1300, 7000][i] ?? 0,
  interest: [1008, 418, 350][i] ?? 0,
}));

export const LOAN_KPIS: LoanKpisOut = {
  as_of: '2026-08-31',
  loans: 2,
  portfolio: 9400,
  rate: 522 / 9400,
  fx_share: 9000 / 9400,
  service: 3208,
  paid: 1630,
  paid_share: 1630 / 3208,
  next_payment: UPCOMING[0] ?? null,
  peak_year: 2028,
  peak_amount: 7350,
  missing_fx: [],
  dscr: null,
};

export const LOAN_ROWS: LoanRowOut[] = [
  {
    loan_id: 1, loan_code: 'ADB-01', creditor: ADB, project: 'Модернизация Чарвакской ГЭС', branch_id: 2, branch_name: 'Чарвакская ГЭС',
    currency: 'USD', rate: 0.05, outstanding: 9000, outstanding_cur: 0.76, original_cur: 0.85, repaid_share: 0.1, grace_until: '2027-01-01', in_grace: true, maturity: '2028-12-31',
  },
  {
    loan_id: 2, loan_code: 'NBU-02', creditor: NBU, project: 'Оборотные средства', branch_id: 3, branch_name: 'Каскад Чирчикских ГЭС',
    currency: 'UZS', rate: 0.18, outstanding: 400, outstanding_cur: 400, original_cur: 500, repaid_share: 0.2, grace_until: null, in_grace: false, maturity: '2027-12-31',
  },
];

const CURRENCIES = [{ name: 'USD', amount: 9000 }, { name: 'UZS', amount: 400 }];

export const KREDITY_SVOD: KreditySvodOut = {
  period: PERIOD_M08_KR, has_loans: true, kpis: LOAN_KPIS, schedule: SCHEDULE, currencies: CURRENCIES, upcoming: UPCOMING,
};

export const KREDITY_REESTR: KredityReestrOut = {
  period: PERIOD_M08_KR, has_loans: true, kpis: LOAN_KPIS, loans: LOAN_ROWS,
  creditors: [{ name: ADB, amount: 9000 }, { name: NBU, amount: 400 }], currencies: CURRENCIES,
};

export const KREDITY_GRAFIK: KredityGrafikOut = { period: PERIOD_M08_KR, has_loans: true, schedule: SCHEDULE, upcoming: UPCOMING };

export const KREDITY_EMPTY_GRAFIK: KredityGrafikOut = {
  period: PERIOD_M08_KR, has_loans: false, schedule: SCHEDULE.map((y) => ({ ...y, principal: 0, interest: 0 })), upcoming: [],
};
```

- [ ] **Step 4: Testlarni yozish**

`frontend/src/sections/kredity/parts/parts.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../../test/axe';
import { ME_ADMIN } from '../../../test/fixtures';
import { json, mockApi } from '../../../test/mockApi';
import { renderWithProviders } from '../../../test/render';
import { LOAN_KPIS, LOAN_ROWS, SCHEDULE, UPCOMING } from '../../../test/s2Fixtures';
import { currencyName } from './currency';
import { DscrCard } from './DscrCard';
import { LoanKpis } from './LoanKpis';
import { LoanRegistry } from './LoanRegistry';
import { NoLoans } from './NoLoans';
import { ScheduleCard } from './ScheduleCard';
import { UpcomingCard } from './UpcomingCard';

const ctx = { section: 'kredity', page: 'svod', br: null, per: 'm08' };
const filters = { br: null, per: 'm08' };

describe('Кредиты: карточки', () => {
  it('KPIs show portfolio, rate, service, next payment and peak year', async () => {
    const { container } = renderWithProviders(<LoanKpis kpis={LOAN_KPIS} />);
    expect(screen.getByText('Кредитный портфель')).toBeInTheDocument();
    expect(screen.getByText('9,4')).toBeInTheDocument();
    expect(screen.getByText('5,55%')).toBeInTheDocument();
    expect(screen.getByText('Обслуживание долга 2026')).toBeInTheDocument();
    expect(screen.getByText('15.09.2026')).toBeInTheDocument();
    expect(screen.getByText('2028')).toBeInTheDocument();
    expect(screen.getByText('на 31.08.2026, кредитов: 2')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('KPIs warn about currencies without a CBU rate', () => {
    renderWithProviders(<LoanKpis kpis={{ ...LOAN_KPIS, missing_fx: ['CNY'] }} />);
    expect(screen.getByText('нет курса ЦБ: CNY')).toBeInTheDocument();
  });

  it('schedule chart is accessible and upcoming payments show missing rates', async () => {
    mockApi({ 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(
      <>
        <ScheduleCard years={SCHEDULE} ctx={ctx} />
        <UpcomingCard payments={UPCOMING} title="Ближайшие платежи" sub="Пять" ctx={ctx} more />
      </>,
    );
    expect(screen.getByRole('img', { name: 'График погашения' })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Ближайшие платежи' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + UPCOMING.length);
    expect(within(table).getAllByText('нет курса').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Весь график' }).getAttribute('href')).toContain('kredity/grafik');
    expect(await screen.findByRole('button', { name: 'Выгрузить таблицу «Ближайшие платежи» в CSV' })).toBeInTheDocument();
  });

  it('registry shows grace badge, total and toggles the branch filter', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<LoanRegistry loans={LOAN_ROWS} asOf="2026-08-31" ctx={ctx} filters={filters} onBranch={onBranch} />);
    const table = screen.getByRole('table', { name: 'Кредиты' });
    expect(within(table).getByText('до 2027 года')).toBeInTheDocument();
    expect(within(table).getByText('Итого')).toBeInTheDocument();
    await user.click(within(table).getByText('Национальный банк'));
    expect(onBranch).toHaveBeenCalledWith(3);
  });

  it('DSCR gap, no-loans message and currency names', () => {
    renderWithProviders(
      <>
        <DscrCard dscr={null} />
        <NoLoans />
      </>,
    );
    expect(screen.getByText(/Источник данных не подключён: финансовая модель/)).toBeInTheDocument();
    expect(screen.getByText(/У выбранного филиала нет кредитов/)).toBeInTheDocument();
    expect(currencyName('USD')).toBe('Доллар США (USD)');
    expect(currencyName('XTL')).toBe('XTL');
  });
});
```

- [ ] **Step 5: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/kredity`
Expected: FAIL — `Failed to resolve import "./currency"`.

- [ ] **Step 6: Implementatsiya — kartalar**

`frontend/src/sections/kredity/parts/currency.ts`:
```ts
import { t, type MessageKey } from '../../../i18n';

const KNOWN = new Set(['USD', 'EUR', 'CNY', 'UZS']);

/** Prototip `curItems`: «Доллар США (USD)»; noma'lum kod — o'zi. */
export function currencyName(code: string): string {
  return KNOWN.has(code) ? t(`kredity.currency.${code}` as MessageKey) : code;
}
```

`frontend/src/sections/kredity/parts/LoanKpis.tsx`:
```tsx
import type { LoanKpisOut } from '../../../api/types';
import { formula } from '../../../dash/formulas';
import { formatMoney, formatPct, moneyParts } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { KpiGrid, KpiTile } from '../../../ui/KpiTile';

function money(value: number | null): { value: string; unit?: string } {
  if (value === null) return { value: t('dash.noValue') };
  const parts = moneyParts(value);
  return { value: parts.value, unit: parts.unit };
}

/** Prototip `kpisCred`: портфель, ставка, валютная доля, обслуживание долга, ближайший платёж, пик. */
export function LoanKpis({ kpis }: { kpis: LoanKpisOut }) {
  const portfolio = money(kpis.portfolio);
  const service = money(kpis.service);
  const next = kpis.next_payment;
  const note = t('kredity.kpi.portfolioNote', { date: formatDate(kpis.as_of), count: kpis.loans });
  return (
    <KpiGrid>
      <KpiTile
        icon="card"
        label={t('kredity.kpi.portfolio')}
        value={portfolio.value}
        unit={portfolio.unit}
        delta={kpis.missing_fx.length ? <span className="neg">{t('kredity.kpi.noRate', { currencies: kpis.missing_fx.join(', ') })}</span> : note}
        hint={formula('portfolio')}
      />
      <KpiTile icon="pct" label={t('kredity.kpi.rate')} value={formatPct(kpis.rate, 2)} delta={t('kredity.kpi.rateNote')} hint={formula('loanRate')} />
      <KpiTile icon="coins" label={t('kredity.kpi.fxShare')} value={formatPct(kpis.fx_share, 1)} delta={t('kredity.kpi.fxShareNote')} hint={formula('fxShare')} />
      <KpiTile
        icon="check"
        label={t('kredity.kpi.service', { year: kpis.as_of.slice(0, 4) })}
        value={service.value}
        unit={service.unit}
        delta={t('kredity.kpi.serviceNote', { paid: formatMoney(kpis.paid), share: formatPct(kpis.paid_share, 0) })}
        hint={`${formula('debtService')}. ${formula('loanPaid')}`}
      />
      <KpiTile
        icon="cal"
        label={t('kredity.kpi.next')}
        value={next ? formatDate(next.day) : t('kredity.kpi.nextNone')}
        delta={next ? t('kredity.kpi.nextNote', { amount: formatMoney(next.total), creditor: next.creditor }) : undefined}
        hint={formula('nextPayment')}
      />
      <KpiTile
        icon="alert"
        label={t('kredity.kpi.peak')}
        value={kpis.peak_year === null ? '—' : String(kpis.peak_year)}
        delta={kpis.peak_amount === null ? undefined : t('kredity.kpi.peakNote', { amount: formatMoney(kpis.peak_amount) })}
        hint={formula('peakYear')}
      />
    </KpiGrid>
  );
}
```

`frontend/src/sections/kredity/parts/ScheduleCard.tsx`:
```tsx
import { useMemo, useRef } from 'react';
import type { LoanYearOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import { barConfig, ChartCanvas, type ChartHandle } from '../../../dash/chart';
import type { ExportContext } from '../../../dash/exportLog';
import { formula } from '../../../dash/formulas';
import { t } from '../../../i18n';
import { Card } from '../../../ui/Card';

const PRINCIPAL = '#0b4fa8';
const INTEREST = '#5fd0e0';

/** TZ 5: график погашения на 10 лет с разделением основного долга и процентов. */
export function ScheduleCard({ years, ctx, className }: { years: LoanYearOut[]; ctx: ExportContext; className?: string }) {
  const title = t('kredity.schedule.title');
  const chartRef = useRef<ChartHandle | null>(null);
  const config = useMemo(
    () =>
      barConfig({
        labels: years.map((y) => String(y.year)),
        series: [
          { label: t('kredity.schedule.principal'), data: years.map((y) => y.principal), color: PRINCIPAL },
          { label: t('kredity.schedule.interest'), data: years.map((y) => y.interest), color: INTEREST },
        ],
        stacked: true,
      }),
    [years],
  );
  const table = {
    headers: [t('kredity.schedule.year'), t('kredity.schedule.principal'), t('kredity.schedule.interest')],
    rows: years.map((y) => [String(y.year), y.principal, y.interest]),
  };
  return (
    <Card className={className} title={title} sub={t('kredity.schedule.sub')} exportSlot={<CardExport title={title} ctx={ctx} chartRef={chartRef} csv={() => table} />}>
      <div className="legend" title={formula('debtService')}>
        <span>
          <i style={{ background: PRINCIPAL }} />
          {t('kredity.schedule.principal')}
        </span>
        <span>
          <i style={{ background: INTEREST }} />
          {t('kredity.schedule.interest')}
        </span>
      </div>
      <ChartCanvas config={config} label={title} table={table} chartRef={chartRef} />
    </Card>
  );
}
```

`frontend/src/sections/kredity/parts/UpcomingCard.tsx`:
```tsx
import type { LoanPaymentOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import { buildHash } from '../../../router/hash';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';

function amount(value: number | null): string {
  return value === null ? t('kredity.upcoming.noRate') : formatMoney(value);
}

export interface UpcomingCardProps {
  payments: LoanPaymentOut[];
  title: string;
  sub: string;
  ctx: ExportContext;
  className?: string;
  more?: boolean;
}

/** Prototip `upcomingList`: ближайшие платежи по графику (дата, кредитор, основной долг, проценты). */
export function UpcomingCard({ payments, title, sub, ctx, className, more = false }: UpcomingCardProps) {
  const headers = [t('kredity.upcoming.date'), t('kredity.upcoming.creditor'), t('kredity.schedule.principal'), t('kredity.schedule.interest'), t('kredity.upcoming.total')];
  const columns: Column<LoanPaymentOut>[] = [
    { key: 'day', header: headers[0] ?? '', cell: (p) => formatDate(p.day), sortValue: (p) => p.day },
    {
      key: 'creditor',
      header: headers[1] ?? '',
      cell: (p) => (
        <>
          {p.creditor}
          <br />
          <span className="note">{p.project}</span>
        </>
      ),
      sortValue: (p) => p.creditor,
      wrap: true,
    },
    { key: 'principal', header: headers[2] ?? '', cell: (p) => amount(p.principal), sortValue: (p) => p.principal, align: 'right' },
    { key: 'interest', header: headers[3] ?? '', cell: (p) => amount(p.interest), sortValue: (p) => p.interest, align: 'right' },
    { key: 'total', header: headers[4] ?? '', cell: (p) => <b>{amount(p.total)}</b>, sortValue: (p) => p.total, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={sub}
      exportSlot={
        payments.length ? (
          <CardExport title={title} ctx={ctx} csv={() => ({ headers, rows: payments.map((p) => [formatDate(p.day), p.creditor, p.principal, p.interest, p.total]) })} />
        ) : undefined
      }
    >
      <Table caption={title} columns={columns} rows={payments} rowKey={(p) => `${p.day}-${p.loan_id}`} free empty={<p className="note">{t('kredity.upcoming.none')}</p>} />
      {more ? (
        <a className="more" href={buildHash({ kind: 'section', section: 'kredity', page: 'grafik', br: ctx.br, per: ctx.per })}>
          {t('kredity.upcoming.all')}
        </a>
      ) : null}
    </Card>
  );
}
```

`frontend/src/sections/kredity/parts/LoanRegistry.tsx`:
```tsx
import type { LoanRowOut } from '../../../api/types';
import { CardExport } from '../../../dash/CardExport';
import type { ExportContext } from '../../../dash/exportLog';
import { formatMoney, formatPct } from '../../../dash/money';
import { t } from '../../../i18n';
import { formatDate } from '../../../i18n/format';
import type { FilterState } from '../../../shell/useFilters';
import { Badge } from '../../../ui/Badge';
import { Card } from '../../../ui/Card';
import { Table, type Column } from '../../../ui/Table';
import { toggleBranch } from '../../useSection';

function Repaid({ share }: { share: number | null }) {
  return (
    <span className="exec">
      {formatPct(share, 1)}
      <i aria-hidden="true">
        <b style={{ width: `${Math.min(100, Math.max(0, (share ?? 0) * 100))}%` }} />
      </i>
    </span>
  );
}

function grace(row: LoanRowOut) {
  if (!row.grace_until) return '—';
  return row.in_grace ? <Badge tone="blue">{t('kredity.registry.graceUntil', { year: row.grace_until.slice(0, 4) })}</Badge> : <Badge>{t('kredity.registry.graceDone')}</Badge>;
}

export interface LoanRegistryProps {
  loans: LoanRowOut[];
  asOf: string;
  ctx: ExportContext;
  filters: FilterState;
  onBranch(br: number | null): void;
  className?: string;
}

/** TZ 5: реестр кредитов с условиями и долей погашения; нажатие на строку выбирает филиал (TZ 6). */
export function LoanRegistry({ loans, asOf, ctx, filters, onBranch, className }: LoanRegistryProps) {
  const title = t('kredity.registry.title');
  const total = loans.reduce((s, r) => s + (r.outstanding ?? 0), 0);
  const columns: Column<LoanRowOut>[] = [
    { key: 'creditor', header: t('kredity.registry.creditor'), cell: (r) => r.creditor, sortValue: (r) => r.creditor, wrap: true },
    {
      key: 'project',
      header: t('kredity.registry.project'),
      cell: (r) => (
        <>
          {r.project}
          <br />
          <span className="note">{r.branch_name}</span>
        </>
      ),
      wrap: true,
    },
    { key: 'currency', header: t('kredity.registry.currency'), cell: (r) => r.currency, sortValue: (r) => r.currency },
    { key: 'rate', header: t('kredity.registry.rate'), cell: (r) => formatPct(r.rate, 1), sortValue: (r) => r.rate, align: 'right' },
    {
      key: 'outstanding',
      header: t('kredity.registry.outstanding'),
      cell: (r) => <b>{r.outstanding === null ? t('kredity.upcoming.noRate') : formatMoney(r.outstanding)}</b>,
      sortValue: (r) => r.outstanding,
      align: 'right',
    },
    { key: 'repaid', header: t('kredity.registry.repaid'), cell: (r) => <Repaid share={r.repaid_share} />, sortValue: (r) => r.repaid_share, align: 'right' },
    { key: 'grace', header: t('kredity.registry.grace'), cell: grace },
    { key: 'maturity', header: t('kredity.registry.maturity'), cell: (r) => r.maturity.slice(0, 4), sortValue: (r) => r.maturity, align: 'right' },
  ];
  return (
    <Card
      className={className}
      title={title}
      sub={t('kredity.registry.sub', { date: formatDate(asOf) })}
      exportSlot={
        <CardExport
          title={title}
          ctx={ctx}
          csv={() => ({
            headers: [t('kredity.registry.creditor'), t('kredity.registry.project'), t('kredity.registry.currency'), t('kredity.registry.rate'), t('kredity.registry.outstanding'), t('kredity.registry.repaid'), t('kredity.registry.maturity')],
            rows: loans.map((r) => [r.creditor, r.project, r.currency, Math.round(r.rate * 10000) / 100, r.outstanding, r.repaid_share === null ? null : Math.round(r.repaid_share * 1000) / 10, formatDate(r.maturity)]),
          })}
        />
      }
    >
      <Table
        caption={title}
        columns={columns}
        rows={loans}
        rowKey={(r) => r.loan_id}
        onRowClick={(r) => toggleBranch(filters, r.branch_id, onBranch)}
        free
        footer={
          <tr>
            <td colSpan={4}>{t('kredity.registry.total')}</td>
            <td>
              <b>{formatMoney(total)}</b>
            </td>
            <td colSpan={3} />
          </tr>
        }
      />
    </Card>
  );
}
```

`frontend/src/sections/kredity/parts/DscrCard.tsx`:
```tsx
import { NoData } from '../../../dash/DataState';
import { formula } from '../../../dash/formulas';
import { t } from '../../../i18n';
import { formatNumber } from '../../../i18n/format';
import { Card } from '../../../ui/Card';

/** TZ 4: DSCR = EBITDA / обслуживание долга — из финмодели (S5); до этого «источник не подключён». */
export function DscrCard({ dscr, className }: { dscr: number | null; className?: string }) {
  return (
    <Card className={className} title={t('kredity.dscr.title')} sub={t('kredity.dscr.sub')}>
      {dscr === null ? (
        <NoData kind="source" source={t('kredity.dscr.source')} />
      ) : (
        <div className="bigline" title={formula('dscr')}>
          <b>{formatNumber(dscr, 2)}</b>
        </div>
      )}
    </Card>
  );
}
```

`frontend/src/sections/kredity/parts/NoLoans.tsx`:
```tsx
import { t } from '../../../i18n';
import { EmptyState } from '../../../ui/EmptyState';

/** TZ 6 «Нет объектов у филиала»: пояснение вместо пустых карточек. */
export function NoLoans() {
  return <EmptyState icon="card" title={t('kredity.none.title')} text={t('kredity.none.text')} />;
}
```

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/kredity` va `$NODE npm run typecheck && $NODE npm run lint`
Expected: 5 test passed; tsc va eslint xatosiz.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Кредиты» tiplari, formulalar, KPI, grafik, to'lovlar, reyestr va DSCR kartalari

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Frontend — «Кредиты» sahifalari: Сводка, Реестр кредитов, График платежей

**Files:**
- Create: `frontend/src/sections/kredity/svod.tsx`, `frontend/src/sections/kredity/reestr.tsx`, `frontend/src/sections/kredity/grafik.tsx`
- Test: `frontend/src/sections/kredity/kredity.test.tsx`

**Interfaces:**
- Consumes: `useSection`, `SectionData`, `SectionPageProps`, `Card`, `Rank`, 14-vazifa kartalari, fixture'lar `KREDITY_SVOD`, `KREDITY_REESTR`, `KREDITY_GRAFIK`, `KREDITY_EMPTY_GRAFIK`, `ME_ADMIN`.
- Produces: sahifalar `#kredity/svod`, `#kredity/reestr`, `#kredity/grafik` (3-reja reyestri glob orqali avtomatik ulaydi).

- [ ] **Step 1: Testlarni yozish**

`frontend/src/sections/kredity/kredity.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { expectNoAxeViolations } from '../../test/axe';
import { ME_ADMIN } from '../../test/fixtures';
import { json, mockApi } from '../../test/mockApi';
import { renderWithProviders } from '../../test/render';
import { KREDITY_EMPTY_GRAFIK, KREDITY_GRAFIK, KREDITY_REESTR, KREDITY_SVOD } from '../../test/s2Fixtures';
import KredityGrafik from './grafik';
import KredityReestr from './reestr';
import KreditySvod from './svod';

const filters = { br: null, per: 'm08' };

describe('Кредиты', () => {
  it('Сводка: KPIs, schedule, currency structure, five payments and DSCR', async () => {
    mockApi({ 'GET /kredity/svod': json(KREDITY_SVOD), 'GET /auth/me': json(ME_ADMIN) });
    const { container } = renderWithProviders(<KreditySvod section="kredity" page="svod" filters={filters} onBranch={vi.fn()} />);
    expect(await screen.findByText('Кредитный портфель')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'График погашения' })).toBeInTheDocument();
    const currencies = screen.getByRole('list', { name: 'Валютная структура' });
    expect(within(currencies).getByText('Доллар США (USD)')).toBeInTheDocument();
    const upcoming = screen.getByRole('table', { name: 'Ближайшие платежи' });
    expect(within(upcoming).getAllByRole('row')).toHaveLength(1 + 5);
    expect(screen.getByRole('heading', { name: 'Покрытие обслуживания долга (DSCR)' })).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('Реестр: registry, creditors and currencies; row click selects the branch', async () => {
    const onBranch = vi.fn();
    mockApi({ 'GET /kredity/reestr': json(KREDITY_REESTR), 'GET /auth/me': json(ME_ADMIN) });
    const { user } = renderWithProviders(<KredityReestr section="kredity" page="reestr" filters={filters} onBranch={onBranch} />);
    const table = await screen.findByRole('table', { name: 'Кредиты' });
    expect(screen.getByRole('list', { name: 'Остаток по кредиторам' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Валютная структура' })).toBeInTheDocument();
    await user.click(within(table).getByText('Азиатский банк развития'));
    expect(onBranch).toHaveBeenCalledWith(2);
  });

  it('График платежей: schedule and upcoming; branch without loans shows an explanation', async () => {
    mockApi({ 'GET /kredity/grafik': json(KREDITY_GRAFIK), 'GET /auth/me': json(ME_ADMIN) });
    const { unmount } = renderWithProviders(<KredityGrafik section="kredity" page="grafik" filters={filters} onBranch={vi.fn()} />);
    const table = await screen.findByRole('table', { name: 'Предстоящие платежи' });
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 5);
    expect(screen.getByRole('img', { name: 'График погашения' })).toBeInTheDocument();
    unmount();
    mockApi({ 'GET /kredity/grafik': json(KREDITY_EMPTY_GRAFIK), 'GET /auth/me': json(ME_ADMIN) });
    renderWithProviders(<KredityGrafik section="kredity" page="grafik" filters={{ br: 1, per: 'm08' }} onBranch={vi.fn()} />);
    expect(await screen.findByText(/У выбранного филиала нет кредитов/)).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'График погашения' })).toBeNull();
  });
});
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$NODE npx vitest run src/sections/kredity/kredity.test.tsx`
Expected: FAIL — `Failed to resolve import "./svod"`.

- [ ] **Step 3: Implementatsiya — sahifalar**

`frontend/src/sections/kredity/svod.tsx`:
```tsx
import type { KreditySvodOut } from '../../api/types';
import { Rank } from '../../dash/Rank';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { currencyName } from './parts/currency';
import { DscrCard } from './parts/DscrCard';
import { LoanKpis } from './parts/LoanKpis';
import { NoLoans } from './parts/NoLoans';
import { ScheduleCard } from './parts/ScheduleCard';
import { UpcomingCard } from './parts/UpcomingCard';

export default function KreditySvod({ section, page, filters }: SectionPageProps) {
  const query = useSection<KreditySvodOut>('/kredity/svod', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_loans ? (
          <>
            <LoanKpis kpis={data.kpis} />
            <div className="grid">
              <ScheduleCard className="c8 wide" years={data.schedule} ctx={ctx} />
              <Card className="c4 wide" title={t('kredity.currency.title')} sub={t('kredity.currency.sub')}>
                <Rank label={t('kredity.currency.title')} items={data.currencies.map((c) => ({ id: c.name, name: currencyName(c.name), value: c.amount }))} />
              </Card>
              <UpcomingCard className="c8" payments={data.upcoming} title={t('kredity.upcoming.titleShort')} sub={t('kredity.upcoming.subShort')} ctx={ctx} more />
              <DscrCard className="c4" dscr={data.kpis.dscr} />
            </div>
          </>
        ) : (
          <NoLoans />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/kredity/reestr.tsx`:
```tsx
import type { KredityReestrOut } from '../../api/types';
import { Rank } from '../../dash/Rank';
import { t } from '../../i18n';
import { Card } from '../../ui/Card';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { currencyName } from './parts/currency';
import { LoanKpis } from './parts/LoanKpis';
import { LoanRegistry } from './parts/LoanRegistry';
import { NoLoans } from './parts/NoLoans';

export default function KredityReestr({ section, page, filters, onBranch }: SectionPageProps) {
  const query = useSection<KredityReestrOut>('/kredity/reestr', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_loans ? (
          <>
            <LoanKpis kpis={data.kpis} />
            <div className="grid">
              <LoanRegistry className="c12" loans={data.loans} asOf={data.kpis.as_of} ctx={ctx} filters={filters} onBranch={onBranch} />
              <Card className="c6" title={t('kredity.creditors.title')} sub={t('kredity.creditors.sub')}>
                <Rank label={t('kredity.creditors.title')} items={data.creditors.map((c) => ({ id: c.name, name: c.name, value: c.amount }))} />
              </Card>
              <Card className="c6" title={t('kredity.currency.title')} sub={t('kredity.currency.sub')}>
                <Rank label={t('kredity.currency.title')} items={data.currencies.map((c) => ({ id: c.name, name: currencyName(c.name), value: c.amount }))} />
              </Card>
            </div>
          </>
        ) : (
          <NoLoans />
        )
      }
    </SectionData>
  );
}
```

`frontend/src/sections/kredity/grafik.tsx`:
```tsx
import type { KredityGrafikOut } from '../../api/types';
import { t } from '../../i18n';
import type { SectionPageProps } from '../registry';
import { SectionData } from '../SectionData';
import { useSection } from '../useSection';
import { NoLoans } from './parts/NoLoans';
import { ScheduleCard } from './parts/ScheduleCard';
import { UpcomingCard } from './parts/UpcomingCard';

export default function KredityGrafik({ section, page, filters }: SectionPageProps) {
  const query = useSection<KredityGrafikOut>('/kredity/grafik', filters);
  const ctx = { section, page, br: filters.br, per: filters.per };
  return (
    <SectionData query={query}>
      {(data) =>
        data.has_loans ? (
          <div className="grid">
            <ScheduleCard className="c12" years={data.schedule} ctx={ctx} />
            <UpcomingCard className="c12" payments={data.upcoming} title={t('kredity.upcoming.title')} sub={t('kredity.upcoming.sub')} ctx={ctx} />
          </div>
        ) : (
          <NoLoans />
        )
      }
    </SectionData>
  );
}
```

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$NODE npx vitest run src/sections/kredity` va `$NODE npm run check`
Expected: 8 test passed; `check` (tsc, eslint, vitest, build) — xatosiz; 3-reja `SectionScreen` testlari «Кредиты» uchun endi sahifa komponentini topadi (placeholder emas).

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Кредиты» — Сводка, Реестр кредитов, График платежей

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: E2E — «Кредиты» sahifalari, ruxsat va CSP; to'liq tekshiruv, spec holati

**Files:**
- Create: `frontend/e2e/specs/kredity.spec.ts`
- Modify: `docs/superpowers/specs/2026-09-25-s2-kredity-banki-design.md` (holat)
- Test: `frontend/e2e/specs/kredity.spec.ts`

**Interfaces:**
- Consumes: 3-reja E2E (`signIn`, `adminFor`, `expectNoHorizontalScroll`, `e2e_branch` — `economist_filiala`, filial 3; loyihalar `mobile-390`, `tablet-1024`, `desktop-1440`), S1 `scripts/e2e.sh` (sintetik to'liq yuklash — 8 kredit va kunlik USD/EUR/CNY kurslari).
- Produces: E2E ssenariylari.

- [ ] **Step 1: E2E ssenariysini yozish**

`frontend/e2e/specs/kredity.spec.ts`:
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

test('Кредиты: сводка, реестр, график платежей', async ({ page }, info) => {
  const csp = watchCsp(page);
  await page.goto('/#kredity/svod');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Кредиты: сводка' })).toBeVisible();
  await expect(page.getByText('Кредитный портфель')).toBeVisible();
  await expect(page.getByRole('img', { name: 'График погашения' })).toBeVisible();
  await expect(page.getByText('Валютная структура')).toBeVisible();
  await expectNoHorizontalScroll(page);

  await open(page, '#kredity/reestr', 'Реестр кредитов');
  await expect(page.getByText('Остаток по кредиторам')).toBeVisible();
  await open(page, '#kredity/grafik', 'График платежей');
  await expect(page.getByRole('heading', { name: 'Предстоящие платежи' })).toBeVisible();
  if (info.project.name === 'desktop-1440') {
    await expect(page.getByRole('table', { name: 'Предстоящие платежи' }).locator('tbody tr')).toHaveCount(12);
  }
  await expectNoHorizontalScroll(page);
  expect(csp).toEqual([]);
});

test('Экономист филиала не имеет доступа к разделу «Кредиты»', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop-1440', 'bitta kenglik yetarli');
  await page.goto('/#obzor/svod');
  await signIn(page, 'e2e_branch');
  await expect(page.getByRole('heading', { level: 1, name: 'Обзор: сводка' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Кредиты' })).toHaveCount(0);
  for (const path of ['svod', 'reestr', 'grafik']) {
    const denied = await page.request.get(`/api/v1/kredity/${path}`);
    expect(denied.status()).toBe(403);
  }
});
```
(Sahifa sarlavhasi — 3-reja `SectionScreen`: «Сводка» uchun `«<bo'lim>: сводка»`, qolganlari — menyudagi nom. `e2e_branch` roli — `economist_filiala`, TZ 1 bo'yicha «Кредиты» unga yopiq.)

- [ ] **Step 2: To'liq tekshiruv**

```bash
docker compose -f deploy/compose.yml up -d --build
$TEST pytest -q
$NODE npm run check
./scripts/e2e.sh
./scripts/prod_config.sh
```
Expected: backend testlari passed (qamrov darvozasi 4-rejadagidek); frontend `check` passed; Playwright — 3 loyihada `kredity.spec.ts` va S1 `sections.spec.ts` passed (ruxsat testi faqat 1440 da), CSP buzilishi yo'q; `prod-config: OK`.

- [ ] **Step 3: Spec holati**

`docs/superpowers/specs/2026-09-25-s2-kredity-banki-design.md` — `- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)` qatorini almashtiring:
```markdown
- Holat: amalga oshirilgan (S2-reja: docs/superpowers/plans/2026-09-25-06-s2-kredity-banki.md); ochiq savollar 1–7 (bank formatlari, DirectBank, kredit manbai, Telegram roziligi) mijozda
```

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e docs/superpowers/specs
git commit -m "test(e2e): «Кредиты» sahifalari, ruxsat va CSP; S2 spec holati

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
