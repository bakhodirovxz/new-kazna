# UGEKAZNA — S5 bo'lim loyihasi: «Финмодель 2026–2032» + «AI-анализ» + «Экран» rejimi — dizayn spetsifikatsiyasi

- Sana: 2026-09-25
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: TZ ([docs/reference/UGEKAZNA_TZ.pdf](../../reference/UGEKAZNA_TZ.pdf)) 2-bo'lim (AI — faqat server orqali, kalit serverda), 4-bo'lim («Финансовая модель 2026–2032», DSCR), 5-bo'lim («Финмодель»: Сводка, Доходы и расходы, Инвестиции и долг, Сценарии), 6-bo'lim («Режим экрана», holatlar), 7-bo'lim («AI-анализ»), 9-bo'lim (audit, xavfsizlik), 10-bo'lim (5-bosqich; Telegram — S2'da bajarilgan); poydevor spec'i [2026-09-24-poydevor-design.md](2026-09-24-poydevor-design.md); S1–S4 spec'lari; 1–4-rejalar va S1–S4 rejalari (interfeyslar shu rejalar matnidan).
- Controller qarorlari: `.superpowers/sdd/planning/s5-decisions.md`.

## 1. Maqsad

TZ 5-bosqichining qolgan qismi: (1) 4 ssenariyli moliyaviy model 2026–2032 — hisob worker'da build
bosqichida bajariladi, natija `mart`da saqlanadi, UI faqat o'qiydi; «Кредиты» DSCR'i shu modeldan;
(2) «AI-анализ» — joriy sahifa agregatlaridan server yig'adigan xulosa, Claude API orqali oqim bilan
javob, limitlar va jurnal; **standart holatda o'chiq** (axborot xavfsizligi roziligi kerak);
(3) «Экран» (kiosk) rejimi — bo'limlar 60 soniyada almashadi.

## 2. Qamrov

**Kiradi:** `core.fin_assumptions` kalitlarini kengaytirish (quvvat kiritish, boshlang'ich tarif,
o'z ehtiyojlari, investitsiyalarning valyuta ulushi) va har kalit uchun chegaralar; sof hisob moduli
`app/finmodel`; витрина faktlaridan kirish ma'lumotlarini yig'ish; migratsiya 0020
(`mart|pub.agg_finmodel_year`) va agregat bosqichi (`Aggregate.compute`); qayta hisob uchun `rebuild`
manbasi (2-reja navbati orqali); `GET /api/v1/finmodel/model`; «Кредиты» DSCR; migratsiya 0021
(`core.ai_requests`); AI provayder abstraksiyasi + Anthropic SDK amalga oshirilishi + dev/test uchun
soxta provayder; kontekst quruvchi (oq ro'yxat, ≤ 14 000 belgi, sezgir maydon skaneri); limitlar,
jurnal, 90 kunlik saqlash; `GET /ai/status`, `POST /ai/analyze` (SSE), `GET /audit/ai-requests`;
`ai-enable` CLI; sessiya uchun «fon so'rovi» sarlavhasi; `compose.ai.yml` (egress overlay), Caddy
SSE sozlamasi, hujjatlar; frontend: 4 sahifa + ssenariy almashtirgich, admin допущения sahifasi
yangilanishi, AI drawer, AI jurnali sahifasi, kiosk rejimi; testlar (pytest, Vitest, Playwright).

**Kirmaydi:** ikkinchi (on-prem/OpenAI-mos) provayder implementatsiyasi — faqat interfeys va
konfiguratsiya; o'zbekcha AI javobi (til sozlamasi keyin); TZ 7 «второй этап» (har og'ish uchun
«почему так вышло», oylik hisobot qoralamasi); filial kesimidagi moliyaviy model; alohida «displey»
roli.

## 3. Финмодель

### 3.1 Formulalar (TZ 4 — aynan; yil qadami, 2026–2032)
Birliklar: pul — mln so'm; quvvat — MVt; ishlab chiqarish/отпуск — mln kVt·soat; tarif, tannarx —
so'm/kVt·soat.
| Ko'rsatkich | Formula |
|---|---|
| Мощность года | предыдущий год + ввод по АИП (`capacity_add_mw`); база — o'rnatilgan quvvat `as_of` sanasida |
| Выработка | мощность × часы года (kalendar, kabisa — 8784) × КИУМ × коэффициент выработки сценария / 1000 |
| Отпуск в сеть | выработка × (1 − доля собственных нужд) |
| Тариф | 1-yil — `tariff_start`; keyingi yillar — предыдущий × (1 + рост тарифа) |
| Выручка | отпуск × тариф |
| Операционные расходы | 1-yil — база (fakt); keyingi — предыдущий × (1 + индекс роста) |
| Налоги | выручка × ставка налогов и обязательных платежей |
| EBITDA | выручка − операционные расходы − налоги; рентабельность = EBITDA / выручка |
| Инвестиции | план АИП года × (1 + (коэф. курса − 1) × валютная доля инвестиций) |
| Обслуживание долга | график кредитов года: сумовая часть + валютная часть (курс на `as_of`) × коэф. курса |
| Чистый поток | EBITDA − инвестиции − обслуживание долга; остаток = остаток предыдущего + поток (старт — фактический остаток на счетах) |
| DSCR | EBITDA / обслуживание долга (долг 0 → «нет»); ковенант `finmodel.dscr_covenant` = 1,20 |
| Себестоимость 1 кВт·ч | (операционные расходы + налоги) / отпуск |

### 3.2 Допущения (`core.fin_assumptions`, 2-reja versiyali jadvali, admin API)
Yillik kalitlar (ssenariy × yil): `tariff_growth`, `generation_factor`, `fx_rate_factor`, `opex_index`,
`tax_rate`, `kium` (2-reja) + **`capacity_add_mw`** (ввод мощностей по АИП). Skalyar kalitlar (faqat
2026 qatori): **`tariff_start`**, **`own_needs_share`**, **`capex_fx_share`**. Har kalitning chegarasi
kodda (`FIN_KEY_BOUNDS`) — admin API ±10 umumiy chegarasi o'rniga. Ssenariylar (2-reja seed'lari):
Базовый; Маловодье (`generation_factor` 0,85 — 2027–2029); Сдержанный тариф (`tariff_growth` 0,04);
Ослабление сума (`fx_rate_factor` 1,2). Boshlang'ich qiymatlar — prototip (tarif 705, СН 0,016,
valyuta ulushi 0,4, ввод 120/210/95/60/40/30 MVt 2027–2032) — mijoz tasdiqlaydi.

