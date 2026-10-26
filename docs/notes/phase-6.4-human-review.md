# P6.4 Human Review — 条件性SE与95%局部t置信区间

当前工作分支`feat/p6.4-parameter-error`，未合并main。用户在首轮HR反馈横向裁切并要求具体区间后，已确认95%双侧局部t口径（计划v1.1 / ADR-0029）。旧SE的HR与Review不代替本轮。[计划](../status/phase-6.4-plan.md) / [Review](../reviews/phase-6.4-review.md)。

## 2026-10-26反馈后的三项补测（当前）

用户反馈区间被遮挡、不可拖动，要求术语hover解释、Fixed操作引导，并确认“其余都通过”。保留其他已测项通过，只补测以下三项；Fixed此前未理解，不能冒记通过。

先关闭旧应用，再运行下方原启动器；已有体验工程会保留上次保存状态。若停在草稿，点`Latest applied result`查看区间。

1. **完整区间与拖动**：查看第四列，拖动表头两列之间的分隔线，再缩窄窗口、使用结果表底部横向滚动条。→ `[lower,`与`upper]`分两行，默认完整显示；列宽可调，窄窗能滚到最右列，hover单元格仍可读完整原值。
2. **术语解释**：hover结果表的`Estimate`、`Conditional standard error`、`95% confidence interval (local)`表头 / 单元格，再hover图旁RMSE结果文字、`Residuals`标签、源选择及误差方法。→ 有可换行的说明，讲清含义、用途和限制；CI不是预测范围，SE不包含完整系统误差。
3. **固定参数**：点`Use recorded setup` → 勾选`Parameter bounds / fixed values`展开隐藏列及操作说明 → 在c的`Initial`双击填入`160`并按Enter → 必要时把参数表底部横向滚动条拖到右侧，勾选同一行的`Fixed` → 点`Fit`。→ 结果c的Estimate保持160，SE和CI显示`Fixed`；其余自由参数继续拟合。再点`Use recorded setup`，取消c的`Fixed`并重新Fit，c恢复自由估计。固定的是Initial里的数值，不是上一轮Estimate；固定值自身的不确定度不传播。

请分别回复`1通过 / 2通过 / 3通过`，或说明哪一步仍有问题。只等这三项反馈后再收尾P6.4。

## 本机启动

已有`.venv`，**新的独立合成副本**（未覆盖上次体验工程）：

```bash
/Users/leonis/Documents/ai-physics-tracker/experiment/p64-ci-human-review/start.command
```

启动即打开已记录的Measured拟合，四列Parameter / Estimate / Conditional standard error / 95% confidence interval (local)。第一条轨迹有固定seed的模拟测量噪声，不是人工实验观测，不用于证明区间覆盖率。第二轨迹`Legacy SE only — no interval`模拟已有SE而未记录区间的v1结果。

常规空白应用仍为`cd /Users/leonis/Documents/ai-physics-tracker`后`.venv/bin/python -m ai_physics_tracker`，需要手动打开项目。

## 2026-10-24操作 → 预期（原四组，留档）

1. **具体区间与说明**：启动后查看四列，尤其第四列`95% confidence interval (local)`，展开方法并缩窄窗口。→ 每个可估参数有具体`[lower, upper]`（例如本副本c约为[159.96432,160.1678]）；SE与区间分开。能读到95%双侧t / n-p自由度、残差近似正态及非线性局部近似含义；T仍仅数值、不传播误差。
2. **横向可达**：展开`Insert symbols / functions`，在右侧表单底部拖动横向滚动条或触控板横滑到最右侧。→ 最右侧插入按钮 / 示例 / 表单可访问；在数字输入框上横滑不改变区间数字。纵向滚动仍可用。
3. **固定与处理源**：点`Use recorded setup`，将c勾为Fixed后Fit；再选Smoothed后Fit；最后恢复Measured后Fit。→ 固定参数的SE / CI为Fixed；平滑源自由参数SE / CI明确不支持且拟合仍保留；恢复Measured并重新Fit后，自由参数又有数值SE / 区间。遇边界 / 病态 / 数值范围限制时显示具体原因，不伪造0或截断范围。
4. **历史与保存**：选一条本次拟合尝试回看，再Return to my draft并改公式（可输入`sin(`）；然后退出历史、选第二轨迹并点Latest applied result。→ 新历史显示当次区间；草稿 / 预览失败不残留旧统计；第二轨迹保留已有SE，CI显示Not recorded，不自动补算。保存体验副本后重启同一启动器，已录区间仍保持。

原四组的本轮反馈已见顶部；不重复要求已通过项目。

## Gate与历史

项目`AGENTS.md` §7及`docs/workflow.md` §5.1要求新交互由用户亲测，发起HR后停止等待；offscreen与启动自检不能替代。区间产品12ea18d曾通过独立R3 / 全量1408 / CI40077232972双平台各1406 passed / 2个既有可选skip。2026-10-26 F4由用户确认Closed，其余已测项通过；本轮F6 / F7局部GUI修复及自动验证以current为准，三项补测未完成前仍不合并。

旧启动器`experiment/p64-human-review/start.command`保留原副本；本轮使用上方新路径，避免默认打开你先前保存的Smoothed结果而看不到区间。
