"""Konfiguratsiya: muhit o'zgaruvchilari + Docker secrets (/run/secrets).

Ustuvorlik: konstruktor argumentlari > env > /run/secrets. Kodda hech qanday sir yo'q.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import SecretStr
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


class ConfigError(RuntimeError):
    """Xavfli yoki to'liq bo'lmagan konfiguratsiya."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    env: Literal["dev", "test", "prod"] = "dev"
    base_url: str = "https://localhost"
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
    db_pool_size: int = 10
    db_statement_timeout_ms: int = 5000

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")

    master_kek: SecretStr = SecretStr("")
    blind_index_key: SecretStr = SecretStr("")
    session_pepper: SecretStr = SecretStr("")

    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    password_max_age_days: int = 90
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

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
