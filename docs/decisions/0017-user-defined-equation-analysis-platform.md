# ADR-0017 — User-defined equations for the general analysis platform

## Status

Accepted，2026-10-11。用户明确重申：用户给出方程，平台完成之后的通用计算与分析。

## Context

论文 publication 线以复现指定单摆论文为目标，硬编码了 M0/M1 ODE。main Phase 6 的早期草案列出固定拟合模型，未明确表达产品口径，容易把论文复现方案当作主线架构。

## Decision

- main 的长期分析接口以用户提供的公式 / 方程、变量与参数、输入数据、初始 / 边界条件为中心；平台负责计算、拟合、比较、图表与可追溯结果。
- 单摆是基准 / 示例，论文硬编码 ODE 只作实现与验证参考；不以指定单摆 ODE 取代通用方程输入。
- 方程表示、解析范围、单位校验、求解与拟合接口将在 Phase 6 重新规划；不允许通过任意 Python eval/exec 执行用户表达式。
- 角运动 / 求导 / 周期等可复用计算与通用图表仍是输入能力；本决策不批准旧 Phase 6 草案的具体数值门槛或求解器选型。
- 当前优先交付 Analysis 只读、建议帧批次修正、教师模型导入 / 实际帧自检；不在本轮实现方程引擎。

## Consequences

旧 Phase 6 requirements / master / 6.1 草案须按此口径复核后再实施，不能把固定拟合列表当作已批准范围。论文专用科学代码不能整体 merge；未来可作为已声明方程的示例及回归证据。
