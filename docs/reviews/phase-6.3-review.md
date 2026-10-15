# Review Record — Phase 6.3 User-defined Function Fitting and Signal Recurrence

- Subphase / Issue：P6.3 / [#29](https://github.com/KYLeonis/ai-physics-tracker/issues/29)
- 当前轮次：R0，2026-10-15，S0数据契约的定向独立检查；R1已Approve，实现与最终Independent Review尚未开始。
- 冻结范围：`9bf9acd` 中ADR-0021 / GLOSSARY及必要连接代码；不将文档检查当作未实现算法的验收。
- Context：[6.3计划](../status/phase-6.3-plan.md)、[ADR-0021 Accepted](../decisions/0021-function-fit-and-recurrence-result-contract.md)、ADR-0017/0019/0020、CODE_STANDARD。
- Reviewer：R0请求全新ZCode GLM-5.3 / plan；600s超时，无实际模型核验 / 审查结论。R1改由全新Luna-max只读会话审同一冻结契约。

## Checklist

- [x] 源与目标结果身份、样本快照、时间语义、依赖失效 / 删除 / Undo规则自洽
- [x] 不破坏既有schema / clear语义，旧项目和未知扩展有明确保留策略
- [x] 区分交叉重复间隔与物理周期，不以单摆作为通用模型约束
- [ ] 科学算法有解析合成测试与真实基准证据（未实现）
- [ ] 完整实现 / 全量 / 双平台CI通过（未实现）
- [ ] 新Human Review通过（未实现）

## Findings

R0没有可用结论；R1 Approve，无实质finding。

## Review Log

### R0 — S0定向契约检查（2026-10-15）

- 冻结：`9bf9acd`。
- 范围：结果槽、源快照、两类版本栅栏、生命周期、兼容保存、重复间隔含义。
- 模式：只读；不修改产品或文档、不装依赖、不访问用户实验 / 凭据、不调用其他Agent。
- 结果：runner `worker_failed` / worker `timed_out`（600s），stdout / stderr为空，actual_model_selection=null，checks未配置。CLI已退出；Desktop原生任务登记成功，不代表模型 / review通过。无额度耗尽或网络错误证据；不重复派工，改由用户已授权的Luna-max完成窄范围检查。

### R1 — 全新Luna-max定向契约检查（2026-10-15）

- 冻结范围同`9bf9acd`；只读、无文件 / Git变更。Verdict：**Approve，无实质finding**；明确核对两族结果槽、source / target版本、删除 / stale / Undo、clear语义、未知 / 未来版本及科学含义。未审未实现的数值 / GUI，未跑测试。
- 不继承实现过程叙述；只检查契约与必要连接代码。

## Final Verdict

**S0契约Approve；P6.3最终Verdict Pending**。S0定向契约检查不代替完整实现的最终独立审查；数值 / GUI / 持久化实现、真实算法验收与HR仍未完成。


### R2 — 全新Luna-max领域 / 应用独立检查（2026-10-15）

- 冻结`4f0d2bc`；只读，归档副本运行59项定向测试通过并清理副本；不含GUI / 完整CI / HR背书。未发现P1；2P2 / 2P3，结论需修复后复审。
- F1 P2：较旧schema v1写入方重算源而不识别新分析依赖，重开后旧拟合仍valid。修复：Session构造入口核对有限直接依赖 / 源指纹；未知版本保留只读。新增旧写入方源ID替换后重开stale回归。
- F2 P2：科学记数法`1e-6`直接写入MathText导致显示成e减6而非10的幂。修复：常数统一`mantissa × 10^{exponent}`，新增语义 / 数值回归。
- F3 P3：替换时analysis.summary及DerivedInput的未知扩展丢失。修复：仅替换本期拥有键，保留同版本未知summary / input扩展；新增重算回归。
- F4 P3：重复间隔扫描仅前后取消，长扫描不能及时退出。修复：扫描内每256样本检查取消且发布前再检查；新增扫描中途取消回归。
- 状态：实现方已修复，待新完整独立复审。

### 实现方自查（2026-10-15）

- F5：Luna控件初版缺少MathText `$...$` 分隔，图片存在但只是普通文本。已定向返工、真实MathText及错误路径测试补齐，7项通过；不把初版假预览当完成。
- 拟合提交额外复核参数约束、模型预测 / 残差和摘要；周期提交核对信号与事件 / 摘要，篡改样本拒绝。
- 当前全量基线1081 passed（97.42s）；此轮修复后最终全量 / 双平台与完整独立review待执行。
