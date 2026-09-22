# P1 Mini-plan — Four-Landmark Pendulum Measurement

- 日期：2026-09-20
- 状态：**Planned；implementation not started**
- 集成分支：`publication/ejp-damped-pendulum`
- 实施分支：每个 Subphase 单独使用 `feat/p1.<n>-<topic>`，完成 review 后 `--no-ff` 合并回 publication 集成分支
- 前置基线：P0 已完成；ADR-0017 已接受；Windows runtime G1–G4 经用户批准延期，但进入 P6 前必须完成

本计划只定义 P1 的实施顺序、验收和 review gate，不表示 schema v2、PendulumExperiment、多 bodypart DLC 或四轨事务已经存在。当前产品实现仍是 schema v1、单 Track `TrackingRun.track_id`、单 bodypart `target` 与单轨 activation。

## 1. Goal and completion boundary

P1 完成后，学生能从自己的 CFR 视频建立一个 Pendulum experiment，保存固定几何和 release 事实，在同一批帧上完成四个 landmark 的人工标注，训练一个四 bodypart DLC 模型或导入教师模型，执行一次联合推理，审核结果，并以一个可撤销事务采用四条轨迹。

```text
Pendulum experiment
→ fixed pivot / downward true vertical / scale / L / release
→ shared representative frames
→ 4/4 manual labels per complete frame
→ one four-bodypart DLC training OR imported teacher model
→ one joint inference candidate
→ review / manual correction / QC
→ atomic four-track Activate / Replace / Clear / Undo
→ stable adopted measurement for P2
```

P1 不计算 θ、period、energy 或 ODE fit；不建设通用 multi-object identity、任意 skeleton、跨视频标签库、正式 runtime installer 或首发打包。tracked `pivot` 只提供 QC 观测，P2 仍以 `fixed_pivot_px` 和确认过的 true vertical 重建 θ。

## 2. Baseline: reuse and actual gaps

| Area | Existing reusable capability | P1 gap |
| --- | --- | --- |
| Project persistence | 单 manifest、unknown field round-trip、atomic save/backup、staging Save As、外部视频 locator | schema v2 dispatch、required capabilities、typed publication collections、v1→v2 explicit Save As |
| Measurement data | `Track` = physical point；manual last-wins；AI superseded by manual；frame/time provenance | `PendulumExperiment` 与 stable role→Track UUID；experiment revision/history |
| Geometry | `Calibration`、active calibration、scale/origin/rotation、标定 UI | fixed pivot、true vertical direction confirmation、physical L/g、release frame、实验级 stale |
| Annotation | 点击落点、representative frame selection、working zone、保存重开 | shared frame set、逐帧四 role 引导、4/4 completeness、experiment-level fixed-check |
| DLC dataset | 新 per-run project、frame PNG、CSV/HDF5、fixed split | exporter 当前只填第一个 bodypart；需一帧一行 8 坐标并拒绝 3/4 frame |
| Training/inference | DLC 3.x adapter、task lifecycle、run artifacts、cancel/log、candidate 不自动激活 | multi-member run/request/result、一次四 bodypart train/infer、外置 Python worker 产品边界 |
| Model provenance | completed train run + checkpoint/config references | `TeacherModelReference`、安全复制/manifest/bodypart mapping/runtime self-test |
| Review | raw likelihood、difficult-frame mining、Accept/Correct/Skip、run-scoped review state | frame-level four-role prediction/QC、role-aware correction、joint run ownership |
| Activation | candidate/active 分离；单轨 Activate/Replace/Clear/Undo；manual preserved | 四轨一个事务；experiment 为唯一 active truth；旧单轨写入口 guard |
| Workflow | Qt-free projection 与 task cards | experiment-level projection，不能从 Track 名称或四个独立单轨状态推断 |

最小架构方向保持不变：四个普通 `Track` 分别存四种物理点；一个 experiment 聚合 role identity，一个 run 同时消费四个 member Track。P1 不新增 object/individual identity 层。

## 3. Cross-subphase architecture contracts

### 3.1 Authority and ownership

| Fact | Single source of truth |
| --- | --- |
| role identity | `PendulumExperiment.roles` 的 role→Track UUID；Track 显示名可改，不参与语义 |
| scale | 既有 `active_calibration_by_video`；experiment 只解析并在 run 中冻结快照 |
| fixed pivot / vertical / L / g / release | `PendulumExperiment` typed fields |
| representative/fixed-check frame membership | experiment-level frame sets；不复制成四份 per-track state |
| manual landmarks | 既有 `TrackPoint(source="manual")`，按 role binding join |
| candidate prediction | immutable joint infer run artifact；完成不等于 active |
| adopted AI result | `PendulumExperiment.active_infer_run_id`；bound Track 的 legacy refinement pointer 不权威且不得写入 |
| review progress | joint infer run-scoped review state |
| downstream validity | experiment `measurement_revision` + canonical component digests |

### 3.2 Domain and persistence shape

- schema v1 generic project 继续以当前行为读写；schema v2 publication project 才拥有 `required_capabilities` 和 typed `publication` collections。
- `Project`/serializer 必须能区分当前项目应写 v1 还是 v2。禁止靠 `extra_fields` 偷存 active experiment 语义；也不能把所有 v1 项目打开后自动升级。
- v2 中实现 P1 当前需要的 `experiments`、`model_references` 与多成员 `tracking_runs`。因为ADR-0017已经固定`scientific-results-v1`为required capability，P1.1还必须实现P0.2定义的result envelope/load validation与无损保存，不能声称理解该capability却只接受空map；P1不创建θ/fit payload，也不实现P2–P4算法。
- `TrackingRun` 领域表示改为 `member_track_ids`，Pendulum run 另有 `experiment_id` 和完整 `role_bindings` snapshot。generic/legacy run 只有一个 member；可提供只对单 member 合法的兼容访问器，不能让多成员 run 被旧代码静默当成某一条 Track。
- publication collection 的 JSON map key 必须等于对象自身 ID；所有 cross-reference、same-video、role completeness、path containment 和 required capability 在 load/save 两侧 fail closed。

### 3.3 Transaction boundary

