# Phase 5.2 Difficult Frame Benchmark Report

- 日期：2026-09-02
- 视频：Phase_5_2_test.mp4（148 帧）
- infer run：`6b625037-614b-4d7d-85f7-0ec53858090d`
- 预测产物：`data/engines/6b625037-614b-4d7d-85f7-0ec53858090d/Phase_5_2_testDLC_Resnet50_dlc_7f423430Sep02shuffle1_snapshot_best-10.h5` (size=84526, mtime_ns=1788361099087987137)
- 审计表：`docs/benchmarks/phase-5.2-development.csv`（17 帧已标注）
- 参数：top_n=10, seed=0, confidence_threshold=0.6, min_gap_s=0.25, diversity=not_needed

| 策略 | actual_n | needs_review | Precision@N | needs_correction | review yield |
| --- | --- | --- | --- | --- | --- |
| difficult-frame policy | 10 | 8 | 0.800 | 3 | 0.300 |
| lowest-confidence baseline | 10 | 6 | 0.600 | 0 | 0.000 |

**结论：policy 在 Precision@N 与 review yield 上均优于基线（AC-10 达成）**
