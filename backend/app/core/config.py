"""Konfiguratsiya: muhit o'zgaruvchilari + Docker secrets (/run/secrets).

Ustuvorlik: konstruktor argumentlari > env > /run/secrets. Kodda hech qanday sir yo'q.
"""

from __future__ import annotations

import base64
import binascii
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import PositiveFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")
DbRole = Literal["app", "etl", "migrator"]
KEY_FIELDS = ("master_kek", "blind_index_key", "session_pepper")

# deploy/compose.test.yml dagi ochiq test kalitlari. Prod'da ular bilan ishga tushmaydi.
TEST_KEYS = frozenset(
    {
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8=",
        "QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8=",
    }
)

# Oddiy email manzil tekshiruvi: bo'shliq, vergul, <>, @ (ikkinchi marta) — sarlavha
# in'ektsiyasi (CR/LF) va bir nechta manzilni bitta maydonga yashirishning oldini oladi.
_SMTP_ADDR_RE = re.compile(r"^[^\s,<>@]+@[^\s,<>@]+\.[^\s,<>@]+$")


class ConfigError(RuntimeError):
    """Xavfli yoki to'liq bo'lmagan konfiguratsiya."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "prod"  # fail-closed: dev/test faqat aniq ENV bilan
    base_url: str = "https://localhost"
    # S4: HR API manzili/hisobi panelda (integrations); faqat korporativ CA fayli muhitda.
    hr_ca_file: str = "/run/secrets/hr_ca_bundle"
    argon2_profile: Literal["standard", "fast_test"] = "standard"

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "ugekazna"
    db_app_user: str = "ugk_app"
    db_app_password: SecretStr = SecretStr("")
    db_etl_user: str = "ugk_etl"
    db_etl_password: SecretStr = SecretStr("")
    db_migrator_user: str = "ugk_migrator"
    db_migrator_password: SecretStr = SecretStr("")
    # DB_POOL_SIZE: jarayondagi bir vaqtdagi sessiyali so'rovlar (core/db.py `_db_slot`); pool 2x.
    db_pool_size: PositiveInt = 10
    # DB_SLOT_TIMEOUT_SECONDS: slot navbatida kutish chegarasi; oshsa 503 service_busy.
    db_slot_timeout_seconds: PositiveFloat = 5.0
    db_statement_timeout_ms: int = 5000

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")

    master_kek: SecretStr = SecretStr("")
    blind_index_key: SecretStr = SecretStr("")
    session_pepper: SecretStr = SecretStr("")

    etl_statement_timeout_ms: int = 1_800_000
    etl_file_dir: str = "/data/inbox"
    askue_inbox_dir: str = "/data/import/askue"  # S3: АСКУЭ kunlik eksporti (faqat o'qish)
    synthetic_seed: int = 916202617

    # S2: tashqi so'rovlar faqat worker'dan; proksi — ixtiyoriy korporativ HTTP proksi.
    egress_proxy: str = ""
    cbu_base_url: str = "https://cbu.uz"
    bank_inbox_dir: str = "/data/import/banks"
    bank_archive_dir: str = "/data/archive/banks"
    telegram_api_base: str = "https://api.telegram.org"

    smtp_host: str = ""
    smtp_port: int = 25
    smtp_from: str = "ugekazna@localhost"
    smtp_to: str = ""
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # 1C: login/parol/manzil/limit — panelda (core.integrations, shifrlangan). Bu yerda faqat
    # serverga xos (A sinfi) qiymatlar: CA fayli va ochiq HTTP'ga vaqtincha ruxsat.
    onec_ca_file: str = "/run/secrets/onec_ca_bundle"
    onec_allow_http: bool = False


    # S5: AI-анализ. Kalit/model/effort — integrations/sysconfig (panel); bu yerda faqat A sinfi.
    ai_provider: Literal["anthropic", "openai_compatible", "fake"] = "anthropic"
    ai_base_url: str = ""
    ai_ca_file: str = "/run/secrets/ai_ca_bundle"
    # compose.ai.yml belgilaydi (AI_EGRESS=1): api internetga chiqadi — proksi majburiy.
    ai_egress: bool = False
    ai_direct_egress: str = ""  # "ack" — proksisiz chiqishga ongli rozilik (host firewall bilan)
    https_proxy: str = ""

    @property
    def smtp_recipients(self) -> list[str]:
        raw = [a.strip() for a in self.smtp_to.split(",") if a.strip()]
        return [a for a in raw if _SMTP_ADDR_RE.match(a)]

    def pg_url(self, role: DbRole) -> str:
        user: str = getattr(self, f"db_{role}_user")
        password: SecretStr = getattr(self, f"db_{role}_password")
        return (
            f"postgresql+psycopg://{quote(user, safe='')}:"
            f"{quote(password.get_secret_value(), safe='')}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        password = quote(self.redis_password.get_secret_value(), safe="")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    def key_bytes(self, name: str) -> bytes:
        if name not in KEY_FIELDS:
            raise ConfigError(f"noma'lum kalit: {name}")
        raw: str = getattr(self, name).get_secret_value()
        try:
            value = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ConfigError(f"{name}: base64 emas") from exc
        if len(value) != 32:
            raise ConfigError(f"{name}: 32 bayt bo'lishi kerak")
        return value

    def problems(self) -> list[str]:
        """Bo'sh ro'yxat — ishga tushish mumkin. Aks holda ilova ishga tushmaydi."""
        out: list[str] = []
        for name in KEY_FIELDS:
            try:
                self.key_bytes(name)
            except ConfigError as exc:
                out.append(str(exc))
        if not self.db_app_password.get_secret_value():
            out.append("db_app_password bo'sh")
        if self.argon2_profile == "fast_test" and self.env != "test":
            out.append("argon2_profile=fast_test faqat test muhitida")
        if self.smtp_host and not self.smtp_recipients:
            out.append("smtp_host berilgan, lekin smtp_to bo'sh")
        raw_recipients = [a.strip() for a in self.smtp_to.split(",") if a.strip()]
        invalid_recipients = [a for a in raw_recipients if not _SMTP_ADDR_RE.match(a)]
        if invalid_recipients:
            out.append(f"smtp_to: yaroqsiz manzil(lar): {', '.join(invalid_recipients)}")
        if self.smtp_password.get_secret_value() and not (self.smtp_starttls or self.smtp_ssl):
            out.append(
                "smtp_password berilgan, lekin na starttls, na ssl yoqilgan "
                "(parol ochiq matnda yuborilmaydi)"
            )
        for name in ("cbu_base_url", "telegram_api_base"):  # token URL yo'lida - faqat TLS
            if not getattr(self, name).startswith("https://"):
                out.append(f"{name} https:// bilan boshlanishi kerak")
        if self.egress_proxy and not self.egress_proxy.startswith(("http://", "https://")):
            out.append("EGRESS_PROXY http:// yoki https:// bilan boshlanishi kerak")
        if self.ai_provider == "fake" and self.env == "prod":
            out.append("AI_PROVIDER=fake faqat dev/test muhitida")
        if self.ai_base_url and not self.ai_base_url.startswith("https://"):
            out.append("AI_BASE_URL https:// bilan boshlanishi kerak")
        if (self.env == "prod" and self.ai_egress and not self.https_proxy
                and self.ai_direct_egress != "ack"):
            out.append("AI_EGRESS: HTTPS_PROXY (EGRESS_PROXY) bo'sh — proksisiz chiqish "
                       "AI_DIRECT_EGRESS=ack bilan tasdiqlanadi")
        if self.env == "prod":
            if not self.base_url.startswith("https://"):
                out.append("base_url https bo'lishi shart")
            if not self.redis_password.get_secret_value():
                out.append("redis_password bo'sh")
            for name in KEY_FIELDS:
                if getattr(self, name).get_secret_value() in TEST_KEYS:
                    out.append(f"{name}: test kaliti prod'da ishlatilmoqda")
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    secrets_dir = SECRETS_DIR if SECRETS_DIR.is_dir() else None
    return Settings(_secrets_dir=secrets_dir)
