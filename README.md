# aircraft

面向飞行器结构健康监测（SHM）的**证据约束分析系统**。

- 代码与界面在这里；数据与 SHM 分析在 `D:\shm`；RUL 区间研究在 `D:\rul`。
- 定位：LLM 只做“语义编译 + 叙述”，数值由确定性工具算，`validator` 决定能不能交。
- 不是“一个模型吃所有数据”，而是“有限原语 + LLM 组合 + 确定性执行 + 验证器”。

## 0. 当前状态（2026-11-09）

| 模块 | 状态 |
|---|---|
| `skills/check` | 可用：raw 模态覆盖，不报 t85 |
| `skills/metric` | 可用：L1 C3/C4 `.DTA` + L1 C1/C2/L2 `.pridb`；L1-06 = **93.76%**；`.pridb` 1s bin 缓存后 <1s |
| `skills/audit` | 可用：绑定 `tool_call`、重跑工具、时间门/coverage；`L1-06` 示例已从 raw 生成 |
| `skills/compare` | 暂停：返回 unsupported |
| workflow / executor / verifier | **未开始** |
| planner / 3B QLoRA | **未开始** |
| case 级评测 | **未开始** |
| dashboard 合并 | **未开始**（看板仍在 `D:\shm\dashboard`） |
| 调研语料 | 已并入 `survey/`：54 篇、1,154 页 |
| F-MOC 接入 | 7 个 `.pridb`；`t85_full` 58.8–84.4%，`t85_dic` 81.4–86.2%（DIC 末帧为 test_end 下界）；非 L1 口径，见 `docs/fmoc_initial.md` |

诚实的说法：**这是一个 raw-only 的 SHM 工具层 + 一个 claim–evidence 校验器原型；还不是 workflow 合成系统。**

## 1. 目录

```text
aircraft/
├─ README.md
├─ SKILLS.md             ← skill 层、证据契约、边界（原 llm/README.md）
├─ adapters/             ← 只读 raw 的 L1/L2/PHM2019 adapter
├─ skills/               ← check / metric / compare / audit
├─ schema/               ← claim–evidence schema
├─ examples/
├─ tests/
├─ cases/
│  └─ fmoc.json          ← 未知数据集配置
├─ tools/
│  ├─ build_claim_graph.py ← raw → claim 图
│  └─ profile_fmoc.py    ← F-MOC `.pridb` 初析
├─ survey/               ← 54 篇 LLM/SHM 语料 + 综述 + 提案
├─ docs/
│  ├─ metric_standard.md ← t_x 读数标准
│  └─ fmoc_initial.md    ← F-MOC 初析
├─ validate.py
├─ rag.py
├─ rag_index.pkl
├─ dashboard/            ← 待从 D:\shm\dashboard 迁入
├─ web/                  ← 待建：分析/对话/证据链/报告
└─ app.py                ← 待建：本地服务
```

## 2. 待办清单（六个月，demo + 报告口径）

> 结题硬标准：**系统做出来 + demo + 报告**。论文/软著不是必选项。
> 目标不是“任意未知数据集”，而是“有边界的一般性”：任意数据能分诊；在声明的 schema 与工具包络内给出可复算、可审计、该拒答就拒答的结论。

### P0 冻结与清理（第 1–2 周）

- [ ] 写一页《结题交付物清单》，导师确认：3 个成功 case + 1 个拒答 case + 报告 + 视频；明确不承诺“任意数据 / 损伤类型识别 / 边缘部署”。
- [x] `llm_survey/` 并入 `survey/`；`llm/` 展平到仓库根目录并删除；相关路径已调整。
- [x] 冻结 t_x 读数标准：600 s 帧、FBG 负载掩码、线性插值；L1-06 t85 = **93.76%**（UI 93.8）。见 `docs/metric_standard.md`。
- [x] 看板 L1-06 的 SNHI85 改为 **93.76**（UI 93.8），旧值保留在 `t85_step`；`data/L1-06.js`、`index_c3.js`、`index_l1v3.js` 已同步。
- [x] C3/C4 全量 15 组按线性标准重算（`docs/l1_c3c4_canonical.csv`）；看板 `data/` 与 `index_c3/c4/l1v3` 已同步；C1/C2 看板旧值待按 anchor 口径重出。
- [ ] 修 `skills/check/run.py`、`SKILLS.md`、`skills/*/SKILL.md` 的过期状态（`check` 里“metric 未实现”、`sys.path` 注释写 `D:\shm`、报告中文编码）。
- [x] 建 git（`main` 分支）+ `requirements.txt`（`jsonschema / numpy / pdfplumber / scikit-learn / requests`）；大文件（`survey/pdfs/`、`rag_index.pkl`）不入库。

### P1 打通唯一真链（第 2–6 周）

