"""Shared helpers for the Redis persistence tests.

None of these tests need a real Redis: the check tools are injected as fake
runners, or as fake executables placed on ``PATH`` for the shell-script tests.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Sequence

from compiler.persistence.health import ToolResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "redis-persistence.sh"


class FakeRunner:
    """A scripted runner: per tool name either a ToolResult or an exception."""

    def __init__(self, **results: object) -> None:
        self.results: Dict[str, object] = results
        self.calls: List[List[str]] = []

    def __call__(self, command: Sequence[str]) -> ToolResult:
        arguments = [str(item) for item in command]
        self.calls.append(arguments)
        tool = Path(arguments[0]).name
        outcome = self.results.get(tool)
        if outcome is None:
            outcome = ToolResult(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, ToolResult)
        return outcome

    @property
    def tools_called(self) -> List[str]:
        return [Path(call[0]).name for call in self.calls]


def write_aof(
    data_dir: Path,
    content: bytes = b"*2\r\n$3\r\nSET\r\n$4\r\ndemo\r\n",
    *,
    layout: str = "dir",
) -> Path:
    """Create an AOF in the requested layout and return its path."""

    data_dir = Path(data_dir)
    if layout == "dir":
        directory = data_dir / "appendonlydir"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "appendonly.aof.manifest").write_text(
            "appendonly.aof.1.incr.aof\n", encoding="utf-8"
        )
        (directory / "appendonly.aof.1.incr.aof").write_bytes(content)
        return directory
    path = data_dir / "appendonly.aof"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def write_rdb(data_dir: Path, content: bytes = b"REDIS0011-fake-snapshot") -> Path:
    path = Path(data_dir) / "dump.rdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def bash_path() -> str | None:
    """A working bash, used to exercise the shell script itself."""

    for candidate in ("bash", "sh"):
        found = shutil.which(candidate)
        if found:
            return found
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def write_fake_tools(
    bin_dir: Path,
    *,
    aof_check_ok: bool = True,
    aof_fix_ok: bool = True,
    include_aof_tool: bool = True,
) -> Path:
    """Create fake redis-* executables that record what they were called with."""

    bin_dir = Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "calls.log"
    started = bin_dir / "redis-server.started"
    args_file = bin_dir / "redis-server.args"
    fixed = bin_dir / "aof.fixed"

    def script(name: str, body: str) -> Path:
        path = bin_dir / name
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
        return path

    if include_aof_tool:
        fix_branch = f'touch "{fixed}"' if aof_fix_ok else "exit 1"
        script(
            "redis-check-aof",
            f'''
echo "redis-check-aof $*" >> "{log}"
if [ "${{1:-}}" = "--fix" ]; then
  {fix_branch}
  exit 0
fi
if [ -f "{fixed}" ]; then exit 0; fi
exit {0 if aof_check_ok else 1}
''',
        )

    script(
        "redis-check-rdb",
        f'''
echo "redis-check-rdb $*" >> "{log}"
echo "RDB looks OK"
exit 0
''',
    )
    script(
        "redis-server",
        f'''
echo "redis-server $*" >> "{args_file}"
if [ "${{1:-}}" = "--version" ]; then
  echo "Redis server v=7.2.5 sha=00000000:0 malloc=jemalloc bits=64 build=test"
  exit 0
fi
touch "{started}"
echo "started"
exit 0
''',
    )
    script(
        "redis-cli",
        f'''
echo "redis-cli $*" >> "{log}"
if [ -f "{started}" ]; then echo PONG; fi
exit 0
''',
    )
    return bin_dir


def server_arguments(bin_dir: Path) -> str:
    """The arguments the fake redis-server was started with."""

    path = Path(bin_dir) / "redis-server.args"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def recorded_calls(bin_dir: Path) -> str:
    """Everything the fake tools were called with."""

    path = Path(bin_dir) / "calls.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_script(
    data_dir: Path,
    *,
    bin_dir: Path | None = None,
    env_extra: Dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run scripts/redis-persistence.sh with an isolated data dir and PATH."""

    bash = bash_path()
    assert bash is not None, "bash is required for the shell-script tests"
    # Inside bash the tools live in a POSIX PATH; only coreutils are needed
    # besides the fake redis-* executables.
    path_entries = [to_posix(bin_dir)] if bin_dir else []
    path_entries += ["/usr/bin", "/bin"]
    env = {
        "PATH": ":".join(path_entries),
        "REDIS_DATA_DIR": to_posix(data_dir),
        "REDIS_PORT": "6399",
        "HOME": to_posix(data_dir),
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [bash, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=180,
    )


def to_posix(path: Path) -> str:
    """A path bash understands (``C:/x`` -> ``/c/x``)."""

    text = Path(path).as_posix()
    if len(text) > 1 and text[1] == ":":
        return f"/{text[0].lower()}{text[2:]}"
    return text
