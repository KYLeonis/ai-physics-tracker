# 数据模型规范（Data Model Spec）— Phase 1 地基

- 日期：2026-08-28 · 状态：**Accepted**（作为 Phase 1 实现依据）
- 来源：`docs/research/software-spec-plan.md` 行动项 A1（领域模型与数据分层）、A2（时间语义）、A3（坐标与标定）、A5（最小接口边界）的书面结论
- 输入：`docs/architecture.md` §2、`docs/research/open-source-project-map.md` §3/§6/§7、raw notes（openphysics-tracklab / kinovea / tracker / sleap / deeplabcut）、`docs/development.md` §1.1
- 性质：本文档到**字段级建议**为止，不写 Python class（实现属 Phase 1）；持久化格式决策见 `project-format.md` 与 ADR-0003；Phase 1 需求细化见 `phase1-requirements.md`

---

## 0. 设计原则（来自调研的六条硬约束）

1. **观测即上下文（observation with provenance）**：持久化的观测单元不是裸坐标，必须携带 frame/time、source、confidence/visibility（project map §6.1，Tracker/Kinovea/SLEAP/DLC/TAPIR/TrackLab 六家共同形态）。
2. **原始观测只存像素、不可变**：标定坐标、平滑、微分、拟合全部是带 provenance 的派生层；raw 层只增不改（project map §6.6）。
3. **显式 Timeline 契约**：任何代码禁止从数组行号/DataFrame 行号推断时间（project map §6.2、§7.11）。
4. **手工与自动的不同覆写策略**：自动 first-wins、手工 last-wins、修正分层保留不销毁原值（project map §6.3）。
5. **标定是纯函数服务**：变换可逆、可解析测试；标定变更不触碰 raw 层（project map §6.4）。
6. **领域层无 Qt 依赖**：本规范中所有对象都是纯数据 + 纯函数（project map §7.9，Tracker/Kinovea GUI-数据耦合的反面教训）。

---

## 1. 术语表（中英对照）

| 中文 | 英文 | 定义 |
| --- | --- | --- |
| 项目 | Project | 一次实验分析会话的持久化容器：视频引用、轨迹、标定、派生数据的根 |
| 视频（元数据） | Video | 一个被分析的视频资源的**元数据 + 文件引用**；永不包含帧像素数据 |
| 时间轴 | Timeline | 一个视频的帧率约定、帧计数规则与工作区（working zone）；帧↔时间换算的唯一权威 |
| 轨迹 | Track | 一个被跟踪目标（一个物理点）在一段视频上的身份 + 其全部观测的集合 |
| 轨迹点 / 观测 | TrackPoint / Observation | 单帧单目标的带上下文观测：像素坐标 + 时间 + source + confidence + visibility + flags。**本系统的原子数据单元** |
| 人工标注 | Annotation | **TrackPoint 的一种语义角色**（source=manual），不是独立存储对象；同时是 AI 训练数据来源（§3.6） |
| 标定 | Calibration | 像素坐标 ↔ 物理坐标的变换参数：比例尺、原点、旋转；按视频生效 |
| 派生数据 | DerivedData | 由 raw 层经纯函数计算（坐标变换/平滑/微分/拟合）产生的带 provenance 数据层，可随时删除重算 |
| 工作区 | Working Zone | 用户在时间轴上设定的分析起止帧 [in_frame, out_frame]；只做过滤，不重置时间基准 |
| 生效值 | Effective value | 同一 (track, frame) 上多条观测中按 §4.3 规则胜出、参与计算与显示的那一条 |
| 引擎运行 | Tracking run | 一次引擎（模板匹配/DLC/…）批量产出观测的过程；Phase 1 仅以 `source_detail` 字符串记录其 id（§8） |
| 缺测 | Missing | 某帧无观测记录（不造值、不写 NaN 行）；与"观测存在但 visibility=occluded"严格区分 |
| 原点 | Origin | 世界坐标系原点在像素坐标中的位置（`origin_px`） |

---

## 2. 对象关系总览（概念级）

```text
Project
 ├── 1 ── * Video ──── 1 ── 1 Timeline        （Timeline 每视频一份，持久化于 Project）
 ├── 1 ── * Track ──── * ── 1 Video
 ├── 1 ── * Calibration ── * ── 1 Video       （按 video 映射当前生效者）
 ├── 1 ── * TrackPoint ── * ── 1 Track        （观测是独立集合，按 track 归组）
 ├── 1 ── * DerivedData ── * ── 1 Track       （并引用 Calibration 与输入层）
 └── Annotation ≙ TrackPoint 中 source=manual 的语义角色（无独立表）
```

要点：

