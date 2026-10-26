# UGEKAZNA 04b-reja: sozlamalarni admin paneldan boshqarish — implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Biznes, ETL, saqlash, monitoring va xavfsizlik siyosatining barcha qiymatlari hamda integratsiya hisob ma'lumotlari «Администрирование» bo'limidan, qayta ishga tushirishsiz, versiya va audit bilan boshqariladi; infratuzilma va kriptografik ildiz env/Docker secrets'da qoladi.

**Architecture:** Yagona tipli reyestr `app/core/sysconfig.py` (`SettingDef`: adapter, chegaralar, kategoriya, ruxsat, himoya) — manba ustuvorligi panel (`core.settings`) > env > kod standarti; issiq yo'l 30 s jarayon keshi orqali, ETL/worker tranzaksiya ichida o'qiydi; worker cron'lari har 60 s da panel bilan sinxronlanadi. Integratsiyalar `app/core/integrations.py` reyestrida, sirlar `core.integration_credentials` da AES-256-GCM (`integration_creds`), API sirni hech qachon qaytarmaydi; ulanish tekshiruvi `core.integration_checks` navbati orqali worker'da. Xavfsizlik va integratsiya o'zgarishlari alohida ruxsat (`admin:security`, `admin:integrations`), sabab va joriy TOTP kodini (step-up) talab qiladi; frontend'da uchta yangi admin sahifa.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (sync) + psycopg 3, pydantic 2, APScheduler 3, PostgreSQL 16, Redis 7, pytest; React 18 + TypeScript strict, TanStack Query 5, Vitest + Testing Library + axe, Playwright 1.49.1.

**Spec:** [docs/superpowers/specs/2026-10-26-admin-settings-design.md](../specs/2026-10-26-admin-settings-design.md). Asos: 1-reja (`Ctx`, `require_perm`, `AuditAction`, `log_event`, `keystore`, `reencrypt.REGISTRY`, `totp`, `ratelimit`, `sync_reference`), 2-reja (`DEFAULT_SETTINGS`, `validate_setting`, `current_setting`, `config_service`, worker, `notify`, `quality`, `compute_window`), 3-reja (admin qobig'i, `ADMIN_PAGES`, `ADMIN_COMPONENTS`, `AlertRulesPage` namunasi, `mockApi`, E2E fixture'lari), 4-reja (`app/ops.py`, `docs/security/*`, `docs/ops/*`, `backend/tests/ops/test_docs.py`, `make check`). 1–4-rejalar bajarilgan deb hisoblanadi; S1–S5 hali bajarilmagan.

## Global Constraints

