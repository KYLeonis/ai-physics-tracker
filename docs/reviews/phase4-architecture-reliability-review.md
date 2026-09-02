# Phase 4 收尾 Review — Architecture / Reliability / Product Boundary

- 日期：2026-09-01
- 范围：`main` @ `1466289`（Phase 0–4 全部完成后的工程基础）
- 性质：只读 review，不修改实现代码；不改 roadmap 既有安排
- 方法：通读 `src/` 全部四层与 `tests/`、核心 spec（data-model / project-format / phase2–4 requirements）、ADR-0003/0005/0006/0007/0008/0011/0012、workflow/roadmap/status；运行全量测试（**433 passed in 41s**，offscreen）；对可疑点做临时目录内的只读复现与性能测量（见各 finding 的 Evidence）
- **处置状态（2026-09-02 更新）**：F1/F4/F5/F6 已由 Subphase 4.5（Issue #16）修复；F3 已由 Phase 5.0（Issue #17）关闭，见 [phase-5.0-review.md](phase-5.0-review.md)；F2 保留在 Phase 5.4；其余按 §10 归属不变。

---

## 1. Executive Summary

**总体工程健康度：良好，高于同阶段项目的平均水准。** Phase 0–4 沉淀下来的核心资产质量是真实的：

- 领域层（frozen dataclass + 函数式更新 + 全量跨对象校验）忠实实现了 data-model spec，raw-只增不改、manual last-wins / engine first-wins、生效值解析、supersede 链等语义都有测试锁定；
- 持久化具备原子写 + 单备份 + 备份发布失败回滚 + schema 守卫 + 未知键容忍读取 + 加载时 time_mismatch 标记；
- 并发边界是这个代码库最强的部分：播放（delivery generation + request id + latest-wins）、时序验证（两阶段 + 代际合并）、运动学（输入快照比对 + 原子批次提交）、AI 任务（spawn 独占 worker + 文件交换 + run/媒体/会话/项目快照四重身份校验 + first-wins 原子导入）各自都有明确的迟到结果丢弃规则；
- 数值管线有解析解测试（匀速/匀加速/单摆小角度）、NaN 分段滤波、显式 `delta=1/fps`、标定/时序溯源随派生数据持久化，"程序正常但物理结果错误"的已知风险面被压得很小。

**主要问题集中在三处，且都不是地基问题：**

1. **一个确定性功能回归**：删除带 TrackingRun 的 Track 在 domain 层被校验拒绝，GUI 未捕获异常 → 按钮**静默失效**（F1，已复现）。这是 Phase 4 引入 run 注册表后与 Phase 2 删除路径的组合漏洞，无测试覆盖。
2. **产品闭环缺一块**：spec §4.4 定义的"按 run 清除引擎观测"没有暴露到会话层与 GUI，而 first-wins 使重复推理必然 0 插入——**用户没有任何办法整体替换一条不好的 AI 轨迹**（F2）。这正是 Phase 5 修正闭环的前置需求。
3. **编排栈双轨**：4.2/4.3 的 `TrainingCoordinator`/`InferenceCoordinator` 完整生命周期与 4.4 的 `TrackingJobRunner` 统一管线并存，GUI 只用后者（F3）；伴随 application↔infrastructure 互相 import 与跨包私有符号引用，分层测试只是字符串匹配（F4）。

Critical 0 个；High 1 个（F1）；值得在 Phase 5 前处理的还有 F2（并入 Phase 5 规划）、F5/F6（廉价加固）。**建议一个小而有限的 stabilization subphase（P4.5，约 2–4 天）处理后即可安全进入 Phase 5**；不需要大重构，地基不需要动。

---

## 2. Current Architecture Assessment

### 2.1 分层现状

四层结构（GUI / application / domain / infrastructure）实际存在且域规则成立：

- domain 无任何框架依赖，纯数据 + 纯函数（`domain/kinematics.py` 只依赖 numpy/scipy）；
- application 不 import Qt（有回归测试锁定）；GUI 不 import infrastructure/cv2/deeplabcut（字符串级测试锁定）；
- DLC 通过 `EngineAdapter` Protocol + `MockEngineAdapter` 隔离，monkey-patch（`_selected_snapshot`、`_prediction_progress`）全部限制在独占 spawn 子进程内且有 finally 恢复，第三方实现没有泄漏进 domain。

