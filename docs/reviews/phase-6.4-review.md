# Review Record — Phase 6.4 Fit Parameter Error Interpretation

- Subphase / Issue：P6.4 Fit Parameter Error Interpretation / #42
- Review 范围（commits / 分支 / 文件）：`feat/p6.4-parameter-error`，基线 `c265be8`；首轮检查 `c265be8..3a84d59` 全 diff（domain/application/GUI、测试、ADR及状态文档），并检查了之后工作树中的 F2/F3 修复草稿。修复草稿尚未由本 Reviewer 独立复审。
- Context（spec / ADR / plan 路径）：`docs/status/phase-6.4-plan.md`、`docs/decisions/0028-fit-parameter-conditional-standard-errors.md`、`AGENTS.md`、`CODE_STANDARD.md`、`docs/workflow.md`。
- 轮次：R1 / R2 / R3（2026-10-24科学审查）；2026-10-26后续GUI Gate及全部HR通过，最终源码 / 测试`9c1aa63`，F1–F8 Closed。

## Checklist

**正确性**

- [x] 实现与 subphase plan 的 AC / 相关 spec 一致
- [x] 边界情况处理正确（空数据、缺测值、越界、异常输入）
- [x] 数值逻辑有合成数据验证（如适用；审查了独立闭式线性 SE fixture、参数/残差尺度、边界、病态与非有限用例）

**质量**

- [x] diff 无范围外改动
- [x] 遵守 `docs/development.md` §1.1 可移植性规则（本期新增代码未引入平台专属路径或文件处理）
- [x] 公开接口与数据结构有说明，命名与既有代码一致
- [x] 测试真实覆盖新逻辑，而非只覆盖 happy path

**流程**

- [x] 提交信息符合 Conventional Commits
- [x] 属于 ADR 级别的决策已记录（ADR-0028）

## Findings

### F1 — 读取器未验证参数误差状态与记录源类型兼容

- **Severity**：Blocker
- **Evidence**：在首轮原始 diff 中，v1 读取器只核对版本、计数、参数名、状态和有限值，没有用记录源类型核对状态。将 `source_snapshot.kind` 设为 `smoothed_position`，而自由参数记录为 `status='estimated'`、`standard_error=0.1`、合法计数时，读取器接受该条目并让参数表显示数值。
- **Impact**：平滑或导数源的拟合可能显示不受本期契约支持的参数 SE。
- **Recommendation**：依据记录源类型拒绝冲突状态；非原始源的自由参数必须为 `unsupported_source`，原始源不能记录 `unsupported_source`。
- **Decision**：Fix Now — Implementation Agent 已在读取器加入源类型/状态交叉检查。
- **Fix commit**：`d382fef`
- **Verification**：首轮复现；后续新增的 source-conflict 定向回归由 Implementation Agent 执行。R1 未独立运行完整测试套件。
- **Re-review**：R2全新独立Reviewer检查完整`c265be8...895ecc4`及相关调用，确认Closed（2026-10-24）。
- **Status**：Closed

### F2 — 未知扩展合并可把非有限值带入新结果并破坏保存

- **Severity**：Blocker
- **Evidence**：旧分析摘要中含未知扩展 `future_summary={'bad': NaN}` 时，首轮实现保留该扩展并允许新结果应用；随后 `ProjectRepository.create_from_project` 因 `Out of range float values are not JSON compliant: nan` 失败。首轮的嵌套统计读取器也未检查未知统计扩展是否为严格有限 JSON，因此损坏扩展可能与有效 SE 一同通过只读显示。
- **Impact**：新结果可能进入会话但无法持久化；损坏的统计对象也可能继续展示数值。
- **Recommendation**：在合并未知扩展后对最终记录和输入扩展执行 `allow_nan=False` 校验并原子拒绝；读取 v1 统计时对完整对象（包含未知字段）执行同样的有限 JSON 校验。
- **Decision**：Fix Now — 最终记录合并处校验已提交；统计对象读取边界的补充校验在 R1 时仍为工作树改动。
- **Fix commit**：`3a84d59` / `895ecc4`
- **Verification**：首轮复现保存失败；六类扩展位置的原子拒绝与统计嵌套未知非有限扩展回归已添加，最终验证待 Implementation Agent 完成并由新 Reviewer 复核。
- **Re-review**：R2全新独立Reviewer检查完整`c265be8...895ecc4`及相关调用，确认Closed（2026-10-24）。
- **Status**：Closed

