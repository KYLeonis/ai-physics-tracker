# CODE_STANDARD.md — AI Physics Tracker 代码规范

本文件回答一个问题：**在这个项目里，代码应该怎样写。** 目标是让不同 Coding Agent、不同会话、未来的开发者产出的代码在命名、组织、风格、错误处理、类型、测试上保持一致——呈现出稳定、克制、成熟的工程风格，而不是各自的习惯。

- 依据：`docs/spec/data-model.md`（领域模型与术语）、`docs/spec/project-format.md` + ADR-0003（持久化）、`docs/architecture.md`（分层）、`docs/development.md` §1.1（跨平台规则）。规范与 spec 冲突时以 spec 为准并修订本文件。
- 适用于 `src/` 与 `tests/` 的全部 Python 代码。GUI（PySide6）规范为 Phase 2 预留，仅有原则性约定。

---

## 1. Agent 使用规则（写代码前必读）

1. 顺序阅读：`AGENTS.md` → 本文件 → 当前任务相关的 spec（`docs/spec/`）→ **改动点附近的已有代码**。
2. **延续附近代码的既有模式**。本文件规定的是底线与统一项；具体模块内已有约定（如某包的错误类型组织方式）优先延续。
3. 发现已有代码与本规范不一致时：
   - **不要**顺手大规模重构无关代码；
   - 本次修改的**新代码**遵循本规范；
   - 重要历史问题记录为后续 cleanup（记入 subphase plan 的遗留问题或 `docs/status/current.md`），集中处理。

---

## 2. 总原则（Quality Principles）

```text
可读性优先于聪明          Readability over cleverness
显式优先于隐式            Explicit over implicit
先简单后抽象              Simple before abstract
小而内聚的模块            Small cohesive modules
稳定的公共接口            Stable public interfaces
能用纯函数就用纯函数      Pure functions where practical
没有隐藏的全局状态        No hidden global state
不过早优化，不过早抽象    No premature optimization / abstraction
```

核心度量：**下一个人（很可能是另一个 Agent）能否在不读完整实现的情况下正确使用和修改这段代码。**

---

## 3. 命名规范

### 3.1 通用规则

| 对象 | 规则 | 示例 |
| --- | --- | --- |
| 包 / 模块 | `snake_case`，短、名词、单数 | `ai_physics_tracker.domain.timeline` |
| 类 | `PascalCase` 名词 | `TrackPoint`、`ProjectRepository` |
| 异常 | `PascalCase` + `Error` 后缀 | `ProjectFormatError` |
| 函数 / 方法 / 变量 | `snake_case` | `frame_to_time`、`pixel_x` |
| 常量 | `UPPER_SNAKE` | `DEFAULT_FPS = 30.0` |
| 私有成员 | 前导 `_` | `_rebuild_index` |
| Protocol | 名词或形容词，`PascalCase` | `ObservationSink` |
| 测试文件 / 函数 | `test_<模块>.py` / `test_<行为>` | `test_time_to_frame_is_deterministic` |

### 3.2 领域词汇表（强制统一，禁用别名）

项目核心术语的命名**以 `docs/spec/data-model.md` 术语表为唯一权威**，代码中禁止使用同义变体：

| 规范名（唯一） | 禁止的变体 |
| --- | --- |
| `frame_index` | `frameId` / `frame_id_` / `frameID` / `frame`（作字段名时） |
| `time_s` | `timestampSec` / `timeSeconds` / `ts` / `t_s` |
| `fps_nominal` | `fps`（无修饰）/ `nominal_fps` |
| `fps_container` | `container_fps` |
| `pixel_x` / `pixel_y` | `x_px` / `coordX`（坐标分量用 `pixel_` / `world_` **前缀**区分空间） |
| `width_px` / `height_px` | `videoWidth` / `w_px` |
| `working_zone` | `clip_range` / `trim_zone` |
| `origin_px` / `rotation_deg` / `known_length` | — |
| `confidence` / `visibility` / `quality_flags` | `prob` / `score`（作字段名时） |
| `source` / `source_detail` | `engine` / `origin` |
| `superseded_by` / `status` | — |

命名与单位的约定：

- **数值字段带单位后缀**：`_s`（秒）、`_px`（像素）、`_deg`（度）、`_m`（米）；无后缀的数值不是物理量。
- **坐标分量用空间前缀**：`pixel_x`（raw 层唯一存储形态）与 `world_x`（派生层）严格区分，见 §9。
- 布尔用谓词形式（`is_` / `has_` / `_suspected`），避免否定式命名（用 `is_active` 而非 `is_not_deleted`）。

