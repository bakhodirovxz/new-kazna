# UGEKAZNA

«Узбекгидроэнерго» AJ uchun UGE ERP ustidagi analitik BI-qatlam.
Spec: `docs/superpowers/specs/`, rejalar: `docs/superpowers/plans/`, TZ: `docs/reference/UGEKAZNA_TZ.pdf`.

## Tez boshlash (dev, Windows / Git Bash)

```bash
python scripts/gen_secrets.py
docker compose -f deploy/compose.yml up -d --build
docker compose -f deploy/compose.yml exec api python -m app.cli create-admin --username admin --full-name "Администратор"
```
Sintetik ma'lumot (dev): `docker compose -f deploy/compose.yml exec worker python -m app.cli etl-run --source synthetic --mode full`
(worker dev'da buni har kecha 02:00 da o'zi bajaradi). Aktiv build'ni qaytarish: `python -m app.cli rollback-build`.
CSV yuklash: fayllarni `etl_inbox` volume'iga (`<maqsad>.csv`, UTF-8, `;`, ISO sanalar) qo'yib, `etl-run --source file`.
API: https://localhost:8443/api/v1/ (sertifikat Caddy'ning ichki CA'si — brauzer ogohlantiradi).

## Testlar

```bash
docker compose -f deploy/compose.test.yml run --rm test pytest
docker compose -f deploy/compose.test.yml run --rm test ruff check app tests
docker compose -f deploy/compose.test.yml run --rm test mypy app
docker compose -f deploy/compose.test.yml down
```

## Operator CLI (`python -m app.cli <buyruq>`)

| Buyruq | Nima qiladi | Qayerda ishga tushiriladi |
|---|---|---|
| `create-admin --username U --full-name F` | birinchi administrator (vaqtinchalik parol bir marta chiqadi) | `api` konteyneri |
| `rotate-key --purpose P` | DEK rotatsiyasi + qayta shifrlash | **faqat `migrate` konteyneri** |
| `retire-keys [--grace-minutes N]` | ishlatilmayotgan eski DEK'larni yo'q qilish | **faqat `migrate` konteyneri** |
| `rewrap-keys --new-kek-file F` | KEK rotatsiyasi (barcha DEK'larni yangi KEK bilan qayta o'raydi) | **faqat `migrate` konteyneri** |
| `audit-verify` | audit zanjirini tekshirish (buzilgan bo'lsa chiqish kodi 2) | `api` konteyneri |
| `cleanup` | eskirgan sessiya, 2FA challenge va staging qatorlarini o'chirish | `worker` konteyneri |
| `etl-run --source S --mode full\|incremental [--no-retry]` | ETL yuklash | `worker` konteyneri |
| `rollback-build [--build ID]` | aktiv build'ni qaytarish | `worker` konteyneri |

`retire-keys` va `rewrap-keys` `core.crypto_keys.wrapped_key` ustunini bo'shatadi/qayta yozadi —
bu ustunga `ugk_app`(API)ning yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5), shuning
uchun dev'da `api` konteyneriga migrator siri berilmagan va bu ikki buyruq faqat shunday ishga
tushiriladi. `rotate-key` ham endi migrator ulanishini talab qiladi (fix r1, I1): `ugk_app`
`dwh.dim_counterparty.inn_enc`/`dwh.dim_bank.account_enc`ga umuman kira olmaydi, shuning uchun
bu buyruq avval "app" ulanishida `core.*` ustunlarni, so'ng "migrator" ulanishida `dwh.*`
ustunlarni qayta shifrlaydi. Admin API (`POST /admin/keys/{purpose}/rotate`) hamon ishlaydi,
lekin faqat `core.*` (role="app") ustunlarni qayta shifrlaydi — `dwh.*` ustunlar operator
`rotate-key` buyrug'ini kutadi:

```bash
docker compose -f deploy/compose.yml run --rm migrate python -m app.cli rotate-key --purpose pii
docker compose -f deploy/compose.yml run --rm migrate python -m app.cli retire-keys
```

(`make retire-keys` / `make rewrap-keys f=...` — Linux/prod uchun qulay yorliqlar, `Makefile`ga qarang.)

### `rewrap-keys` — KEK rotatsiyasi

Yangi KEK (base64, aynan 32 bayt) alohida faylga yozilib, `migrate` konteyneriga **absolyut**
yo'l bilan (Docker bind-mount nisbiy yo'lni konteyner ichida kutilganidek hal qilmaydi) va
konteyner foydalanuvchisi (`10001:10001`) o'qiy oladigan huquqlar bilan bog'lanadi:

```bash
python -c "import base64, secrets; open('/tmp/new_kek','w').write(base64.b64encode(secrets.token_bytes(32)).decode())"
chmod 644 /tmp/new_kek   # yoki: chown/chmod uid 10001 o'qiy oladigan qilib
docker compose -f deploy/compose.yml run --rm -v "/tmp/new_kek:/tmp/new_kek:ro" migrate \
  python -m app.cli rewrap-keys --new-kek-file /tmp/new_kek
shred -u /tmp/new_kek   # yoki: rm -P /tmp/new_kek — fayl diskda qolmasin
```

Buyruq yangi KEK joriy KEK bilan bir xil bo'lsa rad etadi (chiqish kodi 1). Muvaffaqiyatli
tugagach, baza allaqachon YANGI KEK bilan o'ralgan bo'ladi — shu zahoti
`deploy/secrets/master_kek`ni yangi qiymat bilan almashtirib, `api`/`migrate` xizmatlarini
qayta ishga tushiring (aks holda ular eski KEK bilan ishga tushishga urinib, kalitlarni
ocha olmay yiqiladi).

## Xavfsizlik asoslari

- Sirlar faqat Docker secrets orqali (`deploy/secrets.example/README.md`).
- Parollar Argon2id; hamma uchun majburiy TOTP 2FA.
- Sezgir ustunlar AES-256-GCM (envelope, KEK → DEK), kalit rotatsiyasi: `python -m app.cli rotate-key --purpose mfa`.
- Audit jurnali faqat qo'shishga ochiq, hash-chain: `python -m app.cli audit-verify`.