四轨修改使用现有 frozen `Project` + `TrackStore` candidate + `_commit_project`/session snapshot，不引入第二套事务框架。Activate/Replace/Clear 构造完整 candidate 后只提交一次，因此 Undo/Redo 恢复 observations、experiment pointer、history、revision 和 stale state 的同一个快照。

所有 experiment-bound Track 的旧单轨 AI 写入口在应用层统一 guard：

- `import_engine_points`
- `activate_infer_run`
- `replace_active_infer_run`
- `clear_active_ai_observations`
- 旧 single-track inference prepare/import 路径
- 任何直接按 `track_id` 重建 AI projection 的 UI action

这些入口要么明确拒绝并提示使用 Pendulum workflow，要么路由到完整 experiment 事务；不能逐 role 循环调用四次。generic unbound Track 继续执行现有代码和回归测试。

### 3.4 External worker boundary in P1

P0.3 的 `scripts/publication_runtime_spike/` 只提供证据，不直接成为产品模块。P1.3 将其已验证的协议约束收敛为最小产品 runner：

- host/app 负责准备 request、启动可信 worker、显示进度、取消和最终 candidate 交付；
- external Python worker 只执行 DLC adapter 操作并写 run-owned staging/artifacts；
- request/result 使用 JSON 与文件，含 protocol/job/input digest、worker/runtime identity、device、status、输出 size/SHA256；不用 pickle；
- worker 不持有活动 `ProjectSession`，不写 `project.json`；
- application 在主线程按 capture digest 复核，成功后才登记 completed run；cancel/timeout/late success 不能提交；
- P1 只支持由开发/高级设置提供的已有兼容 runtime 路径以及 actionable “runtime unavailable”错误。环境下载、repair、GPU wheel selection、签名和 first-run wizard 留给 P6。

generic single-track task runner在P1期间保持兼容；新 Pendulum joint train/infer 必须走 external worker。是否在以后统一两条 runner 路径，等 P1 证据稳定后再决定，不作为本 Phase 的重构任务。

### 3.5 Review cadence

每个 Subphase 单独建立 `docs/reviews/publication-p1.<n>-review.md`。高风险核心在接 GUI 前先做一次 fresh-context read-only review；Subphase 收尾复审同一记录中的 findings。这样 schema/事务/协议错误不会等到 P1.4 才暴露。

每个 Subphase 的 GUI 增量在自动化测试通过后发起 Human Review，停止等待用户反馈；通过后才完成 review、集成与状态更新。

## 4. Dependency and implementation order

```text
P1.1 schema v2 + experiment/setup + legacy write guards
  ↓
P1.2 shared frames + 4/4 annotation + joint exporter/fixed-check
  ↓
P1.3 external worker product boundary + joint train + teacher import
  ↓
P1.4 joint infer + review/QC + atomic four-track activation
  ↓
P2 adopted four-landmark measurement request
```

保留 Master Plan 的 P1.1–P1.4 边界。调整内部依赖的唯一说明是：四 bodypart exporter 在 P1.2 完成，因为 4/4 join 和共同 split 是 annotation contract 的验收对象；P1.3 只消费已验证 exporter 来训练。external worker 的产品化放在 P1.3 第一个 AI slice，P1.1/P1.2 的纯数据和 GUI 不依赖 AI runtime。

## 5. P1.1 — Pendulum setup

### Goal

能从新项目直接创建 schema v2 Pendulum experiment，或把 v1 项目通过明确 Save As 迁移副本后创建；四个 role 稳定绑定到同视频四个 Track，并保存 fixed pivot、downward true vertical、active scale、physical L/g 和 manual release frame。原 v1 目录不改变。

### Context Pack

- `publication/spec/experiment-run-derived-contracts.md` §§1–2、5–6、8
- `docs/decisions/0017-publication-project-contract.md`
- `docs/reviews/publication-p0.2-review.md`
- `docs/spec/data-model.md`、`docs/spec/project-format.md`
- `src/ai_physics_tracker/domain/project.py`
- `src/ai_physics_tracker/domain/tracking_run.py`
- `src/ai_physics_tracker/infrastructure/project_serializer.py`
- `src/ai_physics_tracker/infrastructure/project_repository.py`
- `src/ai_physics_tracker/application/project_session.py`
- `src/ai_physics_tracker/gui/project_actions.py`
- `src/ai_physics_tracker/gui/main_window.py`
- `src/ai_physics_tracker/gui/calibration_dialog.py`

### Scope

做：

- schema v1/v2 双格式读取与按项目格式写回；required capability validation；typed P1 publication collections；scientific result envelope的验证/无损保存（无P1 producer）。
- explicit Save As publication migration，复制可移动资产、保留 UUID/unknown siblings，记录源 manifest SHA 与 schema。
- `PendulumExperiment`、四 role binding、measurement/binding revision/history、setup completeness projection。
- 创建或由用户显式选择四个同视频 Track；默认显示名可用 role，但 identity 只看 UUID mapping。
- fixed pivot、true vertical top→bottom confirmation、physical L/g provenance、release frame；复用 existing Calibration。
- experiment-bound Track 的所有 legacy single-track AI mutator guard。
- setup UI 与 workflow task card。

不做：

- representative frames、DLC dataset/train/infer、teacher model、θ reconstruction。
- 自动从 Track 名称猜 role、从 tracked pivot 推 fixed pivot、从 tip radius 推 L、从画面方向猜重力向下。
- v2→v1 downgrade、原目录原地升级、科学结果 payload。

### Main design decisions

1. **Save As 是转换事务**：UI 收集 destination 与完整四 role draft；application 构造 v2 candidate，repository 在 sibling staging 中复制源项目并写 v2 manifest，rename 成功后才切换 session。任何失败保持当前 v1 session/root/manifest/backup 不变。
2. **新空项目也直接写 v2**：用户选择 Pendulum experiment 时，以 v2 首存；普通 generic 项目仍写 v1。
3. **roles 一次提交**：普通模式不保存部分 binding。setup wizard 中可暂存未完成选择，但 domain commit 必须恰好四个 distinct same-video Track。
4. **display name 非语义**：允许改名；role badge、workflow 和 request 全从 experiment mapping 解析。
5. **vertical direction 是事实**：用户按 top→bottom 顺序确认“down”；端点 digest 变化即撤销确认。`rotation_deg` 不覆盖 true vertical。
6. **L 与 scale 分开**：active Calibration 提供 px↔unit；physical `length_m` 是明确的 pivot-to-COM 输入和来源，不从任意像素半径暗算。
7. **release 可后补**：setup incomplete 允许保存；release null 时 P1 标注/训练可继续，但 P2 分析入口保持 disabled。Set release frame 写当前 source frame，不做 −1 调整。

