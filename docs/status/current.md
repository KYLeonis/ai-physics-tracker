# Current Status

> 2026-10-15：用户授权推进P6.3；Codex负责主要实现与复杂算法，GLM按需局部精修，Luna-max承担边界明确的子任务。

- 最后更新：2026-10-18（公式拟合联动本轮HR通过，以aa86d79集成main；0b80008主分支双平台CI39099618728通过，已验收产品树不变）

## Current

- **Phase**：Phase 6；6.1 / 6.2 / 6.3 / 6.3.1均完成并集成main。
- **Subphase / Slice**：[公式拟合联动](fit-linked-source-plan.md) S0–S3完成；最终8ea1f1b全量1271 / 独立Approve / 双平台CI通过，2026-10-18用户回复“通过”，本轮HR完成，以aa86d79集成main。6.4 / 6.5未开始。
- **Worktree / Branch**：产品主线 `/Users/leonis/Documents/ai-physics-tracker` / `main`，集成aa86d79；本轮实现分支`codex/fit-linked-source`已集成。论文worktree未改。
- **Development Mode**：Build Mode

## Next Recommended Action

- **本轮已交付**：用户通过grill-me确认先体验B后内部A，第一批公式拟合，并回复“自动补齐”。本轮[联动计划](fit-linked-source-plan.md)自动Gate / HR均通过并已集成，契约[ADR-0025](../decisions/0025-automatic-fit-source-preparation.md)。不扩大为重复间隔或后续阶段已完成。

