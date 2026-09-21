# Independent Review — Publication P1.1

- Date:2026-09-21;Scope:P1.1 S1–S4(schema v2 domain/serializer、Save As 迁移、session invariants/legacy guards、geometry/release 动作),commits `c7e3dd0` + `0d0970b`,分支 `feat/p1.1-pendulum-setup`。
- Reviewer:两个 fresh-context 只读 GLM-5.3-Flash agent 并行(R1 legacy bypass/guard 专项;R2 schema/migration/data-loss 专项)。Reviewer 只读,处置全部由实现方完成并复测。
- 计划:[p1.1 执行 mini-plan](../../publication/plans/p1.1-pendulum-setup-execution.md);契约:[experiment-run-derived-contracts](../../publication/spec/experiment-run-derived-contracts.md);ADR-0017。
- 状态:**S3 review gate 的两轮初审 NEEDS-FIX 已全部修复复测(899 passed)**;S6 收尾前做最终 re-review。S5 GUI 尚未开始。

## R1 — legacy bypass / guard 完整性专项

Verdict(初审):NEEDS-FIX → 全部 findings 已修复复测(下表)。

| Finding | 摘要 | 处置 | 状态 |
| --- | --- | --- | --- |
| G1 (Major) | 迁移未清除 bound track 的 legacy 单轨 active 指针,且 guard 封死清理路径,契约 §2 要求迁移时清除/归档 | `save_as_publication` 在构造 candidate 时对四个 role member strip `refinement_state.active_infer_run_id`(activation_history 保留为归档);迁移成功后重建 session store。回归:`test_migration_strips_legacy_active_pointer_from_bound_tracks` | CLOSED(fixed `0d0970b`) |
| G2 (Major) | rebind 解绑后 `delete_track` 级联整条删除共享 joint run,违反契约 §5 引用检查 | `delete_track` 对"被 experiment-bound multi-member run 引用"的 track 抛错(不自动断引用)。回归:`test_delete_track_blocked_by_experiment_joint_run_membership` | CLOSED(fixed `0d0970b`) |
| G3 (Minor) | `record/update_tracking_run` 可把 generic run 挂到 bound track | 实现方调整:不在 domain validate 拒绝(迁移携带的 legacy run 是合法历史,契约 §1"legacy v1 run 迁移为一个 member"),改为 session 层对**新** generic run 注册/更新 guard。回归:`test_new_generic_run_registration_rejected_on_bound_track` | CLOSED(方案调整后 fixed `0d0970b`) |
| G4 (Minor) | bound track 人工单点修正不递增 measurement_revision、不置结果 stale(契约 §2) | 三个 manual 写入口(`mark_point`/`correct_suggested_frame`/`delete_active_manual_point`)统一经 `_with_manual_edit_experiment_state`:revision+1 + stale,不改 active run 身份。回归:`test_manual_point_on_bound_track_bumps_revision_and_stales` | CLOSED(fixed `0d0970b`) |
| G5 (Nit) | `remove_track` 对 bound track 抛裸 ValueError | 包装为 ProjectSessionError | CLOSED(fixed `0d0970b`) |
| G6 (Nit) | remove/update calibration 对非 active/同值也 stale | 保留:契约 §6 明示首版保守方向;input digest 复核兜底 | WONTFIX(有意保守,记录在案) |
| G7 (Nit) | 多成员 run 的 `track_id` property 裸 ValueError 泄漏(inference_job 访问顺序) | `prepare_inference` guard 移到 accessor 使用之前 | CLOSED(fixed `0d0970b`) |

R1 其余专项结论(无 finding):guard 拒绝后五状态零变化;rebind 单次 commit/undo-redo 完整/旧 run 快照保留;validate 拒绝矩阵(active 指向非法 run、跨 video、双 experiment、v1 混装、members 乱序等);calibration stale 覆盖;`save_as_publication` 失败后 session 状态零变化。`apply_tracking_candidate` 的 `is` 身份检查使过期候选结构性不可写入。

## R2 — schema / migration / data-loss 专项

Verdict(初审):NEEDS-FIX → 全部 findings 已修复并复测(下表)。方法:代码走读 + 全量测试 + 7 个 /tmp 对抗性验证脚本(旧 serializer 字节级对照、30+ 类恶意 payload、迁移故障注入、undo/redo 混合序列、binding 篡改、task-result 交换)。

| Finding | 摘要 | 处置 | 状态 |
| --- | --- | --- | --- |
| F1 (Major) | joint run 在场时 `_check_validation_series_removal`/`correct_suggested_frame` 经 `run.track_id` 抛裸 ValueError,validation series 删除/undo 永久不可用 | 两处改成员判断;review 路径对多成员 run 显式 ProjectSessionError。回归:`test_validation_series_ops_survive_joint_run_presence` | CLOSED(fixed `d999ad7`) |
| F2 (Major) | 两步流(先迁移后 `create_pendulum_experiment`)不清 legacy 单轨 active 指针,guard 封死后无清理路径 | `create_pendulum_experiment` 对四个新 bound track 执行与迁移一致的 strip(归档保留)。回归:`test_create_experiment_strips_legacy_active_pointers` | CLOSED(fixed `d999ad7`) |
| F3 (Minor) | 迁移静默丢弃与 v2 顶层键(`experiments` 等)同名的 v1 未知 sibling | `save_as_publication` fail closed 拒绝并点名冲突键。回归:`test_migration_rejects_v2_colliding_extra_keys` | CLOSED(fixed `d999ad7`) |
| F4 (Minor) | active run 的 role_bindings 与当前 roles 置换不一致时加载不拒绝(契约 §2"加载时也验证") | active 指针校验补 `run.role_bindings != experiment.roles → raise`。回归:`test_active_run_role_binding_permutation_rejected` | CLOSED(fixed `d999ad7`) |
| F5 (Nit) | v1 manifest 键序改变(tracking_runs 移末尾) | v1/v2 writer 显式排序,恢复原布局 | CLOSED(fixed `d999ad7`) |
| F6 (Nit) | serializer 直调时 `2.0`/`True` 因 Python `==` 语义误入 v2/v1 分支 | dispatch 前置 bool/非 int 拒绝。回归:`test_serializer_dispatch_rejects_non_integer_schema_version` | CLOSED(fixed `d999ad7`) |
| F7 (Nit) | 缺键 payload 抛裸 KeyError | `payload_helpers.string/integer/number` 缺键抛带键名 ValueError | CLOSED(fixed `d999ad7`) |

