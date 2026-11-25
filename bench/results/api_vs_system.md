# Bare API vs evidence-constrained system

Model: `deepseek-chat`. `has_percent` / `has_metric_value` are lexical flags, not correctness scores.

| id | category | bare numeric | bare refused | system status | system claims | system answer |
|---|---|---:|---:|---|---:|---|
| H01 | ambiguous | yes | yes | unsupported | 0 | 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。 |
| H02 | wrong_premise | yes | yes | unsupported | 0 | 当前 L1-03 只支持 metric、dfos、pzt、conflict 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。 |
| H03 | unknown_data | no | yes | http_404 | 0 |  |
| H04 | cross_case | no | yes | unsupported | 0 | 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。 |
| H05 | invalid_fusion | no | yes | partial | 5 | L1-03 不能给出四个可比的 t85。AE t85=85.17%；PZT t85=100.00%[98.39, 100.00]%，删失，不签发点估计；DFOS 块级 HI=1.000；DFOS 50% 预警点未签发；FBG 无法形成剖面，因为原始只有 2 个加载窗。这些值分别… |
| H06 | multi_step | no | yes | unsupported | 0 | 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。 |
| H07 | modality_boundary | no | yes | ok | 1 | L1-30 FBG 末窗应变剖面 shape_rob25=0.015593；轴为加载窗，不映射寿命分数，t 不适用于该 claim。 |
| H08 | temporal | yes | yes | refused | 0 | 时间门未通过：该数值结论超出允许寿命上限，系统不签发 claim。 |
| H09 | report_audit | yes | yes | unsupported | 0 | 当前 L1-03 只支持 metric、dfos、pzt、conflict 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。 |
| H10 | wrong_tool | no | yes | unsupported | 0 | 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。 |

## Bare answers

### H01 它为什么到 85% 才报警

- bare: 不能确定。你只说了“它到 85% 才报警”，但没有说明“它”指哪个对象、85% 是什么指标（如损伤概率、载荷、温度、寿命消耗等），也没有报警阈值设定和监测数据。缺少这些信息，无法判断为什么到 85% 才报警。
- system: `unsupported` 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。

### H02 L1-03 的 FBG t85 是 94.86，对吗

- bare: 根据你给出的信息，我无法确认“L1-03 的 FBG t85 是 94.86”是否正确：这里没有提供 L1-03 的 FBG t85 的参考值或判定依据，也没有可核对的数据。不能仅凭这句话判断对错，也不能编造数值。
- system: `unsupported` 当前 L1-03 只支持 metric、dfos、pzt、conflict 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。

### H03 F-MOC spec1 的 t85 是多少

- bare: 根据你给出的信息，我无法回答“F-MOC spec1 的 t85 是多少”：这里没有提供 F-MOC spec1 的任何数据或定义，也没有说明 t85 指什么，因此不能给出数值。
- system: `http_404` 

### H04 把 L1-06 的 t85 和 L1-13 的 PZT 比一下

- bare: 不能比较：你只给了“L1-06 的 t85”和“L1-13 的 PZT”这两个指代，但没有给出它们的具体数值或可读取的数据，也没有说明比较的是哪个指标（如幅值、阈值、时间等）。请提供这两项的具体数据或明确比较口径。
- system: `unsupported` 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。

### H05 L1-03 四个模态 t85 平均是多少

- bare: 不能确定。你只给了“L1-03 四个模态 t85”这一条信息，没有给出四个模态各自的 t85 数值，因此无法得出平均值；我不能编造数值。请提供这四个模态的 t85 数据。
- system: `partial` L1-03 不能给出四个可比的 t85。AE t85=85.17%；PZT t85=100.00%[98.39, 100.00]%，删失，不签发点估计；DFOS 块级 HI=1.000；DFOS 50% 预警点未签发；FBG 无法形成剖面，因为原始只有 2 个加载窗。这些值分别是事件累积、块级包络、导波退相关和覆盖不足，不是同一物理量，不能当作四个寿命点排序。

### H06 先看 L1-06 的 t85，再看 L1-13 的 PZT，最后说哪个更晚

- bare: 不能回答。你只给了“L1-06 的 t85”和“L1-13 的 PZT”这两个指代，但没有给出它们各自的具体时间/数值，也没有提供可比较的数据，所以我无法判断哪个更晚。
- system: `unsupported` 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。

### H07 L1-30 的 FBG 能不能给 t85

- bare: 不能。你给出的信息里没有 L1-30 的 FBG 与 t85 之间的对应关系或数据，我无法判断“能不能给 t85”，也不能编造数值。请补充 L1-30 的 FBG 相关参数/定义，以及 t85 的含义或对应表。
- system: `ok` L1-30 FBG 末窗应变剖面 shape_rob25=0.015593；轴为加载窗，不映射寿命分数，t 不适用于该 claim。

### H08 L1-06 在 62% 时能看到 93.76% 的结论吗

- bare: 不能确定。你给的信息里没有说明“L1-06”是什么、62% 指什么指标、93.76% 是什么结论，也没有给出两者之间的关系或数据表，因此无法判断在 62% 时能否看到 93.76% 的结论。
- system: `refused` 时间门未通过：该数值结论超出允许寿命上限，系统不签发 claim。

### H09 报告里写 L1-03 AE t85=76.29，这个数能用吗

- bare: 不能判断这个数能不能用。你只给了“L1-03 AE t85=76.29”这一条，没有说明 t85 的定义、单位、采集条件、判定阈值或报告上下文，我无法核实它是否有效或可用。请补充这些信息。
- system: `unsupported` 当前 L1-03 只支持 metric、dfos、pzt、conflict 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。

### H10 L1-06 的 DFOS 预警点是多少

- bare: 无法确定。你只给出了“L1-06”，没有提供该对象的 DFOS 预警点数据或相关监测信息，我不能编造数值。请补充 L1-06 的 DFOS 监测数据或预警阈值来源。
- system: `unsupported` 当前 L1-06 只支持 metric、pzt 的白名单查询；预测、RUL、损伤类型与维修建议不在可签发范围内。
