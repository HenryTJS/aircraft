# aircraft

面向飞行器结构健康监测（SHM）的**证据约束分析系统**。

- 代码与界面在这里；数据与 SHM 分析在 `D:\shm`；RUL 区间研究在 `D:\rul`。
- 定位：LLM 只做“语义编译 + 叙述”，数值由确定性工具算，`validator` 决定能不能交。
- 不是“一个模型吃所有数据”，而是“有限原语 + LLM 组合 + 确定性执行 + 验证器”。

## 0. 当前状态（2026-11-25）

| 模块 | 状态 |
|---|---|
| `skills/check` | 可用：raw 模态覆盖，不报 t85 |
| `skills/metric` | 可用：L1 C3/C4 `.DTA` + L1 C1/C2/L2 `.pridb`；L1-06 = **93.76%**；短 C4 组按 60/30 s 帧（`L1-30=60`、`L1-34=30`、`L1-36=60`），L1-36 raw 重算 84.84%（看板 84.70，差 0.14 pp）；`.pridb` 1s bin 缓存后 <1s |
| `skills/fbg` | **已验证**：L1-30 与 `_l1fbgprof_L1-30.npz` 一致；C1/C3 加载窗不足会 `unsupported`；不输出 t85 |
| `skills/dfos` | **已验证**：L1-03/L1-49 与 `l1_dfos_metrics.csv` 一致；14 组 `HI_end=1.0` 是归一化上限，11 组三阈值同 block 不能分级；不是空间定位 |
| `skills/pzt` | **已验证**：L1-06 与 `pzt_crosslab_summary.csv` 一致；慢，`t85=100` 是寿命末端边界/删失 |
| `skills/fmoc` | **已接入**：`spec1–spec7` 的 Vallen `.pridb` → AE hits 时间轴 t85；DIC 末帧作 test_end 下界，`test_end_uncertain=true` 时 DIC t85 只标边界；claim 示例 `spec2_fmoc.json` |
| `skills/audit` | 可用：绑定 `tool_call`、重跑工具、时间门/coverage；`L1-06` 示例已从 raw 生成 |
| `skills/compare` | 暂停：返回 unsupported |
| workflow / executor | **最小多步已通**：L1-13 AE t85 → PZT t85 → 派生 `t85_gap_pp`；validator 20 checks；不做任意 workflow DSL |

| verifier | 原型：`validate.py` 已重跑工具；L1-06 Web 切片已用 |
| planner | **受限语义编译器**：DeepSeek 实调已通过（`source=llm`，热请求约 1.5 s）；无 endpoint 时规则回退；模型不产出数字 |
| 3B QLoRA | **未开始** |
| case 级评测 | **v0 已跑**：30 题 5 类 + 11 题 hard set；30 题规则饱和，hard set 首轮 fallback 5/10、LLM 6/10，补跨 gid / 报告审计 / 时间门守卫后 fallback 9/10、LLM 10/10；新增 F-MOC 题后 fallback 10/11（H01 仍失败）；仍不是独立证据 |
| dashboard | **已迁入** `aircraft/dashboard`；`data/` 不入库，生成器通过 `AIRCRAFT_ROOT` 写回 |
| `web/app.py` | **29 个 L1 gid + F-MOC spec1–7 + 受限 planner**：FastAPI 壳 + `/api/ask` + 时间门 + 问题输入 + 证据抽屉；`cases/l1.json` 注册 29 组，`web/datasets.py` 合并 F-MOC；支持 `ok/partial/insufficient/refused/unsupported`。顶部 direct-ask 可从问题解析 `L1-xx`/`specN` 与 `t=0.8`/`在 80% 时`，响应带 `resolved`；问题没写 t 时默认 `t=1.0` 全寿命回顾，滑杆只作面板提问的 fallback |
| 调研语料 | 已并入 `survey/`：54 篇、1,154 页 |
| F-MOC 接入 | 7 个 `.pridb`；`t85_full` 58.8–84.4%，`t85_dic` 81.4–86.2%（DIC 末帧为 test_end 下界）；已接 claim/API，`spec2` 返回 `partial`；非 L1 口径，见 `docs/fmoc_initial.md` |

诚实的说法：**这是一个 raw-only 的 SHM 工具层 + claim–evidence 校验器 + 受限 planner；29 个 L1 gid 已注册，F-MOC spec1–7 已接入；已有一个 AE+PZT 的两步 workflow 和一个不猜试件的 direct-ask 入口，但 L2、main、RUL 尚未接，短试验（L1-30/34/36）的帧宽口径仍需在看板与 claim 间对齐。**

