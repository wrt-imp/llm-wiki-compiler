#!/usr/bin/env bash
# Managed Redis startup with RDB + AOF hybrid persistence.
#
# Flow:
#   1. make sure the data dir and the corrupted/ quarantine dir exist
#   2. if Redis already answers PING: nothing to do
#   3. validate dump.rdb (redis-check-rdb, best effort)
#   4. validate the AOF (redis-check-aof; manifest dir on Redis 7, single file
#      on Redis 6)
#   5. when the AOF is broken: quarantine it with a timestamp (never delete),
#      try to repair a *copy*, verify the copy, and otherwise fall back to the
#      latest RDB snapshot
#   6. start redis-server (AOF enabled) and report which source was used and
#      whether data may have been lost
#
# Exit codes: 0 usable (possibly degraded), 1 could not start Redis at all.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${REDIS_DATA_DIR:-$REPO_ROOT/data/redis}"
CORRUPTED_DIR="$DATA_DIR/corrupted"
CONF="${REDIS_CONF:-$REPO_ROOT/redis/redis.conf}"
PORT="${REDIS_PORT:-6379}"
BIND="${REDIS_BIND:-127.0.0.1}"
FOREGROUND="${REDIS_FOREGROUND:-0}"
LOG_FILE="$DATA_DIR/redis-server.log"
PID_FILE="$DATA_DIR/redis.pid"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

log_info() { printf 'INFO    %s\n' "$*"; }
log_warn() { printf 'WARNING %s\n' "$*"; }
log_error() { printf 'ERROR   %s\n' "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

main() {
  log_info "Redis persistence check started"
  log_info "repo=$REPO_ROOT data=$DATA_DIR conf=$CONF port=$PORT"

  if ! mkdir -p "$DATA_DIR" "$CORRUPTED_DIR" 2>/dev/null; then
    log_error "cannot create data directory '$DATA_DIR' (permission?)"
    return 1
  fi
  if [ ! -w "$DATA_DIR" ]; then
    log_error "data directory '$DATA_DIR' is not writable (permission?)"
    return 1
  fi

  if have redis-cli && redis-cli -p "$PORT" ping 2>/dev/null | grep -q PONG; then
    log_info "Redis already running on port $PORT; nothing to do"
    return 0
  fi

  if ! have redis-server; then
    log_error "redis-server not found in PATH (install Redis, e.g. 'sudo apt-get install redis-server')"
    return 1
  fi

  local redis_major
  redis_major="$(redis-server --version 2>/dev/null | sed -n 's/.*v=\([0-9]*\)\..*/\1/p')"
  [ -n "$redis_major" ] || redis_major=7
  log_info "redis-server major version: $redis_major"

  check_rdb

  local aof_kind aof_path status
  read -r aof_kind aof_path <<<"$(find_aof)"
  status="$(check_aof "$aof_kind" "$aof_path")"

  local degraded=0
  case "$status" in
    missing) log_info "No AOF yet; Redis will create one" ;;
    empty)   log_warn "AOF file is empty ($aof_path); Redis will rebuild it from RDB" ;;
    ok)      log_info "AOF file check passed ($aof_kind: $aof_path)" ;;
    *)
      degraded=1
      handle_broken_aof "$aof_kind" "$aof_path" "$status" || degraded=1
      ;;
  esac

  log_info "Starting Redis (appendonly=yes, appendfsync=everysec, aof-use-rdb-preamble=yes)"
  local args=("$CONF" --dir "$DATA_DIR" --port "$PORT" --bind "$BIND"
              --pidfile "$PID_FILE" --appendonly yes --appendfsync everysec
              --logfile "$LOG_FILE")
  if [ "$redis_major" -ge 7 ]; then
    args+=(--appenddirname appendonlydir)
  fi
  if [ "$FOREGROUND" = "1" ]; then
    args+=(--daemonize no)
    log_info "running in the foreground (REDIS_FOREGROUND=1)"
    redis-server "${args[@]}"
    return $?
  fi
  args+=(--daemonize yes)
  if ! redis-server "${args[@]}"; then
    log_error "redis-server failed to start; see $LOG_FILE"
    return 1
  fi

  local waited=0
  while [ "$waited" -lt 20 ]; do
    if have redis-cli && redis-cli -p "$PORT" ping 2>/dev/null | grep -q PONG; then
      if [ "$degraded" = "1" ]; then
        log_info "Redis started successfully using RDB"
      else
        log_info "Redis started successfully using AOF"
      fi
      return 0
    fi
    sleep 0.25
    waited=$((waited + 1))
  done

  log_error "redis-server did not answer PING on port $PORT; see $LOG_FILE"
  return 1
}

