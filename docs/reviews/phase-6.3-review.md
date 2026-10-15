# Review Record — Phase 6.3 User-defined Function Fitting and Signal Recurrence

- Subphase / Issue：P6.3 / [#29](https://github.com/KYLeonis/ai-physics-tracker/issues/29)
- 当前轮次：R6，2026-10-15；R4核心修复闭环、R5结果Undo增量、R6测试缺口均已独立通过。
- 最终产品代码：`e74608d`；测试补齐：`bec8d61`；文档交付不改产品树。
- Context：[6.3计划](../status/phase-6.3-plan.md)、[ADR-0021 Accepted](../decisions/0021-function-fit-and-recurrence-result-contract.md)、ADR-0017/0019/0020、CODE_STANDARD。
- Reviewer：R0 GLM-5.3请求600s超时 / 无有效模型核验或结论；R1–R6为分别隔离、只读的Luna-max任务。Codex负责实现与修复验收；Luna交付公式控件，Codex检查并返工其MathText模式问题。

## Checklist

- [x] 源与目标结果身份、样本快照、时间语义、依赖失效 / 删除 / Undo规则自洽
- [x] 不破坏既有schema / clear语义，旧项目和未知扩展有明确保留策略
- [x] 区分交叉重复间隔与物理周期，不以单摆作为通用模型约束
- [x] 科学算法有解析合成测试与真实基准证据（P011应用均值相对差0.21996%）
- [x] 完整实现 / 全量 / 双平台CI通过（最终bec8d61双平台1095 passed / 2 skipped）
- [ ] 新Human Review通过（已交付步骤，等待用户亲测）

## Findings

R0无可用结论；F1–F9均经修复 / 独立复审Closed。R4补充的同ID内容变化及步骤顺序两项P3测试缺口已由bec8d61补齐、R6独立验证Closed；没有未处置的运行时P1/P2/P3。

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

**Independent Review Approve；Human Review Pending。** R2领域 / 应用、R3完整产品、R4修复、R5新增结果历史和R6测试闭环分别记录于下方；最终自动Gate通过后发起[本轮HR](../notes/phase-6.3-human-review.md)，用户反馈前不合并main。


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


### CI快照共享回归修复（2026-10-15，e0431eb）

- 用户收到失败邮件后核对旧run [38701032845](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38701032845)：macOS与Windows均仅失败`test_detached_shares_frozen_project_without_copying`；各1083 passed / 2 skipped / 1 failed，依赖安装全部通过。
- 原因：R2 F1修复把归一化放在Session构造器，每次detached重建Project，破坏已有O(1)共享契约。已将指纹复核移到`ProjectSession.load`实际加载入口，保留构造 / detached共享；旧写入方回归走真实save→load。
- 修复本机全量1086 passed（98.27s）；[e0431eb PR CI38701431104](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38701431104)及[push CI38701424825](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38701424825)双平台所有步骤success。不把旧失败run重跑冒充代码修复。


### R3 — 全新Luna-max完整独立检查（2026-10-15）

- 冻结53a0dfd完整产品 / 调用者 / GUI / 依赖与许可，76项定向通过；全量1085通过 / 1失败（同快照共享回归）。Verdict Request changes。未做真实实验 / Windows CI / 真人HR。
- R2 F2 / F3 / F4确认Closed；F1功能成立但引发O(1)回归，修复位置e0431eb待新冻结复审。
- F6 P2：Session构造重建Project，破坏detached O(1)身份 / 性能契约；e0431eb已移至load边界，1086全量及双平台CI通过。
- F7 P3：缓存source_snapshot.extra_fields.timing_context为标量时，displaySaved串联get触发AttributeError。已显式判mapping并披露“时序不可读 / 缓存只读”，GUI回归覆盖。
- F8 P3：多项式fixture实际参数断言1e-6，宽于计划1e-7。已按模型分别断言绝对容差、rel=0，定向通过；不改变冻结门槛。
- 实现方另补F9：旧分析区间超出当前working zone时，恢复控件会静默钳位并声称恢复成功。现明确拒绝 / 提示先扩展zone，保存结果仍可只读查看；新增GUI回归。
- 修复后63项相关回归通过；待新R4独立复审。


### R4 — 全新Luna-max修复复审（2026-10-15）

- 冻结1b8d173；从Git对象库导出副本避免共享HEAD前移混入e74608d。114项相关定向通过，F1–F9实现逻辑全部Closed；没有新P1/P2运行时缺陷。
- 追加两项P3测试缺口：源ID不变只改values应命中指纹分支；pipeline成员相同只改顺序应命中有序步骤校验。当前行为均由独立合成探针确认正确，要求补长期回归；bec8d61已补，R6验证。
- 性能表述边界：detached保留Project对象共享；TrackStore初始化既有O(N)成本未在本轮优化，不宣称整个detached调用严格O(1)。

### R5 — 全新Luna-max结果历史定向复审（2026-10-15）

- 冻结e74608d，对新增Undo result / Redo result及完整历史调用链检查；**Approve，无finding**。67项相关回归通过，diff检查通过。
- 专用入口只允许栈顶差异属于本期ANALYSIS_KINDS；raw / track / calibration / refinement / runs / 上游结果变化均拒绝、不跳过历史。原Analysis全局Undo仍禁用；save清栈不变，pending / busy / closing守卫成立。

### R6 — 全新Luna-max测试闭环（2026-10-15）

- 冻结bec8d61；仅测试变更，产品树与e74608d一致。**Approve，无当前行为finding**。6项相关参数化测试通过；独立探针确认同ID源值变化命中fingerprint比较、calibrated velocity反序精确触发步骤顺序错误。
- 备注：step_order用例目前匹配ProjectSessionError类型；独立探针核实具体分支，本轮非阻断。后续若修改校验顺序，可把消息匹配收紧；不因此重复修改已验证产品。

### 最终验证 / 交付（2026-10-15）

- 产品e74608d本机全量1095 passed（86.17s，Python3.12）；bec8d61仅补2个测试参数化情形，该文件18 passed。最终[PR CI38704158579](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38704158579)：Windows / macOS Python3.11均1095 passed / 2 skipped，所有安装 / FFprobe / 测试步骤success。Matplotlib3.8.4 / pyparsing3.3.2有弃用警告，不影响通过。
- P011冻结协议未改；最终18种量 / 测量平滑组合prepare通过，实际角量重复间隔仍1.041266844s，与独立人工1.0389815s差0.21996%；7事件夹点吻合。旧DLC为自动预测，不冒充人工真值；参考使用同视频原PTS，不宣称独立校时。
- 真实与合成HR工程实际open_project / 首帧解码 / 探针通过，均在本地忽略experiment，不入库；主main feaa80f及论文worktree保持干净未改。公式子任务worktree已归档，用户主worktree保留。
- 本轮HR尚待用户；Windows/CUDA真机沿既有批准延期Phase9前，未扩大声称已验证。
