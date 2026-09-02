# Phase 5 — AI-assisted Annotation & Refinement 需求规范

> 状态：**Accepted（2026-09-01；Phase 5.0 已完成，等待 5.1）**
> 本文定义产品边界、数据语义与验收口径；除标明完成的 R0 外，其余需求尚未实现。实施顺序见
> [PHASE_5_PLAN](../status/phase-5-plan.md)。Phase 4 基线见
> [Phase 4 requirements](phase4-requirements.md)、[ADR-0011](../decisions/0011-deeplabcut-integration-architecture.md)、
> [ADR-0012](../decisions/0012-gui-tracking-task-boundaries.md) 与
> [Phase 4 review](../reviews/phase4-architecture-reliability-review.md)。

---

## 1. 目标与边界

### 1.1 目标体验

```text
初始代表帧 → 用户标注 → 训练 → 推理
                         ↓
候选池 → 排名 → 时序去重/视觉多样性 → Top N 建议帧
                         ↓
查看预测 → Accept / Correct / Skip → 更新训练数据
                         ↓
Training Advisor → resume 或重新训练 → 固定验证集比较 → 新一轮推理
```

AI 只负责指出“哪些帧值得看”和解释原因；用户负责提供正确标签。

### 1.2 硬性不变式

1. **模型预测永不自动成为 ground truth**。只有用户产生的 active manual `TrackPoint` 才能进入训练标签。
2. **Accept 不是标注**：只记录“用户检查过、当前预测可接受”，不复制预测坐标到 manual 数据。
3. **Correct 才产生训练标签**：沿用 manual last-wins，并保留被遮蔽预测的 run provenance。
4. **Skip 不产生标签**：不把遮挡、模糊或无效画面伪造成坐标。
5. **推荐与事实分开**：confidence、coverage、困难帧分数是筛查信号；精度比较只使用人工固定验证数据。
6. **训练不会自动循环**：Advisor 只提出下一步和理由，训练/替换结果仍需用户显式启动或确认。
7. **first-wins 保持不变**：新推理不会静默覆盖当前 AI 结果；替换通过显式、原子的 run 激活操作完成。

### 1.3 明确不做

- 不做完整 HPO、Bayesian optimization、Population Based Training 或无限自动训练。
- 不自动调整 learning rate、scheduler、optimizer、网络结构或 augmentation。
- 不提前实现 Phase 7 模型库、跨项目模型版本管理或模型发布。
- 不引入主动学习模型、embedding 模型或新依赖；第一版使用 DLC 能力与可解释规则。
- 不扩展多目标、多 bodypart、多视频联合训练或遮挡类别标注。

---

## 2. 当前基线与 DLC 3.0.1 复核

### 2.1 当前 `main` 可承接能力

- `TrackingRun` 已保存训练/推理参数、snapshot、评价、run 目录与导入统计。
- `TrackPoint.source_detail` 可关联 infer run；manual 修正会遮蔽但保留预测。
- 原始 DLC HDF5/CSV 保存在 run 产物中，可读取被 `min_confidence` 过滤掉的帧，不必把所有低置信度预测写入领域层。
- `TrackStore.clear_engine_run()` 已有领域实现，但没有 session/GUI 闭环（Review F2）。
- Phase 5.0 已删除旧 coordinator 的 start/poll/cancel 生命周期；训练/推理现统一走 `TrackingJobRunner + TrackingActions + BackgroundTaskRunner`（Review F3 Closed）。
- 当前 `TrackingRun.config/extra_fields`、run 目录与 project 扩展字段可先承载迭代证据；本规划不先改 schema。

### 2.2 DLC 能力映射

