# Subphase Plan — Phase 5.2 Difficult Frame Mining

- Issue：[#19](https://github.com/KYLeonis/ai-physics-tracker/issues/19)
- 分支：`feat/p5.2-difficult-frames`
- 日期 / 状态：2026-09-02 · 🚧 代码与基准工具链完成；冻结审计集待用户标注（见 Result）

## Goal

从一个已完成的 infer run 的全帧原始预测中，确定性地产生少量、可解释、时间上去重且
具有视觉/时序多样性的困难帧候选；低于 Phase 4 导入阈值和缺测的帧不得丢失。
对应 spec R2、R8 与 AC-2/AC-3/AC-4，并为 5.3 的审核队列提供 Qt-free 输入。

## Scope

**做**：

- 在 DLC 适配边界公开经过严格校验的全帧 raw prediction 读取结果，字段统一为
  `frame_index/pixel_x/pixel_y/confidence`；缺测只存在于内存计算层，不生成 `TrackPoint`。
- 定义 Qt-free 的 mining params/request/candidate/result；请求绑定 completed infer run、
  video/track/model snapshot、原始预测文件指纹、working zone、seed 和全部算法参数。
- 第一版候选信号：低 confidence/缺测、相邻帧 jump、raw 相对 Savitzky-Golay 局部平滑
  轨迹的残差，以及显式传入的既有 Correct 帧邻域。
- 固定策略顺序：candidate pool → component normalization + weighted rank → temporal
  de-duplication → visual/temporal diversity → Top N；每个候选保留分量、原因和 infer run。
- 复用 5.1 已有 K-means 特征提取/聚类路径，对“显式候选帧集合”做视觉多样化；不再实现
  第二套聚类。视觉特征不足时按已有分数顺序补齐，不静默改变候选分数。
- 使用 `BackgroundTaskRunner` 执行 mining；支持取消、输入文件复核与原子结果文件写入，
  worker 不持有活动 `ProjectSession`，GUI/会话切换语义留给 5.3。
- 建立可复现 benchmark：开发集用于阈值/权重调整；冻结审计集只做最终评估，报告
  `Precision@N`、review yield 和 lowest-confidence-only Top N 基线。

**不做**：

- 不新增 GUI、Accept/Correct/Skip、审核进度持久化或保存重开恢复（5.3）。
- 不改 `project.json` schema、不新增 `TrackingRun.task_type`、不修改 AI 结果激活语义（5.4）。
- 不自动创建/修改 manual 或 AI `TrackPoint`，不把候选分数伪装成定位误差或概率。
- 不引入 embedding/主动学习模型、新依赖、DLC napari refinement 或高层
  `extract_outlier_frames` 的文件副作用。
- 不做自动训练、fixed validation、Advisor 或 resume/restart（5.4–5.5）。
- 不在冻结审计集结果出来后反向调权；未优于基线时如实记录并回到开发集调整后重新冻结
  一份新的、带版本号的审计集，旧结果保留。

## Deferred Findings（顺带完成项）

来自 [runtime review](../reviews/phase-5.0-5.1-runtime-review.md)（Issue [#18](https://github.com/KYLeonis/ai-physics-tracker/issues/18)，F1/F2/F3a/F5 已在 5.2 开工前修复）。以下三项随本 Subphase 或 5.3 顺带完成，不改变本计划 scope：

- **F3b**：`dlc_adapter.py` 的 `_kmeans_via_dlc` 实际不经过 DLC（sklearn 直连），改名
  `_kmeans_via_sklearn` 并修正相关 docstring（含模块级"依赖 DLC FrameExtractor"的过时描述）
  → 随 **Slice 3** 触碰 `dlc_adapter.py` 时顺带，不单独占用提交。
- **F4**：选帧无用户取消入口、取消结果显示为 "Failed: Frame selection cancelled"
  → 随 **5.3** 处理：本 Subphase 明确不新增 GUI，且 5.2 的 mining 任务落地后，
  取消交互应在 5.3 为"选帧/mining 后台任务"统一设计一次（含非 Failed 措辞）。
- **F6**：`task_panel.py` 算法下拉用 `"k" in text` 启发式映射算法 ID
  → 随 **5.3** 改为 `addItem(data=...)` 显式映射；纯实现细节，行为不变。

## Proposed Defaults and Semantics

这些值是待本计划批准的第一版默认值；全部进入结果参数快照，后续只能在开发集上调整：

| 项目 | 第一版语义 |
| --- | --- |
| `confidence_threshold` | `0.6`，与现有 GUI 推理默认值一致；缺测的 uncertainty 分量固定为 `1.0` |
| jump / residual 触发 | 对有效连续段分别计算像素距离，以 median/MAD 的 robust z-score `>= 3.5` 判异常；MAD 为零时仅把严格大于 median 的值视为异常 |
| residual 平滑 | 复用 `domain.kinematics.smooth_savgol`，默认 `window_length=7, polyorder=2`；短段/缺测行为沿用 ADR-0008 |
| component normalization | 仅在当前 candidate pool 内做确定性的 percentile rank，得到 `[0, 1]` 分量，不称为概率 |
| weights | uncertainty `0.40`、jump `0.25`、residual `0.25`、prior-correction neighborhood `0.10` |
| prior correction 邻域 | 调用方显式传入 Correct 帧；默认半径 `2` 帧，5.2 无历史时为空 |
| temporal de-duplication | 按总分降序贪心选择，默认最小间隔 `0.25 s`；候选不足 N 时逐级放宽并记录实际间隔/数量 |
| visual diversity | 从时间去重后的高分 shortlist（最多 `4N`）中复用 K-means 选至多 N 帧；最终候选仍按总分排序 |
| benchmark 指标 | `Precision@N = needs_review / actual_n`；`review_yield = needs_correction / actual_n` |

实现前先为新目录建立 `docs/benchmarks/README.md` 约定；开发集、冻结审计集与报告分别使用
`phase-5.2-development.csv`、`phase-5.2-audit-v1.csv` 和 `phase-5.2-report.md`。审计表取困难帧
策略 Top N 与基线 Top N 的候选并集，打乱并隐藏来源/排名后再人工判定；每行只记录
`frame_index`、`needs_review`、`needs_correction` 和短备注。视频、模型和预测文件不入 Git，
只在报告记录内容标识和对应 infer run；`needs_correction => needs_review`。

## Acceptance Criteria

- [x] 指定 completed infer run 的 HDF5/CSV 被全帧读取；低于导入阈值与缺测帧仍进入
  mining 输入，重复/越界/不完整帧批次被整体拒绝（AC-2）。
- [x] request/result 同时绑定 run/video/track/model snapshot/raw artifact；run 不匹配、文件缺失
  或文件指纹变化时拒绝执行/读取，不混合不同 run（R2.1、R8.2）。
- [x] 四类信号均有合成轨迹测试；每个候选保存 finite component scores、触发原因、总分与
  run id，同输入/参数/seed 得到相同结果（AC-4）。
- [x] 测试固定 pipeline 顺序；连续低 confidence/长 gap 不能垄断 Top N，候选不足时只放宽
  时间间隔并报告 `actual_n` 与实际间隔（AC-3）。
- [x] K-means 只复用现有 5.1 路径并支持显式候选帧集合；visual path 与 temporal fallback
  都不返回重复帧、不越过 working zone、不选已排除帧。
- [x] mining 通过统一后台 runner 可取消；取消、错误与迟到结果不修改活动项目、不留下可被
  误读为 completed 的结果。
- [ ] 真实单摆开发集与冻结审计集完成版本化记录；在未查看冻结标签的前提下运行一次最终
  比较，困难帧策略的 `Precision@N` 与 review yield 均高于 lowest-confidence-only 基线
  （Phase 5 AC-10）。若未超过，保留失败证据并暂停收尾，不通过调参覆盖结果。
  —— **进行中**：开发集审计表已从真实 2767 帧单摆 run 生成（`docs/benchmarks/`），
  等待用户人工标注 → score → 开发集调参 → 从不同 infer run emit 冻结审计集 v1。
- [x] 定向测试、`QT_QPA_PLATFORM=offscreen python -m pytest`、`python -m compileall src scripts`
  与独立 numerical/application boundary review 全部通过；本 Subphase 无 GUI 变化，不触发
  Human Review。

## Relevant Context

- `docs/spec/phase5-requirements.md` R2、R8、AC-2/AC-3/AC-4/AC-10
- `docs/status/phase-5-plan.md` §3 Phase 5.2、§5
- `docs/roadmap.md` Phase 5
- `docs/research/open-source-project-map.md` §10–§11
- `docs/research/raw/deeplabcut-notes.md` “Outlier frames”
- `docs/decisions/0011-deeplabcut-integration-architecture.md`
- `docs/decisions/0012-gui-tracking-task-boundaries.md`
- `CODE_STANDARD.md` §4、§9、§14–§15
- `src/ai_physics_tracker/infrastructure/dlc_predictions.py`
- `src/ai_physics_tracker/application/inference_job.py`
- `src/ai_physics_tracker/application/tracking_job.py`
- `src/ai_physics_tracker/domain/kinematics.py`
- `src/ai_physics_tracker/infrastructure/dlc_adapter.py`

## Slices

- [x] Slice 1 — Raw prediction + run identity：公开全帧 raw prediction 值对象/读取入口；从活动
  session 验证 completed infer run、working zone、snapshot、预测产物路径与文件指纹，形成不可变请求；
  用 HDF5/CSV、低阈值、缺测、错误 run/文件的定向测试证明 AC-2。（`d67f57d`）
- [x] Slice 2 — Pure mining policy：在一个新的内聚 application 模块实现四类 component、
  robust normalization、weighted rank 与时间去重/放宽；用单点 jump、平滑残差、连续低置信度、
  长 gap、prior Correct 邻域和退化轨迹固定数值行为。（`7af74a0` + 审查修复 `dcb6819`）
- [x] Slice 3 — Diversity + background job：给 5.1 selector 增加可选显式候选集合，复用其
  K-means；接入 `BackgroundTaskRunner`、取消、原子 JSON 结果与结果身份校验，并验证不修改项目；
  顺带完成 F3b 改名（`_kmeans_via_sklearn`）。（`9c14405`）
- [x] Slice 4 — Benchmark + close：benchmark 工具链（`application/benchmark.py` +
  `scripts/benchmark_difficult_frames.py`）与真实开发集审计表已交付；开发集标注、调参与
  冻结审计集比较待用户完成后收尾。（`5feefd1`）

## Verification

```bash
# raw prediction、策略与后台任务
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_dlc_predictions.py \
  tests/test_difficult_frames.py \
  tests/test_frame_selection.py \
  tests/test_tracking_job.py -v

# 全回归与编译
QT_QPA_PLATFORM=offscreen python -m pytest
python -m compileall src scripts

# 冻结审计集（确切命令由 Slice 4 的 benchmark 入口固定，输入为本地项目/run 与审计表）
python scripts/benchmark_difficult_frames.py --help
```

Independent Review 聚焦：数值退化情况、pipeline 顺序、run/file identity、跨层依赖、取消/迟到
结果，以及冻结审计集是否发生数据泄漏。由于 5.2 不新增用户可感知交互，不发起 GUI Human Review；
候选解释的真人体验随 5.3 队列统一验收。

## Result（收尾时填写）

- 完成日期 / 合并 commit：代码与工具链 2026-09-02（`d67f57d` / `7af74a0` / `9c14405` /
  `dcb6819` / `5feefd1`）；**整体收尾待冻结审计集 AC-10 完成后补记**
- AC 勾选结果：除"真实开发集/冻结审计集比较（AC-10）"外全部勾选；AC-10 进行中
  （开发集审计表已生成，等待人工标注）
- 偏离计划之处及原因：
  - 冻结审计集比较需要人工标注，无法在本轮会话内完成 → 工具链交付 + 明示交接，
    Review Record R3 记录待办
  - 真实 run（5.1 时代产物）`extra_fields` 为空 → benchmark CLI 内置内存回填
    （不修改用户数据），同时 prepare 的 legacy 容忍分支被测试钉住
- 遗留问题：Accept/Skip 抑制与 Correct provenance 由 5.3 持久化；5.2 request 已预留显式集合输入；
  `#18` F4/F6 顺带项仍按计划随 5.3 处理；`_file_info` 双实现待下次共同触碰时合并（review S1）
- 独立 review 结论：R1 request-changes（H1 身份绑定）+ R2 approve-with-comments（覆盖/舍入）
  全部修复闭环，见 [phase-5.2-review.md](../reviews/phase-5.2-review.md)；全回归 566 passed
