"""Deterministik tasodifiy oqimlar: bir xil (seed, kalit) → bir xil qiymatlar.

Har (filial, statya, oy) o'z oqimiga ega — shuning uchun o'tgan oylar ma'lumoti `as_of`
sanasiga bog'liq emas (inkremental qayta yuklash hech narsani o'zgartirmaydi).
"""

from __future__ import annotations

import hashlib
import random


def rnd(seed: int, *parts: object) -> random.Random:
    key = ":".join(str(p) for p in (seed, *parts)).encode()
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))
