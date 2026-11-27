# L1 claim/validator/API 审计（29 组）

这份记录比 `l1_metric_audit.md` 多走两步：生成 claim/evidence/tool_call 图，跑
`validate.py` 的 14 项检查，再通过 `/api/ask` 走一次完整入口。它仍不是独立物理复算，
validator 重跑的是同一个 `skills/metric`。

运行条件：

- `--t-max 1.0 --mode retrospective`，避免把 t85 > 0.95 的组误判成时间门失败。
- API 用 TestClient，`SHM_LLM_DISABLE=1`，问题为 `t85 是多少`，`t=1.0`。
- 所有组只生成 `t85` 一条 claim。

## C1/C2

| gid | 批次 | validate | API | claim 数 | API 时延 s |
|---|---|---|---:|---:|---:|
| L1-04 | C1 | 0 failed / 14 checks | ok | 1 | 12.3 |
| L1-05 | C1 | 0 failed / 14 checks | ok | 1 | 5.6 |
| L1-09 | C1 | 0 failed / 14 checks | ok | 1 | 6.1 |
| L1-50 | C2 | 0 failed / 14 checks | ok | 1 | 2.2 |
| L1-51 | C2 | 0 failed / 14 checks | ok | 1 | 2.3 |
| L1-52 | C2 | 0 failed / 14 checks | ok | 1 | 2.3 |
| L1-54 | C2 | 0 failed / 14 checks | ok | 1 | 2.4 |
| L1-55 | C2 | 0 failed / 14 checks | ok | 1 | 2.3 |
| L1-56 | C2 | 0 failed / 14 checks | ok | 1 | 2.5 |
| L1-59 | C2 | 0 failed / 14 checks | ok | 1 | 2.3 |
| L1-60 | C2 | 0 failed / 14 checks | ok | 1 | 2.2 |

## C3 小数据组

| gid | validate | API | claim 数 | 备注 |
|---|---|---|---:|---|
| L1-14 | 0 failed / 14 checks | ok | 1 | 600 s 帧 |
| L1-24 | 0 failed / 14 checks | ok | 1 | 600 s 帧 |

## C4 与 L1-22

| gid | API 内校验 | API | claim 数 | API 时延 s | 备注 |
|---|---|---|---:|---:|---|
| L1-25 | 0 failed / 10 checks | ok | 1 | 64.4 | 600 s 帧 |
| L1-27 | 0 failed / 10 checks | ok | 1 | 122.8 | 600 s 帧，raw 556 帧 |
| L1-29 | 0 failed / 10 checks | ok | 1 | 56.7 | 600 s 帧 |
| L1-31 | 0 failed / 10 checks | ok | 1 | 85.5 | 600 s 帧 |
| L1-35 | 0 failed / 10 checks | ok | 1 | 109.5 | 600 s 帧 |
| L1-41 | 0 failed / 10 checks | ok | 1 | 34.7 | 600 s 帧 |
| L1-44 | 0 failed / 10 checks | ok | 1 | 402.9 | 600 s 帧 |
| L1-22 | 0 failed / 10 checks | ok | 1 | 362.1 | 600 s 帧，AE 约 20.7 GB |

## 计数

- 29/29 组 API 端到端通过。
- 29/29 组 raw metric 有独立记录。
- C4 与 L1-22 只保存了 API 路径的 10 项校验，没有单独保存 14 项 builder 图。
- C4 与 L1-22 的 API 时延包含 builder 与 validator 两次 raw 解析。

## 限制

- 只测 `t85`，没有测 `t50`、FBG/DFOS/PZT 多工具、workflow 或 conflict。
- 没有做浏览器点击，只做 TestClient。
- `--t-max 1.0` 只验证图能通过验证，不验证时间门拒绝；时间门已有独立测试。
- L1-27、L1-36 的帧边界差异保留，没有强行改数。
- validator 是同一工具重跑，不是独立物理复算。
