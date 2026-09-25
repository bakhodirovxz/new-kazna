# UGEKAZNA — S4 bo'lim loyihasi: «Закупки» + «Инвестиции» (Адреса/АИП) + «Кадры» — dizayn spetsifikatsiyasi

- Sana: 2026-09-25
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: TZ ([docs/reference/UGEKAZNA_TZ.pdf](../../reference/UGEKAZNA_TZ.pdf)) 1-bo'lim (rollar), 3-bo'lim (`fact_procurement`, `fact_investment`, `fact_hr`, `dim_object`, `dim_source`, `dim_position`), 4-bo'lim («Закупки», «Инвестиции (Адреса)», «Кадры», «Панель „Требует внимания“»), 5-bo'lim, 8-bo'lim (портал закупок, mehnat.uz), 9-bo'lim («Кадры» — faqat agregatlar, ФИО yo'q), 10-bo'lim (4-bosqich); poydevor spec'i [2026-09-24-poydevor-design.md](2026-09-24-poydevor-design.md); S1 [2026-09-25-s1-obzor-kazna-design.md](2026-09-25-s1-obzor-kazna-design.md), S2 [2026-09-25-s2-kredity-banki-design.md](2026-09-25-s2-kredity-banki-design.md), S3 [2026-09-25-s3-proizvodstvo-sklad-design.md](2026-09-25-s3-proizvodstvo-sklad-design.md); 1–4-rejalar va S1–S3 rejalari (interfeyslar shu rejalar matnidan).
- Controller qarorlari: `.superpowers/sdd/planning/s4-decisions.md`.

## 1. Maqsad

TZ 4-bosqichi: «Закупки», «Инвестиции», «Кадры» (har biri 4 sahifa) витрина агрегатлари ustida; 9 ta qoida
«Требует внимания» paneliga; manbalar: xarid portali (kanonik CSV + portal adapteri interfeysi), 1C
`/purchasePlan` (yillik xarid rejasi), АИП (kanonik CSV — adreska'dan yoki qo'lda), HR API
(`hr-api.uzgidro.uz`, server tomonida token) va mehnat.uz interfeysi (3-bosqich — stub).
Shaxsiy ma'lumot yo'q: «Кадры» faqat agregatlar, ФИО hech qayerda saqlanmaydi va ko'rsatilmaydi.

## 2. Qamrov

**Kiradi:** migratsiyalar 0016–0019: `dwh.fact_object_stage` (obyekt bosqichlari) va `fact_procurement` holat/usul
cheklovlari; `mart`/`pub`: `agg_procurement_lots`, `agg_procurement_plan`, `agg_investment_month`,
`agg_object_stages`, `agg_hr_month`; `/api/v1/zakupki/{svod,loty,postavshiki,ekonomiya}`,
`/api/v1/investicii/{svod,obekty,istochniki,riski}`, `/api/v1/kadry/{svod,chislennost,fot,dvizhenie}`;
9 qoida; `SyntheticConnector` oilalari (`procurement`, `investment`, `hr`); `ProcurementConnector` + `ProcurementPortal`
interfeysi (xarid.uzex.uz stub'i), `OneCPurchasePlanConnector`, `HrConnector` + `HrApiSource`/`MehnatSource`;
sozlamalar va audit qilinadigan CLI (`hr-orgs`, `hr-check`); worker jadvali, prod compose, hujjatlar va so'rov xatlari
(`docs/integration/hr-sorov-s4.md`, `1c-sorov-s4.md`); frontend: 12 sahifa; testlar.

**Kirmaydi:** xarid portalining haqiqiy API ulanishi (format noma'lum — stub), mehnat.uz ulanishi (TZ 8: 3-bosqich —
faqat interfeys), adreska bilan jonli integratsiya (11-bo'lim, 1-qaror), E-IMZO, `.xlsx` eksporti (TZ faqat Обзор),
`/purchaseRequests` (TZ ko'rsatkichiga mos kelmaydi va javobida `responsible_name` — ФИО bor).

## 3. Ma'lumot manbalari

### 3.1 Закупки (`fact_procurement`, mln so'm)
- **Semantika** (hujjat `docs/integration/zakupki-format.md`): bir qator — bitta lot. `status ∈ {объявлен, на оценке,
  договор заключён, отменён, план}`; `method ∈ {eshop, contest, tender, exchange, direct, other, plan}` (электронный
  магазин, электронный конкурс, тендер, биржевые торги, прямой договор, прочие). `date` — lot holatining sanasi:
  «в работе» va «отменён» — e'lon sanasi, «договор заключён» — shartnoma sanasi. `procedure_days` — faqat
  tuzilgan shartnoma uchun (e'londan shartnomagacha kun). «В работе» lotlarning kunlari build sanasiga nisbatan
  hisoblanadi. Yillik reja — `doc_type = procurement_plan`, `status = план`, `method = plan`, sana — yilning 1-yanvari,
  summa `start_price` da. Migratsiya 0016 holat va usulni `CHECK` bilan cheklaydi.
- **Kanonik CSV** — 2-reja `FileConnector` maqsadi `fact_procurement.csv` (+ `dim_counterparty.csv`,
  `dim_nomenclature.csv` — predmet = nomenklatura kategoriyasi); TZ 8 qoidalari (UTF-8, `;`, ISO sana, nuqta).
  Yakka tartibdagi tadbirkor/jismoniy shaxs yetkazib beruvchi nomi yozilmaydi — umumiy kod `CP-FL`
  «Физическое лицо» (S2 qarori bilan bir xil).
- **Portal adapteri**: `ProcurementPortal` protokoli (`lots(window) -> Iterator[PortalLot]`), `XaridPortal` —
  «не настроен» (`ConfigError`); `ProcurementConnector` `PortalLot` → kanonik qatorlar (buyurtmachi INN →
  `dim_branch.inn`, usul/holat nomlari → kodlar, 14 xonali INN → `CP-FL`, summa so'm → mln). Haqiqiy portal
  formati kelganda faqat adapter yoziladi.
- **1C `/purchasePlan`** (`hs/aiassistant`, S1 hisobi): `{"Year": Y}` → `items[] {org_name, nomenclature_name,
  quantity_incoming, sum_incoming}` → yillik reja qatorlari (tashkilot → filial `onec.orgs` nomi bo'yicha,
  moslashtirilmagan → S1 xulqi: `1C:<nom>` → publish to'xtaydi). Kechasi to'liq (`etl.onec_zakupki_cron`).
  Bo'shliqlar (xat `1c-sorov-s4.md`): lotlar/shartnomalar va xarid usuli (XARID_TURI_API_SOROV davomi),
  predmet kategoriyasi.
- **Normativlar**: `zakupki.method_norms` = `{eshop: 15, contest: 40, tender: 70, exchange: 20, direct: 12,
  other: 40}` kun — `core.settings` (admin API orqali o'zgartiriladi, versiya + audit); agregat build vaqtida
  o'qiydi (keyingi build'dan amal qiladi).

### 3.2 Инвестиции / АИП (`fact_investment`, `fact_object_stage`, mln so'm)
- `fact_investment` — obyekt × oy (sana — oyning 1-kuni, `forward` maqsad: yil oxirigacha reja): `plan` (oy
  grafigi), `fact` (moliyalashtirish), `physical_pct` (КС-2 bo'yicha bajarilgan hajm / smeta, oy oxiriga,
  0..1, to'planib boruvchi), `advance` (oy oxiridagi yopilmagan avans qoldig'i), `advance_date_id` (eng eski
  yopilmagan avans berilgan sana); `doc_type = aip_opening` — tarix boshlanishidan oldingi to'plangan
  moliyalashtirish (bitta qator, «освоено ранее» ga kiradi, oylik faktga kirmaydi).
- `fact_object_stage` (0016) — obyekt × bosqich: `stage_no`, `stage_name`, sana = rejadagi tugash sanasi,
  `fact_date_id` — haqiqiy tugash.
- **Manba — kanonik CSV** (`FileConnector`: `dim_source.csv`, `dim_object.csv`, `fact_investment.csv`,
  `fact_object_stage.csv`; hujjat `docs/integration/aip-format.md`, unda adreska maydonlari → ustunlar jadvali).

### 3.3 Кадры (`fact_hr`, odamlar soni; ФОТ — mln so'm)
- `fact_hr` — filial × toifa (`dim_position.category`) × oy: `headcount_plan` (штат), `headcount_fact`,
  `hired`, `fired`, `overtime_hours`; bir oyda bir nechta sana bo'lsa — oydagi oxirgi sana.
- **ФОТ** = `pub.agg_cash_month` dagi `kazna.calendar_kinds.salary` statyalari bo'yicha rasxod (TZ formulasi
  «выплаты по статье „Заработная плата и приравненные платежи“»; S1 sozlamasi qayta ishlatiladi);
  `fact_hr.payroll` ko'rsatkichlarda ishlatilmaydi.
- **HR API** (`HR_BASE_URL`, eski dashboard: `https://hr-api.uzgidro.uz`): `POST /auth/login`
  (form-urlencoded) → `access_token`, `expires_in` — token faqat xotirada, muddatidan 60 s oldin/401 da
  yangilanadi; sirlar `hr_username`, `hr_password` (Docker secrets, faqat worker), ixtiyoriy korporativ CA
  `hr_ca_bundle`; TLS har doim tekshiriladi, `trust_env=False`, redirect yo'q, ≤ 8 MiB, `EGRESS_PROXY`.
  `GET /dashboard/main` (`total_employees_count` — nazorat jami), `GET <hr.breakdown_path>` (standart
  `/dashboard/employees-by-category`): qatorlar faqat oq ro'yxatdagi kalitlardan o'qiladi (toifa, soni,
  tashkilot, `staff_units`, `hired`, `fired`, `overtime_hours`); boshqa har qanday kalit (jumladan `full_name`,
  `fio`, `pinfl`) e'tiborsiz — saqlanmaydi, log'ga yozilmaydi. Tashkilot → filial `hr.orgs` (audit qilinadigan
  CLI `hr-orgs`). Tashkilot kesimi bo'lmasa — `no_branch_breakdown` (ogohlantirish), `fact_hr` yozilmaydi;
  moslashtirilmagan tashkilot — `unmapped_org` (+ xabar `hr_rows_rejected`); jami > 1% farq — `total_mismatch`.
  Joriy oy snapshot'i: `src_id = <filial>:<toifa>:<YYYYMM>`, sana — bugun, upsert.
- Bo'shliqlar (xat `hr-sorov-s4.md`): tashkilot kesimi, штат, qabul/bo'shatish, ish vaqtidan tashqari soatlar,
  ixtiyoriy hisoblangan ФОТ. Kelguncha prod'da `fact_hr.csv` (`FileConnector`, hujjat `kadry-fayl.md`).
- **mehnat.uz** — `MehnatSource` stub (`ConfigError`: «mehnat.uz — этап 3»); `HrSource` protokoli bir xil.

### 3.4 Sintetik manba
Prototip «procurement data», «investments (Адреса)», «HR data» bo'yicha: har filialda oyiga 1–3 lot (HQ 2–4),
usul og'irliklari va tejash/davomiylik diapazonlari prototipdan, yillik reja = yil lotlari boshlang'ich narxi ×
1,4; 14 АИП obyekti (oylik reja/fakt 2025–2026, ochilish qoldig'i, КС-2 foizi, avanslar, 7 bosqich); har filial
× 4 toifa × oy xodimlar (штат prototip formulasi), qabul/bo'shatish/ish vaqtidan tashqari soatlar. Predmetlar —
`dim_nomenclature` `PS-01…07`. Deterministik.

## 4. Ko'rsatkichlar (TZ 4 — formulalar aynan)

Davr `per`, filial `br`; yopilmagan oy — haqiqiy kunlar.
| Ko'rsatkich | Formula |
|---|---|
| Заключено договоров | Σ цена договора по лотам «договор заключён» с датой в периоде |
| Экономия | начальная цена − цена договора; доля = экономия / начальная цена |
| Исполнение годового плана | заключено с 1 января года периода по конец периода / годовой план |
| Лоты в работе | лоты «объявлен», «на оценке» (текущее состояние, объявлены не позже конца периода) |
| Просроченные лоты | лоты в работе, где дни процедуры > норматив способа + 10 |
| Доля прямых договоров | сумма прямых договоров / сумма всех договоров периода |
| Средний срок закупки | среднее число дней от объявления до заключения (договоры периода) |
| Программа года | Σ годового плана объектов (план месяцев года) |
| Освоено с начала года / за период | Σ факта финансирования с 1 января / за месяцы периода |
| Исполнение графика | факт с начала года / план на отчётную дату (открытый месяц — доля прошедших дней) |
| Финансовое выполнение | (освоено ранее + освоено в году) / общая стоимость объекта |
| Физическое выполнение | КС-2 / смета — последнее значение не позже конца периода |
| Разрыв | финансовое − физическое, п.п. |
| Незакрытые авансы | остаток аванса и дни = конец периода − дата выдачи |
| Статус объекта | ≥ 90% по графику, 75–90% отстаёт, < 75% под угрозой |
| Штат / факт | на последний месяц периода с данными |
| Вакансии | штат − факт; доля = вакансии / штат (штат 0 → «нет данных») |
| ФОТ | выплаты по статьям зарплаты; доля = ФОТ / всё расходование |
| Средняя зарплата | ФОТ / численность / число месяцев (открытый месяц — доля дней) |
| Текучесть | уволено за период / численность (без пересчёта на год — TZ) |
| Сверхурочные | часы сверх нормы / численность |
Filialda obyekt yo'q → `has_objects = false`, UI: «У выбранного филиала нет объектов адресной программы.»

## 5. Yangi agregatlar (2-reja `register(Aggregate)`)
- 0017 `agg_procurement_lots (branch_id > 0, month_id, lot_src; date_id, lot_no, method, status, start_price,
  contract_price, days, norm_days, overdue, subject, supplier)` — reja qatorlarisiz barcha lotlar;
  `agg_procurement_plan (branch_id ≥ 0, month_id = YYYY01, plan)`.
- 0018 `agg_investment_month (branch_id > 0, month_id, object_id; obyekt atributlari, plan, fact, opening,
  physical_pct, advance, advance_date_id)` — `date_from` dan joriy yil dekabrigacha; КС-2 va avans oy
  oxirigacha oldinga to'ldiriladi (faqat `as_of` oyigacha); `agg_object_stages (branch_id > 0, month_id =
  as_of oyi, object_id, stage_no; …, done, late)`.
- 0019 `agg_hr_month (branch_id ≥ 0, month_id, category; headcount_plan, headcount_fact, hired, fired,
  overtime_hours)`.
Hammasi `FORCE ROW LEVEL SECURITY` + `core.rls_branch_ok`, `pub.*` — `security_invoker`, aktiv build; obyekt
nomlari mart'ga denormalizatsiya qilinadi (filial foydalanuvchisi boshqa filial obyektini ko'rmaydi).

## 6. API (GET, `br`/`per`, `ctx.assert_branch`, kesh + ETag, route-guard `EXPECTED_ROUTES`)
| Endpoint | Ruxsat | Mazmun (prototip) |
|---|---|---|
| `zakupki/svod` | `section:zakupki:view` | 6 KPI, oylar bo'yicha shartnomalar, usullar, 8 lot |
| `zakupki/loty` | 〃 | KPI, lotlar reyestri (≤ 1000, kechikkanlar birinchi; filtr «все/в работе/просроченные/заключённые» — klientda) |
| `zakupki/postavshiki` | 〃 | KPI, yetkazib beruvchilar, predmetlar, filiallar (reja, yil boshidan, bajarilish, tejash) |
| `zakupki/ekonomiya` | 〃 | KPI, usullar bo'yicha tejash va o'rtacha muddat, bekor qilingan lotlar |
| `investicii/svod`, `obekty`, `istochniki`, `riski` | `section:investicii:view` | TZ 5 sahifalari; `has_objects` |
| `kadry/svod`, `chislennost`, `fot`, `dvizhenie` | `section:kadry:view` | TZ 5 sahifalari |

## 7. «Требует внимания» (S1 dvigateli; seed'lar 2-rejada)
| Kod | Metrika | Standart |
|---|---|---|
| `procurement_overdue_lots` | kechikkan lotlar soni | `> 3`, критично, `zakupki/loty` |
| `direct_contracts_share` | прямые / все договоры | `> 0.25`, внимание, `zakupki/postavshiki` |
| `procurement_plan` | yil boshidan / yillik reja | `< 0.6`, внимание, `zakupki/svod` |
| `investment_schedule` | исполнение графика | `< 0.9`, внимание, `investicii/svod` |
| `fin_phys_gap` | uzilishi chegaradan katta obyektlar soni (p.p.) | `> 20`, внимание, `investicii/riski` |
| `advances_90d` | yoshi chegaradan katta avanslar soni | `> 90` kun, внимание, `investicii/riski` |
| `vacancies_share` | вакансии / штат | `> 0.1`, внимание, `kadry/chislennost` |
| `turnover` | уволено / численность | `> 0.08`, внимание, `kadry/dvizhenie` |
| `overtime` | часы / численность | `> 20`, внимание, `kadry/dvizhenie` |
Maxraj 0 yoki ma'lumot yo'q — qoida o'tkazib yuboriladi.

## 8. UI (3-reja qobig'i, S1 `src/dash`)
Prototip `zakup`, `invest`, `hr` bo'limlari etalon: KPI'lar (TZ 4 formulasi izohda), «Заключённые договоры по
месяцам», usullar Rank'i, lotlar jadvali segment filtri bilan (kechikkan — `badge late`), yetkazib
beruvchilar/predmetlar Rank'lari, filiallar jadvali; «Освоение нарастающим итогом» (reja — uzuk-uzuk chiziq),
manbalar progress'i, obyektlar reyestri (moliyaviy bajarilish polosa, jismoniy — belgi), orqada qolganlar,
uzilishlar, bosqichlar lentasi, avanslar; ФОТ ustun + o'rtacha ish haqi o'ng o'qda, xodimlar tuzilmasi, filiallar
jadvali, qabul/bo'shatish, ish vaqtidan tashqari soatlar, qo'nimsizlik. Yangi vizual naqsh yo'q (prototip
primitivlari), CSV/PNG eksport (audit), TZ 6 holatlari; qator bosish — filial tanlash.

## 9. Worker va ekspluatatsiya
| Job | Sozlama (standart) | Shart |
|---|---|---|
| `etl_hr` | `etl.hr_cron` = `30 6 * * *` | `HR_BASE_URL` berilgan |
| `etl_onec_zakupki` | `etl.onec_zakupki_cron` = `40 2 * * *` (to'liq) | `ONEC_BASE_URL` berilgan |
CLI: `hr-orgs [--file]`, `hr-check`. `xarid` va `mehnat` manbalari — «не настроен». Tashqi so'rov faqat worker
(`hr-api.uzgidro.uz:443` — egress qoidasi; DNS yo'q bo'lsa compose override'da `extra_hosts`). Hujjatlar:
`zakupki-format.md`, `aip-format.md`, `kadry-fayl.md`, `hr-connector.md`, `hr-sorov-s4.md`, `1c-sorov-s4.md`.

## 10. Testlar
Backend (haqiqiy PostgreSQL/Redis): agregatlar va so'rovlar — qo'lda hisoblangan ssenariylar (ochiq oy, chorak,
kechikish, oldinga to'ldirish, avans kunlari, HQ/bo'sh filial); har endpoint — RLS (403 `scope_violation`,
to'g'ridan-to'g'ri SQL), 304, ruxsatsiz 403; qoidalar yonishi/o'tkazib yuborilishi; konnektorlar —
`httpx.MockTransport` va yozib olingan fixture'lar (token keshlanishi va 401 dan keyin yangilanish, shaxsiy
maydonlar tashlanishi va log'ga tushmasligi, moslashtirilmagan tashkilot, portal xaritalash, 1C reja); **shaxsiy
ma'lumot testi**: HR jadvallari/view'larida ФИО-ga o'xshash ustun yo'q va `kadry/*` javoblarida bunday kalit yo'q.
Tarmoqqa chiqish yo'q. Frontend: Vitest (sahifalar, axe), Playwright: 12 sahifa, filial doirasi, CSP.

## 11. Qarorlar (planner)
1. **АИП manbai — kanonik CSV (`FileConnector`), adreska importi emas.** adreska — alohida ilova: API faqat
   foydalanuvchi sessiyasi (cookie/CSRF, 2FA) bilan, eksport endpointi yo'q, har loyiha × 6 blok so'rovi, javobda
   ФИО (`responsible_person`, `chief_engineer`, `signed_by`); bazasiga to'g'ridan-to'g'ri ulanish — boshqa ilova
   sxemasi va sirlariga bog'lanish. adreska → CSV ustunlari moslik jadvali hujjatda; kerak bo'lsa keyin
   `AdreskaExport` adapteri shu kanonik qatorlarni beradi (витрина o'zgarmaydi).
2. Lotlar reyestri va xarid KPI'lari bitta `agg_procurement_lots` snapshot'idan; «в работе»/«просрочено» — joriy
   holat (S1 «заявки в работе» qaroriga o'xshash), kunlar build sanasiga.
3. Normativlar `core.settings` da, agregat build vaqtida o'qiydi (keyingi build'dan amal qiladi); 10 kun zaxira —
   TZ formulasi, kodda.
4. ФОТ — faqat pul oqimidan (TZ formulasi), statyalar — S1 `kazna.calendar_kinds.salary`.
5. Qo'nimsizlik — TZ formulasi (yilga qayta hisoblanmaydi; prototip yilga hisoblaydi — TZ ustun).
6. HR API tashkilot kesimisiz — `fact_hr` yozilmaydi (ogohlantirish), prod'da `fact_hr.csv`; HR API'ning
   kelishilmagan kalitlari oq ro'yxat bilan tashlanadi.
7. `/purchaseRequests` yuklanmaydi (ko'rsatkichga mos emas, ФИО bor); 1C reja — alohida manba `onec_zakupki`.
8. Obyekt bosqichlari uchun yangi fakt `fact_object_stage` (TZ risk sahifasi talab qiladi, 3-bo'limda yo'q).

## 12. Ochiq savollar (mijozga)
1. Xarid portali (xarid.uzex.uz / davlat xaridlari portali): API yoki reyestr eksporti, format, lot holatlari,
   buyurtmachi identifikatori (INN?), yetkazish yo'li va jadvali.
2. Usullar bo'yicha normativ kunlar (standart 15/40/70/20/12) va xarid usullari ro'yxati.
3. АИП manbai: adreska (qaysi bo'lim eksport qiladi?), 1C yoki ПТО jadvali; avanslarni yopish (hisobga olish) qayerda yuritiladi; bosqichlar ro'yxati.
4. HR API: tashkilot kesimi, штат, qabul/bo'shatish, ish vaqtidan tashqari soatlar (xat); egress va IP (DNS) ruxsati; hisob faqat o'qish uchunmi.
5. Qo'nimsizlik chegarasi 8% — davr uchunmi yoki yillik hisobdami; boshqa chegaralarni tasdiqlash (3 lot, 25%, 60%, 90%, 20 п.п., 90 kun, 10%, 20 soat).
6. ФОТ statyalari (1C statya nomlari) — `kazna.calendar_kinds.salary` ro'yxati.
