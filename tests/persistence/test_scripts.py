"""The shell script itself: quarantine, fallback and startup (with fake tools)."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import (
    bash_path,
    run_script,
    server_arguments,
    write_aof,
    write_fake_tools,
    write_rdb,
)

pytestmark = pytest.mark.skipif(
    bash_path() is None, reason="bash is not available on this machine"
)


def test_healthy_aof_starts_redis_with_aof(tmp_path: Path) -> None:
    data = tmp_path / "data"
    bin_dir = write_fake_tools(tmp_path / "bin", aof_check_ok=True)
    write_aof(data)
    write_rdb(data)

    result = run_script(data, bin_dir=bin_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AOF file check passed" in result.stdout
    assert "Redis started successfully using AOF" in result.stdout
    assert "--appendonly yes" in server_arguments(bin_dir)
    assert not list((data / "corrupted").iterdir())


def test_corrupt_aof_is_quarantined_and_rdb_is_used(tmp_path: Path) -> None:
    data = tmp_path / "data"
    bin_dir = write_fake_tools(
        tmp_path / "bin", aof_check_ok=False, aof_fix_ok=False
    )
    aof = write_aof(data, b"GARBAGE-AOF", layout="file")
    write_rdb(data)

    result = run_script(data, bin_dir=bin_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    for expected in (
        "Redis AOF is corrupted.",
        "Original AOF has been moved to",
        "Falling back to the latest RDB snapshot",
        "Data written after the latest RDB snapshot may be lost.",
        "Redis started successfully using RDB",
    ):
        assert expected in output
    quarantined = list((data / "corrupted").iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"GARBAGE-AOF"
    assert not aof.exists()


def test_successful_repair_keeps_the_original(tmp_path: Path) -> None:
    data = tmp_path / "data"
    bin_dir = write_fake_tools(tmp_path / "bin", aof_check_ok=False, aof_fix_ok=True)
    write_aof(data, b"BROKEN-AOF", layout="file")
    write_rdb(data)

    result = run_script(data, bin_dir=bin_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Repaired AOF verified" in result.stdout + result.stderr
    quarantined = list((data / "corrupted").iterdir())
    assert quarantined and quarantined[0].read_bytes() == b"BROKEN-AOF"
    assert (data / "appendonly.aof").exists()


def test_missing_check_tool_does_not_block_startup(tmp_path: Path) -> None:
    data = tmp_path / "data"
    bin_dir = write_fake_tools(tmp_path / "bin", include_aof_tool=False)
    write_aof(data)
    write_rdb(data)

    result = run_script(data, bin_dir=bin_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "redis-check-aof not found" in output
    assert "Redis started successfully" in output


def test_running_twice_is_idempotent(tmp_path: Path) -> None:
    data = tmp_path / "data"
    bin_dir = write_fake_tools(tmp_path / "bin")
    write_aof(data)
    write_rdb(data)

    first = run_script(data, bin_dir=bin_dir)
    second = run_script(data, bin_dir=bin_dir)

    assert first.returncode == 0
    assert second.returncode == 0
    assert "already running" in second.stdout
    arguments = server_arguments(bin_dir)
    assert "--version" in arguments and "--appendonly yes" in arguments
