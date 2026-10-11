# 论文线与 main：功能、UI 与回移区别清单

> 2026-10-11 固定快照。结论：论文线已经形成“四点单摆实验 → 联合 AI → 科学分析 / 教学 → 独立运行环境 / Mac 预发行”的完整扩展；main 仍是 Phase 0–5 的通用单轨产品。可以分批吸收，但没有适合整分支 merge 的候选。
>
> 本文覆盖全部 tracked 文件差异、分叉后提交及产品模块入口，区分 **已进 main / 已在维护分支 / 论文独有 / 主线独有**。它是功能与实现差异审查，不是重新完成科学正确性、真人体验或发行验收。

> 后续状态（2026-10-11）：用户已确认上一轮主线维护 HR 通过，进入集成收尾。本文比较表与 TSV 保留扫描时固定快照；当前进度见[状态入口](../status/current.md)。

## 1. 比较对象与范围

| 对象 | 固定 commit | 实际状态 |
| --- | --- | --- |
| 通用产品 `main` / `origin/main` | `50a79241753a72c5d232b81ee1fdce49572b3407` | Phase 0–5 完成；Phase 6 仅有规划草案 |
| 论文集成 `publication/ejp-damped-pendulum` / origin | `b459e4affcdc2072ebe25bc7905e65e095372138` | 已集成到论文 P6.3 Mac 开发交付 |
| 论文最新工作线 `codex/ejp-p6-4-release` / origin | `154f262c6ff53e96dff7ba349333f1527ba43796` | 包含 P6.4 LGPL 修复、鼠标 / 深色提示修复与发行记录；尚未集成论文长期分支 |
| 当前主线维护 `fix/main-ui-backports` / origin | `3c435444522bb7a0197d48d7045a73f5f95fe2a7` | 五项通用修复、顶部下一步推荐已实现；自动验证通过，等待 Human Review，未进 main |
| 已发布 Mac 预发行 `v0.1.0` | `54638e484ca3160d2d335e8f78c0580bef21949a` | 发行源码固定于此；后续 `154f262` 是发行记录文档 |

两个 worktree 均干净；本轮已 fetch 并确认上述远程与本地 refs 一致。共同祖先为
`41580580220019844fef690974c772402126d6ef`。`main...论文最新工作线` 的可达提交计数为
**7 / 229**，论文侧含 **207 个非 merge 提交**。其中 **13 个提交**尚未进入论文集成分支。
因此只看 `publication/ejp-damped-pendulum` 会漏掉最新发行与 UI 修复。

完整文件 diff 为 **637 个文件，115103 行新增 / 798 行删除**，包括：

| 类别 | 文件数 | 说明 |
| --- | ---: | --- |
| 产品源码 | **80** | **53 新增 / 27 修改**；没有源码删除 |
| 测试及夹具 | **62** | **43 新增 / 19 修改** |
| 论文合同、profile、证据、计划 | 100 | 包含冻结数值证据，并非 100 个产品功能 |
| 打包 / runtime 资源 / 上游许可材料 | 321 | 差异数量的大头，不宜用文件或行数衡量功能量 |
| 共享文档 / review | 45 | 两条线各自状态、规范、决策与审查 |
| 开发 / 证据 / 构建脚本 | 18 | 数值 parity、runtime、native build、来源核验等 |
| CI | 3 | tests 修改，packaging / runtime-profiles 新增 |
| 根目录配置 / 文档 | 8 | README、AGENTS、LICENSE、依赖及忽略 / 换行规则 |

更正扫描中间口径：最初进度消息的“81 个源码”是计数误差；固定 refs 的最终 inventory 与
`git diff --name-status -- src/` 均为 **80**。

可逐项检查的附件：

- [全部 637 文件清单](publication-main-difference-inventory.tsv)：A/M/D、分类、两端 blob SHA、是否与维护 / 论文集成端相同。
- [全部 229 提交清单](publication-main-commit-inventory.tsv)：完整 SHA、时间、标题、merge 标记、论文集成归属、main patch 等价标记。
- [全部 80 源码模块覆盖表](publication-main-source-coverage.md)：模块职责、顶层入口；新增类的方法仍以实际源码为准。

清单方向是 **main → 论文最新工作线**。其中 D 的 6 个文件是主线专用文档，
不代表论文功能删除了主线数据。`maintenance_vs_paper=different` 也不等于“尚未回移”：
同一文件可能已经部分适配回移，仍有大量论文专用代码，须结合第 2 节判断。

## 2. 同步状态：先避免重复开发

