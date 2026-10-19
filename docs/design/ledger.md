# UGEKAZNA — dizayn ledger'i (3-reja)

Vizual manba qulflangan: `.superpowers/sdd/planning/prototype.*` (foydalanuvchi tasdiqlagan).
2026-10-19: foydalanuvchi manbani qayta tasdiqladi — `.superpowers/sdd/planning/prototype-v2-artifact.html`
(tokenlar, layout va komponentlar o'zgarmagan; qo'shimcha: `.srcbar` manba paneli va «—» bo'sh holatlar).
Refero faqat prototipda yo'q ekranlar uchun ishlatildi (refero-design skill: "user-provided visual
source" bor — style qidiruvi o'rniga screens/flows). Tokenlar ma'nosi o'zgartirilmadi.

## Tadqiqot (Refero MCP, 2026-09-24)

| Ekran | Manbalar (Refero ID) | Olingan qaror |
|---|---|---|
| Login | Mercury flow 11027 (`28a05ea2`, `94763a9a`), Starbucks `0e3698ed`, Preply `e0f62a4b` | Markazlashgan bitta karta, tepada logotip; xato — maydonlar ustidagi alert qutisi; parol ko'rsatish tugmasi. Marketing paneli, "remember me", "забыли пароль" self-service — rad (ichki tizim; parolni admin tiklaydi, pastda shu haqida matn). |
| 2FA kodi | Mercury `e9329782`, Wise `991ab591`, Wealthsimple `2276e6de` | Bitta katta raqamli maydon (`inputmode=numeric`, `autocomplete=one-time-code`), 6-raqamda avto-yuborish; ostida "Использовать резервный код" havola-tugmasi; inline xato. "Trust this device 30 days" — rad (spec: 2FA har kirishda majburiy). 6 alohida katak (Chargetrip) — rad: paste/autofill/ekran o'quvchi uchun yomon. |
| 2FA ulash | Chargetrip flow 9285 (`f12d8128`, `8a6a34e1`, `5a04877c`), Mapbox flow 9709 (`d67e0815`, `c0d26731`), Family `6d315be3` | 2 qadam ("Шаг 1 из 2"): QR chapda + qo'lda kiritiladigan kalit (4 belgili guruhlar, nusxalash) + kod maydoni; so'ng "Резервные коды": ogohlantirish qutisi (warn tokenlari), 10 kod monospace ro'yxatda, "Скачать"/"Скопировать", "Я сохранил…" belgisi bo'lmaguncha "Продолжить" o'chiq. |
| Parol almashtirish | Nothing `62c5434a`, GoFundMe `365201a4`, Dropbox `9e983e6c` | Joriy/yangi/takror maydonlar ostida jonli qoidalar ro'yxati (≥12 belgi, 4 turdan 3 tasi, loginsiz, mos kelish); server qaytargan `password_policy` muammolari matn bilan. |
| Mening sessiyalarim | Yelp `548e0f63`, Framer `2b704cf5` | Ro'yxat: qurilma, IP, kirish vaqti, faollik; joriy sessiya — badge, boshqalari — "Завершить" (tasdiq bilan). |
| Admin jadvallari | Linear `e0937c40`, Mercury `2bc9e411` / `91b4670c`, Fingerprint `0363a002` | Sarlavha qatori: qidiruv chapda, asosiy amal o'ngda; zich jadval, ikki qatorli katak (asosiy + kichik kulrang); holat badge'lari; qatorni bosish → tahrirlash dialogi; xavfli amallar dialog pastida alohida bo'limda. |
| Audit jurnali | Dropbox `5e6ff4e4` | "Фильтр" qatori (sana oralig'i, foydalanuvchi, amal, natija) + "Сбросить" + "Выгрузить CSV"; jadval: vaqt / foydalanuvchi / amal / natija / obyekt / IP; qator → tafsilot dialogi. |
| Xato holati | Trip.com `a9860253` | Kontent ichida xabar + "Повторить"; TZ bo'yicha qo'shimcha: oxirgi muvaffaqiyatli yuklash vaqti va so'rov kodi. |
| Bo'sh holat | Linear `321d1c36` | Ikonka + sarlavha + nima o'zgartirish kerakligi haqida bir jumla. |
| Ctrl+K palitra | Raycast `370ddbce`, fal `43640d5d`, Runey `237a7449` | Markaziy dialog, tepada qidiruv, ro'yxatda "nomi — turi" (o'ngda kulrang), ↑↓/Enter/Esc, pastda klaviatura ishoralari. |
| Mobil filtrlar | LinkedIn `da294cea`, `a4508d4e`, Uber Eats `78449ca7` | Pastki varaq: tutqich, sarlavha + yopish, ichida o'sha filtr boshqaruvlari, pastda to'liq kenglikdagi "Готово"; "Сбросить всё" chiplar qatorida qoladi. |
| Mobil menyu | Wispr Flow `e64e8236`, Kin `805f8a85` | Chapdan chiqadigan drawer: tepada bo'lim nomi/ikonkasi, ostida sahifalar ro'yxati (≥44 px qatorlar). |

## Qarorlar

| Qaror | Manba | Rol qoidasi | Sabab |
|---|---|---|---|
| Qobiq, kartalar, jadvallar, chiplar — prototip klasslari va o'lchamlari | prototip | tokenlar ma'nosi o'zgarmaydi | qulflangan vizual manba |
| Auth kartasi `--card` + `--shadow`, fon — prototip radial gradientlari | prototip + Mercury | qizil faqat xato | yagona vizual til |
| Kod maydoni — bitta input | Mercury, craft (paste/autofill) | — | a11y va parol menejerlari |
| Ogohlantirishlar (`--warn`/`--warn-bg`) | Mapbox `c0d26731` | faqat "diqqat" (zaxira kodlar, eskirgan ma'lumot, 2FA ulanmagan) | qizil manfiy/xato uchun band |
| Muvaffaqiyat (`--ok`/`--ok-bg`, to'q moviy-yashil) | ko'k gamma (TZ 6) | faqat "faol/muvaffaqiyatli" holat | yashil palitraga chiqmaslik |
| Jadval mobil'da kartochka (`data-label`) | spec 7.5 | — | gorizontal skrollsiz |
| Filtrlar URL'da, chiplar ×, "Сбросить всё" 2+ chip bo'lsa | TZ 6, prototip `chips()` | — | prototip xatti-harakati |
| Manba paneli `.srcbar` (sarlavha ostida): `live` — chap chegara `--brand2`, `warn` — `--neg` | prototype-v2 (foydalanuvchi 2026-10-19 tasdiqladi) | qizil faqat eskirgan ma'lumot | real ilovada manba/freshness paneli (`/meta/freshness`) |
| Bo'sh holat: manbada ma'lumot yo'q → KPI qiymati «—» + izoh `common.noData`; karta o'rniga EmptyState matni; plan=0 → foiz «—» (0 ga bo'lish yo'q) | prototype-v2 | — | S1–S5 bo'lim rejalarida qo'llanadi (`KpiTile value="—" delta=…`, `formatNumber(NaN) → «—»`) |

## Token qarorlari va kontrast (WCAG 2.1)

`src/styles/tokens.test.ts` har juftlikni tekshiradi.

| Token | Prototip | Yangi | Sabab (o'lchangan nisbat) |
|---|---|---|---|
| `--muted` | `#5f7288` | `#5a6d83` | `--soft` ustida 4.50 (chegarada) → 4.85; `--bg` ustida 4.99 |
| `--neg` | `#e0453a` | `#c9362c` | oq ustida 4.13 (yiqiladi) → 5.19; `--neg-bg` ustida 4.54 |
| fokus halqasi | `#2ba3db` | `--focus #1d6df2` | oq ustida 2.85 (<3) → 4.64; yuqori panelda `--focus-on-dark #fff` |
| yuqori panel gradienti | `#0b4fa8→#1668d6→#2b8ae6` | `--top → --top-end #1668d6` | `#d5e7ff` matn `#2b8ae6` ustida 2.83 |
| yuqori panel matni | `#d5e7ff`/`#cfe6ff` | `--top-ink #eaf3ff`, asboblar `#fff` | `--top-end` ustida 4.71 |
| `.badge.blue` | `--brand2` `--soft` ustida (4.23) | `--brand` | 7.09 |
| yangi: `--warn`/`--warn-bg` | — | `#8a5a00`/`#fff4dc` | 5.4 |
| yangi: `--ok`/`--ok-bg` | — | `#0a6b73`/`#e2f7f9` | 5.6 |

KPI qiymatidagi gradient matn (`#0b4fa8→#2f8ef5`, oq ustida ≥3.33) faqat katta matn (≥ 2.1rem, 700) uchun —
WCAG "large text" 3:1 talabiga mos. `html` o'lchami `clamp(16px, calc(10px + .45vw), 21px)` — prototipning
16/17/18/21 px pog'onalarini silliq takrorlaydi.

## Ma'lum cheklovlar

- Caddy'da brotli kodlovchi yo'q — `encode zstd gzip` (spec 6.2 "brotli/gzip" o'rniga zstd/gzip).
- Mobil kartochka rejimida `display:block` jadval semantikasini ba'zi brauzerlarda (Safari) yo'qotadi;
  har katakda `data-label` ko'rinadigan yorliq bor. E2E mobil'da jadval rolini tekshirmaydi.
