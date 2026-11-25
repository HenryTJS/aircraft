# dfos

## 目的

从原始分布式应变 CSV 计算**块级 HI 包络**和 0.25/0.50/0.70 预警 cycle，不读 `l1/results`。  
它回答“块级应变偏离有没有累积”，不回答“损伤在哪个坐标”。

## 输入

```json
{"gid": "L1-49", "base": "post"}
```

只支持 L1 C1/C2；`base` 取 `post`（冲击后前 10 段）或 `bi`（双向基准）。

## 输出

```json
{
  "gid": "L1-03",
  "modality": "DFOS",
  "n_blocks": 30,
  "hi_end": 1.0,
  "warn25_pct": 5.0,
  "warn50_pct": 5.0,
  "warn70_pct": 5.0,
  "tail_mono_pct": 100.0,
  "saturation": true,
  "n_f": 152458,
  "axis": "cycle",
  "coverage": null
}
```

`warn*_pct` 是预警 cycle 占 `n_f` 的百分比。  
`tail_mono_pct` 是末段单调比例；`saturation=true` 是工具边界标记：HI 到归一化上限 1.0，且三个阈值落在同一 block。它不等于物理饱和。

## 算法

1. `evaluate_l1_dfos.analyze(gid, base_mode=...)` 读原始 CSV 与 FBG/DFOS 块锚；
2. 每个 block 取空间剖面，算相对基线的局部峰偏离；
3. 按 p90 归一化，得到块级 HI；
4. 取 HI 首次达到 0.25/0.50/0.70 的 block cycle；`first_th` 用首个越阈块，不做线性插值；
5. 检查末段单调性和饱和。

## 规则

1. 只做块级包络，不做空间损伤图；DFOS 空间定位在本项目已证伪；
2. `base=post` 不是冲击前真健康态，报告里必须写；
3. HI 达归一化上限且三个阈值同 block 时，块级分辨率不足，不能分级；不能报“物理饱和”；
4. 现有 `analyze` 会写 `D:/shm/l1/results/_l1_dfos_hi_<gid>.npz`，这是复用产线的副作用，不是数值源；
5. 没有原始 CSV → `unsupported`；
6. 已用 `L1-03`、`L1-49` 验证：块数、`HI_end`、预警 cycle 与 `l1_dfos_metrics.csv` 一致；14 组 `HI_end` 全为 1.0，这是归一化上限；其中 11 组 0.25/0.50/0.70 同 block，块级分辨率不足。只有 L1-09、L1-23、L1-56 的阈值有区分。

## 命令

```powershell
python skills\dfos\run.py --gid L1-49 --json
python skills\dfos\run.py --gid L1-03 --base post --json
```
