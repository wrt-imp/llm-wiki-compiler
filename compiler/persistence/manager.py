"""Startup-time persistence management (approach C).

The manager inspects and prepares the persistence files. Starting the Redis
process stays with ``scripts/redis-persistence.sh`` (WSL / systemd); this module
exists so the application can always keep running:

* a broken AOF is quarantined with a timestamp and never deleted
* a repair is attempted on a copy and verified before it is used
* otherwise the latest RDB snapshot is used and a data-loss warning is emitted
* nothing in this module ever raises because of a persistence problem
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .health import (
    DEFAULT_AOF_TOOL,
    DEFAULT_RDB_TOOL,
    AOFAudit,
    AOFStatus,
    RDBAudit,
    RDBStatus,
    Runner,
    check_aof,
    check_rdb,
    find_aof,
    quarantine,
    repair_aof_copy,
)

LOGGER = logging.getLogger("compiler.persistence")

#: Where the data came from, as reported to the caller.
SOURCE_AOF = "aof"
SOURCE_AOF_REPAIRED = "aof-repaired"
SOURCE_RDB = "rdb"
SOURCE_EMPTY = "empty"
SOURCE_UNKNOWN = "unknown"

ACTION_NONE = "none"
ACTION_QUARANTINED = "quarantined"
ACTION_UNVERIFIED = "unverified"
ACTION_FAILED = "failed"


@dataclass
class PersistenceReport:
    """Everything the startup check learned and did."""

    data_dir: Path
    rdb: Optional[RDBAudit] = None
    aof: Optional[AOFAudit] = None
    action: str = ACTION_NONE
    source: str = SOURCE_UNKNOWN
    usable: bool = True
    quarantine_path: Optional[Path] = None
    repaired_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def log_lines(self) -> List[str]:
        """Human readable lines, in the order the spec asks for."""

        return list(self.metadata.get("log_lines", []))

    @property
    def data_loss_possible(self) -> bool:
        return self.source in (SOURCE_RDB, SOURCE_EMPTY) and self.action in (
            ACTION_QUARANTINED,
            ACTION_NONE,
        ) and self.aof is not None and self.aof.status.is_broken


class PersistenceManager:
    """Inspect the persistence files and prepare a safe startup."""

    def __init__(
        self,
        data_dir: Union[str, Path],
        *,
        corrupted_dir: Optional[Union[str, Path]] = None,
        aof_tool: str = DEFAULT_AOF_TOOL,
        rdb_tool: str = DEFAULT_RDB_TOOL,
        runner: Optional[Runner] = None,
        strict: bool = False,
        repair: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.corrupted_dir = (
            Path(corrupted_dir)
            if corrupted_dir is not None
            else self.data_dir / "corrupted"
        )
        self.aof_tool = aof_tool
        self.rdb_tool = rdb_tool
        self.runner = runner
        self.strict = strict
        self.repair = repair
        self.logger = logger or LOGGER

    def ensure(self, *, timestamp: Optional[str] = None) -> PersistenceReport:
        """Run the check; always returns a report, never raises."""

        report = PersistenceReport(data_dir=self.data_dir)
        lines: List[str] = []

        def info(message: str) -> None:
            self.logger.info(message)
            lines.append(f"INFO    {message}")

        def warn(message: str) -> None:
            self.logger.warning(message)
            lines.append(f"WARNING {message}")
            report.warnings.append(message)

        def error(message: str) -> None:
            self.logger.error(message)
            lines.append(f"ERROR   {message}")
            report.warnings.append(message)

        stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")

        try:
            info("Redis persistence check started")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.corrupted_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            error(f"cannot prepare data directory '{self.data_dir}': {exc}")
            report.usable = False
            report.action = ACTION_FAILED
            report.metadata["log_lines"] = lines
            return report

        try:
            report.rdb = check_rdb(
                self.data_dir, runner=self.runner, tool=self.rdb_tool
            )
            self._log_rdb(report.rdb, info, warn)

            report.aof = check_aof(
                self.data_dir, runner=self.runner, tool=self.aof_tool
            )
            info(f"AOF file check started ({report.aof.path})")

            status = report.aof.status
            if status is AOFStatus.OK:
                info("AOF file check passed")
                report.source = SOURCE_AOF
            elif status in (AOFStatus.MISSING, AOFStatus.EMPTY):
                info("no AOF yet; Redis will create one from the RDB snapshot")
                report.source = self._fallback_source(report.rdb)
            elif status.is_unverified:
                warn(
                    "AOF validation skipped "
                    f"({status.value}: {report.aof.detail}); Redis will load the "
                    "AOF as it is"
                )
                report.action = ACTION_UNVERIFIED
                report.source = SOURCE_UNKNOWN
                report.usable = not self.strict
            elif status.is_broken:
                self._recover_broken_aof(report, stamp, info, warn, error)
            else:  # pragma: no cover - defensive
                warn(f"unexpected AOF status {status.value}")
                report.source = self._fallback_source(report.rdb)
        except Exception as exc:  # pragma: no cover - the promise: never crash
            error(f"persistence check failed unexpectedly: {exc}")
            report.usable = False
            report.action = ACTION_FAILED

        report.metadata["log_lines"] = lines
        return report

    # ------------------------------------------------------------------
    def _log_rdb(self, rdb: RDBAudit, info: Callable[[str], None], warn) -> None:
        if rdb.status is RDBStatus.OK:
            info(f"RDB file check passed ({rdb.path})")
        elif rdb.status is RDBStatus.MISSING:
            info("RDB file check skipped (no snapshot yet)")
        elif rdb.status is RDBStatus.TOOL_MISSING:
            warn(f"redis-check-rdb not found; skipping RDB validation ({rdb.path})")
        else:
            warn(f"RDB file check reported {rdb.status.value} ({rdb.path})")

    def _fallback_source(self, rdb: Optional[RDBAudit]) -> str:
        if rdb is not None and rdb.status.is_usable and rdb.status is not RDBStatus.MISSING:
            return SOURCE_RDB
        return SOURCE_EMPTY

    def _recover_broken_aof(
        self,
        report: PersistenceReport,
        stamp: str,
        info: Callable[[str], None],
        warn: Callable[[str], None],
        error: Callable[[str], None],
    ) -> None:
        aof = report.aof
        assert aof is not None  # for the type checker
        warn(f"Redis AOF validation failed ({aof.status.value}: {aof.path})")
        warn("Redis AOF is corrupted.")

        kind, path = find_aof(self.data_dir)
        try:
            report.quarantine_path = quarantine(
                path, self.corrupted_dir, timestamp=stamp
            )
            warn(f"Original AOF has been moved to {report.quarantine_path}")
        except OSError as exc:
            error(f"could not quarantine '{path}': {exc}")
            report.usable = False
            report.action = ACTION_FAILED
            report.source = SOURCE_UNKNOWN
            return

        report.action = ACTION_QUARANTINED

        if self.repair:
            work_path = (
                self.data_dir / f"appendonlydir.repaired.{stamp}"
                if kind == "dir"
                else self.data_dir / f"appendonly.aof.repaired.{stamp}"
            )
            repaired = repair_aof_copy(
                kind,
                report.quarantine_path,
                work_path,
                runner=self.runner,
                tool=self.aof_tool,
            )
            if repaired is not None and self._install_repaired(kind, repaired):
                report.repaired_path = repaired
                report.source = SOURCE_AOF_REPAIRED
                info(
                    "Repaired AOF verified and put back in place "
                    f"({repaired}); the original stays in "
                    f"{report.quarantine_path}"
                )
                return
            info("Repair was not possible or did not verify; keeping the quarantine")

        report.source = self._fallback_source(report.rdb)
        warn("Falling back to the latest RDB snapshot")
        if report.source is SOURCE_RDB:
            warn("Data written after the latest RDB snapshot may be lost.")
            info("Redis will start from the RDB snapshot and rebuild the AOF")
        else:
            error("no usable RDB snapshot either; Redis will start empty")
            warn("Data may be lost.")

    def _install_repaired(self, kind: str, repaired: Path) -> bool:
        """Move a verified repair into the layout Redis expects."""

        target = (
            self.data_dir / "appendonlydir"
            if kind == "dir"
            else self.data_dir / "appendonly.aof"
        )
        try:
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(repaired), str(target))
            return True
        except OSError:
            return False


def ensure_persistence(
    data_dir: Union[str, Path], **options: Any
) -> PersistenceReport:
    """Convenience wrapper around :class:`PersistenceManager`."""

    return PersistenceManager(data_dir, **options).ensure()
