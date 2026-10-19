"""Xavfsiz xato matnlari (findings r1, I1): xom istisno matni (DB DETAIL, konnektor xabari,
foydalanuvchi/manba kiritgan qiymat — masalan INN, hisob raqami) jurnal (`core.etl_run.error`,
`core.etl_step.detail`), xabarnoma (`app.etl.notify.Notification`) yoki logga HECH QACHON
to'g'ridan-to'g'ri chiqmasligi kerak — faqat sinf nomi (va, `DBAPIError` uchun, SQLSTATE —
hech qachon drayver xabari yoki DETAIL emas).

Faqat BIZ nazorat qiladigan, xabari faqat ID/kod/sozlama kalitidan iborat (hech qachon
tashqi/manba/foydalanuvchi qiymati emas) kichik YOPIQ sinflar ro'yxatining xabari saqlanadi —
qolgan BARCHA istisnolar (DB drayveri, konnektor, kutilmagan/uchinchi tomon kodi) uchun faqat
sinf nomi qaytariladi. Bu ataylab RuntimeError/ValueError kabi keng tarqalgan built-in turlar
bo'yicha EMAS, balki aniq SINF IDENTITETI bo'yicha ishlaydi — chunki, masalan, konnektor ham
`ValueError("bad INN ...")` ko'tarishi mumkin, va uni tasodifan "xavfsiz" deb hisoblash xom
qiymatni sizdirishi mumkin edi. `app/etl/quality.py`ning kontekst tekshiruvlari (scope_all,
build/run mosligi) RuntimeError/ValueError ko'taradi (Task-7, o'zgarmagan) — runner ularni shu
yerdagi `QualityContextError`ga o'rab beradi, chunki ularning xabari FAQAT ID/kod/holat
nomlaridan iborat ekanligi tekshirilgan (quality.py manbasi)."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError


class EtlBusyError(Exception):
    """Boshqa yuklash bajarilmoqda."""


class QualityContextError(Exception):
    """`app.etl.quality.run_checks()` noto'g'ri kontekstda chaqirilgan (scope_all yoki
    build/run mosligi buzilgan) — bu DASTURIY xato (bug), tashqi ma'lumot emas; xabari faqat
    ID/kod/holat nomlaridan iborat (quality.py, task-7 fix r1 M2/M3) — xavfsiz."""


class EtlConfigError(Exception):
    """`core.settings`ni o'qish/talqin qilishdagi dasturiy xato — xabari faqat sozlama
    kaliti/qiymat turi haqida, manba/foydalanuvchi ma'lumoti emas — xavfsiz."""


class FileFormatError(ValueError):
    """CSV format xatosi (FileConnector): xabari faqat fayl nomi:qator va xato turidan iborat,
    manba qiymatini O'ZIDA SAQLAMAYDI — xavfsiz. ValueError qoldi: qayta urinilmaydi."""


_SAFE_MESSAGE_TYPES: tuple[type[BaseException], ...] = (
    EtlBusyError, QualityContextError, EtlConfigError, FileFormatError,
)


def is_safe(exc: BaseException) -> bool:
    """`exc` — biz to'liq nazorat qiladigan, xabari xavfsiz turlardan biri. Faqat shunday
    turlar uchun logga to'liq traceback (`exc_info`) yozish ham xavfsiz hisoblanadi (I1:
    DB/drayver/konnektor yoki noma'lum xatolar uchun `exc_info` HECH QACHON yozilmaydi)."""
    return isinstance(exc, _SAFE_MESSAGE_TYPES)


def sqlstate_of(exc: BaseException) -> str | None:
    """`DBAPIError` uchun SQLSTATE kodi (agar drayver bergan bo'lsa) — xabar/DETAIL emas."""
    if isinstance(exc, DBAPIError):
        value = getattr(exc.orig, "sqlstate", None)
        return str(value) if value else None
    return None


def safe_error(exc: BaseException) -> str:
    """Xabarnoma/jurnal/`etl_run.error`ga yoziladigan matn: sinf nomi, faqat yopiq
    ro'yxatdagi turlar uchun + ularning (xavfsiz, faqat ID/kod) xabari, `DBAPIError` uchun
    qo'shimcha SQLSTATE — hech qachon drayver xabari yoki DETAIL emas."""
    name = type(exc).__name__
    if is_safe(exc):
        text = str(exc)
        return f"{name}: {text}" if text else name
    state = sqlstate_of(exc)
    return f"{name} (SQLSTATE {state})" if state else name
