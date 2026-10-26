# 项目推进健康度与计划评估（2026-10-26）

- 基线：`main @ 8940352`，进入会话时工作区干净。
- 性质：产品只读评估与建议；未冻结新范围，未修改 roadmap / AC / ADR，未启动6.5或维护实现。
- 比较对象：初始提交`cd3ce1b`的README / roadmap、当前需求 / 计划 / Review与主干代码。
- 假定使用规模：单人本地桌面实验；数百至3.6万条观测为主要检查范围，10万条作为扩展压力点。Windows真机测试不作为本报告重点。
- 同日事实补查：原评估遗漏了当前图表PNG快照、ADR-0011的MIT方向及v0.1.0历史Mac测试发行，下文已据实修正；通用main与历史发行分别记账。

## 结论

总体健康，工程成熟度领先于外部有效性与交付证据。现有四层架构、统一观测体系、显式采用AI结果、科学来源与迟到拒收机制值得继续沿用。近期更需要完成整体验证、让别人拿到结果并试用；连续纯架构整理的优先级应下降。

初始预期应分项判断，不能按Phase编号计算完成百分比：

| 初始目标 | 当前判断 | 证据与限度 |
| --- | --- | --- |
| 手工与AI共用数据、标定、保存和重开 | 已形成可靠基础 | domain / application / infrastructure分离，原子保存、Undo引用完整性及分层测试 |
| 少量标注→训练→推理→修正→再训练 | 功能闭环已完成，收益证据有限 | Phase 4真实CPU冒烟、Phase 5真实闭环；AC-9改善目标仍明示未达成 |
| 可用于物理实验的分析 | 大部分能力已交付，整体收口待6.5 | 角量、相图、用户公式、重复间隔及条件性参数区间；P011局部真实对照已通过 |
| 普通用户容易完成任务 | 本人HR已有证据，独立新用户证据不足 | 6.3.1已修复常数公式 / 初值 / 结果解释等问题；未找到非项目参与者独立完成任务的验收记录 |
| 无需配置Python、结果可导出分享的桌面产品 | 当前main尚未闭合；已有历史Mac测试发行 | main已有当前图表PNG快照，科学数据文件 / 完整报告和Phase 7–9仍未交付；[历史v0.1.0](https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0)已有Mac安装器与独立AI环境，不能当作当前main的完成证据 |

通用表达式、只读历史和科学有效性保护比早期固定单摆示例更完整。这是合理演进；原计划没有明确交付日期或工时预算，本报告不据日历跨度判定延期。

## 值得优先处理的问题

### 1. AI闭环的产品价值仍需独立证据

