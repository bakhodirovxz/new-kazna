# UGEKAZNA — «Ввод данных»: 1C bermaydigan ma'lumotni qo'lda kiritish va fayldan yuklash — dizayn spetsifikatsiyasi

- Sana: 2026-10-27
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: buyurtmachi talabi «Ma'lumot kiritish» — «fayl yuklashmi yoki qo'lda formalarmi?» savoliga javob:
  **«Ikkalasi ham»**. Poydevor spec'i [2026-09-24-poydevor-design.md](2026-09-24-poydevor-design.md) (3.3–3.6, 4, 5);
  S1–S5 spec'lari (bo'shliqlar: S1 G2/G4/G5/G6, S2 §3.1, S3 §3.1/G5/G7/G8, S4 §3.2/§3.3, S5 §3.3);
  04b [2026-10-26-admin-settings-design.md](2026-10-26-admin-settings-design.md) (reyestr, `expected_version`, sabab,
  step-up). Kod holati — `demo/mvp` (d9ecad9): `app/etl/{runner,merge,staging,file_connector}.py`,
  `app/dwh/{targets,aggregates,treasury_aggregates,builds}.py`, `app/etl/quality.py`, `app/auth/{permissions,context,stepup,seed}.py`,
  `app/audit/service.py`, `app/core/{sysconfig,keystore,reencrypt,ratelimit}.py`, migratsiyalar 0001–0010 (+0008a).
- Reja: [../plans/2026-10-27-manual-data-entry.md](../plans/2026-10-27-manual-data-entry.md).

## 1. Maqsad va chegaralar

Vakolatli foydalanuvchi 1C (va boshqa avtomatik manbalar) bermaydigan yozuvlarni UI'da qo'shadi, tahrirlaydi va
o'chiradi — formada, Excel'ga o'xshash jadvalda (oy × statya) yoki kanonik shablondagi CSV/XLSX faylni yuklab.
Yozuvlar **hech qachon to'g'ridan-to'g'ri `dwh`/`mart` ga yozilmaydi**: ular `core.manual_*` omboriga
versiya bilan tushadi, ikkinchi shaxs tasdiqlagach mavjud ETL pipeline'i (`ManualConnector` →
stg → merge → aggregates → quality → publish) orqali витринага chiqadi. Natija — dashboard'lar «Источник не
подключён» o'rniga haqiqiy raqam ko'rsatadi, har o'zgarish auditda, eski build'ga qaytish (rollback) ishlaydi.

**Kiradi:** qo'lda kiritish ombori (`core.manual_batch`, `core.manual_head`, `core.manual_entry`, 0022);
obyektlar reyestri (`app/manual/entities.py`, 17 ta obyekt, 5 bo'lim); maker–checker (paket = «пакет»);
`ManualConnector` (`source = "manual"`); manbalar ustuvorligi view'lari `dwh.*_effective` (0023) va agregatlarning
ularga o'tishi; sifat tekshiruvi 2 uchun qo'lda kiritilgan qoldiq istisnosi; davrni yopish
(`manual.locked_through`); yangi ruxsatlar `data:<bo'lim>:write|approve`; API `/api/v1/data/*`; shablon
(CSV/XLSX) va import; UI — markaziy «Ввод данных» bo'limi (reyestr, drawer-forma, jadval muharriri, import,
«История изменений», «На согласовании») + bo'lim sahifalaridan chuqur havola; testlar; ekspertiza hujjatlari.

**Kirmaydi:** pul oqimi (`fact_cashflow`), to'lov topshiriqlari holati (`fact_payment_order`), ЦБ kurslari, АСКУЭ
fakt ishlab chiqarishi, ombor qoldiqlari qiymati — bular faqat avtomatik manbadan (§2.3); maydon darajasidagi
birlashtirish (bitta qatorning bir qismi 1C'dan, qolgani qo'ldan — §4.4); tasdiqlovchiga e-mail/Telegram
xabarnomasi; ombor minimal zaxirasi va xarid lotlari (2-bosqich, §2.2); `fact_cashflow` statyalarini qayta
tasniflash (ПКМ №54 — S1 G7).

## 2. Qamrov — obyektlar