### 3.3 类命名的两条路线

- **值对象（数据）**：直接用领域名词，与 spec 术语表同名——`Project`、`Video`、`Timeline`、`Track`、`TrackPoint`、`Calibration`、`DerivedData`。
- **服务 / 组件（行为）**：领域名词 + 角色后缀——`ProjectRepository`、`TrackStore`、`CalibrationTransform`、`DLCAnnotationConverter`。禁止 `Manager` / `Helper` / `Util` 类名。

### 3.4 Qt 层（Phase 2 起）

Qt 层内部（widget、signal/slot、方法覆写）遵循 **Qt 惯例 camelCase**（`frameChanged`、`onPlayClicked`），与领域层的 snake_case 形成清晰分层边界——看到 camelCase 即知在 GUI 层。signal 名用名词/过去式状态（`frameChanged`、`projectLoaded`），不用 `do*` / `handle*` 前缀命名 signal 本身。

---

## 4. 模块与包组织

- src-layout，包名 `ai_physics_tracker`（Phase 1 建立，`pyproject.toml` 见 phase1-requirements.md §7）。
- 分层与依赖方向遵守 `docs/architecture.md` 四层结构，硬规则：**领域层（domain）不 import Qt、不 import 任何 GUI 模块**；基础设施与 GUI 可以依赖领域层，反之禁止。
- 模块按领域概念组织（`domain/timeline.py`、`domain/track.py`），不按技术角色组织（禁止 `models.py` / `managers.py` / `utils.py` 这类万能筐）。
- 一个模块一个内聚主题；超过 ~500 行且包含多个主题时拆分。`__init__.py` 只做有意的再导出，不放实现。
- 第三方库的数据格式（DLC DataFrame、OpenCV 属性、HDF5）**只在适配层边界出现**，不得渗透为内部模型（project map §7.12 反模式；ADR-0003 结论 2）。

---

## 5. 函数与方法

- 单一职责；典型函数 ≤ ~50 行，超过时先问"它在做几件事"。
- 参数 ≤ ~5 个（数据对象可整体传入）；返回值明确——返回 `None` 表示"无值"时不与"空集合"混用。
- **优先 early return**，嵌套 ≤ 3 层；嵌套过深说明逻辑该拆分或反转条件。
- 避免隐藏副作用：函数名或 docstring 应能看出它是否修改存储、写文件。纯函数（时间换算、坐标变换、生效值解析）保持纯——同类输入只做计算，便于测试与复用。
- **不为"复用"创建没有实际价值的抽象**：出现第二个真实用例之前保留局部实现；两次真实复用后再抽公共函数。同样不为单一调用方建 factory / builder。

什么时候拆函数：一段逻辑需要独立命名才读得懂、需要独立测试、或在 ≥2 处真实重复。什么时候保留局部：拆出来反而要求读者跳转三处才能理解主流程。

---

## 6. 类与数据模型

- **值对象（领域数据）**用 `@dataclass`；不可变语义优先（`frozen=True`，除非 spec 明确要求可变，如 `modified_at` 更新与 registries）。字段名与 spec 字段一一对应（§3.2 词汇表）。
- **服务 / 组件**（Repository、Store、Transform）用普通类或模块级纯函数集——spec §7 的概念契约已给出边界，实现不要扩大职责。
- 数据对象 vs 服务的判据：**"它是事实，还是对事实的操作"**。事实用 dataclass；操作用服务/函数。不给 dataclass 加业务方法之外，也不给服务类塞一堆可变数据字段。
- 组合优先于继承；继承只用于"确实是一种"（如异常层级）。禁止 God Object：一个类同时管数据、持久化和 UI 就是错误信号。
- 数据校验发生在**构造/写入边界**（Timeline 拒绝 fps ≤ 0、Calibration 拒绝退化输入），构造成功即合法——下游代码不需要防御性重查。

---

## 7. 类型注解

Python 3.11，使用现代语法（`list[str]`、`X | None`，不用 `Optional`/`List`）。

