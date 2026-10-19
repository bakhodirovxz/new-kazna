"""DB ulanishlari (rol bo'yicha), sessiyalar va RLS konteksti.

Sinxron SQLAlchemy: endpointlar `def`, Starlette ularni threadpool'da bajaradi.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DbRole, get_settings


@lru_cache(maxsize=3)
def get_engine(role: DbRole = "app") -> Engine:
    settings = get_settings()
    if role == "app":
        timeout = settings.db_statement_timeout_ms
    elif role == "etl":
        timeout = settings.etl_statement_timeout_ms
    else:
        timeout = 0
    options = (
        f"-c statement_timeout={timeout} "
        "-c idle_in_transaction_session_timeout=60000 -c TimeZone=UTC"
    )
    return create_engine(
        settings.pg_url(role),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={"options": options, "application_name": f"ugekazna-{role}"},
        # ETL staging qatorlari (INN, hisob raqami va h.k.) bog'langan parametrlarda
        # yuradi — SQLAlchemy istisnolari ularni logga aks ettirmasin (fix r1, I1).
        hide_parameters=role == "etl",
    )


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine("app"), autoflush=False, expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: so'rov uchun bitta sessiya, oxirida commit yoki rollback."""
    db = new_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# scope="function": commit/rollback endpoint qaytgach, javob YUBORILISHIDAN OLDIN bajariladi
# (standart "request" scope'da teardown javobdan keyin ishlaydi — read-your-writes buziladi).
# Hamma joyda shu `DB`dan foydalaning: boshqa scope'dagi `Depends(get_db)` ikkinchi sessiya beradi.
DB = Annotated[Session, Depends(get_db, scope="function")]


def apply_rls(db: Session, branch_ids: frozenset[int] | None) -> None:
    """Joriy tranzaksiya uchun filial doirasini o'rnatadi (SET LOCAL).

    `None` — barcha filiallar (scope_all). Bo'sh to'plam — hech narsa ko'rinmaydi.
    """
    ids = "{" + ",".join(str(int(b)) for b in sorted(branch_ids or ())) + "}"
    db.execute(
        text(
            "SELECT set_config('app.scope_all', :scope_all, true), "
            "set_config('app.branch_ids', :ids, true)"
        ),
        {"scope_all": "on" if branch_ids is None else "off", "ids": ids},
    )
