# Publication P5.3 Independent Review

- 日期：2026-10-02；reviewer：gpt-6-luna/max；主实现方：root；reviewer只读。
- 范围：P5.3新项目入口、三工作区整链接线、恢复/保存指引、学生任务与未完成gate；P5.2科学导出内部由其专项review负责。
- 最终Verdict：待复审；真实用户/学生HR及Windows副本重开没有发生。

## R1 — Request Changes

F1/P2：学生指南在首次Setup要求设置tip radius reference，但tip标注安排在之后的Acquire；setter需要固定pivot和当前帧已有effective tip点。

Reviewer独立入口/工作区导航测试 **2 passed**；确认radius不阻断标注或教师推理，记录模板保持not_run，未发现schema/通用工作区变更。

## 修复与验证

- A支：先在Acquire标出可靠tip，保持该帧，回Setup设置半径参考，再训练。
- B支：先教师模型推理/review/采用，导航到可靠采用tip；必要时手工补正，再设置半径参考。未采用preview不能充当参考。
- Setup下一步也按相同顺序：其他设置完成而没有tip时引导Acquire；有tip才引导半径参考。
- Root定向工作流/GUI/推理门禁 **37 passed（17.14s）**，含新建实验→标tip→设参考的实际session回归。

## R2

待复审。
