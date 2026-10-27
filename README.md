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
**Diqqat (operator):** har `<maqsad>.csv` yuklash oynasi uchun BARCHA qatorlarni o'z ichiga olishi shart
(`--mode full` — `etl.history_start`dan beri butun tarix); to'liq bo'lmagan CSV'da yo'q qatorlar bazadan
O'CHIRILADI. Sanasi bo'sh qatorlar `missing_value` sifatida rad etiladi. Shu sababli `--mode full --source file`
faqat `--allow-full-replace` bilan ishlaydi (admin navbati orqali file+full so'rovlar rad etiladi).

**Eslatma (dev):** bu branch'da migratsiyalar joyida o'zgartirilgan — oldingi dev bazalarini qayta yarating
(`docker compose -f deploy/compose.yml down -v`) va `python scripts/gen_secrets.py` ni qayta ishga tushiring
(`smtp_password` siri qo'shilgan).
API: https://localhost:8443/api/v1/ (sertifikat Caddy'ning ichki CA'si — brauzer ogohlantiradi).

Frontend: https://localhost:8443/ (build `frontend/Dockerfile` → Caddy). O'zgarishdan keyin: `make web`
yoki `docker compose -f deploy/compose.yml up -d --build caddy`.

Frontend testlari (Node faqat Docker'da):
```bash
NODE="docker compose -f deploy/compose.frontend.yml run --rm node"
$NODE npm ci
$NODE npm run check            # tsc + eslint + vitest
curl -skf https://localhost:8443/api/v1/openapi.json -o frontend/openapi.json && $NODE npm run gen:api   # API tiplari
```

## Testlar

```bash
docker compose -f deploy/compose.test.yml run --rm test pytest
docker compose -f deploy/compose.test.yml run --rm test ruff check app tests tools
docker compose -f deploy/compose.test.yml run --rm test mypy app tools
docker compose -f deploy/compose.test.yml down
```

E2E (Playwright, 390/1024/1440 kenglik, haqiqiy dev stack):
```bash
docker compose -f deploy/compose.yml up -d --build
./scripts/e2e.sh                       # seed-e2e (faqat dev/test) + Playwright
```
Hisobot: `frontend/e2e/playwright-report/index.html`.
`make e2e-ci` — CI'dagi E2E (toza checkout).

Darvozalar: `make check` (repo + backend + frontend). `make hooks` ulaydigan pre-commit hook — qulaylik uchun (faqat staged o'zgarishlar); hakamlik qiluvchi darvoza — `make check-repo` (butun git tarixi).
Limit: to'liq yugurish 6 login (10/min) va ~7 MFA (20/min) ishlatadi — ~60 s ichida qayta yugurtirsangiz 429 chiqishi mumkin; bir daqiqa kuting.

## Operator CLI (`python -m app.cli <buyruq>`)

| Buyruq | Nima qiladi | Qayerda ishga tushiriladi |
|---|---|---|
| `create-admin --username U --full-name F` | birinchi administrator (vaqtinchalik parol bir marta chiqadi) | `api` konteyneri |
| `rotate-key --purpose P` | DEK rotatsiyasi + qayta shifrlash | **faqat `migrate` konteyneri** |
| `retire-keys [--grace-minutes N]` | ishlatilmayotgan eski DEK'larni yo'q qilish | **faqat `migrate` konteyneri** |
| `rewrap-keys --new-kek-file F` | KEK rotatsiyasi (barcha DEK'larni yangi KEK bilan qayta o'raydi) | **faqat `migrate` konteyneri** |
| `audit-verify` | audit zanjirini tekshirish (buzilgan bo'lsa chiqish kodi 2) | `migrate` konteyneri (`make audit-verify`) |
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

(`make retire-keys` / `make rewrap-keys f=...` — qulay yorliqlar; `make retire-keys` standart `--grace-minutes` bilan ishlaydi, boshqa qiymat uchun CLI'ni to'g'ridan-to'g'ri chaqiring.)

Operator buyruqlari (`create-admin`, `audit-verify`, `rotate-keys`, `retire-keys`, `rewrap-keys`, `etl-run`, `rollback-build`, `ops-check`, `migrate`) standart holda dev stack'ga qaratilgan; prod uchun buyruq qatorida `STACK=prod` bering (muhit o'zgaruvchisi hisobga olinmaydi). Prod host'da: `make prod-up`, `make prod-down`, `make prod-ps`. **Prod host'da (`deploy/prod.env` bor) dev-stack buyruqlari (`up`, `down`, `build`, `logs`, `web`, `seed-synthetic`, `STACK=dev` bilan operator buyruqlari) xatolik bilan rad etiladi** — dev va prod compose loyiha nomi bir xil (`ugekazna`), shuning uchun `make down` prod'ni to'xtatardi.

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

## Sifat darvozalari (CI)

Hammasi Docker'da (host'ga faqat Docker Desktop va Git for Windows kerak). Linux/CI — `make`,
Windows — `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 <target>`:

| Target | Nima qiladi |
|---|---|
| `check` | gitleaks (butun tarix), semgrep, hadolint, ruff, mypy, bandit, pip-audit, pytest (qamrov ≥ 85 %, `app/core`, `app/auth`, `app/dwh` ≥ 95 %), tsc, eslint, vitest, npm audit |
| `scan` | prod image'lar (digest bilan qotirilgan base) + Trivy HIGH/CRITICAL + CycloneDX SBOM (`build/sbom/`) |
| `hooks` | pre-commit hook: staged o'zgarishlarda gitleaks + ruff |
| `test-caddy`, `db-smoke`, `prod-config` | prod konfiguratsiyasi testlari |
| `backup-selftest` | zaxira/tiklash avtotesti (sekin) |
| `load-test` | k6 yuklama testi (dev stack + sintetik ma'lumot) |

CI: `.github/workflows/ci.yml` va `.gitlab-ci.yml` — ikkalasi ham `make check` va `make scan`.
Istisnolar reyestri: `docs/security/sast-exceptions.md`.

## Prod

O'rnatish, yangilash va orqaga qaytarish: `docs/ops/install-upgrade.md`. Reliz paketi: `make release VERSION=1.0.0`
(image'lar, SBOM, `deploy/`, `scripts/`, hujjatlar, `SHA256SUMS`). Prod stack: `deploy/compose.prod.yml`.

## Hujjatlar

- Xavfsizlik (ekspertiza uchun, rus tilida): `docs/security/README.md`
- Ekspluatatsiya (rus tilida): `docs/ops/README.md`

## Bog'liqliklar

`backend/requirements*.txt` — `make lock` (pip-compile `--generate-hashes`) natijasi, image `--require-hashes`
bilan o'rnatadi. Lock-fayl sarlavhasidagi `--no-index` — pip-tools 7.6.1 sarlavha xususiyati, o'rnatishga ta'sir
qilmaydi; kanonik buyruq — `make lock`.
