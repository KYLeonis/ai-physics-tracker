# Phase 1 需求与验收标准（Project & Data Foundation）

- 日期：2026-08-28 · 状态：**Completed**（2026-08-29，AC-1…AC-10 全部通过）
- 来源：`docs/research/software-spec-plan.md` 行动项 A6；上游依据 `docs/roadmap.md` Phase 1
- 输入：`docs/spec/data-model.md`（A1/A2/A3/A5 结论）、`docs/spec/project-format.md` + [ADR-0003](../decisions/0003-project-persistence-format.md)（A4 结论）、DLC CollectedData 格式（project map §3.4 / raw note）
- 与 roadmap 的关系：本文档是 roadmap Phase 1 验收标准的**细化**，逐条可勾选判定；两者如有矛盾以本文档为准并回改 roadmap

---

## 1. 范围

Phase 1 建立**统一数据体系**：手工跟踪与 AI 跟踪共享同一套数据结构，并以编程方式（无 GUI）完成"创建项目 → 添加视频元数据与轨迹 → 持久化 → 恢复"闭环。

- 领域层无 Qt 依赖；全部逻辑可 pytest 覆盖（development.md §4/§5）。
- 包结构：src-layout，包名 `ai_physics_tracker`，`pyproject.toml` + `requirements.txt` 锁定（Python 3.11，ADR-0002）。
- 数据模型以 `data-model.md` 为准；持久化以 `project-format.md` / ADR-0003 为准。

## 2. 功能点清单（R1–R8）

### R1 项目生命周期
创建（目录 + `project.json` 骨架）、打开、保存、另存、关闭。保存走原子替换 + 滚动备份（project-format.md §5）；schema 版本守卫：高于支持版本明确拒绝，低于走迁移链（当前无历史版本，守卫逻辑先落地）。

### R2 视频登记
以编程方式构造 `Video` 元数据并加入项目（Phase 1 **不解码视频**，探测属 Phase 2）；项目内相对路径与外部绝对 locator 解析、缺失时 relink 流程（project-format.md §3）；重复登记检测（按实际 locator）。

### R3 Timeline 与时间换算
`fps_nominal` / `working_zone` 管理；`frame_to_time` / `time_to_frame` / 步进钳位；观测 `time_s` 冻结与加载一致性校验（data-model.md §5）。VFR 视频在登记接口层显式拒绝（`vfr_suspected` → 拒绝进入分析）。

### R4 轨迹与观测存取（TrackStore）
创建/命名/删除 Track；手工加点（last-wins）、引擎批量写入（first-wins，报告写入/跳过数）、手工修正遮蔽引擎点（superseded + superseded_by 链）、生效值解析纯函数、删除语义（data-model.md §4.4）。confidence/visibility/quality_flags 按 §4.5 语义写入。

### R5 标定与坐标变换
创建/校验/编辑 Calibration（退化输入拒绝）；按视频维护 active calibration；`CalibrationTransform` 纯函数（前向/逆向/往返不变量）；标定编辑 → 世界系 DerivedData 置 stale 的传播（data-model.md §6.3）。

### R6 持久化
save/load 往返相等（对象图逐字段一致）；UTF-8；目录整体移动（模拟：换根目录加载）后路径解析成功；备份文件滚动。

### R7 DLC 标注转换（设计文档交付，见 §4）
roadmap 验收项"手工标注数据结构可无损转换为 DeepLabCut 标注格式的**设计文档**"——本文档 §4 即该交付物；Phase 1 代码是否提前实现转换器由实现期决定（实现则必须过 §4.3 round-trip 测试）。

### R8 单元测试
见 §5；roadmap 验收项"核心数据模型有单元测试且通过"的判定标准。

## 3. Phase 1 验收标准（细化，逐条可判定）

| # | 验收标准 | 判定方式 | 状态 |
| --- | --- | --- | --- |
| AC-1 | 能以编程方式创建项目、添加视频元数据与轨迹数据并持久化/恢复 | pytest 集成测试：create → add video/track/points/calibration → save → 从新路径 load → 对象图逐字段相等 | [x] |
| AC-2 | 项目目录可移动 | 同一测试在临时目录 A 保存、目录改名为 B 后加载成功；项目内相对路径继续解析，外部 locator 不存在时返回 relink 状态 | [x] |
| AC-3 | schema 守卫 | 测试：构造 `schema_version = 999` 文件 → 加载被明确拒绝且给出提示语义 | [x] |
| AC-4 | 时间换算契约 | data-model.md §5 全部规则成测：0-based、`frame/fps`、就近取整确定性、29.97 fps、无增量累积（抽查大帧号误差 < 1µs）、working zone 不改时间基准（§5.4 场景：zone=[100,500] 时第 100 帧导出 time = 100/fps） | [x] |
| AC-5 | 覆盖与修正语义 | 测试：引擎批量写入遇已有帧跳过（first-wins）；手工修正后引擎点 superseded 且**原值保留可查**；manual 删除后引擎点恢复 active（data-model.md §4.2/4.4） | [x] |
| AC-6 | 标定变换正确性 | data-model.md §6.2 六条规格逐条成测（比例尺/Y 翻转/旋转/往返不变量/退化拒绝/单位换算） | [x] |
| AC-7 | 标定失效传播 | 测试：编辑标定后 raw 观测逐字段不变；世界系派生置 stale | [x] |
| AC-8 | 原子保存 | 测试：保存过程模拟中断（临时文件残留）→ 原文件完好；成功保存后备份文件为上一版内容 | [x] |
| AC-9 | DLC 无损转换设计文档 | 本文档 §4 存在且经评审（round-trip 保真范围明确、列映射完整） | [x] |
| AC-10 | 核心模型单元测试通过 | §5 测试矩阵全绿（本地 macOS + CI 双平台，CI 为实施期顺手任务） | [x] |