| 能力 | DLC 3.0.1 现状 | Phase 5 取舍 |
| --- | --- | --- |
| 初始取帧 | `extract_frames` 支持 `uniform`/`kmeans`；底层工具可返回 frame index | **直接复用算法**，由 `DLCAdapter` 包装成无 Qt、返回帧号的后台能力；K-means 默认，uniform 可选 |
| 困难帧 | `extract_outlier_frames` 支持 `uncertain`、`jump`、`fitting`，再以 uniform/K-means 抽取 | 复用输入格式、启发式定义与 primitives；本项目补综合排名、解释和去重 |
| 人工 refinement | `refine_labels` 启动 napari 编辑 `machinelabels` | **不嵌入**；Suggested Frames UI 保持 ProjectSession 为唯一标注真相 |
| 合并数据 | `merge_datasets` 合并 DLC machine labels 并增加 config iteration | **不作为内部迭代模型**；每轮从 canonical manual TrackPoint 导出 |
| 固定 split | `create_training_dataset` 接受显式 `trainIndices`/`testIndices`；`mergeandsplit` 可冻结 split | **直接复用**；validation 成员后续不得静默进入训练 |
| 继续训练 | PyTorch `train_network(..., snapshot_path=...)` | **直接复用**；resume/restart 由用户决定 |
| snapshot 评价 | `evaluate_network(..., snapshotindex=...|"all")` | **直接复用**；本项目关联 fixed split、iteration 与 delta |

高层 `extract_outlier_frames` 一次只选择一种 outlier algorithm，主要把结果写进 DLC `labeled-data`，
不返回“综合分数 + 原因 + 跨规则去重”的候选对象，因此只能作为参考/基线，不能单独满足 Suggested Frames 契约。

---

## 3. 功能需求

### R0 任务编排单轨化（Review F3）

> **实现状态**：✅ Phase 5.0 于 2026-09-02 完成，F3 Closed；证据见
> [phase-5.0-plan.md](../status/phase-5.0-plan.md) 与
> [phase-5.0-review.md](../reviews/phase-5.0-review.md)。

1. Phase 5 新任务接入前，收敛旧 `TrainingCoordinator`/`InferenceCoordinator` 的 start/poll/cancel 生命周期。
2. 保留统一管线仍使用的 prepare/read helpers；`TrackingJobRunner` 统一启动、`BackgroundTaskRunner` 管进程/句柄、`TrackingActions` 管轮询/取消触发/活动 session 提交，三者构成唯一生命周期路径。
3. 取消、迟到结果、会话归属、恢复与错误状态只维护一套规则。
4. 本项是独立 5.0 清理 Subphase，不与主动学习功能混批。

### R1 初始代表帧

1. 第一次训练前可为当前 video/track 请求 N 个建议帧，只扫描 Timeline working zone。
2. 默认 DLC K-means visual selection；DLC uniform selection 作为快速选项和基线。
3. 排除已有 active manual 帧；候选不足 N 时返回实际数量，不重复帧。
4. 后台执行、可取消；记录算法、N、seed、working zone、`cluster_step` 与颜色模式等实际参数。
5. 结果只是 frame index 建议，不直接创建 manual 点。
6. 不自研第二套 K-means；DLC 小版本兼容只在 adapter 内处理。

### R2 困难帧挖掘

1. 输入绑定一个 completed infer run 及其 video/track/model/snapshot/原始预测，不混合不同 run。
2. 读取全帧原始预测，包括导入阈值以下与缺测帧，不能只读 `effective_points()`。
3. 第一版 candidate pool 至少覆盖：低 confidence/缺测、相邻帧 jump、raw 相对局部平滑轨迹的异常残差、此前 Correct 帧邻域。
4. 每个候选保留 component scores、触发原因和 run；固定默认权重可记录，分数不伪装成概率。
5. 固定流程：

   ```text
   candidate pool → score/rank → temporal de-duplication → visual/temporal diversity → Top N
   ```

6. 连续异常片段不能垄断队列；候选不足时才放宽最小间隔，并明示实际数量。
7. 视觉多样性优先复用 DLC K-means primitive，不引入 embedding 模型。
8. Accept/Skip 按 infer run 抑制本轮重复建议；新 infer run 可重新评估，Correct 的 manual 点长期保留。

