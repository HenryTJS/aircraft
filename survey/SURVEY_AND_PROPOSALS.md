# LLM 在航空航天/工业/PHM/SHM 的应用综述与项目备选方案

**语料版本**：2026-10-29  
**规模**：54 篇 arXiv 论文，全部 PDF 已下载并通过 `pdfplumber` 校验；共 1,154 页，201.5 MB。  
**清单**：[papers_table.md](papers_table.md)（含 arXiv 与本地 PDF 链接）  
**元数据**：[papers_valid.csv](papers_valid.csv)、[papers_valid.jsonl](papers_valid.jsonl)  
**校验报告**：[corpus_report.json](corpus_report.json)

---

## 0. 结论摘要

这 54 篇论文的共同趋势不是“用一个大模型替代专业软件”，而是：

> **把 LLM 放在“语言接口 + 任务编排 + 证据整合”层，把数值计算、仿真、优化、信号处理留给确定性工具或小模型。**

主流方案可以归为六类：

1. 领域 benchmark 与能力评估；
2. RAG / 知识图谱 grounding；
3. 工具调用型 Agent / generalist-specialist 架构；
4. 多模态与时序适配器；
5. 小模型 + LLM 协同、校准与不确定性；
6. 闭环设计、标准/认证与数字孪生。

这批文献暴露出的空白，恰好是你们项目可以做的：

- 缺 **跨机构/跨 campaign 的可迁移性**评测；
- 缺 **claim 级证据审计**，多数 RAG 只评估答案像不像；
- 缺 **时间泄漏**控制，PHM/SHM 尤其危险；
- 缺 **AE/FBG/DFOS/PZT 异构窗口**的统一适配；
- 缺 **标准/认证条文级**的 compliance 检查；
- 缺 **工作流级**的时间、成本、决策影响评估。

下面给出四个备选方案。推荐顺序：

> **A（证据约束跨机构审计）> B（跨模态适配器）> D（标准/认证审计）> C（闭环实验设计）**

A 最适合当前数据与 6 个月周期；B 是方法层第二篇；D 取决于能否拿到标准原文；C 科学价值最高但实验风险最大。

---

## 1. 语料与方法

### 1.1 检索

用 arXiv API，17 组查询，覆盖：

- aerospace / aviation / aircraft；
- structural health monitoring / prognostics / fault diagnosis；
- manufacturing / maintenance / digital twin；
- engineering design / requirements / certification；
- multimodal time series / industrial agent / RAG engineering / reliability / industrial robotics。

共获得 307 个候选，148 个按关键词相关性入选，最终下载并校验 54 篇。

### 1.2 纳入与排除

纳入：

- LLM/VLM/Agent/RAG 在专业工程领域的应用、benchmark、系统或综述；
- 与 SHM/PHM/航空/制造/运维/设计/认证直接相关；
- 有 PDF 可读。

排除：

- 纯通用 NLP/聊天机器人；
- 纯 CV 且与工程决策无关；
- 无法下载全文或只有摘要的论文；
- 与专业领域无关的社交媒体/法律/医学文本。

### 1.3 局限

- 只覆盖 arXiv，未系统检索 IEEE Xplore/Elsevier/Springer 的付费论文；
- 2026 年论文多为预印本，peer-review 状态未逐一确认；
- 领域标签来自检索 query，不是严格分类；
- 方法统计基于标题/摘要关键词，是“语料内出现频次”，不是领域总体比例。

---

## 2. 语料统计

### 2.1 年份

| 年份 | 篇数 |
|---|---:|
| 2024 | 9 |
| 2025 | 23 |
| 2026 | 22 |

### 2.2 检索领域

| 领域标签 | 篇数 |
|---|---:|
| aerospace | 10 |
| aviation | 10 |
| fault diagnosis | 9 |
| aircraft | 4 |
| engineering design | 4 |
| maintenance | 4 |
| PHM | 3 |
| industrial agent | 3 |
| SHM | 2 |
| digital twin | 2 |
| certification | 1 |
| manufacturing | 1 |
| multimodal time series | 1 |

### 2.3 方法关键词出现频次

同一篇可命中多个关键词：

