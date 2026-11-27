# 多模态 claim 接入的三级审查

日期：2026-11-25  
范围：`skills/fbg`、`skills/dfos`、`skills/pzt`、`skills/fmoc` → `tools/build_claim_graph.py` → `validate.py` → `web/planner.py` → `/api/ask` → `web/static/assistant.js`。

本轮审查的是“接入是否正确”，不是“物理结论是否成立”。所有数值 claim 都来自 raw 工具的确定性输出，LLM 只输出白名单计划。

## 1. 事实来源

| claim | 数值 | raw 来源 | 交叉核对 | 结论 |
|---|---:|---|---|---|
| L1-30 FBG `shape_rob25_last` | 0.015593122804356103 | `E:\l1\L1-30\FBG` | 与 `_l1fbgprof_L1-30.npz` 一致；validator 重跑一致 | 可复核 |
| L1-03 DFOS `hi_end` | 1.0 | `E:\l1\L1-03\L1-03分布式应变.csv` | `l1_dfos_metrics.csv` 一致；validator 重跑一致 | 可复核，但只是块级归一化上限 |
| L1-03 DFOS `warn50_pct` | 5.0 | 同上 | 25/50/70 落在同一 block，`threshold_resolved=false` | 只能标 insufficient |
| L1-13 PZT `t85_pct` | 87.73662551440329 | `E:\l1\L1-13` 的 PZT `.mat` | `pzt_crosslab_summary.csv` 一致；validator 重跑一致 | 可复核，状态步进 |
| L1-06 PZT `t85_pct` | 100.0 | `E:\l1\L1-06` 的 PZT `.mat` | 与 summary 一致；`censored=true`，coverage 0.9486 | 只能标 insufficient |
| spec2 F-MOC `t85_hit_pct` | 74.55 | `E:\fmoc\ACOUSTIC\spec2.pridb` | 与 `docs/fmoc_initial.md` 一致；validator 重跑一致 | 可复核，时间轴不是 cycle |
| spec2 F-MOC `t85_dic_pct` | 82.23 | `E:\fmoc\DIC` 末帧 | `test_end_uncertain=true`；末帧只是下界 | 只能标 insufficient |

事实源检查结论：

- `web/app.py` 的 `_answer()` 只格式化 claim 的 `value`，不调用模型生成数字。
- `web/planner.py` 的 `Plan` 没有 value 字段；LLM 只返回 intent/tool/gid/metrics/base/stride。
- `validate.py` 的 `tool_reexecution` 会重跑对应 skill，数值不一致时失败。
- 仍有一个必须写明的限制：validator 重跑的是同一套 `skills/*` 实现，不是第二套独立物理算法。它能抓“图与工具不一致”，不能证明“工具物理正确”。

## 2. 逻辑合理性

### 2.1 planner

- 白名单：gid 由 `cases/l1.json` 注册 29 个 L1，加上 `cases/fmoc.json` 的 `spec1`–`spec7`；每个 gid 的 tool 由 `web/datasets.py::load_supported()` 限定。F-MOC 只允许 `fmoc`。
- LLM 返回的 plan 必须通过 `_parse_plan()` 的 intent/tool/gid/metric/base/stride 校验；越界或 gid 不匹配会回退到规则解析，不会进入工具。
- 问题显式点名工具而 LLM 选了另一个工具时，`compile_question()` 会拒绝该 plan 并回退。例如 L1-06 上问 `PZT t85`，不会被当成 AE metric。
- LLM 过度拒答时，只有规则解析能识别出显式非 metric 工具才允许恢复；预测、RUL、损伤类型、维修建议仍然拒绝。
- 规则回退先检查 blocked 词，再看工具关键词；同时点名多个工具时返回 unsupported。

### 2.2 claim 状态

- FBG：`shape_rob25_last` 是窗口轴形状指标，`cycle_anchor=null`，没有寿命门；`coverage_basis=not_applicable`。
- DFOS：`hi_end` 是块级归一化包络，可以 supported；`warn50_pct` 只有在 `threshold_resolved=true` 时才 supported，否则 insufficient 并写 `missing_evidence`。
- PZT：只有 `censored=false` 且 `coverage>=0.95` 才 supported；删失或覆盖不足一律 insufficient。`crossing_interval_pct` 是状态区间，不是精确点。
- validator 的 `boundary_consistency` 会拒绝“supported 但 boundary 说未 resolved/已删失/未越阈/窗口有 cycle anchor”的组合。
- validator 的 temporal gate 在 retrospective 模式下比较 claim 的百分数值与 `allowed_lifetime_max`；PZT L1-13 在 `t=0.80` 被拒，`t=0.95` 通过。

