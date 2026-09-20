# Independent Scientific Review — Publication P0.1

- Date：2026-09-20；用户显式要求的独立科学审查。
- Scope：P0.1 scientific profiles、source map/golden evidence、只读verifier/contract tests；不包含数值core、GUI或runtime。
- Context：[mini-plan](../../publication/plans/p0.1-scientific-profiles.md)、[scientific contract](../../publication/spec/scientific-profiles.md)、[evidence](../../publication/evidence/README.md)。
- Reviewer：fresh-context read-only agent `/root/p01_scientific_review`；与实现者分离，无写入权限任务授权。
- 最终 verdict：**PASS — 无未关闭 blocking finding**。F1–F4均由原Reviewer复审确认关闭。
- Continuation：Reviewer在F3修复后因usage limit中断；用户随后明确“继续”，已向同一Reviewer发出followup恢复复审，保留原findings上下文。

## Verification by implementer

13 unittest（旧release、absolute time、压缩gap、角度单位、mask、missing likelihood、JSON/provenance负例）通过；离线15文件和83 external来源只读检查通过。数值重拟合/SG/ODE算法未实现，也未声称通过。

## Findings / triage / re-review

### F1 — Manual source / IC / sufficiency歧义（Blocking，CLOSED：Reviewer复审确认）

Reviewer发现manual weight=1与missing-AI-likelihood排除规则可能冲突；IC valid、N_interval与span未绑定精确统计对象。

处置：student按当前adopted source判断，manual不依赖superseded AI likelihood；AI source缺likelihood才排除；明确base QC在区间截取前计算IC五帧，N_interval包含区间全部源帧，span取fit-valid首末时间。加入manual-policy负例。

### F2 — Golden primary schema/units不够显式（Blocking，CLOSED：Reviewer复审确认）

Reviewer发现fit48/trajectory/inputs24只有文件hash、内容和散文，没有完整manifest字段/单位/比较元数据。

处置：全部15个golden均加入有序columns及逐字段type/unit/nullability/provenance/comparison；IC列指向具体TOML路径并定义嵌套坐标。verifier验证headers、types、nested schema及critical unit metadata；新增unit/column mutation负例。

### F3 — Extrema golden仅有count不足以锁定输出（Blocking，CLOSED：Reviewer复审确认）

Reviewer指出213这个count不足以证明选中了正确帧，原info summary也只是跨视频汇总。

处置：从fig03已归档is_detected_extremum flags提取P011完整213条序列，冻结frame/time/type/theta/omega及完整字段provenance。没有重新运行探峰。offline verifier核对source join/type/order；external verifier比对原始flag完整time序列；负例证明同count但错误frame不能通过。

### F4 — positive timestamp vs positive dt（Blocking，CLOSED：Reviewer复审确认）

Reviewer指出positive timestamps可能排除合法t=0或pre-release负时间。

处置：IC/derivative明确仅要求相邻dt>0、严格递增，允许t_relative=0及pre-release负值；增加机器可读timestamp_zero_allowed与edge contract test。Reviewer已确认此修复闭环。

### Implementer integration check — byte preservation

暂存检查发现Git text=auto会规范化原始CSV的CRLF，导致干净checkout的source SHA不匹配。增加局部.gitattributes：golden/** -text，profiles JSON eol=lf；重新暂存并在core.autocrlf=true临时checkout验证15个冻结文件通过。只改变仓库保存方式，不改科研原件或golden expected字节。

## Final verification / limitations

独立Reviewer实际复核13/13 unittest、offline 15文件/48fit/2完整trajectory、external83 sources，最终明确PASS。未执行历史科研脚本或numerical core；本轮不是P2/P3数值回归完成证明。cross-platform数值容差/完整lock、raw四点与pre-release重建、逐start日志的缺口均已记录，不阻塞P0.1或P0.2契约工作。无GUI增量，不触发GUI Human Review。

Commit范围：本记录随P0.1文档/证据收尾commit保存；integration目标仅publication/ejp-damped-pendulum。后续commit身份可用`git log --oneline -- docs/reviews/publication-p0.1-review.md`定位，不向正文填循环依赖的自身hash。
