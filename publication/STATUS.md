# Publication Status — EJP Undergraduate Pendulum Platform

- 最后更新：2026-10-01。
- Worktree：`ai-physics-tracker-ejp`；integration branch：`publication/ejp-damped-pendulum`。
- 当前：**P0/P1/P2完成；P2.3用户于2026-10-01确认图表已出现、当前增量可交付并明确授权收尾。Independent Review全部finding Closed、最终Approve；最终验证1251 tests/9subtests及冻结证据通过；--no-ff merge `99f34b0`已完成，提交最终状态后推送。** 当前角运动为tip + fixed pivot，辅助role仅诊断；默认SG9/3，支持显式7/3、5/2及自定义窗口/阶数，配置随结果保存。
- P3–P6未启动；本阶段结束后停止，等待用户下一条指令。图表外观一般已记为非阻断改善事项，不在本轮追加实现。
- Windows G1–G4仍按用户既有决定延期至P6前、证据not_run；main通用产品线状态不随本次P2完成改变。

## P1 planning

P1 最终验证（2026-09-30）：全量 **1154 passed, 9 subtests passed**，Independent/Human Review 均通过并已合并；macOS/Windows CI run 36674309852 通过。旧的 1151/待 Human Review 状态已由最终证据替代。

- [P1 complete mini-plan](plans/p1-four-landmark-measurement.md)：保留P1.1–P1.4边界，按schema/setup → complete-frame annotation/export → external worker/joint training/teacher import → joint inference/review/atomic activation实施。
- 计划明确每个Subphase的Context Pack、scope、slice依赖、AC、自动化与真实DLC验证、增量Human Review、risk-based Independent Review及失败恢复。
- 关键实现顺序：先v1/v2双格式与Save As事务，再共享4/4标注；AI阶段先收敛P0.3 external worker边界，再训练/导入/推理；最后才做四轨activation和P2 adopted-measurement handoff。
- 以上为P1初始规划边界；实际实施进度以本状态页开头和各Subphase执行mini-plan为准。

## P0.2–P0.4 deliverables / current gate

- [Experiment/run/derived contract](spec/experiment-run-derived-contracts.md)：四role、scale与方向确认、release/L/g、model来源、四轨事务、single-track API guard、多输入stale及Qt-free结果。
- [ADR-0017](../docs/decisions/0017-publication-project-contract.md)：用户已明确批准schema v2 + Save As迁移副本；本轮没有实现迁移。
- [Runtime boundary](spec/runtime-boundary.md)、[8项冻结程序实测证据/命令](evidence/runtime/README.md)、[结果及source hashes](evidence/runtime/results.json)：Mac CPU真实1 epoch训练/10帧推理/5manual保护/保存重开通过；MPS仅tensor自检。取消/错误日志通过；DLC取消只测到启动期。
- 20项contract tests、P0.1离线15文件校验通过。src/产品代码未改；仅修复既有DLC smoke的过期自动激活断言。无GUI，无GUI Human Review。
- **未满足的验收：Windows x64 frozen启动/CPU DLC train+infer/进程树取消（G1–G4）**。已备PowerShell交接命令；用户已明确选择“明确延期 Windows 验证，作为 P6 前必须完成的门禁”（2026-09-20）。macOS已有venv不能证明clean-machine安装，G5保留P6。本次延期仅调整验收时点，不将Windows标记通过；未完成该门禁不得进入P6。

独立只读Reviewer最终确认：数据合同/协议范围PASS，无未关闭blocking finding；其独立运行7项tests通过。记录：[P0.2](../docs/reviews/publication-p0.2-review.md)、[P0.3](../docs/reviews/publication-p0.3-review.md)、[P0.4](../docs/reviews/publication-p0.4-review.md)。合同审查通过不代替Windows证据。

## Current direction

own video → Pendulum experiment → fixed calibration / manual release → four landmarks → own DLC training OR teacher model import → infer/review/QC → θ/phase/period/energy → M0/M1 → criticism/structural identifiability → export。首发Windows x64 + macOS arm64，轻量app + first-run runtime。

## P0.1 deliverables