### 2.3 API 状态

`_evaluate()` 的返回顺序：

1. validator 有 failed → `refused`，不返回 graph。
2. 没有 supported claim → `insufficient`，返回 graph 和边界原因。
3. 部分 claim insufficient → `partial`，返回 graph，前端逐条标状态。
4. 全部 supported → `ok`；FBG 的 gate 是 `not_applicable`，其他是 `pass`。

`/api/ask` 不会把 `insufficient` 当成 `ok`，也不会把 `refused` 的 graph 返回。前端对 `ok`、`partial`、`insufficient`、`refused`、`unsupported` 分别渲染。

### 2.4 C1 冲突 case

`build_conflict_graph("L1-03")` 把四个模态的可用性放进一张图：

| claim | predicate | status | 依据 |
|---|---|---|---|
| C001 | AE `t85_pct=85.167` | supported | `skills/metric`，coverage 0.9905 |
| C002 | DFOS `hi_end=1.0` | supported | 块级归一化上限，`threshold_resolved=false` |
| C003 | DFOS `warn50_pct=5.0` | insufficient | 25/50/70 同 block，不能给三个预警点 |
| C004 | PZT `t85_pct=100.0` | insufficient | `censored=true`，交叉区间 `[98.388,100.0]` |
| C005 | FBG limitation | insufficient | 原始只有 2 个加载窗，`fbg.profile` 要至少 5 个 |

API 返回 `partial`，graph 保留 5 条 claim，FBG limitation 没有 evidence/tool_call，validator 不要求它重跑。结论是“不能给出四个可比的 t85”，而不是把四个数排成四个寿命点。

### 2.5 F-MOC

`build_skill_graph("fmoc","spec2")` 生成两条 claim：

- C001 `t85_hit_pct=74.55`，status `supported`，allowed=`t_max`，boundary `time_axis=true`、`test_end_uncertain=true`、`dic_last_h=3.99`；它是观测时间轴上的 hits 分位，不是 cycle 寿命。
- C002 `t85_dic_pct=82.23`，status `insufficient`，allowed=None，原因是 DIC 末帧只给出 test_end 下界，`test_end_uncertain=true` 时不能签 supported。

validator 的 `boundary_consistency` 要求 `t85_hit_pct` 的 `time_axis=true`，并拒绝把 `test_end_uncertain=true` 的 `t85_dic_pct` 标 supported。API 对 `spec2` 返回 `partial`；`t=0.70` 时 C001 超过 allowed，返回 `refused`。

### 2.6 最小两步 workflow

`build_workflow_graph("L1-13")` 生成两条独立工具 claim 和一条派生 claim：

- C001 AE `t85_pct=93.0488`，`supported`，allowed=`t_max`。
- C002 PZT `t85_pct=87.7366`，`supported`，coverage 0.9572。
- C003 `t85_gap_pp=5.312145`，`comparative`，`evidence_ids=[E001,E002]`，`tool_call_ids=[T001,T002]`；值由 raw t85 直接相减，不由模型生成。

validator 对 C001/C002 各自重跑工具，对 C003 跳过单条 `numeric_value`，改走 `derived_value`，从 E001/E002 的 `t85_pct` 重算差并卡 `tolerance=0.01`。示例 `examples/L1-13_workflow.json` 通过 20 checks。API t=.95 返回 `ok`，3 条 claim；t=.80 时 C001 超 allowed，返回 `refused`，不返回 graph。

2026-11-25 用 headless Edge + CDP 在真实页面上点了一次 workflow。t=.95 显示 `已核验通过 · 0 failed / 20 checks`，三张 claim 卡和两条 evidence/tool 链都在；t=.80 显示时间门拒答，页面明确“未返回任何 claim、evidence 或 tool_call”。截图保存在 `docs/evidence/workflow_ok.png` 和 `docs/evidence/workflow_refused.png`。

