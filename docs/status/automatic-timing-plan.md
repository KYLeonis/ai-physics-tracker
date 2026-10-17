# 自动接受近似时序 — 实施计划

- 日期：2026-10-17；用户授权取消Review timing / Yes确认。
- 分支：`fix/automatic-timing-acceptance`，基线main@9250a3e（P6.3.1 HR通过并已集成）。
- Goal：程序完成原Yes动作，检测完成即可继续，不要求用户额外判断。

## Agent Context Pack

AGENTS / CODE_STANDARD；ADR-0007（原检测 / 预算）、[ADR-0024](../decisions/0024-automatic-near-cfr-acceptance.md)（本次覆盖）；`TimingActions`、`ProjectSession.accept_approximate_timing`、`approximation_errors`；`test_timing_actions.py`、`test_timing_approximation.py`与`test_signal_analysis.py`。P6.3.1 R6历史授权迟到拒绝保持。

## Scope / AC

- [x] 同步 / 后台打开、重开、切视频，对合格Near-CFR自动接受，不出现Yes弹窗或Review timing入口。
- [x] 新来源记录auto，旧记录不改写；近似FPS与误差可见，原Timeline / raw / 数值计算保持。
- [x] unknown / VFR / 超预算 / 不匹配 / 取消仍给出原因，必要Retry保留；保存忙 / 换上下文不误授权。
- [x] Acquire标注与Analysis Fit / Measure均无需额外点击，回归、独立复审及双平台CI通过，给出新HR步骤。

## Review Gate

High-risk（时序权限 / 来源契约），Independent Review必须，只读Reviewer审main基线后的diff及上述契约。定向测试后全量、macOS / Windows CI；交付新交互后按AGENTS §7停等用户HR。PR可选。不开始6.4 / 6.5或架构重构。

## Human Review（2026-10-17通过）

保存并关闭旧窗口。使用已有P011副本，原启动器不重置数据：

```bash
PYTHONPATH=/Users/leonis/.codex/worktrees/bd40/ai-physics-tracker/src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python /Users/leonis/Documents/ai-physics-tracker/experiment/p631-human-review/start_p631.py
```

1. 打开 / 重新打开原先需要Yes的视频，检测结束应直接可标注，显示`Approximate timing (automatic)`及FPS / 误差，没有Review timing / Yes确认。
2. 进入Analysis → Fit a formula / Measure repeat intervals。已有可用源时按钮直接可用；需要准备源时按源准备提示操作，整个流程不再要求判断时序。再重开同样自动检测 / 采用，旧标注与历史结果保留。

请用户回复本轮免确认流程“通过 / 不通过”。按AGENTS §7，新交互通过后才合并此补丁；上一轮P6.3.1 HR已单独收口。

## Verification

产品f34053f；主Agent46 / 91项、charts单项通过；只读独立复审Approve（73项）；本机全量1241 passed（307.87s）。后续4a713bc仅删除多余Timing准备入口，定向31 passed（20.30s），独立末轮51项通过并Approve；最后双平台CI回执见下。见[review](../reviews/automatic-timing-review.md)。原main@9250a3e的双平台CI39011226102成功，P6.3.1 Issue #31 / PR #32已关闭 / 合并。本轮用户HR通过后，此补丁以--no-ff集成main。

最终产品`4a713bc`的[最终CI39011866524](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39011866524) **success**，macOS / Windows Python3.11各 **1239 passed / 2 skipped**（可选pandas），安装 / FFprobe / 测试 / 清理步骤全部完成。后续只改文档，源 / 测试树与此SHA相同，不将文档HEAD说成另跑过CI。2026-10-17用户明确回复“通过”，新交互HR完成，补丁以--no-ff集成main。

## Result

2026-10-17：本轮用户HR通过，所有AC / Gate闭环，以--no-ff集成main；集成时只同步文档，产品 / 测试树与4a713bc一致。原启动命令继续可用，main启动也包含免确认流程。等待下一条指令，不开始6.4 / 6.5。

main集成`801fda5`的[CI39014441071](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39014441071)已完成，macOS / Windows Python3.11均success；源 / 测试 / CI配置与已验收`4a713bc`完全一致。本次回执仅改文档。