- 1–4-rejalarning barcha Global Constraints'lari amal qiladi: UTC, `/api/v1`, xato formati `{"error": {code, message, request_id, params?}}`, `TEST="docker compose -f deploy/compose.test.yml run --rm test"`, `NODE="docker compose -f deploy/compose.frontend.yml run --rm node"`, bind-mount'li `docker run` oldidan `MSYS_NO_PATHCONV=1`, buyruqlar repo ildizidan (`C:\Users\uge226\Desktop\ugekazna`) Git Bash'da; host'ga hech narsa o'rnatilmaydi.
- Bajarilish tartibi: 4-reja → 04b → S1. Migratsiya `0008a` (`revision = "0008a"`, `down_revision = "0008"`); `0009..0021` S1–S5 uchun band.
- Har sozlama kaliti faqat `backend/app/core/sysconfig.py` `_DEFS` da, nomi `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`, ≤ 64 belgi. Kodda sozlama qiymatining ikkinchi nusxasi (konstanta) qolmaydi.
- Xavfsizlik va monitoring kalitlari faqat qattiqlashtiriladi — oraliqlar spec 2-bo'lim C jadvalidagi qiymatlar aynan (masalan `security.session_idle_minutes` 30; 5..30).
- Sir qiymati API javobida, audit `details`'da, log'da, xato matnida va `core.integration_checks` da hech qachon yo'q; shifrlash faqat `keystore.encrypt_str(Purpose.INTEGRATION, plain, "core.integration_credentials.value_enc:{name}")`.
- Step-up faqat `app.auth.stepup.require_step_up` orqali: joriy TOTP (zaxira kodi emas), `totp_last_step` dan katta qadam, limit 5 / 900 s.
- Kesh: `sysconfig.CACHE_TTL = 30.0`; worker `schedules` jobi 60 s, `integration_checks` jobi 10 s; probe tarmoq timeout'i 10 s; `running` holatidagi tekshiruv 5 daqiqadan keyin `failed`/`timeout`.
- Xato kodlari (ruscha matn `app/core/errors.py` `MESSAGES` da): `reason_required`, `step_up_required`, `step_up_failed`, `invalid_secret`, `insecure_smtp` (422, `params.fields`), `conflict_modified` (409).
- UI matnlari ruscha, faqat `t()` orqali (`src/i18n/ru.ts` oxiriga); reja prozasi va kod izohlari o'zbekcha. Hujjatlar `docs/security/*`, `docs/ops/*` — ruscha; backtick ichidagi har test nomi va yo'l mavjud bo'lishi shart (`backend/tests/ops/test_docs.py`).
- Credential fayllari (`deploy/secrets/`, `.env`, `secrets.php`, `auth.php`, `auth.js`, `apache-proxy.conf`, `gazna_bot/config.py`) ochilmaydi.
- Har commit xabari oxirida bo'sh qatordan keyin: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **Administrator SMTP manzilini begona serverga o'zgartiradi, parol esa saqlangan** — eski parol yangi manzilga yuborilmasligi kerak (panel siri o'chadi, env siri fallback bo'lmaydi): 5-vazifa `test_endpoint_change_clears_panel_secret`, `test_env_secret_not_used_once_endpoint_is_set_in_panel`.
2. **`core.settings` da pol ostidagi qiymat** (qo'lda yozilgan yoki reliz pol qattiqlashtirgan) — o'qishda standartga qaytadi, siyosat zaiflashmaydi: 1-vazifa `test_invalid_panel_value_falls_back`, 4-vazifa `test_weaker_panel_value_is_ignored`.
3. **Kirishda ishlatilgan TOTP kodi step-up'da qayta ishlatiladi** — rad etiladi va audit qilinadi: 3-vazifa `test_step_up_rejects_replayed_code`.
4. **Sir javobga, auditga yoki tekshiruv natijasiga sizadi** (probe istisnosi matnida parol bo'lishi mumkin) — faqat holat va xavfsiz kod: 5-vazifa `test_secret_is_encrypted_and_never_returned_or_audited`, 6-vazifa `test_probe_exception_text_is_not_stored`.
5. **Kesh yangilanayotganda DB ishlamayapti** — so'rovlar yiqilmaydi, oxirgi (yoki standart) qiymatlar ishlatiladi: 1-vazifa `test_value_keeps_last_snapshot_when_db_fails`, `test_value_defaults_when_db_down_without_snapshot`.

---

## Fayl tuzilishi

```
backend/app/core/sysconfig.py                 reyestr, manba ustuvorligi, kesh (1-vazifa)
backend/app/dwh/reference.py                  DEFAULT_SETTINGS/SETTING_TYPES/validate_setting/current_setting — taxalluslar
backend/migrations/versions/0008a_admin_settings.py   core.integration_credentials, core.integration_checks
backend/app/auth/permissions.py, seed.py      admin:security, admin:integrations; yangi ruxsat admin roliga bir marta
backend/app/core/reencrypt.py                 REGISTRY += core.integration_credentials.value_enc
backend/app/auth/stepup.py                    require_step_up (TOTP)
backend/app/auth/{service,sessions,context,passwords,schemas}.py, app/core/ratelimit.py   siyosat reyestrdan
backend/app/core/config.py                    5 ta siyosat maydoni olib tashlanadi
backend/app/admin/config_service.py, config_router.py, dwh_schemas.py   sozlamalar API v2
backend/app/core/integrations.py              IntegrationDef, SecretDef, sirlar ombori, RULES
backend/app/admin/integrations_service.py, integrations_router.py        integratsiyalar API
backend/app/etl/notify.py, app/etl/probes.py  jonli SMTP, smtp_probe, tekshiruv navbati
backend/app/worker.py, app/cli.py             add_cron_job, sync_schedules, integration_checks jobi
backend/app/etl/quality.py, app/etl/runner.py tolerances(), lookback reyestrdan
backend/app/ops.py                            ops.* chegaralari reyestrdan (4-reja moduli)
backend/app/audit/service.py, app/core/errors.py, app/main.py
backend/tests/helpers.py, conftest.py         put_setting/clear_setting, `setting` fixture
backend/tests/test_sysconfig.py, test_admin_settings_schema.py, test_settings_api.py,
  test_security_policy.py, test_integrations.py, test_notify_live.py, test_worker_schedules.py, test_ops_settings.py
frontend/src/api/{openapi.json→frontend/openapi.json, schema.d.ts, types.ts}
frontend/src/admin/{access.ts, registry.ts, api.ts, settingValue.ts, SettingsList.tsx, SettingsPage.tsx,
  SecurityPage.tsx, IntegrationsPage.tsx}
frontend/src/auth/{passwordRules.ts, PasswordChangePage.tsx}, src/i18n/ru.ts, src/test/fixtures.ts
frontend/src/admin/{settingValue.test.ts, settingsPage.test.tsx, integrations.test.tsx}
frontend/e2e/specs/admin-settings.spec.ts
docs/security/{access-control,secure-configuration,audit-log,asvs-l2,data-classification,key-management}.md,
  docs/ops/admin-guide.md, docs/superpowers/specs/2026-09-24-poydevor-design.md (7.6)
```

---

### Task 1: `sysconfig` reyestri — `SettingDef`, manba ustuvorligi, kesh; `reference.py` taxalluslari

**Files:**
- Create: `backend/app/core/sysconfig.py`
- Modify: `backend/app/dwh/reference.py` (sozlamalar qismi → taxalluslar; `ensure_reference` sozlamalarni seed qilmaydi), `backend/tests/helpers.py` (`put_setting`, `clear_setting`), `backend/tests/conftest.py` (`_fresh_sysconfig`, `setting`), `backend/tests/test_reference.py` (kalitlar to'plami)
- Test: `backend/tests/test_sysconfig.py`

**Interfaces:**
- Consumes: `get_settings`, `Settings`, `get_engine`, `Perm`, `today_tashkent`, `CronTrigger`.
- Produces:
  - `app.core.sysconfig`: `Kind`, `Apply`, `Source`, `CACHE_TTL = 30.0`, `EMAIL_RE`, `SettingDef` (`key, default, adapter, kind, category, title, perm=Perm.ADMIN_SETTINGS, guarded=False, apply="live", unit="", lo=None, hi=None, env=None, env_attr=None`; `.step_up -> bool`; `.validate(value) -> Any`, `ValueError`), `check_cron(value: str) -> str`, konstruktorlar `int_def`, `float_def`, `bool_def`, `cron_def`, `str_def`, `_DEFS: tuple[SettingDef, ...]`, `REGISTRY: dict[str, SettingDef]`, `resolve(d, panel: dict[str, Any]) -> tuple[Any, Source]`, `panel_rows(conn) -> dict[str, Any]`, `current(conn, key) -> Any` (keshsiz; noma'lum kalit — `KeyError`), `value(key) -> Any` (keshlangan), `invalidate() -> None`.
  - `app.dwh.reference`: `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `current_setting`, `_cron` — reyestrdan hosil bo'lgan taxalluslar (S1–S5 importlari buzilmaydi).
  - `tests.helpers`: `put_setting(key, value, *, invalidate=True) -> None` (tekshiruvsiz, API'siz), `clear_setting(key) -> None` (migrator bilan barcha versiyalarni o'chiradi). `tests.conftest`: autouse `_fresh_sysconfig`, fixture `setting(key, value)` (test oxirida tozalaydi).

- [ ] **Step 1: Test yordamchilari**

`backend/tests/helpers.py` — importlarga `import json`, `from sqlalchemy import text`, `from app.core import sysconfig`, `from app.core.db import get_engine` (yo'q bo'lsa) qo'shing va oxiriga:
```python
def put_setting(key: str, value: object, *, invalidate: bool = True) -> None:
    """Panel qiymati API'siz va TEKSHIRUVSIZ (yaroqsiz qiymat testlari ham shu bilan)."""
    with get_engine("app").begin() as conn:
        version = conn.execute(
            text("SELECT coalesce(max(version), 0) + 1 FROM core.settings WHERE key = :k"),
            {"k": key}).scalar_one()
        conn.execute(text("UPDATE core.settings SET is_current = false "
                          "WHERE key = :k AND is_current"), {"k": key})
        conn.execute(text("INSERT INTO core.settings (key, version, value) "
                          "VALUES (:k, :v, CAST(:val AS jsonb))"),
                     {"k": key, "v": version, "val": json.dumps(value)})
    if invalidate:
        sysconfig.invalidate()


def clear_setting(key: str) -> None:
    """Kalitning barcha versiyalari o'chadi — qiymat env/standartga qaytadi."""
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.settings WHERE key = :k"), {"k": key})
    sysconfig.invalidate()
```
`backend/tests/conftest.py` — importlarga `from app.core import sysconfig` va `from tests.helpers import clear_setting, put_setting` qo'shing, fixture'lar oxiriga:
```python
@pytest.fixture(autouse=True)
def _fresh_sysconfig() -> Iterator[None]:
    sysconfig.invalidate()
    yield
    sysconfig.invalidate()


@pytest.fixture
def setting() -> Iterator[Callable[[str, object], None]]:
    """Panel qiymatini yozadi; test oxirida tegilgan kalitlar standartga qaytariladi."""
    touched: list[str] = []

    def put(key: str, value: object) -> None:
        touched.append(key)
        put_setting(key, value)

    yield put
    for key in dict.fromkeys(touched):
        clear_setting(key)
```

- [ ] **Step 2: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_sysconfig.py`:
```python
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.auth.permissions import Perm
from app.core import sysconfig
from app.core.config import Settings
from app.core.db import get_engine
from app.dwh.reference import (
    DEFAULT_SETTINGS,
    current_setting,
    ensure_reference,
    validate_setting,
)
from tests.helpers import clear_setting, put_setting

Put = Callable[[str, object], None]

# docs/security da e'lon qilingan qiymat = eng zaif ruxsat etilgan chegara (spec 3.3).
WEAKEST: dict[str, tuple[str, int]] = {
    "security.session_idle_minutes": ("hi", 30),
    "security.session_absolute_hours": ("hi", 12),
    "security.password_max_age_days": ("hi", 90),
    "security.login_max_failures": ("hi", 5),
    "security.login_lockout_minutes": ("lo", 15),
    "security.password_min_length": ("lo", 12),
    "security.password_history": ("lo", 5),
    "ratelimit.login_per_min": ("hi", 10),
    "ratelimit.mfa_per_min": ("hi", 20),
    "ratelimit.api_per_min": ("hi", 300),
    "ratelimit.password_change_per_15min": ("hi", 5),
    "retention.audit_months": ("lo", 12),
    "retention.fact_years": ("lo", 5),
}


class _Broken:
    def connect(self) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("db down"))


def test_registry_is_consistent() -> None:
    keys = [d.key for d in sysconfig._DEFS]
    assert len(keys) == len(set(keys)) == len(sysconfig.REGISTRY)
    for d in sysconfig.REGISTRY.values():
        assert sysconfig.KEY_RE.fullmatch(d.key) and len(d.key) <= 64, d.key
        assert d.title and d.category, d.key
        assert d.validate(d.default) == d.default, d.key
        if d.kind in ("int", "float"):
            assert d.lo is not None and d.hi is not None and d.lo <= d.default <= d.hi, d.key
        if d.perm != Perm.ADMIN_SETTINGS:
            assert d.guarded and d.step_up, d.key


def test_env_defaults_match_settings_defaults() -> None:
    for d in sysconfig.REGISTRY.values():
        if d.env is not None and d.env_attr is None:
            default = Settings.model_fields[d.env].default
            assert (default.get_secret_value() if isinstance(default, SecretStr) else default) \
                == d.default, d.key
    assert sysconfig.REGISTRY["notify.email_to"].default == []


def test_security_bounds_are_tighten_only() -> None:
    for key, (side, bound) in WEAKEST.items():
        d = sysconfig.REGISTRY[key]
        assert getattr(d, side) == bound == d.default, key
        assert d.guarded and d.env is None, key
    for key in WEAKEST:
        if key.startswith(("security.", "ratelimit.")) or key == "retention.audit_months":
            assert sysconfig.REGISTRY[key].perm == Perm.ADMIN_SECURITY, key


def test_resolve_prefers_panel_then_env_then_default(monkeypatch: pytest.MonkeyPatch) -> None:
    d = sysconfig.REGISTRY["smtp.host"]
    monkeypatch.setattr(sysconfig, "get_settings", lambda: Settings(smtp_host="relay.uge.uz"))
    assert sysconfig.resolve(d, {}) == ("relay.uge.uz", "env")
    assert sysconfig.resolve(d, {"smtp.host": "mail.uge.uz"}) == ("mail.uge.uz", "panel")
    monkeypatch.setattr(sysconfig, "get_settings", lambda: Settings(smtp_host=""))
    assert sysconfig.resolve(d, {})[0] == ""
    to = sysconfig.REGISTRY["notify.email_to"]
    monkeypatch.setattr(sysconfig, "get_settings",
                        lambda: Settings(smtp_to="a@uge.uz, b@uge.uz"))
    assert sysconfig.resolve(to, {}) == (["a@uge.uz", "b@uge.uz"], "env")


def test_invalid_panel_value_falls_back() -> None:
    d = sysconfig.REGISTRY["security.session_idle_minutes"]
    assert sysconfig.resolve(d, {d.key: 45}) == (30, "default")
    assert sysconfig.resolve(d, {d.key: "10"}) == (30, "default")  # strict: satr emas
    assert sysconfig.resolve(d, {d.key: True}) == (30, "default")
    assert sysconfig.resolve(d, {d.key: 10}) == (10, "panel")


def test_current_reads_inside_transaction(setting: Put) -> None:
    setting("builds.keep", 4)
    with get_engine("app").connect() as conn:
        assert sysconfig.current(conn, "builds.keep") == 4
        assert current_setting(conn, "builds.keep") == 4
        assert sysconfig.current(conn, "freshness.max_age_hours") == 6
        with pytest.raises(KeyError):
            sysconfig.current(conn, "no.such")


def test_value_is_cached_until_invalidate() -> None:
    assert sysconfig.value("partitions.months_ahead") == 3
    try:
        put_setting("partitions.months_ahead", 5, invalidate=False)
        assert sysconfig.value("partitions.months_ahead") == 3  # kesh (≤ 30 s)
        sysconfig.invalidate()
        assert sysconfig.value("partitions.months_ahead") == 5
    finally:
        clear_setting("partitions.months_ahead")
    with pytest.raises(KeyError):
        sysconfig.value("no.such")


def test_value_keeps_last_snapshot_when_db_fails(
    setting: Put, monkeypatch: pytest.MonkeyPatch
) -> None:
    setting("builds.keep", 4)
    assert sysconfig.value("builds.keep") == 4
    monkeypatch.setattr(sysconfig, "get_engine", lambda role="app": _Broken())
    monkeypatch.setattr(sysconfig, "CACHE_TTL", 0.0)
    assert sysconfig.value("builds.keep") == 4


def test_value_defaults_when_db_down_without_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    sysconfig.invalidate()
    monkeypatch.setattr(sysconfig, "get_engine", lambda role="app": _Broken())
    assert sysconfig.value("security.session_idle_minutes") == 30


def test_reference_aliases_follow_registry() -> None:
    assert DEFAULT_SETTINGS == {k: d.default for k, d in sysconfig.REGISTRY.items()}
    assert validate_setting("builds.keep", 4) == 4
    with pytest.raises(ValueError):
        validate_setting("builds.keep", 11)
    with pytest.raises(KeyError):
        validate_setting("no.such", 1)


def test_ensure_reference_does_not_seed_settings() -> None:
    with get_engine("app").begin() as conn:
        ensure_reference(conn)
    with get_engine("app").connect() as conn:
        seeded = conn.execute(text(
            "SELECT count(*) FROM core.settings WHERE key LIKE 'security.%' "
            "OR key LIKE 'smtp.%'")).scalar_one()
    assert seeded == 0
```

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_sysconfig.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.sysconfig'`.

- [ ] **Step 4: `backend/app/core/sysconfig.py`**

```python
"""Tizim sozlamalari reyestri (spec 2026-10-26-admin-settings-design.md, 3–4-bo'limlar).

Har kalit — bitta `SettingDef`: tur va chegaralar (adapter), kategoriya, ruxsat, himoya.
Manba ustuvorligi: `core.settings` (panel) > env/Docker secret (faqat `env` bog'langan
kalitlar) > kod standarti. Har manbadagi qiymat bir xil adapter bilan tekshiriladi —
yaroqsiz bo'lsa keyingi manba olinadi (reliz pollarni qattiqlashtirsa, eski panel qiymati
ularni chetlab o'tolmaydi).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal

from apscheduler.triggers.cron import CronTrigger
from pydantic import AfterValidator, Field, SecretStr, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.logging import get_logger
from app.dwh.dates import today_tashkent

Kind = Literal["int", "float", "bool", "str", "cron", "date", "list", "json"]
Apply = Literal["live", "next_run"]
Source = Literal["panel", "env", "default"]
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
EMAIL_RE = r"^[^\s,<>@]+@[^\s,<>@]+\.[^\s,<>@]+$"  # app/core/config.py bilan bir xil
CACHE_TTL = 30.0  # s: boshqa jarayonlar (uvicorn worker'lari, worker) o'zgarishni shu muddatda ko'radi

log = get_logger("ugekazna.sysconfig")


@dataclass(frozen=True, slots=True)
class SettingDef:
    key: str
    default: Any
    adapter: TypeAdapter[Any]
    kind: Kind
    category: str
    title: str
    perm: Perm = Perm.ADMIN_SETTINGS
    guarded: bool = False  # sabab (reason) majburiy
    apply: Apply = "live"
    unit: str = ""
    lo: float | None = None
    hi: float | None = None
    env: str | None = None  # Settings maydoni: bootstrap qiymati, "env" manbai model_fields_set'dan
    env_attr: str | None = None  # qiymat boshqa atributdan olinsa (smtp_to → smtp_recipients)

    @property
    def step_up(self) -> bool:
        """Xavfsizlik va integratsiya kalitlari: sabab + joriy TOTP kodi (ASVS 3.7.1)."""
        return self.guarded and self.perm != Perm.ADMIN_SETTINGS

    def validate(self, value: Any) -> Any:
        try:
            return self.adapter.validate_python(value)
        except PydanticValidationError as exc:
            raise ValueError(f"{self.key}: noto'g'ri qiymat") from exc


def check_cron(value: str) -> str:
    # A4.2: aniq timezone="UTC" — tzlocal qidiruvisiz; worker TASHKENT bilan rejalashtiradi.
    CronTrigger.from_crontab(value, timezone="UTC")  # noto'g'ri bo'lsa ValueError
    return value


def _history_start(value: str) -> str:
    # M1: kelajak sanasi bo'sh oyna beradi; 2015 dan oldin ma'lumot yo'q.
    parsed = date.fromisoformat(value)
    if not date(2015, 1, 1) <= parsed <= today_tashkent():
        raise ValueError("etl.history_start: 2015-01-01 va bugun oralig'ida bo'lishi kerak")
    return parsed.isoformat()


def int_def(key: str, default: int, lo: int, hi: int, **kw: Any) -> SettingDef:
    adapter = TypeAdapter(Annotated[int, Field(strict=True, ge=lo, le=hi)])
    return SettingDef(key, default, adapter, "int", lo=lo, hi=hi, **kw)


def float_def(key: str, default: float, lo: float, hi: float, **kw: Any) -> SettingDef:
    adapter = TypeAdapter(Annotated[float, Field(strict=True, ge=lo, le=hi, allow_inf_nan=False)])
    return SettingDef(key, default, adapter, "float", lo=lo, hi=hi, **kw)


def bool_def(key: str, default: bool, **kw: Any) -> SettingDef:
    return SettingDef(key, default, TypeAdapter(Annotated[bool, Field(strict=True)]), "bool", **kw)


def cron_def(key: str, default: str, **kw: Any) -> SettingDef:
    adapter = TypeAdapter(Annotated[str, Field(strict=True, max_length=64),
                                    AfterValidator(check_cron)])
    return SettingDef(key, default, adapter, "cron", **kw)


def str_def(key: str, default: str, pattern: str, max_length: int, **kw: Any) -> SettingDef:
    adapter = TypeAdapter(Annotated[str, Field(strict=True, pattern=pattern,
                                               max_length=max_length)])
    return SettingDef(key, default, adapter, "str", **kw)


_SEC: dict[str, Any] = {"category": "security", "perm": Perm.ADMIN_SECURITY, "guarded": True}
_SMTP: dict[str, Any] = {"category": "integrations", "perm": Perm.ADMIN_INTEGRATIONS,
                         "guarded": True}
_EMAILS = TypeAdapter(Annotated[
    list[Annotated[str, Field(strict=True, pattern=EMAIL_RE, max_length=254)]],
    Field(max_length=20)])

_DEFS: tuple[SettingDef, ...] = (
    # Витрина va ETL (2-reja kalitlari — nomlar va chegaralar o'zgarmagan)
    int_def("freshness.max_age_hours", 6, 1, 168, category="data",
            title="Порог устаревания данных витрины", unit="ч"),
    SettingDef("etl.history_start", "2024-01-01",
               TypeAdapter(Annotated[str, AfterValidator(_history_start)]), "date",
               category="etl", title="Начало истории загрузки", apply="next_run"),
    cron_def("etl.synthetic_cron", "0 2 * * *", category="etl",
             title="Расписание синтетической загрузки (только dev)"),
    int_def("builds.keep", 3, 2, 10, category="data", title="Хранить сборок витрины",
            apply="next_run"),
    int_def("partitions.months_ahead", 3, 1, 12, category="data",
            title="Создавать партиции наперёд", unit="мес.", apply="next_run"),
    cron_def("maintenance.partitions_cron", "30 3 * * *", category="etl",
             title="Обслуживание партиций"),
    cron_def("maintenance.cleanup_cron", "0 4 * * *", category="etl",
             title="Очистка сеансов и промежуточных данных"),
    int_def("etl.incremental_lookback_days", 45, 7, 120, category="etl",
            title="Окно инкрементальной загрузки", unit="дн.", apply="next_run"),
    # Sifat va saqlash
    float_def("quality.control_tolerance", 0.001, 0.0, 0.01, category="quality",
              title="Допуск сверки контрольных сумм (доля)", guarded=True, apply="next_run"),
    float_def("quality.balance_tolerance", 0.01, 0.0, 1.0, category="quality",
              title="Допуск баланса остатков (доля оборота)", guarded=True, apply="next_run"),
    int_def("retention.fact_years", 5, 5, 10, category="retention",
            title="Хранение фактов витрины", unit="лет", guarded=True, apply="next_run"),
    int_def("retention.audit_months", 12, 12, 120, category="retention",
            title="Хранение журнала аудита", unit="мес.", perm=Perm.ADMIN_SECURITY,
            guarded=True, apply="next_run"),
    SettingDef("notify.email_to", [], _EMAILS, "list", category="notify",
               title="Получатели оповещений (e-mail)", guarded=True, env="smtp_to",
               env_attr="smtp_recipients"),
    # Xavfsizlik siyosati: zaif tomondagi chegara = hujjatlashtirilgan qiymat (faqat qattiqlashtirish)
    int_def("security.session_idle_minutes", 30, 5, 30, title="Завершение сеанса при бездействии",
            unit="мин", **_SEC),
    int_def("security.session_absolute_hours", 12, 1, 12, title="Максимальная длительность сеанса",
            unit="ч", **_SEC),
    int_def("security.password_max_age_days", 90, 30, 90, title="Срок действия пароля",
            unit="дн.", **_SEC),
    int_def("security.login_max_failures", 5, 3, 5,
            title="Неудачных попыток входа до блокировки", **_SEC),
    int_def("security.login_lockout_minutes", 15, 15, 1440, title="Длительность блокировки",
            unit="мин", **_SEC),
    int_def("security.password_min_length", 12, 12, 64, title="Минимальная длина пароля",
            unit="симв.", **_SEC),
    int_def("security.password_history", 5, 5, 24,
            title="Запрет повторного использования паролей", unit="посл.", **_SEC),
    int_def("ratelimit.login_per_min", 10, 3, 10, title="Попыток входа с одного IP в минуту",
            **_SEC),
    int_def("ratelimit.mfa_per_min", 20, 5, 20, title="Проверок кода 2FA с одного IP в минуту",
            **_SEC),
    int_def("ratelimit.api_per_min", 300, 60, 300,
            title="Запросов API одного пользователя в минуту", **_SEC),
    int_def("ratelimit.password_change_per_15min", 5, 1, 5,
            title="Попыток смены пароля за 15 минут", **_SEC),
    # SMTP (integratsiya maydonlari — faqat /admin/integrations orqali o'zgaradi)
    str_def("smtp.host", "", r"^[A-Za-z0-9.-]{0,253}$", 253, title="Сервер SMTP",
            env="smtp_host", **_SMTP),
    int_def("smtp.port", 25, 1, 65535, title="Порт", env="smtp_port", **_SMTP),
    str_def("smtp.from", "ugekazna@localhost", r"^[^\s,<>@]+@[^\s,<>@]+$", 254,
            title="Адрес отправителя", env="smtp_from", **_SMTP),
    str_def("smtp.user", "", r"^[\x21-\x7e]{0,128}$", 128, title="Учётная запись",
            env="smtp_user", **_SMTP),
    bool_def("smtp.starttls", True, title="STARTTLS", env="smtp_starttls", **_SMTP),
    bool_def("smtp.ssl", False, title="SSL/TLS (SMTPS)", env="smtp_ssl", **_SMTP),
)
REGISTRY: dict[str, SettingDef] = {d.key: d for d in _DEFS}


def _plain(value: Any) -> Any:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _try(d: SettingDef, raw: Any, source: Source) -> tuple[Any, Source] | None:
    try:
        return d.validate(raw), source
    except ValueError:
        log.error("setting_invalid", key=d.key, source=source)
        return None


def resolve(d: SettingDef, panel: dict[str, Any]) -> tuple[Any, Source]:
    if d.key in panel and (hit := _try(d, panel[d.key], "panel")) is not None:
        return hit
    if d.env is not None:
        settings = get_settings()
        source: Source = "env" if d.env in settings.model_fields_set else "default"
        if (hit := _try(d, _plain(getattr(settings, d.env_attr or d.env)), source)) is not None:
            return hit
    return d.default, "default"


def panel_rows(conn: Connection | Session) -> dict[str, Any]:
    rows = conn.execute(text("SELECT key, value FROM core.settings WHERE is_current")).all()
    return {r.key: r.value for r in rows if r.key in REGISTRY}


def current(conn: Connection | Session, key: str) -> Any:
    """Tranzaksiya ichida, keshsiz (ETL, worker joblari, CLI)."""
    d = REGISTRY[key]
    row = conn.execute(text("SELECT value FROM core.settings WHERE key = :k AND is_current"),
                       {"k": key}).first()
    return resolve(d, {} if row is None else {key: row.value})[0]


_lock = threading.Lock()
_cache: tuple[float, dict[str, Any]] | None = None


def _refresh(now: float) -> dict[str, Any]:
    global _cache
    try:
        with get_engine("app").connect() as conn:
            panel = panel_rows(conn)
    except SQLAlchemyError as exc:
        log.warning("settings_unavailable", error=type(exc).__name__)
        # Oxirgi qiymatlar (yoki hujjatlashtirilgan standartlar); TTL'dan keyin qayta urinadi.
        values = _cache[1] if _cache is not None else {
            k: resolve(d, {})[0] for k, d in REGISTRY.items()}
    else:
        values = {k: resolve(d, panel)[0] for k, d in REGISTRY.items()}
    _cache = (now, values)
    return values


def value(key: str) -> Any:
    """Keshlangan qiymat (≤ CACHE_TTL eskirgan) — har so'rovdagi issiq yo'l."""
    if key not in REGISTRY:
        raise KeyError(key)
    now = time.monotonic()
    cached = _cache
    if cached is not None and now - cached[0] < CACHE_TTL:
        return cached[1][key]
    with _lock:
        cached = _cache
        if cached is not None and now - cached[0] < CACHE_TTL:
            return cached[1][key]
        return _refresh(now)[key]


def invalidate() -> None:
    global _cache
    with _lock:
        _cache = None
```

- [ ] **Step 5: `backend/app/dwh/reference.py` — taxalluslar**

`_cron`, `_iso_date`, `_history_start`, `DEFAULT_SETTINGS`, `SETTING_TYPES`, `validate_setting`, `current_setting` ta'riflarini o'chiring (va endi ishlatilmaydigan `CronTrigger`, `AfterValidator`, `Field`, `TypeAdapter`, `PydanticValidationError`, `today_tashkent`, `Annotated` importlarini); modul boshidagi importlardan keyin qo'shing:
```python
from app.core.sysconfig import REGISTRY
from app.core.sysconfig import check_cron as _cron  # noqa: F401 -- S1–S5 rejalari shu nomni import qiladi
from app.core.sysconfig import current as current_setting  # noqa: F401 -- taxallus (freshness, runner, S1–S5)

# Taxalluslar: yagona manba — app/core/sysconfig.py reyestri (04b).
DEFAULT_SETTINGS: dict[str, Any] = {k: d.default for k, d in REGISTRY.items()}
SETTING_TYPES: dict[str, TypeAdapter[Any]] = {k: d.adapter for k, d in REGISTRY.items()}


def validate_setting(key: str, value: Any) -> Any:
    return REGISTRY[key].validate(value)  # noma'lum kalit → KeyError
```
(`TypeAdapter` importi shu taxallus uchun qoladi.) `ensure_reference` ichidagi `for key, value in DEFAULT_SETTINGS.items(): …` siklini o'chiring: sozlama qatori faqat panelda o'zgartirilganda paydo bo'ladi, aks holda env'dan ustun turib qolardi. Modul docstring'idagi «Seed … sozlamalar» jumlasini «alert qoidalari va допущения» deb tuzating.

`backend/tests/test_reference.py` — `test_settings_defaults_and_validation` oxiridagi `assert set(DEFAULT_SETTINGS) == {…}` ni almashtiring:
```python
    assert {
        "freshness.max_age_hours", "etl.history_start", "etl.synthetic_cron", "builds.keep",
        "retention.fact_years", "retention.audit_months", "partitions.months_ahead",
    } <= set(DEFAULT_SETTINGS)
```

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_sysconfig.py tests/test_reference.py tests/test_admin_dwh_api.py tests/test_config_lost_race.py tests/test_worker.py tests/test_etl_runner.py -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(config): sysconfig reyestri — tipli kalitlar, panel > env > standart, 30 s kesh

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Migratsiya `0008a`, yangi ruxsatlar va `reencrypt` reyestri

**Files:**
- Create: `backend/migrations/versions/0008a_admin_settings.py`
- Modify: `backend/app/auth/permissions.py` (`Perm`, `_PERM_TITLES`), `backend/app/auth/seed.py` (`sync_reference`), `backend/app/core/reencrypt.py` (`REGISTRY`)
- Test: `backend/tests/test_admin_settings_schema.py`

**Interfaces:**
- Consumes: `keystore.encrypt_str`, `Purpose.INTEGRATION`, `EncryptedColumn`, `ROLE_SEEDS`, `ADMIN_ROLE`, `PERMISSIONS`.
- Produces:
  - Jadvallar: `core.integration_credentials (name varchar(64) PK, value_enc bytea NOT NULL, updated_by bigint, updated_at timestamptz)`, `core.integration_checks (id bigserial PK, name varchar(32), requested_by bigint, requested_at, status pending|running|ok|failed, code varchar(32), finished_at)`.
  - Huquqlar: `ugk_app` — credentials `SELECT, INSERT, UPDATE, DELETE`, checks `SELECT, INSERT, UPDATE` + sequence; `ugk_etl` — credentials `SELECT`.
  - `Perm.ADMIN_SECURITY = "admin:security"`, `Perm.ADMIN_INTEGRATIONS = "admin:integrations"`.
  - `sync_reference`: kod ro'yxatiga YANGI qo'shilgan va admin seed roliga tegishli ruxsat mavjud admin roliga bir marta beriladi.
  - `reencrypt.REGISTRY += EncryptedColumn("core.integration_credentials", "name", "value_enc", Purpose.INTEGRATION, "app")`.

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_admin_settings_schema.py`:
```python
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.auth.models import Role, RolePermission
from app.auth.permissions import PERMISSIONS, Perm
from app.auth.seed import sync_reference
from app.core import keystore
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.reencrypt import REGISTRY
from app.etl.db import etl_transaction

AAD = "core.integration_credentials.value_enc:t.secret"


@pytest.fixture(autouse=True)
def _clean() -> None:
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials WHERE name LIKE 't.%'"))


def test_credentials_grants_and_ciphertext_check() -> None:
    blob = keystore.encrypt_str(Purpose.INTEGRATION, "pw", AAD)
    with get_engine("app").begin() as conn:
        conn.execute(text("INSERT INTO core.integration_credentials (name, value_enc) "
                          "VALUES ('t.secret', :b)"), {"b": blob})
        conn.execute(text("UPDATE core.integration_credentials SET updated_at = now() "
                          "WHERE name = 't.secret'"))
    with etl_transaction() as conn:
        assert conn.execute(text("SELECT count(*) FROM core.integration_credentials "
                                 "WHERE name = 't.secret'")).scalar_one() == 1
    with pytest.raises(ProgrammingError), etl_transaction() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials"))
    with pytest.raises(IntegrityError), get_engine("app").begin() as conn:
        conn.execute(text("INSERT INTO core.integration_credentials (name, value_enc) "
                          "VALUES ('t.short', '\\x01')"))


def test_checks_table_accepts_only_known_statuses() -> None:
    with get_engine("app").begin() as conn:
        row_id = conn.execute(text("INSERT INTO core.integration_checks (name, requested_by) "
                                   "VALUES ('smtp', 1) RETURNING id")).scalar_one()
        conn.execute(text("UPDATE core.integration_checks SET status = 'ok' WHERE id = :i"),
                     {"i": row_id})
    with pytest.raises(IntegrityError), get_engine("app").begin() as conn:
        conn.execute(text("UPDATE core.integration_checks SET status = 'weird' WHERE id = :i"),
                     {"i": row_id})


def test_credentials_column_is_reencrypted_by_app_role() -> None:
    col = next(c for c in REGISTRY if c.table == "core.integration_credentials")
    assert (col.pk, col.column, col.purpose, col.role) == (
        "name", "value_enc", Purpose.INTEGRATION, "app")
    assert col.aad("t.secret") == AAD


def test_new_permissions_have_titles() -> None:
    assert PERMISSIONS[Perm.ADMIN_SECURITY.value] == "Администрирование: политика безопасности"
    assert PERMISSIONS[Perm.ADMIN_INTEGRATIONS.value] == (
        "Администрирование: интеграции и учётные данные")


def _admin_has(s: Session, admin_id: int, code: str) -> bool:
    return s.execute(select(RolePermission).where(
        RolePermission.role_id == admin_id, RolePermission.permission_code == code)).first() \
        is not None


def test_new_permission_is_granted_to_admin_role_once() -> None:
    code = Perm.ADMIN_SECURITY.value
    with new_session() as s:
        admin_id = s.execute(select(Role.id).where(Role.code == "admin")).scalar_one()
    with get_engine("migrator").begin() as conn:  # "eski baza": ruxsat hali yo'q
        conn.execute(text("DELETE FROM core.permissions WHERE code = :c"), {"c": code})
    try:
        with new_session() as s:
            sync_reference(s)
            s.commit()
            assert _admin_has(s, admin_id, code)
            s.execute(delete(RolePermission).where(RolePermission.role_id == admin_id,
                                                   RolePermission.permission_code == code))
            s.commit()
            sync_reference(s)  # endi ruxsat mavjud — qayta berilmaydi
            s.commit()
            assert not _admin_has(s, admin_id, code)
    finally:
        with new_session() as s:
            if not _admin_has(s, admin_id, code):
                s.add(RolePermission(role_id=admin_id, permission_code=code))
                s.commit()
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_admin_settings_schema.py -v`
Expected: FAIL — `relation "core.integration_credentials" does not exist`, `AttributeError: ADMIN_SECURITY`.

- [ ] **Step 3: Migratsiya**

`backend/migrations/versions/0008a_admin_settings.py`:
```python
"""integratsiya hisob ma'lumotlari va ulanish tekshiruvlari (04b-reja)

Revision ID: 0008a
Revises: 0008
Create Date: 2026-10-26
"""

from alembic import op

revision = "0008a"
down_revision = "0008"
branch_labels = None
depends_on = None

STATEMENTS = [
    # Tarix saqlanmaydi: eski sir qatori qolmaydi; o'zgarish — audit (set/cleared).
    # value_enc ≥ 32 bayt: 15 bayt sarlavha+nonce + ≥ 1 bayt + 16 bayt tag (app/core/crypto.py).
    r"""
    CREATE TABLE core.integration_credentials (
      name varchar(64) PRIMARY KEY CHECK (name ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),
      value_enc bytea NOT NULL CHECK (octet_length(value_enc) >= 32),
      updated_by bigint,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE core.integration_checks (
      id bigserial PRIMARY KEY,
      name varchar(32) NOT NULL,
      requested_by bigint NOT NULL,
      requested_at timestamptz NOT NULL DEFAULT now(),
      status varchar(8) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ok', 'failed')),
      code varchar(32),
      finished_at timestamptz
    )
    """,
    "CREATE INDEX integration_checks_open_idx ON core.integration_checks (name, id) "
    "WHERE status IN ('pending', 'running')",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON core.integration_credentials TO ugk_app",
    "GRANT SELECT ON core.integration_credentials TO ugk_etl",
    "GRANT SELECT, INSERT, UPDATE ON core.integration_checks TO ugk_app",
    "GRANT USAGE ON SEQUENCE core.integration_checks_id_seq TO ugk_app",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE core.integration_checks")
    op.execute("DROP TABLE core.integration_credentials")
```

- [ ] **Step 4: Ruxsatlar, seed va reencrypt**

`backend/app/auth/permissions.py` — `Perm` ga `ADMIN_SECURITY = "admin:security"` va `ADMIN_INTEGRATIONS = "admin:integrations"` (`ADMIN_KEYS` dan keyin); `_PERM_TITLES` ga: `Perm.ADMIN_SECURITY: "Администрирование: политика безопасности"`, `Perm.ADMIN_INTEGRATIONS: "Администрирование: интеграции и учётные данные"`. `_PERM_TITLES[Perm.ADMIN_SETTINGS]` matni o'zgarmaydi.

`backend/app/auth/seed.py` — `sync_reference` boshida (advisory lock'dan keyin) `existing = set(db.execute(select(Permission.code)).scalars())`; `admin_id` olingandan keyin `ADMIN_GUARANTEED` sikli o'rniga:
```python
    admin_seed = next(s for s in ROLE_SEEDS if s.code == ADMIN_ROLE).permissions
    # Kodga yangi qo'shilgan admin ruxsati mavjud admin roliga BIR MARTA beriladi; keyin
    # olib tashlansa qayta qo'shilmaydi. Bo'sh bazada rol seed'i o'zi hammasini beradi.
    fresh = (set(PERMISSIONS) - existing) & admin_seed if existing else set()
    for perm in sorted(ADMIN_GUARANTEED | fresh):
        db.execute(
            pg_insert(RolePermission)
            .values(role_id=admin_id, permission_code=perm)
            .on_conflict_do_nothing()
        )
```
`backend/app/core/reencrypt.py` — `REGISTRY` oxiriga:
```python
    # 04b: integratsiya sirlari — admin API (ugk_app) yozadi, AAD tabiiy kalit (name) bo'yicha.
    EncryptedColumn("core.integration_credentials", "name", "value_enc", Purpose.INTEGRATION,
                    "app"),
```

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_admin_settings_schema.py tests/test_identity_seed.py tests/test_reencrypt_registry.py tests/test_keys_cli.py -v`
Expected: barcha testlar passed (`test_system_roles_match_spec` admin uchun barcha `Perm` qiymatlarini kutadi — yangi ikkitasi ham bor).

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(db): 0008a — integratsiya sirlari va tekshiruvlar jadvali; admin:security, admin:integrations

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Step-up (TOTP) va sozlamalar API v2 — metadata, kalit ruxsati, sabab, `expected_version`, tarix

**Files:**
- Create: `backend/app/auth/stepup.py`
- Modify: `backend/app/auth/service.py` (`_decrypt_secret` → `decrypt_totp_secret`, barcha chaqiruvlar), `backend/app/core/ratelimit.py` (`STEP_UP_PER_USER`), `backend/app/audit/service.py` (`STEP_UP_FAILED`), `backend/app/core/errors.py` (`MESSAGES`), `backend/app/admin/dwh_schemas.py` (`SettingOut`, `SettingUpdate`, `SettingVersionOut`), `backend/app/admin/config_service.py`, `backend/app/admin/config_router.py`, `backend/app/auth/context.py` (`require_perm` docstring), `backend/tests/test_route_guards.py` (`EXPECTED_ROUTES`, joy egalari)
- Test: `backend/tests/test_settings_api.py`

**Interfaces:**
- Consumes: `REGISTRY`, `SettingDef`, `resolve`, `invalidate` (1-vazifa), `Perm.ADMIN_SECURITY/ADMIN_INTEGRATIONS` (2-vazifa), `totp.verify`, `User`, `log_event`, `ratelimit.check`, `Limit`.
- Produces:
  - `app.auth.stepup.require_step_up(db: Session, actor: AuthContext, otp: str | None, meta: ClientMeta) -> None` — 422 `step_up_required`/`step_up_failed` (`fields=["otp"]`), muvaffaqiyatda `users.totp_last_step` yangilanadi (commit — chaqiruvchida).
  - `ratelimit.STEP_UP_PER_USER = Limit(events=5, window=900)`; `AuditAction.STEP_UP_FAILED = "auth.step_up.failed"`; `service.decrypt_totp_secret(user) -> str | None`.
  - `config_service`: `require_reason(reason: str | None) -> str`, `setting_out(db, key) -> SettingOut`, `list_settings(db, actor) -> list[SettingOut]`, `setting_history(db, actor, key) -> list[SettingVersionOut]`, `write_setting(db, key, normalized, user_id) -> tuple[int | None, Any]` (commit'siz; o'zgarmasa `(None, before)`; poyga → 409), `update_setting(db, actor, key, value, meta, *, expected_version=None, reason=None, otp=None) -> SettingOut`.
  - `SettingOut` += `default, source, category, title, kind, perm, guarded, step_up, apply, unit, lo, hi`; `SettingUpdate` += `expected_version: int | None (ge=0)`, `reason: str | None (≤ 500)`, `otp: str | None (≤ 8)`; `SettingVersionOut(version, value, updated_by, updated_at)`.
  - Marshrutlar: `GET /admin/settings`, `PUT /admin/settings/{key}`, `GET /admin/settings/{key}/history` — `require_perm(admin:settings, admin:security, admin:integrations, any_of=True)`, kalit ruxsati servisda; `category == "integrations"` kalitlari `PUT` da 404 (tarixi ochiq).

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_settings_api.py`:
```python
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.models import Role, RolePermission
from app.core.db import get_engine, new_session
from app.main import create_app
from tests.helpers import SeedUser, clear_setting, create_user, login

URL = "/api/v1/admin/settings"
IDLE = "security.session_idle_minutes"
REASON = "Письмо ИБ №7"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c


@pytest.fixture
def restore() -> Iterator[None]:
    yield
    for key in (IDLE, "builds.keep"):
        clear_setting(key)


def _role_user(*perms: str) -> SeedUser:
    code = f"r_{uuid.uuid4().hex[:8]}"
    with new_session() as s:
        role = Role(code=code, name=f"Тест {code}", scope_all=True, is_system=False)
        s.add(role)
        s.flush()
        for perm in perms:
            s.add(RolePermission(role_id=role.id, permission_code=perm))
        s.commit()
    return create_user(code)


def _last_audit(action: str, user_id: int) -> dict[str, Any]:
    with get_engine("app").connect() as conn:
        row = conn.execute(text("SELECT details, result FROM core.audit_log WHERE action = :a "
                                "AND user_id = :u ORDER BY id DESC LIMIT 1"),
                           {"a": action, "u": user_id}).one()
    return {"details": row.details, "result": row.result}


def _error(r: Any) -> dict[str, Any]:
    return dict(r.json()["error"])


def test_list_has_metadata_and_respects_permissions(client: TestClient) -> None:
    login(client, _role_user("admin:settings"))
    keys = {s["key"]: s for s in client.get(URL).json()}
    assert IDLE not in keys and "smtp.host" not in keys
    keep = keys["builds.keep"]
    assert (keep["kind"], keep["lo"], keep["hi"], keep["perm"], keep["apply"], keep["default"]) \
        == ("int", 2, 10, "admin:settings", "next_run", 3)
    assert keys["retention.fact_years"]["guarded"] is True
    assert keys["retention.fact_years"]["step_up"] is False


def test_security_admin_sees_only_security_keys(client: TestClient) -> None:
    login(client, _role_user("admin:security"))
    listed = client.get(URL).json()
    assert listed and {s["perm"] for s in listed} == {"admin:security"}
    idle = next(s for s in listed if s["key"] == IDLE)
    assert (idle["step_up"], idle["category"], idle["value"]) == (True, "security", 30)


def test_settings_admin_cannot_change_security_key(client: TestClient) -> None:
    user = _role_user("admin:settings")
    login(client, user)
    r = client.put(f"{URL}/{IDLE}", json={"value": 20, "reason": REASON, "otp": "123456"})
    assert r.status_code == 403
    assert _last_audit("security.access_denied", user.id)["result"] == "denied"


@pytest.mark.usefixtures("restore")
def test_guarded_key_needs_reason_and_fresh_totp(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    admin = make_user("admin")
    login(client, admin)
    path = f"{URL}/{IDLE}"
    assert _error(client.put(path, json={"value": 20}))["code"] == "reason_required"
    missing = _error(client.put(path, json={"value": 20, "reason": REASON}))
    assert (missing["code"], missing["params"]["fields"]) == ("step_up_required", ["otp"])
    bad = client.put(path, json={"value": 20, "reason": REASON, "otp": "12345"})
    assert bad.status_code == 422 and _error(bad)["code"] == "step_up_failed"
    assert _last_audit("auth.step_up.failed", admin.id)["result"] == "fail"
    ok = client.put(path, json={"value": 20, "reason": REASON, "otp": admin.next_code(),
                                "expected_version": 0})
    assert ok.status_code == 200, ok.text
    assert (ok.json()["value"], ok.json()["source"], ok.json()["version"]) == (20, "panel", 1)
    audit = _last_audit("admin.setting.updated", admin.id)["details"]
    assert (audit["before"], audit["after"], audit["reason"]) == (None, 20, REASON)


@pytest.mark.usefixtures("restore")
def test_step_up_rejects_replayed_code(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    admin = make_user("admin")
    login(client, admin)
    code = admin.next_code()
    path = f"{URL}/{IDLE}"
    assert client.put(path, json={"value": 25, "reason": REASON, "otp": code}).status_code == 200
    again = client.put(path, json={"value": 20, "reason": REASON, "otp": code})
    assert again.status_code == 422 and _error(again)["code"] == "step_up_failed"


@pytest.mark.usefixtures("restore")
def test_stale_expected_version_is_409(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    version = next(s for s in client.get(URL).json() if s["key"] == "builds.keep")["version"]
    path = f"{URL}/builds.keep"
    assert client.put(path, json={"value": 4, "expected_version": version}).status_code == 200
    stale = client.put(path, json={"value": 5, "expected_version": version})
    assert stale.status_code == 409 and _error(stale)["code"] == "conflict_modified"


def test_out_of_range_reports_bounds(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    r = client.put(f"{URL}/builds.keep", json={"value": 11})
    err = _error(r)
    assert r.status_code == 422 and err["code"] == "invalid_setting"
    assert (err["params"]["fields"], err["params"]["lo"], err["params"]["hi"]) == (["value"], 2, 10)


def test_integration_fields_are_not_edited_here_but_have_history(
    client: TestClient, make_user: Callable[..., SeedUser]
) -> None:
    login(client, make_user("admin"))
    assert client.put(f"{URL}/smtp.host", json={"value": "x"}).status_code == 404
    assert client.get(f"{URL}/smtp.host/history").json() == []
    assert client.get(f"{URL}/no.such/history").status_code == 404


def test_history_lists_versions_newest_first(
    client: TestClient, make_user: Callable[..., SeedUser],
    setting: Callable[[str, object], None],
) -> None:
    setting("builds.keep", 4)
    setting("builds.keep", 5)
    login(client, make_user("admin"))
    rows = client.get(f"{URL}/builds.keep/history").json()
    assert [r["value"] for r in rows[:2]] == [5, 4]
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_settings_api.py -v`
Expected: FAIL (`KeyError: 'kind'`, `reason_required` o'rniga 200 va h.k.).

- [ ] **Step 3: Step-up, rate limit, audit, xato matnlari**

`backend/app/auth/service.py` — `_decrypt_secret` ni `decrypt_totp_secret` deb qayta nomlang (barcha chaqiruvlar shu faylda).

`backend/app/core/ratelimit.py` — `AUDIT_VERIFY_GLOBAL` dan keyin: `STEP_UP_PER_USER = Limit(events=5, window=900)`.
`backend/app/audit/service.py` — `AuditAction` ga: `STEP_UP_FAILED = "auth.step_up.failed"`.
`backend/app/core/errors.py` — `MESSAGES` ga (`"internal_error"` dan oldin):
```python
    "reason_required": "Укажите причину изменения",
    "step_up_required": "Подтвердите изменение кодом из приложения",
    "step_up_failed": "Неверный код подтверждения",
    "invalid_secret": "Недопустимое значение учётных данных",
    "insecure_smtp": "Пароль SMTP передаётся только по защищённому соединению (STARTTLS или SSL)",
```
`backend/app/auth/stepup.py`:
```python
"""Sezgir sozlama o'zgarishlarini joriy TOTP kodi bilan tasdiqlash (ASVS 3.7.1, spec 3.7).

Zaxira kodi qabul qilinmaydi (bir martalik zaxira tiklash uchun); kirishda ishlatilgan qadam
qayta qabul qilinmaydi (`totp_last_step`). Commit — chaqiruvchida (o'zgarish bilan birga).
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, log_event
from app.auth import totp
from app.auth.context import AuthContext
from app.auth.models import User
from app.auth.service import decrypt_totp_secret
from app.core import ratelimit
from app.core.errors import ValidationFailed
from app.core.request_meta import ClientMeta


def require_step_up(db: Session, actor: AuthContext, otp: str | None, meta: ClientMeta) -> None:
    if not otp:
        raise ValidationFailed("step_up_required", fields=["otp"])
    ratelimit.check("step_up_user", str(actor.user_id), ratelimit.STEP_UP_PER_USER)
    user = db.execute(select(User).where(User.id == actor.user_id).with_for_update()).scalar_one()
    secret = decrypt_totp_secret(user)
    step = totp.verify(secret, otp, user.totp_last_step, time.time()) if secret else None
    if step is None:
        log_event(meta, AuditAction.STEP_UP_FAILED, user_id=actor.user_id, result="fail")
        raise ValidationFailed("step_up_failed", fields=["otp"])
    user.totp_last_step = step
```

- [ ] **Step 4: Sxemalar va servis**

`backend/app/admin/dwh_schemas.py` — `SettingOut` va `SettingUpdate` ni almashtiring, `SettingVersionOut` qo'shing (`Literal` importi):
```python
class SettingOut(BaseModel):
    key: str
    value: Any
    version: int
    updated_by: int | None
    updated_at: datetime | None
    default: Any
    source: Literal["panel", "env", "default"]
    category: str
    title: str
    kind: str
    perm: str
    guarded: bool
    step_up: bool
    apply: Literal["live", "next_run"]
    unit: str
    lo: float | None
    hi: float | None


class SettingUpdate(_In):
    value: Any
    expected_version: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=500)
    otp: str | None = Field(default=None, max_length=8)


class SettingVersionOut(BaseModel):
    version: int
    value: Any
    updated_by: int | None
    updated_at: datetime
```
`backend/app/admin/config_service.py` — `from app.dwh.reference import DEFAULT_SETTINGS, validate_setting` importini olib tashlang; qo'shing: `from app.auth.stepup import require_step_up`, `from app.core import sysconfig`, `from app.core.errors import ForbiddenError`, `from app.core.sysconfig import REGISTRY, SettingDef, resolve`, `SettingVersionOut`. `_setting_row` o'zgarmaydi; `list_settings` va `update_setting` ni quyidagilar bilan almashtiring:
```python
_ROW_COLS = "key, value, version, updated_by, updated_at"


def require_reason(reason: str | None) -> str:
    cleaned = " ".join((reason or "").split())
    if len(cleaned) < 5:
        raise ValidationFailed("reason_required", fields=["reason"])
    return cleaned


def _out(d: SettingDef, row: Any | None) -> SettingOut:
    value, source = resolve(d, {} if row is None else {d.key: row.value})
    return SettingOut(
        key=d.key, value=value, version=0 if row is None else row.version,
        updated_by=None if row is None else row.updated_by,
        updated_at=None if row is None else row.updated_at,
        default=resolve(d, {})[0], source=source, category=d.category, title=d.title,
        kind=d.kind, perm=d.perm.value, guarded=d.guarded, step_up=d.step_up, apply=d.apply,
        unit=d.unit, lo=d.lo, hi=d.hi)


def setting_out(db: Session, key: str) -> SettingOut:
    return _out(REGISTRY[key], _setting_row(db, key))


def list_settings(db: Session, actor: AuthContext) -> list[SettingOut]:
    rows = {r.key: r for r in db.execute(text(
        f"SELECT {_ROW_COLS} FROM core.settings WHERE is_current")).all()}
    return [_out(d, rows.get(d.key)) for d in REGISTRY.values()
            if d.category != "integrations" and actor.has(d.perm)]


def _readable(actor: AuthContext, key: str) -> SettingDef:
    d = REGISTRY.get(key)
    if d is None:
        raise NotFoundError()
    if not actor.has(d.perm):
        raise ForbiddenError()
    return d


def setting_history(db: Session, actor: AuthContext, key: str) -> list[SettingVersionOut]:
    _readable(actor, key)
    rows = db.execute(text("SELECT version, value, updated_by, updated_at FROM core.settings "
                           "WHERE key = :k ORDER BY version DESC LIMIT 100"), {"k": key}).all()
    return [SettingVersionOut(**dict(r._mapping)) for r in rows]


def write_setting(db: Session, key: str, normalized: Any,
                  user_id: int | None) -> tuple[int | None, Any]:
    """Yangi versiya (commit'siz). Qiymat o'zgarmasa (None, joriy). Parallel yozuv → 409."""
    row = _setting_row(db, key, lock=True)
    before = None if row is None else row.value
    if row is not None and row.value == normalized:
        return None, before
    version = 1 if row is None else row.version + 1
    try:
        with db.begin_nested():
            db.execute(text("UPDATE core.settings SET is_current = false WHERE key = :k "
                            "AND is_current"), {"k": key})
            db.execute(text("INSERT INTO core.settings (key, version, value, updated_by) "
                            "VALUES (:k, :v, CAST(:val AS jsonb), :u)"),
                       {"k": key, "v": version, "val": json.dumps(normalized), "u": user_id})
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != "23505":  # faqat unique buzilishi — poyga
            raise
        raise ConflictError("conflict_modified") from exc
    return version, before


def update_setting(db: Session, actor: AuthContext, key: str, value: Any, meta: ClientMeta, *,
                   expected_version: int | None = None, reason: str | None = None,
                   otp: str | None = None) -> SettingOut:
    d = REGISTRY.get(key)
    if d is None or d.category == "integrations":  # integratsiya maydoni — /admin/integrations
        raise NotFoundError()
    if not actor.has(d.perm):
        log_event(meta, AuditAction.ACCESS_DENIED, user_id=actor.user_id, result="denied",
                  details={"setting": key, "required": [d.perm.value]})
        raise ForbiddenError()
    try:
        normalized = d.validate(value)
    except ValueError as exc:
        raise ValidationFailed("invalid_setting", fields=["value"], key=key, lo=d.lo,
                               hi=d.hi) from exc
    cleaned = require_reason(reason) if d.guarded else None
    if d.step_up:  # qiymat tekshiruvidan keyin: xato yozuv kodni "yoqib" yubormasin
        require_step_up(db, actor, otp, meta)
    row = _setting_row(db, key, lock=True)
    if expected_version is not None and expected_version != (0 if row is None else row.version):
        raise ConflictError("conflict_modified")
    version, before = write_setting(db, key, normalized, actor.user_id)
    db.commit()  # commit-then-audit; step-up qadami ham saqlanadi
    if version is not None:
        details: dict[str, Any] = {"version": version, "before": before, "after": normalized}
        if cleaned:
            details["reason"] = cleaned
        log_event(meta, AuditAction.SETTING_UPDATED, user_id=actor.user_id,
                  object_type="setting", object_id=key, details=details)
        sysconfig.invalidate()
    return setting_out(db, key)
```

- [ ] **Step 5: Router va marshrut testlari**

`backend/app/admin/config_router.py` — `SettingVersionOut` importi va:
```python
SettingsReader = Annotated[AuthContext, Depends(require_perm(
    Perm.ADMIN_SETTINGS, Perm.ADMIN_SECURITY, Perm.ADMIN_INTEGRATIONS, any_of=True))]


@router.get("/settings")
def list_settings(ctx: SettingsReader, db: DB) -> list[SettingOut]:
    return service.list_settings(db, ctx)


@router.get("/settings/{key}/history")
def setting_history(key: str, ctx: SettingsReader, db: DB) -> list[SettingVersionOut]:
    return service.setting_history(db, ctx, key)


@router.put("/settings/{key}")
def update_setting(key: str, body: SettingUpdate, ctx: SettingsReader, db: DB,
                   meta: Meta) -> SettingOut:
    # Kalit ruxsati (d.perm) servisda tekshiriladi va rad etish auditga yoziladi.
    return service.update_setting(db, ctx, key, body.value, meta,
                                  expected_version=body.expected_version, reason=body.reason,
                                  otp=body.otp)
```
`backend/app/auth/context.py` — `require_perm` docstring'idagi «faqat o'qish uchun» o'rniga: «faqat o'qish uchun yoki servis obyekt ruxsatini o'zi tekshirsa (`PUT /admin/settings/{key}`)».
`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga `("GET", "/api/v1/admin/settings/{key}/history")` qo'shing.

- [ ] **Step 6: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_settings_api.py tests/test_admin_dwh_api.py tests/test_config_lost_race.py tests/test_route_guards.py tests/test_auth_api.py -v`
Expected: barcha testlar passed.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(admin): sozlamalar API v2 — metadata, kalit ruxsati, sabab, TOTP step-up, expected_version, tarix

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Xavfsizlik siyosati jonli — sessiya, bloklash, parol, rate limit

**Files:**
- Modify: `backend/app/core/config.py` (5 maydon olib tashlanadi), `backend/app/auth/sessions.py`, `backend/app/auth/context.py` (`build_context`, `get_ctx`), `backend/app/auth/service.py` (`login`, `_fail_attempt`, `change_password`, rate limit chaqiruvlari), `backend/app/auth/passwords.py`, `backend/app/core/ratelimit.py`, `backend/app/auth/schemas.py` (`MeOut`, `me_out`)
- Test: `backend/tests/test_security_policy.py`

**Interfaces:**
- Consumes: `sysconfig.value` (1-vazifa), `security.*`, `ratelimit.*` kalitlari.
- Produces:
  - `Settings` da endi yo'q: `session_idle_minutes`, `session_absolute_hours`, `password_max_age_days`, `login_max_failures`, `login_lockout_minutes` (env'da berilsa — e'tiborsiz, `extra="ignore"`).
  - `passwords.min_length() -> int`, `passwords.history_depth() -> int` (`MIN_LENGTH`, `HISTORY_DEPTH` konstantalari o'chadi).
  - `ratelimit.login_per_ip() -> Limit` (60 s), `mfa_per_ip() -> Limit` (60 s), `api_per_user() -> Limit` (60 s), `password_change_per_user() -> Limit` (900 s) — `LOGIN_PER_IP`, `MFA_PER_IP`, `API_PER_USER`, `PASSWORD_CHANGE_PER_USER` konstantalari o'rniga.
  - `MeOut.password_min_length: int`.

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_security_policy.py`:
```python
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import passwords, sessions
from app.auth.models import User, UserSession
from app.core import ratelimit, sysconfig
from app.core.config import Settings
from app.core.db import get_engine, new_session
from app.main import create_app
from tests.helpers import SeedUser, login

Put = Callable[[str, object], None]


def _client() -> TestClient:
    return TestClient(create_app(), base_url="https://testserver")


def test_session_timeouts_follow_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    setting("security.session_idle_minutes", 10)
    setting("security.session_absolute_hours", 2)
    user = make_user("admin")
    now = datetime.now(UTC)
    with new_session() as s:
        new = sessions.create(s, user.id, None, "pytest", now)
        row = s.get(UserSession, new.id)
        assert row is not None
        assert row.idle_expires_at == now + timedelta(minutes=10)
        assert row.absolute_expires_at == now + timedelta(hours=2)
        s.rollback()


def test_weaker_panel_value_is_ignored(setting: Put) -> None:
    setting("security.session_idle_minutes", 45)
    setting("security.login_max_failures", 50)
    assert sysconfig.value("security.session_idle_minutes") == 30
    assert sysconfig.value("security.login_max_failures") == 5


def test_lockout_follows_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    setting("security.login_max_failures", 3)
    setting("security.login_lockout_minutes", 60)
    user = make_user("admin")
    with _client() as client:
        for _ in range(3):
            r = client.post("/api/v1/auth/login",
                            json={"username": user.username, "password": "Wrong-Passw0rd!"})
            assert r.status_code == 401
    with new_session() as s:
        locked_until = s.get(User, user.id).locked_until  # type: ignore[union-attr]
    assert locked_until is not None
    assert locked_until - datetime.now(UTC) > timedelta(minutes=55)


def test_password_policy_follows_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    setting("security.password_min_length", 14)
    setting("security.password_history", 8)
    assert "password_too_short" in passwords.policy_problems("Qwz-Lmn-8472x", username="ivan")
    assert "password_too_short" not in passwords.policy_problems("Qwz-Lmn-8472xy",
                                                                 username="ivan")
    assert passwords.history_depth() == 8
    with _client() as client:
        login(client, make_user("admin"))
        assert client.get("/api/v1/auth/me").json()["password_min_length"] == 14


def test_password_max_age_follows_panel(setting: Put, make_user: Callable[..., SeedUser]) -> None:
    user = make_user("admin")
    with get_engine("app").begin() as conn:
        conn.execute(text("UPDATE core.users SET password_changed_at = now() - interval "
                          "'40 days' WHERE id = :i"), {"i": user.id})
    with _client() as client:
        login(client, user)
        assert client.get("/api/v1/auth/me").json()["must_change_password"] is False
        setting("security.password_max_age_days", 30)
        assert client.get("/api/v1/auth/me").json()["must_change_password"] is True


def test_login_rate_limit_follows_panel(setting: Put) -> None:
    setting("ratelimit.login_per_min", 3)
    assert ratelimit.login_per_ip() == ratelimit.Limit(events=3, window=60)
    with _client() as client:
        codes = [client.post("/api/v1/auth/login",
                             json={"username": "nobody_x", "password": "x"}).status_code
                 for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_removed_env_fields_are_ignored() -> None:
    settings = Settings(session_idle_minutes=120, login_max_failures=99)  # type: ignore[call-arg]
    assert not hasattr(settings, "session_idle_minutes")
    assert not hasattr(settings, "login_max_failures")
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_security_policy.py -v`
Expected: FAIL (idle 30 daqiqa, `AttributeError: login_per_ip`, `password_min_length` yo'q).

- [ ] **Step 3: Iste'molchilarni reyestrga o'tkazish**

- `backend/app/core/config.py`: `session_idle_minutes`, `session_absolute_hours`, `password_max_age_days`, `login_max_failures`, `login_lockout_minutes` maydonlarini o'chiring.
- `backend/app/auth/sessions.py`: `create` — `idle = timedelta(minutes=int(sysconfig.value("security.session_idle_minutes")))`, `default_absolute = now + timedelta(hours=int(sysconfig.value("security.session_absolute_hours")))`; `resolve` — `idle` xuddi shunday; `get_settings` importi ishlatilmasa olib tashlang.
- `backend/app/auth/context.py`: `build_context` — `max_age = timedelta(days=int(sysconfig.value("security.password_max_age_days")))`; `get_ctx` — `ratelimit.api_per_user()`.
- `backend/app/auth/service.py`: uchala bloklash joyida `settings.login_max_failures` → `int(sysconfig.value("security.login_max_failures"))`, `settings.login_lockout_minutes` → `int(sysconfig.value("security.login_lockout_minutes"))`; `ratelimit.LOGIN_PER_IP` → `ratelimit.login_per_ip()`, `ratelimit.MFA_PER_IP` → `ratelimit.mfa_per_ip()` (3 joy), `ratelimit.PASSWORD_CHANGE_PER_USER` → `ratelimit.password_change_per_user()`, `passwords.HISTORY_DEPTH` → `passwords.history_depth()` (2 joy); ishlatilmay qolgan `settings = get_settings()` qatorlarini o'chiring.
- `backend/app/auth/passwords.py`: `MIN_LENGTH`, `HISTORY_DEPTH` o'rniga:
```python
def min_length() -> int:
    return int(sysconfig.value("security.password_min_length"))


def history_depth() -> int:
    """Joriy parol + oldingilari: oxirgi N tasi qayta ishlatilmaydi."""
    return int(sysconfig.value("security.password_history"))
```
  `policy_problems`: `if len(password) < min_length():`.
- `backend/app/core/ratelimit.py`: to'rtta konstantani o'chirib:
```python
def _per(key: str, window: int) -> Limit:
    return Limit(events=int(sysconfig.value(key)), window=window)


def login_per_ip() -> Limit:
    return _per("ratelimit.login_per_min", 60)


def mfa_per_ip() -> Limit:
    return _per("ratelimit.mfa_per_min", 60)


def api_per_user() -> Limit:
    return _per("ratelimit.api_per_min", 60)


def password_change_per_user() -> Limit:
    return _per("ratelimit.password_change_per_15min", 900)
```
- `backend/app/auth/schemas.py`: `MeOut` ga `password_min_length: int`; `me_out` da `password_min_length=passwords.min_length()` (`from app.auth import passwords`).

`grep -rn "LOGIN_PER_IP\|MFA_PER_IP\|API_PER_USER\|PASSWORD_CHANGE_PER_USER\|MIN_LENGTH\|HISTORY_DEPTH\|session_idle_minutes\|login_max_failures\|login_lockout_minutes\|password_max_age_days\|session_absolute_hours" backend/app backend/tests` — qolgan har bir moslikni (izohlardan tashqari) yuqoridagi funksiyalarga almashtiring.

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_security_policy.py tests/test_auth_api.py tests/test_auth_concurrency.py tests/test_passwords.py tests/test_ratelimit.py tests/test_context.py tests/test_config.py -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(auth): sessiya, bloklash, parol va rate limit siyosati paneldan (faqat qattiqlashtirish)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Integratsiyalar yadrosi — reyestr, shifrlangan sirlar, manzilga bog'langan sir, API

**Files:**
- Create: `backend/app/core/integrations.py`, `backend/app/admin/integrations_service.py`, `backend/app/admin/integrations_router.py`
- Modify: `backend/app/admin/dwh_schemas.py`, `backend/app/audit/service.py` (`INTEGRATION_UPDATED`, `INTEGRATION_CHECK_REQUESTED`), `backend/app/main.py` (router), `backend/tests/test_route_guards.py` (`EXPECTED_ROUTES`, `{name}`/`{check_id}` almashtirish)
- Test: `backend/tests/test_integrations.py`

**Interfaces:**
- Consumes: `sysconfig.current`, `REGISTRY`, `invalidate`; `keystore.encrypt_str/decrypt_str`, `Purpose.INTEGRATION`; `config_service.write_setting`, `setting_out`, `require_reason` (3-vazifa); `require_step_up`; jadvallar (2-vazifa).
- Produces:
  - `app.core.integrations`: `SecretDef(name, title, env=None, pattern=None, max_length=4096)` + `.validate(plain) -> str` (`ValueError`), `IntegrationDef(name, title, fields, endpoint, secrets, check_in="worker")`, `INTEGRATIONS`, `SECRETS: dict[str, tuple[IntegrationDef, SecretDef]]`, `RULES: dict[str, Callable[[Connection], tuple[str, str] | None]]`, `SecretState = Literal["panel", "env", "none"]`, `secret_aad(name) -> str`, `secret(conn, name) -> str` ("" — yo'q), `secret_state(conn, name) -> tuple[SecretState, datetime | None, int | None]`, `store_secret(conn, name, plain, user_id) -> None`, `clear_secret(conn, name) -> bool`, `field_values(conn, name) -> dict[str, Any]`.
  - Sxemalar: `SecretStatusOut(name, title, state, updated_at, updated_by)`, `IntegrationCheckOut(id, name, status, code, requested_at, finished_at)`, `IntegrationOut(name, title, check_in, endpoint: list[str], fields: list[SettingOut], secrets: list[SecretStatusOut], last_check: IntegrationCheckOut | None)`, `IntegrationUpdate(values: dict[str, Any], secrets: dict[str, str | None], reason: str | None, otp: str | None)` (bo'shliqlar kesilmaydi).
  - Servis: `list_integrations(db) -> list[IntegrationOut]`, `get_integration(db, name) -> IntegrationOut`, `update_integration(db, actor, name, body, meta) -> IntegrationOut`, `request_check(db, actor, name, meta) -> IntegrationCheckOut`, `get_check(db, check_id) -> IntegrationCheckOut`.
  - Marshrutlar (`admin:integrations`): `GET /admin/integrations`, `PUT /admin/integrations/{name}`, `POST /admin/integrations/{name}/check` (202), `GET /admin/integrations/checks/{check_id}`.
  - Audit: `admin.integration.updated` (`changes[{key, before, after, version}]`, `secrets[{name, action}]`, `reason`), `admin.integration.check_requested`.

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_integrations.py`:
```python
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from app.admin import integrations_service as svc
from app.admin.dwh_schemas import IntegrationOut, IntegrationUpdate
from app.auth.context import AuthContext
from app.auth.permissions import PERMISSIONS
from app.core import integrations, keystore, sysconfig
from app.core.config import Settings
from app.core.crypto import Purpose
from app.core.db import get_engine, new_session
from app.core.errors import ValidationFailed
from app.core.request_meta import ClientMeta
from app.main import create_app
from tests.helpers import SeedUser, clear_setting, login

META = ClientMeta(ip=None, ua=None, request_id=None)
PLAIN = "Relay-Pa55word!"
API = "/api/v1/admin/integrations"


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials"))
        conn.execute(text("DELETE FROM core.integration_checks"))
    for key in integrations.INTEGRATIONS["smtp"].fields:
        clear_setting(key)


@pytest.fixture
def actor(make_user: Callable[..., SeedUser]) -> AuthContext:
    user = make_user("admin")
    return AuthContext(user_id=user.id, username=user.username, full_name="A",
                       role_code="admin", permissions=frozenset(PERMISSIONS), branch_ids=None,
                       session_id=uuid.uuid4())


@pytest.fixture
def no_step_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step-up 3-vazifada tekshirilgan; bu yerda sir mantig'i."""
    monkeypatch.setattr(svc, "require_step_up", lambda *args, **kwargs: None)


def _update(actor: AuthContext, **body: Any) -> IntegrationOut:
    with new_session() as s:
        return svc.update_integration(
            s, actor, "smtp", IntegrationUpdate(reason="Заявка ИТ-42", otp="000000", **body), META)


def _state(out: IntegrationOut) -> str:
    return next(s.state for s in out.secrets if s.name == "smtp.password")


def _audit() -> dict[str, Any]:
    with get_engine("app").connect() as conn:
        return dict(conn.execute(text(
            "SELECT details FROM core.audit_log WHERE action = 'admin.integration.updated' "
            "ORDER BY id DESC LIMIT 1")).scalar_one())


@pytest.mark.usefixtures("no_step_up")
def test_secret_is_encrypted_and_never_returned_or_audited(actor: AuthContext) -> None:
    out = _update(actor, values={"smtp.host": "relay.uge.uz", "smtp.port": 587},
                  secrets={"smtp.password": PLAIN})
    assert PLAIN not in out.model_dump_json() and _state(out) == "panel"
    with get_engine("app").connect() as conn:
        blob = conn.execute(text("SELECT value_enc FROM core.integration_credentials "
                                 "WHERE name = 'smtp.password'")).scalar_one()
        assert PLAIN.encode() not in bytes(blob)
        assert keystore.decrypt_str(Purpose.INTEGRATION, blob,
                                    "core.integration_credentials.value_enc:smtp.password") == PLAIN
        assert integrations.secret(conn, "smtp.password") == PLAIN
    details = _audit()
    assert PLAIN not in json.dumps(details, ensure_ascii=False)
    assert details["secrets"] == [{"name": "smtp.password", "action": "set"}]
    assert details["reason"] == "Заявка ИТ-42"
    assert {c["key"] for c in details["changes"]} == {"smtp.host", "smtp.port"}


@pytest.mark.usefixtures("no_step_up")
def test_endpoint_change_clears_panel_secret(actor: AuthContext) -> None:
    _update(actor, values={"smtp.host": "relay.uge.uz"}, secrets={"smtp.password": PLAIN})
    out = _update(actor, values={"smtp.host": "mail.evil.example"})
    assert _state(out) == "none"
    assert _audit()["secrets"] == [{"name": "smtp.password", "action": "cleared_endpoint_changed"}]
    kept = _update(actor, values={"smtp.host": "relay.uge.uz"}, secrets={"smtp.password": PLAIN})
    assert _state(_update(actor, values={"smtp.user": "ugk"})) == _state(kept) == "panel"


@pytest.mark.usefixtures("no_step_up")
def test_env_secret_not_used_once_endpoint_is_set_in_panel(
    actor: AuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(integrations, "get_settings",
                        lambda: Settings(smtp_password=SecretStr("env-secret")))
    with get_engine("app").connect() as conn:
        assert integrations.secret(conn, "smtp.password") == "env-secret"
        assert integrations.secret_state(conn, "smtp.password")[0] == "env"
    _update(actor, values={"smtp.host": "relay.uge.uz"})
    with get_engine("app").connect() as conn:
        assert integrations.secret(conn, "smtp.password") == ""
        assert integrations.secret_state(conn, "smtp.password")[0] == "none"


@pytest.mark.usefixtures("no_step_up")
def test_password_without_tls_is_rejected_and_rolled_back(actor: AuthContext) -> None:
    with pytest.raises(ValidationFailed) as exc:
        _update(actor, values={"smtp.host": "relay.uge.uz", "smtp.starttls": False,
                               "smtp.ssl": False}, secrets={"smtp.password": PLAIN})
    assert (exc.value.code, exc.value.params["fields"]) == ("insecure_smtp", ["smtp.starttls"])
    with get_engine("app").connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM core.integration_credentials")) \
            .scalar_one() == 0
        assert sysconfig.current(conn, "smtp.host") == ""


@pytest.mark.usefixtures("no_step_up")
@pytest.mark.parametrize(("body", "field"), [
    ({"values": {"smtp.port": 0}}, "smtp.port"),
    ({"values": {"builds.keep": 3}}, "builds.keep"),
    ({"secrets": {"smtp.password": "a\r\nb"}}, "smtp.password"),
    ({"secrets": {"onec.password": "x"}}, "onec.password"),
])
def test_bad_values_and_unknown_names_are_422(
    actor: AuthContext, body: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValidationFailed) as exc:
        _update(actor, **body)
    assert exc.value.params["fields"] == [field]


def test_missing_reason_is_422_before_step_up(actor: AuthContext) -> None:
    with pytest.raises(ValidationFailed) as exc, new_session() as s:
        svc.update_integration(s, actor, "smtp",
                               IntegrationUpdate(values={"smtp.port": 587}), META)
    assert exc.value.code == "reason_required"


def test_check_request_is_deduplicated(actor: AuthContext) -> None:
    with new_session() as s:
        first = svc.request_check(s, actor, "smtp", META)
        second = svc.request_check(s, actor, "smtp", META)
    assert first.id == second.id and first.status == "pending"


def test_http_flow_requires_permission_and_totp(make_user: Callable[..., SeedUser]) -> None:
    admin = make_user("admin")
    with TestClient(create_app(), base_url="https://testserver") as client:
        login(client, admin)
        listed = client.get(API).json()
        assert [i["name"] for i in listed] == ["smtp"]
        assert listed[0]["endpoint"] == ["smtp.host", "smtp.port"]
        body = {"values": {"smtp.host": "relay.uge.uz"}, "secrets": {"smtp.password": PLAIN},
                "reason": "Заявка ИТ-42"}
        assert client.put(f"{API}/smtp", json=body).json()["error"]["code"] == "step_up_required"
        r = client.put(f"{API}/smtp", json={**body, "otp": admin.next_code()})
        assert r.status_code == 200, r.text
        assert PLAIN not in r.text
        check = client.post(f"{API}/smtp/check")
        assert check.status_code == 202
        assert client.get(f"{API}/checks/{check.json()['id']}").json()["status"] == "pending"
        assert client.put(f"{API}/nope", json=body).status_code == 404
    with TestClient(create_app(), base_url="https://testserver") as other:
        login(other, make_user("rukovodstvo"))
        assert other.get(API).status_code == 403
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_integrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.admin.integrations_service'`.

- [ ] **Step 3: `backend/app/core/integrations.py`**

```python
"""Integratsiyalar reyestri va sirlar ombori (spec 2026-10-26, 3.5–3.6, 4.2).

Sir faqat ishlatish joyida ochiladi (`secret`) va API/log/audit'ga chiqmaydi. Manzil kaliti
panelda qayta belgilangan bo'lsa env'dagi sir fallback bo'lmaydi — hisob ma'lumotini boshqa
serverga yo'naltirib bo'lmaydi (credential redirect).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core import keystore, sysconfig
from app.core.config import get_settings
from app.core.crypto import Purpose

SecretState = Literal["panel", "env", "none"]
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class SecretDef:
    name: str
    title: str
    env: str | None = None  # Settings SecretStr maydoni — bootstrap
    pattern: str | None = None
    max_length: int = 4096

    def validate(self, plain: str) -> str:
        if (not plain or len(plain) > self.max_length or _CONTROL.search(plain)
                or (self.pattern is not None and not re.fullmatch(self.pattern, plain))):
            raise ValueError(f"{self.name}: yaroqsiz qiymat")
        return plain


@dataclass(frozen=True, slots=True)
class IntegrationDef:
    name: str
    title: str
    fields: tuple[str, ...]  # sysconfig kalitlari (category="integrations")
    endpoint: tuple[str, ...]  # o'zgarsa sirlar tozalanadi
    secrets: tuple[SecretDef, ...]
    check_in: Literal["worker", "api"] = "worker"  # probe qayerda (egress bor joyda)


_ALL: tuple[IntegrationDef, ...] = (
    IntegrationDef(
        "smtp", "Почтовый сервер (SMTP)",
        fields=("smtp.host", "smtp.port", "smtp.from", "smtp.user", "smtp.starttls", "smtp.ssl"),
        endpoint=("smtp.host", "smtp.port"),
        secrets=(SecretDef("smtp.password", "Пароль SMTP", env="smtp_password"),)),
)
INTEGRATIONS: dict[str, IntegrationDef] = {i.name: i for i in _ALL}
SECRETS: dict[str, tuple[IntegrationDef, SecretDef]] = {
    s.name: (i, s) for i in _ALL for s in i.secrets}


def secret_aad(name: str) -> str:
    return f"core.integration_credentials.value_enc:{name}"  # = reencrypt EncryptedColumn.aad


def _env_secret(sd: SecretDef) -> str:
    if sd.env is None:
        return ""
    raw = getattr(get_settings(), sd.env)
    return raw.get_secret_value() if isinstance(raw, SecretStr) else str(raw)


def _endpoint_overridden(conn: Connection, integ: IntegrationDef) -> bool:
    return conn.execute(text("SELECT 1 FROM core.settings WHERE is_current AND key = ANY(:k) "
                             "LIMIT 1"), {"k": list(integ.endpoint)}).first() is not None


def _row(conn: Connection, name: str) -> Any:
    return conn.execute(text("SELECT value_enc, updated_at, updated_by FROM "
                             "core.integration_credentials WHERE name = :n"), {"n": name}).first()


def secret(conn: Connection, name: str) -> str:
    """Ochiq sir — faqat konnektor/notifier ichida ishlatiladi."""
    integ, sd = SECRETS[name]
    row = _row(conn, name)
    if row is not None:
        return keystore.decrypt_str(Purpose.INTEGRATION, row.value_enc, secret_aad(name))
    return "" if _endpoint_overridden(conn, integ) else _env_secret(sd)


def secret_state(conn: Connection, name: str) -> tuple[SecretState, datetime | None, int | None]:
    integ, sd = SECRETS[name]
    row = _row(conn, name)
    if row is not None:
        return "panel", row.updated_at, row.updated_by
    if _env_secret(sd) and not _endpoint_overridden(conn, integ):
        return "env", None, None
    return "none", None, None


def store_secret(conn: Connection, name: str, plain: str, user_id: int | None) -> None:
    _integ, sd = SECRETS[name]
    blob = keystore.encrypt_str(Purpose.INTEGRATION, sd.validate(plain), secret_aad(name))
    conn.execute(text(
        "INSERT INTO core.integration_credentials (name, value_enc, updated_by) "
        "VALUES (:n, :b, :u) ON CONFLICT (name) DO UPDATE SET value_enc = EXCLUDED.value_enc, "
        "updated_by = EXCLUDED.updated_by, updated_at = now()"),
        {"n": name, "b": blob, "u": user_id})


def clear_secret(conn: Connection, name: str) -> bool:
    return conn.execute(text("DELETE FROM core.integration_credentials WHERE name = :n "
                             "RETURNING name"), {"n": name}).first() is not None


def field_values(conn: Connection, name: str) -> dict[str, Any]:
    return {key: sysconfig.current(conn, key) for key in INTEGRATIONS[name].fields}


def _smtp_rule(conn: Connection) -> tuple[str, str] | None:
    tls = bool(sysconfig.current(conn, "smtp.starttls")) or bool(sysconfig.current(conn, "smtp.ssl"))
    return None if tls or not secret(conn, "smtp.password") else ("insecure_smtp", "smtp.starttls")


# Integratsiya darajasidagi tekshiruv: (xato kodi, maydon) yoki None. Saqlashdan oldin, shu
# tranzaksiyada (yangi qiymatlar bilan) chaqiriladi.
RULES: dict[str, Callable[[Connection], tuple[str, str] | None]] = {"smtp": _smtp_rule}
```

- [ ] **Step 4: Sxemalar, servis, router**

`backend/app/admin/dwh_schemas.py` — `ConfigDict` importi va oxiriga:
```python
class SecretStatusOut(BaseModel):
    name: str
    title: str
    state: Literal["panel", "env", "none"]
    updated_at: datetime | None
    updated_by: int | None


class IntegrationCheckOut(BaseModel):
    id: int
    name: str
    status: Literal["pending", "running", "ok", "failed"]
    code: str | None
    requested_at: datetime
    finished_at: datetime | None


class IntegrationOut(BaseModel):
    name: str
    title: str
    check_in: Literal["worker", "api"]
    endpoint: list[str]
    fields: list[SettingOut]
    secrets: list[SecretStatusOut]
    last_check: IntegrationCheckOut | None


class IntegrationUpdate(BaseModel):
    # _In emas: str_strip_whitespace sir qiymatini jimgina o'zgartirib yuborardi.
    model_config = ConfigDict(extra="forbid")
    values: dict[str, Any] = Field(default_factory=dict, max_length=20)
    secrets: dict[str, str | None] = Field(default_factory=dict, max_length=10)  # None — o'chirish
    reason: str | None = Field(default=None, max_length=500)
    otp: str | None = Field(default=None, max_length=8)
```
`backend/app/audit/service.py` — `AuditAction` ga: `INTEGRATION_UPDATED = "admin.integration.updated"`, `INTEGRATION_CHECK_REQUESTED = "admin.integration.check_requested"`.

`backend/app/admin/integrations_service.py`:
```python
"""Integratsiyalar: maydonlar (versiyali sozlamalar), sirlar (write-only), tekshiruv navbati."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin.config_service import require_reason, setting_out, write_setting
from app.admin.dwh_schemas import (
    IntegrationCheckOut,
    IntegrationOut,
    IntegrationUpdate,
    SecretStatusOut,
)
from app.audit.service import AuditAction, log_event
from app.auth.context import AuthContext
from app.auth.stepup import require_step_up
from app.core import sysconfig
from app.core.errors import NotFoundError, ValidationFailed
from app.core.integrations import (
    INTEGRATIONS,
    RULES,
    IntegrationDef,
    clear_secret,
    secret_state,
    store_secret,
)
from app.core.request_meta import ClientMeta
from app.core.sysconfig import REGISTRY

_CHECK_COLS = "id, name, status, code, requested_at, finished_at"


def _integration(name: str) -> IntegrationDef:
    integ = INTEGRATIONS.get(name)
    if integ is None:
        raise NotFoundError()
    return integ


def _last_check(db: Session, name: str) -> IntegrationCheckOut | None:
    row = db.execute(text(f"SELECT {_CHECK_COLS} FROM core.integration_checks WHERE name = :n "
                          "ORDER BY id DESC LIMIT 1"), {"n": name}).first()
    return None if row is None else IntegrationCheckOut(**dict(row._mapping))


def get_integration(db: Session, name: str) -> IntegrationOut:
    integ = _integration(name)
    conn = db.connection()
    secrets = []
    for sd in integ.secrets:
        state, at, by = secret_state(conn, sd.name)
        secrets.append(SecretStatusOut(name=sd.name, title=sd.title, state=state, updated_at=at,
                                       updated_by=by))
    return IntegrationOut(name=integ.name, title=integ.title, check_in=integ.check_in,
                          endpoint=list(integ.endpoint),
                          fields=[setting_out(db, key) for key in integ.fields],
                          secrets=secrets, last_check=_last_check(db, name))


def list_integrations(db: Session) -> list[IntegrationOut]:
    return [get_integration(db, name) for name in INTEGRATIONS]


def update_integration(db: Session, actor: AuthContext, name: str, body: IntegrationUpdate,
                       meta: ClientMeta) -> IntegrationOut:
    integ = _integration(name)
    secret_defs = {sd.name: sd for sd in integ.secrets}
    unknown = sorted((set(body.values) - set(integ.fields)) | (set(body.secrets) - set(secret_defs)))
    if unknown:
        raise ValidationFailed("validation_failed", fields=unknown)
    normalized: dict[str, Any] = {}
    for key, raw in sorted(body.values.items()):
        try:
            normalized[key] = REGISTRY[key].validate(raw)
        except ValueError as exc:
            d = REGISTRY[key]
            raise ValidationFailed("invalid_setting", fields=[key], key=key, lo=d.lo,
                                   hi=d.hi) from exc
    for sname, plain in body.secrets.items():
        try:
            if plain is not None:
                secret_defs[sname].validate(plain)
        except ValueError as exc:
            raise ValidationFailed("invalid_secret", fields=[sname]) from exc
    reason = require_reason(body.reason)
    if not normalized and not body.secrets:
        return get_integration(db, name)
    require_step_up(db, actor, body.otp, meta)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_integration_' || :n))"),
               {"n": name})
    changes: list[dict[str, Any]] = []
    for key, new in normalized.items():
        version, before = write_setting(db, key, new, actor.user_id)
        if version is not None:
            changes.append({"key": key, "before": before, "after": new, "version": version})
    endpoint_changed = any(c["key"] in integ.endpoint for c in changes)
    conn = db.connection()
    actions: list[dict[str, str]] = []  # ro'yxat: kalit nomi ("smtp.password") audit maskasiga tushmasin
    for sd in integ.secrets:
        if sd.name in body.secrets:
            plain = body.secrets[sd.name]
            if plain is None:
                if clear_secret(conn, sd.name):
                    actions.append({"name": sd.name, "action": "cleared"})
            else:
                store_secret(conn, sd.name, plain, actor.user_id)
                actions.append({"name": sd.name, "action": "set"})
        elif endpoint_changed and clear_secret(conn, sd.name):
            actions.append({"name": sd.name, "action": "cleared_endpoint_changed"})
    rule = RULES.get(name)
    if rule is not None and (problem := rule(conn)) is not None:
        raise ValidationFailed(problem[0], fields=[problem[1]])  # get_db/sessiya rollback qiladi
    db.commit()  # commit-then-audit
    if changes or actions:
        log_event(meta, AuditAction.INTEGRATION_UPDATED, user_id=actor.user_id,
                  object_type="integration", object_id=name,
                  details={"changes": changes, "secrets": actions, "reason": reason})
        sysconfig.invalidate()
    return get_integration(db, name)


def request_check(db: Session, actor: AuthContext, name: str,
                  meta: ClientMeta) -> IntegrationCheckOut:
    integ = _integration(name)
    if integ.check_in != "worker":
        raise NotFoundError()  # api tomonidagi probe'lar (S5) o'z endpointida
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('ugk_integration_check_' || :n))"),
               {"n": name})
    row = db.execute(text(f"SELECT {_CHECK_COLS} FROM core.integration_checks WHERE name = :n "
                          "AND status IN ('pending', 'running') ORDER BY id DESC LIMIT 1"),
                     {"n": name}).first()
    if row is None:
        row = db.execute(text("INSERT INTO core.integration_checks (name, requested_by) "
                              f"VALUES (:n, :u) RETURNING {_CHECK_COLS}"),
                         {"n": name, "u": actor.user_id}).one()
        db.commit()
        log_event(meta, AuditAction.INTEGRATION_CHECK_REQUESTED, user_id=actor.user_id,
                  object_type="integration", object_id=name, details={"check_id": row.id})
    else:
        db.commit()
    return IntegrationCheckOut(**dict(row._mapping))


def get_check(db: Session, check_id: int) -> IntegrationCheckOut:
    row = db.execute(text(f"SELECT {_CHECK_COLS} FROM core.integration_checks WHERE id = :i"),
                     {"i": check_id}).first()
    if row is None:
        raise NotFoundError()
    return IntegrationCheckOut(**dict(row._mapping))
```
`backend/app/admin/integrations_router.py`:
```python
"""Integratsiyalar va ularning hisob ma'lumotlari (admin:integrations)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.admin import integrations_service as service
from app.admin.dwh_schemas import IntegrationCheckOut, IntegrationOut, IntegrationUpdate
from app.auth.context import AuthContext, require_perm
from app.auth.permissions import Perm
from app.core.db import DB
from app.core.request_meta import Meta

router = APIRouter(prefix="/admin/integrations", tags=["admin"])
IntegrationsAdmin = Annotated[AuthContext, Depends(require_perm(Perm.ADMIN_INTEGRATIONS))]
Name = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,31}$")]


@router.get("")
def list_integrations(ctx: IntegrationsAdmin, db: DB) -> list[IntegrationOut]:
    return service.list_integrations(db)


@router.put("/{name}")
def update_integration(name: Name, body: IntegrationUpdate, ctx: IntegrationsAdmin, db: DB,
                       meta: Meta) -> IntegrationOut:
    return service.update_integration(db, ctx, name, body, meta)


@router.post("/{name}/check", status_code=202)
def request_check(name: Name, ctx: IntegrationsAdmin, db: DB,
                  meta: Meta) -> IntegrationCheckOut:
    return service.request_check(db, ctx, name, meta)


@router.get("/checks/{check_id}")
def get_check(check_id: Annotated[int, Path(gt=0)], ctx: IntegrationsAdmin,
              db: DB) -> IntegrationCheckOut:
    return service.get_check(db, check_id)
```
`backend/app/main.py` — `from app.admin.integrations_router import router as integrations_router` va `app.include_router(integrations_router, prefix=API_PREFIX)` (`config_router` dan keyin).
`backend/tests/test_route_guards.py` — `EXPECTED_ROUTES` ga `("GET", "/api/v1/admin/integrations")`, `("PUT", "/api/v1/admin/integrations/{name}")`, `("POST", "/api/v1/admin/integrations/{name}/check")`, `("GET", "/api/v1/admin/integrations/checks/{check_id}")`; 401 testidagi `req_path` zanjiriga `.replace("{name}", "smtp").replace("{check_id}", "1")`.

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_integrations.py tests/test_route_guards.py tests/test_reencrypt_registry.py tests/test_keys_cli.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(admin): integratsiyalar — shifrlangan write-only sirlar, manzilga bog'langan sir, tekshiruv navbati

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: SMTP — jonli notifier, `smtp_probe` va worker `integration_checks` jobi

**Files:**
- Create: `backend/app/etl/probes.py`
- Modify: `backend/app/etl/notify.py`, `backend/app/worker.py` (`build_notifier()`, `integration_checks` jobi), `backend/app/cli.py` (`build_notifier()`), `backend/tests/test_notify.py` (`test_build_notifier_adds_email_only_when_configured` → `test_build_notifier_is_live`), `backend/tests/test_worker.py` (`JOBS`)
- Test: `backend/tests/test_notify_live.py`

**Interfaces:**
- Consumes: `sysconfig.current`, `integrations.secret`, `store_secret`, `EmailNotifier`, `CompositeNotifier`, `LogNotifier`, `get_engine`, `_guarded` (worker).
- Produces:
  - `app.etl.notify`: `SmtpConfig(host, port, sender, recipients, username, password, starttls, ssl)`, `smtp_config() -> SmtpConfig | None` (host yoki qabul qiluvchi yo'q — `None`), `LiveEmailNotifier(loader=smtp_config, smtp_factory=smtplib.SMTP, smtp_ssl_factory=smtplib.SMTP_SSL)`, `smtp_probe(loader=smtp_config, smtp_factory=smtplib.SMTP, smtp_ssl_factory=smtplib.SMTP_SSL) -> str`, `build_notifier() -> Notifier` (argumentsiz; `[LogNotifier(), LiveEmailNotifier()]`).
  - Probe kodlari: `ok`, `not_configured`, `insecure_refused`, `auth_failed`, `tls_failed`, `timeout`, `protocol_error`, `connect_failed`; `probes.py` da qo'shimcha `error`, `not_supported`.
  - `app.etl.probes`: `PROBES: dict[str, Callable[[], str]] = {"smtp": smtp_probe}`, `process_integration_checks() -> int`.
  - Worker: `integration_checks` jobi (interval 10 s).

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_notify_live.py`:
```python
import smtplib
import ssl
from collections.abc import Callable, Iterator
from dataclasses import replace
from email.message import EmailMessage
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from app.core import integrations
from app.core.db import get_engine
from app.etl import probes
from app.etl.notify import (
    LiveEmailNotifier,
    Notification,
    SmtpConfig,
    smtp_config,
    smtp_probe,
)

CFG = SmtpConfig(host="relay.uge.uz", port=587, sender="ugk@uge.uz",
                 recipients=["kazna@uge.uz"], username="ugk", password="pw", starttls=True,
                 ssl=False)
NOTE = Notification("etl_failed", "Загрузка завершилась ошибкой", "Шаг: facts")


class FakeSMTP:
    fail: ClassVar[BaseException | None] = None
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, timeout: float, context: Any = None) -> None:
        if FakeSMTP.fail is not None:
            raise FakeSMTP.fail
        self.host, self.port = host, port
        self.tls = False
        self.login_args: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self, context: Any = None) -> None:
        self.tls = True

    def login(self, user: str, password: str) -> None:
        self.login_args = (user, password)

    def noop(self) -> tuple[int, bytes]:
        return 250, b"ok"

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    FakeSMTP.fail = None
    FakeSMTP.instances.clear()
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.integration_credentials"))
        conn.execute(text("DELETE FROM core.integration_checks"))


def test_live_notifier_uses_current_config() -> None:
    LiveEmailNotifier(loader=lambda: CFG, smtp_factory=FakeSMTP).notify(NOTE)
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.tls, smtp.login_args) == ("relay.uge.uz", True, ("ugk", "pw"))
    assert smtp.sent[0]["To"] == "kazna@uge.uz"
    LiveEmailNotifier(loader=lambda: None, smtp_factory=FakeSMTP).notify(NOTE)
    assert len(FakeSMTP.instances) == 1


def test_smtp_config_reads_panel_and_secret(setting: Callable[[str, object], None]) -> None:
    assert smtp_config() is None
    setting("smtp.host", "relay.uge.uz")
    assert smtp_config() is None  # qabul qiluvchi yo'q
    setting("notify.email_to", ["kazna@uge.uz"])
    setting("smtp.port", 587)
    with get_engine("app").begin() as conn:
        integrations.store_secret(conn, "smtp.password", "Panel-Secret-1", None)
    cfg = smtp_config()
    assert cfg is not None
    assert (cfg.host, cfg.port, cfg.recipients, cfg.password) == (
        "relay.uge.uz", 587, ["kazna@uge.uz"], "Panel-Secret-1")


@pytest.mark.parametrize(("fail", "code"), [
    (None, "ok"),
    (smtplib.SMTPAuthenticationError(535, b"bad"), "auth_failed"),
    (ssl.SSLError("bad cert"), "tls_failed"),
    (TimeoutError(), "timeout"),
    (smtplib.SMTPServerDisconnected("gone"), "protocol_error"),
    (ConnectionRefusedError(), "connect_failed"),
])
def test_probe_maps_failures_to_safe_codes(fail: BaseException | None, code: str) -> None:
    FakeSMTP.fail = fail
    assert smtp_probe(loader=lambda: CFG, smtp_factory=FakeSMTP) == code


def test_probe_refuses_unconfigured_and_plaintext_auth() -> None:
    assert smtp_probe(loader=lambda: None, smtp_factory=FakeSMTP) == "not_configured"
    plain = replace(CFG, starttls=False)
    assert smtp_probe(loader=lambda: plain, smtp_factory=FakeSMTP) == "insecure_refused"
    assert FakeSMTP.instances == []


def _enqueue(status: str = "pending", age: str = "0 minutes") -> int:
    with get_engine("app").begin() as conn:
        return int(conn.execute(text(
            "INSERT INTO core.integration_checks (name, requested_by, status, requested_at) "
            "VALUES ('smtp', 1, :s, now() - CAST(:a AS interval)) RETURNING id"),
            {"s": status, "a": age}).scalar_one())


def _check(row_id: int) -> Any:
    with get_engine("app").connect() as conn:
        return conn.execute(text("SELECT status, code, finished_at FROM core.integration_checks "
                                 "WHERE id = :i"), {"i": row_id}).one()


def test_process_checks_runs_probe_and_expires_stuck(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "PROBES", {"smtp": lambda: "auth_failed"})
    stuck = _enqueue("running", "10 minutes")
    fresh = _enqueue()
    assert probes.process_integration_checks() == 1
    assert tuple(_check(fresh))[:2] == ("failed", "auth_failed")
    assert _check(fresh).finished_at is not None
    assert tuple(_check(stuck))[:2] == ("failed", "timeout")


def test_probe_exception_text_is_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> str:
        raise RuntimeError("login failed for password=Panel-Secret-1")

    monkeypatch.setattr(probes, "PROBES", {"smtp": boom})
    row_id = _enqueue()
    assert probes.process_integration_checks() == 1
    assert tuple(_check(row_id))[:2] == ("failed", "error")
```
`backend/tests/test_notify.py` — `test_build_notifier_adds_email_only_when_configured` ni almashtiring (va `get_settings` importi ishlatilmasa olib tashlang):
```python
def test_build_notifier_is_live() -> None:
    notifier = build_notifier()
    assert isinstance(notifier, CompositeNotifier)
    assert [type(n) for n in notifier.notifiers] == [LogNotifier, LiveEmailNotifier]
```
(`LiveEmailNotifier` importini qo'shing.) `backend/tests/test_worker.py` — `JOBS` ga `"integration_checks"`.

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_notify_live.py tests/test_notify.py -v`
Expected: FAIL — `ImportError: cannot import name 'LiveEmailNotifier'`.

- [ ] **Step 3: `notify.py` — konfiguratsiya, jonli notifier, probe**

`backend/app/etl/notify.py` — `from app.core.config import Settings` importini olib tashlang; qo'shing: `from app.core import integrations, sysconfig`, `from app.core.db import get_engine`. `build_notifier` ni almashtiring va qo'shing:
```python
@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    sender: str
    recipients: list[str]
    username: str
    password: str
    starttls: bool
    ssl: bool


def smtp_config() -> SmtpConfig | None:
    """Joriy SMTP sozlamasi (panel > env > standart); host yoki qabul qiluvchi yo'q — None."""
    with get_engine("app").connect() as conn:
        host = str(sysconfig.current(conn, "smtp.host"))
        recipients = list(sysconfig.current(conn, "notify.email_to"))
        if not host or not recipients:
            return None
        return SmtpConfig(
            host=host, port=int(sysconfig.current(conn, "smtp.port")),
            sender=str(sysconfig.current(conn, "smtp.from")), recipients=recipients,
            username=str(sysconfig.current(conn, "smtp.user")),
            password=integrations.secret(conn, "smtp.password"),
            starttls=bool(sysconfig.current(conn, "smtp.starttls")),
            ssl=bool(sysconfig.current(conn, "smtp.ssl")))


class LiveEmailNotifier:
    """Har xabarda joriy sozlama — panel o'zgarishi worker'ni qayta ishga tushirmasdan ishlaydi."""

    def __init__(self, loader: Callable[[], SmtpConfig | None] = smtp_config,
                 smtp_factory: Callable[..., Any] = smtplib.SMTP,
                 smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL) -> None:
        self._loader = loader
        self._factory = smtp_factory
        self._ssl_factory = smtp_ssl_factory

    def notify(self, notification: Notification) -> None:
        cfg = self._loader()
        if cfg is None:
            return
        EmailNotifier(host=cfg.host, port=cfg.port, sender=cfg.sender, recipients=cfg.recipients,
                      username=cfg.username, password=cfg.password, starttls=cfg.starttls,
                      ssl=cfg.ssl, smtp_factory=self._factory,
                      smtp_ssl_factory=self._ssl_factory).notify(notification)


def smtp_probe(loader: Callable[[], SmtpConfig | None] = smtp_config,
               smtp_factory: Callable[..., Any] = smtplib.SMTP,
               smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL) -> str:
    """Ulanish + TLS + login (xat yuborilmaydi). Faqat xavfsiz kod qaytaradi."""
    cfg = loader()
    if cfg is None:
        return "not_configured"
    if cfg.password and not (cfg.starttls or cfg.ssl):
        return "insecure_refused"
    context = ssl.create_default_context()
    try:
        if cfg.ssl:
            client = smtp_ssl_factory(cfg.host, cfg.port, context=context, timeout=10.0)
        else:
            client = smtp_factory(cfg.host, cfg.port, timeout=10.0)
        with client as smtp:
            if cfg.starttls and not cfg.ssl:
                smtp.starttls(context=context)
            if cfg.password:
                smtp.login(cfg.username or cfg.sender, cfg.password)
            smtp.noop()
    except smtplib.SMTPAuthenticationError:
        return "auth_failed"
    except ssl.SSLError:
        return "tls_failed"
    except TimeoutError:
        return "timeout"
    except smtplib.SMTPException:
        return "protocol_error"
    except OSError:
        return "connect_failed"
    return "ok"


def build_notifier() -> Notifier:
    return CompositeNotifier([LogNotifier(), LiveEmailNotifier()])
```
(`except` tartibi muhim: `SMTPAuthenticationError` ⊂ `SMTPException` ⊂ `OSError`, `SSLError`/`TimeoutError` ⊂ `OSError`.)

- [ ] **Step 4: Tekshiruv navbati va worker**

`backend/app/etl/probes.py`:
```python
"""Integratsiya ulanish tekshiruvlari navbati (worker, egress bor joyda).

Natija — faqat xavfsiz kod; istisno matni saqlanmaydi (unda sir bo'lishi mumkin).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text

from app.core.db import get_engine
from app.core.logging import get_logger
from app.etl.notify import smtp_probe

log = get_logger("ugekazna.probes")
PROBES: dict[str, Callable[[], str]] = {"smtp": smtp_probe}
_BATCH = 5


def process_integration_checks() -> int:
    with get_engine("app").begin() as conn:
        conn.execute(text("UPDATE core.integration_checks SET status = 'failed', code = 'timeout', "
                          "finished_at = now() WHERE status = 'running' "
                          "AND requested_at < now() - interval '5 minutes'"))
        rows = conn.execute(text(
            "UPDATE core.integration_checks SET status = 'running' WHERE id IN ("
            "SELECT id FROM core.integration_checks WHERE status = 'pending' ORDER BY id "
            "LIMIT :n FOR UPDATE SKIP LOCKED) RETURNING id, name"), {"n": _BATCH}).all()
    for row in rows:
        probe = PROBES.get(row.name)
        try:
            code = probe() if probe is not None else "not_supported"
        except Exception as exc:  # noqa: BLE001 -- bitta probe xatosi navbatni to'xtatmaydi
            log.error("integration_probe_failed", name=row.name, error=type(exc).__name__)
            code = "error"
        with get_engine("app").begin() as conn:
            conn.execute(text("UPDATE core.integration_checks SET status = :s, code = :c, "
                              "finished_at = now() WHERE id = :i"),
                         {"s": "ok" if code == "ok" else "failed", "c": code[:32], "i": row.id})
        log.info("integration_checked", name=row.name, code=code)
    return len(rows)
```
`backend/app/worker.py` — `from app.etl.probes import process_integration_checks`; `build_scheduler` da `etl_requests` jobidan keyin:
```python
    scheduler.add_job(_guarded("integration_checks", process_integration_checks),
                      "interval", seconds=10, id="integration_checks", **opts)
```
`main()` da `build_notifier(settings)` → `build_notifier()`; `backend/app/cli.py` da `build_notifier(get_settings())` → `build_notifier()` (keraksiz importni olib tashlang).

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_notify_live.py tests/test_notify.py tests/test_worker.py tests/test_config.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(notify): jonli SMTP sozlamasi, smtp_probe va worker'da ulanish tekshiruvi navbati

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Worker jadvallari paneldan (`add_cron_job`, `sync_schedules`) va ETL siyosati kalitlari

**Files:**
- Modify: `backend/app/worker.py`, `backend/app/etl/quality.py` (`tolerances`, `run_checks`, `_control_totals`, `_balance_identity`), `backend/app/etl/runner.py` (`compute_window`, `INCREMENTAL_LOOKBACK` o'chadi), `backend/tests/test_worker.py` (`JOBS`)
- Test: `backend/tests/test_worker_schedules.py`

**Interfaces:**
- Consumes: `sysconfig.current`, `CronTrigger`, `TASHKENT`, `_guarded`.
- Produces:
  - `worker.add_cron_job(scheduler, job_id: str, key: str, func, *, args: tuple[Any, ...] = (), **opts) -> None` — cron'ni `key` dan o'qiydi, `_applied[job_id] = (key, cron)`.
  - `worker.sync_schedules(scheduler) -> list[str]` — o'zgargan job id'lari; `schedules` jobi (60 s). `build_scheduler` boshida `_applied.clear()`.
  - `partitions` → `maintenance.partitions_cron`, `cleanup` → `maintenance.cleanup_cron`, `etl_synthetic_full` → `etl.synthetic_cron` — hammasi `add_cron_job` orqali.
  - `quality.tolerances(conn) -> tuple[Decimal, Decimal]` (`quality.control_tolerance`, `quality.balance_tolerance`); `CONTROL_TOLERANCE`/`BALANCE_TOLERANCE` konstantalari o'chadi.
  - `compute_window(mode, *, today, history_start, last_watermark, lookback_days: int = 45) -> Window`; `Runner` `etl.incremental_lookback_days` ni o'qib uzatadi.

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_worker_schedules.py`:
```python
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app import worker
from app.core.config import get_settings
from app.core.db import get_engine
from app.etl.notify import LogNotifier
from app.etl.quality import tolerances
from app.etl.runner import compute_window
from app.etl.types import Mode

Put = Callable[[str, object], None]


def _hm(job: Any) -> tuple[str, str]:
    fields = {f.name: str(f) for f in job.trigger.fields}
    return fields["hour"], fields["minute"]


def _scheduler() -> Any:
    return worker.build_scheduler(get_settings().model_copy(update={"env": "dev"}), LogNotifier())


def test_panel_cron_change_is_applied_without_restart(setting: Put) -> None:
    scheduler = _scheduler()
    assert _hm(scheduler.get_job("partitions")) == ("3", "30")
    assert worker.sync_schedules(scheduler) == []
    setting("maintenance.partitions_cron", "15 2 * * *")
    setting("etl.synthetic_cron", "30 1 * * *")
    assert sorted(worker.sync_schedules(scheduler)) == ["etl_synthetic_full", "partitions"]
    assert _hm(scheduler.get_job("partitions")) == ("2", "15")
    assert _hm(scheduler.get_job("etl_synthetic_full")) == ("1", "30")
    assert worker.sync_schedules(scheduler) == []


def test_invalid_panel_cron_keeps_default(setting: Put) -> None:
    setting("maintenance.cleanup_cron", "every night")
    assert _hm(_scheduler().get_job("cleanup")) == ("4", "0")


def test_scheduler_has_sync_job() -> None:
    assert _scheduler().get_job("schedules") is not None


def test_incremental_lookback_is_a_parameter() -> None:
    window = compute_window(Mode.INCREMENTAL, today=date(2026, 9, 24),
                            history_start=date(2024, 1, 1),
                            last_watermark=datetime(2026, 9, 20, 3, tzinfo=UTC), lookback_days=30)
    assert window.date_from == date(2026, 8, 21)


def test_quality_tolerances_follow_panel(setting: Put) -> None:
    with get_engine("app").connect() as conn:
        assert tolerances(conn) == (Decimal("0.001"), Decimal("0.01"))
    setting("quality.control_tolerance", 0.005)
    with get_engine("app").connect() as conn:
        assert tolerances(conn) == (Decimal("0.005"), Decimal("0.01"))
```
`backend/tests/test_worker.py` — `JOBS` ga `"schedules"`.

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_worker_schedules.py -v`
Expected: FAIL — `AttributeError: module 'app.worker' has no attribute 'sync_schedules'`.

- [ ] **Step 3: Worker**

`backend/app/worker.py` — `from app.dwh.reference import current_setting` o'rniga `from app.core import sysconfig` (qolgan `current_setting(conn, …)` chaqiruvlari `sysconfig.current(conn, …)` bo'ladi); modul darajasida:
```python
# job_id -> (sozlama kaliti, qo'llangan cron). S1–S5 cron joblari ham shu orqali qo'shiladi.
_applied: dict[str, tuple[str, str]] = {}


def add_cron_job(scheduler: BaseScheduler, job_id: str, key: str, func: Callable[..., Any], *,
                 args: tuple[Any, ...] = (), **opts: Any) -> None:
    with get_engine("app").connect() as conn:
        cron = str(sysconfig.current(conn, key))
    scheduler.add_job(func, CronTrigger.from_crontab(cron, timezone=TASHKENT), args=args,
                      id=job_id, **opts)
    _applied[job_id] = (key, cron)


def sync_schedules(scheduler: BaseScheduler) -> list[str]:
    """Panelda o'zgargan cron'lar ≤ 60 s ichida qo'llanadi (qayta ishga tushirishsiz)."""
    changed: list[str] = []
    with get_engine("app").connect() as conn:
        for job_id, (key, applied) in list(_applied.items()):
            cron = str(sysconfig.current(conn, key))
            if cron == applied or scheduler.get_job(job_id) is None:
                continue
            scheduler.reschedule_job(job_id, trigger=CronTrigger.from_crontab(cron,
                                                                             timezone=TASHKENT))
            _applied[job_id] = (key, cron)
            changed.append(job_id)
    if changed:
        log.info("schedules_synced", jobs=changed)
    return changed
```
(`from apscheduler.schedulers.base import BaseScheduler`, `Callable` importlari.) `build_scheduler` boshida `_applied.clear()`; uchta cron job:
```python
    if settings.env == "dev":
        add_cron_job(scheduler, "etl_synthetic_full", "etl.synthetic_cron", run_etl_job,
                     args=("synthetic", Mode.FULL, notifier), **opts)
    ...
    add_cron_job(scheduler, "partitions", "maintenance.partitions_cron",
                 _guarded("partitions", lambda: maintain_partitions(today_tashkent())), **opts)
    add_cron_job(scheduler, "cleanup", "maintenance.cleanup_cron",
                 _guarded("cleanup", cleanup_job), **opts)
    scheduler.add_job(_guarded("schedules", lambda: sync_schedules(scheduler)),
                      "interval", seconds=60, id="schedules", **opts)
```

- [ ] **Step 4: Sifat va oyna**

`backend/app/etl/quality.py` — konstantalar o'rniga:
```python
def tolerances(conn: Connection) -> tuple[Decimal, Decimal]:
    """(nazorat jami nisbiy dopuski, balans dopuski) — paneldan, keyingi yuklashdan."""
    return (Decimal(str(sysconfig.current(conn, "quality.control_tolerance"))),
            Decimal(str(sysconfig.current(conn, "quality.balance_tolerance"))))
```
`_control_totals(conn, source, window, totals, tolerance: Decimal)` va `_balance_identity(conn, build_id, window, tolerance: Decimal)` — konstanta o'rniga parametr; `run_checks` da `control_tol, balance_tol = tolerances(conn)` va uzatish.

`backend/app/etl/runner.py` — `INCREMENTAL_LOOKBACK` ni o'chiring; `compute_window(..., lookback_days: int = 45)` va `wm_day - timedelta(days=lookback_days)`; docstring'dagi «45 kun» → «lookback_days (standart 45, TZ)». `Runner` da `history_start` o'qilgan `try` blokiga `lookback = int(sysconfig.current(conn, "etl.incremental_lookback_days"))` qo'shing va `compute_window(..., lookback_days=lookback)`.

- [ ] **Step 5: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_worker_schedules.py tests/test_worker.py tests/test_etl_runner.py tests/test_quality.py -v`
Expected: barcha testlar passed.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(worker): cron jadvallari paneldan (60 s sinxron), sifat dopusklari va inkremental oyna

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `ops-check` chegaralari reyestrga

**Files:**
- Modify: `backend/app/core/sysconfig.py` (`_DEFS` += 5 ta `ops.*`), `backend/app/ops.py` (4-reja moduli)
- Test: `backend/tests/test_ops_settings.py`

**Interfaces:**
- Consumes: 4-reja `app.ops`: `check_restore`, `check_tls`, `ops_check`, `record_restore_test`, `RestoreResult`, `RESTORE_KEY`, `RESTORE_MAX_AGE`, `DEK_MAX_AGE`, `CLOCK_SKEW_MAX`, `TLS_WARN`, `TLS_CRITICAL`.
- Produces:
  - Kalitlar (`category="ops"`, `perm=ADMIN_SECURITY`, `guarded`): `ops.restore_max_age_days` (35; 1..35), `ops.dek_max_age_days` (365; 30..365), `ops.clock_skew_max_seconds` (60; 5..60), `ops.tls_warn_days` (30; 30..90), `ops.tls_critical_days` (7; 7..30).
  - `check_restore(value, now, *, max_age: timedelta = RESTORE_MAX_AGE)`, `check_tls(path, now, *, warn: timedelta = TLS_WARN, critical: timedelta = TLS_CRITICAL)`; `ops_check` chegaralarni shu kalitlardan o'qiydi. Konstantalar standart qiymat sifatida qoladi (CLI testlari va `test_check_restore_rules` o'zgarmaydi).

- [ ] **Step 1: Muvaffaqiyatsiz testlarni yozish**

`backend/tests/test_ops_settings.py`:
```python
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import ops
from app.core import sysconfig
from app.core.db import get_engine

Put = Callable[[str, object], None]


@pytest.fixture
def restore_row() -> Iterator[None]:
    yield
    with get_engine("migrator").begin() as conn:
        conn.execute(text("DELETE FROM core.settings WHERE key = :k"), {"k": ops.RESTORE_KEY})


def test_ops_keys_are_tighten_only() -> None:
    expected = {"ops.restore_max_age_days": (35, "hi"), "ops.dek_max_age_days": (365, "hi"),
                "ops.clock_skew_max_seconds": (60, "hi"), "ops.tls_warn_days": (30, "lo"),
                "ops.tls_critical_days": (7, "lo")}
    for key, (bound, side) in expected.items():
        d = sysconfig.REGISTRY[key]
        assert d.default == bound == getattr(d, side) and d.step_up and d.category == "ops", key


def test_check_restore_accepts_threshold() -> None:
    now = datetime.now(UTC)
    value = {"at": (now - timedelta(days=20)).isoformat(), "result": "ok", "rto_ok": True}
    assert ops.check_restore(value, now) == []
    assert [p.code for p in ops.check_restore(value, now, max_age=timedelta(days=10))] == [
        "restore_test_overdue"]


@pytest.mark.usefixtures("restore_row")
def test_ops_check_uses_panel_thresholds(setting: Put) -> None:
    now = datetime.now(UTC)
    with get_engine("app").begin() as conn:
        ops.record_restore_test(conn, ops.RestoreResult(
            at=now - timedelta(days=20), result="ok", duration_seconds=60, backup="t", details=""))
    assert "restore_test_overdue" not in {p.code for p in ops.ops_check(now=now)}
    setting("ops.restore_max_age_days", 10)
    setting("ops.clock_skew_max_seconds", 5)
    codes = {p.code for p in ops.ops_check(
        now=now, app_clock=lambda: datetime.now(UTC) + timedelta(seconds=20))}
    assert {"restore_test_overdue", "clock_skew"} <= codes
```

- [ ] **Step 2: Testlar yiqilishini tekshirish**

Run: `$TEST pytest tests/test_ops_settings.py -v`
Expected: FAIL — `KeyError: 'ops.restore_max_age_days'`.

- [ ] **Step 3: Kalitlar va `ops.py`**

`backend/app/core/sysconfig.py` — `_DEFS` ga (xavfsizlik blokidan keyin):
```python
    int_def("ops.restore_max_age_days", 35, 1, 35, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Проверка восстановления не реже, чем раз в", unit="дн."),
    int_def("ops.dek_max_age_days", 365, 30, 365, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Предупреждать о ротации ключа старше", unit="дн."),
    int_def("ops.clock_skew_max_seconds", 60, 5, 60, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Допустимое расхождение часов", unit="с"),
    int_def("ops.tls_warn_days", 30, 30, 90, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Предупреждать об истечении TLS-сертификата за", unit="дн."),
    int_def("ops.tls_critical_days", 7, 7, 30, category="ops", perm=Perm.ADMIN_SECURITY,
            guarded=True, title="Критично при истечении TLS-сертификата за", unit="дн."),
```
`backend/app/ops.py` — `from app.core import sysconfig`; `check_restore` ga `*, max_age: timedelta = RESTORE_MAX_AGE` (taqqoslashda `max_age`); `check_tls` ga `*, warn: timedelta = TLS_WARN, critical: timedelta = TLS_CRITICAL`; `ops_check` ichida, `with get_engine("app").connect() as conn:` blokining boshida:
```python
        days = lambda key: timedelta(days=int(sysconfig.current(conn, key)))  # noqa: E731
        restore_max_age = days("ops.restore_max_age_days")
        dek_max_age = days("ops.dek_max_age_days")
        tls_warn, tls_critical = days("ops.tls_warn_days"), days("ops.tls_critical_days")
        skew_max = timedelta(seconds=int(sysconfig.current(conn, "ops.clock_skew_max_seconds")))
```
va `check_restore(..., max_age=restore_max_age)`, `now - created_at > dek_max_age` (xabarda `{dek_max_age.days} дней`), `skew > skew_max`, `check_tls(tls_cert, now, warn=tls_warn, critical=tls_critical)`. (`days` lambda o'rniga ichki `def` yozsangiz ham bo'ladi — ruff E731 shunda kerak emas.)

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$TEST pytest tests/test_ops_settings.py tests/test_ops.py tests/test_sysconfig.py -v`
Expected: barcha testlar passed.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(ops): ops-check chegaralari paneldan (faqat qattiqlashtirish)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Frontend — «Настройки» va «Политика безопасности» sahifalari, parol qoidasi uzunligi

**Files:**
- Create: `frontend/src/admin/settingValue.ts`, `frontend/src/admin/SettingsList.tsx`, `frontend/src/admin/SettingsPage.tsx`, `frontend/src/admin/SecurityPage.tsx`
- Modify: `frontend/openapi.json`, `frontend/src/api/schema.d.ts` (generatsiya), `frontend/src/api/types.ts`, `frontend/src/admin/api.ts`, `frontend/src/admin/access.ts`, `frontend/src/admin/registry.ts`, `frontend/src/auth/passwordRules.ts`, `frontend/src/auth/PasswordChangePage.tsx`, `frontend/src/i18n/ru.ts`, `frontend/src/test/fixtures.ts` (`ALL_PERMISSIONS`, `ME_*`), `frontend/src/admin/adminScreen.test.tsx` (8 → 11 havola)
- Test: `frontend/src/admin/settingValue.test.ts`, `frontend/src/admin/settingsPage.test.tsx`

**Interfaces:**
- Consumes: 3–5-vazifa endpointlari; `api`, `isApiError`, `Card`, `Table`, `Modal`, `Field`, `TextInput`, `Checkbox`, `OtpInput`, `FormError`, `Badge`, `ErrorBanner`, `PageSkeleton`, `useToast`, `useFocusFirstInvalid`, `formatDecimal`, `parseDecimal`, `formatDateTime`.
- Produces:
  - `types.ts`: `SettingOut`, `SettingUpdate`, `SettingVersionOut`, `IntegrationOut`, `IntegrationUpdate`, `IntegrationCheckOut`, `SecretStatusOut`.
  - `api.ts`: `adminKeys.settings`, `adminKeys.integrations`, `useSettings()`, `useSettingHistory(key: string | null)`, `useUpdateSetting()` (`{ key, body: SettingUpdate }`).
  - `settingValue.ts`: `Parsed = { ok: true; value: unknown } | { ok: false; error: string }`, `formatSetting(s, value): string` (muharrir uchun), `displaySetting(s, value): string` (jadval uchun, birligi bilan), `parseSetting(s, raw): Parsed`, `rangeHint(s): string`.
  - `SettingsList({ perm }: { perm: string })`, `SettingDialog`, `SourceBadge({ source })` (eksport — 10-vazifa ishlatadi), `FieldEditor` (eksport: `{ setting, value, onChange, error }`).
  - Admin sahifalari: `settings` (`admin:settings`, ikonka `list`), `security` (`admin:security`, `lock`), `integrations` (`admin:integrations`, `plug`; komponent 10-vazifada).
  - `checkPassword(password, username, minLength = 12)`, `passwordProblemText(code, minLength = 12)`.

- [ ] **Step 1: OpenAPI snapshot va tiplar**

Dev stack: `docker compose -f deploy/compose.yml up -d --build`.
```bash
curl -skf https://localhost:8443/api/v1/openapi.json -o frontend/openapi.json
$NODE npm run gen:api
grep -c "SettingVersionOut\|IntegrationOut\|SecretStatusOut" frontend/src/api/schema.d.ts
```
Expected: `grep` > 0. `frontend/src/api/types.ts` — `SettingOut` qatoridan keyin:
```ts
export type SettingUpdate = Schemas['SettingUpdate'];
export type SettingVersionOut = Schemas['SettingVersionOut'];
export type SecretStatusOut = Schemas['SecretStatusOut'];
export type IntegrationCheckOut = Schemas['IntegrationCheckOut'];
export type IntegrationOut = Schemas['IntegrationOut'];
export type IntegrationUpdate = Schemas['IntegrationUpdate'];
```
`frontend/src/test/fixtures.ts` — `ALL_PERMISSIONS` ga `'admin:security'`, `'admin:integrations'` (`'admin:keys'` dan keyin); har `ME_*` ga `password_min_length: 12`.

- [ ] **Step 2: Muvaffaqiyatsiz testlarni yozish**

`frontend/src/admin/settingValue.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { displaySetting, formatSetting, parseSetting } from './settingValue';

const INT = { kind: 'int', lo: 5, hi: 30, unit: 'мин' } as const;

describe('settingValue', () => {
  it('parses numbers with comma decimals and checks the range', () => {
    expect(parseSetting(INT, '20')).toEqual({ ok: true, value: 20 });
    expect(parseSetting(INT, '31')).toEqual({ ok: false, error: 'Допустимо от 5 до 30' });
    expect(parseSetting(INT, '2,5')).toEqual({ ok: false, error: 'Введите целое число' });
    expect(parseSetting({ kind: 'float', lo: 0, hi: 0.01, unit: '' }, '0,005')).toEqual({ ok: true, value: 0.005 });
    expect(parseSetting(INT, 'abc').ok).toBe(false);
  });

  it('handles lists, json, cron and bool', () => {
    const list = { kind: 'list', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(list, 'a@uge.uz\n b@uge.uz ,')).toEqual({ ok: true, value: ['a@uge.uz', 'b@uge.uz'] });
    expect(formatSetting(list, ['a@uge.uz', 'b@uge.uz'])).toBe('a@uge.uz\nb@uge.uz');
    const json = { kind: 'json', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(json, '{"a": [1]}')).toEqual({ ok: true, value: { a: [1] } });
    expect(parseSetting(json, '{a')).toEqual({ ok: false, error: 'Некорректный JSON' });
    const cron = { kind: 'cron', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(cron, '  ')).toEqual({ ok: false, error: 'Заполните значение' });
    const flag = { kind: 'bool', lo: null, hi: null, unit: '' } as const;
    expect(parseSetting(flag, 'true')).toEqual({ ok: true, value: true });
    expect(displaySetting(flag, false)).toBe('Нет');
  });

  it('displays numbers with units and empty values as a dash', () => {
    expect(displaySetting(INT, 30)).toBe('30 мин');
    expect(displaySetting({ kind: 'float', lo: 0, hi: 1, unit: '' }, 0.001)).toBe('0,001');
    expect(displaySetting({ kind: 'str', lo: null, hi: null, unit: '' }, '')).toBe('—');
    expect(displaySetting({ kind: 'list', lo: null, hi: null, unit: '' }, [])).toBe('—');
  });
});
```
`frontend/src/admin/settingsPage.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SettingOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { apiError, json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import { SettingsList } from './SettingsList';

const BASE: Omit<SettingOut, 'key' | 'title' | 'value' | 'default' | 'category' | 'kind' | 'perm' | 'lo' | 'hi' | 'unit'> = {
  version: 0,
  updated_by: null,
  updated_at: null,
  source: 'default',
  guarded: false,
  step_up: false,
  apply: 'live',
};
const KEEP: SettingOut = { ...BASE, key: 'builds.keep', title: 'Хранить сборок витрины', value: 3, default: 3, category: 'data', kind: 'int', perm: 'admin:settings', lo: 2, hi: 10, unit: '', apply: 'next_run' };
const IDLE: SettingOut = { ...BASE, key: 'security.session_idle_minutes', title: 'Завершение сеанса при бездействии', value: 30, default: 30, category: 'security', kind: 'int', perm: 'admin:security', lo: 5, hi: 30, unit: 'мин', guarded: true, step_up: true, version: 2, source: 'panel', updated_at: '2026-10-20T05:00:00Z' };

describe('SettingsList', () => {
  it('shows only settings of its permission grouped by category', async () => {
    mockApi({ 'GET /admin/settings': json([KEEP, IDLE]) });
    const { container } = renderWithProviders(<SettingsList perm="admin:settings" />);
    const table = await screen.findByRole('table', { name: 'Витрина и сборки' });
    expect(table).toHaveTextContent('Хранить сборок витрины');
    expect(table).toHaveTextContent('По умолчанию');
    expect(screen.queryByText('Завершение сеанса при бездействии')).not.toBeInTheDocument();
    await expectNoAxeViolations(container);
  });

  it('saves an unguarded value with expected_version and no reason', async () => {
    const server = mockApi({
      'GET /admin/settings': json([KEEP]),
      'GET /admin/settings/builds.keep/history': json([]),
      'PUT /admin/settings/builds.keep': json({ ...KEEP, value: 4, version: 1, source: 'panel' }),
    });
    const { user } = renderWithProviders(<SettingsList perm="admin:settings" />);
    await user.click(await screen.findByText('Хранить сборок витрины'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Хранить сборок витрины' });
    expect(within(dialog).getByText('Применяется со следующей загрузки или обслуживания')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Причина изменения')).not.toBeInTheDocument();
    const input = within(dialog).getByLabelText('Значение');
    await user.clear(input);
    await user.type(input, '11');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText('Допустимо от 2 до 10')).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, '4');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    const put = server.calls.find((c) => c.method === 'PUT');
    expect(put?.body).toEqual({ value: 4, expected_version: 0 });
  });

  it('requires reason and TOTP for a security setting and shows a server OTP error', async () => {
    const server = mockApi({
      'GET /admin/settings': json([IDLE]),
      'GET /admin/settings/security.session_idle_minutes/history': json([{ version: 2, value: 30, updated_by: 1, updated_at: '2026-10-20T05:00:00Z' }]),
      'PUT /admin/settings/security.session_idle_minutes': apiError(422, 'step_up_failed', 'Неверный код подтверждения', { fields: ['otp'] }),
    });
    const { user } = renderWithProviders(<SettingsList perm="admin:security" />);
    await user.click(await screen.findByText('Завершение сеанса при бездействии'));
    const dialog = screen.getByRole('dialog', { name: 'Настройка: Завершение сеанса при бездействии' });
    expect(await within(dialog).findByRole('table', { name: 'История изменений' })).toBeInTheDocument();
    const input = within(dialog).getByLabelText('Значение');
    await user.clear(input);
    await user.type(input, '20');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(within(dialog).getByText('Укажите причину (не менее 5 символов)')).toBeInTheDocument();
    expect(within(dialog).getByText('Введите 6-значный код')).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === 'PUT')).toBe(false);
    await user.type(within(dialog).getByLabelText('Причина изменения'), 'Письмо ИБ №7');
    await user.type(within(dialog).getByLabelText('Код из приложения'), '123456');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    expect(await within(dialog).findByText('Неверный код подтверждения')).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === 'PUT')?.body).toEqual({ value: 20, expected_version: 2, reason: 'Письмо ИБ №7', otp: '123456' });
  });
});
```
`frontend/src/admin/adminScreen.test.tsx` — `toHaveLength(8)` → `toHaveLength(11)`.

- [ ] **Step 3: Testlar yiqilishini tekshirish**

Run: `$NODE npm test -- src/admin/settingValue.test.ts src/admin/settingsPage.test.tsx`
Expected: FAIL — `Failed to resolve import "./settingValue"`.

- [ ] **Step 4: Matnlar**

`frontend/src/i18n/ru.ts`:
- `'password.rule.length': 'Не менее 12 символов',` → `'password.rule.length': 'Не менее {n} символов',`; `'password.problem.too_short': 'Пароль короче 12 символов',` → `'password.problem.too_short': 'Пароль короче {n} символов',`.
- `} as const satisfies …` dan oldin:
```ts
  'admin.page.settings': 'Настройки',
  'admin.page.security': 'Политика безопасности',
  'admin.page.integrations': 'Интеграции',
  'settings.category.data': 'Витрина и сборки',
  'settings.category.etl': 'Загрузки и обслуживание',
  'settings.category.quality': 'Контроль качества данных',
  'settings.category.retention': 'Сроки хранения',
  'settings.category.notify': 'Оповещения',
  'settings.category.security': 'Вход и сеансы',
  'settings.category.ops': 'Контроль эксплуатации',
  'settings.col.name': 'Настройка',
  'settings.col.value': 'Значение',
  'settings.col.source': 'Источник',
  'settings.col.version': 'Версия',
  'settings.col.updated': 'Изменено',
  'settings.source.panel': 'Панель',
  'settings.source.env': 'Конфигурация сервера',
  'settings.source.default': 'По умолчанию',
  'settings.editTitle': 'Настройка: {title}',
  'settings.value': 'Значение',
  'settings.range': 'Допустимо от {lo} до {hi}',
  'settings.defaultValue': 'По умолчанию: {value}',
  'settings.applyLive': 'Применяется в течение минуты без перезапуска',
  'settings.applyNextRun': 'Применяется со следующей загрузки или обслуживания',
  'settings.reason': 'Причина изменения',
  'settings.reasonHint': 'Номер заявки или письма — попадёт в журнал аудита',
  'settings.reasonRequired': 'Укажите причину (не менее 5 символов)',
  'settings.otp': 'Код из приложения',
  'settings.otpHint': 'Изменение настройки безопасности подтверждается кодом 2FA',
  'settings.otpRequired': 'Введите 6-значный код',
  'settings.invalidNumber': 'Введите число',
  'settings.invalidInteger': 'Введите целое число',
  'settings.invalidJson': 'Некорректный JSON',
  'settings.required': 'Заполните значение',
  'settings.listHint': 'По одному значению в строке',
  'settings.saved': 'Настройка сохранена. Изменение записано в журнал аудита.',
  'settings.history': 'История изменений',
  'settings.empty': 'Нет доступных настроек',
```

- [ ] **Step 5: `settingValue.ts`**

```ts
import type { SettingOut } from '../api/types';
import { t } from '../i18n';
import { formatDecimal, parseDecimal } from './numbers';

type Meta = Pick<SettingOut, 'kind' | 'lo' | 'hi' | 'unit'>;
export type Parsed = { ok: true; value: unknown } | { ok: false; error: string };

export function rangeHint(s: Meta): string {
  return t('settings.range', { lo: formatDecimal(s.lo ?? 0), hi: formatDecimal(s.hi ?? 0) });
}

/** Muharrir maydoni uchun matn. */
export function formatSetting(s: Meta, value: unknown): string {
  if (s.kind === 'int' || s.kind === 'float') return typeof value === 'number' ? formatDecimal(value) : '';
  if (s.kind === 'bool') return value === true ? 'true' : 'false';
  if (s.kind === 'list') return Array.isArray(value) ? value.map(String).join('\n') : '';
  if (s.kind === 'json') return JSON.stringify(value, null, 2);
  return typeof value === 'string' ? value : '';
}

/** Jadval uchun qisqa ko'rinish. */
export function displaySetting(s: Meta, value: unknown): string {
  if (s.kind === 'bool') return value === true ? t('common.yes') : t('common.no');
  if (s.kind === 'list') return Array.isArray(value) && value.length ? value.map(String).join(', ') : '—';
  if (s.kind === 'json') {
    const text = JSON.stringify(value);
    return text.length > 80 ? `${text.slice(0, 79)}…` : text;
  }
  const text = formatSetting(s, value);
  if (!text) return '—';
  return s.unit ? `${text} ${s.unit}` : text;
}

export function parseSetting(s: Meta, raw: string): Parsed {
  const text = raw.trim();
  switch (s.kind) {
    case 'int':
    case 'float': {
      const n = parseDecimal(text);
      if (n === null) return { ok: false, error: t('settings.invalidNumber') };
      if (s.kind === 'int' && !Number.isInteger(n)) return { ok: false, error: t('settings.invalidInteger') };
      if ((s.lo !== null && n < s.lo) || (s.hi !== null && n > s.hi)) return { ok: false, error: rangeHint(s) };
      return { ok: true, value: n };
    }
    case 'bool':
      return { ok: true, value: text === 'true' };
    case 'list':
      return { ok: true, value: text.split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean) };
    case 'json':
      try {
        return { ok: true, value: JSON.parse(text) as unknown };
      } catch {
        return { ok: false, error: t('settings.invalidJson') };
      }
    case 'str':
      return { ok: true, value: text }; // bo'sh satr — "o'chirilgan" (masalan smtp.host)
    default:
      return text ? { ok: true, value: text } : { ok: false, error: t('settings.required') };
  }
}
```

- [ ] **Step 6: Hook'lar, sahifalar, reyestr**

`frontend/src/admin/api.ts` — importlarga `IntegrationCheckOut, IntegrationOut, IntegrationUpdate, SettingOut, SettingUpdate, SettingVersionOut`; `adminKeys` ga `settings: ['admin', 'settings'] as const, integrations: ['admin', 'integrations'] as const,`; `useUpdateFinAssumptions` dan keyin:
```ts
export function useSettings() {
  return useQuery({
    queryKey: adminKeys.settings,
    queryFn: ({ signal }) => api<SettingOut[]>('/admin/settings', { signal }),
    staleTime: 0,
  });
}

export function useSettingHistory(key: string | null) {
  return useQuery({
    queryKey: [...adminKeys.settings, 'history', key],
    queryFn: ({ signal }) => api<SettingVersionOut[]>(`/admin/settings/${encodeURIComponent(key ?? '')}/history`, { signal }),
    enabled: key !== null,
    staleTime: 0,
  });
}

export function useUpdateSetting() {
  const invalidate = useInvalidate(adminKeys.settings);
  const onError = useRefetchOnConflict(adminKeys.settings);
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: SettingUpdate }) =>
      api<SettingOut>(`/admin/settings/${encodeURIComponent(key)}`, { method: 'PUT', body }),
    onSuccess: invalidate,
    onError,
    meta: { inline: true },
  });
}
```
`frontend/src/admin/access.ts` — `AdminPageId` ga `| 'settings' | 'security' | 'integrations'`; `ADMIN_PAGES` da `finmodel` dan keyin:
```ts
  { id: 'settings', perm: 'admin:settings', titleKey: 'admin.page.settings', icon: 'list' },
  { id: 'security', perm: 'admin:security', titleKey: 'admin.page.security', icon: 'lock' },
  { id: 'integrations', perm: 'admin:integrations', titleKey: 'admin.page.integrations', icon: 'plug' },
```
`frontend/src/admin/registry.ts` — `settings: lazy(() => import('./SettingsPage')),`, `security: lazy(() => import('./SecurityPage')),` (`integrations` — 10-vazifa).
`frontend/src/admin/SettingsPage.tsx`:
```tsx
import { SettingsList } from './SettingsList';

export default function SettingsPage() {
  return <SettingsList perm="admin:settings" />;
}
```
`frontend/src/admin/SecurityPage.tsx` — xuddi shunday, `perm="admin:security"`.

`frontend/src/admin/SettingsList.tsx`:
```tsx
import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { SettingOut, SettingVersionOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Checkbox, Field, FormError, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { OtpInput } from '../ui/OtpInput';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useSettingHistory, useSettings, useUpdateSetting } from './api';
import { displaySetting, formatSetting, parseSetting, rangeHint } from './settingValue';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const CATEGORIES: Record<string, MessageKey> = {
  data: 'settings.category.data',
  etl: 'settings.category.etl',
  quality: 'settings.category.quality',
  retention: 'settings.category.retention',
  notify: 'settings.category.notify',
  security: 'settings.category.security',
  ops: 'settings.category.ops',
};
const ORDER = Object.keys(CATEGORIES);

/** S1–S5 kategoriyalari (kazna, banks, …) lug'atda bo'lmasa — kalit nomi. */
function categoryTitle(category: string): string {
  return Object.hasOwn(CATEGORIES, category) ? t(CATEGORIES[category] as MessageKey) : category;
}

export function SourceBadge({ source }: { source: string }) {
  if (source === 'panel') return <Badge tone="blue">{t('settings.source.panel')}</Badge>;
  if (source === 'env') return <Badge tone="warn">{t('settings.source.env')}</Badge>;
  return <Badge tone="neutral">{t('settings.source.default')}</Badge>;
}

export interface FieldEditorProps {
  setting: SettingOut;
  value: string;
  onChange(value: string): void;
  error?: string | undefined;
}

export function FieldEditor({ setting, value, onChange, error }: FieldEditorProps) {
  const label = setting.title;
  if (setting.kind === 'bool') {
    return <Checkbox label={label} checked={value === 'true'} onChange={(v) => onChange(String(v))} />;
  }
  if (setting.kind === 'list' || setting.kind === 'json') {
    return (
      <Field label={label} hint={setting.kind === 'list' ? t('settings.listHint') : undefined} error={error}>
        {({ id, describedBy, invalid }) => (
          <textarea id={id} className="input" rows={6} spellCheck={false} aria-describedby={describedBy} aria-invalid={invalid || undefined} value={value} onChange={(e) => onChange(e.target.value)} />
        )}
      </Field>
    );
  }
  const numeric = setting.kind === 'int' || setting.kind === 'float';
  return (
    <TextInput
      label={label}
      hint={numeric && !error ? rangeHint(setting) : undefined /* xato bo'lsa oraliq matni xatoda — takrorlanmasin */}
      inputMode={numeric ? 'decimal' : undefined}
      spellCheck={false}
      value={value}
      error={error}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function SettingsList({ perm }: { perm: string }) {
  const settings = useSettings();
  const [editing, setEditing] = useState<SettingOut | null>(null);
  if (settings.isError) return <ErrorBanner error={settings.error} lastSuccessAt={settings.dataUpdatedAt} onRetry={() => void settings.refetch()} />;
  if (settings.isPending) return <PageSkeleton />;
  const rows = settings.data.filter((s) => s.perm === perm);
  if (!rows.length) return <EmptyState title={t('settings.empty')} />;
  const rank = (c: string) => (ORDER.includes(c) ? ORDER.indexOf(c) : ORDER.length);
  const categories = [...new Set(rows.map((s) => s.category))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  const columns: Column<SettingOut>[] = [
    { key: 'name', header: t('settings.col.name'), align: 'left', wrap: true, cell: (s) => (<span className="cell-main"><b>{s.title}</b><small className="mono">{s.key}</small></span>) },
    { key: 'value', header: t('settings.col.value'), align: 'left', wrap: true, cell: (s) => <span className="mono">{displaySetting(s, s.value)}</span> },
    { key: 'source', header: t('settings.col.source'), align: 'left', cell: (s) => <SourceBadge source={s.source} /> },
    { key: 'version', header: t('settings.col.version'), cell: (s) => s.version || '—' },
    { key: 'updated', header: t('settings.col.updated'), cell: (s) => (s.updated_at ? formatDateTime(s.updated_at) : '—') },
  ];
  return (
    <>
      {categories.map((category) => (
        <Card key={category} title={categoryTitle(category)}>
          <Table caption={categoryTitle(category)} captionHidden columns={columns} rows={rows.filter((s) => s.category === category)} rowKey={(s) => s.key} onRowClick={(s) => setEditing(s)} free />
        </Card>
      ))}
      {editing ? <SettingDialog setting={editing} onClose={() => setEditing(null)} /> : null}
    </>
  );
}

type Errors = { value?: string; reason?: string; otp?: string };

function SettingDialog({ setting, onClose }: { setting: SettingOut; onClose(): void }) {
  const formId = useId();
  const toast = useToast();
  const update = useUpdateSetting();
  const history = useSettingHistory(setting.key);
  const [raw, setRaw] = useState(() => formatSetting(setting, setting.value));
  const [reason, setReason] = useState('');
  const [otp, setOtp] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const formRef = useFocusFirstInvalid(errors);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parseSetting(setting, raw);
    const next: Errors = {};
    if (!parsed.ok) next.value = parsed.error;
    if (setting.guarded && reason.trim().length < 5) next.reason = t('settings.reasonRequired');
    if (setting.step_up && !/^\d{6}$/.test(otp)) next.otp = t('settings.otpRequired');
    setErrors(next);
    if (!parsed.ok || Object.keys(next).length) return;
    update.mutate(
      {
        key: setting.key,
        body: {
          value: parsed.value,
          expected_version: setting.version,
          ...(setting.guarded ? { reason: reason.trim() } : {}),
          ...(setting.step_up ? { otp } : {}),
        },
      },
      {
        onSuccess: () => {
          toast.show(t('settings.saved'), 'success');
          onClose();
        },
        onError: (error) => {
          if (isApiError(error, 422) && Array.isArray(error.params.fields)) {
            const fields = error.params.fields as string[];
            setErrors({
              ...(fields.includes('value') ? { value: error.message } : {}),
              ...(fields.includes('reason') ? { reason: error.message } : {}),
              ...(fields.includes('otp') ? { otp: error.message } : {}),
            });
          }
        },
      },
    );
  };

  const inline = Boolean(errors.value || errors.reason || errors.otp);
  const historyColumns: Column<SettingVersionOut>[] = [
    { key: 'version', header: t('settings.col.version'), cell: (r) => r.version },
    { key: 'value', header: t('settings.col.value'), align: 'left', wrap: true, cell: (r) => <span className="mono">{displaySetting(setting, r.value)}</span> },
    { key: 'updated', header: t('settings.col.updated'), cell: (r) => formatDateTime(r.updated_at) },
  ];
  return (
    <Modal
      open
      onClose={onClose}
      title={t('settings.editTitle', { title: setting.title })}
      note={`${setting.key} · ${t('settings.defaultValue', { value: displaySetting(setting, setting.default) })}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form={formId} loading={update.isPending}>{t('common.save')}</Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit}>
        <div className="span-2"><FormError error={update.error && !inline ? update.error : null} /></div>
        <div className="span-2">
          <FieldEditor setting={{ ...setting, title: t('settings.value') }} value={raw} onChange={setRaw} error={errors.value} />
          <p className="field__hint">{setting.apply === 'next_run' ? t('settings.applyNextRun') : t('settings.applyLive')}</p>
        </div>
        {setting.guarded ? (
          <div className="span-2">
            <TextInput label={t('settings.reason')} hint={t('settings.reasonHint')} maxLength={500} value={reason} error={errors.reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        ) : null}
        {setting.step_up ? (
          <div className="span-2">
            <OtpInput label={t('settings.otp')} hint={t('settings.otpHint')} value={otp} onChange={setOtp} error={errors.otp} />
          </div>
        ) : null}
      </form>
      <section aria-label={t('settings.history')}>
        {history.isError ? (
          <ErrorBanner error={history.error} onRetry={() => void history.refetch()} />
        ) : history.data && history.data.length ? (
          <Table caption={t('settings.history')} columns={historyColumns} rows={history.data} rowKey={(r) => r.version} mobile="scroll" />
        ) : null}
      </section>
    </Modal>
  );
}
```
(`EmptyState`, `Badge` `tone` qiymatlari va `Table` `mobile` prop'i — 3-reja komponentlaridagi nomlar; farq qilsa mavjudiga moslang.)

`frontend/src/auth/passwordRules.ts` — `checkPassword(password: string, username: string, minLength = MIN_PASSWORD_LENGTH)` (`length: password.length >= minLength`), `passwordProblemText(code: string, minLength = MIN_PASSWORD_LENGTH)` — `too_short` uchun `t('password.problem.too_short', { n: minLength })`; `MIN_PASSWORD_LENGTH` izohi: «server standarti; haqiqiy qiymat — `me.password_min_length`». `PasswordChangePage.tsx`: `checkPassword(next, me.username, me.password_min_length)`, `passwordProblemText(code, me.password_min_length)`, `t('password.rule.length', { n: me.password_min_length })`.

- [ ] **Step 7: Testlar o'tishini tekshirish**

Run: `$NODE npm test -- src/admin src/auth && $NODE npm run typecheck && $NODE npm run lint`
Expected: barcha testlar passed, tsc va ESLint xatosiz.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Настройки» va «Политика безопасности» — tur bo'yicha muharrir, sabab, TOTP, tarix

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Frontend — «Интеграции» sahifasi (write-only sirlar, manba, ulanish tekshiruvi)

**Files:**
- Create: `frontend/src/admin/IntegrationsPage.tsx`
- Modify: `frontend/src/admin/api.ts`, `frontend/src/admin/registry.ts` (`integrations`), `frontend/src/i18n/ru.ts`
- Test: `frontend/src/admin/integrations.test.tsx`

**Interfaces:**
- Consumes: 5–6-vazifa endpointlari; `SourceBadge`, `FieldEditor` (9-vazifa), `parseSetting`, `formatSetting`, `displaySetting`, `PasswordInput`, `OtpInput`.
- Produces:
  - `useIntegrations()`, `useUpdateIntegration()` (`{ name, body: IntegrationUpdate }`), `useRequestCheck()` (`name → IntegrationCheckOut`), `useIntegrationCheck(id: number | null)` (2 s polling, `ok`/`failed` da to'xtaydi, fon so'rovi).
  - `IntegrationsPage` (default export): har integratsiya — `Card` (maydonlar jadvali, sirlar jadvali, «Проверить подключение», «Изменить»), tahrir dialogi: faqat o'zgargan maydonlar va kiritilgan/o'chirilgan sirlar yuboriladi; manzil maydoni o'zgarsa ogohlantirish.

- [ ] **Step 1: Muvaffaqiyatsiz testni yozish**

`frontend/src/admin/integrations.test.tsx`:
```tsx
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { IntegrationOut, SettingOut } from '../api/types';
import { expectNoAxeViolations } from '../test/axe';
import { json, mockApi } from '../test/mockApi';
import { renderWithProviders } from '../test/render';
import IntegrationsPage from './IntegrationsPage';

function field(key: string, title: string, kind: string, value: unknown, extra: Partial<SettingOut> = {}): SettingOut {
  return { key, title, kind, value, default: value, version: 0, updated_by: null, updated_at: null, source: 'env', category: 'integrations', perm: 'admin:integrations', guarded: true, step_up: true, apply: 'live', unit: '', lo: null, hi: null, ...extra };
}

const SMTP: IntegrationOut = {
  name: 'smtp',
  title: 'Почтовый сервер (SMTP)',
  check_in: 'worker',
  endpoint: ['smtp.host', 'smtp.port'],
  fields: [field('smtp.host', 'Сервер SMTP', 'str', 'relay.uge.uz'), field('smtp.port', 'Порт', 'int', 587, { lo: 1, hi: 65535 })],
  secrets: [{ name: 'smtp.password', title: 'Пароль SMTP', state: 'env', updated_at: null, updated_by: null }],
  last_check: null,
};

describe('IntegrationsPage', () => {
  it('shows secret state without a value and runs a connection check', async () => {
    const server = mockApi({
      'GET /admin/integrations': json([SMTP]),
      'POST /admin/integrations/smtp/check': json({ id: 7, name: 'smtp', status: 'pending', code: null, requested_at: '2026-10-26T05:00:00Z', finished_at: null }, 202),
      'GET /admin/integrations/checks/7': json({ id: 7, name: 'smtp', status: 'failed', code: 'auth_failed', requested_at: '2026-10-26T05:00:00Z', finished_at: '2026-10-26T05:00:05Z' }),
    });
    const { user, container } = renderWithProviders(<IntegrationsPage />);
    const card = await screen.findByRole('region', { name: 'Почтовый сервер (SMTP)' });
    expect(within(card).getByText('Из конфигурации сервера')).toBeInTheDocument();
    await expectNoAxeViolations(container);
    await user.click(within(card).getByRole('button', { name: 'Проверить подключение' }));
    expect(await within(card).findByText('Неверные учётные данные')).toBeInTheDocument();
    expect(server.calls.filter((c) => c.method === 'POST')).toHaveLength(1);
  });

  it('sends only changed fields, warns on endpoint change and never pre-fills the password', async () => {
    const server = mockApi({
      'GET /admin/integrations': json([SMTP]),
      'GET /admin/settings/smtp.host/history': json([]),
      'PUT /admin/integrations/smtp': json({ ...SMTP, secrets: [{ ...SMTP.secrets[0], state: 'none' }] }),
    });
    const { user } = renderWithProviders(<IntegrationsPage />);
    await user.click(await screen.findByRole('button', { name: 'Изменить' }));
    const dialog = screen.getByRole('dialog', { name: 'Интеграция: Почтовый сервер (SMTP)' });
    const password = within(dialog).getByLabelText('Пароль SMTP');
    expect(password).toHaveValue('');
    const host = within(dialog).getByLabelText('Сервер SMTP');
    await user.clear(host);
    await user.type(host, 'mail.uge.uz');
    expect(within(dialog).getByText('Адрес изменён: сохранённые учётные данные будут удалены, если не ввести новые.')).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Причина изменения'), 'Заявка ИТ-42');
    await user.type(within(dialog).getByLabelText('Код из приложения'), '654321');
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }));
    const put = server.calls.find((c) => c.method === 'PUT');
    expect(put?.body).toEqual({ values: { 'smtp.host': 'mail.uge.uz' }, secrets: {}, reason: 'Заявка ИТ-42', otp: '654321' });
  });
});
```

- [ ] **Step 2: Test yiqilishini tekshirish**

Run: `$NODE npm test -- src/admin/integrations.test.tsx`
Expected: FAIL — `Failed to resolve import "./IntegrationsPage"`.

- [ ] **Step 3: Matnlar, hook'lar, sahifa**

`frontend/src/i18n/ru.ts` — oxiriga:
```ts
  'integrations.fields': 'Параметры',
  'integrations.secrets': 'Учётные данные',
  'integrations.col.state': 'Состояние',
  'integrations.secret.panel': 'Задан в панели {time}',
  'integrations.secret.env': 'Из конфигурации сервера',
  'integrations.secret.none': 'Не задан',
  'integrations.edit': 'Изменить',
  'integrations.editTitle': 'Интеграция: {title}',
  'integrations.secretKeep': 'Оставьте пустым, чтобы не менять. Сохранённое значение не показывается.',
  'integrations.secretClear': 'Удалить сохранённое значение',
  'integrations.endpointWarning': 'Адрес изменён: сохранённые учётные данные будут удалены, если не ввести новые.',
  'integrations.check': 'Проверить подключение',
  'integrations.checking': 'Проверка подключения…',
  'integrations.saved': 'Интеграция сохранена. Изменение записано в журнал аудита.',
  'integrations.code.ok': 'Подключение успешно',
  'integrations.code.auth_failed': 'Неверные учётные данные',
  'integrations.code.tls_failed': 'Ошибка TLS (сертификат или протокол)',
  'integrations.code.timeout': 'Сервер не ответил вовремя',
  'integrations.code.connect_failed': 'Не удалось подключиться к серверу',
  'integrations.code.protocol_error': 'Ошибка протокола',
  'integrations.code.not_configured': 'Интеграция не настроена',
  'integrations.code.insecure_refused': 'Пароль не передаётся без шифрования',
  'integrations.code.not_supported': 'Проверка не поддерживается',
  'integrations.code.error': 'Внутренняя ошибка проверки',
```
`frontend/src/admin/api.ts` — `useUpdateSetting` dan keyin:
```ts
export function useIntegrations() {
  return useQuery({
    queryKey: adminKeys.integrations,
    queryFn: ({ signal }) => api<IntegrationOut[]>('/admin/integrations', { signal }),
    staleTime: 0,
  });
}

export function useUpdateIntegration() {
  const invalidate = useInvalidate(adminKeys.integrations);
  return useMutation({
    mutationFn: ({ name, body }: { name: string; body: IntegrationUpdate }) =>
      api<IntegrationOut>(`/admin/integrations/${encodeURIComponent(name)}`, { method: 'PUT', body }),
    onSuccess: invalidate,
    meta: { inline: true },
  });
}

export function useRequestCheck() {
  return useMutation({
    mutationFn: (name: string) => api<IntegrationCheckOut>(`/admin/integrations/${encodeURIComponent(name)}/check`, { method: 'POST' }),
    meta: { inline: true },
  });
}

const CHECK_DONE = new Set(['ok', 'failed']);

export function useIntegrationCheck(id: number | null) {
  return useQuery({
    queryKey: [...adminKeys.integrations, 'check', id],
    queryFn: ({ signal }) => api<IntegrationCheckOut>(`/admin/integrations/checks/${id ?? 0}`, { signal, background: true }),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data && CHECK_DONE.has(query.state.data.status) ? false : 2_000),
  });
}
```
`frontend/src/admin/registry.ts` — `integrations: lazy(() => import('./IntegrationsPage')),`.

`frontend/src/admin/IntegrationsPage.tsx`:
```tsx
import { useId, useState, type FormEvent } from 'react';
import { isApiError } from '../api/client';
import type { IntegrationCheckOut, IntegrationOut, SecretStatusOut, SettingOut } from '../api/types';
import { t, type MessageKey } from '../i18n';
import { formatDateTime } from '../i18n/format';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Checkbox, FormError, PasswordInput, TextInput } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { OtpInput } from '../ui/OtpInput';
import { PageSkeleton } from '../ui/Skeleton';
import { Table, type Column } from '../ui/Table';
import { useToast } from '../ui/Toast';
import { useIntegrationCheck, useIntegrations, useRequestCheck, useUpdateIntegration } from './api';
import { displaySetting, formatSetting, parseSetting } from './settingValue';
import { FieldEditor, SourceBadge } from './SettingsList';
import { useFocusFirstInvalid } from './useFocusFirstInvalid';

const CODES = ['ok', 'auth_failed', 'tls_failed', 'timeout', 'connect_failed', 'protocol_error', 'not_configured', 'insecure_refused', 'not_supported', 'error'];

function checkText(check: IntegrationCheckOut): string {
  if (check.status === 'pending' || check.status === 'running') return t('integrations.checking');
  const code = check.code ?? 'error';
  return CODES.includes(code) ? t(`integrations.code.${code}` as MessageKey) : code;
}

function secretText(s: SecretStatusOut): string {
  if (s.state === 'panel') return t('integrations.secret.panel', { time: s.updated_at ? formatDateTime(s.updated_at) : '' });
  return s.state === 'env' ? t('integrations.secret.env') : t('integrations.secret.none');
}

export default function IntegrationsPage() {
  const list = useIntegrations();
  const [editing, setEditing] = useState<IntegrationOut | null>(null);
  if (list.isError) return <ErrorBanner error={list.error} lastSuccessAt={list.dataUpdatedAt} onRetry={() => void list.refetch()} />;
  if (list.isPending) return <PageSkeleton />;
  return (
    <>
      {list.data.map((integration) => (
        <IntegrationCard key={integration.name} integration={integration} onEdit={() => setEditing(integration)} />
      ))}
      {editing ? <IntegrationDialog integration={editing} onClose={() => setEditing(null)} /> : null}
    </>
  );
}

function IntegrationCard({ integration, onEdit }: { integration: IntegrationOut; onEdit(): void }) {
  const request = useRequestCheck();
  const [checkId, setCheckId] = useState<number | null>(null);
  const check = useIntegrationCheck(checkId);
  const status = check.data ?? integration.last_check;
  const fieldColumns: Column<SettingOut>[] = [
    { key: 'name', header: t('settings.col.name'), align: 'left', cell: (s) => s.title },
    { key: 'value', header: t('settings.col.value'), align: 'left', wrap: true, cell: (s) => <span className="mono">{displaySetting(s, s.value)}</span> },
    { key: 'source', header: t('settings.col.source'), align: 'left', cell: (s) => <SourceBadge source={s.source} /> },
  ];
  const secretColumns: Column<SecretStatusOut>[] = [
    { key: 'name', header: t('settings.col.name'), align: 'left', cell: (s) => s.title },
    { key: 'state', header: t('integrations.col.state'), align: 'left', cell: (s) => <Badge tone={s.state === 'none' ? 'neutral' : 'ok'}>{secretText(s)}</Badge> },
  ];
  return (
    <Card
      title={integration.title}
      actions={
        <>
          {integration.check_in === 'worker' ? (
            <Button variant="secondary" loading={request.isPending} onClick={() => request.mutate(integration.name, { onSuccess: (c) => setCheckId(c.id) })}>
              {t('integrations.check')}
            </Button>
          ) : null}
          <Button onClick={onEdit}>{t('integrations.edit')}</Button>
        </>
      }
    >
      <Table caption={t('integrations.fields')} columns={fieldColumns} rows={integration.fields} rowKey={(s) => s.key} free />
      <Table caption={t('integrations.secrets')} columns={secretColumns} rows={integration.secrets} rowKey={(s) => s.name} free />
      <FormError error={request.error} />
      {status ? (
        <p role="status">
          <Badge tone={status.status === 'ok' ? 'ok' : status.status === 'failed' ? 'neg' : 'blue'}>{checkText(status)}</Badge>
          {status.finished_at ? ` ${formatDateTime(status.finished_at)}` : null}
        </p>
      ) : null}
    </Card>
  );
}

function IntegrationDialog({ integration, onClose }: { integration: IntegrationOut; onClose(): void }) {
  const formId = useId();
  const toast = useToast();
  const update = useUpdateIntegration();
  const initial = Object.fromEntries(integration.fields.map((f) => [f.key, formatSetting(f, f.value)]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [clear, setClear] = useState<Record<string, boolean>>({});
  const [reason, setReason] = useState('');
  const [otp, setOtp] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const formRef = useFocusFirstInvalid(errors);
  const changed = integration.fields.filter((f) => values[f.key] !== initial[f.key]);
  const endpointChanged = changed.some((f) => integration.endpoint.includes(f.key));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    const body: { values: Record<string, unknown>; secrets: Record<string, string | null> } = { values: {}, secrets: {} };
    for (const f of changed) {
      const parsed = parseSetting(f, values[f.key] ?? '');
      if (parsed.ok) body.values[f.key] = parsed.value;
      else next[f.key] = parsed.error;
    }
    for (const s of integration.secrets) {
      if (clear[s.name]) body.secrets[s.name] = null;
      else if (secrets[s.name]) body.secrets[s.name] = secrets[s.name] ?? '';
    }
    if (reason.trim().length < 5) next.reason = t('settings.reasonRequired');
    if (!/^\d{6}$/.test(otp)) next.otp = t('settings.otpRequired');
    setErrors(next);
    if (Object.keys(next).length) return;
    update.mutate(
      { name: integration.name, body: { ...body, reason: reason.trim(), otp } },
      {
        onSuccess: () => {
          toast.show(t('integrations.saved'), 'success');
          onClose();
        },
        onError: (error) => {
          if (isApiError(error, 422) && Array.isArray(error.params.fields)) {
            setErrors(Object.fromEntries((error.params.fields as string[]).map((f) => [f, error.message])));
          }
        },
      },
    );
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={t('integrations.editTitle', { title: integration.title })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" form={formId} loading={update.isPending}>{t('common.save')}</Button>
        </>
      }
    >
      <form id={formId} ref={formRef} className="form-grid" noValidate onSubmit={submit} autoComplete="off">
        <div className="span-2"><FormError error={update.error && !Object.keys(errors).length ? update.error : null} /></div>
        {integration.fields.map((f) => (
          <div key={f.key} className="span-2">
            <FieldEditor setting={f} value={values[f.key] ?? ''} onChange={(v) => setValues((prev) => ({ ...prev, [f.key]: v }))} error={errors[f.key]} />
          </div>
        ))}
        {endpointChanged ? <p className="span-2 field__error" role="alert">{t('integrations.endpointWarning')}</p> : null}
        {integration.secrets.map((s) => (
          <div key={s.name} className="span-2">
            <PasswordInput
              label={s.title}
              hint={t('integrations.secretKeep')}
              autoComplete="new-password"
              value={secrets[s.name] ?? ''}
              disabled={clear[s.name] === true}
              error={errors[s.name]}
              onChange={(e) => setSecrets((prev) => ({ ...prev, [s.name]: e.target.value }))}
            />
            {s.state === 'panel' ? <Checkbox label={t('integrations.secretClear')} checked={clear[s.name] === true} onChange={(v) => setClear((prev) => ({ ...prev, [s.name]: v }))} /> : null}
          </div>
        ))}
        <div className="span-2">
          <TextInput label={t('settings.reason')} hint={t('settings.reasonHint')} maxLength={500} value={reason} error={errors.reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <div className="span-2">
          <OtpInput label={t('settings.otp')} hint={t('settings.otpHint')} value={otp} onChange={setOtp} error={errors.otp} />
        </div>
      </form>
    </Modal>
  );
}
```
(`Card` `section aria-labelledby` bilan `region` roli beradi — test shunga tayanadi.)

- [ ] **Step 4: Testlar o'tishini tekshirish**

Run: `$NODE npm test -- src/admin && $NODE npm run typecheck && $NODE npm run lint`
Expected: barcha testlar passed, xatosiz.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): «Интеграции» — write-only sirlar, manba holati, manzil ogohlantirishi, ulanish tekshiruvi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: E2E — sozlama tahriri va integratsiya siri haqiqiy stack'da

**Files:**
- Create: `frontend/e2e/specs/admin-settings.spec.ts`

**Interfaces:**
- Consumes: `signIn`, `adminFor`, `expectNoAxeViolations`, `E2E_TOTP_SECRET`, `totp` (3-reja E2E fixture'lari); 9–10-vazifa sahifalari.
- Produces: E2E: (1) «Настройки» — `freshness.max_age_hours` 6 → 7 → 6, tarixda versiyalar; (2) «Интеграции» — SMTP paroli sabab + keyingi TOTP qadami bilan saqlanadi, javob tanasida parol yo'q, holat «Задан в панели».

- [ ] **Step 1: E2E spec**

`frontend/e2e/specs/admin-settings.spec.ts`:
```ts
import { expect, test } from '@playwright/test';
import { adminFor, E2E_TOTP_SECRET, expectNoAxeViolations, signIn } from '../fixtures';
import { totp } from '../totp';

const SECRET = 'E2e-Relay-Pa55!';

test('admin: sozlama tahriri va integratsiya siri write-only', async ({ page }, info) => {
  test.setTimeout(120_000);
  await page.goto('/#admin/settings');
  await signIn(page, adminFor(info.project.name));
  await expect(page.getByRole('heading', { level: 1, name: 'Настройки' })).toBeVisible();
  await expectNoAxeViolations(page);

  // Umumiy kalit: faqat bitta loyihada (parallel loyihalar expected_version bilan 409 olmasin).
  if (info.project.name === 'desktop-1440') {
    for (const value of ['7', '6']) {
      await page.getByText('Порог устаревания данных витрины').click();
      const edit = page.getByRole('dialog', { name: 'Настройка: Порог устаревания данных витрины' });
      await edit.getByLabel('Значение').fill(value);
      await edit.getByRole('button', { name: 'Сохранить' }).click();
      await expect(edit).toBeHidden();
    }
    await page.getByText('Порог устаревания данных витрины').click();
    const history = page.getByRole('dialog').getByRole('table', { name: 'История изменений' });
    await expect(history).toContainText('7 ч');
    await page.getByRole('dialog').getByRole('button', { name: 'Отмена' }).click();
  }

  await page.goto('/#admin/integrations');
  const card = page.getByRole('region', { name: 'Почтовый сервер (SMTP)' });
  await card.getByRole('button', { name: 'Изменить' }).click();
  const dialog = page.getByRole('dialog', { name: 'Интеграция: Почтовый сервер (SMTP)' });
  await dialog.getByLabel('Пароль SMTP').fill(SECRET);
  await dialog.getByLabel('Причина изменения').fill('E2E: проверка панели');
  // Kirishda joriy qadam ishlatilgan — step-up keyingi qadam kodi bilan (server ±1 qadam qabul qiladi).
  await dialog.getByLabel('Код из приложения').fill(totp(E2E_TOTP_SECRET, Date.now() + 30_000));
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/v1/admin/integrations/smtp') && r.request().method() === 'PUT'),
    dialog.getByRole('button', { name: 'Сохранить' }).click(),
  ]);
  expect(response.status()).toBe(200);
  expect(await response.text()).not.toContain(SECRET);
  await expect(card.getByText(/Задан в панели/)).toBeVisible();
  await expect(page.getByText(SECRET)).toHaveCount(0);
});
```
(`smtp.host` bo'sh qoladi — notifier faol bo'lmaydi; har loyiha o'z admin foydalanuvchisi bilan, shuning uchun TOTP qadami to'qnashmaydi.)

- [ ] **Step 2: E2E'ni ishga tushirish**

Run: `bash scripts/e2e.sh`
Expected: barcha E2E spec'lar (yangi `admin-settings.spec.ts` ham, uchala kenglikda) passed.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e
git commit -m "test(e2e): admin sozlamalari va integratsiya siri (write-only) haqiqiy stack'da

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Ekspertiza hujjatlari, admin qo'llanmasi, spec 7.6 va yakuniy darvoza

**Files:**
- Modify: `docs/security/access-control.md`, `docs/security/secure-configuration.md`, `docs/security/audit-log.md`, `docs/security/asvs-l2.md`, `docs/security/data-classification.md`, `docs/security/key-management.md`, `docs/ops/admin-guide.md`, `docs/superpowers/specs/2026-09-24-poydevor-design.md` (7.6), `docs/superpowers/specs/2026-10-26-admin-settings-design.md` (holat)
- Test: mavjud `backend/tests/ops/test_docs.py` (havolalar va test nomlari), `make check`

**Interfaces:**
- Consumes: 1–11-vazifa test nomlari va yo'llari (hujjatlarda backtick ichida faqat mavjudlari).
- Produces: hujjatlar 04b holatini aks ettiradi; `make check` yashil.

- [ ] **Step 1: Kirish matritsasi**

`docs/security/access-control.md`, «## 3. Разрешения» jadvali — `admin:settings` qatorini almashtiring va undan keyin ikki qator qo'shing:
```markdown
| `admin:settings` | пороги «Требует внимания», допущения финмодели, настройки витрины, загрузок, качества данных и оповещений; OpenAPI в prod |
| `admin:security` | политика входа и сеансов, ограничения частоты запросов, срок хранения журнала аудита, пороги контроля эксплуатации; изменение — с причиной и кодом 2FA |
| `admin:integrations` | параметры и учётные данные внешних систем (SMTP и др.), проверка подключения; изменение — с причиной и кодом 2FA |
```
Jadvaldan keyingi «Гарантии» abzatsidan oldin:
```markdown
Новое разрешение, добавленное в код, один раз выдаётся существующей роли «Администратор»
(`test_new_permission_is_granted_to_admin_role_once`). Ключ каждой настройки проверяется на сервере:
`admin:settings` не даёт менять настройки безопасности (`test_settings_admin_cannot_change_security_key`).
```

- [ ] **Step 2: Xavfsiz konfiguratsiya**

`docs/security/secure-configuration.md` — «## 10. Правила разработки» dan OLDIN yangi bo'lim (keyingi bo'limlar raqami o'zgarmasligi uchun sarlavha — «## 9a»):
```markdown
## 9a. Настройки, управляемые из панели администратора

Значения политики хранятся в `core.settings` (версии, журнал аудита) и меняются в разделах
«Настройки», «Политика безопасности», «Интеграции» без перезапуска (до 30 секунд для других процессов,
расписания — до 60 секунд). Инфраструктура (ключи, пароли ролей СУБД, TLS, порты, сети, `ENV`) в панель
не выводится и меняется только оператором ОС.

| Настройка | По умолчанию | Допустимо | Кто меняет |
|---|---|---|---|
| Завершение сеанса при бездействии | 30 мин | 5–30 | `admin:security` |
| Максимальная длительность сеанса | 12 ч | 1–12 | `admin:security` |
| Срок действия пароля | 90 дн. | 30–90 | `admin:security` |
| Попыток входа до блокировки / блокировка | 5 / 15 мин | 3–5 / 15–1440 мин | `admin:security` |
| Минимальная длина пароля / история | 12 / 5 | 12–64 / 5–24 | `admin:security` |
| Попыток входа и 2FA с IP в минуту, запросов API пользователя | 10, 20, 300 | не выше значений по умолчанию | `admin:security` |
| Хранение журнала аудита / фактов | 12 мес. / 5 лет | ≥ 12 мес. / ≥ 5 лет | `admin:security` / `admin:settings` |

Ослабить политику относительно значений по умолчанию нельзя: граница проверяется при записи и при
чтении — недопустимое значение в базе игнорируется (`test_security_bounds_are_tighten_only`,
`test_invalid_panel_value_falls_back`, `test_weaker_panel_value_is_ignored`). Изменение настроек
безопасности и интеграций требует причины и текущего кода 2FA, повтор кода отклоняется
(`test_guarded_key_needs_reason_and_fresh_totp`, `test_step_up_rejects_replayed_code`).
Учётные данные интеграций хранятся зашифрованными (AES-256-GCM, назначение `integration_creds`), API
их не возвращает; смена адреса сервера удаляет сохранённый пароль
(`test_secret_is_encrypted_and_never_returned_or_audited`, `test_endpoint_change_clears_panel_secret`,
`test_env_secret_not_used_once_endpoint_is_set_in_panel`).
```
«## 10. Правила разработки» ro'yxatiga:
```markdown
14. Новая настройка — только запись `SettingDef` в `backend/app/core/sysconfig.py` (тип, границы,
    раздел, разрешение); новый секрет внешней системы — `SecretDef` в `backend/app/core/integrations.py`.
    Константы политики в коде и новые переменные окружения для неё не добавляются.
```

- [ ] **Step 3: Audit, ASVS, tasnif, kalitlar**

`docs/security/audit-log.md`, «## 1. Регистрируемые события» — `admin.alert_rule.updated…` qatoridan keyin:
```markdown
| `admin.integration.updated`, `admin.integration.check_requested` | изменение параметров и учётных данных интеграций (только факт «задан/удалён», без значения), запрос проверки подключения |
| `auth.step_up.failed` | неверный код 2FA при подтверждении изменения настройки |
```
`docs/security/asvs-l2.md` — 3.7.1 qatori:
```markdown
| 3.7.1 | Проверка перед чувствительными операциями | Частично | Смена пароля требует текущий пароль; изменение настроек безопасности и интеграций — причина и текущий код 2FA; прочие административные операции — в сессии с пройденной 2FA | `test_forced_password_change`, `test_guarded_key_needs_reason_and_fresh_totp` |
```
4.3.3 qatoridagi «Отдельные разрешения `admin:keys`, `audit:read`» → «Отдельные разрешения `admin:keys`, `admin:security`, `admin:integrations`, `audit:read`», tekshiruv ustuniga `test_settings_admin_cannot_change_security_key`.
`docs/security/data-classification.md`, «## 2. Элементы данных» — «Учётные данные интеграций» qatorini almashtiring:
```markdown
| Учётные данные интеграций | `core.integration_credentials.value_enc` | К1 | AES-256-GCM (`integration_creds`), только запись через API | worker, api (при использовании) | до смены или удаления в панели |
```
`docs/security/key-management.md`, «## 1. Реестр секретов» — `smtp_password` qatorini almashtiring:
```markdown
| `smtp_password` | учётная запись SMTP-релея (начальная настройка) | по политике почтовой службы | служба ИТ | Docker secret; после ввода в панели «Интеграции» — `core.integration_credentials` (AES-256-GCM), файл секрета очищается | worker | по политике организации |
```

- [ ] **Step 4: Admin qo'llanmasi va spec**

`docs/ops/admin-guide.md` — «## 10. Типовые обращения» dan oldin (`## 9a`):
```markdown
## 9a. Настройки, политика безопасности и интеграции

- «Настройки» (`admin:settings`): витрина, загрузки, обслуживание, качество данных, оповещения.
  «Источник»: «Панель» — задано здесь, «Конфигурация сервера» — из переменных окружения,
  «По умолчанию» — значение программы. Расписания применяются в течение минуты.
- «Политика безопасности» (`admin:security`): сеансы, блокировка, пароли, ограничения частоты, хранение
  журнала аудита, пороги `ops-check`. Значения можно только ужесточать. Сохранение требует причины
  (номер заявки или письма ИБ) и кода из приложения 2FA.
- «Интеграции» (`admin:integrations`): адрес, порт и учётные данные внешних систем. Пароль вводится и
  не показывается повторно; поле, оставленное пустым, не меняет сохранённое значение. Смена адреса
  удаляет сохранённый пароль — введите его заново. «Проверить подключение» выполняется сервером загрузок
  и показывает результат без подробностей ошибки. После ввода пароля в панели очистите соответствующий
  Docker secret ([../security/key-management.md](../security/key-management.md)).
- Каждое изменение — новая версия (история в карточке настройки) и событие журнала аудита.
```
`docs/superpowers/specs/2026-09-24-poydevor-design.md`, 7.6 «Admin:» qatori oxiriga: «, Настройки, Политика безопасности, Интеграции (04b-reja)». `docs/superpowers/specs/2026-10-26-admin-settings-design.md` — «Holat: tasdiqlashga» → «Holat: bajarildi».

- [ ] **Step 5: Yakuniy tekshiruv**

Run: `$TEST pytest tests/ops/test_docs.py -v && make check`
Expected: `test_docs.py` passed; `make check` — ruff, mypy, bandit, pytest (qamrov darvozasi), frontend testlari, lint va skanerlar xatosiz.

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs(security): panel sozlamalari — kirish matritsasi, xavfsiz konfiguratsiya, audit, ASVS, admin qo'llanmasi

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
