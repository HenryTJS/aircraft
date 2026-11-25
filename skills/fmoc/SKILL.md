# fmoc.profile

F-MOC 未知数据入口。读取 `E:/fmoc/ACOUSTIC/specN.pridb` 的原始 Vallen
`ae_data`，按 `Time` 排序后对 hit 累积曲线取 50/85/99% 的时间点。

## 输入

- `gid`：`spec1`–`spec7`，必须存在于 `cases/fmoc.json` 的 `specimens`。
- 配置：`cases/fmoc.json` 的 `root`、`dic_dir`、`settype=2`、`time_factor=1e-7`。

## 输出

- `t85_hit_pct`：观测时间窗口内，hit 累积到 85% 的时间分数。不是 cycle
  分数，不是 RUL。
- `t85_dic_pct`：`t85_s / dic_last_s`，DIC 末帧只作为 test_end 的下界。
- `test_end_uncertain`：AE 记录超过 DIC 末帧 2% 以上时为 true。
- `coverage` 固定为 1.0，表示扫描了该试件的完整 AE 记录；`coverage_basis`
  为 `lifetime`，但寿命轴是观测时间。
- `axis="time"`、`indicator="hits"`。

## 边界

- 没有 cycle 日志，不能建 cycle 轴，不能与 L1 的 cycle-fraction 直接比较。
- 尾部 hit 稀疏，`t85_hit_pct` 容易被拉低；`t85_dic_pct` 是敏感性值，不是
  独立验证的失效时刻。
- 只分析 AE；DIC 15 GB 尚未做位移/应变交叉验证。
- 七个试件同实验室同批次，不是跨机构泛化证据。

## 运行

```powershell
conda run -n xjtushm python skills/fmoc/run.py --gid spec2 --json
```
