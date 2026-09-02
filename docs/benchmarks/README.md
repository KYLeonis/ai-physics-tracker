# docs/benchmarks — 困难帧基准（Phase 5.2）

本目录存放 Phase 5.2 困难帧策略的可复现基准记录：开发集审计表、冻结审计集与最终报告。
约定依据 `docs/status/phase-5.2-plan.md`（Proposed Defaults / Slice 4）与
`docs/spec/phase5-requirements.md` R2、Phase 5 AC-10。

## 文件命名

| 文件 | 用途 | 入 Git |
| --- | --- | --- |
| `phase-5.2-development.csv` | 开发集审计表（调参用，可多次重发） | ✅（含人工标注） |
| `phase-5.2-audit-v1.csv` | 冻结审计集（只做最终评估，发后不得改动） | ✅（含人工标注） |
| `phase-5.2-report.md` | 最终比较报告 | ✅ |
| `*.meta.json` | emit 时的机器侧记录（候选帧、参数、产物指纹） | ❌（本地保留，已 gitignore） |

- 视频文件、模型权重、原始 HDF5/CSV 预测一律不入 Git；报告只记录项目内相对路径与
  `(st_size, st_mtime_ns)` 指纹。
- 冻结审计集未优于基线时，如实保留失败证据；回到**开发集**调整参数后重新冻结
  `audit-v2`，旧结果保留，不得在冻结集上反向调参。

## 流程

```bash
# 1) 开发集：emit → 人工标注 → score（可迭代调参）
python scripts/benchmark_difficult_frames.py emit-audit \
    --project <项目目录> --top-n 10 --seed 0 \
    --output docs/benchmarks/phase-5.2-development.csv
# …人工填写 CSV（见下方标注约定）…
python scripts/benchmark_difficult_frames.py score \
    --project <项目目录> --audit docs/benchmarks/phase-5.2-development.csv

# 2) 冻结审计集：调参结束后 emit 一次 v1，标注，score，写 report
python scripts/benchmark_difficult_frames.py emit-audit \
    --project <项目目录> --output docs/benchmarks/phase-5.2-audit-v1.csv
python scripts/benchmark_difficult_frames.py score \
    --project <项目目录> --audit docs/benchmarks/phase-5.2-audit-v1.csv \
    --output docs/benchmarks/phase-5.2-report.md
```

`score` 会用相同输入/参数/seed 确定性重算两种策略并与 emit 记录核对；
视频或预测产物在两次运行之间被改动会直接报错。

## 人工标注约定

审计表由 `emit-audit` 生成：困难帧策略 Top N 与 lowest-confidence 基线 Top N 的
**并集**，固定种子打乱、隐藏来源与排名。逐帧判定方法：在应用中打开该项目，跳转到
对应帧号，对照 AI 预测标记与画面中摆的真实位置。

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `needs_review` | `1`/`0` | 该帧的预测可疑（低置信/位置不对/缺测），值得人看一眼 |
| `needs_correction` | `1`/`0` | 确认预测错误，需要人工修正（隐含 `needs_review=1`） |
| `note` | 短文本 | 备注（如 "occluded"、"completely wrong"），可留空 |

硬性规则：`needs_correction=1` 时 `needs_correction => needs_review`（违反会被
`score` 拒绝）；并集内每帧都必须标注；只填 `1`/`0`/`true`/`false`/`yes`/`no`。

## 指标

- `Precision@N = needs_review / actual_n`（actual_n 可能小于 top_n）
- `review_yield = needs_correction / actual_n`
- AC-10 要求：策略在两项指标上**均**严格优于 lowest-confidence-only 基线。
