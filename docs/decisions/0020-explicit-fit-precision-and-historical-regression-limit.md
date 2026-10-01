# ADR-0020 — Explicit fit precision and historical regression limit

## Status

Accepted，2026-10-01。用户在查看P3.2失败证据后明确回复“没有问题，继续P3.3/P3.4”，接受保留历史复现缺口并提供显式高精度设置。

## Context

24×2完整回归E3仅30/48通过（M0 24/24、M1 6/24），E2 47/48；源公式/输入parity独立审查成立，但默认adaptive integration与finite-difference耦合会令无噪声M1错误收敛。当前macOS/NumPy1.26.4与归档Windows/NumPy2.4.3环境不同。完整证据和F1/F2见publication P3.2 review及regression摘要。

## Decision

- 冻结legacy/student profiles、expected和E2/E3容差保持原值，失败数值保持失败，不改成通过。
- 用户允许将当前超限和冻结默认M1恢复缺口作为已接受限制继续开发。P3.2 AC1/AC7以“显式高精度synthetic恢复 + 默认限制记录 + 完整48项差异/独立审查/用户裁定”收口，不声称默认或历史回归已通过。
- 新拟合请求提供显式High precision（DOP853 rtol2e−10/atol2e−12）与Historical precision（2e−7/2e−9）及Advanced自定义。UI明示当前选择与实际值，初始推荐High precision；历史结果读回原值，无自动重试或静默替换。
- actual resolved integration/optimizer/IC/interval/bounds/sample/loss进入请求身份和immutable结果；Normal/Advanced共用core，不依赖SG能否产生导数。
- optimizer success表示数值停止条件满足，不代表参数唯一/模型正确；历史精度选择显示已知敏感性，拟合比较不输出二次阻尼证明。
- Windows精确历史环境复跑作为P6前已有平台门禁的后续证据任务；本轮不增加依赖或伪造跨平台认证。

## Consequences

继续P3.3/P3.4，但科学复现限制永久可追溯。高精度可能较慢，不保证全部视频最优或可辨识；用户可以查看各start/cost/convergence并改变明示配置。