- **TrackPoint 是唯一的事实载体**。Track 只携带身份元数据；坐标数据全部在观测集合里（对照 SLEAP `Labels/LabeledFrame/Instance` 与 Kinovea `Timeline<T>` 的稀疏集合经验）。
- **一切坐标观测以像素形态存在于 raw 层**；物理坐标永远是按需计算或派生层缓存。
- 一个 Project 可登记多个 Video（为 Phase 10 多相机留位），Phase 1 的工作流按"单视频分析"操作，不提供多视频联动。

---

## 3. 逐对象字段级定义

通用约定：

- `id` 类字段为 UUID（小写、连字符格式），由创建方生成；
- 时间戳字段为 ISO 8601 UTC 字符串（含时区偏移）；
- 所有列表/对象字段在读取时必须容忍"未知键"（tolerant read，见 project-format.md §4）；
- 枚举一律为小写字符串，注册表（registry）持久化在项目文件中，新增枚举值属数据级扩展、不触发 schema 迁移。

### 3.1 Project

| 字段 | 类型 | 约束/缺省 | 说明 |
| --- | --- | --- | --- |
| `project_id` | uuid | 必填 | 项目身份 |
| `name` | str | 必填 | 显示名；项目**目录名**可与之不同（目录名需过滤 Windows 非法字符） |
| `description` | str \| null | null | |
| `created_at` / `modified_at` | datetime | 必填 | modified_at 每次保存更新 |
| `videos` | list[Video] | 可空 | 登记顺序即列表顺序 |
| `timelines` | list[Timeline] | 可空 | 每个 Video 恰好一份，以 `video_id` 关联 |
| `tracks` | list[Track] | 可空 | |
| `observations` | list[TrackPoint] | 可空 | 全部观测的扁平集合（按 track 归组展示；存储形态见 project-format.md） |
| `calibrations` | list[Calibration] | 可空 | |
| `active_calibration_by_video` | map[uuid, uuid] | 可空 | `video_id → calibration_id`；缺少某 video_id = 该视频未标定 |
| `derived` | list[DerivedData] | 可空 | |
| `registries` | object | 必填 | `sources`、`units`、`quality_flags` 的注册表（§4.5） |
| `ui_state` | object | 可空 | GUI 布局等非逻辑状态；逻辑层必须**原样保留、原样写回**，永不解析 |

### 3.2 Video（仅元数据）

| 字段 | 类型 | 约束/缺省 | 说明 |
| --- | --- | --- | --- |
| `video_id` | uuid | 必填 | |
| `file_path` | str | 必填 | **相对项目根的相对路径**（posix 风格 `/` 分隔，见 project-format.md §3）；视频不复制、不入库 |
| `original_path` | str \| null | null | 登记时的绝对路径，仅作重连提示/缓存，不参与解析 |
| `display_name` | str | 必填 | 默认取文件名 |
| `width_px` / `height_px` | int | > 0 | 像素坐标系的范围依据 |
| `fps_container` | float | > 0 | 容器/探测报告的名义帧率（OpenCV/ffprobe 所得），**仅供参考** |
| `frame_count` | int | > 0 | 探测得到的总帧数；加载真实视频后需以实际解码数复核（Phase 2） |
| `container_format` | str \| null | null | 如 `mp4`；仅提示 |
| `sha256` | str \| null | null | 重连时校验同一性；null = 未计算 |
| `vfr_suspected` | bool | false | 容器平均帧率与流帧率不一致时置 true（§5.3） |

> Phase 1 不解码视频：以上字段由调用方/探测脚本提供。真实探测与复核在 Phase 2（VideoReader）落地。

### 3.3 Timeline

每个视频一份；**帧↔时间换算的唯一权威**。

| 字段 | 类型 | 约束/缺省 | 说明 |
| --- | --- | --- | --- |
| `video_id` | uuid | 必填 | |
| `fps_nominal` | float | > 0 | **本项目采用的名义帧率**（约定值）。初始化自 `fps_container`，用户可修正（如容器误报 59.94 而实际 60）；修正后触发 §5.7 的时间一致性复核 |
| `frame_indexing` | str | 恒为 `"zero-based"` | 帧号从 0 计数，指向**源视频**的帧；固定约定，不提供切换 |
| `working_zone` | [int, int] | [0, frame_count−1] | [in_frame, out_frame]，含端点；只影响显示/计算/步进范围，不影响时间基准（§5.4） |

换算规则与精度、VFR、seek/step、导出语义见 §5。

### 3.4 Track

| 字段 | 类型 | 约束/缺省 | 说明 |
| --- | --- | --- | --- |
| `track_id` | uuid | 必填 | |
| `video_id` | uuid | 必填 | 轨迹归属的视频 |
| `name` | str | 项目内唯一 | 默认 `Track 1`…；亦是未来 DLC 转换时的 bodypart 名（phase1-requirements.md §4） |
| `color` | str | hex `#RRGGBB` | 纯显示用途，非物理数据 |
| `kind` | str | `"point"` | Phase 1 仅点目标；`segment`/`ellipse` 等为 Phase 10 预留 |
| `keypoint_group` | str \| null | null | 多关键点骨架分组预留（Phase 10）；Phase 1 恒 null，一个 Track = 一个物理点 = 一个 DLC bodypart |
| `notes` | str \| null | null | |
| `created_at` | datetime | 必填 | |

