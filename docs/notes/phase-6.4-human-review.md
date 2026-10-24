# P6.4 Human Review — 条件性SE与95%局部t置信区间

当前工作分支`feat/p6.4-parameter-error`，未合并main。用户在首轮HR反馈横向裁切并要求具体区间后，已确认95%双侧局部t口径（计划v1.1 / ADR-0029）。旧SE的HR与Review不代替本轮。[计划](../status/phase-6.4-plan.md) / [Review](../reviews/phase-6.4-review.md)。

## 本机启动

已有`.venv`，**新的独立合成副本**（未覆盖上次体验工程）：

```bash
/Users/leonis/Documents/ai-physics-tracker/experiment/p64-ci-human-review/start.command
```

启动即打开已记录的Measured拟合，四列Parameter / Estimate / Conditional standard error / 95% confidence interval (local)。第一条轨迹有固定seed的模拟测量噪声，不是人工实验观测，不用于证明区间覆盖率。第二轨迹`Legacy SE only — no interval`模拟已有SE而未记录区间的v1结果。

常规空白应用仍为`cd /Users/leonis/Documents/ai-physics-tracker`后`.venv/bin/python -m ai_physics_tracker`，需要手动打开项目。

## 操作 → 预期（四组）

1. **具体区间与说明**：启动后查看四列，尤其第四列`95% confidence interval (local)`，展开方法并缩窄窗口。→ 每个可估参数有具体`[lower, upper]`（例如本副本c约为[159.96432,160.1678]）；SE与区间分开。能读到95%双侧t / n-p自由度、残差近似正态及非线性局部近似含义；T仍仅数值、不传播误差。
2. **横向可达**：展开`Insert symbols / functions`，在右侧表单底部拖动横向滚动条或触控板横滑到最右侧。→ 最右侧插入按钮 / 示例 / 表单可访问；在数字输入框上横滑不改变区间数字。纵向滚动仍可用。
3. **固定与处理源**：点`Use recorded setup`，将c勾为Fixed后Fit；再选Smoothed后Fit；最后恢复Measured后Fit。→ 固定参数的SE / CI为Fixed；平滑源自由参数SE / CI明确不支持且拟合仍保留；恢复Measured并重新Fit后，自由参数又有数值SE / 区间。遇边界 / 病态 / 数值范围限制时显示具体原因，不伪造0或截断范围。
4. **历史与保存**：选一条本次拟合尝试回看，再Return to my draft并改公式（可输入`sin(`）；然后退出历史、选第二轨迹并点Latest applied result。→ 新历史显示当次区间；草稿 / 预览失败不残留旧统计；第二轨迹保留已有SE，CI显示Not recorded，不自动补算。保存体验副本后重启同一启动器，已录区间仍保持。

请回复`全部通过`，或给出未通过组号和实际情况。窗口可达性或说明难理解也请指出位置。

## Gate与历史

项目`AGENTS.md` §7及`docs/workflow.md` §5.1要求本轮新交互由用户亲测，发起HR后停止等待；offscreen与启动自检不能替代。首轮F4横向布局以1067312修复（GUI87 passed）；本轮区间产品12ea18d，独立R3 Approve / 70定向，实施方129定向及110关联通过，最终全量1408 passed；CI40077232972双平台各1406 passed / 2个既有可选skip，均success。真人HR尚未通过、未合并。

旧启动器`experiment/p64-human-review/start.command`保留原副本；本轮使用上方新路径，避免默认打开你先前保存的Smoothed结果而看不到区间。
