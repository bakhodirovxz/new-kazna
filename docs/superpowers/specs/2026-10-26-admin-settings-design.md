# UGEKAZNA — sozlamalarni admin paneldan boshqarish (04b) — dizayn

Sana: 2026-10-26. Holat: bajarildi (E2E demo stack'da alohida). Reja: [../plans/2026-10-26-04b-admin-settings.md](../plans/2026-10-26-04b-admin-settings.md).

Talab (foydalanuvchi, so'zma-so'z): «Barcha sozlamalar iloji boricha admin paneldan boshqariladigon qilish kerak».

Bajarilish tartibi: 4-reja (Ops) → **04b** → S1 … S5. S1–S5 rejalari o'zgartirilmaydi — ularga
`.superpowers/sdd/admin-settings-carry/amendments-s1-s5.md` dagi tuzatishlar har vazifa brifiga qo'shib beriladi.

## 1. Maqsad va doira

- Biznes, ETL, saqlash, monitoring va xavfsizlik siyosatining har bir qiymati — bitta tipli reyestr kaliti;
  administrator uni «Администрирование» bo'limidan o'zgartiradi, o'zgarish qayta ishga tushirishsiz kuchga kiradi,
  har o'zgarish versiyalanadi va auditga yoziladi.
- Integratsiya hisob ma'lumotlari (SMTP, keyinchalik 1C, HR, Telegram, AI) panelda kiritiladi, AES-256-GCM
  (`integration_creds`) bilan shifrlanib saqlanadi va hech qachon qaytarilmaydi; «Проверить подключение» bor.
- Infratuzilma va kriptografik ildiz (KEK, DB rollari, TLS, portlar, tarmoq/egress, `ENV`) panelga chiqmaydi —
  ularni o'zgartirish OS operatori va reliz jarayonining ishi (ekspertiza: ajratilgan vazifalar).
- Doiradan tashqari: ikki kishilik tasdiq (four-eyes), admin rolidan `admin:security`ni olib tashlash imkoni,
  sertifikat/CA yuklash, rate-limit oynalarini (sekund) o'zgartirish.

## 2. Inventarizatsiya va tasnif

Sinflar: **A** — infratuzilma/bootstrap (env, Docker secrets, compose, kod invarianti); **B** — panelda,
`admin:settings`, qo'shimcha himoyasiz; **C** — panelda, himoya bilan (chegaralar, sabab, kerak bo'lsa TOTP, alohida
ruxsat, audit eski/yangi); **D** — integratsiya siri: panelda faqat yoziladi, shifrlangan, tekshirish tugmasi.
Jami: **A 42, B 39, C 42, D 9**.

### A — panelga chiqmaydi (42)

| Guruh | Elementlar | Sabab |
|---|---|---|
| `Settings` (1–3-rejalar), 23 | `env`, `base_url`, `argon2_profile`, `db_host/port/name`, `db_{app,etl,migrator}_user`, `db_{app,etl,migrator}_password`, `db_pool_size`, `db_statement_timeout_ms`, `redis_host/port/password`, `master_kek`, `blind_index_key`, `session_pepper`, `etl_statement_timeout_ms`, `etl_file_dir`, `synthetic_seed` | Ulanish va kriptografik ildiz: DB'dan o'qib bo'lmaydi (tovuq-tuxum); KEK va rol parollari OS operatorida (1-reja I2 qarori); pool/timeout — engine yaratishda; katalog — mount yo'li |
| 4-reja, 7 | TLS sertifikat/kalit, host portlari (`UGK_HTTPS_PORT`, `UGK_HTTP_PORT`), `UGK_PG_PROFILE` + `postgresql.conf`, pgBackRest jadvali/saqlash/shifr (`BACKUP_*`, `repo1-*`), `UGK_VERSION` + `images.lock.env`, Docker tarmoqlari/egress, monitor/tiklash testi timer'lari | Tarmoqsiz `backup` konteyneri DB'ni o'qimaydi (izolyatsiya); qolganlari — host/compose darajasi |
| S1–S5, 12 | `onec_ca_file`, `onec_allow_http`, `egress_proxy`, `cbu_base_url`, `telegram_api_base`, `bank_inbox_dir`, `bank_archive_dir`, `askue_inbox_dir`, `hr_ca_file`, `ai_provider`, `ai_base_url`, `ai_ca_file` | Ishonch ildizi (CA), TLS'ni o'chirish, tashqi manzil va egress — infosec tasdig'i bilan bog'liq (S5 qarori: AI egress faqat overlay); katalog — mount |

