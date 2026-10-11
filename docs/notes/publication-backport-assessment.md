# 论文线通用修复回移评估

- 日期：2026-10-11
- 产品线基线：`main @ 3baddf5`；论文 worktree 干净。
- 审查目标：论文集成分支 `publication/ejp-damped-pendulum @ b459e4a`，
  及其尚未集成的发行工作分支 `codex/ejp-p6-4-release @ 154f262`。
- 方法：提交历史/实际双端 diff、共享文件调用路径、论文 review/STATUS、
  `git cherry` patch 等价检查、只读兼容性探针、主线定向测试。

## 结论

有值得回移的通用 UI 修复，建议在 Phase 6 实现前单独做一个小型维护分支；
没有适合整体 merge 的论文分支。论文工作分支相对 main 有 229 个可达提交，
涉及 schema v2、四点联合 AI、科学结果与发行流程；它的 P0–P6 编号也不是主线阶段编号。
回移应仅取目标代码/测试 patch，在主线重新验证并记录 source commit；不复制整个文件。

## 优先回移

| 项目 | 原始提交 / 回移位置 | 主线证据与最小范围 |
| --- | --- | --- |
| 普通鼠标滚轮缩放 | `a13b4b1`；`gui/video_view.py` + `tests/gui/test_video_view.py` | main `wheelEvent` 全部交给 Qt 平移；+120/-120/+60/+240 四种事件 scale 恒为 1.0。候选 handler 在主线内存中分别得到 1.25/0.8/1.1180/1.5625，TouchPad 无 pixelDelta 时保持 scale。仅取设备识别/滚轮 handler 与回归测试 |
| 固定浅色背景的文字可读性 | `a13b4b1`；`gui/main_window.py`、`gui/task_panel.py` | 标定引导框和 Correct 提示按钮设背景但不设前景；深色 palette 探针读出引导框文字 `#ffffff`，补前景后为 `#172b4d`。配齐这两处前景色；主线没有 `nextStepLabel`，不取该 hunk |

以上 video/test 与 main-window/task-panel patch 均 `git apply --check` 通过。
这是部分 patch 的适用性，不表示完整提交可直接 cherry-pick：`a13b4b1` 同时修改了论文状态、
共享治理文档及主线尚不存在的顶部推荐框。更不能整分支 merge。

## 可同批带回的小改进

| 项目 | 原始提交 / 回移位置 | 判断 |
| --- | --- | --- |
| 标注/标定模式的 viewport 光标 | `0f04896`；`gui/video_view.py::_update_cursors` | main 只设置图像/marker 的 cursor，黑边 viewport 仍为 ArrowCursor；补一行 viewport cursor。该文件 patch 适用性检查通过；其余四点连续修正流程不回移 |
| 历史条目显示完整时间 | `231e4d8`、`7cda8cd`；`gui/task_panel.py::_runLabel` | main 条目仅含任务、状态、短 ID，缺少创建时间；复用 `created_at.astimezone()` 显示年月日/时分秒。不取 model_busy、member_track_ids 或模型自检改动 |
| 长任务状态自动换行 | `827f31f`；`gui/task_panel.py::stageLabel` | 可取 `setWordWrap(True)`。该提交的真实联合推理进度属于论文 AI 路径；main 没有 Discarded stage 调用者，不因这一状态增加分支 |

## 保留在论文线 / 暂不回移

| 候选 | 排除原因 |
| --- | --- |
| 顶部常驻下一步按钮（`9f5cff7`） | 主线 WorkflowHeader 的现有契约是导航/状态展示；论文实现联动 publication_task_card、实验与模型操作。可在 6.2 UI 设计时评估，不能直接带回论文专用 action |
| 允许预建空目录（`2b77d2e`）及并发文件保护（`199bc52`） | main 目前拒绝已存在目录，没有论文新空目录清理路径，也没有对应并发误删问题。引入前者是持久化行为扩展，必须一起带保护和测试，另立计划/Independent Review；本轮不归为紧急主线修复 |
| CSV 推理交付/worker.log（`146c6a3`） | 主要解决 frozen host 无 PyTables 与外置 worker 日志位置。main 的单轨 worker 已写 `data/engines/<run>.log` 并登记 log_path，AI 栈仍同环境；不是当前日志读取缺陷。host/runtime 分离时再评估 CSV |
| 联合模型自检/设备路由/模型任务 Cancel（`7cda8cd`、`5ada419`、`231e4d8`） | 依赖论文联合任务、教师模型与 modelActions；主线不存在这一任务类型，不能把论文修复当作单轨路径缺陷 |
| schema v2、四点引导/联合激活、θ/QC/ODE/教学交互 | 已是论文专用领域/科学数据契约，不属于 Phase 0–5 通用维护。主线 Phase 6 继续按自己的需求/ADR/审查门推进 |
| runtime 安装、PyInstaller、Mac FFmpeg LGPL 修复 | 依赖论文发行构建与许可决策。主线尚未打包；留作 Phase 9 输入，不回移 License/运行时架构 |

## 已存在的修复

`4d4e3e9` 与 `6323e11` 在 `git cherry main codex/ejp-p6-4-release` 中均为 `-`
（main 分别已有 `bf8f0c5` / `8a7d90d` 等价 patch）。实际双端
`infrastructure/task_runner.py` 和 `tests/test_task_runner.py` 都无 diff，不重复引入取消修复。

## 验证与执行门

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/gui/test_video_view.py tests/gui/test_workflow_ui.py tests/gui/test_tracking_actions.py tests/test_task_runner.py`：**50 passed，7.07 s**。
- 只读内存探针：主线四种滚轮事件复现、候选 handler 兼容性、TouchPad 保持倍率、
  viewport cursor、深色 palette 前景色核对。没有改动 src/tests，不能代替真人体验验收。
- 本轮为回移建议审查，不做完整论文科学/打包审计，不声称 Windows 新 GUI HR 已通过；
  论文 STATUS 明确仍在等待滚轮/深色提示 Q1/Q2 反馈。
- 用户决定执行后，建立 `fix/main-ui-backports`：优先两项修复，可捎带三项小改进，
  Normal-risk；自动回归后按 AGENTS.md/Workflow §5.1 发起主线 Human Review，
  通过后再 `--no-ff` 集成/push，不带入论文 schema/科学算法/依赖/License。

## 执行接续

2026-10-11 用户已授权回移上述五项；分支 `fix/main-ui-backports`、Issue
[#23](https://github.com/KYLeonis/ai-physics-tracker/issues/23)，代码 checkpoint `53a6fb9`。
最新验证/HR/集成状态见[维护 mini-plan](../status/main-ui-backports-plan.md)，不以本评估的旧只读状态判断实现进度。