- [Scientific profiles contract](spec/scientific-profiles.md)：legacy/student/diagnostic边界、精确科学语义、Qt-free请求契约、证据限制。
- [Legacy JSON](profiles/legacy-publication-v1.json)、[student JSON](profiles/student-default-v1.json)、[diagnostics JSON](profiles/diagnostics-v1.json)：数值/公式、边界规则及provenance；不是科学功能实现。
- [Source map](evidence/source-map.json)：正式source版本、ZIP成员、逐视频input/trajectory hash、SQLite table selection、method→profile→golden。
- [Golden evidence](evidence/README.md)：15个小型冻结文件，包括24输入元数据、48正式fit、2个完整processed轨迹及诊断；E0–E4字段/单位/比较门槛；synthetic cases合同；其余22条完整轨迹按路径/hash读取原件。
- [Read-only verifier](../scripts/verify_publication_evidence.py)与[13 contract tests](../tests/publication/test_evidence_contract.py)。
- [Mini-plan](plans/p0.1-scientific-profiles.md)；[Independent Scientific Review](../docs/reviews/publication-p0.1-review.md)。

## Resolved scientific decisions

- D01：publication SG9/3独立于main7/2；历史短段策略与student≥9点分段策略分别命名。
- D02：legacy保留原mask（不检查tracked pivot finite）；student严格完整四点+geometry+explicit exclusion，无0.60 hardcut；人工tip相对weight1且confidence保留null。
- D03/D04：正式effective-release source allowlist；旧residual/history表不能作正式golden；fitting.py使用正式hash匹配的ZIP版本。
- D05：information extrema、phase halfcycle skip2、EDP skip5、tail、objective各自保留算法和积分容差。halfcycle signed contraction与EDP abs loss分开；速度分层frame/interval分开。
- D06/U04：manual release无自动−1；前5有效帧且确认静止才默认IC；否则显式fixed IC。student gap不桥接、tail最后1/3且≥10完整周期、fit count/跨度门槛等均标new_student_policy。
- U03：SciPy1.17.1隐式参数已按版本源码恢复；保留run-reported environment，未伪造完整lock或跨平台数值等价结果。

## Verification boundary / remaining items

本轮：13 unittest通过；core.autocrlf=true暂存树临时checkout的哈希验证通过（非Windows数值实测）；离线15文件/48fit/2完整trajectory检查通过；带root的83个外部来源只读hash/表selection核验通过；4个public-library URL源码在恢复时按固定版本取hash。正式source11项均匹配run manifest；全部24 IC hash对应正式fit。未修改科研原件、执行历史分析脚本、重拟合、训练或生成论文图。

这些是证据/契约验证，**不是P2–P4数值功能或48fit复跑已通过**。拟定数值容差待未来实现逐项实测；非bitwise依赖lock缺失如实保留。剩余非阻塞项：raw四点→θ/mask及pre-release median没有offline历史重算；历史逐start日志缺失；部分完整轨迹仍从外部根读取；模型/原视频实体按用户要求不追查。angular acceleration无历史默认，本轮不纳入必交付。

main Phase5.6 AC-9未达到改善目标的历史缺口不受影响；main历史804 tests不能冒称本轮运行结果。P0.1无GUI增量，不触发GUI Human Review。

## P0.1 Review / integration

Independent Scientific Review已完成：F1–F4修复并独立复审关闭，最终PASS、无未关闭blocking finding。具体处置与验证见review record。未改Accepted ADR；没有引入依赖、产品代码、runtime或数据schema迁移。

## P1.1 progress (2026-09-21)

- 分支 `feat/p1.1-pendulum-setup`,三个实现 commit:`c7e3dd0`(S1–S4 主体)、`0d0970b`(R1 guard 专项修复)、`d999ad7`(R2 schema 专项修复)。未合并回 publication 集成分支、未 push。
- S1:schema v1/v2 双格式 serializer/repository(按 `required_capabilities` 分派;v1 路径纯净性经字节级对照)、`domain/pendulum.py`、`domain/scientific_result.py`(envelope 验证+无损保存,无 producer)、多成员 `TrackingRun`。
- S2:`save_as_publication` 显式迁移(source manifest SHA、staging/回滚、源零改动经 8 类故障注入)。
- S3:experiment create/rebind/delete 事务、旧单轨 AI mutator/prepare/注册全 guard、calibration→结果 stale、undo/redo 快照扩至 publication 集合。
- S4:geometry/physical/release 动作(revision、确认撤销、stale);`application/pendulum_setup.py` 投影与依赖 digest。
- Review:[publication-p1.1-review.md](../docs/reviews/publication-p1.1-review.md)——R1(legacy bypass)G1–G7 与 R2(schema/migration)F1–F7 全部 CLOSED(除 G6 有意保守);G3 处置调整为 session 层 guard 以保留迁移 legacy run 历史。
- 验证:全量 **899 passed, 9 subtests** + `compileall`;S5 GUI 挂载点勘探完成(File 菜单 specs、workflow 投影分支、video_view 点选模式、guide 复用)。
- 测试命令(macOS):`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest`(本 worktree 无独立 venv,借用主 worktree 解释器 + PYTHONPATH 指向本树)。

