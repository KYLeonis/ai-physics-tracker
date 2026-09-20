# EJP Publication Platform — Master Phase Plan

- 2026-09-19规划，2026-09-20文档收尾；状态：**requirements / inventory / master planning completed；P0–P6 均未启动实现**。
- Worktree `ai-physics-tracker-ejp`；integration branch `publication/ejp-damped-pendulum`。
- 产品基础：`62239fa` / immutable tag `ejp-damped-pendulum-baseline-phase5.7`；本轮调查HEAD `0e1e4f1`。
- 需求：[platform-requirements](spec/platform-requirements.md)；详细证据：[scientific-asset-inventory](spec/scientific-asset-inventory.md)；交接：[STATUS](STATUS.md)。

## 1. Planning conclusion

**这条发布线自行交付单摆科学分析与本科生桌面流程，不等待main Phase 6。** 复用Phase5.7的测量/AI/交互地基，围绕四landmark、明确测量语义、一个Qt-free科学核心和独立AI runtime做必要扩展。首发必须有自训与教师模型两条路径，以及Windows/macOS实际安装包。

推荐继续采用P0–P6的七阶段边界，但P0包含**runtime执行边界早期spike**，P1包含teacher model最小导入，不把这两项拖到全功能完成后才发现不兼容。P5是整链教学/导出收口，不能成为补造全部前期数据契约的阶段。

本轮只完成规划；所有spike、synthetic tests、golden回归、GUI与打包均是未来工作。下一步要先由用户启动P0，再交给Sol编写P0.1 mini-plan。

## 2. Scientific Asset Inventory summary

详细method/result → source asset对应见inventory A01–A16，含脚本、输入、配置、输出、数据库表和unknown状态。

| 类别 | 已发现与验证的证据 | 对计划的直接影响 |
| --- | --- | --- |
| 24 releases | 正式48行M0/M1输出；24份effective-release轨迹CSV.gz；相邻DLC_DATA有24CSV/TOML目录项 | 可从保存的θ与结果做软件回归，不要求重训练历史模型/重做论文实验 |
| SQLite | 149张表；`effective_release_formal_inversion_results`48行与封存CSV的关键参数/RMSE/release列一致 | DB可用，但必须按method/version选择表 |
| 旧数据混存 | DB `residual_trajectories`是旧LED口径，P011 3249点；论文effective文件是3250点、0–108.311227s | 不能“全部读取SQLite默认表”就称复现；P0固定source map，保留历史不改库 |
| Blind annotation | 3×72事件，88 unique frames、18视频，83帧repeatability；raw labels与recovered mapping有文件 | 科研输入完整性有证据；不是平台训练集；不把共享标定的盲标误差当绝对角度不确定度 |
| 177 DLC labels / model | 177行split、159/18划分、训练配置与selected checkpoint路径/哈希 | 用户确认保存；本轮不再追查实体，不阻塞规划。平台仍需未来用新小样本真实验收四点训练/教师导入 |
| 正式拟合源 | 正式入口`pendulum_peak_vs_trajectory.py`+models/fitting/pipeline；zip内`fitting.py`与正式hash匹配 | 旧`pendulum_inversion.py`的LM/raw/Fisher路线排除；同名脚本不能替代provenance判断 |
| 数值配置 | SG9/3直接导数；DOP853；500点；bounded multistart；soft-L1 0.5°；IC/bounds/weights已恢复 | publication profile独立，不继承main SG7/2或0.60截断 |
| Figures / physical checks | 正文Fig4–7的11个EJP source inputs哈希匹配；period/energy/valley脚本可读 | 提供golden evidence与算法依据，不把论文制图流程移入产品GUI |

### 科学决策入口（P0必须处理）

1. **D02四点QC差异**：正文all-four finite，正式fit mask未检查tracked pivot finite；main有0.60置信过滤，正式fit没有此硬截断。用户裁定legacy mask与student mask的命名/使用，禁止默默统一。
2. **D05不同诊断不同算法**：信息图extrema、half-cycle extrema、EDP extrema不同；skip2与skip5不混淆。energy raw/envelope/specific proxy分别定义。
3. **D06/U04新视频政策**：缺测分段/短段、manual权重、release前不足5帧、非静止IC、短视频tail、50点/50%有效门槛。历史值可恢复，任意新视频的默认不能伪称已验证。
4. **U03数值版本**：恢复SciPy隐式参数，约定跨平台容差和golden比较方式。历史Python3.13环境不直接替代产品Python约束。

