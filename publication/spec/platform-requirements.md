# EJP Publication Platform Requirements

- 日期：2026-09-19；状态：**planning baseline，尚未实现任何 Publication Phase**。
- 产品：**pendulum-focused undergraduate experiment platform**。
- 分支：`publication/ejp-damped-pendulum`；worktree：`ai-physics-tracker-ejp`。
- 科学依据：[Scientific Asset Inventory](scientific-asset-inventory.md)；交付顺序：[PHASE_PLAN](../PHASE_PLAN.md)。
- 本契约按本轮用户方向制定，优先于旧 publication“等待 main Phase 6”政策。main Phase 0–10 状态不因本文改变。

## 1. Platform goals and boundaries

让未参与开发的本科生在 Windows x64 或 macOS Apple Silicon 上安装桌面应用，从**自己拍摄的视频**完成测量、DLC训练或教师模型导入、QC、单摆动力学分析、M0/M1全轨迹ODE拟合、模型批评和结构可辨识性探索，并保存/导出可追溯结果。

这是有明确物理语义的教学平台；不承诺任意视频都能训练出合格模型、不要求M1总优于M0、不以高likelihood或漂亮拟合图代替科学判断。不供应统一训练视频或通用pendulum pretrained model；学生与教师负责自己教学场景的标注/模型。

平台自身必须交付科学能力，不依赖 main Phase 6 完成。main 的适用缺陷修复可以有选择地同步，publication 的科学profile与验收始终由本目录负责。

## 2. Student workflow

| 步骤 | 学生操作 / 可见结果 | 进入下一步的事实条件 |
| --- | --- | --- |
| Install / setup | 安装应用；first-run setup显示设备、进度、成功或可执行修复动作 | 基础应用能独立启动；AI使用前runtime自检通过 |
| Own video | 导入自己的视频，创建Pendulum experiment | 视频可读，时序已验证或有明确近似授权；保留源帧身份 |
| Calibration | 设置比例尺、fixed pivot、true vertical、物理L；`Set release frame` | 参数完整且合法；L与tip几何半径的含义明确 |
| Four landmarks | 同一组representative frames逐帧标注tip/body_top/body_bottom/pivot | 每帧4/4有效人工点才计为完整训练帧；不完整帧可保存/续标 |
| Model branch A | 确认固定检查帧，训练自己的DLC模型 | train/test按完整帧互斥；模型/配置/评价可追踪 |
| Model branch B | `Import DLC Model…`导入教师模型 | 验证四landmark映射、配置、checkpoint、引擎兼容；无需伪造本项目训练记录 |
| Infer / review / QC | 推理、预览候选、检查四点与几何、修正困难帧、显式采用 | completed不等于active；manual修正保留，采用四点作为同一批结果 |
| Reconstruct | 重建signed θ(t)，显示QC缺口与release-relative time | 使用当前采用结果+manual有效观测、当前标定；明确可计算/部分/待更新/最新 |
| Core analysis | θ/ω、phase portrait、period、specific energy | 图表显示单位、算法profile、范围、输入版本；不能跨缺测画伪连续曲线 |
| Fit | 选M0/M1、`Run fit`，查看starred参数、RMSE、trajectory overlay、residuals | 输入/QC/初态/区间已冻结；异步运行可取消 |
| Criticise | 比较全轨迹与高速/早晚段证据、bound/convergence状态、物理一致性 | 同一数据快照可比较；允许“无明显改善/证据不足” |
| Identifiability | reference raw parameters → λ slider →变化raw、固定starred、重叠trajectory与valley位置 | 使用同一物理方程/IC；教学示例不能覆盖fit结果 |
| Save / export | 保存重开；导出轨迹/分析/fit/诊断CSV、参数与来源JSON、图表PNG/PDF | 导出明确valid/stale/preview状态；结果可由配置及输入恢复 |

学生无需理解run UUID、snapshot命名、series ID才能走普通路径。沿用 Setup / Acquire / Analysis 三工作区和状态任务卡；可返回修正，不另造必须逐页通过的向导状态机。

## 3. Four-landmark contracts

### 3.1 固定物理语义

| Landmark | Track/bodypart | 分析职责 |
| --- | --- | --- |
| tip | 一个Track=一个物理点=一个DLC bodypart | fixed pivot→tip决定θ |
| body_top | 同上 | 与body_bottom一起做body separation与pose QC |
| body_bottom | 同上 | 与body_top有序定义body axis；不替代tip |
| pivot | 同上 | 跟踪到的pivot只用于QC，不作为动态角度原点 |

