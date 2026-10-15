# Review Record — Phase 6.3 User-defined Function Fitting and Signal Recurrence

- Subphase / Issue：P6.3 / [#29](https://github.com/KYLeonis/ai-physics-tracker/issues/29)
- 当前轮次：R8，2026-10-15；R4核心修复闭环、R5结果Undo增量、R6测试缺口均已独立通过；R7本轮HR交互复审发现两项，3cc546a已修复，R8独立复审Approve。
- 核心产品：`e74608d`；测试补齐：`bec8d61`；最新HR入口修复：`04495a4`；本轮交互修复2eeee68 / 3cc546a，R8独立复审Approve。
- Context：[6.3计划](../status/phase-6.3-plan.md)、[ADR-0021 Accepted](../decisions/0021-function-fit-and-recurrence-result-contract.md)、ADR-0017/0019/0020、CODE_STANDARD。
- Reviewer：R0 GLM-5.3请求600s超时 / 无有效模型核验或结论；R1–R6为分别隔离、只读的Luna-max任务。R7 / R8为本轮交互增量的全新只读Luna-max任务。Codex负责实现与修复验收；Luna交付公式控件，Codex检查并返工其MathText模式问题。

## Checklist

- [x] 源与目标结果身份、样本快照、时间语义、依赖失效 / 删除 / Undo规则自洽
- [x] 不破坏既有schema / clear语义，旧项目和未知扩展有明确保留策略
- [x] 区分交叉重复间隔与物理周期，不以单摆作为通用模型约束
- [x] 科学算法有解析合成测试与真实基准证据（P011应用均值相对差0.21996%）
- [x] 完整实现 / 全量 / 双平台CI通过（最终bec8d61双平台1095 passed / 2 skipped）
- [ ] 新Human Review通过（A / C用户通过；B交互修复待补测，D未反馈）

## Findings

R0无可用结论；F1–F9均经修复 / 独立复审Closed。R4补充的同ID内容变化及步骤顺序两项P3测试缺口已由bec8d61补齐、R6独立验证Closed；原核心review没有未处置的运行时P1/P2/P3；本轮R7两项交互finding已由3cc546a修复、R8确认Closed。

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

**Independent Review Approve（最终R8）；Human Review部分通过：A / C通过，B修复待补测、D待反馈。** R2领域 / 应用、R3完整产品、R4修复、R5新增结果历史和R6测试闭环分别记录于下方；本轮R7交互修复已由R8独立Approve。最终自动Gate通过后发起[本轮HR](../notes/phase-6.3-human-review.md)，用户反馈前不合并main。


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


### HR反馈 — 入口不明显（2026-10-15）

- F12 Normal-risk GUI：用户未找到Analysis工具；诊断现有Python GUI进程cwd为原main，6.3未集成main。原入口又位于第二层长标签，缺少常驻提示。
- 修复：WorkflowHeader常驻蓝色直达按钮，MainWindow纯导航openAnalysisTools，分析页提示及短标签；绝对PYTHONPATH启动命令保证从任意cwd加载本轮源码。未更改科学算法 / 持久化 / 后台事务。
- 验证：31项相关GUI / 工作区 / Analysis只读回归通过，真实鼠标点击可从Setup / Acquire / Analysis进入编辑器，observations和derived保持相同。入口易用性仍待用户补测；原A/B/C/D无通过反馈。

F12自动验证回执：04495a4的[CI38732368831](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38732368831) macOS / Windows Python3.11均1096 passed / 2 skipped。入口易用性仍待本人补测，原main未合并。


### R7 — HR交互修复（2026-10-15）

- 用户A / C通过；B因滚动 / 调线 / 信息密度不通过，D未反馈。已完成本轮UX修复，领域数值、schema与P011冻结协议未变。
- 主体2eeee68新增事件路由、视图范围恢复、实时参考线与旧事件隔离、微小信号滑块限幅、窄窗与草稿取消回归。相关GUI77项、本机全量1102项通过；最后定向14项通过。2eeee68双平台CI38759873770 success。
- 全新只读Luna-max复审：14项定向通过，但不Approve；两项finding：R7-F1，700px窗口下viewport420 < 表单508，禁用横向条仍裁切；R7-F2，Measured→Smoothed→Measured清空事件后无法重现。
- 修复3cc546a：滚动区根据实际表单最小宽度动态约束分栏与窗口；事件重建集中到配方刷新，实际样本须与缓存一致，避免将旧事件叠到新数据；源切回可自动恢复。补回可见SG导数说明及完整时序tooltip。补充700px缩窗尝试、源往返与不同样本隔离回归。
- 本轮仍要求用户亲自补测B；main和论文worktree不改，不提前关闭HR或AC-8。


### R8 — HR交互修复独立复审（2026-10-15）

- 冻结3cc546a；全新只读Luna-max聚焦R7-F1/F2及其必要调用链，不重开数值 / schema范围。**Approve，无新增实质bug；R7-F1 / F2 Closed**。
- 独立验证：14项GUI定向、额外1项窄窗回归通过；diff检查通过。核对700px缩窗尝试不裁切、源切回事件恢复、实际样本不匹配时不复用标记、SG说明恢复。
- 主Agent末轮35项GUI / 工作区 / Analysis只读回归通过（11.06s）。[最终CI38760538586](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38760538586)：macOS1100 passed / 2 skipped（77.92s）、Windows1100 passed / 2 skipped（158.54s），安装 / FFprobe / 测试 / 清理均success。


### HR反馈 — Fit禁用而时序入口不可见（2026-10-16）

- 风险：Normal-risk局部GUI bugfix；不改变数值 / schema / 时序授权策略 / 结果提交或Undo契约，不重开已关闭核心finding。
- 原因：P011重开后can_measure=False是正确门禁；时序确认按钮留在Acquire，被父页面隐藏。来源条 / 工具说明却错误将无近似授权等同为已验证CFR，且在同页重开工程 / 接受授权后没有完整刷新。
- 修复e4f04a0：时序标签和按钮复用同一实例随videoView重挂 / 恢复原布局；Analysis来源条监听当前工程 / 轨迹 / 分析变化并正确区分无授权。Fit和交叉工具显示禁用原因 / tooltip，确认后撤去提示。
- 自审：保留原TimingActions确认对话框、No分支、重开再确认、后台验证 / 重试与prepare源配方校验；未将历史授权偷偷恢复为当前权限，未添加训练帧门槛。15项定向通过，含5帧工程重开后的完整确认流程、CFR→Near-CFR时仍要求重算不兼容源、任意合法阻尼余弦预览，以及来回切页的原布局索引 / 隐藏按钮状态。
- 真实只读检查：P011结果工程near_cfr / Fit禁用 / 确认入口不可见已复现；修复后入口可见、禁用原因 / 来源正确，project.json SHA256仍037e243d16a26b85093f9f8c9d3d5b6ac39485b96b9b816a6aade2217d95fdde。在独立内存会话按既有用户授权确认后，x / theta各215样本prepare通过，未apply或save。此非真人HR替代。
- e4f04a0本机全量1103 passed（123.20s），diff检查通过；e4f04a0的[CI38766019892](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38766019892) macOS1101 passed / 2 skipped（103.07s）、Windows1101 passed / 2 skipped（153.89s），全部步骤success。界面体验待用户按[HR补测](../notes/phase-6.3-human-review.md)亲自确认。