### 3.5 TrackPoint（观测单元）

| 字段 | 类型 | 约束/缺省 | 说明 |
| --- | --- | --- | --- |
| `point_id` | uuid | 必填 | |
| `track_id` | uuid | 必填 | |
| `frame_index` | int | ≥ 0，源视频帧号 | 与 track 的 video 对应 |
| `time_s` | float | 写入时冻结 | 按 §5.2 由 Timeline 计算；加载时做一致性校验（§5.7） |
| `pixel_x` / `pixel_y` | float | 图像坐标系 | 原点左上、x 向右、**y 向下**；允许亚像素浮点；范围 [0, width]×[0, height]，越界为警告不拒绝 |
| `source` | str | 注册表枚举 | 见 §4.5.1；Phase 1 注册 `manual`、`template` |
| `source_detail` | str \| null | null | 引擎运行 id / 模型标识（如 `run-20260828-01`、`dlc:shuffle=1:snapshot=50`） |
| `confidence` | float \| null | [0, 1] | 源给出的**检测/定位确信度**；null = 该来源不提供（manual 恒 null）；语义见 §4.5.2 |
| `visibility` | str | `visible` \| `occluded` \| `unknown` | 三态可见性，与 confidence 独立；manual 缺省 `visible`，引擎缺省 `unknown`；§4.5.3 |
| `quality_flags` | list[str] | 可空 | 开放字符串集：`interpolated` / `extrapolated` / `outlier` / `low_confidence` / `user_locked` / `repaired`；消费方忽略未知值 |
| `status` | str | `active` \| `superseded` | 见 §4；`superseded` = 被更高优先级观测遮蔽，**保留不删** |
| `superseded_by` | uuid \| null | null | 指向取代者（status=superseded 时必填），构成修正链 |
| `created_at` / `modified_at` | datetime | 必填 | 写入/最后修改审计 |

缺测语义：**某帧不存在观测 = 缺测**。不写 NaN 行、不用 (0,0) 占位、不静默插值。需要连续序列的计算层（Phase 3）在内存中将缺测展开为 NaN，存储层保持稀疏。

### 3.6 Annotation（语义角色，非独立对象）

- `Annotation` = **source=manual 的 active TrackPoint**。它同时承担两个职责：用户的测量输入；未来 AI 训练数据的来源（对应 architecture.md §3 的转换入口）。
- **Phase 1 不设独立"标注集/训练集划分"对象**：全部 active manual 观测即标注集。Phase 4 需要训练/验证划分时，以追加 `annotation_sets` 对象的方式扩展（additive，不破坏现有结构）。
- 理由：SLEAP 的 `Instance` vs `PredictedInstance` 类型分离证明"用户/预测"必须可区分——本模型用 `source` 字段区分；而"训练集划分"是训练期的工作流概念，提前物化会引入与训练流程耦合的负担（DLC 自身也是在 `create_training_dataset` 阶段才做划分）。

### 3.7 Calibration

每个标定归属一个视频；一个视频可有多个标定方案，Project 通过
`active_calibration_by_video` 为每个视频分别指定生效者。

| 字段 | 类型 | 约束/缺省 | 说明 |
| --- | --- | --- | --- |
| `calibration_id` | uuid | 必填 | |
| `video_id` | uuid | 必填 | |
| `name` | str | 必填 | |
| `type` | str | `"line_scale"` | Phase 1 仅线比例尺；`plane`（单应）等为远期预留 |
| `scale_end_1_px` / `scale_end_2_px` | [float, float] | 必填 | 比例尺两端点的像素坐标；两点距离必须 > 0 |
| `known_length` | float | > 0 | 两端点对应的真实长度 |
| `unit` | str | 注册表枚举 | `m` / `cm` / `mm`（向 SI（米）的换算系数固定内置于实现） |
| `origin_px` | [float, float] \| null | null = `(0, height_px)`（画面左下角） | 世界原点在像素坐标中的位置 |
| `rotation_deg` | float | 0.0 | 世界 x 轴相对图像 x 轴的旋转角；**在世界系（y 向上）中逆时针为正** |
| `applies_from_frame` / `applies_to_frame` | int \| null | null = 全时间轴有效 | 时变标定预留（Kinovea `GetPointAtTime` 语义）；Phase 1 恒 null |
| `notes` / `created_at` | — | | |

派生量 `pixels_per_unit s = dist(scale_end_1, scale_end_2) / known_length` 一律**现算不存储**（纯函数，避免两处真值）。

变换数学、Y 轴方向与测试要求见 §6.2/§6.4。

