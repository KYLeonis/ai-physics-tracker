# Publication P5.3 Independent Review

- 日期：2026-10-02；reviewer：gpt-6-luna/max；主实现方：root；reviewer只读。
- 范围：P5.3新项目入口、三工作区整链接线、恢复/保存指引、学生任务、真实推理进度与未完成gate；P5.2科学导出内部由其专项review负责。
- 最终Verdict：R5 **Approve**，零开放finding；F1/F2 Closed，训练循环三项用户HR通过。新进度视觉HR、非开发学生pilot及Windows副本重开待执行。

## R1 — Request Changes

F1/P2：学生指南在首次Setup要求设置tip radius reference，但tip标注安排在之后的Acquire；setter需要固定pivot和当前帧已有effective tip点。

Reviewer独立入口/工作区导航测试 **2 passed**；确认radius不阻断标注或教师推理，记录模板保持not_run，未发现schema/通用工作区变更。

## 修复与验证

- A支：先在Acquire标出可靠tip，保持该帧，回Setup设置半径参考，再训练。
- B支：先教师模型推理/review/采用，导航到可靠采用tip；必要时手工补正，再设置半径参考。未采用preview不能充当参考。
- Setup下一步也按相同顺序：其他设置完成而没有tip时引导Acquire；有tip才引导半径参考。
- Root定向工作流/GUI/推理门禁 **37 passed（17.14s）**，含新建实验→标tip→设参考的实际session回归。

## R2

- 复审commit：`5228537`。Reviewer确认A/B与setter前置一致，Setup提示无残留死路，未采用preview没有被当作effective tip。
- 独立新增session回归 **1 passed**；F1 Closed，无开放blocking finding。
- 三项Independent Review通过不代替真实学生/用户HR；pilot保留not_run，P5不能标完成。

## R3 — training-loop HR follow-up / Request Changes

- 范围：`777c92b..916adeb`，预声明High-risk [mini-plan](../../publication/plans/p5.3-hr-training-loop.md)；root实现，gpt-6-luna/max只读。
- F2/P2（Reviewer本轮称F1）：最新failed/cancelled inference无条件覆盖标签digest变化的建议顺序。新增四点标签后仍主推Retry inference，违背先重训再使用更新标签的循环要求。
- Reviewer独立10项定向通过（4.35s）；帧集并集/partial标注保留、experiment owner、fixed-check No不训/Yes继续、在途autosave新增标签落盘与session/experiment guard、当前实验新模型默认选择无开放finding。
- Root修复`87d5e89`：标签变化时保留retrain primary，失败/取消历史仍可查；旧标签保持Retry。真实session cycle回归参数化failed/cancelled，补齐交叉状态；定向工作流+GUI21 passed（6.17s）。
- `916adeb`主全量1357 passed / 1 existing strict xfailed / 9subtests（198.08s）；strict xfail仍为ADR-0020 Accepted Limitation，未记为数值通过。修复只涉及任务卡分支及回归，无算法/schema改动。

## R4 — Approve

- 复审`87d5e89`；F2 Closed，零开放blocking finding。
- Reviewer确认failed/cancelled只在标签不变时覆盖主步骤；changed保留digest派生的Train/Label顺序，history仍存在。独立参数化failed/cancelled回归2 passed（1.86s）。
- 最终GUI HR待复测；不得将自动化/Independent Review等同于学生pilot或Windows真机验收。

## R5 — inference progress / Approve

- 范围：`59acdf7..827f31f`；[High-risk mini-plan](../../publication/plans/p5.3-hr-inference-progress.md)；root实现，gpt-6-luna/max只读review。
- 无finding。Reviewer确认计数来自后处理帧，run/分母一致且有界读取；坏/截断记录忽略；新run重置、100%仍running直到结果验证、取消后拒收迟到success，session切换后进度/结果均不应用。
- 独立定向6 passed（11.21s）。Root定向60 passed（37.30s），最终parser/进度/session swap三项3 passed（10.74s）。
- 新视觉必须用户亲测；前轮用户三个训练循环HR通过不替代此项或外部学生/Windows真机gate。

- 最终源码`827f31f` CI run[36972340803](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36972340803) Windows/macOS success；后续文档同步无代码/测试变更。
