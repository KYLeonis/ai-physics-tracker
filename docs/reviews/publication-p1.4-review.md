# Independent Review — Publication P1.4

- Date:2026-09-29;Scope:P1.4 S3(四轨激活事务/数据丢失专项)与 S5(P2 adopted measurement 科学语义专项)。分支 `feat/p1.4-joint-inference-activation`,对象 commits `d047950`/`13702dd`(S1 `7169b97` 的推理协议已由实现时专项验证,不在本轮两道 gate 范围)。Reviewer 为两个 fresh-context 只读 code-reviewer subagent(分别独立派发、各自探针实证);处置由实现方(主会话)完成并复测。
- 依据:[数据合同](../../publication/spec/experiment-run-derived-contracts.md) §3–§6/§8、[scientific-profiles](../../publication/spec/scientific-profiles.md)、[P1.4 执行 mini-plan](../../publication/plans/p1.4-joint-inference-activation-execution.md) S3/S5、CODE_STANDARD。
- 两道 gate 首轮 verdict 均 **approve**(无 Blocker/Major);Minor/Nit 由实现方全部处置闭环,无未关闭 finding。S3/S5 gate 通过,进入 S4 UI。

## S3 四轨事务/数据丢失专项

| ID | 摘要 | 处置 |
| --- | --- | --- |
| m1 (Minor) | 激活复核经 `_capture_input` 要求模型当前 live compatible 且模型文件在位;推理后模型目录被移走 → candidate 永久无法激活也无法重推(工作流死端),与合同 §4「模型文件缺失只阻断新 infer」冲突 | CLOSED(代码):激活复核不再依赖 live 模型,改为按 run 冻结身份独立复核——当前视频 SHA vs `extra_fields["video_sha256"]`、`input_digest` config/extra 自洽、`verified_min_confidence` 一致,`read_experiment_candidate` 继续负责 binding/artifact SHA/frame_count;bodypart_mapping 一致性由 verify 期冻结 + artifact SHA 结构性覆盖。回归 `test_joint_activation_survives_missing_model_files`(删模型后激活成功 + 视频替换后仍拒绝) |
| m2 (Minor,实证) | `review_experiment_frame`/`create_experiment_review_queue` 只复核 artifact SHA,不复核 source video 替换;reviewer 探针证实替换视频后 Correct 仍写入 manual 点(旧候选坐标 vs 新画面错位,manual 直接成为测量真值) | CLOSED(代码):两个入口增加当前视频文件 SHA 与 run 冻结 `video_sha256` 对比,不一致即拒绝("joint candidate video changed after inference",与 adopted measurement 同语义)。回归 `test_joint_review_rejects_replaced_source_video`(Correct 与建队列双拒绝 + 零变化断言) |
| m3 (Minor,测试缺口) | 状态机拒绝路径零测试:无 active 时 Replace/Clear、已激活再 Activate、Replace 传当前 active run、artifact 被删后激活 | CLOSED(测试):`test_joint_activation_rejects_invalid_state_matrix` 覆盖全部四类拒绝 + 零变化断言 |
| m4 (Minor,测试缺口) | 错误注入只覆盖第三 role,未覆盖第四 role | CLOSED(测试):`test_joint_activation_failure_on_fourth_role_keeps_original_snapshot`(tip 注入,整 Project 相等断言) |
| n1 (Nit) | TrackPoint 装配在 per-role try 外,异常类型不一致(实际不可达,解析器已拒 Inf) | CLOSED:装配纳入同一 try,统一包装 `ProjectSessionError` |
| n2 (Nit) | P1.4 新增代码 docstring/注释为英文,违反 CODE_STANDARD §198 | CLOSED:experiment_review / adopted_measurement / project_session 新段全部中文化 |
| n3 (Nit) | `_capture_input` 弱类型注解;manual 计数逐 role 重扫全量 observations(O(n²)) | CLOSED(部分):O(n²) 消除(replace 不触碰 manual,循环外一次统计);注解维持现状——激活已不调用 `_capture_input`,剩余调用方(prepare/verify)解包全部字段,可读性可接受 |

Reviewer 确认无问题方向:单次提交原子性(局部 store + `_commit_project` 两行赋值无中间抛错点)、错误注入零变化(整 Project 相等)、undo/redo 全维度覆盖与 peek 先校验、Clear/Replace/激活后 Correct 的 manual 保留、`activation_history`/`measurement_revision` 域模型与重开一致、`active_infer_run_id` 加载期域校验、artifact 路径逃逸防护、NaN/Inf 过滤链、review 记录与 manual point id 一致性、`delete_active_manual_point` 对 joint review 的联动回滚、legacy guard 六入口矩阵、TOCTOU 记录为协议固有局限。

## S5 P2 handoff 科学语义专项