### 3.8 DerivedData（派生数据；Phase 1 仅定义结构，不实现计算）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `derived_id` | uuid | |
| `track_id` | uuid | 派生自哪条轨迹 |
| `kind` | str 注册表 | `world_position` / `smoothed_position` / `velocity` / `acceleration` / `custom` |
| `input` | object | `{track_id, source_filter: str\|null, include_superseded: false}`——声明输入是哪条轨迹的哪层观测 |
| `calibration_ref` | uuid \| null | 世界坐标类派生必须记录所用标定 id；标定变更即 stale（§6.3） |
| `pipeline` | list[object] | 有序步骤：`{step: 注册表名, params: object}`，如 `savgol{window,polyorder}` → `finite_difference{method}`；**参数必须完整可复现**（Pose2Sim recap 教训） |
| `frames` | list[int] | 稀疏帧号数组（与 values 对齐；缺测帧不出现） |
| `values` | list[list[float]] \| null | 逐帧值；大型数组置 null 并用 `payload_ref` 外置 |
| `payload_ref` | str \| null | 外置数据文件的相对路径（如 `data/derived/xxx.npy`） |
| `unit` | str | 值的单位（长度单位或其导出单位 m/s、m/s² 等） |
| `produced_by` | str | 应用版本 + 算法实现版本 |
| `created_at` | datetime | |
| `status` | str | `valid` \| `stale`——stale 表示输入已变化需重算，重算前不得用于结论性输出 |

---

## 4. 四层数据语义与读写/覆盖规则

### 4.1 四层定义

| 层 | 名称 | 内容 | 可变性 |
| --- | --- | --- | --- |
| L1 | 原始观测（raw observation） | 全部 TrackPoint（含引擎输出与手工点） | **只增不改**；修正以"新增 + 遮蔽"表达 |
| L2 | 人工标注（manual annotation） | L1 中 source=manual 的子集 | 语义角色；用户可删改自己的点（见 §4.4），但不触碰引擎点 |
| L3 | 跟踪结果（tracking result） | L1 中 source=engine 的子集，按 `source_detail`（run id）分组 | 一次运行的输出整体存在；不被后续运行覆盖 |
| L4 | 派生数据（derived data） | DerivedData 全部 | 可随时删除/重算/标记 stale |

L2 与 L3 都是 L1 的投影（按 source 过滤），不是独立存储；这一条直接回应"raw tracking data、manual corrections、processed data 如何区分"——**区分靠 source 与 status 字段，不靠物理分表**。

### 4.2 写入与覆盖规则

同一 `(track_id, frame_index)` 上可能并存多条观测（不同 source / 不同 run）。

| 操作 | 规则 | 对应先例 |
| --- | --- | --- |
| 手工加点（帧上无 manual 点） | 新增 manual 观测（active） | TrackLab `addOrReplacePointOnTrack` |
| 手工加点（帧上已有 manual 点） | **last-wins**：旧 manual 点被硬删除，新点 `created_at` 记录时间；引擎点被遮蔽（§4.3） | 同上 |
| 引擎批量写入（run） | **first-wins**：目标帧已存在任何 active 观测（manual 或先前 run）则跳过该帧，不报错不覆盖 | TrackLab `addPointToTrack`；Kinovea `PerformTracking` 拒绝已跟踪时间戳 |
| 用户显式"重新跟踪并允许覆盖" | 不覆盖旧 run；新 run 正常写入（first-wins 跳过已有帧），随后用户可将旧 run 整体清除或逐点遮蔽 | DLC refine 循环（旧预测始终保留） |
| 手工修正一帧（该帧有引擎点） | 新增/替换 manual 点；该帧的引擎点置 `status=superseded`、`superseded_by=<新 manual 点 id>`，**数值原样保留** | **本规范核心决策，见下** |

**决策①（A1 验收问题 ①）**：AI 预测被人工修正后**不覆盖原预测值**；两者分层保留，引擎点被遮蔽但可查（修正前后对比、再训练收益评估都依赖原值）。此为 TrackLab first-wins/last-wins 双路径 + Kinovea 修正语义 + SLEAP user/predicted 分离的综合结论。

### 4.3 生效值解析（effective resolution）

对任意 `(track, frame)`，参与显示/计算/导出的观测按以下纯函数规则唯一确定：

1. 过滤 `status == "active"` 的观测；
2. 若存在 manual 观测 → 生效（manual 至多一条，由 §4.2 保证）；
3. 否则取 `created_at` 最新的引擎观测（同一 run 内 first-wins 保证至多一条）。

实现提示：加载时可预计算 effective 索引；`status/superseded_by` 是持久化的冗余（便于 GUI 显示修正链），解析规则本身必须是纯函数并被单元测试覆盖。

### 4.4 删除语义

