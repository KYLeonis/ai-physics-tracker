# P6.4 Human Review — 参数条件性标准误差

仅验收P6.4增量；当前工作分支`feat/p6.4-parameter-error`，未合并main。自动Gate与独立复审证据见[计划](../status/phase-6.4-plan.md) / [Review](../reviews/phase-6.4-review.md)。真人反馈前不标记HR通过。

## 本机启动

已有`.venv`，独立合成体验副本已生成（本地忽略，不覆盖用户工程）：

```bash
/Users/leonis/Documents/ai-physics-tracker/experiment/p64-human-review/start.command
```

常规空白应用入口（需要手动打开已有项目）：

```bash
cd /Users/leonis/Documents/ai-physics-tracker
.venv/bin/python -m ai_physics_tracker
```

启动器打开`experiment/p64-human-review/synthetic/project`并进入已记录拟合。合成位置包含固定随机种子的模拟测量噪声，不是人工实验观测，不用于证明SE覆盖率或完整实验精度。第二轨迹`Legacy fit — no recorded SE`是旧摘要兼容演示。

## 操作 → 预期（四组）

1. **结果与说明**：启动后查看四个参数的`Parameter / Estimate / Conditional standard error`表，展开`Parameter error assumptions / method`；缩窄窗口检查可达性。→ 参数估计与SE分列，假设能看懂，能找到残差/RMSE与系统误差局限；`T`只显示换算数值及不传播不确定度说明。
2. **固定与处理源**：点`Use recorded setup`，在参数表找到`c`并勾`Fixed`，点`Fit`；再将`Source`切为`Smoothed`并点`Fit`。→ `c`显示`Fixed`，不是0；平滑源自由参数显示`Unsupported source`原因，拟合曲线/残差仍可用。需要时拖动表内滚动条或悬停查看完整原因。
3. **草稿、历史与旧记录**：查看一个本次Fit的尝试，再`Return to my draft`或`Use recorded setup`编辑公式；可输入`sin(`制造预览失败。→ 草稿/失败不保留旧SE，历史中仅显示当次记录。退出历史后在`Track`选第二轨迹，再点`Latest applied result`。→ SE列显示`Not recorded`，不自动补算。对新拟合可在保存前点`Undo result / Redo result`检查相应结果表随结果切换。
4. **间隔与保存**：回第一轨迹，返回草稿，切到重复间隔工具，选择x / Measured并使用已有参考160、rising、hysteresis5、separation0.2（可用`Latest applied result` → `Use recorded setup`恢复），点`Measure crossing intervals`。→ 保留逐次间隔、均值和sample std，并解释它是间隔之间的离散，不是均值误差或参数SE。保存体验副本并关闭重开，拟合记录中的SE或旧`Not recorded`状态应保持。

封闭反馈：以上四组是否通过？回复`全部通过`，或给出失败组号及看到的情况；窄窗或术语若难用，也请指出对应位置。

## Gate要求

项目`AGENTS.md` §7及`docs/workflow.md` §5.1要求本轮新交互由用户亲自测试，Agent在发起HR后停止并等待；offscreen与启动路径自检不代替真人体验。

## 首轮反馈后补测（2026-10-24）

右侧表单横向裁切已以1067312修复，重启同一启动器后，展开符号插入区，在右侧表单底部拖动常驻横向滚动条，或用触控板横滑，最右侧按钮和完整公式内容应可访问；横滑数字输入框不能改变区间值。相关GUI87 passed，待用户复测。用户另已要求新增置信区间，具体水平 / 方法待确认；上述原SE操作单不代表新增CI范围已实现或验收。
