# 第二作者 Windows 适配审查与 main 同步说明

> 当前进度（2026-11-14）：用户已确认先做论文候选工作线内部集成，main通用补丁另排。PR #46原10提交和后续修复均已完整审查；F1–F7在109ef88/38628ba修复、独立复审关闭，同源双平台tests/packaging、产物核对与Mac本机包冒烟均PASS。下一步等待第二作者Windows、用户Mac本轮真人验收，通过后才合入`codex/ejp-p6-4-release`。见[集成计划](plans/windows-followup-integration.md)与[验收文档](plans/windows-followup-human-review.md)。下文11/11失败、当时未修复及main优先建议为历史记录，不覆盖本轮裁定。

检查日期：2026-11-11。本文回答“他改了什么、目前是否通过、接下来如何同步”。用户已确认：**按仓库证据更新，未验证项保留待验**。本轮只审查与同步文档，不合并或修改产品代码。

## 1. 结论

第二作者做了有价值的安装可靠性与操作体验改进：下载重试/断点续传、复用已安装 AI 环境、隐藏 Windows 后台黑窗、方向键逐帧、标注辅助与进度提示。但当前分支**需要先修复再集成**：Windows CI 有两项失败；另复现了环境复用必经路径的问题及两项 macOS 测试失败。

**他的 `main` 没有新增代码。10 个新提交都在 `codex/windows-followup`，从我们的论文发行分支分出。** 不能因双方都叫 `main`，就把整条 Windows 分支合入我们的 `main`；它携带论文线专属工程格式、四点流程、ODE、runtime 与打包基础。

建议两条线分别处理：通用修复先适配当前 `main`，验证后合入；论文专属改进保留在论文线，修复和复测后再集成。已发布的 `v0.1.0` 不变。

## 2. 仓库与分支关系

