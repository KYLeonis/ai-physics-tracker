# P6 — 封装与首发执行计划（供 GLM5.3 接续）

- 日期：2026-10-02；当前状态：**P6.1/P6.2代码/审查/双平台CI及Mac HR通过，已集成回publication（2f0fc98）；尚未公开发布。** 下面未更新的原始Slice清单保留为规划记录，实施状态以[STATUS](../STATUS.md)和[P6.2 mini-plan](p6.2-managed-runtime.md)为准。
- Worktree：`/Users/leonis/Documents/ai-physics-tracker-ejp`。
- Integration branch：`publication/ejp-damped-pendulum`；规划基线：`b0251cd`。
- 这里的 P6 是论文产品线 Distribution and First Release，**不是 main 的 Phase 6 Advanced Physics Analysis**。
- 当前授权：P6.2已交付；用户决定先完成Mac release，本轮只建立[P6.3 Mac mini-plan](p6.3-mac-release-candidate.md)，执行未开始，等待用户指定GLM范围。Windows实机门禁按其后续裁定延期，不能标为通过；公开tag/GitHub Release必须等用户说“发”。
- 以下Windows前置时点、License待定、Qt锁、四profile和not_run等原规划描述由后续用户裁定、ADR-0021/0022和实施mini-plan覆盖：实际三份锁（Mac CPU/MPS共享一份），原生OS锁，源码MIT，DLC3.0.1 LGPL；额度只在需要时读取当前接口，不沿用旧快照。

## 1. 交付目标与实施顺序

普通用户下载 Windows x64 安装程序或 Mac arm64 app/dmg，启动后通过界面安装独立 AI 环境，完成标注→训练→推理→修正→分析→导出；不需要预装 Python 或手工编辑 YAML。

