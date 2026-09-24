"""I1 (fix round 1): ikkita administrator bir vaqtda bir-birini bloklasa (X → Y, Y → X),
`assert_admin_remains`dagi `pg_advisory_xact_lock` bu poyga holatini ketma-ketlashtirishi
kerak — faqat BITTASI muvaffaqiyatli bo'lishi, ikkinchisi `last_admin` bilan rad etilishi,
va kamida bitta administrator FAOL qolishi kerak (READ COMMITTED ostida, qulfsiz, ikkalasi
ham "hali kamida bitta admin bor" deb committing bo'lib, nol administrator qolib ketishi
mumkin edi)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from sqlalchemy import select, update

from app.admin import service as admin_service
from app.auth.context import AuthContext
from app.auth.models import User
from app.auth.permissions import Perm
from app.core.db import new_session
from app.core.errors import ConflictError
from app.core.request_meta import ClientMeta
from tests.helpers import SeedUser


def _full_admin_ctx(user_id: int, username: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        username=username,
        full_name="A",
        role_code="admin",
        permissions=frozenset(p.value for p in Perm),
        branch_ids=None,
        session_id=uuid.uuid4(),
    )


def test_concurrent_mutual_block_leaves_exactly_one_admin_active(
    make_user: Callable[..., SeedUser],
) -> None:
    admin_a = make_user("admin")
    admin_b = make_user("admin")
    with new_session() as s:
        s.execute(
            update(User).where(User.id.not_in([admin_a.id, admin_b.id])).values(is_active=False)
        )
        s.commit()

    meta = ClientMeta(ip=None, ua=None, request_id=None)
    outcomes: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def _block(key: str, actor: SeedUser, target_id: int) -> None:
        db = new_session()
        try:
            ctx = _full_admin_ctx(actor.id, actor.username)
            barrier.wait(timeout=10)
            admin_service.set_active(db, ctx, target_id, False, meta)
            db.commit()
            outcomes[key] = "ok"
        except ConflictError as exc:
            db.rollback()
            outcomes[key] = exc.code
        finally:
            db.close()

    t1 = threading.Thread(target=_block, args=("a", admin_a, admin_b.id))
    t2 = threading.Thread(target=_block, args=("b", admin_b, admin_a.id))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not t1.is_alive() and not t2.is_alive(), "thread(lar) tugallanmadi"
    assert set(outcomes) == {"a", "b"}
    assert set(outcomes.values()) == {"ok", "last_admin"}

    with new_session() as s:
        active_admins = s.execute(
            select(User.id).where(
                User.id.in_([admin_a.id, admin_b.id]), User.is_active.is_(True)
            )
        ).scalars().all()
    assert len(active_admins) == 1