**偏离点**（详见 F4）：application 与 infrastructure 互相纠缠——`application/tracking_job.py` 直接 import `DLCAdapter`、`ProjectRepository`，以及基础设施私有符号 `_QueueLogStream`、`_tracking_run_to_payload/_from_payload`、`_inference_process_worker`；`infrastructure/engine_adapter.py` 反向 import `application.tracking_types`。组合根（`gui/app.py`）只注入 repository/decoder/probe，AI 链路的 adapter 是在 application 内部默认构造的。这在当前规模可用，但它使"端口注入"的架构意图打了折扣，且现有分层测试对这类侵蚀不可见。

### 2.2 状态所有权与数据流

- **状态所有权清晰**：活动 `ProjectSession` 只在 GUI 线程变更（`TrackingActions`/`ProjectActions`/`ChartActions` 的注释与实现一致）；worker 只持有 frozen `Project` 快照与独占资源；所有后台结果经"候选 + 身份校验 + 主线程提交"回流。
- **ProjectSession 正在成为枢纽**（1078 行）：视频登记/时序授权、track/标注、标定 CRUD、运动学、run 登记与导入、save/load/save_as、undo/redo 全在一个类里。目前内聚性尚可，但 Phase 5（选帧/困难帧/修正）与 Phase 6（θ/ω/α）都会继续往上加。`MainWindow`（1163 行）同理，同时容纳播放接线、track 管理、标定 UI、标注交互。**这是趋势性观察（F10），不是当前需要动手的债**；建议 Phase 5 动到哪块就顺势把哪块抽成独立 controller/service。
- 临时接口固化风险的具体实例是 F3：4.2/4.3 的协调器生命周期 API 已经不被 GUI 使用，但仍是公共接口并被测试固定，随时可能与 4.4 路径发生行为漂移。

### 2.3 依赖方向之外的结构评价

- `TrackStore` 的写入语义（manual last-wins + 遮蔽链、engine first-wins、按 run 清除）与 spec §4 完全一致；`resolve_effective_points` 在写路径已保证至多一条 active 的前提下仍防御性处理冲突。
- 领域校验（`validate_project`）在每次 `replace()` 后全量执行，O(n) 但在桌面规模可接受；它正是抓住 F1 的那道闸门——问题是删除路径没有先清 runs。
- 时间语义实现严格：`frame_to_time` 单步换算、`time_to_frame` half-up 舍入、`has_time_mismatch` 容差、加载时标记、近似时序显式同意并把误差预算写进 `source_detail`。

---

## 3. Reliability Assessment

按题目逐项结论（细节见 Findings）：

| 关注点 | 结论 |
| --- | --- |
| 项目保存/恢复 | **强**。原子写 + 备份轮转 + 备份失败回滚主文件（`project_repository.py:206-223`）；`load` 拒绝损坏数据并指向备份，不静默修复；`_publish_project` 暂存目录发布、失败保留恢复路径 |
| Undo / Redo | **符合设计**。快照仅含 tracks/observations/calibrations/active_map/derived；run 历史刻意不回滚（有测试锁定 `test_import_is_one_undo_and_tracking_run_history_survives_undo_redo`）；保存清空历史是文档化决策（Accepted，F13） |
| raw / derived 保护 | **强**。raw 像素只增不改（manual last-wins 是 spec §4.2 明确例外）；所有派生带 `pipeline`/`calibration_ref`/`timing_context` 溯源；标定/轨迹/时序变化均正确传播 stale（含首次标定使 px 运动学 stale 的合理扩展） |
| Timeline / frame-time 一致性 | **强**。冻结 time_s + 加载复核 + 引擎导入前逐点时间校验（`import_engine_points`，`project_session.py:383-398`） |
| Calibration stale 传播 | **正确**。edit/switch/delete 三路径 + 首次标定，图表侧还做 calibration_ref 二次比对并降级显示 |
| 后台任务生命周期 | **总体强，一处双轨债（F3）**。D1 策略（关闭/切换强制取消）在 `guarded`/`requestWindowClose`/`shutdown` 全链路落实 |
| cancel / close / project switch | **强**。取消经后台线程执行、评价阶段取消保留已产模型（`cancel_tracking_job` + `_recovering_model`）、导航前确认、save-as/relink 在任务期禁用 |
| late / stale result | **强**。四套代际/身份机制（播放 delivery generation、timing token、kinematics 输入快照、tracking 的 session/project/context 三重比对 + `base_project is` 身份检查）各有测试 |
| DLC 训练/推理失败 | **良好**。进程异常退出兜底 failed、评价失败不伪称训练失败、取消后迟到终态被忽略（有 GUI 测试） |
| partial failure | **强**。整批校验、失败不产生部分提交（`import_engine_points` 先验证后写、kinematics 批次完整性检查） |
| dependency missing | **良好**。DLC/pandas 缺失都有明确 RuntimeError 且经任务日志/失败状态呈现 |
| corrupted / missing assets | **良好**。视频缺失→可恢复态+Relink；sha256 身份校验（无哈希时显式警告）；项目文件损坏→拒绝+备份指引 |
| exception handling | **主路径良好，一处裸露（F1）**。GUI 多数 slot 捕获 `ProjectSessionError/ValueError`，但 `_deleteSelectedTrack` 未捕获；PySide6 6.11 实测 slot 异常只走 excepthook、事件循环存活——即静默失效而非崩溃 |
| atomic commit / rollback | **强**（见上） |

