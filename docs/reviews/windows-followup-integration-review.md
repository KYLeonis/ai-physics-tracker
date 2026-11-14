# Review Record — Windows follow-up / PR #46 integration

- Subphase / Issue：Windows follow-up integration / PR #46
- Review 范围：R1完整PR `23c0a227179c96e9a8a501634850b58825d1f38a..2edd01b1d53eba7a877b10d14e574f30f9d7e9c0`，覆盖原作者十提交 `154f262..6a7a031`、其后的修复与文档同步；R2复审 `2edd01b1d53eba7a877b10d14e574f30f9d7e9c0..109ef88f4e727b658a68fa7686eb8614f05ce8f8`；R3复审打包pin/NOTICE `109ef88f4e727b658a68fa7686eb8614f05ce8f8..38628baf3a4b25543a49aef5bfa9b703bfa762b2`。
- Context：`AGENTS.md`、`CODE_STANDARD.md`、`docs/workflow.md` §5.1/§6、`docs/templates/review.md`、ADR-0021/0022/0023、`publication/spec/runtime-boundary.md`、`publication/plans/p6.2-managed-runtime.md`、`publication/plans/windows-followup-integration.md`。
- 轮次：R1 2026-11-14（首轮）· R2 2026-11-14（复审）· R3 2026-11-14（Windows FFprobe pin/NOTICE复审）

## Checklist

**正确性**

- [x] 本次源码审查范围内的实现与验收契约一致（剩余集成/Human Review门禁单列）
- [x] 已检查并修复边界问题（短EOF、网络取消、runtime身份、模式退出）
- [x] 数值逻辑不适用

**质量**

- [x] 已审完整PR范围，包括原作者十提交及后续修复
- [x] 已追踪下载/安装/复用/指针、worker启动回收、GUI调用者与状态变化
- [x] 新增逻辑测试覆盖准确（短EOF与异常分类回归已覆盖）
- [x] 检查了Windows/macOS条件路径与相关项目契约
- [x] R3核对了Windows FFprobe release/asset身份、SHA/ZIP内容、源码入口及随包许可路径

**流程**

- [x] 提交信息符合Conventional Commits
- [x] 现有依赖/打包/运行时决策已有ADR覆盖

## Findings

### F1 — 左右方向键截走组合框的原生选择操作

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/gui/main_window.py:562-566,2375-2379` 创建默认 `WindowShortcut`，焦点保护只识别 `QAbstractSpinBox`、`QLineEdit`、`QPlainTextEdit`。焦点在视频或标定 `QComboBox` 时，offscreen Qt复现中按Right保持原下标不变，窗口级快捷键触发。
- **Impact**：用户聚焦视频/标定选择器并按方向键时，播放帧被步进，选择器无法按原生键盘操作切换选项。
- **Recommendation**：方向键快捷键在有原生方向键语义的焦点控件上让位，至少包括 `QComboBox`；覆盖组合框的键盘回归。
- **Decision**：Fix Before Close — 按Implementation Agent R1 triage修复。
- **Fix commit**：`109ef88f4e727b658a68fa7686eb8614f05ce8f8`
- **Verification**：R1 offscreen Qt复现确认组合框下标不变且快捷键触发；未用GUI自动化代替Human Review。
- **Re-review**：R2确认焦点保护覆盖`QComboBox`、`QAbstractSlider`、`QAbstractItemView`、`QTabBar`及富文本控件；新键盘回归通过。
- **Status**：Closed

### F2 — 正常短EOF不会进入下载重试与Range续传

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/infrastructure/runtime_install.py:169-193,212-227` 只在 `_copy_download_stream` 抛异常时进入重试；长度不足但无异常的响应直接在226-227行失败。Python 3.12的 `http.client.HTTPResponse.read(amt)` 在已知Content-Length时可于提前EOF返回短数据而不抛 `IncompleteRead`。候选的 `tests/test_runtime_install.py:65-73` 只确认短响应失败，没有覆盖短EOF后的续传。
- **Impact**：代理或服务端在传输中正常关闭连接时，最常见的短响应路径仍要求用户整轮手动重试，新增的自动重试/续传没有工作。
- **Recommendation**：把“已接收长度小于清单长度”的响应作为可重试的中断，保留部分文件并复用Range逻辑；满长度SHA不匹配仍立即拒绝。新增首轮正常短EOF、第二轮206及重试耗尽清理回归。
- **Decision**：Fix Before Close — 按Implementation Agent R1 triage修复。
- **Fix commit**：`109ef88f4e727b658a68fa7686eb8614f05ce8f8`
- **Verification**：R1定向pytest运行与实现方并行编辑新回归交叠，结果157 passed、3 skipped、5 failed；不视为候选2edd01b的最终测试结果。R2 `tests/test_runtime_install.py` 通过短EOF Range续传、服务器忽略Range全量重下、短EOF耗尽清理、满长度SHA不匹配立即拒绝。
- **Re-review**：R2确认短响应被作为可重试的ConnectionError处理，满长度SHA mismatch仍立即失败；相关回归通过。
- **Status**：Closed

