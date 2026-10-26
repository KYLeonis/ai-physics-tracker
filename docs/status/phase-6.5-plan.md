# Subphase Plan — Phase 6.5 Integrated Pendulum Acceptance

- 日期 / 状态：2026-10-26 · **v0.1规划草案，grilling第一轮待答；未冻结，未实施**。
- 接手基线：`main @ deab669`，进入会话时工作区干净，远端main同提交；P6.4已完成。
- Issue / 实现分支：尚未创建，待共同理解确认；规划文档可在main同步。
- 风险等级：High-risk（完整科学分析及AI结果 / 保存重开证据）；只修验收暴露的本期阻断问题。
- Development Mode：当前仍为Build Mode；Q4建议本期采用Stabilization Mode，待用户决定。

## Goal

在冻结P011参考上完成主线单摆任务，逐项给出角运动、相图、拟合、重复间隔、误差解释及保存重开的可复核证据，收口Phase 6。完整任务的AI起点与拟合周期判据按下列访谈决定；不以历史局部通过代替本次整体验收。

## 本轮已核实的事实

- P011源视频、600帧片段、原参数 / DLC CSV、人工参考及冻结协议 / 基准工程均仍存在，相关SHA256与冻结记录一致；`experiment/`由Git忽略，原件未改。
- 原人工参考为7个交叉事件、6个完整间隔，中点约定均值1.038981500s；分析闭区间[0,214]及参考线 / 方向 / 去抖设置保持。
- 旧分析结果工程记录重复间隔均值1.041266844s，相对差0.21996%；旧阻尼余弦拟合的Omega约6.027572755，由既有换算公式可复算T约1.042407211s，相对人工均值差约0.32972%。后者有数值，尚无事前冻结的拟合周期对照判据；不是已经通过roadmap该项的证据。
- P011旧轨迹来自既有DLC CSV；已有分析prepare→run→apply→save→load及当期HR证据，尚不能据此认定当前main从人工标注开始的新训练全链已完成。

## Agent Context Pack

### Authoritative Docs