**数据丢失风险评估：未发现会导致用户数据丢失的路径。** 保存候选与活动会话分离、IO 失败不提交根目录绑定、发布失败不自动删除、引擎取消不导入半批结果。最接近风险的场景（应用在训练中被强杀遗留孤儿进程）产物都按 run 目录隔离，重开项目会把中断 run 标记 failed（ADR-0012 D5），属 Accepted（F12）。

---

## 4. User Boundary & Failure Analysis

从正常用户操作序列出发的检查结果：

- **快速连续点击/seek/scrub**：latest-wins 合并 + 请求编号丢弃旧交付 + 拖动期间不回写滑块 + 落点拒绝在途帧（`_onAnnotationClicked` 的 `_has_pending_request` 守卫）——处理完备。
- **播放中切换项目/视频/新建**：`guarded` 统一走 dirty 提示 + AI 任务取消确认；切换视频在任务期强制经确认路径。正确。
- **训练/推理中保存**：允许 Save（保持活动 session 身份，`accept_saved_snapshot` 合并后台新数据并保留一步回溯），Save-as/Relink 禁用。符合 ADR-0012 D4。
- **推理期间继续人工修改**：`prepare_tracking_candidate` 在后台按**最新**人工点重算导入（first-wins 保护人工点），候选过期（`base_project` 身份不符）则用新快照重建。正确且有测试。
- **训练/评价中取消**：评价阶段取消保留模型并转为可导入结果；纯训练阶段取消不留 run 结果。有 GUI 测试。
- **视频被移动/删除**：解析为 None → browsing-only + Relink；Relink 时有 sha256 身份校验（无哈希时显式确认）。正确。
- **project.json 损坏**：拒绝加载 + 备份指引 + 明确错误文本。正确（不自动回退备份，符合"永不静默修复"）。
- **空项目 / 空 Track / 极短视频**：图表给出明确消息（"no valid data / too few continuous points"）；1 帧视频可打开（frame_count>0 校验通过）。未发现崩溃路径。
- **大量 TrackPoint**：正确性不受影响；性能见 F5（deepcopy O(n)）。
- **缺测 / NaN**：分段滤波、图表 connect 断开、不造值。正确。
- **无 GPU / DLC 不可用**：device auto→mps→cpu；DLC 缺失时任务失败并给出明确原因。正确。
- **磁盘/写入失败**：保存失败不清 dirty、不误报成功；发布失败保留 staging 并在异常信息中给出路径。正确。
- **重复训练 / 重复推理**：重复训练正常产出新模型；重复推理 first-wins 0 插入是**测试锁定的预期行为**，但从产品视角用户此时没有任何整体替换手段（F2）。
- **Undo/Redo 边界、保存后继续编辑**：符合设计（保存点=历史边界）。
- **旧任务结果晚到**：多处显式丢弃规则 + 测试覆盖（`test_late_success_after_cancel_is_ignored_and_next_task_can_start` 等）。
- **删除已训练过的 Track**：**失败且无反馈（F1）**——本节唯一的确定性坏行为。

---

## 5. Numerical / Scientific Reliability

结论：**当前管线在"程序正常运行但物理结果错误"这个维度上的已知风险都很小，且大多有显式的用户可见提示。**