这些是实现前的明确决策，不是本轮追加论文科学分析的任务。没有改写任何原始资产或论文。

## 3. Existing capability vs missing capability

静态核查以下实现；历史804 tests/双平台CI通过来自Phase5.7记录，本轮未重跑产品套件，也未把mock CI当真实DLC或安装器验证。

| 能力 | 现有代码 / 可复用内容 | publication缺失 |
| --- | --- | --- |
| Video/project | `domain/{project,track,track_store,timeline}.py`、`application/{project_session,video_session,video_timing}.py`、repository/serializer | Pendulum experiment角色、release-relative语义、关联输入失效；保留frame/time/raw像素体系 |
| Calibration | `domain/calibration.py`、`gui/calibration_dialog.py`；scale/origin/rotation与overlay | fixed pivot、true vertical的教学语义、tip半径与COM L分开、release frame入口 |
| Label / select | manual TrackPoint、uniform/K-means、困难帧review与Undo | 同帧4/4完整性、共享帧集、逐点/逐帧审核、共同split |
| Dataset / training | `application/{training_job,tracking_job,tracking_types}.py`；`infrastructure/{engine_adapter,dlc_adapter}.py`；后台任务、fresh per-run目录、fixed checks、resume | `prepare_training`硬编码`target`；exporter一行仅首bodypart填坐标；需要按frame join四Track，重用一次image导出与一次训练 |
| Inference | `application/inference_job.py`、`dlc_predictions.py`、DLCAdapter；raw predictions、阈值、model provenance、取消 | snapshot loader只接受`[target]`；request/run单track；逐bodypart解析/计数、批次成员校验；teacher import不能依赖本项目completed train run |
| Activation / validation | `refinement_history.py`、`suggested_frame_review.py`、ProjectSession；candidate隔离、manual优先、原子单track激活、资格三态 | 四track批次激活/replace/clear；固定检查帧与污染判定跨四role；不能将四个独立run伪装成一次模型推理 |
| Kinematics | `domain/kinematics.py`、`application/kinematics_job.py`；标定、NaN分段、SG、输入代际提交 | θ/ω、period、energy均未实现；SG7/2不是publication默认 |
| Charts | `application/chart_data.py`、`gui/{chart_actions,chart_panel}.py`；x/y/v/a/xy、frame联动、PNG | scalar angle、phase、period、energy、overlay/residual/valley、数据导出；当前adapter要求二维values，不能硬塞scalar pretending x/y |
| Workflow | `application/workflow_projection.py`；Setup/Acquire/Analysis、Normal/Advanced共入口、candidate/active/analysis独立 | experiment级条件、4/4计数、teacher分支、scientific stages与stale原因；继续是从事实重建的投影，不存第二套workflow真值 |
| Fitting / identifiability | repo无相应产品core；外部科研脚本可作为依据 | Qt-free M0/M1 forward/objective/fit、完整诊断/保存，raw transformation与valley教学 |
| Distribution | `pyproject.toml`将DLC列为必需依赖；`packaging/README.md`仅未来占位；现有spawn使用当前解释器 | 轻量app/外置runtime分离、worker协议、bootstrap/repair、版本清单、真实双平台包和签名验证 |

### Four-landmark最小必要架构改动

保留`TrackPoint`原子事实与四个普通Track，添加pendulum角色关联；将**一次job/run的输入成员**从一个track扩为有序role映射。共同dataset/frame split、一次推理、按role回填、四轨原子采用、共同依赖签名是完整最小闭环。旧single-track run可被显式适配为一个成员，不能让旧读者默默误解四轨数据。

`TrackingRun.track_id`、`DerivedInput.track_id`及图表二维约束都是真实耦合点。是否以版本化extension还是schema变更表达，由P0.2用旧项目round-trip/旧读者行为验证后定ADR；“extra_fields能存”不等于所有下游自动正确。无需引入对象身份关联、object detector、multi-animal或任意骨架框架。