这里的“多步”是固定两步，不是任意 workflow DSL；C003 只做一致性检查，不能写成 RUL 偏差。

### 2.7 direct-ask 入口

`resolve_gid()` 只认问题里显式写出的 `L1-xx` 或 `specN`。没写就用当前看板；多个或未知 gid 返回 `unsupported`，不猜试件。`resolve_t()` 只认 `t=0.8` 或在 80% 时这类写法；裸 `85%` 不会被当作 t。问题没写 t 时，direct ask 默认 `t=1.0`，做全寿命回顾，不沿用滑杆。

`/api/ask` 的 `gid`/`t` 都可选，响应统一带 `resolved={gid,t,gid_source,t_source}`。`unsupported` 的 multiple/unknown/missing 三种情况带不同 message，不建 claim 图。

2026-11-25 用 headless Edge + CDP 从 L1-06 页面直接提问：`L1-13 先查 AE t85 再查 PZT t85 做一致性判断` 自动切到 L1-13，t=100%，返回 `已核验通过 · 0 failed / 20 checks`，3 条 claim；`L1-13 在 80% 时 t85 的结论是什么` 返回时间门拒答，无 graph。截图在 `docs/evidence/direct_ok.png` 和 `direct_refused.png`。

这个入口仍然只支持白名单 gid，不是通用问答；它解决的是“问题自己带试件和时间”，不是“任意数据都能问”。

### 2.8 L1 全量注册与短帧例外

`cases/l1.json` 注册 29 个 L1 gid，`web/datasets.py::load_supported()` 合并 F-MOC 后返回 36 个 gid；`web/app.py` 不再手写 `SUPPORTED`。工具数：metric 29、pzt 20、dfos 14、fbg 9、workflow 2、conflict 1。

短 C4 组 L1-30 / L1-34 / L1-36 的 AE 只覆盖试验的一小段。`skills/metric/run.py` 用 `FRAME_S_BY_GID` 改为 60 / 30 / 60 s 帧，否则 600 s 只剩 2–13 帧：

| gid | 帧宽 | raw t85 | canonical | 差 |
|---|---:|---:|---:|---:|
| L1-30 | 60 s | 94.3812 | 94.38 | 0.00 pp |
| L1-34 | 30 s | 82.6846 | 82.68 | 0.00 pp |
| L1-36 | 60 s | 84.8367 | 84.6992 | 0.14 pp |

L1-36 的差异来自 43 帧 vs canonical 42 帧的边界取法。看板仍显示 84.70，API/claim 用 84.84；报告必须写清帧宽和来源，不能把两者当同一个数。其它 C3/C4 组仍用 600 s。

### 2.9 测试

- `tests.test_validate`：10/10
- `tests.test_skill_claims`：9/9
- `web.tests.test_planner`：34/34
- `web.tests.test_api`：28/28
- `web.tests.test_asof`：7/7
- 合计 88/88 通过；2026-11-27 全量 197.688 s。

浏览器点击验证：

- L1-30 FBG：`已核验通过 · 0 failed / 10 checks`，panel `证据约束分析 · L1-30`，chain `C001 ← E001 ← T001`。
- L1-03 DFOS：`部分签发 · 0 failed / 13 checks`，C001 supported，C002 insufficient。
- L1-06 PZT：`不签发 · 0 failed / 9 checks`，t85=100 删失，明确写“不签发点估计”。
- L1-03 conflict：`部分签发 · 0 failed / 21 checks`，5 条 claim，答案明确“不能给出四个可比的 t85”。
- direct-ask：从 L1-06 页面输入 L1-13 workflow 问题，自动切 gid，`已核验通过 · 0 failed / 20 checks`；再输入“在 80% 时”问题，时间门拒答，无 graph。

### 2.10 L1-13 / main-016 as-of 前缀

`/api/asof` 不读全寿命 `t85`，只读 `prefix/L1-13.npz` 或 `prefix/main-016.npz` 中查询 cycle 之前的帧。响应显式写 `boundary.t85_available=false`、`contains_future=false`，不返回 `n_f` 或全寿命总 hits。L1-13 的 `PZT` 取最近一个不晚于查询 cycle 的状态，`age_cycles` 明确标注落后量；main-016 返回 `frame_energy`、`cum_energy`、`ce_log`，这是记录进度，不是损伤度或 RUL。

