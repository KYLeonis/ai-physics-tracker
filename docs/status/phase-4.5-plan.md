# Subphase Plan — Phase 4.5 Engineering Stabilization

- Issue：[#16](https://github.com/KYLeonis/ai-physics-tracker/issues/16)
- 分支：`feat/p4.5-stabilization`
- 日期 / 状态：2026-09-01 · 已完成

## Goal

消化 Phase 4 收尾 review 中 Fix Now / Fix Before Beta 级别的工程稳定性债务（F1/F4/F5/F6），使 Phase 0–4 工程基础可安全承载 Phase 5 扩展。

## Scope

**做**：S1 delete_track 级联 tracking_runs（F1）；S2 DLC 导出目录按视频定位并拒绝外来目录（F6）；S3 detached 去除 deepcopy（F5）；S4 AST 分层测试 + 跨包私有符号转正（F4）。

**不做**：F2（AI 轨迹清除/替换，Phase 5 需求）、F3（编排双轨收敛，Phase 5 首个 subphase）、F7/F9/F10/F14 与全部 Accept 项；不改 schema/依赖/CI/ADR。

## Acceptance Criteria

- [x] `python -m pytest` 全绿（**441 passed**，offscreen，main 基线 433）
- [x] AC-1（F1）：domain 级联 + 其他 track runs 保留（`test_delete_track_cascades_tracking_runs_and_keeps_other_tracks_runs`）；session 删除成功且 undo 后 runs 保持删除（`test_remove_track_with_runs_succeeds_and_undo_keeps_runs_deleted`）；GUI 删除带已完成 run 的 track 成功（`test_delete_track_with_completed_run_removes_track_and_runs`）；GUI slot 异常防护（`_deleteSelectedTrack` try/except + 状态栏反馈）
- [x] AC-2（F6）：导出写入 `labeled-data/<video-stem>`（既有 `test_dlc_export_annotations`）且外来子目录时抛含恢复指引的 RuntimeError、拒绝先于任何写入（`test_dlc_export_annotations_rejects_foreign_labeled_data_folders`）
- [x] AC-3（F5）：双向写隔离测试（`test_detached_snapshot_is_isolated_from_subsequent_writes`）+ O(1) 共享契约测试（`test_detached_shares_frozen_project_without_copying`）；全 dict 变更路径 grep 取证为 copy-first
- [x] AC-4（F4）：`tests/test_layer_boundaries.py` AST 化（层方向 / 第三方 / deeplabcut 限定 / 跨包私有符号四类规则 + 检测器自检）；`_tracking_run_to_payload/_from_payload`→公共、`_QueueLogStream`→`QueueLogStream`
- [x] Review Record 建立：[phase-4.5-review.md](../reviews/phase-4.5-review.md)

## Result

- 完成日期 / 合并 commit：2026-09-01 · `feat/p4.5-stabilization` → main（--no-ff）
- AC 勾选结果：6/6 全部满足
- 偏离计划之处：
  - **F1 修复比计划多一层**：domain 级联之外，`ProjectSession.remove_track` 原实现经 `_commit_store` 只回填三个字段、会把已删除的 run 带回旧聚合（新 session 测试当场抓到），改为提交整个 candidate——属 F1 修复本体的必要部分，未扩范围。
  - **独立 review 不可执行**：本环境 subagent 模型提供方未配置（两种 reviewer 均启动失败），按 Review Record 顶部偏差声明以对抗性自查 + 取证替代。
- 遗留问题：F3（编排双轨收敛）→ Phase 5 首个 subphase；F2 → Phase 5 需求规划。已记入 `docs/status/current.md`。
- 独立 review 结论：[phase-4.5-review.md](../reviews/phase-4.5-review.md) —— 修改后通过（2 个 Suggestion 当场修复、1 个理论风险 Accept），无 Blocker。

## 手动验证步骤（可选抽查，替代未执行的独立 review）

macOS 已有 `.venv`：

```bash
source .venv/bin/activate
python -m ai_physics_tracker
```

1. **F1**：打开一个训练过/推理过的项目 → 选中带 AI 记录的 track → Delete track → 预期：track 从列表消失、无报错；Ctrl+Z 撤销 → track 与标注点恢复、AI 任务历史不恢复（Task Panel 中该 run 不再出现）。
2. **F6**（需触发条件，可选）：在项目 `data/engines/dlc/<track>/labeled-data/` 下手工建一个其他名字的子目录 → 再次训练 → 预期：任务失败并显示 "DLC labeled-data contains folders from another video…"，删除该目录后重训恢复正常。
