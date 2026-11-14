# PR #46 — 同源候选与真人验收

- Date: 2026-11-14
- Status: awaiting_human_review（自动验证与包核对已完成，等待双方实际反馈）
- Source: `38628baf3a4b25543a49aef5bfa9b703bfa762b2`
- Target: `codex/ejp-p6-4-release`；[PR #46](https://github.com/KYLeonis/ai-physics-tracker/pull/46)
- 范围与分工以[集成计划](windows-followup-integration.md)为准；[完整审查](../../docs/reviews/windows-followup-integration-review.md)。

## 自动验证与包身份

| 验证 | 状态 / 证据 |
| --- | --- |
| macOS / Windows tests | [43602320267](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320267)：双平台PASS；Mac1523 passed/7 skipped/1既有strict xfailed（164.75s），Windows1524 passed/6 skipped/1既有strict xfailed（419.88s） |
| macOS / Windows packaging | [43602320306](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320306)：双平台构建/原生冒烟PASS |
| Mac DMG、artifact、SHA256、签名与本机冒烟 | [artifact14116778309](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320306/artifacts/14116778309)，下载ZIP195710616 bytes，SHA256 `2bc6a130c2e50f2315fcd8a89fbdf37a09ef464e0512ea6285ff9637a78e5a83`；DMG196575804 bytes，SHA256 `721843fcdccc26e8e75d562d6b80e3831aa1803c51b7ae906db973c0d9a1f492`。CRC、manifest源/产物/2198项App inventory、114个worker源码逐字节核对与ad_hoc签名验证PASS；macOS27.2.1 arm64本机packaged smoke PASS。没有Apple公证。 |
| Windows portable ZIP、artifact、SHA256、worker源码身份 | [artifact14116992725](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320306/artifacts/14116992725)，下载ZIP209679592 bytes，SHA256 `3a1c44126793534616357bbf9415bab922b02f8258798622527ebbbfca6c4d43`；内层portable ZIP210805208 bytes，SHA256 `a68b1505269e1911c9ef91ac2be46afcb85e9b43a59a80603657caf7366a1063`。双层ZIP CRC、FFprobe与固定上游二进制逐字节核对PASS；114个worker及runtime/NOTICE/license文本在CRLF→LF规范化后与同源源码一致，差异仅Windows checkout换行。Windows原生冒烟由CI完成，本机没有执行exe。 |

机器可读证据：[windows-followup-2026-11-14.json](../evidence/runtime/windows-followup-2026-11-14.json)。Windows包没有Mac式build-info/release manifest；其来源证据为固定head的CI checkout、artifact digest及上述归档内容核对，不声称有未生成的签名/provenance文件。

只使用上述source对应的新包。公开v0.1.0、10/31交接包内旧exe及已取消的2edd/109候选都不用于本轮验收。原始失败/取消记录保留在集成计划中。

## 启动与测试副本

Mac候选已从核验后的DMG复制到独立目录，磁盘映像已弹出。退出旧版后启动：

```sh
open -n "/Users/leonis/Documents/ai-physics-tracker-ejp/dist/windows-followup-hr/38628ba/AI Physics Tracker.app"
```

不需要配置Python或重装开发venv。在File → Open Project中打开测试工程：

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
Source: 38628baf3a4b25543a49aef5bfa9b703bfa762b2
Artifact ID / inner package SHA256:
Test project copy:
M1–M5 or W1–W5: PASS / FAIL / NOT_RUN (each)
Diagnostics / first failing action (if any):
```

| 真人验收 | 当前状态 |
| --- | --- |
| 第一作者Mac M1–M5 | pending，未收到本候选反馈 |
| 第二作者Windows W1–W5 | pending，未收到本候选反馈 |

两边本轮反馈通过后才进入合并。未执行写NOT_RUN，发现问题回到修复/重构候选，不将旧B/C/D报告或自动测试移作本轮真人反馈。CUDA、G5干净机器、学生pilot、teacher-import及完整科学导出恢复按各自证据另记；本轮基本保存重开不关闭完整恢复门禁。
