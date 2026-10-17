# P6.3.1 Independent Review Record

## Scope / Gate

High-risk；[计划](../status/phase-6.3.1-plan.md)、[ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)。基线main@985fd7c，首个完整实现2d4e0ef；数值、日志、GUI编排及已保存结果语义。Reviewer只读、主Agent修复；原6.3 HR不能替代本轮。

## R1 — 定向独立审查与Codex验收

GLM Flash独立worktree负责误差解释模块；Luna分别负责日志codec、用途导航。Luna随后交叉审查未参与编写的数值与日志编排。以下均由Codex实施修复；最终完整独立复审确认后才Closed。

| ID | 等级 / Decision | 问题与证据 | 处置 / 回归 | 状态 |
| --- | --- | --- | --- | --- |
| F1 | P2 / Must fix | 归一化Jacobian仍用绝对eps判零，1e17及1e-200常数误报不可辨识 | 先按每列最大值缩放再取列范数和相对秩；极端尺度常数回归 | Closed（Luna复审） |
| F2 | P2 / Must fix | 纯噪声也必有FFT最大峰，返回无依据振荡初值 | 初值正余弦投影须解释至少一半样本起伏，否则明确人工回退；seed0–4纯噪声 | Closed（Luna复审） |
| F3 | P2 / Must fix | segment_indices长度/维度/有限性没验证 | 1D/同形/有限验证；4种畸形输入回归 | Closed（Luna复审） |
| F4 | P2 / Must fix | 合法JSON但formula为数值/elapsed为文本可使GUI刷新崩溃 | codec验证已拥有字段及唯一ID，原字节只读保留；3畸形字段回归 | Closed（Luna复审） |
| F5 | P2 / Must fix | 非预期prepare异常外逸并遗留running | GUI边界记录failed及原因；RuntimeError回归 | Closed（Luna复审） |
| F6 | P3 / Should fix | 只读日志显示Retry，点击却无效 | 只对可重试IO错误显示；只读原因继续可见 | Closed（Luna复审） |
| F7 | P3 / Should fix | 源/目标版本拒绝记成普通failed | ProjectSessionError明确记rejected，保留原因 | Closed（Luna复审） |
| F8 | P2 / Must fix | GLM任务/回复声称64*eps阈值，代码漏eps；runner tests_failed | Codex核对diff并补eps，实际16项通过再cherry-pick；不追加调用 | Closed（Luna复审） |
| F9 | P3 / Should fix | Show whole model会覆盖Reset的源范围（Codex自查） | 显式展示模型但保留源范围，Reset回归 | Closed（Luna复审） |

R1附带边界：混叠频率不可由离散样本唯一恢复，初值说明明确为 sampled signal / 可能alias，不自动作物理周期；接近两周期频谱网格边界保守拒绝，说明需扩区间。带符号的部分等价自定义写法仍可人工输入，不宣称完整符号代数等价识别。

## R2发现与修复

| ID | 等级 / Decision | 问题 | 修复与回归 | 状态 |
| --- | --- | --- | --- | --- |
| F10 | P2 / Must fix | 同project_id不同根的副本可被旧内存日志覆盖 | 普通sync按ID+root重新加载，只有显式saved=True转移；bind核对源字节，副本差异保留；应用与codec回归 | Closed（Luna复审） |
| F11 | P2 / Must fix | 初次读故障被永久readonly，Retry无效 | load_pending先恢复磁盘基线和未知字段再追加内存项；未知/损坏仍只读；故障与恢复扩展回归 | Closed（Luna复审） |
| F12 | P2 / Should fix | 只缩放残差仍可因参数单位报假收敛 | 非零初值绝对值作参数坐标尺度；零初值使用预算内模型响应探针，失败回退1，原单位输出，记录parameter_scales；线性/二次1e12/1e-200回归 | Closed（Luna复审） |
| F13 | P3 / Should fix | writer允许重复ID，reader拒绝自己写的文件 | 读写共用字段校验，重复ID/改ID拒绝在写前 | Closed（Luna复审） |
| F14 | P3 / Should fix | 缺status无法分类/中断 | status在读写边界必须为非空文本，原坏文件保留 | Closed（Luna复审） |
| F15 | P2 / Must fix | 正在运行的preview阻塞正式Fit共享队列 | ADR-0023独立预览executor/Event，正式任务不排在其后；实际阻塞预览回归 | Closed（Luna复审） |
| F16 | P2 / Must fix | Previous saved result实际读取最新内存槽 | 磁盘保存基线getter与Latest applied result分离，Save前后对照回归 | Closed（Luna复审） |
| F17 | P2 / Must fix | annotate/submit异常遗留running或外逸 | 正式/预览提交统一错误边界，清理任务并结束正式日志；提交失败回归 | Closed（Luna复审） |
| F18 | P3 / Should fix | 工具目标与顶部来源条不一致 | 工具路径用panel目标及实际点来源计数，设置/目标更改刷新；双轨迹回归 | Closed（Luna复审） |

