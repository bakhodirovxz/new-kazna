from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app import worker
from app.core.config import get_settings
from app.core.db import get_engine
from app.etl.notify import LogNotifier
from app.etl.quality import tolerances
from app.etl.runner import compute_window
from app.etl.types import Mode

Put = Callable[[str, object], None]


def _hm(job: Any) -> tuple[str, str]:
    fields = {f.name: str(f) for f in job.trigger.fields}
    return fields["hour"], fields["minute"]


def _scheduler() -> Any:
    return worker.build_scheduler(get_settings().model_copy(update={"env": "dev"}), LogNotifier())


def test_panel_cron_change_is_applied_without_restart(setting: Put) -> None:
    scheduler = _scheduler()
    assert _hm(scheduler.get_job("partitions")) == ("3", "30")
    assert worker.sync_schedules(scheduler) == []
    setting("maintenance.partitions_cron", "15 2 * * *")
    setting("etl.synthetic_cron", "30 1 * * *")
    assert sorted(worker.sync_schedules(scheduler)) == ["etl_synthetic_full", "partitions"]
    assert _hm(scheduler.get_job("partitions")) == ("2", "15")
    assert _hm(scheduler.get_job("etl_synthetic_full")) == ("1", "30")
    assert worker.sync_schedules(scheduler) == []


def test_invalid_panel_cron_keeps_default(setting: Put) -> None:
    setting("maintenance.cleanup_cron", "every night")
    assert _hm(_scheduler().get_job("cleanup")) == ("4", "0")


def test_scheduler_has_sync_job() -> None:
    assert _scheduler().get_job("schedules") is not None


def test_incremental_lookback_is_a_parameter() -> None:
    window = compute_window(Mode.INCREMENTAL, today=date(2026, 9, 24),
                            history_start=date(2024, 1, 1),
                            last_watermark=datetime(2026, 9, 20, 3, tzinfo=UTC), lookback_days=30)
    assert window.date_from == date(2026, 8, 21)


def test_quality_tolerances_follow_panel(setting: Put) -> None:
    with get_engine("app").connect() as conn:
        assert tolerances(conn) == (Decimal("0.001"), Decimal("0.01"))
    setting("quality.control_tolerance", 0.005)
    with get_engine("app").connect() as conn:
        assert tolerances(conn) == (Decimal("0.005"), Decimal("0.01"))
