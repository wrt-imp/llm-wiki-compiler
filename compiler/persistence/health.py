"""Health checks for the Redis persistence files.

The checks call the official tools (``redis-check-aof`` / ``redis-check-rdb``)
and never try to understand the file formats themselves. Every outcome - missing
file, empty file, truncated tail, corrupt content, missing tool, failing tool,
permission problem - becomes a status value, so callers decide what to do
instead of being interrupted by an exception.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

DEFAULT_AOF_TOOL = "redis-check-aof"
DEFAULT_RDB_TOOL = "redis-check-rdb"
DEFAULT_TIMEOUT = 30.0


class PersistenceError(RuntimeError):
    """Raised only for programming mistakes; runtime problems are reported."""


class AOFStatus(str, Enum):
    """Outcome of the AOF check."""

    MISSING = "missing"
    EMPTY = "empty"
    OK = "ok"
    TRUNCATED = "truncated"
    CORRUPT = "corrupt"
    UNREADABLE = "unreadable"
    TOOL_MISSING = "tool-missing"
    TOOL_FAILED = "tool-failed"

    @property
    def is_broken(self) -> bool:
        """The file exists but the official tool rejected it."""

        return self in (
            AOFStatus.TRUNCATED,
            AOFStatus.CORRUPT,
            AOFStatus.UNREADABLE,
        )

    @property
    def is_unverified(self) -> bool:
        """We could not run the check, so the file was not validated."""

        return self in (AOFStatus.TOOL_MISSING, AOFStatus.TOOL_FAILED)


class RDBStatus(str, Enum):
    """Outcome of the RDB check."""

    MISSING = "missing"
    EMPTY = "empty"
    OK = "ok"
    CORRUPT = "corrupt"
    UNREADABLE = "unreadable"
    TOOL_MISSING = "tool-missing"
    TOOL_FAILED = "tool-failed"

    @property
    def is_usable(self) -> bool:
        """Can this snapshot be used to bring Redis back up?"""

        return self in (RDBStatus.OK, RDBStatus.TOOL_MISSING)


@dataclass(frozen=True)
class ToolResult:
    """What a check tool returned."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def output(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


@dataclass(frozen=True)
class AOFAudit:
    """Result of inspecting the AOF."""

    status: AOFStatus
    path: Path
    kind: str = "none"  # "file", "dir" or "none"
    detail: str = ""
    tool: str = DEFAULT_AOF_TOOL


@dataclass(frozen=True)
class RDBAudit:
    """Result of inspecting the RDB snapshot."""

    status: RDBStatus
    path: Path
    detail: str = ""
    tool: str = DEFAULT_RDB_TOOL


#: A runner takes a full command line and returns a ToolResult. It may raise
#: ``FileNotFoundError`` (tool missing) or ``subprocess.TimeoutExpired``.
Runner = Callable[[Sequence[str]], ToolResult]


def subprocess_runner(timeout: float = DEFAULT_TIMEOUT) -> Runner:
    """Return the default runner, which executes the tool as a child process."""

    def run(command: Sequence[str]) -> ToolResult:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return ToolResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    return run


def find_aof(data_dir: Path) -> Tuple[str, Path]:
    """Locate the AOF: Redis 7 keeps a directory, Redis 6 a single file."""

    data_dir = Path(data_dir)
    manifest = data_dir / "appendonlydir" / "appendonly.aof.manifest"
    if manifest.is_file():
        return "dir", data_dir / "appendonlydir"
    single = data_dir / "appendonly.aof"
    if single.is_file():
        return "file", single
    return "none", single


def aof_target(kind: str, path: Path) -> Path:
    """The path the check tool should be pointed at."""

    if kind == "dir":
        manifest = Path(path) / "appendonly.aof.manifest"
        return manifest if manifest.is_file() else Path(path)
    return Path(path)


def file_size(path: Path) -> int:
    """Size of a persistence file; a seam so tests can simulate permissions."""

    return Path(path).stat().st_size


def aof_data_files(kind: str, path: Path) -> list:
    """The files that actually hold AOF data (segments, not the manifest)."""

    path = Path(path)
    if kind == "file":
        return [path] if path.exists() else []
    if not path.is_dir():
        return []
    return sorted(
        item for item in path.iterdir() if item.is_file() and item.suffix != ".manifest"
    )


