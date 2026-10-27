"""«Проверить подключение» (U8): `/payments` (bugun, limit=1). Faqat xavfsiz kod qaytadi."""

from __future__ import annotations

import httpx

from app.core.config import ConfigError
from app.core.db import get_engine
from app.core.integrations import configured
from app.dwh.dates import today_tashkent
from app.dwh.reference import current_setting
from app.etl.onec.client import (
    OneCCaError,
    OneCClient,
    OneCConfig,
    OneCError,
    OneCUnavailableError,
)
from app.etl.onec.models import PaymentsResponse, parse

_TRANSPORT: httpx.BaseTransport | None = None  # testlarda MockTransport


def onec_probe() -> str:
    with get_engine("etl").connect() as conn:
        if not configured(conn, "onec"):
            return "not_configured"
        config = OneCConfig.load(conn)
        orgs = current_setting(conn, "onec.orgs")
    today = today_tashkent().strftime("%Y%m%d")
    body: dict[str, object] = {"date_from": today, "date_to": today, "limit": 1}
    if orgs:
        body["org_uid"] = orgs[0]["org_uid"]
    try:
        client = OneCClient(config, transport=_TRANSPORT)
    except OneCCaError:
        return "ca_invalid"
    except ConfigError:
        return "insecure_refused"  # http:// taqiqlangan yoki manzil yaroqsiz
    try:
        parse(PaymentsResponse, client.post("/payments", body), "/payments")
    except (OneCError, OneCUnavailableError) as exc:
        return exc.code
    finally:
        client.close()
    return "ok"