## 4. Phase / Subphase plan

每个Subphase后续交给Sol写mini-plan，至少包含输入文档、Goal/Scope/Non-goals、可验证AC、Slices、验证命令、风险与Result。以下是边界与完成判据，不是实现授权。

### P0 — Scientific, Data and Runtime Contracts

- **Goal**：把历史证据、学生语义与执行边界固定为可实现契约，尽早暴露发行风险。
- **Scope**：source/profile与discrepancy裁定、experiment/run/model/result契约、误差容差/fixtures计划、runtime桥接spike、低保真流程评审。
- **Non-goals**：完成GUI、训练正式模型、重新生成论文结果、通用数据架构重构。
- **Dependencies**：本轮requirements/inventory；相关ADR0008/0009/0011/0012/0014/0016与data-model/project-format。
- **Major decisions**：legacy vs student QC；IC/gap/tail/manual weights；多Track单run的兼容表示；app/runtime协议；科学profile版本与正常/高级一致性。
- **AC**：所有阻塞科学分歧有用户裁定记录；源表版本和golden输入/输出/容差逐项列明；旧single-track与新four-role的读写/失效设计可审查；目标两平台的runtime桥接可行性有实测而非推测；未通过的平台项保持未完成。
- **Review gates**：科学契约与持久化Independent Review；用户确认D02等科学政策；runtime独立技术审查；低保真用户走查可做但不冒充最终GUI Human Review。
- **主要风险**：把“保存了数据”误当“算法版本唯一”；外部runtime与当前spawn不兼容；开局就引入过大schema改造。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P0.1 Evidence and resolved scientific profiles | 固定DB/file source map、精确参数、分歧清单、最小golden测试资产引用；只作软件复现准备 | 每个default能指向版本化来源；D02/D05/D06/U03/U04有明确处理；unknown不填猜测值 |
| P0.2 Experiment / run / derived contracts | 四role、release/calibration/L、teacher model、四轨原子事务、多输入stale、fit result与export契约 | 旧项目兼容策略和新字段validation明确；schema ADR proposal审定；Normal/Advanced请求同形 |
| P0.3 Distribution feasibility spike | 最小冻结app→managed Python worker桥接、PyTorch/DLC安装/设备self-test、版本组合调查 | Win x64及Mac arm64记录实际启动/小train+infer/取消结果，CPU可用；没有现成机器则如实留下gate，不推迟到P6才发现 |
| P0.4 Contracts close | 合并科学/数据/runtime结论，修订后续mini-plan输入 | Independent Review关闭blocking findings；用户关键科学选择记录；P0收尾后停止 |

P0.3只是风险验证，不建设完整安装向导；原型可删弃，只有已验证结论成为正式依赖。

### P1 — Four-Landmark Pendulum Measurement

- **Goal**：学生用自己的视频得到可审查、可采用的四landmark轨迹。
- **Scope**：experiment/calibration/release、同帧四点、multi-bodypart dataset/train/infer、教师模型导入、四轨review/QC/activation。
- **Non-goals**：通用multi-object、跨视频标签池管理、任意skeleton、θ/ODE产品界面。
- **Dependencies**：P0.1/0.2；运行边界遵从P0.3。
- **Major decisions**：共享frame membership与stable role mapping；import model有独立来源，不造假train run；同一模型批次一套provenance。
- **AC**：真实DLC四bodypart闭环；export每完整帧一行8个坐标；3/4帧不入训练；fixed checks四role共同排除；teacher模型对新视频推理；四轨采用/撤销/取消/保存重开无部分更新；tracked pivot始终QC role。
- **Review gates**：数据/AI生命周期Independent Review；标定、四点标注、teacher import、review/adopt各增量Human Review。
- **主要风险**：exporter看似支持bodyparts却只填首列；snapshot配置/路径不可携带；按单点统计误算训练量；旧激活逻辑跨role破坏一致性。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P1.1 Pendulum setup | role绑定、fixed pivot/vertical/scale/L/release与保存 | 几何/帧语义测试和setup Human Review通过；变更产生正确stale |
| P1.2 Complete-frame annotation | shared representative frames、4/4计数、共同split/export | round-trip与DLC格式检查；人工标签完整性/Undo/续标实测 |
| P1.3 Joint training and teacher model import | 一次dataset/training，最小Import DLC Model与兼容验证 | 真实训练产物及外部教师config+model都可被正确解析；错误bodypart明确拒绝 |
| P1.4 Joint inference, review and activation | 一次推理、逐点QC与四轨事务；困难帧修正 | 两条模型路径真实推理；candidate/active/manual一致；独立review+Human Review后收尾 |