### F3 — 源快照与分析选择冲突时仍会显示 SE

- **Severity**：Blocker
- **Evidence**：在 F1 修复后的代码上，独立探针输入 `quantity='x'`、`selection.smoothed=True`、`source_snapshot.kind='world_position'`，并提供其他合法的 v1 SE 字段，`parameter_error_rows()` 仍返回 `(('a', '2', '0.1'),)`。选择字段表示应使用 `smoothed_position`，但读取器只信任快照中的原始源类型。
- **Impact**：当同一记录的重复来源事实互相冲突时，参数表仍把 SE 作为有效数值展示，无法确定该统计对应的处理源。
- **Recommendation**：把记录源解析集中到应用层公开读取入口；严格校验 `selection.smoothed` 为 bool、由 `quantity + smoothed` 推导源类型，并要求存在的 `source_snapshot.kind` 与之相同。正式目标校验与 saved/attempt 显示共用此入口。
- **Decision**：Fix Now — Implementation Agent 已在工作树中集中实现 `recorded_parameter_errors()` 并增加目标与 GUI 回归。
- **Fix commit**：`895ecc4`
- **Verification**：R1 对修复前路径进行了可复现探针；修复后的新增回归与定向验证待 Implementation Agent 完成并由新 Reviewer 复核。
- **Re-review**：R2全新独立Reviewer检查完整`c265be8...895ecc4`及相关调用，确认Closed（2026-10-24）。
- **Status**：Closed

## Review Log

### R1 — 2026-10-24 · 首轮

- 范围 / 基线：`c265be8..3a84d59` 全 diff及之后 F2/F3 修复草稿；基线 `c265be8`。
- 结论：Request Changes。拟合局部 SVD 与尺度恢复有独立解析 fixture；发现 F1–F3 三项读取/保存边界问题。实现方已着手修复，必须由全新独立 Reviewer 对最终提交复审后再作批准结论。
- Findings 变化：新增 F1、F2、F3；关闭 —

## Final Verdict（收口时填写）

- [ ] 通过（无未处置 Blocker）
- [x] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 需要重做（说明理由）

- 最终代码审查结论：**Approve（R3）**，F1–F5 Closed；2026-10-26 F6 / F7修复913d4ef后以1082a09追加可拖动布局；2026-10-26用户明确“HR通过，收尾”，F6 / F7 / F8 Closed；F1–F8全部关闭。自动Gate及真人HR独立核对，不由代码Approve代替。
- 日期 / 依据轮次：2026-10-26收口；科学R3 Approve及原SE的R2保留，后续Normal-risk GUI自动验证 / 本轮HR通过；F1–F8 Closed。

### R2 — 2026-10-24 · 全新独立只读复审

- 范围：完整`c265be8...895ecc4`源码 / 测试diff与fit_function、摘要校验、保存和历史调用链；Reviewer未参与实现，不修改产品或测试。
- 结论：**Approve**；无新可行动问题。F1通过quantity / smoothed与状态共同核对关闭；F2通过完整统计对象及最终合并扩展的有限JSON / 原子拒绝关闭；F3通过共享`recorded_parameter_errors`选择 / 快照核对关闭。
- Reviewer未重复跑pytest；实施方相关65 passed（10.06s），最终本机全量及双平台CI结果见下方Gate记录。原始R1的“待提交”叙述保留其当时事实，最终修复为895ecc4。

## Gate记录（与代码Review区分）

- 本机全量：**1387 passed**（250.59s）。[CI40061881700](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40061881700) macOS / Windows Python3.11均success，各**1385 passed / 2个既有可选skip**（144.27s / 203.64s）。均对应895ecc4源码 / 测试。
- 新HR待用户，未合并main；操作单见[phase-6.4-human-review](../notes/phase-6.4-human-review.md)。

## HR反馈 — 2026-10-24（原自动Gate后）

