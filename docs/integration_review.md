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

- 白名单：gid 只能是 `L1-06`、`L1-13`、`L1-30`、`L1-03`、`spec1`–`spec7`；每个 gid 的 tool 由 `SUPPORTED` 限定。F-MOC 只允许 `fmoc`。
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

这里的“多步”是固定两步，不是任意 workflow DSL；C003 只做一致性检查，不能写成 RUL 偏差。

### 2.7 测试

- `tests.test_validate`：10/10
- `tests.test_skill_claims`：9/9
- `web.tests.test_planner`：26/26
- `web.tests.test_api`：21/21
- 合计 66/66 通过，完整测试耗时 185.638 s。

浏览器点击验证：

- L1-30 FBG：`已核验通过 · 0 failed / 10 checks`，panel `证据约束分析 · L1-30`，chain `C001 ← E001 ← T001`。
- L1-03 DFOS：`部分签发 · 0 failed / 13 checks`，C001 supported，C002 insufficient。
- L1-06 PZT：`不签发 · 0 failed / 9 checks`，t85=100 删失，明确写“不签发点估计”。
- L1-03 conflict：`部分签发 · 0 failed / 21 checks`，5 条 claim，答案明确“不能给出四个可比的 t85”。

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
14. **workflow 只做了 API 测试，没有做浏览器点击复验**。前端已加逐 claim 链和 `graph: N claims` 汇总，`node --check` 通过；但 L1-13 workflow 的 `ok` 三卡展示没有在浏览器里点过一次。

## 结论

接入在“工具数值 → claim/evidence → validator → planner/API/前端”这条链上是通的，F-MOC `spec2` 返回 `partial`，C001 可签、C002 只标边界；C1 冲突 case 已把“四个模态不可比”落成 5 条 claim 和 21 项 validator 检查；L1-13 的最小两步 workflow 已把 AE t85、PZT t85 和派生 `t85_gap_pp` 放进同一张图，validator 从两条 evidence 重算差值。

但这不是“物理正确性验收”。DFOS 的 coverage 补值、PZT 的步进口径、F-MOC 的 test_end 下界、同源重跑和 LLM 语义质量都仍是明确边界；workflow 只覆盖固定 AE+PZT 两步，不能外推成任意编排。下一轮应做 P4 demo 和更窄的多步扩展，而不是继续堆单工具 gid。