### P2 — Pendulum Reconstruction and Core Analysis

- **Goal**：从已采用四点观测得到可信、可解释的θ/phase/period/energy。
- **Scope**：角度与时间、QC masks、SG9/3、extrema/period/tail、能量基础表示、scalar/phase图表与多输入失效。
- **Non-goals**：参数反演、普适信号处理工具箱、未批准的自动插值/校准修正。
- **Dependencies**：P1及P0 scientific profiles；纯数值开发可使用冻结输入，不以真实GPU训练完成作为写纯函数的前提。
- **Major decisions**：几何量与物理L区分；derived内容按scalar/series语义承载，不伪装二维；不同diagnostic各自profile；fit-dependent energy在P3再接结果。
- **AC**：合成旋转/符号/release测试正确；缺测不串段；9/3与source-derived ω按预定容差一致；period与无阻尼能量解析解验证；短tail不可用状态明确；图表frame导航/单位/状态正确。
- **Review gates**：科学数值与失效Independent Review；分析图/缺口/返回视频Human Review。
- **主要风险**：二次SG平滑、压缩时间、混淆尾部去中心与真实vertical、把g/L proxy称拟合specific energy。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P2.1 θ and QC core | signed angle、release-relative arrays、QC原因/共同mask、输入签名 | 几何synthetic+frozen θ复核；pivot QC改变不偷偷移动θ原点 |
| P2.2 Derivative, phase and periods | SG9/3、gap/short segment、extrema各profile、过零period/tail | 解析及封存数据核对；无跨缺口周期、无虚假频率 |
| P2.3 Energy and analysis UI | reference potential/specific-energy primitives、analysis adapter/charts、保存 | energy identity测试；学生能识别单位、缺口、来源与stale；Human Review收尾 |

### P3 — Full-Trajectory ODE Fitting

- **Goal**：以同一Qt-free core完成M0/M1全轨迹拟合与可追溯输出。
- **Scope**：RHS/forward、sample/weights/IC/bounds/seeds、robust optimisation、FitRequest/Result、后台执行、Normal/Advanced UI、完整RMSE/overlay与诊断。
- **Non-goals**：M2、raw四参数自由拟合、普通curve-fit框架、自动HPO、额外论文统计分析。
- **Dependencies**：P2.1/P2.2；P0 resolved profiles和golden结果；既有任务提交/取消机制。
- **Major decisions**：纯数值无Qt/DLC/IO；应用层冻结输入并在提交时核验版本；same input / same core / same result；边界/失败单独呈现。
- **AC**：M1在α₂=0时与M0一致；已知synthetic参数恢复；数值integration与energy identity达约定容差；500sample选择/weights单位正确；正式48行golden regression差异可解释并按gate裁定；取消/失败/过期结果不覆盖；Normal/Advanced等配置等结果。
- **Review gates**：先科学core Independent Review，后线程/持久化review，最后fit UI Human Review。
- **主要风险**：全惩罚residual误当成功、soft-L1尺度deg/rad错误、valid-frame序号压缩时间、多局部最小与跨SciPy版本差异、GUI冻结。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P3.1 Forward and objective | 两模型RHS、DOP853、IC、选样/weights、loss | synthetic和source golden unit checks通过；失败结构化，不访问GUI/文件 |
| P3.2 Bounded multistart fit | bounds/seeds/M0 warm start、逐start诊断、full-grid输出 | 参数恢复与48行历史结果软件回归记录；没有用论文目标值调参“凑一致” |
| P3.3 Application execution and persistence | snapshot请求、取消、代际、原子结果、stale与重开 | 注入取消/输入改变/失败不会提交部分或旧结果；配置round-trip |
| P3.4 Fit UI | Normal M0/M1与Run fit、Advanced配置、overlay/RMSE/residual | 同core证明、Human Review完成自选视频拟合；P3收尾停止 |

