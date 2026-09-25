"""Qayta urinishlar (spec 5.2, TZ 8): 3 ta, pauza 30 s -> 2 min -> 8 min, +-jitter.

`sleep` va `rng` injeksiya qilinadi -- testlar haqiqatda uxlamaydi.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence

from sqlalchemy.exc import OperationalError

from app.etl.types import ConnectorUnavailableError

RETRY_DELAYS: tuple[float, ...] = (30.0, 120.0, 480.0)
# Faqat vaqtinchalik xatolar. Ma'lumot/format xatosi (ValueError) qayta urinilmaydi.
RETRYABLE: tuple[type[BaseException], ...] = (
    ConnectionError, TimeoutError, OSError, OperationalError, ConnectorUnavailableError,
)


def call_with_retries[T](
    fn: Callable[[], T],
    *,
    delays: Sequence[float] = RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
    jitter: float = 0.1,
    rng: Callable[[], float] = random.random,  # kriptografik emas, jitter uchun
    retry_on: tuple[type[BaseException], ...] = RETRYABLE,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    attempt = 0
    while True:
        try:
            return fn()
        except retry_on as exc:
            if attempt >= len(delays):
                raise
            pause = delays[attempt] * (1 + jitter * (2 * rng() - 1))
            if on_retry is not None:
                on_retry(attempt + 1, exc, pause)
            sleep(pause)
            attempt += 1