## P1.2 progress (2026-09-23)

- 分支 `feat/p1.2-complete-frame-annotation`;执行 mini-plan [p1.2-complete-frame-annotation-execution.md](plans/p1.2-complete-frame-annotation-execution.md)(Context Pack 勘探完成,exporter 首列缺陷定位 `dlc_adapter.py:197-204`,其固化断言 `test_dlc_adapter.py:481` 待 S5 重写)。
- **S1 完成**(`1a1886e`+`e321f96`):ExperimentFrameSet 域对象、v2 serializer 无损通道(P1.1 manifest 兼容)、session set/clear 动作;独立 review FS1–FS5 已修复闭环(working_zone 内容校验、serializer fail-closed、死代码、mini-plan 同步)。
- **S2 完成**(`daf535a`):`application/annotation_join.py` 纯函数——同帧 4/4 join(complete/partial/superseded-only/AI-only/non-finite 分类,AI 永不补位,duplicate 防御)+ canonical label digest(坐标/point_id/frame 敏感,显示属性无关)。
- **identity 专项 review PASS**(5 项 Low/Info:ID1 partial 帧坐标损坏诊断、ID2 ROLE_ORDER 复用、ID3 defense-in-depth 文档、ID5 补 role 重绑/残留测试)——已全部修复复测,最终全量 **948 passed**。S3(引导标注 UI,含 selection owner experiment 化)/S4(共享 fixed-check)/S5(四 bodypart exporter)/S6(DLC smoke)未开始。

## P1.3 progress (2026-09-25)

- 执行 mini-plan:[p1.3-joint-training-execution.md](plans/p1.3-joint-training-execution.md)(S1 external runner → S2 joint request → S3 model reference+review gate → S4 teacher import → S5 self-test → S6 GUI/closure);分支 `feat/p1.3-joint-training` 自 `3f06de9` 切出。
- 依赖就绪:join/digest/exporter/split(P1.2)、multi-member run 与 guard(P1.1)、spike Protocol v1 证据(P0.3);test1 帧集 10/10 全 4/4 可作真实 DLC smoke 输入。
- CI 触发已扩展到 `publication/**`(用户批准,`787b169`)。
- **S1 完成(`a7dcd35`,2026-09-25)**:product external worker——`worker/__main__.py`(受信操作白名单 hello/wait/fail/selftest_runtime、源 SHA 自验、原子 result)+ `infrastructure/external_worker.py`(canonical digest 链、env 白名单、协作/强制整组取消、fail-closed read_result:身份/exit/时间戳/outputs containment+SHA、迟到结果拒绝)。Flash 实现 + 只读 review(request-changes)→ M1–M4/m1–m5 全部修复复测(取消路径 fail-open 收口、result 时间戳、负例补齐 10 个)。**1015 passed, 9 subtests**(基线 987 + 28)。i3–i6 交接项记入 mini-plan S2 节。
- **S2 完成(2026-09-28,主会话直实现)**:subagent 模型路由诊断结论=客户端启动时快照,需用户重启 ZCode 后生效(重启前不派 subagent,避免占用个人套餐 Flash);S2 由主会话实现——`application/experiment_training_job.py`(prepare 唯一路径 EX4+全量 digest 冻结+active-task 守卫;verifier digest 回显/stale 复核/bodyparts/输出 containment)+ worker `train_experiment` 操作(视频 sha 复核、DLC 项目在 job 目录内、协作取消、outputs 声明)。**1027 passed**(+12)。S2 只读 review 待用户重启后与 S3 一起派发。
- **S3 完成(2026-09-28)**:`domain/teacher_model.py`(TeacherModelReference + ModelManifestEntry,构造期校验:origin/manifest 一致性/路径封堵/四 role mapping/compatible 需证据)+ Project `model_references` 集合(v2 serializer 双向,旧 payload 无键读空)+ session `register_trained_model_reference`(completed 联合 run 校验、逐文件 size/SHA 冻结、undoable、重复注册拒绝;快照/transition 扩第 10 元素)+ `application/teacher_models.teacher_model_availability`(missing/size/SHA → unavailable)。**1044 passed**(+17)。S1–S3 Independent Review 已完成(2026-09-28,用户裁定走个人套餐直接派发):request-changes → B1(联合训练 bodypart 守卫,真实链路必炸)+M1–M3+m1–m7+Nit 全部处置闭环,新增回归 10 个,**1054 passed**;记录 [publication-p1.3-review.md](../docs/reviews/publication-p1.3-review.md)。gate 通过。
- **S4 完成(2026-09-28)**:`application/teacher_import.py`(safe YAML/身份 fail-closed 清单/兄弟 staging 原子发布/路径重写+provenance)+ session `import_teacher_model`(undoable,OSError 包装);slice review request-changes(M1 bodyparts 重复放行/M2 同名冲突测试缺口 + m1–m4)全部处置闭环。**1077 passed**(+23)。
- **S5 完成(2026-09-28)**:worker `selftest_model`(sha 三重复核、单帧解码、DLC 推理经 adapter 下沉、bottom-up 输出结构校验)+ `teacher_models` 编排(payload 构造/evidence 冻结含 pose_cfg sha/组合入口 model_effective_state)+ session `apply_model_selftest`/`mark_model_incompatible`(状态机转移已声明,undoable)。slice review 抓到双 Blocker(trained pose_cfg 用 TF 布局恒 None;runner 输出键是输出名非 bodypart 名——均对照安装的 DLC 源码核实)全部修复。**1097 passed**(+20,含真实 worker 进程的协议级测试)。

