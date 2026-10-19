from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app import cli, worker
from app.core.config import get_settings
from app.core.db import get_engine
from app.dwh import builds, partitions
from app.dwh.freshness import freshness
from app.etl.connectors import make_connector
from app.etl.db import etl_transaction
from app.etl.runner import RunResult
from app.maintenance import cleanup_staging
from tests.etl_helpers import (
    TEST_AS_OF,
    ListConnector,
    RecordingNotifier,
    branch_row,
    cash_row,
    new_source,
    new_tag,
    open_run,
    purge_source,
)

JOBS = {"etl_synthetic_full", "etl_requests", "partitions", "cleanup", "freshness", "heartbeat"}


@pytest.fixture
def source() -> Iterator[str]:
    name = new_source()
    with etl_transaction() as conn:  # boshqa testlardan qolgan so'rovlar bajarilmasin
        conn.execute(text("UPDATE core.etl_requests SET status = 'failed' "
                          "WHERE status = 'pending'"))
    yield name
    purge_source(name)


def _request(source: str) -> int:
    with get_engine("app").begin() as conn:
        return int(conn.execute(text(
            "INSERT INTO core.etl_requests (source, mode, requested_by) "
            "VALUES (:s, 'full', 1) RETURNING id"), {"s": source}).scalar_one())


def _request_row(request_id: int) -> Any:
    with etl_transaction() as conn:
        return conn.execute(text("SELECT status, run_id, error FROM core.etl_requests "
                                 "WHERE id = :i"), {"i": request_id}).one()


def _rows() -> dict[str, list[dict[str, Any]]]:
    b = branch_row(new_tag())
    return {"dim_branch": [b], "fact_cashflow": [cash_row("w1", 20260805, b["code"], 10)]}


def test_scheduler_jobs_dev_and_prod() -> None:
    notifier = RecordingNotifier()
    dev = worker.build_scheduler(get_settings().model_copy(update={"env": "dev"}), notifier)
    assert {j.id for j in dev.get_jobs()} == JOBS
    prod = worker.build_scheduler(get_settings().model_copy(update={"env": "prod"}), notifier)
    assert {j.id for j in prod.get_jobs()} == JOBS - {"etl_synthetic_full"}


def test_process_requests_runs_pending_request(source: str) -> None:
    request_id = _request(source)
    done = worker.process_requests(RecordingNotifier(),
                                   factory=lambda s: ListConnector(s, _rows()), today=TEST_AS_OF)
    assert done == 1
    status, run_id, error = _request_row(request_id)
    assert (status, error) == ("done", None) and run_id is not None
    with etl_transaction() as conn:
        run_status = conn.execute(text("SELECT status FROM core.etl_run WHERE id = :r"),
                                  {"r": run_id}).scalar_one()
    assert run_status == "success"


def test_process_requests_leaves_pending_when_busy(source: str) -> None:
    request_id = _request(source)
    with get_engine("etl").connect() as raw:
        other = raw.execution_options(isolation_level="AUTOCOMMIT")
        other.execute(text("SELECT pg_advisory_lock(hashtext('ugk_etl'))"))
        try:
            assert worker.process_requests(
                RecordingNotifier(), factory=lambda s: ListConnector(s, _rows()),
                today=TEST_AS_OF) == 0
        finally:
            other.execute(text("SELECT pg_advisory_unlock(hashtext('ugk_etl'))"))
    assert _request_row(request_id)[0] == "pending"


def test_process_requests_unknown_source_fails(source: str) -> None:
    request_id = _request(source)

    def factory(name: str) -> ListConnector:
        raise ValueError(f"noma'lum manba: {name}")

    assert worker.process_requests(RecordingNotifier(), factory=factory) == 1
    status, run_id, error = _request_row(request_id)
    assert status == "failed" and run_id is None and error == "ValueError: noma'lum manba"


def test_process_requests_prod_forbids_synthetic(source: str) -> None:
    request_id = _request(source)
    prod = get_settings().model_copy(update={"env": "prod"})
    assert worker.process_requests(
        RecordingNotifier(), factory=lambda s: make_connector("synthetic", prod)) == 1
    status, run_id, error = _request_row(request_id)
    assert status == "failed" and run_id is None
    assert error == "ConfigError: manba bu muhitda taqiqlangan"


class _SpyLog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def error(self, event: str, **kw: Any) -> None:
        self.calls.append((event, kw))

    def info(self, event: str, **kw: Any) -> None:
        self.calls.append((event, kw))