### Slices and dependencies

1. **P1.1-S1 — v2 domain/serializer skeleton**：加入 typed experiment/geometry/physical/history、multi-member run表达、scientific result envelope与cross-reference validation；实现v1/v2 serializer dispatch、unknown optional preservation、future/unknown capability rejection。先完成domain/serializer tests；不实现任何scientific result计算或GUI。
2. **P1.1-S2 — Save As migration service**：在 repository/application 边界实现 v1→v2 publish-to-new-directory，记录 source manifest SHA；覆盖 copy/staging/rollback/Unicode/Windows-safe path。不得在 `load()` 中自动迁移。
3. **P1.1-S3 — experiment/session invariants and guards**：创建/bind/rebind/delete policy、revision/history、active calibration resolution、setup completeness；统一拦截 bound Track 的 legacy single-track AI writes。到此发起一次 data/compatibility Independent Review，关闭 blocking findings 后再接 GUI。
4. **P1.1-S4 — geometry/release application actions**：纯应用动作保存 fixed pivot、directed vertical、L/g/provenance 和 release；每次修改正确增加 revision、撤销相关确认、标记 dependency stale；Undo/Redo 为完整动作。
5. **P1.1-S5 — setup GUI/workflow projection**：Pendulum creation/Save As wizard、四 role picker/create、视频上的 pivot/vertical 操作、L/g/release controls、setup checklist/task card。复用 calibration UI，不另建 scale truth。
6. **P1.1-S6 — integrated save/reopen and review**：offscreen GUI、full regression、migration failure probes、Human Review、Independent re-review，更新状态并集成。

S1→S2→S3 是硬依赖；S4 依赖 S3；S5 只消费 S2–S4 的 application API；S6 最后。

### Acceptance Criteria

- [ ] v1 项目仍按 v1 保存；打开/保存不产生 publication objects 或 schema bump。
- [ ] v1→v2 只通过明确 Save As；成功后源 `project.json`/backup/asset bytes 不变，目标保留 UUID 和 unknown optional fields；任一失败不切换活动 session。
- [ ] v2 reader拒绝 unknown required capability、future schema、collection key/id mismatch、dangling/cross-video references；能验证并无损保存合法`scientific-results-v1` envelope但P1不创建科学结果；旧版 reader 继续明确拒绝 v2。
- [ ] 一个 video 最多一个普通 Pendulum experiment；roles 恰好为四个规范 key、四个 distinct same-video Track UUID；重命名 Track 不改变 role。
- [ ] role rebind 一次提交完整 old/new snapshot/revision，清除旧 joint active projection并保留 manual；partial binding 不能进入 domain。
- [ ] fixed pivot、vertical direction confirmation、L/g、release 的 finite/range/provenance 校验与 null/incomplete 状态准确；tracked pivot 不写入 fixed pivot。
- [ ] active calibration 被编辑、切换或删除时 setup projection/digest/stale 正确，且不会静默选择另一 Calibration。
- [ ] 对 bound Track 调用每一个旧单轨 AI mutator都 fail closed 且 Project/TrackStore/undo history不变；unbound Track 的现有行为不退化。
- [ ] Save/reopen 后 experiment、roles、geometry、physical、release、history、revision 与 format identity 一致；Undo/Redo 不产生悬空引用。

### Automated tests

- domain table tests：role key/order/uniqueness/same-video、finite/range、direction digest、release bounds、L/g provenance。
- serializer mutation tests：v1/v2 round-trip、unknown fields、key/id、required capability、future schema、paths、legacy run→single member。
- repository fault injection：copy/write/replace失败，源 manifest/hash/backup不变，staging 路径可诊断。
- session tests：bind/rebind、calibration edits、release changes、revision/stale、delete guards、all legacy single-track mutators on bound/unbound Tracks。
- GUI offscreen：wizard cancel/success、incomplete setup、vertical re-confirm、release current-frame semantics、save/reopen projection。
- 全量 `pytest` 与现有 schema v1 regression。

### Real DLC verification

无。P1.1 不应启动 DLC；用 Mock/既有 completed run fixture 只验证 guard，不冒充 AI 验收。

### Human Review

自动化全绿后，用户从一个已有 v1 项目执行 Create Pendulum experiment → Save As → bind/create four roles → scale/fixed pivot/vertical/L/release → save/reopen；确认源项目仍可独立打开、方向提示明确、setup checklist 不误导。未通过前停止 P1.1 集成。

### Independent Review gate

- S3 后：schema/migration/cross-reference/data-loss/legacy bypass 专项 review。
- S6：复审全部 findings，并审查 GUI 只调用 application API、没有第二套 role/setup truth。
- Blocking findings 必须在 P1.1 关闭；不能留到四轨 activation 才修 schema。

### Risks and failure recovery

- 最大风险是 v1 保存路径被全局 schema bump。恢复策略是双 writer regression + 原目录 byte/hash probes。
- 迁移复制大型 assets 中断时保留明确 staging recovery path；活动 session仍指向 source，不自动删除或继续半成品。
- Track 删除/rebind 若破坏引用，操作必须先校验整个 candidate；失败不提交。
- calibration/vertical 含义混淆时宁可保持 setup incomplete，不自动推断。

### Completion documentation

- 更新 `publication/STATUS.md`、本计划 Result、`docs/status/current.md` publication banner。
- 新增/更新 `docs/reviews/publication-p1.1-review.md` 与索引。
- 若实现必须推翻 ADR-0017 才新增 superseding ADR；按本计划实现不新增 ADR。
- 架构文件只记录已实现的 v2/experiment boundary，不能提前写 P1.2–P1.4 已完成。

## 6. P1.2 — Complete-frame annotation

