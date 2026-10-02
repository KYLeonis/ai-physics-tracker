# P5 学生试用与最终 Human Review

状态：**待真人执行**。自动测试和开发者检查不代替以下试用。Windows真实跨平台重开、训练权重来源、G1–G4分别如实记录；P6安装包尚未提供。

## 启动与材料

开发机启动一次后，学生只操作GUI：

```bash
cd /Users/leonis/Documents/ai-physics-tracker-ejp
PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m ai_physics_tracker
```

准备一段自己的单摆视频、摆长L/重力g和标定尺，以及一个可导入的四关键点DLC/PyTorch教师模型目录（含config与checkpoint）。教师角色为`tip / body_top / body_bottom / pivot`。省赛P011/P014目前只有成功推理与已保存分析可用于分析/导出UI，原训练权重/标签尚待Windows提供，不能把这些CSV当作教师模型。

## 学生任务（无需理解UUID或snapshot编号）

请由**没有参与开发的本科生**独立完成A、B两支。观察员只记步骤、耗时、卡住的位置，学生需要提示时记录原话；不得先替学生点击关键操作。

### A. 自己训练

1. `File → Open video (new session)…`，再`Create Pendulum experiment…`。选择新工程目录；按Setup标定尺、fixed pivot、竖直top→bottom并确认、L/g、release frame。暂不设置radius reference：它需要当前帧已有可靠tip点。
2. 时序显示near-CFR时，先阅读误差说明，再明确选择`Use approximate timing`；不能接受近似时停止测量。这项授权每次重开重新检查。
3. `Acquire → 1 · Recommend 20 frames`先生成代表帧，再点`2 · Label recommended frames`。每帧按提示标`tip → body_top → body_bottom → pivot`，四点完成自动跳到下一推荐帧；已标点和之前的帧集保留。首次点击其他标注入口也会先推荐帧。导航回可靠tip所在帧，回`Setup → Use current tip as radius reference`，再回Acquire。
4. 点`3 · Train / retrain with current labels`；需要fixed-check时先显示预选帧确认，选择Yes后继续训练，No不启动。记录开始/完成/取消时间；Activity显示在途状态，Cancel可停止。完成后点`4 · Verify & run inference`，窗口默认选本实验最新训练模型，仍可自行选择带日期的其他模型。
5. 点`5 · Mine difficult frames / choose a batch`，程序从最新联合推理自动推荐困难帧。调整推荐数量、取消勾选不想标的帧，再开始选中批次；每帧补齐四点后自动下一帧。只标自己选择的几组，点`Done labeling — train with these labels`结束并重训；需要重新确认fixed-check时，Yes后直接继续。之后再次点4、5，按结果重复。五个编号操作持续可见，任务卡突出建议下一步；修改标签后提示重训。满意后`Use candidate for analysis`明确采用，候选未采用时不进入科学分析。
6. `Analysis`计算Kinematics，按需要调整SG并重新计算；运行M0/M1拟合，查看残差、未收敛/不足说明与模型诊断。SG不阻断raw θ拟合；辅助点不阻断tip+fixed pivot分析。

### B. 教师模型

新建另一个实验工程，完成同样Setup，暂不设置radius reference；`Import teacher model…`选择完整模型目录并检查四角色映射，然后选择`Verify & run inference`。**这一支不需要标训练集、冻结fixed-check或先训练**。检查并采用候选后，导航到有可靠采用tip的帧（缺点或位置不可靠时先在Acquire手工补正），再回`Setup → Use current tip as radius reference`。之后同A分析与导出；未采用的preview点不能作为半径参考。

### 两支都要完成的保存与恢复

