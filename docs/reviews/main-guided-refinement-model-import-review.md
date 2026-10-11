# Review Record — Main Guided Refinement / Teacher Model Import

- Issue：[#24](https://github.com/KYLeonis/ai-physics-tracker/issues/24)
- 范围：`6296617..feat/main-guided-refinement-model-import`；S1–S4 与本轮修复。
- Context：[mini-plan](../status/main-guided-refinement-model-import-plan.md)、ADR-0017/0018、AGENTS §7、workflow §6、CODE_STANDARD。
- Reviewer：R1 `/root/independent_review`；R2 `/root/independent_r2`，R3 全新会话复核 F4 补漏。
- 状态：R2 已关闭 F1/F2/F3/F5/F6，F4 busy 入口补漏已修复 `0c71910`，R3 Approve，全部 findings Closed。HR 待用户亲测；此前 HR 不覆盖本轮。

## Findings / Triage

| ID | Severity | Evidence / Impact | Decision / Fix | Verification / Re-review | Status |
| --- | --- | --- | --- | --- | --- |
| F1 | Blocker | Batch Skip 只推进队列，重开仍为 pending | Fix Now：困难帧复用 session Skip 原子事务；保留已有 Correct；代表帧 Skip 不产生标签 | Undo 分步及保存重开回归；R2 确认 | Closed |
| F2 | Blocker | 导入绑定旧 session / video generation；同项目切换视频丢弃导入 | Fix Now：导入绑定 project UUID / root，接收当前 detached 会话；probe 仍绑定 video / generation | 同项目 detached + 视频切换回归；R2 确认 | Closed |
| F3 | Blocker | 自检未约束当前视频；A 的证明可给 B 用 | Fix Now：证明包含 video UUID / source SHA256 / stat；GUI 轻量核对，后台准备 / 推理前后 / 提交核对完整内容 | 不同 UUID / 修改内容 / 同尺寸同 mtime 替换回归；R2 确认 | Closed |
| F4 | Blocker | Analysis 的 Undo/Redo、A/S、隐藏 Track / calibration 入口可写入 | Fix Now：视频编辑共用 writable guard（保持原有 Acquire 静默 autosave 期间 Undo 契约）；显式 Create track 推荐先去 Acquire | Analysis 全入口不变 + Acquire Undo 恢复回归；R3 确认 `0c71910` 已覆盖 busy 期间的标尺 / 原点 / 标定 / Delete 入口及状态恢复 | Closed |
| F5 | Blocker | 重测仅内存撤销旧证明；失败后 Discard / 重开复活授权 | Fix Now：重测前先持久化撤销，保存成功才 spawn；失败不启动 | 启动前重开、取消后重开、磁盘失败不启动回归；R2 确认 | Closed |
| F6 | Suggestion | EXEC_MODEL 缺 mode 映射，运行中显示 blocked | Fix Before Close：映射 Inspect 与已有 cancel 路由 | 运行中 task card mode 回归；R2 确认 | Closed |

Fix commits：`c998fd0`、`0c71910`。R1 后定向 `45 passed（5.18 s）`；复核真实 DLC/MPS probe + infer 成功，全量 `864 passed（55.56 s）`，R2/R3 后最新全量 `865 passed（77.50 s）`。

## Review Log

### R1 — 2026-10-11

- 结论：F1–F5 必须修复后再交付 HR，F6 同轮修复；15 个定向测试通过。
- 首轮发现后的实现补充：模型登记等待既有 save 完成，避免 autosave busy 丢失登记。
- 验证中发现 Qt clear 重入导致一次 segfault；去掉 selection-change → 整体 refresh，清列表加 signal blocker。对应重入回归及后续全量 857 passed（229b7d4）；不是未解释的随机故障。

- 同步事务测试移除 handler 后 qWait20（`8018566`），避免和完成审核后的正常 autosave timer 竞争；保存重开由独立持久化回归覆盖。

### R2 — 2026-10-11 · 新会话复审

- Verdict：Reject，P1 F4 仍阻断；F1/F2/F3/F5/F6 代码和 57 项定向确认关闭。
- F4 补漏：模型 busy 可通过 Draw scale / Origin / Delete 入口写入，既有 calibration mode 也未清除。Analysis 已守住，但模型任务的 shared guard 未覆盖这些回调。
- Fix Now：所有绘尺 / 原点 / Delete 入口复用 canEditVideo；模型开始清除标定 mode；编辑状态变化刷新控件与隐藏写入口，恢复正常控件。
- 新增真实 MainWindow 回归直接调用全部忙碌写入口、确认数据不变和结束后控件恢复；16 项 main/model/analysis、12 项 calibration 定向通过。最新完整回归 `865 passed（77.50 s）`，R3 与 CI 待完成。
- 8018566 的同步事务测试去掉 qWait20 经 R2 确認合理；保存重开回归继续验证持久化。

### R3 — 2026-10-11 · 全新独立会话复审

- Verdict：Approve；F4 Closed。仅复核 `0c71910` 完整 diff、相关初始化 / refresh / 关闭调用链，以及 F4 写入入口，不重审 R2 已关闭且未受改动的 F1/F2/F3/F5/F6。
- `canEditVideo()` 已覆盖本轮相关的 Undo/Redo、手工点删除、Track 增删、标注点击、标尺 / 原点回调、旋转 / 标定编辑 / 删除 / 选择入口。Analysis 与 model busy 均拒绝实际写入；Acquire 的静默 autosave 期间 Undo/Redo 契约仍保留。
- `ModelActions._begin()` 在任务进入 busy 前清除标定按钮和 `videoView` calibration mode；`refresh()` 只在 editable 状态翻转时刷新标定 / history 控件。初始化、busy→idle、workspace 切换和关闭链均未发现 stale control、重复刷新或可写 re-entry；`analysisChanged` 的同步重入在第二次 refresh 时状态不变并收敛。
- 定向复核：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/gui/test_analysis_read_only.py tests/gui/test_model_actions.py tests/gui/test_calibration_ui.py tests/gui/test_main_window.py`，`28 passed（7.95 s）`；`git diff --check 0c71910^ 0c71910` 通过。实现方另报最新全量 `865 passed（77.50 s）`，CI 仍在进行中。
- 未发现新的 Blocker / High finding。Correction mode 的进入只改变内存状态，实际标注写入仍经过共同 guard；忙碌期间控件和隐藏回调均不能落盘或改变项目数据。

## Final Verdict

Approve；F4 已关闭。本轮 Human Review 已发起，待用户完成；未合并 main，Issue 保持 open。

- 实现方收尾确认：最新 `0c71910` [CI 38144024802](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38144024802) macOS/Windows Python 3.11 两个 job 均 success；文档收尾未再修改产品 / 测试。

## Actual runtime evidence

- 只读本地已有 4-bodypart DLC PyTorch 权重，受管副本 + 临时 320×240 三帧视频；spawn 实际帧自检 `auto → mps`，所有关键点有限；完整三帧指定 tip 推理成功。没有修改已有实验 / 论文 worktree。
- Windows CUDA 真机和用户 GUI 体验尚未验证；双平台 CI 只证明对应 Python 3.11 自动化测试。