- **frame/timestamp**：单步换算无累积漂移；NTSC 类帧率的 float 误差在 spec 论证范围内；`time_s` 冻结 + 加载复核。
- **coordinate spaces**：raw 永远像素（y 向下）；world y 向上 + 旋转 + 原点按 spec §6.2 精确实现，往返不变量有测试；无标定时图表明确标注 px 且注明 y 轴向下。
- **units**：`derive_unit` 链路一致（m/s、m/s²、px/s）；DLC 原生评价指标附单位说明（`_evaluation_metric_unit`）。
- **calibration**：退化标定显式拒绝（不静默 identity）；比例现算不存双份真值；首次标定/编辑/切换/删除的 stale 传播正确；图表对 `calibration_ref` 不匹配的曲线降级为 stale 提示。
- **missing observations**：缺测帧 NaN 展开、分段 SG、不跨段桥接（有测试）；图表按连接性断线。
- **smoothing / differentiation**：实现与 ADR-0008 完全一致——SG deriv 单步等价于"先平滑后微分"，`delta=1/fps_nominal` 显式传入（规避 DLC2Kinematics 的 delta bug），短段缩窗/跳过规则有测试；解析解（匀速/匀加速/单摆小角度）验证过恢复精度。
- **manual/AI fusion**：`effective_points` manual 优先、引擎取最新；kinematics 与图表统一走 effective 入口；AI 导入使旧派生 stale，UI 提示 recompute。
- **confidence**：manual 恒 null（spec §3.5）；低置信度帧在解析边界整帧丢弃不造点（`missing/low_confidence` 计数持久化）；**限制**：逐帧 confidence 不进入领域层（原始 h5 归档于 run 目录），UI 无法按置信度审阅/着色——这是 Phase 5 困难帧检测的直接输入，属既定规划（F8，Later）。
- **persistence round-trip**：serializer 对全部对象有 round-trip 测试（含 pipeline 参数）；`allow_nan=False` 保证 JSON 合法；未知键保留。
- **已知取舍**：近似时序（near-CFR）下的速度/加速度误差不可保证——但整个链路（显式同意对话框、误差预算、`timing_context` 溯源、图表常驻提示）都把它暴露给用户而非掩盖。这是正确的科学态度。

---

## 6. Test & Verification Assessment

**433 个测试是"真测试"为主**：领域语义（写入规则、supersede 链、生效值、stale 传播）、数值解析解、持久化 round-trip/损坏拒绝/原子性、并发行为（latest-wins、迟到丢弃、取消竞态、保存身份保持）都有行为级断言。GUI 集成测试（`tests/gui/test_tracking_actions.py`）用 spawn 进程 + mock adapter 覆盖了最难的几个场景：取消期间 Qt 循环保持响应、取消后迟到成功被忽略、评价期取消保留模型、导航确认、上下文破坏动作不误取消任务。CI 双平台（macOS/Windows 3.11）通过；真实 DLC 链路有 CPU 冒烟脚本（`scripts/smoke_test_*.py`）作为 CI 外证据，且 4.4 有用户 Human Review 记录。

真实缺口（按价值排序）：

1. **F1 组合无测试**：delete_track × tracking_runs。域校验存在、写路径存在、但两者组合从未一起测过——这是漏网的根本原因。
2. **分层测试太弱**（F4）：三个字符串 `not in` 断言无法发现跨包私有 import、组合根旁路。改用 AST import 检查成本很低。
3. **mock 与真实 DLC 的残余差距**：mock `evaluate` 返回结构与真实 `_read_evaluation_scores` 结构不同（真实有 train/test/metadata/units，mock 是扁平 metrics）——GUI 只做展示问题不大，但意味着评价展示路径在 CI 中验证的是 mock 形状。真实形状只被冒烟脚本覆盖。
4. **大规模数据无任何测试**（F5 相关）：没有任何测试构造 >1 万观测的场景，O(n) 假设从未被压过。
5. 未使用的 `TrackStore.clear_engine_run` 有单测但无会话/GUI 集成测试（对应 F2 的空缺）。

不构成缺口的：Human Review 已按流程执行（4.4 通过）；Windows/CUDA 真机延期是用户明示批准的既定决策，不是测试缺口。

---

## 7. Findings

> Severity/Likelihood 定义：Critical=数据丢失/损坏；High=核心功能失效或崩溃；Medium=功能受限或维护风险；Low=体验/风格。Decision 取值：Fix Now / Fix Before Beta / Fix in Phase 5 / Later / Accept / Investigate First。

### F1 — 删除带 TrackingRun 的 Track 静默失败（Phase 4 引入的回归）

- **Finding**：任何 track 一旦有过 train/infer run，"Delete track" 即失效；GUI slot 未捕获异常，用户零反馈。
- **Evidence**：`domain/project.py:296-308` `delete_track` 级联 tracks/observations/derived 但不清 `tracking_runs`；`domain/project.py:407-411` `validate_project` 要求 run 必须引用已注册 track。临时目录只读复现：`delete_track(project, tid)` → `ValueError: every tracking run must reference a registered track`。`gui/main_window.py:649-662` `_deleteSelectedTrack` 无 try/except；实测 PySide6 6.11 下 slot 未捕获异常仅打印 excepthook、事件循环存活（不崩溃、也不提示）。无测试覆盖该组合。
- **Impact**：Phase 4 主工作流（训练）之后，一个 Phase 2 交付的常规操作静默失效；用户无法移除建错且已训练的 track。无数据损坏（异常发生在变更前）。
- **Likelihood**: High　**Severity**: High
- **Recommended Action**：在 `delete_track` 中级联删除该 track 的 tracking_runs（与 observations 级联一致；undo 快照不含 runs，需同步确认 undo 语义——建议 run 记录随 track 删除后不可经 undo 复活并在 UI 提示），或者 GUI 拦截并给出明确指引（先清除 run）。补域级 + GUI 级测试。
- **Fix Cost**：Low（< 0.5 day）
- **Decision**：**Fix Now**。确定性回归、修复廉价、Phase 5 修正流程会更高频地删 track。