### Goal

一个 Pendulum experiment 拥有共享 representative frame set；学生在每个 frame 依次标注 tip/body_top/body_bottom/pivot，只有同一 source frame 的 4/4 active manual points 才进入完整训练帧和共同 train/fixed-check split。

### Context Pack

- P1.1 merged result、review record、schema v2 fixtures
- `publication/spec/experiment-run-derived-contracts.md` §3
- `publication/spec/scientific-profiles.md` 的 source/missing semantics
- `src/ai_physics_tracker/application/tracking_job.py` frame selection request/result
- `src/ai_physics_tracker/application/project_session.py` manual point/Undo semantics
- `src/ai_physics_tracker/domain/track_store.py`
- `src/ai_physics_tracker/infrastructure/dlc_adapter.py` annotation exporter
- `src/ai_physics_tracker/application/refinement_history.py` fixed validation concepts
- `src/ai_physics_tracker/gui/video_view.py`、`tracking_actions.py`、`fixed_check_dialog.py`

### Scope

做：shared frame selection/persistence、four-role guided annotation、4/4 join/completeness、experiment-level fixed-check membership、joint DLC CSV/HDF5 exporter、save/reopen/Undo continuation。

不做：DLC training、teacher model、推理、基于 body geometry 的 θ/QC mask、跨视频标签合并。

### Main design decisions

1. **frame set 属于 experiment**：帧号与 selection provenance 只存一次；现有 selection algorithm继续按 video/working zone 工作，不从某个 Track 的manual帧推导四点完成度。
2. **partial 是编辑状态，不是训练样本**：退出/保存时允许某帧 0–3 个 manual role；UI 标明 incomplete。Complete/Next 只有 4/4 时可用；训练 join只返回4/4。
3. **manual storage 不变**：每个点击仍生成对应 role Track 的 `TrackPoint`，保留现有 last-wins、source/provenance 和单点修正能力。显示和 join通过 role UUID mapping，不用名字。
4. **共同 fixed-check**：固定检查集合是 frame membership；一个 fixed-check frame 的四个 label共同进入 test，训练帧共同排除。任一 role label改动都使对应 frozen comparison invalid。
5. **exporter 接受 complete rows**：输入是已排序的 `frame → four role TrackPoint` value，不是把四条点列表拼接。每帧只抽一次 PNG，只写一行 8 个坐标；重复/缺role/非finite/跨帧/非manual整体拒绝。

### Slices and dependencies

1. **P1.2-S1 — experiment frame-set model and projection**：持久化 ordered unique frame membership、algorithm/seed/working-zone/video digest；改造现有 selection request owner identity，复用 uniform/K-means worker；save/reopen/cancel/late result tests。
2. **P1.2-S2 — pure 4/4 join/completeness**：按 experiment role binding join active manual points，输出 complete/incomplete/duplicate diagnostics；加入 canonical label snapshot/input digest。先做负例和属性不变量测试。
3. **P1.2-S3 — guided annotation transaction/UI**：四 role 顺序提示和overlay；完成当前帧后跳下一 representative frame；退出保留partial；Undo/Redo、改点、删点、frame/track/video切换均由 session action控制。完成增量 Human Review。
4. **P1.2-S4 — shared fixed-check**：从 complete frames显式确认共同holdout；保存frame membership与四label snapshot；invalid/renew/deactivate语义复用现有validation概念，但不写四份per-track active series。
5. **P1.2-S5 — four-bodypart exporter**：最小扩展 adapter/export protocol，使四 bodypart按规范顺序输出；一帧一次decode，一行八坐标，共同split索引基于导出行顺序。
6. **P1.2-S6 — DLC-format and subphase closure**：用真实 DLC 读取/建四 bodypart dataset，做save/reopen/full regression；Independent Review、最终 Human Review、文档集成。

### Acceptance Criteria

- [ ] representative frame set 与 experiment/video/working-zone/input digest绑定；重复帧、越界、stale/late selection拒绝；保存重开顺序一致。
- [ ] 每个complete training frame恰好包含同一frame_index上的四个active manual points；3/4、AI补点、superseded、nonfinite、跨视频均不计入。
- [ ] role identity只从experiment mapping解析；交换Track显示名不会交换CSV列或UI role。
- [ ] partial frame可保存/恢复但明确显示incomplete；Complete/Next和training eligibility不会误报。
- [ ] fixed-check membership对四role共同生效；split index与导出行顺序一致；修改任一role label使comparison invalid。
- [ ] CSV/HDF5每complete frame一行，列严格为tip/body_top/body_bottom/pivot各x/y；每帧只导出一张PNG；3/4 frame完全不进入dataset。
- [ ] exporter遇到duplicate role/frame、missing mapping、decode failure或foreign video folder时不发布半个dataset。
- [ ] generic unbound single-track representative selection/annotation/export测试继续通过。

### Automated tests

- pure join table tests：0/4到4/4、manual vs AI、superseded、duplicate、role rename、frame ordering。
- label/input digest mutation tests：任一point ID/revision/coordinate、binding、frame set、fixed-check变化都会变digest；UI颜色/名字不改变。
- selection lifecycle：cancel、late result、video/timeline/working-zone改变、save/reopen。
- exporter golden structure：PNG count、MultiIndex headers、8 coordinates、HDF5/CSV一致、共同split、large frame index ordering。
- GUI offscreen：role prompt、partial恢复、Next gate、Undo/Redo、fixed-check dialog、project/video switch。
- 全量 regression，尤其 current single-track annotation、fixed-check 和 representative selection。

### Real DLC verification

必须执行一个小型四 bodypart dataset smoke：从合成短视频与至少一个train frame/一个fixed-check frame生成CSV/HDF5，调用已安装DLC 3.x `create_training_dataset`，验证DLC读取到四个bodyparts和共同split。此处不训练，不声称模型精度。

### Human Review

- S3：代表帧列表→同帧四点引导→partial退出/恢复→Undo/修正→4/4完成的交互。
- S6：共同fixed-check解释与预览；确认学生能分辨“完整训练帧”“未完成帧”“固定检查帧”。

### Independent Review gate