| 对象 | 删除方式 |
| --- | --- |
| manual 观测 | 允许硬删除（用户点击误标，意图明确）；若它遮蔽了引擎点，被遮蔽点**恢复为 active**（修正链回退） |
| 引擎观测 | 不允许逐点硬删除；只允许 (a) 手工修正遮蔽（§4.2）或 (b) 按 run 整体清除（需确认，且清除的是该 run 全部点） |
| Track | 删除 Track 级联删除其全部观测与相关 DerivedData（需确认） |
| Calibration | 允许删除非 active 的标定；删除 active 标定 = 回到"未标定"，其 `calibration_ref` 派生数据置 stale |
| DerivedData | 随时删除，无损（可重算） |

### 4.5 元数据字段

#### 4.5.1 source（决策②）

`source` 是**开放注册表枚举**（持久化于 `Project.registries.sources`），Phase 1 注册：

| 值 | 含义 |
| --- | --- |
| `manual` | 用户手工标注/修正 |
| `template` | OpenCV 模板匹配（确定性 fallback 引擎） |

文档化预留（Phase 4+ 适配器接入时追加注册，不迁移 schema）：

| 值 | 含义 |
| --- | --- |
| `dlc` | DeepLabCut 推理（likelihood → confidence） |
| `tapir` | TAPIR/TAPNext（visibility prob + expected_dist → visibility/confidence） |
| `cotracker` | CoTracker（布尔 visibility → visibility；许可解决前不集成） |
| `sam2` | SAM2 掩码派生点（mask→点，`quality_flags` 加 `derived_from_mask`） |

判定规则：**能否容纳 = 新引擎是否只需追加注册表项即可写入数据**。以上四类均满足（TAPIR 的 expected_dist 放入 `source_detail` 说明或未来 additive 字段）。未知 source 值按 tolerant read 原样保留。

#### 4.5.2 confidence（决策③之一）

- 连续值 [0, 1]；**缺测 = null，null ≠ 0 ≠ 1**（Sports2D/DLC2Kinematics 的"低置信度不静默造值"教训）。
- manual 点恒 null——"用户目击"不是引擎置信度，赋 1.0 会污染置信度过滤语义；过滤规则实现为 `confidence is None or confidence >= threshold`（manual 天然通过）。
- 各引擎在适配器边界完成归一化（如 OpenCV `TM_CCOEFF_NORMED` 的 [−1,1] 截断到 [0,1]），原始分数写入 `source_detail`。

#### 4.5.3 visibility（决策③之二）

**confidence 与 visibility 是两个字段**，不合并：

- confidence 回答"引擎对这个坐标有多确信"；visibility 回答"目标此刻是否真的在画面中/可见"。DLC 的 likelihood 属前者（遮挡时仍可能高 likelihood 地贴着背景纹理）；TAPIR 同时输出 occlusion 与 expected_dist，正是两个概念的证明；SLEAP 的 point_scores / tracking_scores 分离同理。
- 三态枚举 `visible / occluded / unknown`：manual 可标注遮挡（物理实验常见：摆线被支架遮挡一瞬）；引擎在适配器边界映射（阈值规则记录于适配器文档）。
- 运动学计算对两者的处理不同：occluded 点**可参与**计算（位置可能准确）也可被用户排除；confidence 低于阈值的点默认排除（Phase 3 以 ADR 定阈值语义）。

#### 4.5.4 quality_flags

开放字符串集合（§3.5）。与 confidence/visibility 的区别：flags 是**离散处理标记**（"这点是插值出来的""被用户锁定"），由工具写入、人消费；枚举值追加不需要迁移。

---

## 5. 时间语义（Timeline 契约）

> 目标：杜绝 `time = row_index / fps` 类隐式假设。对应 A2。

### 5.1 基本约定

- **帧号从 0 计数**，指向源视频的真实帧：`frame_index ∈ [0, frame_count − 1]`。与外部系统交界处（OpenCV 的 `CAP_PROP_POS_FRAMES` 是 1-based 位置、DLC 提取帧命名等）由边界代码显式转换并加测试（Phase 2/4 实测确认，`docs/development.md` §1.1 的边界实测原则）。
- **Phase 1 假设 CFR（恒定帧率）**，时间由 `fps_nominal` 定义（§3.3），VFR 处理见 §5.3。
- `fps_container`（文件声明）与 `fps_nominal`（本项目约定）分离：用户可修正错误元数据；观测的 `time_s` 在写入时冻结，因此 fps 修正是显式操作而非静默变化（§5.7）。

### 5.2 frame ↔ time 换算与精度规则

```text
frame_to_time(N) = N / fps_nominal                      # 一次除法
time_to_frame(t) = round(t × fps_nominal)               # 一次乘法 + 就近取整，钳位到 [0, frame_count−1]
```

精度规则：