Kod invariantlari (A sanog'iga kirmaydi, reliz bilan o'zgaradi): Argon2 parametrlari, TOTP qadami/raqamlar,
MFA challenge muddati/urinishlar, CSRF va cookie nomlari, shifrmatn formati, `MAX_BODY_BYTES`, CSP/HSTS, `SLIDE_EVERY`,
kesh TTL'lari, `ERROR_LIMIT`, audit verify limiti, ETL qayta urinish kechikishlari, freshness tekshiruvi oralig'i (30 daqiqa).

### B — `admin:settings` (39)

| Manba | Kalitlar |
|---|---|
| Mavjud (2-reja), 5 + 2 guruh | `freshness.max_age_hours`, `etl.history_start`, `etl.synthetic_cron`, `builds.keep`, `partitions.months_ahead`; «Пороги „Требует внимания“» (20 qoida) va «Допущения финмодели» — mavjud sahifalar, o'zgarishsiz |
| 04b, 3 | `maintenance.partitions_cron` (`30 3 * * *`), `maintenance.cleanup_cron` (`0 4 * * *`), `etl.incremental_lookback_days` (45; 7..120) |
| S1, 6 | `kazna.calendar_kinds`, `onec.orgs`, `onec.income_enabled`, `onec.page_limit`, `etl.onec_full_cron`, `etl.onec_incremental_cron` |
| S2, 8 | `banks.accounts`, `banks.statement_branches`, `banks.formats`, `etl.banks_cron`, `etl.cbu_cron`, `fx.currencies`, `fx.lookback_days`, `telegram.summary_cron` |
| S3, 9 | `askue.stations`, `askue.inbox_days`, `askue.live_cron`, `askue.live_keep_days`, `askue.live_stale_minutes`, `etl.askue_cron`, `onec.sklad_months`, `etl.onec_sklad_full_cron`, `etl.onec_sklad_incremental_cron` |
| S4, 4 | `zakupki.method_norms`, `hr.orgs`, `etl.hr_cron`, `etl.onec_zakupki_cron` |
| S5, 2 | `finmodel.dscr_covenant`, `finmodel.opex_exclude_items` |

### C — himoyalangan (42)

| Guruh | Kalitlar (standart; ruxsat etilgan oraliq) | Ruxsat | Himoya |
|---|---|---|---|
| Xavfsizlik siyosati, 12 | `security.session_idle_minutes` (30; 5..30), `security.session_absolute_hours` (12; 1..12), `security.password_max_age_days` (90; 30..90), `security.login_max_failures` (5; 3..5), `security.login_lockout_minutes` (15; 15..1440), `security.password_min_length` (12; 12..64), `security.password_history` (5; 5..24), `ratelimit.login_per_min` (10; 3..10), `ratelimit.mfa_per_min` (20; 5..20), `ratelimit.api_per_min` (300; 60..300), `ratelimit.password_change_per_15min` (5; 1..5), `retention.audit_months` (12; 12..120) | `admin:security` | sabab + TOTP |
| Monitoring chegaralari (4-reja `ops-check`), 5 | `ops.restore_max_age_days` (35; 1..35), `ops.dek_max_age_days` (365; 30..365), `ops.clock_skew_max_seconds` (60; 5..60), `ops.tls_warn_days` (30; 30..90), `ops.tls_critical_days` (7; 7..30) | `admin:security` | sabab + TOTP |
| Ma'lumot sifati va saqlash, 4 | `retention.fact_years` (5; 5..10), `quality.control_tolerance` (0.001; 0..0.01), `quality.balance_tolerance` (0.01; 0..1 mln so'm), `notify.email_to` (env `SMTP_TO`; ≤ 20 manzil) | `admin:settings` | sabab |
| Integratsiya maydonlari, 18 | SMTP: `smtp.host`, `smtp.port`, `smtp.from`, `smtp.user`, `smtp.starttls`, `smtp.ssl`; S1: `onec.base_url`, `onec.max_mb`; S2: `telegram.chat_ids`, `cbu.enabled`; S3: `askue.live_url`, `onec_sklad.base_url`; S4: `hr.base_url`, `hr.breakdown_path`; S5: `ai.model`, `ai.effort`, `ai.max_tokens`, `ai.fallbacks` | `admin:integrations` | sabab + TOTP; manzil o'zgarsa sir tozalanadi |
| AI yoqish va limitlar (S5), 3 | `ai.enabled` (false), `ai.user_per_hour` (20), `ai.org_per_day` (300) | `admin:security` | sabab + TOTP (sababga infosec xati raqami yoziladi) |