- **public API 与领域模型完整标注**（每个函数签名、每个 dataclass 字段）——这是 Agent 之间互不误解的主要手段。
- 私有辅助函数可不标返回类型之外的全部参数，但标了就不许含糊。
- `pathlib.Path` 用于一切文件系统路径；**持久化内的相对路径**按 project-format.md §3 用 `PurePosixPath` 语义存储。
- `None` 必须有明确语义且写下来（`confidence: float | None`——`None` = 来源不提供，**不是 0 也不是低**，data-model.md §4.5.2）。
- 集合标注元素类型（`list[TrackPoint]`，不裸 `list`）。
- numpy 数组在有分工价值时标注（`np.ndarray[tuple[int, ...], np.dtype[np.float64]]` 或至少 `npt.NDArray[np.float64]`）。
- 禁止无理由的 `Any`；使用处需注释为什么无法更精确。
- typing 帮助理解代码，不制造噪音：为了满足类型系统而把代码写得比无类型版更绕时，先怀疑设计。

---

## 8. 错误处理

错误语义的权威定义在 data-model.md §7（各组件"错误语义"小节），实现必须一致：

| 情形 | 处理方式 | 示例 |
| --- | --- | --- |
| 非法参数 / 退化输入（领域校验） | 抛 `ValueError` 语义的异常，构造边界拒绝（§6） | `known_length ≤ 0`、端点重合 |
| 持久化 / IO / schema 失败 | 自定义领域异常（`ProjectFormatError` 等，`*Error` 后缀，按包组织在 `errors.py`），消息指向原因与恢复路径 | schema 版本高于实现、JSON 损坏 |
| 预期内"未成功"（非错误） | **正常返回值**，不抛异常 | first-wins 批量写入的跳过计数；越界帧号钳位返回 |
| 缺测 | 数据中不存在该记录（稀疏），**不造值**：不写 NaN 行、不写 (0,0)、不静默插值 | data-model.md §3.5 |

规则：

- **永不静默修复、永不静默吞错**。禁止 `except Exception: pass`；捕获必须能回答"为什么这里可以恢复、恢复后系统处于什么状态"，并写为注释或日志。
- 不用异常做正常控制流（上表第三行的场景返回值就是为此）。
- 用户可见错误（GUI 提示/对话框）与开发者日志分离：领域层只抛异常携带结构化信息，翻译成人话是 GUI 层职责（Phase 2 起）。
- 异常消息包含操作上下文（哪个文件、哪个 track/frame），但不包含巨大数据。

---

## 9. 数值与科学计算代码

这是本项目最容易出错、也最要求纪律的部分：

1. **帧号是 `int`，时间是 `float` 秒**，永远不混用、不互相推断。一切 frame↔time 换算**只经 Timeline 纯函数**（`frame_to_time` / `time_to_frame`）；禁止 `row_index / fps`、禁止 `t += 1/fps` 增量累积（data-model.md §5.2）。
2. **像素与世界坐标严格分层**：raw 层只存像素（原点左上、y 向下）；世界坐标（y 向上）永远是 `CalibrationTransform` 派生结果。变量名用 `pixel_` / `world_` 前缀自证空间；一个函数内同时出现两种坐标时，中间量必须命名（不留无名元组穿层）。
3. **NaN 只存在于计算层的内存展开**（data-model.md §3.5：存储层稀疏，Phase 3 计算层展开为 NaN）。NaN 语义在注释/docstring 中声明，不隐式传播。
4. **浮点比较用容差**：测试断言带显式 `atol`；时间比较容差 `1e-9` s（data-model.md §5.2.3）。生产代码中禁止裸 `==` 比较浮点。
5. **无魔法数字**：算法参数（窗口长度、容差、阈值）一律命名常量或显式参数；DerivedData 的 pipeline 参数必须完整可复现（data-model.md §3.8）。
6. **公式注明依据**：数学变换（如 pixel→world 的 `R(θ)·diag(1/s,−1/s)`）注释引用 spec 章节（"data-model.md §6.2"）；不直观的数值技巧必须解释为什么。
7. 数值算法的测试用**解析已知解的合成数据**（匀速/匀加速/单摆小角度、标定六条规格），固定随机种子。

---

## 10. 路径与跨平台

`docs/development.md` §1.1 是完整规则，代码层面强制：

