# DepthBenchCAD

[简体中文](README_zh-CN.md) | [English](README.md)

**DepthBenchCAD：更多审计何时能带来更可靠的结论？**

本仓库是 **DepthBenchCAD** 的可执行发布版。DepthBenchCAD 是论文 *DepthBenchCAD: When Does More Auditing Yield More Reliable Conclusions?* 提出的三级反事实审计基准，用于研究在固定评估预算下，如何在任务模板、独立模型生成结果及同一程序内部的反事实编辑状态之间分配评估证据。

DepthBenchCAD 基于 BenchCAD 任务语料构建，包含两个互不重叠的评估环境：**DepthBenchCAD-A** 包含来自八个任务族的 72 个模板（24 个校准、48 个测试）；**DepthBenchCAD-B** 包含来自六个不重叠任务族的 48 个模板（12 个校准、36 个测试）。每个模板都包含独立的 CadQuery 参考程序、合法参数范围、任务约束，以及 16 个冻结编辑状态：局部、边界、关联和语义编辑各 4 个。

发布内容包含 2,760 条生成级记录、44,160 条状态级审计记录，以及 800 条双人标注的专家验证样本。公开数据包提供基准分析所需的标识符和结果字段；不包含服务商侧提示词、候选源代码、token 用量、原始延迟日志或解码元数据。

## 基准结构

| 环境 | 模板数 | 任务族数 | 校准 / 测试 | 每模板生成数 | 每程序状态数 | 系统数 | 审计记录数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| DepthBenchCAD-A | 72 | 8 | 24 / 48 | 5 | 16 | 5 | 28,800 |
| DepthBenchCAD-B | 48 | 6 | 12 / 36 | 4 | 16 | 5 | 15,360 |

为使记录字段更简洁，代码中保留了环境内部简称 `A` 和 `B`；它们分别与 DepthBenchCAD-A 和 DepthBenchCAD-B 一一对应。

## 快速开始

需要 Python 3.10 或更高版本。CAD 执行器针对 CadQuery 2.5.x / OCCT 7.8.x 设计。

~~~powershell
python -m pip install -r requirements.txt
python scripts/validate_release.py
pytest -q
~~~

生成或验证 DepthBenchCAD 任务语料：

~~~powershell
python scripts/prepare_depthbenchcad_tasks.py
~~~

使用冻结状态审计新的模型生成清单：

~~~powershell
python scripts/run_audit.py --templates data/templates/depthbenchcad_tasks.json --generations data/runs/generations.jsonl --output data/runs/audits.jsonl
python scripts/analyze_records.py data/runs/audits.jsonl --out data/runs/report.json
~~~

每条待评估的生成记录都需标明系统、模板和生成结果，并提供候选源代码或 CadQuery 程序路径。执行器会运行名义程序及所有指定的冻结编辑状态，然后记录构建状态、几何探针结果、裁判阶段和审计结论。按照论文协议，初始程序无效时，主要风险估计会将全部 16 个状态计为失败。

## 已发布数据

### 任务定义

`data/templates/depthbenchcad_tasks.json` 包含 120 个 DepthBenchCAD 任务定义及全部 1,920 个冻结编辑状态。`data/programs/` 包含对应的 CadQuery 参考程序。任务源自 BenchCAD；DepthBenchCAD 在此基础上增加了论文所用的冻结环境划分、反事实状态集合、执行与裁判约定、成本协议和审计记录层级。

### 生成记录

`data/generations/` 包含 1,800 条 DepthBenchCAD-A 生成记录和 960 条 DepthBenchCAD-B 生成记录。每条记录都将系统、模板和生成结果标识关联到其 16 个已审计状态，并记录汇总失败数及编辑类型细分。公开生成清单有意不包含候选源代码，因此这些记录中的 `candidate_program_available=false`。这不影响以审计结果为输入的记录级统计分析。

### 审计记录

- `data/records/depthbenchcad_A_audits.jsonl`：28,800 条 DepthBenchCAD-A 审计结果。
- `data/records/depthbenchcad_B_audits.jsonl`：15,360 条 DepthBenchCAD-B 审计结果。
- `data/records/depthbenchcad_A_expert_annotations.jsonl`：从 DepthBenchCAD-A 抽取的 800 条专家验证样本。

以上文件是论文分析流程的规范输入。

## 复现论文分析

~~~powershell
python scripts/reproduce_tables.py --records-a data/records/depthbenchcad_A_audits.jsonl --records-b data/records/depthbenchcad_B_audits.jsonl --expert data/records/depthbenchcad_A_expert_annotations.jsonl --out-dir results/reproduced
python scripts/validate_paper_results.py --results results/reproduced
~~~