class _BoomRunner:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def run(self) -> RunResult:
        raise ValueError("secret 123456789")


def test_escaping_run_exceptions_are_not_leaked(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SpyLog()
    monkeypatch.setattr(worker, "log", spy)
    monkeypatch.setattr(worker, "Runner", _BoomRunner)
    request_id = _request(source)
    worker.process_requests(RecordingNotifier(), factory=lambda s: ListConnector(s, {}))
    assert worker.run_etl_job("file", worker.Mode.FULL, RecordingNotifier()) is None
    worker._guarded("boom", lambda: (_ for _ in ()).throw(ValueError("secret 123456789")))()
    assert len(spy.calls) == 3
    assert "123456789" not in repr(spy.calls) and "exc_info" not in repr(spy.calls)
    status, _, error = _request_row(request_id)
    assert (status, error) == ("failed", "ValueError")


def test_maintain_partitions_creates_ahead_and_drops_old() -> None:
    with etl_transaction() as conn:
        partitions.ensure_partitions(conn, "fact_stock", date(2017, 1, 1), date(2017, 12, 31))
    result = worker.maintain_partitions(date(2033, 5, 10))
    with etl_transaction() as conn:
        cash = set(partitions.list_partitions(conn, "fact_cashflow"))
        stock = set(partitions.list_partitions(conn, "fact_stock"))
    assert {"fact_cashflow_p203305", "fact_cashflow_p203308"} <= cash
    assert "fact_stock_p2017" not in stock
    assert result["dropped"] >= 1
    with get_engine("app").connect() as conn:
        audited = conn.execute(text("SELECT count(*) FROM core.audit_log "
                                    "WHERE action = 'dwh.partitions.dropped'")).scalar_one()
    assert audited >= 1


def test_check_freshness_notifies_once_per_stale_period(
    monkeypatch: pytest.MonkeyPatch, synthetic_run: RunResult
) -> None:
    monkeypatch.setattr(worker, "_alerted_for", worker._NEVER)
    with get_engine("app").connect() as conn:
        last = freshness(conn, datetime.now(UTC)).last_success_at
    assert last is not None
    notifier = RecordingNotifier()
    assert worker.check_freshness(notifier, now=last + timedelta(hours=7)) is True
    assert worker.check_freshness(notifier, now=last + timedelta(hours=8)) is True
    assert notifier.kinds == ["stale_data"]
    assert worker.check_freshness(notifier, now=last + timedelta(hours=1)) is False
    assert worker.check_freshness(notifier, now=last + timedelta(hours=9)) is True
    assert notifier.kinds == ["stale_data", "stale_data"]


def test_cleanup_staging_removes_old_loads(source: str) -> None:
    run_id = open_run(source)
    with etl_transaction() as conn:
        conn.execute(text("INSERT INTO stg.rows (load_id, target, payload) "
                          "VALUES (:l, 'dim_item', '{}'::jsonb)"), {"l": run_id})
        conn.execute(text("UPDATE core.etl_run SET started_at = now() - interval '10 days', "
                          "status = 'failed' WHERE id = :l"), {"l": run_id})
    assert cleanup_staging(7) >= 1
    with etl_transaction() as conn:
        left = conn.execute(text("SELECT count(*) FROM stg.rows WHERE load_id = :l"),
                            {"l": run_id}).scalar_one()
    assert left == 0


def test_heartbeat(tmp_path: Path) -> None:
    path = tmp_path / "hb"
    worker.heartbeat(path)
    assert path.exists()


def test_cli_etl_run_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["etl-run", "--source", "oracle", "--mode", "full"]) == 2
    # etl_file_dir (/data/inbox) test konteynerida yo'q → manba mavjud emas, qayta urinishsiz.
    assert cli.main(["etl-run", "--source", "file", "--mode", "full", "--no-retry"]) == 1
    assert "status=failed" in capsys.readouterr().out


def test_cli_rollback_build(published_synthetic: int) -> None:
    with etl_transaction() as conn:
        newer = builds.create_build(conn, None)
        builds.mark_ready(conn, newer)
        builds.publish(conn, newer, keep=3)
    assert cli.main(["rollback-build"]) == 0
    with etl_transaction() as conn:
        assert builds.active_build(conn) == published_synthetic
    assert cli.main(["rollback-build", "--build", "999999999"]) == 1