1. **禁止增量累积**——不得用 `t += 1/fps` 循环构造时间序列（浮点漂移）；一律由 frame_index 直接一步换算（TrackLab 29.97 fps 测试的教训）。
2. 就近取整必须确定性：实现采用 `floor(t × fps + 0.5)` 语义（正数域），并在测试中固化；不依赖语言内建 round 的银行家舍入。
3. 时间比较用容差 `|t1 − t2| < 1e-9 s`；帧相等用整数相等。
4. 视频时长定义 `duration_s = frame_count / fps_nominal`（内部权威）；容器报告的时长仅存于 `Video` 元数据作交叉核对。
5. 浮点实现：`fps_nominal` 为 float64。NTSC 类帧率（29.97 = 30000/1001）以 float 存储在换算一万帧内误差远小于 1 µs，可接受；若未来需要比特级可复现，预留 `fps_rational: [num, den]` additive 字段，Phase 1 不实现。

### 5.3 VFR 策略

- 登记视频时若探测发现容器 `avg_frame_rate ≠ r_frame_rate` 或时间戳不规则迹象，置 `vfr_suspected = true`。
- **Phase 1 明确策略：只支持 CFR；对 `vfr_suspected` 的视频拒绝进入分析并提示用户转码为 CFR**（提示语建议 ffmpeg 命令模板）。此结论即使未来改变，也只是放宽校验 + 启用"逐帧真实时间戳"路径——数据模型已通过"观测冻结 time_s"为此留位（TrackLab time 权威制、Kinovea `AverageTimeStampsPerFrame` 的教训均已吸收）。

### 5.4 Working Zone（裁剪）语义

- `working_zone = [in_frame, out_frame]`（含端点），作用：步进/播放/图表/计算/导出的**过滤范围**。
- **时间基准永不重置**：zone 内帧的时间仍是源视频绝对时间 `frame / fps_nominal`。

**决策（A2 验收问题）**：用户从第 100 帧裁剪到第 500 帧后，导出的 `time_s` **从原视频时间起算**（第 100 帧 → `100/fps`），`frame` 列也是源视频帧号。理由：重置基准会制造"两套时间真相"，破坏观测、标定与未来训练数据对源视频的可追溯性；相对时间是平凡的减法（`time_s − in_frame/fps`），分析端随时可得，反之不可复原。Tracker（VideoClip 保留源帧号语义）与 Kinovea（时间戳制）均为此做法。

### 5.5 seek / step 语义

- 逐帧步进 = `frame_index ± 1`（整数运算），随后由 `frame_to_time` 得到显示时间；不经过浮点中间量。
- 按时间跳转 = `time_to_frame`。
- 拖动时间轴（scrub）期间不产生观测写入；标注点永远打在"当前帧"`frame_index` 上，`time_s` 由 Timeline 现算后随观测冻结。
- GUI 的 scrub/commit 解耦（拖动中轻量预览、松手才解码）属 Phase 2 视频层职责，此处只约束数据语义。

### 5.6 导出 CSV 的时间字段

- `frame`：int，源视频 0-based 帧号；
- `time_s`：float，源视频绝对秒（`frame / fps_nominal`）。
- **禁止**输出"行号当时间"或未命名的相对时间列；未来若加 `time_rel_s`（相对 working zone 起点）属 additive 列，且与 `time_s` 并存。
- 缺测帧：稀疏导出，空单元格留空（TrackLab `TrackExporter` 的稳定表头 + 空单元格模式）。

### 5.7 fps 修正与时间一致性复核

- 加载项目时逐观测校验 `|time_s − frame_index / fps_nominal| ≤ 0.5 / fps_nominal + 1e-6`；不一致的观测标记 `quality_flags += "time_mismatch"` 并在 UI 提示（不静默改写）。
- 用户显式"按新 fps 重算全部时间"= 一次性迁移操作：重写 `time_s`、清除 flag、`modified_at` 更新、保存。
- 触发场景：用户修改 `fps_nominal`；或加载真实视频（Phase 2）后实测帧数/帧率与登记不符。

---

## 6. 坐标与标定

### 6.1 坐标空间分层（决策：raw 永远像素）

| 空间 | 定义 | 用途 | 是否持久化 |
| --- | --- | --- | --- |
| screen | GUI 控件像素（含缩放/平移） | 交互命中测试 | 永不 |
| **image/pixel** | 视频栅格坐标：原点左上，x 右，**y 下**，亚像素 float | **raw 观测的唯一存储空间** | 是 |
| world/physical | 物理坐标：原点/旋转/比例尺按标定，**y 上**，单位 = 标定 unit | 物理计算与图表 | 仅以 DerivedData 形态缓存 |

规则：

1. 观测写入只接受像素坐标；GUI 层负责 screen→pixel 的逆映射后再入存储。
2. 像素→物理的完整链路（A3 验收问题）：`p_px（TrackPoint）→ p_px − origin_px → S(1/s,−1/s) → R(θ) → p_world`，其中 `s = pixels_per_unit` 现算自标定（§6.2）；链路实现为纯函数，无隐藏状态。
3. 世界系固定 **y 向上**（物理惯例），Y 翻转内建于正向变换的 `S(1/s,−1/s)` 算子，不是用户选项；TrackLab 的 `S(s,−s)` 是其反向 world→pixel 变换。x/y 互换、Z 轴等远期需求走 additive 扩展。
4. 某视频未出现在 `active_calibration_by_video` 时，系统不为该视频产生世界坐标；图表可显示像素坐标并明确标注单位为 px。

