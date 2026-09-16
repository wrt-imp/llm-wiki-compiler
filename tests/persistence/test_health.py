"""AOF/RDB health check tests (no Redis, no real tools)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from compiler.persistence import (
    AOFStatus,
    RDBStatus,
    ToolResult,
    aof_target,
    check_aof,
    check_rdb,
    find_aof,
    quarantine,
    repair_aof_copy,
)
from compiler.persistence import health as health_module

from helpers import FakeRunner, write_aof, write_rdb


def test_missing_aof(tmp_path: Path) -> None:
    audit = check_aof(tmp_path)

    assert audit.status is AOFStatus.MISSING
    assert audit.kind == "none"


def test_empty_aof_is_detected_without_calling_the_tool(tmp_path: Path) -> None:
    write_aof(tmp_path, b"")
    runner = FakeRunner()

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.EMPTY
    assert runner.calls == []


def test_healthy_aof(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(**{"redis-check-aof": ToolResult(0, "AOF analyzed: OK")})

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.OK
    assert audit.kind == "dir"
    assert "analyzed" in audit.detail


def test_truncated_aof_is_reported_as_truncated(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **{
            "redis-check-aof": ToolResult(
                1, "AOF analyzed: size=200, ok_up_to=120\nAOF is truncated"
            )
        }
    )

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.TRUNCATED


def test_corrupt_aof_is_reported_as_corrupt(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **{"redis-check-aof": ToolResult(1, "Bad file format reading the append only file")}
    )

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.CORRUPT
    assert audit.status.is_broken is True


def test_unrecognised_tool_rejection_counts_as_corruption(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(**{"redis-check-aof": ToolResult(3, "something strange")})

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.CORRUPT
    assert audit.status.is_broken is True


def test_tool_that_cannot_run_is_reported_as_unverified(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **{"redis-check-aof": ToolResult(1, "redis-check-aof: command not found")}
    )

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.TOOL_FAILED
    assert audit.status.is_unverified is True


def test_missing_check_tool_is_reported(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(**{"redis-check-aof": FileNotFoundError("no tool")})

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.TOOL_MISSING
    assert "not installed" in audit.detail


def test_timing_out_check_tool_is_reported(tmp_path: Path) -> None:
    write_aof(tmp_path)
    runner = FakeRunner(
        **{"redis-check-aof": subprocess.TimeoutExpired(cmd="redis-check-aof", timeout=1)}
    )

    audit = check_aof(tmp_path, runner=runner)

    assert audit.status is AOFStatus.TOOL_FAILED


def test_unreadable_aof_is_reported(tmp_path: Path, monkeypatch) -> None:
    write_aof(tmp_path)

    def raise_permission_error(path):
        raise PermissionError("access denied")

    monkeypatch.setattr(health_module, "file_size", raise_permission_error)

    audit = check_aof(tmp_path, runner=FakeRunner())

    assert audit.status is AOFStatus.UNREADABLE


def test_single_file_layout_is_detected(tmp_path: Path) -> None:
    path = write_aof(tmp_path, b"*1\r\n$4\r\nPING\r\n", layout="file")

    kind, found = find_aof(tmp_path)

    assert (kind, found) == ("file", path)
    assert aof_target(kind, found) == path


def test_directory_layout_prefers_the_manifest(tmp_path: Path) -> None:
    directory = write_aof(tmp_path)

    kind, found = find_aof(tmp_path)

    assert (kind, found) == ("dir", directory)
    assert aof_target(kind, found).name == "appendonly.aof.manifest"


def test_rdb_states(tmp_path: Path) -> None:
    assert check_rdb(tmp_path).status is RDBStatus.MISSING

    write_rdb(tmp_path, b"")
    assert check_rdb(tmp_path).status is RDBStatus.EMPTY

    write_rdb(tmp_path, b"REDIS0011")
    runner = FakeRunner(**{"redis-check-rdb": ToolResult(0, "RDB looks OK")})
    assert check_rdb(tmp_path, runner=runner).status is RDBStatus.OK

    broken = FakeRunner(**{"redis-check-rdb": ToolResult(1, "Wrong signature")})
    assert check_rdb(tmp_path, runner=broken).status is RDBStatus.CORRUPT

    missing = FakeRunner(**{"redis-check-rdb": FileNotFoundError("nope")})
    assert check_rdb(tmp_path, runner=missing).status is RDBStatus.TOOL_MISSING


def test_quarantine_keeps_the_original_bytes(tmp_path: Path) -> None:
    path = write_aof(tmp_path, b"broken-aof-content", layout="file")

    moved = quarantine(path, tmp_path / "corrupted", timestamp="20260916-230000")

    assert moved.name == "appendonly.aof.corrupted.20260916-230000"
    assert moved.read_bytes() == b"broken-aof-content"
    assert not path.exists()


def test_quarantine_never_overwrites(tmp_path: Path) -> None:
    corrupted = tmp_path / "corrupted"
    first = write_aof(tmp_path, b"first", layout="file")
    moved_first = quarantine(first, corrupted, timestamp="stamp")

    second = write_aof(tmp_path, b"second", layout="file")
    moved_second = quarantine(second, corrupted, timestamp="stamp")

    assert moved_first != moved_second
    assert moved_first.read_bytes() == b"first"
    assert moved_second.read_bytes() == b"second"


def test_repair_uses_a_copy_and_verifies_it(tmp_path: Path) -> None:
    quarantined = write_aof(tmp_path / "corrupted", b"broken", layout="file")
    runner = FakeRunner(
        **{
            "redis-check-aof": ToolResult(0, "AOF analyzed: OK"),
        }
    )

    repaired = repair_aof_copy(
        "file", quarantined, tmp_path / "repaired.aof", runner=runner
    )

    assert repaired is not None
    assert repaired.read_bytes() == b"broken"
    assert quarantined.read_bytes() == b"broken"  # original untouched
    assert runner.calls[0][1] == "--fix"
    assert runner.tools_called == ["redis-check-aof", "redis-check-aof"]


def test_repair_is_rejected_when_verification_fails(tmp_path: Path) -> None:
    quarantined = write_aof(tmp_path / "corrupted", b"broken", layout="file")
    runner = FakeRunner(**{"redis-check-aof": ToolResult(1, "still broken")})

    assert (
        repair_aof_copy(
            "file", quarantined, tmp_path / "repaired.aof", runner=runner
        )
        is None
    )
    assert quarantined.read_bytes() == b"broken"


def test_default_runner_is_used_when_none_is_given(
    tmp_path: Path, monkeypatch
) -> None:
    write_aof(tmp_path)
    seen = {}

    def fake_runner(command):
        seen["command"] = list(command)
        return ToolResult(0, "AOF analyzed: OK")

    monkeypatch.setattr(
        health_module, "subprocess_runner", lambda timeout=30.0: fake_runner
    )

    audit = check_aof(tmp_path)

    assert audit.status is AOFStatus.OK
    assert seen["command"][0] == "redis-check-aof"