`test_future_invariance` 把 L1-13 prefix 截到 100000 再查同一 cycle，`state`、`pzt`、`asof` 与完整 prefix 完全一致；`test_main_future_invariance` 对 main-016 做同样检查。浏览器端从 L1-13 看板点“当前时刻状态”，实测返回约 `230,388 cycle`、`9,247,312` 累计 hits、PZT `D=0.036`、`ΔTOF=2.00 µs`，无 `t85`。main-016 目前通过 API 查询，尚未接主样本看板。这两条仍是单条轨迹，不是全量在线监测。

## 3. 未证实与边界

以下内容不能从本轮测试推出：

1. **DFOS coverage=1.0 是补值**。工具扫全试验，但没有逐块覆盖字段；builder 在 `build_skill_graph()` 里补 1.0 并在 `coverage_basis=block` 说明块级限制。它不是 raw 的逐块覆盖率。
2. **PZT t85=100 是删失边界**。第一个 `life=100%` 状态累计已过 85%，无法区分“100% 前越阈”还是“100% 处越阈”。
3. **PZT 与 AE 的 t85 口径不同**。PZT 是状态步进，AE 是线性插值；跨模态比较前必须统一，不能直接说“谁更早”。
4. **FBG 不是寿命指标**。`shape_rob25_last` 的轴是加载窗，不是 cycle 或 lifetime；它不能回答“还剩多少寿命”。
5. **同源重跑不是独立物理验证**。validator 重跑同一 skill，只能证明图和工具一致。
6. **F-MOC 只覆盖 AE 时间轴**。`spec1`–`spec7` 已进 `/api/ask`，但 L2、主样本、RUL 仍未进；`postMessage`、claim↔图、报告导出仍未做。
7. **LLM 语义质量没有开放集证据**。30 题闭集和 11 题 hard set 都是同一人编写题目与规则，规则饱和；裸 API 对照只覆盖 10 题，不能证明 LLM 在未知表达上更强。
8. **冷启动仍约 30 s**。API 和 verifier 各跑一次 raw；PZT 单次约 3 s 到数十秒。
9. **改动未提交 git**。`README.md`、`SKILLS.md`、schema、三个 skill、builder、validator、`web/` 都还在工作区。
10. **冲突 case 的浏览器点击已做一次**。2026-11-25 用 headless Edge + CDP 点击 L1-03 conflict，返回 `部分签发 · 0 failed / 21 checks`，5 条 claim；没有做多浏览器或重复稳定性测试。
11. **冲突 case 的旧表数值不可用**。`four_modal.csv` 的 L1-03 AE/FBG/DFOS/PZT 为 76.29/94.86/88.04/98.78，但当前 raw 工具给 AE 85.17、PZT 100、DFOS 1.0/5.0、FBG 覆盖不足；旧表只能当历史参考，不能当 evidence。
12. **F-MOC 的 t85 不是 cycle 寿命**。`t85_hit_pct` 是观测时间轴上的 hits 分位；DIC 末帧只给 test_end 下界，`test_end_uncertain=true` 时 `t85_dic_pct` 只能标 insufficient。API 的 `t` 对 F-MOC 是允许观测时间分数，不是 RUL；temporal gate 只表示结论落在允许观测窗口内，不能写成寿命预测。F-MOC 未做浏览器点击复验。
13. **F-MOC 只对 spec2 做了端到端 API 验证**。`spec1`–`spec7` 都在 `SUPPORTED` 且走同一 `skills/fmoc` 路径，但本轮的 claim/validator/API 实测只覆盖 `spec2`；其余试件未逐个跑通，不能写成“7 个试件全部验收”。
14. **workflow 浏览器点击已做一次**。2026-11-25 用 headless Edge + CDP 点击 L1-13 workflow，t=.95 返回 `已核验通过 · 0 failed / 20 checks`，3 条 claim；t=.80 返回时间门拒答，无 graph。截图在 `docs/evidence/workflow_ok.png` 和 `docs/evidence/workflow_refused.png`。没有做多浏览器或重复稳定性测试。
15. **direct-ask 的上下文解析是规则，不是语义理解**。`resolve_gid()` 只认 `L1-xx`/`specN`；`resolve_t()` 只认 `t=0.8` 或“在/当/允许 80%”。没写 gid 用当前看板，没写 t 默认 1.0；多个/未知 gid 拒答。它不解决指代、省略试件或“上一个问题”的上下文；这些仍会拒答或落到 fallback。
16. **29 个 L1 gid 已逐个跑过 claim/validator/API，但仍不是物理正确性验收**。`cases/l1.json` 注册 29 组，`web/datasets.py` 合并出 36 个 gid；`docs/l1_coverage.md` 记录 29/29 端到端。短 C4 组 L1-30/L1-34/L1-36 用 60/30/60 s 帧，L1-36 raw 84.84% 与看板 84.70% 差 0.14 pp；报告必须写帧宽和来源。

