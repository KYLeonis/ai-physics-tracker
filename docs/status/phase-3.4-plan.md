# Subphase Plan — Phase 3.4 Integration & Phase Close

- 日期 / 状态：2026-08-31 · **Draft，等待确认；未开始实现或真人验收**。
- 基线：`main` / `162017e`，进入时工作区干净，`main` 与本地 `origin/main` 一致。
- 前置交付：3.3 merge `51c1cce`，[Issue #9](https://github.com/KYLeonis/ai-physics-tracker/issues/9)
  已关闭，current/Issue 记录 Human Review 5 轮通过。
- Issue：确认计划后创建或复用；计划分支 `feat/p3.4-integration-acceptance`，尚未创建。
- 规划基线验证：**303 passed**，`pip check` 通过；这是已有版本基线，不代表 3.4 验收完成。

## Goal

证明标定、手工标注、运动学计算、图表与保存恢复能在同一个实验项目中正确协作，
补齐 Phase 3 的可追溯验收证据，满足关卡后收尾并停止，不直接进入 Phase 4。

## Scope

**做**：

- 逐项核对 Phase 3 的 R1–R9、AC-1…AC-10 与完成定义，区分已有证据、待验证及真实缺口。
- 复用已有单元/GUI 回归，仅补缺失的组合测试，优先下述三个端到端场景。
- 对阻断既定闭环的数据丢失、单位/时间错误、状态失效、取消/保存竞态做必要的小范围修复。
  先补能失败的回归；若发现需求尚未实现或需要裁剪验收标准，先报告用户，不自行改标准。
- 将 3.3 HR 中已交付的多选轨迹 overlay、当前标注目标、帮助气泡、Save PNG 纳入回归，
  不重做已通过的交互设计。PNG 只验当前图表快照，不扩大为 Phase 8 的科学导出系统。
- 组织一轮真实实验项目的整体 Human Review；核对 Windows 真机遗留与 Phase 收尾关卡。
- 补齐文档/ADR 的已批准变更记录，最后将每条验收结论绑定到测试、commit、CI 或用户反馈。

**不做**：

- 不新增图表、跟踪算法、拟合/误差分析、插值、替代滤波器、标定模型、数据编辑器或安装包。
- 不新增 CSV/Excel/PDF/矢量/批量导出；不把现有 PNG 称为可复现的科学数据导出。
- 不升级依赖、改变 schema/原始时间、迁移历史点，不调整 CFR/near-CFR 授权预算。
- 不自动删除、移动、覆盖真实实验媒体；破坏性失败场景只用测试生成的数据和临时目录。
- 不使用 computer-use 或截图自检替代 Human Review；本轮规划不执行 GUI 验收或修改 CI。

## 前置事实与文档缺口

1. 3.3 已收尾，不再重复要求其单独 HR。已核实 [CI run 33353856199](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33353856199)
   对应 `51c1cce` / `main`，macOS 与 Windows Python 3.11 jobs 均成功。
   该记录是 3.3 的证据，不能替代未来 3.4 交付提交的 CI。
2. 本机 Python 3.12.13 / NumPy 2.4.6 / SciPy 1.17.1 / PySide6-Essentials 6.11.2 /
   PyQtGraph 0.13.7，依赖与现有锁定版本一致；本轮未安装或升级依赖。
3. `current.md` 部分段落、README/AGENTS/roadmap 横幅及 3.3 本地计划仍留着“待 HR/CI”。
   本次只订正这些阶段状态；Phase 3 AC 最终勾选留待 3.4 按证据逐项完成。
4. 3.3 HR 的 PNG 交付（`71a33fe`，合入 `eed7974`）与 ADR-0009 D1 的“不引入导出”
   及早期 spec/计划排除项不一致。确认后在 Slice 1 补 ADR-0010，**仅记录已有 HR 决定**，
   部分取代该排除条款；不重写 Accepted ADR 正文、不借机扩展导出范围。
5. 303 项通过不代表所有断言充分。盘点发现 PNG 取消分支有 `or True` 恒真断言；
   多选 overlay 测试未同时给两条轨迹写点，PNG 写出测试未装载真实图表数据。这些是补测目标。

## 三个优先集成场景

### E1：同一实验项目的完整闭环

打开合成 CFR 视频 → 创建比例尺、原点/旋转 → 连续标注 → GUI 触发后台 Recompute →
查看五图 → 保存到新目录 → 关闭并通过 Open project 重开。

- 验证 Project/Video/Track/Point/Calibration ID、raw 像素与冻结时间不变；
  四类 DerivedData 的 `frames/values/unit/pipeline/calibration_ref/timing_context` 往返一致。
- 图表单位、数据和保存帧恢复；重开保持暂停/clean，不因浏览令 dirty 改变。
- 图表时间仍为源视频绝对时间，覆盖非零 working zone；数值精度用解析合成数据证明，
  不凭真实单摆曲线“看起来平滑”判定精度。

### E2：解释条件改变后的 stale→valid

已有结果 → 在 GUI 修改原点/旋转或切换标定 → 图表提示 stale → 修改 SG 参数并重算 →
显示新的 valid 结果 → Undo/Redo → 保存重开。

- 验证旧结果不会继续被称作当前有效结果，重算使用正确标定和实际 SG 参数/单位；
  raw 不改写，缺测不跨段连线，短段按 ADR-0008 处理。
- 复用已有取消/输入变更/保存/切换竞态测试，不另建任务框架；检查拼接后仍无部分提交。
- 重开后的 near-CFR 授权不能永久复用；unknown/拒绝授权不能通过重算按钮绕过门禁，
  保存的缓存仍可只读查看。需要时补一个已有场景的分支，不扩展时间模型。

### E3：两条有数据的轨迹与当前图表 PNG

两条 Track 各有多个点 → 视频列表多选同屏显示 → 明确 currentItem 标注目标 →
图表勾选叠加 → 切换当前 tab → Save PNG 到测试临时目录。

- 分别断言两条轨迹的点、颜色、当前帧高亮，新增标记只落到当前标注目标。
  视频列表选择与图表勾选按现有设计操作，不强加新的同步或持久化规则。
- PNG 非空、可解码且来自所选图表，不只是验证扩展名；取消前后文件清单不变，
  写入失败有提示且项目/图表状态不被破坏。所有文件仅为测试资产，不覆盖用户输出。
- PNG 是显示快照；检查单位/图例/过期标识的可见性并记录近似时序提示的导出局限，
  若发现可能误导结论的缺陷先报告，不默认增加水印、布局或新导出参数。

## Phase 3 验收证据索引（不是本轮完成勾选）

| AC | 已有自动化入口 | 3.4 补充核对 |
| --- | --- | --- |
| 1–2 | `tests/gui/test_calibration_ui.py` 的 draw scale / origin / rotation；`test_video_view.py` overlay | E1 实际对话框输入、标定与标注模式切换；真人观感 |
| 3 | `tests/test_kinematics.py::test_batch_pixel_to_world_ac3`；`tests/test_calibration.py` round-trip | 保持 <1e-9 合成精度，串到 E1 的实际单位 |
| 4 | `test_kinematics.py::test_smooth_uniform_velocity_ac4` | 保持速度误差 <0.01；不放宽容差 |
| 5 | `test_kinematics.py::test_smooth_uniform_acceleration_ac5` | 保持加速度误差 <0.05；不放宽容差 |
| 6 | `test_kinematics.py::test_nan_gap_no_bridging_ac6` / `test_short_segment_window_shrink_ac6` | E2 的图表断线/空态，不能把缺测补成零 |
| 7–8 | `tests/gui/test_charts.py`；`test_chart_request_identity.py`；`tests/test_chart_data.py` | E1/E3 五图、双轨迹、呈现/请求帧分离；整体 HR |
| 9 | `tests/test_kinematics_session.py::test_pipeline_serialization_roundtrip_ac9` | E1 GUI 保存/重开全字段核对 |
| 10 | `test_kinematics_session.py::test_stale_on_calibration_change_ac10`；`tests/test_kinematics_job.py` 首次标定 | E2 GUI 改标定→警告→重算→刷新→历史恢复 |

详细结果在本计划 Result 记录：AC 编号、状态、测试 node id、验证 commit/环境、
CI run/job 链接、Human Review 日期/反馈。总测试数量不是单项验收证据。

## Acceptance Criteria（3.4 完成判定）

- [ ] P34-1：Phase 3 AC-1…AC-10 均有可追溯证据；R1–R9 的偏差明确说明，不擅自裁剪。
- [ ] P34-2：E1/E2/E3 的必要组合回归通过，无恒真/空转断言；不降低原有容差或跳过关键测试。
- [ ] P34-3：同一个真实实验项目的整体 Human Review 通过，记录使用的版本与媒体类型。
- [ ] P34-4：交付提交的本地验证与 macOS/Windows Python 3.11 CI 通过；Windows 真机事项
  按下节处理，CI 与真机结论分开记录。
- [ ] P34-5：spec/roadmap/README/AGENTS/current/相关 ADR 与实际交付一致；获准后合并、
  关闭 Issue 并 push。Phase 3 状态只在所有必要关卡满足后改为 Completed，然后停止。

## Windows 与暂停边界

- 3.3 CI 全绿不是 Windows 真机验收。Phase 2 延后事项继续保留，Slice 1 对照原记录
  核清范围（含 MP4/H.264 全流程及 HEVC 兼容性记录），不凭“2 项”自行注销遗留。
- `docs/development.md` §1.1 要求涉及 GUI/视频的 Phase 收尾验证 Windows；默认把
  Windows x64 上的完整闭环、DPI/帮助气泡、PNG/中文路径冒烟列入本次收尾关卡。
  不引入安装包/CUDA 验收，HEVC 结果如实记录，不把所有编码都可用新增为硬指标。
- 现在没有 Windows 反馈不阻止本轮规划或先做自动化/macOS 验收；**不能因此直接宣称
  Phase 3 全平台验收完成**。若希望继续延期并先收尾，需要用户明确确认例外和后续节点，
  Phase 2 先前的延期不自动扩展成 Phase 3 的永久豁免。
- 新依赖、格式变更、范围/验收标准变更及 CI 配置改动另行请求确认；git push 另行授权。

## Slices

- [ ] Slice 1：确认范围，建立 Issue/工作分支；整理 AC 证据表、核清 Windows 遗留，
  补记 PNG 的 ADR/spec 例外及 3.3 HR 行为文档，不改 Accepted ADR 正文。
- [ ] Slice 2：补 E1/E2/E3 中缺少的自动化组合测试，替换失效断言；发现阻断缺陷才做
  对应最小修复，并运行相关测试与全回归。无新缺陷则不为收尾制造实现改动。
- [ ] Slice 3：必要的独立 Luna-max review → 整体 Human Review；若有代码修复，
  review 必须覆盖修复范围。发起 HR 后停止等反馈，失败则修复/复验，不提前合并。
- [ ] Slice 4：验收通过并处理 Windows 条件后，请求 push 授权验证交付提交 CI；
  合并与文档收尾、关闭 Issue、推送并检查结果；停止，不自行启动 Phase 4。

## Relevant Context

- `AGENTS.md` §6–§11，`CODE_STANDARD.md`，`docs/workflow.md` §3/§5.1/§8/§11。
- `docs/roadmap.md` Phase 3，`docs/spec/phase3-requirements.md` R1–R9 / AC-1…AC-10 / DoD。
- `docs/spec/data-model.md` §3.8/§5/§6；`docs/spec/project-format.md`；ADR-0007/0008/0009。
- `docs/status/phase-3.3-plan.md` 收尾补记及 Issue #9；`docs/development.md` §1.1/§5。
- 若涉及对应修复，先读 `docs/research/open-source-project-map.md` §6/§7 与其路由的
  Tracker/TrackLab 时间、标定、图表参考；不复制上游受限源码。

## Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m pip check`、安装版本核对、`git diff --check`。
- 测试放已有 `tests/` / `tests/gui/`，合成数据与产物只使用临时目录；不提交视频、PNG
  输出或用户实验项目。功能修复前重读 CODE_STANDARD 与相关 research/spec。
- 不修改现有 CI YAML；CI 读取 commit、run、两个 job 的结果，不把旧 run 代替新交付。

### 计划中的 Human Review（本轮不开始，准备完成后再发起）

在仓库运行 `.venv/bin/python -m ai_physics_tracker`；Windows 从零命令见
`docs/development.md` §5。使用一个新建的验收项目，保留原视频只读；优先单摆素材。

1. 打开视频并确认时序状态，设置比例尺/单位/原点/旋转，连续标注至少 9 帧 →
   标定与标注模式清晰切换；原点和轴方向正确。
2. 勾选并 Recompute，切换五图，播放/逐帧/图表反向定位 → 单位正确、画面与游标一致。
3. 修改标定并查看旧图，再调整 SG/重算、Undo/Redo → stale/valid 与参数同步，缺测仍断开。
4. 两条有点轨迹多选同屏，切换标注目标并查看 ? 帮助，切换图表后 Save PNG →
   新点目标正确，图像对应当前图表；取消导出不新增文件。
5. 保存新项目、关闭、重开，尝试未保存切换后 Cancel → 原始/派生数据和标定不丢失、
   初始暂停；近似时序重新确认，不能自动复用测量授权。

以上按 macOS/Windows 分别记录是/否和版本；已通过的 3.3 单项 HR 作为前置证据保留，
本轮只验证完整工作链，遇到问题再复测相关单项。

## Result（执行后填写）

- 本轮只完成规划、只读盘点与基线验证；未创建 3.4 Issue/分支、未改代码/测试/依赖/CI，未 push。
- 规划基线：303 tests passed；依赖检查通过；3.3 CI run 的两平台结果已只读核实。
- 3.4 AC / HR / Windows / 交付 CI / 合并：**均未开始或尚待验证**，不提前勾选。
- 下一步：用户确认计划后从 Slice 1 开始；Windows 若需延期，单独明确例外，不默认批准。
