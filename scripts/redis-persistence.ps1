# Windows entry point for the managed Redis startup.
#
# Redis itself is expected to run in WSL (recommended) or as a native Windows
# build (Memurai / a portable redis-server.exe). This wrapper only forwards the
# work to scripts/redis-persistence.sh so the recovery logic lives in one place.
#
# Usage:
#   powershell -File scripts\redis-persistence.ps1                 # via WSL
#   powershell -File scripts\redis-persistence.ps1 -Native         # native redis-server.exe

param(
    [switch]$Native,
    [int]$Port = 6379,
    [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "redis-persistence.sh"

if ($Native) {
    if (-not (Get-Command redis-server -ErrorAction SilentlyContinue)) {
        Write-Error "redis-server.exe not found in PATH; use WSL (no -Native) or install Memurai."
        exit 1
    }
    $env:REDIS_PORT = "$Port"
    if ($DataDir) { $env:REDIS_DATA_DIR = $DataDir }
    # Native Windows builds have no bash: run the same steps inline, minimally.
    $data = if ($DataDir) { $DataDir } else { Join-Path $repoRoot "data\redis" }
    New-Item -ItemType Directory -Force -Path $data, (Join-Path $data "corrupted") | Out-Null
    $aof = Join-Path $data "appendonly.aof"
    $rdb = Join-Path $data "dump.rdb"
    Write-Host "INFO    Redis persistence check started (native, data=$data)"
    if (Test-Path $rdb) { Write-Host "INFO    RDB file check passed ($rdb)" } else { Write-Host "INFO    RDB file check skipped (no snapshot yet)" }
    if (Test-Path $aof) {
        $check = Get-Command redis-check-aof -ErrorAction SilentlyContinue
        if ($check) {
            & redis-check-aof $aof *> $null
            if ($LASTEXITCODE -ne 0) {
                $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
                $quarantined = Join-Path (Join-Path $data "corrupted") "appendonly.aof.corrupted.$stamp"
                Write-Warning "Redis AOF validation failed; moving it to $quarantined"
                Move-Item -LiteralPath $aof -Destination $quarantined
                Write-Warning "Falling back to the latest RDB snapshot"
                Write-Warning "Data written after the latest RDB snapshot may be lost."
            } else {
                Write-Host "INFO    AOF file check passed"
            }
        } else {
            Write-Warning "redis-check-aof not found; cannot validate $aof"
        }
    }
    $conf = Join-Path $repoRoot "redis\redis.conf"
    Start-Process -FilePath "redis-server" -ArgumentList @("`"$conf`"", "--dir", "`"$data`"", "--port", "$Port", "--appendonly", "yes", "--appendfsync", "everysec", "--daemonize", "no") -WindowStyle Hidden
    Write-Host "INFO    redis-server started (native)"
    exit 0
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-Error "wsl.exe not found; install WSL (wsl --install) or use -Native."
    exit 1
}

$wslRepo = (wsl.exe -e bash -lc "wslpath -a '$($PSScriptRoot -replace '\\','/')/..'" ).Trim()
if (-not $wslRepo) {
    Write-Error "could not resolve the repository path inside WSL."
    exit 1
}

$envArgs = "REDIS_PORT=$Port"
if ($DataDir) {
    $wslData = (wsl.exe -e bash -lc "wslpath -a '$($DataDir -replace '\\','/')'").Trim()
    $envArgs = "$envArgs REDIS_DATA_DIR=$wslData"
}

Write-Host "INFO    delegating to WSL: $wslRepo/scripts/redis-persistence.sh"
wsl.exe -e bash -lc "cd '$wslRepo' && $envArgs bash scripts/redis-persistence.sh"
exit $LASTEXITCODE