| 顺序 | Subphase | 可检查交付物 | 进入条件 |
| --- | --- | --- | --- |
| 0 | Windows 前置门禁 | G1–G4 原生执行记录 | 用户提供 Windows 主机及兼容 DLC 环境 |
| 1 | [P6.1](#p61-native-application-builds-mini-plan) | 轻量 GUI、Windows installer、Mac app/dmg | G1–G4 全部实测通过 |
| 2 | [P6.2](#p62-managed-runtime-setup-and-repair-mini-plan) | 首次 AI setup、版本锁定、设备自检、修复与日志 | P6.1 Review/HR 通过 |
| 3 | [P6.3](#p63-release-candidate-verification-mini-plan) | 干净机器 R01–R12、学生两分支验收 | P6.2 Review/HR 通过 |
| 4 | [P6.4](#p64-first-release-close-mini-plan) | 可审查的软件发行候选、说明与校验清单 | P6.3 关闭 blocking findings |

### 共同 Agent Context Pack

顺序阅读：本 worktree 的 `AGENTS.md` → `publication/STATUS.md` → [platform requirements](../spec/platform-requirements.md)（尤其 R01–R12）→ [Phase master plan](../PHASE_PLAN.md#p6--distribution-and-first-release) → 本文相应 mini-plan。写代码前再读 `CODE_STANDARD.md`。

- 执行与环境合同：[runtime-boundary](../spec/runtime-boundary.md)、[P0.3 证据及 Windows 命令](../evidence/runtime/README.md)。复用 Protocol v1、已有身份/输出校验和取消逻辑。
- 工作方式：`docs/workflow.md` §5.1/6/10.2/10.4；每个 subphase 工作分支，`--no-ff` 集成到 publication；不合并 main，不重写历史。
- 参考：`docs/research/open-source-project-map.md` §3.14/Phase 9；只借鉴打包清单方法，不复制 GPL 项目实现或通用 hidden-import 大清单。
- 既有 Review：`docs/reviews/publication-p1.3-review.md`、`publication-p1.4-review.md` 及 P5 Review。训练/自检/推理的身份、兼容性、换 session、迟到成功与整树取消守卫均须保留；先核对实际文件名与 finding，再修改对应路径。
- 已通过：P5 用户 HR、最终集成 `355b375` 的 Windows/macOS CI；现存 CI 无真实 DLC/GPU 训练，不能证明安装器可用。
- 未完成：Windows G1–G4、G5 clean-machine setup、非开发学生两分支 pilot、Windows 可携带副本重开。ADR-0020 历史严格 xfail 仍是限制，不改 golden/profile 来让它通过。
- 不变量：candidate 不自动 adopted；训练标签不是推理结果；固定 pivot 与辅助点职责不变；近 CFR 仍须显式同意；不跨 gap 生成科学结果；保存/导出身份与科学核心共用原有实现。
- 本阶段不做：新跟踪算法、新科学模型、自动更新服务、云端运行、全平台支持、巨型离线 AI 安装包、论文/Zenodo deposit。用户项目、权重和视频不入 Git。

## 2. 前置门禁：先补 Windows G1–G4

这是 2026-09-20 用户明确延期至 P6 前的门禁；**此次“写计划”没有取消它**。缺 Windows 实机时，只能报告缺项、整理资料和交接，不进入 P6 产品实现；要改变门禁需用户明确裁定。

1. 原生 Windows x64 checkout publication 同一基线，记录 OS/CPU/GPU/driver、commit、build Python 和 AI Python 的真实绝对路径。
2. 使用 [runtime README Windows handoff](../evidence/runtime/README.md#windows-handoff用户批准延期进入p6前必须完成) 的现有 PowerShell 命令构建一次性 frozen host；`$RuntimePython` 必须替换成实际路径。这里的 tiny host 是补 P0.3 证据，不是 P6 安装器。
3. G1：hello 证明 host frozen、worker 非 frozen 且使用独立解释器；G2：CPU tensor + DLC import；G3：实际小型 CPU DLC train/infer/save-reopen；G4：协作取消、强制整树取消、故意错误保留 traceback。README 已含强制取消；另以 `host.py --help` 核实实际操作/参数，补协作取消，不能猜 CLI。
4. 每次保留 `host-result.json`、request/result、worker.log、版本、source/binary SHA；强制取消后原生检查所有记录子 PID 已消失。故意 fail 退出非零是预期，其余失败不可忽略。
5. NVIDIA CUDA 另记独立结果；G1–G4 的 CPU 通过不冒充 CUDA 通过。更新 `publication/evidence/runtime/results.json` 与 README，保留既有 Mac 证据。

**完成判据**：Windows G1–G4 都有实机证据且符合预期，review 核对后 status 写“可进入 P6.1”。现有 Mac venv 成功不替代 G5。若不满足，转交文档明确 `blocked by Windows evidence`，不写“Windows 已支持”。

## 3. 建议封装方案及先决决策

### 3.1 GUI 与 AI 环境分别交付

- **建议**延续 P0.3 的 PyInstaller `onedir`，Windows 用 Inno Setup 包装，Mac 输出 `.app` 并以系统 `hdiutil` 生成 dmg。原生平台分别构建，不在 Mac 交叉生成 Windows exe；onedir 更方便检查依赖闭包。[PyInstaller 官方说明](https://pyinstaller.org/en/stable/operating-mode.html)
- host 只含实际 GUI/视频/数值/绘图依赖；Torch/DLC 放独立 Python。先追踪 host import closure，不能仅靠 `excludes` 声称分离成功。当前 `pyproject.toml` 把 DLC 列为必装，实施时需拆出 worker/AI extra 并验证原有开发安装方式。
- build 环境独立创建，禁止调整共享 `/Users/leonis/Documents/ai-physics-tracker/.venv`。PyInstaller 6.22.3 是 P0.3 已测候选；正式构建也要锁 hooks/全部 host 依赖，不用浮动 latest。
- GUI 包带**同一 commit 的受信 worker 源码资源**，显式传 `package_root`；worker 的实际导入路径与 host 哈希对象一致。不要指向开发 checkout，不建立第二份科学实现。
- AI 环境位于 Qt `QStandardPaths` 的用户应用数据目录；bundle、Program Files 和项目目录不作为 runtime 安装目录。解释器、缓存、日志位置在 About/诊断页可见。

### 3.2 Python bootstrap 与版本锁定

- 首选待验证候选：锁定 CPython 3.12 的 `python-build-standalone` 平台归档；按其元数据识别解释器、架构和最低 OS，验证下载 SHA 后解压。用现有标准库处理下载/归档，不额外引入 uv/conda 服务。[归档官方结构](https://gregoryszorc.com/docs/python-build-standalone/main/distributions.html)
- **这是待批准/实测的发行材料来源，不是本轮已选定依赖**。P6.1 S1 形成 ADR 草案与实际下载、许可、pip/venv 可用性结果；涉及新依赖/技术选择按 AGENTS 取得必要裁定后才落地。若候选失败，再提出一个具体替代，不并行维护多个 bootstrap 后端。
- 不默认采用 Windows embeddable ZIP + get-pip：官方未将这种 pip 管理模式作为受支持的常规安装方式。[Python Windows 文档](https://docs.python.org/3.12/using/windows.html#the-embeddable-package)
- 锁定行按 `OS + arch + Python ABI + device profile` 分开：Win CPU、Win CUDA、Mac CPU、Mac MPS。记录 Python、Torch/torchvision、DLC、NumPy 及全部传递依赖、wheel URL/index、SHA、最低 OS/driver；只发布真正完成小 train+infer 的组合。Mac 本地 3.12/Torch2.13/DLC3.0.1 是候选证据，不是四行通用 lock。
- `requirements.txt` 是无 DLC 的 CI 集合，不能直接当 AI runtime lock。以实际解析结果生成全量固定 wheel 清单，安装 `pip --require-hashes`；首发不要求用户本机编译。依赖下载选择参考 [DLC 官方安装](https://deeplabcut.github.io/DeepLabCut/docs/installation.html) 和 [PyTorch 官方平台选择](https://pytorch.org/get-started/locally/)，不能拿当前 selector 输出冒充已实测组合。
- 首次训练可能另外下载 backbone：明确下载阶段、固定来源与缓存位置，离线推理测试确认自检/推理不再隐式联网。

### 3.3 冻结边界的实际改动点

| 已有位置 | 实施责任 / 需要核对 |
| --- | --- |
| `gui/main_window.py` 的 ModelActions / ExperimentInferenceActions 初始化 | 目前显式传 `_sys.executable`；统一注入已验证的 runtime Python，冻结 exe 不是 Python worker |
| `gui/model_actions.py`、`gui/experiment_inference_actions.py` | 默认 `sys.executable` 仅限 source dev；frozen 缺 runtime 时进入 setup，不启动递归 GUI |
| `application/model_worker.py` | 复用 ModelWorkerRunner，为受信资源 package_root 增加最小必要注入；避免每个按钮各做一套 resolver |
| `infrastructure/external_worker.py` | 已有 env 白名单/结果守卫；默认根从 `__file__` 回推 src，冻结时显式传资源根；保留 venv 解释器不 resolve 的行为 |
| 全部 subprocess / legacy TrackingJobRunner / multiprocessing 调用 | `rg` 所有调用与实际模块，确认 frozen 可达路径；复用 external runner 或明确入口禁用，不顺手重写遗留算法 |
| `__main__.py`、`infrastructure/ffprobe_timing.py`、`scripts/setup_ffprobe.py` | bundled FFprobe 绝对路径、已有 SHA 检查、跨平台二进制/许可；Finder 启动不依赖开发 PATH |
| `pyproject.toml`、`packaging/`、`.github/workflows/` | host/worker 依赖边界、原生构建、版本与资源；保留既有 pytest CI，构建 CI 另标 artifact smoke |

PyInstaller 改动的 DLL 搜索状态会影响子进程。Windows 的 `SetDllDirectoryW` 不是仅清 env 就能覆盖；核对实际冻结 host→worker/FFprobe 行为，集中处理并考虑 GUI 并发调用，不在各按钮临时改全局状态。POSIX/macOS 检查环境与 Finder PATH；Mac 复制/归档保留 symlink。[官方 frozen subprocess 注意事项](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)

<a id="p61-native-application-builds-mini-plan"></a>
## P6.1 Native application builds — mini-plan

**Goal**：无开发 Python/DLC 的两平台机器能安装并启动完整基础 GUI，打开视频、标注、保存重开和运行现有分析/导出。

**Agent Context Pack**：共同 Context Pack + `__main__.py`/`gui/app.py`/上述改动表、`scripts/setup_ffprobe.py`、`packaging/README.md`、P0.3 frozen evidence。风险 High-risk（依赖分发、冻结、进程启动）。

**Scope**：原生 host 构建与安装容器、资源/FFprobe/日志/入口；AI 缺失时明确 setup 占位并保留手工及已有结果功能。无联网 setup 实现；不得修改科学模型、持久化格式或默认 SG。

**Slices**：

- [ ] S1：Windows 门禁通过后开 `feat/p6.1-native-builds`；实测候选封装/ bootstrap 材料，提交 ADR 及 host/AI 依赖拆分方案，列明所需用户裁定。选择确定后固定工具版本。
- [ ] S2：最小 PyInstaller spec/构建入口；收集 Qt plugins、实际动态导入、FFprobe、worker 源码、图标及许可资源。追踪 PDF/图像导出实际依赖，不遗漏其延迟导入。
- [ ] S3：组合根资源/runtime 注入、冻结多进程入口（需要时 `freeze_support`）、无 DLC 冷启动、文件日志和可导出错误；缺 runtime 不误报模型不兼容。
- [ ] S4：Windows per-user installer/卸载、Mac `.app`/dmg。安装/卸载只管理程序文件，不清用户项目/模型/runtime；不默认申请管理员权限。不强制新增文件关联。
- [ ] S5：原生构建 CI artifact，记录 commit、build 环境/锁、资源 SHA、体积/冷启动实测，完成 Review 与双平台 HR。

**Acceptance Criteria / Verification**：

- [ ] Win x64/Mac arm64 均有原生 artifact；无 checkout、无 Python/PATH 前提，从 Explorer/Finder 启动。
- [ ] 中文含空格用户名/项目路径、bundle/安装目录只读、Open/Save As/重开、视频解码/完整时序探测、PDF/CSV 导出实际通过。
- [ ] host 不加载 Torch/DLC；AI 入口显示“安装 AI 环境”，已有轨迹/分析正常，不导入开发 venv。
- [ ] artifact 包含版本、依赖/资源清单；没有测试视频、用户权重、venv 和开发路径泄漏。
- [ ] 按实际改动跑 entry/resource/external-worker/FFprobe 定向；原生构建 smoke 与 pytest 分别记录。全量最终 CI 两平台 success，strict xfail 保持原解释。

**Review Gate**：只读 Independent Review 看完整冻结/启动 diff；修复 findings 后 Human Review 给“下载/安装→启动→视频→保存重开→已有分析导出”操作与封闭式问题，**停等用户实测**。截图/模拟器不能替代。

**Result**：not_run。完成后更新 STATUS、Review Record、ADR、实际构建命令和 packaging README；`--no-ff` 集成/push 后方可进入下一 subphase。

<a id="p62-managed-runtime-setup-and-repair-mini-plan"></a>
## P6.2 Managed runtime setup and repair — mini-plan

**Goal**：普通用户通过界面安装、检测和修复 AI 环境，训练/自检/推理始终使用经验证的独立解释器。

**Agent Context Pack**：共同 Context Pack + P6.1 Accepted ADR/build 结果、runtime-boundary、external_worker/model_worker、现有 selftest_runtime/selftest_model、auto 设备证据。High-risk（安装事务、环境身份、后台生命周期）。

**Scope**：一个 runtime 管理实现、一个 setup/repair 界面、测试矩阵与日志；复用 existing worker。只清理本任务自己的失败 staging，不改共享开发环境、不删除用户数据、不新增云端依赖。

**Slices**：

- [ ] S1：实际解析/安装并冻结四个 profile 的完整 wheel 清单；最低 OS/driver 由依赖兼容性及真机确定，缺组合保留 not_run，不宣称支持全部 Windows10/11 或全部 Mac。
- [ ] S2：每次 install 在固定最终版本目录内创建独占 staging 标记；成功前不可被 resolver 选中。**不要创建 venv 后改其路径**（脚本可能含绝对路径）；同卷原子切换小型 active 指针仅在 self-test 后完成。旧 ready runtime 继续可用，修复生成新的版本目录。
- [ ] S3：标准库下载/校验/安全解包、锁定 pip 安装、worker resource digest、runtime identity 自检；拒绝 archive 越界、逃逸 symlink、架构/ABI/哈希不符。保留运行所需合法内部 symlink，不粗暴全部展开。安装互斥优先 Qt `QLockFile`，复用已有任务线程/取消机制。
- [ ] S4：Setup 界面显示下载字节/总量、安装阶段、耗时/日志、Cancel/Retry/Repair/Export diagnostics；未知时长使用明确阶段和 busy 状态，不伪造完成百分比。网络/空间/权限/依赖失败提供本次具体恢复入口。
- [ ] S5：main window 统一使用 ready runtime；auto 在实际 worker 按 CUDA→MPS→CPU 检测。用户可显式 CPU/CUDA/MPS，显示 requested/actual device；GPU执行失败须明确报错并由用户选 CPU 重试，不偷偷降级。保留现有 model self-test 和兼容性 evidence。
- [ ] S6：真实 CPU 小训练+推理，两平台 GPU 分别做同规模 train+infer；协作及强制整树取消、故障恢复；核对已安装后离线自检/推理/重开。compile/autocast 默认 false，沿用 P5 已测行为，不为“加速”额外扩展。

**Acceptance Criteria / Verification**：

- [ ] 新用户无 Python，在线 setup 后 G5 与真实四点小闭环通过；同帧四点/固定检查集/新模型自检流程无回退。
- [ ] 错 SHA/截断下载/断网/不足空间/拒绝写入/中途取消/进程崩溃不产生 ready；重启后识别 pending 状态且可以重试；旧 runtime/用户项目字节不受影响。
- [ ] 下载、pip、自检各阶段取消均验证子进程树退出；终态先于迟到 success，换项目不续跑旧请求；运行中禁止替换其 runtime。
- [ ] CPU、CUDA、MPS 的 `available` 与真实任务 success 分别记录；不支持 GPU 具体说明，CPU 路径经实测。按 master AC，未验证 GPU 的组合不得以通过名义发布。
- [ ] 离线已安装环境可打开已存工程并用已有模型推理；首次离线安装明确失败且可恢复。模型 backbone/cache 缺项单独可见。
- [ ] 一份诊断导出含 app/runtime/profile/model/protocol/source SHA、OS/设备/版本、任务阶段及日志；凭据不入日志。
- [ ] installer 状态/指针/资源/hash/取消恢复负例定向测试 + existing worker/device/job 回归；两平台 full CI。真实 DLC evidence 单独留存，不用 mock 顶替。

**Review Gate**：只读 Independent Review 安装发布事务、受信下载/路径、实际 worker 与取消；Windows/macOS 新用户安装/故障→恢复/真实任务 Human Review。HR 前不集成，不把“导入现有 venv”当 clean-machine。

**Result**：not_run。更新 runtime matrix、恢复说明、证据/Review/STATUS；集成/push 后进入 P6.3。

<a id="p63-release-candidate-verification-mini-plan"></a>
## P6.3 Release candidate verification — mini-plan

2026-10-02用户决定Mac优先：具体Slice/AC/GLM边界以[P6.3 Mac执行mini-plan](p6.3-mac-release-candidate.md)为准；用户2026-10-03确认p63-taskA-01 HR通过并授权本次Mac开发交付收尾。以下保留双平台完整目标；Windows缺项单列not_run，Mac范围通过不等于双平台P6完成。

**Goal**：同一候选 commit 的发行包在真实非开发环境完成完整链，证明 P0–P5 的科学与教学合同在冻结环境中仍成立。

**Agent Context Pack**：共同 Context Pack + P6.1/6.2 artifact/lock/Review，`publication/student-pilot.md`、`student-pilot-record.md`、existing portable exporter 和 scientific evidence verifier。High-risk（端到端发行/恢复验收）。

**Scope**：RC 取证、必要封装 bugfix、两分支学生任务、P5 延期副本重开；不改 R01–R12 或科学容差来迁就结果。复用合法小视频/新训练模型，省赛 Windows 权重未提供不构成可使用凭证。

**Slices / Evidence**：

- [ ] S1：冻结 RC commit 与两平台 artifact SHA；记录 clean-machine 含义：没有开发 checkout/venv/Python 可供 app 偷用，安装前后实测。若同机新账户仍可见开发环境，记录隔离方式；不以换账号自动证明干净。
- [ ] S2：R01/R03/R11：两平台从安装到推荐约20帧→四点训练→自检→全片小视频推理→困难帧小批修正→重训/再推理；检查进度、取消、失败恢复、GPU实际路径。
- [ ] S3：R04–R09/R12：现有 geometry/timing/gap/fitting/λ 合成及 frozen verifier；在安装版检查角度/相图、M0/M1/残差/参数诊断、可行域。ADR-0020 明列已隔离限制；不重训练历史网络或修改 frozen scientific evidence。
- [ ] S4：R02：至少一位未参与开发本科生，用自己的视频完成 train-own 与 teacher-import 两支；只给安装/任务说明，不现场代替点击或编辑 Python/YAML。记录卡住的位置与完成情况，修复后按失败点复测。
- [ ] S5：R05/R10：显式候选采用、人工修正/stale/重新计算、保存退出重开、portable copy 跨平台重开、CSV/JSON/PDF 与结果身份核对；升级/重装保留用户 runtime/project，任务活动期间关闭/升级不破坏数据。
- [ ] S6：将 R01–R12 每行映射到实际 evidence 路径、commit/artifact SHA、平台、结果；Independent Review 关闭阻塞项，最终 HR 停等用户。

**Acceptance Criteria / Verification**：每项 R 都能追到日志/原生记录/测试/学生反馈；自动测试、真实 DLC、真人体验三种证据分栏；两平台最终源码 CI success，发行包验证关联同一 commit。学生 pilot、Windows portable 重开不再 not_run。未具备机器/反馈时留 pending 并停止相应验收，不做通过推断。

**Review Gate**：Independent Review 汇总 R01–R12 与故障恢复；两平台安装 Human Review + 非开发学生两支 pilot。新增体验必须再 HR；单纯文档勘误不重复全链。

**Result（2026-10-03）**：当前Mac开发交付按用户HR授权带发行待补项收尾；完整R01–R12未完成，Windows暂未实机验证、teacher-import/学生/完整安装版证据保留，见Mac mini-plan与STATUS。集成/push后停止，等待用户指令进入P6.4。

<a id="p64-first-release-close-mini-plan"></a>
## P6.4 First release close — mini-plan

**Goal**：得到可审查、可复现、版本及来源明确的软件首发候选，并按实际发布授权收尾。

**Agent Context Pack**：共同 Context Pack + P6.3 final evidence、repo 当前 `LICENSE`（用户2026-10-02已定MIT）、实际依赖 notices、runtime lock 和 build ADR。High-risk（公开分发/签名/依赖材料）；文档本身 Normal-risk。当前执行入口：[P6.4 mini-plan](p6.4-release-preparation.md)。

**Slices / Acceptance Criteria**：

- [ ] S1：填写支持矩阵、最低 OS/driver、包/下载/磁盘体积实测、安装/修复/设备/离线指南、已知科学与硬件限制、卸载保留说明。普通用户不需要看 JSON 或执行 shell。
- [ ] S2：actual dependency/material review：PySide/Qt、FFprobe、Torch/DLC、CPython/bootstrap、packager/installer 的实际版本许可、notices 与源码提供义务材料。**不自行把 TBD License 改成某许可**，形成具体候选与待用户裁定项；不能把进程分离当自动豁免依据。[Inno Setup 官方信息与许可入口](https://jrsoftware.org/isinfo.php)
- [ ] S3：Windows签名、Mac codesign/notarization 的账号/证书/签名范围/下载隔离后启动验证；缺证书则记录 unsigned test candidate，不标普通用户首发通过。先准备可检查产物，再请用户补签名资料或裁定，不自行购买/更改账号设置。[Apple notarization 文档](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [ ] S4：生成 RC manifest：版本/tag建议、source commit、host/runtime locks、二进制与资源 SHA256、签名结果、build命令、验证CI/evidence、notices。产物上传前再次核对不存在用户视频/模型/密钥；审查候选不等于公开发行授权。
- [ ] S5：同步 publication README/STATUS/PHASE_PLAN、packaging README、相关 architecture/development/AGENTS 标记；发布说明只写真实能力。确认具体版本与公开发布授权后才打 release tag/上传 GitHub Release；若无授权，停在已 push 的可审查候选，明确“发行尚未执行”。

**Review Gate**：材料/manifest Self-review + Independent Review 检查此前 blocking 项与来源；签名后实际下载安装 HR。修改 License、新依赖及公开发布遵守项目的必要裁定，不能用计划文件代替授权。

**Result（2026-10-04）**：用户已授权开始；S1指南/草案、S2实际二进制材料复查、S3签名与清单工具进行中。发现cv2自带GPL FFmpeg发行阻断，待用户裁定；无有效Developer ID证书，实际签名/公证待补。P6不宣布完成；无公开tag/Release。当前具体证据及下一步见执行mini-plan。

## 4. 统一验证、Git 和资源预算

- 每 Slice 先核对所属 mini-plan；实施者自己完成共享状态与连续决策，不把所有代码交给子 Agent。Independent Review 仅在规定 gate 委派只读，报告输入 diff/合同/完成判据；不伪造独立审查。
- Windows 使用原生 build shell；Mac 使用独立 host-build venv。开发源码定向验证可用既有环境：

  ```bash
  cd /Users/leonis/Documents/ai-physics-tracker-ejp
  PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_external_worker.py tests/test_ffprobe_timing.py
  ```

  上述是未来实施后的示例定向命令，不是安装器验收；按实际改动追加最小相关测试。结束 subphase 才跑必要全量/两平台最终 CI；没有新改动/失败，不重复昂贵训练或全量。
- DLC 验证先用可追溯的小数据/1 epoch/短视频/batch1–2；满足真假闭环与设备证据即可，不重跑 P012 四小时全片只为 UI。用户正在运行的训练/推理不得被接手 Agent 终止。
- 分支生命周期一个 subphase，基于 publication HEAD；每 Slice 小提交。HR 未过保持工作分支，最终 `--no-ff` 合并 publication、文档同步提交、push并核对CI；从不 merge 到 main。
- 新工具/版本/格式等必要裁定先做可审查 ADR/差异/样机结果，依据已获授权继续；缺明确授权才说明具体规则来源并询问。不能静默调整上述 Windows 门禁、R01–R12、License。

## 5. GLM5.3 执行入口与 20:11 后转交

可给 GLM 的提示词：

> 在 `/Users/leonis/Documents/ai-physics-tracker-ejp`，读取 AGENTS.md、publication/STATUS.md 和 publication/plans/p6-packaging-execution-plan.md。用户另行授权执行后，按本文从 Windows G1–G4 门禁开始；没有真机证据时不要进入 P6 产品实现。按 P6.1–P6.4 各 mini-plan 的 Slice 推进，保持 publication 分支边界，保留科学与 worker 合同。不要修改共享开发环境、用户工程或 main。每个 required HR 给出实际启动/安装路径、步骤与封闭式问题并停等反馈。到用户要求转交时保存最小可审查增量、更新 STATUS、记录未完成事项，不靠时间推断 CI/HR/额度已通过。

GLM 转交时才创建 `publication/plans/p6-handoff-YYYY-MM-DD.md`，并让用户把路径发给接手 Codex；本规划文件已是当前接续入口，无需再写重复的空 handoff。必须写：

1. 当前 worktree、branch、HEAD、基线、`git status`；各 Slice 的 done/in_progress/not_run，下一条确切动作。
2. 真机/设备证据、CI run URL/所验证 SHA、Review/HR 结果；Windows 门禁是否满足，不能仅写“测试通过”。
3. 修改文件与关键决策/仍待裁定项；运行中的**自身**任务 PID/日志/处理方式、用户任务保持运行。
4. native artifact/lock/manifest/模型 fixture 的本地路径与 SHA、最短复现命令；大文件不入 Git。
5. 失败与阻塞的原始错误/日志，已尝试什么、下一步如何验证；没有实施就明确“计划已就绪，尚未执行”。

20:11:32 是本轮接口提供的 reset 时点，接手时重新读取额度或以用户当前信息为准；不创建提醒/定时任务，不自动向其他聊天发消息。**本轮结束停在计划提交，不运行上述命令。**
