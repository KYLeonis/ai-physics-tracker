# Independent Engineering / Scientific Review — Publication P4.3

- Subphase：P4.3 — Model criticism and λ teaching UI
- 审查范围：基线 `8addd43`（`codex/ejp-p4-3-teaching-ui`）及其当前未提交增量：`application/pendulum_exploration.py`、`gui/pendulum_exploration.py`、`gui/pendulum_teaching_panel.py`、`gui/pendulum_criticism_panel.py`、`gui/pendulum_fit.py`、`gui/main_window.py`，以及对应的两个 exploration tests。
- Context：[P4.3 mini-plan](../../publication/plans/p4.3-valley-teaching-ui.md)、[platform requirements §8](../../publication/spec/platform-requirements.md)、[scientific profiles §5](../../publication/spec/scientific-profiles.md)、[P4.1 review](publication-p4.1-review.md)、[P4.2 review](publication-p4.2-review.md)、[PHASE_PLAN P4](../../publication/PHASE_PLAN.md)、[ADR-0020](../decisions/0020-explicit-fit-precision-and-historical-regression-limit.md)。
- Reviewer：独立只读审查；除本 Review Record 外未修改产品代码、测试或冻结 evidence。

## Checklist

- [x] 只从当前、同源、已验证的保存 fit 建立 exploration；stale / 缺 fit / fit 正在变更时清空或拒绝交付。应用入口调用 `load_fit_result` 与 `validated_fit_inputs`，未重跑优化器。
- [x] Exploration 与两个教学页均只读；λ 变换、独立 raw forward、直接 objective 与绘图不写 observations、fit payload 或 Project。定向应用测试比较 Project 与 payload bytes。
- [x] 模型批评使用已批准的 P4.1 evidence：raw θ residual 保留源 frame/time，不依赖 SG；SG速度分层和 reference energy 仅作可缺失的辅助 evidence；phase按同源分段和方向展示。较低 RMSE 未被描述为二次阻尼证明。
- [x] q/gL、fit q、`g/q` 表观动力学长度和模型能量平衡分别标明来源、单位及其解释边界；图表坐标与类别映射符合对应数据。
- [x] λ 可行范围由 raw 参数完整 bounds 交集计算；Reference A 与 Displayed B 的 raw/starred 参数同时列出。等价 overlay 来自两次独立 raw RHS forward；q +5% 控制改变 starred q，并显式标作非等价，不显示等价声明。
- [x] 条件曲面复用当前 fit 的 request / parameters 和 P4.2 q curve；固定 starred damping、IC、samples、weights、loss 的条件切面说明清楚，标注 `rad²` 与 ratio/log10 单位语义，不称为 profile likelihood 或置信区间。cursor objective 使用直接 ODE 评价。
- [x] 缓存由当前 fit / 输入 / 视频 / delivery generation 约束；刷新信号覆盖 fit 结果、输入、项目和轨迹选择变化。后台任务接收取消事件、报告实际 q-scan 完成计数，取消或身份过期时拒收迟到结果；关闭时停止 timer 并关闭 executor。
- [x] 原始 surface raster 与 cursor 显示坐标分别处理：cursor 越过 raster 时仅扩展 view range，surface 网格不外推，并显示提示；surface unavailable 的说明在 preview 更新后仍保留。
- [x] 定向测试覆盖 source frame 映射、原始参数/单位、surface 轴方向、λ快速变化时复用同一曲线、实际 222-node scan、取消、代际/视频/输入变化、关闭及新 cursor 边界。

## Findings

无开放 finding。

## Verification

- Reviewer 独立定向运行：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_pendulum_exploration.py tests/gui/test_pendulum_exploration_ui.py -q` → **3 passed**（15.70 s）。
- 主实现方最终 GUI 边界增量定向运行：`tests/gui/test_pendulum_exploration_ui.py` **2 passed**（13.64 s），覆盖更新后的 raster 边界、no-color-extrapolation 与 zero-objective说明检查。
- 主实现方全量回归：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q` → **1341 passed / 1 existing strict xfailed / 9 subtests passed**（269.76 s）。该全量发生在最后 GUI raster 边界断言加入之前；之后的 GUI 定向结果覆盖新增检查。
- 主实现方 frozen evidence verifier：15 个 evidence files / 48 正式 fit 行 / 2 条轨迹核对通过；`git diff --check` 通过。
- 主实现方提供的同源真实 payload 接入探针：P011 双模型、P014 单模型；独立 raw A/B 最大差分别为 `3.74e−9 rad` 与 `3.22e−15 rad`，原 manifest SHA 未变。它们是只读数值接入检查，不代表真人界面验收。
- 本 reviewer 未重跑冻结数值回归；P4.1/P4.2 core 及历史数值政策不在本次审查范围。Default strict xfail、E3 `30/48`、E2 `47/48` 及 ADR-0020 Accepted Limitation 均未更改，也未计为科学通过。
- P4.3 的 GUI Human Review 仍待用户亲测；本审查不代替该关卡。mini-plan AC5 的 Human Review 通过前不得关闭 P4 或进入 P5。

## Review Log

### R1 — 2026-10-01 · 首轮

- 范围 / 基线：`8addd43` 加当前列明的 P4.3 application / GUI / test 工作树增量；P4.1/P4.2 core 与历史限制只按其既有批准结果作为输入核对。
- 结论：**Approve**；在审查范围内未发现阻断 correctness、source identity、科学解释或 GUI 生命周期的问题。
- Findings变化：无新增；无开放 finding。

## Final Verdict

- [x] 通过（无未处置 Blocker）
- [ ] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 需要修改后复审

- 最终结论：P4.3 当前增量 **Approve**，可进入 mini-plan 规定的统一 Human Review；P4 整体仍未关闭，真人验收与其他收尾 gate 仍待完成。
- 日期 / 依据轮次：2026-10-01 / R1