> roadmap 原始三条验收标准的对应：第 1 条 → AC-1/2；第 2 条 → AC-9（§4）；第 3 条 → AC-10。

## 4. DLC 标注格式无损转换设计（R7 交付物）

### 4.1 外部契约：DLC CollectedData

- 形态：Pandas DataFrame，列 MultiIndex `(scorer, bodyparts, coords)`，单动物项目 `coords ∈ {x, y}`；行对应一张标注帧（帧索引 + 提取帧图片路径）；HDF5（key `df_with_missing`）与 CSV 双写（DLC `trainingsetmanipulation.py`，raw note §Key Files）。
- 预测输出同构但 coords 含 `likelihood`（Phase 4 导入路径，本文只定标注导出/导入）。
- DLC 项目目录（config.yaml + `labeled-data/<video>/…`）由 Phase 4 的 DLCAdapter 生成；本转换器只负责**标注数据的双向映射**。

### 4.2 映射规则

| 内部（Annotation = manual TrackPoint） | DLC CollectedData | 说明 |
| --- | --- | --- |
| `Track.name`（每 Track 一个物理点） | `bodyparts` 维度（列组） | 轨迹名即关键点名；创建 Track 时校验 DLC 命名合法性（Phase 4 复核 DLC 字符集约束） |
| `frame_index`（0-based 源帧） | 行的帧索引 / 提取帧编号 | **0-based 对应关系在 Phase 4 实现时以 DLC 实测确认**（提取帧命名规则），并写入转换器测试 |
| `pixel_x`, `pixel_y` | `(scorer, bodypart, x/y)` 值 | 像素坐标系同为"原点左上、y 向下"（与 DLC/图像惯例一致），无需翻转 |
| 多视频项目 | DLC 单项目按 video 分 `labeled-data` 子目录 | 转换器按 video 分组导出 |
| 未标注帧 | 不出现在表中 | 双侧稀疏语义一致 |
| `confidence` / `visibility` / `source_detail` / status 链 | **无对应列** | 保真范围之外，见 §4.3 |
| `scorer` | 常量字符串（标注者标识） | 导出时由参数给定，往返保留在转换器上下文中 |

### 4.3 "无损"的判定：round-trip 保真范围

**保真范围（DLC 格式可表达的子集）**：`(video, frame_index, track, pixel_x, pixel_y)` 的集合，即标注帧集 × 关键点集 × 亚像素坐标。

**判定方式（验收定义）**：内部标注 → DLC 格式 → 解析回内部，须满足——

1. 帧集合、轨迹（bodypart）集合、逐点坐标**一一对应**；
2. 坐标数值经 **HDF5 路径**往返后 `exact` 或 `atol ≤ 1e-10`（float64 保真）；CSV 路径按文本往返容差 `atol ≤ 1e-6` 单独测（CSV 文本化的精度损失被显式承认）；
3. 保真范围之外的字段（confidence 等）**声明为不保真**：它们本来就不在 DLC 标注格式中，转换器不伪造、不丢弃内部数据——往返只重建保真子集，内部完整对象仍以 `project.json` 为准。

**明确不转换**：superseded 引擎点（只有 active manual 点是 Annotation）、派生数据、标定、UI 状态。

### 4.4 已识别的开放项（Phase 4 实现前确认）

- DLC 提取帧编号的 0/1 基准与文件名格式（实测确认后固化进测试 fixture）；
- `scorer` 命名与多动物（individuals）维度的出现条件（本项目 Phase 4 预计单动物项目，individuals 维度缺省）；
- DLC 对 NaN（未标注关键点）的容忍形态（`df_with_missing` 即为此设计，导出时保持稀疏）。

## 5. 测试要求（R8）

| 模块 | 必测内容 | 数据 |
| --- | --- | --- |
| Timeline | AC-4 全部 | 合成（含 29.97/60 fps） |
| TrackStore | AC-5 全部 + 生效值解析纯函数 | 合成观测序列 |
| CalibrationTransform | AC-6 全部 | 解析已知点；随机参数往返（固定种子） |
| ProjectRepository | AC-1/2/3/8 + UTF-8 中文路径/名称往返 | 临时目录 fixture |
| DLC 转换器（若实现） | §4.3 round-trip（HDF5/CSV 双路径） | 小型合成标注集 fixture |
| DerivedData | stale 传播规则（§6.3 表） | 合成 |

- 全部测试平台无关（无 Qt、无真实视频文件、无网络）；CI 双平台（mac + windows-latest）为实施期顺手任务（PLAN §4 Later 表已列）。
- 数值断言带显式容差；禁止 `==` 比较浮点。

## 6. 明确不做（Phase 1 边界）

GUI / 视频解码与探测 / 引擎适配器 / 任务系统 / 运动学计算与平滑 / 图表 / CSV-Excel 导出 UI / 模型库 / VFR 支持 / 多相机 / 标注集划分（见 data-model.md §7.6 推迟清单，各项均已确认"推迟不改变 Phase 1 数据结构"）。

## 7. 完成定义（Definition of Done）

- [x] AC-1…AC-10 全部勾选；
- [x] `src/` + `tests/` 按 R1–R8 落地，pytest 全绿；
- [x] `pyproject.toml`（src-layout，`requires-python = ">=3.11,<3.13"`）与 `requirements.txt` 就位；
- [x] 按 AGENTS.md §11 完成文档同步与 push。
