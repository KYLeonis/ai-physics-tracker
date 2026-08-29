# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-29

---

## Current Phase

**Phase 2 — Video Analysis MVP** 🔄 进行中

## Current Subphase

**2.1 — Desktop Video Foundation** ✅ 已完成（Issue #2 已关闭，merge `7da0af1` → main，CI 双平台全绿）。Phase 2 下一个 subphase 待启动。

## Current Slice

无（2.1 已收尾，等待 Phase 2.2 指令）

## Current Goal

从命令行启动桌面窗口，打开 CFR 视频并完成首帧显示、上一/下一与帧号跳转；保持 GUI/application/OpenCV 分层。

## Recently Completed

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

**Blockers**：无。

## Next Recommended Action

Phase 2.2 候选主题（按 roadmap Phase 2 交付物顺序）：① 连续播放/暂停 + 时间轴（含 VFR 显式拒绝的 UI 呈现）；② 视频画面缩放/平移；③ 手工标记（点选添加轨迹点）。等待用户选择或调整范围划分后，按 `docs/workflow.md` §3 建 Issue + mini-plan 启动。