### F2 — 无法整体清除/替换一条 AI 轨迹（refinement 闭环缺口）

- **Finding**：spec data-model §4.2/§4.4 定义的"按 run 整体清除引擎观测"未暴露：`TrackStore.clear_engine_run`（`domain/track_store.py:231`）存在但 `ProjectSession` 与 GUI 均未提供入口；first-wins 使对同 track 重复推理必然 0 插入（`tests/test_inference_session.py::test_all_skipped_or_empty_import_only_updates_run` 锁定该行为）。
- **Evidence**：`ProjectSession` 无 clear-run 方法；`task_panel.py`/`tracking_actions.py` 无对应动作；phase4-requirements 只要求 manual last-wins 覆盖，未要求 run 清除——按 Phase 4 验收标准这不是违规，而是能力空位。
- **Impact**：用户对一次差劲的推理结果（坏模型、错超参）除了逐帧手工遮蔽外没有任何整体替换手段；Phase 5 的"修正困难帧→再训练→再推理"闭环在再推理处会直接卡住（新推理插不进被旧轨迹占据的帧）。
- **Likelihood**: High（用户做第二次推理即触发）　**Severity**: Medium
- **Recommended Action**：作为 **Phase 5 需求** 正式纳入规划（run 级清除 + 确认对话框 + undo + 派生失效 + run 状态记录），而不是当作纯技术债。若 Phase 5 排期不允许，至少先提供"删除 track 并重建"作为临时出路（依赖 F1 修复）。
- **Fix Cost**：Medium（1–2 days，含测试）
- **Decision**：**Fix in Phase 5**（是 Phase 5 闭环的组成部分；不建议在 stabilization 中顺手做，避免范围蔓延）。

### F3 — 任务编排双轨：4.2/4.3 协调器生命周期与 4.4 统一管线并存

- **Finding**：`TrainingCoordinator.start_training/poll_messages/cancel_training`（`application/training_job.py:181-313`）与 `InferenceCoordinator.start_inference/poll_messages/cancel_inference`（`application/inference_job.py:197-292`）实现了完整任务生命周期，但 4.4 GUI 只走 `TrackingJobRunner` + `run_tracking_worker` 单一独占 worker（`gui/tracking_actions.py:28`）。旧生命周期仅测试在用；两套状态机在取消语义、会话归属检查上已有细微差异。
- **Evidence**：GUI 侧全部调用点在 `tracking_actions.py`（`backend.start`、`prepare_tracking_candidate`、`cancel_tracking_job`）；旧路径的 `start_inference`/`poll_messages` 无 GUI 调用者。`prepare_training`/`prepare_inference`/`prepared_request` 作为工厂仍被 4.4 复用。
- **Impact**：Phase 5 将新增任务类型（选帧、困难帧检测）；双栈意味着每个 late-result/cancel 修复都要做两遍，漏一边就是只在测试里正确的代码。行为漂移已被测试双轨掩盖。
- **Likelihood**: Medium　**Severity**: Medium
- **Recommended Action**：把 4.2/4.3 生命周期方法收缩为内部/legacy（或直接删除并迁移测试），保留 prepare_* 作为共享工厂；`TrackingJobRunner` 成为唯一生命周期实现。作为 stabilization 或 Phase 5 首个 subphase 的一部分。
- **Fix Cost**：Medium（1–2 days，主要是测试迁移）
- **Decision**：**Fix Before Beta**（建议随 stabilization 一并做，见 §9）。
- **Resolution（2026-09-02）**：**Closed**。Phase 5.0 删除两套旧 coordinator lifecycle，保留模块级 prepare/read；统一路径回归与真实 DLC smoke 通过，独立 R2 复审确认。

### F4 — application ↔ infrastructure 互相纠缠 + 分层测试形同虚设