### 2.1 Tamoyillar
- **Fakt** — vaqt qatori (`date_id` bor, `fact_*` ga tushadi); **reference** — o'lchov (`dim_*`), davrsiz.
- Har obyekt bitta `Target` (2-reja `app/dwh/targets.py`) ga moslanadi; maydon nomlari = `Target.allowed_keys`
  = FileConnector kanonik CSV sarlavhalari. Shuning uchun UI shabloni, ops inbox fayli (`FileConnector`) va qo'lda
  kiritish **bitta format**da (docs/integration/*-fayl.md).
- `doc_type` obyekt bo'yicha qat'iy (`manual_balance`, `manual_plan`, …); semantik ajratuvchi `doc_type` lar
  mavjud qiymatni oladi: kalendar — `payment_schedule` (`SCHEDULE_DOC_TYPE`), ishlab chiqarish rejasi —
  `generation_plan` (S3). `src_id = "M:<entry_id>"`, `src_system = "manual"`.
- Qo'lda yaratilgan reference kodi `M-<tur>-<entry_id>` (masalan `M-CT-42`) — 1C/fayl kodlari bilan
  to'qnashmaydi. Istisno — tabiiy identifikatori bor o'lchovlar S2 sxemasidagi kodni oladi: bank hisobi
  `BA-<HMAC(blind_index_key, hisob)[:16]>`, kontragent (9 xonali INN) `CP-<HMAC(inn)[:16]>` — keyin bank fayli yoki
  1C o'sha hisob/kontragentni bersa, `dwh` da **bitta** qator bo'ladi.
- 1C/fayldan kelgan reference qo'lda tahrirlanmaydi (UI'da faqat tanlash); qo'lda — faqat `M-`/`BA-`/`CP-`
  kodli, manual omborda boshlangan yozuvlar.

### 2.2 Obyektlar reyestri

| № | Obyekt (`entity`) | UI nomi | Tur → `Target` | Asosiy maydonlar | Bo'shliq / manba munosabati | Tartib |
|---|---|---|---|---|---|---|
| 1 | `kazna.bank_account` | Банковские счета | ref → `dim_bank` | filial, bank, hisob raqami (shifr.), valyuta | S1 G2/G10; S2 bank fayli kelsa — o'sha `BA-` kod | **MVP** |
| 2 | `kazna.balance` | Остатки на счетах | fakt → `fact_balance` | filial, hisob, sana, qoldiq (mln so'm, manfiy mumkin) | S1 G2 (2 kritik qoida); S2 ko'chirma — ustun | **MVP** |
| 3 | `kazna.payment_plan` | План платежей (бюджет) | fakt → `fact_payment_plan` | filial, statya, oy, summa | 1C `/budget` (S1) — ustun; jadval (statya × oy) | **MVP** |
| 4 | `kazna.payment_schedule` | Платёжный календарь | fakt → `fact_payment_plan` (`payment_schedule`) | filial, statya, sana (≤ +366 kun), summa | S1 G5 | 2 |
| 5 | `kazna.counterparty` | Контрагенты | ref → `dim_counterparty` | nomi, INN (shifr., faqat yuridik shaxs), tur | S1 G7 | 2 |
| 6 | `kazna.contract` | Договоры | ref → `dim_contract` | filial, raqam, sana, kontragent, summa, muddat, tur, АИП obyekti | S1 G4 | 2 |
| 7 | `kazna.debt` | Задолженность по договорам | fakt → `fact_debt` | filial, shartnoma, sana, Дт/Кт сальдо, просрочка, kunlar | S1 G4 (2 qoida) | 2 |
| 8 | `kazna.funding_source` | Источники финансирования | ref → `dim_source` | nomi, tur (`budget/ifi/bank/own`) | S1 G6, S4 | 2 |
| 9 | `kazna.target_funds` | Целевые средства | fakt → `fact_target_funds` | filial, manba, obyekt (ixt.), oy, выделено, использовано | S1 G6 | 2 |
| 10 | `kredity.loan` | Кредиты (реестр) | ref → `dim_loan` (SCD-2 stavka) | filial, kreditor, loyiha, valyuta, stavka, imtiyoz, muddat, summa | S2 §3.1 (prod — CSV) | 3 |
| 11 | `kredity.loan_schedule` | График погашения | fakt → `fact_loan_schedule` (forward) | kredit, sana, asosiy qarz, foiz, qoldiq (kredit valyutasida) | S2 §3.1 | 3 |
| 12 | `proizvodstvo.generation_plan` | План выработки | fakt → `fact_generation` (`generation_plan`) | stansiya, oy, reja (mln kVt·soat); jadval (stansiya × oy) | S3 G8 | 4 |
| 13 | `proizvodstvo.energy_sales` | Реализация электроэнергии | fakt → `fact_energy_sales` | filial, xaridor, oy, начислено, оплачено, hajm | S3 G7 | 4 |
| 14 | `investicii.object` | Объекты АИП | ref → `dim_object` | nomi, dastur kodi, ish turi, manba, yil, smeta | S4 §3.2 | 4 |
| 15 | `investicii.aip_month` | АИП: план и освоение | fakt → `fact_investment` | filial, obyekt, oy, reja, fakt, КС-2 %, avans, avans sanasi | S4 §3.2, S5 §3.3 | 4 |
| 16 | `investicii.object_stage` | Этапы объектов | fakt → `fact_object_stage` (S4) | obyekt, bosqich №, nomi, reja/fakt sanasi | S4 §3.2 | 4 |
| 17 | `kadry.headcount` | Штат и численность | fakt → `fact_hr` | filial, toifa, oy, штат, факт, принято, уволено, сверхурочные; jadval (toifa × oy, штат) | S4 §3.3 | 4 |

«Tartib» — rejadagi to'lqin (§9). 2-bosqichga qoldiriladi: **ombor minimal zaxirasi** (S3 1C ombori subschyot
darajasida — nomenklatura × ombor kalitiga minimum bog'lanmaydi, alohida tuzilma kerak; mijoz savoli 10) va
**xarid lotlari** (portal integratsiyasi kutilmoqda, hajm katta — UI import CSV yetarli bo'lishi mumkin).
«Кадры» obyektida ФИО yoki boshqa shaxsiy maydon **yo'q** (S4 testiga obyekt ham qo'shiladi).

### 2.3 Nima qo'lda kiritilmaydi (qaror)
`fact_cashflow`, `fact_payment_order`, `fx_rate`, `fact_generation` fakti, `fact_stock`/`fact_stock_move`,
`fact_power_snapshot`, `dim_branch`, `dim_item`. Sabab: ular pul harakati va texnologik o'lchovlar — 1C/bank/АСКУЭ
yagona haqiqat manbai; qo'lda kiritish nazorat summasi (sifat 1) va «Разница» (sifat 2) ma'nosini buzadi.

## 3. Ma'lumot oqimi (asosiy qaror)

```
UI forma / jadval / fayl ──► POST /api/v1/data/batches (ugk_app, RLS)
        core.manual_batch (черновик → на согласовании → утверждено)
        core.manual_head (yozuv boshi: tasdiqlangan versiya, kutilayotgan paket, versiya hisoblagichi)
        core.manual_entry (append-only versiyalar; sezgir maydon AES-256-GCM)
                  │  tasdiq (boshqa shaxs) → core.etl_requests (source='manual', mode='full'), takrorlanmaydi
                  ▼
worker process_requests (30 s) → Runner(ManualConnector) — ETL qulfi ostida
  extract: tasdiqlangan joriy versiyalar → stg.rows (sezgir maydon staging'da qayta shifrlanadi)
  dims → facts: merge_target(..., replace=True) — `src_system='manual'` qatorlari to'liq almashtiriladi
  aggregates: `dwh.*_effective` view'laridan (ustuvorlik) → mart (yangi build)
  quality → publish (core.data_version) — xato bo'lsa oldingi build aktiv qoladi
```

### 3.1 Ombor (0022)
- `core.manual_batch` — paket («пакет»): `entity`, `branch_id`, `status ∈ {draft, submitted, approved, rejected,
  withdrawn}` («Черновик», «На согласовании», «Утверждено», «Отклонено», «Отозвано»), `origin ∈ {form, grid, import}`,
  `file_sha256`, `reason`, `created_by/at`, `submitted_at`, `decided_by/at`, `decision_comment`, `content_hash`
  (submit paytidagi kanonik mazmun SHA-256), `version` (optimistik qulf), `etl_request_id`.
  `CHECK (decided_by IS NULL OR decided_by <> created_by)` — o'zini tasdiqlash DB darajasida taqiqlangan.
- `core.manual_head` — bitta biznes-yozuv: `entity`, `branch_id`, `business_key` (`UNIQUE (entity, business_key)` —
  bitta hisob-sanaga ikki qoldiq bo'lmaydi), `code` (reference uchun), `approved_version`, `approved_deleted`,
  `pending_batch_id` (bitta yozuvda bir vaqtda bitta kutilayotgan o'zgarish), `version` (so'nggi versiya raqami —
  `expected_version`).
- `core.manual_entry` — versiya: `entry_id`, `version`, `batch_id`, `branch_id`, `payload jsonb` (sezgir bo'lmagan
  kanonik qiymatlar), `bank_enc`/`pii_enc` (bytea, AAD `core.manual_entry.bank_enc:{id}` / `…pii_enc:{id}`),
  `masks jsonb` (`{"account_number": "…1234"}`), `deleted`, `created_by/at`. **Append-only**: UPDATE faqat
  `*_enc` ustunlarida (kalit rotatsiyasi `reencrypt`), DELETE faqat `draft` paketda (trigger).
- Uchala jadval — `ENABLE + FORCE ROW LEVEL SECURITY`, policy `core.rls_branch_ok(branch_id)` (USING + WITH CHECK).
  Filial foydalanuvchisi boshqa filial yozuvini SQL orqali ham ko'rmaydi va yoza olmaydi.

### 3.2 Versiyalar, tuzatish va o'chirish
- Tuzatish — yangi versiya yangi paketda (tasdiq bilan). O'chirish — `deleted = true` versiya (tombstone),
  tasdiq bilan. **Storno ishlatilmaydi**: BI qatlamida yozuv holati muhim, buxgalteriya proводкаси emas; tarix
  (oldingi versiyalar) to'liq saqlanadi va «История изменений» da ko'rinadi.
- Tasdiqlangan yozuvni tuzatish/o'chirish paketida «Причина изменения» (≥ 5 belgi) majburiy; rad etishda
  izoh majburiy.
- Reference o'chirilsa `dwh` o'lchov qatori qoladi (FK nishoni); unga bog'langan qo'lda kiritilgan faktlar bor
  bo'lsa o'chirishga ruxsat yo'q (`reference_in_use`).

### 3.3 `ManualConnector`
`source = "manual"`; `extract` o'z `etl_transaction()` ida `scope_all` bilan `approved_version` qatorlarini
o'qiydi (`approved_deleted = false`), sezgir maydonni `keystore.decrypt_str` bilan ochadi va `sink.add(target, …)`
ga beradi (`app.etl.staging.protect()` dwh AAD bilan qayta shifrlaydi — ochiq qiymat faqat worker xotirasida);
`by_target` — barcha qo'lda kiritiladigan maqsadlar (0 qatorlilari ham) → `merge_facts(..., complete=…)` ularni
`src_system='manual'` doirasida **to'liq almashtiradi** (o'chirilgan yozuv `dwh` dan ketadi). Oyna — `Mode.FULL`
(tarix boshidan bugungacha; `forward` maqsadlarda yuqori chegara yo'q) — hajm kichik. `watermark` —
oxirgi `decided_at`; `control_totals` — `None`. Reference'lar dims bosqichida faktlardan oldin birlashadi.
Rejalashtirilgan cron yo'q — faqat tasdiq navbati (boshqa manbalarning yuklashlari `manual` qatorlariga tegmaydi:
`_replace_sql` faqat o'z `src_system` ini o'chiradi).

### 3.4 Manbalar ustuvorligi — `dwh.*_effective` (0023)
Qo'lda kiritilgan yozuv **bo'shliqni to'ldiradi, avtomatik manbani almashtirmaydi**. Har qo'lda kiritiladigan fakt
uchun view: `src_system = 'manual'` qatori, xuddi shu **don** (grain) da `manual` va `synthetic` dan boshqa manba
qatori bo'lsa — yashiriladi; `synthetic` qatori xuddi shu donda `manual` qatori bo'lsa — yashiriladi (dev/demo:
inson kiritgani sintetik o'rnini bosadi; prod'da sintetik yo'q). Boshqa manbalar juftligi o'zgarmaydi — qo'lda
yozuv bo'lmasa view = jadval (har view uchun test).

| View | Jadval | Don |
|---|---|---|
| `dwh.balance_effective` | `fact_balance` | filial, hisob, oy |
| `dwh.payment_plan_effective` | `fact_payment_plan` | filial, statya, oy (reja) / sana (`payment_schedule`), tur |
| `dwh.debt_effective` | `fact_debt` | shartnoma, oy |
| `dwh.target_funds_effective` | `fact_target_funds` | filial, manba, obyekt, oy |
| `dwh.loan_schedule_effective` | `fact_loan_schedule` | kredit, sana |
| `dwh.generation_effective` | `fact_generation` | filial, oy, `doc_type = generation_plan` (faktga tegmaydi) |
| `dwh.energy_sales_effective` | `fact_energy_sales` | filial, xaridor, oy |
| `dwh.investment_effective` | `fact_investment` | obyekt, oy |
| `dwh.hr_effective` | `fact_hr` | filial, toifa, oy |
| `dwh.object_stage_effective` (0024, S4 dan keyin) | `fact_object_stage` | obyekt, bosqich № |

Snapshot faktlarda (qoldiq, qarz, kadrlar) don — **oy**: tizim shu oyda shu kalitga biror qator bergan bo'lsa,
qo'lda kiritilgan oy qatorlari ishlatilmaydi (aks holda oy oxiridagi qo'lda yozuv tizimning oy ichidagi
snapshot'ini «oxirgi» sifatida bosib ketardi). Barcha agregat modullari (`app/dwh/*_aggregates.py`), S5
финмодель kirishlari va sifat tekshiruvlari shu view'larni o'qiydi; `tests/test_code_rules.py` ga qoida:
ro'yxatdagi `dwh.fact_*` ni agregat/finmodel/quality kodida to'g'ridan-to'g'ri o'qish taqiqlangan (S-rejalar
keyin qo'shadigan kod ham shu test bilan ushlanadi). `fact_cashflow` — S2 `dwh.cashflow_effective` o'zgarishsiz.
UI'da yozuv holati: «Действует», «Перекрыто источником (1С/банк/файл)», «Удалено». «Перекрыто» belgisi har
build'da (istalgan manba yuklaganda) kichik agregat `mart.agg_manual_shadow (build_id, branch_id, entry_id,
shadowed_by)` da hisoblanadi va `pub` view orqali o'qiladi — API `dwh` faktlarini o'qimaydi (TZ 9 qoidasi).

### 3.5 Sifat tekshiruvlari
- 1, 3, 4, 5 — o'zgarishsiz (qo'lda kiritishda o'lchovlar kiritish vaqtida tekshiriladi, `missing_dim` deyarli
  bo'lmaydi; bo'lsa — publish yo'q, xabarnoma).
- 2 («Разница» ≤ 1% oborot): filial-oyning kiruvchi yoki chiquvchi qoldig'ini bergan qatorlardan kamida bittasi
  `manual` bo'lsa — tekshiruv shu filial-oy uchun o'tkazib yuboriladi (`unverifiable`, sabab `manual_balance`),
  publish to'xtamaydi: qo'lda kiritilgan qoldiq va 1C talabnomalari orasidagi farq — manbalararo solishtirish,
  yuklash nuqsoni emas (S2 §3.4 qarori bilan bir xil mantiq; S2 6-vazifadagi istisno bilan birga ishlaydi).

### 3.6 Davrni yopish
`manual.locked_through` (`YYYY-MM`, standart bo'sh; `admin:settings`, `guarded` — sabab majburiy, audit) —
sana/oyi shu oy yoki undan oldin bo'lgan fakt yozuvini yaratish, tahrirlash, o'chirish, yuborish va **tasdiqlash**
taqiqlangan (`period_locked`, 422). Tuzatish kerak bo'lsa administrator chegarani sabab bilan oldinga suradi
(auditda), keyin qaytaradi. Reference'larga qo'llanmaydi. Avtomatik yopish (har oyning N-kuni) — mijoz savoli 3.

### 3.7 Nashr holati
Tasdiq tranzaksiyasida `core.etl_requests (source='manual', mode='full', requested_by=tasdiqlovchi)` yoziladi,
agar `pending` holatidagi `manual` so'rov yo'q bo'lsa (bor bo'lsa — o'sha so'rovga bog'lanadi; tasdiqlar
birlashadi). Paket holati UI'da: «Ожидает публикации» → «Публикуется» → «Опубликовано (сборка №N)» yoki «Ошибка
публикации» (sifat/xato — admin «Состояние обменов» sahifasiga havola). Har tasdiq yangi build yaratadi:
`builds.keep` (3) rollback chuqurligi vaqt bo'yicha qisqaradi — risk §8.

## 4. Xavfsizlik

### 4.1 Ruxsatlar va rollar
- Yangi ruxsatlar (kodda, `section_perm` kabi generatsiya): `data:<bo'lim>:write` — kiritish/tahrir/import/yuborish,
  `data:<bo'lim>:approve` — tasdiqlash/rad etish; bo'limlar: `kazna`, `kredity`, `proizvodstvo`, `investicii`,
  `kadry` (10 ta). `Perm` enum'iga **kirmaydi** — admin roli seed'i ularni avtomatik olmaydi (vazifalar ajratilishi:
  administrator foydalanuvchilarni boshqaradi, moliyaviy ma'lumot kiritmaydi).
- Seed: `spec_kazna` — `data:kazna:write`, `data:kredity:write`; `economist_filiala` — `data:{kazna,proizvodstvo,kadry}:write`
  (o'z filiali); `nach_otdela` — beshta `:approve`; qolganlar — yo'q (mijoz savoli 1). Mavjud bazalarda tizim
  rollariga kodga **yangi** qo'shilgan ruxsat `sync_reference` da **bir marta** beriladi (04b admin qoidasining
  umumlashmasi; keyin olib tashlansa qayta qo'shilmaydi).
- «История изменений»: shu bo'limda `write` yoki `approve` (o'z doirasida) yoki `audit:read`.
- DB: yangi DB roli **yo'q**. `ugk_app` — `core.manual_*` ga SELECT/INSERT, ustun darajasidagi UPDATE (holat
  ustunlari), draft'da DELETE (trigger); `dwh` ga yozish huquqi yo'q (o'zgarishsiz). `ugk_etl` — `core.manual_*`
  ga faqat SELECT. Tanlov ro'yxatlari uchun `ugk_app` ga `dwh` o'lchovlarining **sezgir bo'lmagan** ustunlariga
  SELECT (`dim_bank(bank_id, code, bank_name, currency, account_last4)`, `dim_counterparty(cp_id, code, name, kind)`,
  `dim_contract`, `dim_loan`, `dim_source`, `dim_object`, `dim_position`; `*_enc/*_bidx` — yo'q). `dim_contract`,
  `dim_loan` da RLS allaqachon bor.

### 4.2 Filial doirasi
Paket va yozuv `branch_id` bilan; API `ctx.assert_branch(branch_id)` (403 `scope_violation` + audit
`rls_violation_attempt`), DB — RLS WITH CHECK. Filialsiz `dwh` o'lchovlari (kontragent, manba, obyekt, bank
hisobi) uchun manual boshida yaratuvchining filiali turadi — tasdiqlash doirasi shu bilan; `dwh` ga chiqqach
ular hammaga tanlovda ko'rinadi. Tasdiqlovchining doirasi paket filialini qamrashi shart.

### 4.3 Maker–checker — **ha**
Barcha obyektlar uchun ikki shaxs: kirituvchi (`write`) yuboradi, boshqa foydalanuvchi (`approve`) tasdiqlaydi;
o'zini tasdiqlash — 403 `self_approval_forbidden` (servis) + DB `CHECK`. Sabablar: (1) qo'lda kiritilgan qoldiq va
qarz 1C nazoratlaridan tashqarida, ular kritik qoidalarni (S1 `cash_below_monthly_outflow`,
`payments_14d_exceed_balance`, `contracts_overdue_90d`) va rahbariyat hisobotini (Telegram 08:30) to'g'ridan-to'g'ri
o'zgartiradi — bitta xato raqam butun kompaniya uchun yolg'on signal; (2) ichki nazorat (vnutr_kontrol) va
ekspertiza uchun vazifalar ajratilishi (ASVS 1.4/4.1, ISO 27001 A.5.3) eng arzon tushuntiriladigan nazorat;
(3) tasdiq paket darajasida — 12 oylik jadval bitta bosish bilan tasdiqlanadi, sekinlashuv minimal.
04b'dagi «four-eyes o'rniga step-up» qarori bu yerga ko'chirilmaydi: u kam uchraydigan admin sozlamalari uchun;
bu yerda — ko'p sonli filial xodimlari kiritadigan moliyaviy ma'lumot. Step-up (TOTP) talab qilinmaydi (2FA
majburiy emas — 2026-10-27 qarori; tasdiqlovchi segregatsiyasi + audit yetarli).

### 4.4 Audit va shifrlash
- Hodisalar: `data.batch.saved` (yaratish/draft saqlash — soni), `data.batch.submitted` (diff + `content_hash`),
  `data.batch.approved` (`content_hash` — tasdiqlovchi aynan shu mazmunni tasdiqladi), `data.batch.rejected`,
  `data.batch.withdrawn`, `data.imported` (fayl nomi, SHA-256, qatorlar soni — mazmunsiz), `security.access_denied`
  / `rls_violation_attempt` (mavjud). Davr chegarasi — mavjud `admin.setting.updated`.
- Diff: har yozuv uchun `{entry_id, version, before, after}` (tasdiqlangan versiya ↔ yangi) — ≤ 100 yozuv, undan
  ko'pi — sonlar + `content_hash`; to'liq oldin/keyin qiymatlari append-only `core.manual_entry` da qoladi va
  `content_hash` audit hash-zanjiriga kiradi — keyingi har qanday o'zgartirish aniqlanadi.
- Sezgir maydonlar (bank hisob raqami — `Purpose.BANK`, kontragent INN — `Purpose.PII`): faqat `bank_enc`/`pii_enc`
  da AES-256-GCM, AAD `core.manual_entry.{bank_enc|pii_enc}:{id}` (poydevor 3.5 formati), `reencrypt.REGISTRY`
  (`role="app"`). Auditda, logda, `etl_error` da, javobda — faqat niqob (`…1234`) va `changed: true`. API sezgir
  qiymatni **qaytarmaydi** (faqat yoziladi; aniq qidiruv — blind index orqali kod). Ochiq qiymat faqat API
  so'rovi xotirasida (shifrlashdan oldin) va worker xotirasida (staging'dan oldin).

### 4.5 So'rov himoyasi
- CSRF — mavjud double-submit (barcha POST/PUT/DELETE); import — `fetch` bilan xom tana (`Content-Type: text/csv`
  yoki `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`), multipart yo'q (yangi bog'liqlik yo'q).
- Optimistik qulf: yozuvda `expected_version` (= `manual_head.version`), paketda `expected_version`
  (= `manual_batch.version`); mos kelmasa 409 `conflict_modified`. Kutilayotgan o'zgarishi bor yozuv — 409
  `pending_change`; takroriy biznes-kalit — 409 `duplicate_record` (mavjud yozuvga havola bilan).
- Rate limit: yozish `ratelimit.data_write_per_min` (60; 10..60, faqat qattiqlashtiriladi), import — 10 / 10 daqiqa
  foydalanuvchiga (kod konstantasi); umumiy 300/daq saqlanadi. Bitta so'rovda ≤ 500 yozuv.
- Kiritish tekshiruvi: Pydantic `extra='forbid'` (obyekt reyestridan quriladi), summalar `numeric(20,2)` chegarasi,
  sana oralig'i (`etl.history_start`..bugun; `forward` — +10 yil, kalendar — +366 kun), matn ≤ 200 belgi,
  boshqaruv belgilarisiz; reference mavjudligi (`dwh` yoki tasdiqlangan manual reference; draft'ga havola yo'q).
- Fayl: tana ≤ 1 MiB (mavjud `MAX_BODY_BYTES`, o'zgarmaydi), ≤ 5 000 qator; CSV — FileConnector qoidalari
  (UTF-8/BOM, `;`, ISO sana, razryad ajratkichisiz — `_number`/`_iso_date` qayta ishlatiladi); XLSX — `openpyxl`
  `read_only=True, data_only=True`, faqat birinchi varaq, ZIP a'zolari ≤ 100, yechilgan hajm ≤ 20 MiB, makros
  (`vbaProject.bin`) va tashqi havolalar rad, formulasi bor keshlanmagan katak rad; Python 3.12 expat'ining
  entity-amplification himoyasi (billion laughs testi). Import **hammasi yoki hech narsa**: xatoli qatorlar ro'yxati
  (`import_invalid`, ≤ 200 xato: qator, ustun, kod) qaytadi, hech narsa saqlanmaydi.
- Shablon yuklab olish — formula-injection himoyasi (S1 CSV qoidasi).

## 5. API (`/api/v1/data/*`)

| Metod va yo'l | Ruxsat (router) + servis tekshiruvi | Mazmun |
|---|---|---|
| `GET data/entities` | biror `data:*` yoki `audit:read` | foydalanuvchiga ruxsat etilgan obyektlar: maydonlar (tur, majburiy, chegaralar, birlik, ref), layout (`form`/`grid`), huquqlar |
| `GET data/entities/{e}/records?br&per&status&page` | `write`/`approve` | joriy yozuvlar: qiymat, holat (действует/перекрыто/удалено), kutilayotgan paket, `version` |
| `GET data/entities/{e}/options/{field}?q&br` | `write` | tanlov ro'yxati (≤ 50, RLS) |
| `GET data/records/{entry_id}/history` | `write`/`approve`/`audit:read` | versiyalar: kim, qachon, paket, sabab, oldin/keyin (niqoblangan) |
| `POST data/batches` | `write` | `{entity, branch_id, origin, items[], submit?, reason?}` → paket (`draft` yoki `submitted`) |
| `PUT data/batches/{id}` | `write`, faqat yaratuvchi, `draft` | `{expected_version, items[]}` — qo'shish/tahrir/o'chirish (`delete: true`) |
| `POST data/batches/{id}/submit` · `/withdraw` | yaratuvchi | `{expected_version, reason?}` |
| `POST data/batches/{id}/approve` · `/reject` | `approve`, ≠ yaratuvchi, doira | `{expected_version, comment}` → tasdiq + nashr so'rovi |
| `GET data/batches?box=mine|inbox&status` · `GET data/batches/{id}` | `write`/`approve` | paketlar ro'yxati; paket tafsiloti (tasdiqlangan versiyaga nisbatan diff, nashr holati) |
| `GET data/entities/{e}/template.csv|.xlsx` | `write` | kanonik shablon (sarlavhalar + ruscha izoh varag'i) |
| `POST data/entities/{e}/import?branch_id` | `write` | xom fayl → `draft` paket yoki 422 `import_invalid` |

Xato kodlari (`app/core/errors.py` `MESSAGES`, ruscha): `period_locked`, `duplicate_record`, `pending_change`,
`self_approval_forbidden`, `reference_not_found`, `reference_in_use`, `import_invalid`, `unsupported_file`,
`batch_not_editable`, mavjudlari `conflict_modified`, `reason_required`, `scope_violation`, `rate_limited`.
Barcha route'lar `EXPECTED_ROUTES` (route-guard testi) ga qo'shiladi.

## 6. UI

### 6.1 Joylashuv — markaziy «Ввод данных» + bo'limlardan havola (qaror)
Yuqori menyuda yangi guruh «Данные» → bo'lim «Ввод данных» (`#vvod/<sahifa>?br=&per=`), faqat biror `data:*`
ruxsati bo'lsa (`/meta/menu`). Chap menyu: «На согласовании» (hisoblagich, `approve` bo'lsa), «Мои пакеты», so'ng
bo'limlar bo'yicha guruhlangan obyektlar. Bo'lim sahifalaridagi «Источник не подключён» / «Нет данных за период»
holatida va kartaning ⋯ menyusida «Ввести данные» havolasi (faqat `write` bo'lsa) — tegishli obyekt sahifasiga
o'sha `br`/`per` bilan. Sabab: dashboard nashr qilingan agregatlarni ko'rsatadi, tasdiq + qayta qurish oralig'ida
kartada «tahrirlangan» raqam ko'rinmaydi — inline tahrir chalg'itadi; bitta umumiy (metadata asosidagi) sahifa
~25 ta kartaga alohida forma yozishdan arzon; huquq va tasdiq oqimi bitta joyda.

### 6.2 Obyekt sahifasi
- Sarlavha: obyekt nomi, `srcbar` («Данные этого раздела 1С не передаёт» / «Перекрываются источником»), davr va
  filial filtrlari (qobiq), tugmalar «Добавить», «Загрузить из файла», «Скачать шаблон».
- Reyestr jadvali (mavjud `Table`): qiymatlar, holat `Badge` («Действует», «На согласовании», «Перекрыто
  источником», «Удалено»), ⋯ — «Редактировать», «Удалить», «История изменений».
- Forma — `Drawer` (mobil — to'liq ekran): maydonlar reyestr metadata'sidan (summa — `млн сум`, 2 kasr, ruscha
  format `12 345,67`; oy — `MonthPicker`; reference — `Combobox` qidiruv bilan; sezgir — parol kabi maydon, faqat
  yangi qiymat, «…1234» ko'rsatiladi), klient tomonida tekshiruv + server xatolari maydon yonida
  (`aria-invalid`, `aria-describedby`, birinchi xatoli maydonga fokus — `useFocusFirstInvalid`), «Причина
  изменения» (tuzatish/o'chirishda), «Сохранить черновик» / «Отправить на согласование». 409 — «Запись изменена
  другим пользователем, обновите страницу» + «Обновить».
- Jadval muharriri (`layout = grid`: statya/stansiya/toifa × 12 oy): `role="grid"`, ←↑→↓/Tab/Enter, Esc — bekor,
  Delete — tozalash, **Excel'dan nusxa qo'yish** (Ctrl+V, TSV), o'zgargan katak belgisi, qator va ustun jami, yopiq
  oylar faqat o'qish uchun (`period_locked`), ≤ 500 katak bitta saqlashda. <768 px — birinchi ustun yopishqoq,
  ichki gorizontal skroll (sahifada gorizontal skroll yo'q).
- Import dialogi: shablon → fayl tanlash → yuklash → xatolar jadvali (qator, ustun, ruscha sabab) yoki «Создан
  черновик: N строк» → paket sahifasi.
- «История изменений» — `Drawer`: versiyalar lentasi (sana, kim, holat, sabab), oldin/keyin farqi.
- «На согласовании»: paketlar ro'yxati (obyekt, filial, kim, qachon, qatorlar soni), paket sahifasida diff
  jadvali (yangi / o'zgargan / o'chirilgan — rang + matn belgisi, rangga tayanmasdan), «Утвердить», «Отклонить»
  (izoh majburiy); o'zi yaratgan paketda tugmalar yo'q (izoh bilan).
- Paket holati: «Ожидает публикации / Публикуется / Опубликовано (сборка №N) / Ошибка публикации».

### 6.3 Umumiy talablar
Ruscha matnlar faqat `t()` orqali (`src/i18n/ru.ts`); obyekt/maydon nomlari backend reyestridan (ruscha, 04b
`SettingDef.title` kabi). CSP: inline style/skript yo'q, fayl — `fetch` + `Blob`, yuklab olish — `src/dash/download.ts`.
a11y: kontrast ≥ 4.5:1, ko'rinadigan fokus, jadval muharriri klaviaturada to'liq, `aria-live` saqlash holati,
axe testlari. Responsive: 390 / 1024 / 1440 (Playwright), teginish nishoni ≥ 44 px.

## 7. Boshqa rejalar bilan bog'liqlik

- **Bajarilish tartibi:** S2–S4 1-to'plami (S2 1–5, S3 1–9, S4 1–13) `demo/mvp` ga qo'shilgandan keyin.
  To'lqinlar (§9, reja). Migratsiyalar: 0022 (ombor, grantlar, `dim_bank.account_last4`), 0023 (`*_effective`
  view'lari — 0006 faktlari, `mart|pub.agg_manual_shadow`), 0024 (`object_stage_effective`, S4 0016 dan keyin). Shoxobchada `down_revision` —
  boshlanish paytidagi head; integrator S-rejalar kabi qayta zanjirlaydi.
- **S-rejalarga tuzatishlar** (rejaning «S-rejalarga tuzatishlar» bo'limi — ishlayotgan agentlar brifiga
  qo'shiladi; S-reja matnlari o'zgartirilmaydi):
  - S2 6-vazifa (sifat 2 istisnosi, `cashflow_effective`) — `manual_balance` istisnosi bilan bitta
    `_UNVERIFIABLE` ro'yxatida birlashtiriladi; 8-vazifa (`BankFileConnector`) — `BA-` kod funksiyasini
    `app/etl/codes.py` dan oladi (`bank_account_code`, `counterparty_code`), `dim_bank.account_last4` ni to'ldiradi.
  - S2 13, S3 14, S4 17-vazifalar (hujjatlar) — kanonik fayl hujjatiga «UI: Ввод данных → Загрузить из файла»
    bo'limi.
  - S2 14–15, S3 15–17, S4 18–21 (frontend) — `DataState`ning «Источник не подключён» holatiga `entry`
    (obyekt id) prop'i; havola manual rejaning 22-vazifasida bir joyda qo'shiladi.
  - S5 3-vazifa (финмодель kirishlari) — `fact_balance`, `fact_investment`, `fact_loan_schedule` o'rniga
    `*_effective`; S5 oldin qo'shilsa — manual rejaning 9-vazifasi o'zgartiradi (kod qoidasi testi
    `app/finmodel` ni ham qamraydi va keyingi to'lqinlarda qayta ishlaydi).
  - S3 1C ombori va S4 HR API: maydon darajasidagi birlashtirish yo'q — HR API filial kesimida `штат` bermasa,
    `kadry.headcount` qatori tizim qatori tomonidan to'liq yopiladi (risk §8, savol 7).

## 8. Xatarlar
1. **Agregat manbalarining o'zgarishi (regressiya):** barcha agregat SQL'lari `*_effective` ga o'tadi — qo'lda yozuv
   yo'q bo'lsa view = jadval testi, to'liq pytest to'plami, build vaqti o'lchovi (≤ +10%).
2. **Rollback chuqurligi:** har tasdiq — yangi build; `builds.keep = 3` bir kunda bir necha marta almashadi.
   Yumshatish: so'rovlar birlashadi; admin qo'llanmasida eslatma; kerak bo'lsa `builds.keep` oshiriladi (04b kaliti).
3. **Sifat xatosi:** `manual` yugurishining facts bosqichi commit qilinadi — sifat yiqilsa ham qatorlar `dwh` da
   qoladi va keyingi 1C yuklashida nashr qilinadi (barcha manbalar uchun mavjud arxitektura). Tasdiqlangan ma'lumot
   bo'lgani uchun qabul qilinadi; xabarnoma va paket holati «Ошибка публикации».
4. **BI va 1C ajralib ketishi:** foydalanuvchilar 1C'da tuzatish o'rniga BI'da kiritadi — ustuvorlik qoidasi
   (tizim yutadi), «Перекрыто источником» holati, 1C dasturchilariga bo'shliq xatlari.
5. **Maydon darajasidagi birlashtirish yo'q** (HR штат, АИП reja/fakt bir qatorda) — tizim manbai qisman bersa,
   qo'lda yozuv to'liq yopiladi.
6. **Kredit stavkasi SCD-2:** `dim_loan_version.valid_from` = yuklash sanasi — o'tgan sanadan stavka o'zgarishini
   qo'lda kiritib bo'lmaydi (savol 7).
7. **Admin vazifalarni chetlab o'tishi:** admin `data:*` olmaydi, lekin lavozim/rollarni boshqaradi — o'ziga
   yozish ruxsatini bergan holat auditda (`admin.role.updated`, `admin.user.updated`); to'liq SoD — 04b savoli 1.
8. **XLSX hujum yuzasi:** ZIP/XML bomb, makros — chegaralar va testlar (§4.5); kerak bo'lsa XLSX importini
   o'chirib, faqat CSV qoldirish — bitta sozlama emas, kod (reja 11-vazifa).
9. **Redis yiqilsa rate limit fail-open** (mavjud qoida); yozish yo'llari baribir RLS, tasdiq va audit ostida.

## 9. Testlar
Backend (haqiqiy PostgreSQL/Redis): reyestr izchilligi (har maydon `Target.allowed_keys` da, don ⊂ maydonlar,
sezgir maydonlar `Target.sensitive` bilan mos); ombor triggerlari (append-only, draft DELETE, o'zini tasdiqlash
CHECK, reencrypt UPDATE ruxsati); RLS — filial foydalanuvchisi API (403) va `ugk_app` to'g'ridan-to'g'ri SQL orqali
boshqa filial paketini ko'rmaydi/yozmaydi; `expected_version` 409, `pending_change`, `duplicate_record`,
`period_locked` (yaratish, yuborish, tasdiqlash), sabab majburiyligi; maker–checker (o'zini tasdiqlash 403, doira
tashqarisi 403); audit — diff, `content_hash`, sezgir qiymat audit/log/javobda yo'q; `ManualConnector` runner orqali
— tasdiqlangan qatorlar `dwh` da, o'chirilgan ketadi, idempotent, draft/rad etilgan chiqmaydi; har `*_effective`
view — manual yozuvsiz jadvalga teng, tizim qatori manualni yopadi, manual sintetikni yopadi; agregatlar — qo'lda
qoldiq «Казначейство» kiruvchi/chiquvchi qoldig'ida; sifat 2 istisnosi; import — CSV/XLSX, BOM, razryad
ajratkichi, noto'g'ri sana, ZIP bomb, billion laughs, makros, 5 001 qator, hammasi-yoki-hech narsa; kod qoidasi
testi. Frontend (Vitest, axe): obyekt sahifasi, forma tekshiruvi va 409, jadval klaviaturasi va TSV qo'yish,
import xatolari, tarix, «На согласовании». Playwright (390/1024/1440): kirituvchi qoldiq kiritadi → yuboradi →
tasdiqlovchi tasdiqlaydi → nashr → «Казначейство / Сводка» da qoldiq; o'zini tasdiqlash yo'q; filial
foydalanuvchisi boshqa filialga kirita olmaydi; CSP buzilishi yo'q.

## 10. Qarorlar (planner, controller tasdig'i uchun)
1. Qo'lda yozuv `core.manual_*` → `ManualConnector` → mavjud pipeline; `dwh`/`mart` ga to'g'ridan-to'g'ri yozuv yo'q.
2. Ustuvorlik — don darajasida, tizim manbai yutadi; qo'lda yozuv faqat bo'shliqni to'ldiradi (sintetikdan ustun).
3. Uchta umumiy jadval (paket, bosh, versiya) + Python obyekt reyestri — har obyektga alohida jadval emas.
4. Tuzatish/o'chirish — versiya va tombstone, storno emas.
5. Maker–checker barcha obyektlar uchun, paket darajasida, DB `CHECK` bilan; step-up yo'q.
6. Yangi DB roli yo'q: `ugk_app` manual omborga yozadi (RLS FORCE), `ugk_etl` o'qiydi.
7. Sezgir maydonlar faqat yoziladi, alohida `bank_enc`/`pii_enc` ustunlarida, auditda niqob.
8. Davr yopish — bitta `manual.locked_through` sozlamasi, tasdiqlashni ham bloklaydi.
9. Markaziy «Ввод данных» bo'limi + bo'lim sahifalaridan chuqur havola; inline karta tahriri yo'q.
10. Import — xom tana (multipart yo'q), ≤ 1 MiB, hammasi-yoki-hech narsa, `draft` paket yaratadi; UI importi
    ops inbox'idagi `FileConnector` o'rnini bosmaydi (u tarix/ommaviy yuklash uchun qoladi), lekin bir xil format.
11. Pul oqimi, topshiriqlar, kurslar, АСКУЭ fakti, ombor qiymati — qo'lda kiritilmaydi.

## 11. Ochiq savollar (mijozga)
1. Har obyekt uchun kim kiritadi va kim tasdiqlaydi (filialda — bosh hisobchi yoki HQ «Начальник отдела»)? Profil
   xizmati (`profil_sluzhba`) ishlab chiqarish/АИП/kadrlar ma'lumotini kiritadimi?
2. Maker–checker barcha obyektlarga kerakmi yoki faqat moliyaviylariga (qoldiq, qarz, reja, kredit, maqsadli
   mablag')? Bitta tasdiqlovchi yetarlimi?
3. Davrni kim yopadi va qachon (masalan, keyingi oyning 10-kuni avtomatik)? Yopilgan davrni tuzatish tartibi.
4. 1C/bank shu ma'lumotni bera boshlaganda tizim manbai yutishi to'g'rimi yoki qo'lda tuzatish 1C'dan ustun
   bo'lishi kerakmi (BI'da 1C xatosini to'g'rilash)?
5. Qoldiqlar: har hisob × kun yoki faqat oy oxiri; valyuta hisoblari — valyutada (ЦБ kursi bilan o'giriladi) yoki
   so'm ekvivalentida; qaysi schyotlar (5110/5210/5530)?
6. Bank hisobi raqami va kontragent INN UI'da faqat oxirgi 4 raqam bilan ko'rinishi maqbulmi?
7. Kredit stavkasi o'zgarishining amal qilish sanasi kerakmi; HR штат va АИП rejasi tizimdan qisman kelsa
   maydon darajasida birlashtirish kerakmi?
8. Mavjud Excel shakllaringiz (to'lov rejasi, kreditlar grafigi, АИП) — shablon ustunlarini ularga moslash uchun
   namunalar.
9. Tasdiqlovchiga yangi paket haqida xabar (e-mail/Telegram) kerakmi?
10. Ombor minimal zaxirasi va xarid lotlarini qo'lda yuritish kerakmi (2-bosqich)?
11. Qo'lda kiritilgan yozuvlar tarixi qancha saqlanadi (taklif: витрина kabi 10 yil; audit — 1 yil, `retention.audit_months`)?
