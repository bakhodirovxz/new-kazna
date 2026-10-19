# Korporativ CA

`*.crt` (PEM) fayllar npm TLS-inspeksiya qiluvchi proksi orqasida ishlashi uchun kerak:
`deploy/compose.frontend.yml` va `frontend/Dockerfile` ularni `NODE_EXTRA_CA_CERTS` orqali ulaydi.
Fayl bo'lmasa Node faqat ogohlantirish chiqaradi — proksisiz tarmoqda hammasi ishlaydi.