| ID | 摘要 | 处置 |
| --- | --- | --- |
| m1 (Minor) | `missing_reasons_by_role` 只有 `no_adopted_point`,低置信被筛与 DLC 无预测不可区分;数值不受污染但损失追溯粒度 | CLOSED(文档):P1 快照语义(缺测显式、不置 0)已满足;快照冻结 `prediction_sha256`,原始 per-role 缺测统计在 candidate artifact(`missing_by_role`)/run extras,可回溯。P2 立项时若需缺测原因分布,从 artifact 重算——记入本文件作 P2 注意事项,不为此改 P1 数据形状 |
| m2 (Minor) | frozen dataclass 的 `payload` 仍是可变 dict,"只读交付物"靠约定 | CLOSED(文档):P2 消费边界规则定为「使用前必须 `assert_adopted_measurement_current`」(篡改检出已测试钉住:改 payload 坐标 → stale,还原 → 通过);P2 立项时在消费入口强制该调用。MappingProxyType 方案否决——canonical digest 走 json 序列化,包装类型破坏 digest 兼容 |
| m3 (Minor,测试缺口) | AI confidence 原样、缺测 reason、calibration/physical/release/revision 各自 stale、mixed-run、篡改检出未钉住 | CLOSED(测试):`test_adopted_measurement_screens_roles_and_flags_dependency_stale`(min_confidence=0.95 全筛 → 四 role 显式缺测 reason;physical/release/calibration/Correct-revision 四类变更各自 stale 且 undo 恢复)+ `test_adopted_measurement_rejects_foreign_ai_and_tampered_payload`(外源 AI 点拒绝 + payload 篡改检出/还原)。防御分支(active_run_id 不一致、无 input_digest)不可达构造,由构造期校验结构性覆盖 |
| m4 (Minor) | `assert_adopted_measurement_current` 每次重建快照并全量视频哈希(O(视频字节)) | CLOSED(文档):调用节奏定为 P2 每次「激活分析」一次,不逐帧调用;P2 若需高频再议 size/mtime 预检 + 周期全量 SHA。记入本文件 |
| n1 (Nit) | assert 内部 build 的具体错误(如 video changed)穿透,不统一为 stale | CLOSED:外层包装为 "adopted measurement snapshot is stale: <原因>",保留 cause 与原信息 |
| n2 (Nit) | mixed-run 文案也会命中绑前遗留外源点,诊断误导 | CLOSED:文案改为 "AI observations not from the current active run" |

Reviewer 确认无问题方向:只读性(构建前后 undo 栈深度不变,实测)、Qt-free import 链全量 grep、CFR 帧→时间换算与 release-relative 逐字对齐 P0.1 student 语义(负时间保留、无 release 显式 None)、manual 优先/AI 不补位/superseded 过滤、confidence 域不变量(manual null / AI ∈[0,1])、fixed/tracked pivot 字段分离、calibration/physical/release provenance 冻结、digest 确定性与输入敏感性(实测)、视频替换守卫全链闭环(prepare→verify→activation→snapshot)、P1 无越界科学计算。

## P2 立项时注意事项(本轮记录,非 P1 缺陷)

1. 缺测原因分布(m1):从 candidate artifact(`prediction_sha256` 回溯)重算,或扩展 activation 冻结筛选统计。
2. payload 消费边界(m2):P2 入口强制 `assert_adopted_measurement_current`,禁止直接长期持有可变 payload 当真值。
3. assert 调用节奏(m4):每次分析激活调一次;高频场景加轻量预检。
4. qc_overoverrides 尚未在 src 实现(reviewer 对照合同 §8 指出):P2 把 QC exclusions 纳入 payload+digest 时一并定形。

## S6 最终 lifecycle/persistence 复审(2026-09-30)

- 触发:mini-plan Review Gate 第三道;重点为 S4 交互语义转变(审核关卡→训练帧推荐/连续重标批量流,commits `72cbfff`/`ef63a38`/`ec2f34e`/`c794e18`)后的数据一致性与生命周期完整性。Reviewer fresh-context 只读,独立实证(自建 undo/redo 混合序列探针、pool 膨胀最小复现)。
- 首轮 verdict **request-changes**(1 Major);处置:
  - **F1 (Major) CLOSED**:`experiment_difficulty_pool` 以 `fixed_pivot_px=None` 计算,tip 半径诊断全帧失败→几何补扫把全部帧计入池(60 帧干净数据实测 pool=60)。修复:pool 与 queue 用同一 fixed pivot,且无 pivot 时几何补扫跳过(fail-closed 而非全收);新增内容级测试(干净数据+3 弱帧→pool 恰为弱帧集);依赖旧 bug 行为的 unit fixture 改用帧间跳变信号。
  - **F2 (Minor) CLOSED**:workflow 投影 `candidate_reviewed`(跨批累计)与 `candidate_total`(当前批)分母不一致——reviewed 改为「当前批 suggestion_frames 中已有 record 的帧数」。
  - **F3 (Minor) CLOSED(文案)**:skip 是 GUI 簿记不持久化(有意:推荐是可选建议),下一批消息明示「skipped frames may reappear until labeled」。
  - **F4 (Nit) 记录**:busy 期间按钮单向禁用——同次 sync 的 `_update_selection` 分支已自愈,不改。
  - **F5 (Nit) 记录**:重算在 GUI 线程两遍 mining;84 帧实测无感,长视频优化留 Phase 9。
  - **F6 (Nit) CLOSED**:smoke 脚本随 S6 改动一并提交。
- Reviewer 确认无问题方向:重算合并与校验闭环(records⊆candidates 不变式)、批量流写路径单一性(全部经 session 事务)、帧集/fixed-check fail-closed、推荐算法确定性、S3/S5 已关闭 finding 的守卫在语义转变后完整无损(video SHA/冻结身份/模型解耦三守卫)、undo/redo 跨动作边界、save/reopen 一致性。
- 处置后全量:**1154 passed, 9 subtests**(基线 1153 + 1 pool 内容测试)。

## Verification

- 处置后全量回归:**1137 passed, 9 subtests passed**(review 前基线 1131;新增 6 个 review 回归测试)。
- Reviewer 各自独立运行专项 8 tests 通过;S3 reviewer 另以探针实证 m2(替换视频后 Correct 放行)与 dirty 语义排除;S5 reviewer 以探针实证 undo 隔离、负时间、digest 稳定性与篡改检出。
- S6 最终 lifecycle/persistence re-review 按 mini-plan Review Gate 另行执行后记入本文件。