| 项目 | main | 当前维护分支 | 论文线 | 判断 / 来源 |
| --- | --- | --- | --- | --- |
| 三工作区、单轨手工标注、训练 / 推理、困难帧审核、显式采用 | 已有 | 已有 | 保留，并增加实验路径 | 不是论文新增的整套基础工作流 |
| 取消时强杀后确认 worker 退出 | 已有 | 已有 | 等价同步 | main `bf8f0c5` / `8a7d90d` ↔ paper `4d4e3e9` / `6323e11`；`git cherry` 为 `-`；task_runner 源码 / 测试无 diff |
| 单轨 auto：CUDA → MPS → CPU | 已有 | 未改行为 | 相同探测器；联合路径另修复 | paper `5ada419` 修的是联合 / external runtime 固定 CPU，不是主线单轨缺陷 |
| 单轨实际帧推理进度 | 已有 | 已有 | 联合路径也接入，并加速率 / ETA | 不应把论文联合进度修复说成主线完全没有进度 |
| 普通垂直鼠标滚轮缩放 | 尚无 | **已实现** | 已实现，最新发行工作线 | paper `a13b4b1` → main 适配 `53a6fb9` |
| 固定浅背景的引导 / Correct 前景色 | 尚无显式前景 | **已修复** | 已修复 | 同上；顶部提示前景随推荐框一起实现 |
| 标注 / 标定时黑边 viewport 光标 | 尚无同步 | **已修复** | 已修复 | paper `0f04896`，只取通用 cursor 部分 |
| 任务历史完整本地年月日与秒 | 尚无 | **已实现** | 已实现 | paper `231e4d8` / `7cda8cd` |
| 长 stage 提示换行 | 尚无 | **已实现** | 已实现 | paper `827f31f`，不带联合任务 Discarded 状态 |
| 顶部常驻下一步摘要 / 推荐按钮 | 尚无 | **已实现** | 已实现 | paper `9f5cff7` 的呈现思路 → main `8c16908`；复用 main TaskCard / dispatcher |
| 分析页视频只读 | **尚无保护** | **尚无保护** | 已有 | 本轮新增的优先候选，见第 8 节 |
| Phase 6 通用规划与取消审查记录 | **主线独有** | 保留 | 未同步这些主线文档 | 不应以论文旧 roadmap 覆盖 main 的当前计划 |

维护分支顶部推荐显示一个主动作、最多两个旁路和不可用原因；无工程时推荐 Add video，
审核 / 标注动作切回获取轨迹。论文的推荐内容还涉及实验设置、教师模型、四点批次、科学计算 / 导出，
并未全部复制到 main。论文还有“标签已改变时优先重训”等 publication 特定判定（`87d5e89`）。