普通模式固定四个role，role→Track UUID→engine bodypart映射稳定，不靠Track显示名称猜语义。历史科研资产使用`marker_tip`，导入时允许明确的`marker_tip → tip`别名映射并记录来源，不重命名源模型文件。

### 3.2 一次dataset / training / inference消费四个Track

- 同一experiment、同一视频共享representative-frame集合；四点全部有效人工完成才导出该帧。遮挡无法可靠定位时保留unfinished/skip状态，不强迫猜点。
- 完整帧=4个role各有唯一有效manual坐标；AI Accept不变成人工label，review Skip不代表正确。
- 导出每帧一次图像、一个DLC多bodypart坐标行；不把同一帧拆成4个training examples。四点的train/test membership必须相同。
- 一次训练、一次推理、一个checkpoint及原始预测文件，共同绑定四role；按bodypart映射回原有TrackPoint结构，逐点保留likelihood与source。
- 一批结果的Activate/Replace/Clear要原子覆盖四Track的AI投影，保留manual与superseded来源；失败不得只更新其中几个role。
- 校验run成员、video、bodypart集合、帧数与配置，防止不同推理版本混成一副四点几何。
- 教师导入需足够的config/pytorch config/checkpoint/metadata来加载，不能仅凭一个`.pt`就声明可用。不要求构建通用模型库。

持久化形态待P0 mini-plan与ADR proposal评审：最小experiment关联记录+run的多Track membership；保留现有单Track历史可读。不能只给现有`bodyparts`列表增加四个字符串：当前exporter其余列填空、snapshot loader要求`target`，训练/推理/激活/验证均有单Track约束。

## 4. Angular, time and measurement conventions

### 4.1 Angle

原始TrackPoint始终存像素。calibrated fixed pivot为c，tip为p，d=p−c；true vertical是图像坐标中自上向下的单位向量v：

```text
θ = atan2(v_y d_x − v_x d_y, v_x d_x + v_y d_y)
vertical-down = 0
internal: rad; display: rad or degree
```

- 图像竖直时tip在pivot右侧为正；任意相机roll下都用校准竖直，不默认图像y轴。
- tracked pivot的抖动不会让角度原点移动；它变化会影响QC。
- 普通模式是平面自由衰减摆动；不静默unwrap穿越±π的数据为多圈旋转。角度分支、零半径、deg/rad混用要有合成测试和明确输入错误。
- 比例尺、pivot-to-tip像素半径、pivot-to-COM物理L分别记录。L用于g/L频率尺度/界限；不把marker位置自动等同质心。

### 4.2 Time / initial state

- 用户`Set release frame`选择的就是有效释放帧r；`t_rel(f)=Timeline.time(f)−Timeline.time(r)`。源`frame_index`和既有绝对`time_s`不改写。
- pre-release帧仍可用于初态估计；分析默认完整post-release范围。裁剪/working zone不可偷偷改变t=0或IC。
- 历史论文LED−1仅是原实验已记录的判定，不作为学生视频自动offset。
- CFR/时基准确性沿用现有门禁。VFR若只能近似处理，必须展示近似来源；不得宣称严格重现真实采样时刻。
- P0.1已固定：连续有效前5帧circular median且用户确认静止释放时ω₀=0；不足/非静止须显式固定IC，详见[scientific profiles](scientific-profiles.md)。禁止偷偷用第一个抽样点替代释放初态。
- 标定、release、有效观测、QC mask、分析区间或配置改变，相关θ、导数、fit、model comparison和valley全部stale。计算结果只能在输入版本仍匹配时提交。

## 5. QC and scientific profiles

必须分别呈现：raw prediction、manual correction、per-landmark likelihood、四点完整性、几何可用性、review状态、fit可用性。不得合成“科学认证通过”的单一分数。