### F3 — 重试异常参数化测试重复覆盖同一种错误

- **Severity**：Suggestion
- **Evidence**：`tests/test_runtime_install.py:42-53,251-258` 建立了ConnectionResetError、TimeoutError、SSLEOFError和URLError四种`drop`，但`_flaky_resuming_server`把异常硬编码为ConnectionResetError，循环调用时也没有传入`drop`。
- **Impact**：测试报告看似覆盖了四类网络错误，实际只跑ConnectionResetError；将来其他异常分类回归时该测试不会发现。
- **Recommendation**：把异常参数传入helper，并从helper抛出对应值；四种迭代各断言自己的错误路径。
- **Decision**：Fix Before Close — 按Implementation Agent R1 triage修复。
- **Fix commit**：`109ef88f4e727b658a68fa7686eb8614f05ce8f8`
- **Verification**：R1对照候选测试源确认循环变量未使用且helper固定抛ConnectionResetError。R2 `test_transient_drop_is_retried_with_range_resume` 将四种异常分别传给helper并通过。
- **Re-review**：R2确认参数化用例现分别覆盖ConnectionResetError、TimeoutError、SSLEOFError和URLError包装；通过。
- **Status**：Closed

### F4 — 网络错误与用户取消同时发生时被报告为失败

- **Severity**：Suggestion
- **Evidence**：`src/ai_physics_tracker/infrastructure/runtime_install.py:213-234` 在网络异常捕获后，若 `cancel.is_set()` 就 `break`，循环结束统一抛 `RuntimeInstallError`。若用户在阻塞的`urlopen`期间取消、连接随后以`TimeoutError`/`URLError`结束，该异常将进入失败终态；`RuntimeSetupActions._poll` 会显示“Setup failed”。
- **Impact**：环境指针保持不变，但用户主动取消会被显示成安装失败，诊断journal也记录`failed`而非`cancelled`。
- **Recommendation**：在检测到取消时直接抛 `CancelledError`（保留网络异常为cause），再处理重试次数耗尽；覆盖直接与`URLError`包装两种返回。
- **Decision**：Fix Before Close — 按Implementation Agent R1 triage修复。
- **Fix commit**：`109ef88f4e727b658a68fa7686eb8614f05ce8f8`
- **Verification**：R1并行运行中的新增取消回归分别以直接`TimeoutError`和`URLError(ConnectionResetError)`复现两种路径；均得到`RuntimeInstallError`而非`CancelledError`。R2两路取消回归通过。
- **Re-review**：R2确认取消事件优先抛出`CancelledError`，不再落入安装失败终态；通过。
- **Status**：Closed

