# pzt

## 目的

从原始 PZT 导波 `.mat` 状态计算**相邻状态退相关累积**的 t50/t85 和 TOF 漂移，不读 `l1/results`。  
它回答“导波波形有没有持续变化”，不回答“裂纹有多长”。

## 输入

```json
{"gid": "L1-06", "stride": 1}
```

只支持 `pzt_crosslab.BATCH` 中的 L1 组；`stride>1` 表示状态抽样，寿命轴仍按完整序号。

## 输出

```json
{
  "gid": "L1-06",
  "modality": "PZT",
  "n_states": 39,
  "life_min_pct": 5.14,
  "life_max_pct": 100.0,
  "D_sum": 5.267299,
  "t50_pct": 66.8314,
  "t85_pct": 100.0,
  "tof_drift_us": 1.232081,
  "tof_slope_ts": 0.013583,
  "coverage": 0.9486,
  "censored": true,
  "n_f": 202300,
  "axis": "cycle"
}
```

`D_sum` 是 56 条路径相邻状态退相关中位的累积。  
`censored=true` 表示 t85 落在寿命末端或没有真正越阈。

## 算法

1. `pzt_crosslab.run_group(gid)` 读每个状态的 8 个 `.mat`，共 56 条路径；
2. 每条路径做相邻状态退相关，取中位得到 `D`；
3. 在寿命轴上累积 `D`；
4. 取 `D` 的累积曲线首次达到 50%/85% 的状态，得到 t50/t85；`pzt_crosslab.t_at` 用状态步进，不做线性插值；
5. 另算 TOF 漂移的 Theil–Sen 斜率与 95% CI。

## 规则

1. `D` 不是裂纹长度，也不是损伤物理量；
2. t85=100 是寿命末端边界/删失，不能当精确失效点；不能据此说“仍未越阈”；
3. TOF 斜率下界 <= 0 时趋势不显著；
4. 只允许 `pzt_crosslab.BATCH` 中的组，其他组 `unsupported`；
5. 工具可能很慢，单组几十秒到几分钟；先小规模验证再批量；
6. 不读 `_l1cyc` / `l1_hi_ae`，`nf_of` / `life_map` 已覆盖；
7. 已用 `L1-06` 验证：`n_states=39`、`t50=66.8314`、`t85=100.0`、`D_sum=5.2673`、`coverage=0.9486`，与 `pzt_crosslab_summary.csv` 一致；在第一个 `life=100%` 状态累计 86.45%，已越过 85%，不能说“仍未越阈”，只能报“落在寿命末端，无法区分之前还是 100% 处越阈”。

## 命令

```powershell
python skills\pzt\run.py --gid L1-06 --json
python skills\pzt\run.py --gid L1-25 --stride 2 --json
```
