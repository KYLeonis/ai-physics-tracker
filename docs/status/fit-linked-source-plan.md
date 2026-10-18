# 公式拟合联动与源曲线自动补齐

- 2026-10-17；基线main `d38d15e`；实现分支`codex/fit-linked-source`，worktree `/Users/leonis/.codex/worktrees/fit-linked-source/ai-physics-tracker`。
- 用户通过grill-me选择C、先体验B后内部A；第一批先公式拟合，并明确同意源缺失 / 过期时自动补齐、留在当前页面，正式Fit仍显式。
- High-risk：后台生命周期、科学输入 / 目标版本与派生结果提交；不进入6.4 / 6.5，不启动全局任务 / Undo重构。

## Goal / Scope

已有自动预览 / 历史查看继续复用。新增当前公式拟合页的源准备链：只更新所选轨迹的线性或角运动组，沿用该轨迹已确认参考与SG设置，成功后自动更新预览 / 单位 / 来源说明。Charts控件只影响其勾选的轨迹；拟合独立选择其他轨迹时沿用该轨迹记录，缺少线性记录使用既有默认SG7/2并显示。缺少时序、角参考、标定或有效样本时就地解释；不猜物理输入。公式编辑不重新计算无关源；正式Fit / 尝试日志仍显式，预览不生成拟合结果。

相关源变化、区间 / 目标 / 设置变化走同一预览刷新路径。只读历史不触发补齐；保留草稿与显式采用。不能将未知配方 / 重复记录 / 不支持的未来数据当作缺失数据覆盖。取消 / 失败无部分提交且无无限自动重试。

## Agent Context Pack

- `current.md`、`phase-6-plan.md`、`phase-6.3.1-plan.md`（旧计划已完成；本轮为增量，不重开旧HR）。
- ADR-0009 / 0020 / 0021：原子批次、目标版本、源新鲜度与下游失效。
- ADR-0022 / 0023：草稿保护、尝试日志与预览独立执行。
- ADR-0024：真实时序探测与合格Near-CFR自动授权；不恢复人工Yes门。
- `phase-6.3.1-review.md`、`automatic-timing-review.md`：迟到预览、历史只读、保存忙和重开教训。
- `CODE_STANDARD.md`、`research/open-source-project-map.md` §3.3；复用原生数据 / 派生分层与当前runner。

## Slices / Acceptance

- [x] S0：记录自动补齐契约（ADR-0025）与定向回归场景。
- [x] S1：当前轨迹源准备、复用正式批次执行器 / 校验、取消和失败处理。
- [x] S2：相关数据变化自动刷新当前草稿；来源选择与实际含义一致，初值建议后的说明同步；历史查看隔离。
- [x] S3自动Gate：定向 / 全量 / 双平台CI / 全新独立复审。
- [x] S3真人Gate：2026-10-18用户回复“通过”；以aa86d79集成main。

验收：缺失 / stale线性源和已确认参考的角源自动补齐；不动其他轨迹；旧拟合变stale而不自动Fit。旧任务在换轨迹 / 参数 / 项目 / 工作区 / 进入历史或取消后不提交；未知 / 重复源拒绝、缺标定 / 未确认参考提示，无循环重算。公式、参数、初值估算、区间 / 源及源数据更新后，图 / 单位 / 说明对应同一份当前输入；保存 / 只读历史不引发计算。

## Review Gate

High-risk，Independent Review必须；只读Reviewer核对本轮完整diff、保存忙 / 取消 / 迟到 / 历史与源目标版本。实现方处置findings并记录`docs/reviews/fit-linked-source-review.md`。完成有针对性回归、全量、macOS / Windows CI后，提供最短启动命令与最多5条操作 → 预期，停止等用户HR；通过后再`--no-ff`集成 / 同步 / push。PR可选。

## Verification

最终产品`8ea1f1b`本机全量1271 passed（121.19s），末轮定向48 passed（12.15s）；初轮定向93 passed，返工中定向119 passed。最终[双平台CI 39046152498](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39046152498) macOS / Windows Python3.11成功；独立最终复审Approve，F1–F3 Closed，独立30项通过。2026-10-18用户回复“通过”，本轮HR完成；以`aa86d79` `--no-ff`集成main，合并树与分支262da6a一致，源码 / 测试与8ea1f1b一致。详见[review](../reviews/fit-linked-source-review.md)。

## Human Review delivery

使用独立本地副本`experiment/fit-linked-source-human-review/project`，保留原人工观测 / 标定 / 角量，仅从副本移除已知线性源以体验自动补齐；原实验未改。后续重启不重置副本。启动器`start_fit_linked.py`直接进入拟合页。

```sh
cd /Users/leonis/Documents/ai-physics-tracker
PYTHONPATH=/Users/leonis/.codex/worktrees/fit-linked-source/ai-physics-tracker/src .venv/bin/python experiment/fit-linked-source-human-review/start_fit_linked.py
```

1. 首次打开：留在拟合页，源曲线自动补齐后出现预览，不要求切Charts / Recompute。
2. 选择Linear，修改b的Initial：公式数值 / 预览 / 说明联动，尚未生成正式Fit。
3. 点击Fit：图旁展示本次结果；Latest applied result可回看，Return to my draft返回草稿。
4. 将x切为vx再切回x：曲线 / 单位 / 来源说明同步；导数显示SG derivative，不擅自Fit。

自动Gate完成后请用户逐项回答通过 / 不通过；依据AGENTS.md §7停止等待亲自测试，不以截图或自动化代替。

## Result

2026-10-18用户对上述本轮HR回复“通过”；仅记录本轮整体体验验收，不扩大为Windows真机 / CUDA或未覆盖的科研准确性验收。主线已集成，之后只同步记录并push。重复间隔联动及内部整理未实施，等待下一条指令。
