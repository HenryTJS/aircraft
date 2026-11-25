# P3 planner benchmark

30 questions, five categories, one expected plan each. The benchmark measures
the semantic compiler only. It does not claim that the underlying tool or the
validator is physically correct.

## Categories

| category | n | what it tests |
|---|---:|---|
| `single_hop` | 6 | direct gid/tool/metric request |
| `paraphrase` | 6 | synonyms and non-template wording |
| `multi_tool` | 6 | cross-modal conflict, multi-tool limitation |
| `unknown` | 6 | unknown gid, prediction/RUL, missing tool, vague request |
| `temporal` | 6 | allowed-lifetime gate and partial/refused status |

## Run

```bash
conda run --no-capture-output -n xjtushm python -m bench.run_bench
conda run --no-capture-output -n xjtushm python -m bench.run_bench --mode both
conda run --no-capture-output -n xjtushm python -m bench.run_bench --mode fallback --api --api-ids T01,T02
```

`--mode fallback` forces the deterministic parser by clearing
`SHM_LLM_BASE_URL`. `--mode llm` uses the configured endpoint from
`D:/aircraft/.env`. `--api` runs the selected cases through `/api/ask` and
checks the returned status. The default API subset is the six temporal cases;
the full 30-case API run is intentionally not the default because each raw
tool can take tens of seconds.

## Scoring

- `intent`: exact intent match.
- `tool`: exact tool match.
- `metrics`: set match against the expected metric list.
- `status`: only present when `--api` runs that case.

A plan can be correct while the final API status is `insufficient` or
`partial`; that is the intended boundary behavior, not a planner failure.

## Current baseline

First fallback run on 2026-11-25 was 25/30. The six failures were `P02`
(半寿命点 not recognized), `M02`/`M05` (conflict synonyms not recognized),
`M04` (AE+PZT silently became PZT), `U03` (crack-length wording) and `U05`
(vague request defaulted to metric). Those were real rule gaps, so the
fallback was fixed: half-life synonyms, conflict synonyms, explicit AE
detection, crack blocking, and no default metric for unrecognized text.

After those fixes:

| mode | intent | tool | metrics | note |
|---|---:|---:|---:|---|
| fallback | 30/30 | 30/30 | 30/30 | closed set is saturated by rules |
| llm | 30/30 | 30/30 | 30/30 | only 15/30 plans came directly from the LLM; 15 were deterministic preemption or guard fallback |

The LLM direct-plan count is the important number. It was 15/30 because
`conflict_case` is resolved deterministically before the model, PZT t85 was
over-refused by the model and recovered by the rules, and the model proposed a
tool outside the per-gid whitelist in several cases. The hybrid system still
gets 30/30, but this set does **not** prove that the LLM adds value. The
questions and the rules were authored together, so 30/30 is a regression
result, not an independent benchmark. It is not evidence that the LLM is
useless either.

Do not "fix" a case by changing its expectation after seeing the result; add a
new adversarial case instead. The next set should contain vague pronouns,
multi-step questions, wrong-premise audits, unseen-dataset mapping, and
questions whose answer requires saying "I cannot compute this".

## Hard set

`bench/hard_cases.json` is the first adversarial set. It has 11 cases: ambiguous
pronoun, wrong premise, unseen dataset, cross-gid comparison, invalid fusion,
multi-step, modality boundary, temporal gate, report audit, wrong tool, and
F-MOC mapping. The F-MOC case expects `fmoc_profile` and `partial`, because
the DIC end frame is only a lower bound on test end.

```bash
conda run --no-capture-output -n xjtushm python -m bench.run_bench \
  --cases bench/hard_cases.json --mode fallback
conda run --no-capture-output -n xjtushm python -m bench.run_bench \
  --cases bench/hard_cases.json --mode llm
conda run --no-capture-output -n xjtushm python -m bench.compare_api \
  --cases bench/hard_cases.json
```

First hard run, before guard changes:

- fallback 5/10: H01 defaulted to t85, H04/H06 collapsed a cross-gid question
  into one PZT answer, H08 was unsupported instead of refused, H09 answered the
  current AE value without auditing the report claim.
- LLM 6/10: it fixed H01, but H04/H06/H08/H09 still failed.

