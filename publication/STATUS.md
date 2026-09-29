# Publication Status — EJP Undergraduate Pendulum Platform

- 最后更新：2026-09-29。
- Worktree：`ai-physics-tracker-ejp`；integration branch：`publication/ejp-damped-pendulum`。当前开发分支 `feat/p1.4-joint-inference-activation`，自已推送的 P1.3 集成提交 `0546ff7` 切出。
- 当前：**P1.4 S1 联合推理 core 已实现，S2 审核/QC 待执行**：[执行 mini-plan](plans/p1.4-joint-inference-activation-execution.md)。四 role parser、请求冻结、external worker 和 host candidate 验证已落地；自训/导入模型分别完成 Mac CPU 十帧真实 DLC smoke（见 [证据](evidence/runtime/p14-joint-inference-smoke.json)）。P1.3 已完成并合并（2026-09-29，HR 通过；1117 tests）。P1.1–P1.3 已合并；P2 未开始。
- P0已完成且Independent Review PASS；Windows G1–G4经用户明确批准延期至P6之前，证据仍not_run。**P1.1–P1.3已完成，P1.4执行中；P2–P6未开始**；main通用线状态仍在[docs/status/current.md](../docs/status/current.md)。本线科学开发不等待main Phase6。

## P1 planning

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

**执行 [P1.4 mini-plan](plans/p1.4-joint-inference-activation-execution.md) S2：experiment 级逐帧/逐 role 审核与 measurement-integrity QC；随后 S3 四轨原子事务与 Independent Review。** S4/S6 GUI Human Review 和 S5 科学语义 review 按计划执行；P1 完成后停止，不启动 P2。Windows G1–G4 仍是 P6 前门禁。