### 3.3 Faktlardan kirish ma'lumotlari (build `as_of` sanasiga, barcha filiallar)
- Quvvat: `dim_branch_version` (`as_of` da amalda), `kind ∈ {ges, cascade}`.
- Операционные расходы базаси: `dwh.cashflow_effective` дан oxirgi 12 **yopilgan** oy rasxodi,
  `dim_item.activity = 'operating'`, `kazna.calendar_kinds` ning `taxes` va `loans` statyalarisiz;
  yillikka keltirilmaydi — tarix 12 oydan qisqa bo'lsa UI ogohlantiradi (`opex_months`).
- Boshlang'ich qoldiq: har hisob bo'yicha `as_of` gacha oxirgi `fact_balance` yig'indisi.
- АИП rejasi: `fact_investment.plan` yillar bo'yicha (forward qatorlar); reja yo'q yil — investitsiya 0,
  UI «план АИП не загружен» deb belgilaydi.
- Kredit grafigi: `fact_loan_schedule` yillar bo'yicha, valyuta — `as_of` gacha oxirgi ЦБ kursi
  (S2 qarori bilan bir xil); kursi yo'q valyuta — hisobga olinmaydi, `missing_fx` ro'yxatida.

### 3.4 Hisoblash va saqlash
Sof modul `app/finmodel/model.py` (Decimal, DB'siz) — worker'da agregat bosqichida (2-reja
`register(Aggregate)` ga `compute` qo'shiladi) 4 ssenariy × 7 yil hisoblanadi va
`mart.agg_finmodel_year (build_id, branch_id = 0, month_id = as_of oyi, scenario, year, …)` ga
yoziladi; kirish bazasi (quvvat, xarajat bazasi va oylari, qoldiq, `missing_fx`, допущения vaqti,
ковенант) har qatorga denormalizatsiya. `FORCE RLS` — `branch_id = 0` faqat `scope_all`
foydalanuvchilarga. KPI, ssenariylar taqqoslashi va sezgirlik so'rovda 28 qatordan (og'ir hisob yo'q).
Допущения o'zgarsa — keyingi build'da yoki admin «Пересчитать» → `POST /admin/etl/run`
`{source: "rebuild"}` (ekstraktsiyasiz: agregatlar + sifat + publish); UI «допущения изменены после
расчёта» belgisini ko'rsatadi.

### 3.5 API va UI
`GET /api/v1/finmodel/model?scen=base|water|tariff|fx` (`section:finmodel:view`, SQ, kesh + ETag):
`has_model`, `company_wide` (filial tanlangan — «модель по компании в целом»), `base`, 7 yil, tanlangan
ssenariy xulosasi, 4 ssenariy taqqoslashi, sezgirlik (jamg'arilgan oqim farqi bazaga nisbatan).
«Кредиты» `kpis.dscr` — bazaviy ssenariy, hisobot sanasi yili, faqat «все филиалы». UI — prototip
`finmodel` bo'limi: ssenariy almashtirgich har sahifada (URL `scen`), 6 KPI, «Выручка и EBITDA» (o'ng
o'q — rentabellik), «Денежный поток» (остаток chizig'i), yillar jadvali, «Структура выручки»,
«Себестоимость и тариф», DSCR + ковенант chizig'i, investitsiya va qarz jadvali, ssenariylar jadvali,
sezgirlik reytingi, «Исходные данные модели» kartasi. Admin «Допущения финмодели» — yangi kalitlar,
chegaralar, 2026 izohi, «Пересчитать модель».

## 4. AI-анализ (TZ 7)

### 4.1 Oqim
Yuqori paneldagi tugma → drawer: «Проанализировать», savol maydoni, 4 tayyor savol (к прошлому году,
главные риски, что делать в первую очередь, отклонения по плану). Klient faqat `section, page, br,
per, scen, preset | question` yuboradi. Server: funksiya yoqilganmi → bo'lim ruxsati va filial
doirasi → savol tekshiruvi (≤ 500 belgi, ИНН/ПИНФЛ/hisob/pasportga o'xshash qatorlar rad) → kontekst
→ limit + jurnal yozuvi → provayderga oqim → SSE (`start`, `delta`, `done`, `error`). Javob: 3 blok
(«Что важно заметить» 3–5 punkt raqamlar bilan, «Риски и отклонения», «Действия на ближайшие две
недели»), ruscha, summalar млрд/трлн, faqat berilgan raqamlar; UI izohi: «Ответ носит рекомендательный
характер и не заменяет решение ответственного лица».

### 4.2 Kontekst (≤ 14 000 belgi, faqat agregatlar)
Sarlavha (bo'lim, sahifa, filial, davr, ma'lumot sanasi, birliklar) + joriy sahifa quruvchisining
(`app.sections.<bo'lim>.build_<sahifa>`, S1–S4; finmodel — `build_model`) chiqishi **oq ro'yxat
bo'yicha** (raqamlar, sanalar va ruxsat etilgan matn kalitlari: nom, sarlavha, holat, usul, valyuta,
kreditor…) + pul oqimi KPI'lari o'tgan yil bilan (`obzor` ruxsati bo'lsa) + yongan qoidalar (daraja,
sarlavha, qiymat — xabar matni emas, unda kontragent nomi bo'lishi mumkin). Tashlanadi: `*_id`
(`month_id` dan tashqari), kod va raqamlar (`lot_no`, shartnoma raqami), kontragent/yetkazib beruvchi
nomi, ФИО/INN/hisob/pasport/telefon/manzilga o'xshash kalitlar. Ro'yxatlar 12 → 6 → 3 elementgacha
qisqartiriladi, oxirida kesish belgisi. Yakuniy matn skanerdan o'tadi — topilsa so'rov rad
(`ai_context_rejected`, fail-closed).

### 4.3 Provayder
`AiProvider` protokoli (`stream(system, prompt) -> AsyncIterator[str]`, `AiProviderError(code)`).
`ClaudeProvider` — rasmiy `anthropic` Python SDK: `AsyncAnthropic(max_retries=0, timeout=60 s)`,
`DefaultAsyncHttpxClient(proxy=EGRESS_PROXY, verify=korporativ CA yoki tizim, trust_env=False)`,
`messages.stream(...)` (`text_stream` + `get_final_message()`), model — `AI_MODEL` (standart
`claude-opus-5`), `thinking: {type: adaptive}`, `output_config.effort` = `AI_EFFORT` (medium),
`max_tokens` = `AI_MAX_TOKENS` (8000), rad etish uchun server tomonidagi zaxira
(`server-side-fallback-2026-07-01`, `fallbacks: "default"`, `AI_FALLBACKS=false` bilan o'chadi);
`stop_reason = refusal` → `ai_refused` (qisman matn UI'da tashlanadi). Kalit — Docker secret
`ai_api_key`, faqat `api`; brauzerga hech qachon chiqmaydi; prompt va javob log'ga yozilmaydi.
`AI_PROVIDER=openai_compatible` — faqat konfiguratsiya o'rni (hozir «не реализовано», funksiya
o'chiq). `AI_PROVIDER=fake` — faqat dev/test (E2E), prod'da ishga tushmaydi.

### 4.4 Limitlar, vaqt, jurnal
Foydalanuvchiga 20/soat, tashkilotga 300/sutka (sozlamalar `ai.user_per_hour`, `ai.org_per_day`) —
PostgreSQL'dagi jurnal bo'yicha (advisory lock), oshsa `429 ai_limit` + `Retry-After` + `scope`
(user|org); UI keyingi urinish vaqtini ko'rsatadi. 60 s taym-aut (server) va «Отменить» (klient
`AbortController`, server oqimni yopadi). `core.ai_requests`: sana, foydalanuvchi, bo'lim, sahifa,
filtrlar, savol/preset, holat (running|ok|error|timeout|cancelled|refused), xato kodi, kontekst va
javob uzunligi, provayder, model, davomiylik; 90 kun (worker har kuni o'chiradi, 10 daqiqadan eski
`running` → `error`). Audit: `ai.request` (savol matnisiz — audit 1 yil saqlanadi), limit rad etishlari
`denied`, tozalash `ai.journal.purged`. Jurnal — `GET /audit/ai-requests` (`audit:read`) va admin
sahifasi.

## 5. Экран rejimi (TZ 6)
«Экран» tugmasi → `html.screen-mode`: menyu, filtrlar, chiplar, asboblar yashirin, shrift katta;
marshrut Обзор → Казначейство → Производство → Инвестиции → Финмодель → Склад (faqat foydalanuvchi
menyusidagilar, «Сводка» sahifasi, joriy filtrlar bilan), 60 s; Esc yoki «Выйти» — chiqish;
`prefers-reduced-motion` — animatsiyasiz. Kiosk so'rovlari `X-UGK-Background: 1` bilan yuboriladi —
server ularda sessiyaning idle muddatini **uzaytirmaydi**: 30 daqiqa inson harakati bo'lmasa sessiya
tugaydi va to'liq ekranli «Сеанс завершён…» oynasi «Войти снова» tugmasi bilan chiqadi.

## 6. Xavfsizlik, muvofiqlik va risklar
- **AI standart holatda o'chiq.** Agregatlangan moliyaviy ma'lumotni tashqi provayderga yuborish milliy
  ekspertiza uchun axborot xavfsizligi xizmatining roziligini talab qiladi. `ai.enabled = false`
  (`core.settings`) va kalit yo'qligi — ikkalasi ham funksiyani o'chiradi; o'chiq holatda tugma
  yashirin, `/ai/analyze` → `404 ai_disabled`. Yoqish — auditlanadigan sozlama o'zgarishi
  (`PUT /admin/settings/ai.enabled` yoki `python -m app.cli ai-enable on --reason …`).
- **Tarmoq:** `api` konteyneri standart prod compose'da internetga chiqmaydi; AI yoqilganda
  `deploy/compose.ai.yml` overlay'i `api` ni `egress` tarmog'iga qo'shadi va `ai_api_key` sirini
  beradi; tavsiya — korporativ proksi (`EGRESS_PROXY`) va DOCKER-USER'da faqat proksiga ruxsat; TLS
  tekshiruvi doim yoqiq (ixtiyoriy korporativ CA `ai_ca_bundle`).
- **Ma'lumot:** faqat oq ro'yxatdagi agregatlar; ФИО, pasport, INN, hisob raqami, kontragent nomi,
  birlamchi hujjat raqamlari yuborilmaydi (skaner testi va ish vaqtidagi tekshiruv); foydalanuvchi
  savolidagi rekvizitlar rad etiladi. Provayderda ma'lumot saqlash shartlari (ZDR) — mijoz bilan
  kelishiladi (ochiq savol 1).
- **Risklar:** provayder javobi noto'g'ri bo'lishi mumkin (izoh, «только по данным»); xarajat — limitlar;
  provayder mavjud emas — `ai_unavailable`, qolgan tizim ishlaydi; kiosk ekrani qarovsiz qolsa — idle
  muddat tugaydi (sessiya o'g'irlanish oynasi 30 daqiqa).
- Hujjatlar: `docs/ops/ai-analiz.md` (yoqish tartibi, rozilik, egress, kalit rotatsiyasi, jurnal),
  `docs/ops/host-hardening.md` (egress), `docs/security/ai-data-flow.md` (ma'lumot oqimi, STRIDE).

## 7. Testlar
Backend (haqiqiy PostgreSQL/Redis, tarmoqsiz): model formulalari qo'lda hisoblangan 4 ssenariy
(kabisa yili, DSCR va ковенант, nolga bo'lish yo'q); kirish yig'uvchisi — delta usulida (ssenariy
qatorlari yuklanmasdan oldin/keyin); build'da saqlash (4 × 7 qator = `run_model`, RLS, muvaffaqiyatsiz
build tozalanadi, допущения keyingi build'da); API (ruxsat, filial doirasi, `has_model`, eskirgan
допущения, ETag), «Кредиты» DSCR; AI — kontekst oq ro'yxati va skaner (barcha bo'lim sahifalari
sintetik ma'lumotda), savol tekshiruvi, limitlar (user/org, `Retry-After`), o'chiq-standart, SSE soxta
provayder bilan, taym-aut va bekor qilish, jurnal va 90 kun, SDK so'rov shakli (soxta SDK mijozi —
haqiqiy API hech qachon chaqirilmaydi); fon so'rovi idle'ni uzaytirmaydi; ops (compose overlay,
sirlar). Frontend (Vitest): ssenariy almashtirgich va URL, 4 sahifa, admin допущения, AI drawer
holatlari (o'chiq, oqim, xato, limit, bekor), kiosk aylanishi soxta taymerlar bilan, reduced-motion,
sessiya tugashi. Playwright: finmodel sahifalari, AI (dev `fake` provayder, sozlama vaqtincha yoqiladi),
kiosk (`page.clock`), CSP.

## 8. Qarorlar (planner, controller tasdig'i uchun)
1. Skalyar допущения (`tariff_start`, `own_needs_share`, `capex_fx_share`) va `capacity_add_mw` —
   `core.fin_assumptions` da; skalyarlar faqat 2026 qatorida; har kalitga alohida chegara.
2. O'sish kalitlari ikkinchi model yilidan qo'llanadi; 1-yil — baza (tarif, fakt xarajat).
3. Xarajat bazasi — oxirgi 12 yopilgan oy operatsion rasxodi (soliq/kredit statyalarisiz), yillikka
   keltirilmaydi.
4. Model worker'da (`Aggregate.compute`), bitta `mart` jadvali (kirishlar denormalizatsiya), KPI —
   o'qishda.
5. Qayta hisob — `rebuild` manbasi (ekstraktsiyasiz yugurish) 2-reja navbati orqali.
6. Model faqat kompaniya darajasida (`branch_id = 0`); «Кредиты» DSCR faqat «все филиалы».
7. AI limitlari — PostgreSQL jurnalida (aniq, Redis'siz, fail-closed).
8. AI konteksti — mavjud sahifa quruvchilari + oq ro'yxat; qoidalardan faqat sarlavha; skaner
   fail-closed.
9. Provayder — Anthropic SDK, `claude-opus-5` (sozlanadi), adaptiv fikrlash, effort medium, SDK qayta
   urinishlarisiz, server tomonidagi rad-etish zaxirasi yoqiq.
10. AI egress — alohida compose overlay; standart prod'da `api` tashqariga chiqmaydi.
11. Kiosk — alohida displey roli yo'q; 30 daqiqalik idle hammaga; kiosk so'rovlari idle'ni
    uzaytirmaydi; aniq qayta kirish ekrani.
12. Jurnalda savol matni 90 kun; audit hodisasida savol yo'q.

## 9. Ochiq savollar (mijozga)
1. Axborot xavfsizligi xizmatining agregatlangan ma'lumotni Anthropic'ga (tashqi, AQSh) yuborishga
   roziligi; ma'lumot saqlash shartlari (ZDR) yoki on-prem model talabi.
2. Haqiqiy допущения: 2026 tarifi va o'sishi, xarajat indeksi, «ставка налогов» tarkibi (tushumdan
   ulush sifatida), КИУМ, o'z ehtiyojlari, yillar bo'yicha ввод мощностей, investitsiyalarning valyuta
   ulushi.
3. АИП 2027–2032 ko'p yillik rejasining manbai (hozir faqat joriy yil yuklanadi).
4. Ковенант 1,20 — qaysi kreditlar/shartnomalar uchun; DSCR kompaniya bo'yichami.
5. Devor ekrani qarovsiz 24/7 ishlashi kerakmi (unda qurilma-bog'liq kiosk hisobi alohida loyihalanadi).
6. `api.anthropic.com` ga chiqish yo'li (korporativ proksi) va IP/domen ruxsati.
7. Limitlar 20/soat va 300/sutka; AI jurnalini (savollar) kim ko'radi.
8. Model boshlang'ich qoldig'iga maqsadli/cheklangan hisoblar kiradimi.
