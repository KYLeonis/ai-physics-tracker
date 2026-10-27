# Review Record — Phase 6.5 P011 S0/S1 Preparation Checkpoint

- Subphase / Issue：P6.5 integrated pendulum acceptance / #44
- Review 范围（commits / 分支 / 文件）：`feat/p6.5-pendulum-acceptance`，基线 `7abd517..844a5cb`；另纳入本轮工作区中 `scripts/prepare_p65_acceptance.py` 与 `tests/test_prepare_p65_acceptance.py` 的未提交差异（仅 workflow 视频状态键及对应断言）。本地忽略目录 `experiment/p65-acceptance/2026-10-27-run1/` 的协议、结果和两个项目作为真实证据核查对象。
- Context（spec / ADR / plan 路径）：`docs/status/phase-6.5-plan.md`、`docs/notes/phase-6.3-reference-preparation.md`、ADR-0017、ADR-0019、ADR-0020、ADR-0021、ADR-0024、ADR-0028、ADR-0029、`docs/templates/review.md`。
- 轮次：R1 2026-10-27（首轮、S0/S1 checkpoint）· R2 2026-10-27（修复复审、S0/S1 checkpoint）· R3 2026-10-27（F2文档修复复审、S0/S1 checkpoint）

## Checklist

**正确性**

- [x] 本轮 S0/S1 行为与冻结计划一致；S2 真实人工标注 / 新 AI 任务及完整 Phase Gate 仍未完成。
- [x] 检查当前工作区代码的输入指纹拒绝、输出不覆盖、时序授权、来源区分、双周期比较、保存重开、图表构建和空白新工程行为；详见下方证据。
- [x] 拟合和周期数值逻辑有合成数据回归；本轮另核对真实 P011 结果。

**质量**

- [x] 提交范围集中于状态 / 脚本说明、准备脚本和定向测试；工作区差异仅修正新工程 workflow 的视频状态键并补断言。
- [x] 路径使用 `pathlib`，JSON 显式 UTF-8；未发现与本机输入路径之外的跨平台问题。
- [x] 脚本 CLI 和数据用途见 `scripts/README.md`；workflow 状态键遵循 `ProjectMediaService.open_project()` 读取的 `video_id` 契约。
- [x] 修复后入口级冻结协议指纹拒绝会阻止输出创建，并保留原文件（F1，R2复审）。

**流程**

- [x] 本范围提交信息符合 Conventional Commits。
- [x] 本次只复用既有应用计算、时序授权和 ProjectRepository 接口；未引入公共契约或依赖变化，无新增 ADR 需要。

## Findings

### F1 — 准备流程的测试没有经过冻结输入校验失败路径

