# UGEKAZNA — S2 bo'lim loyihasi: «Кредиты» + banklar (fayl / DirectBank) + ЦБ kurslari + Telegram — dizayn spetsifikatsiyasi

- Sana: 2026-09-25
- Holat: loyiha (foydalanuvchi ko'rib chiqishi kutilmoqda)
- Asos: TZ ([docs/reference/UGEKAZNA_TZ.pdf](../../reference/UGEKAZNA_TZ.pdf)) 3-bo'lim (`dim_loan`, `fact_loan_schedule`, `fact_balance`, `fact_cashflow`, `fact_payment_order`), 4-bo'lim («Кредиты», «Панель „Требует внимания“»), 5-bo'lim («Кредиты»), 6-bo'lim, 7-bo'lim («Второй этап: дневная сводка в Телеграм-бот»), 8-bo'lim («Банки», «Общие правила обмена», «Телеграм-бот», ЦБ kurslari), 10-bo'lim (2-bosqich); poydevor spec'i [2026-09-24-poydevor-design.md](2026-09-24-poydevor-design.md); S1 spec'i [2026-09-25-s1-obzor-kazna-design.md](2026-09-25-s1-obzor-kazna-design.md); 1–4-rejalar va S1-reja (interfeyslar shu rejalar matnidan).
- Controller qarorlari: `.superpowers/sdd/planning/s2-decisions.md`.

## 1. Maqsad

TZ 2-bosqichining qolgan qismi: «Кредиты» bo'limining 3 sahifasi витрина агрегатлари ustida; kredit
qoidalari «Требует внимания» paneliga; bank ko'chirmalari (mijoz-bank fayllari) orqali avtomatik qoldiq,
bank проводкалари va to'lov topshiriqlari holatlari (S1 bo'shlig'i G2/G10 ning bankdan yopilishi);
ЦБ РУз kurslari har kuni tarix bilan; Telegram orqali kundalik qisqa hisobot va ETL ogohlantirishlari.

## 2. Qamrov

**Kiradi:** 2 ta yangi `mart` agregati (`agg_loan_month`, `agg_loan_schedule`) + `pub` view'lar;
`/api/v1/kredity/{svod,reestr,grafik}`; 2 ta kredit qoidasi (`loan_payments_30d`, `fx_loans_share`);
`BankFileConnector` (kanonik CSV + adapter interfeysi, fayl jurnali, arxiv), DirectBank (1C) interfeysi
va «не настроен» stub'i; bank ko'chirmasi ↔ 1C oqimlari ustuvorligi qoidasi; `CbuRatesConnector`;
`TelegramNotifier` + 08:30 kundalik hisobot; worker jadvali, operator CLI, prod compose (hajmlar,
sirlar, egress), hujjatlar; frontend: 3 sahifa; testlar (pytest, Vitest, Playwright).

**Kirmaydi:** DSCR hisobi (Финмодель — S5; hozircha «нет данных»), kredit ma'lumotining 1C'dan
yuklanishi (1C'da endpoint yo'q — §3.1), aniq bank eksport formatlari adapterlari (formatlar noma'lum —
§3.2, ochiq savol 1), DirectBank'ning haqiqiy ulanishi (ochiq savol 2), Telegram bot orqali
kiruvchi buyruqlar (faqat chiquvchi xabarlar — TZ 8).

## 3. Ma'lumot manbalari

### 3.1 Kreditlar
`dim_loan` (SCD-2 stavka — `dim_loan_version`) va `fact_loan_schedule` (to'lov sanasi bo'yicha asosiy
qarz, foiz, to'lovdan keyingi qoldiq — **kredit valyutasida, mln birlik**) 2-reja maqsadlari. Manbalar:
dev/test — S1 `SyntheticConnector` `loans` oilasi (qayta yozilmaydi); prod — 1C bermaguncha
`FileConnector` (`dim_loan.csv`, `fact_loan_schedule.csv`, shablon: `docs/integration/kredity-fayl.md`).
`fact_loan_schedule` — `forward` maqsad (S1): kelajak qatorlari ham to'liq beriladi. **Tuzatish:**
`FileConnector` `forward` maqsad qatorlarini oyna bo'yicha kesmaydi (aks holda kelajak grafigi
yuklanmaydi va keyingi to'liq almashtirishda o'chadi).

### 3.2 Banklar (TZ 8 «Банки»: 5 bank, 4 marta kuniga)
Bank kodlari (katalog nomi = kod): `sqb` — Узпромстройбанк, `nbu` — Национальный банк, `asaka` —
Асакабанк, `ipoteka` — Ипотека-банк, `xalq` — Халк банк.

**Fayl qabul qilish.** Worker'ga `/data/import/banks/<bank_code>/` **faqat o'qish** uchun ulanadi
(bank/ops tomoni yozadi: avval `.tmp`, keyin `.csv` ga rename); faqat `*.csv`, yoshi ≥ 60 s,
hajmi ≤ 50 MiB. Har fayl SHA-256 bo'yicha `core.bank_files` jurnaliga yoziladi va baytma-bayt
`/data/archive/banks/<bank>/<YYYY-MM>/<sha256>.csv` ga **ko'chirib** qo'yiladi (arxiv hajmi — worker
uchun yozish mumkin). Inbox o'qish-uchun bo'lgani sababli fayl o'chirilmaydi — host'dagi cron arxivda
bor fayllarni 7 kundan keyin o'chiradi (runbook). Fayl qayta o'qilmaydi, agar jurnalda `rejected`
bo'lsa yoki `staged` bo'lib, o'sha ETL yugurishi `success` bilan tugagan bo'lsa (muvaffaqiyatsiz
yugurishdagi fayllar keyingi safar qayta o'qiladi).

**Kanonik CSV** (TZ 8 «Общие правила обмена»: UTF-8, `;`, ISO 8601 sanalar, summalar nuqta bilan,
razryad ajratkichsiz; to'liq ta'rif — `docs/integration/banks-format.md`). Fayl turi sarlavha to'plami
bo'yicha aniqlanadi:
- *Выписка* — `row_type;account;date;doc_id;direction;amount;counterparty_inn;counterparty_name;item_code`.
  `OB`/`CB` qatorlari — hisob × kun uchun kiruvchi/chiquvchi qoldiq (`amount`, manfiy mumkin);
  `L` — проводка (`doc_id` majburiy, `direction ∈ in|out`, `amount > 0`).
- *Статусы платёжных поручений* — `doc_id;account;date;status;status_date;amount;counterparty_inn;counterparty_name;item_code`;
  `status ∈ accepted|executed|rejected` → «отправлено в банк» / «исполнено» / «отклонено».
Summalar hisob valyutasida (so'm yoki valyuta, tiyin/sent bilan).

**Adapter interfeysi:** `StatementAdapter.parse(data: bytes, name: str) -> ParsedFile` (qoldiqlar,
проводкалар, topshiriqlar, qator xatolari). `banks.formats` sozlamasi bank → adapter nomini beradi
(hozir faqat `canonical`); yangi bank formati = yangi adapter + ro'yxatga bitta qator.

**DirectBank (1C).** `DirectBankClient` protokoli (`statements(account_codes, day)`,
`order_statuses(...)` → o'sha `ParsedFile`), bank qatorlarini staging'ga yozuvchi `BankMapper` fayl va
DirectBank uchun umumiy. `make_connector("directbank")` hozir `ConfigError("DirectBank (1С) не
настроен …")` — mijoz javobini kutadi (ochiq savol 2).

**Moslashtirish.** Hisob raqami → (bank, filial, valyuta, 1C schyoti 5110/5210/5530) — `banks.accounts`
sozlamasi; unda **ochiq hisob raqami yo'q**: kod `BA-<HMAC(blind_index_key, hisob)[:16]>` va oxirgi
4 raqam. Yoziladi faqat `python -m app.cli bank-accounts --file accounts.csv` (versiya + audit).
`dim_bank.account_enc` — staging'da AES-256-GCM, `account_bidx` — blind index (2-reja); hisob raqami
loglarga, `etl_error`ga, fayl jurnaliga va arxiv nomiga tushmaydi (faqat `…1234`).

**Витринага yozish (idempotentlik kaliti — manba, hujjat turi, tashqi id; TZ 8):**
| Kanonik qator | Fakt | `doc_type` | `src_id` |
|---|---|---|---|
| `CB` | `fact_balance` (kun oxiri qoldig'i) | `bank_balance` | `<BA-kod>:<YYYYMMDD>` |
| `L` | `fact_cashflow` (`gl_account` — moslashtirishdan) | `bank_statement` | `<BA-kod>:<doc_id>` |
| status qatori | `fact_payment_order` | `bank_payment_order` | `<BA-kod>:<doc_id>` |
Valyuta hisobi summalari so'mga **o'sha kungi ЦБ kursi** bilan o'giriladi (`dwh.fx_rate`, ≤ 10 kun
eski); kurs yo'q → shu hisob-kuni rad etiladi. Kontragent faqat 9 xonali INN bo'lsa (yuridik shaxs)
yoziladi — kod `CP-<HMAC(inn)[:16]>`, INN shifrlanadi; jismoniy shaxs (ПИНФЛ yoki INN yo'q) —
kontragentsiz (shaxsiy ma'lumot saqlanmaydi); to'lov maqsadi matni yuklanmaydi.

**Tekshiruvlar.** Hisob × kun: `OB` va `CB` bo'lsa `CB = OB + Σin − Σout` (±0,01 hisob valyutasida),
aks holda hisob-kun rad etiladi (`statement_mismatch`). Qator xatolari (`bad_row`, `unknown_account`,
`duplicate_doc`, `fx_rate_missing`, `statement_mismatch`) → `core.etl_error` (step `extract`),
yaroqli qatorlar yuklanadi, keyin Notifier (`bank_rows_rejected`). Sarlavha/kodlash/hajm xatosi →
butun fayl `rejected` (jurnalda yakuniy; tuzatilgan faylni yangi nom bilan qo'yish kerak).
Konnektor maqsadlarni «to'liq berilgan» deb belgilamaydi (`by_target = {}`): fayllar inkremental,
oldingi ko'chirmalar o'chirilmaydi.

### 3.3 ЦБ РУз kurslari (TZ 8: har kuni, tarix bilan)
`GET https://cbu.uz/ru/arkhiv-kursov-valyut/json/all/<YYYY-MM-DD>/` — JSON massiv (tekshirildi
2026-09-25, 75 valyuta): `{"id", "Code", "Ccy", "CcyNm_RU", …, "Nominal": "1", "Rate": "11830.87",
"Diff", "Date": "25.09.2026"}`. `Date` — kurs o'rnatilgan kun (dam olish kunida oldingi ish kuni).
Saqlanadi: so'ralgan har kalendar kun uchun `dwh.fx_rate (currency, date_id, rate = Rate / Nominal)`
— «shu kuni amalda bo'lgan kurs». Valyutalar — `fx.currencies`; kuniga oxirgi `fx.lookback_days`
(7) kun (o'tkazib yuborilganlar to'ldiriladi); tarix — `python -m app.cli cbu-backfill --from … --to …`.
httpx: TLS, `trust_env=False`, redirect yo'q, javob ≤ 1 MiB, `EGRESS_PROXY` (ixtiyoriy);
tarmoq/5xx/429 → qayta urinish (runner), format xatosi → qayta urinilmaydi. Testlar — yozib olingan
fixture'lar bilan, tarmoqsiz.

### 3.4 Bank ko'chirmasi va 1C oqimlari ustuvorligi
1C `/payments` (S1) va bank проводкалари bir xil `fact_cashflow` ga tushadi — ikki marta sanash xavfi;
1C to'lovlarida bank hisobi yo'q (G10), shuning uchun hisob darajasida dublikatni ajratib bo'lmaydi.
Qoida: `banks.statement_branches` (filial kodlari) — shu filiallar oqimi **faqat** bank ko'chirmasidan
(`doc_type = bank_statement`), qolganlari — 1C'dan (`doc_type` `onec_` bilan boshlanadi); boshqa
manbalar (sintetik, fayl) doim hisobga olinadi. `dwh.cashflow_effective` view'i shu qoidani qo'llaydi,
`agg_cash_month`, `agg_payments_month`, `agg_cash_bank_month` shu view'dan o'qiydi. Bank qoldiqlari
(`fact_balance`) hamma filial uchun ishlatiladi (G2 yopiladi). Sifat tekshiruvi 2 («Разница» ≤ 1%
oborot) bank qoldig'i bor, lekin ko'chirma rejimida bo'lmagan filialda o'tkazib yuboriladi — u yerda
«Разница» manbalararo solishtirish (1C talabnomalari ↔ bank qoldig'i), yuklash nuqsoni emas.
Valyuta hisoblarida kurs qayta baholanishi «Разница»ga tushadi (ochiq savol 7).

## 4. Ko'rsatkichlar — «Кредиты» (TZ 4, formulalar aynan)

Hisobot sanasi `D` = davr oxiri (`per`, joriy yil; ochiq davrda — bugun). Kredit valyutasidagi
summalar **`D` sanasidagi ЦБ kursi** bilan so'mga o'giriladi (so'nggi kurs ≤ `D`; UZS = 1) — bitta
snapshot ichidagi barcha ko'rsatkichlar bitta kurs bilan.
| Ko'rsatkich | Formula (TZ 4) |
|---|---|
| Кредитный портфель | остаток основного долга в сумовом эквиваленте по курсу на дату: kredit bo'yicha `D` gacha oxirgi grafik qatorining `balance`i (qator yo'q bo'lsa — birinchi qatorning `balance + principal`) × kurs |
| Средневзвешенная ставка | Σ(остаток × ставка) / Σ остатков; stavka — `dim_loan_version` dan `D` sanasida amalda bo'lgani |
| Доля валютных кредитов | остаток в валюте (valyuta ≠ UZS) / весь портфель |
| Обслуживание долга года | основной долг + проценты по графику `D` yili |
| Оплачено | платежи с датой не позже отчётной (`D` yili ichida) |
| Ближайший платёж | `D` dan keyingi birinchi grafik qatori (sana, summa, kreditor) |
| Год пиковой нагрузки | `D` yili … +9 yil ichida основной долг + проценты eng katta yil |
| График погашения | shu 10 yil bo'yicha основной долг va проценты alohida |
| Валютная структура | portfel valyutalar bo'yicha |
| Реестр | kreditor, loyiha, filial, valyuta, stavka, qoldiq, доля погашения = 1 − qoldiq (valyutada) / boshlang'ich summa (birinchi qatorning `balance + principal`), imtiyozli davr, so'ndirish muddati |
| DSCR | EBITDA года / обслуживание долга года — Финмодель (S5) bo'lmaguncha `null` → «нет данных» |
`D` sanasigacha kursi yo'q valyutadagi kreditlar portfel va ulushlarga kirmaydi, `missing_fx`
ro'yxatida qaytadi (UI ogohlantiradi) — nol deb hisoblanmaydi. Grafik qatori yo'q kredit ko'rsatilmaydi.

## 5. Yangi `mart` agregatlari (0011 migratsiya, 2-reja `register(Aggregate)`)
- `agg_loan_month (build_id, branch_id > 0, month_id, loan_id; snap_date_id, loan_code, creditor,
  project, currency, rate, grace_until, maturity, fx_rate, original_cur, outstanding_cur, outstanding)` —
  build oynasidagi har oy × kredit snapshot'i (`snap_date_id` = oyning `as_of` bilan kesilgan oxiri);
  qator faqat qoldiq > 0 yoki o'sha yilda to'lov bo'lsa.
- `agg_loan_schedule (build_id, branch_id > 0, loan_id, date_id; month_id, principal_cur,
  interest_cur, balance_cur)` — `fact_loan_schedule` kredit × sana bo'yicha, `date_from` dan keyingi
  (kelajak ham).
Ikkalasi — `FORCE ROW LEVEL SECURITY` + `core.rls_branch_ok`, `pub.*` — `security_invoker`, aktiv
build. Portfel/ulush/yillar jami so'rovda (Python) shu kichik agregat qatorlaridan yig'iladi.

0012 migratsiya: `core.bank_files` (fayl jurnali), `dwh.statement_branches`, `dwh.cashflow_effective`,
`pub.fx_rate_latest` (har valyutaning oxirgi kursi — kundalik hisobot uchun).

## 6. API (`/api/v1/kredity/*`, GET, `br`/`per`, `ctx.assert_branch(br)`, kesh + ETag, `section:kredity:view`)
| Endpoint | Mazmun (prototip `kredit` sahifalari) |
|---|---|
| `svod` | 6 KPI (portfel, stavka, valyuta ulushi, yil xizmati + to'langan, eng yaqin to'lov, pik yil), grafik 10 yil, valyuta tuzilmasi, 5 ta eng yaqin to'lov, `dscr` |
| `reestr` | KPI, kreditlar reyestri, kreditorlar bo'yicha qoldiq, valyuta tuzilmasi |
| `grafik` | grafik 10 yil, 12 ta eng yaqin to'lov |
`has_loans = false` — «У выбранного филиала нет кредитов.» (TZ 6 «Нет объектов у филиала»).

## 7. «Требует внимания» (TZ 4 jadvali; S1 dvigateli, reyestrga `app/alerts/loans.py`)
| Kod | Metrika | Standart |
|---|---|---|
| `loan_payments_30d` | `D` dan keyingi to'lovlar, `(sana − D)` kun chegaradan kichik-teng (`<= 30`) | внимание, sahifa `kredity/grafik` |
| `fx_loans_share` | валютная доля портфеля (`> 0.85`) | внимание, sahifa `kredity/svod` |
Chegara/operator/daraja — `core.alert_rules` dan; kreditlar yoki kurslar bo'lmasa qoida o'tkazib
yuboriladi. Qoidalar `section:kredity:view` ruxsati borlarga ko'rinadi.

## 8. UI (3-reja qobig'i; S1 `src/dash` bloklari)
Prototip `kredit` bo'limi etalon: Сводка — KPI qatori, «График погашения» (asosiy qarz/foizlar,
yillar bo'yicha stacked bar), «Валютная структура» (Rank), «Ближайшие платежи» (5, «Весь график»),
DSCR kartasi («нет данных — источник: финансовая модель»); Реестр — KPI, reyestr jadvali (доля
погашения chizig'i, imtiyoz belgisi, «Итого»), kreditorlar va valyutalar; График платежей — grafik va
12 ta to'lov. Reyestr qatorini bosish filialni tanlaydi (TZ 6). Har KPI'da TZ 4 formulasi (tooltip),
PNG/CSV eksport (audit bilan), holatlar TZ 6. Prototipda yo'q UI yo'q (Refero kerak emas).

## 9. Telegram (TZ 7 «Второй этап», TZ 8 «Телеграм-бот»: Bot API, faqat chiquvchi, 08:30)
- `TelegramClient` (`sendMessage`, oddiy matn, 4096 belgigacha, 429 → `retry_after` ≤ 30 s bilan bitta
  qayta urinish), `TelegramNotifier` — 2-reja `Notifier` (ETL xatolari, sifat, nazorat summasi,
  eskirish, bank qatorlari rad etilishi). Token URL yo'lida bo'lgani uchun `httpx` logger'i WARNING
  ga tushiriladi va xato matnlarida faqat xato turi — token hech qayerga yozilmaydi.
- Kundalik hisobot (Toshkent 08:30, `telegram.summary_cron`): ma'lumot sanasi/eskirganlik, qoldiq,
  oy boshidan tushum/xarajat, 14 kunlik to'lovlar va qoplash, kredit portfeli va eng yaqin to'lov,
  USD/EUR kursi, «Требует внимания» soni va **faqat kritik qoidalar sarlavhalari** (xabar matnlari
  emas — ularda kontragent nomi bo'lishi mumkin). Summalar млрд/трлн сум, ruscha. Shaxsiy ma'lumot,
  hisob raqami, kontragent nomi yo'q. Har yuborish auditga yoziladi (`notify.telegram.summary`).
- `telegram_bot_token`, `telegram_chat_ids` — Docker secrets (faqat worker). Tarmoq: faqat worker
  `egress` tarmog'ida; tavsiya — korporativ proksi (`EGRESS_PROXY`), DOCKER-USER'da faqat proksiga
  ruxsat; to'g'ridan-to'g'ri variant — `api.telegram.org`, `cbu.uz` IP'lariga 443.

## 10. Worker jadvali va ekspluatatsiya
| Job | Sozlama (standart) | Shart |
|---|---|---|
| `etl_cbu` | `etl.cbu_cron` = `0 8 * * *` | `CBU_ENABLED=true` |
| `etl_banks` | `etl.banks_cron` = `30 9,12,15,18 * * *` (TZ: 4 marta) | inbox katalogi mavjud |
| `telegram_summary` | `telegram.summary_cron` = `30 8 * * *` | token va chat'lar berilgan |
Runner global lock'i band bo'lsa job o'tkazib yuboriladi (keyingi jadvalda; CBU oxirgi 7 kunni oladi).
CLI: `bank-accounts [--file]`, `bank-files [--limit N]`, `cbu-backfill --from --to`, `telegram-test`.
Hujjatlar: `docs/integration/banks-format.md` (banklar uchun, ruscha), `banks-connector.md`,
`cbu-telegram.md`, `kredity-fayl.md`; `docs/ops/host-hardening.md` — egress qoidalari.

## 11. Testlar
Backend (haqiqiy PostgreSQL/Redis): kredit agregatlari va hisob-kitob — qo'lda hisoblangan ssenariy
(2 kredit, valyuta `XTL` + UZS, kurs o'zgarishi, SCD-2 stavka, kursi yo'q oy); har endpoint — RLS
(API 403 + to'g'ridan-to'g'ri SQL), 304, ruxsatsiz 403, filialsiz kredit; qoidalar yonishi va chegara
o'zgarsa o'chishi; ustuvorlik view'i va sifat tekshiruvi; kanonik CSV (buzilgan qatorlar, BOM,
kodlash, sarlavha, razryad ajratkichi, dublikat, balans nomuvofiqligi); bank konnektori runner orqali
(idempotentlik, qayta yetkazish, fayl jurnali, arxiv, ikkinchi fayl birinchisini o'chirmaydi, hisob
raqami loglarda yo'q); CBU — yozib olingan JSON, `Nominal`, format xatolari, 5xx qayta urinish;
Telegram — `httpx.MockTransport`, 429, token logda yo'q; kundalik hisobot matni (shaxsiy ma'lumotsiz).
Frontend: Vitest (3 sahifa, axe), Playwright: login → Кредиты 3 sahifa; filial foydalanuvchisi API
orqali boshqa filial kreditini ko'rmaydi; CSP.

## 12. Qarorlar (planner, controller tasdig'i uchun)
1. Snapshot ichidagi barcha kredit summalari `D` sanasi kursida (to'langanlar ham) — izchil va
   takrorlanadigan; narxi: to'langanlarni to'lov kuni kursiga o'tkazish — bitta so'rov.
2. Ko'chirma ↔ 1C ustuvorligi filial ro'yxati bilan (§3.4) — narxi: view + sozlama.
3. Inbox faqat o'qish; fayl arxivga nusxalanadi + SHA-256 jurnal, inbox'ni host tozalaydi — narxi:
   rw ulash va `os.replace`.
4. Qator xatolari yuklashni to'xtatmaydi (etl_error + xabar), fayl darajasidagi xato — fayl rad etiladi.
5. Jismoniy shaxs kontragent va to'lov maqsadi saqlanmaydi.
6. Valyuta hisoblari konnektorda kun kursi bilan o'giriladi; kurs yo'q — hisob-kun rad etiladi.
7. CBU: so'ralgan kalendar kun uchun amaldagi kurs saqlanadi; kunlik 7 kun + CLI backfill.
8. Telegram hisobotida faqat agregatlar va kritik qoida sarlavhalari; yuborish auditlanadi.
9. Prod'da kreditlar — `FileConnector` CSV; `forward` maqsadlar oynada kesilmaydi.
10. Bankdan kelgan topshiriq holatlari TZ'ning 6 holatidan 3 tasiga moslanadi.

## 13. Ochiq savollar (mijozga)
1. Har bank uchun mijoz-bank eksport formati (1CClientBankExchange, CSV, …) va yetkazish usuli
   (SFTP → inbox?), hisoblar ro'yxati filial va 1C schyoti bilan (`banks.accounts` uchun).
2. DirectBank (1С): 1C konfiguratsiyasi/versiyasi, qaysi ma'lumot ochiladi, texnik hisob — javobgacha
   fayl orqali.
3. Kredit reyestri va grafiklari manbai (1C'dagi registr yoki g'aznachilik jadvali) — CSV shablon berildi.
4. Qaysi filiallar oqimi bank ko'chirmasidan olinadi (`banks.statement_branches`) va bank проводкаларига
   ПКМ №54 statyasi qanday beriladi (bank statyani bilmaydi — hozir «Прочие»).
5. Telegram: bot egasi, chat'lar ro'yxati, tashqi servisga agregat raqamlarni yuborishga axborot
   xavfsizligi xizmatining roziligi; korporativ proksi mavjudligi.
6. Kredit qoidalari chegaralarini tasdiqlash (30 kun, 85%).
7. Valyuta hisoblarida kurs qayta baholanishi «Разница»ga tushadi va sifat tekshiruvi 2 (>1% oborot)
   publish'ni to'xtatishi mumkin — qabul qilinadimi yoki qayta baholash alohida ko'rsatiladimi.
