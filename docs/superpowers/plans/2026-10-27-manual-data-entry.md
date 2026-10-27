# UGEKAZNA «Ввод данных» — qo'lda kiritish va fayldan yuklash — implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vakolatli foydalanuvchi 1C bermaydigan yozuvlarni (qoldiqlar, to'lov rejasi, qarzdorlik, maqsadli mablag'lar, kreditlar, ishlab chiqarish rejasi, АИП, штат) formada, jadvalda (oy × qator) yoki kanonik CSV/XLSX shablon orqali kiritadi; ikkinchi shaxs tasdiqlagach yozuvlar mavjud ETL pipeline'i orqali versiya, audit va rollback bilan витринага chiqadi.

**Architecture:** Yozuvlar `core.manual_batch` (paket, maker–checker) / `core.manual_head` (biznes-kalit, optimistik qulf) / `core.manual_entry` (append-only versiyalar, sezgir maydon AES-256-GCM) jadvallariga `ugk_app` orqali RLS FORCE ostida yoziladi. Tasdiq `core.etl_requests (source='manual', mode='full')` navbatiga so'rov qo'yadi; worker `Runner(ManualConnector)` bilan stg → merge (`src_system='manual'` to'liq almashtiriladi) → agregatlar → sifat → publish. Agregatlar `dwh.*_effective` view'laridan o'qiydi — don darajasida tizim manbai qo'lda yozuvdan, qo'lda yozuv sintetikdan ustun. Obyektlar Python reyestrida (`app/manual/entities.py`, har biri bitta 2-reja `Target` ga moslanadi), API `/api/v1/data/*`, frontend markaziy «Ввод данных» bo'limi (metadata asosidagi umumiy forma, jadval muharriri, import, tarix, «На согласовании»).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (sync) + psycopg 3, pydantic 2, openpyxl 3.1 (mavjud), PostgreSQL 16, Redis 7, pytest; React 18 + TypeScript strict, TanStack Query 5, Vitest + Testing Library + axe, Playwright 1.49.1. Yangi bog'liqlik yo'q.

**Spec:** [docs/superpowers/specs/2026-10-27-manual-data-entry-design.md](../specs/2026-10-27-manual-data-entry-design.md). Asos (haqiqiy kod `demo/mvp` d9ecad9): 1-reja (`Ctx`, `AuthContext.assert_branch`, `require_perm`, `AuditAction`, `log_event`, `record`, `keystore.encrypt_str/decrypt_str`, `blind_index`, `reencrypt.REGISTRY`, `ratelimit.check`, `sync_reference`, `ROLE_SEEDS`, `section_perm`), 2-reja (`TARGETS`/`Target`, `DbStagingSink`, `merge_dims`/`merge_facts`, `Runner`, `make_connector`, `KNOWN_SOURCES`, `register(Aggregate)`, `build_all`, `builds.*`, `run_checks`, `process_requests`, `FileConnector._number/_iso_date`, `tests.etl_helpers.*`), 3-reja (qobiq, `createRegistry`, `Table`, `Drawer`, `Combobox`, `Field`, `Badge`, `Tabs`, `ConfirmDialog`, `useFocusFirstInvalid`, `parseDecimal/formatDecimal` (`src/admin/numbers.ts`), `mockApi`, `renderWithProviders`, `expectNoAxeViolations`, E2E `signIn`), 04b (`sysconfig.SettingDef`, `int_def`, `str_def`, `config_service` `expected_version` naqshi, `ConflictError("conflict_modified")`, `tests.helpers.put_setting`, `setting` fixture), S1 (`treasury_aggregates.py`, `DataState`, `src/dash/download.ts`, `tests.s1_helpers.rebuild/treasury_scenario`). S2–S4 1-to'plami qo'shilgan deb hisoblanadi; to'lqin 3–4 vazifalari S2/S3/S4 to'liq qo'shilgandan keyin.

## Global Constraints

- 1–4-rejalar va 04b ning barcha Global Constraints'lari amal qiladi: UTC, `/api/v1`, xato formati `{"error": {code, message, request_id, params?}}`, `TEST="docker compose -f deploy/compose.test.yml run --rm test"`, `NODE="docker compose -f deploy/compose.frontend.yml run --rm node"`, bind-mount'li `docker run` oldidan `MSYS_NO_PATHCONV=1`, buyruqlar repo ildizidan (`C:\Users\uge226\Desktop\ugekazna`) Git Bash'da; host'ga hech narsa o'rnatilmaydi.
- Ish alohida worktree'da (`../ugekazna-manual`, shoxobcha `feat/manual-entry`, S2–S4 1-to'plami qo'shilgan `demo/mvp` dan). Boshqa agentlarning worktree'lariga tegilmaydi.
- Migratsiyalar: `0022_manual_store`, `0023_manual_effective`, `0024_manual_object_stage`. `0022.down_revision` = shoxobcha boshlangandagi head (S5 qo'shilgan bo'lsa `"0021"`); integrator S-rejalar kabi qayta zanjirlaydi. Har migratsiyada `downgrade`.
- `dwh`/`mart` ga qo'lda kiritilgan ma'lumot faqat `ManualConnector` → `Runner` orqali tushadi. `ugk_app` ga `dwh` jadvallariga yozish huquqi berilmaydi; `ugk_etl` `core.manual_*` ni faqat o'qiydi.
- Qo'lda kiritiladigan fakt jadvallari (`fact_balance`, `fact_payment_plan`, `fact_debt`, `fact_target_funds`, `fact_loan_schedule`, `fact_generation`, `fact_energy_sales`, `fact_investment`, `fact_hr`, `fact_object_stage`) agregat (`app/dwh/*`), финмодель (`app/finmodel/*`) va sifat (`app/etl/quality.py`) kodida faqat `dwh.*_effective` orqali o'qiladi (9-vazifa kod qoidasi testi).
- Sezgir qiymat (bank hisob raqami, INN) API javobida, audit `details` da, log'da, `core.etl_error` da va xato matnida hech qachon yo'q; shifrlash faqat `keystore.encrypt_str(Purpose.BANK|Purpose.PII, plain, f"core.manual_entry.{bank_enc|pii_enc}:{id}")`.
- Ruxsat nomlari `data:<bo'lim>:write|approve`, bo'limlar faqat `DATA_SECTIONS = (kazna, kredity, proizvodstvo, investicii, kadry)`; ular `Perm` enum'iga kirmaydi.
- Xato kodlari (ruscha matn `app/core/errors.py` `MESSAGES`): `period_locked`, `reason_required`, `invalid_value`, `reference_not_found`, `reference_in_use`, `import_invalid`, `unsupported_file`, `batch_not_editable` (422, `params.fields`/`params.rows`), `duplicate_record`, `pending_change`, `conflict_modified` (409), `self_approval_forbidden` (403), `scope_violation` (403, mavjud).
- Chegaralar: bitta so'rovda ≤ 500 yozuv; import tanasi ≤ 1 MiB (mavjud `MAX_BODY_BYTES`), ≤ 5 000 qator, XLSX ZIP a'zolari ≤ 100, yechilgan ≤ 20 MiB; sabab/izoh 5..500 belgi; matn ≤ 200 belgi; rate limit `ratelimit.data_write_per_min` (60; 10..60), import 10 / 600 s.
- UI matnlari ruscha, faqat `t()` orqali (`src/i18n/ru.ts` oxiriga, `entry.*` kalitlari); reja prozasi va kod izohlari o'zbekcha. Hujjatlar `docs/security/*`, `docs/ops/*`, `docs/integration/*` — ruscha; backtick ichidagi har test nomi va yo'l mavjud bo'lishi shart (`backend/tests/ops/test_docs.py`).
- Credential fayllari (`deploy/secrets/`, `.env`, `secrets.php`, `auth.php`, `auth.js`, `apache-proxy.conf`, `gazna_bot/config.py`) ochilmaydi.
- Har commit xabari oxirida bo'sh qatordan keyin: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **O'zini tasdiqlash / vazifalar ajratilishi** — kirituvchi o'z paketini API orqali ham, `ugk_app` bilan to'g'ridan-to'g'ri SQL orqali ham tasdiqlay olmaydi: 6-vazifa `test_self_approval_forbidden_api`, 2-vazifa `test_self_approval_blocked_by_check`.
2. **Filial doirasi** — filial iqtisodchisi boshqa filial uchun paket yarata olmaydi, ko'rmaydi va `ugk_app` SQL bilan `INSERT` qila olmaydi: 2-vazifa `test_rls_with_check_blocks_foreign_branch`, 7-vazifa `test_foreign_branch_is_403_and_audited`.
3. **Ustuvorlik va regressiya** — qo'lda yozuv bo'lmasa `*_effective` = jadval; tizim qatori qo'lda yozuvni, qo'lda yozuv sintetikni yopadi; agregatlar ikki marta sanamaydi: 9-vazifa `test_effective_equals_table_without_manual`, `test_system_row_shadows_manual`, `test_manual_balance_reaches_kazna_svod`.
4. **Sezgir maydon sizishi** — hisob raqami javobda, auditda, log'da, `etl_error` da yo'q; staging'da qayta shifrlanadi: 5-vazifa `test_account_number_never_returned_or_audited`, 8-vazifa `test_connector_reencrypts_for_staging`.
5. **Yo'qolgan yangilanish va yopiq davr** — eskirgan `expected_version` 409; yopiq oyga yozish, yuborish va tasdiqlash 422: 5-vazifa `test_stale_expected_version_409`, 6-vazifa `test_approve_refused_when_period_locked_meanwhile`.

---

## Fayl tuzilishi

```
backend/app/auth/permissions.py, seed.py              data:<bo'lim>:write|approve, tizim rollariga bir marta (1)
backend/app/core/sysconfig.py, errors.py              manual.locked_through, ratelimit.data_write_per_min; xato kodlari (1)
backend/app/audit/service.py                          DATA_* harakatlari (1)
backend/migrations/versions/0022_manual_store.py      core.manual_{batch,head,entry}, RLS, triggerlar, grantlar, dim_bank.account_last4 (2)
backend/app/core/reencrypt.py                         REGISTRY += manual_entry.bank_enc/pii_enc (2)
backend/app/dwh/targets.py                            dim_bank.account_last4 (2)
backend/app/etl/codes.py                              bank_account_code, counterparty_code (3)
backend/app/manual/entities.py                        FieldDef, ManualEntity, ENTITIES (3, 12–16)
backend/app/manual/validate.py                        pydantic modellar, reference qidiruvi, davr, biznes-kalit (4)
backend/app/manual/store.py                           paket/bosh/versiya SQL, shifrlash, diff, content_hash (5)
backend/app/manual/approval.py                        approve/reject, SoD, nashr so'rovi (6)
backend/app/manual/schemas.py, router.py              /api/v1/data/* (7)
backend/app/etl/manual_connector.py, connectors.py    ManualConnector, KNOWN_SOURCES (8)
backend/migrations/versions/0023_manual_effective.py  dwh.*_effective, mart|pub.agg_manual_shadow (9, 10)
backend/app/dwh/aggregates.py, treasury_aggregates.py, (S2–S5 agregat modullari), app/etl/quality.py   *_effective (9, 13–16)
backend/app/dwh/manual_aggregates.py                  agg_manual_shadow (10)
backend/app/manual/imports.py                         CSV/XLSX parse, shablon (11)
backend/app/meta/menu.py                              «Ввод данных» bo'limi (17)
backend/migrations/versions/0024_manual_object_stage.py   object_stage_effective (15)
backend/tests/manual_helpers.py, test_manual_*.py     testlar
frontend/src/entry/{api.ts,fields.ts,EntityPage.tsx,RecordDrawer.tsx,GridEditor.tsx,ImportDialog.tsx,HistoryDrawer.tsx,BatchPage.tsx,entry.css}
frontend/src/sections/vvod/{_page.tsx,inbox.tsx,batches.tsx}, src/sections/registry.ts (fallback), src/i18n/ru.ts
frontend/src/dash/DataState.tsx (entry havolasi)
frontend/e2e/specs/manual-entry.spec.ts
docs/security/{access-control,threat-model,data-classification,audit-log,asvs-l2,cryptography,secure-configuration}.md,
  docs/ops/{user-guide,admin-guide}.md, docs/integration/vvod-dannyh.md
```

## Bajarilish tartibi va MVP

| To'lqin | Shart | Vazifalar |
|---|---|---|
| 1 — **MVP (tez demo)** | S2–S4 1-to'plami `demo/mvp` da | **1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 18, 20, 23a** |
| 1+ | MVP'dan keyin darhol | 10 (perekryto holati), 19 (jadval muharriri), 11 + 21 (import) |
| 2 | S2 6 va 8-vazifalari qo'shilgan | 12 (kazna qolgani), 13 (kredity) |
| 3 | S3, S4 to'liq qo'shilgan | 14, 15, 16, 22 |
| 4 | hammasi | 23b, 24 |

MVP demo ssenariysi: «Специалист казначейства» bank hisobini va oy oxiri qoldig'ini kiritadi, to'lov rejasi qatorini
qo'shadi → «Отправить на согласование»; «Начальник отдела» «На согласовании» da tasdiqlaydi → ≤ 1 daqiqada
«Казначейство / Сводка» va «Исполнение платежей» yangi qiymatlarni ko'rsatadi; «История изменений» va audit jurnali.
MVP'da jadval muharriri yo'q (to'lov rejasi qatorma-qator forma bilan), import yo'q, «Перекрыто» belgisi yo'q.

## S-rejalarga tuzatishlar (ishlayotgan agentlar brifiga qo'shiladi; S-reja matnlari o'zgartirilmaydi)

- **S2 6-vazifa** (`dwh.cashflow_effective`, sifat 2 istisnosi): istisno ro'yxatini `_UNVERIFIABLE_SQL` ga qo'shimcha
  `UNION` sifatida yozing (9-vazifa xuddi shu joyga `manual_balance` sababini qo'shadi) — sababi `reason` ustunida.
- **S2 8-vazifa** (`BankFileConnector`): `BA-`/`CP-` kodlari `app.etl.codes.bank_account_code` / `counterparty_code`
  dan (3-vazifa yaratadi; S2 oldin bajarilsa — S2 o'z funksiyasini shu modulga qo'yadi, 3-vazifa uni qayta
  ishlatadi); `dim_bank.account_last4` ni to'ldiring (0022 dan keyin).
- **S2 13, S3 14, S4 17** (kanonik fayl hujjatlari): «Загрузка через интерфейс: Ввод данных → Загрузить из файла»
  bandi — ustunlar bir xil, fayl ops inbox'iga emas, UI orqali.
- **S2 14–15, S3 15–17, S4 18–21** (frontend): «Источник не подключён» kartalarida o'zgarish yo'q; 22-vazifa
  `DataState` ga `entry` prop'ini qo'shadi va sahifalarga bir joyda ulaydi.
- **S2–S5 yangi agregat/finmodel/sifat kodi**: ro'yxatdagi `dwh.fact_*` ni to'g'ridan-to'g'ri o'qimang — 9-vazifa
  qo'shilgandan keyin `test_manual_facts_read_via_effective_views` buni ushlaydi; undan oldin yozilgan kod 9/13–16
  vazifalarda mexanik almashtiriladi.

---

### Task 1: Ruxsatlar, sozlamalar, audit harakatlari, xato kodlari [MVP]

**Files:**
- Modify: `backend/app/auth/permissions.py`, `backend/app/auth/seed.py`, `backend/app/core/sysconfig.py`, `backend/app/core/errors.py`, `backend/app/audit/service.py`, `backend/app/core/ratelimit.py`
- Test: `backend/tests/test_manual_perms.py`, `backend/tests/test_identity_seed.py` (yangi holat)

**Interfaces:**
- Produces:
  - `app.auth.permissions`: `DATA_SECTIONS: tuple[Section, ...] = (KAZNA, KREDITY, PROIZVODSTVO, INVESTICII, KADRY)`, `data_perm(section: Section, action: Literal["write","approve"]) -> str` (`"data:kazna:write"`), `PERMISSIONS` += 10 ta (`«Ввод данных „Казначейство“: ввод и изменение»`, `«…: согласование»`); `ROLE_SEEDS`: `spec_kazna` += kazna/kredity write, `economist_filiala` += kazna/proizvodstvo/kadry write, `nach_otdela` += 5 ta approve. Admin seed o'zgarmaydi (`Perm` ga kirmaydi).
  - `app.auth.seed.sync_reference`: kodga yangi qo'shilgan ruxsat **har tizim roliga** (`is_system`, seed'ida shu ruxsat bor) bir marta beriladi (admin qoidasi umumlashadi); bo'sh bazada xulq o'zgarmaydi.
  - `sysconfig`: `manual.locked_through` (`str_def`, `^(\d{4}-(0[1-9]|1[0-2]))?$`, standart `""`, kategoriya `data`, `guarded=True`, `apply="live"`, title «Ввод данных: закрыт период по (ГГГГ-ММ)»), `ratelimit.data_write_per_min` (`int_def` 60; 10..60, `admin:security`, guarded — faqat qattiqlashtiriladi).
  - `ratelimit.data_write_per_user() -> Limit` (60 s oyna), `DATA_IMPORT_PER_USER = Limit(10, 600)`.
  - `AuditAction`: `DATA_BATCH_SAVED = "data.batch.saved"`, `DATA_BATCH_SUBMITTED`, `DATA_BATCH_APPROVED`, `DATA_BATCH_REJECTED`, `DATA_BATCH_WITHDRAWN`, `DATA_IMPORTED = "data.imported"`.
  - `MESSAGES`: Global Constraints'dagi yangi kodlar (masalan `period_locked`: «Период закрыт для изменений», `self_approval_forbidden`: «Нельзя согласовать собственный пакет», `pending_change`: «По записи уже есть изменение на согласовании», `duplicate_record`: «Такая запись уже существует»).

- [ ] **Step 1: Failing testlar**

`backend/tests/test_manual_perms.py`:
```python
from app.auth.permissions import ADMIN_ROLE, PERMISSIONS, ROLE_SEEDS, Section, data_perm


def test_data_perms_generated_and_not_given_to_admin() -> None:
    perms = {data_perm(s, a) for s in (Section.KAZNA, Section.KADRY) for a in ("write", "approve")}
    assert perms <= set(PERMISSIONS)
    admin = next(r for r in ROLE_SEEDS if r.code == ADMIN_ROLE)
    assert not any(p.startswith("data:") for p in admin.permissions)


def test_seeded_roles() -> None:
    by = {r.code: r.permissions for r in ROLE_SEEDS}
    assert "data:kazna:write" in by["spec_kazna"] and "data:kazna:approve" not in by["spec_kazna"]
    assert {"data:kazna:approve", "data:kadry:approve"} <= by["nach_otdela"]
```
`test_identity_seed.py` ga: mavjud bazada `spec_kazna` rolidan `data:kazna:write` ni o'chirib, `PERMISSIONS` dan vaqtincha olib tashlab (monkeypatch) `sync_reference` → qaytarib qo'shib `sync_reference` → rolda bor; yana olib tashlab `sync_reference` → qayta **qo'shilmaydi** (`test_fresh_perm_granted_once_to_system_roles`). Sozlama testlari: `test_locked_through_validation` (`"2026-13"` rad, `""` qabul), `test_data_write_limit_only_tightens`.

- [ ] **Step 2: Run** `$TEST pytest tests/test_manual_perms.py tests/test_identity_seed.py tests/test_sysconfig.py -q` — Expected: FAIL (`ImportError: data_perm`).
- [ ] **Step 3: Implementatsiya** — yuqoridagi interfeyslar; `sync_reference` dagi `fresh` hisobini har `seed` uchun takrorlang: `for seed in ROLE_SEEDS: for perm in sorted(fresh & seed.permissions): insert … ON CONFLICT DO NOTHING` (admin uchun mavjud `ADMIN_GUARANTEED` qatori saqlanadi).
- [ ] **Step 4: Run** — testlar PASS; `$TEST pytest -q tests/test_route_guards.py tests/test_admin_api.py` PASS; `$TEST ruff check app tests && $TEST mypy app` xatosiz.
- [ ] **Step 5: Commit** `git commit -m "feat(manual): data:<bo'lim>:write|approve ruxsatlari, davr yopish va rate-limit sozlamalari, audit harakatlari"`

---

### Task 2: Migratsiya 0022 — manual ombor, RLS, triggerlar, grantlar [MVP]

**Files:**
- Create: `backend/migrations/versions/0022_manual_store.py`
- Modify: `backend/app/core/reencrypt.py` (REGISTRY), `backend/app/dwh/targets.py` (`dim_bank` ustunlariga `account_last4`), `backend/tests/conftest.py` (`_reset_core` — yangi jadvallar)
- Test: `backend/tests/test_manual_store_schema.py`

**Interfaces:**
- Produces (DDL):
  - `core.manual_batch (batch_id bigserial PK, entity varchar(48) NOT NULL, branch_id int NOT NULL REFERENCES dwh.dim_branch, status varchar(10) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','rejected','withdrawn')), origin varchar(8) NOT NULL CHECK (origin IN ('form','grid','import')), file_name varchar(200), file_sha256 bytea, rows int NOT NULL DEFAULT 0, reason varchar(500), created_by bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), submitted_at timestamptz, decided_by bigint, decided_at timestamptz, decision_comment varchar(500), content_hash bytea, version int NOT NULL DEFAULT 1, etl_request_id bigint, CHECK (decided_by IS NULL OR decided_by <> created_by))`; indekslar `(status, batch_id) WHERE status = 'submitted'`, `(created_by, batch_id DESC)`.
  - `core.manual_head (entry_id bigserial PK, entity varchar(48) NOT NULL, branch_id int NOT NULL, business_key varchar(200) NOT NULL, code varchar(32), approved_version int, approved_deleted boolean NOT NULL DEFAULT false, pending_batch_id bigint REFERENCES core.manual_batch, version int NOT NULL DEFAULT 0, updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (entity, business_key))`; `UNIQUE (code) WHERE code IS NOT NULL`.
  - `core.manual_entry (id bigserial PK, entry_id bigint NOT NULL REFERENCES core.manual_head, version int NOT NULL CHECK (version > 0), batch_id bigint NOT NULL REFERENCES core.manual_batch, branch_id int NOT NULL, payload jsonb NOT NULL, bank_enc bytea, pii_enc bytea, masks jsonb NOT NULL DEFAULT '{}', deleted boolean NOT NULL DEFAULT false, created_by bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (entry_id, version))`; indeks `(batch_id)`.
  - RLS: uchala jadvalda `ENABLE` + `FORCE`, `CREATE POLICY branch_scope … USING (core.rls_branch_ok(branch_id)) WITH CHECK (core.rls_branch_ok(branch_id))`.
  - `core.manual_entry_guard()` (BEFORE UPDATE OR DELETE): UPDATE — faqat `to_jsonb(OLD) - '{bank_enc,pii_enc}' = to_jsonb(NEW) - '{bank_enc,pii_enc}'` (reencrypt); DELETE — faqat paket `draft` bo'lsa; aks holda `check_violation`.
  - `core.manual_batch_guard()` (BEFORE UPDATE): ruxsat etilgan o'tishlar `draft→submitted|withdrawn`, `submitted→approved|rejected|withdrawn`, `X→X` (faqat `version`, `rows`, `reason`, `etl_request_id` o'zgaradi); yakuniy holatdan chiqish yo'q.
  - Grantlar: `ugk_app` — `SELECT, INSERT` uchala jadvalga; `UPDATE (status, rows, reason, submitted_at, decided_by, decided_at, decision_comment, content_hash, version, etl_request_id)` paketga; `UPDATE (approved_version, approved_deleted, pending_batch_id, version, updated_at, code)` boshga; `UPDATE (bank_enc, pii_enc), DELETE` versiyaga; sequence'lar. `ugk_etl` — `SELECT` uchala jadvalga. `ugk_app` ga ustun darajasidagi `SELECT`: `dwh.dim_bank (bank_id, code, bank_name, currency, account_last4)`, `dwh.dim_counterparty (cp_id, code, name, kind)`, `dwh.dim_contract (contract_id, code, number, contract_date, branch_id, cp_id, amount, end_date, kind, object_id)`, `dwh.dim_loan (loan_id, code, branch_id, creditor, project, currency)`, `dwh.dim_source`, `dwh.dim_object (object_id, code, name)`, `dwh.dim_position (pos_id, code, category)`, `dwh.dim_nomenclature (nom_id, code, name)` (`*_enc/*_bidx` — yo'q).
  - `ALTER TABLE dwh.dim_bank ADD COLUMN account_last4 varchar(4) CHECK (account_last4 ~ '^[0-9]{4}$')`.
  - `reencrypt.REGISTRY` += `EncryptedColumn("core.manual_entry", "id", "bank_enc", Purpose.BANK, "app")`, `EncryptedColumn("core.manual_entry", "id", "pii_enc", Purpose.PII, "app")`.

