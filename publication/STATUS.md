# Publication Status — EJP Damped Pendulum

> 论文线（`publication/ejp-damped-pendulum`，worktree `ai-physics-tracker-ejp/`）的**当前状态入口**。
> 只反映发布线自身；main 通用产品线状态见 `docs/status/current.md`，两个 status 文件不互相覆盖、不机械同步。
> 策略 / scope / 同步与发布流程：[publication/README.md](publication/README.md)；dual-worktree 规则：main 线 `docs/workflow.md` §10.4。
> 每次发布线任务结束时更新本文件；每次 main → publication 同步在 Relevant Source Commits 登记三要素：
> source commit / 为什么论文需要 / 发布线上重新做了什么验证。

- 最后更新：2026-09-19（发布线建立后的首次初始化）

## Current Work

- 发布线刚建立：baseline（Phase 5.7 收官状态，`62239fa`，不可变 tag
  `ejp-damped-pendulum-baseline-phase5.7`）+ 策略文档（`917cf1d`）+ 本状态文件。
- 尚无 manuscript 支撑工作开始；θ/ω/α、相空间、周期/衰减、拟合等论文所需能力依赖 main 线
  Phase 6，尚未实现、尚未同步。

## Next Action

1. 执行**首次 main → publication 受控同步**（cherry-pick）：将 main 上的 dual-worktree 工作流文档
   （AGENTS.md / docs/workflow.md 更新等治理规则）按需引入发布线，使本 worktree 的 Agent 规则与 main 一致。
2. 此后等待 main 线 Phase 6 科学能力经 Independent Review 收口后，逐项评估是否论文需要，再按
   README §5 同步；每次同步回填本文件 Relevant Source Commits。

## Active Scientific Constraints

论文数值只能建立在这些不变量之上（源头契约在 main 线 spec / ADR；同步进来的代码不得破坏）：

- raw 层只存像素；世界坐标是 `CalibrationTransform` 的派生结果，`pixel_` / `world_` 严格分层
- `frame_index` 是 int、时间是 float 秒；换算只经 Timeline 纯函数（nominal 模型 `frame/fps_nominal`）
- 缺测展开为 NaN 并按连续段滤波：不跨 NaN 段求导、不静默插值、短段按既定缩窗规则（ADR-0008）
- SG 先平滑后微分，默认 window=7 / polyorder=2（ADR-0008）
- 预测永不自动成为 ground truth：completed infer 只是候选，显式 Activate/Replace/Clear 才改观测
- 验证比较资格三态 clean / contaminated / unknown，fail-closed；series ID 相同 ≠ 可独立比较

## Relevant Source Commits

| Source commit（main 线） | 为什么论文需要 | 发布线上的重新验证 | 状态 |
| --- | --- | --- | --- |
| — | 尚未发生同步 | — | — |

- 基线：`62239fa`（tag `ejp-damped-pendulum-baseline-phase5.7`，Phase 5.7 收官，804 passed，双平台 CI 绿）。
- 发布线自有提交：`917cf1d`（策略 README）、本次 STATUS 初始化。

## Reproducibility Status

- [x] 基线确定并打不可变 tag（Phase 5.7 收官状态）
- [ ] 运行环境规范与锁定清单（environment specification）——未开始
- [ ] 干净受控环境下的全流程复现验证——未开始
- [ ] manuscript 冻结 tag（`*-submission` / `*-revision1` / `*-published`）、GitHub Release、Zenodo DOI——未开始，按 README §6 在真实事件发生时创建

## Known Gaps

- 本分支落后 `main` 6 个提交（workflow 2.0 / dual-worktree 文档与 CODE_OF_CONDUCT.md 删除），待 Next Action 1 的首次受控同步。
- 论文核心能力（θ/ω/α、相空间、周期/衰减、拟合与统计、figure 生成）依赖 Phase 6，尚未实现。
- 复现环境目前只有 macOS 开发机（Apple Silicon）验证；Windows 真机 / CUDA 延至 Phase 9（已批准延期），第二环境复现未做。
- Phase 5.6 的 AC-9 改善缺口（冻结基准最佳 −3.3%，未达 ≥5%）已归档：论文如需引用 refinement 改善，必须重新设计实验（独立保留帧 / 第二视频），不得将该数字用作独立改善证据。