- [current](current.md)、[Phase 6总计划](phase-6-plan.md)、[requirements](../spec/phase6-requirements.md)、[roadmap Phase 6](../roadmap.md#phase-6--advanced-physics-analysis-)：原AC逐项映射，不降低或改写既有标准。
- [首发目标](../spec/first-deliverable-target.md)：6.5之后才是最小科学导出 / 四类合成核查、试用包及独立用户试用；6.5完成不等于首发交付完成。
- [P011冻结记录](../notes/phase-6.3-reference-preparation.md)、[6.3计划](phase-6.3-plan.md)：冻结媒体 / 人工参考 / 参数 / 时序 / 分析区间 / 重复间隔判据；本期只读取原件，在新副本运行。
- [当前架构](../architecture.md#当前架构总览接手先读)、[架构进度](architecture-progress.md)：复用既有prepare→run→validated→apply、正式 / 只读执行器和Session事务，不另建框架。
- [ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)、[ADR-0019](../decisions/0019-angular-kinematics-and-multi-input-derived-data.md)、[ADR-0020](../decisions/0020-analysis-batch-result-and-recipe-consistency.md)、[ADR-0021](../decisions/0021-function-fit-and-recurrence-result-contract.md)：用户公式、角度 / 时间 / 缺测、输入与结果身份、实际样本和结果槽。
- [ADR-0024](../decisions/0024-automatic-near-cfr-acceptance.md)、[P6.4计划](phase-6.4-plan.md)、[ADR-0028](../decisions/0028-fit-parameter-conditional-standard-errors.md)、[ADR-0029](../decisions/0029-local-t-parameter-confidence-intervals.md)：时序自动采用规则、条件性SE / 局部t区间和换算结果不传播边界。
- [回移档案](main-backport-backlog.md)、[workflow](../workflow.md)：触及保存续接 / 后台 / 科学结果时核对对应既有约束；不自动回移论文产品。

### Relevant Historical Findings

- [6.2 Review F4–F8](../reviews/phase-6.2-review.md)：时序来源、未知扩展、缓存配方与当前配置区分、领域变化取消及迟到拒收。
- [R08 Review F1](../reviews/signal-history-review.md)、[R09 Review](../reviews/draft-context-review.md)：离开历史须释放只读查看状态，草稿与迟到核对沿用既有公开入口，不重新复制上下文清单。
- [P6.4 Review F1–F8](../reviews/phase-6.4-review.md)：既有统计 / 历史 / 布局 / Fixed交互已收口；本次验证完整流程，不默认重开已关闭问题。
- [Phase 5闭环报告](../benchmarks/phase-5-loop-report.md)：AC-9改善目标缺口已归档，本次不借新单摆结果改写历史结论。

### Scientific / Data / Product Invariants

- 原始观测只存像素；新预测经显式激活才成为活动观测，AI confidence不是位置真值或测量误差。
- 使用原始源帧 / 时间、有效标定与角参考；缺测不补点、不跨段求导 / 配对；stale结果只读，不用于新的结论。
- P011媒体、人工事件、原参数与协议原件保持冻结；新AI结果与旧DLC轨迹分别记录来源，后者不是人工ground truth。
- 重复间隔与公式换算的拟合周期分别报告；拟合成功不证明模型适用，SE / 局部区间不证明完整实验不确定度。
- 同视频人工帧时序参考不等于独立校时；局部SE / 区间仅适用未平滑位置 / 角度源及既定误差假设，换算结果仅数值。
- 真实失败保留证据，不按输出修改参考 / 区间 / 判据。未达标时不勾选相应AC，不宣布Phase 6完成。

### Known Deferred / Accepted Items / Non-goals

- Windows / CUDA真机保持延期，macOS / Windows自动CI继续执行；已有多轨迹叠图保留，新增两轨迹比较已取消。
- 科学CSV / 方法说明、四类合成真值及AI对照、教学素材授权 / 教程、安装 / 离线验证、独立试用各按后续mini-plan推进；本期不要求试用者参与。
- 不新增ODE、FFT、模型选择、完整系统误差传播、模型库、通用归档或新依赖；R07继续搁置。`is_dirty`仅在本次真实阻断时最小修复。

## Scope（提案，待访谈确认）

- **已有范围**：冻结参考复核；θ(t) / ω(t) / α(t)及θ–ω相图；显式用户公式拟合及残差 / 参数解释；独立重复间隔；同机保存 / 关闭 / 重开；Phase 6原AC证据映射和最终Gate。
- **Q1提案**：两条证据线。旧冻结DLC工程只作分析回归；另用同一片段建立新工程，20个不同人工帧→真实训练→推理 / 显式激活→困难帧修正及必要再训练→同一分析 / 保存重开。不以导入旧CSV充当本次训练 / 跟踪证据。
- **Q2提案**：除原重复间隔均值相对人工参考≤5%外，单独验收用户公式拟合周期与人工参考的相对差≤5%。这是新增的拟合周期判据提案，尚未获接受；既有数据 / 拟合结果已经可见，只作为集成验收约定，不声称盲测或独立精度验证。公式 / 初值 / 边界 / 区间须在对应正式验收运行前记录，不能按新结果调整门槛。
- **Q3提案**：本期先完成原AC，不加入可选的比例尺 / 支点 / 处理参数扰动研究；实际暴露的科学问题照常诊断。完整或有限敏感性观察后续按需要安排。
- **Q4提案**：仅本期切换Stabilization Mode，回归 / 修复 / 证据优先，Phase 6收尾后停止。

## Acceptance Criteria（草案，尚未冻结）

- [ ] **P65-AC1 冻结资料**：核对原媒体 / 人工参考 / 参数 / 协议指纹，记录当前运行源码与环境；原件不变，新产物独立保存。
- [ ] **P65-AC2 真实任务**：按Q1最终确定的起点完成单摆流程，标注 / 模型run / 候选激活 / 修正 / 分析均有来源；自动观测不冒充人工参考。是否必须新训练待Q1。
- [ ] **P65-AC3 分析及科学判据**：得到可追溯的θ / ω / α / 相图、公式参数 / 预测 / 残差、独立重复间隔与误差说明；原重复间隔均值≤5%判据保持。拟合周期独立列结果、人工参考及相对差，是否采用≤5%待Q2。
- [ ] **P65-AC4 保存重开**：同机显式保存、关闭、重开后复核观测来源、标定 / 支点、时序、处理配方、公式 / 实际拟合样本、结果及已记录SE / 局部区间；区分已保存结果与当前草稿，不自动补旧历史统计。保存后的Undo沿用原语义。
- [ ] **P65-AC5 Phase映射**：报告逐项映射requirements AC-1–7、6.3 / 6.4已接受子计划及roadmap两项标准；明确复用的历史证据、本次新证据和未达成项，不要求真实录像提供解析θ / ω / α真值。Q3若改变范围再补对应验收条款。
- [ ] **P65-AC6 Gate与收尾**：与改动相称的定向 / 全量、双平台CI、新独立审查和本轮最终HR通过；相关文档同步、集成 / push后停止。只有原AC及最终Gate满足才宣布Phase 6完成。

## Slices（顺序提案）

- [ ] **S0 协议与资料就绪**：访谈收敛并确认共同理解；建立Issue / 实现分支；在任何新正式验收运行前固定两条证据线的参数、拟合公式及比较方法，核对指纹。新协议引用原冻结协议，不覆盖它。
- [ ] **S1 冻结分析回归**：现有600点DLC基准在当前main副本上完成分析 / 结果解释 / 保存重开；建立原AC映射与对照报告，先暴露分析阻断。
- [ ] **S2 真实任务与问题闭环**：按Q1决定执行真实AI任务；记录人工干预、纯AI与修正后来源及分析结果，只修复阻断任务或科学正确性的问题。是否需要再训练由事先记录的修正与验收协议约束，不宣称必然改善。
- [ ] **S3 最终Gate与Phase收尾**：定向 / 全量 / 双平台CI、独立只读review / 必要返工；交付最短启动命令及不超过5项操作→预期，请用户亲测并停止等待；通过后逐项同步roadmap / README / AGENTS / current及Review，集成 / push并停止。

## Verification / 预计改动面

- 首轮规划只验证本地文档链接、diff与Git状态；不重跑产品全量，不运行新训练 / 拟合 / 推理。
- 实施优先复用现有`tests/test_angular*.py`、`tests/test_signal_analysis_job.py`、`tests/test_function_fit.py`、参数误差与保存 / 生命周期 / GUI回归；只为实际缺口或非平凡新逻辑补必要测试。
- 全量：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`；最终实际源码 / 测试提交取得macOS / Windows CI回执。真实DLC任务另给run / 环境证据，mock及CI不替代它。
- 预计持久文档：本计划、`docs/benchmarks/phase-6.5-pendulum-report.md`、`docs/reviews/phase-6.5-review.md`及本轮HR记录；后面三份实施时按实际产生，不预建空文件。媒体 / 工程 / 模型 / 原始日志放本地忽略的`experiment/p65-acceptance/`，仓库报告只留必要参数、指纹与结果。
- 预计产品变更：目前无已确认需求；仅当验收发现阻断时定位到具体调用链，再按`CODE_STANDARD.md`与既有分层最小修复。不预定架构重构或公共契约变更。

## Review Gate

- **Independent Review：必须**。新会话只读，核对科学证据链、冻结参考 / 新AI来源区分、拟合周期与重复间隔比较、统计局限、保存重开及原AC映射；若修产品，追加受影响调用链与回归。以`docs/reviews/phase-6.5-review.md`贯穿finding / 修复 / 复审。
- **PR：建议**作为整份diff观察容器，范围冻结且进入实施后再建，不承担额外审批。
- **Human Review：必须**。本期最终集成任务验收由用户亲测；旧P6.4 HR不替代本轮。准备可审查的工程 / 操作步骤及封闭问题后等待反馈，不以computer-use / 截图替代。
- **失败处理**：保留原结果与失败定位；范围 / 科学判据需要变化时先解释并提交用户决定，不通过换视频 / 改参考 / 降门槛完成收尾。

## Grilling决策树与第一轮

- 已确定的前提：main / P6.4就绪；P011原冻结参考保持；后续导出 / 合成 / 试用边界保持；Independent Review与最终HR必须。
- 当前前沿：Q1真实任务起点；Q2拟合周期是否增加明确≤5%判据；Q3是否按最小范围暂不加敏感性观察；Q4本期模式。
- Q1之后：明确人工标注 / 复核方式、修正与再训练的停止条件及新AI结果的验收口径；现有周期参考不能用作逐帧位置真值。
- Q2之后：确定公式 / 拟合区间 / 初值与参数记录、比较的结果 / 参考对应关系及模型不适用时的处理；不把拟合输出称为独立物理真值。
- Q3若要求加入扰动观察：先定变量、可辩护的扰动范围及报告性质，再安排Slice。
- 分支收敛后：汇总范围 / AC / Slices / Gate，请用户确认共同理解后冻结；本轮Q1–Q4均待答，不能推定接受。

## Result

- 当前仅完成规划草案与状态核对；未实施，全部AC / Slices待验证。后续按实际证据填写，不沿用旧测试数冒充新Gate。
