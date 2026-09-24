# UGEKAZNA

«Узбекгидроэнерго» AJ uchun UGE ERP ustidagi analitik BI-qatlam.
Spec: `docs/superpowers/specs/`, rejalar: `docs/superpowers/plans/`, TZ: `docs/reference/UGEKAZNA_TZ.pdf`.

## Tez boshlash (dev, Windows / Git Bash)

```bash
python scripts/gen_secrets.py
docker compose -f deploy/compose.yml up -d --build
docker compose -f deploy/compose.yml exec api python -m app.cli create-admin --username admin --full-name "Администратор"
```
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
| `rotate-key --purpose P` | DEK rotatsiyasi + qayta shifrlash | `api` konteyneri |
| `retire-keys [--grace-minutes N]` | ishlatilmayotgan eski DEK'larni yo'q qilish | **faqat `migrate` konteyneri** |
| `rewrap-keys --new-kek-file F` | KEK rotatsiyasi (barcha DEK'larni yangi KEK bilan qayta o'raydi) | **faqat `migrate` konteyneri** |
| `audit-verify` | audit zanjirini tekshirish (buzilgan bo'lsa chiqish kodi 2) | `api` konteyneri |
| `cleanup` | eskirgan sessiya va 2FA challenge'larni o'chirish | `api` konteyneri |

`retire-keys` va `rewrap-keys` `core.crypto_keys.wrapped_key` ustunini bo'shatadi/qayta yozadi —
bu ustunga `ugk_app`(API)ning yozish huquqi yo'q (crypto-shredding'dan himoya, spec 3.5), shuning
uchun dev'da `api` konteyneriga migrator siri berilmagan va bu ikki buyruq faqat shunday ishga
tushiriladi:

```bash
docker compose -f deploy/compose.yml run --rm migrate python -m app.cli retire-keys
```

(`make retire-keys` / `make rewrap-keys f=...` — Linux/prod uchun qulay yorliqlar, `Makefile`ga qarang.)

## Xavfsizlik asoslari

- Sirlar faqat Docker secrets orqali (`deploy/secrets.example/README.md`).
- Parollar Argon2id; hamma uchun majburiy TOTP 2FA.
- Sezgir ustunlar AES-256-GCM (envelope, KEK → DEK), kalit rotatsiyasi: `python -m app.cli rotate-key --purpose mfa`.
- Audit jurnali faqat qo'shishga ochiq, hash-chain: `python -m app.cli audit-verify`.