Three safety guards were then added, because these are scope errors rather than
wording variants:

- more than one gid in the question → `unsupported` instead of silently
  answering one gid;
- report/old-table wording plus a numeric claim and an audit request →
  `unsupported`, because there is no report-audit tool;
- a temporal wording such as "在 62% 时能看到结论吗" → `metric_query`, so the
  API `t=0.62` reaches the temporal gate instead of returning `unsupported`.

After the guards:

| mode | intent | tool | metrics | remaining failure |
|---|---:|---:|---:|---|
| fallback | 9/10 | 9/10 | 9/10 | H01 |
| llm | 10/10 | 10/10 | 10/10 | none |

The F-MOC case was added after that run. On the 11-case set, fallback plans
10/11: the F-MOC case routes to `fmoc`, H01 still fails. The LLM number for
the 11-case set has not been rerun. The 11-case fallback rows are saved in
`bench/results/hard_fallback_11.json`.

The bare API comparison in `bench/results/api_vs_system.md` still covers the
original 10 cases; it was not rerun after the F-MOC case was added.

H01 is the case where the LLM currently helps: the deterministic parser sees
"85%" and answers t85; the model notices that "它" has no antecedent and asks
for clarification.

H08 now routes "在 62% 时能看到 93.76% 的结论吗" to a metric t85 plan, so the
API's `t=0.62` reaches the temporal gate and returns `refused`. Before that
guard it returned `unsupported`, which never exercised the gate.

These guards were added after seeing the first hard run. That makes the
post-guard 9/10 and 10/10 regression numbers, not independent evidence. The
first-run numbers are the honest measurement of the gap. H01 is also the only
case where the LLM changed the plan; the other nine are now covered by
deterministic rules, so this set no longer measures LLM value.

## Workflow case

The first real multi-step case is `L1-13`, not a free-form workflow. The plan is
fixed to two steps: AE t85, then PZT t85. The graph has three claims: AE t85,
PZT t85, and the derived gap `t85_gap_pp`. The validator recomputes the gap from
the two t85 evidence values rather than trusting the claim.

At `t=0.95` the API returns `ok` with AE 93.05%, PZT 87.7366%, and gap 5.312145
percentage points. At `t=0.80` it returns `refused` with `temporal_leakage`,
because AE t85 exceeds the allowed lifetime. `examples/L1-13_workflow.json`
passes `validate.py` with 20 checks, including `derived_value`.

This is deliberately not a workflow schema or executor. It does not accept
arbitrary step lists, does not cross gids, and does not yet include DFOS or
F-MOC as a second step.

## Bare API vs system

`bench/compare_api.py` sends each question to the configured chat model with no
tools, then sends the same question through `/api/ask`. It records lexical
numeric flags, refusals, system status, claim count and both answers. The flags
are not correctness scores; the point is to see whether the bare model invents
a number or whether the system can actually produce a grounded claim.

Results are written to `bench/results/api_vs_system.json` and
`bench/results/api_vs_system.md`.

First run on 2026-11-25 with `deepseek-chat`:

| result | bare model | system |
|---|---:|---:|
| explicit refusal | 10/10 | 7 unsupported + 1 refused + 1 404 |
| grounded claim | 0 | 2 (H05 partial, H07 ok) |
| numeric token in answer | 4 (H01, H02, H08, H09) | 2 |

The bare model did **not** hallucinate a t85 in this run. It refused every
question, including H07, where the system could return a real FBG profile, and
H05, where the system could show why the four modalities are not comparable.
The four "numeric" bare answers were quoting numbers from the question, not
computing them. So this comparison does not support the slogan "the API makes
up numbers"; it supports the weaker and more accurate claim that a bare model
cannot produce a grounded, auditable claim from these datasets.

H08 is the only case where the system's answer is a gate refusal rather than a
claim. H05 is `partial`: AE is signed, while DFOS, PZT and FBG are marked
insufficient. H07 is `ok` for the FBG profile, but the answer explicitly says
the axis is a loading window, not lifetime, and t does not apply.

These are ten questions and one model, written by the same person who wrote the
rules. Treat the table as a qualitative check, not a benchmark ranking.
