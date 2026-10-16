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

E. 输入错误公式并点击Fit，再看 **Recent fit attempts**。预期：显示本次拒绝和可执行原因；旧成功结果仍可通过Latest applied result查看；先Save，再用Last saved result查看磁盘版本。关闭/重启，尝试摘要仍在；读取历史不自动激活旧结果或改原始轨迹。

请回复A–E各自“通过/不通过”（不通过附具体操作或现象）。本轮不设固定毫秒或完成分钟数；不把macOS体验验收扩大成Windows/CUDA真机通过。

## 第二轮反馈与复测（2026-10-16）

用户反馈：切换公式感觉不变；Previous saved result没有直接显示公式；提示藏在滚动/折叠内容中；Result details复选方框无法点击。**本轮HR未通过**，不沿用前次自动Gate作为体验通过证据。

只读检查用户当前副本的4次显式Fit（600样本、帧0–599）：

| 表达式 / 输入 | 求解 | RMSE | 实际含义 |
| --- | --- | --- | --- |
| theta / smoothed x | completed | 0.1195667502 m | 无t，拟合常数 |
| theta / measured x | completed | 0.1196561895 m | 无t，常数值约0.002859624 m |
| cos(theta) / measured x | completed | 0.1196561895 m | theta仍是常参数；cos(theta)约0.002859624 m，仍是常数线 |
| a*t^2+b*t+c / measured x | completed | 0.1195611177 m | 误差相比同样本常数线仅减少约0.07945%，未解释振荡 |

记录表明公式和求解确实改变，但不能把completed当作解释了运动。仅选择/自动预览不记正式Fit日志，不能还原所有未点击Fit的试用。用户保存的最后一个function_fit_x是二次式；读取检查不修改该工程或日志。

本轮修复后重点复测：

1. 输入theta或cos(theta)：图上方立即显示当前公式/初值；图旁明确“no t / constant level”，Fit后展示实际参数、常数线误差与本模型误差。预览超出源范围时直接提示Show whole model。
2. 拟合并Save，再用另一公式拟合但不Save，点Last saved result（旧称Previous saved result）：图上方直接显示磁盘版本公式/参数，不展开详情也看得到；编辑器保留当前草稿。Latest applied result应显示新的公式/参数。操作后反馈区域自动进入可见范围。
3. 直接点Result details方框、点文字、按空格均能展开/折叠；Optional settings等同类入口一致。错误公式点Fit或失败/取消时，原因直接出现在图旁，不能被“完成”覆盖。

原A–E其余验收保持；等待用户确认本轮体验，不修改用户真实工程来制造测试成绩。

Last saved result只代表最近一次Save快照，不是上一条拟合尝试；Save后它可能与Latest applied result相同。两者的曲线、公式与参数必须一致说明来源。

## 第三轮反馈与复测（2026-10-16）

用户指出：选择保存快照只有图表切换，公式和表单没有同步；底部尝试选择也应有对应响应。此前“图表回看、表单保留草稿”的分离方式不满足体验，**本轮HR仍未通过**。

保存并关闭旧窗口，使用上方原命令重新启动；保留现有HR副本，不重置用户的尝试。重点复测：

1. 编辑一个不同的公式 / 初值 / 区间，然后选 **Last saved result / Latest applied result**。预期：图表、公式、记录的初值 / 约束、源量、区间和结果解释一起切换，清楚标明只读；表格为Recorded initial，实际拟合参数仍在图上。点 **Return to my draft** 原样恢复刚才草稿；点 **Use recorded setup** 才进入可编辑状态，再点Fit / Measure才生成新结果。
2. 在页面下方 **Fit history — select an attempt** 依次选择已有的不同公式。预期：同样同步整页，图旁立即反馈；原源仍严格匹配的成功记录显示重建曲线、误差和“不是完整历史快照”的说明。再次选当前项也有响应。失败或源已不可用的记录清空旧图并说明原因，不能继续显示上一条曲线。
3. 连续切换不同记录、返回草稿，再重新查看。预期：迟到曲线不覆盖当前选择 / 草稿，不改原始标注、不增加Fit次数、不自动激活历史结果；Crossing历史切回草稿后仍提示Measure，参考值对应当前草稿。

请回复这三项分别“通过 / 不通过”；如不通过，附操作与现象。原A–E其他条件保持。依AGENTS.md §7，这轮交互必须用户亲测后才可合并，自动化检查不替代HR。