### P4 — Model Criticism and Structural Identifiability

- **Goal**：学生能判断模型在何处不足，并亲手验证raw参数连续非唯一。
- **Scope**：共同输入模型比较、regime/phase残差、tail/energy/length一致性、λ交互、等价trajectory、conditional objective valley。
- **Non-goals**：把更低RMSE认证成真模型；通用symbolic identifiability、raw参数CI、新论文实验。
- **Dependencies**：P3 core/result与P2诊断。
- **Major decisions**：先代数不变量，再独立raw forward，再UI；trajectory overlap为同IC结果，valley不是optimiser失败示意；教学exploration不修改fit。
- **AC**：M0/M1对比使用共同mask/区间；无法比较时给原因；energy no-refit与tail same-source边界清楚；λ identity/composition/inverse与可行域通过synthetic tests；raw/lumped RHS和objective invariance数值验证；改变非等价参数的对照不应重叠；用户可解释raw变化但starred不变。
- **Review gates**：变换、valley定义、比较统计Independent Scientific Review；C-level交互与结论文案Human Review。
- **主要风险**：clip打破invariance、直接复制曲线伪造证明、把conditional surface叫profile、混淆结构/数值/统计不确定性。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P4.1 Model criticism evidence | common-grid residual、speed/early-late/zero-crossing、tail/energy/length检查 | synthetic正反例及封存diagnostic核对；无“必然M1优”的断言 |
| P4.2 Identifiability pure core | lump/transform/feasible range、raw RHS、same IC/objective checks | 数学不变量+synthetic先通过独立review，才允许开始GUI |
| P4.3 Valley and λ teaching UI | raw参数并排、starred、overlap/difference、surface/cursor、取消与缓存 | slider不污染fit；直接objective抽点验证surface；完整C-level Human Review |

### P5 — Undergraduate End-to-End Workflow and Scientific Outputs

- **Goal**：把已有能力收为本科生可独立走通、可保存恢复和导出的单一实验流程。
- **Scope**：publication workflow projection、教学说明、两条模型路径、错误恢复、最小科学导出、跨平台项目可携带性、外部学生实测。
- **Non-goals**：LMS/课堂管理、通用model library、paper writer、复刻论文所有多视频统计图。
- **Dependencies**：P1–P4；runtime prototype用于整链测试。
- **Major decisions**：状态来自事实不是新workflow数据库；科研输出和显示截图分开；不隐藏partial/stale或“未发现困难帧”的限制。
- **AC**：未参与开发学生独立完成需求§2两条分支；四点校准/修正导致全部正确失效；中断后可恢复；CSV/JSON包含frame/time/unit/profile/source；PNG/PDF与选定数据一致；项目在另一平台重开无路径依赖丢失。
- **Review gates**：状态/导出/错误恢复Independent Review；学生端到端Human Review是硬gate，不以开发者截图替代。
- **主要风险**：各模块局部可用但整链隐藏步骤多；教师模型导入后仍被“先训练”卡住；导出丢失单位/出处；耗时和失败恢复难以理解。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P5.1 Publication workflow integration | Setup/Acquire/Analysis任务卡与两路径、取消/重试/历史 | 每种状态当前/下一步/能否分析有答案；无需UUID/snapshot选择 |
| P5.2 Save and scientific export | 项目重开、CSV/JSON/PNG/PDF、provenance、stale策略 | machine-readable round-trip/字段精度测试；跨平台项目样本核对 |
| P5.3 Student pilot and integration close | 自有视频、train/import两支、故障恢复、教学文字 | 非开发本科生Human Review通过，blocking UX finding修复复测 |

### P6 — Distribution and First Release