## Verification

- 数值初值/原拟合38项，含冻结样本与上述数值修复。
- 定向日志/应用/GUI/分层40项通过；后续新增交互修复定向22项通过。
- 2d4e0ef本机全量1174 passed（100.23s）；最终代码另做相称验证。
- P011原冻结输入只读，θ拟合换算1.04240721177s，原5%周期阈值未改；详情见[验证记录](../notes/phase-6.3.1-verification.md)。

## R3 — 全新核心 / GUI 独立复审与返工闭环

Reviewer为未参与相应实现的只读Luna会话：`p631_independent_core`、`p631_independent_gui`。完整检查数值初值与求解、解释指标、日志归属与兼容、独立预览生命周期、当前/磁盘结果身份、源/目标守卫；主Agent实施返工，Reviewer复审。不是GLM接管者对自己修改的“独立批准”。

| ID | 等级 / Decision | 问题 | 处置 / 回归 | 状态 |
| --- | --- | --- | --- | --- |
| F22 | P2 / Must fix | SaveAs遇冲突后再次另存可丢失sticky只读状态 | A→冲突B→复制C仍保留只读；B/C原字节不覆盖 | Closed（核心复审） |
| F23 | P2 / Must fix | 零初值固定尺度1仍可假收敛 | 单次求解前用预算内、遵守bounds/cancel的模型响应探针定尺度；不改变可见初值，无效探针回退；解析尺度回归 | Closed（核心复审） |
| F24 | P2 / Must fix | 巨大有限常量的直接均值可溢出 | 缩放后计算常数均值基线；1e308常量RMSE=0、baseline=0、improvement=None | Closed（核心复审） |
| F25 | P2 / Must fix | 回看/恢复设置后曲线、摘要仍可能标成旧保存结果 | Current draft、Latest applied、Previous disk-saved及legend同步；恢复设置清图/详情，再预览当前草稿 | Closed（GUI复审） |

核心最终定向 **57 passed**，结论 **Approve with practical limits，无阻断finding**；GUI最终定向 **28 passed**，结论 **Approve**；Explore用途卡补查4项通过。F1–F18与以上返工已复核。原两个Acquire头部断言已在755993d同步工作区预期，不以旧Analysis训练卡语义限制新用途入口。

数值边界：巨大偏置可能使零参数探针不可辨识；极端异号1e308中心化仍可能溢出并明确拒绝。初值估算只覆盖冻结结构/信息充分样本，单次局部求解不保证任意初值全局收敛；不把这些边界称为物理模型正确性。

## R4 — GLM收尾接管与Windows修复复审

GLM在3275ca0修复日志异常分类，但86de567的Windows CI仍失败（[38876986811](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38876986811)：resize实际1415、预期1292）。其“wait(10)已修复 / 用户不受影响 / 无遗留探针”记录不符合最终代码和CI证据，已撤回。GLM对自己修改的检查按self-review处理。

| ID | 等级 / Decision | 问题 | 处置 / 回归 | 状态 |
| --- | --- | --- | --- | --- |
| F19 | P2 / Must fix | Windows对日志父路径被普通文件占用报FileNotFoundError，误当新日志，恢复后基线冲突 | 保留GLM的_read_existing分类修复，四处读取共用；21日志测试Windows已通过，Luna收尾复审日志+应用24项通过 | Closed（核心复审Approve） |
| F20 | P2 / Must fix | 分析用途卡的宽度与Acquire dock叠加，窗口保留旧最小尺寸 | a6da1a3先刷新当前用途卡再显示dock，最后centralWidget.updateGeometry并重算主布局；删除无效Ignored策略/三层activate及临时probe。24pt在本机复现旧1670≠1449，现通过；保留原resize断言并新增大字体回归 | GUI复审通过；双平台CI通过，Closed |
| F21 | P3 / Should fix | 日志尚绑定但session已清空时showAttempts空引用 | 局部session快照及None保护；会话过渡回归 | Closed（GUI复审） |

本次两个只读Reviewer复用此前会话，仅复查新增收尾diff：核心 **Approve**；GUI几何/空session定向6项通过、用途/工作流22项通过，最终 **Approve**。Reviewer在首次回信带入的两条旧测试finding已按当前a6da1a3核对并明确撤回。完整自动Gate回执及HR状态见[验证记录](../notes/phase-6.3.1-verification.md)。本轮Human Review仍须用户亲测，未集成main。

## R5 — Human Review反馈返工（独立复审通过，HR待复测）

用户明确反馈体验不满足；后台四次Fit有不同公式与参数，不代表用户已看懂结果。本次不放宽科学验收，不改变原始数据或强行让任意公式解释振荡。

