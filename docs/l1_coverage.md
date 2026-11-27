# L1 覆盖审计

生成命令：`python tools/audit_l1_coverage.py`。

这份表只回答“注册/展示/验证”三种状态，不把注册当成验收。

## 总览

- 注册 gid：29
- 工具计数：metric 29、pzt 20、dfos 14、fbg 9、workflow 2、conflict 1
- dashboard 有预计算包：29/29
- 有 metric 缓存：27/29
- 至少跑过一次 raw metric：29/29（见 `docs/l1_metric_audit.md`）
- 端到端验证过：29/29

## 逐组

| gid | 批次 | tools | dashboard t85 | convention | cache | PZT 汇总 | DFOS 汇总 | FBG 窗 | 已端到端验证 | 备注 |
|---|---|---|---:|---|---|---|---|---:|---|---|
| L1-03 | C1 | metric,dfos,pzt,conflict | 85.17 | linear,500cycle,anchor | yes | yes | yes | — | yes |  |
| L1-04 | C1 | metric,dfos,pzt | 97.26 | linear,500cycle,anchor | yes | yes | yes | — | yes |  |
| L1-05 | C1 | metric,dfos,pzt | 88.72 | linear,500cycle,anchor | yes | yes | yes | — | yes |  |
| L1-09 | C1 | metric,dfos,pzt | 95.49 | linear,500cycle,anchor | yes | yes | yes | — | yes |  |
| L1-23 | C1 | metric,dfos,pzt | 89.14 | linear,500cycle,anchor | yes | yes | yes | — | yes | FBG removed: fewer than 5 loading windows |
| L1-49 | C2 | metric,dfos | 82.24 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-50 | C2 | metric,dfos | 97.31 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-51 | C2 | metric,dfos | 68.18 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-52 | C2 | metric,dfos | 95.76 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-54 | C2 | metric,dfos | 88.39 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-55 | C2 | metric,dfos | 87.08 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-56 | C2 | metric,dfos | 92.14 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-59 | C2 | metric,dfos | 98.33 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-60 | C2 | metric,dfos | 93.16 | linear,500cycle,anchor | yes | — | yes | — | yes |  |
| L1-06 | C3 | metric,pzt,workflow | 93.76 | linear,600s,load-mask | yes | yes | — | — | yes |  |
| L1-13 | C3 | metric,pzt,workflow | 93.05 | linear,600s,load-mask | yes | yes | — | — | yes |  |
| L1-14 | C3 | metric,pzt | 83.56 | linear,600s,load-mask | yes | yes | — | — | yes |  |
| L1-22 | C3 | metric,pzt | 96.54 | linear,600s,load-mask | yes | yes | — | — | yes | 20.7 GB AE, cold API ~365 s; raw parsing dominates |
| L1-24 | C3 | metric,pzt | 96.33 | linear,600s,load-mask | yes | yes | — | — | yes |  |
| L1-25 | C4 | metric,fbg,pzt | 93.88 | linear,600s,load-mask | yes | yes | — | 3071 | yes |  |
| L1-27 | C4 | metric,fbg,pzt | 83.06 | linear,600s,load-mask | yes | yes | — | 1020 | yes |  |
| L1-29 | C4 | metric,fbg,pzt | 94.09 | linear,600s,load-mask | yes | yes | — | 3105 | yes |  |
| L1-30 | C4 | metric,fbg,pzt | 94.38 | linear,60s,load-mask | — | — | — | 27 | yes | short trial: metric uses 60 s frames |
| L1-31 | C4 | metric,fbg,pzt | 89.50 | linear,600s,load-mask | yes | yes | — | 2420 | yes |  |
| L1-34 | C4 | metric,pzt | 82.68 | linear,30s,load-mask | — | — | — | — | yes | short trial: metric uses 30 s frames; no FBG |
| L1-35 | C4 | metric,fbg,pzt | 89.42 | linear,600s,load-mask | yes | yes | — | 1779 | yes |  |
| L1-36 | C4 | metric,fbg,pzt | 84.70 | linear,60s,load-mask | yes | — | — | 10 | yes | short trial: metric uses 60 s frames; raw 84.84 vs dashboard 84.70 |
| L1-41 | C4 | metric,fbg,pzt | 99.14 | linear,600s,load-mask | yes | yes | — | 2688 | yes |  |
| L1-44 | C4 | metric,fbg,pzt | 87.76 | linear,600s,load-mask | yes | yes | — | 1849 | yes |  |

## 解释

- `dashboard t85` 是预计算展示包，不是本次 raw 重算结果。
- `cache=yes` 只表示本地有 `skills/cache/metric_<gid>.json`，不代表该缓存仍对应当前代码。
- `PZT/DFOS 汇总` 只表示结果表里有该 gid，不代表该 gid 已接入 claim。
- `FBG 窗` 是原始 `.txt` 文件数；少于 5 个加载窗时 `fbg.profile` 会拒绝。
- `已端到端验证` 只覆盖 claim/validator/API 至少跑通过一次的 gid；其余仍需逐个跑 raw。