- **F4 / GUI可达性**：用户截图显示右侧公式编辑 / 示例 / 插入按钮被裁切，无法向右滚动。本轮HR未通过。
- **原因与修复**：右侧沿用仅纵向的AnalysisScrollArea，隐藏横向轨道并向父级传递整张表单最小宽度，遇到最大460宽侧栏及较大系统字体时裁切。右侧控制区改为常驻横向轨道，横向表单不再强制父级最小宽度；横滑数字控件只滚页面，不改数值。外层页面仍沿原纵向策略。
- **验证**：新增大字号 / 展开插入按钮回归，修复前失败；修复后横向范围 / 右端按钮可达 / 触控板横滑且区间值不变，以及既有窄窗回归2 passed。相关GUI回归87 passed（75.75s）；F4待用户复测。
- 用户同时要求新增具体置信区间，已确认是范围扩展；95%双侧局部Student-t的水平 / 方法正在确认，尚未修改算法 / 冻结AC，旧SE的R2 Approve不覆盖新增区间。

- F4实现提交：`1067312`，Normal-risk局部GUI修复，无统计 / 数据契约变更；原数值R2结论不扩大为新增CI审查。

## R3 — 新增95%局部t区间的全新独立审查（2026-10-24）

- 用户已明确采用95%双侧局部t口径，计划v1.1 / ADR-0029。审查基线1a600c7，覆盖新增CI全diff及调用链；审查后仅修原注释措辞，无可执行逻辑差异，最终提交12ea18d。
- **Verdict：Approve**。独立Reviewer运行`tests/test_parameter_intervals.py tests/test_fit_uncertainty.py tests/test_parameter_error_lifecycle.py tests/gui/test_parameter_errors.py`：**70 passed**。
- 核对df=2 / 39独立常数、SE原尺度 / 半宽、边界不截断、非有限 / 精度不足保留SE、v1不补区间、v2依据已录estimate / SE / df核对端点、未知扩展 / 有限JSON、不支持源清除SE / CI、保存 / Undo / 历史只读。F1–F3既有保护未退化。
- **F5 / P3 注释过期**：function_fit可辨识检查处仍称“不输出参数置信区间”。Decision Fix Now，12ea18d已改为“此处只检查拟合可辨识性，统计另行估计”；纯注释，Closed。不改变R3 Approve。
- 实施方相关129 passed（13.72s），旧GUI / 日志 / 草稿关联110 passed（72.40s）；新隔离工程实际打开自检`P64_CI_HR_OPEN_OK [159.96432, 160.1678]`。
- 新产品全量 / 双平台CI回执待补；F4横滑及区间UI均待新HR，未合并。原v1 SE的R2记录仅代表其当时范围，最终产品按R3及本轮自动Gate / HR判定。

### R3最终自动Gate回执 / 新HR待用户

- 对应最终源码 / 测试12ea18d：本机**1408 passed（220.57s）**；[CI40077232972](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40077232972) macOS / Windows各**1406 passed / 2个既有可选skip**（141.14s / 261.50s），整run success。
- R3最终代码Verdict **Approve**。最终验证后只有文档同步，不重复代码Review或测试。F4横向操作与新增区间交互需用户亲测；本轮HR未通过、未合并main，6.5未开始。

## HR反馈 — 2026-10-26（其余通过 / 局部GUI返工）

- 用户确认“其余都通过”，保留已测项目的真人通过；F4右侧表单横滑Closed。本轮不要求重测已通过的历史 / 保存 / 源切换等项目；Fixed因用户未理解操作，保持补测。
- **F6 / Normal-risk GUI：区间数字省略、不可拖动列宽**。原因：Stretch列宽禁止手动调整，单行区间遇Qt换行布局时被省略。Fix Now：Interactive表头、上下限显式分行、关闭省略、按内容初始化宽度并为长状态限制宽度 / 换行；列宽改变时重算行高，窄窗可横向滚动，tooltip保留完整原值。
- **F7 / Normal-risk GUI：术语与Fixed引导不足**。Fix Now：结果表头及单元格、状态、源、Residuals / RMSE / 基线比较和误差方法增加悬停说明，解释含义、用途与边界；Initial / Lower / Upper / Fixed表头解释固定值与约束的区别，展开参数选项直接显示操作步骤。Fixed明确持有Initial而非历史Estimate，Fixed自身不估SE / CI，其已知值的不确定度不传播。
- 数值 / 摘要契约与既有科学假设未变，不重开R3。F6 / F7代码修复后仍须本轮用户亲测，不能用offscreen代替；自动验证及提交以current为准。