- **Goal**：在普通用户电脑上实际安装并运行完整平台。
- **Scope**：native build/installer/app/dmg、first-run setup/repair、硬件runtime matrix、版本锁定/下载、自检日志、干净机器验收、发行文档。
- **Non-goals**：巨型offline bundle、所有OS/GPU版本、云runtime服务、Zenodo/投稿/科学补充材料。
- **Dependencies**：P0.3已证明执行边界；P5整链通过；没有Windows真机就不能宣布双平台首发完成。
- **Major decisions**：app与AI环境物理隔离；按tested matrix安装、不追latest；CPU可用是底线；MPS/CUDA各自真实train+infer验证；安装程序可恢复。
- **AC**：Windows x64 installer与Mac arm64 app/dmg均在干净环境完成R01–R12；无Python预装前提；安装中断/断网/修复可恢复；日志可导出；已安装环境离线重开/推理；签名与分发依赖材料核对；包版本、runtime版本和项目来源明确。
- **Review gates**：打包/runtime Independent Review；两平台真实安装Human Review+至少一位非开发学生完整发行版验收。
- **主要风险**：wheel ABI/arch和驱动组合、DLC对MPS实际支持、冻结app启动外部解释器、签名/隔离环境、网络失败、下载backbone、超大依赖与空间。

| Subphase | 交付边界 | 完成判据 |
| --- | --- | --- |
| P6.1 Native application builds | 选定打包器，Win installer / Mac app/dmg、基础app无DLC也能开 | 两平台原生build与冷启动；安装位置/非ASCII路径/资源可读 |
| P6.2 Managed runtime setup and repair | tested lock matrix、下载/安装、设备探针、self-test、repair/logs | CPU、Win CUDA、Mac MPS探针实测；不兼容可明确CPU回退；取消/失败不留假ready |
| P6.3 Release candidate verification | 干净机器完整链、教师model跨机器、升级/重开/导出 | R01–R12逐条证据表、Independent Review与Human Review全部收口 |
| P6.4 First release close | 安装说明、已验证matrix/已知限制、版本与校验清单、软件发行构建 | publication分支发布候选完整可审查；按授权发布软件后停止，不执行论文deposit |

## 5. Dependencies and integration strategy

```text
P0.1 scientific profiles ─┐
P0.2 data contracts ─────┼→ P0.4 → P1 → P2 → P3 → P4 → P5 → P6
P0.3 runtime spike ──────┘                  └──── shared core ───┘
```

- **科学纵向闭环**：P1先让四点measurement可信；P2用已保存θ建立分析；P3同core拟合；P4在同一个core上展示非唯一；P5/P6完成教学与发行，不另写第二套科学流程。
- **早期集成**：P1起所有AI job遵循P0验证的worker边界；不等P6才把DLC从冻结GUI拆走。每阶段保留能打开/保存的增量，mock验证之外保留小型真实DLC smoke。
- **回归证据**：先synthetic可解析/可控测试，再选定frozen θ/golden结果。P3完整48行对照可作为慢集成验收，不要求每个commit重跑；参数非唯一时比较starred/forward/residual，按P0预设容差，禁止为了“通过”修改历史资产。
- **数据策略**：SQLite/封存CSV只读作为开发证据；小型经授权fixture及其来源可独立准备，模型/原始视频/大型数据库不入Git。first release学生用自己的视频，不分发统一研究视频来规避训练要求。
- **分支策略**：publication是本产品集成分支；后续subphase可用`codex/ejp-pN-M-topic`工作分支，完成后集成回publication，不能误合main。main修复按源commit/必要性/本线验证登记；不要求先在main实施publication-specific θ/ODE功能。
- **Review策略**：每个涉及科学、公共接口、持久化、AI/runtime生命周期的subphase独立review；GUI增量按workflow§5.1等待用户亲测。每Phase收尾后停止，等待用户下一条指令；本轮结束不自动开始P0。
- **main status**：`docs/status/current.md`保留main Phase5完成/Phase6未立项事实；本线后续动作只看publication/STATUS。旧ADR是背景，不自动批准publication偏离，必要时新增publication ADR而非改写Accepted原文。

## 6. Early ADR proposals（只提出主题，不创建空ADR）

| 提案 | 为何早定 | 接受gate |
| --- | --- | --- |
| Pendulum measurement and multi-track run contract | role/run/activation/multi-input stale/旧项目兼容影响几乎整链 | P0.2独立数据审查；若破坏格式须用户明确批准 |
| Publication scientific profiles and result provenance | D02差异、IC/gap/default冻结，避免UI与脚本各自一套参数 | P0.1科学裁定与Independent Review；仍保留legacy evidence不改写 |
| Lightweight app + managed AI runtime boundary | pyproject依赖拆分、解释器/worker协议、跨平台安装路径后改代价高 | P0.3实测后定工具与版本；本轮只接受用户已定的发行方向 |