- S2/S5 后做 annotation identity/export/split 专项 review；重点找“只填首列”、按四条点数而非完整帧数统计、display name当role等错误。
- S6 复审并关闭 findings；DLC smoke日志纳入review evidence。

### Risks and failure recovery

- 当前 exporter 虽接受 bodyparts list，却只填第一列，这是最可能的静默科学错误；必须用解析后的表内容和真实DLC dataset双重验证。
- partial edits不能写入run input；prepare时重新join并冻结 point IDs/revisions，不信UI计数。
- frame decode/export失败使用run-owned staging；失败后不留下可被P1.3误用的dataset-ready标记。

### Completion documentation

更新 `publication/STATUS.md`、本计划 Result、review record/index、architecture的shared-frame ownership；记录真实DLC版本/平台/命令/结果，不提交视频或dataset产物。

## 7. P1.3 — Joint training and teacher model import

### Goal

从 P1.2 的complete frames和共同split启动一个四 bodypart训练run，或导入一个受管理的四 bodypart教师模型；两条路径都产生可验证的 `TeacherModelReference`，供P1.4一次联合推理使用。

### Context Pack

- P1.1/P1.2 merged code、review与DLC dataset smoke
- `publication/spec/experiment-run-derived-contracts.md` §§3–4、6
- `publication/spec/runtime-boundary.md`
- `publication/evidence/runtime/README.md` 与 `results.json`
- `docs/reviews/publication-p0.3-review.md`
- `src/ai_physics_tracker/application/training_job.py`
- `src/ai_physics_tracker/application/tracking_job.py`
- `src/ai_physics_tracker/infrastructure/task_runner.py`
- `src/ai_physics_tracker/infrastructure/dlc_adapter.py`
- `src/ai_physics_tracker/infrastructure/engine_adapter.py`
- `scripts/publication_runtime_spike/`（证据参考，不复制为产品代码）

### Scope

做：product external worker protocol/runner、joint training prepare/execute/read、四bodypart DLC validation、trained model reference、teacher bundle import/manifest/static validation/runtime self-test、cancellation/stale/late protection、最小GUI。

不做：下载或安装runtime、model library/version browser、任意脚本执行、multi-animal模型、训练精度目标、joint inference全视频与activation。

### Main design decisions

1. **先生产化执行边界，再训练**：P1.3第一批slice建立trusted worker和request/result validator；joint training不得继续依赖frozen GUI的`sys.executable`。
2. **prepare/read保留在application**：label join、digest、run登记和result验证是产品逻辑；worker只接收序列化请求并调用adapter。Normal/Advanced以后共用同一request。
3. **一个run四members**：bodypart order固定为规范role顺序；run snapshot含experiment ID、role bindings、complete frame label snapshots、共同split、config/seed/runtime request。
4. **训练模型也通过ModelReference消费**：completed train经checkpoint/config/manifest验证后创建`origin=trained` reference，source_train_run_id指回run；P1.4不直接从任意run路径猜模型。
5. **teacher import是copy+validate**：复制必要config/checkpoint/engine files到`models/<model_id>/staging`，safe YAML解析、路径重写、逐文件SHA后atomic publish；不运行老师目录中的Python或hook。
6. **mapping显式**：若外部bodypart名字不是规范四role，用户明确映射；missing/duplicate/extra identity/multi-animal/cropped incompatible config fail closed。显示名相同不自动接受歧义。
7. **compatible需要实际load/infer**：static parse成功仍是unverified；使用当前runtime和一个合法输入做self-test后才compatible，记录实际device/runtime/version/evidence digest。P1.3可用单帧/极短输入，不提前做全视频workflow。

### Slices and dependencies

1. **P1.3-S1 — product external runner**：定义最小trusted operations、versioned JSON schema、new job directory、request/worker/runtime digest、logs、output manifest/hash、cooperative/forced cancel、late-result rejection；以依赖注入的runtime Python路径运行。复用现有task handle/poll语义供GUI。
2. **P1.3-S2 — joint training request/result**：从P1.2 complete/fixed split构建immutable request和multi-member run；worker创建dataset/训练/评价；result verifier确认runtime、四bodyparts、checkpoint/config和run-owned paths，再登记completed candidate。
3. **P1.3-S3 — trained model reference**：验证checkpoint属于本次run/config并生成immutable manifest；save/reopen与missing/modified file状态。到此做AI lifecycle/protocol Independent Review，关闭blocking后再实现import UI。
4. **P1.3-S4 — teacher import core**：目录选择、safe config解析、explicit mapping、managed copy/staging/hash/atomic publish、static compatibility state；fault injection覆盖半拷贝/同名/路径逃逸/Unicode。
5. **P1.3-S5 — runtime compatibility self-test**：通过同一external worker实际加载选定checkpoint并对合法输入infer；记录device/versions/evidence；变化使证据失效。训练模型和import模型共用同一validator。
6. **P1.3-S6 — training/import GUI and closure**：Run training、Import DLC Model…、mapping/compatibility/result/log展示；cancel/retry使用新run/model ID；真实DLC两路径smoke、Human Review、Independent re-review、集成。

### Acceptance Criteria

- [ ] joint train request含四member/role snapshot、4/4 label snapshots、共同split、input digest、config/seed/runtime identity；任何3/4frame不出现。
- [ ] external worker不持有session、不写manifest；request/result identity、status/exit、path containment、size/SHA、runtime/device均验证；取消/超时/迟到结果不登记completed model。
- [ ] 一次DLC project/dataset/train含恰好四个规范bodyparts，单run产生可验证checkpoint/config；不能四次单点训练冒充联合训练。
- [ ] trained model reference指向本项目completed train run且manifest一致；imported model的source_train_run_id为null，不制造training history。
- [ ] teacher model bundle全部复制到project-managed path；原目录移动后仍可用；bundle中缺文件、hash变化或配置逃逸变为unavailable/incompatible，不静默寻找替代文件。
- [ ] bodypart mapping missing/duplicate/extra、multi-animal、identity tracking、cropping或不支持engine均fail closed且不发布model reference。
- [ ] static parse只得到unverified；当前runtime真实load/infer成功才compatible；证据记录实际runtime/device/version与input/model digest。
- [ ] save/reopen后run/model/mapping/compatibility state一致；generic unbound single-track train workflow保持兼容。