- [x] `skills/metric` 输出自动生成 claim 图：`tools/build_claim_graph.py` 生成 `tool_call` + 带 `tool_call_id` 的 evidence，claim/evidence/edges 不再手写。
- [x] `validate.py` 重跑工具：校验时执行 `tool_call` 并与 `evidence.content.value` 比对；无绑定、无 coverage、工具不存在、篡改一致值都会 fail。
- [x] 时间门生效：`--t-max 0.62` 生成图，`observed_lifetime_fraction=1.0` 被 `temporal_leakage` 拒绝；`--t-max 1.0` 通过。
- [x] 清理旧示例：删除 `examples/L1-03_t85.json`；`L1-06_t85.json` 由 raw 生成，另加 `L1-06_t85_at062.json` 作时间门反例。
- [x] `.pridb` metric：L1 C1/C2 用 DFOS/FBG anchor（多会话回退 time），L2 用 session→cycle 表；1s SQL bin + `skills/cache`，C2 首次 ~10 s、缓存 <1 s；L2 首次约 4 min/254 M hits。
- [x] F-MOC 接入（配置驱动）：`cases/fmoc.json` + `tools/profile_fmoc.py --config`；输出 `t85_full/t99/t85_dic/coverage/test_end_uncertain`，`axis=time`。
- [ ] F-MOC cycle 轴 / pause 掩码：数据无循环计数与独立失效时刻；`test_end` 暂以 DIC 末帧下界标注。
- [ ] `skills/check` / `skills/metric` / `skills/compare` 的 stale 文案与编码问题修掉。

### P2 Dashboard 合并（第 4–8 周，可与 P1 并行）

- [ ] `dashboard/`（`index.html` / `alignment.html` / `assets/` / `data/`）迁入 `aircraft`；生成器留在 `shm`，加 `--out` 或 `tools/sync_dashboard.py`，不要 fork 生成器。
- [ ] 补 `data/index.js` + 24 组主样本包；确认顶栏出现 5 个数据集（主样本 + C1–C4）。
- [ ] 加公开 API + `postMessage` + URL 深链（`?ds=&gid=&t=`）。
- [ ] 数据 manifest：`schema_version / generated_at / source / raw_hash / evidence_grade`。
- [ ] 来源徽标：`display-only`（结果表口径）vs `raw-derived`（可作证据）；demo 的 3 个 case 从 raw 重出包。
- [ ] **时间游标 = 信息边界**：拖到 `t` 时，`allowed_lifetime_max=t`；85% 之后的曲线变灰，标注“被时间门挡住”。
- [ ] claim ↔ 图联动：`scope.lifetime_min/max` 高亮曲线段；点曲线段弹出 `tool_call → 文件 → 参数 → 重算值`。
- [ ] “就当前时刻提问”：游标处一键把 `{gid, t}` 送进对话。
- [ ] RUL 区间带：point + lo/hi + 覆盖/宽度；单独卡片，不与 t85 同轴。
- [ ] 报告导出 PDF/JSON。

### P3 证明“不是 wrapper”（第 6–12 周）

- [ ] 30 题、5 类：单跳 / 同义改写 / 多跳 / 未知数据接入 / 证据冲突。
- [ ] 对照：LLM 裸 / LLM + 工具 / LLM + 工具 + verifier；另加人（子集）。
- [ ] 指标：意图准确率、workflow 合法率、数值正确率、引用支持率、拒答正确率、延迟。
- [ ] 10 题“API vs 系统”对照表：同一问题，裸 API 编数/答不出，系统给出可复算答案。
- [ ] 若 LLM 只在措辞上赢：诚实降级为“带 NL 接口的 SHM 证据系统”，报告如实写。

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
| L1-03（C1，anchor） | 48.72 | **85.36** | 86.1 |

L1-03 属 C1，已可算：canonical **85.36%**（anchor/cycle，t50 48.72）；看板 86.1 与旧示例 86.4 是旧步进口径，需按本标准更新。

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
python -m unittest discover -s skills\tests -v

# skill
python skills\check\run.py --dataset L1 --gid L1-03
python skills\metric\run.py --dataset L1 --gid L1-06
python skills\audit\run.py --graph examples\L1-06_t85.json

# 从 raw 生成 claim 图（带 tool_call_id），再校验
python tools\build_claim_graph.py --gid L1-06 --out examples\L1-06_t85.json
python validate.py examples\L1-06_t85.json
python validate.py examples\L1-06_t85_at062.json   rem 应 fail：时间门

# 调研语料
python rag.py query "t85 definition" -k 5
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
- [`docs/fmoc_initial.md`](docs/fmoc_initial.md)：F-MOC 7 个试件的初析、限制与下一步
- `D:\shm\README.md` 与 `D:\shm\仓库地图.md`：数据、分析、结果口径
- `D:\rul\README.md`：SN-CQR、可部署口径与边界
