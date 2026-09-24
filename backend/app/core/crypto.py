"""AES-256-GCM ustun shifrlash, envelope kalitlar, blind index (spec 3.5).

Shifrmatn: 0x01 | key_version (2B) | nonce (12B) | ciphertext | tag (16B).
AAD maqsad va joyni bog'laydi: shifrmatnni boshqa ustun/qatorga ko'chirib bo'lmaydi.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap

FORMAT_V1 = 1
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
HEADER_BYTES = 1 + 2 + NONCE_BYTES


class Purpose(StrEnum):
    PII = "pii"
    BANK = "bank"
    MFA = "mfa"
    INTEGRATION = "integration_creds"
    AUDIT = "audit_meta"


class CryptoError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _aad(purpose: str, aad: str) -> bytes:
    return f"ugk|{purpose}|{aad}".encode()


def blob_version(blob: bytes) -> int:
    return int.from_bytes(blob[1:3], "big")


@dataclass(frozen=True, slots=True)
class Keyring:
    keys: Mapping[tuple[str, int], bytes]
    active: Mapping[str, int]

    def encrypt(self, purpose: Purpose, plaintext: bytes, aad: str) -> bytes:
        version = self.active.get(purpose)
        if version is None:
            raise CryptoError("no_active_key")
        nonce = os.urandom(NONCE_BYTES)
        sealed = AESGCM(self.keys[(purpose, version)]).encrypt(nonce, plaintext, _aad(purpose, aad))
        return bytes([FORMAT_V1]) + version.to_bytes(2, "big") + nonce + sealed

    def decrypt(self, purpose: Purpose, blob: bytes, aad: str) -> bytes:
        if len(blob) < HEADER_BYTES + TAG_BYTES or blob[0] != FORMAT_V1:
            raise CryptoError("bad_format")
        key = self.keys.get((purpose, blob_version(blob)))
        if key is None:
            raise CryptoError("unknown_key_version")
        try:
            return AESGCM(key).decrypt(
                blob[3:HEADER_BYTES], blob[HEADER_BYTES:], _aad(purpose, aad)
            )
        except InvalidTag as exc:
            raise CryptoError("integrity") from exc


def new_dek() -> bytes:
    return os.urandom(KEY_BYTES)


def wrap_key(kek: bytes, dek: bytes) -> bytes:
    """RFC 3394 AES Key Wrap."""
    return aes_key_wrap(kek, dek)


def unwrap_key(kek: bytes, wrapped: bytes) -> bytes:
    try:
        return aes_key_unwrap(kek, wrapped)
    except InvalidUnwrap as exc:
        raise CryptoError("unwrap_failed") from exc


def normalize_for_index(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def blind_index(key: bytes, purpose: str, value: str) -> bytes:
    """Shifrlangan maydon bo'yicha aniq qidiruv uchun HMAC-SHA256."""
    message = f"{purpose}|{normalize_for_index(value)}".encode()
    return hmac.new(key, message, hashlib.sha256).digest()


def keyed_hash(key: bytes, label: str, value: str) -> bytes:
    return hmac.new(key, f"{label}|{value}".encode(), hashlib.sha256).digest()
