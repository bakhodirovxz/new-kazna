"""So'rov haqidagi audit uchun kerakli ma'lumotlar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

UA_MAX = 512


@dataclass(frozen=True, slots=True)
class ClientMeta:
    ip: str | None
    ua: str | None
    request_id: str | None


def client_meta(request: Request) -> ClientMeta:
    ua = request.headers.get("user-agent")
    return ClientMeta(
        ip=request.client.host if request.client else None,
        ua=ua[:UA_MAX] if ua else None,
        request_id=getattr(request.state, "request_id", None),
    )


Meta = Annotated[ClientMeta, Depends(client_meta)]
