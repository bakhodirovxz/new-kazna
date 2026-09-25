# UGEKAZNA — S3 bo'lim loyihasi: «Производство» + «Склад» + АСКУЭ (ГЭС) + 1C ombori — dizayn spetsifikatsiyasi

- Sana: 2026-09-25
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: TZ ([docs/reference/UGEKAZNA_TZ.pdf](../../reference/UGEKAZNA_TZ.pdf)) 3-bo'lim (`fact_generation`, `fact_energy_sales`, `fact_stock`, `fact_stock_move`, sifat tekshiruvi 4), 4-bo'lim («Производство», «Склад», «Панель „Требует внимания“»), 5-bo'lim («Производство», «Склад»), 6-bo'lim («Карта ГЭС», «Состояния»), 8-bo'lim (АСКУЭ, 1С), 10-bo'lim (3-bosqich); poydevor spec'i [2026-09-24-poydevor-design.md](2026-09-24-poydevor-design.md); S1 [2026-09-25-s1-obzor-kazna-design.md](2026-09-25-s1-obzor-kazna-design.md); S2 [2026-09-25-s2-kredity-banki-design.md](2026-09-25-s2-kredity-banki-design.md); 1–4-rejalar, S1- va S2-rejalar (interfeyslar shu rejalar matnidan).
- Controller qarorlari: `.superpowers/sdd/planning/s3-decisions.md`.

## 1. Maqsad

TZ 3-bosqichi: «Производство» (3 sahifa) va «Склад» (4 sahifa) витрина агрегатлари ustida; 4 ta qoida
«Требует внимания» paneliga; ГЭС xaritasi ishlab chiqarish ko'rsatkichlari bilan (Обзор va Производство);
АСКУЭ kunlik eksporti uchun konnektor (kanonik CSV + manba interfeysi), treplex.uz jonli quvvat
manbasidan «Текущая мощность» vidjeti, 1C `hs/sklad` servisidan ombor qoldiqlari.

## 2. Qamrov

**Kiradi:** 4 ta yangi `mart` agregati (`agg_generation_month`, `agg_energy_sales_month`,
`agg_stock_month`, `agg_stock_positions`) + `pub` view'lar; `dwh.fact_power_snapshot` + `pub.power_latest`;
`/api/v1/proizvodstvo/{svod,stancii,realiz,moshchnost}`, `/api/v1/sklad/{svod,ostatki,minimum,nelikvid}`;
`StationOut.production` (Обзор xaritasi) to'ldiriladi; 4 qoida; `SyntheticConnector` oilalari
(`production` — ishlab chiqarish va realizatsiya, `stock` — qoldiq va harakat); `AskueConnector` (kanonik CSV, `AskueExport` interfeysi, katalog
eksporti, API stub'i), jonli quvvat poller'i `app.etl.askue.live` (`GesLiveClient`, `poll_power`; treplex.uz), `OneCSkladConnector`; stansiyalar moslashtirishi
`askue.stations` (audit qilinadigan CLI); worker jadvali, prod compose, hujjatlar, 1C'ga so'rov xati
`docs/integration/1c-sorov-s3.md`; frontend: 7 sahifa, xarita `src/dash/map/` ga ko'chiriladi; testlar.

**Kirmaydi:** SCADA (TZ 8, 4-bosqich), АСКУЭ API'ning haqiqiy ulanishi (format noma'lum — stub),
1C'dan реализация/план выработки (endpoint yo'q — xat, prod'da `FileConnector` CSV), minimal zaxira va
oxirgi harakat sanasi 1C'dan (bo'shliq — xat), ombor `.xlsx` eksporti (TZ faqat Обзор uchun).

## 3. Ma'lumot manbalari

### 3.1 Ishlab chiqarish (`fact_generation`, birliklar — mln kVt·soat, 3 kasr)
- **АСКУЭ kunlik eksporti** (TZ 8: «выгрузка по расписанию или API», ежесуточно). Transport noma'lum,
  shuning uchun `AskueExport` protokoli (`files(window) -> Iterator[ExportFile]`): `DirectoryExport` —
  worker'ga **faqat o'qish** uchun ulangan `/data/import/askue/` (`*.csv`, yoshi ≥ 60 s, ≤ 20 MiB, oxirgi
  `askue.inbox_days` = 7 kun ichida o'zgargan fayllar har yugurishda qayta o'qiladi — upsert idempotent,
  jurnal/arxiv yo'q; inbox'ni host cron tozalaydi); `AskueApiExport` — «не настроен» (`ConfigError`).