- **Severity**：Suggestion
- **Evidence**：`tests/test_prepare_p65_acceptance.py:59-66` 先在 `tmp_path` 写入 `keep.json`，再把同一个已存在的 `tmp_path` 作为 `prepare()` 输出目录传入。`prepare()` 在 `scripts/prepare_p65_acceptance.py:175-178` 先因 `output.exists()` 抛出 `FileExistsError`，因此该调用既未读取 `missing-reference`，也未到达 `reference_files()`。随后测试只直接调用 `verified_file()` 验证哈希不匹配。测试标题中的“modified reference”目前没有通过完整 `prepare()` 路径验证。
- **Impact**：现有实现按正确顺序先核验输入再创建输出，本次真实运行也独立复核了协议列出的 9 个输入指纹全部匹配；但如果以后把集成流程中的指纹核验移到输出创建之后或误删，当前回归不会发现输出目录已经被创建这一违约。
- **Recommendation**：补一个非既有输出目录的 `prepare()` 集成测试，让冻结输入校验失败，并断言输出目录未创建、参考文件未改动。可用临时冻结资料和最小替身，不需复制真实媒体。
- **Decision**：Fix Now — 让入口级测试实际走到冻结协议指纹拒绝，且断言新输出目录没有创建、原文件保持；与本次不覆盖约束直接对应。
- **Fix commit**：`966eea7`
- **Verification**：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_prepare_p65_acceptance.py tests/gui/test_guided_representative_annotation.py`：8 passed（5.54s）；UI键也已改为`video_id`并验证选择恢复。最终真实运行另存`experiment/p65-acceptance/2026-10-27-final/`，不覆盖R1原run1。
- **Re-review**：R2 — 新的非既有输出目录下调用完整`prepare()`；冻结协议指纹不匹配时由`reference_files()`拒绝，输出目录仍未创建、协议文件内容保持，定向测试通过。
- **Status**：Closed

### F2 — checkpoint报告把待用户完成的20帧标注写成已完成

- **Severity**：Blocker
- **Evidence**：`docs/benchmarks/phase-6.5-pendulum-report.md:65-66`写“用户亲自在20个……帧标注”并已Keep 4个固定检查帧；但最终`manual-project/project.json`仍有0条observations、0条derived、0个tracking_runs，`docs/notes/phase-6.5-annotation-handoff.md:22-27`和`docs/status/current.md:18`仍要求用户先完成标注，训练计数为0 / 2。
- **Impact**：报告会让后续读者误以为用户标注及检查集步骤已完成，与真实工程和交接状态冲突。
- **Recommendation**：将该句改为待办状态，明确20帧标注和Keep 4个固定检查帧尚未发生；保留0 / 2训练状态。
- **Decision**：Fix Now — 将报告改为明确的待办状态，说明20帧标注和4个固定检查帧尚未完成，真实训练启动仍为0 / 2；不改科学参数或工程产物。
- **Fix commit**：`40028c4`
- **Verification**：最终报告明确20帧标注尚未完成、4个固定检查帧尚未建立，训练启动0 / 2；只读`manual-project/project.json`确认`observations`、`derived`、`tracking_runs`均为空。标注交接要求用户完成并保存20帧，后续再Keep 4个检查帧；`current.md`仍将S2列为等待用户标注。各处状态一致。
- **Re-review**：R3 — 核对`40028c4`中的报告、交接及当前状态修订；与最终manual工程JSON逐项对应，未运行GUI、训练、推理或重算。
- **Status**：Closed

## Review Log

### R1 — 2026-10-27 · 首轮

- **范围 / 基线**：指定提交 `7abd517..844a5cb`，并按主 Agent 要求纳入准备脚本 / 测试的当前未提交 workflow 键修正；仅核对 S0/S1，不运行训练或推理，不修改用户工程或冻结参考。
- **结论**：本轮 S0/S1 准备实现与真实产物可阶段性 Approve，F1 为一项非阻断测试覆盖建议。该结论不代表 P6.5 或 Phase 6 完成；S2 真实新 AI 任务、用户标注和 S3 完整 Gate 均未完成。
- **Findings 变化**：新增 F1；无关闭项。
- **只读证据核查**：`protocol.json` 记录源码提交 `844a5cbc9ae82d6df70246a71bc4e22fb24f152e`，其 preparation script SHA256 与该提交中的脚本匹配；另有 Python 3.12.13、macOS arm64、关键依赖版本和实测 `near_cfr` TimingReport。独立重算协议记录的 9 个输入指纹，均存在且匹配；本地源文件未改。时序以实测报告通过既有 `confirm_video_timing` / `accept_approximate_timing(..., automatic=True)` 应用入口授权。
- **科学结果**：旧参考项目保留 600 条有限 `dlc` 观察；本轮分析用未平滑 `theta`、闭区间帧 `[0,214]` 共 215 个样本。拟合状态为 `success`，`T=1.0424072115 s`，相对人工参考 `1.0389815000 s` 为 `0.32972%`；重复间隔保留 7 个事件 / 全部 6 个间隔，均值 `1.0412668440 s`，相对差 `0.21996%`。两项分别低于冻结的 5% 门槛。产物明确披露 DLC 不等于人工逐帧真值、同视频参考不是独立校时、局部参数区间不覆盖系统误差或证明模型适用。
- **保存 / 图表 / 新工程**：脚本实际保存并重载分析项目，`save_reload_equal=true`；从重载项目构建的 `theta_t`、`omega_t`、`alpha_t`、`theta_omega` 四种图表均为 valid，各有 600 点且单位匹配。新工程保存后有 0 条观察、0 条派生数据、0 个 tracking run，保留一条 active calibration（用户给定比例尺、支点与旋转），当前训练启动计数为 0。run1 是修正 workflow 键之前产生的产物，内含 `selected_video_id`；本轮工作区差异已改为应用读取的 `video_id` 并增加断言。由于该工程仅有一个视频，旧产物由既有“选择首个视频”回退仍能打开；run1 的协议保留了旧脚本指纹，本轮未改写它。
- **测试 / 检查**：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_prepare_p65_acceptance.py -q`：3 passed；`git diff --check` 通过。没有运行训练、推理或真实数据重算。

### R2 — 2026-10-27 · 修复复审（S0/S1 checkpoint）

