# 1C API'ga so'rov: UGEKAZNA 1-bosqichi («Обзор» + «Казначейство») uchun yetishmayotgan ma'lumotlar

**Kimga:** 1C (UGE ERP, con2026) dasturchisi / ma'muriyati
**Kimdan:** UGEKAZNA jamoasi (moliyalashtirish va pul oqimlarini nazorat qilish bo'limi)
**Sana:** 2026-09-25

---

## Hozirgi holat

UGEKAZNA 1C bilan faqat mavjud `hs/aiassistant` HTTP-servislari orqali ishlaydi (to'g'ridan-to'g'ri
bazaga so'rov yo'q). Hozir ishlatiladi:

| Endpoint | Nima uchun | Muammo |
|---|---|---|
| `POST /payments` | Расходование (`fact_cashflow`) | javobda tashkilot, statya/kontragent UID, holat, bank hisobi yo'q; sahifalash yo'q (`limit` dan ortig'i kesiladi) |
| `POST /income` | Поступления | hujjatda aytilganidek, hozir **test ma'lumot** qaytaradi; hujjat raqami/UID yo'q |
| `POST /budget` `{"Mode": "plan"}` | План платежей (oylik) | statya UID va ПКМ №54 kodi yo'q |

TZ 4-bo'limidagi ko'rsatkichlar uchun quyidagilar **yetishmaydi**. Ular bo'lmaguncha tegishli
kartalarda «нет данных — источник не подключён» ko'rsatiladi.

## So'rovlar (ustuvorlik tartibida)

### 1. HTTPS (G1) — xavfsizlik, eng muhim
Servis hozir `http://10.0.90.52/con2026/hs/aiassistant` da. Basic auth paroli tarmoqda ochiq o'tadi.
**So'rov:** web-publikatsiyani HTTPS'ga o'tkazish (korporativ sertifikat), HTTP'ni o'chirish;
UGEKAZNA uchun **faqat o'qish huquqli alohida foydalanuvchi** yaratish. Eski dashboard konfiguratsiyasida
saqlangan 1C paroli almashtirilishi kerak.

### 2. Bank hisoblari qoldiqlari (G2)
```http
POST /balances
{"date_from": "20260101", "date_to": "20260924", "org_uid": "<ixtiyoriy>"}
```
```json
{"balances": [
  {"org_uid": "…", "org_name": "…", "account_uid": "…", "account_number": "2021…",
   "bank_name": "Узпромстройбанк", "currency": "UZS", "gl_account": "5110",
   "date": "2026-09-24", "balance": 1234567890.12}
]}
```
Счета 5110, 5210, 5530; har kun uchun (yoki har hisob bo'yicha o'zgargan kunlar) kun oxiridagi qoldiq.
Kerak: Начальный/конечный остаток, «Разница», покрытие платежей, 2 ta kritik ogohlantirish.

### 3. Nazorat summalari (G3)
```http
POST /turnovers
{"year": 2026, "month": 9}
```
```json
{"items": [{"gl_account": "5110", "debit": 0.00, "credit": 0.00}]}
```
TZ sifat tekshiruvi 1: витринадаги oylik oqim = 1C oborotlari (5110, 5210, 5530) ±0,1%.

### 4. Shartnomalar bo'yicha qarzdorlik (G4)
```http
POST /debts
{"date": "20260924", "org_uid": "<ixtiyoriy>"}
```
```json
{"debts": [
  {"org_uid": "…", "contract_uid": "…", "contract_number": "12/2026", "contract_date": "2026-01-15",
   "contract_sum": 1000000000, "contract_end": "2026-12-31", "contractor_uid": "…",
   "contractor_name": "…", "contractor_inn": "301234567", "kind": "payable|receivable",
   "balance": 250000000, "overdue": 50000000, "due_date": "2026-06-30", "overdue_days": 86}
]}
```
Kerak: Дебиторская/кредиторская/просроченная задолженность, реестр договоров, 2 ta ogohlantirish.

### 5. To'lov talabnomalari holati va rejalashtirilgan sanasi (G5)
`/payments` javobiga qo'shish (Документ.ЗаявкиНаРасходованиеДС):
```json
{"uid": "…", "org_uid": "…", "status": "На согласовании|Согласована|К оплате|Оплачена|Отклонена|Черновик",
 "status_date": "2026-09-20", "desired_payment_date": "2026-09-30",
 "expense_type_uid": "…", "contractor_uid": "…", "bank_account_uid": "…"}
```
va **qo'shimcha**: bank orqali haqiqatda to'langan summalar (Списание с расчётного счёта, проведённые)
alohida endpoint yoki maydon bilan — «Расходование» hozir talabnomalar bo'yicha hisoblanmoqda.
Kerak: платёжные поручения 6 holat bo'yicha, заявки в работе, платёжный календарь 14 kun.

### 6. Maqsadli mablag'lar (G6)
```http
POST /targetFunds
{"year": 2026}
```
```json
{"items": [{"org_uid": "…", "source_uid": "…", "source_name": "Бюджетные средства …",
            "object_uid": "…", "month": 9, "allocated": 0.00, "used": 0.00}]}
```

### 7. Ma'lumotnomalar (G7)
```http
POST /catalogs
{"kind": "organizations|expense_types|contractors"}
```
Tashkilotlar: `uid, name, inn`; statyalar: `uid, name, pkm54_code, activity (централизованная|
операционная|инвестиционная), direction (приход|расход)`; kontragentlar: `uid, name, inn, kind`.
Hozir kodlar nomdan xesh bilan olinmoqda — nom o'zgarsa yangi statya paydo bo'ladi.

### 8. `/income` haqiqiy ma'lumoti va hujjat UID'i (G8)
Test ma'lumot o'rniga `Документ.ДоходыФакт` (yoki Поступление на расчётный счёт) — `uid`, `number`,
`org_uid`, `direction_uid`, `bank_account_uid`.

### 9. Sahifalash va o'zgarish belgisi (G9)
Barcha ro'yxat endpointlariga `offset`/`cursor` (yoki `limit` siz to'liq javob) va har hujjatda
`version`/`changed_at` (ВерсияДанных) — inkremental yuklash va dublikatsiz qayta yuklash uchun.

### 10. Bank hisobi har to'lov/tushumda (G10)
«Поступления/Расходование по банкам» kartalari uchun `bank_account_uid`.

## Texnik talablar (barcha endpointlar)
- Javob: UTF-8 **BOM'siz**, `Content-Type: application/json`; xatoda HTTP 4xx/5xx va JSON
  `{"error": "…"}` (HTML sahifa emas).
- Summalar — son (so'mda, nuqta bilan kasr), razryad ajratkichsiz; sanalar — ISO 8601 (`ГГГГ-ММ-ДД`).
- So'rov parametrlari nomlari bir xil registrda (hozir `/payments` — kichik harf, qolganlari — PascalCase).
- Salbiy summalar (сторно) semantikasini yozma tasdiqlash: hozir UGEKAZNA ularni o'tkazib yuboradi.

## Natija
Yuqoridagilar qo'shilgach, UGEKAZNA tomonida faqat konnektor moslashtirishi qo'shiladi (TZ 1-bosqich:
«дашборд на реальных данных по денежным потокам»).
