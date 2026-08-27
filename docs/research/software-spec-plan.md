# 软件规范设计准备计划（Phase 1 前 · 收敛版 PLAN v2）

- 日期：2026-08-27（v2）· 完成于 2026-08-28 · 状态：**Closed**（全部行动项完成，Phase 1 可启动）
- 定位：**Phase 1 开发开始前的最后一轮准备性调研行动计划。** 本轮结束后停止大范围调研，正式进入 `Phase 1 — Project & Data Foundation`。
- 产出：`docs/spec/data-model.md`（A1/A2/A3/A5）、`docs/spec/project-format.md` + [ADR-0003](../decisions/0003-project-persistence-format.md)（A4）、`docs/spec/phase1-requirements.md`（A6）。
- 本版取代 v1 的大范围 spec 规划：v1 中面向后续 Phase 的内容未删除，统一移入 §4 Later Research / Open Items，待对应 Phase 启动前再取用。
- 阅读输入：`docs/roadmap.md`（Phase 1 交付物/验收标准）、`docs/architecture.md`（§2 数据体系）、`docs/research/open-source-project-map.md`（§3 各项目 Code Map、§6 Patterns）、`docs/development.md` §1.1（跨平台开发模式）。

---

## 1. 本轮要回答的问题

1. 核心领域对象有哪些，`Video / Timeline / Observation / Track / Annotation / Calibration / DerivedData / Project` 如何定义与关联；
2. frame / timestamp / FPS / VFR 等时间语义如何设计；
3. pixel 与 physical/world 坐标如何分层；
4. raw tracking data、manual corrections、processed data 如何区分；
5. confidence / visibility / source / quality flags 等元数据如何表达；
6. 项目数据如何组织与持久化（含项目目录可移动）；
7. Phase 1 需要预留哪些接口，哪些以后再设计；
8. macOS 开发 + Windows 发布对 Phase 1 数据与路径设计的直接影响；
9. Phase 1 的验收标准是什么。

**本轮明确不做**：tracking engine 横向 benchmark、模型对比实验、Windows packaging spike、release plan、C4/UML 全集、产品级 TaskManager 设计、DLC API 细节、高级物理量体系、3D/多相机、商业许可证审计（全部见 §4）。

---

## 2. 行动项（共 6 项）

优先级：**P0 = Phase 1 前必须完成** / **P1 = Phase 1 开始时可并行完成**。

### A1. 领域模型与数据分层语义 — P0（阻塞 Phase 1）

- **目标**：确定 8 个核心领域对象的概念、边界与关系；明确 raw observation / manual annotation / tracking result / derived data 四层数据语义；定义 source、confidence、visibility、quality flags 元数据。
- **输入**：project map §6（六条跨项目结论，尤其"观测即上下文"与"raw/derived 分离"）；raw notes 中五套模型范本——OpenPhysics TrackLab（`Track.ts`/`TrackingModel.ts` 的 first-wins/last-wins）、Kinovea（`TimedPoint` + `TrackingSource` + ephemeral template）、Tracker（`PositionStep`/`dataVariables`）、SLEAP（`Labels/LabeledFrame/Instance/PredictedInstance` 的用户/预测分离）、DLC（scorer/bodyparts/likelihood MultiIndex）。
- **交付物**：`docs/spec/data-model.md` §1–§3——术语表（中英对照）、对象关系图（概念级，非 UML 全集）、逐对象字段级建议（字段/类型/单位/缺测语义）、四层数据的读写与覆盖规则。
- **验收标准**：以下问题有明确书面结论——① AI 预测被人工修正后是否覆盖原值、原预测是否保留（预期：不覆盖，分层保留，参照 first-wins/last-wins + Kinovea 修正语义）；② source 枚举能否容纳 manual / template / dlc / tapir / cotracker / sam2；③ confidence 与 visibility 是同一字段还是两个字段；④ 修改 Calibration 后哪些数据失效需重算（预期：仅派生层）。
- **关键约束**：只到字段级建议，**不写 Python class**（实现属 Phase 1）。

### A2. Timeline 与时间语义 — P0（阻塞 Phase 1，本轮最高优先级之一）

- **目标**：定义 `frame_index / presentation timestamp / nominal fps / duration / time_seconds` 的关系与换算规则，杜绝 `time = row_index / fps` 类隐式假设扩散。
- **输入**：project map §6.2（三种时间语义教训）；raw notes——Kinovea（`VideoReader.MoveBy` 经 `AverageTimeStampsPerFrame`、`Timeline<T>` 时间戳键）、TrackLab（time 权威 + `round(time×fps)` 及 29.97 测试）、Tracker（frame vs step 分离）、SLEAP（frame_idx 状态）；OpenCV `CAP_PROP_*` 时间戳行为（Phase 1 实现时实测）。
- **交付物**：`docs/spec/data-model.md` 时间语义章节——CFR 假设与 VFR 处理策略、帧计数从 0/从 1 的约定、frame↔time 双向换算的精度规则、seek/step 语义、视频裁剪（working zone/起止帧）后的时间表示、导出 CSV 的时间字段定义。
- **验收标准**：给定一段视频元数据，能无歧义回答"第 N 帧的 time_seconds 是多少""用户从第 100 帧裁剪到第 500 帧，导出的 time 从 0 还是原视频时间起算"；VFR 至少有明确策略（即使结论是"Phase 1 只支持 CFR、VFR 显式拒绝并提示"）。

