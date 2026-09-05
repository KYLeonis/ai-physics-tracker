# 审查报告 — Phase 5.0–5.1 运行时健壮性与稳定性

> **性质**：独立全面审查报告（非 `docs/workflow.md` §6 定义的 Subphase Review Record）。
> 范围覆盖 5.0 与 5.1 两个 subphase 的横向运行时风险，供处置决策使用；
> 处置后可按需并入对应 Review Record 或移除。
> **审查日期**：2026-09-02 · **审查人**：ZCode Agent（Leonis 委托）
> **约束**：本报告只记录 findings，未修改任何产品代码。

---

## 1. 总体结论

**两个 subphase 的实现质量整体较高，无 Blocker 级遗留缺陷，可以放心继续 5.2。**
上轮 Review（5.0 F1–F2、5.1 F1–F7）的修复全部在位且有效；核心生命周期（spawn 子进程、
取消三级升级、原子落盘、文件篡改校验）设计严密。全库 495 项测试在当前 `main`（`3b02022`）通过。

本轮独立复核发现 **2 项 Medium、1 项 Low-Medium、3 项 Low** 问题，均不阻塞现有功能，
但其中 F1（选帧静默失败）在 Windows 目标平台上可能表现为"用户看不到任何错误"，建议在 5.2 开发前顺手修复。

## 2. 验证基线

| 项目 | 结果 |
| --- | --- |
| 工作区状态 | clean，`main` @ `3b02022`，与 `origin/main` 一致 |
| 全量测试 | `495 passed in 39.22s`（本地 macOS） |
| 文档一致性 | `docs/status/current.md`、roadmap、review 记录与仓库实际状态相符 |
| 审查范围 | `tracking_job.py`、`training_job.py`、`inference_job.py`、`dlc_adapter.py`、`engine_adapter.py`、`mock_engine_adapter.py`、`task_runner.py`、`tracking_actions.py`、`task_panel.py`、`main_window.py`（5.0/5.1 触及部分）、`pyproject.toml`、`domain/timeline.py` |

---

## 3. Findings

### F1 — 选帧抽帧不检查 `cap.isOpened()`，失败时静默返回空结果 【Medium】

- **位置**：`src/ai_physics_tracker/infrastructure/dlc_adapter.py:819`（`_extract_frame_features`）
- **现象**：`cv2.VideoCapture(str(request.video_path))` 打开失败（文件在校验后被移除、编解码不支持、
  **Windows 上路径含非 ASCII 字符**等）时不会抛错：每次 `cap.read()` 返回 `ret=False`，
  `frames_data` 为空 → `_kmeans_via_dlc` / `_kmeans_fallback` 返回 `[]` →
  `suggest_frames` 以正常 "completed" 状态返回空建议。
- **影响**：UI 显示 "Suggested 0 frame(s)"，用户无法区分"视频打不开"与"真的没有可建议帧"。
  结合目标平台是 Windows（物理实验视频路径常含中文），这是最可能被真实触发的静默失败路径。
- **对照**：项目自己的 `OpenCVVideoReader.open()`（`opencv_video_reader.py:55-56`）显式检查
  `isOpened()` 并报错；`export_annotations` 也校验回读帧号（`decoded.frame_index != point.frame_index`）。
  5.1 新路径没有沿用这两个既有防线。
- **次要风险**：`cap.set(CAP_PROP_POS_FRAMES)` 在个别后端会静默失败，随后 `read()` 解出的
  实际帧与请求帧号不一致——建议帧号与画面错位，用户双击跳转后可能标错帧。概率低但后果是数据质量问题。
- **建议**：
  1. 打开后立即检查 `cap.isOpened()`，失败抛 `RuntimeError`（GUI 已有兜底，会显示 "Failed: ..."）；
  2. 解码成功帧数为 0 时报错而非返回空结果；
  3. （可选）对 seek 路径抽验帧号回读一致性。

### F2 — 训练/推理与选帧的任务互斥不对称 【Medium】

- **位置**：`src/ai_physics_tracker/gui/tracking_actions.py:133`（`TrackingActions._start`）vs
  `tracking_actions.py:430`（`FrameSelectionActions.requestSuggestion`）
- **现象**：`requestSuggestion` 会检查 `trackingActions.pending` 拒绝并发；
  但反向不成立——`_start` 只检查自身 `pending` 和 `projectActions.busy`，
  选帧运行期间训练/推理按钮保持可用（`TrackingActions.refresh` 不感知选帧状态），用户可直接启动训练。