- 几何QC：radius与校准像素半径的偏差；body separation与指定whole-video参考median的偏差；tracked pivot漂移；body pose/θ关系作为诊断。记录参考范围、参考值、阈值、逐帧原因。
- 历史radius10%、body20%有资产支持；pivot漂移新hard threshold没有已批准来源，未确定前只显示诊断。
- confidence不是accuracy、visibility或inverse variance；高置信可几何错误，低置信可几何正确。
- 历史拟合mask、benchmark四点mask和产品0.60过滤不同。D02已由P0.1分为legacy reproduction与严格四点student QC，禁止互相覆盖，均走同一数值核心，具体mask见[scientific profiles](scientific-profiles.md)。
- 缺测保持稀疏/NaN边界，不补0、不压缩时间；导数不跨缺测段，图表不连接缺口；不足数据给出量级明确的限制。
- 固定检查帧的比较资格继续clean/contaminated/unknown，失败关闭优劣判断；不以同一series ID或后续修正后的标签声称独立验证。

Scientific profile为**可序列化的配置数据**，不是第二套算法。来源版本、实际数值、单位、边界规则都保存；Normal与Advanced传入相同的resolved configuration。尚未批准的边缘政策标为待定，不填入“通用合理默认”。历史恢复清单及所有差异见inventory §4–6。

## 6. Core pendulum analysis

- θ(t)、ω(t)、必要时α(t)；ω论文profile为直接9-frame/third-order SG derivative、delta=dt、mode=interp；α的计算规则须单独定义，不能声称正文验证了它。
- 时间着色phase portrait，携带frame映射可返回视频；extrema可叠加并说明所用检测器。
- 周期通过有效连续片段内过零或明确extrema算法形成；whole-period/half-period分开。tail frequency与全轨迹fit的一致性明确标注same-trajectory check。
- 拟合前可显示`(g/L)(1−cosθ)`参考potential proxy；拟合后显示`e*=0.5ω²+ωobs²(1−cosθ)`。不得混称为J或机械能的独立测量。
- 半周期loss区分raw turning-point差值、平滑amplitude envelope差值及M1积分预测；主论文图的skip5/exponential-envelope规则可追溯，不能与phase discrimination的skip2混用。
- 对学生短视频、tail不足、extrema不足给出“此诊断不可用”的具体理由；不妨碍其它有证据支持的分析。

## 7. Full-trajectory ODE fitting

### 7.1 Scientific semantics

```text
M0: θ¨ + α1* θ˙ + ωobs² sinθ = 0
M1: θ¨ + α1* θ˙ + α2* θ˙|θ˙| + ωobs² sinθ = 0
```

拟合量是time-corresponding θ(t)，不是峰值包络、普通curve_fit或对微分后加速度做回归。不能改变观测时间以追齐phase。先从t=0与明确IC积分，在每个抽样观测的原t值比较。

P0.1固定的legacy基准（student显式继承/覆盖见profiles）：DOP853(rtol2e−7,atol2e−9)、最多500 valid samples、bounded least_squares、soft-L1 scale0.5°转rad、max_nfev180、x_scale=jac、M0三起点/M1三起点加M0 warm start、α₁/α₂界[0,0.5]、ωobs²界[0.20,1.60]g/L、tip likelihood floor0.05。精确选样、seeds、初态和隐式库默认见[scientific profiles](scientific-profiles.md)及其JSON，不从main GUI取值。

- 同一fit记录保存输入快照身份、实际sample frame/time、mask与weights、IC、bounds、全部starts、integration/optimiser配置及软件版本。
- 内部角度残差rad；Normal参数显示α₁* s⁻¹、α₂* rad⁻¹、ωobs² s⁻²。raw αa、α₁、α₂、ω₀²不是可独立识别的fit输出。
- 全轨迹RMSE在同一全部有效post-release样本上计算，与robust objective/抽样残差分开。
- 原始拟合代码用1e3残差惩罚integration失败；平台不能把全惩罚候选当有效fit，必须独立记录failure并检查最终forward solution。
- bound hit、nonconverged、integration failure、insufficient data、cancelled各有状态。失败不覆盖上次结果；误差改善不保证物理解释唯一。

### 7.2 Normal / Advanced

Normal：M0/M1、Run fit、参数/单位、RMSE、残差、overlay、comparison与必要状态。Advanced可编辑bounds、sampling、multistart、loss/scale、solver/tolerances、IC策略与fit interval，并能恢复profile；改变后显示新配置，不悄悄改旧结果。

一个Qt-free科学核心：输入数组+不可变配置→数值结果+诊断；不访问widget、ProjectSession、DLC、文件路径或数据库。Application层把当前输入冻结为request，后台任务执行，返回结构化result，主线程复核输入代际后原子提交。GUI只显示/编辑请求和渲染结果。脚本回归与GUI使用同一核心，避免“科研脚本一套、普通按钮一套”。