R2 通过项(无 finding):v1 纯净性(域层+serializer 双保险,generic 项目不可能被写成 v2);v2 读侧 30+ 类恶意 payload 全拒绝;迁移 8 类故障注入下源目录零改动、staging 总保留、migration SHA 对应磁盘原件;快照一致性(9 元组在 undo/redo/accept_* 全路径一致);dispatch 边界;双 codec(v2 中 generic/legacy run 语义一致)。

## Verification

- 修复后全量:`python -m pytest` **899 passed, 9 subtests**(基线 804 + P1.1 新增 95);`compileall` 通过。
- 新增测试文件:`tests/test_pendulum_experiment.py`、`tests/test_project_serializer_v2.py`、`tests/test_publication_migration.py`、`tests/test_pendulum_session.py`(含 R1/R2 回归);更新 `tests/publication/test_legacy_reader_boundary.py`(v2 合法 payload 现在应加载,缺/未知 capability 仍拒绝且 manifest 不动)。
- 测试机械迁移(TrackingRun `track_id`→`member_track_ids`)由独立 Flash agent 完成(9 文件 20 处),其发现的唯一真实回归(`training_job.py:223` 关键字漏改)由实现方修复。
- 两个 Reviewer 均只读;R1 初次启动的 code-reviewer agent 因缺思考档位配置失败,改用 general-purpose(同 Flash)完成;`~/.zcode/agents/code-reviewer.md` 已补 `$high` 档位待下次会话生效。

## R3 — S5/S6 最终复审(2026-09-21)

Reviewer 只读复审 S5(`55ce737`)/S6(`0fd3494`),方法:代码走读 + 全量 917 passed + 4 个 /tmp 探针。初审 Verdict:NEEDS-FIX → 全部 findings 修复复测(920 passed,commit `157ed8e`)。

| Finding | 摘要 | 处置 | 状态 |
| --- | --- | --- | --- |
| S6-R1 (Major) | pivot/true vertical 写入后视频上无持久标记,偏离 HR-3.2 语义(探针实证 scene 零几何图元) | `PendulumOverlayView` 只读视图模型 + `VideoView.set_pendulum_overlay`(十字 pivot、虚线未确认/实线已确认 vertical + down 标签),`_refreshPendulumOverlay` 从 experiment.geometry 投影。回归:`test_geometry_overlay_persisted_after_writes` | CLOSED(fixed `157ed8e`) |
| S6-R2 (Minor) | `_failure_message` 残留使后续 autosave 失败被误报为迁移失败(探针复现) | `_poll` finally 清空。回归:`test_migration_failure_shows_three_question_message_and_keeps_session` 路径覆盖 | CLOSED(fixed `157ed8e`) |
| S6-R3 (Minor) | 向导缺省四组合框同选第 0 项必报重复;<4 track 无创建出口 | ≥4 track 预填四个不同 track;每 role 提供 "New track" 创建按钮(session 回调);<4 track 不再死路。回归:preselect/create-button 两用例 | CLOSED(fixed `157ed8e`) |
| S6-R4 (Nit) | 迁移成功状态栏不含副本路径 | 状态栏附 `project_root` | CLOSED(fixed `157ed8e`) |
| S6-R5 (Nit) | rootless 首存沿用"原项目不动"文案 | `first_save` 参数切换文案 | CLOSED(fixed `157ed8e`) |
| S6-R6 (Nit) | 点选模式不清 track 选择;seekFrame 退出不隐藏引导条 | 入口 `clearSelection()`(与 scale/origin 一致);seekFrame 分支隐藏引导 | CLOSED(fixed `157ed8e`) |
| S6-R7 (Nit) | 直创建路径不检查 tracking.pending | 与迁移路径相同的 pending 检查 | CLOSED(fixed `157ed8e`) |

R3 指定审查项结论:GUI 单一事实源通过(setup 写入全经 ProjectSession,完整性只算于 `pendulum_setup_status`,向导只持 draft);G1/G2/F2/F4 关闭项抽查无回归;HR 协议除 R1(已修)外全部对齐;线程边界/`_run` 扩展/错误处理合格。

## Final verdict

三轮 review(R1 guard 专项、R2 schema 专项、R3 S5/S6 终审)的全部 findings 已修复并复测;最终验证 `python -m pytest` **920 passed, 9 subtests** + `compileall` 通过。剩余 gate:**Human Review(用户照 publication/plans/p1.1-human-review.md 执行)**,通过后合并回 `publication/ejp-damped-pendulum` 并收尾。

## Boundary

真实 DLC smoke 不适用于 P1.1(计划明确无 AI 验收);Windows G1–G4 仍为批准的 P6 前门禁;P1.2–P1.4 未开始。
