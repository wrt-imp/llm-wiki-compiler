# Redis 持久化（RDB + AOF 混合）

这个目录与 `scripts/redis-persistence.sh` 一起，为 Redis 提供**RDB 快照 + AOF 增量日志**的混合持久化，以及"AOF 坏了也不能让服务起不来"的降级恢复。

```text
应用 / Web UI
     ↓
Redis（受 scripts/redis-persistence.sh 管理）
 ├── RDB：dump.rdb            周期性完整快照（save 900 1 / 300 10 / 60 10000）
 └── AOF：appendonlydir/      增量写操作（appendfsync everysec + aof-use-rdb-preamble yes）
```

## 数据目录

```text
data/redis/                      # 运行时目录，已加入 .gitignore
├── dump.rdb                     # RDB 快照
├── appendonlydir/               # Redis 7 的 AOF（manifest + 段文件）
│   └── appendonly.aof.manifest
├── appendonly.aof               # Redis 6 的单文件 AOF（版本不同则只有这一种）
├── corrupted/                   # 损坏文件的隔离区（永不删除）
│   └── appendonly.aof.corrupted.20260916-230000
├── redis-server.log
└── redis.pid
```

## 配置

`redis/redis.conf` 是受管实例的配置，关键项：

```conf
appendonly yes
appendfsync everysec
aof-use-rdb-preamble yes
save 900 1
save 300 10
save 60 10000
```

启动脚本会用命令行参数覆盖 `dir` / `port` / `bind` / `logfile` / `appenddirname`，所以同一份配置在 WSL 与 Windows 都能用（Redis 6 会自动去掉 `appenddirname`）。

## 在 WSL 里跑（推荐）

```bash
# 一次性准备（WSL 里执行）
sudo apt-get update && sudo apt-get install -y redis-server redis-tools

# 启动（带 AOF 健康检查 + 降级恢复）
cd /mnt/c/Users/72878/Desktop/compiler      # 或你在 WSL 里的仓库路径
bash scripts/redis-persistence.sh

# 验证
redis-cli ping                              # PONG
redis-cli config get appendonly             # appendonly -> yes
redis-cli config get appendfsync            # appendfsync -> everysec
redis-cli config get aof-use-rdb-preamble   # yes
```

Windows 侧可以直接转发到 WSL：

```powershell
powershell -File scripts\redis-persistence.ps1              # 交给 WSL 执行
powershell -File scripts\redis-persistence.ps1 -Native      # 本机装了 Memurai/redis-server.exe 时
```

## 恢复流程

```text
启动脚本
   ↓
数据目录/隔离目录检查（权限问题 → 明确报错退出）
   ↓
Redis 已在运行？→ 是：直接返回
   ↓
RDB 检查（redis-check-rdb，缺失工具只警告）
   ↓
AOF 检查（redis-check-aof；Redis 7 指向 manifest，失败则回退检查段文件）
   ├── 正常            → 用 AOF 启动
   ├── 不存在 / 空      → 用 RDB 启动，Redis 会自动重建 AOF
   ├── 工具缺失 / 失败  → 记 WARNING，按"未验证"继续（严格模式可改为失败）
   └── 截断 / 损坏      → 隔离原文件（改名到 corrupted/，绝不删除）
                          → 复制一份用 redis-check-aof --fix 修复
                          → 复验通过 → 放回原位并使用
                          → 复验失败 → 保留隔离文件，回退 RDB 启动
```

损坏时日志形如：

```text
INFO    Redis persistence check started
INFO    RDB file check passed (data/redis/dump.rdb)
INFO    AOF file check started (data/redis/appendonlydir)
WARNING redis-check-aof rejected data/redis/appendonlydir/appendonly.aof.manifest
WARNING Redis AOF validation failed (corrupt: data/redis/appendonlydir)
WARNING Redis AOF is corrupted.
WARNING Original AOF has been moved to data/redis/corrupted/appendonlydir.corrupted.20260916-230000
WARNING Falling back to the latest RDB snapshot
WARNING Data written after the latest RDB snapshot may be lost.
INFO    Redis started successfully using RDB
```

应用侧（不启动 Redis 也能用）：

```powershell
python -m compiler --redis-check                  # 只做检查与恢复准备，打印报告
python -m compiler --redis-check --redis-strict   # 无法验证时退出码 2
python -m compiler --redis-save my-key --check --kb kb.json
python -m compiler --redis-load my-key --check
```

`--redis-check` 只读+准备：会隔离损坏的 AOF、尝试修复副本，但**不会**删除任何文件，也**不会**因为持久化问题让命令崩溃。

## 怎么验证"不会崩"（人为制造损坏）

在 WSL 里（Redis 已停）：

```bash
cd /mnt/c/Users/72878/Desktop/compiler

# 1) 先正常写一点数据，确保有 RDB + AOF
bash scripts/redis-persistence.sh
redis-cli set demo 1 && redis-cli save && redis-cli shutdown nosave

# 2) 制造 AOF 损坏：截断或写入垃圾字节
head -c 200 data/redis/appendonlydir/appendonly.aof.1.incr.aof > /tmp/broken
mv /tmp/broken data/redis/appendonlydir/appendonly.aof.1.incr.aof   # 截断
# 或：printf 'GARBAGE\r\n' >> data/redis/appendonlydir/appendonly.aof.1.incr.aof

# 3) 再启动 —— 期望：隔离损坏 AOF、回退 RDB、Redis 正常起来
bash scripts/redis-persistence.sh
ls data/redis/corrupted/        # 原文件在这里，带时间戳
redis-cli ping                  # PONG
```

其他可验证场景：删除 AOF（应正常用 RDB 启动并重建 AOF）、`PATH` 里临时去掉 `redis-check-aof`（应记 WARNING 后继续）、把数据目录设为不可写（应明确报错退出，而不是 traceback）。

## 限制与约定

- **绝不删除**损坏的 AOF；只改名隔离到 `corrupted/`。
- **不自己解析 AOF**：一律交给 `redis-check-aof`。
- 不静默 `--fix` 原文件：先备份，再修副本，复验通过才使用。
- Redis 6 与 7 的 AOF 布局不同（单文件 vs `appendonlydir/` + manifest），脚本两者都处理并在日志里说明用的是哪种。
- 数据目录里的内容（含损坏文件）**不进 Git**；`.gitignore` 已忽略 `data/`。