17. **Dashboard 的 PZT 面板是显示层，不是新的 claim 工具**。`dashboard/data/pzt.js` 由 `tools/build_dashboard_pzt.py` 从 `D:/shm/l1/results/pzt_crosslab.csv` 与 `pzt_crosslab_summary.csv` 生成，覆盖 17 个 L1 gid；没有 PZT 的组显示“未采 PZT”。面板标题已写“离线汇总”，但它的曲线不是 API 或 validator 的 raw 重算结果，不能当作 claim 证据。
18. **PZT 面板的健康行是补出来的**。L1 数据包的 `chans` 只有 AE/FBG/HI 三行，`buildChanTable()` 在数据包路径额外追加 PZT 行；主样本路径仍走静态 `CHAN_HTML0`。如果以后数据包 `chans` 自带 PZT，会出现重复行，需要去重。
19. **助手减解释后仍不是纯大屏**。默认不打开助手，claim 卡只显示 ID、值、状态、允许上限；证据/工具链折叠；`语义编译` 行已从主面板移除。但回答正文仍保留“数值只做一致性检查”等必要解释，这是审计入口，不是装饰。浏览器 CDP 实测 L1-13 workflow：`已核验通过 · 0 failed / 20 checks`，7 张 claim 卡，未出现“语义编译”字样；只做了 headless Edge，无多浏览器稳定性测试。

20. **as-of 只覆盖 L1-13 与 main-016**。L1-13 prefix 由 `_l1cyc`/`_l1ae_frames`/`pzt_crosslab.csv` 生成；main-016 prefix 由 `016声发射.csv` 的 `SpectralEnergy` 生成；其它 L1 组、main 其余组、L2、F-MOC 没有前缀索引。它不是全量在线监测。
21. **as-of 不是 RUL**。L1-13 返回当前 cycle、累计 hits、hit rate 和最近 PZT 状态；main-016 返回当前 cycle、窗能量、累积能量和 CElog，不返回 `t85`、剩余寿命或失效概率。看板上的曲线仍是回顾性展示，不能因为查询了当前 cycle 就当成在线预测。
22. **as-of 的前缀末帧可能略早于看板当前帧**。看板数据包与 `_l1cyc` 缓存来自不同导出批次；`searchsorted` 取不晚于查询时刻的最后一帧，宁可少算，不使用未来帧。这个差异已写进 `docs/asof_prefix.md`。

## 结论

接入在“工具数值 → claim/evidence → validator → planner/API/前端”这条链上是通的，F-MOC `spec2` 返回 `partial`，C001 可签、C002 只标边界；C1 冲突 case 已把“四个模态不可比”落成 5 条 claim 和 21 项 validator 检查；L1-13 的最小两步 workflow 已把 AE t85、PZT t85 和派生 `t85_gap_pp` 放进同一张图，validator 从两条 evidence 重算差值；direct-ask 已能从问题解析 gid/t 并自动切换看板，同时不猜未知试件。

29 个 L1 gid 已注册并逐个跑过 claim/validator/API，`/api/ask` 不再手写白名单；短试验的 60/30 s 帧例外已写进 `skills/metric` 和文档。L1-13 的 as-of 前缀切片已证明“只读查询时刻之前”，但仍是单条、不是全量在线监测。这些都不是“物理正确性验收”：DFOS 的 coverage 补值、PZT 的步进口径、F-MOC 的 test_end 下界、同源重跑和 LLM 语义质量都仍是明确边界；workflow 只覆盖固定 AE+PZT 两步，不能外推成任意编排。下一轮应做 P4 demo 和 main 在线材料线，而不是继续堆单工具 gid。
