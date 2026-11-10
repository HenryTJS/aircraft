# F-MOC 初步分析（2026-11-10 修订）

> 数据：`E:\fmoc`；配置：`cases/fmoc.json`；代码：`tools/profile_fmoc.py --config`；明细：`docs/fmoc_initial.csv`。
> 结论先行：**F-MOC 可以配置驱动接入；`t85_full`（58.8–84.4%）被 AE 尾部稀释，不能横向比；用 DIC 最后一帧作 test_end 下界，`t85_dic` 为 81.4–86.2%，但仍不是 L1 口径。**

## 1. 数据与格式

| 项 | 内容 |
|---|---|
| 试件 | 7 个，`spec1`–`spec7` |
| 文件 | `E:\fmoc\ACOUSTIC\specN.pridb`，共 2.3 GB；`E:\fmoc\DIC` 约 15 GB，`specN_<seconds>.tif`，50 s 一帧 |
| 采集 | Vallen AMSY-6，8 通道，2 MHz，50 dB；`Time` 单位 100 ns（`ae_fieldinfo` Factor=1e-7） |
| 命中 | `ae_data.SetType=2`；全部在 `Chan=1`；每件 0.81–4.44 M hits |
| 试验 | CFRP 单向带 `[0/45/90/−45]`，400×45×2.28 mm；从完好跑到失效（数据说明） |

## 2. 方法

1. 配置驱动：`cases/fmoc.json` 给出 root、DIC 目录、`settype=2`、`time_factor=1e-7`、`axis=time`；
2. 只取 `SetType=2`，按 `Time` 排序，累积 hits / 能量；
3. `t_x` = 累积量达到终值 x% 的时刻，线性插值；
4. 寿命分数 = `(t_x − t_first) / (t_last − t_first) × 100`，即**观测 AE 窗口内的时间分数**；
5. `t99` = 99% 命中覆盖；`t85_active = t85/t99`；
6. `dic_last` = 该试件最后一张 DIC 的时间戳（秒）；`t85_dic = t85_s / dic_last × 100`；
7. 不建 cycle 轴、不去 pause：文件里没有循环计数，`ae_markers` 只有少量 `Suspend/Resume`。

复算：

```powershell
cd D:\aircraft
python tools\profile_fmoc.py --config cases\fmoc.json --out docs\fmoc_initial.csv
```

## 3. 结果

| 试件 | hits | 时长 (h) | t85_full | t99 | t85_active | DIC 末帧 (h) | **t85_dic** | AE/DIC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| spec1 | 2,994,127 | 16.02 | 84.39 | 98.56 | 85.63 | 15.70 | 86.17 | 1.021 |
| spec2 | 812,797 | 4.40 | 74.55 | 90.14 | 82.72 | 3.99 | 82.23 | 1.103 |
| spec3 | 2,922,729 | 19.65 | 71.14 | 85.31 | 83.39 | 16.56 | 84.44 | 1.187 |
| spec4 | 2,389,220 | 19.11 | 58.78 | 70.67 | 83.19 | 13.40 | 83.94 | 1.427 |
| spec5 | 1,538,064 | 9.47 | 71.38 | 87.84 | 81.28 | 8.32 | 81.36 | 1.140 |
| spec6 | 4,032,218 | 19.12 | 82.99 | 98.19 | 84.53 | 19.11 | 83.08 | 1.001 |
| spec7 | 4,436,308 | 22.54 | 75.91 | 93.62 | 81.09 | 20.88 | 81.98 | 1.080 |

- `t85_full`：中位 **74.55%**，范围 **58.78–84.39%**。
- `t85_dic`：中位 **83.08%**，范围 **81.36–86.17%**。
- `t99` 与 `dic_last` 高度重合：例如 spec4 的 `t99=70.67% × 19.11 h = 13.5 h`，DIC 末帧 **13.4 h**；spec5 的 `87.84% × 9.47 = 8.32 h`，DIC **8.32 h**。

## 4. 关键发现：尾部稀疏 + DIC 末帧

1. **`t85_full` 低，主要是 AE 尾部稀疏**：spec4 最后 10% 时间窗 0 个 hit，第 9 个十分位也是 0；99% 的 hit 在 70.67% 处就到齐了。
2. **DIC 末帧 ≈ t99**，七个试件都成立（见上表）。这说明 DIC 停机时刻和“AE 基本停止”是同一时刻；AE 记录多出来的那段（`AE/DIC` 1.001–1.427）只有约 1% 的 hit，最可能是停机后噪声/尾记录。
3. 因此 **`t85_dic` 比 `t85_full` 更接近真实寿命分数**；`t85_active` 和 `t85_dic` 数值接近（81–86%），互相印证。
4. 但 **DIC 末帧只是 test_end 的下界**：如果试验在 DIC 停机后还继续，真实 test_end 更大，`t85_dic` 会偏大。表里 `AE/DIC` 列就是“AE 超出 DIC 的比例”，也是这个不确定性的量级。
5. **hit 与能量口径仍不一致**：spec2 用 hits 74.6、能量 86.0；spec3 71.1 vs 60.5。单一口径不足以支撑损伤结论。

## 5. 边界（写报告必须带）

- `axis=time`，不是 `docs/metric_standard.md` 的 cycle-fraction 标准；不能和 L1 的 89–94% 同轴比较。
- `t85_dic` 的分母是 DIC 末帧，**不是独立验证的失效时刻**；`test_end_uncertain=true` 的试件（AE/DIC >1.02）只能当敏感性值。
- 没有 cycle 轴、没有 pause 掩码；`ae_markers` 只有少量 Suspend/Resume。
- 7 个试件、同一实验室（TU Delft）、同一批次；**不是跨机构**。
- 只分析了 AE；DIC 15 GB 未做位移/应变交叉验证。
- F-MOC 原生任务是疲劳寿命预测；t85 是外加描述量，不是数据集标签。

## 5.1 论文核对（2026-11-10）

- 开放获取 F-MOC 论文（Komninos et al., *Data-Centric Engineering*，DOI `10.1017/dce.2025.10031`）已下载到 `docs/refs/fmoc_paper.pdf`（13 MB）。
- 论文原文写的是 `cyclic loading with specified intervals and load transitions ... varying stress conditions`——**没有给加载频率/循环数**，而且不是单一恒幅。
- 因此 **F-MOC 无法从论文重建 cycle 轴**；`axis=time` 仍是当前唯一诚实口径，`t85_dic` 仍只是 test_end 下界下的敏感性值。
- 用户给的 DOI `10.4233/uuid:538558fb-...` 是 Eleftheroglou 2020 博士论文（TU Delft，28.9 MB，直链 `https://research.tudelft.nl/files/83535609/Thesis_1.pdf`）；当前环境被 Cloudflare 403 / 仓库超时，**未下载**。

## 6. 下一步

1. **cycle 轴**：从论文/试验记录找加载频率；没有就仍保持 `axis=time`，不要伪造 cycle。
2. **pause 掩码**：用 `ae_markers` + hit 间隔（如 >60 s 无 hit）重建加载时间，重算并对比。
3. **DIC 交叉验证**：抽 2–3 个试件，检查 DIC 末帧附近的位移/应变是否已到失效；若已失效，`t85_dic` 可从“敏感性”升级为“可用”。
4. **三口径对照**：hits / 能量 / 幅值阈值各算一次，选物理上说得清的口径，写进 `scope.indicator`。
5. **作为“未知数据集”演示**：只改 `cases/fmoc.json`，核心代码 0 行；输出 `axis=time`、`indicator=hits`、`coverage`、`test_end_uncertain`，明确“不可与 L1 比”。