不为普通命名、每张图表或每个subphase另立ADR。

## 7. First-run runtime risks and verification

以下是实施风险判断，不是声称已完成技术选型。官方文档查阅于2026-09-19：
[DeepLabCut installation](https://deeplabcut.github.io/DeepLabCut/docs/installation.html)、
[PyTorch installation selector](https://pytorch.org/get-started/locally/)、
[PyInstaller multiprocessing/subprocess pitfalls](https://pyinstaller.org/en/latest/common-issues-and-pitfalls.html)、
[PyInstaller native platform builds](https://pyinstaller.org/en/latest/usage.html)。版本冻结时必须重新核对。

| 风险 | 具体失效方式 | 最早验证 / 首发处理 |
| --- | --- | --- |
| Python / wheel / ABI | DLC、torch、torchvision、NumPy/HDF等组合在arm64/Win不同；历史分析Python3.13不等于DLC runtime版本 | P0.3按平台锁定实测矩阵；禁止安装unbounded latest |
| CUDA / MPS / CPU | 设备“存在”不等于DLC训练+推理工作；CUDA驱动与wheel不匹配，MPS可能有unsupported ops/性能退化 | 小train+infer self-test；记录resolved device，明确CPU fallback；无GPU不阻断DLC |
| frozen host / worker | 当前spawn运行app解释器，不自动切到新venv；冻结进程/资源导入或DLL环境污染导致worker失败 | 早验证managed Python独立入口、结构化IPC、取消和错误日志；不把冻结app直接当pip Python |
| 首次联网依赖 | PyTorch/DLC及backbone体积大；代理/断网/权限/空间不足造成半安装 | staged安装、校验、可重试、原子ready、日志；下载体积透明；使用平台用户目录 |
| macOS分发 | arm64二进制、最低系统版本、签名/notarization、下载隔离、app bundle写权限 | native Mac构建，runtime放用户目录，干净机器测试启动/修复 |
| Windows分发 | DLL/VC runtime、杀毒/进程回收、路径长度/中文、CUDA真机未验收 | native Win构建；真实机器CPU/CUDA与取消/重开测试，不靠mock CI |
| 教师模型携带性 | `.pt`之外还需DLC配置、架构/engine版本、bodypart与snapshot解析；训练绝对路径失效 | P1.3就验证从另一项目/机器导入；拒绝缺件有修复提示，不要求重训才能导入 |
| 依赖分发材料 | 仓库AGENTS/旧文档与ADR0011的License表述不一致，不能当最新完整发行清单 | P6基于实际锁定依赖/当前LICENSE核对发行材料；本轮不改License或给出法律结论 |

## 8. Most likely first-release blockers

1. **四点AI全闭环事务与教师导入**：改动跨dataset/run/inference/validation/activation/GUI，单点mock通过不足以验收。
2. **scientific defaults / QC分歧未裁定**：会使θ/fit/历史回归基准不唯一；先在P0解决，不靠实现者猜。
3. **外置AI runtime与双平台发行**：现有spawn与依赖声明尚不支持用户指定发行方式；Windows/CUDA没有现成真机通过证据。
4. **ODE数值正确性与可诊断失败**：跨版本、初态、sample/time、robust objective及全轨迹RMSE任何混用都会造成“看似能拟合”的错误。
5. **新手整链验收**：4/4标注、科学输入不足、训练耗时、teacher分支、stale与导出必须可理解，开发者操作成功不等于本科生能独立完成。

原始24视频/checkpoint实体的本轮可访问性不是blocker；用户已明确无需追查。结构可辨识GUI也不能降为几行starred参数来绕过首发验收。

## 9. Completion boundary for this planning session

交付requirements、可追溯inventory、phase/subphase计划与publication状态/入口同步；不新增产品代码、测试、依赖、数据库、构建脚本或GUI，不启动任何Publication Phase，不修改论文/原始科研数据，不做新拟合、训练或投稿事务。