- 一律 `pathlib.Path`；禁止手工拼 `/` `\`、写死盘符、写死本机绝对路径。
- 文件读写显式 `encoding="utf-8"`（含 JSON、CSV、日志）。
- 持久化写入用"临时文件 + `os.replace` 原子替换"，绝不原地覆写（ADR-0003 §5）。
- 项目内数据路径以 posix 风格相对路径存储（project-format.md §3）。
- 不用 symlink；import 与路径大小写与磁盘一致。
- 平台差异集中处理：`platform`/`sys` 分支逻辑集中到基础设施层一个模块，禁止散落在领域代码中。

---

## 11. 日志

- 每个模块顶部 `logger = logging.getLogger(__name__)`；**禁止 `print()`**（一次性脚本的 `scripts/` 除外）。
- 级别边界：`debug` = 排查细节（含中间值摘要）；`info` = 有意义的生命周期事件（项目保存、run 完成）；`warning` = 可自动恢复但需知晓（time_mismatch 观测、vfr_suspected）；`error` = 操作失败且已抛出/上报。
- 日志带足上下文（track_id、frame 范围、文件路径），但**不输出巨大数组、完整对象图、帧像素**。
- 领域层不配置 handler / 格式 / 目标——那是应用层（Phase 2 起）的职责。

---

## 12. 注释与 Docstring

> 注释解释"为什么"，代码本身表达"做什么"。

- 必须注释的：数值算法依据（§9.6）、第三方库的坑/限制（含版本）、坐标与时间的非直觉语义、workaround 的原因与撤销条件。
- 禁止的：复述代码的注释（`# increment i`）、提交式注释（`# 修复了 xxx bug`）、与代码脱节的历史注释（过期即删）。
- Docstring 要求：public API、领域类、复杂算法有；**简单直观的函数不写**——机械生成的冗长 docstring 是噪音。格式 Google 风格。
- **语言一律使用中文**（含 `#` 注释与 docstring）：术语、标识符（类型名、函数名、字段名）、spec 文件与章节引用（如 "data-model.md §6.2"）、第三方 API 名保留英文原文；引用的异常消息、用户可见文案原文照抄。测试函数名、日志消息保持英文（与命名规范一致）。
- 每个模块顶部一段短 docstring 说明该模块职责与所属层（如"领域层：无 Qt 依赖"）。

---

## 13. Qt / GUI 代码（Phase 2 预留，仅原则）

- Widget 只做**显示与交互**；业务逻辑、数值计算、持久化调用不在 UI 类中展开。
- 长任务（训练、推理、导出）不阻塞 GUI 线程；通过后台任务机制执行（具体框架 Phase 4 ADR）。
- GUI 状态与领域数据分离：widget 持有引用/副本与显示映射，不把领域对象改成可双向绑定的"活"对象。
- screen 坐标 → pixel 坐标的逆映射发生在 GUI 层，入存储前完成（data-model.md §6.1）。

## 14. 并发 / 后台任务（Phase 4 前仅原则）

- 明确线程/任务所有权：共享数据写明谁拥有、谁只读。
- 不隐式共享 mutable state；跨线程交换的数据是不可变快照或消息。
- 长任务从第一天设计**取消语义**（检查点 + 优雅收尾），不是事后补。
- GUI 与 worker 间通过明确的数据边界通信（signal/queue），不共享裸对象。
- 不为了并行而并行：先测量，再并行化。

---

## 15. 测试代码

- 测试名表达**行为**而非实现：`test_manual_correction_supersedes_engine_point_and_keeps_original`。
- Arrange / Act / Assert 结构清晰（空行或注释分段）；一个测试一个核心行为。
- Deterministic：固定随机种子、无网络、无真实视频、无 sleep 竞态。
- 数值断言带显式容差（§9.4）；核心数值算法必须覆盖**边界条件**（缺测、越界、退化输入、空集合）。
- bug fix 附 regression test（先复现再修）。
- 不为 coverage 数字写无断言价值的测试；fixture 复用项目内合成数据构造器。
- 测试是文档：读者应能从测试名理解 spec 的哪条规则在被验证（AC-4/AC-5…可引用 phase1-requirements.md 编号）。

---

## 16. 反模式（Patterns to Avoid）

| 反模式 | 一句话判据 |
| --- | --- |
| God class / 巨型函数 | 一个名字说不清它做什么 |
| 万能 `utils.py` / `helpers.py` | 模块名没有领域含义 |
| 领域概念重复实现 | 同一语义出现两套名字/两个类 |
| 隐藏 mutable 全局 / 模块级可变状态 | 测试顺序影响结果 |
| magic string / magic number | 读代码的人不知道 0.5 / fps 哪来的 |
| 投机抽象 / 过度 factory | 只有一个实现/一个调用方 |
| 深层嵌套 / 长条件链 | 需要 ≥3 层缩进才能读完 |
| 复制粘贴的数值逻辑 | 平滑/微分/换算逻辑出现第二份拷贝 |
| GUI 里直接跑重计算 | UI 卡顿即违规 |
| 第三方格式当内部模型 | DLC/OpenCV 结构渗透出适配层 |
| 静默吞错 / 静默修复 | 出问题时无人知道发生了什么 |
| "显得高级"的复杂度 | 删掉它行为不变、可读性上升 |

