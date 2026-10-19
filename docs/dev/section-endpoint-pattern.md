# Bo'lim endpointi pattern'i

Har bo'lim endpointi (`/api/v1/<bo'lim>/...`) bir xil zanjir bo'yicha yoziladi:
`router → service → pub view`, javob `Cache` orqali. Namuna — `app/meta/router.py` (`/meta/branches`).

```python
@router.get("/svod", response_model=SvodOut)
def svod(
    cache: Cache,
    db: DB,
    ctx: Ctx,
    br: Annotated[int | None, Query(ge=1)] = None,
    per: Annotated[str, Query(pattern=r"^(ytd|q[1-4]|m(0[1-9]|1[0-2]))$")] = "ytd",
) -> Response:
    ctx.assert_branch(br)                      # 1-qavat RLS: doiradan tashqari → 403 + audit
    period = resolve_period(per, today_tashkent())  # noma'lum kod → 422; kod «bugun»ga nisbiy
    filters = {"br": br, "per": per, "from": period.date_from.isoformat(),
               "to": period.date_to.isoformat()}  # kalitda aniq sanalar — oy/yil almashganda eskiradi
    return cache.respond("kazna.svod", filters, lambda: service.svod(db, br, period))
```

(`SvodOut` va `service.svod` — shu bo'lim rejasida yoziladigan sxema va servis funksiyasi.)

Qoidalar:
1. **Faqat `pub.*` view'lar.** Servis `dwh`/`mart` jadvallarini to'g'ridan-to'g'ri o'qimaydi; view'lar
   faqat aktiv build'ni ko'rsatadi. `security_invoker = true` view'ni chaqiruvchi roli huquqi bilan ishlatadi
   (shu sabab `ugk_app`ga asosiy jadvallarga ham SELECT berilgan); RLS (2-qavat) asosiy jadvallardagi
   `FORCE ROW LEVEL SECURITY` + policy tufayli ishlaydi.
2. **Faktlarga so'rov yo'q** (TZ 9): yangi ko'rsatkich kerak bo'lsa — `app/dwh/aggregates.py` ga
   `register(Aggregate(...))` + migratsiyada `mart.agg_*` jadvali va `pub.*` view.
3. **Kesh kaliti** `ugk:v{data_version}:{endpoint}:{scope_hash}:{filters_hash}` — `endpoint` nomi
   `"<bo'lim>.<sahifa>"`; `filters` ga faqat javobga ta'sir qiluvchi, validatsiyalangan parametrlar.
   Publish/rollback'da kesh o'zi eskiradi; qo'lda tozalash kerak emas.
4. **ETag/304** avtomatik; `Cache-Control: private, no-cache` (umumiy `no-store` ustidan).
5. **Filial filtri**: `br` bo'lsa avval `ctx.assert_branch(br)`; `branch_id = 0` (jami) faqat
   `scope_all` foydalanuvchiga ko'rinadi — filial foydalanuvchisi uchun jami o'z filiali qatorlaridan.
6. **Testlar**: har endpoint uchun (a) filial foydalanuvchisi boshqa filialni ko'rmaydi (API),
   (b) 304, (c) `published_synthetic` fixture bilan haqiqiy agregatlar.

## Kesh to'g'riligi shartnomasi

`Cache` ortidagi loader **sof funksiya** bo'lishi shart: natija faqat (aktiv build, foydalanuvchi
filial doirasi, `filters`) ga bog'liq va ma'lumot faqat so'rovning `db` sessiyasi orqali o'qiladi
(RLS shu yerda qo'llanadi). Shu sababli `Cache` ortida **bo'lmasligi** kerak:
- rol/ruxsatga bog'liq maydonlar (kesh kaliti faqat filial doirasini hisobga oladi);
- «bugun»ga nisbatan standart qiymatlar — agar ular `filters` ichiga aniq sana qilib yozilmasa;
- freshness/yoshga bog'liq bayroqlar (`stale` va h.k.) — vaqt o'tishi bilan o'zgaradi;
- publish'dan tashqarida tahrirlanadigan ma'lumot (`core.alert_rules`, `core.settings`, `dwh.dim_*` — ETL yangilaydi, build'ga bog'liq emas) — build
  versiyasi o'zgarmaydi, kesh eskirmaydi. (`/meta/branches` uchun `dwh.dim_*` qabul qilingan: o'lchovlar yuklashdan
  so'ng darhol publish qilinadi.)

Bunday endpointlar `Cache`siz javob beradi (masalan, `/meta/periods`, `/meta/freshness`, `/meta/menu`).