| 关键词 | 篇数 |
|---|---:|
| RAG / retrieval | 24 |
| tool / tool use | 18 |
| maintenance | 17 |
| benchmark | 15 |
| agent | 13 |
| fault diagnosis | 12 |
| fine-tune / LoRA | 8 |
| multimodal | 6 |
| knowledge graph | 5 |
| digital twin | 4 |
| time series | 4 |
| calibration / uncertainty | 2–3 |

注意：这是“摘要中提及”，不是严格方法分类；但它足以说明 RAG、Agent、benchmark 是当前工程 LLM 的三条主线。

---

## 3. 六类主流方案

### 3.1 领域 benchmark：先证明“通用模型不够用”

代表：

- **PHM-Bench**（[2508.02490](https://arxiv.org/abs/2508.02490)）：从基础能力、核心任务、全生命周期三个维度评估 PHM 大模型，覆盖状态监测、故障诊断、RUL、维护决策。
- **CAMB**（[2508.20420](https://arxiv.org/abs/2508.20420)）：民航维修领域工业级 benchmark，明确指出 RAG 是当前实际系统的主流方案，并评估 embedding 与 LLM。
- **AssetOpsBench**（[2506.03828](https://arxiv.org/abs/2506.03828)）：140+ 工业运维自然语言任务，比较 Tool-as-Agent 与 Plan-Executor 两种 Agent 架构。
- **Pre-Flight / PilotBench**（[2607.01829](https://arxiv.org/abs/2607.01829)、[2604.08987](https://arxiv.org/abs/2604.08987)）：航空运行知识与带安全约束的 Agent 评测。
- **ATSADBench**（[2601.12448](https://arxiv.org/abs/2601.12448)）：航空软件时序异常检测，发现 LLM 在单变量上可以、多变量上接近随机猜测，RAG 甚至可能加重误报。
- **FDM-Bench**（[2412.09819](https://arxiv.org/abs/2412.09819)）、**Engineering AGI benchmark**（[2509.16204](https://arxiv.org/abs/2509.16204)）：增材制造与工程设计能力评测。

**共同结论**：

> 通用 LLM 在专业领域“知识问答”尚可，但在多变量时序、复杂推理、长流程任务上明显不足。  
> 没有领域 benchmark，就无法判断一个系统是否真的有用。

**对你们的意义**：

- 你们已经有 40 条内部 QA benchmark，但它不是“能力 benchmark”；
- 需要把评测从“答对没有”升级为“任务完成没有、证据是否成立、是否越界”。

### 3.2 RAG / 知识图谱 grounding：主流，但不够

代表：

- **CAMB** 直接指出 RAG 是民航维修实际系统的主流方案。
- **PARAM**（[2508.04714](https://arxiv.org/abs/2508.04714)）：轴承振动特征序列化成自然语言，RAG + 多 Agent 生成维护建议。
- **Aviation safety knowledge-grounded LLM**（[2604.13101](https://arxiv.org/abs/2604.13101)）：航空安全知识 grounding。
- **LLM + Knowledge Graph**（[2408.01700](https://arxiv.org/abs/2408.01700)）：卫星电子板测试文档，KG 存元数据、Parquet 存结果、LLM 做抽取与验证。
- **Time-Series Retrieval for RUL**（[2608.19218](https://arxiv.org/abs/2608.19218)）：检索历史相似退化段，转成视觉对比图，再让 MLLM 做 RUL。

**共同结论**：

- RAG 能补领域知识，但不能保证“引用支持结论”；
- 检索相似案例对 RUL 有帮助，但收益依赖模型能力；
- KG 适合结构化约束，LLM 适合抽取/解释，两者互补。

**对你们的意义**：

- 你们现在的“双库 RAG + claim–evidence”方向是对的；
- 但只有 RAG 会退化成知识库，必须加工具和证据校验；
- 可以把“相似退化段检索”作为 L2/L1 的新工具，而不是只检索论文。

### 3.3 工具调用型 Agent / generalist-specialist：最接近你们的方向

代表：

- **SHM-Agents**（[2605.12916](https://arxiv.org/abs/2605.12916)）：generalist-specialist 架构，LLM 负责推理与规划，专业算法负责具体 SHM 任务；支持自然语言端到端执行、模块化扩展；在斜拉桥上做数据异常诊断、信号处理、模态识别、损伤识别、有限元更新、疲劳评估等。
- **AssetOpsBench**（[2506.03828](https://arxiv.org/abs/2506.03828)）：比较 Tool-as-Agent 与 Plan-Executor，强调工业 Agent 需要模拟环境和可复现评测。
- **Industrial Agentic AI**（[2610.26941](https://arxiv.org/abs/2610.26941)）：提出工业 Agent 的五级能力、四层架构，强调物理约束、可靠性、闭环执行。
- **Z-COPA**（[2607.10994](https://arxiv.org/abs/2607.10994)）：多 Agent + 符号动作图 + MILP，用于航空发动机 0D ROM 规划；说明长流程规划不能只靠单 Agent。

**共同结论**：

> 工程 Agent 的核心不是“会聊天”，而是“会选工具、会编排长流程、会把结果交给确定性后端验证”。

**对你们的意义**：

- 你们当前 Agent 的 planner/tool/validator 架构与这条线一致；
- 但你们缺“长流程”和“工具多样性”；
- SHM-Agents 是最直接的竞争/参照：它做单座桥的端到端任务，你们可以做**跨机构/跨 campaign 的可迁移性审计**，避开正面撞车。

### 3.4 多模态与时序适配器：LLM 不适合直接吃原始信号

代表：

- **TS-MLLM**（[2603.07572](https://arxiv.org/abs/2603.07572)）：时序 patch + 频域图像 + 文本知识，三模态联合；TMAF 用时序特征做 query 检索视觉/文本线索。
- **S2S-FDD**（[2603.08048](https://arxiv.org/abs/2603.08048)）：把高维时序转成自然语言摘要（趋势、周期、偏差），再做多轮树状诊断。
- **Time-Series Retrieval**（[2608.19218](https://arxiv.org/abs/2608.19218)）：检索相似退化段，转视觉对比，MLLM 做 RUL。
- **Refining Time Series Anomaly Detectors**（[2503.21833](https://arxiv.org/abs/2503.21833)）：LLM 用于修正/解释时序异常检测器。

**共同结论**：

- 直接把原始波形塞进 LLM 效果差；
- 有效路线是“时序编码器/图文转换 + LLM”；
- 多模态对齐和缺失模态处理仍是难点。

**对你们的意义**：

- 你们的 AE/FBG/DFOS/PZT 是异构窗口，不是图像；
- 需要 modality-specific encoder + shared latent + uncertainty；
- 8 GB GPU 可以训练小型 1D CNN/MLP，但不能训 7B；
- Adapter v0 的 MLP 失败、RF 1.416 mm 的结果说明：小样本下先做特征工程/浅层模型，不要硬上深度。

### 3.5 小模型 + LLM 协同、校准与不确定性

代表：

- **HCAA**（[2510.03815](https://arxiv.org/abs/2510.03815)）：贝叶斯网络先诊断，LLM 做认知仲裁，温度校准 + 风险评估，ECE 降低 75%+。
- **Collaborative Fusion of Large and Small Models**（[2506.05854](https://arxiv.org/abs/2506.05854)）：大模型负责语义/解释，小模型负责数值/实时。
- **TSLAM-Mini**（[2505.07877](https://arxiv.org/abs/2505.07877)）：QLoRA + 数字孪生数据做领域小模型。
- **Power system LLM survey**（[2512.13004](https://arxiv.org/abs/2512.13004)）：领域应用需要可靠性/可解释性/安全性约束。

**共同结论**：

- 高风险领域不能只靠 LLM 黑箱；
- 校准、拒答、置信度、人工复核是系统的一部分；
- 小模型 + LLM 协同比“一个大模型包打天下”更现实。

**对你们的意义**：

- 你们的 `t85/SNHI` 工具就是“小模型/确定性模型”；
- LLM 应该做仲裁/解释，不应替代计算；
- 可以把 ECE、拒答率、证据覆盖率作为核心指标。

### 3.6 闭环设计、标准/认证与数字孪生

代表：

- **Closed-loop AI achieves certifiable engineering design**（[2608.21976](https://arxiv.org/abs/2608.21976)）：LLM 把自然语言需求转成几何/网格，调用 BESO/CalculiX/PSO，自动 reviewer 按五项指标打分，候选送 CCS 做 AIP 认证。
- **Z-COPA**（[2607.10994](https://arxiv.org/abs/2607.10994)）：多 Agent + 图表示 + MILP 做 0D ROM 规划。
- **Digital Twin AI**（[2601.01321](https://arxiv.org/abs/2601.01321)）：数字孪生的建模、镜像、干预、自治四阶段；LLM/世界模型用于自治管理。
- **LLM + KG for aerospace test data**（[2408.01700](https://arxiv.org/abs/2408.01700)）：文档抽取 + KG 验证。
- **LEED certification automation**（[2506.00888](https://arxiv.org/abs/2506.00888)）：CV + LLM-RAG 做认证材料。

**共同结论**：

> 工程领域最强的 LLM 系统，不是“模型自己算”，而是“LLM 编排 + 确定性后端 + 自动 reviewer + 外部认证”。

**对你们的意义**：

- 你们可以把“可比性判断”做成一个 deterministic reviewer + LLM 解释；
- 标准/认证审计是可行的第二方向，但需要标准原文；
- 纯 LLM 打分不可信，必须规则/工具/专家复核。

---

## 4. 这些论文共同证明了什么

### 4.1 通用模型不够，领域评测必须先做

PHM-Bench、CAMB、AssetOpsBench、PilotBench、ATSADBench、FDM-Bench 都在做同一件事：

> 先定义领域任务和指标，再谈模型能力。

你们的 40 条 QA 只是“接口测试”，不是领域能力评测。  
真正的评测应该是：

- 任务完成率；
- 证据正确率；
- 拒答/越界；
- 时间/成本；
- 专家复核工作量。

### 4.2 RAG 是主流，但不是终点

CAMB 明确说 RAG 是当前实际系统的主流；PARAM、Aviation Safety、Time-Series Retrieval 都在用。  
但 RAG 的弱点是：

- 检索到了不等于支持结论；
- 多跳/比较/冲突消解弱；
- 没有工具就算不出新数；
- 没有时间约束就会偷看未来。

所以你们加 claim–evidence + tool + temporal gate 是合理的，但必须用 benchmark 证明它比 RAG-only 强。

### 4.3 Agent 的关键是“工具 + 长流程 + 验证”

SHM-Agents、AssetOpsBench、Industrial Agentic AI、Z-COPA 都指向：

- 单轮问答不是 Agent；
- 长流程规划、工具选择、结果验证才是；
- 需要模拟环境/可复现任务。

你们现在有工具和 validator，但流程太短。  
下一步必须做“多步工作流”，而不是继续加单跳题。

### 4.4 时序/多模态适配器是瓶颈

TS-MLLM、S2S-FDD、Time-Series Retrieval 都在解决“LLM 不能直接吃信号”。  
你们的 AE/FBG/DFOS/PZT 比图像/文本更复杂：

- 采样率不同；
- 物理量不同；
- 缺失模态；
- 跨试件/跨机构分布漂移。

这正是可以做出方法创新的地方，但需要更多数据和严格 LOSO。

### 4.5 高风险领域需要校准、拒答、人工复核

HCAA、Collaborative Fusion、Power System Survey 都强调：

- 不确定性；
- 校准；
- 人机协同；
- 安全约束。

你们把“无证据拒答”做成硬门是对的，但还需要：

- 校准的置信度；
- 错误类型分析；
- 人工复核协议。

---

## 5. 与 D:\shm 项目最相关的空白

| 空白 | 现有论文 | 你们能做什么 |
|---|---|---|
| 跨机构/跨 campaign 可迁移性 | SHM-Agents 单桥；PHM-Bench 单领域 | 跨 L1/L2/PHM 的 transportability audit |
| claim 级证据审计 | RAG 论文多评估答案；少逐 claim | claim–evidence graph + critic + validator |
| 时间泄漏 | PHM 论文少明确处理 | 信息时限 + 未来数据门 |
| AE/FBG/DFOS/PZT 异构窗口 | TS-MLLM 图像/文本；S2S 时序→文本 | modality-specific encoder + shared latent |
| 标准/认证条文级 | 航空维修 benchmark；认证自动化少 | dual RAG + clause-level compliance |
| 工作流级评估 | AssetOpsBench 有任务，但 SHM 无 | 时间/证据/决策影响指标 |

---

## 6. 四个备选方案

### 方案 A：证据约束的跨机构 SHM 审计 Agent（推荐主方案）

**问题**

给一个新 campaign/新数据集，判断它和 L1/L2 是否可比、哪些指标可迁移、哪些结论不能下。  
人做要读协议、对条件、算指标、判断混杂，几小时起步。

**方法**

```text
DatasetAdapter（L1/L2/PHM/新数据）
  + 工具（t85/SNHI/阈值/跨模态/跨 campaign）
  + 双库 RAG（论文 + 标准）
  + claim–evidence graph
  + Critic（quote 是否支持 claim）
  + Validator（数值/scope/时间泄漏）
  + 报告生成
```

输出：

1. 可比/部分可比/不可比；
2. 可比维度与不可比维度；
3. 可迁移/不可迁移指标；
4. 建议补做的对照；
5. 每条结论的 evidence；
6. 置信度与拒答项。

**创新点**

- 不是“SHM 问答”，而是 **transportability audit**；
- claim 级证据图，而不是段落级 RAG；
- 时间泄漏门，避免用未来数据判断早期可用性；
- 跨机构/跨 campaign benchmark，而不是单数据集 QA。

**与现有工作的区别**

- SHM-Agents 做单桥端到端任务，不做跨机构可比性；
- PHM-Bench/CAMB 做能力评测，不做证据审计；
- AssetOpsBench 做工业运维任务，不做 SHM 物理边界。

**数据/算力**

- 现有 L1 29 + L2 3 + PHM 8；
- DeepSeek API + 8 GB GPU；
- 6 个月可完成原型 + 论文。

**评估**

- 20–30 条 workflow tasks；
- 专家复核时间；
- claim–evidence 覆盖率；
- “不可比误判为可比”的次数；
- 与 RAG-only / 人工基线对比。

**风险**

- 审稿人可能说“系统集成，不是模型创新”；
- 需要外部 campaign 或至少 L2/PHM 迁移验证；
- 标准库不足时，只能做文献依据。

**产出**

- ICRE/PHM 系统或 benchmark 论文；
- 专利：证据图 + 时间门 + 可比性审计流程；
- 中期/结题 demo。

---

### 方案 B：跨模态 SHM 适配器 + LLM（方法层第二篇）

**问题**

LLM 不能直接吃 AE/FBG/DFOS/PZT 原始窗口；简单序列化成文本会丢信息。

**方法**

- 每种模态一个轻量 encoder（1D CNN / MLP / 小 Transformer）；
- 投影到共享 latent；
- 模态 embedding + 时间/载荷条件；
- 训练目标：t85/寿命分数回归 + 同试件跨模态对比 + 模态 dropout；
- 输出 128/256 维向量 + 不确定度；
- LLM 只读向量摘要/证据，不读原始波形。

**创新点**

- 异构 SHM 模态，不是图像/文本；
- 缺失模态鲁棒；
- 校准不确定度；
- 跨试件 LOSO / 跨 campaign。

**数据/算力**

- L1 29 AE/17 GW + `four_modal.csv` 5 试件 ×4 模态；
- 8 GB GPU 足够；
- 但当前数据量小，必须先做特征工程/浅层模型。

**评估**

- LOSO MAE/RMSE；
- 校准（ECE）；
- 缺失模态；
- 与 RF/MLP/手工特征对比；
- 接入 Agent 后的 claim 质量。

**风险**

- 数据太少；Adapter v0 MLP 已失败（MAE 4.0 vs 均值 1.87）；
- RF v0 1.416 mm 也不强；
- 需要更多窗口/试件，或预训练波形编码器；
- 论文难度高于 A。

**产出**

- SHM/PHM 期刊或会议；
- 专利：跨模态适配器 + 不确定度；
- 作为 A 的底层能力。

---

### 方案 C：闭环实验设计 Agent（高科学价值，高风险）

**问题**

跨机构差异常和材料/结构/加载/批次混杂。  
人很难决定“下一步最少补哪些试件/测点/对照”，才能区分假设。

**方法**

- LLM 理解假设与约束；
- 调用 deterministic design/simulation（如 Z-COPA 的图 + MILP 思路）；
- 生成候选实验矩阵；
- 用成本/信息增益/可区分性评分；
- 输出最小实验计划 + 证据。

**创新点**

- 从“回答”升级为“设计实验”；
- 主动解决 confound，而不是事后解释；
- 可与闭环认证（Closed-loop AI）结合。

**数据/算力**

- 现有 29+3+8 可做模拟；
- 但真实新实验受预算限制；
- 需要仿真器/代理模型；
- 6–12 个月，风险高。

**评估**

- 专家评分；
- 假设区分能力；
- 实验成本；
- 与人类设计对比。

**风险**

- 没有新实验预算，容易变成“纸上方案”；
- 仿真可信度；
- 审稿人会问“实际验证在哪里”。

**产出**

- 高水平 SHM/PHM 论文；
- 专利：confound-resolving experiment planner；
- 适合作为博士/后续课题，不适合作为唯一结题成果。

---

### 方案 D：标准/认证条文级审计 Agent

**问题**

SHM/航空报告中的 claim 很难逐条对应标准条文；认证材料准备耗时。

**方法**

- 双库 RAG：文献 + 标准；
- 标准条文切分 + clause ID；
- claim–evidence graph，要求 clause-level citation；
- compliance checker：符合/不符合/证据不足；
- 输出审计表。

**创新点**

- 不是通用 RAG，而是 clause-level compliance；
- 与航空维修/认证 benchmark 对接；
- 可做专利/行业工具。

**数据/算力**

- 需要真实 ASTM/ISO/GB 标准原文；
- 目前 `docs/standards` 为空；
- 标准版权/获取是最大风险；
- 6 个月可做原型，但依赖合作方。

**评估**

- 条文检索 recall；
- 合规判断准确率；
- 专家复核；
- 误判成本。

**风险**

- 标准拿不到；
- 领域覆盖窄；
- 不能替代认证机构。

**产出**

- 行业论文/专利；
- 企业合作 demo；
- 与 A 结合成“可比性 + 合规”审计。

---

## 7. 推荐路线

### 主路线：A

理由：

- 最贴合你们现有数据与研究主线；
- 6 个月可做出原型 + 论文；
- 与 SHM-Agents/PHM-Bench/CAMB 有明确差异；
- 可同时产出专利（证据图 + 时间门）和 demo。

### 第二路线：B

理由：

- 方法创新更强；
- 但数据不足，先做 v0 试点；
- 如果 A 的论文需要“模型层”支撑，B 可以作为第二章。

### 第三路线：D

理由：

- 行业价值/专利潜力高；
- 但标准原文是硬门槛；
- 有合作方时再做。

### 不建议作为主路线：C

理由：

- 科学价值最高，但实验验证风险最大；
- 适合作为后续博士课题，不适合作为 2027 结题的唯一成果。

---

## 8. 六个月执行建议（A 为主）

| 月份 | 任务 | 产出 |
|---|---|---|
| 1 | 冻结 A 的任务定义；做 2 个 campaign 的可比性审计原型 | 审计模板、证据 schema |
| 2 | 接 L1/L2/PHM Adapter；补标准/文献 RAG | 端到端 demo |
| 3 | 20–30 条 workflow 任务；专家复核 | 首轮结果 |
| 4 | 与 RAG-only/人工基线对比；错误分析 | 论文结果表 |
| 5 | 专利交底书；论文初稿 | 申请/投稿 |
| 6 | 答辩 demo；开源/复现包 | 结题材料 |

---

## 9. 诚实边界

- 这 54 篇是 arXiv 语料，不是系统综述；不能声称“覆盖全部 LLM+SHM 工作”；
- 其中真正 SHM 的只有 2 篇（SHM-Agents、Deep Generative Models in SHM），PHM 3 篇；跨机构 SHM + LLM 的直接工作很少，这是机会也是风险；
- 多数论文是 2025–2026 预印本，peer-review 状态未确认；
- 方案 A 的“可比性审计”目前没有直接竞品，但也意味着没有现成 benchmark，需要自己定义；
- 方案 B 的 Adapter v0 结果很弱，不能拿它当“方法已成立”；
- 方案 C/D 依赖外部条件（实验预算/标准原文）。

---

## 10. 文件

- 论文清单：[papers_table.md](papers_table.md)
- 元数据：[papers_valid.csv](papers_valid.csv)
- 校验：[corpus_report.json](corpus_report.json)
- 语料目录：[pdfs/](pdfs/)
- 采集脚本：[collect_llm_survey.py](collect_llm_survey.py)
- 修复脚本：[repair_16.py](repair_16.py)

> 说明：所有 54 篇 PDF 均已通过 `pdfplumber` 打开校验；`corpus_report.json` 记录 `n_valid=54, n_bad=0`。
