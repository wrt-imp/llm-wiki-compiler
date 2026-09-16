"""Real Redis integration test: skipped unless the Redis tools are installed.

This is the one test that starts an actual ``redis-server`` (on a dedicated
port, in a temporary data directory), writes data, corrupts the AOF and shows
that the manager quarantines it, falls back to the RDB and never raises.

Run it inside WSL after ``sudo apt-get install redis-server redis-tools``::

    python -m pytest tests/persistence/test_redis_live.py -q
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from compiler.persistence import PersistenceManager, find_aof

REPO_ROOT = Path(__file__).resolve().parents[2]
CONF = REPO_ROOT / "redis" / "redis.conf"
PORT = 6399

redis_server = shutil.which("redis-server")
redis_cli = shutil.which("redis-cli")
redis_check_aof = shutil.which("redis-check-aof")

pytestmark = pytest.mark.skipif(
    not (redis_server and redis_cli and redis_check_aof),
    reason="redis-server / redis-cli / redis-check-aof are not installed",
)


def ping() -> bool:
    result = subprocess.run(
        [redis_cli, "-p", str(PORT), "ping"], capture_output=True, text=True
    )
    return result.stdout.strip() == "PONG"


def start(data_dir: Path) -> None:
    subprocess.run(
        [
            redis_server,
            str(CONF),
            "--dir",
            str(data_dir),
            "--port",
            str(PORT),
            "--appendonly",
            "yes",
            "--appendfsync",
            "everysec",
            "--daemonize",
            "yes",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if ping():
            return
        time.sleep(0.25)
    raise AssertionError("redis-server did not answer PING")


def stop() -> None:
    subprocess.run(
        [redis_cli, "-p", str(PORT), "shutdown", "nosave"],
        capture_output=True,
        text=True,
    )


def test_corrupt_aof_is_quarantined_and_redis_can_be_restarted(tmp_path: Path) -> None:
    data_dir = tmp_path / "redis"
    data_dir.mkdir()
    try:
        start(data_dir)
        subprocess.run(
            [redis_cli, "-p", str(PORT), "set", "demo", "1"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [redis_cli, "-p", str(PORT), "save"],
            check=True,
            capture_output=True,
            text=True,
        )
        stop()

        kind, path = find_aof(data_dir)
        assert kind != "none", "Redis should have created an AOF"
        if kind == "dir":
            aof_file = sorted(path.glob("*.aof"))[0]
        else:
            aof_file = path
        original = aof_file.read_bytes()
        aof_file.write_bytes(original[: max(len(original) // 2, 1)])

        report = PersistenceManager(data_dir, timestamp="live-test").ensure()

        assert report.aof is not None and report.aof.status.is_broken
        assert report.quarantine_path is not None and report.quarantine_path.exists()
        assert report.usable is True
        assert (data_dir / "dump.rdb").exists()
        assert any("may be lost" in warning for warning in report.warnings)

        start(data_dir)  # Redis comes back up with the RDB snapshot
        assert ping()
    finally:
        stop()
