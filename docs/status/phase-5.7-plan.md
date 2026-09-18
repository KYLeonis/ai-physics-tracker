# Phase 5.7 — Interaction Flow Redesign Mini-Plan

- 日期 / 状态：2026-09-16–18 · ✅ 已完成（R1/R2 CLOSED；最终 Human Review 通过）。
- 分支：`feat/p5.7-interaction-redesign` + `fix/p5.7-hr1-followup`。
- 输入：[phase-5.7-interaction-redesign.md](../design/phase-5.7-interaction-redesign.md)（用户已批准方向，
  含 C1/C2）、[interaction-experience.md](../notes/interaction-experience.md)、AGENTS/CODE_STANDARD/workflow。
- 基线：`main @ 81d97c9`（stabilization + followup 已合并，双平台 CI 绿）。

## Goal

按批准设计把主交互从"常驻 AI Tasks 三列表单"重构为"三个工作区 + 状态驱动任务卡"：
普通用户不选 run/snapshot/mode/series 即可完成 标注→学习→生成→检查→采用→分析；
candidate / active / analysis 三态始终明确；系统给技术默认，用户显式启动/采用/修正；
失败有"发生了什么/数据还在吗/下一步"的明确出口。

## Scope（做）

1. **Qt-free workflow projection**（`application/workflow_projection.py`）：执行/轨迹/分析
   三维状态派生、任务卡选择、fixed-check 预选（C1 规则）、推荐→执行计划、分析可用性、
   失败文案构造。不新增任何持久化状态。
2. **三工作区 + 常驻状态头**（Setup / Acquire / Analysis）：central QStackedWidget；
   ChartPanel 自 dock 转为分析页主体；状态头常显 项目/视频/目标/范围/保存、当前轨迹、
   预览 candidate、分析状态。
3. **TaskPanel 重组为任务卡**：保留全部现有控件对象与信号（测试兼容），布局改为
   卡片(标题/说明/主动作/次动作) + 进度条 + "依据与本次设置" + "调整本次设置"(原三列表单)
   + 检查组(审核时呈现) + "结果与历史"。产品语言按钮：挑选代表画面/开始学习/生成轨迹/
   检查这条轨迹/采用此轨迹/继续优化。
4. **C1**：系统预选检查帧 `min(n−3, max(1, floor(0.2n)))`（n≥4，等间隔、平局取早），
   预览确认后 freeze；可换成员；仅 3 帧给"先尝试学习（无法可靠比较）"次要入口。
5. **C2**：任务卡主动作直接执行系统推荐计划（与 Advanced 走同一执行/验证入口）；
   原 Advisor Apply 只填表语义不变。
6. **采用卡**：审核后摘要(coverage/修正/跳过/比较资格/结论) + [采用此轨迹] 影响预览，
   走既有 activate/replace 原子事务；history 选择只 preview。
7. **分析交接**：四态（尚不能计算/可部分分析/待更新/最新）驱动状态头与主动作；
   采用与更新图表保持两步。
8. **失败 UX**：§13 分类文案（what happened / data safe / next step），集中为可测试构造。
9. Slice 5：GUI teardown F1 修复 + 语义测试矩阵 + Independent Review + re-review + HR gate。

## Non-goals（不做）

Phase 6 物理功能；persistence/domain schema 变更；第二套 workflow 持久化/task runner；
自动训练/推理/采用；HPO；"无困难帧=整段准确"或 confidence→accuracy 的话术；
科学认证 badge；视觉品牌重做；Phase 6/8 charts/export；拆 ProjectSession。

## 关键实现决策

- **不拆现有类**：TaskPanel/TrackingActions/ChartActions/DifficultFrameReviewActions
  保留；新增 `workflow_projection.py`（Qt-free 决策）、`gui/workflow_header.py`（状态头）、
  `gui/fixed_check_dialog.py`（C1 确认）。MainWindow 布局重组但播放/解码管线不动。
- **测试兼容**：TaskPanel 现有公共控件与信号全部保留（现有 GUI 测试不改即过）；
  新行为通过 `setTaskCard`/投影单测 + 新 GUI 测试覆盖。
- **工作区实现**：central `QStackedWidget`（视频页=现有布局；分析页=图表主体 + 视频参照
  （videoView 重父化）+ 来源/状态条）。AI dock 移至右侧作为获取轨迹上下文卡。
- **建议/推荐来源**：投影复用 `advisor_collection` + `training_advisor` + P6R-02 资格；
  比较结论四态 better/flat/worse/incomparable。
- **C1/C2 记录**：新增 ADR-0016（fixed-check 预选确认 + 执行推荐入口），不改写既有 ADR 原文。

## Slices

| # | 内容 | 验证 |
| --- | --- | --- |
| 1 | 投影模块（状态派生/任务卡/预选/计划/分析可用性）+ 三工作区 + 状态头 | 投影单测 + GUI 冒烟 |
| 2 | 任务卡接入主动作执行（C2）+ C1 预选确认 + 学习/生成产品化 | targeted GUI 测试 |
| 3 | 检查/比较/采用卡 + 结果摘要 + history 只 preview | targeted GUI 测试 |
| 4 | 分析交接四态 + 失败 UX 文案 + 状态头分析 chip | targeted 测试 |
| 5 | F1 teardown 修复 + 语义矩阵 + 全量 + Independent Review + re-review + CI | 全量 + CI + HR gate |

## Acceptance Criteria

1. 不选 run/snapshot/mode/series，经任务卡完成 标注→开始学习→生成轨迹→检查→采用→更新图表 全链（自动化测试证明）。
2. 任意状态三问有答案：当前步骤/下一步/能否分析（状态头 + 卡片断言）。
3. candidate 永不进 charts；charts 来源（active+manual）始终可见；采用与更新两步。
4. C1：预选规则确定性可测；freeze 必须经用户确认；3 帧次要入口不建虚假基准。
5. C2：主动作执行计划与 Advanced 参数走同一入口与校验；Apply 语义不变（回归）。
6. Accept 不产生 training label、Skip 不代表正确、no-difficult-frames 不代表整段准确——文案与断言。
7. 四种比较结论（better/flat/worse/incomparable）独立呈现；资格不足不显示优劣。
8. 失败文案回答三问；activation 失败不改状态；取消/中断恢复正确。
9. Undo/Redo、save/reopen、A/S/C 不抢输入、Correct 退出、小窗口可用（回归+新测）。
10. 现有测试全绿（739 基线）；macOS/Windows CI 绿；Independent Review + re-review 通过。
11. Human Review gate：用户实测清单通过前不关闭 5.7。

## Result

- 三工作区、常驻状态头、状态驱动任务卡、C1/C2、候选/采用/分析分离、失败 UX 与
  Ready for Analysis 交接均已实现。
- Independent Review R1/R2 findings 全部 CLOSED；HR1 与两轮补充实测发现的布局、预览、
  审核导航、标定引导、困难帧表达和空筛查状态问题全部修复。
- 最终验证：本地全量 **804 passed**，`compileall` 与 layer boundary 通过；
  [CI run 35319559409](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35319559409)
  的 macOS/Windows jobs 均通过。
- Human Review：用户于 2026-09-18 确认最终三个针对性场景均无问题，AC-11 关闭。
- 无 schema、新依赖或底层科研契约变更；Phase 5.6 AC-9 改善幅度缺口保持原记录。