## 8. Model criticism and structural identifiability

### 8.1 Model criticism

最低交付：M0/M1共同区间overlay、raw residual vs t、完整RMSE、early/late或speed分层证据、匹配过零phase偏差、bound/convergence提示；energy/tail/length检查作为相应输入充足时的附加证据。M1多一个参数，不能仅凭较低RMSE输出“证明二次阻尼”。不把24个release当成数万独立重复帧。

### 8.2 C-level教学交互的最小正确架构

令raw reference `p=(αa,α₁,α₂,ω₀²)`，`s=1+αa>0`，则

```text
lump(p) = (α₁/s, α₂/s, ω₀²/s)
transform(p, λ) = (λs−1, λα₁, λα₂, λω₀²), λ>0
lump(transform(p,λ)) = lump(p)
```

若教学物理范围限制αa≥0，slider同时满足`λ≥1/s`；λ可行域来自全部raw参数约束的交集。不能clip各参数后还声称invariant。

最小组成：

1. 纯函数`lump / transform / feasible_lambda_range`，明确raw与starred的类型/单位；非正总惯性等输入拒绝。
2. 共用forward core，分别由reference与transformed raw RHS计算相同IC/时间上的轨迹；返回最大差与数值容差。禁止只复制同一数组制造“重叠证明”。
3. Qt-free教学状态保存reference、λ和派生值；来源可为当前M1的starred值构造一个标为illustrative的raw reference，不冒充测得αa。
4. GUI显示reference/raw transformed并排、三starred不变、trajectory overlay/差值、valley当前位置与说明；拖动去抖，丢弃迟到任务，不改当前fit。
5. objective valley复用fit residual/loss/sample/IC配置；说明条件切面中保持的是starred damping，未对其余参数逐格重新优化。可缓存一维q扫描后投影，验证选定网格点与直接objective一致；不新增昂贵全参数profile optimiser。

顺序必须是纯函数与synthetic tests → forward/objective invariance → worker/projection → GUI Human Review。测试包括λ=1、非平凡λ、composition/inverse、可行边界、各starred保持、独立raw RHS与lumped RHS一致、trajectory误差、objective不变，以及非等价参数对照确实改变结果。

结构不可辨识是理想观测下的连续等价族；不能写成parameter uncertainty、样本太少、noise、optimiser failure或“多跑几次能找到真实αa”。

## 9. Cross-platform application and AI runtime

首发必须有Windows x64 installer与macOS Apple Silicon app/dmg；source/environment安装只作为advanced/scientific fallback，不能作为桌面验收的替代。

采用轻量app installer + first-run AI runtime setup：

- 基础GUI、数值分析和已保存结果查看不依赖AI runtime已经安装；AI功能在自检通过后可用。
- 检测OS/architecture/硬件、CUDA可用性、MPS可用性或CPU；硬件检测只是候选，实际DLC训练与推理self-test决定兼容。
- 使用经过双平台验证的版本组合/下载清单；安装兼容PyTorch后安装/验证DLC，不在首次启动无约束追随latest。
- managed runtime位于用户可写应用数据目录，与签名app bundle和学生项目分离；版本化、失败可重试、部分安装不标ready、可修复/回滚，不改用户系统Python。
- 日志保留阶段、命令/错误摘要、版本、设备与log location；网络失败、空间不足、驱动/架构不兼容有具体下一步。
- 无GPU必须能在CPU训练/推理；MPS失败允许明确切换CPU。CUDA驱动安装不是普通runtime自动安装的隐含承诺。
- 下载前显示预计体积/空间需求；安装取消可恢复，安装成功后离线使用已准备的runtime和模型。通用backbone初次下载若需要联网也必须纳入setup，不在训练中无提示卡住。
- 冻结GUI不能假设其`multiprocessing.spawn`自动运行另一虚拟环境。优先评估managed Python独立worker入口+版本化JSON请求/进度/文件结果协议，复用现有job语义；不引入通用服务框架。该边界需P0早期技术验证。
- 两平台原生构建、签名/notarization与干净机器安装验证均纳入首发。具体打包器/最低OS版本/锁版本由spike证据决定，本轮不冻结未经验证的版本。

## 10. Persistence / export