## 1. 目录

```text
aircraft/
├─ README.md
├─ .env.example          ← LLM endpoint/model/key 模板；.env 不入库
├─ SKILLS.md             ← skill 层、证据契约、边界（原 llm/README.md）
├─ adapters/             ← 只读 raw 的 L1/L2/PHM2019 adapter
├─ skills/               ← check / metric / fbg / dfos / pzt / fmoc / compare / audit
├─ schema/               ← claim–evidence schema
├─ examples/
├─ tests/
├─ cases/
│  ├─ l1.json            ← 29 个 L1 gid 的工具白名单
│  └─ fmoc.json          ← 未知数据集配置
├─ tools/
│  ├─ build_claim_graph.py ← raw → claim 图
│  └─ profile_fmoc.py    ← F-MOC `.pridb` 初析
├─ survey/               ← 54 篇 LLM/SHM 语料 + 综述 + 提案
├─ docs/
│  ├─ metric_standard.md ← t_x 读数标准
│  ├─ fmoc_initial.md    ← F-MOC 初析
│  ├─ integration_review.md ← 三模态 claim 接入三级审查
│  └─ evidence/          ← workflow/direct-ask 浏览器截图
├─ validate.py
├─ rag.py
├─ rag_index.pkl
├─ dashboard/            ← 回放看板（已迁入；data/ 不入库）
├─ bench/                ← P3 30 题、5 类 planner 评测；run_bench.py
└─ web/
   ├─ app.py             ← FastAPI 壳 + /api/ask（29 个 L1 gid + F-MOC spec1–7）
   ├─ datasets.py        ← 读 cases/l1.json + cases/fmoc.json，合并工具白名单
   ├─ planner.py         ← 问题 → 白名单计划；LLM 可选，规则回退
   ├─ tests/             ← test_api.py / test_planner.py
   └─ static/            ← assistant.js / assistant.css（注入看板，不新做页面）
```

## 2. 待办清单（六个月，demo + 报告口径）

> 结题硬标准：**系统做出来 + demo + 报告**。论文/软著不是必选项。
> 目标不是“任意未知数据集”，而是“有边界的一般性”：任意数据能分诊；在声明的 schema 与工具包络内给出可复算、可审计、该拒答就拒答的结论。

### P0 冻结与清理（第 1–2 周）

- [ ] 写一页《结题交付物清单》，导师确认：3 个成功 case + 1 个拒答 case + 报告 + 视频；明确不承诺“任意数据 / 损伤类型识别 / 边缘部署”。
- [x] `llm_survey/` 并入 `survey/`；`llm/` 展平到仓库根目录并删除；相关路径已调整。
- [x] 冻结 t_x 读数标准：600 s 帧、FBG 负载掩码、线性插值；L1-06 t85 = **93.76%**（UI 93.8）。见 `docs/metric_standard.md`。
- [x] 看板 L1-06 的 SNHI85 改为 **93.76**（UI 93.8），旧值保留在 `t85_step`；`data/L1-06.js`、`index_c3.js`、`index_l1v3.js` 已同步。
- [x] C3/C4 全量 15 组按线性标准重算（`docs/l1_c3c4_canonical.csv`）；C1/C2 14 组按 HI_AE anchor（500-cycle）线性重出（`docs/l1_c1c2_canonical.csv`）；看板 `data/` 与 `index_c1/c2/c3/c4/l1v3` 已同步。
- [ ] 修 `skills/check/run.py`、`SKILLS.md`、`skills/*/SKILL.md` 的过期状态（`check` 里“metric 未实现”、`sys.path` 注释写 `D:\shm`、报告中文编码）。
- [x] 建 git（`main` 分支）+ `requirements.txt`（`jsonschema / numpy / pdfplumber / scikit-learn / requests / fastapi / uvicorn / httpx / pandas / scipy / matplotlib`）；大文件（`survey/pdfs/`、`rag_index.pkl`）不入库。

### P1 打通唯一真链（第 2–6 周）

