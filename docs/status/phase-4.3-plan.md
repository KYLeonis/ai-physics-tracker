# Subphase Plan — Phase 4.3 Inference Pipeline & Track Integration

- Issue：待用户确认计划后创建（本轮不操作远程内容）
- 分支：计划使用 `feat/p4.3-inference-pipeline`，尚未创建
- 日期 / 状态：2026-08-31 · 草案，等待用户确认，未开始实现
- 基线：`main` / `7ecb4ea`，与实时查询的远程 main 一致；进入会话时工作区干净。

## Goal

让 4.2 产出的训练模型能够在后台对当前视频执行全帧推理，将经过校验和置信度过滤的预测原子导入现有 Track，并让运动学计算使用人工与 AI 的生效观测。完成后可通过 Qt-free 接口和本地脚本验证闭环；GUI 接线留给 4.4。

## Scope

**做**：

- 单视频、单 Track、单 bodypart=`target`；使用该 Track 已完成训练的 snapshot，不增加模型库。
- 复用 `EngineAdapter` / `DLCAdapter` / `MockEngineAdapter`、spawn `BackgroundTaskRunner` 和 `TrackingRun`，补齐推理启动、帧进度、日志、取消、错误与结果导入。
- 加强已有 `import_results`，不再另写一套 DLC 数据转换器；原始 HDF5/CSV 与导入的第一方观测分开保留。
- 补齐 `ProjectSession` 的引擎批次提交与批量生效观测查询；复用 first-wins、manual last-wins 和修正链。
- 运动学计算及后台输入一致性检查读取同一组生效观测；导入后使相关派生数据失效。
- 合成数据自动测试、本机真实 DLC CPU 冒烟、独立 review 和交接文档。

**不做**：

- Task Panel、训练/推理按钮、进度 UI、AI 空心点等视觉样式、自动刷新/重算接线（4.4）。
- 多视频任务队列、多 bodypart、多模型比较、跨视频模型复用、困难帧检测、自动插值/平滑补点（Phase 5/7 等）。
- 更换依赖、修改 CI、修改项目 schema 或迁移数据；不重构整个训练框架或 ProjectSession。
- 自动删除旧 run、预测、模型或失败任务文件；不覆盖已有人工点和先前 AI run。

## Relevant Context

