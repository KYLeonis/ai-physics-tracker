# Maintenance Plan — Main UI Backports

- Issue：[#23](https://github.com/KYLeonis/ai-physics-tracker/issues/23)
- 分支：`fix/main-ui-backports`（base `main @ 50a7924`）
- 日期 / 状态：2026-10-11 · 本地验证通过，CI / Human Review 待完成
- 风险等级：Normal-risk（局部视频交互与展示，不改科学/数据契约）

## Goal

主线获得论文线已验证的通用鼠标缩放与提示可读性修复，以及三项小型展示改进。

## Agent Context Pack

- Authoritative Docs：[回移评估](../notes/publication-backport-assessment.md)、
  `docs/spec/phase2-requirements.md` R4/R5、Phase 5 R3/R5、`CODE_STANDARD.md`、
  `docs/workflow.md` §5.1/§10.2、`docs/research/open-source-project-map.md` §3.2。
- Relevant Historical Findings：论文 `docs/reviews/publication-p6.4-review.md` 的
  2026-10-08 GUI follow-up，用户报告 Windows 鼠标滚轮与深色提示问题；
  主线此前 Human Review 要求触控板滑动平移，因此仅普通垂直鼠标滚轮改为缩放。
- Invariants：触控板/pixelDelta/scroll phase 保留平移；无视频/横向滚轮不缩放；
  复用现有倍率范围、映射与 ZOOM_STEP；滚轮不造标注；raw、schema、任务与 AI 激活行为不变。
- Deferred / Accepted：Windows/CUDA 完整真机验收仍延期；本次主线 GUI Human Review 单独执行。
- Non-goals：论文 schema v2、四点模式、顶部推荐框、模型任务、科学分析、依赖/许可/打包。

## Scope / 来源

1. `a13b4b1`：video_view 的普通鼠标滚轮处理及十项回归；main_window 标定引导框、
   task_panel Correct 按钮明确前景色。不回移 WorkflowHeader/论文文档。
2. `0f04896`：viewport 光标与标注/标定状态同步。
3. `231e4d8` + `7cda8cd`：历史条目显示本地年月日时分秒，仅修改展示。
4. `827f31f`：stageLabel 自动换行，不引入论文专用进度/Discarded 分支。

改动面：三个 GUI 源文件、video_view 回归测试、计划/current/评估记录；
现有调用者接口、fixtures、config、exports 无变化。

## Acceptance Criteria

- [x] AC-1：普通滚轮正/负/半档/多档缩放；TouchPad/pixelDelta/phase/横向/无视频不改变倍率；滚轮不触发标注。
- [x] AC-2：深色 palette 下浅色引导框与 Correct 提示有可读前景；历史显示完整本地时间，长状态可换行。
- [x] AC-3：标注/标定黑边光标与模式一致；关闭模式恢复；标注/标定/导航既有回归不退化。
- [ ] AC-4：定向/全量 pytest、diff 检查与双平台 CI 通过。
- [ ] AC-5：用户按下方步骤 Human Review 通过，然后 `--no-ff` 集成/push 并关闭 Issue。

## Slices / Verification

- [x] Slice 1：建立分支/Issue，按源提交选取最小 patch，验证回归及展示。
- [ ] Slice 2：self-review、全量测试、文档 checkpoint/push/CI，交付主线 Human Review。
- [ ] Slice 3：反馈修复（如需要），HR 通过后集成与收尾。

定向：video_view、calibration_ui、manual_annotation、suggested_frame_review_actions、
tracking_activation_actions、workflow_ui；全量：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`。
深色 palette /历史时间/viewport 状态用实际 widget 断言核对，视觉与手感由用户确认。

## Review Gate

- Independent Review：不触发，Normal-risk 小型 GUI patch，self-review + 回归。
- PR：不需要；Issue 保存范围/验证/反馈。
- Human Review：**适用，必须在集成前等待用户反馈**（AGENTS.md §7、Workflow §5.1）。

## Human Review

从仓库启动：`.venv/bin/python -m ai_physics_tracker`。

1. 打开视频，普通鼠标上下滚轮 → 放大/缩小；触控板滑动仍平移，捏合仍缩放。
2. 创建/选择 Track，进入标注；指针移到视频黑边 → 十字；关闭标注 → 恢复浏览光标。
3. 切到实验设置并开始标定 → 深色系统外观下浅蓝引导框文字清楚；比例尺/原点仍可正常选取。
4. 若已有 AI review 队列，点 Correct → 浅橙提示文字清楚；查看历史 → 完整日期/时分秒可见。

请回复：Q1 缩放/触控板手感通过或需调整；Q2 光标/提示/历史通过或需调整。
没有鼠标或 review 队列的项注明未测，不当成通过。

## Result

- 代码 checkpoint：`53a6fb9`，包含上述源提交的目标 patch 与溯源记录。
- 定向测试：107 passed（12.60 s），覆盖缩放/标定/标注/审核/激活/任务面板/工作区。
- 原处理函数的进程内回归：四种鼠标滚轮 case 均按预期失败；没有回滚产品文件。
- 实际 widget 断言：深色 palette 两提示前景/背景、标注/标定 viewport 模式进入退出、
  历史日期时间前缀和窄宽度长状态换行均通过；不替代用户体验验收。
- 全量测试：**815 passed（49.36 s）**；`git diff --check` 通过。CI 在分支 push 后核对。
- Human Review 尚未执行；Issue 保持 Open，未集成 main。