- `File → Save`，关闭再打开；重新检查时序授权。既有采用轨迹和科学结果应保留，当前/过期状态仍可辨认。
- 故意启动一次训练或推理后Cancel：原采用测量、人工修正和已保存科学结果保留；Acquire的`Results & history`能查到取消或失败记录，并可以Retry。
- 修正一个tip点：旧结果明确标stale；新候选保持preview，不能代替采用结果。重新计算当前页后得到新结果。
- `File → Export scientific results…`按日期选择某次Kinematics或ODE fit。默认拒绝stale；显式历史导出使用当时冻结输入，不把当前修正混进去。
- `File → Save portable project copy…`选一个**新目录**。将副本搬到另一位置（跨平台测试还需复制到Windows）；原位置的视频/工程不可访问时打开副本，视频、轨迹、科学结果仍可读取。DLC运行能力需要目标机已配置相容runtime及真实self-test，不把工程可读等同于CUDA或安装包验收。

## 导出目录说明

| 文件 | 内容 |
| --- | --- |
| `observations.csv` | 源frame、absolute/relative time、四点像素坐标/likelihood/source/缺测原因、主/辅助QC、θ/ω/参考能量或拟合预测/残差；空单元格=缺测，数组=JSON单元格 |
| `result.json` | 完整不可变结果，包括冻结测量、config/profile/versions、period/tail或参数/start diagnostics/comparison |
| `provenance.json` | 单位、结果日期/身份、来源run/video/hash、current/historical原因与精度说明 |
| `files.json` | 输出文件SHA-256清单 |
| `*.png / *.pdf` | 选定结果的独立科学图，同源数据；PDF为vector，缺测断开；没有可用量时明确Unavailable |

CSV/JSON保留存储浮点精度，图上tick文本会简写。参考能量单位`s^-2`，不是焦耳；较小RMSE不能独自证明阻尼机制或唯一参数。旧payload没有冻结的时序授权时不会捏造，原point `source_detail`及frozen FPS会保留。

## 卡住时

| 现象 | 下一步 |
| --- | --- |
| 模型unverified | 选`Verify & run`；看Activity/Cancel；失败后查Results & history与日志，修好模型目录或导入其他模型 |
| Cancel后无新结果 | 正常：取消任务不采用候选；旧测量仍在 |
| 重开显示interrupted/failed | 读错误和日志，Retry；不要删除工程或原观测 |
| 无ω/phase/energy | 看有效tip连续块与SG提示，减小合法窗口或修复tip缺口；缺测保持缺测 |
| Run fit不可用 | 读相邻输入/IC/时序原因；near-CFR先明确授权，不能靠SG选项绕过 |
| 结果stale | 重算对应页，或显式导出其冻结历史；候选须先review/activate才能成为当前输入 |
| 可携带副本失败 | Relink缺视频/修复缺模型文件；选择新输出目录。原工程保留，失败/取消无半成品目标 |

## 最终HR的五个封闭式问题

1. Setup/Acquire/Analysis的当前状态、下一步和教师导入入口能直接找到吗？（是/否）
2. Cancel/Retry/保存重开后，原测量保留且错误/历史可查吗？（是/否）
3. 当前与历史科学导出的CSV/JSON/PNG/PDF是否符合所选数据和单位、图能读清吗？（是/否）
4. 可携带副本在改目录后能打开视频/结果吗？在Windows重开是否已实测？（Mac是/否；Windows是/否/未测）
5. 一名未参与开发本科生是否独立完成A、B两支并提交记录？（是/否）

用[pilot记录模板](student-pilot-record.md)填写真实证据。任何blocking问题先修复再复测；问题5未完成时P5仍不能标完成。

## 本轮训练循环修复 HR（2026-10-02）

状态：用户明确三项均通过。以下保留复现步骤。

保存P012后退出并用上方命令重启，打开`P012_teacher_test`。这次修复不代改已有工程数据。

1. 点1推荐帧，等待Activity结束，再点2；应看到推荐帧进度和当前角色，四次点击后跳到下一推荐帧，原来标过的帧仍保留。
2. 标好几帧后点3、确认检查帧并训练；完成后点4，应默认选择本实验新模型，允许验证后推理。
3. 推理完成点5，只勾选少量推荐帧；每帧四点后自动继续，结束并训练应在保存/确认后继续；再推理、再挖掘仍可重复。

