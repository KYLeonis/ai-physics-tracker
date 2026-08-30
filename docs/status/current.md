# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-30（Phase 2.4 Human Review 反馈修复：已授权实现到下一轮 HR）

---

## Current Phase

**Phase 2 — Video Analysis MVP** 🔄 进行中

## Current Subphase

**2.4 — Project Workflow & Phase Close** 🔄 Human Review 反馈修复/验证中；[Issue #5](https://github.com/KYLeonis/ai-physics-tracker/issues/5)，分支 `feat/p2.4-project-workflow`；计划见 [phase-2.4-plan.md](phase-2.4-plan.md)。用户已授权修复到下一轮 HR，尚未授权 push。

上一 Subphase 2.3 已完成（Issue #4 已关闭，merge `3967f6a`/`38eaa39`，CI 双平台全绿，Human Review 2 轮通过）。

## Current Slice

Slice 6：首帧预览/后台验证已接通，正在完成 packet 快路径、near-CFR 显式确认及独立回归/复审。

## Current Goal

实现项目生命周期、未保存修改保护、持久化 Timeline 恢复、视频 relink 与 CFR/VFR 验证。Phase 2 最终收尾必须通过用户 Human Review（含 Windows 真机）。

## Recently Completed

- **Phase 2.4 本地增量（待 HR/CI）**：Project 首存/另存/加载/重连、Save/Discard/Cancel 保护；候选会话后台准备与取消；保留持久化 Timeline/ID、视图状态；dirty 与保存基线比较；unknown/VFR 媒体可保存浏览引用但不能新增测量；FFprobe 完整时间戳验证及固定来源工具取得脚本；Luna-max review 两个 Blocker（preview 丢引用、未来 workflow 版本降级）已修复。最新功能提交 `2a139ce`。
- **Phase 2.3 — Manual Annotation**（2026-08-30）：ProjectSession（application，ProjectRepositoryPort 协议 + 组合根注入）；Track 面板（创建/删除/选择、自动命名与调色板）；标注模式（选中即标记、Esc/列表空白退出，D1=A/D2=确认）；点击落点（mapScreenToPixel、呈现帧为唯一落帧来源、在途拒绝）；overlay 拖尾显示（当前帧实心高亮、屏幕固定大小、全缩放锚定）；manual 语义（time_s 冻结、visibility=visible、同帧 last-wins 硬删旧点）；独立 review 4 Blocker 全部修复（visibility、落帧时序、marker 锚点、空转测试）；**HR 反馈修复**：十字光标稳定（item 级 cursor，修 QGraphicsScene hover 覆盖）、快照式 Undo/Redo（按钮+⌘Z/⇧⌘Z、完整恢复被 last-wins 替换的旧点、撤销删除后恢复选择、save 清栈）；本地 124 tests
- **Phase 2.2 — Playback & Viewport**（2026-08-29）：AsyncVideoSession（单线程串行 reader、latest-wins 解码合并、跨视频代际隔离）；播放控制（QTimer 节流、末帧自动暂停、空格/按钮、0.25–4× 倍速）；时间轴 scrub/commit；VideoView 重写为 QGraphicsView（pinch 手势缩放、拖拽平移、Fit/100%/200%/400% 档位、`mapScreenToPixel` ±0.5px）；**顺序解码 fast path（1080p H.264 从 33.3ms/帧降至 11.8ms/帧，根因修复卡顿）**；解码支持矩阵实测入库（development.md）；Human Review 5 轮通过（含 pinch 手势投递修复、`scripts/diagnose_pinch.py` 探针），本地 100 tests + CI 全绿
- **注释语言规范**（2026-08-29）：CODE_STANDARD.md §12 规定注释/docstring 一律中文（标识符、spec 引用、API 名保留英文）；存量 34 个文件的英文 docstring/注释全部改写为中文，AST 对比确认代码逻辑零改动，70 tests 全绿（commit `1b5e303`）

- **Phase 2.1 — Desktop Video Foundation**（2026-08-29）：ADR-0005；PySide6/OpenCV headless/NumPy 2.4.6 依赖；Qt-free VideoReader/VideoSession；桌面入口、视频显示、前后步进/帧号跳转；本地 70 tests + CI macOS/Windows Python 3.11 全绿（run 33256154612）；Luna-max 独立 review 无 Blocker；Issue #2 已关闭，merge `7da0af1`
  - 过程订正：初版锁定 `numpy==2.5.2` 无 Python 3.11 wheel，CI 安装阶段双平台失败；`47758ae` 改锁 2.4.6（3.11/3.12 兼容最新版），ADR-0005/development.md 同步
- **Phase 1 — Project & Data Foundation**（2026-08-29）：src-layout + 锁定依赖；Project/Video/Timeline/Track/TrackPoint/Calibration/DerivedData；TrackStore first-wins/manual last-wins/superseded 恢复语义；可逆标定与 stale 传播；schema v1 JSON repository、迁移守卫、原子保存/滚动备份、Save As、external locator/relink；56 项 pytest 本地与 GitHub Actions macOS/Windows Python 3.11 全绿；独立 review 最终通过
- **ADR-0004**（2026-08-29）：外部视频使用 `file_path = null` + 绝对 `original_path`，项目内视频使用 Windows-safe 相对路径；部分取代 ADR-0003 的 locator 条款
- **代码规范建立**（2026-08-28）：`CODE_STANDARD.md`（根目录）——领域词汇表命名、分层依赖、typing、错误处理语义、数值代码纪律（时间/坐标/容差）、跨平台规则、测试风格、反模式与示例；已加入 Agent 进入协议（AGENTS.md §6 / workflow.md §11）
- **Subphase 1.0 — Phase 1 Spec & Requirements**（2026-08-28）：`docs/spec/data-model.md`（领域模型/时间语义/标定/最小接口）、`docs/spec/project-format.md` + **ADR-0003**（JSON 清单优先持久化）、`docs/spec/phase1-requirements.md`（AC-1…AC-10，含 DLC 无损转换设计）；`docs/research/software-spec-plan.md` §5 Readiness Criteria 全部勾选，PLAN 转 Closed
- **Phase 0 — Project Initialization**（2026-08-27）：仓库结构、基础文档、Git/GitHub 初始化 ✅
- 开源生态调研：project map + 14 份 raw notes（`docs/research/`）
- 跨平台开发模式确定：macOS 开发 → Windows 发布（`docs/development.md` §1.1）
- 软件规范设计准备计划收敛为 v2（`docs/research/software-spec-plan.md`）
- 开发工作流体系建立（`docs/workflow.md` + `docs/status/` + `docs/templates/`，2026-08-28）

## Current Decisions / Blockers

**已定决策**

- Python 3.11（ADR-0002）
- 持久化格式：**JSON 清单优先混合方案**（ADR-0003）——`project.json` 单文件 + 引擎输出外置 `data/engines/`，`schema_version` + 迁移链，原子写入 + 滚动备份
- 外部视频 locator：`file_path = null` + 绝对 `original_path`；项目内视频使用 Windows-safe 相对路径（ADR-0004，部分取代 ADR-0003 Decision 4）
- Phase 2 GUI/视频栈：PySide6-Essentials 6.11.2 + OpenCV headless 4.14.0.94 + NumPy 2.4.6（Python 3.11–3.12 compatible）；Qt-free application contract（ADR-0005）
- 数据模型核心结论（`docs/spec/data-model.md`）：帧号 0-based、CFR（VFR 显式拒绝）、raw 只存像素坐标、手工修正遮蔽 AI 预测不覆盖（superseded 链）、confidence 与 visibility 分立、source 开放注册表、标定变更仅派生层失效、裁剪不重置时间基准
- Phase 1 前的设计只到字段级建议，**不写 Python class**（自 Phase 1.1 起）
- 数值微分/平滑方法 → Phase 3 前出 ADR

**本轮决策**：ADR-0006 确定候选项目提交与 FFprobe 时序关卡；CI 工具使用固定 ffmpeg-static b6.1.1 及 SHA-256 校验，不改系统 PATH。

**验证状态**：规划基线 124 tests → 当前 **173 passed**；本机 FFprobe 和 CI 固定来源 macOS 二进制均验证；compileall/pip check/diff check 通过；Luna-max 最终 Verdict：通过。远端 CI、Windows 工具执行与 Human Review 尚未完成，不声称 Phase 2 已收尾。

**用户未提交修改**：`.github/workflows/README.md`，本次未改动、未纳入提交。

**Human Review 诊断（2026-08-30）**：当前打开的 `P001.mp4` 为 1920×1080 HEVC，
约 110.88 s、3326 帧、250 MB。首帧 0.140 s；全部 packet PTS 扫描 0.264 s；当前
`-show_frames` 全解码验证 91.906 s。完整帧 PTS 与排序后的 packet PTS 完全相同。
时间基 1/90000，间隔 3000 ticks 共 3224 次、3010 ticks 共 101 次；当前 30 FPS + 1 tick
容差规则返回 `vfr_suspected`，从而禁用 Add track。以容器平均 FPS 29.9969636 为参考，
固定时间网格最大偏差约 0.17014 ms；与严格 30 FPS 比则累计偏差 11.2222 ms。
结论：全量解码被放在首屏之前是长等待根因；按钮禁用是严格时序判定的结果，不是 Qt 点击失效。
不能据此把视频称为严格 CFR，也不能直接放开按钮；需明确近似恒定帧率的误差预算/用户确认策略。

## Next Recommended Action

完成 ADR-0007 修复的全回归与独立复审，记录 P001 只读复测结果、本地提交，
发起下一轮 Human Review 后停止。通过后才处理 push 授权/双平台 CI/合并。
保留用户 `experiment/` 与 `.github/workflows/README.md`，不纳入 Git。
