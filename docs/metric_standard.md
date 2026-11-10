# t_x 读数标准（v1）

> 2026-11-09 冻结。报告、看板、论文里的 t50 / t85 以本文件为准。
> 代码实现：`skills/metric/run.py` 的 `_t_at`。

## 1. 定义

```text
t_x = 100 * C^{-1}(x * C_end) / n_f
```

- `C`：600 s 帧上的累积 AE hits；`C_end = sum(hits)`；
- `g`：帧的负载掩码。FBG 窗内应变峰峰值中位 > 200 → 1，否则 0；`fill=holdgap`；
- `f = n_f / (sum(g) * 600)`；
- `cycle = cumsum(g * 600 * f)`，终点严格等于 `n_f`；
- `C^{-1}`：在相邻两帧之间做**线性插值**；
- `x = 0.50 / 0.85`。

## 2. 为什么必须是线性插值

步进插值（`searchsorted` 取上界）会系统性地取到 85% 之后的第一个帧，偏高约半个帧宽，且随帧宽变化：

| 帧宽 | 掩码 | 插值 | L1-06 t85 |
|---:|---|---|---:|
| 300 s | 有 | 线性 | 93.75 |
| 300 s | 有 | 步进 | 93.86 |
| 600 s | 有 | **线性** | **93.76** |
| 600 s | 有 | 步进 | 94.04 |
| 1200 s | 有 | 线性 | 93.48 |
| 1200 s | 有 | 步进 | 94.07 |
| 600 s | 无 | 线性 | 93.78 |
| 600 s | 有 | 线性（时间轴） | 93.76 |
| 600 s | 有 | 线性（常数 dt） | 93.81 |

结论：

- 线性插值在 300/600 s 之间只差 **0.01 pp**；步进差 **0.18 pp**。
- 负载掩码的影响约 0.02 pp；常数 dt 轴约 0.05 pp；帧宽 1200 s 会带来约 0.28 pp 偏差。
- 因此：**600 s 帧 + 负载掩码 + 线性插值**是唯一同时满足“可复算、帧宽稳定、与物理定义一致”的口径。

## 3. 标准值（2026-11-09 复算）

| 试件 | t50 | t85（2 位） | t85（1 位，UI） | 旧表/看板（步进） |
|---|---:|---:|---:|---:|
| L1-06 | 68.02 | 93.76 | 93.8 | 94.0 |
| L1-13 | 67.94 | 93.05 | 93.0 | 93.1 |
| L1-14 | 52.85 | 83.56 | 83.6 | 83.8 |
| L1-24 | 83.87 | 96.33 | 96.3 | 96.5 |

C3/C4 全量 15 组的标准值见 [`docs/l1_c3c4_canonical.csv`](l1_c3c4_canonical.csv)（由 raw frame/cycle 缓存线性插值复算）。

复算命令（需 `E:\l1` 挂载）：

```powershell
cd D:\aircraft
python skills\metric\run.py --dataset L1 --gid L1-06 --json
```

## 4. 适用范围与容差

| 数据 | 状态 |
|---|---|
| L1 C3/C4（`.DTA`） | **适用**；600 s 帧，容差 ±0.1 pp |
| L1 C1/C2（`.pridb`） | **可算**：HI_AE anchor（500-cycle，单/多会话均可用）；线性插值；L1-03=85.17、L1-49=82.24 |
| L2（`.pridb`） | **可算**：session→cycle 表；1 s bin；L2-07=67.57；首次扫描慢，缓存后 <1 s |
| 帧宽 > 600 s | 容差放宽到 ±0.3 pp，或重跑 600 s |
| 无 FBG 的数据集（如 F-MOC） | 只能走时间轴，必须在 `scope.axis` 写 `time`；不得与 cycle 轴混比；`t85_dic` 81.4–86.2%（DIC 末帧为 test_end 下界），`t85_full` 不可横向比；见 `docs/fmoc_initial.md` |

## 4.1 覆盖规则

`t_x` 只有在 `coverage = t_last_valid / test_end >= 0.95` 时才可作为跨试件比较量。coverage < 0.95 时：

- 必须同时报告 `coverage` 与 `t99`；
- 状态标 `insufficient`，不得进入 claim；
- `t85_active = t85_full / t99` 只能作敏感性分析，不是标准值。

F-MOC 的 t99 为 **70.67–98.56%**，所以 `t85_full` 不可横向比；详见 `docs/fmoc_initial.md`。

## 4.2 `.pridb` 补充口径

- **L1 C1/C2**：用 `evaluate_l1_hi_ae.hi_of_group` 的 500-cycle anchor（DFOS/FBG），并裁掉冲击前/寿命外 hit；单/多会话都走这条。1 s bin 仅在 anchor 缺失时 fallback。
- **L2**：用 `skills/metric/pridb.py` 的 session→cycle 表（与 `l2/scripts/l2_ae_scan.py` 同源），逐文件把时间映射到 cycle。
- **1 s bin**：L2 与 fallback 使用 SQL `GROUP BY Time/1e7`，`t_x` 在 bin 中心上线性插值；与逐 hit 的差异 <0.01 pp。
- **缓存**：`skills/cache/pridb_<stem>_<size>_<mtime>.npz`，按文件 mtime/size 失效；首次扫描慢，之后 <1 s。删缓存可重建。

## 5. 强制规则

1. 任何 t50/t85 必须带 `convention`（`linear` / `step`）和 `frame_s`；缺省视为 `linear, 600`。
2. 看板、报告、claim 三处必须是**同一个数**；L1-06 的看板已由 94.0 改为 93.76（UI 93.8）。
3. 旧表（`l1/results/l1_hi_crosslab.csv` 等）是步进口径；引用时必须注明，或按本标准重算。
4. 结果表只能作 display-only；claim 必须来自 raw → `skills/metric` → `tool_result`。
5. 任何 t_x 必须带 `coverage`（或 `t99`）；coverage < 0.95 的跨试件比较一律 `insufficient`。
