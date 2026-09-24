# Sirlar

Haqiqiy fayllar `deploy/secrets/` da (git'ga tushmaydi). Yaratish: `python scripts/gen_secrets.py`.

| Fayl | Mazmun |
|---|---|
| db_superuser_password | PostgreSQL superuser (faqat initdb) |
| db_migrator_password | ugk_migrator — faqat migratsiyalar |
| db_app_password | ugk_app — API |
| db_etl_password | ugk_etl — ETL worker |
| redis_password | Redis `requirepass` |
| master_kek | base64, 32 bayt — DEK'larni o'raydi |
| blind_index_key | base64, 32 bayt — shifrlangan maydon qidiruvi |
| session_pepper | base64, 32 bayt — token HMAC'lari |

Prod (Linux): `chown root:10001 deploy/secrets/* && chmod 0440 deploy/secrets/*`.
`master_kek` zaxirasi boshqa joyda (seyf/HSM) saqlanadi — u yo'qolsa shifrlangan ma'lumot tiklanmaydi.

## `migrate` va `api` sirlari farqi

`deploy/compose.yml`'da `migrate` konteyneri `db_migrator_password`ga ega (migratsiyalar va
`ugk_migrator` (jadval egasi) sifatida bajariladigan kalit boshqaruv amallari uchun), `api`
konteyneri esa faqat `db_app_password`ga ega. Shu sabab `python -m app.cli retire-keys` va
`python -m app.cli rewrap-keys` (ular `core.crypto_keys.wrapped_key`ni yozadi — `ugk_app`da bu
huquq yo'q, crypto-shredding'dan himoya) `api` konteynerida EMAS, balki:

```bash
docker compose -f deploy/compose.yml run --rm migrate python -m app.cli retire-keys
```

kabi `migrate` konteynerida ishga tushiriladi. `rewrap-keys` uchun yangi KEK (base64, 32 bayt)
alohida faylga yozilib, konteynerga bind-mount qilinadi — yo'l **absolyut** bo'lishi va fayl
konteyner foydalanuvchisi (`10001:10001`) o'qiy olishi SHART (masalan `-v $(pwd)/new_kek:/tmp/new_kek:ro`,
`chmod 644` yoki uid 10001'ga tegishli qilib), so'ng `--new-kek-file /tmp/new_kek` beriladi;
joriy `master_kek` siri (eski KEK) — shifrni ochish uchun — konteynerda allaqachon bor. Buyruq
yangi KEK joriy KEK bilan bir xil bo'lsa rad etadi. Muvaffaqiyatli tugagach, host'dagi vaqtinchalik
KEK faylini SHRED qiling (`shred -u new_kek` yoki `rm -P new_kek` — oddiy `rm` diskda iz qoldirishi
mumkin) va `deploy/secrets/master_kek`ni yangi qiymat bilan almashtirib, `api`/`migrate`
xizmatlarini qayta ishga tushiring.