### Automated tests

- protocol schema/negative tests：wrong job/digest/status/exit/device、output escape/hash、duplicate directory、late response、cancel tree、malformed/oversized log payload。
- joint request tests：role order、label/fixed split、input digest、stale annotations/role/video/runtime。
- run/model cross-reference tests：trained/imported origin、source run status/type、manifest mismatch、missing files、save/reopen。
- teacher import fixtures：safe minimal config、renamed bodyparts mapping、missing/duplicate/extra/multi-animal/cropped、absolute path rewrite、copy/rename failures。
- GUI offscreen：runtime unavailable、progress/log/cancel、mapping errors、self-test state、project switch/generation mismatch。
- current single-track train/infer/runner regression全部保留。

### Real DLC verification

以下 slices 必须真实 DLC 3.x 验证：

- S2：四bodypart小dataset做至少1 epoch CPU training，确认checkpoint/config与四role metadata；不以1 epoch声称accuracy。
- S5：把该model bundle复制后作为`origin=imported`导入另一个测试project，执行当前runtime真实load + 最小infer self-test；原训练目录不可作为运行依赖。
- S6：cancel一次真实joint training，确认terminal状态、日志与partial artifacts不产生model reference。原生Windows仍按批准延期，Mac证据不可替代。

### Human Review

用户实际操作两条路径：Run training并查看进度/取消/日志；Import DLC Model…选择bundle、确认mapping、看到unverified→compatible或可操作错误。问题必须指向模型文件、mapping或runtime，而非泛化为“训练失败”。

### Independent Review gate

- S3：external process boundary、run lifecycle、artifact publication、digest/cancel/late result专项review。
- S5：teacher bundle trust boundary、mapping、provenance与self-test语义专项review。
- S6：复审全部 findings；真实DLC日志和artifact manifest作为证据，Mock不能替代。

### Risks and failure recovery

- DLC/PyTorch环境差异会暴露P0.3未覆盖情况；错误保留worker log和实际版本，旧runtime/model继续可用，不自动升级依赖。
- 强制取消可留下run-owned staging；manifest不引用它，提供清晰cleanup/retry提示，新retry使用新ID。
- teacher config路径重写可能损坏bundle；先在staging副本修改并self-test，原老师目录只读，失败不publish。
- 训练输入在后台期间变化：completed artifact可保留作诊断，但capture digest不匹配则不能登记为当前可用model。

### Completion documentation

更新status、计划Result、review records、architecture/runtime docs和scripts smoke说明；记录tested DLC/Python/Torch/platform/device组合。不得写成installer或clean-machine setup已完成。

## 8. P1.4 — Joint inference, review and activation

### Goal

使用P1.3任一compatible model执行一次四bodypart全视频推理，产生不自动生效的joint candidate；学生按frame/role审核和人工修正后，以单一事务Activate/Replace/Clear四轨并支持Undo/Redo/save/reopen，为P2提供稳定adopted measurement。

### Context Pack

- P1.1–P1.3 merged code/reviews/real DLC evidence
- `publication/spec/experiment-run-derived-contracts.md` §§3、5–6、8
- `publication/spec/scientific-profiles.md` QC/source/missing semantics
- `src/ai_physics_tracker/application/inference_job.py`
- `src/ai_physics_tracker/infrastructure/dlc_predictions.py`
- `src/ai_physics_tracker/application/difficult_frames.py`
- `src/ai_physics_tracker/application/suggested_frame_review.py`
- `src/ai_physics_tracker/application/project_session.py` activation/history
- `src/ai_physics_tracker/domain/track_store.py`
- `src/ai_physics_tracker/application/workflow_projection.py`
- `src/ai_physics_tracker/gui/suggested_frame_review_actions.py`、`tracking_actions.py`

### Scope

做：joint inference request/worker/result、四bodypart parser与per-role summaries、candidate artifacts、frame-level review/QC、role-aware manual correction、atomic four-track activation/replace/clear/undo、experiment workflow projection、save/reopen与P2 handoff contract。

不做：θ reconstruction、科学mask最终判定、自动修正、动态pivot、通用multi-object review、模型accuracy承诺。

### Main design decisions

1. **raw prediction artifact 是candidate truth**：completed run保存四role全帧原始x/y/likelihood/missing及hash；不把candidate点写成active observations。Activate才从artifact构建四轨AI projection。
2. **一次parse四bodyparts**：parser先验证scorer/bodypart/coord结构、frame coverage、无duplicate/extra mapping，再按role生成points和missing/low-confidence summaries；某role缺测只缺该点，不删除同frame其他raw values。
3. **review按frame聚合、按role解释**：复用run-scoped queue和Accept/Correct/Skip，但candidate显示四个预测、每role confidence/missing/reason。Correct写对应role的manual `TrackPoint`；manual仍优先且保留AI provenance。
4. **P1 QC只报告measurement integrity**：4/4 completeness、missing/confidence、tracked pivot相对fixed pivot的偏移、body_top/body_bottom/tip几何可计算性。没有历史证据的阈值不得伪装成publication default；新增阈值必须标`new_student_policy`并有provenance。P2决定θ与科学fit mask。
5. **atomic activation**：验证run/model/video/timing/role snapshot/input digest及artifact后，在一个candidate store中清理四member旧AI、装入新四role点、保留manual、更新experiment active/history/revision/stale，然后一次commit。
6. **late/stale分开**：job完成时capture digest过期则run可记录stale/diagnostic状态，但不能成为可Activate candidate；取消后的result永不采用。Activate时再次验证artifact与当前experiment binding。
7. **workflow以experiment投影**：task card显示setup→labels→model→candidate review→adopted measurement。不得把四个single-track cards拼成Pendulum状态。

### Slices and dependencies