- **影响**：两个 spawn 子进程同时解码同一视频（1080p 训练 + 选帧并发），CPU/内存竞争，
  可能拖慢训练启动、造成内存压力。**无数据损坏**（选帧不写共享状态，结果目录按 UUID 隔离），
  属资源竞争与体验问题，非正确性问题。
- **建议**：`_start` 增加一行 `self.window.frameSelectionActions.busy` 检查（忽略请求并在状态栏说明即可），
  或在 `refresh()` 中把选帧忙碌纳入训练/推理按钮的禁用原因。

### F3 — 主 K-means 路径依赖未声明的 scikit-learn，且命名与实现不符 【Low-Medium】

- **位置**：`dlc_adapter.py:891`（`_kmeans_via_dlc` 中 `from sklearn.cluster import MiniBatchKMeans`）、`pyproject.toml`
- **现象**：`pyproject.toml` 只声明 `scipy`，没有 `scikit-learn`。sklearn 当前可用
  （venv 中 1.9.0），但它是 deeplabcut 的**传递依赖**。DLC 未来版本若不再依赖 sklearn，
  主路径 ImportError → 静默走 scipy fallback——功能保留（fallback 存在是好的），
  但聚类结果与 seed 语义会无声改变，用户不可感知。
- **命名问题**：`_kmeans_via_dlc` 及其 docstring（"调用 DLC 底层逻辑"、模块 docstring 提及
  `deeplabcut.FrameExtractor`）与实际实现不符——两条路径（sklearn / scipy）都不经过 DLC。
  会误导后续维护者去 DLC 源码里找这条链路。
- **建议**：二选一——把 `scikit-learn` 写入项目依赖（明确、可复现）；或保留传递依赖但在
  docstring 写明"依赖 DLC 传递引入"。同时把 `_kmeans_via_dlc` 改名为 `_kmeans_via_sklearn`
  并修正相关 docstring。

### F4 — 选帧无用户取消入口；取消结果措辞为 "Failed:" 【Low】

- **位置**：`task_panel.py`（建议帧控件组）、`tracking_actions.py:481-482`
- **现象**：训练/推理有 Cancel 按钮，选帧没有——取消只能靠切换 track/project 或关窗
  （F3 修复提供的守护路径）。5.1 性能优化后常规视频约 9 秒，但 4K/超长视频仍可能分钟级，
  期间用户无法主动停止。另外若 worker 优雅返回 cancelled 的 TaskResult 恰好在 reset 前被消费，
  UI 显示 "Failed: Frame selection cancelled"——取消被措辞为失败。
- **建议**：给建议帧组加取消按钮（复用 `handle.cancel()` 即可）；
  `_finish_error` 对 cancelled 场景使用中性措辞（不带 "Failed:"）。

### F5 — `detect_device()` 异常捕获写法冗余 【Low】

- **位置**：`dlc_adapter.py:52`：`except (ImportError, Exception): pass`
- **现象**：元组里的 `ImportError` 是 `Exception` 子类，整个表达式等价于 `except Exception`。
  行为无碍（探测失败回落 CPU 是预期），但写法暗示"只想捕获 ImportError"，误导读者。
- **建议**：直接写 `except Exception` 并加一行注释（探测不得让选帧/训练失败）。

### F6 — 算法下拉映射用脆弱启发式 【Low】

- **位置**：`task_panel.py:443`：`algorithm = "kmeans" if "k" in algo_text.lower() else "uniform"`
- **现象**：当前 "K-means"/"Uniform" 工作正常，但任何含字母 k 的新文案（如 "Quick uniform"）会被误判为 kmeans。
- **建议**：`QComboBox.addItem` 时用 itemData 存算法 ID，点击处读取 data 而非解析文本。

---

## 4. 上轮 Review 修复项复核（全部在位）

| 上轮 Finding | 复核结论 | 证据位置 |
| --- | --- | --- |
| 5.1-F1 `video.timeline` 属性错误 | ✅ 已改为从 `project.timelines` 查 `working_zone`，空/非法 zone 被 `FrameSelectionRequest.__post_init__` 拦截，GUI 捕获后显示 "Cannot start: ..." | `tracking_job.py:363-372`、`tracking_types.py:219` |
| 5.1-F2 K-means 吞取消异常 | ✅ `except CancelledError: raise` 在通用 `except Exception` 之前 | `dlc_adapter.py:879-880` |
| 5.1-F3 上下文切换不取消子进程 | ✅ `_onContextChanged` / `shutdown` 均调用 `_cancel_active_task`，`TaskHandle.cancel` 为 event→terminate→kill 三级升级 | `tracking_actions.py:514-520,529-535,562-568`、`task_runner.py:87-97` |
| 5.1-F4 `_poll` 不消费 IPC 错误 | ✅ `_poll` 读取 `poll_messages()` 并检查 `TaskResult.success/error` | `tracking_actions.py:470-486` |
| 5.1-F5 跳帧丢失标注模式 | ✅ `jumpToFrame` 在有选中 Track 且允许测量时恢复 `set_annotation_mode(True)`；跳帧经 `seekFrame` 钳位在 working zone 内 | `main_window.py:382-391` |
| 5.1-F6 永真断言测试 | ✅ 真实会话中断言 manual 点数与内容不变 | `tests/gui/test_frame_selection_actions.py` |
| 5.0-F1/F2 生命周期回归与文档 | ✅ 统一路径覆盖取消、迟到、篡改、unchanged-stat 等边界；三层协作措辞已在文档同步 | `tests/test_tracking_job.py`、`docs/architecture.md` |