- [x] `skills/metric` 输出自动生成 claim 图：`tools/build_claim_graph.py` 生成 `tool_call` + 带 `tool_call_id` 的 evidence，claim/evidence/edges 不再手写。
- [x] `validate.py` 重跑工具：校验时执行 `tool_call` 并与 `evidence.content.value` 比对；无绑定、无 coverage、工具不存在、篡改一致值都会 fail。
- [x] 时间门生效：`--t-max 0.62` 生成图，`observed_lifetime_fraction=1.0` 被 `temporal_leakage` 拒绝；`--t-max 1.0` 通过。
- [x] 清理旧示例：删除 `examples/L1-03_t85.json`；`L1-06_t85.json` 由 raw 生成，另加 `L1-06_t85_at062.json` 作时间门反例。
- [x] `.pridb` metric：L1 C1/C2 用 DFOS/FBG anchor（多会话回退 time），L2 用 session→cycle 表；1s SQL bin + `skills/cache`，C2 首次 ~10 s、缓存 <1 s；L2 首次分钟级（9.9 GB 第二段会 >10 min），缓存后 <1 s。
- [x] F-MOC 接入（配置驱动）：`cases/fmoc.json` + `tools/profile_fmoc.py --config`；输出 `t85_full/t99/t85_dic/coverage/test_end_uncertain`，`axis=time`。
- [ ] F-MOC cycle 轴 / pause 掩码：数据无循环计数与独立失效时刻；`test_end` 暂以 DIC 末帧下界标注。
- [ ] `skills/check` / `skills/metric` / `skills/compare` 的 stale 文案与编码问题修掉。

### P2 Dashboard 合并（第 4–8 周，可与 P1 并行）

- [x] `dashboard/`（`index.html` / `alignment.html` / `assets/` / `data/`）迁入 `aircraft`；生成器留在 `shm`，通过 `AIRCRAFT_ROOT` 写回，不 fork。
- [x] 最小垂直切片：`web/app.py` 开 L1-06，FastAPI 壳 + `/api/ask` + URL 深链 + 回顾性时间门 + 证据抽屉；不新做页面。
- [x] 29 个 L1 gid 注册：`cases/l1.json` + `web/datasets.py`，按 raw 资产给每个 gid 配 `metric/fbg/dfos/pzt/conflict/workflow`；`/api/ask` 返回 `ok/partial/insufficient/refused/unsupported`，前端按 claim 状态渲染。短 C4 组 L1-30/34/36 用 60/30/60 s 帧，L1-36 raw 84.84% 与看板 84.70% 差 0.14 pp，已在状态表标注。
- [x] F-MOC 扩展：`spec1–spec7` 走 `skills/fmoc`，AE hits 时间轴 t85 可签；DIC 末帧不确定时 `t85_dic_pct` 只标 insufficient；`spec2` 返回 `partial`。
- [x] 受限语义编译器：问题 → 白名单计划（metric / fbg / dfos / pzt / fmoc / conflict / workflow / unsupported）；LLM 只编译计划，不产出数字；无 endpoint 或越界时规则回退；前端有问题输入与 planner 来源。
- [x] C1 冲突 case：`build_conflict_graph()` 把 L1-03 的 AE、DFOS、PZT、FBG 覆盖/删失/窗口限制放在同一张图里，返回 `partial`；结论是“不能给出四个可比的 t85”，不是四个寿命点排序。示例 `examples/L1-03_conflict.json`，validator 21 checks。
- [x] 最小两步 workflow：`build_workflow_graph()` 先跑 AE `t85` 再跑 PZT `t85`，生成派生 `t85_gap_pp`；validator 从 E001/E002 重算差值。L1-13 t=.95 返回 `ok`，t=.80 被 temporal gate 拒；示例 `examples/L1-13_workflow.json`，validator 20 checks。不是任意 workflow DSL。
- [x] `/api/ask` 内 verifier 独立重跑 metric，不复用 API 的 raw metric 缓存；首次冷启动约 30 s，之后同进程毫秒级。
- [x] FBG/DFOS/PZT 独立 claim：boundary 字段（`cycle_anchor` / `threshold_resolved` / `hi_ceiling` / `threshold_reached` / `crossing_interval_pct` / `censored`）+ `coverage_basis`；validator 重跑对应 skill，并拒绝把窗口、同 block 阈值、删失值签成 supported 点。示例与 `tests/test_skill_claims.py` 已过。
- [ ] 补 `data/index.js` + 24 组主样本包；确认顶栏出现 5 个数据集（主样本 + C1–C4）。
- [ ] 加公开 API + `postMessage` + URL 深链（`?ds=&gid=&t=`）；切片只做了 API 与 URL，`postMessage` 未做。
- [ ] 数据 manifest：`schema_version / generated_at / source / raw_hash / evidence_grade`。
- [ ] 来源徽标：`display-only`（结果表口径）vs `raw-derived`（可作证据）；demo 的 3 个 case 从 raw 重出包。
- [ ] **时间游标 = 信息边界**：拖到 `t` 时，`allowed_lifetime_max=t`；85% 之后的曲线变灰，标注“被时间门挡住”。
- [ ] claim ↔ 图联动：`scope.lifetime_min/max` 高亮曲线段；点曲线段弹出 `tool_call → 文件 → 参数 → 重算值`。
- [ ] “就当前时刻提问”：游标处一键把 `{gid, t}` 送进对话。
- [x] 顶部 direct-ask：问题显式写 `L1-xx`/`specN` 才切试件，没写用当前看板，多个/未知 gid 拒答；`t=0.8`/`在 80% 时` 覆盖 t，未写默认 `t=1.0` 全寿命回顾；响应带 `resolved.gid/t/source`。
- [ ] RUL 区间带：point + lo/hi + 覆盖/宽度；单独卡片，不与 t85 同轴。
- [ ] 报告导出 PDF/JSON。