| 对象 | 本次核对结果 |
| --- | --- |
| 我们的仓库 | [KYLeonis/ai-physics-tracker](https://github.com/KYLeonis/ai-physics-tracker) |
| 第二作者仓库 | [stianyu798-arch/ai-physics-tracker](https://github.com/stianyu798-arch/ai-physics-tracker) |
| 双方远程 `main` | 同为 `7abd517481b8b0d74ab3550f170c4d5950ae66d3`，互相领先 0 个提交 |
| 第二作者修改分支 | [`codex/windows-followup`](https://github.com/stianyu798-arch/ai-physics-tracker/tree/codex/windows-followup)，头提交 `6a7a0318b4895fb7a664c26d6647894b21d97625` |
| 修改基线 | `154f262c6ff53e96dff7ba349333f1527ba43796`，即此前交接的论文测试版开发快照 |
| 本地审查分支起点 | `codex/ejp-p6-4-release` / `f4f7e3a`；相对交接基线另外有两个素材交接文档提交 |
| 第二作者净增量 | 10 commits、21 files、837 insertions / 41 deletions；其中 13 个产品源码文件、8 个测试文件 |
| PR 与新包 | 检查时第二作者仓库无 PR；该 Windows 分支仅查到一轮 tests 工作流，未查到新的 packaging 工作流 |

简化关系如下；省略两条线各自的大量中间提交：

```text
共同历史
├─ 通用产品线 → main 7abd517（双方相同）
└─ 论文产品线 → 154f262
                ├─ 两个素材交接文档提交 → 我们的 f4f7e3a
                └─ 10 个 Windows/体验提交 → 第二作者的 6a7a031
```

Git 名词：仓库是保存代码与历史的地方；分支是一条开发线；commit 是一次有编号的修改；fetch 只下载历史；merge 把整条线的历史合进来；cherry-pick 只取指定提交。PR 是展示差异、讨论和检查结果的页面，不等于已经合并。

## 3. 他具体改了什么

| 提交 | 改动与用户影响 | 同步判断 |
| --- | --- | --- |
| [`22aeb67`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/22aeb67) | 下载遇到部分网络/TLS/5xx 错误最多尝试 5 次，按 1/2/4/8 秒退避；支持 HTTP Range 续传，服务器不接受时重新下载；保留大小与 SHA256 校验 | 论文 managed runtime；先留在论文线 |
| [`b9a5ead`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/b9a5ead) | AI 环境安装/自检结束时区分成功、失败、取消，上色、置顶并提醒任务栏 | 论文 runtime 界面；需真人验收 |
| [`df3d14b`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/df3d14b) | worker、安装进程、FFprobe 在 Windows 启动时使用 `CREATE_NO_WINDOW`，减少空白控制台闪烁 | FFprobe 片段适合 main；worker/runtime 文件目前只在论文线，不能整提交照搬 |
| [`2493f8f`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/2493f8f) | 寻找同 profile、同 manifest 的 ready 环境，重新自检后复用，减少重复安装 | 论文线；存在 F1，先修复 |
| [`531fae8`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/531fae8) | `←/→` 逐帧，文本/数字输入获得焦点时让出方向键 | 适合 main；该提交引入 F2，须一起修复 |
| [`78d2d43`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/78d2d43) | 各步骤增加用途提示；Acquire 隐藏后续分析 Setup 缺项；标注引导同步到状态栏 | 通用 tooltip/状态栏可适配 main；四点与 Setup 提示属于论文流程 |
| [`c7254b8`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/c7254b8) | 增加默认关闭的“四点完成自动下一帧”；标注/几何拾取时显示全幅细十字准线 | 十字准线可适配 main；四点自动跳帧留在论文线 |
| [`3b6213b`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/3b6213b) | 任务状态行加入计数与百分比，传统训练/推理入口增加 epoch/frame 单位，未知总量显示 Working | 可适配 main；须同步旧测试 F3，并核对各任务入口 |
| [`d84e390`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/d84e390) | 困难帧预测点标注 `AI`，进入 Correct 时主窗口置顶/提醒 | 通用审核部分可适配 main；四点推理审核入口留在论文线 |
| [`6a7a031`](https://github.com/stianyu798-arch/ai-physics-tracker/commit/6a7a031) | Windows `taskkill` 清理 worker/安装进程时也隐藏控制台 | 当前只涉及论文线 external worker/runtime |

提交时间为 2026-11-05、11-06、11-10，作者为 `stianyu798-arch`。净增量没有改依赖、许可证、科学算法、schema，也没有提交 Windows 机器信息、实机任务结果或新的验收文档。

## 4. 合并前必须处理的问题

### F1 · P1：已有环境的复用会撞上旧自检目录

位置：[runtime_install.py:351](https://github.com/stianyu798-arch/ai-physics-tracker/blob/6a7a0318b4895fb7a664c26d6647894b21d97625/src/ai_physics_tracker/infrastructure/runtime_install.py#L351)。

正常首次安装已经在 `<install>/selftest` 留下 request/result/log。复用路径再次把同一个目录交给 `verify_runtime`；`ExternalWorkerRunner.start` 为保护已有任务会拒绝非空目录，抛出 `ExternalWorkerError: job directory is not empty (duplicate job)`。这里仅捕获 `RuntimeInstallError`，因此不会按设计复用或转入全新安装。

本轮使用临时 ready 环境、已有 `selftest/request.json`，调用真实 `_reusable_install`，在启动任何子进程之前确定性复现；不依赖 Windows，也没有使用用户环境。原新增测试把整个 `verify_runtime` mock 掉，未覆盖此路径。

最小修复：每次复验使用新的独占自检子目录；明确处理 worker 层复验失败，保留取消语义和旧 active 指针。增加“已有自检结果后再次 Install”的回归，并实际验证两次安装/复用。

### F2 · P1：重复的 A 快捷键使接受候选点失效

位置：[main_window.py:568](https://github.com/stianyu798-arch/ai-physics-tracker/blob/6a7a0318b4895fb7a664c26d6647894b21d97625/src/ai_physics_tracker/gui/main_window.py#L568)，由 `531fae8` 引入。

同一窗口连续创建两个 `A` 的 `QShortcut`，只有后者连接 Accept。Qt 发现快捷键冲突，不执行正常接受动作。已有 `test_shortcuts_and_focus_widget_guard_f04_f08` 在 Windows CI 和本轮 macOS 定向复跑都失败，候选帧未被标成 accepted。

最小修复：删去重复创建，保留原来的一个快捷键及焦点保护；通过既有回归后再检查 `←/→`、`A/S/C` 的联动。不能只修改测试来绕过。

### F3 · P2：进度显示改了，旧测试断言没有同步

位置：[test_task_panel.py:89](https://github.com/stianyu798-arch/ai-physics-tracker/blob/6a7a0318b4895fb7a664c26d6647894b21d97625/tests/gui/test_task_panel.py#L89)。

新状态为 `Training · 3/10 · 30%`，原断言仍要求恰好等于 `Training`。这是显示契约变更后漏更新测试，Windows CI 和本轮 macOS 都失败；与 F2 的真实交互回归不同。

最小修复：按新行为断言状态/计数/百分比，保留进度条、loss/lr、未知总量和日志上限检查。

### F4 · P2：两个新增安装测试无法在 macOS 运行

位置：[test_runtime_install.py:363](https://github.com/stianyu798-arch/ai-physics-tracker/blob/6a7a0318b4895fb7a664c26d6647894b21d97625/tests/test_runtime_install.py#L363)、[389](https://github.com/stianyu798-arch/ai-physics-tracker/blob/6a7a0318b4895fb7a664c26d6647894b21d97625/tests/test_runtime_install.py#L389)。

两个测试固定使用 Windows profile，却没有隔离主机平台判定；macOS 在进入被测逻辑前即被 `profile_supported` 拒绝。本轮这两项均失败。远程 Mac job 为 cancelled，不能记为通过。

最小修复：平台无关的复用逻辑测试隔离平台判定/使用相符 fixture；保留真正 Windows 专属进程测试的 skip。补充 F1 的真实目录保护回归，不能用跳过整个测试文件代替修复。

**审查结论：先修 F1–F4，再验证和集成。** 本文是主 Agent 对外部分支的审查，不冒充后续集成所需的独立审查或真人验收。

## 5. Windows 验证状态：以证据分别记 PASS / FAIL / 待验

2026-11-11 用户确认采用证据口径。代码里增加了 Windows 适配，不等于完整 Windows 验收通过；历史版本的 CI 通过也不能覆盖新提交。

| 验证项 | 当前状态 | 证据与边界 |
| --- | --- | --- |
| 旧版 `54638e4` Windows tests / packaging | **PASS（历史基线）** | [tests 37735873436](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37735873436)、[packaging 37735873042](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37735873042)；既有发行记录，不覆盖新增 10 个提交 |
| 第二作者 `6a7a031` Windows 全量 CI | **FAIL** | [run 42848090521](https://github.com/stianyu798-arch/ai-physics-tracker/actions/runs/42848090521)，Windows job `129940926299`：1495 passed / 2 failed / 6 skipped / 1 xfailed，253.13 秒；失败对应 F2/F3 |
| 新增 Windows 无控制台标志自动回归 | **PASS（自动测试）** | 同一 Windows run 中 external-worker spawn、FFprobe spawn、installer taskkill 的新增参数断言通过；使用 mock，不证明真实桌面不闪窗或进程树已清理 |
| 第二作者同源 macOS CI | **未通过：cancelled** | 同一 run 的 Mac job `129940925688` 已取消，无完整通过结果 |
| 本轮 macOS：8 个改动测试文件 | **FAIL** | 151 passed / 2 failed / 3 skipped，29.82 秒；失败对应 F4，两项复用测试固定 Windows profile |
| 本轮 macOS：既有两项失败测试复核 | **FAIL** | 单独复跑 F2/F3，2 failed，2.59 秒；与 Windows CI 一致 |
| 本轮环境复用真实目录探针 | **FAIL** | F1：真实 runner 在旧 selftest 目录处拒绝，未启动外部 Python |
| 新版本 Windows 打包/原生启动 | **待验** | 检查时未找到该分支新的 packaging run/二进制验收；交接包仍来自旧基线 |
| G1 frozen host → 独立 Python | **待验 / not_run** | 未收到 Windows 冻结 host/worker 身份及原生日志 |
| G2 CPU tensor + DLC import | **待验 / not_run** | 未收到 Windows 实机自检结果；CI 中部分 Torch 测试被跳过 |
| G3 CPU 真训练 → 推理 → 保存重开 | **待验 / not_run** | 未收到 Windows 实际模型、任务/结果日志与重开记录 |
| G4 协作取消 / 强制整树取消 / 错误诊断 | **待验 / not_run** | 新 taskkill 参数断言不等于真实进程树回收验证 |
| G5 无 Python 干净机器安装 / Repair | **待验 / not_run** | 现有开发机/已有环境不等于干净机器；F1 修复后还须复验复用/Repair |
| NVIDIA CUDA 自检 + 真训练/推理 | **待验 / not_run** | 未收到设备、驱动、实际 backend 和任务成功证据 |
| Windows GUI HR（滚轮/深色提示/本次新交互） | **待验** | 未收到逐项真人反馈；自动 GUI 测试不替代 HR，且 A 键已复现回归 |
| Windows 教师模型导入/推理 | **待验** | 静态导入或 Mac 成功不替代 Windows 实机任务 |
| Mac → Windows 可携带工程重开 | **待验** | 未收到 Windows 重开后的媒体/模型/科学结果一致性记录 |
| 完整安装版科学导出 / portable 恢复 / 离线闭环 | **待验** | 未收到 Windows 运行、产物与恢复核对记录 |
| 外部学生/教师试用 | **待验** | 作者开发适配不等于独立学生完成任务；保留既有试用门禁 |

历史 [runtime/results.json](evidence/runtime/results.json) 是 2026-09-20 spike 的原始结果；不回写成新机器已执行。后续新增证据应另建带日期与源码 SHA 的目录/记录，再更新当前摘要。

### 本轮复现方法

在临时独立 checkout 固定源码 `6a7a0318b4895fb7a664c26d6647894b21d97625`，使用已有开发 venv，只设置当前命令的 `PYTHONPATH=src` 与 `QT_QPA_PLATFORM=offscreen`；未安装/升级依赖，未切换两个长期 worktree 的分支，未触碰用户工程。

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_runtime_install.py tests/test_external_worker.py tests/test_ffprobe_timing.py tests/gui/test_runtime_setup_ui.py tests/gui/test_playback_ui.py tests/gui/test_marking_assist_ui.py tests/gui/test_step_guidance_ui.py tests/gui/test_experiment_inference_ui.py -q

QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/gui/test_suggested_frame_review_actions.py::test_shortcuts_and_focus_widget_guard_f04_f08 tests/gui/test_task_panel.py::test_activity_progress_unknown_state_and_bounded_log -q
```

F1 的最小输入为：同 digest 的 ready install、存在的 executable、已有非空 `selftest`。调用 `_reusable_install` 即可在 `ExternalWorkerRunner.start` 的 duplicate-job 检查处复现，不需要真实 AI 包。原新增测试用 mock 自检因此未发现它。

## 6. 我们接下来怎样同步 main

### 第一步：保留原分支，先修复，不覆盖文件

保留第二作者原始 10 个提交，另建修复提交，记录 source SHA；先关闭 F1–F4。不要使用下载 ZIP 后覆盖源码，也不要 force push 或把论文线 reset 到对方分支。

本轮 `git merge-tree --write-tree` 试算表明：我们的 `f4f7e3a` 与他的 `6a7a031` **没有文本冲突**。这只说明 Git 能组合文本，F1–F4 仍存在；没有实际 merge，也不代表测试通过。

### 第二步：把通用修复适配到当前 main

当前 main 存在 FFprobe、普通标注/审核与任务面板，**没有**论文线的 `runtime_install.py`、`external_worker.py`、`runtime_setup.py`、`publication_workflow.py`。因此，连 `df3d14b` 也混合了两条线的文件，不能整体 cherry-pick 后忽略冲突。

建议拆成几个可单独检查的小提交：

1. FFprobe Windows 无控制台启动及对应测试。
2. `←/→` 步进与输入框让键，保留单个 `A` 快捷键。
3. 普通标注十字准线、审核 `AI` 标签/Correct 提醒；沿用 main 现有控件与入口。
4. 计数/百分比与通用用途提示；更新现有测试，不引入论文四点提示/Setup 过滤。

这些提交注明对应第二作者 commit，保留作者归属。已存在且可完整应用的独立提交可用 `git cherry-pick -x <SHA>`；混合提交按当前 main 的结构适配，不复制整份旧文件覆盖 main 的新分析功能。

以下命令**只是为下一次实施准备独立 worktree**，本轮未执行。它从远程 main 建工作分支，避免打断主目录当前的 `feat/p6.5-pendulum-acceptance`。目标目录/分支必须尚不存在：

```sh
cd /Users/leonis/Documents/ai-physics-tracker-ejp
git fetch origin main
git fetch --no-tags https://github.com/stianyu798-arch/ai-physics-tracker.git '+refs/heads/codex/windows-followup:refs/remotes/coauthor/codex/windows-followup'
git worktree add -b codex/windows-main-sync /Users/leonis/Documents/ai-physics-tracker-windows-sync origin/main
cd /Users/leonis/Documents/ai-physics-tracker-windows-sync
git status
```

`fetch` 下载记录而不改工作文件；`worktree add` 新建独立工作目录，不需要用户在原目录来回切分支。这之后才开始适配、测试、提交和审查。若远程 main 已前进，按新基线重看差异。

### 第三步：通用修改验证后，合回 main

先做相关回归，再跑 macOS/Windows 全量 CI；涉及新交互给用户真人测试步骤，runtime/后台生命周期按项目规则安排独立审查。通过后用 `--no-ff` merge 记录一次完整集成，push，并核对集成 SHA 的 CI。可以建 PR 展示完整差异，但不要求用户自己处理 Git 冲突。

不能在本报告仍有 FAIL 时直接执行 merge。后续由 Agent 在正确 worktree 完成具体 Git 操作即可，用户只需要审查功能与真人体验。

### 第四步：论文专属修改再集成到 publication

下载/复用环境、四点自动跳帧与引导等在论文工作分支保留第二作者来源并修复。main 的通用最终修复按项目规则 `cherry-pick -x` 同步到论文线；若论文线已有对应实现，核对差异，避免重复应用。

论文候选也要做同源双平台 tests / packaging、Mac 回归、Windows 实机与 GUI HR；证据记录 source commit / 包 hash / 机器 / backend / run id。通过后才集成到 `publication/ejp-damped-pendulum`；当前公开 `v0.1.0` 不覆盖，新公开发行等待单独授权。

## 7. 下一次开工的完成判据

- F1–F4 修复；F1 使用真实目录保护路径验证，F2 既有回归通过。
- main 通用补丁与论文专属补丁分开，来源与作者可追踪。
- 两条线各自的最终源码验证通过；不把分支上的成功当作集成后成功。
- Windows 新包完成 G1–G5、CPU/CUDA、GUI、教师导入、工程重开、导出恢复的对应实测；缺项继续待验。
- 当前摘要只根据新增证据逐项更新；保留历史失败与原始实验结果、ADR-0020 限制。

本次已完成代码审查、远程 CI 日志核对、本机定向复现与同步方案；未修复/合并源码，未运行 Windows 真机、CUDA、打包或新的训练/推理，没有向第二作者发送消息。

## 8. 两位作者如何持续协作，让双方都看清修改

2026-11-11追加建议，尚未配置协作者权限或创建PR。已核实第二作者仓库是 `KYLeonis/ai-physics-tracker` 的真实 fork；当前我们对他的仓库只有读取权限。

### 推荐：一个主仓库，每项任务一个分支和一个PR

两位固定作者日常共同使用 `KYLeonis/ai-physics-tracker`。第二作者的fork可以保留；日常任务分支直接推到主仓库，减少两份仓库来回同步。GitHub的[共享仓库协作模式](https://docs.github.com/en/pull-requests/reference/pull-requests#shared-repository-model)支持协作者推送任务分支，再通过PR审查和合并。

1. **一次设置**：由仓库所有者在GitHub的 `Settings → Collaborators → Add people` 邀请 `stianyu798-arch`，对方接受后使用主仓库。项目规则要求GitHub设置由用户人工操作，本轮没有发送邀请或改设置。
2. **开工确定基线**：在任务PR描述里写清“目标分支、起点SHA、要解决的问题、谁实现、谁复测”。通用功能从当前 `main` 开始，论文功能从论文工作线开始；不要只说“最新版”。
3. **尽早开Draft PR**：一项任务一条工作分支和一个PR，尚未完成也可公开进度。PR的 `Commits`、`Files changed`、`Checks` 分别展示提交、代码差异、自动验证，讨论集中在 `Conversation`。见[GitHub PR说明](https://docs.github.com/en/pull-requests/reference/pull-requests#working-with-pull-requests)。
4. **修复追加提交**：保留第二作者原提交，我方修复以新的 `fix:` / `test:` 提交追加。每项问题关联对应修复SHA，不把原始实现和审查后修复揉成一个无法区分的提交。需要接手同一任务分支时先交接写入人，接手前 `fetch` / `pull --ff-only`；有本地未提交内容时先保留，不强行覆盖。
5. **以同一源码复测**：我方负责Mac回归与代码审查；第二作者负责Windows实机/必要CUDA复测。每次反馈包含源码SHA、实际包的来源或hash、通过/失败和日志位置，防止测到旧包。
6. **合并后更新基线**：我方完成集成并写明集成SHA；对方下次从新的目标分支建立任务分支。论文线与main仍按本文第6节分开集成，不因使用同一仓库而合并两条产品线。

不要求两人同时写同一个分支。独立任务各用自己的分支；接力修同一任务时，先确认上一位已推送停手，再更新并继续。日常看同一个PR即可，不需要新增一套协作系统。

### 当前这10个提交怎样进入协作流程

保留 `6a7a031` 的原始来源，将这批提交放入主仓库独立的Windows候选分支，连同后续F1–F4修复通过PR展示给双方。完整论文增量的PR观察目标应是现有 `codex/ejp-p6-4-release`，而不是 `main`；此PR用于集中审查，不提前合并。另拆main通用补丁及对应PR，沿用第6节的验证与同步顺序。

如果暂不邀请协作者，也可继续使用现有fork，由第二作者创建上述跨仓库Draft PR，并选择允许维护者编辑PR分支；他开启该选项后，我方可向同一分支追加修复，提交会出现在原PR。见[GitHub维护者修改fork PR的条件](https://docs.github.com/en/pull-requests/how-tos/commit-changes/committing-changes-to-a-pull-request-branch-created-from-a-fork)。目前没有这项授权，不能直接向他的仓库push。

### 固定在PR描述中的修复交接表

下表给双方统一口径；有修复提交后填入真实SHA与结果。已推送的 `f98cc32` 属于审查文档提交，**尚无源码修复提交**。

| 问题 | 我方做了什么 | 修复提交 | Mac/自动验证 | 第二作者Windows复测 |
| --- | --- | --- | --- | --- |
| F1 环境复用遇到旧自检目录 | 已定位并确定性复现 | 待修 | 复现失败，见第4/5节 | 待验：再次安装能否复用、失败后Repair是否可用 |
| F2 重复A快捷键 | 已定位，Mac/Windows原有回归均失败 | 待修 | 失败，见第4/5节 | 待验：A/S/C与方向键、输入框让键 |
| F3 进度旧断言 | 已区分测试契约与产品行为 | 待修 | 失败，见第4/5节 | 待验：训练/推理计数与未知总量提示 |
| F4 安装测试固定Windows平台 | 已在Mac复现两项失败 | 待修 | 失败，见第4/5节 | 自动测试修复后随同源CI复核 |

每次交接只需补充四项：**这次改了什么、哪些问题已关闭、请对方测试哪个SHA/包、还有什么未完成**。表格维护在当前任务PR，不另外复制多份状态表。PR需要查看者自行打开或订阅；本轮没有创建PR、发送评论、@第二作者或保证对方已收到通知。

### 现在可以转给第二作者的说明

> 我们已经审查你Windows分支的10个提交，原始贡献都保留。目前先定位了F1–F4，尚未改源码；最新Windows CI有两项失败，另发现环境复用和Mac测试问题。具体位置、复现证据及同步方案都在本文。建议后续在同一个主仓库用任务分支+PR接力：我方修复后逐项填写commit与Mac/自动测试结果，再请你按指定SHA/包补Windows实测；通用补丁进main，四点/独立AI环境改动留在论文线。
