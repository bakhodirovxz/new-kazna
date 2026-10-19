# UGEKAZNA — 0-kichik loyiha: Poydevor (baza + xavfsizlik) — dizayn spetsifikatsiyasi

- Sana: 2026-09-24
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: [docs/reference/UGEKAZNA_TZ.pdf](../../reference/UGEKAZNA_TZ.pdf) (TZ, 2026-09-18), prototip — claude.ai artifakt `ECfZP55xS7XxL6WVhAPxDV`
- Qayta ishlatiladigan tajriba: `1C.1/adreska/` (FastAPI + React + PostgreSQL xavfsizlik pattern'lari)

## 1. Maqsad va chegaralar

UGEKAZNA — «Узбекгидроэнерго» AJ uchun UGE ERP (1C) ustidagi analitik BI-qatlam. Loyiha noldan
qayta quriladi: backend Python, frontend React, Docker. TZ 6 bosqichdan iborat bo'lgani uchun ish
kichik loyihalarga bo'linadi. **Ushbu spec faqat poydevorni qamraydi.**

### Maqsad
Kiberxavfsizlik markazi ekspertizasidan o'ta oladigan, keyingi barcha bo'limlar quriladigan
xavfsiz, tez va kuzatiladigan asos yaratish.

### Kiradi
1. Docker infratuzilmasi (dev / test / prod), hardening, sirlarni boshqarish.
2. Xavfsizlik: lokal akkauntlar + majburiy TOTP 2FA, sessiyalar, RBAC (lavozim → rol), ikki qavatli RLS,
   AES-256 qatlamli shifrlash, o'zgarmas audit jurnali.
3. Витрина: TZ 3-bo'limidagi to'liq yulduz sxema (11 dim, 14 fact + `fx_rate` kurslar jadvali), partitsiyalar, indekslar,
   oylik agregatlar, atomar publish.
4. ETL karkasi: job runner, konnektor interfeysi, idempotentlik, qayta urinishlar, 5 sifat tekshiruvi,
   jurnal; `SyntheticConnector` va `FileConnector`.
5. API karkasi: auth, admin, audit, meta, health; kesh va unumdorlik pattern'i.
6. Frontend: dizayn tizimi, ilova qobig'i (9 bo'lim, chap menyu, filtrlar, URL holati, Ctrl+K, Ссылка,
   Печать), login/2FA/parol sahifalari, admin panel; responsive.
7. Test, CI xavfsizlik darvozalari, zaxira/tiklash, ekspertiza hujjatlari.

### Kirmaydi (keyingi spec'lar tartibida)
1. Обзор + Казначейство bo'limlari va 1C konnektori (TZ 1-bosqich qolgan qismi).
2. Banklar (DirectBank), платёжный календарь, panel отклонений, xlsx eksport.
3. Производство, Склад, ГЭС xaritasi, АСКУЭ.
4. Закупки, Инвестиции, Кадры.
5. Финмодель, AI-анализ, Telegram bot, Экран rejimi.
6. O'zbek tili, ТОиР, гидрология.