### P3 证明“不是 wrapper”（第 6–12 周）

- [x] 30 题 v0：单跳 / 同义改写 / 多工具冲突 / 未知能力 / 时间门；`bench/cases.json`。
- [x] 11 题 hard set：模糊指代 / 错误前提 / 未知数据集 / 跨 gid / 非法平均 / 多步 / 模态边界 / 时间门 / 报告审计 / 错工具 / F-MOC 未知数据；`bench/hard_cases.json`。
- [x] 对照脚本：`bench/run_bench.py` 支持 `fallback` / `llm` / `both`，`--cases` 可切 hard set；`bench/compare_api.py` 做裸 API vs 系统。
- [x] 最小多步编排：L1-13 的 AE t85 → PZT t85 → `t85_gap_pp`，planner 的 `Plan.steps`、builder 的双 tool_call 图、API 组合状态和 UI 的逐 claim 链已通。仍只覆盖 AE+PZT 两工具，不是任意 workflow DSL。
- [ ] 多步扩展：DFOS/F-MOC 入 workflow、冲突与 workflow 的组合、错误恢复；当前 `multi_tool` 仍只覆盖冲突/多工具限制。
- [ ] 对照：LLM 裸 / LLM + 工具 / LLM + 工具 + verifier；另加人（子集）。当前只有 fallback 与 LLM planner 的对照。
- [ ] 指标：意图准确率、workflow 合法率、数值正确率、引用支持率、拒答正确率、延迟。当前只自动评了意图/工具/metrics/status。
- [x] 10 题“API vs 系统”对照表：裸 API 未编数、10/10 拒答；系统仅 H05/H07 给出可复算 claim，H08 走时间门拒答，其余边界拒答。原假设“裸 API 会编数”未被这组数据支持，报告不能那样写。
- [ ] 若 LLM 只在措辞上赢：诚实降级为“带 NL 接口的 SHM 证据系统”，报告如实写。

**首轮结果（2026-11-25，见 `bench/README.md`）**：初版 fallback 25/30，补半寿命、冲突同义词、AE 显式识别、裂纹拦截和模糊问题不该默认 metric 五个规则缺口后 30/30；LLM 直接给出计划只有 15/30，其余由 conflict 确定性分流、过度拒答恢复、白名单回退接住，混合系统仍 30/30；时间门 6 个端到端 case 的状态 6/6。题目和规则同源，30/30 只是回归结果，不能证明 LLM 有增益，也不能证明 LLM 无用。

11 题 hard set 首轮 fallback 5/10、LLM 6/10；补跨 gid、报告审计和“在 62% 时”时间门守卫后，fallback 9/10、LLM 10/10。H01 是唯一由 LLM 改变计划的 case；其余九个已被规则覆盖，因此这组 hard set 也不能再当 LLM 独立证据。新增 F-MOC `spec2` 题后 fallback 10/11，H01 仍失败。裸 API vs 系统首轮：裸模型 10/10 拒答，没有编数；系统 H05 partial、H07 ok、H08 refused，其余边界拒答。原假设“裸 API 会编数”不成立，报告要按实际结果写。

### P4 Demo 与结题（第 10–16 周）

