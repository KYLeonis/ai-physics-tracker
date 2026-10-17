# 自动接受近似时序 — 实施计划

- 日期：2026-10-17；用户授权取消Review timing / Yes确认。
- 分支：`fix/automatic-timing-acceptance`，基线main@9250a3e（P6.3.1 HR通过并已集成）。
- Goal：程序完成原Yes动作，检测完成即可继续，不要求用户额外判断。

## Agent Context Pack

AGENTS / CODE_STANDARD；ADR-0007（原检测 / 预算）、[ADR-0024](../decisions/0024-automatic-near-cfr-acceptance.md)（本次覆盖）；`TimingActions`、`ProjectSession.accept_approximate_timing`、`approximation_errors`；`test_timing_actions.py`、`test_timing_approximation.py`与`test_signal_analysis.py`。P6.3.1 R6历史授权迟到拒绝保持。

## Scope / AC

- [ ] 同步 / 后台打开、重开、切视频，对合格Near-CFR自动接受，不出现Yes弹窗或Review timing入口。
- [ ] 新来源记录auto，旧记录不改写；近似FPS与误差可见，原Timeline / raw / 数值计算保持。
- [ ] unknown / VFR / 超预算 / 不匹配 / 取消仍给出原因，必要Retry保留；保存忙 / 换上下文不误授权。
- [ ] Acquire标注与Analysis Fit / Measure均无需额外点击，回归、独立复审及双平台CI通过，给出新HR步骤。

## Review Gate

High-risk（时序权限 / 来源契约），Independent Review必须，只读Reviewer审main基线后的diff及上述契约。定向测试后全量、macOS / Windows CI；交付新交互后按AGENTS §7停等用户HR。PR可选。不开始6.4 / 6.5或架构重构。