- **Finding**：`application/tracking_job.py:21-26` import 基础设施公共类（`DLCAdapter`、`ProjectRepository`）与私有符号（`_QueueLogStream`、`_tracking_run_to_payload/_from_payload`、`_inference_process_worker`、`read_observation_exchange`）；`infrastructure/engine_adapter.py:10-12` 反向 import `application.tracking_types`。`tests/test_layer_boundaries.py` 只做三个字符串 `not in` 检查，对以上全部不可见。
- **Impact**：serializer 内部重构会静默破坏 application；端口注入意图被绕过（AI 链路 adapter 在 application 内默认构造）；新开发者难以从测试得知真实分层规则。
- **Likelihood**: Low（当前无实际故障）　**Severity**: Low
- **Recommended Action**：① 把 `tracking_types` 挪到中立位置（或接受 infrastructure 为内层并在 ADR 中改写依赖规则）；② 消除跨包下划线 import（将所需函数转正为公共 API）；③ 分层测试改为 AST import 断言（domain 禁 infrastructure/Qt；application 禁 Qt/引擎直连——或按①修订后的规则）。
- **Fix Cost**：Low–Medium（约 1 day）
- **Decision**：**Fix Before Beta**（与 F3 同一subphase处理最省；AST 测试部分可立即做）。

### F5 — `session.detached()` 的 deepcopy 在 GUI 线程上 O(观测数)；全视频推理数据放大后卡顿

- **Finding**：`ChartActions.recompute`（`gui/chart_actions.py:171-190`）在 GUI 线程调用 `prepare_kinematics_job` → `session.detached()` → `deepcopy(project)`。Phase 4 推理本来就会产出 frame_count 级别的观测点，成本线性放大。
- **Evidence**：本机实测 36k 观测（≈10 min@60fps 单轨迹）deepcopy = **494 ms**；观测对象为 frozen dataclass + tuple，本可安全共享引用（后台线程只读），deepcopy 属纯防御开销。`ProjectActions._saveCandidate`/`select_video` 的 detached 在后台线程执行，不受影响；只有 recompute 路径在 GUI 线程。
- **Impact**：长视频上每次 Recompute 冻结 UI 数百毫秒至秒级；无正确性问题。
- **Likelihood**: Medium（短视频基准实验暂无感；Phase 5 全视频工作流常态化后必现）　**Severity**: Low–Medium
- **Recommended Action**：`detached()` 改为浅共享不可变结构（Project/Track/TrackPoint/Calibration/DerivedData 全部 frozen；仅需对 `ui_state`/`extra_fields` 等 dict 保持复制纪律），配一个大规模合成数据的性能回归测试。
- **Fix Cost**：Low（< 0.5 day + 测试）
- **Decision**：**Fix Before Beta**（廉价、收益随 Phase 5 放大；可放 stabilization）。

### F6 — `export_annotations` 使用第一个 labeled-data 子目录，不校验视频身份

- **Finding**：`infrastructure/dlc_adapter.py:141-146`：`video_subdirs[0]` 任意选中第一个子目录导出 PNG/CSV，与当前视频无关联校验。
- **Evidence**：单 track 单视频不变式下当前正确；但 DLC 项目目录按 track 复用（`training_job.py:123-135`，`if not config_path.is_file()` 复用），配合 Relink（无存储哈希时仅警告确认）可能把新视频的帧写进旧视频名下的 labeled-data，`create_training_dataset` 随后把两个视频的坐标/帧混在一个训练集里——**静默的错误训练数据**。
- **Impact**：低概率但触发即产生难以察觉的错误模型（科学可靠性）；Phase 5 再训练频率上升会放大暴露面。
- **Likelihood**: Low　**Severity**: Medium（若触发）
- **Recommended Action**：子目录名由当前视频 stem 推导；不一致时报错而非取 `[0]`；补一个"目录与视频不匹配拒绝导出"的测试。
- **Fix Cost**：Low（< 0.5 day）
- **Decision**：**Fix Before Beta**（廉价加固，放 stabilization）。

### F7 — 时序授权会话级：每次打开项目都要重跑 FFprobe + 全文件 SHA-256

- **Finding**：`_verified_videos` 不持久化（安全设计），但代价是每次 open/select 都要完整哈希视频（`project_media.py:190-208`，后台线程 + 进度对话框 + 可取消）+ FFprobe 验证后才解锁测量。
- **Impact**：大视频每次打开等待数秒到数十秒的验证；浏览不受影响。正确性无风险（保守方向）。
- **Likelihood**: Certain　**Severity**: Low（UX）
- **Decision**：**Accept / Later**。可用"size+mtime+部分哈希"缓存验证结果优化，待用户实际抱怨大视频时再做；不要现在加复杂度。

### F8 — 逐帧 confidence 不进入领域层，低置信度帧只有计数