复用Project/TrackPoint/Calibration/DerivedData与原子保存。最小扩展承载experiment角色、release、QC profile、teacher model reference、analysis/fit/identifiability配置与来源；具体schema在P0定，不提前写产品类。

需记录并验证多输入依赖：四Track、active run、manual版本、calibration、release、physical L、QC/reference、分析参数。现有单track DerivedData失效链不足以自动覆盖这些依赖，必须扩展输入签名/失效传播，不能仅增加图表kind。

导出至少包括：源帧、绝对与相对time、四点/likelihood/source/QC原因、θ/ω、period/energy、fit observed/predicted/residual、参数/配置/单位/版本、comparability说明、图表PNG/PDF。旧结果可查看但必须标stale；禁止把preview candidate当正式分析源。科学数据导出精度与屏幕显示精度分开。

## 11. Explicit non-goals

- 通用multi-object identity tracking、任意landmark skeleton、3D/multicamera、多摆/任意实验插件体系。
- 统一视频课程数据包、通用pendulum pretrained model、云训练/HPO平台、在线账户/教师班级管理。
- 通用model library/marketplace、跨引擎自动迁移、TensorFlow历史模型无条件兼容、所有GPU/所有OS版本支持。
- M2/Coulomb及更多竞争模型、SINDy、自动发现新物理、论文新的敏感性/统计/不确定度研究；结构可辨识教学不包含通用symbolic identifiability solver。
- 把raw added inertia单独拟合成可信物理估计，或自动生成独立参数CI；把QC/likelihood换算成accuracy。
- 论文文字修改、投稿metadata、补充材料编写、Zenodo/DOI/deposit、论文图重新生产。
- 巨型完全离线AI安装包、main Phase 6/7/8/9整体实现或机械同步、非本链路的UI重构。

## 12. Release-level acceptance criteria

以下均为未来验收项，不因本轮文档完成而勾选。

| ID | 验收标准 | 证据 / gate |
| --- | --- | --- |
| R01 | Win x64与Mac arm64干净非开发环境安装，首次setup后能启动/训练/推理；CPU路径真实可用 | 双平台安装记录、短train+infer self-test、至少Win CUDA及Mac MPS兼容探针；MPS不支持时CPU回退有明示 |
| R02 | 未参与开发的本科生用自己的视频完成完整链路，不编辑Python/YAML才能前进 | Human Review现场任务记录；train-own与teacher-import两分支都覆盖 |
| R03 | 同帧4/4标签、单dataset/frame split、四bodypart训练与推理真实跑通 | parser/exporter单测、fixed-check无泄漏、真实DLC小闭环；未完成帧不入训练 |
| R04 | 标定/符号/单位/释放时间正确，tracked pivot变化不改变θ原点 | 已知几何、相机roll、release与时序、缺测合成测试；Human Review校准显示 |
| R05 | QC、candidate/active/manual、review与完整帧语义保持，四点采用失败无部分写入 | 事务/取消/save-reopen/Undo与stale回归；四点审核Human Review |
| R06 | θ/phase/period/energy来源明确，gap与短数据不生成伪结果 | 解析小角/无阻尼/阻尼合成测试，选定封存golden数据对照，Human Review图表 |
| R07 | M0/M1同一scientific core实现、Normal/Advanced等配置等结果 | 数值单测、无噪声参数恢复、失败/界限/样本/IC检查；正式48行输出的软件回归按P0确定容差核对；不要求重训练历史网络 |
| R08 | 模型比较的分母/区间/QC一致，原始残差可查，不保证M1胜出 | M0 synthetic与M1 synthetic正反例，early/late/high-speed诊断单测与Human Review |
| R09 | λ改变raw但starred、raw-RHS forward trajectories和objective不变；可行域正确 | 纯函数synthetic tests先过，再独立科学review与C-level Human Review；不能仅截图证明 |
| R10 | 保存重开/修正后stale/重新计算/导出可追溯，两平台可重开同一结果项目 | source identity/配置round-trip、export字段与单位核对、取消/崩溃恢复场景 |
| R11 | 安装失败/断网/设备不可用/训练OOM/拟合失败都给具体恢复路径且保留已有数据与日志 | 故障注入及真人恢复流程；不把source安装fallback当安装器验收通过 |
| R12 | scientific discrepancy已逐项裁定或明确隔离，首发未宣称未验证能力 | Independent Review关闭blocking findings；Human Review通过；publication release notes仅报告真实验证 |
