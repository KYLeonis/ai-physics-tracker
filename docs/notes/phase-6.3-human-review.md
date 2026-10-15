# Phase 6.3 Human Review

状态：2026-10-15用户确认A / C通过；B因滚动、拖线及信息密度不通过，修复后补测；D尚未收到反馈。自动化验证不代替HR，尚未集成main。

## 启动

本轮代码在开发worktree；原目录main保持已验收6.2。先关闭旧窗口，再执行下面一行；绝对PYTHONPATH确保从任何目录启动的都是本轮版本。

```bash
PYTHONPATH=/Users/leonis/.codex/worktrees/bd40/ai-physics-tracker/src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m ai_physics_tracker
```

File → Open Project选择下列`project.json`，再点击顶栏蓝色 **Fit formula / Measure intervals** 按钮。该按钮在所有工作区常驻，一次进入工具页；也可在Analysis & charts中选择 **Formula fitting & intervals** 标签。分析页图表标签中有简短入口提示；进入工具后隐藏，避免重复占位。

- 合成水平往复运动：`/Users/leonis/Documents/ai-physics-tracker/experiment/p63-human-review/project/project.json`。明确标为合成数据，不是人工真值。可复现生成命令（输出目录必须尚不存在）：`PYTHONPATH=src <python> scripts/prepare_p63_human_review.py --output <new-directory>`。
- P011真实结果：`/Users/leonis/Documents/ai-physics-tracker/experiment/p63-reference/analysis-result-project/project.json`。沿用用户提供的TOML / 旧DLC与本轮授权的近似时序；原冻结基准工程保持原样。打开后如现有时序门提示Near-CFR，选择已授权的近似模式；不能以未确认时序启动新测量。

## A — 公式与拟合

1. 打开合成工程，选择`x`、Measured、Function fit，点击Restore saved settings。应恢复`c+A*cos(Omega*t+phi)`、初值 / 边界和10–179帧区间；左侧为只读`x(t)`，数学预览可辨认。
2. 点击Preview initial curve，再Fit。应看到测量 / 模型，残差在图表的Residuals标签；拟合约为c=160、A=70、Omega=4.83322、phi=-1.57080，用户换算T≈1.3s。初值曲线只是预览，点击Fit才发布结果。
3. 修改公式或参数，应出现草稿提示，保存结果仍显示其原设置。输入`cos(`应有明确位置错误，不能启动拟合。`-t^2`与`(-t)^2`的数学预览含义不同。使用函数按钮和键盘输入A / s / 空格，应正常编辑且不播放 / 标注视频。
4. 点击Restore saved settings后再拟合一次，使用Undo result / Redo result，应只恢复拟合结果。原全局Undo在Analysis保持禁用，不允许越过标注 / 标定 / 上游源计算事务。

封闭问题A：公式是否清楚可编辑，预览 / 参数 / 拟合 / 结果撤销是否符合上述预期？通过 / 不通过。

## B — 独立重复间隔

1. 同一合成工程切Crossing intervals，Restore saved settings。参考线160、Rising、确认带5、最小间隔0.2s；应有事件源帧夹点、逐次间隔、均值约1.3s与样本标准差。
2. 在Reference value数值框输入250（超出当前信号范围会提示），再点击Measure crossing intervals。应显示无足够事件 / 均值不可估计，不显示假的零周期；拟合结果保留。
3. 选`y`，Function fit输入`c`并Fit，应能拟合常量约100；切Crossing intervals，参考线100后测量，应无法估计间隔。工具始终称重复间隔，不自动声称唯一基本物理周期。

封闭问题B：两种工具能独立使用，参考线可见可调，不适用状态清楚吗？通过 / 不通过。

## C — 源帧、保存与只读

1. 回到`x`的Function fit并恢复设置；把起始帧改20，Preview后Fit。横轴`t=0`应对应源帧20，缺测不会按新段重新计时。点选真实测量样本应定位其视频源帧，不能修改标注。
2. Save后重开同一工程。保存的公式、样本 / 模型 / 残差、参数与来源应恢复可读；点击Restore saved settings可继续编辑。显式Save按既有规则清空Undo。
3. Analysis中点击视频、A/S、旧全局Undo/Redo均不得写原始标注；返回Acquire保留原编辑能力。

封闭问题C：源帧导航、保存重开和Analysis只读保护是否通过？通过 / 不通过。

## D — P011真实工程

1. 打开P011结果工程，选`theta`、Measured。分别查看已保存的函数拟合与交叉测量，并Restore saved settings核对表达式 / 参数。
2. 应披露近似时序、rad单位、源帧0–214；交叉均值约1.04127s，人工参考约1.03898s，相对差约0.220%。拟合RMSE约0.02090rad；用户公式换算值与交叉间隔分别显示，不宣称真实摆动严格符合阻尼余弦。

封闭问题D：真实工程的来源 / 近似时序、公式和结果展示是否清楚？通过 / 不通过。

请回复A / B / C / D分别通过与否；不通过时描述具体操作和实际结果即可。只有用户本人反馈可以关闭本轮HR；自动化测试不替代体验验收。


### 入口可发现性补测（2026-10-15）