> 与 TrackLab 的差异说明：TrackLab 持久化的是模型（世界）坐标，因此标定变更后需要 `retransformTrackPoints` 把旧坐标经像素空间钉回新变换。我们**直接持久化像素坐标**，标定变更天然无需重变换观测——这是"raw 永远像素"原则的直接收益。

### 6.2 标定变换数学（纯函数）

设标定给出 `o_px = origin_px`、端点 `e1, e2`、真实长度 `L`、旋转 `θ`（度，世界系逆时针为正）：

```text
s = ‖e2 − e1‖ / L                （pixels_per_unit，> 0）
p_world = R(θ) · diag(1/s, −1/s) · (p_px − o_px)  # 像素 → 世界
p_px    = o_px + diag(s, −s) · R(−θ) · p_world    # 世界 → 像素（逆变换）
R(θ) = [[cosθ, −sinθ], [sinθ, cosθ]]              # θ 已换算为弧度
```

`rotation_deg` 表示对完成比例换算与 Y 翻转后的坐标向量施加的旋转；在
Y-up 世界系中逆时针为正。它描述的是**坐标值的主动旋转**，不是旋转坐标轴后
重新表达同一向量。

约定与验证示例（作为单元测试规格，Phase 1 实现必须全过）：

1. **比例尺**：端点 (0,0)–(100,0)，L = 50 mm → s = 2 px/mm；
2. **Y 翻转**：沿用规格 1 的 `s = 2 px/mm`，o = (10, 20)，θ = 0，像素 (10, 30)（原点下方）→ 世界 (0, −5) mm；像素 (10, 10)（原点上方）→ 世界 (0, +5) mm；
3. **旋转**：θ = 90°，原点右侧的像素点映射到世界 +y；
4. **往返不变量**：对任意合法标定与采样点，`inverse(forward(p)) == p`（浮点容差 1e-9 相对误差）；
5. **退化拒绝**：端点重合或 `known_length ≤ 0` → 创建/更新时抛校验错误。**故意不采用 TrackLab 的"退化返回 identity"回退**——物理测量中静默退化为恒等变换会伪装成有效数据；错误必须显式。
6. 逆变换用于：GUI 点击的世界坐标换算回像素、标定对比、以及"检查某世界坐标对应的像素位置"类查询。

### 6.3 标定变更的失效传播（决策④）

| 事件 | raw 观测（TrackPoint） | DerivedData | 说明 |
| --- | --- | --- | --- |
| 编辑 active 标定（端点/长度/单位/原点/旋转） | **完全不变** | `calibration_ref` 指向它的世界系派生 → `status = stale` | 像素是事实，世界坐标是解释 |
| 切换 active 标定为另一标定 | 不变 | 同上（按 `calibration_ref` 匹配置 stale；指向新 active 的不受影响） | |
| 删除 active 标定 | 不变 | 世界系派生 stale | 系统回到未标定态 |
| Track 删除 | 级联删除 | 级联删除 | |
| fps 修正 | `time_s` 按 §5.7 处理 | 时间敏感派生置 stale | |
| 引擎 run 清除 / 观测遮蔽变化 | 见 §4 | 输入层受影响的派生置 stale | 派生的 `input.source_filter` 决定敏感集 |

重算策略：stale 只是标记；重算由用户/上层显式触发（Phase 3 起提供"重新处理"操作），Phase 1 仅需实现标记传播。

### 6.4 标定的测试要求（写入 Phase 1 测试计划）

- 全部用**解析已知点**的合成数据（§6.2 的 6 条规格逐条成测）；禁止用渲染截图类测试替代；
- 往返不变量测试覆盖随机标定参数 + 随机点集（固定种子）；
- 单位换算（mm/cm/m → SI）单独成测；
- 退化输入的校验错误路径成测。

---

## 7. Phase 1 最小接口边界（概念契约）

> 只列 Phase 1 真正需要的边界；均为概念级契约（职责 / 输入输出 / 错误语义），不含完整签名。全部无 Qt 依赖、可独立单元测试。

### 7.1 ProjectRepository（项目仓库）

- **职责**：在目录上创建 / 加载 / 保存 / 另存项目；封装原子写入、UTF-8 编码、路径解析（相对↔绝对）、schema 版本守卫与迁移链调用（格式细则见 project-format.md）。
- **输入输出**：路径 ↔ Project 对象（含全部子对象）。
- **错误语义**：文件不存在 → "未找到"；schema 版本高于实现 → **明确拒绝**并提示所需版本（不猜、不部分加载）；JSON 损坏 → 拒绝并指向备份文件；迁移链中任一步失败 → 原文件保持不动。**永不静默修复**。

