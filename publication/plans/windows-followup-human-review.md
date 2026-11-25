# PR #46 — 同源候选与真人验收

- Date: 2026-11-25（自 2026-11-14 基线更新）
- Status: awaiting_human_review（已合入 `35bb617` 与 Windows HR 五项修复至 `d293dd1`，双平台 CI/打包通过，等待 Mac M1–M5 与 Windows `d293dd1` 补充验收）
- Source: `d293dd1f4904f6be5608ba6269a1363262c5f9f5`（替代原 `38628ba`）
- Target: `codex/ejp-p6-4-release`；[PR #46](https://github.com/KYLeonis/ai-physics-tracker/pull/46)
- 范围与分工以[集成计划](windows-followup-integration.md)为准；[完整审查](../../docs/reviews/windows-followup-integration-review.md)。

## 自动验证与包身份（当前候选 `d293dd1`）

| 验证 | 状态 / 证据 |
| --- | --- |
| macOS / Windows tests | [45577876431](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876431)（候选分支）与 [45577863310](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577863310)（PR 分支）：双平台 PASS；Mac `1532 passed / 7 skipped / 1 xfailed`，Windows `1532 passed / 6 skipped / 1 xfailed`；本机 `1536 passed, 3 skipped, 1 xfailed`（210.74s） |
| macOS / Windows packaging | [45577876955](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876955)：双平台原生构建/冒烟 PASS（Mac `smoke: ok`、`worker_sha256` 一致；Windows `smoke: ok`） |
| Mac artifact（`d293dd1`） | [artifact15005611459](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876955/artifacts/15005611459)，外层 ZIP `194,678,713` bytes，CI 上传校验 SHA256 `e89c5089ee0f3084a7941b7a21dafe55e337b13d4b43bee0b0ca1ec7714d3abc` |
| Windows artifact（`d293dd1`） | [artifact15005281891](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876955/artifacts/15005281891)，外层 ZIP `209,702,041` bytes，CI 上传校验 SHA256 `01069037c2d334ddc08559ecb0a932962325a9715c348fa3582f3053ea1041ac` |

> 历史候选 `38628ba`（[43602320267](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320267) / [43602320306](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320306)，Mac artifact `14116778309` / Windows artifact `14116992725`）已完成本机下载、CRC 与 `2198` 项清单核对（证据见 [windows-followup-2026-11-14.json](../evidence/runtime/windows-followup-2026-11-14.json)），并由第二作者于 2026-11-24 回传 Windows W1–W5；后续新增 `35bb617`–`d293dd1` 修改，因此本轮以 `d293dd1` 新包验收为准。

只使用上述 `d293dd1` 对应新包（Mac 亦可用 `ai-physics-tracker-windows-followup` 工作树源码直接启动验证交互）。公开 v0.1.0、10/31 交接包内旧 exe 及旧 `38628ba` / `2edd` / `109` 候选不作为本轮最终验收产物。

## 启动与测试副本

Mac 测试可直接从 GitHub 下载 [artifact15005611459](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876955/artifacts/15005611459) 中的 DMG 启动，或直接从已验证的 `d293dd1` 源码启动：

```sh
cd /Users/leonis/Documents/ai-physics-tracker-windows-followup && PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m ai_physics_tracker
```

在 `File → Open Project` 中打开测试工程（注意：36 帧若全部标满会导致 M5/W5 难例池为空，测试 M3 时可保留第 2 帧不标，或在 M5 前删除 1 帧人工点以便触发审核）：

`/Users/leonis/Documents/ai-physics-tracker-ejp/dist/windows-followup-hr/38628ba/T001_mac_review_copy/project.json`

此工程来自已有`APT_Coauthor_20261031/04_projects/T001_trained`：36帧合成摆、已有模型。准备时先核对132文件共381073751 bytes，再仅从测试副本移除第0、1、2帧的12个人工点并递增measurement revision；其余文件保留。通过正式repository保存/重读确认三帧各缺四点，第3帧仍完整。测试数据用于交互与CPU流程，不作为科学精度证据。准备证据在候选目录`fixture-copy-verification.json`。

Windows第二作者在现有交接包旁创建新的`T001_windows_review_copy`副本，保留视频与`data`目录；原`T001_trained`不变。需要同样的空白标注帧时，可由其Agent在副本中移除frames0–2的manual observations、递增experiment measurement_revision，再确认只有这12点被移除。已准备过的副本不要重复执行删点；在反馈中写明实际测试副本。

Windows下载上表artifact后先解开GitHub外层ZIP，再解开其中`AIPhysicsTracker-0.1.0-win64.zip`到新目录，运行`AI Physics Tracker\AIPhysicsTracker.exe`。两层完整保留，exe旁的`_internal`不可移走。应用版本号仍为0.1.0，因此按artifact/source/hash识别本候选。下载页需登录有仓库访问权的GitHub账号，artifact保留到2027-02-12；不是新公开Release。

## Mac：第一作者操作（共五组）

| ID | 操作 | 预期与封闭式反馈 |
| --- | --- | --- |
| M1 环境 | Settings → AI environment…；同一profile安装成功后再点Install and use与Repair / reinstall；再做一次Check，运行时尝试Cancel，结束后重做Check。 | 当前包的ready环境复验后复用同一解释器；终态清晰，取消后仍能Check/重试。若当前包替换wheel身份与旧包不同，首次建立新环境是预期；第二次应复用。M1：PASS / FAIL / NOT_RUN。 |
| M2 导航 | 打开副本，点视频/播放按钮后按←/→；再聚焦视频/标定下拉框、帧号框、滑条、轨迹列表或tab按方向键；试普通滚轮缩放及深色顶部提示。 | 视频可步进；控件保留其原生按键含义，左右键可以是原生无动作，但不得意外步进视频；滚轮/提示可用。M2：PASS / FAIL / NOT_RUN。 |
| M3 标注 | 进入Acquire的四点引导，在第0帧保持Auto-advance after4/4关闭并依次标四点；点Next到第1帧，勾选自动跳帧后再标四点；随后退出引导，进入几何拾取，移入画面显示准线，退出拾取且保持鼠标静止。 | 默认不自动跳帧；勾选后四点完成跳到第2帧；提示能说明下一步。退出拾取立即隐藏准线。M3：PASS / FAIL / NOT_RUN。 |
| M4 推理 | 选T001已有模型，必要时Verify后，显式选择cpu运行这段36帧推理，观察Activity及完成/取消提示。 | 实际任务完成，帧数/百分比与已知总量对应，未知总量不伪造百分比；失败有可读日志。M4：PASS / FAIL / NOT_RUN。 |
| M5 审核与重开 | 进入新结果的困难帧/预测审核，检查AI标签，试A接受、S跳过、C进入Correct后点击修正；保存副本并退出重开。 | 快捷键无歧义，Correct能继续在视频落点，Accept不冒充人工标注；副本可重开。M5：PASS / FAIL / NOT_RUN。 |

## Windows：第二作者操作（共五组）

| ID | 操作 | 预期与封闭式反馈 |
| --- | --- | --- |
| W1 环境 | 解压候选portable ZIP并启动exe；选Windows CPU profile，成功后重复Install and use与Repair / reinstall，再做Check的取消/重试，Export diagnostics。 | 同profile且同清单/替换包的ready环境复验复用；取消后旧环境仍可Check，终态提示可辨认；安装/自检/回收不弹空白控制台。W1：PASS / FAIL / NOT_RUN。 |
| W2 导航 | 在Windows测试副本中依次试视频←/→、下拉框/输入框/滑条/轨迹列表/tab原生方向键、普通滚轮和深色顶部提示。 | 视频步进及控件按键各自正常，输入/选择不意外改变播放帧，视频可缩放，提示可读。W2：PASS / FAIL / NOT_RUN。 |
| W3 标注 | 用准备好的缺frames0–2人工点的副本，按M3做关闭/开启4/4自动下一帧与几何拾取退出。 | 关闭停当前帧，开启在完成四点后前进；准线退出立即消失，提示明确。W3：PASS / FAIL / NOT_RUN。 |
| W4 CPU任务 | Advanced → Device=cpu，Epochs this run=1，Run joint training；另一次活动任务尝试Cancel并等终态，再重试；对完成模型Verify / run inference覆盖36帧。 | 训练/推理成功；epoch/帧数及百分比正确，未知进度明确；取消能结束并允许重试，全程不弹空白黑窗。若一次任务太快没能取消，取消项写NOT_RUN，不能推定通过。W4：PASS / FAIL / NOT_RUN。 |
| W5 审核与重开 | 对新推理做M5的AI标签、A/S/C与Correct修正、保存/重开，并保存诊断或失败日志。 | 快捷键唯一、Correct焦点可用、人工/预测语义不混淆，副本可重开。W5：PASS / FAIL / NOT_RUN。 |

## 回传与合并门禁

```text
Platform / OS / CPU:
Source: d293dd1f4904f6be5608ba6269a1363262c5f9f5
Artifact ID / ZIP SHA256:
Test project copy:
M1–M5 or W1–W5: PASS / FAIL / NOT_RUN (each)
Diagnostics / first failing action (if any):
```

| 真人验收 | 当前状态 |
| --- | --- |
| 第一作者Mac M1–M5 | pending，未收到反馈 |
| 第二作者Windows W1–W5 | `38628ba`（artifact `14116992725`）2026-11-24 回传：W1 PASS（二次复用/Repair/Check取消/导出诊断 `NOT_RUN`）、W2 PASS、W3 PASS、W4 PASS（`UX-18` FAIL）、W5 PASS；等待新候选 **`d293dd1`**（artifact `15005281891`）补充验证 `W1` 未测项 + `UX-16` 黑边光标 / `UX-18` 联合训练进度 / `UX-19` 横向滚动与 2×2 按钮 / `UX-13b` 联合审核 AI 标签 / 滑条键盘跟随 / 设备列表去 `mps` |

两边对 `d293dd1` 反馈通过后才进入合并。未执行写NOT_RUN，发现问题回到修复/重构候选，不将旧B/C/D报告或自动测试移作本轮真人反馈。CUDA、G5干净机器、学生pilot、teacher-import及完整科学导出恢复按各自证据另记；本轮基本保存重开不关闭完整恢复门禁。