本轮之前维护验证为 **820 passed / 双平台 CI success**，Issue [#23](https://github.com/KYLeonis/ai-physics-tracker/issues/23)
仍 Open。没有用户 HR 反馈，不能把这些条目标为“已合并 main”。

## 3. 用户可见的 UI 与操作差异

| 入口 / 场景 | main 当前行为 | 论文最新行为 | 带回主线时的边界 |
| --- | --- | --- | --- |
| 打开 / 新建项目 | schema v1 通用 Video / Track 工程 | 保留通用工程；增加创建 Pendulum experiment 向导 | 向导与 schema v2 迁移是同一交付，不能只增加按钮 |
| File 菜单 | 通用 New / Open / Save / Save as / Relink / Close | 增加 Create Pendulum experiment、Import DLC Model、Save portable project copy、Export scientific results | 四个入口分别依赖实验 / 模型 / 科学结果 / 外部文件管理 |
| 实验设置页 | 比例尺、原点、坐标方向、时间 / working zone | 增加四轨 role 绑定、固定 pivot、参考半径、竖直方向确认、L/g 来源、release frame、完成度清单 | 可借鉴分步清单，但物理对象与输入语义需 main Phase 6 ADR |
| 视频叠加 | 标记点、标定线 / 原点 | 增加固定 pivot、真实竖直方向叠加与专用拾取模式 | 依赖 Pendulum 实验状态；不是普通 Marker 文案变化 |
| 获取轨迹 | 选中一个 Track，当前帧点一个目标 | 同帧按 tip → body_top → body_bottom → pivot 连续四点引导，显示缺失 role / 完整帧数 / 下一缺失帧 | 建议保留单轨流程；多点作为独立实验模式 |
| 推荐学习循环 | 原本右侧 TaskCard 已有动作；顶部推荐在维护分支待 HR | 顶部与面板联动，Acquire 六步循环：代表帧 → 四点标签 → 训练 → 推理 → 建议 → 重标 | 主线已吸收呈现方式；论文状态机依赖角色与模型事实 |
| 建议帧审核 | 单轨候选 Accept / Correct / Skip；Correct 写 manual，Accept 不造标签 | 四角色帧诊断、建议帧批量选择、逐帧四点连续修正；Pause / Esc / Skip / 完成后训练 | 适合学习“连续下一步”交互，四角色数据 join / review 事务须随模式实现 |
| 批量重新标注 | 按主线 review queue 修正单点 | 可从已有代表帧 / 建议帧选定批次，显示进度，保留旧帧集合，标签变化令 fixed-check 失效 | 来源 `72cbfff` / `ef63a38` / `ec2f34e` / `c794e18` / `916adeb`；不是独立小按钮补丁 |
| 引导入口跳帧 | 主线现有跳帧 / busy 拒绝 | decoder 忙时延迟重试引导入口，避免进入四点状态却停错帧 | `65d31a5`；连续异步请求边界，不能仅搬定时器 |
| 分析页视频 | 重挂视频为图表参考，当前标注模式可能保留 | 进入 Analysis 退出实验引导 / 标注 / 标定；选轨、建议跳帧也不重新启用标注；返回 Acquire 恢复编辑 | 通用、低耦合，优先回移候选；仍需 GUI HR |
| 图表点击定位 | `seekFrame` 限制在 working zone，并退出编辑 | 新 `seekSourceFrame` 可以只读检查 working zone 外的原视频帧 | 与 source frame / timeline / decoder 调用契约相关；不改变 working zone，本身不授权在外部帧标注 |
| 分析主体 | 通用 x/y、速度、加速度、speed 图表 | 增加单摆 Kinematics、ODE fitting、Model criticism、Parameter equivalence 页面；未绑定实验的通用轨迹仍可用原图表 | 将 main ChartActions 整体替换会丢失通用产品语义 |
| 模型选择 | 本工程单轨训练 / 推理记录与 Resume | 教师模型导入、model reference 列表、模型实际帧 self-test、联合推理模型选择 | 专用模型类型、manifest、兼容身份与 backend 是核心依赖 |
| 任务状态 / Cancel | 主线 train / infer 生命周期及 Cancel | 增加 model self-test / 联合任务占用，requested / actual device，自检后启动，帧数 / FPS / elapsed / ETA | main 单轨本来就能取消；不能复制 model_busy 分支却缺少对应任务 |
| 保存与自动保存 | 10 点静默 autosave；已有保存串行化 | 同工程正在 autosave 时可串接 `after` 回调，先存新增标签再继续学习；额外守卫模型 / fit / export | 可独立研究 autosave 续接，其余守卫依赖新增后台类型 |
| 长任务 / 深色 / 缩放 | 五项修复尚未进 main | 论文有这些修复 | 当前维护分支已做，避免再次开重复任务 |
| 导出 | 当前图表 PNG；普通保存 / Save as | 已存科学结果 CSV / JSON / PNG / PDF；portable copy 包含受管模型和媒体 | 主线 Phase 8 的更完整导出仍需独立设计，不宜声称 Excel / 视频导出已完成 |
| 安装 / 启动 | 依赖开发 Python 环境 | 原生 App / DMG，独立 AI 环境配置、安装 / Repair / diagnostics | 主线 Phase 9 输入，依赖 / License / worker 架构须一起评审 |

论文 UI 关键实现入口（固定源码，避免后续 branch 漂移）：
[MainWindow](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/gui/main_window.py)、
[推荐事实投影](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/application/publication_workflow.py)、
[实验设置](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/gui/pendulum_setup.py)、
[四点审核](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/gui/experiment_review_dialog.py)、
[模型操作](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/gui/model_actions.py)。

## 4. 数据模型、AI 与持久化差异

| 契约 / 能力 | main | 论文线 | 回移影响 |
| --- | --- | --- | --- |
| 项目版本 | schema v1 | v1 / v2 双读；通用 v1 仍保存 v1，显式 SaveAs 新副本才升级实验工程 | main 不能打开 v2；无自动降级 / 反向兼容保证 |
| publication 扩展 | 没有 experiments / model_references / scientific_results | v2 集合与 required_capabilities：`pendulum-four-role-v1`、`scientific-results-v1` | 数据模型、serializer、repository、session、tests 必须成套 |
| 迁移 | 通用 Save as | 源 v1 保持不变；保存 IDs、源 manifest SHA 与迁移记录；未知字段保留，冲突 fail-closed | ADR-0017 是论文线契约，不自动成为主线决策 |
| TrackingRun 成员 | 单个 `track_id` | 有序唯一 `member_track_ids`、experiment_id / role_bindings；四轨同视频固定角色 | 单成员兼容属性保留；多成员读取旧 `track_id` 会拒绝，所有消费者需适配 |
| 联合标签 | 独立 TrackPoint | `annotation_join` 仅完整同帧四 role 进入一图一行的训练导出；有明确 label digest / fixed-check | 部分标签、建议帧不会伪装成训练 ground truth |
| 联合训练 | 单 bodypart `target` | 四 bodyparts 联合 DLC 项目、训练请求 / manifest / checkpoint 验证 | 并非把四次单轨训练拼接；需要联合请求、模型角色与运行身份 |
| 联合推理 | 单轨候选产物 | 同一模型 / 视频产生四轨候选；严格 scorer / bodyparts / x-y-likelihood / frame count 检查 | raw NaN / 低置信保留，不把坏行静默抹掉 |
| 采用与失效 | 单轨显式 Activate / Replace / Clear；manual 优先 / Undo | 四轨原子采用、替换、清除；保留 manual 与旧候选；bound tracks 限制旧单轨 mutator，科学结果 stale | 高风险 AI 激活 / Undo 事务，不能单独搬 UI |
| 结果身份 | 主线既有请求、媒体检查；采用产物指纹 size-only | 扩展 SHA256、输入 digest、runtime / model / 原视频身份，提交与读取时复核 | 是可学习的防陈旧结果边界，但升级成本高于局部 fix |
| 科学结果 | DerivedData 与通用分析输出 | 不可变 payload + config / 版本 / 输入哈希 / SHA；旧结果可读，改标签 / 标定 / 来源后 stale | 不应覆盖历史结果，重新计算产生新结果 |
| 受管路径 | 既有 Windows-safe 路径验证 | 共享 domain.paths；模型、科学 payload 和 export 路径复用 | 重构主要支撑新增集合，未发现必须单独带回的通用路径漏洞 |
| 新工程目录 | main 拒绝已存在目录 | 允许预建空目录 / 已知 Finder 元数据，且只清理已核验元数据快照 | `2b77d2e` 必须连同 `199bc52` 并发文件保护；后者修论文新增行为，main 当前没有该清理路径 |
| autosave 续接 | busy 时 autosave 直接返回 | 同 session 的静默 autosave 可接续 completion，再保存 / 调 after | `916adeb` 可候选，但涉及生命周期；不能扩为所有文件操作接续 |

论文的模型导入验证目录 / config / checkpoint、显式 bodypart 映射及文件哈希，
复制为工程受管资源，不执行来源脚本，也不伪造“本工程训练完成”的 run。
模型 self-test 使用实际视频帧；兼容结果绑定模型 manifest、runtime 版本与明确设备，
改变这些条件后旧自检不能冒充有效。

论文当前单轨和联合路径都选择 DLC 生成的 **CSV** 作为声明 / 哈希 / 解析产物（`146c6a3`），
避免 frozen GUI host 没有 PyTables 时读取 HDF5 失败。main 单轨仍选择 HDF5，但已有 CSV 解析支持，
且 AI 与 GUI 尚在同开发环境。可以在拆分 host / runtime 时采用此边界；当前不能据此断言所有 main 推理都有故障。

设备结论保持不变：main Start learning 的 auto 不被系统学习计划覆盖，worker 按
CUDA → MPS → CPU 解析；本机实测 MPS 可用，实际张量在 mps:0。论文 `5ada419` 改的是
联合与 external runtime 固定 CPU、self-test 设备身份。MPS 已被选中后失败会报告失败，
不会静默改用 CPU 重训。详细探针与限制见[前次设备核查](publication-backport-assessment.md#start-learning--macos-auto-设备核查2026-10-11)。

领域与存储证据：
[ADR-0017](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/docs/decisions/0017-publication-project-contract.md)、
[ProjectSession](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/application/project_session.py)、
[v2 serializer](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/infrastructure/publication_serializer.py)、
[联合预测解析](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/infrastructure/dlc_predictions.py)。

## 5. 单摆科学分析、拟合与教学差异

| 能力 | main 当前状态 | 论文最新实现 / 限制 |
| --- | --- | --- |
| θ 重建 | Phase 6 草案，未实现 | **tip + 已标定固定 pivot** 计算角度；body_top / body_bottom 与跟踪 pivot 用于辅助诊断。`869e504` / ADR-0018 后的规则，不能照抄早期“四点全有效才算 θ”的历史描述 |
| 时间原点与 IC | 通用 Timeline、Cartesian 分析 | 相对时间 = Timeline(frame) − Timeline(release_frame)；释放前连续五个有效 θ 的 circular median；静止释放需明确确认，才固定初始 ω=0，否则用显式 IC |
| QC | 主线缺测 / 置信与轨迹分析 | 主 tip 半径容差 ±10%；body 间距 ±20% 为辅助诊断，pivot 漂移不作为动态原点或未批准硬门槛；manual 无 confidence 不填成 1.0 |
| SG 与求导 | SG 先平滑后微分，默认 7/2，短段缩窗；ADR-0008 | 角速度使用直接 SG 导数，默认 9/3，可显式调奇数 window / polyorder；短段不可用，不跨缺测段。ADR-0019 与主线不是同一数值契约 |
| 角量 / 图表 | Cartesian 位置 / 速度 / 加速度、speed | θ（rad / 显示 deg）、ω（rad/s）、随时间着色的 θ–ω 相图、分段周期 / 极值；**没有通用角加速度 α 输出** |
| 参考能量 | 未有单摆专用能量 | `0.5*ω² + (g/L)*(1-cosθ)`，单位 s⁻²，是 reference proxy，**不是焦耳、不是拟合能量**；导数不可用时势能可用、总能量空缺 |
| 保存分析 | 主线 DerivedData | 分析结果不可变保存，含选区 / QC / SG 参数 / 版本 / 输入身份；图表显示选定结果与 stale 提示 |
| ODE 拟合 | Phase 6 未实现 | raw θ 时间序列拟合 M0 线性阻尼 / M1 增加速度二次阻尼；共享 bounded multistart、robust objective、DOP853、显式 interval / IC / sample / loss。拟合不依赖 SG 是否能算 ω |
| 参数与权重 | 未有 ODE 对应能力 | tip AI likelihood 转数值权重（下限 0.05），manual 权重 1 是数值策略；likelihood 不是测量精度或校准不确定度 |
| 拟合 UI | 无 | Normal / Advanced 共用 core；进度报告 elapsed / 当前 start / 已用时，不编造可靠总 ETA；支持后台取消、失败与 stale 拒绝 |
| 积分精度 | 无 | 新 UI 推荐 High precision：rtol 2e-10 / atol 2e-12；Historical 为 2e-7 / 2e-9；实际值保存进结果，无静默重试 / 偷换历史 profile |
| 模型批判 | 无 | 保存 fit 的残差、速度分层、能量损失 / 尾频 / 表观长度诊断；M0 / M1 同输入比较资格，不输出模型正确性认证 |
| 参数等价教学 | 无 | 固定观测，raw 参数族与 λ 滑块、可行边界、直接 raw ODE 预览 / 目标面；条件目标谷不是完整 profile likelihood 或置信区间 |
| 通用误差分析 | Phase 6 草案 | 论文不能据此视为已经完成通用误差传播、α、任意实验拟合、多目标分析全部需求 |

**科学回移必须保留已知限制。** ADR-0020 明确接受历史默认回归缺口：
**E3 30/48（M0 24/24、M1 6/24），E2 47/48**；strict xfail 不计作数值通过。
显式高精度 synthetic 恢复与 UI 可用，不代表历史默认拟合已经全部复现，
optimizer success 也不表示参数唯一或模型正确。将论文数值模块引入 main 前，必须重新制定主线 AC，
不能继承测试绿就宣布 Phase 6 完成。

参考：
[角分析核心](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/domain/angular_analysis.py)、
[重建核心](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/domain/pendulum_reconstruction.py)、
[参考能量](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/domain/pendulum_energy.py)、
[拟合 core](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/domain/pendulum_fit.py)、
[ADR-0020 与历史限制](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/docs/decisions/0020-explicit-fit-precision-and-historical-regression-limit.md)。

## 6. 导出、环境、打包与配置差异

| 领域 | main | 论文线 | 处理建议 |
| --- | --- | --- | --- |
| 科学 CSV / JSON | 未有 | 从**选定已存结果**导出绝对 / 相对时间、四角色坐标 / 来源 / confidence / QC、θ / ω / 参考能量、fit 观测 / 预测 / residual；JSON 留完整配置 / starts / IC / 版本 / SHA | 不用当前轨迹偷偷重算历史结果；默认拒绝 stale，可显式导出冻结历史 |
| 科学 PNG / PDF | 原通用图表 PNG 快照 | Qt 原生独立图，不截图 widget；按保存结果渲染，包含导出列匹配 / 排版修复 | `2fca191` 修 m0/m1 曲线映射、`98bfd25` 修 ylabel；当前 main 没有对应导出函数，不能当作 PNG 快照 bug |
| portable copy | 通用保存 / 媒体管理 | 打包媒体、受管模型、科学资源与来源；缺失外部资源明确失败 / relink；输出原子发布，取消保留旧目录 | 可供 Phase 8 参考，依赖结果 / 模型集合；不能回写或降级源工程 |
| GUI / AI 依赖 | 同开发 Python 环境；DLC 为 pyproject 必装依赖 | GUI host 不强制 DLC，`.[ai]` 可选；worker 在专用 Python 环境 | 不只改 pyproject 一行：启动、任务路由、安装、协议验证要一致 |
| external worker | 既有 spawn worker | 独立进程 request/result 协议、受信源码 SHA、清洁 env、来源 / runtime / device / output hash 校验、取消进程树 | 高风险生命周期 / 信任边界迁移，主线现有取消修复应保留 |
| AI 环境设置 | 无安装 UI | CPU / MPS / CUDA profile，下载大小 / SHA 校验、安装锁、取消、self-test、Repair、diagnostics 导出；UUID 最终目录 + active pointer 原子激活，保留旧环境 | `.venv` 不能靠移动目录修好；需要完整 runtime 安装模型 |
| 依赖配置 | 主线既有 requirements | 增加 pandas 2.3.3 / PyYAML 6.0.3；固定 Python / Torch / DLC / wheel profile | 为论文 runtime / parser 服务；本轮不新增依赖 |
| App 启动 | 开发入口 | frozen `freeze_support`、日志 / AppData、应用身份、内置 ffprobe、设置菜单 | 是打包组合根变化，不是 UI cosmetic |
| 原生构建 | Phase 9 尚未开始 | PyInstaller onedir；Mac `.app` / DMG；Windows zip 候选；host 不含 Torch / DLC | Windows zip 不等于最终 Windows 安装程序已验收 |
| CI | tests push：main / feat/** / fix/** | tests 另支持 publication/** / codex/**；新增 native packaging、runtime-profiles | **codex/** tests trigger 是可独立带回的小配置改进**；若继续用 fix/** 当前不会缺 CI |
| 换行与忽略 | 基础规则 | golden / 原文 license 保留字节，profiles LF；新增 runtime / publication 产物忽略、`.zcodeignore` | 配置服务对应证据 / 打包，不应无内容全量复制忽略规则 |
| License | TBD；AGENTS 中历史 DLC 许可提示仍需正式核对 | 项目 MIT + 第三方材料；Mac cv2 FFmpeg 已做同 ABI LGPL 替换（`5fe09ca` / ADR-0023） | **不自动把 main License 改成 MIT**；也不继续把 paper 最新包当作旧 GPL 候选 |

论文最新 [v0.1.0 公开 prerelease](https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0)
于 2026-10-09 发布，本轮用 `gh release view` 重新核对：固定源码 `54638e4`，**11 项资产**，
Mac arm64 DMG 196260240 bytes，SHA256
`cf6afbbeaf11be77322761faa74418b814ac7986b3cb582f3f786bb45ab3e0e0`。
Windows 包留在 Actions；没有同等 Windows 二进制公开发行。

这是一份 ad-hoc、未 Apple 公证的 Mac 测试发行。论文 STATUS 仍保留：Windows 完整实机 / CUDA、
最新 GUI HR、外部学生 pilot、安装版 teacher-import、完整科学 / portable 导出恢复验收待补。
不能把已有 Mac 开发交付 HR / 双平台 CI 扩大成“全部功能与发行门禁通过”。

证据入口：
[科学导出](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/application/scientific_export.py)、
[external worker](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/infrastructure/external_worker.py)、
[runtime 安装](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/src/ai_physics_tracker/infrastructure/runtime_install.py)、
[论文最新 STATUS](https://github.com/KYLeonis/ai-physics-tracker/blob/154f262c6ff53e96dff7ba349333f1527ba43796/publication/STATUS.md)。

## 7. 共享代码、测试和文档的覆盖说明

除了新模块，下列共享调用链均纳入比较；避免只扫新 UI 文件漏掉后台前提。

| 共享层 | 实际变化重点 |
| --- | --- |
| domain project / tracking_run / types / video | publication 集合与成员不变式、canonical digest、共享路径验证；旧单轨模型的兼容边界 |
| project_session / repository / serializer | v2 显式迁移、角色 / 帧集合 / 模型 / 科学结果、四轨采用与失效、空目录保护、payload 原子发布 |
| training_job / inference_job / tracking_job / tracking_types | bound track 守卫、成员筛选、experiment_id、联合 / external-worker 任务入口；保留主线单轨行为 |
| advisor_collection / workflow_projection | run 成员判断、publication facts / action 可用性；不将实验推荐误当通用主线 action |
| playback / video_session | 只读 source frame 访问，与 working-zone 编辑分开 |
| GUI app / main_window / tracking_actions / project_actions | 新 actions 接线、推荐 / guide / 只读分析、批次标注、异步任务守卫与 autosave 接续 |
| GUI task_panel / video_view / workflow_header | 模型 busy / 进度 / 历史、叠加 / 光标 / 滚轮、顶部推荐 / 深色提示；部分已适配回移 |
| infrastructure dlc_adapter / dlc_predictions / errors | 联合 export / train / infer / self-test，CSV 交付与严格外部数据校验，ExternalWorkerError |
| __main__ / worker | frozen 组合根、独立 runtime 协议与日志 / AppData |

新增测试主要覆盖：v2 / migration / serializer、四角色 join / guide / training / inference / atomic adopt、
teacher import / self-test、θ / QC / SG / energy、ODE / model criticism / equivalence、scientific export / portable、
worker / runtime / native bundle / 新 GUI。共有测试的修改主要适配角色成员与新占用状态、以及通用 UI fix。
新增证据脚本包括冻结输入 / profile / E2-E3 regression、科学证据校验、native smoke、
runtime / packaging / signing / source-material 校验；清单保留每个具体文件。

main 独有的 6 个文件为：本轮此前 backport assessment、Windows cancellation review / mini-plan、
Phase 6 requirements / master plan / 6.1 mini-plan。论文自己的 P0–P6 编号对应 publication scope，
**不是通用 roadmap 的 Phase 0–6**；论文 P6 打包不能作为 main Phase 6 已完成的证据。

## 8. 建议回移顺序与具体候选

| 顺序 | 候选 | 最小范围 / 判断 | 验证与门槛 |
| --- | --- | --- | --- |
| 先完成 | 当前五项 UI fix + 顶部推荐 | 已在 `fix/main-ui-backports`；保持 Issue #23，不另开重复任务 | 既有 820 / 双平台 CI；按现有 mini-plan 完成用户 HR 后集成 |
| **下一项优先** | **Analysis 视频只读** | paper `42e853d` 中只取 workspace / annotation / calibration 守卫；排除 Pendulum actions 与 source-frame / science hunks | 切换 / 选轨 / 跳帧 / Correct / 返回 Acquire 的交互回归与 HR |
| 次优先，先复现 | autosave `after` 续接 | paper `916adeb` 的同 session 静默保存 completion；不带实验 / model / fit 代码 | main 实际 busy 场景、失败不续跑、换 session 不续跑、新标签完整存储；后台生命周期按高风险 review |
| 小配置维护 | tests 的 codex/** trigger | `.github/workflows/tests.yml` 一处；publication trigger 取决于是否继续在主线管理该长期分支 | YAML / 触发规则核对；当前 fix/** 分支已被覆盖 |
| 有需求才做 | 新工程允许预建空目录 | 成套取 `2b77d2e` + `199bc52` 的保护与回归，不能单取便利行为 | persistence / 并发 review；现 main 拒绝目录不是数据丢失 bug |
| Phase 6 输入 | tip + fixed pivot、θ / ω / 周期、明确 QC 与保存结果 | 优先提炼 Qt-free 数值 / 应用契约，结合 main 通用单轨 / 双轨需求；SG、α、结果 schema 先明确 | 主线计划 / ADR / 新 AC / Independent Review，不整搬论文 ScientificResult |
| Phase 6 后续输入 | ODE / model criticism / equivalence UI | 保留高精度与历史失败证据；实验教学范围不代替通用误差分析 | 数值验证 / 输入资格 / 失效 / HR；禁止以 xfail 充通过 |
| Phase 7 / 多点模式输入 | 四点学习、教师模型 / self-test | 独立模式与模型契约；利用现有单轨流程，避免强迫所有实验四点标注 | schema / 原子采用 / 模型安全边界 / Windows 实机 |
| Phase 8–9 输入 | CSV 交付、科学导出 / portable、external runtime / 安装 / packaging | 按依赖顺序立项；复用已验证边界与证据，不带旧包或无关 notices | 导出恢复 / cancellation / 原生平台 / 许可与发行门禁 |

### Analysis 只读候选的证据与范围

main `MainWindow.setWorkspace()` 只改变宿主与面板，没有关闭标注 / 标定。
`_onTrackSelectionChanged()` 与 `jumpToFrame()` 也没有 Analysis workspace 守卫；
`_onAnnotationClicked()` 仅检查 measurement、busy、annotation mode、presented / pending frame，
没有 workspace 检查。符合其他条件时，分析参考视频的点击仍可能写 manual 点。

本轮 offscreen 只读内存探针：建立 MainWindow，打开 annotation mode，切到 analysis，
断言 currentWorkspace=analysis 且 annotation mode 仍 true。当前维护分支与 main 的上述相关导航逻辑相同，
因此该保护尚未因五项 fix / 推荐扩展获得。论文已在进入分析时关闭编辑、并阻止选轨 / 跳帧重新启用。

这是有代码与模式状态证据的误操作风险；本轮**未模拟真实视频点击写点，也未改产品代码**。
实施时应验证数据快照在分析页各种点击后不变，Acquire 原标注能力恢复，review Correct 不被错误禁用。
不能整体 cherry-pick `42e853d`：该提交还包含 scalar / energy UI 与 source frame API。

## 9. 本轮验证、复现与后续入口

- 固定 refs、远程一致性、worktree / status、共同祖先、全部文件 / 提交 inventory、patch 等价检查完成。
- 对全部 80 个差异源码模块做 AST 入口 / 职责核对，沿共有 session、UI、worker、序列化与科学消费者检查功能依赖；附件留全量覆盖，不把 UI 相似当作数据契约相同。
- Analysis 保留 annotation mode 的内存探针通过；没有启动真实训练、修改用户工程、改论文 worktree 或执行产品合并。
- 在线核对公开 release 资产和固定源码；论文测试 / 科学 / HR 数字引用其对应固定 STATUS / ADR，本轮未重跑论文全量或 48 项数值实验。
- 文档本地 / 固定仓库路径与 inventory 计数核对、`git diff --check` 通过；仅文档变更，不为它重复跑产品全量测试。

最小复现命令（在仓库根目录）：

```bash
git diff --name-status 50a7924 154f262
git diff --stat 50a7924 154f262
git log --reverse --oneline 50a7924..154f262
git cherry 50a7924 154f262
git diff 50a7924 154f262 -- src/ai_physics_tracker/gui/main_window.py
gh release view v0.1.0 --json tagName,targetCommitish,publishedAt,assets,url
```

下一步：先按[维护 mini-plan 的 HR 步骤](../status/main-ui-backports-plan.md#human-review)
完成当前已实现增量的主线验收；需要继续回移时，优先单独处理 Analysis 只读，
再对 autosave 续接做主线场景复现。科学 / 多点 / 模型 / 打包扩展按主线阶段范围另行立项。

## 10. HR 通过后的回移建议（2026-10-11）

用户本轮询问下一批值得合入 main 的功能 / UI。建议以收益与契约依赖安排，不再重复实现上一批：

| 优先级 | 值得吸收的能力 | 用户收益与执行范围 |
| --- | --- | --- |
| 第一批维护 | Analysis 视频只读；autosave 后继续学习 | 防止分析页误写标签；先复现保存 busy 时回调丢弃，再修同 session 静默续接。分别保留 Acquire 编辑、失败 / 换工程不续跑边界 |
| 下一阶段主能力 | θ / ω、相图、周期分析与明确配置 | 直接补齐 main Phase 6 的核心使用场景；复用论文 Qt-free 核心与图表经验，按 main 通用轨迹 / 标定契约适配。α 仍需主线另实现 |
| 与分析能力一起设计 | 保存结果参数、输入身份、历史读取与 stale 提示 | 用户能知道图表由哪些标签 / 参数计算，修改后旧结果不会冒充最新。先建立 main 结果契约，不原样复制 publication schema v2 |
| 分析基础稳定后 | ODE 拟合与模型比较 UI | 对单摆价值高；保留显式高精度 / 历史限制、残差与比较资格。参考能量必须标清 proxy 单位；等价参数教学页可后做 |
| 模型功能立项时 | 教师模型导入 / 自检；建议帧连续批次修正 | 减少用户重复训练与逐帧操作；优先提炼通用单轨模式，多点实验再引入四 role join / 原子采用，不强迫所有实验四点标注 |
| 科学工作流与发行阶段 | 已存结果 CSV / JSON / PDF / PNG、portable copy、独立 AI runtime / Repair | 分别支撑导出复现与普通用户安装；依赖结果 / 模型 / host-worker 分离，按 Phase 8–9 集成，许可与平台门禁保留 |

`codex/**` 的 CI trigger 可随下一次配置维护补齐，收益明确但不是主要用户功能。
不建议整分支 merge、替换通用 ChartActions、偷换 SG 默认值或直接复制论文的 License / v2 格式。
本轮批准的是上一轮 HR；以上为后续推荐，没有新建这些功能或声称它们已获验收。
