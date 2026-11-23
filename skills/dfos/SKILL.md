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
  "gid": "L1-49",
  "modality": "DFOS",
  "n_blocks": 24,
  "hi_end": 0.81,
  "warn25_pct": 42.3,
  "warn50_pct": 68.1,
  "warn70_pct": 79.5,
  "tail_mono_pct": 91.2,
  "saturation": false,
  "n_f": 251000,
  "axis": "cycle",
  "coverage": null
}
```

`warn*_pct` 是预警 cycle 占 `n_f` 的百分比。  
`tail_mono_pct` 是末段单调比例；`saturation=true` 表示 HI 到 1.0 且三个预警同刻。

## 算法

1. `evaluate_l1_dfos.analyze(gid, base_mode=...)` 读原始 CSV 与 FBG/DFOS 块锚；
2. 每个 block 取空间剖面，算相对基线的局部峰偏离；
3. 按 p90 归一化，得到块级 HI；
4. 在 0.25/0.50/0.70 处插值得到预警 cycle；
5. 检查末段单调性和饱和。

## 规则

1. 只做块级包络，不做空间损伤图；DFOS 空间定位在本项目已证伪；
2. `base=post` 不是冲击前真健康态，报告里必须写；
3. HI 饱和时不能分级，只能报“已饱和”；
4. 现有 `analyze` 会写 `D:/shm/l1/results/_l1_dfos_hi_<gid>.npz`，这是复用产线的副作用，不是数值源；
5. 没有原始 CSV → `unsupported`。

## 命令

```powershell
python skills\dfos\run.py --gid L1-49 --json
python skills\dfos\run.py --gid L1-03 --base post --json
```
