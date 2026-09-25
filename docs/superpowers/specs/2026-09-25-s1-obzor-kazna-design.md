# UGEKAZNA — S1 bo'lim loyihasi: «Обзор» + «Казначейство» + 1C konnektori — dizayn spetsifikatsiyasi

- Sana: 2026-09-25
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: TZ ([docs/reference/UGEKAZNA_TZ.pdf](../../reference/UGEKAZNA_TZ.pdf)) 4-bo'lim («Денежные средства», «Казначейство», «Панель „Требует внимания“»), 5-bo'lim («Обзор», «Казначейство»), 6-bo'lim, 10-bo'lim (1-bosqich); poydevor spec'i [2026-09-24-poydevor-design.md](2026-09-24-poydevor-design.md); 1–4-rejalar (interfeyslar shu rejalar matnidan olinadi).
- Controller qarorlari: `.superpowers/sdd/planning/s1-decisions.md`.

## 1. Maqsad

TZ 1-bosqichining qolgan qismi: «Обзор» va «Казначейство» bo'limlarining barcha 10 sahifasi витринадаги
агрегатлар ustida ishlaydi; «Требует внимания» paneli g'aznachilik qoidalarini har so'rovda filtrlar bilan
hisoblaydi; mavjud 1C HTTP-servislaridan (`hs/aiassistant`) ma'lumot olib keluvchi `OneCConnector` ETL
karkasiga ulanadi. 1C bermaydigan ma'lumot (bank qoldiqlari, qarzdorlik yoshi va h.k.) ochiq "bo'shliq"
sifatida belgilanadi: prod'da tegishli faktlar bo'sh qoladi, UI «нет данных» holatini ko'rsatadi, 1C
dasturchilariga so'rov xati yoziladi.

## 2. Qamrov

**Kiradi:** 6 ta yangi `mart` agregati + `pub` view'lar; 14 ta API endpoint (`/api/v1/obzor/*`,
`/api/v1/kazna/*`, `/api/v1/exports/log`); «Требует внимания» dvigateli (qoidalar reyestri, 5 ta g'aznachilik
qoidasi, chap menyu hisoblagichi); `.xlsx` eksport (4 varaq); `SyntheticConnector` kengaytmasi (to'lov
kalendari va kredit grafigi); `OneCConnector` (httpx, TLS, BOM, o'lcham chegarasi, qat'iy pydantic);
worker jadvali; prod compose sirlari; frontend: Chart.js 4 o'rami, PNG/CSV eksport, 10 sahifa, ГЭС xaritasi;
testlar (pytest, Vitest, Playwright).