- **Finding**：低置信度观测在解析边界整帧丢弃（`dlc_predictions.py:81-83`），仅 `import_summary` 计数持久化；原始 h5 归档在 run 目录可回溯。
- **Impact**：用户无法在 UI 按置信度审阅轨迹；Phase 5 困难帧检测需要这些数据（从归档 h5 可恢复，不必改 schema）。
- **Decision**：**Fix in Phase 5**（困难帧检测本就规划消费 confidence；届时决定是逐帧入库还是直接读归档）。

### F9 — 后台媒体验证可让未编辑过的项目变为 dirty

- **Finding**：`record_media_validation` 更新 `videos`（sha256/vfr 标志），`is_dirty` 比较 videos → 首次补哈希或 vfr 标志变化后，关闭时会弹"保存修改？"（用户什么都没改）。
- **Evidence**：`project_session.py:529-537` + `is_dirty` 实现；典型触发是一次性的（保存后哈希稳定）。
- **Impact**：一次性困惑提示；无数据风险。**Severity**: Low　**Likelihood**: Low
- **Decision**：**Later**（可随 F7 一并考虑"验证元数据即时持久化或排除出 dirty"）。

### F10 — `MainWindow`（1163 行）与 `ProjectSession`（1078 行）枢纽化趋势

- **Finding**：两者按 Phase 逐步累积职责；当前内聚尚可、未见隐式状态，但 Phase 5/6 的功能（选帧 UI、困难帧面板、θ/ω/α 计算服务）都会继续堆叠。GUI 内已有跨类私有访问（`TrackingActions` 调 `window._refreshMarkers()`、`tracking_job._owned_session` 写 `session._verified_videos`、`TimingActions` 写 `window._measurement_allowed`）。
- **Impact**：再过 1–2 个 Phase 会开始互相牵制、难以测试。
- **Decision**：**Later**（跟踪项，不预做抽象；Phase 5 动到哪块顺势抽取哪块，如把标定 UI 控制器、run/标注服务从 MainWindow/ProjectSession 拆出）。

### F11 — 遗留协调器路径的 CWD 兜底写入

- **Finding**：`training_job.py:119-120`：无 project_root 时 DLC 工作目录落到 `Path.cwd()/data/engines/dlc`。4.4 路径强制已保存项目，不可达；仅旧路径/测试可触发。
- **Decision**：**Accept**（F3 收敛后自然消亡）。

### F12 — 应用硬崩溃（SIGKILL/断电）可遗留孤儿训练进程

- **Finding**：正常关闭链路完备（取消→terminate→kill + atexit join）；但进程被强杀时非 daemon 子进程会继续训练并向 run 目录写产物。下次打开项目时 run 被标记 failed，磁盘产物按 run 隔离。
- **Impact**：后台 CPU/GPU 占用直到训练自然结束；无数据损坏、无假完成状态。
- **Decision**：**Accept**（ADR-0011/0012 已含该取舍；孤儿产物按 run 目录隔离，D5 恢复语义已验证）。

### F13 — 保存清空 Undo 历史

- **Finding**：`ProjectSession.save/save_as` 清空 undo/redo（"保存点是安全边界"，代码注释明示）。
- **Decision**：**Accept**（文档化的有意决策；对科学工具而言保存点前状态仍完整保留在磁盘备份中）。

### F14 — fps_nominal 修正与 working_zone 编辑无 UI

- **Finding**：域层完整支持（`update_timeline` 的重算/time_mismatch 路径有测试），但 GUI 从未暴露。
- **Decision**：**Later**（等真实需求：容器帧率误报的用户场景出现时再做，spec §5.7 流程已备好）。

### F15 — 单备份文件、无 fsync

- **Finding**：`_atomic_write_manifest` 原子 replace + 单备份轮转，无 fsync；断电极端场景可能同时丢主/备。
- **Decision**：**Accept**（本地桌面工具的合理取舍；加载端有完整拒绝路径兜底）。

---

## 8. Risk Matrix

| | Severity: Critical | Severity: High | Severity: Medium | Severity: Low |
| --- | --- | --- | --- | --- |
| **Likelihood: High** | — | **F1**（删 track 静默失败） | **F2**（无法替换 AI 轨迹） | F7（每次打开重新验证） |
| **Likelihood: Medium** | — | — | F3（编排双轨）、F5*（GUI deepcopy 卡顿）、F6*（导出目录不校验） | F10（枢纽化趋势） |
| **Likelihood: Low** | — | — | F6（触发即错训练数据）、F8 | F4（分层侵蚀）、F9、F12、F14、F15 |

\* F5/F6 的 Likelihood 按"未来 1–2 个 Phase 内被正常使用触发"计；F6 触发概率低但后果直接指向错误科学结果，故保持 Medium。

---

## 9. Recommended Stabilization Actions

