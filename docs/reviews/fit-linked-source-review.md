# 公式拟合联动与源自动补齐 — Review Record

2026-10-17；基线main `d38d15e`；分支`codex/fit-linked-source`。High-risk，范围与契约见[计划](../status/fit-linked-source-plan.md)、[ADR-0025](../decisions/0025-automatic-fit-source-preparation.md)。

## Scope / Gate

当前可编辑公式拟合页自动准备选中轨迹的源分析组，复用已有job / 原子提交；相关源变化刷新预览、单位和说明。正式Fit / 尝试记录仍显式，历史只读。核对切工程 / 轨迹 / 区间 / 参考 / 工作区、取消 / 保存忙 / 迟到、未知配方和不重试循环。普通图表与重复间隔不自动准备。

## Verification / Independent Review

- 主Agent定向：源准备应用层、GUI联动、guided fit、signal analysis、历史查看、角运动图表与分层规则，93 passed（61.64s）。
- `288d836`本机全量1268 passed（121.56s，1609 warnings）；样本结构 / 本轨迹配方补充回归32 passed（2.36s）。最终F3修复`8ea1f1b`定向48 passed（12.15s），最终全量1271 passed（121.19s，1609 warnings）。
- 初版`7260772`双平台CI 39016589154成功；修复后`288d836`双平台CI 39045775556成功。最终`8ea1f1b`的[CI 39046152498](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39046152498) macOS / Windows Python3.11均success，不沿用初版结果。
- 独立只读Reviewer `fit_source_review`首轮发现F1 / F2；修复后复审因额度限制未运行。新Reviewer `fit_source_final_review`确认F1 / F2修复有效，另发现F3；最终对`8ea1f1b`复审 **Approve，无新增阻断性问题**，独立应用层 / 新GUI回归30 passed。
- 本轮Human Review已交付独立副本、启动命令和4条操作 → 预期（见计划）；2026-10-18用户回复“通过”，本轮HR完成。未以既有P6.3.1 / 时序补丁HR替代本轮。

## Findings / Result

| Finding | 影响 | 实现方处理 | 独立复审 |
| --- | --- | --- | --- |
| F1 / P1 | 拟合独立选择轨迹B时，可能误用Charts轨迹A的SG / 角参考 | `288d836`按控件所属轨迹区分；B沿用自己的记录。缺失线性组沿用既有默认7/2，角参考不猜测；准备 / 发布 / 预览核对同一设置 | Closed；新Reviewer确认 |
| F2 / P1 | stale源中不匹配量的已知步骤可能被自动覆盖 | `288d836`复用配方结构校验，覆盖前检查组内每条记录的步骤 / 参考 / 单位 / 时序 / 观测选择 / 样本宽度与顺序 | Closed；新Reviewer确认 |
| F3 / P1–P2 | 同组各记录虽单独合法，但SG / 支点等定义冲突，选首条会覆盖其他定义 | `8ea1f1b`自动替换前要求组内标定 / 参考 / unwrap / SG公共参数一致；冲突保留数据并引导Charts显式确认重算，3种冲突回归 | Closed；独立复审确认两种控件归属路径 |

两项较低优先级观察一并处理：源未就绪时Fit禁用并说明原因；导数量尝试 / 历史使用实际SG derivative语义。新增多轨迹 / 导数历史GUI回归及六种stale损坏输入拒绝回归。

最终自动Gate与本轮HR均通过，2026-10-18以`aa86d79` `--no-ff`集成main。合并树与分支262da6a一致，源码 / 测试与已验证8ea1f1b一致；本轮收尾未再改产品。PR [#33](https://github.com/KYLeonis/ai-physics-tracker/pull/33)记录完整diff；论文线及用户实验未改。

收尾提交`0b80008`的[主分支CI39099618728](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39099618728) macOS / Windows Python3.11均success；之后只补此文档回执，源码 / 测试树保持不变。