### R3 Suggested Frames Review & Correction

1. 队列显示当前候选帧、现有 AI prediction、建议原因/分数、进度和前后导航。
2. **Accept** 只记录 reviewed/accepted；**Correct** 写入 manual point 并保留原预测；**Skip** 不产生坐标。
3. Correct 复用现有 screen→pixel、manual last-wins、Undo/Redo 与 marker 刷新。
4. 保存/重开可恢复已提交 disposition 与 Correct 点；未提交点击不落盘。
5. 结束显示 reviewed/accepted/corrected/skipped/remaining，并可生成 Advisor 建议。

### R4 推理结果激活、清除与替换（Review F2）

1. 区分“completed infer run”与“当前激活为轨迹的 infer result”。
2. 后续推理先完整保存 run 与原始预测，不得因 first-wins 的 0 inserted 被误报为无结果。
3. 用户显式 Activate/Replace 时，原子完成：清除当前 AI 观测、导入所选 run、保留全部 manual、标记 DerivedData stale、记录新旧激活关系与统计。
4. 替换前确认影响范围；支持 Undo/Redo，失败不得留下半批结果。
5. Clear 只移除当前 AI 观测，不删除 manual、TrackingRun、模型、原始 HDF5/CSV 或日志。
6. 旧 run 仍可比较和重新激活；原始产物缺失时明确禁用。

### R5 Refinement Iteration 与 Evaluation History

每轮至少可追溯：iteration/parent、manual/training/fixed-validation labels、new corrections、
accepted/skipped、training parameters、resume/restart、source/produced snapshot、train/fixed-validation evaluation、
全视频 coverage/confidence、remaining difficult frames 与 review yield。

1. 首个具备足够人工标签的可比较 iteration 固定 validation membership；后续困难帧默认进入 training。
2. fixed validation 标签若需修订，显式开启新的 evaluation series；不重写旧轮结论。
3. train/validation RMSE 与 confidence coverage 分栏展示，coverage 不能代替 ground-truth 精度。
4. 标签过少时允许训练，但标记“无可比较 fixed validation”，Advisor 不得声称精度提升。
5. 5.4 才冻结持久化设计；若必须改 schema，先更新 spec/ADR 并请求用户批准。

### R6 Refinement Retraining

1. 训练数据只来自 canonical active manual TrackPoint，并排除 fixed validation frames。
2. 复用 DLC `create_training_dataset` 显式 split，不每轮随机重分。
3. 支持 Resume/fine-tune（选择 completed snapshot）与 Restart（不加载旧 snapshot）。
4. 复用 DLC snapshot resume、epochs、batch size、device 与评价；实际参数全部进入 run 记录。
5. 训练完成不自动替换当前轨迹；仍需推理、比较和显式激活。

### R7 Training Advisor（规则型第一版）

输出必须包含建议动作、参数、证据和限制；用户可把建议带入表单，但仍需手动启动。

| 建议项 | 第一版边界 |
| --- | --- |
| 是否继续训练 | train/validation 都差且仍改善时建议有限追加 epochs；停滞时不建议盲目续训 |
| 再标多少帧 | 根据未审候选、review yield 和多样性缺口给出有上限数量 |
| 先修帧或先训练 | train 好而 validation 差、或困难帧集中时优先增加多样 manual labels |
| resume/restart | 数据兼容且少量新增同目标标签时优先建议 resume；持续恶化、来源不兼容或公平从头比较时建议 restart |
| additional epochs | 从预设小档位给有限追加量，不自动循环 |
| batch size | 沿用最近成功值；OOM 后建议降低；无硬件证据时不自动增大 |
| snapshot | 只按同一 fixed-validation series 选择；无可比 validation 时不声称“最佳” |

### R8 可靠性与用户边界