## Next Recommended Action

**P2收尾后停止，等待用户授权进入P3。届时先核对集成分支/status，阅读P3 requirements、master plan与相关profile/IC契约，并在每个subphase进入前建立mini-plan。本次未开始P3规划或实现。**

## P2.1 delivery (2026-09-30)

- Qt-free signed θ、分段 φ、共同 QC+原因、body median 支持集、relative weights、fixed/tracked pivot 分离及 input digest。
- 显式 QC exclusions：domain/codec/session/revision/stale/Undo/保存重开；旧 schema2 缺字段取空集。
- snapshot 消费强制 current assert；数值摘要统一 float64 语义，修复整数坐标/vertical重开差异。
- 定向91、全量1187 tests/9 subtests，冻结 evidence verifier通过；[Independent Review](../docs/reviews/publication-p2.1-review.md) 两项 Closed，最终 approve。没有新增 GUI；P2.2/P2.3 待实现。

## P2.2 delivery (2026-09-30)

- 直接 SG9/3、源帧缺口/short/nonuniform/edge、独立 extrema、分段 crossing/period/tail、同源 phase matching；Qt-free adapter。
- P011/P014 ω1e−8、P011213 extrema精确一致、tail period1e−8/q1e−7；20定向、全量1207 tests/9 subtests。
- [Independent Review](../docs/reviews/publication-p2.2-review.md) 发现零平台伪周期及provenance顺序，修复复审approve。旧科研只读、golden未改。

## P2.3 delivery checkpoint (2026-09-30)

- reference energy q=g/L s⁻² proxy、typed immutable JSON、多输入signature/外部SHA与提交stat代际、后台cancel/late guard、Save As/重开；四个scalar/phase页与准确源帧检查（不改working zone）。
- [mini-plan](plans/p2.3-energy-analysis-ui.md)已在实施前建立；[Independent Review](../docs/reviews/publication-p2.3-review.md)两项Closed，复审Approve。Human Review尚未通过；本branch为交付checkpoint，不代表P2.3/P2关闭。

- 最终验证：**1218 passed, 9 subtests passed**；13 review-fix定向；frozen evidence verifier与diff check通过。macOS共用main `.venv`，无需新依赖。按mini-plan启动命令测试后回复Q1–Q3（通过/需调整）；当前工作分支提交并推送，publication集成分支仍停在P2.2 `4ec09b6`。


## P2.3 Human Review feedback checkpoint (2026-09-30)

