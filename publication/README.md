# EJP Publication Platform — Damped Pendulum

本目录管理 `publication/ejp-damped-pendulum` 分支的 **pendulum-focused undergraduate experiment platform**。目标是在Windows x64和macOS Apple Silicon桌面上，让学生从自己视频完成四landmark测量、DLC自训或教师模型导入、QC、θ/phase/period/energy、M0/M1 ODE拟合和structural identifiability教学交互。

## Planning entry points

- [STATUS](STATUS.md)：本线当前状态与确切下一步。
- [Platform requirements](spec/platform-requirements.md)：产品/科学契约与release-level验收。
- [Scientific Asset Inventory](spec/scientific-asset-inventory.md)：论文方法/结果到源代码、配置、数据库表和输出的只读对应。
- [Scientific profiles](spec/scientific-profiles.md)与[golden evidence](evidence/README.md)：P0.1固定的legacy/student契约、source map及只读验证入口。
- [Experiment/run/result contract](spec/experiment-run-derived-contracts.md)与[ADR-0017](../docs/decisions/0017-publication-project-contract.md)：用户批准的schema2与Save As边界。
- [Runtime contract/evidence](evidence/runtime/README.md)：Mac冻结程序探针，Windows未验证；不是正式installer。
- [PHASE_PLAN](PHASE_PLAN.md)：P0–P6边界、Subphases、依赖、review gates与发行风险。

## Baseline

- Product baseline：`62239faee60ad45770d81aeaf2e17abdcada2dfb`。
- Immutable tag：`ejp-damped-pendulum-baseline-phase5.7`。
- Publication line建立日期：2026-09-18；原有Phase5.7的review/CI记录保留。
- 2026-09-19用户明确的新方向：**publication-native scientific development**。核心科学能力和首发打包在本线规划/实现，不等待main Phase6，也不承担main整个通用roadmap。

## Scope / integration

普通Pendulum Mode固定tip/body_top/body_bottom/pivot；保留one Track = one physical point = one DLC bodypart。科学默认来自实际论文科研资产，差异明确记录，不继承main通用值。发行使用lightweight app installer + first-run AI runtime setup；不提供通用pendulum模型或统一训练视频。

通用缺陷仍优先在main修复验证；main适用修复可受控cherry-pick，登记source commit、论文平台需要的原因和本线验证；不机械同步整个Phase。publication-specific分析/交互直接在本线开发，后续subphase集成回publication，不误合main。main状态仍见`docs/status/current.md`；本线会话以`publication/STATUS.md`为准。

不做通用multi-object identity、多相机/3D/任意实验插件、通用model library、论文修改/投稿metadata/Zenodo deposit或新的论文科学补充分析。完整non-goals见requirements。

P0已完成科学/数据/runtime合同与Mac探针；Windows验证经用户批准延至P6前，仍not_run。未实现P1–P6功能。后续每Phase通过科学/工程Independent Review及适用Human Review后收尾，并停止等待下一条指令。未来软件release的构建、验证与版本冻结按P6执行；不提前创建论文submission/published标签或归档事项。