---

## 17. 示例

### 17.1 命名 + 数据模型（Preferred）

```python
@dataclass(frozen=True)
class TrackPoint:
    """单帧单目标的观测，系统原子数据单元（data-model.md §3.5）。

    像素坐标系：原点左上，x 向右，y 向下。
    confidence 为 None 表示来源不提供（manual 恒 None），不是低置信度。
    """

    point_id: UUID
    track_id: UUID
    frame_index: int          # 0-based，指向源视频帧
    time_s: float             # 写入时由 Timeline 冻结
    pixel_x: float
    pixel_y: float
    source: str               # registries.sources 枚举
    confidence: float | None
    visibility: str           # "visible" | "occluded" | "unknown"
    quality_flags: list[str]
    status: str               # "active" | "superseded"
    superseded_by: UUID | None
    created_at: datetime
    modified_at: datetime
```

Avoid：`frameId: int`、`ts: float`、`x/y: float`（无空间前缀）、`conf: float`、`visible: bool`（丢失三态）、给 TrackPoint 加 `save()`/`to_dlc()` 方法（数据对象带服务职责）。

### 17.2 函数与错误处理（Preferred）

```python
def resolve_effective_point(
    points: list[TrackPoint], frame_index: int
) -> TrackPoint | None:
    """生效值解析（data-model.md §4.3）：manual 优先，其次最新引擎观测。

    返回 None 表示该帧缺测——调用方不得把它当作 (0, 0)。
    """
    active = [p for p in points if p.frame_index == frame_index and p.status == "active"]
    manual = [p for p in active if p.source == "manual"]
    if manual:
        return manual[0]
    if not active:
        return None
    return max(active, key=lambda p: p.created_at)
```

Avoid：返回 `(0.0, 0.0)` 占位、抛 `KeyError` 表达缺测、内嵌 `try/except` 掩盖输入错误。

### 17.3 数值代码（Preferred）

```python
# data-model.md §5.2：一步换算，禁止 t += 1/fps 增量累积（浮点漂移）
def frame_to_time(frame_index: int, timeline: Timeline) -> float:
    return frame_index / timeline.fps_nominal


def assert_times_close(t_a: float, t_b: float, fps: float) -> None:
    # 一帧的一半以内视为一致（加载复核阈值，data-model.md §5.7）
    assert abs(t_a - t_b) <= 0.5 / fps + 1e-6
```

Avoid：`time = row / fps`（行号当帧号）、`np.isclose(a, b)`（不写明 rtol/atol 就算"默认容差过关"）、`0.5` 直接出现在三处不同含义的地方。

### 17.4 路径与 IO（Preferred）

```python
def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    # Windows 文件锁：被打开的文件不可覆盖 → 临时文件 + 原子替换（ADR-0003 §5）
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
```

Avoid：`path + "/" + name`、`open(p)`（无 encoding）、原地 `write_text` 覆写。

---

## 18. 工具链

**当前状态**（2026-08-28）：仓库尚无代码与 lint/type 配置；`pyproject.toml` 于 Phase 1.1 建立。

**推荐**（Phase 1.1 落地时最终确认，不提前建复杂工具链）：

| 工具 | 用途 | 范围 |
| --- | --- | --- |
| `pytest` | 测试（已定，见 development.md §2 / phase1-requirements.md §5） | 全部 |
| `ruff` | lint + format（单工具替代 flake8/isort/black） | 全部；规则集保持默认偏严，逐步收紧 |
| `mypy` | 静态类型 | 领域层（`ai_physics_tracker.domain`）先行，其余逐步 |
| `pre-commit` | 可选，Phase 1 末再评估 | — |

工具配置进 `pyproject.toml`，规则与本文件冲突时**先改本文件再改配置**——文档是意图，工具是执行。

---

## 19. 变更与例外

- 本文件由任何 Agent/开发者提出修订；修订走 docs 提交（`docs: clarify error handling rule in CODE_STANDARD`），无需 ADR（它不是架构决策，是工程约定）。
- 例外必须有书面理由：在偏离处注释引用本文件哪一条、为什么偏离（例如某第三方 API 强制 camelCase 字段名）。
