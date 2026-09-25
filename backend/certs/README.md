# Korporativ CA

Bu yerdagi `*.crt` fayllar (PEM) — TLS-inspeksiya qiluvchi korporativ proksi orqasida
`pip` (build vaqtida) va tashqi HTTPS so'rovlar ishlashi uchun. Papka bo'sh bo'lsa hech
narsa o'zgarmaydi. Bu ochiq sertifikat, sir emas.

**Build bosqichi** (`pip install`): CA har doim ishonchli — proksi orqasida bo'lmasa,
bo'sh papka bilan hech narsa o'zgarmaydi, xavfsiz.

**Runtime image** (ishlab turgan konteyner): CA'ga ishonish ENDI IXTIYORIY, sukut
bo'yicha O'CHIQ — build-arg `RUNTIME_EXTRA_CA` (sukut `false`). Bugungi kunda 1C
(10.0.90.52) oddiy HTTP orqali ishlaydi va runtime'da tashqi HTTPS integratsiyasi yo'q,
shuning uchun ilova konteyneri korporativ proksi CA'siga umuman ishonmaydi (kichikroq
hujum yuzasi). Kelajakda runtime'dan TLS-inspeksiya proksisi orqasidagi HTTPS xizmatga
integratsiya kerak bo'lsa, image'ni shu bilan quring:

```
docker build --build-arg RUNTIME_EXTRA_CA=true -t ugekazna-backend backend/
```

Compose (`deploy/compose.yml`, `deploy/compose.test.yml`) ushbu build-arg'ni bermaydi,
shuning uchun ular sukut bo'yicha `false` — runtime konteynerlar bu CA'ga ishonmaydi.