回复：推荐与四点推进是否正常、训练→新模型推理是否正常、小批重标→重训循环是否正常（各项通过/需调整）。本轮复测通过也不等于外部学生pilot或Windows真机门禁完成。

## 本轮推理进度 HR（2026-10-02）

P012原CPU推理已于16:34:54成功完成（3320帧，约4小时17分）。在GUI确认结果并保存工程，退出GUI，再用本文开头命令启动；新进度从下一次推理生效，不需要先重训。

1. Acquire点`4 · Verify & run inference`，选择已相容模型并启动；Activity应显示加载阶段、`0/总帧数`、百分比和不断更新的耗时，首批前明确ETA尚不可用。
2. 首批后检查帧数/百分比逐步增加，同时出现`frames/s`和`ETA ≈`。它按实际完成批次更新，不要求每秒增加；ETA是累计吞吐估计。
3. 预测帧数达到100%后，显示保存/检查阶段，结果验证成功才显示Completed和新候选；已有采用测量保持到显式采用为止。

回复一个封闭式结论：帧数/百分比、耗时/ETA和阶段说明是否清楚且符合实际？（通过/需调整）

## 本轮自动设备 HR（2026-10-02）

状态：待用户亲测。先保存当前已完成的P012结果并按开头命令重启；已有040模型无需重训。本机该权重的真实MPS单帧自检通过，4帧测试约为CPU的1.9倍吞吐；compile/autocast保持关闭。

1. `Acquire → Adjust this run's settings → Device`选择`auto`，这台8 GB Mac先把推理batch设1或2。点`4 · Verify & run inference`，窗口的`Inference device`应继承auto与batch，仍可手动改为cpu/mps/cuda。取消窗口应保留原设置。
2. 启动后应先出现模型self-test的auto请求，再显示实际`mps`并开始推理；Activity的进度说明应含`Device mps`、真实帧数/百分比、耗时与首批后的速度/约ETA。Windows的auto优先可用CUDA，否则当前版本用CPU；本轮Windows CUDA真机仍未测。
3. 需要测试取消时，Cancel后应停止该任务，已有采用测量和人工修正保留；自检失败或取消不应自动开始推理。显式选`cpu`再试时，必要的CPU自检后应显示`Device cpu`，可使用同一权重。

回复：auto设备继承、实际设备显示和推理/取消是否正常？（通过/需调整）新进度也按上一节回答；用户HR不能代替外部学生pilot或Windows真机门禁。

## 本轮拟合导出 HR（2026-10-02）

状态：已修复，待用户复测。P012这次M0/M1结果各有3243个有效残差，旧绘图列映射错误导致PDF空白。已用同一保存结果生成本地`P012_teacher_test/scientific-results-corrected`，保留原导出；CSV/JSON字节相同，无需再训练或Run fit。

1. 直接打开新目录的`residual.pdf`（或同名PNG），应看到蓝色M0、橙色M1残差；纵轴为rad，刻度与轴标题分开。
2. 打开`angle.pdf`，应看到观测θ、M0与M1预测，共三条曲线；预测仍保留原结果的缺口。
3. 后续GUI导出：保存并退出，按本文开头命令重启；File → Export scientific results选择原ODE fit结果，输出到另一个新目录即可，不需要重算。

回复：新残差图和角度图是否显示正常？（通过/需调整）本轮文件检查不代替既有进度/设备HR、外部学生pilot或Windows门禁。

## 本次开发HR收尾确认（2026-10-02）

用户确认“HR通过，目前可以收尾P5”，前述用户图像/交互HR待测试记录按本次整体确认关闭；不虚构逐题现场日志。外部本科生两支pilot与Windows副本重开仍须真实执行，记录模板保持not_run；依用户当前指令不阻止P5开发收尾，仍作为发行前验收待办。Windows G1–G4仍为进入P6前门禁。