### D — integratsiya sirlari (9)

`smtp.password`; S1: `onec.username`, `onec.password`; S2: `telegram.bot_token`; S3: `onec_sklad.username`,
`onec_sklad.password`; S4: `hr.username`, `hr.password`; S5: `ai.api_key`.

## 3. Asosiy qarorlar

1. **Yagona reyestr** `backend/app/core/sysconfig.py`: har kalit — `SettingDef` (tur va chegaralar bitta joyda,
   kategoriya, ruxsat, `guarded`, `apply`, env bog'lanishi). `app.dwh.reference` dagi `DEFAULT_SETTINGS`,
   `SETTING_TYPES`, `validate_setting`, `current_setting` reyestrdan hosil bo'ladigan taxalluslar bo'lib qoladi.
2. **Manba ustuvorligi:** panel (`core.settings`) > env/Docker secret (faqat `env` bog'langan kalitlar: SMTP,
   `notify.email_to`) > kod standarti. Har manbadagi qiymat o'sha adapter bilan tekshiriladi; yaroqsiz bo'lsa keyingi
   manba olinadi va log'ga `setting_invalid` yoziladi. Xavfsizlik siyosati kalitlarida env bog'lanishi yo'q —
   env orqali siyosatni zaiflashtirib bo'lmaydi.
3. **Faqat qattiqlashtirish:** xavfsizlik va monitoring kalitlarining zaif tomondagi chegarasi = hujjatlarda
   (docs/security) e'lon qilingan qiymat. Administrator siyosatni faqat qattiqroq qila oladi; ekspertizadagi da'volar
   har qanday panel qiymatida rost qoladi. Eski yoki qo'lda yozilgan yaroqsiz qiymat o'qishda standartga qaytadi.
4. **Kuchga kirish:** issiq yo'l (sessiya, bloklash, parol, rate limit) — jarayon keshi `sysconfig.value()`, TTL
   30 s, yozgan jarayonda darhol `invalidate()`; ETL/worker/CLI — `sysconfig.current(conn, key)` tranzaksiya ichida
   (keshsiz). Worker cron jadvallari — `sync_schedules` jobi har 60 s da `reschedule_job` qiladi. `apply`:
   `live` (≤ 60 s) yoki `next_run` (keyingi yuklash/texnik xizmatda). Qayta ishga tushirish talab qiluvchi kalit
   reyestrga kiritilmaydi (A sinfi).
5. **Sirlar:** `core.integration_credentials(name, value_enc, updated_by, updated_at)` — `keystore.encrypt_str(Purpose.INTEGRATION, …)`,
   AAD `core.integration_credentials.value_enc:{name}`, `reencrypt.REGISTRY` da (`role="app"`) — DEK rotatsiyasi va
   retire qamrab oladi. Tarix saqlanmaydi (eski sir qatori qolmaydi), audit faqat `set`/`cleared` yozadi.
   API sir qiymatini hech qachon qaytarmaydi: faqat holat `panel` / `env` / `none` va vaqt.
6. **Manzilga bog'langan sir:** integratsiyaning manzil kaliti (`smtp.host`, `smtp.port`, `onec.base_url`, …) panelda
   o'zgarsa va shu so'rovda yangi sir berilmasa — saqlangan sir o'chiriladi; manzil panelda qayta belgilangan bo'lsa,
   env'dagi sir fallback sifatida ishlatilmaydi. Sabab: hisob ma'lumotini begona serverga yo'naltirish (credential
   redirect) imkoni yopiladi.