- **Kanonik CSV** (`docs/integration/askue-format.md`, TZ 8 umumiy qoidalari: UTF-8, `;`, ISO sana,
  nuqta, razryad ajratkichsiz): `station;date;generation_mwh;own_needs_mwh;supply_mwh;work_hours` —
  stansiya × sutka, MVt·soat. Tekshiruvlar: sarlavha/kodlash/hajm → butun fayl rad (`bad_header`,
  `bad_encoding`, `too_large`, `too_many_rows`); qator: `bad_row` (son/sana), `negative`,
  `own_gt_generation`, `bad_hours` (0–24), `future_date`, `duplicate_row`, `unknown_station`. Qator xatolari
  `core.etl_error` (step `extract`, target `askue_file`) + Notifier (`askue_rows_rejected`), yaroqli qatorlar
  yuklanadi. `fact_generation`: `doc_type=askue_daily`, `src_id="<station>:<YYYYMMDD>"`, MVt·soat / 1000.
  Konnektor maqsadlarni «to'liq» deb belgilamaydi (upsert). Sifat tekshiruvi 4 (`capacity_limit`,
  2-reja) har yuklashda ishlaydi — sutkalik ishlab chiqarish > quvvat × 24 → publish yo'q.
- **Stansiyalar moslashtirishi** `askue.stations = [{code, name, branch_code}]` — `code` CSV uchun, `name`
  jonli manba nomi uchun (normallashtirilgan taqqoslash), bir filialga (kaskad) bir nechta stansiya.
  Yoziladi faqat `python -m app.cli askue-stations --file stations.json` (versiya + audit).
- **Reja** — oylik (`doc_type=generation_plan`, oyning 1-kuni, `generation = 0`, `plan`); prod'da
  `FileConnector` (`fact_generation.csv`, shablon `docs/integration/proizvodstvo-fayl.md`) 1C bermaguncha.
