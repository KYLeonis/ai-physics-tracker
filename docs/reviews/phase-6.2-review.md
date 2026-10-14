# Review Record — Phase 6.2 Angular Charts and Phase Space

- 日期：2026-10-13–15；Issue [#27](https://github.com/KYLeonis/ai-physics-tracker/issues/27)，分支 `feat/p6.2-angular-charts`，基线 `main @ 8b8fa93`。
- Context：[6.2 mini-plan](../status/phase-6.2-plan.md)、ADR-0008/0009/0019/0020、CODE_STANDARD。
- R1 Reviewer 为全新 ZCode GLM-5.3 / plan 只读会话，R2 为全新本地 Codex 只读 reviewer；Codex 汇总记录、处置 findings 与最终验收。
- 当前：原科学 / 事务R3 **Approve**，F1–F9全部Closed；用户确认其余HR及轨迹多选补测通过，已集成main（`12b0911`）。

## Scope

R1 冻结 `8b8fa93..5cdf5ed` 的 application `chart_data` / `chart_recipe` / `workflow_projection` 与连接科学契约及测试；GUI 写入任务独立推进，不混入本轮冻结审查。后续完整审查须覆盖参考配置、导航、设置 / 项目 / track 变化、后台提交与持久化恢复。

## Self-review / Verification before R1

S1 首轮與定向返工中由 Codex 复现并修复输入 / SG / 时序配对漏检、旧来源猜测、stale 显示降级丢失、空参数误当配方、单摆错误引用 B、严格区间 / 近似来源读取及空首轨迹比较基准。最后返工由 GLM-5.3-Flash 正常完成，实际模型 / 套餐核对、runner 的暂存与未暂存 diff 检查通过。

- 定向：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_chart_data.py tests/test_angular_chart_data.py tests/test_workflow_projection.py` → **74 passed（1.84s）**。
- 真实保存的合成 demo：stale 时间图仍 stale；空 SG、单摆带 B、不同 input filter、SG mode、近似来源五组均拒绝相图，raw 工程未变。
- CLI 两轮执行上限保留有效增量；Bash 测试审批 client 不可用单独处置，改由 runner / Codex 执行测试。没有 5 小时额度耗尽证据，不作额度接管声明。

## Findings

### F1 — 线性计算补齐时序来源（P3，S2 已计划的前置）

- Evidence：冻结 S1 的同步 linear 未写 context，后台缺 working_zone；x–vx 明确拒绝，旧重算路径尚不能补齐。
- Decision：Fix Before Close，已归 GUI S2 ownership，生产线补齐 fps / zone / approximation，并验证实际新计算可配对。
- Status：Closed；修复 `365c2cc`，R2 确认同步 / 后台新计算均写完整来源，x–vx 缺失来源仍拒绝；实际后台结果的回归通过。

### F2 — 拒绝的相图不应同时宣称以 stale 展示（P3）

- Evidence：`_phase_pair_rejected` 在硬拒绝之前追加 shown as stale；标定过期且配方不一致时提示冲突。
- Decision：Fix Before Close，所有硬拒绝通过后才披露 stale。
- Status：Closed；修复 `365c2cc`，先失败的 stale 文案回归通过，R2 确认硬拒绝后不宣称展示。

### F3 — 未知步骤字典键序误报不兼容 / 不可读参考措辞（P3）

- Evidence：`_unknown_steps` 用 repr(params)，语义相同但键序不同误拒绝；未读取参考的 fallback 文案不准确。
- Decision：Fix Before Close，按参数的结构比较，调整不可读参考提示；不引入新框架。
- Status：Closed；修复 `365c2cc`，先失败的嵌套参数键序回归通过，R2 确认结构比较成立。

### F4 — 旧线性缓存时序来源 fail-open（P2）

- Evidence：`365c2cc` 线性时间图将缺失来源或字符串 / 浮点区间的缓存当作 valid；时序摘要通过 int() 猜测区间。工作流 latest 也未检查完整来源。
- Impact：旧缓存缺口不可见，可能把来源不明的结果解释为当前有效分析。
- Decision：Fix Before Close。保留只读曲线但标 stale，严格读取区间并披露来源未记录 / 不可读；工作流改为 needs_update，不改持久化缓存。
- Verification：5 个 legacy / malformed 图表回归、2 个按族投影回归先失败；补齐原标定 fixture 的真实时序来源，保留其标定切换断言。
- Status：Closed，修复 `ead9b0d`，R3确认严格读取 / stale / needs_update 成立；末轮证据见下方。

### F5 — 同步重算丢失未知扩展（P2）

- Evidence：`compute_angular()` 重建目标四条记录时丢掉旧 extra_fields 和 input.extra_fields；后台提交已有合并逻辑。
- Impact：公共同步 API 重算可能丢失旧项目 / 插件字段；线性同步路径存在同一原因。
- Decision：Fix Before Close。将已有扩展合并提为 `domain.derived.preserve_derived_extensions`，同步线性 / 角运动和后台批次复用；本次时序 / effective 选择覆盖旧值。
- Verification：同步重算扩展 / owned 字段更新回归先失败；两族均检查每 kind 扩展、raw 不变、Undo/Redo 与保存重开。
- Status：Closed，修复 `ead9b0d`，R3确认两族同步 / 后台扩展保留及 owned 覆盖成立。

### F6 — 未来视图版本错误重置 UI（P3）

- Evidence：版本检查发生在默认重置后，当前 θ–ω / degree / smoothed 被未来 version=2 变回默认。
- Decision：Fix Before Close。未来版本在重置之前直接返回；旧项目缺省仍恢复默认，未知版本原字段保持可保存。
- Verification：真实保存重开测试扩展该断言，修复前失败。
- Status：Closed，修复 `ead9b0d`，R3确认未来版本保持当前 UI，未知字段可保存。

### F7 — 领域 / 工作区变化未立即取消 worker（P3）

- Evidence：raw / calibration / timing / zone / workspace 变化仅刷新；应用层最终拒绝晚到结果，但 worker 一直运行。
- Decision：Fix Before Close。分析刷新信号核对现有 AnalysisInputs 快照与工作区，只在有计算意义的变化时发取消，不因显示 / 保存误取消。
- Verification：扩展 5 个 event-gated 上下文回归，取消事件修复前未设置；仍用忽略 cancel 的 runner 验证晚到结果不提交。另测普通刷新 / degree 切换保留任务，旧慢保存用例保留。
- Status：Closed，修复 `ead9b0d`，R3确认有意义输入变化立即取消，显示 / 保存不误取消，晚到仍拒绝。

### F8 — 编辑参考后重算按钮未及时禁用（P3，自查）

- Evidence：`_settingsChanged` 未安排刷新，已确认参考编辑后虽然应用层拒绝计算，按钮仍保持可点；与 HR A 的预期矛盾。
- Decision：Fix Before Close。复用已有 scheduleRefresh，一行修复。
- Verification：先排空原刷新计时器，再仅修改参考；修复前 waitUntil 明确失败，不能靠别的 UI 事件触发刷新。
- Status：Closed，修复 `ead9b0d`，R3确认参考编辑后按钮及时禁用。

### F9 — 轨迹列表无法直观勾选多条（P2，Human Review）

- Evidence：用户截图 / 反馈“在这个框无法勾选两个轨迹，其余HR通过”。名称点击只高亮单行而不勾选，macOS原生列表的未勾选标识不明显。
- Decision：Fix Before Close。控件局部使用清晰空框，整行左键切换CheckState；保持原itemChanged / checkedTracks / 计算管线。相同轨迹列表刷新保留当前行，空格在列表内接管，键盘选择不触发播放。
- Fix：`76e9439`；Normal-risk，仅GUI控件与回归，未改变科学计算或事务代码。
- Verification：新增名称 / 框 / 方向键+空格3个真实输入回归；名称点击先失败，连续键盘再复现刷新 / 播放快捷键干扰，修复后GUI定向 **51 passed（32.09s）**。验证取消某项不会取消另一项、勾选不改raw或Acquire目标、重算只选中的两轨迹且显示两曲线；diff检查及[CI38580981879](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38580981879) macOS / Windows Python3.11均通过。
- Status：Closed。用户本轮回复“通过”确认多选补测；与此前“其余HR通过”合并记录，F9闭环（收尾记录2026-10-15）。

## Review Log

### R1 — S1 Scientific Review

- 范围：冻结 `5cdf5ed`。
- 结论：**Approve with findings**；无 P1/P2，三项 P3；S1 科学不变式确认成立，GUI / 生命周期 / CI / Human 不在本次结论内。
- 实际模型：GLM-5.3 / 现有 BigModel Coding Plan；CLI 正常返回，读固定 git show；工具记录无 Edit / Write / ApplyPatch，确为只读。
- Findings：F1–F3 纳入收尾，尚不标 Closed。

### R2 — Complete Independent Review（2026-10-14）

- 范围：`8b8fa93..365c2cc` 全部 source / tests 及连接调用；全新本地只读 Codex reviewer，禁止修改文件 / Git。
- 首次因明确 Codex usage limit 中断，用户要求继续后恢复；该证据不代表 ZCode 套餐限额。
- 结论：**Request changes**，无 P1；新增 F4/F5 两个 P2，F6/F7 两个 P3。F1–F3 复审确认 Closed。
- 核对：科学配对 / 单位 / 多轨迹、源帧导航、游标、取消 / 晚到提交、Undo/Redo、保存重开 / view、旧五图 / Help / PNG / 滚轮、Analysis 只读。
- Reviewer 定向109通过，未修改 source；引用本机991和代码 `365c2cc` 双平台CI成功。真人体验与 Windows/CUDA 真机未验收。

## Final Verdict

**Approve**。科学 / 事务R3在 `ead9b0d` 上通过；后续Normal-risk GUI修复 `76e9439` 的Self-review / 51项GUI回归及双平台CI通过，用户本轮确认多选补测通过。[Human Review](../notes/phase-6.2-human-review.md)全部闭环，F1–F9 Closed，P6.2已集成main（`12b0911`）；整个Phase 6的周期 / 用户方程 / 误差范围仍未完成。

### S1–S3 checkpoint evidence（2026-10-13）

GUI / remaining P3 fixes `365c2cc`：数据76 / GUI55通过，完整本机 **991passed（66.72s）**；[CI38413697035](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38413697035) macOS/Windows Python3.11均success。ZCode网络ECONNRESET后停止派工，没有额度耗尽证据；本地全新只读reviewer正在审查完整diff，源码冻结。HR尚未发起 / 无反馈。

2026-10-14：本地完整独立 reviewer 上轮因明确的 Codex usage limit 中断，未产生最终结论；用户明确要求继续后恢复同一只读审查。该错误来自 Codex，不能作为 ZCode 套餐额度证据。

### R2 fixes / Verification（2026-10-14）

- 修复提交：`ead9b0d`，F4–F8；两族同步 / 后台使用同一扩展保留函数，不改变算法、schema 或依赖。
- 修复前，旧来源 / 同步扩展 / 5 个领域或工作区取消 / 未来视图共12个回归失败；新增两族工作流来源回归2个失败；独立的参考编辑刷新回归失败。
- 中间定向：数据 / 投影 / 同步与后台 API / 新旧 GUI / 请求身份 / Help 共 **186 passed（11.29s）**；其后 F8 一行修复纳入完整验证。
- 最终：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --tb=short` → **1007 passed（88.42s）**；`git diff --check` 通过。保存中的慢任务、忽略取消的晚到结果、原扩展往返、Analysis 只读均在本轮全量内。
- 最新源码已 push；[CI38512989022](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38512989022) 在 `ead9b0d` 上 macOS / Windows Python3.11 均 success。

### R3 — Fresh Independent Re-review（2026-10-14）

- 范围：`365c2cc..ead9b0d` 及必要连接调用，P6.2基线 `8b8fa93`；全新本地只读 Codex reviewer，无 source / tests / docs / Git 修改。
- 结论：**Approve**，无新增 P1/P2/P3；逐项确认 F4–F8 Closed；此前 F1–F3 已由 R2 确认 Closed。
- 科学配对 / 源帧、Undo/Redo、保存与 GUI 生命周期未见修复回归；Reviewer 定向 **131 passed**，补充生命周期 / 保存 **5 passed**，compileall / diff 检查通过。
- 真人体验尚无反馈，Windows/CUDA 真机仍未覆盖；后者沿用已批准的 Phase 9 前延期。

### HR1 / normal-risk UI fix（2026-10-14）

用户确认除轨迹多选以外的HR通过；F9控件修复及真实鼠标 / 键盘回归由Codex直接完成，同步原P6.2工作分支。科学 / 数据 / 后台模块未变更，原R3结论保留对应范围；此增量按mini-plan补充的Normal-risk关卡验证，仅等待多选补测。

`76e9439` 的 CI38580981879：macOS / Windows Python3.11 两作业均 **1008 passed / 2 skipped**（分别101.29s / 114.29s）；不将已有可选依赖跳过扩大为真人设备验收。

### Final Human acceptance / integration（2026-10-15）

用户确认多选补测“通过”，F9 Closed，全部HR闭环。最终验收分支 `fb071d8` 的[CI38582553294](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38582553294) macOS / Windows均success；后续 `8b1221b` 仅HR记录文档变化。main合并 `12b0911` 的树与分支tip完全一致，源码 / 测试与 `76e9439` 一致，无新增实现或独立review范围扩张。