7. **Step-up:** `admin:security` va `admin:integrations` kalitlarini o'zgartirish joriy TOTP kodini talab qiladi
   (zaxira kodi emas, qayta ishlatish taqiqlangan — `totp_last_step`), xato kod — audit `auth.step_up.failed`,
   limit 5 / 15 daqiqa. Bu ASVS 3.7.1 ni shu operatsiyalar uchun yopadi va ikki kishilik tasdiq o'rnini bosadi.
8. **RBAC:** yangi ruxsatlar `admin:security` (xavfsizlik siyosati, monitoring chegaralari, AI yoqish, audit saqlash)
   va `admin:integrations` (ulanishlar va sirlar). `admin:settings` — biznes/ETL sozlamalari. Kod ro'yxatiga yangi
   qo'shilgan va admin seed roliga tegishli ruxsat mavjud «Администратор» roliga `sync_reference` da **bir marta**
   beriladi (keyin olib tashlansa qayta qo'shilmaydi).
9. **Yo'qolgan yangilanish:** `PUT /admin/settings/{key}` `expected_version` qabul qiladi; mos kelmasa 409
   `conflict_modified` (Plan 2 carry).
10. **Migratsiya** `0008a` (`down_revision = "0008"`): S1–S5 `0009..0021` raqamlari band; S1 ning `0009`
    migratsiyasida faqat `down_revision = "0008a"` o'zgaradi (S1 rejasi buni allaqachon ko'zda tutgan).

## 4. Arxitektura

### 4.1 Reyestr
`SettingDef(key, default, adapter, kind, category, title, perm, guarded, apply, unit, lo, hi, env, env_attr)`;
`kind ∈ int|float|bool|str|cron|date|list|json` — UI muharriri shu bo'yicha tanlanadi. Kategoriyalar: `data`, `etl`,
`quality`, `retention`, `notify`, `security`, `ops`, `integrations`, keyin bo'lim nomlari (`kazna`, `banks`, …).
`step_up = guarded and perm != admin:settings`. Integratsiya maydonlari `category = "integrations"` va faqat
integratsiya API orqali o'zgaradi (6-qoida shu yerda bajariladi).

