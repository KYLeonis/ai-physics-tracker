# Subphase Plan — Phase 6.4 Fit Parameter Error Interpretation

- 日期 / 状态：2026-10-24 · **mini-plan v0.2，grilling进行中；Q1–Q4已确认：参数条件性误差、取消两轨迹比较、仅未平滑位置 / 角度源支持SE、换算结果仅数值；其余科学 / 产品口径未冻结，未开始实现。**
- 规划基线：`main @ ca8013d`，本地与远端main一致，进入会话时工作区干净。
- Issue / 实现分支：尚未创建；计划确认并授权实施后建立。
- 风险等级：**High-risk**（拟合统计及结果摘要契约）。
- 上下阶段：6.1–6.3.1及R01–R04 / R08已集成；本期承接Phase 6 AC-6及相关AC-7。用户取消新增两轨迹比较，既有叠图保留；6.5整体验收独立执行。

## Goal

让用户回答：**当前公式的参数在给定假设下估得有多稳定？**（Q1已认可）
在现有英文、图表优先的Analysis中呈现数值、适用条件和不可估计原因，区分拟合残差、重复间隔离散、条件性参数标准误差与系统误差。

## Agent Context Pack

### Authoritative Docs

- [current](current.md)、[Phase master](phase-6-plan.md)、[requirements R4 / R5](../spec/phase6-requirements.md)：当前状态、误差边界及生命周期要求；旧建议门槛不自动成为本期验收。
- [当前架构](../architecture.md#当前架构总览接手先读)、[已完成重构](architecture-progress.md)：复用source_recipe、prepare/run/validated/apply、独立预览与SignalHistory，不重开R07。
- [ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)：用户定义方程，平台不从参数名字推断物理模型。
- [ADR-0019](../decisions/0019-angular-kinematics-and-multi-input-derived-data.md)、[ADR-0020](../decisions/0020-analysis-batch-result-and-recipe-consistency.md)：参考 / 单位 / 缺测、输入与目标版本、区间与时序。
- [ADR-0021](../decisions/0021-function-fit-and-recurrence-result-contract.md)、[ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)：既有拟合结果 / 实际样本 / 尝试日志契约；残差不等于测量不确定度。
- [ADR-0023](../decisions/0023-preview-task-isolation.md)、[ADR-0027](../decisions/0027-analysis-computation-and-publication.md)：只读与正式执行隔离、必要冻结输入、受控原子发布。
- [6.3.1计划](phase-6.3.1-plan.md)、[回移档案](main-backport-backlog.md)：英文、图表主位、无固定响应时限；ODE / 联合拟合 / 模型比较等延期项不自动纳入。

### Relevant Historical Findings

- [6.2 Review F4 / F5 / F7](../reviews/phase-6.2-review.md)：旧缓存缺时序不能当有效源；扩展字段必须保留；输入变化取消、晚到结果拒绝。再次触及这些契约时纳入复审。
- [R08 Review F1](../reviews/signal-history-review.md)：离开工具要经history.leave；新增展示不能让历史锁定 / 迟到曲线泄入当前草稿。
- 同Review F2版本类型宽松仍Deferred；新摘要边界严格校验类型，不把本期扩大为全项目版本读取重写。

### Scientific / Data / Product Invariants

- raw只存像素；拟合使用既有实际源帧 / 时间 / 标定 / 参考和有效样本，缺测不插值。
- 结果新鲜度、可读缓存和可用于新分析分别判断；stale只读展示不能参与新的标准误差结论。
- 已有拟合保持单初值、等权最小二乘；新增统计不得暗改参数、预测、残差或求解成功语义。统计不可估计时保留合法拟合结果。
- AI confidence不换算成测量误差；参数标准误差不代表真实测量的完整不确定度。
- 自动预览不写工程、不改dirty或Undo；正式拟合 / Measure、历史查看及原子结果Undo/Redo维持既有职责。

### Known Deferred / Accepted Items / Non-goals

- 不做正式参数置信区间、预测带、Bootstrap、自动残差相关性修正、完整系统误差传播、用户换算结果的不确定度传播。
- **用户已取消两轨迹比较**：不做A−B差值、新比较入口或比较统计；既有叠图不改。也不做跨视频比较、多轨迹联合拟合、模型优劣排名、自动物理判定、ODE、单位编辑 / 自动量纲推导、完整历史库和Phase 8导出。
- 不以本期补完Phase 6：P011冻结参考 / ≤5%均值对照门槛不变，6.5仍需完整单摆流程与最终HR；Windows/CUDA真机仍按既有决定延期。

## Scope（建议，待确认）

### A. 拟合参数的条件性标准误差（目标 / 支持范围已认可，展示与数值契约待定）

- 在现有拟合参数旁增加`Conditional standard error`及可展开的假设 / 不可估计原因；保留残差图和RMSE原有含义。
- 建议使用最终解处局部Jacobian及残差方差估计，方法与支持边界在S0冻结；复用现有NumPy / SciPy，不更换求解器。
- 候选口径：实际样本数n、自由参数数p，残差方差为SSE/(n-p)，局部协方差约为该方差乘以(JᵀJ)的逆，标准误差取对角项平方根。实现宜用SVD等稳定分解，不直接求逆；必须恢复现有参数坐标 / 残差缩放后的原数值尺度。
- 仅解释为给定公式、固定参数、源数据和误差假设下的局部估计。披露零均值、独立同方差残差及局部线性近似假设；它不证明物理模型成立，也不包含比例尺、支点、时间等系统误差。
- 固定参数标`Fixed / not estimated`，不能填0；自由度不足、秩不足、病态、边界约束主导或非有限值给出不可估计原因。数值判据在S0经解析fixture冻结，不在草案中臆定阈值。
- **Q3已确认**：首版仅对未平滑的位置 / 角度数据提供条件性参数标准误差；平滑源及数值微分得到的速度 / 加速度仍正常拟合，SE显示当前方法不支持并说明原因。未平滑源也不自动证明独立性，仍披露统计假设。
- **Q4已确认**：仅直接拟合参数输出SE；例如Omega可有SE，用户公式`T = 2*pi/Omega`仍只显示换算值，不输出传播后的SE或完整实验不确定度。
- 旧结果无新统计时显示`Not recorded`，不自动重新拟合或回填。新拟合统计随原结果保存 / Undo；尝试日志有已记录统计才展示，历史重建不能编造当时未记录的估计。

科学依据：[SciPy curve_fit文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)说明残差方差缩放及局部线性协方差的局限；[least_squares文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)说明Jacobian与边界语义。本项目继续使用已锁定的SciPy 1.17.1；链接用于方法核对，不意味着升级依赖。上述公式是本期候选方法，仍待S0确认。

### B. 统一误差说明（融入现有结果，不另建工具）

- 区分四类：拟合残差 / RMSE、逐次重复间隔的样本标准差、参数条件性标准误差、尚未量化的系统误差。
- 重复间隔均值 / 样本标准差已有实现，补清楚“间隔之间的离散”；不默认新增std/√N，因为相邻间隔可能共享事件误差且可能相关。
- 沿用当前量 / 源的配方与来源披露：SG窗口 / 导数、端点、缺测、近似时序及角参考。只显示与当前结果相关的短说明和详情，不新建全局诊断面板。

## Acceptance Criteria（草案，全部待冻结）

- [ ] AC-1 参数统计：已知设计矩阵的线性拟合，条件性标准误差与独立解析计算一致；参数 / 残差尺度变换后保持正确，原拟合参数 / 预测 / RMSE不退化。
- [ ] AC-2 不可估计：固定 / 全固定、自由度不足、病态 / 秩不足、边界、非有限及不支持的处理源有明确状态 / 原因；没有伪造0或NaN / Infinity写入JSON，也不因统计失败抹掉合法拟合。
- AC-3 原差值验收：**2026-10-24用户明确取消，删除，不记作已通过。**
- [ ] AC-4 解释：UI可辨认四类误差含义及条件；不将重复间隔标准差当均值误差，或从参数SE推断完整测量精度。
- [ ] AC-5 生命周期：新统计保存重开 / 结果Undo/Redo一致，旧 / 未知字段与未来版本受保护；历史无记录不回填；源变化、切项目 / 轨迹 / 视频 / 工作区及晚到结果不能留下冒充当前的数值。
- [ ] AC-6 Gate：定向 / 全量、macOS+Windows CI、Independent Review / fixes / re-review及新一轮用户HR通过；文档与验收证据同步后集成 / push，只收尾6.4。

解析fixture、病态 / 边界数值判据及容差在S0、实现前明确记录；不新增真实准确率或固定响应时长门槛。现有P011仅用于回归与演示，不据此认定参数SE校准正确。

## Slices

- [ ] S0 — 用户确认范围与产品语义；冻结统计支持边界、数值fixture / 容差和摘要additive契约。重要新契约新增ADR，不改写Accepted旧ADR；建立Issue / 实现分支。
- [ ] S1 — 拟合统计贯通：domain纯计算 → 应用摘要 / 校验 → 保存 / 尝试日志 / 历史兼容 → 现有拟合页展示；解析与边界回归通过。
- 原S2两轨迹比较：**用户取消，未实施。**
- [ ] S3 — 解释与完整Gate：统一当前结果的误差含义，相关回归 / 全量 / 双平台 / 独立复审；给最短启动命令、操作→预期及封闭问题，停止等待真人HR。通过后集成 / 文档 / push。

## Verification / 预计改动面

| 范围 | 优先复用 / 检查点 |
| --- | --- |
| domain | function_fit的现有求解与缩放；新增统计纯计算；不改recurrence算法 |
| application | signal_analysis_job的summary与validated_analysis；source_recipe读取处理来源；fit_attempts / fit_attempt_view不重拟合历史 |
| GUI | signal_analysis_panel / fit_explanation参数展示及ChartActions结果交付；SignalHistory与SignalPreview维持职责 |
| 数据 / fixtures | 既有analysis summary additive字段、日志摘要、ProjectRepository往返；不做schema迁移 / 新依赖；旧记录与未知扩展fixtures |
| tests / docs | function_fit、signal_analysis_job、fit_attempt_view / journal、GUI与Session事务相关回归；本计划、current、Phase总计划及实际契约 / 架构文档 |

- 数值：用线性设计矩阵的独立解析解核对SE；非线性已知模型只验证局部估计与边界，不把一次合成拟合当覆盖率证明。
- 生命周期：新摘要严格有限JSON、字段类型 / 版本、未知扩展、保存重开、原子Undo、历史不回填、源变化与迟到拒绝。
- GUI：offscreen验证显示状态与只读，真人验证参数解释、不可估计提示及窄窗可达；不以截图 / computer-use替代HR。
- 产品实现后的全量命令：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`；最终分支经PR运行现有macOS / Windows CI，保持当前workflow分支触发策略。
- 本轮仅规划：检查文档链接、git diff与工作区；不重跑已通过的产品测试，不把历史1329项通过当本期验证。

## Review Gate

- **Independent Review：必须**，实现后的全新只读review会话。重点：统计尺度恢复 / 假设 / 不可估计、摘要兼容 / 历史只读、原子提交与迟到拒绝；记录`docs/reviews/phase-6.4-review.md`，修复后复审。
- **PR：建议**，作为完整diff与双平台CI观察容器，不增加额外形式审批。
- **Human Review：必须**，交付新用户交互时按workflow §5.1发起并等待用户亲测；本轮计划审阅不能代替实现后的HR。

## Grilling决策记录 / 下一轮

- Q1（2026-10-24）：用户“认可”。本期首先回答给定公式与误差假设下参数估计的稳定程度，不声称完整实验不确定度。
- Q2（同日）：用户“我们不做两条轨迹的比较了吧”。明确取消该新增范围及差值验收；既有叠图功能不删除。
- Q3（同日）：用户“支持”。首版仅未平滑位置 / 角度源提供条件性SE；平滑 / 导数源拟合保留，SE明确不支持。
- Q4（同日）：用户“接受”。直接拟合参数给SE，换算结果只给数值，误差传播后续。
- 下一轮：Q5确认参数值与SE的呈现方式；Q6确认重复间隔工具仅补误差解释，不新增统计计算。
- 所有回答汇总并经用户确认达到共同理解后，再冻结计划；访谈不等于实施授权。

## Result

- 当前仅形成可审阅草案；产品、测试、用户工程与论文线均未修改。
- 范围冻结、Issue、实现、数值验证、Independent Review、CI和HR均未完成；不勾选AC、不启动下一Slice。