1. 选帧、挖掘、训练、评价、推理均走统一后台生命周期，可取消且不阻塞 GUI。
2. 提交前复核 session/video/track/run/snapshot；取消、错误和迟到结果不污染活动项目。
3. working zone、0-based frame、时序授权和保存/切换语义沿用既有 ADR。
4. Suggested Frames 与激活/替换必须 Human Review；自动化测试不能替代。

---

## 4. Subphase 划分

| Subphase | 名称 | 独立交付 |
| --- | --- | --- |
| 5.0 ✅ | Tracking Pipeline Consolidation | F3 Closed；统一 runner/actions/task handle 生命周期，无新产品能力 |
| 5.1 | Representative Frame Selection | DLC uniform/K-means 建议帧；后台、可取消、可复核 |
| 5.2 | Difficult Frame Mining | 原始预测候选池、可解释评分、时序去重、DLC 视觉多样性、Top N |
| 5.3 | Suggested Frame Review & Correction | Accept/Correct/Skip、provenance、恢复与 Human Review |
| 5.4 | Iteration History & Result Activation | fixed validation/history；处理 F2 clear/activate/replace |
| 5.5 | Training Advisor & Retraining | 规则建议、resume/restart、snapshot/epochs/batch size、跨轮比较 |
| 5.6 | Refinement Loop Integration & Acceptance | 单摆闭环、量化对比、全回归、独立 review 与 Human Review |

---

## 5. 验收标准

| # | 验收标准 | 判定方式 |
| --- | --- | --- |
| AC-1 | DLC uniform/K-means 在 working zone 返回去重帧号、排除 manual、不自动造标签 | adapter/mock + 合成视频 |
| AC-2 | 挖掘消费指定 infer run 的全帧原始预测，低置信度/缺测不因 Phase 4 导入阈值消失 | 单元/集成测试 |
| AC-3 | pipeline 顺序被测试固定，连续异常段不会垄断 Top N | 合成轨迹测试 |
| AC-4 | 每帧有可解释原因；同输入/参数/seed 可复核 | 单元测试 + Human Review |
| AC-5 | Accept 不加 label；Correct 保留预测 provenance；Skip 不造坐标；保存重开一致 | session/GUI + Human Review |
| AC-6 | completed 新 run 可显式激活；clear/replace 不丢 manual/旧产物，原子、可撤销、派生 stale | domain/session/GUI |
| AC-7 | 至少两轮使用同一 fixed validation；分开显示 RMSE 与 coverage/confidence | 持久化 + 真实 DLC |
| AC-8 | Advisor 覆盖 labels、resume/restart、epochs、batch size、snapshot，建议有限且不自动训练 | 规则表测试 |
| AC-9 | 单摆完成一次建议→Correct→再训练→再推理→比较→激活闭环，报告三类 delta | 真实 DLC 记录 |
| AC-10 | 冻结人工审计集上报告 Precision@N/review yield，并优于 lowest-confidence-only Top N 基线 | 基准实验 |
| AC-11 | F3 关闭后只维护一套任务生命周期；全回归与独立 review 通过；仅当有用户可感知交互变化时追加 macOS Human Review | 架构/回归/Review；交互变化时 Human Review |

AC-9 不假定每轮必然改善：未改善时必须如实显示并给出停止/补标建议；但 Phase 5 收尾前仍需记录
至少一次冻结基准上可复现的 refinement 改善证据。

---

## 6. 延期到以后

- learning rate/scheduler/optimizer、网络结构与 augmentation 自动优化；
- Bayesian/HPO、多 trial、自动 early-stopping 搜索；
- ensemble、蒸馏、伪标签、自训练和自动接受高 confidence prediction；
- Monte-Carlo dropout、专用 uncertainty/embedding 主动学习模型；
- Phase 7 模型库、跨项目 lineage；多目标/多关键点 identity correction；
- Windows/CUDA 真机验收仍按既有批准延期到 Phase 9 前专门关卡。