1. **P1.4-S1 — joint inference request/result/parser**：compatible model reference→immutable request→external worker one-call DLC infer；解析四role全帧artifact，生成per-role/4-of-4 summaries和input digest；candidate不改observations。
2. **P1.4-S2 — experiment-level review/QC core**：把现有 difficult-frame signals扩为role-aware frame candidates；加入raw completeness/pivot/body geometry diagnostics与run-scoped review serialization；Correct动作写manual并更新revision/stale。
3. **P1.4-S3 — atomic four-track transaction**：实现Activate/Replace/Clear和history，一次candidate commit/undo；统一bound Track legacy guards；覆盖artifact重读、manual supersede/provenance、all-or-nothing fault injection。完成后立即做transaction/data-loss Independent Review。
4. **P1.4-S4 — experiment workflow/UI**：joint inference进度/cancel/log、四点overlay/QC/review queue、candidate vs active提示、Activate/Replace/Clear confirmation、history与task cards。
5. **P1.4-S5 — P2 adopted-measurement boundary**：提供Qt-free read-only snapshot builder，输出四role adopted observations、source/confidence/missing/frame/time、fixed geometry/calibration/release/L/g及canonical digest；不计算θ。
6. **P1.4-S6 — end-to-end acceptance/closure**：自训模型和import模型两条真实infer路径；取消/stale/late/save-reopen/Undo/full regression；Human Review；Independent re-review；更新P1状态并停止。

### Acceptance Criteria

- [ ] 一次DLC analyze call返回四个bodyparts；run恰好绑定当前experiment四members和role snapshot，不能由四个独立infer run拼接。
- [ ] bodypart mapping missing/duplicate/extra、错误scorer/coords、frame重复/越界/不完整batch、nonfinite非法值均整体fail closed；合法missing按role保留。
- [ ] completed inference只成为candidate；在用户Activate前experiment active pointer和四tracks effective AI observations不变。
- [ ] review显示四role prediction/confidence/missing/reason；Correct产生manual provenance，Accept/Skip不伪造manual label。
- [ ] tracked pivot仅出现在QC与adopted measurement中；fixed pivot不被逐帧prediction覆盖，P2 handoff明确区分两者。
- [ ] Activate/Replace/Clear对四tracks、experiment pointer/history/revision/stale为单次原子更新；任何一个role/artifact校验失败时零变化。
- [ ] manual corrections在四轨替换后仍优先，旧AI保留合理superseded provenance；Clear只清active AI projection，不删manual/run/raw artifacts。
- [ ] Undo/Redo完整恢复四tracks和experiment状态，不产生mixed-run；save/reopen后一致。
- [ ] stale input、context switch、cancel、timeout、late success、modified artifact均不能污染当前active result。
- [ ] bound Track所有legacy single-track AI写入口不能绕过；generic unbound Track完整回归通过。
- [ ] P2 snapshot builder只在当前四role binding与active run一致时返回，包含absolute source frame/time和release事实，不压缩gap、不计算θ。

### Automated tests

- parser matrix：fourbodypart DataFrame/HDF/CSV、scorer层级、bodypart mapping、missing/nonfinite、frame coverage、per-role counts。
- lifecycle tests：pending/running/terminal、candidate not active、capture digest变化、cancel/late、project/video/model switch、artifact hash。
- review/QC tests：per-role reason、4/4 completeness、manual Correct、fixed vs tracked pivot distinction、unknown/new policy provenance。
- transaction tests：每个validation step fault injection；Activate/Replace/Clear/Undo/Redo；manual preservation；mixed-run impossible；history counts/digests；save/reopen。
- guard matrix：对四个bound Track逐一调用全部legacy mutator，assert project/store/history byte-equivalent；unbound controls成功。
- workflow/offscreen tests：task cards、candidate/active labels、confirmation counts、review navigation、autosave、context generation。
- P2 handoff contract tests：units/source/time/missing/geometry/release/digest，修改任一dependency后旧snapshot拒绝。
- 全量现有single-track/refinement/GUI regression。

### Real DLC verification

必须真实验证：

- S1：P1.3自训四bodypart模型对短视频一次joint inference；确认原始文件四bodyparts/全frame覆盖及per-role summary。
- S1/S6：同一测试bundle按teacher import路径在另一experiment/video执行joint inference，证明不依赖本项目伪造train history。
- S6：真实infer中取消一次并验证无completed candidate/active污染；再成功运行→review一个frame→manual correct→Activate→Replace或Clear→Undo→save/reopen。

这些是结构与生命周期smoke，不是tracking accuracy benchmark。Mac CPU为P1必需证据；可额外记录MPS但不能以tensor self-test替代DLC infer。Windows仍not_run并受P6前gate约束。

### Human Review

自动化和真实DLC通过后，用户从P1.3的compatible model执行：Run inference → 查看四点overlay和QC → Correct一处 →确认candidate未自动生效 → Activate → Replace/Clear → Undo → save/reopen。封闭式确认重点是role辨识、candidate/active差异、manual保留、tracked/fixed pivot表达和错误可操作性。

### Independent Review gate

- S3：四轨事务、legacy bypass、artifact/input identity、manual provenance、Undo/data-loss专项review；blocking finding关闭后才接activation UI。
- S5：P2 handoff scientific semantics review，确认fixed pivot/time/missing/source边界。
- S6：最终AI lifecycle + persistence re-review；所有finding Closed才宣布P1完成。

### Risks and failure recovery

- 四条轨逐一commit会产生mixed run，是P1最大事务风险；实现和测试必须只有一个candidate/commit point。
- 四bodypart HDF列层级或mapping错误可能交换role；run snapshot、parser和activation三处均核对规范mapping与track IDs。
- 大批量points不能经进程queue；worker写immutable artifact，host只传summary/path/hash。
- artifact损坏不删除旧active result；candidate标不可用并给重新infer入口。
- review时新增manual会改变measurement digest；允许保留candidate raw artifact，但Activate必须按当前manual优先规则重建并记录新digest。

### Completion documentation

- 完成 `publication/STATUS.md`、本计划Result、P1.4 review record/index、architecture与运行/体验说明。
- P1 phase closure逐项核对本计划总体验收，运行全量tests与真实DLC smoke；适用CI通过后push。
- Windows runtime延期状态继续写`not_run`和P6前门禁，不能在P1收尾改成通过。
- P1完成后停止，等待用户启动P2；不自动实现θ或科学core。

## 9. Phase-level acceptance matrix

