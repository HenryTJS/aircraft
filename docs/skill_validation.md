# 独立工具验证记录（2026-11-24）

## 结论

三个工具都能从 raw 数据产出符合自身 schema 的 JSON，且与 `D:/shm/l1/results` 的既有产物对得上。  
三个工具已经接入 `tools/build_claim_graph.py` 和 `validate.py`，但只把各自可签的数值签成 claim；DFOS 同 block 阈值和 PZT 删失值以 `boundary` 字段标成 `insufficient`，不冒充 supported 点。

## 运行方式

```powershell
conda run --no-capture-output -n xjtushm python skills\fbg\run.py --gid L1-30 --json
conda run --no-capture-output -n xjtushm python skills\dfos\run.py --gid L1-03 --json
conda run --no-capture-output -n xjtushm python skills\pzt\run.py --gid L1-06 --json
```

必须加 `--no-capture-output`。普通 `conda run` 会把子进程输出按控制台编码重编码，中文变成 `鐨�`；这不是源码或 JSON 的问题。

## FBG

- `L1-30`：`n_windows=51`、`n_channels=10`、`n_f=10150`；`shape_rob25_first=0.014813`、`last=0.015593`、`median=0.015569`、`max=1.454694`、`centroid_drift=0.011286`。
- 与 `D:/shm/l1/results/_l1fbgprof_L1-30.npz` 的 `shape_rob25` 逐项一致。
- `L1-03`、`L1-23` 返回 `unsupported`，原因是加载窗少于 5 个。C1/C3 多数只有 1–2 个长 FBG 文件，不能算形状漂移；C4 多文件组可用。
- 51 个窗口是按 140 行切出的加载窗，按时间排序；窗口序号不是循环数/寿命分数。工具没有 t/载荷/循环锚，不能直接映射；单有 `n_f` 不够。
- 没有 t85。

## DFOS

- `L1-03`：`n_blocks=30`、`n_f=152458`、`hi_end=1.0`、`warn25/50/70=7622.9 cycle`、`tail_mono=100%`、`rmse_end=344.7`、`saturation=true`。
- `L1-49`：`n_blocks=90`、`n_f=43702`、`hi_end=1.0`、`warn25/50/70=273.1 cycle`、`tail_mono=100%`、`rmse_end=92.0`、`saturation=true`。
- 与 `D:/shm/l1/results/l1_dfos_metrics.csv` 一致。
- 全量 14 组 `HI_end` 都是 1.0。这是 `clip(local/p90, 0, 1)` 的归一化上限，不是物理饱和。11 组 0.25/0.50/0.70 落在同一 block，块级分辨率不足，不能给三个独立预警点；只有 `L1-09`、`L1-23`、`L1-56` 的三个阈值有区分。
- `L1-03` 的实际块级 HI 是 `0, 0.8614, 0.8614, 1.0, ...`，`p90=1031.16`；三个阈值都在第 2 个 block（约 7622.9 cycle）被越过，所以只能报一个共同下界，不能报“已饱和”。
- 这是块级包络，不是空间定位；`base=post` 不是冲击前真健康态。

## PZT

- `L1-06`：`n_states=39`、`life_min=5.1409%`、`life_max=100%`、`D_sum=5.267299`、`t50=66.8314%`、`t85=100.0%`、`tof_drift=1.232081 µs`、`tof_slope_ts=0.013583`、95% CI `[0.009705, 0.017855]`、`kendall_tau=0.6239`、`p=2.28e-8`、`coverage=0.9486`、`censored=true`。
- 与 `D:/shm/l1/results/pzt_crosslab_summary.csv` 的 `L1-06` 行逐项一致。
- `t85=100` 是寿命末端边界/删失，不是精确失效点。`L1-06` 在第一个 `life=100%` 状态累计 86.45%，已越过 85%，所以不能说“到寿命终点仍未越阈”；只能说不确定是 100% 前刚越阈还是 100% 处才越阈。
- PZT 的 `t_at` 是状态步进，和 AE 的线性插值不同，跨模态比较前必须统一口径。

## claim 接入

- `tools/build_claim_graph.py --tool fbg|dfos|pzt` 生成 `T001`、claim/evidence/edge，evidence 带 `tool_call_id`、`coverage`、`coverage_basis` 和 `boundary`。
- `validate.py` 用 `TOOL_RUNNERS` 独立重跑对应 skill；coverage 按 `coverage_basis` 分支。`boundary_consistency` 拒绝四种情况：FBG 窗口 claim 带非空 `cycle_anchor`；DFOS 阈值未分块却 supported；PZT 删失 t85 却 supported；PZT 未越阈却 supported。
- 已生成并校验：
  - `examples/L1-30_fbg.json`：supported，`cycle_anchor=null`、`coverage_basis=not_applicable`；
  - `examples/L1-03_dfos.json`：`hi_end` supported，`warn50_pct` insufficient，`threshold_resolved=false`；
  - `examples/L1-06_pzt.json`：t85 insufficient，`censored=true`、`threshold_reached=true`、`crossing_interval_pct` 为状态区间；
  - `examples/L1-13_pzt.json`：t85 supported，`censored=false`、coverage 0.9572、交叉区间 `[85.597, 87.737]`，允许上限 1.0 时通过。
- `tests/test_skill_claims.py` 7/7 通过；`tests/test_validate.py` 10/10 通过。
- DFOS 的 `coverage` 由 builder 补为 1.0，因为工具扫描全试验；其限制写在 `coverage_basis=block` 和 `threshold_resolved`，不是寿命覆盖不足。

## L1 短试验帧宽补充（2026-11-25）

`skills/metric/run.py` 增加 `FRAME_S_BY_GID`，对短 C4 组改帧宽：L1-30=60 s、L1-34=30 s、L1-36=60 s。原因与对照：

| gid | 帧宽 | raw t85 | canonical | 差 |
|---|---:|---:|---:|---:|
| L1-30 | 60 s | 94.3812 | 94.38 | 0.00 pp |
| L1-34 | 30 s | 82.6846 | 82.68 | 0.00 pp |
| L1-36 | 60 s | 84.8367 | 84.6992 | 0.14 pp |

600 s 帧对 L1-36 只剩 5 帧，给 77.82%，与看板 84.70 不可比；因此不能把 600 s 硬套到短试验。L1-36 的 0.14 pp 差异来自 43 帧 vs canonical 42 帧的边界取法，看板仍为 84.70，claim/API 为 84.84。

## 已做检查

- `py_compile` 三个工具通过；
- 三个 schema 对输出 `json.loads` 后 `jsonschema.validate` 通过；
- `skills/registry.json` 的 entry/contract/doc 路径全部存在；
- 三个模块可 import；
- `--json` 输出可被 JSON 解析，无前置打印。

## 当时未做（后续已补）

- 三个工具后来已接进 `web/planner.py` 和 `/api/ask`；
- C1 四模态冲突 case 已用 `build_conflict_graph()` 落地，`examples/L1-03_conflict.json` 通过 21 项 validator 检查；
- 仍未做批量组、超时、并发和缓存；
- 仍未提交 git。