- [ ] **Step 1: Failing test** — `backend/tests/test_manual_store_schema.py`:
```python
def _as_app(branch_ids: frozenset[int] | None): ...  # ugk_app ulanishi + apply_rls (test_rls_structure naqshi)

def test_rls_with_check_blocks_foreign_branch(make_user) -> None:
    with _as_app(frozenset({2})) as s:
        with pytest.raises(DBAPIError):  # new row violates row-level security policy
            s.execute(text("INSERT INTO core.manual_batch (entity, branch_id, origin, created_by) "
                           "VALUES ('kazna.balance', 3, 'form', 1)"))

def test_self_approval_blocked_by_check() -> None:
    # draft → submitted, keyin decided_by = created_by bilan approved → check_violation
    ...

def test_entry_append_only_except_reencrypt() -> None:
    # submitted paketdagi versiyada payload UPDATE → xato; bank_enc UPDATE → ok; DELETE → xato
    ...

def test_draft_entry_can_be_deleted() -> None: ...
def test_etl_reads_but_cannot_write() -> None:  # ugk_etl INSERT → permission denied
    ...
```
`tests/test_reencrypt_registry.py` yangi `*_enc` ustunlarni avtomatik qamraydi (o'zgarishsiz PASS bo'lishi kerak); `tests/test_rls_structure.py` — `core.manual_*` ni FORCE RLS ro'yxatiga qo'shing.
- [ ] **Step 2: Run** `$TEST pytest tests/test_manual_store_schema.py -q` — FAIL (`relation "core.manual_batch" does not exist`).
- [ ] **Step 3: Migratsiya** — 0007 `STATEMENTS` naqshi (raw SQL ro'yxati, `upgrade`/`downgrade`), `downgrade` teskari tartibda `DROP`; `targets.py` — `_dim("dim_bank", ("code", "bank_name", "account_enc", "account_bidx", "currency", "account_last4"), …)`.
- [ ] **Step 4: Run** — `$TEST pytest tests/test_manual_store_schema.py tests/test_reencrypt_registry.py tests/test_rls_structure.py tests/test_dwh_dims.py -q` PASS; `$TEST alembic downgrade -1 && $TEST alembic upgrade head` xatosiz.
- [ ] **Step 5: Commit** `feat(manual): 0022 — core.manual_{batch,head,entry}, RLS FORCE, append-only va SoD triggerlari, o'lchov ustunlariga SELECT`

---

### Task 3: Obyekt reyestri, kod funksiyalari va MVP obyektlari [MVP]

**Files:**
- Create: `backend/app/manual/__init__.py`, `backend/app/manual/entities.py`, `backend/app/etl/codes.py`
- Test: `backend/tests/test_manual_entities.py`

**Interfaces:**
- Produces:
  - `app.etl.codes`: `bank_account_code(account: str) -> str` (`"BA-" + HMAC(blind_index_key, "account", normalize)[:16]`, S2 sxemasi), `counterparty_code(inn: str) -> str` (9 xonali → `CP-<16>`, aks holda `ValueError`), `normalize_account(s) -> str` (faqat raqamlar).
  - `app.manual.entities`:
    ```python
    FieldKind = Literal["money", "volume", "int", "decimal", "pct", "date", "month", "text", "enum", "ref", "secret"]

    @dataclass(frozen=True, slots=True)
    class FieldDef:
        name: str            # Target payload kaliti (canonical CSV ustuni), masalan "bank_code"
        kind: FieldKind
        title: str           # ruscha
        required: bool = True
        lo: Decimal | None = None
        hi: Decimal | None = None
        options: tuple[tuple[str, str], ...] = ()   # enum: (kod, ruscha nom)
        ref: str | None = None   # dim nomi ("dim_bank") — reference tanlovi
        purpose: Purpose | None = None  # secret: BANK yoki PII
        pattern: str | None = None
        unit: str = ""

    @dataclass(frozen=True, slots=True)
    class ManualEntity:
        id: str                  # "kazna.balance"
        section: Section
        title: str
        target: str              # TARGETS kaliti
        doc_type: str | None     # faktlar uchun; dim → None
        fields: tuple[FieldDef, ...]
        grain: tuple[str, ...]   # biznes-kalit maydonlari (fakt: oy/sana maydoni bilan)
        code_prefix: str | None = None   # dim: "M-CT"; None → code_fn
        code_fn: Callable[[Mapping[str, Any]], str] | None = None
        layout: Literal["form", "grid"] = "form"
        grid: tuple[str, str, str] | None = None   # (qator maydoni, ustun maydoni "month", qiymat maydoni)
        future_days: int = 0     # fakt sanasi bugundan qancha keyin bo'lishi mumkin

        @property
        def kind(self) -> Literal["dim", "fact"]: ...   # TARGETS[target].kind

    ENTITIES: dict[str, ManualEntity]
    MANUAL_TARGETS: frozenset[str]          # fakt + dim maqsadlari
    def business_key(entity: ManualEntity, values: Mapping[str, Any]) -> str: ...  # "<grain1>|<grain2>|…", oy → YYYYMM
    def payload_for_target(entity, values, *, entry_id: int, code: str | None) -> dict[str, Any]: ...
    ```
  - MVP obyektlari: `kazna.bank_account` (`dim_bank`; maydonlar `branch_code` (filial — doira uchun, `dim_bank`ga yozilmaydi: `payload_for_target` uni tashlaydi), `bank_name` enum (S2 5 ta bank nomi), `account_number` secret `Purpose.BANK` pattern `^[0-9]{20}$`, `currency` enum (`UZS`, `USD`, `EUR`, `RUB`, `CNY`, `JPY`), `account_last4` — hosila; `code_fn = bank_account_code(account_number)`; grain `("code",)`), `kazna.balance` (`fact_balance`, `doc_type="manual_balance"`; `branch_code`, `bank_code` ref `dim_bank`, `date` date, `balance` money (manfiy mumkin, |x| ≤ 10¹⁵); grain `("branch_code", "bank_code", "date:month")`), `kazna.payment_plan` (`fact_payment_plan`, `doc_type="manual_plan"`; `branch_code`, `item_code` ref `dim_item` (faqat `direction = out`), `date` month, `amount` money ≥ 0; grain `("branch_code", "item_code", "date:month")`; `layout="grid"`, `grid=("item_code", "date", "amount")`).

- [ ] **Step 1: Failing test** — `backend/tests/test_manual_entities.py`:
```python
@pytest.mark.parametrize("entity", list(ENTITIES.values()), ids=lambda e: e.id)
def test_fields_map_to_target_keys(entity: ManualEntity) -> None:
    target = TARGETS[entity.target]
    allowed = target.allowed_keys | {"branch_code", "account_last4"}
    assert {f.name for f in entity.fields} <= allowed | {"date"}
    assert {g.split(":")[0] for g in entity.grain} <= {f.name for f in entity.fields} | {"code"}
    secrets = {f.name for f in entity.fields if f.kind == "secret"}
    assert secrets == {s.field for s in target.sensitive}


def test_business_key_month_grain() -> None:
    e = ENTITIES["kazna.balance"]
    a = business_key(e, {"branch_code": "B1", "bank_code": "BA-x", "date": date(2026, 9, 30)})
    b = business_key(e, {"branch_code": "B1", "bank_code": "BA-x", "date": date(2026, 9, 1)})
    assert a == b == "B1|BA-x|202609"


def test_payload_has_manual_src_and_doc_type() -> None:
    p = payload_for_target(ENTITIES["kazna.balance"], {...}, entry_id=7, code=None)
    assert p["src_id"] == "M:7" and p["doc_type"] == "manual_balance" and "date_id" in p


def test_bank_account_code_matches_s2_scheme() -> None:
    assert bank_account_code("2020 8000 1234 5678 9012") == bank_account_code("20208000123456789012")
    assert bank_account_code("20208000123456789012").startswith("BA-")
```
- [ ] **Step 2: Run** — FAIL (`ModuleNotFoundError: app.manual`).
- [ ] **Step 3: Implementatsiya** — reyestr, `payload_for_target`: `date` → `date_id` (oy maydonida oyning 1-kuni; qoldiqda kiritilgan sana), `src_id = f"M:{entry_id}"`, `doc_type`; dim'da `code`; `branch_code` faqat `Target.lookups` da `branch_id` bo'lsa qoladi.
- [ ] **Step 4: Run** PASS; ruff/mypy.
- [ ] **Step 5: Commit** `feat(manual): obyekt reyestri (FieldDef/ManualEntity), BA-/CP- kodlari, MVP obyektlari`

---

### Task 4: Tekshiruv qatlami — modellar, reference'lar, davr, biznes-kalit [MVP]

**Files:**
- Create: `backend/app/manual/validate.py`
- Test: `backend/tests/test_manual_validate.py`

**Interfaces:**
- Consumes: `ENTITIES`, `sysconfig.current(conn, "manual.locked_through")`, `sysconfig.current(conn, "etl.history_start")`, `today_tashkent`, `FileConnector` raqam/sana qoidalari (`_number`, `_iso_date` → `app.etl.file_connector.parse_number/parse_iso_date` deb ommaviy qiling, eski nomlar taxallus).
- Produces:
  - `model_for(entity) -> type[BaseModel]` (`extra='forbid'`, har `FieldKind` → pydantic tur + chegara; `money` → `Decimal` `max_digits=20, decimal_places=2`; `month` → `date` 1-kunga normallashadi; `text` → ≤ 200, `^[^\x00-\x1f]*$`; `secret` → `SecretStr`, pattern).
  - `ItemErrors = list[{"row": int, "field": str, "code": str}]`.
  - `check_items(db: Session, ctx: AuthContext, entity, branch_id: int, items: Sequence[Mapping]) -> tuple[list[BaseModel], ItemErrors]` — model, sana oralig'i (`history_start`..bugun + `future_days`), davr yopiq (`period_locked`), reference mavjudligi (`dwh.<dim>.code` RLS ostida ∪ tasdiqlangan manual bosh `code`; draft/submitted havolasi — `reference_not_found`), filial `branch_code` = paket filiali, bitta so'rov ichida takroriy biznes-kalit (`duplicate_record`).
  - `assert_period_open(db, entity, values_list) -> None` (`ValidationFailed("period_locked", fields=[…])`) — 5/6-vazifalar submit va approve paytida qayta chaqiradi.
- [ ] **Step 1: Failing test** — `test_manual_validate.py`: `test_money_bounds_and_scale` (`12345.678` → `invalid_value`), `test_month_normalized`, `test_future_date_refused_for_balance`, `test_period_locked` (`setting("manual.locked_through", "2026-08")` → `2026-08-31` qoldig'i `period_locked`, `2026-09-01` — ok), `test_reference_must_exist_or_be_approved` (draft bank_account kodiga havola → `reference_not_found`), `test_text_control_chars_rejected`, `test_extra_field_forbidden`.
- [ ] **Step 2–4:** Run FAIL → implementatsiya → PASS (`$TEST pytest tests/test_manual_validate.py tests/test_file_connector.py -q`).
- [ ] **Step 5: Commit** `feat(manual): kiritish tekshiruvi — tur/chegara, sana oralig'i, yopiq davr, reference'lar`

---

### Task 5: Paket servisi — yaratish, draft, yuborish, qaytarib olish, shifrlash, audit [MVP]

**Files:**
- Create: `backend/app/manual/store.py`, `backend/tests/manual_helpers.py`
- Test: `backend/tests/test_manual_store.py`

**Interfaces:**
- Consumes: `check_items`, `assert_period_open`, `keystore.encrypt_str`, `log_event`, `ClientMeta`, `data_perm`, `ratelimit.check`.
- Produces (`app.manual.store`):
  - `ItemIn(entry_id: int | None, expected_version: int | None, values: dict, delete: bool = False)`.
  - `create_batch(db, ctx, meta, *, entity_id, branch_id, origin, items, submit=False, reason=None, file_meta=None) -> BatchOut` — ruxsat `write`, `ctx.assert_branch`, rate limit, tekshiruv; har yangi yozuvga `manual_head` (`INSERT … ON CONFLICT (entity, business_key) DO NOTHING` → mavjud bo'lsa va `entry_id` berilmagan bo'lsa 409 `duplicate_record`, `params.entry_id`); mavjud yozuvda `SELECT … FOR UPDATE`, `expected_version` ≠ `head.version` → 409 `conflict_modified`, `pending_batch_id` boshqa paket → 409 `pending_change`; versiya `head.version + 1`, `pending_batch_id = batch`; sezgir maydon: `id = nextval('core.manual_entry_id_seq')`, `bank_enc = encrypt_str(Purpose.BANK, plain, f"core.manual_entry.bank_enc:{id}")`, `masks = {"account_number": "…" + last4}`; `payload` da sezgir qiymat yo'q.
  - `update_batch(db, ctx, meta, batch_id, *, expected_version, items) -> BatchOut` — faqat yaratuvchi, `draft`; yozuvning draft versiyasi `DELETE` + `INSERT` (versiya raqami o'zgarmaydi); `delete: true` — draft'dan olib tashlash (yangi yozuv) yoki tombstone versiya (tasdiqlangan yozuv).
  - `submit_batch(db, ctx, meta, batch_id, *, expected_version, reason) -> BatchOut` — davr qayta tekshiriladi; tasdiqlangan yozuvni o'zgartirgan/o'chirgan bo'lsa `reason` majburiy (`reason_required`); `content_hash = sha256(canonical_json([(entry_id, version, deleted, payload, sha256(enc))…]))`; audit `DATA_BATCH_SUBMITTED` `{batch_id, entity, branch_id, rows, content_hash, changes[≤100]: {entry_id, version, op: add|change|delete, before, after}}` (sezgir maydon — `{"changed": true, "mask": "…1234"}`).
  - `withdraw_batch(...)` — yaratuvchi, `draft|submitted` → `withdrawn`, boshlarda `pending_batch_id = NULL`.
  - `get_batch(db, ctx, batch_id) -> BatchDetailOut` (diff tasdiqlangan versiyaga nisbatan), `list_batches(db, ctx, *, box, status, page)`.
  - Commit — servisda (`db.commit()` keyin audit — commit-then-audit, `etl_router` naqshi); muvaffaqiyatsiz amal `result="fail"` bilan audit.
  - `tests.manual_helpers`: `bank_account_item(tag)`, `balance_item(code, day, value)`, `plan_item(item_code, month, amount)`, `maker(branch_ids=())`, `checker()`.
- [ ] **Step 1: Failing test** — `test_manual_store.py`:
```python
def test_create_submit_records_versions_and_audit(db, make_user) -> None:
    maker = make_user("spec_kazna")
    batch = create_batch(db, ctx_of(maker), META, entity_id="kazna.bank_account", branch_id=1,
                         origin="form", items=[bank_account_item("t1")], submit=True)
    assert batch.status == "submitted" and batch.rows == 1
    ev = last_audit("data.batch.submitted")
    assert ev.details["content_hash"] and ev.details["changes"][0]["op"] == "add"


def test_account_number_never_returned_or_audited(db, make_user, caplog) -> None:
    plain = "20208000123456789012"
    batch = create_batch(..., items=[{"values": {..., "account_number": plain}}], submit=True)
    dumped = batch.model_dump_json() + json.dumps(all_audit_details()) + caplog.text
    assert plain not in dumped and "…9012" in batch.model_dump_json()
    blob = raw_entry(batch)  # migrator ulanishi
    assert plain.encode() not in blob.bank_enc and plain not in json.dumps(blob.payload)


def test_stale_expected_version_409(...) -> None: ...      # conflict_modified
def test_pending_change_409(...) -> None: ...              # boshqa paketda kutilayotgan yozuv
def test_duplicate_business_key_409(...) -> None: ...      # params.entry_id mavjud yozuvga
def test_reason_required_for_correction(...) -> None: ...
def test_withdraw_frees_entries(...) -> None: ...
def test_rate_limited(...) -> None: ...                     # ratelimit.data_write_per_min = 10, 11-so'rov 429
```
- [ ] **Step 2–4:** FAIL → implementatsiya → PASS.
- [ ] **Step 5: Commit** `feat(manual): paket servisi — draft/yuborish/qaytarib olish, optimistik qulf, sezgir maydon shifrlash, diff va content_hash auditi`

---

### Task 6: Tasdiqlash — approve/reject, SoD, doira, nashr so'rovi [MVP]

**Files:**
- Create: `backend/app/manual/approval.py`
- Test: `backend/tests/test_manual_approval.py`

**Interfaces:**
- Produces:
  - `approve_batch(db, ctx, meta, batch_id, *, expected_version, comment=None) -> BatchOut` — ruxsat `data:<bo'lim>:approve`, `ctx.assert_branch(batch.branch_id)`, `batch.created_by == ctx.user_id` → `ForbiddenError("self_approval_forbidden")` (audit `denied`), `status == 'submitted'`, `version` (409), `assert_period_open` (davr oraliqda yopilgan bo'lishi mumkin), qayta hisoblangan `content_hash` = saqlangan (aks holda 409 `conflict_modified` — mazmun o'zgargan); boshlar: `approved_version = entry.version`, `approved_deleted = entry.deleted`, `code` (dim), `pending_batch_id = NULL`; nashr so'rovi:
    ```sql
    SELECT pg_advisory_xact_lock(hashtext('ugk_manual_publish'));
    SELECT id FROM core.etl_requests WHERE source = 'manual' AND status = 'pending' ORDER BY id LIMIT 1;
    -- yo'q bo'lsa:
    INSERT INTO core.etl_requests (source, mode, requested_by) VALUES ('manual', 'full', :u) RETURNING id;
    ```
    `batch.etl_request_id` = shu id; audit `DATA_BATCH_APPROVED` `{batch_id, content_hash, etl_request_id}`.
  - `reject_batch(...)` — izoh majburiy (`reason_required`, `fields=["comment"]`), SoD xuddi shunday; boshlar bo'shatiladi; audit.
  - `publication_status(db, batch) -> Literal["none","queued","running","published","failed"]` + `build_id` — `core.etl_requests` va `core.etl_run` dan.
  - Reference o'chirish tasdig'ida bog'liq qo'lda faktlar bo'lsa (`payload->>'<ref>_code' = code` bo'lgan tasdiqlangan, o'chirilmagan bosh) → 422 `reference_in_use`.
- [ ] **Step 1: Failing test** — `test_manual_approval.py`: `test_self_approval_forbidden_api` (403, audit `denied`), `test_checker_outside_scope_403` (filial approver boshqa filial paketi), `test_approve_sets_heads_and_queues_one_request` (ikki paket ketma-ket tasdiqlansa — bitta `pending` so'rov), `test_new_request_when_previous_running`, `test_approve_refused_when_period_locked_meanwhile`, `test_reject_requires_comment`, `test_content_tamper_detected` (migrator bilan draft bo'lmagan versiya payload'ini trigger'ni o'chirmasdan o'zgartirib bo'lmaydi — trigger'ni vaqtincha `DISABLE` qilib o'zgartirish → approve 409), `test_reference_in_use`.
- [ ] **Step 2–4:** FAIL → implementatsiya → PASS.
- [ ] **Step 5: Commit** `feat(manual): maker–checker tasdig'i — SoD, doira, yopiq davr, mazmun xeshi, birlashtirilgan nashr so'rovi`

---

### Task 7: API `/api/v1/data/*` va tarix [MVP]

**Files:**
- Create: `backend/app/manual/schemas.py`, `backend/app/manual/router.py`
- Modify: `backend/app/main.py` (router), `backend/tests/test_route_guards.py` (`EXPECTED_ROUTES`)
- Test: `backend/tests/test_manual_api.py`

**Interfaces:**
- Produces: spec §5 jadvalidagi endpointlar (`template`/`import` — 11-vazifa). Router darajasida `require_perm(*ALL_DATA_PERMS, Perm.AUDIT_READ, any_of=True)` (`dependency.any_of` — route-guard testi ko'radi); obyekt ruxsati servisda. Schemalar `extra='forbid'`: `BatchIn {entity, branch_id, origin: Literal["form","grid"], items: list[ItemIn] (≤ 500), submit: bool = False, reason: str | None}`, `BatchUpdateIn`, `DecisionIn {expected_version: int, comment: str | None}`, `EntityOut {id, section, title, kind, layout, grid, fields: [FieldOut], can_write, can_approve}`, `RecordOut {entry_id, version, branch_id, values, masks, status: "active"|"pending"|"deleted", pending_batch_id, shadowed_by: str | None}`, `HistoryOut {versions: [{version, batch_id, batch_status, created_by_name, created_at, decided_by_name, decided_at, reason, deleted, values, masks}]}`, `BatchOut`, `BatchDetailOut {…, items: [{entry_id, op, before, after}], publication: {status, build_id}}`, `Page[T]`.
  - `GET data/entities/{e}/records` — `core.manual_head` ⋈ joriy versiya (tasdiqlangan yoki kutilayotgan), filtr `br`, `per` (davr oylari — `resolve_period`), sahifalash ≤ 500; `shadowed_by` 10-vazifagacha `None`.
  - `GET data/entities/{e}/options/{field}?q&br` — `ref` maydoni uchun `dwh.<dim>` (ustun grantlari) ∪ tasdiqlangan manual boshlar, `ILIKE` parametr bilan, ≤ 50.
  - `GET data/records/{entry_id}/history` — `write`/`approve` shu bo'lim yoki `audit:read`; foydalanuvchi ismi `core.users.full_name`.
- [ ] **Step 1: Failing test** — `test_manual_api.py` (TestClient + `login`): `test_entities_filtered_by_perms` (economist — faqat kazna/proizvodstvo/kadry obyektlari, `can_approve=False`), `test_full_form_flow_http` (POST submit → checker approve → `GET records` status `active`), `test_foreign_branch_is_403_and_audited` (economist `branch_id` = boshqa → 403 `scope_violation`, audit `security.rls_violation_attempt`), `test_csrf_required` (header'siz POST → 403 `csrf_failed`), `test_items_limit_500` (501 → 422), `test_history_masks_secret`, `test_options_respect_rls` (economist boshqa filial shartnomasini ko'rmaydi — 12-vazifadan keyin kengaytiriladi), `test_no_perm_403`.
- [ ] **Step 2–4:** FAIL → implementatsiya → PASS; `$TEST pytest tests/test_route_guards.py -q` PASS.
- [ ] **Step 5: Commit** `feat(manual): /api/v1/data — obyektlar, yozuvlar, paketlar, tasdiq, tarix; route guard'lar`

---

### Task 8: `ManualConnector` — pipeline'ga ulanish [MVP]

**Files:**
- Create: `backend/app/etl/manual_connector.py`
- Modify: `backend/app/etl/connectors.py` (`KNOWN_SOURCES += ("manual",)`, `make_connector`), `backend/app/cli.py` (`etl-run` yordam matnida `manual`)
- Test: `backend/tests/test_manual_connector.py`

**Interfaces:**
- Produces:
  ```python
  class ManualConnector:
      source = "manual"
      def healthcheck(self) -> HealthResult: return HealthResult(True, "manual")
      def watermark(self) -> Watermark: ...      # max(decided_at) approved paketlar
      def extract(self, window: Window, sink: StagingSink) -> ExtractStats:
          # etl_transaction() (scope_all): head.approved_version IS NOT NULL AND NOT approved_deleted
          # ⋈ manual_entry (entry_id, approved_version); dim'lar avval (DIM_TARGETS tartibida), keyin faktlar;
          # sezgir: keystore.decrypt_str(purpose, blob, f"core.manual_entry.{col}:{id}") → values[field]
          # fakt: window.contains_id(date_id) yoki TARGETS[t].forward va date_id > window.to_id
          # by_target = {t: n for t in MANUAL_TARGETS}  (0 ham) — to'liq almashtirish
      def control_totals(self, window: Window) -> None: return None
  ```
  Worker o'zgarmaydi (`process_requests` → `make_connector("manual")`, `Mode.FULL`; faqat `file+full` rad etiladi).
- [ ] **Step 1: Failing test** — `test_manual_connector.py`:
```python
def test_approved_rows_reach_dwh_and_deleted_leave(db, make_user) -> None:
    acc = approve(create_batch(..., "kazna.bank_account", items=[bank_account_item(tag)], submit=True))
    bal = approve(create_batch(..., "kazna.balance", items=[balance_item(acc.code, "2026-09-30", "1500.00")], submit=True))
    result = Runner(make_connector("manual"), mode=Mode.FULL, notifier=LogNotifier()).run()
    assert result.status == "success"
    assert dwh_balance(src="manual") == [(Decimal("1500.00"), 20260930)]
    approve(delete_batch(bal))                    # tombstone
    Runner(make_connector("manual"), mode=Mode.FULL, notifier=LogNotifier()).run()
    assert dwh_balance(src="manual") == []


def test_drafts_and_rejected_not_extracted(...) -> None: ...
def test_rerun_is_idempotent(...) -> None: ...      # rows_upserted == 0 ikkinchi yugurishda
def test_connector_reencrypts_for_staging(...) -> None:
    # dwh.dim_bank.account_enc AAD "dwh.dim_bank.account_enc:<code>" bilan ochiladi va hisobga teng;
    # core.etl_error/etl_step.detail da hisob raqami yo'q
def test_other_source_run_keeps_manual_rows(...) -> None:  # file/synthetic yuklash manual qatorlarga tegmaydi
def test_queued_request_processed_by_worker(...) -> None:  # process_requests(notifier) → request done, run_id
```
- [ ] **Step 2–4:** FAIL → implementatsiya → PASS (`$TEST pytest tests/test_manual_connector.py tests/test_worker.py tests/test_etl_runner.py -q`).
- [ ] **Step 5: Commit** `feat(etl): ManualConnector — tasdiqlangan yozuvlar stg → dwh, to'liq almashtirish, worker navbati`

---

### Task 9: Ustuvorlik view'lari (0023), agregatlarning o'tishi, sifat 2 istisnosi, kod qoidasi [MVP]

**Files:**
- Create: `backend/migrations/versions/0023_manual_effective.py`
- Modify: `backend/app/dwh/aggregates.py`, `backend/app/dwh/treasury_aggregates.py`, S2–S4 1-to'plami qo'shgan barcha `backend/app/dwh/*_aggregates.py` modullari (ro'yxatni kod qoidasi testi chiqaradi — nomlarni taxmin qilmang), `backend/app/finmodel/*` (S5 qo'shilgan bo'lsa), `backend/app/etl/quality.py`, `backend/tests/test_code_rules.py`
- Test: `backend/tests/test_manual_effective.py`

**Interfaces:**
- Produces: spec §3.4 jadvalidagi 9 ta view (`object_stage` — 15-vazifa). Shablon (har view `WITH (security_invoker = true)`, `GRANT SELECT … TO ugk_etl`):
  ```sql
  CREATE VIEW dwh.balance_effective WITH (security_invoker = true) AS
  SELECT f.* FROM dwh.fact_balance f
  WHERE (f.src_system <> 'manual' OR NOT EXISTS (
           SELECT 1 FROM dwh.fact_balance o
           WHERE o.src_system NOT IN ('manual', 'synthetic')
             AND o.branch_id = f.branch_id AND o.bank_id = f.bank_id
             AND o.date_id / 100 = f.date_id / 100))
    AND (f.src_system <> 'synthetic' OR NOT EXISTS (
           SELECT 1 FROM dwh.fact_balance o
           WHERE o.src_system = 'manual'
             AND o.branch_id = f.branch_id AND o.bank_id = f.bank_id
             AND o.date_id / 100 = f.date_id / 100));
  ```
  Donlar (`_GRAINS` migratsiyada, Python dict → SQL): `payment_plan` — `branch_id, item_id, (doc_type = 'payment_schedule')` + reja uchun `date_id/100`, kalendar uchun `date_id`; `generation` — faqat `doc_type = 'generation_plan'` qatorlari solishtiriladi (fakt qatorlari shartsiz o'tadi); `debt` — `contract_id, date_id/100`; `hr` — `branch_id, pos_id, date_id/100`; boshqalar — spec jadvali. Indeks: `CREATE INDEX fact_balance_grain_idx ON dwh.fact_balance (bank_id, branch_id, date_id)` (2-reja carry: `_CASH_TOTALS` uchun ham foydali), qolganlarida mavjud FK indekslari.
  - Agregatlar: ro'yxatdagi har `FROM dwh.fact_<x> ` / `JOIN dwh.fact_<x> ` → `dwh.<x>_effective` (mexanik). `quality._UNVERIFIABLE_SQL` va `_balance_identity` dagi `first_ever` — `dwh.balance_effective`; `_capacity` — o'zgarishsiz (fakt qatorlari).
  - Sifat 2 istisnosi: `_UNVERIFIABLE_SQL` ga `UNION` — filial-oyning kiruvchi yoki chiquvchi qoldig'ini bergan `balance_effective` qatori `src_system = 'manual'` bo'lsa (aggregates `_CASH_TOTALS` dagi `DISTINCT ON (bank_id) … ORDER BY bank_id, date_id DESC` lateral'i bilan bir xil, `src_system` ni qaytaradi), `unverifiable` ga `{"branch_id", "month_id", "reason": "manual_balance"}`.
  - Kod qoidasi: `test_manual_facts_read_via_effective_views` — `app/dwh/**/*.py`, `app/finmodel/**/*.py`, `app/etl/quality.py` da `re.search(r"dwh\.fact_(balance|payment_plan|debt|target_funds|loan_schedule|generation|energy_sales|investment|hr|object_stage)\b")` topilmasligi kerak (istisno: `app/dwh/targets.py`, `app/dwh/partitions.py`, `quality._capacity` — `# manual-ok` izohli qator).
- [ ] **Step 1: Failing test** — `test_manual_effective.py`:
```python
@pytest.mark.parametrize("view,table", EFFECTIVE)  # 9 juftlik
def test_effective_equals_table_without_manual(published_synthetic, view, table) -> None:
    assert count(f"SELECT * FROM dwh.{table} EXCEPT ALL SELECT * FROM dwh.{view}") == 0


def test_system_row_shadows_manual() -> None:
    # bir xil filial × hisob × oyga 'filexx' (fayl) va 'manual' qoldig'i → view'da faqat fayl qatori
def test_manual_shadows_synthetic() -> None: ...
def test_schedule_and_plan_rows_do_not_shadow_each_other() -> None: ...
def test_generation_fact_rows_never_shadowed() -> None: ...
def test_manual_balance_reaches_kazna_svod(make_user) -> None:
    # treasury_scenario + manual qoldiq (yangi BA- hisob) → ManualConnector run → /kazna/svod closing_balance
    # = sintetik/ssenariy + 1500
def test_manual_balance_month_is_unverifiable_not_failed() -> None:
    # quality.balance_identity ok, unverifiable[...].reason == "manual_balance"
def test_build_time_regression(published_synthetic) -> None:  # build_all vaqti ≤ 1.1 × bazaviy (log, skip CI'da emas)
```
`test_code_rules.py` ga `test_manual_facts_read_via_effective_views`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implementatsiya** — migratsiya, mexanik almashtirish, quality istisnosi.
- [ ] **Step 4: Run** — **to'liq** `$TEST pytest -q` PASS (S1–S4 agregat testlari o'zgarishsiz o'tishi — regressiya darvozasi); ruff/mypy.
- [ ] **Step 5: Commit** `feat(dwh): 0023 — *_effective ustuvorlik view'lari, agregatlar va sifat tekshiruvi ularga o'tdi; manual_balance istisnosi`

---

### Task 10: «Перекрыто источником» holati — `agg_manual_shadow` [1+]

**Files:**
- Create: `backend/app/dwh/manual_aggregates.py`
- Modify: `backend/migrations/versions/0023_manual_effective.py` (agar 9-vazifa hali birlashtirilmagan bo'lsa; aks holda `0023a_manual_shadow.py`, `down_revision="0023"`), `backend/app/dwh/aggregates.py` (import), `backend/app/manual/router.py` (`shadowed_by`)
- Test: `backend/tests/test_manual_shadow.py`

**Interfaces:**
- Produces: `mart.agg_manual_shadow (build_id, branch_id > 0, entry_id bigint, shadowed_by varchar(32), PRIMARY KEY (build_id, entry_id))` (FORCE RLS, `pub.agg_manual_shadow` aktiv build) — har manual fakt qatori (`src_id = 'M:<entry_id>'`) uchun jadvalda bor-u view'da yo'q bo'lsa, yopgan qatorning `src_system`; `register(Aggregate("agg_manual_shadow", (...)))`. API: `RecordOut.shadowed_by` — `pub.agg_manual_shadow` dan (`onec*` → «1С», `bank*` → «банк», `file` → «файл», boshqasi — kod).
- [ ] **Step 1–4:** `test_shadowed_record_reported` (fayl qatori yuklangach keyingi build'da `GET records` → `shadowed_by == "file"`), `test_branch_user_sees_only_own_shadow_rows`; FAIL → implementatsiya → PASS.
- [ ] **Step 5: Commit** `feat(manual): «Перекрыто источником» — agg_manual_shadow agregati va API holati`

---

### Task 11: Shablon va import (CSV/XLSX) [1+]

**Files:**
- Create: `backend/app/manual/imports.py`
- Modify: `backend/app/manual/router.py`, `backend/tests/test_route_guards.py`
- Test: `backend/tests/test_manual_import.py`, fixture'lar `backend/tests/fixtures/manual/*.xlsx` (testda `openpyxl` bilan generatsiya; bomb fayllari `zipfile` bilan)

**Interfaces:**
- Produces:
  - `template_csv(entity) -> bytes` (UTF-8 BOM, `;`, sarlavha = `FieldDef.name`, sezgir maydon ham; misol qatori yo'q), `template_xlsx(entity) -> bytes` (1-varaq «Данные» sarlavhalar, 2-varaq «Описание»: ustun, ruscha nom, tur, majburiy, format; formula-injection — `=+-@` bilan boshlanadigan matn `'` bilan).
  - `parse_upload(entity, body: bytes, content_type: str) -> list[dict[str, str]]` — CSV: `utf-8-sig`, `csv.DictReader(delimiter=";")`, sarlavha = maydonlar to'plami (ortiqcha/yetishmayotgan → `import_invalid` `{row: 1, field, code: "bad_header"}`), raqam/sana `parse_number/parse_iso_date`; XLSX: avval `zipfile.ZipFile` — a'zolar ≤ 100, `sum(file_size) ≤ 20 MiB`, `xl/vbaProject.bin` yoki `xl/externalLinks/` → `unsupported_file`; so'ng `openpyxl.load_workbook(BytesIO, read_only=True, data_only=True)`, 1-varaq, formula keshsiz katak (`None` + `data_type == 'f'`) → xato; sana katagi `datetime` → ISO. ≤ 5 000 qator.
  - `POST data/entities/{e}/import?branch_id` — `Request.body()` (≤ 1 MiB — middleware), `Content-Type` ∈ {`text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`} aks holda 422 `unsupported_file`; `DATA_IMPORT_PER_USER` limit; qatorlar → `check_items` → xato bo'lsa 422 `import_invalid` (`params.rows` ≤ 200), aks holda `create_batch(origin="import", file_meta={name (X-File-Name, ≤ 200, faqat ko'rsatish), sha256})`; audit `DATA_IMPORTED` (nom, sha256, qatorlar — mazmunsiz). Fayl diskka yozilmaydi.
  - `GET data/entities/{e}/template.csv|.xlsx` — `Content-Disposition: attachment`.
- [ ] **Step 1: Failing test** — `test_csv_import_creates_draft`, `test_bom_and_comma_decimal`, `test_thousands_separator_rejected`, `test_bad_header`, `test_all_or_nothing` (1 xatoli qator → hech narsa saqlanmaydi), `test_5001_rows_rejected`, `test_xlsx_roundtrip_template`, `test_xlsx_zip_bomb_rejected`, `test_xlsx_macro_rejected`, `test_billion_laughs_rejected` (`sharedStrings.xml` da entity kengayishi → 422, jarayon xotirasi oshmaydi), `test_formula_without_cache_rejected`, `test_wrong_content_type_422`, `test_import_rate_limited`, `test_template_formula_injection_safe`.
- [ ] **Step 2–4:** FAIL → implementatsiya → PASS.
- [ ] **Step 5: Commit** `feat(manual): kanonik shablon va CSV/XLSX import — hammasi yoki hech narsa, ZIP/XML bomb va makros himoyasi`

---

### Task 12: «Казначейство» — kalendar, kontragentlar, shartnomalar, qarzdorlik, maqsadli mablag'lar [2]

**Files:**
- Modify: `backend/app/manual/entities.py`, `backend/tests/manual_helpers.py`
- Test: `backend/tests/test_manual_kazna.py`

**Interfaces:**
- Produces (reyestr): `kazna.payment_schedule` (`fact_payment_plan`, `doc_type=SCHEDULE_DOC_TYPE`, `future_days=366`, grain `branch_code,item_code,date`), `kazna.counterparty` (`dim_counterparty`; `name`, `inn` secret `Purpose.PII` `^[0-9]{9}$`, `kind` enum dim CHECK bo'yicha; `code_fn = counterparty_code(inn)`), `kazna.contract` (`dim_contract`; `branch_code`, `number`, `contract_date`, `cp_code` ref, `amount`, `end_date`, `kind`, `object_code` ref ixt.; `code_prefix="M-CT"`), `kazna.debt` (`fact_debt`, `doc_type="manual_debt"`; `branch_code`, `contract_code` ref (filial mos bo'lishi shart), `cp_code` — shartnomadan hosila, `date`, `receivable`, `payable`, `overdue`, `overdue_days` int ≥ 0; tekshiruv: `overdue ≤ receivable + payable`), `kazna.funding_source` (`dim_source`; `name`, `kind` enum `budget/ifi/bank/own`; `M-SRC`), `kazna.target_funds` (`fact_target_funds`, `doc_type="manual_funds"`; `branch_code`, `source_code` ref, `object_code` ref ixt., `date` month, `allocated`, `used` ≥ 0; ogohlantirish emas — tekshiruv `used ≤ allocated` emas (qayta taqsimlash bo'lishi mumkin)).
- [ ] **Step 1: Failing test** — `test_debt_reaches_dogovory` (kontragent → shartnoma → qarz, uchta paket, bitta nashr yugurishi → `/kazna/dogovory` reyestrida `M-CT-…`, `contracts_overdue_90d` qoidasi yonadi), `test_inn_write_only_and_cp_code_matches_s2`, `test_schedule_in_calendar_14d` (`/kazna/calendar` ga tushadi, oylik rejaga tushmaydi), `test_target_funds_in_celevye`, `test_contract_branch_mismatch_rejected`, `test_options_respect_rls` (economist boshqa filial shartnomasini tanlovda ko'rmaydi).
- [ ] **Step 2–4:** FAIL → implementatsiya → PASS.
- [ ] **Step 5: Commit** `feat(manual): «Казначейство» — kalendar, kontragent (INN shifr.), shartnoma, qarzdorlik, manbalar, maqsadli mablag'lar`

---

### Task 13: «Кредиты» — kreditlar reyestri va grafigi [2]

**Files:**
- Modify: `backend/app/manual/entities.py`, S2 kredit agregat moduli (agar 9-vazifadan keyin qo'shilgan bo'lsa — `*_effective`), `backend/tests/manual_helpers.py`
- Test: `backend/tests/test_manual_kredity.py`

**Interfaces:**
- Produces: `kredity.loan` (`dim_loan`; `branch_code`, `creditor`, `project`, `currency` enum, `rate` pct 0..1, `grace_until`, `maturity`, `amount_uzs`; `M-LN`; tekshiruv `grace_until ≤ maturity`), `kredity.loan_schedule` (`fact_loan_schedule`, `doc_type="manual_loan_schedule"`, `forward`, `future_days = 3650 + 366`; `branch_code` — kreditdan hosila, `loan_code` ref, `date`, `principal`, `interest`, `balance` ≥ 0 — kredit valyutasida, mln birlik (UI birligi kredit valyutasidan)). Spec risk 6: stavka o'zgarishi `dim_loan_version.valid_from` = yuklash sanasi — UI izohi «Новая ставка действует с даты публикации».
- [ ] **Step 1: Failing test** — `test_manual_loan_in_reestr_and_grafik` (S2 `/kredity/reestr`, `/kredity/grafik`), `test_future_schedule_rows_kept` (forward — to'liq almashtirishda kelajak qatorlari o'chmaydi), `test_file_schedule_shadows_manual_same_date`, `test_rate_change_creates_scd_version`.
- [ ] **Step 2–4:** FAIL → implementatsiya (S2 kodida qolgan to'g'ridan-to'g'ri o'qishlarni `loan_schedule_effective` ga — kod qoidasi testi) → PASS; to'liq `$TEST pytest -q`.
- [ ] **Step 5: Commit** `feat(manual): «Кредиты» — kreditlar reyestri va to'lov grafigi`

---

### Task 14: «Производство» — ishlab chiqarish rejasi va realizatsiya [3]

**Files:** Modify `backend/app/manual/entities.py`, S3 agregat modullari (`*_effective`); Test `backend/tests/test_manual_proizvodstvo.py`

**Interfaces:**
- Produces: `proizvodstvo.generation_plan` (`fact_generation`, `doc_type="generation_plan"`; `branch_code` (faqat `dim_branch.kind ∈ {ges, cascade}`), `date` month, `plan` volume (mln kVt·soat, 3 kasr), `generation = 0` doimiy; `layout="grid"`, `grid=("branch_code","date","plan")` — scope_all foydalanuvchida stansiyalar × oylar, filial foydalanuvchisida bitta qator), `proizvodstvo.energy_sales` (`fact_energy_sales`, `doc_type="manual_sales"`; `branch_code`, `cp_code` ref (xaridor), `date` month, `accrued`, `paid` ≥ 0, `volume` volume).
- [ ] **Step 1: Failing test** — `test_plan_in_stancii_execution` (S3 `/proizvodstvo/stancii` bajarilish %), `test_hq_branch_refused_for_plan`, `test_capacity_check_unaffected` (reja qatorlari sifat 4 ga kirmaydi), `test_sales_payment_level`.
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS → commit `feat(manual): «Производство» — ishlab chiqarish rejasi (jadval) va realizatsiya`

---

### Task 15: «Инвестиции» — АИП obyektlari, oylik reja/fakt, bosqichlar (0024) [3]

**Files:** Create `backend/migrations/versions/0024_manual_object_stage.py` (`dwh.object_stage_effective`, don `object_id, stage_no`); Modify `backend/app/manual/entities.py`, S4 АИП agregat moduli va S5 финмодель kirishlari (`investment_effective`, `balance_effective`, `loan_schedule_effective`); Test `backend/tests/test_manual_investicii.py`

**Interfaces:**
- Produces: `investicii.object` (`dim_object`; `name`, `program_code`, `work_type`, `source_code` ref, `commissioning_year` 2000..2100, `total_cost`; `M-OBJ`), `investicii.aip_month` (`fact_investment`, `doc_type="manual_aip"`, S4 `forward` bo'yicha; `branch_code`, `object_code`, `source_code` ixt., `date` month, `plan`, `fact` ≥ 0, `physical_pct` 0..1 (UI %), `advance` ≥ 0, `advance_date` (≤ `date` oyi oxiri, `advance > 0` bo'lsa majburiy)), `investicii.object_stage` (`fact_object_stage`; `branch_code`, `object_code`, `stage_no` 1..50, `stage_name`, `date` (reja tugashi), `fact_date` ixt.).
- [ ] **Step 1: Failing test** — `test_aip_month_in_obekty` (S4 `/investicii/obekty`), `test_physical_pct_bounds`, `test_advance_date_required_when_advance`, `test_object_stage_effective_equals_table_without_manual`, `test_finmodel_inputs_use_effective` (S5 qo'shilgan bo'lsa; aks holda `skip` sababi bilan).
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS (to'liq to'plam) → commit `feat(manual): «Инвестиции» — АИП obyektlari, oylik reja/fakt, bosqichlar; 0024`

---

### Task 16: «Кадры» — штат va численность [3]

**Files:** Modify `backend/app/manual/entities.py`, S4 `hr_aggregates.py` (`hr_effective`), S4 shaxsiy ma'lumot testi (`tests/test_kadry_api.py` yoki S4 nomi); Test `backend/tests/test_manual_kadry.py`

**Interfaces:**
- Produces: `kadry.headcount` (`fact_hr`, `doc_type="manual_hr"`; `branch_code`, `pos_code` ref `dim_position` (toifa), `date` month (oyning **oxirgi** kuni sifatida yoziladi — S4 «oyning oxirgi snapshot'i» mantiqi), `headcount_plan`, `headcount_fact` decimal(10,1) ≥ 0, `hired`, `fired` int ≥ 0, `overtime_hours` decimal ≥ 0, `payroll = 0` doimiy; `layout="grid"`, `grid=("pos_code","date","headcount_plan")`). Reyestrda ФИО/ПИНФЛ/tug'ilgan sana kabi maydon yo'q.
- [ ] **Step 1: Failing test** — `test_headcount_in_chislennost` (S4 vakansiyalar), `test_hr_api_row_shadows_manual_month`, `test_no_personal_fields_in_manual_entities` (har obyekt maydon nomlari `fio|full_name|pinfl|passport|birth` ga mos kelmaydi; S4 testiga ham obyekt reyestri qo'shiladi).
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS → commit `feat(manual): «Кадры» — штат va численность (jadval), shaxsiy maydonsiz`

---

### Task 17: Frontend asoslari — tiplar, API, «Ввод данных» bo'limi, matnlar [MVP]

**Files:**
- Modify: `backend/app/meta/menu.py` (bo'lim `vvod` — «Ввод данных», guruh «Данные»; sahifalar `inbox` «На согласовании», `batches` «Мои пакеты» va foydalanuvchi ruxsatidagi obyektlar (`kazna-balance` kabi — `id.replace(".", "-")`); ko'rinish sharti — biror `data:*`), `backend/tests/test_meta_api.py`
- Create: `frontend/src/entry/api.ts`, `frontend/src/entry/fields.ts`, `frontend/src/sections/vvod/_page.tsx`
- Modify: `frontend/src/sections/registry.ts` (bo'lim darajasidagi zaxira: `./<section>/<page>.tsx` yo'q bo'lsa `./<section>/_page.tsx`), `frontend/src/api/{openapi.json,schema.d.ts,types.ts}` (generatsiya), `frontend/src/i18n/ru.ts`, `frontend/src/test/fixtures.ts`
- Test: `frontend/src/entry/fields.test.ts`, `frontend/src/sections/registry.test.tsx`

**Interfaces:**
- Produces:
  - `entry/api.ts`: `useEntities()`, `useRecords(entity, filters, page)`, `useOptions(entity, field, q, br)`, `useHistory(entryId)`, `useBatches(box, status)`, `useBatch(id)`, mutatsiyalar `useCreateBatch`, `useUpdateBatch`, `useSubmitBatch`, `useWithdrawBatch`, `useApproveBatch`, `useRejectBatch` (muvaffaqiyatda `records`, `batches` invalidatsiya; 409 → `ApiError.code` saqlanadi).
  - `entry/fields.ts`: `toInput(field, value) -> string`, `fromInput(field, raw) -> {value} | {error: 'entry.err.*'}` (`money` — `parseDecimal`, 2 kasr, `pct` — % ↔ 0..1, `month` — `YYYY-MM` ↔ `YYYY-MM-01`), `unitLabel(field)`.
  - `ru.ts` kalitlari: `entry.title` «Ввод данных», `entry.add` «Добавить», `entry.edit` «Редактировать», `entry.delete` «Удалить», `entry.saveDraft` «Сохранить черновик», `entry.submit` «Отправить на согласование», `entry.approve` «Утвердить», `entry.reject` «Отклонить», `entry.withdraw` «Отозвать», `entry.history` «История изменений», `entry.import` «Загрузить из файла», `entry.template` «Скачать шаблон», `entry.reason` «Причина изменения», `entry.status.*` («Черновик», «На согласовании», «Утверждено», «Отклонено», «Отозвано»), `entry.record.*` («Действует», «Перекрыто источником: {src}», «Удалено»), `entry.pub.*` («Ожидает публикации», «Публикуется», «Опубликовано (сборка №{n})», «Ошибка публикации»), `entry.err.*` (server kodlari bilan bir xil).
- [ ] **Step 1: Failing test** — backend `test_menu_has_vvod_only_with_data_perms`; frontend `fields.test.ts` (`fromInput(money, '12 345,67')` → `'12345.67'`, `'1,234'` → xato, `pct '12,5'` → `'0.125'`), `registry.test.tsx` (`resolve('vvod','kazna-balance')` → `_page`, boshqa bo'limda zaxira yo'q bo'lsa `null`).
- [ ] **Step 2:** `$TEST pytest tests/test_meta_api.py -q`; `$NODE npm run test -- entry registry` — FAIL.
- [ ] **Step 3:** Implementatsiya; `$NODE npm run gen:api` (3-reja skripti).
- [ ] **Step 4:** PASS; `$NODE npm run typecheck && $NODE npm run lint`.
- [ ] **Step 5: Commit** `feat(frontend): «Ввод данных» bo'limi asoslari — tiplar, API hook'lari, maydon formatlari, matnlar`

---

### Task 18: Obyekt sahifasi — reyestr, drawer-forma, tekshiruv, 409, tarix [MVP]

**Files:**
- Create: `frontend/src/entry/EntityPage.tsx`, `RecordDrawer.tsx`, `HistoryDrawer.tsx`, `entry.css`
- Modify: `frontend/src/sections/vvod/_page.tsx` (obyekt id → `EntityPage`)
- Test: `frontend/src/entry/entityPage.test.tsx`

**Interfaces:**
- Consumes: `Table`, `Drawer`, `Field`, `Combobox`, `Select`, `Badge`, `Button`, `ConfirmDialog`, `EmptyState`, `ErrorBanner`, `Skeleton`, `useToast`, `useFocusFirstInvalid`, `useFilters` (`br`, `per`), `SectionPageProps`.
- Produces: `EntityPage({ section, page, filters, onBranch })` — sarlavha + `srcbar` («Сведения, которые 1С не передаёт. Данные попадают в отчёты после согласования.»), «Добавить», reyestr (ustunlar — `fields` dan, holat badge'i, ⋯ menyu), bo'sh holat; `RecordDrawer({ entity, record?, branch, onClose })` — maydonlar `fields` bo'yicha, `aria-invalid` + `aria-describedby`, server `params.fields` → maydon xatosi, birinchi xatoga fokus, `secret` maydon (`type="password"`, `autocomplete="off"`, mavjud yozuvda «…1234 — оставьте пустым, чтобы не менять»), tasdiqlangan yozuvni o'zgartirish/o'chirishda «Причина изменения» majburiy (≥ 5), tugmalar «Сохранить черновик» / «Отправить на согласование»; 409 `conflict_modified`/`pending_change` → banner + «Обновить»; `duplicate_record` → «Открыть существующую запись» (`params.entry_id`); `HistoryDrawer({ entryId })` — versiyalar lentasi, maydon farqlari (`<del>`/`<ins>` + matn «было/стало», rangga tayanmasdan).
- [ ] **Step 1: Failing test** — `entityPage.test.tsx` (`mockApi`): `renders records and statuses`, `validates money before submit` (`'1,234'` → xato, POST yo'q), `submits with reason when editing approved record`, `shows conflict banner on 409`, `secret field never prefilled`, `history shows before/after`, `axe has no violations`, `branch-locked user cannot pick other branch`.
- [ ] **Step 2–4:** `$NODE npm run test -- entityPage` FAIL → implementatsiya → PASS; typecheck/lint.
- [ ] **Step 5: Commit** `feat(frontend): obyekt sahifasi — reyestr, drawer-forma, tekshiruv, 409, tarix`

---

### Task 19: Jadval muharriri (qator × oy), klaviatura, Excel'dan qo'yish [1+]

**Files:** Create `frontend/src/entry/GridEditor.tsx`, `frontend/src/entry/grid.ts`; Modify `EntityPage.tsx` (`layout === 'grid'` → «Таблица» / «Список» `Tabs`); Test `frontend/src/entry/grid.test.ts`, `gridEditor.test.tsx`

**Interfaces:**
- Produces: `grid.ts` — `parseTsv(text) -> string[][]` (`\r?\n`, `\t`, oxirgi bo'sh qator tashlanadi), `applyPaste(cells, at: {row, col}, block) -> {cells, changed: Key[]}` (chegaradan chiqqan qism kesiladi, yopiq ustunlar o'tkazib yuboriladi), `toItems(entity, cells, records) -> ItemIn[]` (faqat o'zgarganlar, mavjud yozuvda `entry_id` + `expected_version`, bo'shatilgan katak → `delete`); `GridEditor({ entity, branch, year })` — `role="grid"`, `aria-rowcount/colcount`, roving `tabIndex`, ←↑→↓/Tab/Shift+Tab/Enter/Esc/Delete, Ctrl+V (`onPaste` — `clipboardData.getData('text/plain')`), o'zgargan katak (`.cell--dirty` + `aria-label` «изменено»), yopiq oy (`aria-readonly`, «Период закрыт»), qator/ustun jami, ≤ 500 o'zgarish (aks holda «Сохраните частями»), saqlash → `useCreateBatch({origin: 'grid'})`; <768 px — yopishqoq birinchi ustun, ichki skroll.
- [ ] **Step 1: Failing test** — `grid.test.ts` (`parseTsv('1\t2\r\n3\t4\r\n')`, chegaradan chiqish, yopiq ustun, `toItems` faqat o'zgarganlar), `gridEditor.test.tsx` (strelkalar fokusni ko'chiradi, paste 3×2 blok, Esc qaytaradi, saqlash tanasi, axe).
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS → commit `feat(frontend): jadval muharriri — oy × qator, klaviatura, Excel'dan qo'yish`

---

### Task 20: «На согласовании», «Мои пакеты», paket sahifasi va nashr holati [MVP]

**Files:** Create `frontend/src/sections/vvod/inbox.tsx`, `frontend/src/sections/vvod/batches.tsx`, `frontend/src/entry/BatchPage.tsx`; Modify `frontend/src/sections/vvod/_page.tsx` (`batch-<id>` sahifasi yoki `?batch=` parametri); Test `frontend/src/entry/batch.test.tsx`

**Interfaces:**
- Produces: `inbox` — `useBatches('inbox','submitted')` jadvali (obyekt, filial, kirituvchi, yuborilgan, qatorlar), chap menyu hisoblagichi (`NavItem.count`, fon so'rovi `X-UGK-Background: 1`); `batches` — o'z paketlari holat filtri bilan; `BatchPage({ id })` — diff jadvali (op belgisi matn bilan: «новая», «изменена», «удалена»), sabab, «Утвердить» / «Отклонить» (izoh dialogi, majburiy), o'z paketida tugmalar o'rniga «Согласовать может другой сотрудник с правом согласования», draft'da «Редактировать», «Отправить», «Отозвать»; nashr holati `entry.pub.*`, 5 s polling (fon) faqat `queued|running` holatida.
- [ ] **Step 1: Failing test** — `approver sees inbox and approves`, `reject requires comment`, `own batch has no approve button`, `publication status polls until published`, `axe`.
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS → commit `feat(frontend): «На согласовании», «Мои пакеты», paket diff'i va nashr holati`

---

### Task 21: Import dialogi va shablon yuklab olish [1+]

**Files:** Create `frontend/src/entry/ImportDialog.tsx`; Modify `EntityPage.tsx`, `frontend/src/api/client.ts` (xom tana yuborish: `api.postRaw(path, body: Blob, contentType)` — CSRF header bilan); Test `frontend/src/entry/import.test.tsx`

**Interfaces:**
- Produces: `ImportDialog({ entity, branch })` — «Скачать шаблон (CSV / Excel)» (`fetch` → `Blob` → `src/dash/download.ts`), fayl tanlash (`accept=".csv,.xlsx"`, ≤ 1 MiB klientda tekshiriladi), yuklash → 422 `import_invalid` → xatolar jadvali (qator, ustun, ruscha sabab `entry.err.*`, ≤ 200), muvaffaqiyat → «Создан черновик: {n} строк» + paketga o'tish; `X-File-Name` (encodeURIComponent).
- [ ] **Step 1: Failing test** — `uploads csv as raw body with csrf`, `shows row errors`, `refuses >1 MiB client-side`, `downloads template`, `axe`.
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS → commit `feat(frontend): fayldan yuklash dialogi va shablonlar`

---

### Task 22: Bo'lim sahifalaridan chuqur havola [3]

**Files:** Modify `frontend/src/dash/DataState.tsx` (`entry?: string` prop: «Источник не подключён» / «Нет данных за период» holatida va `CardExport` ⋯ menyusida «Ввести данные» — `#vvod/<entry>?br&per`, faqat `useEntities()` da `can_write`), S1 `kazna/{svod,platezhi,calendar,dogovory,celevye}.tsx`, S2 `kredity/*`, S3 `proizvodstvo/{svod,stancii,realiz}.tsx`, S4 `investicii/*`, `kadry/*` (tegishli kartalarga `entry=` prop); Test `frontend/src/dash/DataState.test.tsx`

- [ ] **Step 1: Failing test** — `shows entry link only with write permission`, `link keeps br and per`.
- [ ] **Step 2–5:** FAIL → implementatsiya → PASS → commit `feat(frontend): bo'lim kartalaridan «Ввести данные» havolasi`

---

### Task 23: E2E — maker → checker → nashr; filial doirasi, CSP [23a MVP, 23b to'liq]

**Files:** Create `frontend/e2e/specs/manual-entry.spec.ts`; Modify `backend/app/devtools.py` (E2E seed: `spec_kazna` va `nach_otdela` foydalanuvchilari ma'lum TOTP bilan, faqat ENV dev/test)

**Interfaces:**
- Consumes: E2E `signIn`, `expectNoHorizontalScroll`, `adminFor`; demo stack'dagi worker (yo'q bo'lsa — `docker compose … exec worker python -m app.cli etl-run --source manual --mode full`).
- [ ] **Step 1 (23a):** `maker enters account and balance, checker approves, Казначейство shows it` — 390/1024/1440; `self approval is impossible` (o'z paketida tugma yo'q + API 403); `branch economist cannot post for another branch` (`page.request.post` → 403); `no CSP violations` (`securitypolicyviolation` tinglovchisi).
- [ ] **Step 2 (23b, 4-to'lqin):** jadval muharriri (paste), import (CSV xatosi va muvaffaqiyat), «Перекрыто источником», kredit grafigi importi, «Кадры» jadvali.
- [ ] **Step 3:** `scripts/e2e.sh manual-entry` PASS.
- [ ] **Step 4: Commit** `test(e2e): «Ввод данных» — maker/checker, nashr, filial doirasi, CSP`

---

### Task 24: Hujjatlar — Kiberxavfsizlik markazi ekspertizasi uchun va foydalanuvchiga [4]

**Files:** Modify `docs/security/access-control.md` (ruxsatlar matritsasi `data:*`, SoD, seed rollar), `threat-model.md` (yangi qatorlar: R-M1 kirituvchi yolg'on raqam (Tampering) → maker–checker + `content_hash`; R-M2 o'zini tasdiqlash (Elevation) → DB `CHECK`; R-M3 boshqa filialga yozish → RLS WITH CHECK; R-M4 inkor qilish (Repudiation) → audit hash-zanjiri + append-only versiyalar; R-M5 import orqali DoS/XML bomb → chegaralar; R-M6 hisob raqami sizishi → write-only + AES-GCM; R-M7 BI va 1C ajralishi → ustuvorlik qoidasi), `data-classification.md` (`core.manual_*` — «Конфиденциально», `bank_enc`/`pii_enc`), `audit-log.md` (`data.*` hodisalari, `content_hash`), `asvs-l2.md` (V1.4.1, V4.1.3, V4.2.1 IDOR, V4.3, V5.1.3, V8.3.4, V12.1.1, V12.2.1, V12.3.x, V13.2.x — test havolalari bilan), `cryptography.md` (yangi AAD, REGISTRY), `secure-configuration.md` (`manual.locked_through`, `ratelimit.data_write_per_min`); `docs/ops/user-guide.md` («Ввод данных»: kiritish, jadval, import, tasdiq, davr), `docs/ops/admin-guide.md` (ruxsatlar berish, davrni yopish, `builds.keep` eslatmasi, «Ошибка публикации» tartibi); Create `docs/integration/vvod-dannyh.md` (har obyekt: ustunlar, turlar, misol, FileConnector bilan bir xilligi); spec holati «bajarildi».
- [ ] **Step 1:** `$TEST pytest tests/ops/test_docs.py -q` — yangi havolalar bilan PASS (backtick ichidagi har test nomi mavjud).
- [ ] **Step 2:** `make check` yashil.
- [ ] **Step 3: Commit** `docs(security,ops): «Ввод данных» — kirish matritsasi, tahdid modeli, tasnif, audit, ASVS, foydalanuvchi va admin qo'llanmasi`

---

## Self-review

- Spec §2 obyektlari → 3, 12–16; §3.1 → 2; §3.2 → 5, 6; §3.3 → 8; §3.4 → 9, 10, 15; §3.5 → 9; §3.6 → 1, 4, 6; §3.7 → 6, 20; §4.1 → 1, 2; §4.2 → 2, 5, 7; §4.3 → 2, 6; §4.4 → 2, 5; §4.5 → 1, 5, 7, 11; §5 → 7, 11; §6 → 17–22; §7 tuzatishlari → yuqoridagi bo'lim; §9 testlari → har vazifa; hujjatlar → 24.
- Jami 24 vazifa; MVP — 13 (1–9, 17, 18, 20, 23a).
