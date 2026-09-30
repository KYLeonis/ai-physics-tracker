# Independent Review — Publication P2.3

- Date：2026-09-30；branch `feat/p2.3-energy-analysis-ui`，base `4ec09b6`。
- Scope：reference energy/scalar payload；snapshot消费、signature/capture/currentness；immutable JSON/session事务；后台cancel/generation；半径setup门槛、GUI source frame/trim导航与兼容。
- Reviewer：fresh-context只读subagent `p2_3_review`。首轮 **request-changes (P2)**，未发现P0/P1阻塞；新增源帧链路独立2定向通过。

| ID | Finding | Triage / Fix / status |
| --- | --- | --- |
| F1 (P2) | energy provenance使用canonical source-map不存在的source-energy | FIX：改为energy、policy-student-v1；新增精确来源断言。修复后13定向通过，Closed，复审确认 |
| F2 (P2) | experiment存在即顶部宣称adopted，无active run时与面板提示矛盾 | FIX：有active run才显示adopted四role，否则no active adopted joint inference；真实MainWindow未采用状态回归。Closed，复审确认，真人也须核对 |

## Self-review / verification

- 非线性无阻尼能量恒等式 A=.3/1.4 rad、None/short/gap/nonfinite与实际source identity；q=g/L、s⁻² proxy，非拟合值/焦耳。
- adopted实际点与metadata冻结、relative weight/QC/源帧/绝对与相对time；typed columns含所有scalar，missing带reason。
- worker detached、current assert消费及完成时外部SHA复核；SHA前后stat一致，GUI提交再次检查全部内存事实与文件代际（不是mtime代替SHA）。
- 新ID JSON同目录暂存/flush/fsync/atomic no-overwrite link、hash读；manifest在完整文件后一次Undo事务。Save As/重开、漏置stale、写盘失败、视频改变、取消/关闭/晚到拒绝均有回归。
- radius缺项只阻塞P2计算，不阻断四点标注/训练/推理/采用。source inspection可看working zone外的真实帧，zone和普通播放clamp不变。旧_requestFrame callback默认调用形式恢复兼容。
- 最终 **1218 tests/9 subtests** 全量通过；源帧检查新增一项已计入；旧图表hook失败修复后13定向通过；evidence verifier/diff check通过。
- 复审 **Approve**（独立4定向、此前源帧2定向通过），无开放findings；Human Review待用户亲自测试；不能以自动化或审查替代。P2.3/P2均未关闭。


## Human Review feedback repair — Independent Review

- Scope：本轮相对0ea984a的diff，训练完成自动selftest、Verify & run续跑、取消/失败/关闭/换session/experiment守卫、日期与sidebar文案。
- Reviewer：fresh-context只读 `p2_3_feedback_review`；最终 **Approve，无开放finding**。独立GUI38、worker/core71通过。
- 确认：6种selftest终态、证据拒绝Activity/Cancel收尾、原session/experiment续跑、重新检查busy、推理前完整model/evidence fail-closed；训练→selftest→compatible全链回归。
- 主会话验证：38定向、全量1226 tests/9 subtests；随后仅补证据拒绝Activity终态，6定向通过。evidence15/48/2、diff check通过。真实用户3模型单帧推理均success，用户manifest未覆盖。
- Human Review：用户反馈的按钮截断/模型不能使用/日期已修；Q4–Q5及原Q1–Q3待真人复测。代码审查通过不代表P2已关闭，不集成/不进入P3。


## HR主线稀疏θ/空图 — display repair review

- 用户Q4/Q5已通过；本轮仅Normal-risk显示/诊断：蓝QC/灰geometry-only preview、finite/empty可用性、具体修复帧例子、联合preview frozen role映射与cache key。
- 数值core/共同QC/SG9/3/timeline/schema均未修改；既有adopted数据与用户manifest未写。当前真实旧/new数据均42 QC/最长5/ω0，不能假称最新模型已改善。
- 只读reviewer p2_3_feedback_review：**Approve，无开放finding**。独立GUI21、预测解析/联合推理契约104通过，确认source frame/selected interval、empty autorange拒绝、empty-valid-empty、role切换cache隔离；repair example只指引，不保证分支/非均匀时间等检查必过。
- 主会话：19 GUI定向、全量1228 tests/9 subtests；最后repair文案4 GUI定向；diff check通过。仍等Q6及原Q2/Q3真人复测，不集成/P2不关闭。


## HR建议帧四点修复入口 — Independent Review

- Scope：指定QC缺帧复用既有四role引导/mark_point事务，四点自动下一帧、源帧拒绝/退出/换项目；当前已验证payload入口与stale guard；分析视频只读；联合已采用run不再标not adopted。
- 首轮reviewer p2_3_feedback_review：Request changes，发现工作区切换后joint Correct仍保留角色但点击模式关闭（P2）。独立新增GUI31、既有review/workspace48通过；其余路由/生命周期/科学边界无finding。
- 修复：返回Acquire按joint既有_sync_review恢复当前frame/role点击；_sync_review在Analysis不重开编辑模式，startCorrect显式去Acquire。无selected track的Analysis刷新/零写入/返回后真实落点回归通过。复审Approve，P2 finding closed，32定向通过，零开放finding。
- 主会话：45 GUI定向、全量1230 tests/9 subtests通过；随后分析页calibration模式38定向通过；审查finding修复后41 joint/annotation/workflow定向通过。未改数值core/共同QC/SG/阈值/schema，未覆盖用户项目；仍需Q7及原Q2/Q3 Human Review。