- F6 / F7实现提交：**913d4ef**，已push；关联GUI **114 passed（112.90s）**。新增大字号两行端点完整宽度 / 行高、真实表头拖动 / 窄视口滚动及实际展开Fixed / 鼠标勾选 / 拟合保持Initial回归通过；原体验副本打开自检通过，c显示[159.96432, 160.1678]。[双平台全量CI40270483866](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40270483866) macOS / Windows均success，F6 / F7仍待三项真人补测。

## F6补充HR反馈 / 可拖动面板（2026-10-26）

- 用户截图指出结果表右侧大量空白、大小仍受限制，要求可拖动式布局；913d4ef的列宽拖动未满足面板调整大小，F6不关闭，F7未收到新增通过反馈。
- 1082a09改为左右与上下两个原生QSplitter，带可见分隔条和拖动提示；移除结果表175高度 / 右侧460宽度上限；最后一列铺满余宽，CI取消强制换行；宽度缩小时按内容换行 / 横滚，返回草稿时结果区整体收起。保持数值 / 统计摘要、源 / 历史职责与既有R3科学结论。
- 定向11 passed（10.57s），覆盖实际鼠标拖动两个分隔条、窗口变宽时填满、结果表可超过旧高度上限、草稿收起及既有列宽拖动 / 完整端点。关联GUI115 passed（95.70s），原体验工程打开自检通过；新[双平台全量CI40272503263](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40272503263) macOS / Windows均success，最终回执见current；布局仍须本轮用户亲测。

## F8 — Fixed空框不可见 / 点击无法切换（2026-10-26 HR）

- **Evidence / Cause**：用户截图Fixed列全为空白、无法勾选；原生macOS空框不明显，默认item delegate只在小标记范围响应点击，Fixed项未带Selectable标记。新增真实输入回归修复前整格点击 / 键盘两条失败，标记点击通过，证实此前只测左侧小标记遗漏了常用操作。
- **Decision / Fix**：Fix Now，Normal-risk局部GUI。9c1aa63复用Phase6.2轨迹列表F9的Fusion清晰空框样式和整格复选交互；原_TrackChoiceDelegate原样移入check_state_delegate.CheckStateDelegate，轨迹列表与Fixed列共用。草稿创建及SignalHistory重建都保留Selectable / Checkable；Fixed列接管空格，避免全局播放快捷键抢占。历史表格仍整体禁用，采用记录设置后恢复可编辑。
- **Verification**：整格 / 实际标记 / 空格均进入实际Fit并保持Initial，其他参数不受影响；历史只读时不能切换、采用后可连续勾选 / 取消且不写工程，轨迹列表原三种输入及历史回归通过。相关GUI **56 passed（40.09s）**，原体验工程打开自检通过；新[双平台全量CI40280942412](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40280942412) macOS / Windows均success，最终回执见current。
- **Scope / Status**：SE / CI算法、参数值、摘要 / 存储和事务均未改；R3科学结论保持。F8代码已修、待当前真人补测；本条反馈不代表F6 / F7通过，不合并main。

## 最终HR / Gate收口（2026-10-26）

- 用户本轮原文：“HR通过，收尾”。最终布局 / hover / Fixed及此前已通过项全部完成真人验收，**F6 / F7 / F8 Closed**，F1–F8无未处置finding。
- 最终代码9c1aa63；R3科学代码Approve保持，随后Normal-risk GUI修复经56项相关回归及本轮HR通过。最终[CI40280942412](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40280942412) macOS / Windows各**1412 passed / 2个既有可选skip**（167.61s / 225.77s），两作业及整run success。先前各轮“待HR / 未合并”段落保留历史事实，当前以本节与current为准。
- 当前HEAD的src / tests与9c1aa63一致；之后仅文档收尾，复用对应自动验证。准备--no-ff集成与push；不开始6.5，不把本次HR扩大为整个Phase6单摆整体验收。

- 最终集成：**e31a4ac**，--no-ff合并 / push main；源码 / 测试与9c1aa63一致，Issue #42 Closed / PR #43 Merged。全部Gate与本轮HR完成，当前P6.4关闭；6.5未开始。