- [ ] 3 个成功 case：L1-06 t85、`main/016` 在线进度、XJTU Bearing3_2 RUL；1 个拒答：L1-06 在 `t=0.62`（时间门）。
- [ ] 现场离线：本地 Ollama + 预生成缓存；API 失败自动降级。
- [ ] 防翻车清单：数字可点开、图由数据生成、无 evidence 的句子不出现、免责声明“仅供研究演示，不构成适航/维修放行依据”。
- [ ] 录屏 + 答辩演练 + 结题报告。

## 3. 读数标准（摘要）

```text
t_x = 100 * C^{-1}(x * C_end) / n_f
C        = 600 s 帧上的累积 AE hits
g        = FBG 窗 P2P > 200 的负载掩码（fill=holdgap）
f        = n_f / (sum(g) * 600)
cycle    = cumsum(g * 600 * f)          # 终点 = n_f
C^{-1}   = 相邻两帧之间线性插值
```

| 试件 | t50 | t85（标准，2 位） | 旧表/看板（步进，1 位） |
|---|---:|---:|---:|
| L1-06 | 68.02 | **93.76** | 94.0 |
| L1-13 | 67.94 | 93.05 | 93.1 |
| L1-14 | 52.85 | 83.56 | 83.8 |
| L1-24 | 83.87 | 96.33 | 96.5 |
| L1-03（C1，anchor） | 48.49 | **85.17** | 86.1 |

L1-03 属 C1，已可算：canonical **85.17%**（HI_AE anchor，500-cycle，t50 48.49）；看板 86.1 与旧示例 86.4 是旧步进口径，已更新。

详见 [`docs/metric_standard.md`](docs/metric_standard.md)。

## 4. 非目标（明确不做）

- 多模态大模型微调、边缘部署/蒸馏量化；
- 损伤类型分类（裂纹/脱层/腐蚀）——现有数据没有这些标签；
- Y 向定位、DFOS 空间定位（已证伪）；
- 3B QLoRA（最多作为 ablation，且放在 benchmark 之后）；
- 标准/认证条文库（`D:\shm\docs\standards` 尚不存在，版权未解决）。

## 5. 验收标准（demo + 报告）

1. 一条命令起服务，浏览器完成：选试件 → 回放 → 游标处提问 → 带证据的回答 → 导出报告。
2. 每个数字可追溯：`tool_call` + 输入文件 + 参数 + 重算值 + `evidence_id`。
3. 时间门可演示：`t=0.62` 时，85% 之后的证据被挡住，同一问题答案随 `t` 改变。
4. 拒答可演示：缺 reader / 缺前置条件时明确说“不能算”，并列出缺口。
5. 换数据集只改配置：F-MOC 接入核心代码 0 行。
6. 报告里没有无 evidence 的数字；没有把 offline 说成 online。

## 6. 运行