## 5. 确认稳健、无需改动的部分

- **5.0 推理链路校验严密**：输入文件前后 stat 比对（含 st_ino）、帧数一致性
  （`row_count != frame_count` 拒绝）、计数守恒校验、`_project_path` 相对路径逃逸检查、
  观测交换文件原子写入。`_train` 中"模型已产出、评价失败单独记录"的处理语义正确。
- **原子落盘**：所有结果 JSON 走 `tmp + replace`，`allow_nan=False` 保证严格合法。
- **快照边界**：跨进程只传 frozen dataclass（Project 快照、UUID、Path、frozenset），无可变会话/Qt 对象越界；
  `_owned_session` 的授权注入有注释限定用途。
- **空/非法输入**：`prepare_frame_selection_request` 对缺 track/视频/timeline、文件缺失、
  非法 zone 均有明确错误；`n_frames` 由 spinbox（1–200）约束并在 dataclass 再校验。
- **孤儿进程权衡**：子进程 `daemon=False`（为 PyTorch DataLoader worker，Phase 4 既有决策），
  GUI 崩溃时选帧子进程会跑完并写完结果后自行退出。可接受，Phase 9 打包时复核即可。
- **语义差异（记录在案，非缺陷）**：选帧不要求 `can_measure` 时序授权——合理，
  选帧只读视频帧、不产出物理数据。

---

## 6. 处置建议优先级

| 优先级 | Finding | 建议时机 |
| --- | --- | --- |
| 建议尽快 | F1（isOpened + 零帧报错） | 5.2 开工前顺手修复（同文件、改动小） |
| 建议尽快 | F2（互斥不对称） | 5.2 开工前（一行守卫 + 一处 refresh） |
| 择机 | F3（依赖声明 + 改名） | 任意文档/依赖整理窗口；改名可并入 5.2 |
| 择机 | F4（取消入口与措辞） | 可并入 5.2 的 GUI 改动 |
| 随手 | F5、F6 | 下次触碰对应文件时一并处理 |

以上均为建议，**未经确认不实施任何修改**。

---

## 7. 处置记录（2026-09-02）

用户确认分两层处置，跟踪 Issue：[#18](https://github.com/KYLeonis/ai-physics-tracker/issues/18)。

**已修复（分支 `fix/p5.1-frame-selection-robustness`，5.2 开工前）**：

| Finding | 修复内容 | 验证 |
| --- | --- | --- |
| F1 | `_extract_frame_features` 打开后检查 `cap.isOpened()`，候选帧全部解码失败时抛 `RuntimeError`；`_kmeans_suggest` 对 `RuntimeError` 不再触发 scipy fallback（必然同样失败） | `test_dlc_adapter_kmeans_unopenable_video_raises` |
| F2 | `TrackingActions._start` 增加 `frameSelectionActions.busy` 守卫，拒绝时状态栏提示 "Cannot start: frame selection is running" | `test_frame_selection_running_blocks_training_start` |
| F3a | `pyproject.toml` 显式声明 `scikit-learn>=1.2,<2`（`n_init="auto"` 需 ≥1.2；原靠 deeplabcut 传递引入） | pip dry-run 安装校验 |
| F5 | `detect_device` 改为 `except Exception` 并注释"探测失败回落 CPU" | 既有 device 测试 |

全量回归 **497 passed**（原 495 + 新增 2），`python -m compileall src scripts` 通过。

**顺带项（记录于 `docs/status/phase-5.2-plan.md` §Deferred Findings）**：

- F3b ✅ 已随 5.2 Slice 3 完成（`_kmeans_via_sklearn` 改名 + docstring 修正）。
- F4 ✅ 已随 5.3 完成：选帧/挖掘获得中性取消（`_finish_cancelled`，无 Failed 前缀）与取消入口。
- F6 ✅ 已随 5.3 完成：算法下拉改用 `currentData()` 显式映射。