### Qabul qilingan qarorlar
| Savol | Qaror |
|---|---|
| Autentifikatsiya | Lokal akkauntlar, Argon2id, hamma uchun majburiy TOTP 2FA |
| Shifrlash | Qatlamli: LUKS disk + ilova darajasida sezgir ustunlar (AES-256-GCM) + shifrlangan zaxira + TLS |
| Server | Linux, ichki tarmoq, tashqi kirish faqat VPN |
| Arxitektura | Modulli monolit (FastAPI) + alohida ETL worker, PostgreSQL 16, Redis, Caddy |
| Joylashuv | Alohida repo `Desktop/ugekazna` (eski repo tarixi va sizib chiqqan sirlar o'tmaydi) |

## 2. Loyiha tuzilishi va infratuzilma

```
ugekazna/
  backend/            FastAPI ilova: api va worker bitta image, entrypoint har xil
    app/core/         config, db, crypto, security, cache, errors, logging
    app/auth/         login, 2FA, sessiyalar, parol siyosati
    app/admin/        foydalanuvchilar, lavozimlar, rollar, sozlamalar
    app/audit/        audit jurnali
    app/dwh/          витрина modellari, RLS konteksti, publish
    app/etl/          runner, konnektorlar, sifat tekshiruvlari, notifier
    app/meta/         filiallar, davrlar, menyu, data-freshness
    migrations/       Alembic (DDL, partitsiyalar, RLS policy'lar, DB rollari)
    tests/
  frontend/           Vite + React 18 + TypeScript strict
  deploy/             compose.yml, compose.prod.yml, caddy/, postgres/, pgbackrest/, secrets/ (gitignore)
  docs/               spec'lar, reference/, security/, ops/
  Makefile
```

### Konteynerlar
| Servis | Image | Vazifa | Tarmoq | Tashqi port |
|---|---|---|---|---|
| caddy | caddy:2-alpine | TLS 1.2/1.3, HSTS, CSP, statika, `/api` proksi | edge | 443 (80→301) |
| api | backend | uvicorn, 4 worker | edge, backend | — |
| worker | backend | ETL, rejalashtiruvchi, partitsiya/tozalash | backend | — |
| db | postgres:16 | витрина va tizim jadvallari | backend (internal) | — |
| redis | redis:7-alpine | kesh, rate limit; `requirepass` + ACL | backend (internal) | — |
| backup | pgbackrest | full/diff/WAL, AES-256 repo | backend (internal) | — |

`backend` tarmog'i `internal: true` — tashqi internetga chiqish yo'q.

### Konteyner hardening (hamma servis)
non-root foydalanuvchi; `read_only: true` + `tmpfs`; `cap_drop: [ALL]`; `security_opt: no-new-privileges`;
xotira/CPU limitlari; image'lar digest bo'yicha qotirilgan; healthcheck; log rotatsiyasi.

### Sirlar
Docker secrets (`/run/secrets/*`). Host'da `deploy/secrets/` — `root:root 0600`, git'ga tushmaydi,
`secrets.example/` faqat nomlar bilan. Kod, `.env` va compose fayllarida parol yo'q. Ro'yxat:
`db_app_password`, `db_etl_password`, `db_migrator_password`, `redis_password`, `master_kek`,
`blind_index_key`, `session_pepper`, `pgbackrest_cipher_pass`, `smtp_password`.

### Muhitlar
dev (sintetik ma'lumot, `Caddyfile.dev`, hot reload), test (prod'ning anonimlashtirilgan nusxasi,
≤1 hafta eski — `make anonymize-copy`), prod. Relizdan oldin test muhitida qabul; image teglari
orqali orqaga qaytish.

## 3. Xavfsizlik modeli

### 3.1 Autentifikatsiya
- Parol xeshi: Argon2id (m=64 MiB, t=3, p=4). `session_pepper` faqat sessiya tokenlari HMAC'i uchun ishlatiladi, parol xeshida emas.
- Parol siyosati: ≥12 belgi; top-100k buzilgan parollar ro'yxati (bundle ichida, offline) bo'yicha rad;
  oxirgi 5 parolni qayta ishlatish taqiqlangan; 90 kunlik muddat; birinchi kirishda majburiy almashtirish.
- 2FA: TOTP (RFC 6238, SHA-1, 30 s, 6 raqam, ±1 oyna), **hamma rol uchun majburiy**, birinchi kirishda ulanadi.
  TOTP siri AES-256-GCM bilan shifrlangan. Bitta kodni qayta ishlatish taqiqlangan (oxirgi ishlatilgan
  qadam saqlanadi). 10 ta zaxira kod — HMAC-SHA256(session_pepper), bir martalik.
- Brute-force: login bo'yicha 5 xato → 15 daqiqa blok; IP bo'yicha rate limit (10/daq); bir xil javob
  matni va doimiy vaqt (mavjud bo'lmagan foydalanuvchi uchun soxta verify).
- Login oqimi: `POST /auth/login` → `{mfa_required, mfa_token}` (5 daqiqalik, bir martalik, faqat 2FA
  uchun) → `POST /auth/2fa/verify` → sessiya cookie. 2FA'siz sessiya hech qanday ma'lumot endpointiga kirmaydi.

### 3.2 Sessiyalar va CSRF
- Token: 256-bit tasodifiy; cookie `__Host-ugk_session`, `HttpOnly; Secure; SameSite=Strict; Path=/`.
- DB'da faqat `HMAC-SHA256(session_pepper, token)` saqlanadi.
- Muddat: idle 30 daqiqa, absolyut 12 soat. Parol/rol/2FA o'zgarishi yoki bloklash → foydalanuvchining
  barcha sessiyalari bekor.
- Foydalanuvchi o'z sessiyalarini ko'radi va bekor qiladi.
- CSRF: double-submit — `__Host-ugk_csrf` cookie + `X-CSRF-Token` header, barcha o'zgartiruvchi so'rovlar uchun.

### 3.3 Avtorizatsiya
- Model: `user → position (lavozim) → role → permissions + data_scope`. TZ bo'yicha rol lavozimga beriladi.
- Rollar (seed): `rukovodstvo`, `nach_otdela`, `spec_kazna`, `economist_filiala`, `profil_sluzhba`,
  `admin`, `vnutr_kontrol`.
- Ruxsatlar kodda enum sifatida (`section:<id>:view`, `export:csv`, `export:xlsx`, `admin:users`,
  `admin:roles`, `admin:settings`, `admin:etl`, `admin:keys`, `audit:read`); rol → ruxsat bog'lanishi DB'da.
- Bo'limlarga kirish TZ 1-bo'lim jadvaliga mos seed qilinadi.
- `data_scope`: `all` yoki filiallar ro'yxati (`economist_filiala` — o'z filiali).
- Tekshiruv faqat serverda; frontend faqat yashiradi.

### 3.4 RLS (ikki qavat)
1. **API qavati:** har so'rovda `data_scope` hisoblanadi; so'ralgan `br` scope'dan tashqarida bo'lsa → 403 +
   audit hodisasi `rls_violation_attempt`.
2. **DB qavati:** har tranzaksiya boshida `SET LOCAL app.branch_ids = '{…}'` va `SET LOCAL app.scope_all = 'on'|'off'`.
   `branch_id` ustuni bor barcha `dwh`, `mart`, `pub` jadvallarida `ENABLE` + `FORCE ROW LEVEL SECURITY` va policy:
   `branch_id = ANY(current_setting('app.branch_ids')::int[])` yoki `current_setting('app.scope_all') = 'on'`.
   `branch_id = 0` (umumiy yig'indi) faqat `scope_all` uchun. Sozlama o'rnatilmagan bo'lsa — 0 qator.

DB rollari:
| Rol | Huquq |
|---|---|
| `ugk_migrator` | DDL; faqat migratsiya vaqtida ishlatiladi |
| `ugk_app` | `core` (cheklangan), `pub` SELECT; RLS majburiy; `BYPASSRLS` yo'q; `audit_log` ga faqat INSERT |
| `ugk_etl` | `stg`, `dwh`, `mart` yozish; `core.etl_*` yozish; `core.data_version` UPDATE |
| `ugk_readonly` | ixtiyoriy, tekshiruvchilar uchun `pub` SELECT, RLS bilan |

### 3.5 Shifrlash
- **Diskda:** LUKS2 (AES-256-XTS) — host qo'llanmasi.
- **Uzatishda:** TLS 1.2/1.3, faqat AEAD shifrlar; korporativ sertifikat; HSTS.
- **Ustun darajasida (AES-256-GCM, envelope):**
  - KEK — `master_kek` Docker secret (32 bayt).
  - DEK — maqsad bo'yicha (`pii`, `bank`, `mfa`, `integration_creds`, `audit_meta`), 32 bayt, KEK bilan
    AES-KW (RFC 3394) orqali o'ralgan holda `core.crypto_keys (purpose, version, wrapped_key, status, created_at)`.
  - Shifrmatn formati: `v1 | key_version(2B) | nonce(12B) | ciphertext | tag(16B)`, `bytea`.
  - AAD = `"{schema}.{table}.{column}:{row_pk}"` — shifrmatnni boshqa qatorga ko'chirish aniqlanadi.
  - Rotatsiya: yangi DEK versiyasi `active`, eskisi `decrypt_only`; worker fonda qayta shifrlaydi, keyin `retired`.
    KEK rotatsiyasi — faqat DEK'larni qayta o'rash.
  - Blind index: `HMAC-SHA256(blind_index_key, normalize(value))` — INN, hisob raqami bo'yicha aniq qidiruv.
- **Shifrlanadigan maydonlar:** `dim_counterparty.inn`, rekvizitlar; `dim_bank.account_number`;
  `core.users.totp_secret`; `core.integration_credentials.*`; `core.audit_log.ip`, `user_agent`.
- **Zaxira:** pgBackRest `repo1-cipher-type=aes-256-cbc`.
- Kripto kutubxonasi: `cryptography` (OpenSSL). O'z algoritm yozilmaydi.

### 3.6 Audit
- `core.audit_log` (oylik partitsiya): `id, ts, user_id, action, object_type, object_id, result,
  request_id, details jsonb, ip_enc, ua_enc, prev_hash, hash`.
- `hash = SHA-256(prev_hash || kanonik_json(yozuv))`; `make audit-verify` zanjirni tekshiradi.
- `ugk_app` — faqat INSERT; UPDATE/DELETE yo'q. Partitsiya tozalash (1 yil) faqat worker orqali, o'zi auditga yoziladi.
- Hodisalar: login (muvaffaqiyatli/xato), logout, 2FA ulash/tiklash, parol almashtirish, sessiya bekor qilish,
  foydalanuvchi/lavozim/rol o'zgarishi, eksport, AI so'rovi (keyin), ETL ishga tushishi/xatosi, chegara va
  допущения o'zgarishi, kalit rotatsiyasi, `rls_violation_attempt`, 403/401 ketma-ketligi.
- Ko'rish: `audit:read` (admin, vnutr_kontrol).

### 3.7 HTTP va ilova himoyasi
- CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self';
  font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`.
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (hammasi o'chiq),
  `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`. CORS yo'q (same-origin).
- Kirish: Pydantic v2 qat'iy modellari (`extra='forbid'`); so'rov tanasi ≤1 MB; sahifalash majburiy (≤500).
- SQL: faqat SQLAlchemy parametrlari; dinamik identifikator — whitelist.
- Xatolar: `{error: {code, message, request_id}}`; stack trace faqat logda.
- Loglar: structlog JSON; parol, token, cookie, TOTP, INN, hisob raqami avtomatik maskalanadi.
- OpenAPI/Swagger UI prod'da faqat `admin` uchun.

### 3.8 Ekspertiza hujjatlari (`docs/security/`)
Tahdid modeli (STRIDE, ma'lumot oqimi diagrammasi bilan); OWASP ASVS 4.0 L2 muvofiqlik jadvali;
kriptografiya tavsifi; kalit boshqaruvi va rotatsiya reglamenti; hodisaga javob berish reglamenti;
host hardening qo'llanmasi; SBOM.

## 4. Витрина (ma'lumotlar modeli)

### 4.1 Sxemalar
| Sxema | Mazmun |
|---|---|
| `core` | users, positions, roles, permissions, sessions, audit_log, crypto_keys, settings, alert_rules, fin_assumptions, etl_run, etl_step, etl_error, data_version, integration_credentials |
| `stg` | manbadan xom yuklangan ma'lumot: umumiy `stg.rows` (jsonb, UNLOGGED) + `stg.batch`, har yuklash `load_id` bilan; sezgir maydonlar staging'dan oldin shifrlanadi |
| `dwh` | yulduz sxema: `dim_*`, `fact_*`, `fx_rate` |
| `mart` | oylik agregatlar (`build_id` bilan) |
| `pub` | UI o'qiydigan view'lar (faqat aktiv build) |

### 4.2 Umumiy qoidalar
- Summalar `numeric(20,2)`, **mln so'm**. Hajmlar: kVt·soat uchun `numeric(20,3)` mln kVt·soat.
- Sana kaliti `date_id int` (YYYYMMDD) → `dim_date`.
- Texnik ustunlar: `load_id bigint`, `src_system text`, `doc_type text`, `src_id text`, `updated_at timestamptz`;
  `UNIQUE (src_system, doc_type, src_id)` — idempotentlik (partitsiyalangan faktlarda `+ date_id`, PostgreSQL talabi; sana o'zgarsa loader eski nusxani o'chiradi). O'lchovlarda — `code UNIQUE`.
- Tarixiy o'lchovlar SCD-2 alohida versiya jadvallarida (`valid_from`, `valid_to`, `is_current`): `dim_branch_version` (quvvat), `dim_loan_version` (stavka); `dim_branch`/`dim_loan` — FK nishoni (joriy qiymat).
  Qolganlari SCD-1.

### 4.3 O'lchovlar (`dwh`)
`dim_date`, `dim_branch` (kod, nomi, INN, tur: головная/ГЭС/каскад, quvvat MVt, kenglik, uzunlik),
`dim_item` (ПКМ №54 kodi, faoliyat turi, yo'nalish: приход/расход), `dim_counterparty` (INN — shifrlangan +
blind index, nomi, tur), `dim_contract` (raqam, sana, kontragent, filial, summa, muddat, АИП obyekti),
`dim_bank` (bank, hisob — shifrlangan + blind index, valyuta), `dim_nomenclature` (kategoriya, o'lchov birligi,
ЕНБТ kodi), `dim_object` (АИП obyekti, dastur kodi, ish turi, manba, ishga tushirish muddati),
`dim_loan` (kreditor, loyiha, valyuta, stavka, imtiyozli davr, so'ndirish muddati), `dim_position`
(xodim kategoriyasi, bo'linma — shaxsiy ma'lumotsiz), `dim_source` (бюджет, МФИ, банк, собственные).

### 4.4 Faktlar (`dwh`)
| Jadval | Granulyarlik | Partitsiya |
|---|---|---|
| fact_cashflow | bank проводкаси | oylik RANGE(date_id) |
| fact_balance | hisob × sana | yillik |
| fact_payment_plan | статья × oy × filial | — |
| fact_payment_order | платёжное поручение | oylik RANGE(date_id) |
| fact_debt | shartnoma × sana | yillik |
| fact_generation | stansiya × sutka | yillik |
| fact_energy_sales | xaridor × oy | — |
| fact_procurement | lot | — |
| fact_stock | nomenklatura × ombor × sana | yillik |
| fact_stock_move | harakat | yillik |
| fact_investment | obyekt × oy | — |
| fact_loan_schedule | kredit × to'lov sanasi | — |
| fact_hr | filial × oy | — |
| fact_target_funds | manba × obyekt × oy | — |
| fx_rate | valyuta × sana | — |

Ustunlar TZ 3-bo'limidagi o'lchov va mezonlarga mos.

### 4.5 Indekslar
- TZ majburiy: `(date_id, branch_id)`, `(branch_id, item_id)`, `(contract_id)` — tegishli faktlarda.
- Barcha FK ustunlarida B-tree.
- Partial: `fact_payment_order (branch_id, date_id) WHERE status IN ('на согласовании','утверждено')`;
  `fact_debt (branch_id) WHERE overdue_days > 0`; `fact_procurement (branch_id) WHERE status IN ('объявлен','на оценке')`.
- BRIN `date_id` bo'yicha — katta append-only faktlarda (`fact_cashflow`, `fact_stock_move`).
- `mart.*`: `(build_id, branch_id, month_id)` PK/unique.
- FK faktlardan o'lchovlarga — `DEFERRABLE INITIALLY DEFERRED` (ETL tranzaksiyasida tartib erkin).

### 4.6 Partitsiyalarni boshqarish
Worker har kuni: kelgusi 3 oy partitsiyalarini oldindan yaratadi; 5 yildan eski fakt partitsiyalarini
`DETACH` + `DROP` (arxiv — pgBackRest zaxiralari); audit partitsiyalari 1 yil. Har amal jurnalga yoziladi.

### 4.7 Agregatlar va publish
- `mart.agg_<soha>_month` — TZ 4-bo'limidagi har bir ko'rsatkich oilasi uchun (cash, payments, debt,
  generation, energy_sales, procurement, stock, investment, loans, hr, target_funds).
  Kalit: `(build_id, branch_id, month_id, …qo'shimcha kesim)`. `branch_id = 0` — barcha filiallar jami.
  Joriy yopilmagan oy uchun `days_in_period`; o'tgan yil bilan solishtirish shu kunlar bo'yicha.
- Saqlash: agregatlar 10 yil, faktlar 5 yil.
- `core.data_version (id, active_build_id, published_at)` — bitta qator.
- `pub.*` view'lari: `SELECT … FROM mart.agg_x WHERE build_id = (SELECT active_build_id FROM core.data_version)`.
- Publish = bitta `UPDATE core.data_version` tranzaksiyasi. Oxirgi 3 build saqlanadi; `make rollback-build`.
- Poydevorda agregat hisoblash freymvorki va 2 ta namunaviy agregat (`agg_cash_month`, `agg_payments_month`)
  quriladi; qolganlari tegishli bo'lim spec'larida.

### 4.8 Sozlanadigan jadvallar
- `core.alert_rules (code, threshold jsonb, level, enabled, version, updated_by)` — TZ 4-bo'limdagi 20 qoida seed qilinadi.
- `core.fin_assumptions (scenario, year, key, value, version, updated_by)` — 4 ssenariy.
- `core.settings` — tizim sozlamalari (freshness chegarasi 6 soat va h.k.).
Har o'zgarish yangi `version` qatori + audit.

## 5. ETL karkasi

### 5.1 Runner
- `worker` konteyneri: APScheduler + PostgreSQL advisory lock (job kaliti bo'yicha) — bitta job parallel ishlamaydi.
- Jadval sozlamada (`core.settings`): 1C kechasi to'liq (02:00, 06:00 gacha tugashi kerak), kunduzi 3 marta
  inkremental (10:00, 13:00, 16:00, har biri ≤10 daqiqa); banklar 4 marta (keyingi spec).
- Pipeline qadamlari: `dims → facts → aggregates → quality → publish`. Istalgan qadam xatosi → publish yo'q,
  oldingi build aktiv qoladi.
- Qo'lda ishga tushirish: admin UI (`core.etl_requests` navbati, worker bajaradi) yoki `make etl-run SOURCE=… MODE=full|incremental`.

### 5.2 Konnektor interfeysi
```python
class SourceConnector(Protocol):
    source: str
    def healthcheck(self) -> HealthResult: ...
    def watermark(self) -> Watermark: ...
    def extract(self, window: Window, sink: StagingSink) -> ExtractStats: ...
    def control_totals(self, window: Window) -> ControlTotals | None: ...
```
- Inkremental oyna: `min(watermark − 45 kun, joriy oyning 1-kuni)` dan hozirgacha (eski watermark bo'lsa oraliq ham qamraladi); yopilmagan davr to'liq qayta.
- `stg → dwh`: `INSERT … ON CONFLICT (src_system, doc_type, src_id) DO UPDATE` (faqat o'zgargan bo'lsa).
- Qayta urinishlar: 3 ta, pauza 30 s → 2 min → 8 min (+jitter); keyin `failed` + notifier.
- Poydevordagi konnektorlar:
  - `SyntheticConnector` — deterministik seed'li generator: prototipdagi 16 filial, 5 bank, statьyalar,
    real ko'rinishdagi hajmlar; 3 yil tarix. Dev, test va yuklama testi uchun.
  - `FileConnector` — CSV (UTF-8, `;`, ISO 8601, ajratkichsiz summalar) — TZ fayl formati.
- Integratsiya parollari `core.integration_credentials` da shifrlangan.

### 5.3 Sifat tekshiruvlari
1. `fact_cashflow` oylik summasi = manba nazorat summasi (5110, 5210, 5530) ±0,1% (`control_totals` bo'lsa).
2. `balance_end = balance_start + ЧДП + Разница`, `|Разница| ≤ 1%` oborot.
3. `branch_id` va `item_id` to'ldirilgan; statьyasiz → "Прочие" + `core.etl_error`.
4. `generation_day ≤ capacity_mw × 24`.
5. Mavjud bo'lmagan o'lchovga havola yo'q (FK + hisobot).
Buzilish → `etl_run.status = 'failed_quality'`, publish yo'q, notifier.

### 5.4 Jurnal va xabarnomalar
- `core.etl_run (id, source, mode, started_at, finished_at, status, rows_in, rows_upserted, build_id)`,
  `core.etl_step`, `core.etl_error`.
- `Notifier` interfeysi: `LogNotifier`, `EmailNotifier` (SMTP, ichki relay). Telegram — keyingi spec.
- Hodisalar: yuklash xatosi, >6 soat kechikish, nazorat summasi >0,1% farq.

## 6. API, kesh, unumdorlik

### 6.1 Endpointlar (poydevor)
| Guruh | Endpointlar |
|---|---|
| auth | `POST /auth/login`, `POST /auth/2fa/verify`, `POST /auth/2fa/enroll/start`, `POST /auth/2fa/enroll/confirm`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password/change`, `GET/DELETE /auth/sessions` |
| admin | `users` (CRUD, block, reset-2fa, reset-password), `positions`, `roles`, `alert-rules`, `fin-assumptions`, `etl/runs`, `etl/run`, `keys` (holat, rotate), `builds` (ro'yxat, rollback) |
| audit | `GET /audit` (filtr, sahifalash), `GET /audit/export.csv`, `POST /audit/verify` |
| meta | `GET /meta/branches` (RLS bo'yicha), `GET /meta/periods`, `GET /meta/menu` (rolga qarab), `GET /meta/freshness` |
| health | `GET /healthz`, `GET /readyz` — faqat ichki tarmoqda |

- Prefiks `/api/v1`. OpenAPI 3.1 avtomatik; frontend tiplari `openapi-typescript` bilan generatsiya.
- Bo'lim endpointlari pattern'i (keyingi spec'lar uchun): `router → service → pub view` + `@cached(...)` dekoratori.

### 6.2 Kesh
1. **Redis:** kalit `ugk:v{data_version}:{endpoint}:{scope_hash}:{filters_hash}`; TTL 1 soat; publish'da
   `data_version` o'zgaradi → eski kalitlar ishlatilmaydi. Single-flight: `SET NX` lock (5 s).
   `scope_hash` — foydalanuvchi filial doirasidan; boshqa scope keshi hech qachon qaytmaydi.
2. **HTTP:** `ETag = hash(data_version, scope, so'rov)`; `If-None-Match` → 304; `Cache-Control: private, no-cache`.
3. **Frontend:** TanStack Query `staleTime` 5 daqiqa, `placeholderData: keepPreviousData`.
- Statika: hash'langan fayllar `Cache-Control: public, max-age=31536000, immutable`; `index.html` — `no-cache`;
  brotli/gzip.

### 6.3 DB unumdorligi
- SQLAlchemy 2.0 (sinxron, threadpool) + psycopg3 pool (api: pool 10/worker, etl: 5).
- `statement_timeout`: api 5 s, etl 30 daqiqa. `idle_in_transaction_session_timeout` 60 s.
- `pg_stat_statements`, `log_min_duration_statement = 500ms`, `auto_explain` (dev/test).
- `deploy/postgres/postgresql.conf` — 8 GB va 16 GB profillar.

### 6.4 Himoya limitlari
Rate limit (Redis, sliding window): umumiy 300/daq foydalanuvchiga, login 10/daq IP'ga, 2FA verify 5/daq
`mfa_token`ga. Javob `429` + `Retry-After`.

### 6.5 Maqsadlar (TZ 9-bo'lim)
Sahifa ≤2 s, filtr ≤1 s — 20 bir vaqtdagi foydalanuvchida (p95); 50 degradatsiyasiz, 100 hisobiy cho'qqi.

## 7. Frontend: qobiq va dizayn tizimi

### 7.1 Stek
Vite, React 18, TypeScript strict, TanStack Query, hash router, Chart.js 4 (keyingi spec'larda),
Onest shrifti lokal (woff2). Hech qanday CDN yo'q.

### 7.2 Dizayn tokenlari (prototipdan)
`--bg #f5f8fd`, `--card #ffffff`, `--ink #132338`, `--muted #5f7288`, `--line #e4ebf4`, `--soft #eef5ff`,
`--brand #0b4fa8`, `--brand2 #1d6df2`, `--teal #5fd0e0`, `--neg #e0453a`, `--top #0b4fa8`, `--top2 #083a7d`.
Qizil faqat manfiy qiymat va muddati o'tganlar uchun. Shrift o'lchami `clamp(16px, …, 21px)`. Yorug' tema.
Implementatsiya vaqtida Refero orqali login/2FA, admin jadvallar va dashboard qobig'i namunalari o'rganilib,
tokenlar va komponent uslubi aniqlashtiriladi (kontrast ≥4.5:1 saqlangan holda).

### 7.3 Primitivlar
Button, IconButton, Input, PasswordInput, OtpInput, Select, Combobox, Chip, Card (hover'da eksport joyi),
Table (sort, klaviatura, mobil kartochka rejimi), Modal, Drawer, BottomSheet, Toast, Tooltip, Skeleton,
EmptyState, ErrorBanner ("Повторить" + oxirgi muvaffaqiyatli yuklash vaqti), KpiTile, Badge, Tabs.

### 7.4 Qobiq
- **Yuqori panel:** logo; 9 bo'lim guruhlari bilan (Обзор · Финансы: Казначейство, Кредиты, Финмодель ·
  Обеспечение: Закупки, Склад · Производство: Производство, Инвестиции · Персонал: Кадры) — ro'yxat
  `/meta/menu` dan, rolga qarab; o'ngda Поиск (Ctrl/Cmd+K), Ссылка (filtrli URL nusxasi), Печать,
  data-freshness (>6 soat — ogohlantirish), foydalanuvchi menyusi. AI-анализ va Экран — o'z spec'larida.
- **Chap menyu:** bo'limga tegishli (TZ 5-bo'lim jadvali), aktiv sahifa belgilangan, "Требует внимания" hisoblagichi.
- **Filtrlar:** filial (hammasi / 16 dan biri; `data_scope` bitta filial bo'lsa qulflangan), davr (yil boshidan /
  chorak / oy); URL'da (`#kazna/svod?br=3&per=5`); chiplar × bilan va "Сбросить всё".
- **Klaviatura:** ← → bo'limlar orasida (input fokusda emas bo'lsa), Enter/Space jadval qatorlarida, ko'rinadigan fokus.
- **Bo'lim sahifalari:** "раздел в разработке" EmptyState.
- **Print CSS:** menyu/filtr/tugmalar yashirin, oq fon, `break-inside: avoid` kartalarda.

### 7.5 Responsive
| Kenglik | Joylashuv |
|---|---|
| ≥1280 px | to'liq; bo'limlar sig'masa 2-qatorga o'tadi, kesilmaydi |
| 768–1279 px | chap menyu yig'iladigan panel, 2 ustun |
| <768 px | yuqori menyu gorizontal skroll, chap menyu Drawer, filtrlar BottomSheet, 1 ustun, jadvallar kartochka/ichki skroll |
Sahifada gorizontal skroll yo'q; teginish nishonlari ≥44 px.

### 7.6 Sahifalar
- Auth: Login, 2FA kodi, 2FA ulash (QR + 10 zaxira kod, yuklab olish), majburiy parol almashtirish, Mening sessiyalarim.
- Admin: Foydalanuvchilar, Lavozimlar va rollar, Требует внимания chegaralari, Финмодель допущения,
  Состояние обменов (ETL), Buildlar (rollback), Audit jurnali, Kalitlar.

### 7.7 Accessibility va til
Kontrast ≥4.5:1; ARIA yorliqlari; `prefers-reduced-motion`; to'liq klaviatura boshqaruvi. Interfeys ruscha;
i18n (`ru` lug'at) boshidan — o'zbekcha keyin. Formatlar: bo'shliq bilan razryadlar, vergul bilan kasr,
`ДД.ММ.ГГГГ`, hafta dushanbadan.

## 8. Xatolar bilan ishlash
- Backend: domen xatolari (`AuthError`, `PermissionDenied`, `ScopeViolation`, `ValidationError`,
  `NotFound`, `RateLimited`, `Conflict`) → yagona JSON format va to'g'ri HTTP kod; kutilmagan xato → 500 +
  `request_id`, tafsilot faqat logda.
- 401 → frontend login'ga yo'naltiradi (joriy URL saqlanadi); 403 → "нет доступа" sahifasi; 429 →
  toast + qayta urinish vaqti; tarmoq xatosi → ErrorBanner "Повторить".
- ETL: qadam xatosi `etl_step` ga, publish bloklanadi, notifier.

## 9. Test strategiyasi
- **Backend (pytest + testcontainers PostgreSQL 16 + Redis):**
  kripto (round-trip, AAD, noto'g'ri kalit, rotatsiya); auth (lockout, 2FA, TOTP qayta ishlatish, zaxira kod,
  sessiya muddati, CSRF, parol siyosati); **RLS** (filial foydalanuvchisi API orqali ham, `ugk_app` bilan
  to'g'ridan-to'g'ri SQL orqali ham boshqa filialni ko'rmaydi — TZ qabul mezoni 2); ETL (idempotentlik,
  5 tekshiruv, publish, rollback); audit (hash-chain buzilishini aniqlash); kesh (scope izolyatsiyasi,
  `data_version` eskirishi). Qamrov ≥85%, `core`/`auth`/`dwh` ≥95%.
- **Frontend:** Vitest + Testing Library (qobiq, filtr ↔ URL, rolga qarab menyu, formalar); axe-core;
  Playwright E2E (login → 2FA → navigatsiya → admin) 3 kenglikda (390, 1024, 1440).
- **Yuklama:** k6, sintetik ma'lumot, 20/50/100 VU; p95 maqsadlari 6.5 ga mos.

## 10. CI va sifat darvozalari
`make check` (lokal va CI): ruff, mypy --strict, bandit, semgrep (p/owasp-top-ten, p/python, p/typescript),
pip-audit, npm audit --omit=dev, gitleaks, hadolint, tsc, eslint, vitest, pytest; `make scan`: Trivy image
(HIGH/CRITICAL → xato), CycloneDX SBOM. Pre-commit hook'lar. Bog'liqliklar xesh bilan qotiriladi
(`pip-compile --generate-hashes`, `package-lock.json`).

## 11. Ekspluatatsiya
- `Makefile`: `up`, `down`, `migrate`, `seed-synthetic`, `create-admin`, `etl-run`, `rollback-build`,
  `backup`, `restore-test`, `rotate-keys`, `audit-verify`, `anonymize-copy`, `check`, `scan`.
- Zaxira (pgBackRest): to'liq kunlik, diff 6 soatda, WAL arxivi (`archive_timeout = 15min`) → RPO 15 daqiqa;
  repo AES-256; alohida volume/tashqi disk; `restore-test` oylik, natija `core.settings`/jurnalga.
- Relizlar: migratsiyadan oldin avtomatik zaxira; har migratsiyada `downgrade`; image tegi bo'yicha orqaga qaytish.
- Host qo'llanmasi (`docs/ops/host-hardening.md`): LUKS2, ufw (443 + VPN'dan SSH), SSH faqat kalit, auditd,
  chrony, unattended-upgrades, Docker daemon (`userns-remap`, `live-restore`, `no-new-privileges`, log limitlari).

## 12. Topshiriladigan natijalar
Ishlaydigan `docker compose up` (dev) sintetik ma'lumot bilan: login → 2FA → qobiq → admin; to'liq витрина
sxemasi migratsiyalari; ETL karkasi va 2 konnektor; testlar va CI darvozalari yashil; `docs/security/*`,
`docs/ops/*`, OpenAPI; admin qo'llanmasi.

## 13. Ochiq savollar (keyingi spec'lar uchun, poydevorni to'xtatmaydi)
TZ'dagi mijozga savollar: filiallar kodlari va koordinatalari, ПКМ №54 klassifikatori, 1C'ga kirish usuli
(replika yoki OData yoki mavjud `hs/aiassistant` HTTP-servislari), banklar formati, финмодель допущения,
chegaralarni tasdiqlash, foydalanuvchilar va rollar ro'yxati, rasmiy logotip. Shuningdek: eski repodagi
1C paroli (`apache-proxy.conf`) almashtirilishi kerak.