分析流程会重新计算：三级方差分量和有限总体设计误差；冻结审计深度网格上的定深度比较；`k=4→8` 和 `k=8→16` 的收益方向预测；汇总、留一系统、完整系统和按编辑类型分层的分配策略；共享 / 系统 oracle 遗憾值及 5% 稳健覆盖率；重复的按任务族分层划分及留一任务族迁移；DepthBenchCAD-A 到 DepthBenchCAD-B 的迁移；逆概率专家验证和 Cohen's κ；在 512 / 1024 / 2048 预算下的配对模型决策重放；以及三级模型与程序独立模型的 95% 区间覆盖率。

`results/reproduced/` 中包含使用 `--replay-scale 0.02` 生成的轻量验证快照。不使用该参数时，将运行完整冻结重放协议（`1.0`）。`data/paper_results.json` 是论文中报告数值结果的机器可读转录文件。

## 评估协议

`configs/paper_protocol.json` 记录了 DepthBenchCAD 协议：主随机种子 `20270901`、预算 `512/1024/2048`、模板与编辑成本、系统特定的生成成本、超时设置、重试策略、环境划分、固定审计深度、转移比较、区间实验，以及专家验证抽样设计。

自动裁判按照论文第 4.2 节的顺序执行：

1. 构建是否完成；
2. 实体是否有效、连通分量是否符合要求；
3. 拓扑及圆形 / 孔洞特征；
4. 编辑参数是否产生预期响应；
5. 尺寸、间距、对称性和包含关系；
6. 高层语义约定。

长度容差为 `max(0.05 mm, 0.001*Lref)`，角度容差为 `0.1 deg`，相对体积容差为 `0.5%`。拓扑计数精确匹配，不设置浮点容差。落入配置灰区的数值案例会转交人工复核，不会被直接判定。

应用人工复核标签：

~~~powershell
python scripts/apply_review_labels.py --audits data/runs/audits.jsonl --reviews data/runs/reviews.jsonl --output data/runs/audits_resolved.jsonl
~~~

## 仓库结构

- `src/depthbenchcad/catalog.py` — 从 BenchCAD 源语料派生的 DepthBenchCAD 任务目录。
- `src/depthbenchcad/audit.py` — 冻结编辑状态的构建。
- `src/depthbenchcad/executor.py` — 隔离的 CadQuery 执行与几何探针。
- `src/depthbenchcad/judge.py` — 有序自动裁判和灰区转人工复核。
- `src/depthbenchcad/variance.py` — 三级方差方程和有限总体校正。
- `src/depthbenchcad/allocation.py` — 对可行 `(q, g, k)` 组合的穷举搜索。
- `src/depthbenchcad/replay.py` — 嵌套有限池重放和程序级均方误差。
- `src/depthbenchcad/strategies.py` — 汇总、留一系统、系统、分层和配对分配方法。
- `src/depthbenchcad/paper_analysis.py` — 第 4.3 至 5.3 节的分析层。
- `examples/` — 单条生成记录的最小执行示例。
- `scripts/run_audit.py` — 使用冻结基准审计新的候选程序。
- `scripts/reproduce_tables.py` — 从已发布记录复现论文分析。
- `scripts/validate_release.py` — 验证语料、记录数量及关联关系。
- `scripts/validate_paper_results.py` — 验证复现的论文级不变量。
- `docs/` — 裁判、协议、分析和验证文档。

## 验证

在仓库根目录运行完整发布检查：

~~~powershell
$env:PYTHONPATH = "src"
pytest -q
python -m compileall -q src tests scripts data/programs
python scripts/validate_release.py
python scripts/validate_paper_results.py --results results/reproduced
~~~

验证套件检查任务数量、状态组成、生成记录与状态的关联、专家样本量、分配可行性、有限池抽样、聚类区间、分层、配对比较、收益预测、遗憾值汇总和专家一致性。

## 公开数据范围

仓库公开发布 DepthBenchCAD 任务、参考程序、生成标识、状态级结果、专家验证标签、裁判和完整分析代码。服务商侧候选源代码及服务商遥测数据不在公开数据包内。因此，用户可以基于已发布结果记录端到端地验证基准及论文报告的统计分析，但无法独立验证此处未提供的外部服务商对话记录。

## 许可证

代码和仓库材料采用 MIT License 发布。详情见 `LICENSE`。