### A3. 坐标与标定模型 — P0（阻塞 Phase 1）

- **目标**：划定 image/pixel、world/physical、screen 三种坐标的边界；定义 scale、origin、axis direction、rotation、Y-flip 与标定 provenance；保证 raw observation 永远保留原始像素，物理坐标是可重算的派生结果。
- **输入**：project map §6.4；raw notes——TrackLab `ModelViewTransformFactory`（`T·R·S(s,-s)` 纯函数、retransform 不变量）、Kinovea `CalibrationHelper`/`CalibratorPlane`（变换栈与 `CalibrationChanged` 事件）、Tracker `CoordAxes`/`ImageCoordSystem`。
- **交付物**：`docs/spec/data-model.md` 标定章节——坐标分层规则、标定对象的字段级定义（比例尺两端点/单位、原点像素坐标、角度、时间有效性）、标定变更的失效传播规则（哪些派生数据标记 stale）、变换的测试要求（解析点）。
- **验收标准**：能回答"标定被修改后，已有 raw observations 是否变化"（预期：不变，仅派生层重算）与"一个观测如何从像素坐标得到物理坐标"的完整链路；Y 轴方向约定（物理 Y 向上）明确写入。

### A4. 持久化与项目格式（含跨平台路径规则）— P0（阻塞 Phase 1）

- **目标**：对比 JSON / SQLite / Parquet-CSV / 混合方案，结合 project metadata、annotations、raw tracks、derived tracks、calibration、（未来的）models 的形态，给出 Phase 1 推荐方案与可移动项目目录结构；固化跨平台数据/路径规则。
- **输入**：raw notes 中三个先例——Kinovea `.kva` XML sidecar（视频不入库、先读尺寸/时序再读坐标）、DLC（config.yaml + labeled-data + H5/CSV 分层目录）、SLEAP（.slp 单文件 + 分析导出分离）、Pose2Sim（分阶段目录）；`docs/development.md` §1.1（跨平台规则总则）；补充少量业界调研：schema versioning/migration 常见模式（够 ADR 引用即可，不展开）。
- **交付物**：`docs/spec/project-format.md`（推荐方案、目录结构、schema 版本与迁移策略、大文件边界——视频/模型只引用不复制、项目可移动性规则）+ **ADR-0003 持久化格式决策**。
- **验收标准**：目标目录结构形如 `MyExperiment/ + project.* + data/…`，满足：整个目录复制/移动到另一台机器（mac↔Windows）后项目可打开；路径以相对引用为主、绝对路径仅作缓存提示；逐帧大量数据（万级 observation）在所选格式下的读写方式有明确结论；schema 带 version 字段且有升级策略。
- **关键约束**：不把大型视频塞进项目数据库；不做完整性能实验，够支撑 ADR 决策即可。

### A5. Phase 1 最小接口边界 — P1（不阻塞，Phase 1 开始时可并行定稿）

- **目标**：只定义 Phase 1 真正需要的边界——`ProjectRepository`（保存/加载）、`Timeline`、`Calibration transform`（纯函数）、`Track storage`；确保数据模型未来能容纳不同 tracking source 的结果，但**不**提前设计 DLC/SAM2/TAPIR 引擎接口与 TaskManager。
- **输入**：A1–A4 结论；project map §6.5/§6.8（任务抽象与适配器契约仅作"不要堵死"的检查表，不作 Phase 1 交付物）。
- **交付物**：`docs/spec/data-model.md` 最小接口章节（概念级契约：职责、输入输出、错误语义；不含完整签名）。
- **验收标准**：能列出 Phase 1 的模块清单及"刻意推迟"清单（引擎适配器、任务系统、导出服务 → Phase 2/4），且推迟项不改变 Phase 1 数据结构。

### A6. Phase 1 需求与验收标准 — P0（阻塞 Phase 1）

- **目标**：把 roadmap Phase 1 的交付物/验收标准细化为可执行、可测试的 Phase 1 需求（编程方式创建项目→添加视频元数据/轨迹→持久化→恢复；标注结构↔DLC 格式的无损转换设计文档；核心模型单元测试）。
- **输入**：`docs/roadmap.md` Phase 1；A1–A4 结论；DLC `CollectedData` 格式（project map §3.4 / raw note）。
- **交付物**：`docs/spec/phase1-requirements.md`——范围、功能点清单、验收标准细化（含"无损转换"的判定方式：往返转换 round-trip 测试）、明确不做清单。
- **验收标准**：Phase 1 完成与否可逐条勾选判定；与 roadmap 验收标准一致且更细，无矛盾。

---

## 3. 已有充分结论、本轮不再调研的部分