### 7.2 Timeline 运算（纯函数集）

- **职责**：`frame_to_time` / `time_to_frame` / working zone 钳位 / 一致性校验（§5）。
- **输入输出**：Timeline 值对象 + 帧或时间标量 ↔ 对应标量。
- **错误语义**：帧号越界 → 钳位并返回（用于 UI 步进）；非法 fps（≤0）在 Timeline 构造/修改时拒绝。

### 7.3 CalibrationTransform（纯函数集）

- **职责**：由 Calibration 构造可逆变换；前向/逆向点变换；`pixels_per_unit` 计算（§6.2）。
- **输入输出**：Calibration 值对象 → 变换对象（或无状态函数对）；点 ↔ 点。
- **错误语义**：退化标定在构造时拒绝（ValueError 语义）；变换函数要求已验证的标定，不做运行时回退。

### 7.4 TrackStore（观测存取与解析）

- **职责**：观测集合的增查改：手工加点（last-wins + 遮蔽链维护）、引擎批量写入（first-wins 跳过）、删除语义（§4.4）、生效值解析（§4.3）、按 track/frame/run 的查询迭代。存储后端（project.json 内嵌 or 未来外置）被本接口隐藏。
- **输入输出**：TrackPoint 值对象 / 查询条件 ↔ 观测集合。
- **错误语义**：track_id 不存在 → 拒绝；对引擎点逐点硬删 → 拒绝（只允许遮蔽或按 run 清除）；first-wins 的"跳过"是正常返回值的一部分（报告写入数/跳过数），不是错误。

### 7.5 DLC 标注转换器（Phase 1 交付设计文档，非代码）

- **职责**：内部标注（source=manual 观测）↔ DLC CollectedData（MultiIndex：scorer/bodyparts/coords，HDF5+CSV 双写）双向转换。映射规则、无损判定与 round-trip 测试定义见 `phase1-requirements.md` §4。
- **错误语义**：轨迹名含 DLC 非法字符、帧索引越界等 → 转换前校验并拒绝，不出部分产物。

### 7.6 刻意推迟清单（推迟不改变 Phase 1 数据结构）

| 推迟项 | 去向 | 数据模型已留位 |
| --- | --- | --- |
| EngineAdapter / 引擎适配器契约 | Phase 4（先有 benchmark-spec） | `source` 开放注册表；first-wins 批量写入即适配器落点 |
| TaskManager / 任务抽象 | Phase 4 前 | 不持久化任务状态；run 以 `source_detail` 记录 |
| TrackingRun 溯源表（run→引擎版本/模型/参数） | Phase 4 | `source_detail` 字符串承载 id，届时加 `runs` 集合（additive） |
| VideoDecoder / VideoReader 服务 | Phase 2 | `Video` 元数据对象与 `frame_count/fps` 字段即其产出契约 |
| 运动学计算（平滑/微分） | Phase 3 | DerivedData 结构与 stale 传播已定义 |
| 导出服务（CSV/图表/视频） | Phase 8（CSV 列定义已定于 §5.6） | |
| 模型库 | Phase 7 | 不入 project.json；`models/` 目录引用（project-format.md） |
| 标注集/训练集划分 | Phase 4 | §3.6 的 additive 路径 |
| 多相机 / 3D / 时变标定 | Phase 10 | `videos` 多登记、`applies_from/to_frame` 预留 |

---

## 8. 决策索引

| 决策 | 结论 | 依据 |
| --- | --- | --- |
| 观测单元一步到位带 provenance | §3.5 | project map §6.1 |
| 手工修正不覆盖 AI 预测，遮蔽保留 | §4.2 决策① | TrackLab / Kinovea / SLEAP |
| source 开放注册表可容纳 6 类来源 | §4.5.1 | PLAN A1 验收② |
| confidence 与 visibility 分立 | §4.5.2–4.5.3 | PLAN A1 验收③；DLC/TAPIR/SLEAP 输出形态 |
| 标定变更仅派生层失效 | §6.3 | PLAN A1 验收④；TrackLab/Kinovea |
| 帧号 0-based、CFR、VFR 显式拒绝 | §5.1/§5.3 | PLAN A2；TrackLab 29.97 测试 |
| 裁剪不重置时间基准 | §5.4 决策 | PLAN A2；Tracker/Kinovea |
| raw 只存像素、世界坐标可重算 | §6.1 | PLAN A3；TrackLab retransform 的对照收益 |
| 退化标定显式报错（不学 TrackLab identity 回退） | §6.2 约定 5 | project map §7.8 的反面教训 |
| Annotation 是角色不是表 | §3.6 | SLEAP user/predicted 分离 + DLC 划分时机 |
| 持久化格式与目录 | project-format.md + ADR-0003 | PLAN A4 |