用户未找到入口；诊断时现有GUI进程工作目录为原main，P6.3仍在开发worktree。已提供绝对PYTHONPATH启动命令，并增加顶栏常驻直达按钮 / 分析页提示 / 缩短标签名称。请关闭旧窗口后按新命令启动，确认无需寻找第二层标签即可看见公式编辑器。封闭问题：入口现在是否明显、一次点击能进入？通过 / 不通过。入口问题之后用户已确认A / C通过；B体验需修复，D尚未反馈。

入口补丁自动验证：本机31项GUI通过；04495a4双平台CI各1096 passed / 2 skipped。请按上方绝对路径命令重启后补测入口，旧窗口不会热更新。


### B交互补测（2026-10-15）

原问题：页面原生滚动条自动隐藏、图表普通滚轮缩放和拖动平移相互混淆，横向溢出裁掉轴与文字；参考线不好找 / 调整，页面内容过密。A / C已通过，不要求重走全部步骤。

本轮变化：工具页纵向滚动条常驻、整页无横向滚动；普通滚轮（含数字框 / 下拉框 / 参考滑块上）只滚页面；Ctrl+滚轮或Zoom按钮缩放，普通拖动不平移坐标。Reset view回到源信号范围，初始模型和远处参考线不再挤压源信号。参考线实时同步数值 / 滑块，Center reference回到信号中点，Find reference显式扩大范围找回线。旧事件仅在当前草稿与已保存配方一致时显示；调整参考线不发布新测量，仍需显式Measure。

1. 用上方绝对路径命令重启，打开合成工程，点击顶栏Fit formula / Measure intervals。窗口缩至约1024×640：纵向滚动条应一直可见；整页不出现横向滚动，坐标轴 / 表单不被裁切。移入图表或数字框滚轮，应只滚页面，不缩放 / 误改数值。
2. 切Crossing intervals → Restore saved settings。应恢复参考值160；界面按选数据、设参考 / 测量、看图与关键结果排列。Noise / separation options、参数边界和Result details默认收起，展开仍能查看完整设置、事件与来源。
3. 拖橙线、拖滑块或输入数值：三者同步，图表坐标不随拖动漂走；改动后旧事件标记隐藏，保存结果仍明确标为Saved。点击Measure才产生当前配方的事件。
4. Reference value输入250，应提示超出信号范围；Find reference可找回线，Center reference应恢复160及信号视图。Ctrl+滚轮 / Zoom可明确缩放，Reset view可随时恢复。参考值250时Measure应显示无可估计间隔；改回160测量约1.3s。
5. 切Function fit看同一已保存拟合：Signal / model与Residuals分标签，关键参数 / RMSE / T直接可读，详细结果可展开。切换后仍可找到数据、设置与结果，不需要猜滚轮或拖动含义。

封闭问题B补测：滚动条、缩放 / 恢复、参考线调整和页面信息层次是否清楚易用？通过 / 不通过。

D仍按原D步骤独立反馈；本轮没有更改P011冻结数据、算法 / 容差、时间 / 标定协议。


本轮交互修复的独立验收：3cc546a经全新只读R8复审Approve，关闭R7窄窗与事件恢复两项finding；主Agent最终35项GUI / 工作区 / Analysis只读回归通过。独立复审不替代以上B / D真人反馈。


最终自动验证回执：3cc546a的[CI38760538586](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38760538586) macOS / Windows Python3.11各1100 passed / 2 skipped，所有步骤success。其后仅文档同步，不改变产品 / 测试树。请重启后补测B，并反馈尚未验收的D。


### Fit禁用 / 时序确认入口补测（2026-10-16）

P011是Near-CFR；每次重开工程沿既有契约重新核对当前媒体会话。此前Analysis只重挂视频，时序状态 / 按钮留在Acquire，因此Fit禁用却无法在当前页看到确认入口，来源条还将无授权误写为verified CFR。已由e4f04a0修复：同一时序状态及按钮随视频移动；Fit / Preview / 交叉测量按钮旁直接显示禁用原因，来源条与当前会话同步。没有增加20帧训练条件，也不根据函数是否适合数据决定按钮能否点击。

1. 保存并关闭旧窗口，按上方绝对路径命令重启，打开P011结果工程，进入Fit formula / Measure intervals。
2. 视频旁应显示Near-CFR状态和Use approximate timing…按钮；Fit旁提示Timing not authorized，来源条不能写verified CFR。先拒绝确认，应继续只读且Fit仍禁用。
3. 再点击Use approximate timing…并接受本次近似：Fit / Preview应启用，来源条改为approximate timing，确认按钮隐藏。选择合法公式及有效参数后可以尝试预览 / 拟合，函数是否合适由结果判断。当前P011在当前探针确认后，x / theta源准备均通过。若其他工程源的时间配方确有变化，仍须重新计算源图表，不绕过旧源配方校验。
4. 往返Acquire / Analysis，时序状态和按钮应保持对应状态，视频与控件不重复、不丢失；原始点不改变。

封闭问题：现在禁用原因是否清楚，能否直接在Analysis确认时序并正常启用Fit？通过 / 不通过。A / C原通过记录保留，B交互补测 / D仍待反馈。

时序入口补丁自动验证：e4f04a0本机全量1103 passed；[CI38766019892](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38766019892)macOS / Windows各1101 passed / 2 skipped，全部步骤success。自动化不代替以上入口可见性 / 操作体验的本人确认。