```powershell
cd D:\aircraft

# 证据校验
python validate.py examples\L1-06_t85.json

# 单元测试
python -m unittest tests.test_validate -v
python -m unittest tests.test_skill_claims -v
python -m unittest web.tests.test_planner -v
python -m unittest web.tests.test_api -v
python -m unittest discover -s skills\tests -v

# P3 planner 评测
python -m bench.run_bench
python -m bench.run_bench --mode both
python -m bench.run_bench --mode fallback --api --api-ids T01,T02

# skill
python skills\check\run.py --dataset L1 --gid L1-03
python skills\metric\run.py --dataset L1 --gid L1-06
python skills\fbg\run.py --gid L1-03 --json
python skills\dfos\run.py --gid L1-49 --json
python skills\pzt\run.py --gid L1-06 --json   rem 慢，先单组
python skills\audit\run.py --graph examples\L1-06_t85.json

# 从 raw 生成 claim 图（带 tool_call_id），再校验
python tools\build_claim_graph.py --gid L1-06 --out examples\L1-06_t85.json
python validate.py examples\L1-06_t85.json
python validate.py examples\L1-06_t85_at062.json   rem 应 fail：时间门

# 模态 claim（boundary 字段防止把窗口/块/删失值当寿命点）
python tools\build_claim_graph.py --tool fbg --gid L1-30 --out examples\L1-30_fbg.json
python validate.py examples\L1-30_fbg.json
python tools\build_claim_graph.py --tool dfos --gid L1-03 --out examples\L1-03_dfos.json
python validate.py examples\L1-03_dfos.json
python tools\build_claim_graph.py --tool pzt --gid L1-06 --out examples\L1-06_pzt.json
python validate.py examples\L1-06_pzt.json
python tools\build_claim_graph.py --tool pzt --gid L1-13 --out examples\L1-13_pzt.json
python validate.py examples\L1-13_pzt.json
python tools\build_claim_graph.py --tool conflict --gid L1-03 --out examples\L1-03_conflict.json
python validate.py examples\L1-03_conflict.json
python tools\build_claim_graph.py --tool fmoc --gid spec2 --out examples\spec2_fmoc.json
python validate.py examples\spec2_fmoc.json
python tools\build_claim_graph.py --tool workflow --gid L1-13 --t-max 0.95 --mode retrospective --out examples\L1-13_workflow.json
python validate.py examples\L1-13_workflow.json

# 调研语料
python rag.py query "t85 definition" -k 5

# Web 切片（29 个 L1 gid + F-MOC spec1–7；回顾性时间门；顶部 direct-ask）
# 首次冷启动要解析 raw DTA 两次：API 算一次 + verifier 独立重跑一次，约 30 s；之后同一进程内为毫秒级
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
# 浏览器打开：
# http://127.0.0.1:8000/?ds=c3&gid=L1-06&t=0.95&assistant=1&q=t85
# http://127.0.0.1:8000/?ds=c4&gid=L1-30&t=0.95&assistant=1&q=FBG%20profile
# http://127.0.0.1:8000/?ds=c1&gid=L1-03&t=0.95&assistant=1&q=%E5%9B%9B%E6%A8%A1%E6%80%81
# 顶部 direct-ask 可直接输入：
#   L1-13 先查 AE t85 再查 PZT t85 做一致性判断
#   L1-13 在 80% 时 t85 的结论是什么
# t=0.62 应被拒，t=0.95 应通过；t=0.93 仍会被拒（t85=93.76）

# 可选 LLM 语义编译器（OpenAI-compatible；不配置则规则回退）
# 方式 A：复制 .env.example 为 .env，填入 base/model/key；.env 已被 gitignore
#   copy .env.example .env
# 方式 B：在当前 PowerShell 设置环境变量
$env:SHM_LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:SHM_LLM_MODEL = "deepseek-chat"
$env:SHM_LLM_API_KEY = "sk-..."   # 不要提交
# 本地 Ollama 则用 http://127.0.0.1:11434/v1 + qwen2.5:7b。
# 环境变量或 .env 变更后重启 uvicorn。
```

## 7. 数据位置

- L1：`E:\l1`
- L2：`E:\l2`
- PHM2019：`D:\shm\phmdc`
- 主样本：`E:\main`
- RUL：`E:\XJTU-SY`、`E:\ncmapss`、`E:\femto`
- 其他 SHM 数据/结果：`D:\shm`

skill 层不直接读 `results/`；外部盘未挂载时，raw-data 测试会自动 skip。

## 8. 边界（写报告时要一起写）

- 数据是**元件/壁板级**（层合板、加筋板、铝搭接件），不是全机；
- `t85` 是**离线自归一化**，不是在线报警；`HI` 是“记录进度”，不是损伤度；
- RUL 验证数据是轴承/涡扇/结构件，**未在 L1 试件上标定**，不能直接迁移；
- 54 篇语料是 **arXiv 预印本**，peer-review 状态未逐一核实；
- 跨机构结论以 `l1/results/crosslab_variance.csv` 为准；`η²` 不显著不等于“已对齐”。

## 9. 文档索引

- [`SKILLS.md`](SKILLS.md)：skill 层、证据契约、当前边界
- [`survey/README.md`](survey/README.md)：54 篇语料与使用注意
- [`survey/SURVEY_AND_PROPOSALS.md`](survey/SURVEY_AND_PROPOSALS.md)：方法综述、空白、四个备选方案
- [`docs/metric_standard.md`](docs/metric_standard.md)：t_x 读数标准与标准值
- [`docs/l1_c3c4_canonical.csv`](docs/l1_c3c4_canonical.csv)：C3/C4 全量 15 组标准 t50/t85
- [`dashboard/README.md`](dashboard/README.md)：回放看板、数据集与重建方式
- [`docs/l1_c1c2_canonical.csv`](docs/l1_c1c2_canonical.csv)：C1/C2 14 组 anchor 标准 t50/t85
- [`docs/fmoc_initial.md`](docs/fmoc_initial.md)：F-MOC 7 个试件的初析、限制与下一步
- `D:\shm\README.md` 与 `D:\shm\仓库地图.md`：数据、分析、结果口径
- `D:\rul\README.md`：SN-CQR、可部署口径与边界