- 侧栏radius按钮改两行；模型选择与训练历史含完整本地日期时间/秒与短UUID；模型列表最新优先，trained使用来源run开始时间。
- 未验证模型支持Verify & run：复用真实external selftest，成功后在原session/experiment自动推理；失败/取消/证据拒绝/换项目/关闭均不续跑。今后联合训练完成自动自检。
- 用户test2_pendulum今天10:59/12:01/12:52三次训练成功，train帧11→26→41，标注digest变化。三个trained模型真实单帧selftest全部success、内存验证compatible；用户manifest未写。此前无自检证据且chooser无入口导致新模型无法使用。
- 验证：38定向；全量 **1226 tests/9 subtests**；evidence15/48/2与diff check通过。补充Independent Review Approve（独立GUI38/worker-core71，零开放finding）；Q4/Q5用户确认通过；Human Review主线Q1–Q3反馈待修复复测，保持当前开发分支不集成/P2未关闭。
- 下一步：补充审查已通过；用户重启并打开test2_pendulum，Q4/Q5已获用户确认通过；继续原分析页Q1–Q3主线亲自验收；通过后才--no-ff集成、push与P2收尾。


## P2.3 HR主线反馈（2026-09-30）

- 用户确认上一轮Q4/Q5全部通过；报告Angle只有部分点、其他图空且坐标范围异常。对应payload133θ有限/42共同QC/最长5<SG9，ω/energy0；非数据丢失。旧run71c2c8ef仍adopted，最新34de7208未采用；detached模拟替换仍42/5/0，最新tip/body_bottom/pivot均0/148达到0.6阈值。因此不能仅靠采用新模型或放宽SG来造出可靠曲线。
- 修复：Angle蓝色QC点+灰色排除几何预览可点回源帧；empty隐藏坐标轴并呈现具体原因/缺role数/最长段与最少QC缺项的9帧例子（当前11–19，检查12–15）；未改科学计算或写用户项目。联合candidate预览修复默认target错误，按run冻结bodypart及role缓存身份读取。
- 19 GUI定向、全量1228 tests/9 subtests通过；最后display建议4定向通过；补充只读审查Approve（独立GUI21/契约104，零开放finding）。当前branch未集成；Q6及原Q2/Q3待真人，P2未关闭。
- 下一步：审查通过，checkpoint提交并push；用户保存/重启/重新计算，检查灰叉源帧与三页不可用提示，必要时重标12–15四点以先得到11–19连续段的局部图，再确认stale/保存重开。模型质量改善需以新的跟踪验证结果为证据，不能把training完成当精度已通过。


## P2.3 HR：建议帧直接四点修复（2026-09-30）

- 用户再次操作后，active run已换be47b1fc（latest trained d8b6cb6e、阈值0.4），42共同QC/最长5仍未变。最新typed结果中12帧缺pivot，13–15缺body_bottom/pivot；tip有限、半径正常也不满足完整四点QC。截图tip96含未保存变化，manifest20:50仅94；诊断只读，无覆盖用户项目。
- 新入口Repair suggested frames显示确切帧号，复用MainWindow四role引导和既有mark_point事务；每帧重标全部四点、自动下一帧、目标帧未呈现时禁止点击，完成返回分析页供重算；Esc/换项目清空临时任务，已写manual保留。分析视频只读，不能再按选中tip静默写点；旧结果/区间改变/输入变化拒绝启动建议。
- 联合采用以experiment.active_infer_run_id为真值；同一run不再被单轨状态画成“not adopted”的raw preview，头部明确Joint analysis source。未改科学共同QC、SG9/3、confidence阈值或保存格式，也未自动采用新候选。
- 验证：45 GUI定向、全量1230 tests/9 subtests；随后仅清除分析页calibration mode/修正文案，38 annotation/setup/workflow定向通过。合成数据四点修复后ω/phase/energy恢复；真实用户重标精度仍需真人检查。Independent Review首轮P2 joint Correct工作区切换回归已修复，41定向通过，复审Approve（32独立定向、零开放finding）；仍保持P2.3工作分支等待Human Review。

本轮修复checkpoint `6ca7f05`，文档同步后推送当前P2.3分支；publication集成分支仍停P2.2，待真人HR通过再集成。


## P2.3 用户纠正：tip + fixed pivot（2026-09-30，当前规则）

