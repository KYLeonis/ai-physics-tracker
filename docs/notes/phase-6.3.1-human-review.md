# P6.3.1 Human Review（待用户）

原P6.3整体HR已通过；本轮新交互独立验收。按AGENTS.md §7，“停止并等待用户亲自测试的反馈”；自动化/真实媒体打开探针不能替代体验判断。

## 启动

macOS沿用现有`.venv`，无需安装依赖。该命令显式加载实现worktree，打开独立P011副本，不会加载旧main源码：

```bash
PYTHONPATH=/Users/leonis/.codex/worktrees/bd40/ai-physics-tracker/src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python /Users/leonis/Documents/ai-physics-tracker/experiment/p631-human-review/start_p631.py
```

启动器/副本位于本机忽略的`experiment/p631-human-review/`；已通过实际视频首帧打开检查。原冻结输入及用户的`p63-reference/analysis-result-project`未修改。普通启动方式：同一PYTHONPATH与Python，执行`-m ai_physics_tracker`，然后Open Project。

## 五项体验

A. 按视频旁提示确认该片段近似时序；依次进入 **Explore motion / Measure repeat intervals / Fit a formula**。预期：能看懂各自输入、输出与操作；分析工具顶部不再要求先标20帧。此处仍需要用户对本次媒体确认，软件不自动授权。

B. **Fit a formula**中选x（默认）、完整区间，再点击 **Damped cosine**。预期：出现`Estimated from data`初值、橙色初值曲线；点击Fit后，当前叠图和RMSE/相对常数均值的改善出现在图旁。参数细节可展开；求解成功不自动认定物理模型。

C. 把公式改成`theta`，在 **Optional settings**填结果名`T`、公式`2*pi/Omega`，点击Fit。预期：说明常数模型不解释时间起伏；主拟合完成，同时显著说明T未算出、缺Omega。图旁编辑/清除换算或转测重复间隔的按钮可用；原表达式及失败原因可回看。

D. 重选Damped cosine并主动Estimate（此前若已手改，软件会保护当前值）；手改一个初值，再改区间。预期：初值不被自动覆盖，预览随当前值更新。主动Estimate才重新准备；很大的初值可用Show whole model找回，Reset view回源范围。普通滚轮滚控件/页面，Ctrl+滚轮缩放图，常驻滚动条可见；Analysis → Acquire往返后窗口仍可缩小。

E. 输入错误公式并点击Fit，再看 **Recent fit attempts**。预期：显示本次拒绝和可执行原因；旧成功结果仍可通过Latest applied result查看；先Save，再用Previous saved result查看磁盘版本。关闭/重启，尝试摘要仍在；读取历史不自动激活旧结果或改原始轨迹。

请回复A–E各自“通过/不通过”（不通过附具体操作或现象）。本轮不设固定毫秒或完成分钟数；不把macOS体验验收扩大成Windows/CUDA真机通过。
