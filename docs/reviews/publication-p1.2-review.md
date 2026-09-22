# Independent Review — Publication P1.2

- Date:2026-09-23;Scope:P1.2 S1–S6(experiment 帧集、同帧 4/4 join、引导标注、共享 fixed-check、四 bodypart exporter、真实 DLC smoke),分支 `feat/p1.2-complete-frame-annotation`,commits `1a1886e`…(见 git log)。Reviewer 均为 fresh-context 只读 agent,处置由实现方完成并复测。
- 计划:[P1.2 mini-plan](../../publication/plans/p1-four-landmark-measurement.md) §6 + [执行 mini-plan](../../publication/plans/p1.2-complete-frame-annotation-execution.md);契约 §3。

## R1 — S1 frame-set 专项

Verdict:NEEDS-FIX → 全部修复(`e321f96`)。

| Finding | 摘要 | 状态 |
| --- | --- | --- |
| FS1 (Medium) | frame_set working_zone 无内容语义校验(逆序/负起点可落盘) | CLOSED:构造期对齐 Timeline 先例;回归测试 |
| FS2 (Medium) | serializer 对畸形 working_zone 静默降级 None(违反 fail-closed 声明) | CLOSED:非二元 list 显式 raise;回归测试 |
| FS3 (Low) | session 负帧分支不可达死代码 | CLOSED:删除并注明 |
| FS4 (Low/Info) | P1.1 既有:v1 manifest 携带 publication 键在 v2 写出时静默丢弃(需手造 manifest) | WONTFIX(记录;域互斥已封死语义通道) |
| FS5 (Low) | 实现与 mini-plan 文本偏离(experiment_frames.py 未建) | CLOSED:mini-plan 同步并注明理由 |

## R2 — S1+S2 identity 专项(计划 gate 前半)

Verdict:**PASS**(5 项 Low/Info 全部顺手修复)。核心结论:role↔track 对齐被域不变量结构性排除错位;帧聚类按整数精确;五分类互斥;digest float 单射/无碰撞面;frame_set 与 join 零耦合;duplicate raise 是外部改写防线。修复:ID1(partial 帧坐标损坏进 nonfinite 诊断)、ID2(ROLE_ORDER 复用)、ID3(docstring 写明 defense-in-depth)、ID5(role 重绑 digest 敏感 + 残留计数回归)。

## R3 — S5 export / S4 fixed-check 专项(计划 gate 后半)

Verdict:**PASS**(EX1/EX2 Low 已修,EX3–EX5 记录)。核心结论:plan 划分严格(fixed_check_status fail closed + 独立重 join + 聚合校验三道防线);split_indices 与导出行序一致;exporter 与单轨版行为对齐且 bodypart 顺序错位整体拒绝;bound track 无法经旧单轨 export 路径导出(结构性隔离);S4 子集 digest 语义与契约"对应 frozen comparison"一致(检查帧外改动不失效,探针实证两端)。修复:EX1(坐标元数/有限性 defense-in-depth)、EX2(YAML 非 mapping 显式 RuntimeError)。EX4 为 P1.3 交接提醒:训练 request 必须唯一路径 build→rows→export→split_indices 并冻结全量 label digest。

## S3 测试驱动的 src 缺陷(测试 subagent 发现)

1. 引导按钮死路:`guide_skip/next/finish` 分发在一次原子回滚的编辑批次中丢失,真实 UI 点击无效果 → 已修复并补分发(`b490ea1`)。
2. skip 集合在全跳过时被误清 → 点击会落到被跳过 role → 修复为仅换帧清空(`b490ea1`)。

## Human Review

P1.2 交互(S3 引导标注)与整链终验(S6)按用户指示合并为一次验收,协议见 [p1.2-human-review.md](../../publication/plans/p1.2-human-review.md)。结果待用户执行。

## Verification

- 全量 `python -m pytest`:**980 passed, 9 subtests**(P1.1 基线 921 + P1.2 新增 59);`compileall` 通过。
- 真实 DLC smoke(macOS arm64,DLC 3.0.1):`PYTHONPATH=src python scripts/smoke_test_dlc_p12_dataset.py` → **PASS**:合成四标记视频 → 四 bodypart config → `export_experiment_annotations`(7 行×8 坐标)→ `create_training_dataset` 共同 split(train 4/test 3)→ 独立解析生成 CSV 确认 4 规范 bodyparts 与完整坐标行。结构/生命周期 smoke,不训练、不声称精度。

## Boundary

训练执行与 teacher import 属 P1.3(EX4 交接);θ/QC mask 属 P2;Windows G1–G4 仍为 P6 前门禁。