- 前轮四点共同QC/补辅助点不符合用户明确用途。按用户指令发布student-default-v2，tip source/radius/人工排除决定θ/ω/phase/period/energy mask；辅助问题独立auxiliary_qc_reasons，body参考只要求有效body pair，不作角运动门槛。SG9/3、时间/缺口与能量公式不改；v1/legacy与golden字节保留。
- 重建与scalar bundle core2.0及profile SHA写入签名，旧结果显示stale，必须重算。Repair建议改为tip-only一点击下一帧；训练四点流程保留。决定见[ADR-0018](../docs/decisions/0018-tip-fixed-pivot-angular-qc.md)、scientific-profiles §8。
- 最新实际payload4b128602只读重建：旧QC42→48、最长5→9、ω/energy0→各9，无用户文件写入；其余tip缺测/半径异常保留。
- 验证87定向/3subtests，全量1233 tests/9subtests；profile文字/SHA/verifier及source bar补充后79定向/3subtests+evidence15/48/2通过，scalar core version升级14 analysis/UI通过。Independent Review F1/P2已关闭，复审Approve（独立14 evidence/3subtests、75 core/UI/stale）；最终主会话53/3subtests与evidence通过，仍待用户Q8新版tip分析与原Q2/Q3导航/stale/保存重开真人反馈。

代码checkpoint `869e504`；五小时额度剩余5%时已写[简单交接](plans/p2.3-handoff-2026-09-30.md)。待用户Human Review，勿提前集成或进入P3。


## P2.3 HR：可调SG（2026-10-01）

- test1有66/112有效角度、最长连续8帧，默认SG9/3阻断全部ω。用户授权自定义SG，见ADR-0019与scientific-profiles §9；同一分段直接SG核心支持显式奇数窗口/阶数，默认9/3与frozen profiles不变，legacy不接受override。
- UI提供9/3、7/3、5/2快捷与自定义、预计覆盖/窗时间跨度/噪声取舍、实际图参数/edge数；参数随digest/job/immutable结果保存，重开恢复；改变设置需Compute、旧图保持旧设置，设置代际迟到拒收，repair按保存窗口并拒绝未应用设置。
- test1最新a2d4bb43只读重算：9/3 ω/energy0；7/3各15；5/2各32；3/1各39。周期/tail仍0，未跨gap构造周期；未写用户manifest或derived。
- 全量1249 tests/9subtests、evidence15/48/2与diff通过；Independent Review首轮F1/P1完整配置来源读回、F2/P2历史参数恢复均修复并复审Approve（独立51项），最终主会话65定向/3subtests通过。Q9新版SG与原Q2/Q3真人反馈前不集成、不关闭P2、不进入P3。

本轮代码checkpoint `01a8f87`，工作分支推送后等待Q9真人验收；publication集成分支仍停P2.2。


## P2 closeout（2026-10-01）

- P2.3 Human Review：用户确认图已出现、当前增量可交付并明确授权收尾；图表外观一般列为非阻断事项。未虚构历史Q2/Q3逐题现场实测，已有自动化/独立审查覆盖。
- P2.3 8条AC与P2最终验收矩阵已核对勾选；所有Independent Review finding Closed，最后Approve。最终全量1251 tests/9subtests（80.80s）、evidence15/48/2、diff通过。
- 集成：P2.3文档收尾 `97ce664`，--no-ff merge `99f34b0`（parents `4ec09b6` + `97ce664`）；集成回publication，main通用产品线未被本次P2收尾修改。
- 同时另一会话已同步Windows取消修复（见下）；补充47项task_runner/external_worker/pendulum_analysis通过。无P2额外数值改动、无用户项目写入。
- 下一步：停止，等待用户授权P3；进入每个subphase前建立mini-plan。运行与体验步骤见[P2.3交付计划](plans/p2.3-energy-analysis-ui.md)。

## Relevant Source Commits — Windows cancellation sync

另一活跃会话针对用户的Windows CI报错，在main侧先修复并受控同步；本轮收尾核查其来源，不重复实施：

| main source | publication commit | 为什么论文需要 / 本线验证 |
| --- | --- | --- |
| bf8f0c5 | 4d4e3e9 | 共用TaskHandle强杀后的退出回收；初版有界异常方案随后被下一提交替代 |
| 8a7d90d | 6323e11 | 最终kill后native join，保留原取消接口；避免Windows退出异步导致取消后仍存活。代码与测试字节和main source一致；本线47项task/external-worker/analysis通过 |

main复审记录位于source `842460c:docs/reviews/task-cancel-windows-review.md`，最终Approve、两项Closed。最终Windows/macOS远程CI由该修复会话继续确认；本记录不把待完成的远程运行写成通过，不影响用户已接受的P2交付。