1. **本轮收尾后停止，等待下一条开发指令**：公式拟合联动HR已通过，F1–F3 Closed，以aa86d79 `--no-ff`集成；PR [#33](https://github.com/KYLeonis/ai-physics-tracker/pull/33)记录完整diff。后续按已确认方向，先梳理重复间隔工具需要哪些联动，再形成小步计划；不要直接启动全局重构。
2. [架构扫描复核建议](../notes/architecture-review-assessment-2026-10-17.md)保留；按用户选择先体验B后内部A，当前先完成公式拟合，后续重复间隔联动及内部整理另按已确认方向推进，全局任务统一与Undo拆分仍后置。
3. 不自动开始6.4 / 6.5；GLM派工前读[协作记录](../notes/glm-collaboration-playbook.md)。

## Active Constraints

当前仍然影响下一步的规则（只列规则本身，细节以引用为准；新任务不得破坏）：

**数据与科学契约**

- P6.3两族`function_fit_<quantity>` / `signal_recurrence_<quantity>`各track / quantity最新一个槽，源只接既有线性 / 角量；完整source ID / 内容指纹和目标槽版本分别核对，原始 / 相对时间与实际样本保存，源删除 / 替换 / stale传播，schema v1 additive / 未来版本只读（ADR-0021）。
- `Undo result / Redo result`只移动栈顶本期结果事务，不越过raw / track / calibration / runs / 上游源；原Analysis全局Undo仍禁用。

- main 用户提供方程 / 公式，由通用平台计算与分析；论文硬编码 ODE 仅作复现参考（ADR-0017）
- 同步 / 后台计算均需本次有效时序；GUI合格Near-CFR自动按ADR-0024取得权限，不再要求人工Yes；修改区间置相关派生 stale，不改 raw 时间；提交还核对目标结果版本 / 配方 / 标定（ADR-0020）。
- 角运动四种标量 kind（angular_position / smoothed_angular_position / angular_velocity / angular_acceleration，rad 系，单列 values）；每轨迹每种 kind 至多一条，重算整组替换（ADR-0019）；6.2已显式消费标量与按帧配对的相图

- raw 层只存像素；世界坐标是 `CalibrationTransform` 的派生结果，`pixel_` / `world_` 前缀严格分层
- `frame_index` 是 int、时间是 float 秒；换算只经 Timeline 纯函数（nominal 模型 `frame/fps_nominal`，非 VFR 引擎）
- 缺测展开为 NaN 并按连续段滤波：不跨 NaN 段求导、不静默插值、短段按既定缩窗规则（ADR-0008）
- 平滑微分 = SG 先平滑后微分，默认 window=7 / polyorder=2（ADR-0008）
- Phase 6 规划约束：现有 `KINEMATICS_KINDS` 四项批次与图表两列 values 不是通用高级分析接口；新标量量和双轨迹依赖须显式适配并验证失效（pre-phase6 review §10）
- 预测永不自动成为 ground truth：completed infer 只是候选，显式 Activate/Replace/Clear 原子事务才改观测
- Accept 不产生 ground truth；Correct 才写 manual 并保留 prediction provenance
- `FrameSelectionResult` 只含帧号，不创建 TrackPoint
- 验证比较资格三态 clean / contaminated / unknown，fail-closed；series ID 相同 ≠ 可独立比较（Resume 祖先暴露）
- 被 train run 引用的 validation series 拒绝物理删除（Undo 路径同守卫）
- 显式 Save / Save as 清空应用内 Undo；静默 autosave 保留 Undo/Redo（accept_autosaved_snapshot）；激活产物指纹为 size-only（已接受的风险）

**工程约束**

- 首次 GUI 学习需当前轨迹 20 个不同 active manual 帧；已有 completed train 的该轨迹保留原再训练门槛。默认选帧 20 / K-means，推荐框和高级表单共享选帧信号 / 算法选择；新建 / 切换项目重置默认。不改变引擎至少 3 个训练帧的技术契约；固定检查帧可从 20 个标注中留出。候选 / Skip 不算标签；教师模型自检 / 推理不受此训练门槛限制。
- 推荐 `label_frame` 仅消费当前 Track 的真实选帧结果，在 working zone 内排除已有 manual 后启动连续队列；没有结果时不能顺序扫描源视频。新选帧取代旧代表帧批次，已保存标签不变。
- decoder 交付对象走 `queue.SimpleQueue` + 无参 Qt signal 唤醒：禁止 worker 线程直接 emit 携带 Python 对象的 queued signal（Windows heap corruption 教训）
- 训练强制 fresh per-run DLC 目录（复用旧目录会导致 shuffle 编号错位）
- Windows 真机 / CUDA 验收已批准延期至 Phase 9 打包前
- Phase 5.6 AC-9 改善目标缺口已归档（最佳 −3.3%，未达 ≥5%）：不重开、不改口径，留待独立保留帧或第二视频再评估

## Relevant Risks / Historical Context

- High-risk 改动（schema/持久化、坐标/时间语义、数值算法、拟合/不确定度、Undo/Redo、AI 激活、后台并发、打包/迁移）默认触发 Independent Review，在 mini-plan Review Gate 提前声明（`docs/workflow.md` §10.2）
- **P6R-02 教训**（[pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md)）：不得从 ID 本身推断科学有效性——同 series 也可能因祖先训练暴露而不可比；历史 RMSE 未改写，资格为 compute-on-read
- **P6R-01 教训**：Undo/Redo 必须维护 Track / run / 引用的一致事务，越依赖原子拒绝（回归：`tests/test_undo_run_integrity.py`）
- `Closed` finding 只代表当时证据下关闭；再触同一 invariant 时经 mini-plan Context Pack 引用（`docs/workflow.md` §6.3）

## Recently Completed

- **公式拟合联动HR通过 / 集成（2026-10-18）**：用户回复“通过”。本轮源自动补齐、相关输入变化刷新预览 / 单位 / 说明、各轨迹独立设置与冲突保护通过HR；以aa86d79集成已验证8ea1f1b产品树，本机1271 / 独立Approve（F1–F3 Closed）/ 双平台CI39046152498通过。只同步收尾文档，未改产品或用户实验；不开始重复间隔联动 / 内部整理 / 6.4 / 6.5。

  集成收尾提交0b80008的[主分支CI39099618728](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39099618728) macOS / Windows Python3.11均success；后续仅记录此回执，不重复产品测试。

- **自动近似时序 HR通过 / 集成（2026-10-17）**：用户确认本轮免确认流程“通过”。以已复审 / CI验证的4a713bc产品树通过801fda5集成main，集成CI39014441071双平台通过；代码与数值不再改动，保留近似来源 / FPS / 误差及异常重试。同步计划、Review与状态，等待下一条指令；不启动6.4 / 6.5。

- **自动近似时序增量（2026-10-17）**：用户授权取消Review timing / Yes；f34053f让同步 / 后台 / 重开对合格Near-CFR自动调用既有守卫，来源区分auto与旧user accepted，保持FPS / 两项误差说明；unknown / 真VFR / 超预算 / 取消不伪造权限。首批46、扩大91、charts单项及f34053f全量1241项通过，独立复审Approve / 73项通过；4a713bc清多余入口后31项通过，最终双平台CI通过，本轮HR待用户；未合并此补丁。

- **P6.3.1 HR通过 / 集成（2026-10-17）**：用户明确回复HR通过；已有独立R6 / 本机1232项 / 双平台CI通过，c0d1461以--no-ff集成main，保留main上084422f的架构评估文档和记录，源 / 测试树与97d7238一致。同步AC / 状态与HR记录；不将用户新增的取消时序确认需求倒填为旧HR已通过功能。

- **架构扫描复核（2026-10-17）**：核对GLM五个候选与现有代码 / ADR / 测试；修正任务生命周期Normal-risk、Undo / 配方无测试等判断。定向59项通过（2.62s），独立只读核查任务 / GUI回归137项通过（39.54s，561 warnings）；[建议草案](../notes/architecture-review-assessment-2026-10-17.md)按配方 / 源元数据、6.3.1局部生命周期、计算提取、后续全局生命周期 / Undo排顺序。仅评估与文档，未改产品、未开始6.3.1或重构，待用户选定方向。

- **P6.3.1第三轮HR返工（2026-10-16）**：97d7238让保存结果 / 底部尝试同步完整只读配方与图旁反馈，保留任意草稿，显式Return / Use；尝试仅在原源严格匹配及prepare守卫通过时评估记录参数，失败 / 缺源清旧图。R6发现全Fixed、离开Analysis、旧crossing标记三项边界，一并修复，26项 / 独立复审Approve。本机全量1232项通过（176.50s），[97d7238双平台CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38901656875)通过，HR待用户复测；不写用户实验、不集成main。

- **P6.3.1第二轮HR返工（2026-10-16）**：只读确认4次Fit已执行，theta/cos(theta)为常数，二次式误差仅改善0.07945%；Last saved result是最近Save快照。b9a5311/7a0c8f3/d90bd85直接展示实际公式/参数、外显含义/估值/错误，标准复选框支持方框/文字/space；提交拒绝不会冒称完成，恢复crossing提示正确Measure动作。定向47、最终guided20、状态3及恢复1项通过；本机最终全量1206通过，GUI复审Approve with limits，F26–F30闭环；最新macOS / Windows CI通过，HR待复测。原工程/日志只读未改。

- **P6.3.1收尾接管（2026-10-16）**：核对GLM交接与86de567失败CI，保留日志跨平台读取修复3275ca0；a6da1a3修复用途卡/dock刷新顺序及central widget缓存，删除无效布局补丁和临时probe，补大字体/会话过渡回归。定向58项、本机全量1199项通过，核心日志复审24项、GUI收尾6项及用途/工作流22项通过。原main/论文线保持原HEAD，P011冻结哈希未变；[a6da1a3双平台CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38890193235)通过。本轮新HR待用户，未开始6.4/6.5。

- **P6.3.1实现（2026-10-16）**：已授权开工，ADR-0022先冻结数值样本/日志契约；用途入口、图旁状态、自动草稿预览、受支持初值估算与手改保护、偏差/常数基线解释、部分换算失败动作、独立尝试日志和回看已实现。P011原冻结项目只读估算后一次拟合，θ T≈1.042407212s，原5%门不变，工程哈希不变。GLM Flash首轮tests_failed（漏eps），Codex接管修正，16项通过；worker工具权限限制和教训已存档。完整独立复审及返工复审通过；最终全量1199通过，macOS / Windows CI通过；用户实验/main/论文线未改。


- **P6.3.1规划冻结（2026-10-16）**：用户完成grilling Q1–16并明确认可冻结；偏好为英文版、图表主位 / 解释旁置，不接受固定毫秒或5分钟验收门槛。只读核查已保存试用：y源 / RHS theta实际是常数拟合，T换算缺Omega；旧结果仍显示、失败缺日志等机制解释“看起来没效果”。新计划单列High-risk估初值 / 解释指标 / 自动预览生命周期 / 日志契约，不倒填旧6.3交付或实施新代码，待开工。

- **P6.3 HR通过（2026-10-16）**：用户明确确认整体HR通过；既有A / C、B与时序入口补测、D的本轮HR关卡按此次整体反馈收口。用户同时提出新手不知用途 / 输出、反馈不够直观的新一轮改进，单独进入grilling，未修改旧验收口径、计算算法或用户工程。此反馈不扩大为Windows/CUDA真机或任意公式均可成功的准确性验收。已以92d00a2集成并push main；后续只做新的体验规划。

- **P6.3 Fit禁用 / 时序入口修复（2026-10-16）**：用户P011截图中的Fit / Preview禁用由本次媒体会话未确认Near-CFR引起，与公式类型 / 20帧训练门槛无关。只读实机探针复现：near_cfr、can_measure=False、确认按钮被Acquire父页面隐藏；Analysis还误报verified CFR。e4f04a0让同一时序状态 / 按钮随视频往返两工作区（不复制授权状态），Fit / 交叉按钮附近显示拦截原因，来源条随工程 / 轨迹 / 时序状态刷新。授权门、重开再确认、取消 / 拒绝守卫与计算契约保持不变；属Normal-risk局部GUI修复。新增工程重开 / 拒绝 / 接受 / 任意合法公式预览 / 布局恢复回归，定向15通过，本机全量1103通过（123.20s）；e4f04a0的[CI38766019892](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38766019892) macOS / Windows各1101 passed / 2 skipped，全部步骤success。真实P011读盘只读复现并核对project.json SHA256不变；按既有授权在独立内存会话确认后，x / theta各215样本prepare通过，未apply或save。B / D及此入口仍待真人补测，不集成main。

- **P6.3 HR反馈 / 交互修复（2026-10-15）**：用户A / C通过，B滚动 / 调线 / 信息密度不通过，D未反馈。工具页改常驻非瞬态纵向条、取消整页横向溢出；普通滚轮只滚页（数字框也不误改），Ctrl+滚轮 / 按钮缩放、Reset view恢复源范围。参考线与数值 / 滑块实时同步，Find / Center可找回；旧事件仅配方一致时显示。残差单独标签、明细 / 高级设置折叠，关键结果保留；数据来源显示真实来源而非错误manual-only(0)。主体相关GUI77项、本机全量1102项通过；最终补丁3cc546a增加窄窗最小宽度约束、切回原源后恢复事件并核对实际样本；末轮35项定向通过（11.06s），R8全新只读复审Approve，R7两项finding Closed；3cc546a的[最终双平台CI38760538586](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38760538586) macOS / Windows各1100 passed / 2 skipped，全部安装 / FFprobe / 测试 / 清理步骤success。尚未合并main；不把A / C通过扩大成整轮HR通过。

- **P6.3 HR入口可发现性修复（2026-10-15）**：用户找不到新工具；只读进程检查显示现有GUI工作目录为原main，原main未包含6.3。新UI原来位于Analysis第二层标签，入口不足。新增顶栏常驻蓝色Fit formula / Measure intervals直达、分析页蓝色提示、标签缩短为Formula fitting & intervals；改为绝对PYTHONPATH单行启动，避免从main加载旧源码。31项GUI回归通过（含任意工作区点按钮直达 / 数据不变），不改算法 / 数据契约 / main；最新双平台CI38732368831各1096 passed / 2 skipped，等待入口补测及原A/B/C/D。


- **P6.3自动Gate完成 / HR交付（2026-10-15）**：产品e74608d，本机全量1095；bec8d61仅补同ID源内容变化 / pipeline反序两个回归，文件18通过；最终CI38704158579 macOS / Windows Python3.11各1095 passed / 2 skipped。R4核心修复114定向、R5结果专用Undo67、R6测试闭环6项，分别独立Approve，F1–F9 Closed。P011应用均值1.041266844s vs人工1.0389815s，差0.21996%，最终18源组合prepare通过。公式 / 参数 / 初值预览 / 拟合 / 残差、独立交叉工具、追溯 / stale / 保存恢复和不越过raw / 源的结果Undo/Redo已交付。真人HR待用户；main与论文worktree未改，不集成 / 不进入后续。


- **P6.3 S1–S4增量 / R2修复（2026-10-15）**：实现安全表达式、单初值有界等权最小二乘、可辨识 / 失败 / 取消状态、通用交叉事件 / 段内重复间隔、结果换算。源 / 目标双版本、样本 / 时间快照、独立槽 / Undo / stale、删除参考轨迹历史保留与保存重开；Analysis中公式 / 参数 / 初值预览、叠图 / 残差、真实帧导航和保存设置恢复。复用一个执行器。R2发现2P2 / 2P3已修复待完整复审；全量基线1081通过，后续1085通过 / 1失败定位为detached共享契约，已e0431eb修复并定向55通过。最终全量 / CI / R3 / HR仍待，不宣称收尾。


- **P6.3 S0完成 / S1–S2初版（2026-10-15）**：用户提供P011原TOML，标定 / 支点 / 竖直方向及旧DLC哈希核对通过，600点连续轨迹与现有角量管线生成可重开的基准工程；无需改变角参考验收条件。冻结协议SHA `64ccd90b…53e63e`。首次新重复间隔算法获得7事件 / 6间隔，均值1.041266844s，人工1.0389815s，相对差0.21996%，全部交叉帧夹点与人工一致；此为领域算法对照，不代替后续应用 / GUI Gate。表达式28、拟合9、重复间隔13测试通过。公式控件已派给隔离Luna-max，复杂算法由Codex实现。


- **P6.3 S0启动（2026-10-15）**：用户授权Codex主要实现，GLM小任务 / Luna-max按需协作。从main `feaa80f`建立`feat/p6.3-function-fitting`。Luna只读核对上游派生ID传播入口；Codex起草ADR-0021及高级分析术语，保留既有clear全部派生语义。原目录本地逐帧人工参考页已生成，600帧图片 / 原source映射齐全，不含自动周期检测；已请用户亲自标记至少6个交叉事件。S0尚未完整冻结，未修改数值算法 / 安装依赖。

- **P6.3计划冻结（2026-10-15）**：用户最终回复“认可”，通用周期适用条件及整份[6.3计划](phase-6.3-plan.md)已确认，Q1–19决策闭合。建立跟踪Issue [#29](https://github.com/KYLeonis/ai-physics-tracker/issues/29)并同步需求 / 总计划 / roadmap / README / AGENTS / 回移档案。仅规划文档变化，8项产品AC与S0–S5仍未完成；P011仅完成候选媒体准备，真实参考未冻结，未安装Matplotlib或实现公式 / 拟合 / 周期算法。

- **P6.3规划 / P011候选（2026-10-15，草稿）**：用户通过grill-me确认显式公式编辑 / MathText、单标量拟合、测量默认 / 平滑可选、相对`t`与原始时间后台留存、普通最小二乘、独立周期及可选结果公式；ODE / 单位管理 / 置信区间等后续。用户指出周期工具不得绑定单摆，草稿补通用适用条件，待最终共同确认。P011源帧[300,900)裁成600帧 / 20.002111s候选，600帧完整解码 / source映射 / Near-CFR探针通过，源文件保留；manifest与逐帧CSV在原目录本地忽略`experiment/p63-reference/`。仍缺轨迹 / 角参考及独立人工周期参考，未冻结真实验收基准；无产品代码 / 依赖安装 / 算法实现。

- **P6.2全部HR通过 / main集成（2026-10-15）**：用户先确认其余HR，再确认轨迹多选补测“通过”，F1–F9 Closed。`--no-ff` 合并 `12b0911` 的树与 `feat/p6.2-angular-charts @ 8b1221b` 完全一致；源码 / 测试与 `76e9439` 一致。科学 / 事务全量1007及R3 Approve，控件51项GUI和最终双平台 **1008 passed / 2 skipped**；[已验收分支CI38582553294](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38582553294) success。同步AC-7、README / roadmap / AGENTS / review及后续档案；main已推送，PR #28 Merged / Issue #27 Closed；收尾文档 `a26f968` 的[main CI38595699864](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38595699864) macOS / Windows Python3.11均success。之后仅补此回执，不重复测试。本轮未新增产品代码 / 开始6.3，论文worktree与用户实验未改。

- **P6.2 HR轨迹多选修复（2026-10-14）**：用户反馈列表无法勾选两条、其余HR通过。局部控件修复 `76e9439`：可见空框、整行点击独立勾选、保持键盘当前行并由列表接管空格，原勾选信号 / 计算入口不变。新增名称 / 框 / 键盘3个真实输入回归，修复前名称点击失败；连续键盘回归另暴露刷新与全局播放快捷键问题，一并修复。51项GUI回归通过（32.09s），最新双平台CI38580981879通过；修复同步原P6.2分支供重启补测，真实项目 / 科学算法 / 论文worktree未改。

- **P6.2 完整review闭环 / HR交付（2026-10-14）**：R2关闭F1–F3，F4–F7（2P2 / 2P3）与自查F8修复 `ead9b0d`；旧线性来源披露与needs_update、两族同步 / 后台未知扩展保留、未来视图、领域变化即时取消、参考编辑刷新。定向186 / 全量 **1007 passed（88.42s）**，全新R3独立复审 **Approve / F1–F8 Closed**，[CI38512989022](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38512989022) macOS / Windows Python3.11均success。本轮Human A/B/C/D已发起，等待反馈；合成媒体已补齐且真实打开路径通过，用户实验和论文worktree未改。[review](../reviews/phase-6.2-review.md)。

- **P6.2 实现 checkpoint（2026-10-13）**：S1由ZCode GLM-5.3 / Flash交付并独立GLM-5.3科学审查Approve with P3；GUI增量由Flash交付，后续返工报明确ECONNRESET，CLI已退出，按Skill不自动重试、没有额度耗尽证据。Codex完成授权范围内GUI局部修复及测试。新增角量3时间图、θ–ω / x–vx、两种参考、rad/degree只显示、按源帧导航、按族状态 / 单executor / 缓存配方与显示恢复。数据76 / GUI55 / 全量 **991 passed（66.72s）**；代码 `365c2cc` 的[双平台CI38413697035](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38413697035)通过，当时完整独立review / HR待完成；后续闭环见上方2026-10-14记录，尚未集成main。[草稿PR #28](https://github.com/KYLeonis/ai-physics-tracker/pull/28)作为完整diff容器。局部证据与HR合成工程位于本地忽略`.zcode-control/`；2026-10-14补齐合成媒体并验证实际打开路径，真实实验和论文worktree未改。


- **通用 ZCode Skill 公开发布（2026-10-13）**：独立仓库 [KYLeonis/codex-zcode](https://github.com/KYLeonis/codex-zcode)，MIT / `v0.1.0`。已移除个人路径与项目记录，保留派工、模型核验、5 小时限额接管及 Desktop 对话登记；新增本地任务 / 日志 Git exclude 保护。18 项回归、Skill 格式校验、GitHub 安装器远端安装与安装后测试通过，本机全局 Skill 已同步。CI 模板已附，但当前 OAuth 缺少 workflow 权限，未启用云端 CI；Windows 真机与其他 ZCode 版本仍待验证。本轮未改产品代码 / 启动 6.2。

- **本机 ZCode 桌面对话同步（2026-10-13）**：全局 `$codex-zcode` runner 自动为派工会话登记 Desktop 项目索引，保留原生历史与已有用户记录；超时会话仅在工作区 / 时间 / 完整任务文本匹配唯一时登记。15 项回归与真实派工通过，Desktop 搜索 / 打开历史及 `DESKTOP_AUTO_OK` 回复已实测；客户端无需常驻，已打开的侧栏可能需搜索打开以刷新。5 小时额度用尽后由 Codex 检查增量并接续的授权已写入 Skill。本轮未改产品代码 / 开始新阶段；后续已授权派工沿项目状态入口推进。

- **全部 HR 通过 / main 集成（2026-10-13）**：用户确认本轮代表帧修复通过，同时确认此前 A/B/C 全部通过。按序 `--no-ff` 集成三项增量（`126e71d`）、6.1（`890f5b1`）、20 帧 / K-means / 自定义 / 代表帧队列修复（`4c8398e`）。各合并树与分支 tip 完全相同，最终树与已验收 `998501e` 一致；相比已通过双平台 CI 的 `653e315` 仅文档变化。main 文档收尾 `24403f0` [CI 38364390179](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38364390179) macOS / Windows Python3.11 success；Issue #24 / #25 / #26 已更新 Result 并 Closed。没有新增产品 / 测试代码或 GUI 行为；用户未提供逐项设备 / 平台详情，不扩大为 Windows CUDA 真机或科学准确性验收。论文 worktree 与用户实验未改。

- **本机 Codex → ZCode 基础配置（2026-10-13）**：全局 `$codex-zcode` Skill 已安装，复用 ZCode.app 内置 CLI 0.16.9 与现有 BigModel Individual Coding Plan；Flash 常规实现、GLM-5.3 复杂任务 / review、Codex 验收与有限返工。两种模型真实调用及 Flash 写文件链路通过；runner 11 项自检通过，补齐暂存区检查、实际模型核对与 Windows 进程树清理（Windows 仅 mock）。任务 / 日志放本地忽略的 `.zcode-control/`，未修改产品代码 / 启动新阶段；下一步仍按上方 HR 顺序，后续已授权实现可调用该 Skill。

- **HR 反馈修复：K-means 结果未被推荐标注消费（2026-10-13）**：`20261013_test5` 两次真实结果均为跨视频的 20 帧，已有人工标签却为 0–19；根因为 `label_frame` 顺序遍历 working zone，零标签选帧成功后还推荐再选。代码 `2fa955a` 改为沿当前轨迹的实际算法结果启动连续标注；排除已有 manual，不顺序补帧，显式重选时替换旧代表帧批次。新增 5 个回归，定向 88、全量 **938 passed（63.02 s）**，用户原实验四个文件 SHA256 未改变。当时 HR 待重测；现已通过并集成 main，未启动 6.2。
  `8153cb1` CI macOS success、Windows 935 passed / 2 skipped / 1 failed（原检查集重建 fixture 无 lineage、粗时钟下 created_at 同值）；fixture 改为明确训练来源并强制相同时间，`653e315` 定向 34 / 最终全量 938 passed（59.72 s），产品时间语义不变。[CI 38361205836](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38361205836) macOS / Windows Python3.11 success。

- **首次学习 / 选帧引导（2026-10-13）**：分支 `fix/initial-annotation-guidance`，代码 `b9267e3`，Issue [#26](https://github.com/KYLeonis/ai-physics-tracker/issues/26)。首次 GUI 学习需 20 个不同人工帧，推荐框 / 高级训练 / 连续标注完成提示一致；20 / K-means 默认选帧，推荐框自定义弹窗解释并选择 K-means / Uniform，取消不启动，同一项目沿用算法，新建 / 切换项目恢复默认。已有 completed train 的同轨迹再训练保留门槛，教师模型路径与引擎至少 3 个训练帧契约不变。新增 4 回归；定向 118、末轮 58、最终全量 **933 passed（56.79 s）**，diff 检查通过；`85be73e` [CI 38349426753](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38349426753) macOS / Windows Python3.11 success；后续 HR 已通过并集成 main，未启动 6.2，实现与集成记录见[计划](initial-annotation-guidance-plan.md)。

- **6.1 完整复审 / 6.2 计划（2026-10-12–13）**：复审整个 6.1 调用链，修复原 R2 与新增 R8–R13：旧构造兼容、公共计算时序、近似 / 区间来源、旧批次覆盖新结果、规格 / SG / 引用一致、标定 pipeline 一致；代码 `80661c1` / `aacb379` / `5f50a16` / `4842560`。新增 21 回归，定向87、全量 **929 passed（66.38 s）**，全新最终独立复审 Approve，[CI 38274300024](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38274300024) macOS / Windows Python3.11 success。ADR-0020 与 6.2 mini-plan 已写，未改论文 worktree / 未实现 6.2；现已在前置 HR 通过后集成 main。

- **Phase 6.1 角运动分析基础（2026-10-11）**：分支 `feat/p6.1-angular-analysis`（Issue #25），实现+review 修复共 3 提交。交付 ADR-0019、`domain/angular.py`、`DerivedInput.reference_track_id`（双轨迹失效/级联/同视频校验）、`compute_angular`、`angular_job` 后台原子批次与序列化往返；新增 43 测试，本机全量 **908 passed** 零回归，分支 [CI 38157600556](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38157600556) 双平台 success。Independent Review 首轮 Approve with findings（7 项：5 修复+复审确认、2 延期——R2 zone 失效移交 6.2、R7 父分支 flake 与本 diff 无关）；[review record](../reviews/phase-6.1-review.md)。原分支已 push；R2 / R7 后续均 Closed，现已在前置 HR 通过后集成 main。

- **本轮三项增量实现 / 复审（2026-10-11）**：工作分支 `feat/main-guided-refinement-model-import`，代码 `1743f61` / `229b7d4` / `c998fd0` / `0c71910`；定向45 + 末轮28通过，全量 **865 passed（77.50 s）**，最新代码 [CI 38144024802](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38144024802) macOS/Windows Python3.11 success。R1/R2/R3 六项 findings Closed / Approve；[review record](../reviews/main-guided-refinement-model-import-review.md)。实际 DLC spawn 四点自检及三帧 tip 推理 `auto → mps` 成功；当时 HR 待反馈；现用户确认 A/B/C 全部通过，已集成 main。方程口径与后续档案同步 ADR-0017/0018 / AGENTS / roadmap / specs / README。

- **主线 UI 维护 HR / 集成（2026-10-11）**：用户整体确认“上一轮的HR通过”，五项回移与顶部推荐完成 `--no-ff` 集成 / push（`017cc04`）；无新产品 / 测试修改，合并树与分支 `24ec071` 的双平台 success CI 一致。main [CI 38138010183](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38138010183) 双平台 success，Issue #23 已关闭。用户未提供逐项设备 / 平台明细，不扩大为 Windows/CUDA 全阶段验收。后续优先级见[区别文档 §10](../notes/publication-main-feature-ui-differences.md#10-hr-通过后的回移建议2026-10-11)。

- **论文 / main 全量区别扫描（2026-10-11）**：固定 main `50a7924` / 论文集成 `b459e4a` / 最新工作线 `154f262` / 当前维护 `3c43544`；完整 inventory **637 文件、229 提交、80 源码模块（53 新增 / 27 修改）**，明确已同步、待主线 HR、论文独有及 main 独有文档。补充 Analysis 模式仍可保留标注的内存探针与回移候选；保留 E3 30/48 / E2 47/48 与发行真人缺项。公开 v0.1.0 的 11 资产 / 固定源码重新在线核对；链接、计数、diff 检查通过。仅文档，未跑真实训练 / 论文全量、未改用户工程 / 论文 worktree / 合并产品；[报告及附件](../notes/publication-main-feature-ui-differences.md)。

- **macOS Start learning 设备核查（2026-10-11）**：主线 auto 保留到 worker，按 CUDA→MPS→CPU 解析；本机 `.venv` Torch 2.13.0 实测解析 mps / 张量 mps:0。GUI 捕获三种设备选择均保留，定向 4+9 passed；论文 `5ada419` 是联合路径固定 CPU 修复，单轨无需回移。仅记录检查，未改产品/用户工程、未启动 DLC 完整训练；[核查记录](../notes/publication-backport-assessment.md#start-learning--macos-auto-设备核查2026-10-11)。

- **顶部推荐扩展（2026-10-11）**：按用户补充授权，常驻主线 TaskCard 的摘要/主动作/最多两个旁路；复用原动作入口，空会话推荐 Add video，审核/标注返回获取轨迹。定向 **72 passed（9.19 s）**，全量 **820 passed（48.44 s）**，self-review/diff/窄窗口布局探针通过。代码 `8c16908` / CI checkpoint `fe051f5` 双平台通过，Human Review 本轮用户已确认通过；[mini-plan](main-ui-backports-plan.md)。

- **UI 回移自动验证（2026-10-11）**：代码 `53a6fb9`，三个 GUI 文件/十项滚轮回归，五项通用修复与源提交溯源；定向 107 passed（12.60 s）、全量 815 passed（49.36 s）、实际 widget 展示断言及 diff 检查通过。checkpoint `167a518` 的 [CI 38110444232](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38110444232) 双平台 success；无论文 schema/领域/依赖改动。分支已 push，用户已确认 HR 通过，本轮已集成 main（`017cc04`）。
- **论文线回移评估（2026-10-11）**：审查 publication 集成分支及最新发行分支 `154f262`；确认两项值得优先回移的通用 UI 问题、三项小改进，取消源码/测试已等价同步。主线定向 50 passed（7.07 s），只读探针与目标 patch 适用性检查通过；产品代码未修改。详见 [评估记录](../notes/publication-backport-assessment.md)。
- **Phase 6 规划草案（2026-10-11）**：已核对主线/远程、既有运动学/图表/DerivedData 契约，新增 requirements、总计划及 6.1 mini-plan；建议误差门槛待确认，未修改产品代码或论文线。主线回归 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`：**805 passed，56.91 s**；草案本地链接与 `git diff --check` 通过。基线 `b997100` 最新 CI [36813834691](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36813834691) 已在线复核 success。
- **Windows 取消维护修复（2026-10-01）**：强杀后原生 join 确认 worker 退出；54 项定向与 Independent Review Approve。main CI [36813075358](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36813075358) 双平台通过；细节见 [mini-plan](windows-cancel-fix-plan.md)。
- **Agent-first Workflow 2.0 升级（2026-09-18，分支 `docs/agent-workflow-2.0`）**：引入 Agent Context Pack、Cold-start Protocol 2.0、risk-based Review Gate / PR 流程、Source of Truth 分工表、Development Modes、finding 继承规则；重写 subphase-plan 模板，current.md 改为运行时入口结构。顺手修正过期事实：repo 可见性 Private→Public、architecture.md ADR 索引补 0009–0016、AGENTS.md 移除已删除的 CODE_OF_CONDUCT.md 条目。
- **Phase 5 收官（2026-09-18）**：5.7 R1/R2 CLOSED + 最终 Human Review 通过；全量 **804 passed**，双平台 CI 绿（[run 35319559409](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35319559409)）。Phase 5.0–5.7 全部完成；AC-9 缺口保持归档。各 subphase 交付与 review 见 `docs/status/phase-5.*-plan.md` 与 `docs/reviews/`。
- **Pre-Phase 6 Stabilization（2026-09-16，已合并）**：P6R-01/02/03/04 及 R1 补漏（P6R-02-R1 / 03-R1 / 05）全部关闭，生命周期见 [pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md) §17–19 与 [pre-phase6-stabilization-review.md](../reviews/pre-phase6-stabilization-review.md)；**Phase 6 Entry Gate：READY**。
- **Windows CI heap corruption 根治（2026-09-16）**：根因为 decoder worker 线程 emit 携带 Python 对象的 queued Qt signal；`_DecodeDeliveryBridge` 修复 + 4 项回归（取证与细节见 git log `fix/windows-ci-crash` 与 pre-phase6 review §5）。

CI回执：用户报告旧53a0dfd失败邮件，已取回双平台日志确认均仅快照共享断言失败；e0431eb修复后push与PR CI全部success，[记录](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38701431104)。