- `AGENTS.md`、`CODE_STANDARD.md`、`docs/workflow.md`、`docs/status/README.md`。
- `docs/roadmap.md` Phase 4；`docs/spec/phase4-requirements.md` R4、AC-3/4；ADR-0011。
- `docs/spec/data-model.md` §4/5/7；`docs/spec/project-format.md` §2/3；ADR-0007/0008/0009。
- `docs/research/open-source-project-map.md` §3.4/9；`docs/research/raw/deeplabcut-notes.md` 推理/进度部分。
- [4.2 Issue #13](https://github.com/KYLeonis/ai-physics-tracker/issues/13) 已关闭。
- [DLC 3.0.1 官方 compat.py](https://github.com/DeepLabCut/DeepLabCut/blob/v3.0.1/deeplabcut/compat.py)：以本机安装版本源码和真实调用复核具体参数，不能把 `analyze_videos` 返回值当作 DataFrame。

### 已确认的实现基础与缺口

- `TrackStore.add_engine_points()` 和 `resolve_effective_point()` 已实现首写优先和人工优先，融合语义不需要重新设计。
- `EngineAdapter` 已有 `import_results()`，但尚无推理执行契约；现有解析器会把缺失/非有限 likelihood 当作 1.0、把越界 confidence 截断，且 CSV 路径虽写在 docstring 中却没有读取分支。4.3 应修复这些信任边界问题，不能直接作为真实预测导入入口。
- `dlc_infer_worker()` 当前仅发送模拟进度，不执行模型推理、不产出预测。
- **训练交接前置缺口**：真实训练 worker 只查 `dlc-models`，而本机 DLC PyTorch 使用 `dlc-models-pytorch`；找不到快照时仍拼出一个未经存在性验证的路径并报 completed。`config_path` 也仅存于 TrainingCoordinator 内存，没有写入训练 run。341 项测试通过不代表这些真实模型交接条件已满足。Slice 1 需做定向修复和回归，不扩展为 4.2 全面重做；不自动更改历史 run。
- `ProjectSession` 已能记录并保存 `TrackingRun`，但缺少引擎点批次提交入口。
- `ProjectSession.compute_kinematics()`、`kinematics_job.analysis_inputs()` 当前只使用 `manual_points()`；只导入而不改两处读取路径会遗漏 AI 数据，也会漏判后台计算输入变化。
- GUI overlay 当前也只读取 manual 点；此处明确交给 4.4，不在 4.3 提前改视觉行为。

## Proposed Implementation Decisions

### 1. 参数、模型与原始文件

- 在既有协议文件补充最小的推理参数/结果值对象及 `infer` 方法，新增 `application/inference_job.py` 做编排；不增加通用任务管理框架。
- 启动时要求项目已保存、视频可访问且具有当前会话的时序授权、训练 run 已完成、Track/Video 对应、config 和 snapshot 存在。
- 明确指定并核实本次使用的 snapshot，继承训练 run 的 shuffle/trainingsetindex；不得无提示改用目录中的最新模型。记录实际设备、引擎版本、训练 run、模型与参数快照。
- 先修复训练到推理的必要交接：依据当前 shuffle/训练集定位真正产出的模型，找不到模型应失败，不能返回猜测路径；新训练 run 使用已有可扩展字段记录相对 config/model 引用。历史记录无法验证时明确阻止推理，提供重新训练或显式选择可验证配置的恢复方式，不自动修改旧 project.json。
- 当前只支持一个活动推理任务；共享 DLC 项目目录的训练与推理不能并发修改同一配置/模型，采用最小的活动任务检查，不引入排队系统。
- 每次输出放在 `data/engines/<run_id>/`，不写到用户原视频目录，也不复用旧 run 的输出目录。动手前先在项目格式说明中补充该子目录用途、命名和保留规则。
- 原始输出的相对路径、行数、文件哈希和导入统计放入 `TrackingRun` 已有可扩展字段；不增加 schema 版本。项目内路径按相对根目录的 POSIX 路径存储，执行时再解析。
- 兼容读取 4.2 已存在的模型/config 路径；发现旧绝对路径在项目移动后失效时明确报错，不隐式迁移或猜测替代模型。

### 2. 帧号、置信度与异常结果

- 全视频推理保持源视频 0-based 帧号；`working_zone` 仍只约束后续显示/计算，不重新编号。`time_s` 只经 `frame_to_time(frame_index, timeline)` 生成。
- DLC MultiIndex 的 scorer/bodypart/coords 必须可唯一确定；按显式帧索引解析，不能在过滤后用行序号重建帧号。
- 接受条件为 `confidence >= min_confidence`；校验阈值为有限数且在 `[0,1]`。保持已有 adapter 默认 `0.0` 的兼容性，推理编排调用端显式指定阈值，4.4 再确认面向用户的默认值。
- 映射为 `source="dlc"`、`confidence=likelihood`、`visibility="unknown"`、`source_detail=本次 run 的来源标识`；低 confidence 不推断为 occluded。
- 正常缺测 NaN 和低置信度点不生成 TrackPoint，报告各自数量；不填 `(0,0)`、不插值、不静默裁剪数值。原始文件保留全部预测，以便后续重新过滤。
- 缺列、歧义 scorer/bodypart、重复/非整数/负数/越界帧号、无穷值、越界 likelihood、文件损坏等拒绝整批导入。全帧结果必须核对总帧数和索引覆盖，不能把截断输出当成功；过滤后零点是可报告的正常结果。
- 近似 CFR 授权沿用已有规则，并将其时序依据保存在 run 参数/扩展字段，`source_detail` 仍用于关联 run。

### 3. 后台生命周期与提交边界

- worker 仅拥有推理请求快照，负责 DLC 调用、结果解析与校验；不修改活动 ProjectSession。DLC/HDF5/DataFrame 不进入领域模型。
- 复用结构化队列传递日志、真实 `processed_frames/total_frames` 与结果；只在推理输出完整且导入提交成功后记录 completed。
- 先复核真实 DLC 的模型选择与进度输出方式；适配逻辑限定在 DLCAdapter/子进程内。不能取得真实帧进度时记录阻塞并讨论方案，不用时间估算或 0→100 冒充实时进度，也不自行降低 R4 验收标准。
- 取消、异常退出、spawn 启动失败、结果校验失败、晚到/重复消息均落到可解释的终态，不导入半批数据。取消后必须 join 回收；输出文件保留但不得当作成功结果读取。
- 按 4.2 D1 提供 `cancel_all` 关闭/切换契约及 Qt-free 测试；真实窗口的关闭/切换接线在 4.4 一并完成。
- 回传时复核会话、project root、Track/Video、媒体和 Timeline/时序授权；切换/另存/重新关联后旧结果不得落入新上下文。推理期间新增人工点可以保留，并在提交时按当前 Store 首写优先跳过。
- 先在候选 Store/Project 完成跨对象校验，再一次提交观测、派生失效和 run 完成状态；坏结果不污染当前数据和 Undo/Redo。
- 观测导入作为一次可撤销的数据操作；run 的执行历史仍保留。全部过滤/冲突跳过时不新增观测撤销项，不误标派生失效。

### 4. 融合与运动学

- 保留 `manual_points()` 的含义，训练仍只读人工标注；新增批量 `effective_points()` 供分析使用，不把 AI 预测反过来当训练标签。
- first-wins 同时保护已有人工点和旧 AI 点。导入后人工修正按现有 superseded 链保留原预测；再次推理不自动替换旧 run。
- `compute_kinematics()` 与 `analysis_inputs()` 同步改读生效观测；派生输入的 `source_filter` 如实记录为混合来源，并保留可复现的来源选择说明。
- 目标 AI 数据变化后，旧派生标记 stale，旧后台计算结果不得覆盖新输入；不触发同步自动重算，沿用显式重算 API，4.4 接完成通知。
- 全视频批量写入避免每个点扫描全部历史观测：在现有 `add_engine_points` 内使用本批次局部 active 帧键集合，保持原校验及计数语义；批量生效查询同样避免逐帧全表扫描。不引入持久索引或新存储后端。

## Acceptance Criteria

- [ ] P43-1：mock API 与真实 DLC 冒烟均证明使用指定 snapshot 对当前视频全帧推理，结果文件只落在本次 run 目录。
- [ ] P43-2：合成 MultiIndex/HDF5/CSV 验证字段、源帧号、时间、阈值等于边界、缺测/零点、非法结构与截断输出；坏批次不会部分写入。
- [ ] P43-3：真实 spawn + mock adapter 验证真实帧计数消息、成功、取消回收、worker 异常、进程异常退出及重复/晚到消息；取消/失败没有新增观测。
- [ ] P43-4：首写优先保护人工及旧 AI，推理中人工编辑不丢；导入后人工覆盖保留原预测；跨会话/媒体/时间上下文的结果被拒绝。
- [ ] P43-5：成功导入按单次操作 Undo/Redo，影响目标派生 stale；全冲突/全过滤不改旧派生；save→load 保留 confidence、run 关联及相对输出引用。
- [ ] P43-6：混合 manual/AI 的已知解析轨迹重算正确，训练仍只导出 manual；AI 导入使进行中的旧运动学批次失效，纯手工回归不变。
- [ ] P43-7：本机真实 CPU 冒烟验证“已有/1 epoch 训练 snapshot → 推理 → 导入 → 保存重开”，明确这只证明管线可用，不代表单摆跟踪精度合格。
- [ ] P43-8：全回归及独立 review 通过；文档同步完成。Windows CUDA 延后不伪称已验证；推送后的双平台 CI 以实际结果记录。

## Slices

| Slice | 交付 | 主要文件 | 验证 |
| --- | --- | --- | --- |
| 1 | 复核真实 DLC snapshot/帧进度/输出契约；修复模型交接缺口；补目录约定与推理参数、协议、mock | `engine_adapter.py`、`dlc_adapter.py`、`training_job.py`、`mock_engine_adapter.py`、`docs/spec/project-format.md` | API 参数测试、快照真实存在/归属测试、短视频真实调用；提前暴露接口风险 |
| 2 | 真实推理与结果解析、严格校验、原始输出引用 | `dlc_adapter.py`、已有 adapter 测试 | 合成 MultiIndex/HDF5/CSV、阈值与失败边界 |
| 3 | 会话原子导入、融合查询、批量写入成本、运动学输入衔接 | `project_session.py`、`track_store.py`、`kinematics_job.py` | 导入/Undo/Redo/持久化、修正链、解析轨迹和过期批次测试 |
| 4 | 推理编排、spawn 生命周期、取消与晚到结果保护 | 新增 `application/inference_job.py`、必要的既有任务接口小改 | 真实 spawn + mock 的集成测试 |
| 5 | 本地真实闭环、独立 review、文档与 Subphase 收尾 | 推理冒烟脚本、`scripts/README.md`、status/spec/development/architecture | CPU 冒烟、全回归、AC 逐项核对 |

文件名均相对既有包/目录，按用途放置；不预创建未来空文件。实现按切片落地，出现不可兼容接口、依赖或范围变更先暂停确认。

## Verification

- 基线已运行：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **341 passed in 22.05s**。
- 基线 [CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33374271303) 为 success，对应 `7ecb4ea`；本轮未修改 CI。
- 实现时先跑相关 adapter/session/job/kinematics 测试，再跑上述全量回归；CI 用 mock，不安装额外依赖。
- 新增本地推理冒烟脚本，复用现有合成视频逻辑和训练产物；仅生成开发测试数据，不操作用户实验目录、不自动清理历史文件。
- 复核项目内相对引用在复制后仍能读取原始结果；旧 4.2 DLC 绝对路径的模型搬迁修复不作为已完成能力声称。
- 新公共接口和数值输入变化触发 `docs/workflow.md` §6 独立 review。
- 4.3 没有新增 GUI 控件/视觉交互，按 Qt-free AC 验收；如实际修改涉及用户可感知交互，则按 §5.1 发起 Human Review，不能用自动化替代。

## Approval and Next Action

此草案沿用已接受架构，不请求新增依赖或数据格式迁移。用户确认范围后：创建 4.3 Issue 与工作分支，先完成 Slice 1，再逐片实现和验证。源代码阶段可以按 commit 回退；原始预测文件和旧项目数据保留。`git push`、删除及其他红线动作仍单独遵守用户授权，不将计划确认解释成这些动作的授权。

## Result

- 本轮只完成进入检查、基线验证与计划草案；未开始 4.3 实现。
- AC 均未验收，独立实现 review 未开始。
- 下一步：用户确认本计划后，从 Slice 1 的真实 DLC 契约核对开始。
