"""Redis persistence for the LLM Wiki Compiler: RDB + AOF, with recovery.

Two halves, on purpose (approach C):

* ``scripts/redis-persistence.sh`` (plus the PowerShell wrapper) owns the Redis
  *process* and the persistence files: it validates RDB/AOF, quarantines a
  corrupted AOF and starts Redis.
* this package owns the *application* side: it inspects the same files, reports
  what it found and never raises because of a persistence problem, so the
  compiler keeps working (Redis is an optional store).

    >>> from compiler.persistence import ensure_persistence
    >>> report = ensure_persistence("data/redis")
    >>> report.source, report.usable
    ('aof', True)
"""

from .health import (
    DEFAULT_AOF_TOOL,
    DEFAULT_RDB_TOOL,
    AOFAudit,
    AOFStatus,
    PersistenceError,
    RDBAudit,
    RDBStatus,
    ToolResult,
    aof_target,
    check_aof,
    check_rdb,
    find_aof,
    quarantine,
    repair_aof_copy,
    subprocess_runner,
)
from .manager import (
    ACTION_FAILED,
    ACTION_NONE,
    ACTION_QUARANTINED,
    ACTION_UNVERIFIED,
    SOURCE_AOF,
    SOURCE_AOF_REPAIRED,
    SOURCE_EMPTY,
    SOURCE_RDB,
    SOURCE_UNKNOWN,
    PersistenceManager,
    PersistenceReport,
    ensure_persistence,
)
from .store import DEFAULT_NAMESPACE, RedisStore

__all__ = [
    "ACTION_FAILED",
    "ACTION_NONE",
    "ACTION_QUARANTINED",
    "ACTION_UNVERIFIED",
    "AOFAudit",
    "AOFStatus",
    "DEFAULT_AOF_TOOL",
    "DEFAULT_NAMESPACE",
    "DEFAULT_RDB_TOOL",
    "PersistenceError",
    "PersistenceManager",
    "PersistenceReport",
    "RDBAudit",
    "RDBStatus",
    "RedisStore",
    "SOURCE_AOF",
    "SOURCE_AOF_REPAIRED",
    "SOURCE_EMPTY",
    "SOURCE_RDB",
    "SOURCE_UNKNOWN",
    "ToolResult",
    "aof_target",
    "check_aof",
    "check_rdb",
    "ensure_persistence",
    "find_aof",
    "quarantine",
    "repair_aof_copy",
    "subprocess_runner",
]