| ID | 等级 / Decision | 问题 | 修复 / 回归 | 状态 |
| --- | --- | --- | --- | --- |
| F26 | P2 / Must fix | 当前/历史公式和拟合参数只在折叠详情，常数模型说明在滚动表单 | 图上方独立modelLabel用记录的表达式/参数；meaningLabel移出controlsScroll。历史回看不改编辑器；初值/历史身份回归 | Closed（GUI复审） |
| F27 | P2 / Must fix | 操作完成/拒绝/取消、估值回退和超范围提示需要用户翻找 | 显式showFeedback定位外层分析页；自动预览不滚动，图旁保留保护/估值/视野说明及带单位的基线对照 | Closed（GUI复审） |
| F28 | P2 / Must fix | checkable QGroupBox标题方框命中不符合用户直觉 | 五个折叠入口改标准QCheckBox及独立内容；实际indicator/文字/space输入回归 | Closed（GUI复审） |
| F29 | P2 / Must fix | _poll提交结果被guard拒绝后，尾部仍会覆盖为Current calculation completed | 仅apply成功后标完成；旧结果不变、日志rejected及错误文字保留回归 | Closed（GUI复审） |
| F30 | P3 / Should fix | 从crossing恢复设置仍提示click Fit，指向隐藏动作 | 按工具区分恢复标题/提示；实际保存/恢复crossing回归通过，Reviewer核对1项通过 | Closed（GUI复审） |

只读Luna复审当前GUI增量：**Approve with limits，无P1/P2阻断项**；指出的F30也已修复并复审。Reviewer定向68项、后续35项、最终guided20项及crossing恢复1项均通过。主Agent定向47项、状态3项通过，本机最终全量 **1206 passed（166.80s）**；最新macOS / Windows CI通过。Limits是Windows原生体验与HR由主Agent/用户另行验收，不替代科学模型正确性。

## R6 — 历史配方整页同步（独立复审通过，HR待复测）

用户第三轮反馈否定“只换图表、编辑器仍是草稿”的交互；保存结果与底部尝试入口须一致响应。新增SignalHistory保留原始草稿并投影完整只读配方；attempt重建只评估已记录参数，严格检查原源与当前prepare守卫，不调用Fit、不激活 / 写入Project或日志。日志摘要契约保持不变。

| ID | Severity | 发现 | 修复 / 证据 | 状态 |
| --- | --- | --- | --- | --- |
| F31 | P2 / Must fix | 保存快照只有曲线切换，表单与指引未同步 | 公式、记录初值 / 约束、输入 / 区间、方法与解释整页只读同步；Return原样恢复草稿、Use显式采用；无效草稿与项目 / dirty / Undo不变回归 | Closed（R6独立复审） |
| F32 | P2 / Must fix | 底部尝试只有JSON摘要，未提供对应曲线 / 整页反馈 | activated选择（含同项重选）同步配方；原源严格匹配时后台重建，失败 / 缺源清旧图并就地说明；跨视频、变源、返回 / 新选择 / 授权撤销后迟到拒绝 | Closed（R6独立复审） |
| F33 | P2 / Must fix | 全Fixed的given_parameters被误当非成功历史 | 接受既有可发布的success / given_parameters；真实全Fixed结果评估比对，显式浮点容差1e-12 | Closed（R6独立复审） |
| F34 | P2 / Must fix | 切Acquire改源后仍保留历史模式和旧图 | 离开Analysis恢复草稿、取消历史交付、失效初值预览；Acquire修改源往返回归 | Closed（R6独立复审） |
| F35 | P3 / Should fix | Use crossing setup后旧事件线被源预览重新叠加 | 清事件及样本匹配，禁止草稿源预览复用旧标记；下一次显式Measure / 历史回看才显示记录事件 | Closed（R6独立复审） |

只读Reviewer `p631_independent_gui`独立检查GUI和新应用层重建模块，首轮定向22项并指出F33–F35；主Agent修复后，对产品`97d7238`复审 **Approve，无新增finding**，独立26项通过（21.76s）。主Agent同一新应用 / GUI回归26项通过（15.87s）；完整Gate证据见[验证记录](../notes/phase-6.3.1-verification.md)。本轮交互仍需[第三轮HR](../notes/phase-6.3.1-human-review.md#第三轮反馈与复测2026-10-16)，未集成main，不以自动Gate代替用户体验。

## 2026-10-17最终HR与集成

用户明确回复“HR通过”。P6.3.1按本轮整体反馈收口，c0d1461以--no-ff集成main，保留084422f架构评估文档；产品 / 测试树与97d7238相同，已有1232本机全量 / R6 Approve / 双平台CI通过。不把该反馈扩大为Windows/CUDA真机通过，也不包含同条消息新提出的自动接受近似时序；后者单独开发 / 验收。
