# 重复间隔源联动与候选交叉点 — Review Record

2026-10-18；main基线0afe9f9，开发分支`codex/recurrence-linked`，实现0888297。High-risk，Scope / Context / Gate见[计划](../status/recurrence-linked-plan.md)、[ADR-0026](../decisions/0026-live-recurrence-preview.md)。

## Scope

复用SignalPreview独立执行器与源准备，纯预览在application，候选事件不发布记录。正式Measure / 科学算法 / 格式 / 事务不变。保留R01 F1–F3设置归属、未知 / 损坏组及内部冲突拒绝。

## Verification

- 首批GUI兼容与新增预览70项：69 passed；唯一失败为新测试错误地禁止换工具后启动新工具的预览，断言已纠正，旧工具迟到源仍要求不发布。
- 最终定向源 / 新预览 / signal job / recurrence：59 passed（31.81s，277 warnings）。覆盖自动补齐且不碰其他轨迹、空正式槽 / 无尝试日志、参考线 / 方向 / 抑噪与显式Measure一致、保curve / view、不改Undo、raw / 区间 / 量更新、历史 / 换页 / 换方法 / 换轨迹迟到拒绝、Measure不等待预览、已知缺测段 / 非零绝对时间、取消和未知源。
- 0888297产品全量1289 passed（220.19s，1661 warnings）；f5c727a仅补充测试，无源码改动，两文件31 passed（36.65s，301 warnings），追加角量 / 支点 / 单位联动、历史 / 保存 / 失败、工程代际、保存busy延后显示。
- Independent Reviewer `fit_source_final_review`只读审核f7fe7a2..0888297源码及f5c727a测试，**Approve，无新增finding**。独立定向50 passed，先前兼容51 passed；diff检查、compileall、模块导入通过。确认候选事件不发布、生命周期 / 保存busy / 曲线保持、F1–F3与Fit兼容。
- 最终[CI39103525201](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39103525201)，f5c727a的macOS / Windows Python3.11均success（各1293 passed / 2 skipped）；产品初版0888297的[CI39103232233](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39103232233)也均success。CI两个skip为未安装pandas的既有可选测试（test_difficult_frames / test_dlc_predictions），本机全量没有skip。

## Findings / Result

独立完整复审已Approve，无待处置finding；最终双平台CI通过，自动Gate完成。新Human Review尚未通过，产品未合并main。PR [#35](https://github.com/KYLeonis/ai-physics-tracker/pull/35)为diff与CI容器。

## Human Review

[计划中的启动命令与5条操作 → 预期](../status/recurrence-linked-plan.md#human-review自动gate通过后执行)；提供独立工程副本，不替代原工程。待用户亲自反馈。