[初始roadmap](https://github.com/KYLeonis/ai-physics-tracker/blob/cd3ce1b/docs/roadmap.md)明确要求修正后精度量化提升。[Phase 5.6 Review](../reviews/phase-5.6-review.md)与[报告](../benchmarks/phase-5-loop-report.md)显示：148帧视频、11帧反复使用的验证参考上，基准3.30px，最佳3.19px（改善3.3%），未达到5%目标；该参考也参与过迭代决策。

这是一项已知证据缺口。历史screening凑数问题已修复，不将旧缺陷误报为现存bug。以后要宣称AI更省事或更准确时，用第二视频或从未参与决策的保留数据，并事先固定标注 / 审核预算，记录最终误差、人工操作量和关键物理量偏差。新数据的门槛应事先讨论，不能沿用旧结果倒推；不重开已批准归档的AC-9。

### 2. 参数区间尚不能代表整项实验的可靠程度

P6.4按[ADR-0028](../decisions/0028-fit-parameter-conditional-standard-errors.md) / [0029](../decisions/0029-local-t-parameter-confidence-intervals.md)明确限定了条件性SE与局部t区间，处理是审慎的。[SciPy官方说明](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)同样指出局部协方差依赖最优点附近的线性近似。

后续需要补的是实际测量链的证据：比例尺、支点、时序、拍摄几何和处理参数对目标物理量有多大影响。[P011](phase-6.3-reference-preparation.md)的周期对照差0.21996%证明该冻结片段的分析结果与同视频人工参考相符，不证明独立校时、全流程跟踪精度或所有视频的物理准确性。

建议在6.5规划中讨论一页伴随敏感性观察：在原冻结基准之外，用副本改变合理范围内的标定 / 支点 / 处理设置并记录结果。先识别主要误差来源，再决定是否需要完整传播、镜头校正或其他统计方法；不改变既有AC和冻结参考。

### 3. 最小导出与独立试用排得偏晚

当前[Phase 7 / 8](../roadmap.md)把完整模型库放在科学导出之前。用户已有教师模型导入、真实帧自检、候选推理和run溯源，完整模型库的部分基础已经存在。

main已通过[ADR-0010](../decisions/0010-current-chart-png-snapshots.md)提供`Save PNG…`，它是当前可见图表快照，不含面板外参数或时序说明。建议6.5之后补选定结果的CSV与方法 / 来源信息，并核对已有PNG是否满足目标任务，再让少量目标用户独立完成一次任务，记录卡在哪一步、理解错了什么。沿用用户已确认的“不设新手完成时限”。完整Excel、视频导出、模型复制 / 评价界面按真实需求继续排。

### 4. 普通用户的安装与AI运行环境需要提前做小范围可行性验证

`pyproject.toml`把DLC列为正式依赖，但CI用`requirements.txt`与`--no-deps`安装轻环境，真实DLC训练测试使用fake模块；这对快速回归合理，却不证明新机器能安装并运行当前main的AI。main现有spawn提供进程隔离，独立AI环境的安装 / Repair尚未回移；历史v0.1.0发行已经提供该实现和用户验收先例。

[DLC官方安装说明](https://deeplabcut.github.io/DeepLabCut/docs/installation.html)仍要求选择环境、PyTorch与设备组合。建议在完整Phase 7投入前先对照历史发行与main的差异，按[回移档案](../status/main-backport-backlog.md)选择必要复用，再验证当前main的环境安装、启动、解码、CPU推理与恢复路径，避免从零重做。完整安装器仍留在Phase 9，这项建议独立于已知的Windows真机测试。

### 5. 有一处已测到的GUI只读热点

[`ProjectSession.is_dirty`](../../src/ai_physics_tracker/application/project_session.py)每次创建两个`replace(Project, ...)`，二者都会触发[`validate_project`](../../src/ai_physics_tracker/domain/project.py)遍历观测。它被[`ProjectActions.refresh`](../../src/ai_physics_tracker/gui/project_actions.py)用于更新窗口标题，也被保存保护调用。

本机Python3.12.13 / Darwin arm64、现有`.venv`，单轨迹合成有效观测、无派生结果；操作5次取中位数，实际save / load各3次，使用自动清理的临时目录：

| 观测数 | is_dirty | detached | 单帧观测查询 | 保存 | 重开 | manifest |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 600 | 0.91ms | 0.11ms | 0.06ms | 7.67ms | 7.36ms | 0.31MiB |
| 36,000 | 54.57ms | 6.70ms | 3.19ms | 452.00ms | 547.68ms | 18.51MiB |
| 100,000 | 174.89ms | 19.63ms | 9.20ms | 1,285.35ms | 1,588.34ms | 51.46MiB |

这是方法级合成探针，不是GUI整机性能验收，也不含真实视频解码 / AI / 多轨迹 / 派生数据。最小修复方向是让未保存判断成为廉价的数据变更判断，保留Undo回到保存点、显式保存和autosave的现有语义；继续在输入 / 写入边界校验。建议6.5后、扩大真实视频规模前处理，若6.5遇到卡顿则提前。

当前3.6万条观测的实际保存与重开尚在亚秒级。JSON可以继续沿用；增加真实派生结果与多轮操作的样例后，再按测量决定索引、存储拆分或迁移，不能据文件大小直接重写持久化。

### 6. 文档同步与公开分发目标已有事实漂移

- 初查通过GitHub连接器`get_repo`确认仓库public，LICENSE当时仍写TBD / 应保持private。本轮事实校正已移除private表述并区分历史发行；正式许可仍待用户确认。本报告不判断法律合规、不选择许可证、不改变仓库可见性。
- 补查发现[ADR-0011](../decisions/0011-deeplabcut-integration-architecture.md)已有MIT方向，v0.1.0发布说明也写主程序MIT；本报告原先只看TBD文件而遗漏这两项。下一版需确认如何衔接既有决策。DeepLabCut实际3.0.1及官方资料为LGPL，不能继续沿用AGPL描述；软件库与ImageNet预训练等模型权重须分别核对，不能据库许可推出模型可商业使用。
- 初查development环境表仍写NumPy2.4.6 / OpenCV4.14，与末尾P6.3说明和当前锁文件 / 实际环境不一致；本轮已校正为NumPy1.26.4 / OpenCV-headless4.11.0.86，并补齐源码环境安装步骤。

建议当前事实集中维护在状态入口 / 锁文件 / 对应ADR，其他入口简要链接；历史Review保留当时状态并标明证据日期。减少多处粘贴最新提交与测试数，避免新增另一套维护流程。

## 框架与实现调整的时机

四层分工、domain纯计算、prepare→run→validated→apply、原子事务与两类分析执行器继续保持。R01–R04 / R08 / R09已经解决实际重复与所有权问题；R07继续搁置，通用JobSupervisor / 计算框架 / 图表统一不应仅因代码增长立项。

主窗口2054行、ProjectSession1841行、TrackingActions1617行，说明职责集中，但行数本身不构成重写理由。可随下一次真实功能改动收敛两处边界：

- 触及分析表单 / 历史时，让面板拥有草稿采集与还原，逐步减少`SignalHistory.capture/_load`对参数表列数与widget布局的直接了解，顺带清理已记录的六个遗留私有访问；只增加透传getter没有收益。
- 进入模型库 / 新视频复用时，复用已有ImportedModel、TrackingRun与工作流事实，把新增选择策略放在application，GUI负责操作与呈现；先实现保存 / 追溯 / 复用的核心路径，再按真实需求扩展完整管理功能。

建议顺序如下，均为待确认建议：

| 时机 | 工作重点 | 退出依据 |
| --- | --- | --- |
| 现在 | 确认首个可交付版本的目标任务，校正文档事实，明确许可 / 分发目标 | 有清晰任务和一致的事实入口 |
| 下一轮6.5 | 以现有冻结参考完成主线单摆全流程、保存重开和最终HR；讨论切换Stabilization Mode | 原AC逐条有证据，失败项如实记录；不夹带新工具或完整AI改善研究 |
| 6.5后、完整Phase 7前 | 最小导出、独立目标用户试用、有限运行环境探针；处理已测热点 | 用户能拿到结果，知道卡点，交付路径可验证 |
| 随后Phase 7 / 8 | 根据跨视频复用与实验报告需求实现模型管理、完整导出 / 归档 | 以真实任务收益决定范围 |
| Phase 9 | 基于前期数据做正式性能优化、安装器和发布 | 沿用正式发布验收与已知平台边界 |

## 本轮验证与边界

定向回归命令：

```bash
.venv/bin/python -m pytest -q tests/test_layer_boundaries.py tests/test_track_store.py tests/test_project_repository.py tests/test_refinement_history.py tests/test_function_fit.py tests/test_fit_uncertainty.py tests/test_parameter_intervals.py
```

结果：**103 passed in 3.42s**。最初命令含不存在的测试文件名，未执行测试；按仓库实际文件名修正后运行上述命令通过。

检查了初始目标、当前状态 / 架构 / 计划、Phase 5闭环及P011证据、数据查询 / 保存 / 校验、GUI刷新与历史、任务 / 导入模型和CI依赖边界；不是逐行完整审计。未重跑1414项全量、真实DLC训练 / 推理、GUI真人试用、独立新视频实验、安装器或Windows真机。当前全量与双平台证据沿用[current](../status/current.md)记录，不冒充本轮新结果。临时计时目录已清理，未修改用户实验。