- **范围 / 基线**：修复提交`844a5cb..966eea7`；核对`experiment/p65-acceptance/2026-10-27-final/`中的`protocol.json`、`reference-result.json`、reference / manual两个`project.json`及启动器，并审查新增分析报告、标注交接；此前R1范围保持不变。
- **结论**：F1已关闭；准备脚本、最终真实旧DLC分析产物、空白新工程与`video_id`恢复键符合S0/S1冻结要求。阶段性Verdict为：**S0/S1技术与产物核查通过；checkpoint文档因F2 Blocker暂不通过**，须更正待办标注状态后才能作为准确交接记录。S2新AI线、最终HR及S3 / Phase Gate仍未完成，Final Verdict保持待填。
- **Findings变化**：关闭F1；新增F2（Open）。
- **修复复审**：新增入口测试用未存在的输出目录调用完整`prepare()`，伪造的冻结协议在指纹核验处失败，断言输出不存在、协议原文未变；旧输出拒绝断言仍保留。`ProjectMediaService.open_project()`按`ui_state.workflow.video_id`选视频，帧恢复也检查同一键；新工程实际持久化的`video_id`和`selected_track_id`均匹配对应project对象。没有仅凭单视频回退推断修复有效。
- **产物 / 科学核查**：协议记录`source_commit=966eea7c4317fad2b5c70a877bc612efd9df2330`，与HEAD一致；记录的准备脚本SHA256`026621b2ecc9b3e5f223aefa3d71d9d13de52ea56b0b769cc7dd70369a5b10f1`与工作区及该提交脚本一致。运行协议中的9项原始输入指纹逐项重算均匹配。协议公式、初值、无界非固定参数、1000次求值预算、5%分别比较门槛及Restart / 50 epochs / batch 8 / auto、20帧 / 4检查帧配置与冻结计划一致。
- **结果 / 新工程**：`reference-result.json`记录未平滑theta、闭区间[0,214]、215样本，拟合周期1.0424072114606664s / 相对差0.329718%，重复间隔均值1.0412668440335058s / 相对差0.219960%，两项各自≤5%；7事件 / 全部6间隔、拟合统计摘要及局限均保留。旧DLC项目有600条观察及10条派生、无训练run；保存重开相等，四图各600点。新manual项目使用独立project / video / track / calibration ID，完整600帧区间、活动标定与正确workflow恢复键；0条观察 / 派生 / 训练run，启动计数0。启动器以该工程为目标打开并请求20 / K-means选帧，交接文档要求用户标注后保存、暂不训练。上述均为读取现有产物 / 代码，不重写或重算真实工程。
- **报告准确性**：周期结果、参考均值、相对差、样本数、图表单位 / 点数与保存重开事实符合产物；限制说明符合冻结计划。唯一发现为F2：第65行将用户尚未执行的标注 / 检查集步骤陈述成既成事实，与零标签工程和交接 / 当前状态相矛盾。
- **验证 / CI**：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_prepare_p65_acceptance.py tests/gui/test_guided_representative_annotation.py`：8 passed。GitHub Actions run [40447943481](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40447943481) 与 [40447940176](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/40447940176) 均对应HEAD `966eea7c4317fad2b5c70a877bc612efd9df2330`，macOS / Windows检查全成功。未重跑报告记载的全量1417项；未启动训练 / 推理、GUI交接或真人标注，也未重算真实科学结果。

### R3 — 2026-10-27 · F2文档修复复审（S0/S1 checkpoint）

- **范围 / 基线**：仅复核F2修复提交`40028c4bbd80319669f58e8273d03fbdddbdc94d`；当前分支`feat/p6.5-pendulum-acceptance`，HEAD与该提交一致，工作区起始时干净。
- **F2复审**：最终报告已明确20帧人工标注尚未完成、4个固定检查帧尚未建立、真实训练启动0 / 2。只读`experiment/p65-acceptance/2026-10-27-final/manual-project/project.json`，确认`observations: []`、`derived: []`、`tracking_runs: []`；标注交接仍要求用户完成20帧并保存，之后再Keep 4个检查帧；`current.md`仍标记S2等待用户标注。与冻结计划一致，未发现新的文档状态矛盾。
- **结论**：F2已关闭，无新增finding。**S0/S1技术与产物核查通过；修正文档后的checkpoint状态与实际工程和交接一致。** S2用户人工标注、新AI训练 / 推理 / 科学验收及S3独立复审 / 最终Human Review仍待，不能据此判定完整Phase Gate通过。
- **操作边界**：仅核对既有文档与JSON；未启动GUI、训练、推理或重算，未修改产品、工程或冻结参考。

## Final Verdict（待 S3 收口）

- [ ] 通过（无未处置 Blocker）
- [ ] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 需要重做（说明理由）

- 最终结论：本轮阶段性结论见 R1 / R2 / R3；完整 Final Verdict 留待 S2 / S3 及 Phase Gate 收口时填写。
- 日期 / 依据轮次：—
