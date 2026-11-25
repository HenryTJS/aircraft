# fbg

## 目的

从原始 FBG 文本计算**应变剖面形状**和载荷窗覆盖，不读 `l1/results`，不输出 t85。  
它回答“光纤测到的应变分布有没有迁移”，不回答“结构还剩多少寿命”。

## 输入

```json
{"gid": "L1-03"}
```

只支持 `L1-xx`，且原始目录 `E:/l1/<gid>/FBG/*.txt` 必须存在。
要求至少有 5 个加载窗；C1/C3 多数组只有 1–2 个长文件，加载窗不足，会返回 `unsupported`。C4 多文件组可用。

## 输出

```json
{
  "gid": "L1-30",
  "modality": "FBG",
  "n_windows": 51,
  "n_channels": 10,
  "p2p_med": 1941.287,
  "shape_rob25_first": 0.014813,
  "shape_rob25_last": 0.015593,
  "shape_rob25_max": 1.454694,
  "centroid_drift": 0.011286,
  "n_f": 10150,
  "axis": "window",
  "coverage": null
}
```

`shape_rob25` 是每个加载窗的 10 通道 P2P 归一化剖面，与前 25% 加载窗中位剖面的 L1 距离。  
`axis="window"` 表示这是加载窗序号，不是寿命分数；窗口序号不能直接映射成 cycle，必须有 t/载荷/循环锚，当前工具没有。

## 算法

1. `fbg_tools.group_profile(gid, root="E:/l1")` 扫描原始 FBG 文本；
2. 每个文件按加载窗取 10 通道 P2P；
3. 每个窗除以自身中位 P2P，得到形状；
4. 以最早 25% 加载窗的中位形状为基线，算 L1 距离；
5. `centroid_drift` 是通道重心相对基线的漂移。

## 规则

1. skill 层不读 `results/`，也不读看板预计算包；
2. 没有原始 FBG 目录 → `unsupported`，不猜；
3. 窗口轴不能当寿命轴；要 cycle 必须另给同步的 t/载荷/循环锚，单有 `n_f` 不够；
4. 光纤应变受载荷、温度、停机影响，不能单独当损伤度；
5. 当前只做形状，不做空间定位，不做裂纹长度；
6. 已用 `L1-30` 验证：51 窗、10 通道，`shape_rob25_last=0.015593`，与 `_l1fbgprof_L1-30.npz` 一致；`L1-03`、`L1-23` 因加载窗不足返回 `unsupported`。

## 命令

```powershell
python skills\fbg\run.py --gid L1-03 --json
```