- **Реализация** (`fact_energy_sales`, покупатель × месяц, mln so'm, hajm mln kVt·soat) — prod'da
  `FileConnector` (`fact_energy_sales.csv`), 1C endpointi so'raladi (xat G7).

### 3.2 Jonli quvvat (treplex.uz, «Текущая мощность»)
`GET ASKUE_LIVE_URL` (standart bo'sh; eski dashboard: `https://treplex.uz/api/cascades/ges`, auth yo'q) →
`{date, cascades:[{name, "all-power", "all-agg", stations:[{ges, power, agg}]}]}`; `power` — MVt (son yoki
satr), `agg` — `"ishda/zaxira/ta'mir"` agregatlar soni. Bu kunlik energiya EMAS — faqat joriy quvvat.
Poller (`poll_power`, worker, `askue.live_cron` = har 10 daqiqa, Runner/build'siz) bir so'rovning barcha
stansiyalarini bitta `snap_at` (UTC, daqiqagacha) bilan `dwh.fact_power_snapshot (station, snap_at; station_name,
branch_id, cascade_name, power_mw, units_working, units_reserve, units_repair, source_date)` ga yozadi;
moslashtirilmagan stansiya — log (`askue_live_unmapped`), yozilmaydi; `askue.live_keep_days` = 35 kundan
eskisi o'chiriladi. Manba ishlamasa — oxirgi snapshot saqlanadi, UI «устарело» (`askue.live_stale_minutes`
= 30). httpx: TLS, `trust_env=False`, redirect yo'q, ≤ 1 MiB, `EGRESS_PROXY`; faqat `https://`.
`pub.power_latest` — RLS bilan, har foydalanuvchi o'z filiallarining oxirgi snapshot'i.

### 3.3 1C ombori (`POST {ONEC_SKLAD_BASE_URL}/materials`, `…/con2026/hs/sklad`)
So'rov `{"date_from":"yyyy-MM-dd","date_to":"yyyy-MM-dd","org_uid"}` — har tashkilot (`onec.orgs`, S1) ×
har oy; javob `{"data":[{accountCode, accountName, isTotal, openingSum, closingSum, …}]}` (snake_case
variantlari ham qabul qilinadi), `{"success": false, "code", "error"}` → qayta urinilmaydigan xato.
S1 `OneCClient` (TLS, BOM, 64 MiB, `connect 5 s / read 180 s`, `http://` faqat `ONEC_ALLOW_HTTP`) qayta
ishlatiladi; alohida hisob — Docker secrets `onec_sklad_username`, `onec_sklad_password`.
Moslashtirish: `isTotal`/`1000` qatorlari tashlanadi (ikki marta sanalmaydi); har subschyot (yoki
kelajakda nomenklatura) → `dim_nomenclature` (`1C-ACC-<schyot>` yoki `1C-N-<xesh>`, kategoriya =
subschyot nomi), `fact_stock` (`doc_type=onec_stock`, sana = oy oxiri yoki bugun, `value` = closing / 10⁶,
`qty` = `closing_qty` yoki 0). Ixtiyoriy maydonlar kelsa (`nomenclature_name`, `unit`, `warehouse_name`,
`closing_qty`, `min_qty`, `last_move_date`, `debit_sum`, `credit_sum`) — ular ham yuklanadi (xatda aynan
shu nomlar so'raladi); `debit/credit` → `fact_stock_move`. Oyna — oxirgi `onec.sklad_months` = 13 oy
(Runner'da `connector.lookback_months`), maqsadlar to'liq → oyna ichida almashtirish.
**Bo'shliqlar** (xat `docs/integration/1c-sorov-s3.md`): G1 nomenklatura va ombor kesimi; G2 miqdor;
G3 prixod/rasxod oborotlari; G4 oxirgi harakat sanasi; G5 minimal zaxira; G6 javob formati hujjati va
`org_uid` filtri; G7 elektr energiyasi realizatsiyasi (покупатель × месяц); G8 oylik ishlab chiqarish
rejasi; G9 HTTPS va alohida read-only hisob. Bo'shliq bo'lsa tegishli ko'rsatkich `null` → UI «Источник
не подключён», qoida o'tkazib yuboriladi.

### 3.4 Sintetik manba
Prototip «production data» / «warehouse data» bo'yicha: 15 stansiya × kun ishlab chiqarish (quvvat × 24 ×
oylik КИУМ × tebranish ≤ quvvat × 24), oylik reja, 2 xaridor bo'yicha realizatsiya (tarif 655/705 so'm),
har filialda 10 (HQ — 6) nomenklatura oy oxiri qoldiqlari (minimum, oxirgi harakat sanasi) va oylik
prixod/rasxod. Deterministik, `as_of` ga bog'liq emas.

## 4. Ko'rsatkichlar (TZ 4 — formulalar aynan)

Davr `per`, filial `br`; yopilmagan oy — haqiqiy kunlar; o'tgan yil bilan — o'sha kunlar (`*_cmp`).
| Ko'rsatkich | Formula |
|---|---|
| Выработка | Σ выработки за период (брутто) + изменение к прошлому году (o'sha kunlar) |
| Выполнение плана | факт / план; план — oylik, ochiq oyda `план × прошедшие дни / дни месяца` |
| Установленная мощность | Σ мощностей станций выборки (`dim_branch_version`, davr oxiri sanasida) |
| КИУМ | выработка × 1000 / Σ(мощность × часы) — har oy o'sha oy snapshot sanasidagi quvvat bilan |
| Собственные нужды | собственные нужды / выработка |
| Отпуск в сеть | выработка − собственные нужды |
| Уровень оплаты | оплачено / начислено |
| Стоимость запасов | Σ стоимость позиций на дату (davr oxiri; oy ichidagi oxirgi snapshot) |
| Оборачиваемость | стоимость запасов / (расход за период / число дней) — kunlarda |
| Ниже минимума | позиции, где количество < минимума; обеспеченность = количество / минимум |
| Неликвиды | стоимость позиций без движения > 180 дней, доля = неликвиды / стоимость |
| Возраст запасов | стоимость по срокам: ≤ 90, 91–180, 181–365, > 365 дней, «нет данных» |
Stansiya = `dim_branch.kind ∈ {ges, cascade}`. Tanlovda stansiya yo'q (HQ) → `has_stations = false`,
UI: «Головная организация не эксплуатирует станции. Выберите «Все филиалы» или конкретную ГЭС.»

## 5. Yangi agregatlar (0013–0015, 2-reja `register(Aggregate)`)
- `agg_generation_month (branch_id ≥ 0, month_id; days_in_period, days_in_month, stations,
  capacity_mw, capacity_hours, generation, generation_cmp, own_needs, plan, plan_full)` — har stansiya ×
  oy (ishlab chiqarishsiz ham) + stansiya bo'lmagan, lekin fakti bor filiallar; `branch_id = 0` — jami.
- `agg_energy_sales_month (branch_id ≥ 0, month_id; accrued, paid, volume)`.
- `agg_stock_month (branch_id ≥ 0, month_id, category; snap_date_id, positions, value, below_min,
  min_known, idle_value, age_le90, age_91_180, age_181_365, age_gt365, age_unknown, inflow, outflow)`.
- `agg_stock_positions (branch_id > 0, month_id, nom_id, warehouse; …, below_min, idle)` — faqat
  belgilangan (minimumdan past yoki > 180 kun) pozitsiyalar.
Hammasi `FORCE ROW LEVEL SECURITY` + `core.rls_branch_ok`, `pub.*` — `security_invoker`, aktiv build.
0015: `dwh.fact_power_snapshot` (RLS) va `pub.power_latest`.

## 6. API (GET, `br`/`per`, `ctx.assert_branch`, kesh + ETag, route-guard `EXPECTED_ROUTES`)
| Endpoint | Ruxsat | Mazmun (prototip) |
|---|---|---|
| `proizvodstvo/svod` | `section:proizvodstvo:view` | 6 KPI, oylar (fakt/reja/o'tgan yil), top-8 stansiya, xarita stansiyalari |
| `proizvodstvo/stancii` | 〃 | KPI, stansiyalar jadvali (quvvat, reja, fakt, bajarilish, КИУМ, отпуск) |
| `proizvodstvo/realiz` | 〃 | KPI, oylar (начислено/оплачено), stansiyalar to'lov darajasi bo'yicha |
| `proizvodstvo/moshchnost` | 〃 | jonli quvvat: snapshot vaqti, eskirganlik, jami MVt, agregatlar holati, stansiyalar; kesh kalitiga oxirgi `snap_at` kiradi |
| `sklad/svod`, `sklad/ostatki`, `sklad/minimum`, `sklad/nelikvid` | `section:sklad:view` | TZ 5 sahifalari |
`obzor/svod` — `StationOut.production = {generation, plan, execution, kium, payment_level} | null`.

## 7. «Требует внимания» (S1 dvigateli; seed'lar 2-rejada)
| Kod | Metrika | Standart |
|---|---|---|
| `generation_plan` | reja > 0 bo'lgan stansiyalar ichida bajarilishi chegaradan past bo'lganlar soni (`per=station`) | `< 0.95`, внимание, `proizvodstvo/stancii` |
| `energy_payment_level` | tanlov bo'yicha оплачено / начислено | `< 0.85`, внимание, `proizvodstvo/realiz` |
| `stock_below_minimum` | davr oxirida minimumdan past pozitsiyalar soni | `> 5`, критично, `sklad/minimum` |
| `illiquid_stock_share` | неликвиды / стоимость запасов | `> 0.2`, внимание, `sklad/nelikvid` |
Ma'lumot bo'lmasa (reja/realizatsiya/minimum/yosh ma'lumoti yo'q) qoida o'tkazib yuboriladi.

## 8. UI (3-reja qobig'i, S1 `src/dash`)
Prototip `proizv`, `sklad` bo'limlari etalon. Производство/Сводка: KPI, «Выработка по месяцам» (fakt —
ustun, reja — chiziq), «Выработка по станциям» (Rank, reja belgisi), ГЭС xaritasi + stansiya paneli (qizil —
bajarilish < 95%), «Текущая мощность» kartasi (jami MVt, «по данным на …», agregatlar holati, stansiyalar;
eskirgan — ogohlantirish; manba yo'q — «Источник не подключён»). Выработка по станциям: jadval + «Итого».
Реализация: oylik grafik, to'lov darajasi Rank (< 88% qizil). Склад: KPI (6), «Движение запасов по
месяцам», kategoriyalar, «Ниже минимального запаса» (obespechennost chizig'i), filiallar jadvali, yosh
bo'yicha Rank, неликвидлар ro'yxati. Xarita `src/dash/map/` ga ko'chiriladi (`tip` prop), Обзор xaritasi
ham TZ 6 tooltip'ini oladi (nom, quvvat, ishlab chiqarish, reja %). Energiya birligi «млн/млрд кВт·ч».
Har KPI'da TZ 4 formulasi, PNG/CSV (audit), TZ 6 holatlari; qator bosish — filial tanlash.
«Текущая мощность» kartasi prototipda yo'q: Refero'dagi monitoring vidjetlari (OneSoil «последнее
обновление» sarlavhasi, Enode holat kartalari) asosida prototip primitivlaridan (`gp-grid`, `Rank`, `Badge`).

## 9. Worker va ekspluatatsiya
| Job | Sozlama (standart) | Shart |
|---|---|---|
| `etl_askue` | `etl.askue_cron` = `15 7 * * *` (inkremental) | `/data/import/askue` mavjud |
| `askue_live` | `askue.live_cron` = `*/10 * * * *` | `ASKUE_LIVE_URL` berilgan |
| `etl_onec_sklad_full` / `_incremental` | `etl.onec_sklad_full_cron` = `30 3 * * *`, `etl.onec_sklad_incremental_cron` = `30 10,13,16 * * *` | `ONEC_SKLAD_BASE_URL` berilgan |
CLI: `askue-stations [--file]`, `askue-live-check`, `onec-sklad-check`. Tashqi so'rov faqat worker
(`egress`): treplex.uz:443 (S2 proksi qoidasi), 1C — ichki tarmoq. Hujjatlar: `askue-format.md`,
`askue-connector.md`, `proizvodstvo-fayl.md`, `1c-sorov-s3.md`, `host-hardening.md`.

## 10. Testlar
Backend (haqiqiy PostgreSQL/Redis): agregatlar — qo'lda hisoblangan ssenariylar (quvvat SCD o'zgarishi,
ochiq oy, o'tgan yil, HQ); har endpoint — RLS (403 + to'g'ridan-to'g'ri SQL), 304, ruxsatsiz 403; qoidalar
yonishi/o'chishi/o'tkazib yuborilishi; АСКУЭ CSV (BOM, sarlavha, buzilgan qatorlar, noma'lum stansiya),
runner orqali yuklash va sifat tekshiruvi 4; jonli manba — `httpx.MockTransport` fixture'lari, eskirganlik,
manba yiqilganda oxirgi snapshot saqlanishi; 1C ombor — soxta server (joriy va kengaytirilgan shakl,
`success:false`, BOM, HTML). Tarmoqqa chiqish yo'q. Frontend: Vitest (sahifalar, axe), Playwright:
Производство va Склад sahifalari, filial foydalanuvchisi boshqa filialni ko'rmaydi, CSP.

## 11. Qarorlar (planner)
1. Reja oylik (1-kun), ochiq oyda o'tgan kunlar ulushi bilan — kunlik reja bo'lsa bitta ifoda o'zgaradi.
2. Отпуск = выработка − СН (TZ formulasi); yuklangan `supply` ustuni ko'rsatkichda ishlatilmaydi.
3. КИУМ — har oy o'sha oy sanasidagi quvvat bilan (SCD-2); «Установленная мощность» — davr oxirida.
4. Jonli quvvat Runner/build'dan tashqarida (har 10 daqiqada agregatlar qayta qurilmaydi); rollback unga ta'sir qilmaydi.
5. АСКУЭ inbox faqat o'qish, oxirgi 7 kun qayta o'qiladi (idempotent), jurnal/arxiv yo'q.
6. 1C ombor — oxirgi 13 oy oylik snapshot'lari, subschyot darajasida (kengaytirilgan maydonlar kelguncha).
7. To'lov darajasi qoidasi tanlov jamida (TZ'da «по станции» yo'q); ishlab chiqarish qoidasi — stansiya bo'yicha.
8. Xarita `src/dash/map/` da; Обзор ko'ruvchilari stansiya ishlab chiqarishini ham ko'radi (TZ 6 tooltip).
9. Reja va realizatsiya prod'da `FileConnector` CSV orqali (1C endpointi kelguncha).

## 12. Ochiq savollar (mijozga)
1. АСКУЭ kunlik eksporti: fayl yoki API, format, stansiya kodlari, yetkazish (SFTP → inbox?), vaqti; birlik (MVt·soat?).
2. treplex.uz: egasi, har 10 daqiqada so'rovga ruxsat, stansiya nomlari barqarorligi, axborot xavfsizligi roziligi (egress).
3. Ishlab chiqarish rejasi va elektr energiyasi realizatsiyasi manbai (1C, billing yoki jadval).
4. 1C `/materials` kengaytmasi (xat G1–G9), minimal zaxira qayerda yuritiladi, omborlar ro'yxati.
5. Qoida chegaralarini tasdiqlash (95%, 85%, > 5 pozitsiya, 20%) va to'lov darajasi qoidasi stansiya bo'yicha bo'lishi kerakmi.
6. Kaskadlarda quvvat: filial quvvati (1C) va stansiyalar yig'indisi mosligi.
