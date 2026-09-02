# Subphase Plan — Phase 5.1 Representative Frame Selection

- Issue：Phase 5.1 — Representative Frame Selection（待创建）
- 分支：`feat/p5.1-representative-frames`
- 日期 / 状态：2026-09-02 · 进行中

## Goal

第一次训练前，用 DLC uniform/K-means 为用户推荐少量分布良好的帧号（仅推荐，不自动打标），
减少手工拖时间轴的负担。对应 spec R1 与 AC-1。

## Scope

**做**：

- `FrameSelectionRequest` / `FrameSelectionResult` Qt-free 数据类（tracking_types.py）。
- `EngineAdapter` Protocol 新增 `suggest_frames` 方法。
- `DLCAdapter.suggest_frames`：uniform（np.linspace）和 K-means（DLC 底层 KmeansbasedFrameselection）。
- `MockEngineAdapter.suggest_frames`：确定性输出，不依赖 DLC/Qt。
- `FrameSelectionRunner` + `prepare_frame_selection_request` + `run_frame_selection_worker`：
  复用 BackgroundTaskRunner，后台可取消，文件完整性校验。
- 最小 GUI：Task Panel 新增"建议帧"控件组，TrackingActions 新增选帧相关方法，跳帧集成。
- 新增 `tests/test_frame_selection.py`（纯策略/adapter 测试）。
- 新增 `tests/gui/test_frame_selection_actions.py`（GUI offscreen）。

**不做**：

- 不自动创建 TrackPoint（结果只是帧号列表）。
- 不实现困难帧挖掘（5.2）、Suggested Frames Review（5.3）、Advisor（5.5）。
- 不改 schema、不引入新依赖、不改 CI 配置。
- 不做 F2 的 AI 轨迹 clear/activate/replace。

## Acceptance Criteria

- [x] DLC uniform/K-means 在 working zone 返回去重帧号，排除已有 manual 帧，不自动造 TrackPoint（AC-1）
- [x] 候选不足 N 时返回实际数量；重复帧被去重（AC-1）
- [x] 后台执行、可取消；结果记录 algorithm/N/seed/zone/cluster_step/excluded_count/actual_n（AC-1）
- [x] 测试：两种算法、排除已有标签、working zone 约束、seed、取消、不足 N（45 单元测试 + 16 GUI offscreen = 61 测试）
- [x] 全回归 ≥ 433 passed 不退化（494 passed in 64.60s）
- [ ] GUI Human Review：建议帧列表出现，点击跳帧，不自动打标（**待用户验收**）

## Relevant Context

- `docs/spec/phase5-requirements.md` R1、AC-1
- `docs/status/phase-5-plan.md` §3 Phase 5.1
- `src/ai_physics_tracker/application/tracking_types.py`（扩展数据类）
- `src/ai_physics_tracker/infrastructure/engine_adapter.py`（Protocol 扩展）
- `src/ai_physics_tracker/infrastructure/dlc_adapter.py`（真实实现）
- `src/ai_physics_tracker/infrastructure/mock_engine_adapter.py`（Mock 实现）
- `src/ai_physics_tracker/application/tracking_job.py`（Runner 接入）
- `src/ai_physics_tracker/gui/task_panel.py`（UI 控件）
- `src/ai_physics_tracker/gui/tracking_actions.py`（动作层）

## Slices

- [x] Slice 1：`FrameSelectionRequest` / `FrameSelectionResult` 数据类
- [x] Slice 2：DLC Adapter + Mock Adapter `suggest_frames` 实现
- [x] Slice 3：`FrameSelectionRunner` + `prepare_frame_selection_request` + `run_frame_selection_worker`
- [x] Slice 4：最小 GUI（Task Panel + TrackingActions）→ **Human Review 待完成**

## Verification

```bash
# 单元测试（45 passed）
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_frame_selection.py -v

# GUI offscreen 测试（16 passed）
QT_QPA_PLATFORM=offscreen python -m pytest tests/gui/test_frame_selection_actions.py -v

# 全回归（494 passed）
QT_QPA_PLATFORM=offscreen python -m pytest

# 编译检查
python -m compileall src
```

## Result

- 3 个并发子智能体审查通过，识别 7 项 Finding（含 P0/P1），全部就地修复闭环（详见 [docs/reviews/phase-5.1-review.md](../reviews/phase-5.1-review.md)）。
- 61 个新增测试全部通过，全库 494 测试全绿。
- 当前状态：S1–S4 开发与 Review 闭环完成，等待 Human Review 用户真机体验。