| 主题 | 结论位置 |
| --- | --- |
| 开源生态全景与代码参考 | project map 全文（Phase 1 实现时按 §10 阅读顺序查阅即可） |
| 领域模型的设计模式依据 | project map §6（六条跨项目结论直接作为 A1–A3 的输入） |
| 跨平台开发模式总则（构建策略/真机验收/CUDA 验证） | development.md §1.1（已有 CUDA Windows 笔记本，真机途径已落实） |
| 技术栈与版本（Python 3.11 / PySide6 优先评估 / PyQtGraph 等） | ADR-0002 + development.md §2 + roadmap 版本记录 |
| 测试基本原则（pytest + 解析合成数据 + GUI 剥离） | roadmap §7 + development.md §5（完整 test-strategy 文档后移） |
| 许可证一级结论（CoTracker NC 阻断、GPL 只参考、DLC/SAM2 可行） | project map §8（商业级审计后移到发布前） |

---

## 4. Later Research / Open Items（不阻塞 Phase 1）

| 事项 | 建议启动时点 | 参考材料 |
| --- | --- | --- |
| Tracking engine benchmark（OpenCV / TAPIR / TAPNext / CoTracker / DLC / SAM2 对比实验） | Phase 3 末–Phase 4 前（benchmark-spec 先于实验定稿） | project map §5 / §11 |
| DLC 程序化 API 稳定性与集成细节、版本锁定 | Phase 4 前 | project map §3.4 |
| EngineAdapter / TaskManager 产品级设计 | Phase 4 前（Phase 1 只保证数据可容纳） | project map §6.5/§6.8 |
| Windows packaging 早期 spike（PyInstaller 体积/启动实测） | Phase 2 末（低成本一次，非阻塞）；正式打包 Phase 9 | development.md §1.1、v1 计划 S11 |
| CI 骨架（mac+Windows 双平台测试） | Phase 1 实施期顺手任务（建立 pyproject/测试后即加，属实施非调研） | development.md §1.1 |
| Windows exe 构建流水线与 artifact 下载闭环 | Phase 2 | development.md §1.1 |
| MVP UX 线框与交互规范 | Phase 2 前 | project map §4/§10 |
| 数值精度政策 + 平滑/微分 ADR | Phase 3 前 | project map §6.6、DLC2Kinematics 陷阱 |
| PyQtGraph 性能验证（长序列实时联动） | Phase 3 前 | — |
| 视频解码后端对比（OpenCV/PyAV/decord，含 H.265） | Phase 2 中 | development.md §1.1 |
| NFR 全量指标 / personas / 完整 requirements | Phase 2–3 前（Phase 1 只需 A6 的最小版） | v1 计划 S3 |
| 并发模型 ADR、C4 架构图更新 | Phase 2 前（轻量）/ Phase 4 前（完整） | v1 计划 S7/S8 |
| release plan、版本策略、依赖许可清单机制 | Phase 8–9 | project map §8 |
| 风险登记册（统一格式） | 任一 Phase 收尾时建立即可 | v1 计划 S4 |
| 商业级许可证审计、SBOM | 发布前 | project map §8 |

> v1 计划的完整工作项清单（S1–S16）已被本表吸收：S1→A1/A2/A3，S2→A4，S3→A6（收缩）+ Later，S4/S5(部分)/S7/S8/S9/S11–S15→Later，S5(编码规范)→Phase 1 实施期顺手，S6→A5（收缩），S10/S16→Phase 1/2 实施期任务。

---

## 5. Phase 1 Readiness Criteria

以下核心问题得到书面结论（落在新 spec 文档中）后，**即可开始 Phase 1**，无需等待其他任何事项：

- [x] Domain vocabulary 基本确定（data-model.md 术语表）
- [x] Timeline/time semantics 明确（CFR 约定、VFR 策略、frame↔time 换算规则）
- [x] Raw vs derived 数据边界明确（覆盖策略、失效传播）
- [x] Calibration 数据模型明确（字段级 + 派生重算规则）
- [x] Project persistence 方案确定（ADR-0003 Accepted）
- [x] Cross-platform path strategy 明确（相对路径、可移动项目目录、UTF-8）
- [x] Phase 1 最小验收标准明确（phase1-requirements.md）

**明确不要求**（它们不阻塞 Phase 1）：Tracking engine 已选定、DLC 已集成、Windows exe 已打包、AI benchmark 已完成。

---

## 6. 执行顺序与收尾

- 建议顺序：A1 → A2 → A3（三者同源，可一次调研会话完成）→ A4（含 ADR-0003）→ A6 定稿；A5 与 Phase 1 实现并行。
- 预计产物：`docs/spec/data-model.md`、`docs/spec/project-format.md`、`docs/spec/phase1-requirements.md` 三份文档 + ADR-0003。不为形式增设其他 spec 文件。
- 收尾：勾选 §5 全部条目 → 更新 research/README 与 AGENTS.md 的文档索引 → 提交并推送 → **停止调研，进入 Phase 1**。
- 本 PLAN 完成使命后转为归档（状态改 Closed），后续缺口按 v1 方式在对应 Phase 前新增小型计划。