| Required outcome | Primary Subphase / evidence |
| --- | --- |
| v1原项目不破坏；v2明确Save As | P1.1 repository fault injection + Human Review source reopen |
| role identity不依赖Track名称 | P1.1 role mapping tests；P1.2 renamed-track exporter test |
| training frame必须4/4 manual | P1.2 pure join/export negative matrix |
| one dataset/train/infer consumes four bodyparts | P1.2 dataset smoke；P1.3 train smoke；P1.4 infer smoke |
| teacher import不伪造training history | P1.3 origin/source cross-reference tests + imported bundle smoke |
| wrong/missing mapping fail closed | P1.3 import fixtures；P1.4 parser matrix |
| candidate不自动active | P1.4 lifecycle/session tests + Human Review |
| manual correction priority/provenance | P1.2 TrackPoint reuse；P1.4 activation/review tests |
| atomic Activate/Replace/Clear/Undo | P1.4 transaction fault injection + save/reopen |
| bound Track不能绕过single-track path | P1.1 guard matrix，P1.4再次全矩阵回归 |
| tracked pivot只用于QC | P1.1 fixed pivot ownership；P1.4 handoff/review tests |
| save/reopen state一致 | 每个Subphase round-trip；P1.4 end-to-end |
| cancel/stale/late不污染 | P1.2 selection、P1.3 training、P1.4 inference各自lifecycle tests |
| generic single-track兼容 | 每个Subphase全量回归与unbound control tests |
| stable adopted measurement for P2 | P1.4 Qt-free snapshot builder contract |

Phase完成判据还包括：四个Subphase各自review final verdict通过；四次适用Human Review通过或由用户明确跳过；P1.2/P1.3/P1.4指定的真实DLC smoke有版本、平台、命令和日志；产品代码、tests和文档状态一致。

## 10. Test execution strategy

每个slice先跑最小targeted tests，再跑其Subphase涉及的domain/application/infrastructure/GUI集合。每个Subphase收尾跑：

```bash
python -m pytest
python -m compileall -q src tests
```

GUI使用`QT_QPA_PLATFORM=offscreen`自动化；体验只由Human Review判定。真实DLC smoke使用项目外临时目录，不提交视频、dataset、checkpoint或runtime。P1收尾运行macOS现有runtime闭环并触发macOS/Windows普通CI；普通Windows CI不等同延期的原生Windows DLC G1–G4。

测试断言按风险分层：

- trust/data boundary：负例优先，fail closed且候选快照不变；
- transaction：故障注入到每个校验/文件/commit节点；
- DLC：结构与生命周期真实smoke，不设置虚假的accuracy门槛；
- GUI：只测状态投影和动作路由，不复制domain不变量；
- compatibility：generic unbound control贯穿每个Subphase。

## 11. Risks requiring explicit watch

1. **schema writer drift**：`CURRENT_SCHEMA_VERSION=2`若全局使用会把generic项目静默升级；必须按project format dispatch。
2. **run compatibility shim misuse**：多成员run若暴露一个任意`track_id`，旧代码会静默只处理第一role；兼容访问只允许single member，多成员必须显式API。
3. **partial transaction**：四次单轨activate/clear即使包在UI循环里也不是原子事务；只允许一个Project candidate commit。
4. **exporter false confidence**：当前bodyparts参数存在但其余列为空；真实CSV/HDF内容和DLC loader必须验收。
5. **role/mapping drift**：display name、teacher bodypart名和规范role是三层不同信息；mapping snapshot和digest贯穿dataset/model/run/result。
6. **candidate contamination**：completed prediction artifact不能在Activate前进入active observations；review Correct除外，它是明确manual事实。
7. **runtime scope creep**：P1只做external runner和已有runtime路径；下载/repair/installer会吞噬P1且仍无法替代P6 clean-machine验收。
8. **QC overclaim**：没有科研证据的pivot/body阈值不得伪装historical default；P1报告measurement integrity，P2应用scientific profile。

## 12. Per-subphase branch and documentation checklist

| Subphase | Branch | Review record | Status after completion |
| --- | --- | --- | --- |
| P1.1 | `feat/p1.1-pendulum-setup` | `docs/reviews/publication-p1.1-review.md` | P1.1 complete；next P1.2 |
| P1.2 | `feat/p1.2-complete-frame-annotation` | `docs/reviews/publication-p1.2-review.md` | P1.2 complete；next P1.3 |
| P1.3 | `feat/p1.3-joint-training-model-import` | `docs/reviews/publication-p1.3-review.md` | P1.3 complete；next P1.4 |
| P1.4 | `feat/p1.4-joint-inference-activation` | `docs/reviews/publication-p1.4-review.md` | P1 complete；stop before P2 |

每个Subphase在开始时从本节拆出短的执行mini-plan/Issue正文，按实际代码再细化文件，不预生成空模块。每次收尾更新`publication/STATUS.md`、`docs/status/current.md` publication banner、本计划Result与review索引；架构或runtime文档只记录已经实现并验证的事实。

## 13. Result

- **P1.1（2026-09-21，`feat/p1.1-pendulum-setup` 已合并）**：S1–S6 全部完成。schema v1/v2 双格式读写（required_capabilities 分派、keyed publication 集合、capability fail-closed）、v1→v2 显式 Save As 迁移（source manifest SHA、源零改动经故障注入）、rootless v2 首存、`PendulumExperiment`/四 role/几何（true vertical 端点 digest 确认）/物理/release、多成员 `TrackingRun`（单成员兼容访问器 fail-closed）、experiment 事务与全部旧单轨 AI 入口 guard、geometry/release 动作（revision/stale/undo）、setup GUI（向导/侧栏 checklist/视频 pivot 与 vertical 有序点选/持久 overlay/L·g mm 输入/release 当前帧）、workflow 投影 experiment 事实卡、scientific result envelope 验证与无损保存（无 producer）。三轮 independent review（guard/schema/S5-S6 终审）与两轮 Human Review 全部通过；最终 921 tests。已知中间态：bound track 无 AI 训练路径（joint 属 P1.3）；migration 后旧 generic run 保留为历史记录。Real DLC smoke：不适用（P1.1 无 AI 验收）。
- P1.2–P1.4 未开始。