def check_aof(
    data_dir: Path,
    *,
    runner: Optional[Runner] = None,
    tool: str = DEFAULT_AOF_TOOL,
) -> AOFAudit:
    """Validate the AOF with the official tool."""

    kind, path = find_aof(Path(data_dir))
    if kind == "none":
        return AOFAudit(status=AOFStatus.MISSING, path=path, kind=kind)

    target = aof_target(kind, path)
    try:
        if not target.exists():
            return AOFAudit(AOFStatus.MISSING, path, kind, f"{target} is missing")
        data_files = aof_data_files(kind, path)
        if not data_files or sum(file_size(item) for item in data_files) == 0:
            return AOFAudit(AOFStatus.EMPTY, path, kind, f"{path} holds no data")
    except OSError as error:
        return AOFAudit(AOFStatus.UNREADABLE, path, kind, str(error))

    runner = runner or subprocess_runner()
    try:
        result = runner([tool, str(target)])
    except FileNotFoundError:
        return AOFAudit(
            AOFStatus.TOOL_MISSING, path, kind, f"{tool} is not installed"
        )
    except subprocess.TimeoutExpired:
        return AOFAudit(AOFStatus.TOOL_FAILED, path, kind, f"{tool} timed out")
    except OSError as error:
        return AOFAudit(
            AOFStatus.TOOL_FAILED, path, kind, f"{tool} could not run: {error}"
        )

    if result.returncode == 127:
        return AOFAudit(
            AOFStatus.TOOL_MISSING, path, kind, f"{tool} is not installed"
        )
    if result.returncode == 0:
        return AOFAudit(AOFStatus.OK, path, kind, result.output)

    output = result.output.lower()
    if "truncated" in output:
        return AOFAudit(AOFStatus.TRUNCATED, path, kind, result.output)
    if any(
        marker in output
        for marker in ("command not found", "no such file", "not recognized")
    ):
        return AOFAudit(
            AOFStatus.TOOL_FAILED, path, kind, result.output or "tool not runnable"
        )
    # The tool ran and rejected the file: treat that as corruption, never as a
    # reason to keep going silently.
    return AOFAudit(AOFStatus.CORRUPT, path, kind, result.output or "rejected")


def check_rdb(
    data_dir: Path,
    *,
    runner: Optional[Runner] = None,
    tool: str = DEFAULT_RDB_TOOL,
) -> RDBAudit:
    """Validate the RDB snapshot with the official tool (best effort)."""

    path = Path(data_dir) / "dump.rdb"
    if not path.exists():
        return RDBAudit(RDBStatus.MISSING, path)
    try:
        if file_size(path) == 0:
            return RDBAudit(RDBStatus.EMPTY, path, "snapshot is empty")
    except OSError as error:
        return RDBAudit(RDBStatus.UNREADABLE, path, str(error))

    runner = runner or subprocess_runner()
    try:
        result = runner([tool, str(path)])
    except FileNotFoundError:
        return RDBAudit(RDBStatus.TOOL_MISSING, path, f"{tool} is not installed")
    except subprocess.TimeoutExpired:
        return RDBAudit(RDBStatus.TOOL_FAILED, path, f"{tool} timed out")
    except OSError as error:
        return RDBAudit(RDBStatus.TOOL_FAILED, path, f"{tool} could not run: {error}")
    if result.returncode == 127:
        return RDBAudit(RDBStatus.TOOL_MISSING, path, f"{tool} is not installed")
    if result.returncode == 0:
        return RDBAudit(RDBStatus.OK, path, result.output)
    return RDBAudit(RDBStatus.CORRUPT, path, result.output)


def quarantine(path: Path, corrupted_dir: Path, *, timestamp: str) -> Path:
    """Move a broken persistence file aside; the original is never deleted."""

    path = Path(path)
    corrupted_dir = Path(corrupted_dir)
    corrupted_dir.mkdir(parents=True, exist_ok=True)
    target = corrupted_dir / f"{path.name}.corrupted.{timestamp}"
    attempt = 1
    while target.exists():
        attempt += 1
        target = corrupted_dir / f"{path.name}.corrupted.{timestamp}.{attempt}"
    shutil.move(str(path), str(target))
    return target


def repair_aof_copy(
    kind: str,
    quarantined: Path,
    work_path: Path,
    *,
    runner: Optional[Runner] = None,
    tool: str = DEFAULT_AOF_TOOL,
) -> Optional[Path]:
    """Repair a *copy* with ``redis-check-aof --fix`` and verify that copy.

    The quarantined original is never modified: the repair runs on a copy, and
    the copy is only returned when it validates afterwards.
    """

    quarantined = Path(quarantined)
    work_path = Path(work_path)
    runner = runner or subprocess_runner()
    try:
        if kind == "dir":
            if work_path.exists():
                shutil.rmtree(work_path)
            shutil.copytree(quarantined, work_path)
            target = work_path / "appendonly.aof.manifest"
            if not target.is_file():
                target = work_path
        else:
            work_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(quarantined, work_path)
            target = work_path
    except OSError:
        return None

    try:
        fixed = runner([tool, "--fix", str(target)])
        if fixed.returncode != 0:
            return None
        verified = runner([tool, str(target)])
        if verified.returncode != 0:
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return work_path