建议设立一个**范围严格受限的 stabilization subphase（P4.5，预计 2–4 天）**，只做四件事：

| # | 内容 | 对应 Finding | 预估 |
| --- | --- | --- | --- |
| S1 | `delete_track` 级联清理 tracking_runs（或 GUI 明确拦截）+ 域级/GUI 级测试 | F1 | 0.5 day |
| S2 | `export_annotations` 按 videos 推导子目录并在不匹配时报错 + 测试 | F6 | 0.5 day |
| S3 | `detached()` 去除 deepcopy（不可变结构共享引用 + dict 复制纪律）+ 大规模性能回归测试 | F5 | 0.5–1 day |
| S4 | 分层测试升级为 AST import 检查；消除跨包私有 import（`_QueueLogStream` 等转正公共 API） | F4（部分） | 1 day |

**可选项（若时间允许，与 Phase 5 首个 subphase 合并亦可）**：

- S5：收敛 4.2/4.3 编排双轨（F3，1–2 天，主要是测试迁移）。

**明确不放入 stabilization**：F2（属 Phase 5 功能需求，做了反而扩大范围）、F7/F9（UX 优化，等反馈）、F10（顺势重构，不预做）、全部 Accept 项。

---

## 10. Accepted / Deferred Risks

**明确接受（不再投入）**：

- F11 CWD 兜底（随 F3 消亡）、F12 硬崩溃孤儿进程（产物隔离 + 恢复语义完备）、F13 保存清 undo（文档化决策）、F15 单备份/无 fsync（桌面工具取舍）、近似时序的速度/加速度误差不可保证（已通过显式同意 + 溯源 + 常驻提示充分暴露）。

**延期并有归属**：

- F2 → Phase 5.4（refinement 闭环必需）；F8 → Phase 5（confidence 消费）；F3 → **Closed（Phase 5.0 / Issue #17）**；F7/F9 → 用户反馈驱动；F10 → Phase 5/6 顺势抽取；F14 → 真实需求出现时。

**既有已批准延期（重申，非新发现）**：Windows/CUDA 真机验收延至 Phase 9 打包前（用户明示批准；GitHub Actions Windows mock 测试不等于真机验证）。

---

## 11. Phase 5+ Readiness

**截至 2026-09-02，P4.5 与 Phase 5.0 均已完成，可以继续 Phase 5.1。** 理由：

1. **数据体系就绪**：统一观测模型、provenance、first-wins/last-wins、confidence 字段、run 溯源——Phase 5 的困难帧检测（低置信度/轨迹异常）所需的全部数据语义已就位，无需 schema 变更。
2. **并发骨架就绪**：F3 已由 Phase 5.0 关闭；Phase 5 的新任务类型（选帧、困难帧扫描）可直接复用统一 runner 的独占 worker + 文件交换 + 身份校验模式。
3. **修正闭环有一个已知缺口（F2）**：再推理被 first-wins 挡住是设计使然，Phase 5 必须把"清除旧 run / 允许覆盖"作为一等需求规划进去，否则闭环在第二个迭代就停摆。
4. **UI 枢纽化（F10）在 Phase 5 会首次感受到压力**：困难帧面板 + 修正交互会继续加大 MainWindow；建议 Phase 5 的 subphase 划分把"抽取标注/修正服务"作为一个自然切片，而非事后重构。

---

### Stabilization Recommendation

- **实际处置**：P4.5 已完成 S1–S4；F3/S5 已在 Phase 5.0 完成，均未引入 schema 或 roadmap 范围变化。
- **已关闭**：F1/F4/F5/F6 与 F3。
- **随 Phase 5 自然处理**：F2（5.4）、F8（困难帧输入）与 F10（触及相关模块时顺势抽取）。
- **明确接受不修**：F7、F9、F11、F12、F13、F15 以及近似时序精度声明——它们要么是文档化的有意取舍，要么影响太小不值得现在的复杂度。

---

## 附：本次 Review 的验证证据

- 全量测试：`QT_QPA_PLATFORM=offscreen python -m pytest` → **433 passed in 41.09s**（main @ `1466289`，工作区干净）。
- F1 复现：临时目录内构造含 TrackingRun 的合法 Project 后调用 `domain.delete_track` → `ValueError: every tracking run must reference a registered track`（见 §7 F1）。
- PySide6 slot 异常行为：offscreen 最小程序实测 6.11.2 下未捕获 slot 异常走 `sys.excepthook`，事件循环存活。
- F5 量化：36k 合成观测的 `deepcopy(Project)` 实测 494 ms（Apple Silicon 本机）。
- 代码引用基于 `main @ 1466289` 的行号。
