# LLM 专业领域应用语料库（survey）

本目录是 2026-10-29 构建的 arXiv 语料库，用于综述 LLM 在航空航天、航空、制造、PHM、SHM、工业运维、工程设计、认证等领域的应用。

> 2026-11-09：原 `D:\aircraft\llm_survey` 并入 `survey`；采集脚本都用 `HERE`，相对路径不变。

## 规模

- **54 篇论文**
- **1,154 页**
- **201.5 MB PDF**
- 全部通过 `pdfplumber` 打开校验
- `corpus_report.json`：`n_valid=54, n_bad=0`

## 先读什么

1. [SURVEY_AND_PROPOSALS.md](SURVEY_AND_PROPOSALS.md)  
   方法综述、研究空白、四个备选方案、推荐路线。

2. [papers_table.md](papers_table.md)  
   54 篇清单，含 arXiv 链接和本地 PDF 链接。

3. [papers_valid.csv](papers_valid.csv)  
   元数据：标题、作者、年份、领域标签、摘要、PDF 路径。

## 重点论文

| 方向 | 论文 |
|---|---|
| SHM Agent | SHM-Agents, arXiv:2605.12916 |
| PHM benchmark | PHM-Bench, arXiv:2508.02490 |
| 航空维修 benchmark/RAG | CAMB, arXiv:2508.20420 |
| 工业运维 Agent benchmark | AssetOpsBench, arXiv:2506.03828 |
| 工业 Agent 综述 | Industrial Agentic AI, arXiv:2610.26941 |
| 时序多模态 | TS-MLLM, arXiv:2603.07572 |
| 时序检索 + RUL | Time-Series Retrieval, arXiv:2608.19218 |
| 信号到语义诊断 | S2S-FDD, arXiv:2603.08048 |
| 可信故障诊断 | HCAA, arXiv:2510.03815 |
| 闭环可认证设计 | Closed-loop AI, arXiv:2608.21976 |
| 多 Agent 规划 | Z-COPA, arXiv:2607.10994 |
| 知识图谱 + LLM | LLM+KG, arXiv:2408.01700 |

## 目录结构

```text
survey/
├─ SURVEY_AND_PROPOSALS.md   ← 综述与方案
├─ papers_table.md           ← 54 篇清单
├─ papers_valid.csv          ← 元数据
├─ papers_valid.jsonl
├─ corpus_report.json        ← 校验统计
├─ pdfs/                     ← 54 个已校验 PDF
├─ candidates.jsonl          ← 307 个候选
├─ collect_llm_survey.py     ← 采集脚本
├─ repair_16.py              ← 截断 PDF 修复脚本
└─ papers.jsonl              ← 早期清单（可能含未校验记录，以 papers_valid 为准）
```

## 引用注意

- 这些是 arXiv 预印本，peer-review 状态未逐一确认；
- 引用前请用 arXiv 页面/DOI 核对版本；
- 2026 年论文可能仍在更新；
- 不要把“摘要中的数字”当成最终实验结论，正式引用前读全文相关段落。
