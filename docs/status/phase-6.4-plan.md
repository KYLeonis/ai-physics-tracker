# Subphase Plan — Phase 6.4 Fit Parameter Error Interpretation

- 日期 / 状态：2026-10-24 · **mini-plan v1.0，用户明确回复“冻结”，Q1–Q6及计划范围 / AC / Gate已冻结；2026-10-24用户授权开工，S0完成 / S1已实现，S2自动Gate通过、待本轮HR，未集成main。**
- 初始规划基线：`main @ ca8013d`（2026-10-22）；范围 / AC / Gate于2026-10-24冻结。
- 实现接手基线更新（2026-10-24）：`main @ 850df3e`，包含R09草稿上下文集中（`c14c78a`，源码 / 测试与`ad00f9c`一致）。仅同步接手事实 / 复用入口与回归清单，v1.0已冻结的范围 / AC / Gate不变；实际开工时再核对最新HEAD。
- Issue / 实现分支：[#42](https://github.com/KYLeonis/ai-physics-tracker/issues/42) / `feat/p6.4-parameter-error`；开工基线`c265be8`；[Draft PR #43](https://github.com/KYLeonis/ai-physics-tracker/pull/43)。
- 风险等级：**High-risk**（拟合统计及结果摘要契约）。
- 上下阶段：6.1–6.3.1及R01–R04 / R08 / R09已集成；本期承接Phase 6 AC-6及相关AC-7。用户取消新增两轨迹比较，既有叠图保留；6.5整体验收独立执行。

## Goal

让用户回答：**当前公式的参数在给定假设下估得有多稳定？**（Q1已认可）
在现有英文、图表优先的Analysis中呈现数值、适用条件和不可估计原因，区分拟合残差、重复间隔离散、条件性参数标准误差与系统误差。

## Agent Context Pack

### Authoritative Docs

- [current](current.md)、[Phase master](phase-6-plan.md)、[requirements R4 / R5](../spec/phase6-requirements.md)：当前状态、误差边界及生命周期要求；旧建议门槛不自动成为本期验收。
- [当前架构](../architecture.md#当前架构总览接手先读)、[已完成重构](architecture-progress.md)：复用source_recipe、prepare/run/validated/apply、独立预览与SignalHistory，不重开R07。
- [R09计划](draft-context-plan.md)、[R09 Review](../reviews/draft-context-review.md)：analysis_draft_context集中GUI草稿事实与源准备迟到判定；MainWindow.draftContextFacts、ChartActions.prepareSignal / closed / signalJobActive及panel视图状态公开入口已落地，P6.4沿用这些入口。
- [ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)：用户定义方程，平台不从参数名字推断物理模型。
- [ADR-0019](../decisions/0019-angular-kinematics-and-multi-input-derived-data.md)、[ADR-0020](../decisions/0020-analysis-batch-result-and-recipe-consistency.md)：参考 / 单位 / 缺测、输入与目标版本、区间与时序。
- [ADR-0021](../decisions/0021-function-fit-and-recurrence-result-contract.md)、[ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)：既有拟合结果 / 实际样本 / 尝试日志契约；残差不等于测量不确定度。
- [ADR-0023](../decisions/0023-preview-task-isolation.md)、[ADR-0027](../decisions/0027-analysis-computation-and-publication.md)：只读与正式执行隔离、必要冻结输入、受控原子发布。
- [6.3.1计划](phase-6.3.1-plan.md)、[回移档案](main-backport-backlog.md)：英文、图表主位、无固定响应时限；ODE / 联合拟合 / 模型比较等延期项不自动纳入。

### Relevant Historical Findings

- [6.2 Review F4 / F5 / F7](../reviews/phase-6.2-review.md)：旧缓存缺时序不能当有效源；扩展字段必须保留；输入变化取消、晚到结果拒绝。再次触及这些契约时纳入复审。
- [R08 Review F1](../reviews/signal-history-review.md)：离开工具要经history.leave；新增展示不能让历史锁定 / 迟到曲线泄入当前草稿。
- 同Review F2版本类型宽松仍Deferred；新摘要边界严格校验类型，不把本期扩大为全项目版本读取重写。
- [R09 Review A-F1 / B-F2](../reviews/draft-context-review.md)：源准备迟到核对须保留history / method / tab → 延迟selection → workspace的求值顺序和异常传播；已有Qt-free顺序回归。signal_history六个遗留panel私有访问仍属后续清理，P6.4不新增同类跨模块私有访问。

### Scientific / Data / Product Invariants

- raw只存像素；拟合使用既有实际源帧 / 时间 / 标定 / 参考和有效样本，缺测不插值。
- 结果新鲜度、可读缓存和可用于新分析分别判断；stale只读展示不能参与新的标准误差结论。
- 已有拟合保持单初值、等权最小二乘；新增统计不得暗改参数、预测、残差或求解成功语义。统计不可估计时保留合法拟合结果。
- AI confidence不换算成测量误差；参数标准误差不代表真实测量的完整不确定度。
- 自动预览不写工程、不改dirty或Undo；正式拟合 / Measure、历史查看及原子结果Undo/Redo维持既有职责。
- R09的草稿上下文是瞬时GUI事实，不是科学源身份或统计结果；继续保留source指纹 / 目标槽版本 / prepare与validated核对。新增SE随对应正式结果或已记录历史显示；返回草稿 / 预览失败时由panel所属展示路径清除不再对应当前视图的SE，源变化仍按既有stale / 只读策略披露，不能留下旧SE冒充当前结果；不另建上下文键清单或执行器。

### Known Deferred / Accepted Items / Non-goals

- 不做正式参数置信区间、预测带、Bootstrap、自动残差相关性修正、完整系统误差传播、用户换算结果的不确定度传播。
- **用户已取消两轨迹比较**：不做A−B差值、新比较入口或比较统计；既有叠图不改。也不做跨视频比较、多轨迹联合拟合、模型优劣排名、自动物理判定、ODE、单位编辑 / 自动量纲推导、完整历史库和Phase 8导出。
- 不以本期补完Phase 6：P011冻结参考 / ≤5%均值对照门槛不变，6.5仍需完整单摆流程与最终HR；Windows/CUDA真机仍按既有决定延期。

## Scope（Q1–Q6已确认 / 已冻结）

### A. 拟合参数的条件性标准误差

- **Q5已确认**：在现有拟合结果旁显示`Parameter / Estimate / Conditional standard error`三列；有效估计显示数值，固定参数显示`Fixed`，不可估计或源不支持时显示具体原因。假设 / 方法详情可展开，英文界面、图表主位保持。估计值与SE分列，不使用没有解释的±或包装成置信区间；保留残差图和RMSE原有含义。
- 实现方案使用最终解处局部Jacobian及残差方差估计，具体数值判据 / 摘要契约在S0冻结；复用现有NumPy / SciPy，不更换求解器。
- 计划采用口径：实际样本数n、自由参数数p，残差方差为SSE/(n-p)，局部协方差约为该方差乘以(JᵀJ)的逆，标准误差取对角项平方根。实现宜用SVD等稳定分解，不直接求逆；必须恢复现有参数坐标 / 残差缩放后的原数值尺度。
- 仅解释为给定公式、固定参数、源数据和误差假设下的局部估计。披露零均值、独立同方差残差及局部线性近似假设；它不证明物理模型成立，也不包含比例尺、支点、时间等系统误差。
- 固定参数标`Fixed / not estimated`，不能填0；自由度不足、秩不足、病态、边界约束主导或非有限值给出不可估计原因。数值判据在S0经解析fixture冻结，不在草案中臆定阈值。
- **Q3已确认**：首版仅对未平滑的位置 / 角度数据提供条件性参数标准误差；平滑源及数值微分得到的速度 / 加速度仍正常拟合，SE显示当前方法不支持并说明原因。未平滑源也不自动证明独立性，仍披露统计假设。
- **Q4已确认**：仅直接拟合参数输出SE；例如Omega可有SE，用户公式`T = 2*pi/Omega`仍只显示换算值，不输出传播后的SE或完整实验不确定度。
- 旧结果无新统计时显示`Not recorded`，不自动重新拟合或回填。新拟合统计随原结果保存 / Undo；尝试日志有已记录统计才展示，历史重建不能编造当时未记录的估计。

科学依据：[SciPy curve_fit文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)说明残差方差缩放及局部线性协方差的局限；[least_squares文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)说明Jacobian与边界语义。本项目继续使用已锁定的SciPy 1.17.1；链接用于方法核对，不意味着升级依赖。以上为计划采用的方法；S0记录具体数值判据、fixture与摘要契约，不改变已冻结的产品范围。

### B. 统一误差说明（融入现有结果，不另建工具）

- 区分四类：拟合残差 / RMSE、逐次重复间隔的样本标准差、参数条件性标准误差、尚未量化的系统误差。
- **Q6已确认**：重复间隔工具保留现有逐次间隔、均值与样本标准差，仅补清楚“间隔之间的离散”及与参数SE的区别，不新增统计量或检测方法。尤其不新增std/√N，因为相邻间隔可能共享事件误差且可能相关。
- 沿用当前量 / 源的配方与来源披露：SG窗口 / 导数、端点、缺测、近似时序及角参考。只显示与当前结果相关的短说明和详情，不新建全局诊断面板。

## Acceptance Criteria（已冻结；实现验证进行中，HR待做）

- [ ] AC-1 参数统计：已知设计矩阵的线性拟合，条件性标准误差与独立解析计算一致；参数 / 残差尺度变换后保持正确，原拟合参数 / 预测 / RMSE不退化。
- [ ] AC-2 不可估计：固定 / 全固定、自由度不足、病态 / 秩不足、边界、非有限及不支持的处理源有明确状态 / 原因；没有伪造0或NaN / Infinity写入JSON，也不因统计失败抹掉合法拟合。
- [ ] AC-3 展示 / 解释：三列参数信息与有效 / Fixed / 不可估计状态正确，原因可见，假设 / 方法可展开；UI可辨认四类误差含义及条件，不将重复间隔标准差当均值误差，或从参数SE推断完整测量精度；换算结果仅数值，重复间隔原数值输出不变。
- [ ] AC-4 生命周期：新统计保存重开 / 结果Undo/Redo一致，旧 / 未知字段与未来版本受保护；历史无记录不回填；源变化、切项目 / 轨迹 / 视频 / 工作区及晚到结果不能留下冒充当前的数值。
- [ ] AC-5 Gate：定向 / 全量、macOS+Windows CI、Independent Review / fixes / re-review及新一轮用户HR通过；文档与验收证据同步后集成 / push，只收尾6.4。

解析fixture、病态 / 边界数值判据及容差在S0、实现前明确记录；不新增真实准确率或固定响应时长门槛。现有P011仅用于回归与演示，不据此认定参数SE校准正确。

## Slices

- [x] S0 — 用户授权实施后，建立Issue / 实现分支，冻结数值fixture / 容差、不可估计判据及摘要additive契约。重要新契约新增ADR，不改写Accepted旧ADR；不重开已定产品范围。
- [x] S1 — 拟合统计贯通：domain纯计算 → 应用摘要 / 校验 → 保存 / 尝试日志 / 历史兼容 → 现有拟合页展示；解析与边界回归通过。
- [ ] S2 — 解释与完整Gate：统一当前结果的误差含义，相关回归 / 全量 / 双平台 / 独立复审；给最短启动命令、操作→预期及封闭问题，停止等待真人HR。通过后集成 / 文档 / push。

## Verification / 预计改动面

| 范围 | 优先复用 / 检查点 |
| --- | --- |
| domain | function_fit的现有求解与缩放；新增统计纯计算；不改recurrence算法 |
| application | signal_analysis_job的summary与validated_analysis；source_recipe读取处理来源；fit_attempts / fit_attempt_view不重拟合历史 |
| GUI | signal_analysis_panel / fit_explanation参数展示及ChartActions结果交付；复用R09草稿事实和公开访问入口，新增SE展示状态归panel；SignalHistory与SignalPreview维持职责 |
| 数据 / fixtures | 既有analysis summary additive字段、日志摘要、ProjectRepository往返；不做schema迁移 / 新依赖；旧记录与未知扩展fixtures |
| tests / docs | function_fit、signal_analysis_job、fit_attempt_view / journal、GUI与Session事务相关回归；接触R09调用链时保留test_analysis_draft_context与gui/test_analysis_private_access守卫；本计划、current、Phase总计划及实际契约 / 架构文档 |

- 数值：用线性设计矩阵的独立解析解核对SE；非线性已知模型只验证局部估计与边界，不把一次合成拟合当覆盖率证明。
- 生命周期：新摘要严格有限JSON、字段类型 / 版本、未知扩展、保存重开、原子Undo、历史不回填、源变化与迟到拒绝。
- GUI：offscreen验证显示状态与只读，真人验证参数解释、不可估计提示及窄窗可达；不以截图 / computer-use替代HR。
- 产品实现后的全量命令：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`；最终分支经PR运行现有macOS / Windows CI，保持当前workflow分支触发策略。
- 初始规划 / 冻结仅检查文档链接、git diff与工作区，不把历史1329项通过当本期验证；后续R09接手补查见Result，其定向测试不代表P6.4已经实现或验收。

## Review Gate

- **Independent Review：必须**，实现后的全新只读review会话。重点：统计尺度恢复 / 假设 / 不可估计、摘要兼容 / 历史只读、原子提交与迟到拒绝；记录`docs/reviews/phase-6.4-review.md`，修复后复审。
- **PR：建议**，作为完整diff与双平台CI观察容器，不增加额外形式审批。
- **Human Review：必须**，交付新用户交互时按workflow §5.1发起并等待用户亲测；本轮计划审阅不能代替实现后的HR。

## Grilling决策记录 / 冻结确认

- Q1（2026-10-24）：用户“认可”。本期首先回答给定公式与误差假设下参数估计的稳定程度，不声称完整实验不确定度。
- Q2（同日）：用户“我们不做两条轨迹的比较了吧”。明确取消该新增范围及差值验收；既有叠图功能不删除。
- Q3（同日）：用户“支持”。首版仅未平滑位置 / 角度源提供条件性SE；平滑 / 导数源拟合保留，SE明确不支持。
- Q4（同日）：用户“接受”。直接拟合参数给SE，换算结果只给数值，误差传播后续。
- Q5（同日）：用户“接受”。三列显示参数 / 估计值 / 条件性SE，固定 / 不可估计状态明确，方法 / 假设折叠，保持图表主位。
- Q6（同日）：用户“接受”。重复间隔工具仅补解释，现有统计和检测方法保持，不增加新统计量。
- v0.1的差值验收 / 比较Slice已按Q2取消，未实施、未验收；v0.3重新连续编号AC与Slices，取消内容只保留决策记录，不冒记完成。
- 最终确认（2026-10-24）：用户明确回复“冻结”，共同理解确认，计划冻结为v1.0。冻结当时仅授权规划；后续已于同日获用户开工授权并执行，见顶部当前状态。

## Result / 历史记录

- 冻结时：Q1–Q6及计划v1.0于2026-10-24由用户明确冻结；当时仅文档改动。后续开工及产品证据见顶部与下文。
- 冻结时：Issue / 实现 / 验证 / HR未执行；后续用户已授权开工，历史等待状态不代表当前状态。
- R09接手补查（2026-10-24，850df3e）：核对94d15ab之后的源码 / 测试diff、公开入口调用方、stamp启动 / 取消 / 交付与既有Review；未发现新增阻塞问题。本机offscreen定向119 passed（117.31s，覆盖草稿事实 / 私有访问守卫、工作流事实、拟合、历史、重复间隔、源联动、只读和分层）。仅补上下文 / 复用入口 / 回归清单；Goal / Scope / AC / Slices / Gate与冻结版逐段一致，无需重新冻结；未实施P6.4，未重跑全量或双平台CI。

## S0 数值与摘要冻结（2026-10-24）

具体判据、解析fixture / 2e-5相对容差及additive摘要契约见[ADR-0028](../decisions/0028-fit-parameter-conditional-standard-errors.md)。保持既有拟合可辨识拒绝语义，统计不可估计单独返回；原产品范围不变。

- 2026-10-24实现检查点：S0契约见ADR-0028；S1统计 / 三列与只读生命周期已贯通；定向191 passed（85.27s，另追加1项历史不回填回归随全量执行）。独立Review及全量进行中，CI / HR待完成。未集成main，旧冻结记录为历史事实。

## 实现中间检查点（2026-10-24；最终状态见下节）

- 产品`d382fef` / 原子扩展修复`3a84d59` / 统一统计读取修复`895ecc4`；无新依赖、schema迁移或数值拟合求解变更。
- 首轮定向191 passed；最终读取 / 生命周期等相关65 passed（10.06s）。R1三项读取与有限JSONfinding已修复，待全新R2复审；最终全量与双平台CI40061881700运行中。
- [本轮HR操作与启动](../notes/phase-6.4-human-review.md)：隔离合成噪声工程及旧无SE轨迹已生成；实际打开路径自检`P64_HR_OPEN_OK`。未进行真人验收、未合并；HR通过后才勾产品AC / 收尾6.4。

## 最终自动Gate / HR交付（2026-10-24）

- 产品`895ecc4`：本机全量**1387 passed**（250.59s，1337基线+50新增）；[CI40061881700](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40061881700) macOS / Windows Python3.11均success，各**1385 passed / 2个既有可选skip**（144.27s / 203.64s）。
- 全新独立R2完整复审Approve，R1 F1–F3全部Closed；[Review](../reviews/phase-6.4-review.md)。修复相关65 passed，原定向191 passed；中间因代码修复终止的全量不计Gate，旧提交CI / 重复push CI不作最终验收依据。
- S0 / S1完成；AC-1 / 2 / 4自动验证通过，AC-3自动化通过仍待真人判断说明与可达性，AC-5待本轮HR / 集成收尾，因此产品AC勾选留待HR之后，S2尚未整体完成。
- [启动与四组HR步骤](../notes/phase-6.4-human-review.md)已交付；独立合成工程实际打开路径`P64_HR_OPEN_OK`，不覆盖用户工程。**停止等待用户反馈，不合并、不进入6.5**。最终验证之后只同步文档，不修改源码 / 测试。

## HR反馈与范围扩展讨论（2026-10-24）

- 用户反馈右侧表单无法向右滑动；本轮HR未通过。F4布局修复草稿及相关回归见Review；保持未合并。
- 用户明确选择“增加置信区间：先明确区间水平与方法，再调整计划”。现建议95%双侧局部Student-t区间：estimate ± t(0.975,n-p) × SE，增加残差近似正态假设；保持原始位置 / 角度源、固定 / 不支持 / 不可估计原因、换算不传播及旧历史不回填边界。具体水平 / 方法待用户确认，当前v1.0数值与AC尚未改写，也未实施区间算法。
- 方法参考：[SciPy Student-t分位数](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html)；[SciPy局部协方差近似局限](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)。提案不是完整测量不确定度或预测区间。

- F4布局修复`1067312`已实现并推送；大字号宽表单失败回归修复后通过，相关GUI87 passed（75.75s）。数值 / 摘要算法未改，真人可达性待重启复测。