### 4.2 Integratsiyalar
`backend/app/core/integrations.py`: `IntegrationDef(name, title, fields, endpoint, secrets, check_in)`,
`SecretDef(name, title, env, pattern, max_length)`; `secret(conn, name)` (faqat ishlatish joyida), `secret_state`,
`store_secret`, `clear_secret`, `RULES` (integratsiya darajasidagi tekshiruvlar, masalan SMTP: parol bor — TLS shart).
04b'da bitta integratsiya — `smtp`; S1–S5 o'zinikini qo'shadi. Tekshirish: `core.integration_checks` navbati,
worker `integration_checks` jobi (10 s) probe'ni bajaradi va faqat xavfsiz kod yozadi (`ok`, `auth_failed`,
`tls_failed`, `timeout`, `connect_failed`, `protocol_error`, `not_configured`, `insecure_refused`) — xato matni
saqlanmaydi (unda sir bo'lishi mumkin). Egress faqat worker'da bo'lgani uchun probe worker'da (`check_in="worker"`);
S5 AI probe — `api` (overlay egress).

### 4.3 API
- `GET /admin/settings` — `require_perm(admin:settings | admin:security | admin:integrations, any_of)`; faqat
  foydalanuvchi ruxsati bor va `integrations` bo'lmagan kalitlar; har biri: qiymat, versiya, manba, standart,
  metadata (`kind`, `lo`, `hi`, `unit`, `apply`, `guarded`, `step_up`, `perm`, `category`, `title`).
- `PUT /admin/settings/{key}` — `{value, expected_version?, reason?, otp?}`; kalit ruxsati serverda tekshiriladi.
- `GET /admin/settings/{key}/history` — versiyalar (integratsiya maydonlari uchun ham).
- `GET /admin/integrations`, `PUT /admin/integrations/{name}` — `{values, secrets: {name: str|null}, reason, otp}`,
  `POST /admin/integrations/{name}/check` (202, takror bosilsa o'sha so'rov), `GET /admin/integrations/checks/{id}` —
  hammasi `admin:integrations`.
- `GET /auth/me` + `password_min_length` (parol almashtirish sahifasi qoidasi uchun).
- Xato kodlari: `reason_required`, `step_up_required`, `step_up_failed` (422, `fields`), `invalid_setting`
  (`lo`, `hi`), `invalid_secret`, `insecure_smtp`, `conflict_modified` (409).

### 4.4 Audit
`admin.setting.updated` (mavjud) — `before`, `after`, `version`, `reason`; `admin.integration.updated` —
`changes[{key, before, after, version}]`, `secrets[{name, action: set|cleared|cleared_endpoint_changed}]`, `reason`;
`admin.integration.check_requested`; `auth.step_up.failed`. Sir qiymati, uning uzunligi yoki xeshi yozilmaydi.

### 4.5 UI
Admin menyusiga uchta sahifa: «Настройки» (`admin:settings`), «Политика безопасности» (`admin:security`),
«Интеграции» (`admin:integrations`). Sozlamalar kategoriya bo'yicha kartalarda (jadval: nomi, qiymat, manba,
versiya, o'zgargan); qatorni bosish — muharrir dialogi: tur bo'yicha maydon, oraliq ko'rsatmasi va mijoz
tomonida tekshiruv, `guarded` — «Причина изменения», `step_up` — «Код из приложения», `apply = next_run` —
«Применяется со следующей загрузки», tarix jadvali. Integratsiya kartasi: maydonlar, sirlar holati
(«задан в панели {дата}» / «из конфигурации сервера» / «не задан»), «Изменить» (sir maydoni bo'sh = o'zgarmaydi,
«Удалить сохранённое значение»), manzil o'zgarsa ogohlantirish, «Проверить подключение» (natija kodi ruscha).

## 5. Boshqa rejalar bilan bog'liqlik
- **4-reja:** kodga tuzatish yo'q (u avval bajariladi). 04b'ning 8-vazifasi `app/ops.py` chegaralarini reyestrga
  o'tkazadi, 12-vazifasi `docs/security/*` (kirish matritsasi, xavfsiz konfiguratsiya, audit, ASVS 3.7.1/4.3.3/14.x,
  ma'lumotlar tasnifi, kalitlar reglamenti) va `docs/ops/admin-guide.md` ni yangilaydi. 4-reja hujjatlaridagi
  «idle 30 / absolyut 12 soat» kabi da'volar «eng zaif ruxsat etilgan qiymat» sifatida rost qoladi.
- **S1–S5:** har yangi sozlama `SettingDef`, har yangi sir `SecretDef`, har yangi cron — `add_cron_job`, har tashqi
  tizim — `IntegrationDef` + probe; integratsiya sozlanmagan bo'lsa job qo'shiladi, lekin `not_configured` bilan
  o'tkazib yuboradi. Ro'yxat: `.superpowers/sdd/admin-settings-carry/amendments-s1-s5.md`.

## 6. Xatarlar va ochiq savollar
- Admin roli doim `admin:security` va `admin:integrations` ga ega (admin rolini API orqali tahrirlab bo'lmaydi —
  1-reja qarori). To'liq vazifa ajratilishi (admin ≠ ИБ) kerak bo'lsa — mijoz qarori, alohida kichik vazifa.
- Panel va env'da bir xil sir turishi mumkin (bootstrap uchun). UI manbani ko'rsatadi; admin qo'llanmasi panelga
  o'tgach Docker secret'ni bo'shatishni talab qiladi.
- Kesh TTL 30 s: siyosat o'zgarishi boshqa jarayonlarda 30 s gacha kechikadi (yozgan jarayonda darhol).
- Ikki kishilik tasdiq yo'q — o'rniga alohida ruxsat + sabab + TOTP + audit. Mijoz/ИБ talab qilsa — alohida reja.
- `last_restore_test` tizim yozuvi panelda ko'rsatilmaydi (4-reja qarori, o'zgarishsiz).
