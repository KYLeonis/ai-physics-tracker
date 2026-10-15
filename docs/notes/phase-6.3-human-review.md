# Phase 6.3 Human Review

状态：2026-10-15正式发起，等待用户A/B/C/D反馈。产品自动Gate已通过（独立R4/R5/R6及双平台CI各1095 passed / 2 skipped），不代表HR通过。

## 启动

本轮代码在开发worktree；原目录main保持已验收6.2。先关闭旧窗口，再执行下面一行；绝对PYTHONPATH确保从任何目录启动的都是本轮版本。

```bash
PYTHONPATH=/Users/leonis/.codex/worktrees/bd40/ai-physics-tracker/src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m ai_physics_tracker
```

File → Open Project选择下列`project.json`，再点击顶栏蓝色 **Fit formula / Measure intervals** 按钮。该按钮在所有工作区常驻，一次进入工具页；也可在Analysis & charts中选择 **Formula fitting & intervals** 标签。分析页蓝色提示条会指出入口。

- 合成水平往复运动：`/Users/leonis/Documents/ai-physics-tracker/experiment/p63-human-review/project/project.json`。明确标为合成数据，不是人工真值。可复现生成命令（输出目录必须尚不存在）：`PYTHONPATH=src <python> scripts/prepare_p63_human_review.py --output <new-directory>`。
- P011真实结果：`/Users/leonis/Documents/ai-physics-tracker/experiment/p63-reference/analysis-result-project/project.json`。沿用用户提供的TOML / 旧DLC与本轮授权的近似时序；原冻结基准工程保持原样。打开后如现有时序门提示Near-CFR，选择已授权的近似模式；不能以未确认时序启动新测量。

## A — 公式与拟合

1. 打开合成工程，选择`x`、Measured、Function fit，点击Restore saved settings。应恢复`c+A*cos(Omega*t+phi)`、初值 / 边界和10–179帧区间；左侧为只读`x(t)`，数学预览可辨认。
2. 点击Preview initial curve，再Fit。应看到测量 / 模型与残差；拟合约为c=160、A=70、Omega=4.83322、phi=-1.57080，用户换算T≈1.3s。初值曲线只是预览，点击Fit才发布结果。
3. 修改公式或参数，应出现草稿提示，保存结果仍显示其原设置。输入`cos(`应有明确位置错误，不能启动拟合。`-t^2`与`(-t)^2`的数学预览含义不同。使用函数按钮和键盘输入A / s / 空格，应正常编辑且不播放 / 标注视频。
4. 点击Restore saved settings后再拟合一次，使用Undo result / Redo result，应只恢复拟合结果。原全局Undo在Analysis保持禁用，不允许越过标注 / 标定 / 上游源计算事务。

封闭问题A：公式是否清楚可编辑，预览 / 参数 / 拟合 / 结果撤销是否符合上述预期？通过 / 不通过。

## B — 独立重复间隔

1. 同一合成工程切Crossing intervals，Restore saved settings。参考线160、Rising、确认带5、最小间隔0.2s；应有事件源帧夹点、逐次间隔、均值约1.3s与样本标准差。
2. 拖动橙色参考线到250，再点击Measure crossing intervals。应显示无足够事件 / 均值不可估计，不显示假的零周期；拟合结果保留。
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

用户未找到入口；诊断时现有GUI进程工作目录为原main，P6.3仍在开发worktree。已提供绝对PYTHONPATH启动命令，并增加顶栏常驻直达按钮 / 分析页提示 / 缩短标签名称。请关闭旧窗口后按新命令启动，确认无需寻找第二层标签即可看见公式编辑器。封闭问题：入口现在是否明显、一次点击能进入？通过 / 不通过。原A/B/C/D尚未收到通过反馈。