**Kirmaydi:** DirectBank (2-bosqich), Производство ma'lumotlari (xarita panelidagi ishlab chiqarish bloki
`production: null` — 3-bosqich rejasi to'ldiradi), boshqa bo'limlarning 15 qoidasi (reyestrga o'z rejalarida
qo'shiladi), 1C'ning `/invoices`, `/purchaseRequests`, `/purchasePlan`, `/incomePlan`, `/budget` (limitlar),
`/sklad/*`, АИИСКУЭ `/ges` endpointlari (tegishli bo'lim rejalarida).

## 3. Ma'lumot manbalari va moslashtirish

### 3.1 1C HTTP-servislari (`{ONEC_BASE_URL}` = `…/con2026/hs/aiassistant`, hammasi `POST` JSON)

| 1C endpoint | So'rov | Витрина | Qoida |
|---|---|---|---|
| `/payments` (`Документ.ЗаявкиНаРасходованиеДС`) | `{"org_uid","date_from":"YYYYMMDD","date_to","limit"}` (kichik harf) — har tashkilot uchun alohida | `fact_cashflow` (`direction=out`, `doc_type=onec_payment`, `src_id="{org_uid}:{number}:{date}"`), `dim_item` (`expense_type_name`), `dim_counterparty` (`contractor_name`) | javobda tashkilot yo'q → tashkilot `org_uid` bo'yicha so'raladi; `len == limit` → xato (sahifalash yo'q, kesilgan ma'lumot yuklanmaydi) |
| `/income` (`Документ.ДоходыФакт`) | `{"DateFrom","DateTo","Limit"}` | `fact_cashflow` (`direction=in`, `doc_type=onec_income`) | 1C hujjatiga ko'ra hozir **test ma'lumot** → `onec.income_enabled=false` (standart) bo'lsa yuklanmaydi; `org_name` → filial `onec.orgs` orqali |
| `/budget` `{"Year","Mode":"plan"}` (`РегистрНакопления.Лимиты`) | yil bo'yicha | `fact_payment_plan` (`doc_type=onec_budget_plan`, `date_id` = oyning 1-kuni) | oynaga tushgan yillar; bir xil (tashkilot, statya, oy) summalanadi |

Umumiy: javob boshidagi UTF-8 BOM olib tashlanadi; kutilgan kalit (`payments`/`items`) ro'yxat bo'lishi
shart (evristik qidiruv yo'q); summalar so'mda keladi → `/ 1 000 000`, `numeric(20,2)` mln so'm
(ROUND_HALF_EVEN); sana `YYYY-MM-DD` (ixtiyoriy `T00:00:00`); `sum ≤ 0` qator o'tkazib yuboriladi va
ogohlantirish logga yoziladi; HTML/JSON bo'lmagan javob, noto'g'ri tuzilma → qayta urinilmaydigan xato;
tarmoq/timeout/5xx → `ConnectorUnavailableError` (runner 3 marta qayta urinadi).
Statya va kontragent kodlari 1C UID'lari yo'qligi sababli normallashtirilgan nomdan barqaror xesh:
`1C-O-<sha256[:12]>`, `1C-I-…`, `1C-CP-…`; faoliyat turi `operating` (bo'shliq G7).
`dim_branch` 1C'dan olinmaydi: filiallar seed qilingan, `core.settings` → `onec.orgs`
(`[{branch_code, org_uid, org_name}]`) moslashtiradi, `python -m app.cli onec-orgs --file …` bilan
yoziladi (audit). Moslashtirilmagan tashkilot → `missing_branch` → sifat tekshiruvi 3 → publish yo'q.

### 3.2 Ulanish va xavfsizlik (controller qarori)
Hisob ma'lumotlari — Docker secrets `onec_username`, `onec_password`, ixtiyoriy `onec_ca_bundle`
(bo'sh fayl = tizim CA); `ONEC_BASE_URL` env'da; DB jadvali emas, veb orqali tahrirlanmaydi. httpx:
`connect 5 s, read 180 s`, TLS tekshiruvi yoqilgan, `trust_env=False` (proksi o'zgaruvchilari
e'tiborga olinmaydi), javob ≤ 64 MiB, faqat `worker` konteyneri `egress` tarmog'ida. `http://` manzil
rad etiladi; faqat `ONEC_ALLOW_HTTP=true` bo'lsa ruxsat (har yugurishda ogohlantirish) — 1C hozir
`http://10.0.90.52` da nashr qilingan (bo'shliq G1). Testlar faqat soxta 1C serveri (`httpx.MockTransport`
+ yozib olingan namunaviy javoblar) bilan; haqiqiy tizimga murojaat yo'q.
Jadval: to'liq yuklash `etl.onec_full_cron = "0 2 * * *"`, inkremental `"0 10,13,16 * * *"` (faqat
`ONEC_BASE_URL` berilgan bo'lsa). Watermark — yuklash boshlangan vaqt (1C'da o'zgarish vaqti yo'q).

### 3.3 Bo'shliqlar (1C bermaydi — prod'da fakt bo'sh, UI «нет данных»)
| № | Kerak | Ta'sir |
|---|---|---|
| G1 | 1C servisini HTTPS'da nashr qilish | Basic parol ochiq tarmoqdan o'tadi |
| G2 | Bank hisoblari qoldiqlari (5110/5210/5530) sana bo'yicha | Начальный/конечный остаток, Разница, покрытие, 2 kritik qoida |
| G3 | 5110/5210/5530 oylik oborotlari (nazorat summalari) | Sifat tekshiruvi 1 o'tkazib yuboriladi |
| G4 | Shartnomalar bo'yicha qarzdorlik (сальдо Дт/Кт, to'lov sanasi, muddati o'tgan kunlar), shartnoma rekvizitlari | Дебиторка/кредиторка/просрочка, реестр договоров, 2 qoida |
| G5 | To'lov topshiriqlari/talabnomalar holati va rejalashtirilgan to'lov sanasi (`status`, `desired_payment_date`, UID) | 6 holat, «заявки в работе», платёжный календарь |
| G6 | Maqsadli mablag'lar (manba × obyekt × oy: ajratilgan/ishlatilgan) | «Целевые средства» |
| G7 | Statya UID, ПКМ №54 kodi, faoliyat turi; kontragent UID va INN; tashkilotlar ro'yxati (UID, INN) | Barqaror kodlar, «по видам деятельности» |
| G8 | `/income` haqiqiy ma'lumoti, hujjat UID/raqami | Поступления |
| G9 | Sahifalash (`offset`/kursor) yoki limitsiz javob; `ВерсияДанных`/o'zgarish sanasi | Katta hajm, inkremental yuklash |
| G10 | Bank (hisob) har bir to'lov/tushumda | «по банкам» kartalari |
Bo'shliqlar uchun xat: `docs/integration/1c-sorov-s1.md` (rejaning 13-vazifasi).

### 3.4 Sintetik manba
2-rejadagi oilalar (`cash`, `payments`, `debt`, `funds`) sahifalar uchun yetarli; qo'shiladi: `calendar`
(`fact_payment_plan`, `doc_type=payment_schedule`, as_of+1…as_of+30 kunlar, soliq/ish haqi/shartnomalar)
va `loans` (`fact_loan_schedule`, 8 kredit, choraklik to'lovlar). `fact_payment_plan` ichida oylik reja
(`payment_plan`/`onec_budget_plan`) va sanali to'lov jadvali (`payment_schedule`) `doc_type` bilan
ajraladi; `agg_payments_month` faqat oylik rejani oladi. Kelajak sanali faktlar uchun `Target.forward`:
to'liq berilgan maqsadda oynadan keyingi eski qatorlar ham almashtiriladi.

## 4. Ko'rsatkichlar (TZ 4 — formulalar aynan shu)

Barcha summalar mln so'm; birlik UI'da avtomatik (млн/млрд/трлн). Davr — `per` (`ytd|q1..q4|m01..m12`,
joriy yil); filial — `br`. Yopilmagan oy haqiqiy kunlar bo'yicha; o'tgan yil bilan solishtirishda o'sha
oy shuncha kun bo'yicha (`*_cmp`, `closing_cmp`).

| Ko'rsatkich | Formula (TZ 4) | Manba (`pub`) |
|---|---|---|
| Начальный остаток | davr 1-kunidagi qoldiq (1-oyning `opening_balance`) | `agg_cash_month` (`item_id=0`) |
| Поступления / Расходование | Σ `fact_cashflow` приход / расход | `agg_cash_month` |
| ЧДП | поступления − расходование | — |
| Конечный остаток | oxirgi kundagi qoldiq (oxirgi oyning `closing_balance`) | `agg_cash_month` |
| Разница | конечный − (начальный + ЧДП) | — |
| Изменение к прошлому году | joriy / o'tgan yilning o'sha davri − 1 | `*_cmp`, `agg_cash_bank_month.closing_cmp` |
| Исполнение плана платежей | факт платежей / план платежей периода | `agg_payments_month` |
| Отклонение по статье | план статьи − факт статьи | `agg_payments_month` |
| Платёжные поручения | 6 holat bo'yicha soni va summasi | `agg_payment_orders_month` |
| Заявки в работе | «на согласовании» + «утверждено» soni va summasi (joriy holat, davrdan qat'i nazar) | `agg_payment_orders_month` |
| Дебиторская / Кредиторская | shartnomalar сальдоси (davr oxiridagi oy) | `agg_debt_month` |
| Просроченная задолженность | to'lov sanasi o'tgan shartnomalar summasi | `agg_debt_month`, `agg_debt_contracts` |
| Платёжный календарь | as_of+1…as_of+14 kunlar bo'yicha 4 tur (налоги, зарплата, кредиты, договоры) | `agg_calendar_day` |
| Покрытие платежей остатком | joriy qoldiq / kalendar summasi | `agg_cash_month`, `agg_calendar_day` |
| Целевое использование | использовано / выделено manba bo'yicha | `agg_target_funds_month` |

Kalendar turlari `core.settings` → `kazna.calendar_kinds` (statya kodlari: `taxes`, `salary`, `loans`;
qolgani `contracts`); `loans` — filialda oyna ichida `fact_loan_schedule` bo'lsa undan (valyuta × oxirgi
`fx_rate`), aks holda reja qatorlaridan (ikki marta sanalmaydi).

## 5. Yangi `mart` agregatlari (2-reja `register(Aggregate)` freymvorki, 0009/0010 migratsiyalar)
`agg_cash_bank_month (branch, month, bank_name; inflow, outflow, closing_balance, closing_cmp)`,
`agg_payment_orders_month (branch, month, status; doc_count, amount)`,
`agg_target_funds_month (branch, month, source_id; source_name, allocated, used)`,
`agg_debt_contracts (branch>0, month, contract_id; number, cp_name, kind, end_date, receivable, payable, overdue, overdue_days)`,
`agg_debt_month (branch, month; receivable, payable, overdue_receivable, overdue_payable, contracts)`,
`agg_calendar_day (branch, date_id, kind; month_id, as_of_id, amount)` — har filial × kun × tur uchun
qator (nol ham), shuning uchun `as_of` doim aniqlanadi. `branch_id = 0` — jami (faqat `scope_all`).
Hammasi `FORCE ROW LEVEL SECURITY` + `core.rls_branch_ok`, `pub.*` — `security_invoker`, faqat aktiv build.
UI faqat `pub.*` ni o'qiydi (TZ 9).

## 6. API (`/api/v1`, hammasi GET, `br`/`per`, `ctx.assert_branch(br)`, kesh + ETag)
| Endpoint | Ruxsat | Mazmun |
|---|---|---|
| `obzor/svod` | `section:obzor:view` | 6 KPI + o'tgan yil, oylar (2 yil), faoliyat turlari, filiallar, top statyalar, stansiyalar (xarita) |
| `obzor/vnimanie`, `obzor/vnimanie/count` | 〃 | sharti bajarilgan qoidalar (kritiklari birinchi) / hisoblagich |
| `obzor/postup`, `obzor/rasxod` | 〃 | KPI, oylik seriyalar, statyalar, banklar, filiallar |
| `obzor/excel` | 〃 | filiallar jadvali + statyalar tafsiloti |
| `obzor/excel.xlsx` | 〃 + `export:xlsx` | 4 varaq (Сводка, Детализация, По месяцам, План-факт), audit, ≤10 s |
| `obzor/items/{item_id}` | 〃 | statyaning filiallar bo'yicha taqsimoti (reja bilan) |
| `kazna/svod`, `kazna/platezhi`, `kazna/platezhi/items/{item_id}`, `kazna/calendar`, `kazna/dogovory`, `kazna/celevye` | `section:kazna:view` | TZ 5 sahifalari |
| `POST exports/log` | `export:csv` | brauzerdagi CSV/PNG eksportini auditga yozish (204) |
Kesh kaliti filtrlariga `today` ham kiradi (davr sanaga bog'liq). Router darajasida `require_perm`.
Branch tanlash: `br` berilsa — shu filial; `scope_all` va `br` yo'q — `branch_id = 0`; aks holda
foydalanuvchining filial qatorlari yig'indisi (RLS).

## 7. «Требует внимания» (TZ 4 jadvali, TZ 10 qabul mezoni 8)
`app/alerts`: reyestr `code → evaluator`; dvigatel `core.alert_rules` dagi joriy, yoqilgan qoidalarni
oladi, faqat evaluatori bor va foydalanuvchi qoida bo'limini ko'ra oladiganlarini hisoblaydi (keyingi
bo'limlar o'z evaluatorini qo'shadi); natija: kritiklar birinchi, so'ng seed tartibi. Chegara, operator
va daraja — DB'dan (kodda emas). S1 qoidalari:
| Kod | Metrika | Standart |
|---|---|---|
| `cash_below_monthly_outflow` | davr oxiridagi qoldiq / o'rtacha oylik расходование (joriy oy kunlar ulushi bilan) | `< 1.0`, критично |
| `payments_14d_exceed_balance` | kalendar 14 kun / joriy qoldiq | `> 1.0`, критично |
| `payment_plan_execution` | факт / план | `< 0.9`, внимание |
| `contracts_overdue_90d` | muddati > N kun o'tgan shartnomalar soni (davr oxiri) | `> 90`, критично |
| `overdue_payables_share` | muddati o'tgan kreditorlik / kreditorlik | `> 0.2`, внимание |
Ma'lumot bo'lmasa qoida o'tkazib yuboriladi (yolg'on signal yo'q). Qatorni bosish → qoidaning
`section/page` sahifasi o'sha `br`/`per` bilan. Hisoblagich — `obzor/vnimanie/count`, chap menyuda
`NavItem.count` (3-reja joyi). Foydalanuvchi ko'ra olmaydigan bo'lim qoidalari ko'rsatilmaydi.

## 8. UI (3-reja qobig'i, sahifa reyestri `src/sections/<bo'lim>/<sahifa>.tsx`)
Prototip (`prototype.js` "pages", "generic blocks", "charts"; `prototype.css`) — etalon:
- **Обзор/Сводка:** 6 KPI (YoY), «Сравнение с прошлым годом» jadvali + grafik, ГЭС xaritasi (geometriya —
  prototip `GEO`, Toshkent viloyati alohida kattalashtirilgan ramkada; koordinatalar `/meta/branches`
  lat/lon), tanlangan stansiya paneli (moliyaviy blok; ishlab chiqarish bloki 3-bosqichda), oylik oqim,
  faoliyat turlari, filiallar bo'yicha расходование (top-8), top-5 statyalar (bosilsa — filiallar dialogi).
- **Требует внимания**, **Поступления**, **Расходование**, **Таблица Excel** (qidiruv, saralash,
  yo'nalish filtri, «Скачать Excel»).
- **Казначейство:** Сводка, Исполнение платежей (statya → filiallar), Платёжный календарь (14 kun ×
  4 tur, qoplash koeffitsienti, banklar, filiallar bo'yicha zayavkalar), Договоры и задолженность
  (filtr «все / дебиторская / кредиторская / просроченные», muddati o'tganlar birinchi, filiallar),
  Целевые средства.
- Grafiklar: Chart.js 4 (bundle, CDN yo'q), yupqa React o'rami, `aria-label` + yashirin jadval, har
  kartada PNG; jadvallar CSV (BOM, `;`, formula-injection himoyasi) — yuklab olishdan oldin
  `exports/log` muvaffaqiyatli bo'lishi shart. Har ko'rsatkichda TZ 4 formulasi bilan tooltip.
- Holatlar (TZ 6): skelet, «Нет данных за период» (nima o'zgartirish kerakligi bilan), «Источник не
  подключён» (bo'shliqlar uchun — kartaning o'zida, sarlavha saqlanadi), ErrorBanner + oxirgi
  muvaffaqiyatli yuklash, freshness (qobiqda).
- Filial qatorini bosish filial filtrini tanlaydi, qayta bosish olib tashlaydi (`SectionPageProps.onBranch`);
  qulflangan foydalanuvchida — o'zgarishsiz.

## 9. Testlar
Backend (pytest, haqiqiy PostgreSQL/Redis): har agregat qo'lda hisoblangan kichik ssenariy bilan; har
yangi endpoint — filial foydalanuvchisi boshqa filialni ko'rmaydi (API 403 + to'g'ridan-to'g'ri SQL),
304, ruxsatsiz 403; har qoida tayyorlangan ma'lumotda ishlaydi va chegara o'zgarsa o'chadi; xlsx
mazmuni, formula-injection, ≤10 s, audit; 1C: soxta server bilan parsing, BOM, xato turlari, limit,
moslashtirish, runner orqali to'liq yuklash va sifat tekshiruvi. Frontend: Vitest (komponentlar va
sahifalar mock API bilan, axe), Playwright: login → Обзор → Требует внимания → Казначейство 5 sahifa →
xlsx yuklab olish; filial foydalanuvchisi boshqa filialni URL orqali ham ko'rmaydi; CSP buzilishi yo'q.

## 10. Ochiq savollar (mijozga)
1. 1C bo'shliqlari G1–G10 (xat: `docs/integration/1c-sorov-s1.md`) — ayniqsa G2 (qoldiqlar) va G4
   (qarzdorlik): ularsiz 1-bosqich natijasi «дашборд на реальных данных» qisman.
2. `/payments` — bu `ЗаявкиНаРасходованиеДС` (talabnomalar); «расходование» sifatida bank orqali
   haqiqatda to'langan summalar kerak — manbani tasdiqlash.
3. Tashkilotlar ro'yxati va UID'lari (`onec.orgs` uchun), ПКМ №54 klassifikatori, kalendar turlari
   uchun statya kodlari (`kazna.calendar_kinds`).
4. «Требует внимания» chegaralarini tasdiqlash (TZ ochiq savoli).
5. Salbiy summali (сторно) to'lovlar semantikasi.