check_rdb() {
  local rdb="$DATA_DIR/dump.rdb"
  if [ ! -f "$rdb" ]; then
    log_info "RDB file check skipped (no snapshot yet: $rdb)"
    return 0
  fi
  if [ ! -s "$rdb" ]; then
    log_warn "RDB file is empty: $rdb"
    return 0
  fi
  if ! have redis-check-rdb; then
    log_warn "redis-check-rdb not found; skipping RDB validation ($rdb)"
    return 0
  fi
  if redis-check-rdb "$rdb" >/dev/null 2>&1; then
    log_info "RDB file check passed ($rdb)"
  else
    log_warn "RDB file check failed ($rdb); Redis may refuse to load this snapshot"
  fi
}

# find_aof prints "<kind> <path>"; kind is dir, file or none.
find_aof() {
  local manifest="$DATA_DIR/appendonlydir/appendonly.aof.manifest"
  if [ -f "$manifest" ]; then
    printf 'dir %s\n' "$DATA_DIR/appendonlydir"
    return 0
  fi
  if [ -f "$DATA_DIR/appendonly.aof" ]; then
    printf 'file %s\n' "$DATA_DIR/appendonly.aof"
    return 0
  fi
  printf 'none %s\n' "$DATA_DIR/appendonly.aof"
}

check_aof() {
  local kind="$1" path="$2"
  [ "$kind" = "none" ] && { printf 'missing\n'; return 0; }

  local target="$path"
  [ "$kind" = "dir" ] && target="$path/appendonly.aof.manifest"

  if [ ! -s "$target" ]; then printf 'empty\n'; return 0; fi

  if ! have redis-check-aof; then
    log_warn "redis-check-aof not found; cannot validate $target"
    printf 'tool-missing\n'
    return 0
  fi

  local output
  if output="$(redis-check-aof "$target" 2>&1)"; then
    printf 'ok\n'
  else
    # Redis 6 cannot check a Redis 7 manifest; retry with the first segment.
    if [ "$kind" = "dir" ]; then
      local segment
      segment="$(ls "$path"/appendonly.aof.*.incr.aof "$path"/appendonly.aof.*.base.rdb 2>/dev/null | head -n 1)"
      if [ -n "$segment" ] && redis-check-aof "$segment" >/dev/null 2>&1; then
        log_warn "redis-check-aof could not validate the manifest but accepted $segment"
        printf 'ok\n'
        return 0
      fi
    fi
    log_warn "redis-check-aof rejected $target"
    [ -n "$output" ] && printf 'WARNING %s\n' "$(printf '%s' "$output" | head -n 3)" >&2
    printf 'corrupt\n'
  fi
}

handle_broken_aof() {
  local kind="$1" path="$2" status="$3"
  log_warn "Redis AOF validation failed ($status: $path)"
  log_warn "Redis AOF is corrupted."

  local quarantined="$CORRUPTED_DIR/$(basename "$path").corrupted.$TIMESTAMP"
  if mv "$path" "$quarantined" 2>/dev/null; then
    log_warn "Original AOF has been moved to $quarantined"
  else
    log_error "could not quarantine '$path' (permission?); refusing to continue with a broken AOF"
    return 1
  fi

  if repair_copy "$kind" "$quarantined"; then
    log_info "Repaired AOF verified; Redis will use the repaired copy"
    return 0
  fi

  log_warn "Falling back to the latest RDB snapshot"
  if [ -f "$DATA_DIR/dump.rdb" ] && [ -s "$DATA_DIR/dump.rdb" ]; then
    log_warn "Data written after the latest RDB snapshot may be lost."
  else
    log_error "no usable RDB snapshot either; Redis will start with an empty dataset"
    log_warn "Data may be lost."
  fi
  return 0
}

# Copy the quarantined AOF, let redis-check-aof --fix repair the copy, verify it
# and only then put it back. The original never gets modified.
repair_copy() {
  local kind="$1" quarantined="$2"
  have redis-check-aof || return 1

  local work="$DATA_DIR/.repair-$TIMESTAMP"
  rm -rf "$work"
  if [ "$kind" = "dir" ]; then
    cp -r "$quarantined" "$work" || return 1
    local target="$work/appendonly.aof.manifest"
  else
    cp "$quarantined" "$work" || return 1
    local target="$work"
  fi

  if ! redis-check-aof --fix "$target" >/dev/null 2>&1; then
    log_warn "redis-check-aof --fix could not repair the copy; keeping the quarantined file"
    rm -rf "$work"
    return 1
  fi
  if ! redis-check-aof "$target" >/dev/null 2>&1; then
    log_warn "repaired copy still fails validation; keeping the quarantined file"
    rm -rf "$work"
    return 1
  fi

  if [ "$kind" = "dir" ]; then
    target="$DATA_DIR/appendonlydir"
  else
    target="$DATA_DIR/appendonly.aof"
  fi
  if mv "$work" "$target" 2>/dev/null; then
    log_info "Repaired AOF written to $target (original kept in $quarantined)"
    return 0
  fi
  rm -rf "$work"
  return 1
}

main "$@"