### F5 — 复用检查只比较OpenCV替换包是否存在，不比较包身份

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/infrastructure/runtime_install.py:336-348` 只比较 `bool(state["opencv_replacements"])` 与 `opencv_wheels is not None`；安装状态实际保存了完整替换artifact身份。应用更新后若runtime profile不变、随包LGPL OpenCV wheel/FFmpeg替换manifest的SHA或构建身份更新，旧runtime仍满足该布尔检查。复验只检查Torch/DLC等版本（355-366行），不会发现旧替换wheel。
- **Impact**：`AppDataLocation`中的旧环境会被重新激活，未安装当前应用随包提供的替换wheel，绕过ADR-0023要求的runtime替换包身份。
- **Recommendation**：将当前已验证的replacement artifact映射传入复用筛选，只有它与`install-state.json`完全相同才复用；否则走新环境安装。
- **Decision**：Fix Before Close — 按Implementation Agent R1 triage修复。
- **Fix commit**：`109ef88f4e727b658a68fa7686eb8614f05ce8f8`
- **Verification**：R1静态追踪 `install_runtime` → `verified_opencv_wheels` → `_reusable_install` → `publish_runtime`；未运行实际Mac wheel安装。R2复用测试覆盖相同身份复用、替换wheel SHA变化、FFmpeg身份变化后走新安装，以及新安装失败时保留旧active指针。
- **Re-review**：R2确认当前已验证replacement映射与ready状态完整比较；同身份复用，不同身份进入新安装，失败不改active pointer；新增回归通过。
- **Status**：Closed

### F6 — 退出标定拾取后静止准线仍留在画面

- **Severity**：Suggestion
- **Evidence**：`src/ai_physics_tracker/gui/video_view.py:357-365` 在`set_calibration_mode(None)`时不隐藏准线；隐藏仅发生于后续鼠标移动/离开处理（962-981行）。R1 offscreen复现：scale模式显示准线后调用`set_calibration_mode(None)`，两条`QGraphicsLineItem`仍为visible。
- **Impact**：用户结束标定模式且鼠标停在视频上时，准线会冻结在旧位置，让画面继续呈现拾取状态。
- **Recommendation**：模式被清除时立即隐藏两条准线，并为标定模式退出增加一个回归断言。
- **Decision**：Fix Before Close — 按Implementation Agent R1 triage修复。
- **Fix commit**：`109ef88f4e727b658a68fa7686eb8614f05ce8f8`
- **Verification**：R1 offscreen `VideoView` 复现，模式退出后两条线仍可见。R2新增scale/origin/pivot/vertical四种模式退出用例并通过。
- **Re-review**：R2确认清除标定模式且annotation mode未启用时立即隐藏两条准线；四种模式回归通过。
- **Status**：Closed

### F7 — Windows打包固定到已删除的日常FFprobe资产

- **Severity**：Blocker
- **Evidence**：R2候选 `109ef88f4e727b658a68fa7686eb8614f05ce8f8` 的 `scripts/build_ffprobe_lgpl.ps1` 固定到日常release `autobuild-2026-10-01-13-06` / `ffmpeg-n8.1.3-14-g330caae0c1-win64-lgpl-8.1.zip`。Windows packaging run `43601805936` 的 job `132467947940` 下载此URL时收到404。上游 [FFmpeg-Builds retention policy](https://github.com/FFmpeg-Builds/FFmpeg-Builds#release-retention-policy) 只保留最近14个日常包，月末最后一包保留两年。
- **Impact**：该固定依赖不可下载，Windows原生打包在PyInstaller前失败，无法生成可供后续门禁核验的候选。
- **Recommendation**：固定到上游两年保留的月末release及其asset digest，并同步NOTICE中的版本、许可和源码入口。
- **Decision**：Fix Before Close — 按Implementation Agent triage修复。
- **Fix commit**：`38628baf3a4b25543a49aef5bfa9b703bfa762b2`
- **Verification**：R3确认 `autobuild-2026-10-31-12-59` 的asset `ffmpeg-n8.1.3-27-g8dca1586f4-win64-lgpl-8.1.zip`（ID `695397529`）在GitHub release API中的大小为167,778,744 bytes、digest为`sha256:d4c2a42673917b4a97104a3e9f082729a9730796b98664e37c0b7eba6c6c613d`；独立核对本机同名ZIP的完整SHA-256、大小及全部CRC，均匹配。包内唯一`bin/ffprobe.exe`为131,577,856 bytes；其嵌入许可字符串为`LGPL version 3 or later`且build configuration含`--enable-version3`、不含`--enable-gpl`/`--enable-nonfree`。`packaging/ai_physics_tracker.spec`将`packaging/licenses/`整体收进应用，包含NOTICE所列LGPL-3.0与GPL-3.0全文；FFmpeg源码短hash `8dca1586f4`可解析为commit `8dca1586f468bfcbb78ae3ed618af1361d9f140a`，tag源码页与NOTICE一致地标为构建脚本/依赖配方及FFmpeg源码入口，并明确不把它们表述成所有依赖的完整源码包。R3未在macOS执行PowerShell或Windows打包；原生打包重跑仍属集成验证门禁。
- **Re-review**：R3确认脚本与NOTICE锁定同一月末asset、digest、版本及许可；无需新增依赖或改变既有FFmpeg架构决策。
- **Status**：Closed — pin/NOTICE源码审查完成；Windows原生打包重跑由集成门禁确认。

## Review Log

### R1 — 2026-11-14 · 首轮

- 范围 / 基线：完整检查`23c0a227..2edd01b`，覆盖`154f262..6a7a031`原始十提交、之后修复提交和文档；追踪runtime下载重试/续传/取消、安装复用身份/原子指针、worker启动与Windows回收，以及方向键/焦点、四点自动跳帧、准线、AI标签、引导提示和训练/推理进度。
- 结论：需要修改；F1、F2、F5为Blocker，F3、F4、F6为Suggestion，当前不能批准集成。
- Findings变化：新增F1–F6；关闭 —
- 验证：offscreen键盘与准线复现；定向套件因与实现方并行添加回归交叠而非候选稳定树，157 passed、3 skipped、5 failed（短EOF与网络取消分支；详情见F2/F4）。
- 未覆盖：Windows/macOS真机交互与实际runtime安装由独立原生/人审门禁完成，本轮不以自动化替代。

### R2 — 2026-11-14 · 复审

- 范围 / 基线：复审完整修复提交`109ef88f4e727b658a68fa7686eb8614f05ce8f8`相对R1候选`2edd01b1d53eba7a877b10d14e574f30f9d7e9c0`的GUI焦点、runtime下载/取消/reuse身份和准线改动，以及新增回归。
- 结论：F1–F6均修复；代码审查修改后通过。
- Findings变化：关闭F1–F6；无新增Finding。
- 验证：`PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -p no:cacheprovider tests/gui/test_playback_ui.py tests/gui/test_marking_assist_ui.py tests/test_runtime_install.py`：72 passed、1 skipped（Windows-only console suppression），7.34s。
- 验证边界：R2 reviewer运行于macOS；这不是Windows原生GUI/worker验收、实际runtime安装或Human Review证据。

### R3 — 2026-11-14 · Windows FFprobe pin/NOTICE复审

- 范围 / 基线：只读复审 `109ef88f4e727b658a68fa7686eb8614f05ce8f8..38628baf3a4b25543a49aef5bfa9b703bfa762b2` 中的 `scripts/build_ffprobe_lgpl.ps1` 与 `packaging/NOTICE-third-party.md`，并核对PyInstaller许可证收集路径及release/source引用。
- 结论：F7所指旧日常asset已换为上游按月保留的固定LGPL asset；pin、digest、NOTICE版本与原始许可相符，R3代码/文档审查通过。
- Findings变化：关闭F7；无新增Finding。
- 验证：GitHub release API 1项asset元数据核对（tag、asset ID、文件名、大小、digest）；本机ZIP完整SHA-256与167,778,744-byte大小匹配，ZIP `testzip()`无CRC错误；检查了包内单个ffprobe.exe、嵌入build configuration/许可标识，FFmpeg源码commit可解析；确认PyInstaller spec收集完整`packaging/licenses/`。本轮未运行pytest或Windows PowerShell打包脚本，因为变更仅为pin/NOTICE且reviewer运行于macOS；Windows原生packaging重跑结果不在本轮声明范围内。
- 来源依据：上游[release retention policy](https://github.com/FFmpeg-Builds/FFmpeg-Builds#release-retention-policy)、[固定release](https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/autobuild-2026-10-31-12-59)、[构建配方tag](https://github.com/FFmpeg-Builds/FFmpeg-Builds/tree/autobuild-2026-10-31-12-59)、[FFmpeg源码commit](https://github.com/FFmpeg/FFmpeg/commit/8dca1586f468bfcbb78ae3ed618af1361d9f140a)。

## Final Verdict（收口时填写）

- [ ] 通过（无未处置Blocker）
- [x] 修改后通过（findings按Decision处置完毕，复审确认）
- [ ] 需要重做（说明理由）

- 最终结论：完整源码范围的F1–F6已在`109ef88f4e727b658a68fa7686eb8614f05ce8f8`修复并经R2关闭；F7对应的Windows FFprobe pin/NOTICE已在`38628baf3a4b25543a49aef5bfa9b703bfa762b2`修复并经R3关闭。记录批准代码与NOTICE审查范围。Windows原生打包重跑、Windows原生测试/GUI、Mac Human Review及runtime实装仍由集成计划独立门禁确认，本记录不声明这些门禁通过。
- 日期 / 依据轮次：2026-11-14 / R3
