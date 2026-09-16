"""Startup recovery tests: the fifteen scenarios, without a real Redis."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from compiler.persistence import (
    ACTION_FAILED,
    ACTION_NONE,
    ACTION_QUARANTINED,
    ACTION_UNVERIFIED,
    SOURCE_AOF,
    SOURCE_AOF_REPAIRED,
    SOURCE_EMPTY,
    SOURCE_RDB,
    SOURCE_UNKNOWN,
    ToolResult,
    PersistenceManager,
)

from helpers import FakeRunner, write_aof, write_rdb

OK_AOF = {"redis-check-aof": ToolResult(0, "AOF analyzed: OK")}
CORRUPT_AOF = {"redis-check-aof": ToolResult(1, "Bad file format reading the append only file")}
TRUNCATED_AOF = {"redis-check-aof": ToolResult(1, "AOF is truncated")}
OK_RDB = {"redis-check-rdb": ToolResult(0, "RDB looks OK")}


def manager(data_dir: Path, **options) -> PersistenceManager:
    options.setdefault("runner", FakeRunner(**OK_RDB, **OK_AOF))
    return PersistenceManager(data_dir, **options)


def test_healthy_aof_and_rdb_use_the_aof(tmp_path: Path) -> None:
    write_aof(tmp_path)
    write_rdb(tmp_path)

    report = manager(tmp_path).ensure(timestamp="20260916-230000")

    assert report.aof is not None and report.aof.status.value == "ok"
    assert report.rdb is not None and report.rdb.status.value == "ok"
    assert report.source == SOURCE_AOF
    assert report.action == ACTION_NONE
    assert report.usable is True
    assert report.warnings == []
    assert not (tmp_path / "corrupted").exists() or not list(
        (tmp_path / "corrupted").iterdir()
    )


def test_missing_aof_falls_back_to_the_rdb(tmp_path: Path) -> None:
    write_rdb(tmp_path)

    report = manager(tmp_path).ensure()

    assert report.aof is not None and report.aof.status.value == "missing"
    assert report.source == SOURCE_RDB
    assert report.usable is True


def test_empty_aof_falls_back_to_the_rdb(tmp_path: Path) -> None:
    write_aof(tmp_path, b"")
    write_rdb(tmp_path)

    report = manager(tmp_path).ensure()

    assert report.aof is not None and report.aof.status.value == "empty"
    assert report.source == SOURCE_RDB


def test_truncated_aof_is_quarantined_and_rdb_is_used(tmp_path: Path) -> None:
    write_aof(tmp_path, b"*2\r\n$3\r\nSET\r\n$4\r\nde", layout="file")
    write_rdb(tmp_path)
    runner = FakeRunner(**OK_RDB, **TRUNCATED_AOF)

    report = PersistenceManager(tmp_path, runner=runner).ensure(timestamp="20260916-230000")

    assert report.action == ACTION_QUARANTINED
    assert report.source == SOURCE_RDB
    assert report.usable is True
    assert report.quarantine_path is not None
    assert report.quarantine_path.read_bytes() == b"*2\r\n$3\r\nSET\r\n$4\r\nde"
    assert report.quarantine_path.name == "appendonly.aof.corrupted.20260916-230000"
    assert not (tmp_path / "appendonly.aof").exists()


def test_corrupt_aof_keeps_the_original_and_warns_about_data_loss(
    tmp_path: Path, caplog
) -> None:
    write_aof(tmp_path, b"GARBAGE", layout="file")
    write_rdb(tmp_path)
    runner = FakeRunner(**OK_RDB, **CORRUPT_AOF)

    with caplog.at_level(logging.WARNING, logger="compiler.persistence"):
        report = PersistenceManager(tmp_path, runner=runner).ensure()

    assert report.source == SOURCE_RDB
    assert report.usable is True
    assert report.quarantine_path is not None and report.quarantine_path.exists()
    messages = "\n".join(record.message for record in caplog.records)
    assert "Redis AOF is corrupted" in messages
    assert "Original AOF has been moved to" in messages
    assert "Falling back to the latest RDB snapshot" in messages
    assert "Data written after the latest RDB snapshot may be lost." in messages
    assert any("may be lost" in warning for warning in report.warnings)


def test_missing_check_tool_does_not_stop_startup(tmp_path: Path, caplog) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **OK_RDB, **{"redis-check-aof": FileNotFoundError("not installed")}
    )

    with caplog.at_level(logging.WARNING, logger="compiler.persistence"):
        report = PersistenceManager(tmp_path, runner=runner).ensure()

    assert report.action == ACTION_UNVERIFIED
    assert report.source == SOURCE_UNKNOWN
    assert report.usable is True
    assert any("validation skipped" in warning for warning in report.warnings)


def test_missing_check_tool_fails_only_in_strict_mode(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **OK_RDB, **{"redis-check-aof": FileNotFoundError("not installed")}
    )

    report = PersistenceManager(tmp_path, runner=runner, strict=True).ensure()

    assert report.usable is False
    assert report.action == ACTION_UNVERIFIED


def test_failing_check_tool_does_not_stop_startup(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **OK_RDB,
        **{"redis-check-aof": subprocess.TimeoutExpired(cmd="tool", timeout=1)},
    )

    report = PersistenceManager(tmp_path, runner=runner).ensure()

    assert report.action == ACTION_UNVERIFIED
    assert report.usable is True


def test_corrupt_aof_without_rdb_still_returns_a_report(tmp_path: Path) -> None:
    write_aof(tmp_path, b"GARBAGE", layout="file")
    runner = FakeRunner(**OK_RDB, **CORRUPT_AOF)

    report = PersistenceManager(tmp_path, runner=runner).ensure()

    assert report.usable is True
    assert report.source == SOURCE_EMPTY
    assert any("no usable RDB snapshot" in warning for warning in report.warnings)
    assert report.quarantine_path is not None and report.quarantine_path.exists()


def test_successful_repair_puts_a_verified_copy_back(tmp_path: Path) -> None:
    write_aof(tmp_path, b"BROKEN", layout="file")
    write_rdb(tmp_path)

    class RepairRunner:
        """The first AOF check fails; --fix and the verification succeed."""

        def __init__(self) -> None:
            self.calls = []
            self.aof_checks = 0

        def __call__(self, command):
            call = [str(item) for item in command]
            self.calls.append(call)
            tool = Path(call[0]).name
            if tool == "redis-check-rdb":
                return ToolResult(0, "RDB looks OK")
            if "--fix" in call:
                return ToolResult(0, "Successfully truncated AOF")
            self.aof_checks += 1
            if self.aof_checks == 1:
                return ToolResult(1, "Bad file format")
            return ToolResult(0, "AOF analyzed: OK")

    report = PersistenceManager(tmp_path, runner=RepairRunner()).ensure(
        timestamp="20260916-230000"
    )

    assert report.source == SOURCE_AOF_REPAIRED
    assert report.repaired_path is not None
    assert (tmp_path / "appendonly.aof").read_bytes() == b"BROKEN"
    assert report.quarantine_path is not None
    assert report.quarantine_path.read_bytes() == b"BROKEN"


def test_unexpected_error_never_raises(tmp_path: Path, monkeypatch) -> None:
    write_aof(tmp_path)

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("compiler.persistence.manager.check_aof", explode)

    report = PersistenceManager(tmp_path).ensure()

    assert report.usable is False
    assert report.action == ACTION_FAILED
    assert any("boom" in warning for warning in report.warnings)


def test_unwritable_data_dir_is_reported(tmp_path: Path, monkeypatch) -> None:
    def fail_mkdir(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    report = PersistenceManager(tmp_path / "redis").ensure()

    assert report.usable is False
    assert report.action == ACTION_FAILED
    assert any("permission" in warning.lower() or "denied" in warning for warning in report.warnings)


def test_report_lines_cover_the_required_facts(tmp_path: Path) -> None:
    write_aof(tmp_path, b"GARBAGE", layout="file")
    write_rdb(tmp_path)
    runner = FakeRunner(**OK_RDB, **CORRUPT_AOF)

    report = PersistenceManager(tmp_path, runner=runner).ensure()
    text = "\n".join(report.log_lines())

    assert "Redis persistence check started" in text          # what ran
    assert "AOF file check started" in text                   # which file
    assert "Redis AOF is corrupted." in text                  # why
    assert "Original AOF has been moved to" in text           # what we did
    assert "Falling back to the latest RDB snapshot" in text  # recovery
    assert "may be lost" in text                              # data loss risk
    assert report.source == SOURCE_RDB                        # which source


def test_two_runs_report_the_same_outcome(tmp_path: Path) -> None:
    write_aof(tmp_path, b"GARBAGE", layout="file")
    write_rdb(tmp_path)

    first = PersistenceManager(tmp_path, runner=FakeRunner(**OK_RDB, **CORRUPT_AOF)).ensure(
        timestamp="20260916-230000"
    )
    second = PersistenceManager(tmp_path, runner=FakeRunner(**OK_RDB)).ensure(
        timestamp="20260916-230001"
    )

    assert first.source == SOURCE_RDB
    assert second.source == SOURCE_RDB  # AOF is gone now, RDB is still used
    assert second.usable is True
