# Development — AI Physics Tracker

开发环境、版本选择依据、开发与验证工作流。

---

## 1. 目标与开发平台

- **主要开发环境**：macOS（Apple Silicon, arm64）
- **首要发布目标**：Windows 10 / 11 64-bit 安装程序（`AIPhysicsTracker-Setup.exe`）
- **后续发布目标**：macOS Apple Silicon（`.dmg`）
- 本项目采用"macOS 开发 → Windows 发布"的跨平台模式，策略与注意事项见 §1.1；涉及平台差异的新决策需记 ADR 并同步本文件。

### 1.1 跨平台开发模式与注意事项（macOS 开发 → Windows 发布 → 未来 macOS dmg）

#### 基本事实与构建策略

| 事项 | 结论 |
| --- | --- |
| 交叉编译 | PyInstaller / Nuitka **均不支持**在 macOS 上产出 Windows exe；Windows 包必须在 Windows (x64) 上构建 |
| Windows 构建途径 | 首选 GitHub Actions `windows-latest` runner（x64）——仓库已具备 GitHub 远程与 CI 条件；阶段性构建产出 exe artifact 供下载验证 |
| Windows 真机验收 | CI 构建不能替代真机：GUI 交互、视频解码、安装体验、CUDA 路径均可在**自有的 Windows x64（NVIDIA GPU）笔记本**上验收——真机途径已落实，需保持固定的验收节奏（涉及 GUI/视频/打包的 Phase 收尾必验） |
| Apple Silicon 上的 Windows VM | UTM/Parallels 中的 Windows 是 **ARM64**：PyTorch/CUDA/DLC 的 Windows **x64** 轮子生态不可用，仅能做纯 GUI 冒烟；本项目已有 Windows 真机，正常流程不依赖 VM |
| macOS dmg（未来） | PyInstaller 在本机 arm64 可直接产出；正式分发需 codesign + notarization（Apple Developer 账号，年费成本），Phase 9 后决策 |

#### 代码可移植性规则（Phase 1 起遵守，逐步用 CI 检查固化）

1. 路径一律 `pathlib`，禁止硬编码 `/`、`\` 或盘符。
2. 文件读写显式 `encoding="utf-8"`（Windows 默认编码是 cp936/GBK，中文路径与内容会乱码甚至崩溃）；日志、CSV/JSON 导出同理。
3. Windows 文件锁：被打开的文件（视频）不可覆盖/删除；项目持久化采用"写临时文件 + 原子替换"，绝不原地覆写。
4. 路径长度：Windows MAX_PATH 默认 260 字符，DLC 项目目录层级深，注意项目根路径总长。
5. 文件命名：避开 Windows 保留名（CON/PRN/AUX/NUL 等）与非法字符 `<>:"/\|?*`；用户输入的导出文件名需过滤。
6. 行尾：添加 `.gitattributes`（`* text=auto` + 明确二进制标记），避免 CRLF 混入代码与测试 fixture。
7. 不使用 symlink。
8. 大小写：macOS/Windows 文件系统均大小写不敏感，但 import 与路径的大小写保持与磁盘一致（Linux CI 敏感，纪律现在建立）。

#### 依赖栈的平台差异

| 组件 | macOS (arm64) 开发 | Windows x64 发布 | 要点 |
| --- | --- | --- | --- |
| PyTorch | CPU / MPS 轮子 | CPU / CUDA 轮子 | 设备选择代码需三态（cuda/mps/cpu）；MPS 算子覆盖不全，**不要以 mac 上的行为推断 Windows** |
| CUDA 路径 | 本机无法验证 | 已有支持 CUDA 的 Windows 笔记本 | CUDA 分支在自有 NVIDIA Windows 笔记本上验证；CI（无 GPU）覆盖 CPU 路径回归 |
| PySide6 | 基本一致 | 基本一致 | DPI 缩放、字体、OpenGL/绘制后端差异在 Phase 2 于 Windows 真机验证 |
| OpenCV/FFmpeg | brew 装 ffmpeg（仅开发用） | 需随安装包分发 ffmpeg（注意 GPL/LGPL 构建变体的许可选择） | 视频格式覆盖以 Windows 实测为准（重点：手机 H.265/HEVC） |
| DeepLabCut | 官方支持 macOS | 官方支持 Windows | 以官方支持矩阵为准；Phase 4 锁定版本后复核两端行为一致 |

#### 阶段性验证节奏

- **领域层/数值单元测试**：平台无关，本地（macOS）+ CI（`macos-latest` + `windows-latest`）双平台每次运行。
- **涉及 GUI、视频解码、打包的改动**：Phase 收尾时必须在 Windows 环境（CI artifact 或真机）冒烟通过才算完成。
- **数值跨平台一致性**：合成数据测试加容差断言（浮点实现差异存在，但误差应小于设定容差）。
- **GPU 相关代码**：合并前至少通过 CPU 路径测试（本地 + CI）；CUDA 路径在自有 NVIDIA Windows 笔记本上验证，验证结论记录进 Phase 收尾文档。

#### 视频解码支持矩阵（macOS arm64 实测，2026-08-29）

实测方法：顺序读取（`OpenCVVideoReader` fast path）逐帧解码耗时，取 48+ 帧均值；素材为随机噪声帧（压缩最不利情况，真实实验视频更快）。帧率预算：30fps=33.3ms/帧、60fps=16.7ms/帧。**实现不含任何分辨率/编码硬编码**，fps 与尺寸全部读取容器元数据。

| 分辨率 | H.264 (avc1) | MPEG-4 (mp4v) | MJPEG | H.265 (hvc1) |
| --- | --- | --- | --- | --- |
| 640×360 | ✓ (1.3ms) | ✓ (0.3ms) | ✓ (3.1ms) | 未测 |
| 1280×720 | ✓ (5.0ms) | ✓ (1.1ms) | ✓ (10.7ms) | ✓ (0.9ms) |
| 1920×1080 | ✓ (11.8ms，含 60fps) | ✓ (3.2ms) | 30fps ✓ / 60fps ✗ (24.1ms) | 未测 |
| 3840×2160 | 30fps ✗ (48ms，软解限制，Phase 9 GPU/硬解处理) | ✓ (10.5ms) | ✗ (95.3ms) | 未测 |

- 结论：**主战场 MP4/H.264 ≤1080p（含 60fps）顺序播放流畅**；4K H.264 为软解性能边界，已知并接受（Phase 9 优化项），浏览器/播放器级 4K 流畅需要硬解。
- H.265 依赖 OpenCV wheel 内置 FFmpeg；macOS 已验证可读。Windows 行为在 Phase 2.4 真机验收时确认（重点：手机 HEVC 录像）。
- 随机跳帧（scrub 后首次、seek 路径）耗时高于顺序读（关键帧回溯），交互上已由 latest-wins 合并掩盖，无需按帧预算约束。

## 2. 开发环境（2026-08 确定）

| 组件 | 选择 | 说明 |
| --- | --- | --- |
| OS（目标） | Windows 10 / 11 64-bit | 发布平台 |
| Python | **3.11** | 见下方依据；DeepLabCut 3.x 支持 3.10–3.12 |
| AI Framework | PyTorch（2.x，最新稳定版） | 先装 PyTorch 再装 deeplabcut |
| Tracking | DeepLabCut 3.x（PyTorch 引擎） | `pip install "deeplabcut[gui]"` 可作为参考安装 |
| GUI | PySide6-Essentials 6.11.2（Qt Widgets） | Phase 2 确认，见 ADR-0005 |
| Video | opencv-python-headless 4.14.0.94；FFmpeg 边界后续补充 | OpenCV 不提供 GUI，避免与 PySide6 Qt 插件冲突 |
| Array | NumPy 2.4.6 | 支持项目 Python 3.11–3.12；解码帧的 RGB 数组边界 |
| Sci Comp | NumPy、SciPy、Pandas | |
| Plotting | PyQtGraph 0.13.7（交互）、Matplotlib（Phase 8 导出） | Phase 3.3 / ADR-0009 |
| 包管理 | venv/conda + pip，`requirements.txt` / `pyproject.toml` | Phase 1 起锁定 |

### Python 3.11 选择依据（ADR-0002）

- DeepLabCut 官方安装文档要求 **Python 3.10–3.12**（2026-08 查证）
- PyTorch 稳定版对 3.11 支持最成熟；Python 3.13+ 曾出现 torch 轮子缺失问题
- PySide6、OpenCV、NumPy/SciPy/Pandas 在 3.11 上均有长期维护的轮子
- 当前机器 Homebrew Python 为 3.14（**不在 DLC 支持范围内**），开发环境需单独安装 3.11

### DeepLabCut 安装注意（Phase 4 已落地）

1. 创建独立环境（venv，Python 3.11–3.12）
2. 安装依赖：`pip install -e .`（`pyproject.toml` 包含 `deeplabcut>=3.0,<4.0`）
3. 本地验证：`python scripts/smoke_test_dlc_train.py`（单摆合成视频 1 epoch 冒烟验证）
4. 设备探测与计算加速：
   - macOS (Apple Silicon)：自动使用 MPS 加速（降级为 CPU 稳定运行）
   - Windows (NVIDIA GPU)：自动使用 CUDA 加速
   - CI 环境：不安装真实 DLC，通过 `MockEngineAdapter` 覆盖 100% 协议与任务流程测试
5. 验证设备支持：`python -c "import torch; print('CUDA:', torch.cuda.is_available(), 'MPS:', hasattr(torch.backends, 'mps') and torch.backends.mps.is_available())"`

### Phase 4.3 推理接口与真实验证

- 本地已有环境：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`。
- 真实 CPU 闭环：`.venv/bin/python scripts/smoke_test_dlc_infer.py`。脚本生成独立实验，
  训练 1 epoch 后全帧推理、导入、重算、保存重开；最终应显示 `PASSED`，10 帧中人工 5 点
  被保护、AI 新增 5 点。输出目录会打印并保留；首次预训练权重可能需要网络下载。
- GUI 尚无推理按钮；4.4 才接 Task Panel、窗口取消和 AI 视觉样式，当前不要求操作 GUI。
- API 顺序：`prepare_inference(session, training_run_id, InferenceParams(min_confidence=...))`
  → `start_inference(session, run_id)` → 定时 `poll_messages(session, run_id)`。
  项目必须先保存，视频必须具备本次会话时序授权，训练模型必须具有可信 SHA-256。
  首选项目内 config/model；可验证的外部旧式模型允许显式指定 config，成功后将模型及配置
  副本归档到本次 run 目录，新引用仍为相对路径。没有模型哈希的旧训练记录需重新训练，
  不能仅凭相同文件名继续推理。已登记的视频 SHA-256 会复核，内容变化不会混入旧轨迹。
- `cancel_all(session)` 在切换/关闭前回收该会话任务。推理导入成功会使目标派生 stale；
  调用既有重算 API 后使用 manual/AI 生效观测，训练标注仍只取 manual。
- 低于指定阈值及缺测不生成观测，但原始 HDF5/CSV 保留；first-wins 会跳过已有 AI，
  调低阈值再推理只能补空缺，不自动替换旧点。阈值不是模型准确度保证。
- DLC 3.0.1 兼容边界：经 `compat.analyze_videos` 调用，不重复传递它已指定的 `overwrite`；
  用 `DLCLoader.snapshots()` 定位 PyTorch 权重；帧进度在独占 worker 中临时桥接
  `InferenceRunner._extract_results`，以已后处理的预测数计数；同时在 DLC 实际解析模型时
  校验所选路径，避免 snapshot index 因目录变化而指向其他权重。结束时恢复原方法。
  升级 DLC 后必须重跑真实冒烟；不修改安装包源码，不以读帧或耗时模拟进度。
- 当前真实 DLC 验证仅 macOS CPU；MPS/CUDA 与 Windows 真机仍需另外验收。4.3 集成提交
  `e58b28d` 的 [macOS/Windows Python 3.11 CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33380207408) 均通过；CI 使用 mock，不等同 Windows CUDA 验收。
- **4.4 设计修订（用户反馈，当前工作分支已实现）**：取消 AI 链路的重复全文件 SHA-256 和缺历史 hash 门禁，
  使用轻量文件状态、实际模型引用与会话代际检查；明确不防御大小/修改时间等都相同的内容替换。
  抽帧、训练集生成、结果解析等必要耗时操作已后台化。4.4 替代 4.3 AI 任务调用路径，
  详见 `docs/status/phase-4.4-plan.md` D0；依赖下载校验不受此调整影响。
- 4.4 当前本地实现可用 `.venv/bin/python scripts/smoke_test_gui_tracking.py` 做 offscreen
  GUI 组件+真实 CPU 引擎闭环；输出独立项目路径并保留。它不代替真人 GUI 验收。
  真实短训练记录 epoch/loss/lr，并对确切 snapshot 生成 train/test RMSE（px）及样本量；
  数值用于验证评价管线，不把 1 epoch/少量样本结果当模型精度结论。

## 3. 仓库工作流

```text
main（稳定） ← 工作分支 feat/p<phase>.<sub>-<topic> / fix/<topic> / docs/<topic>
```

- 开发如何组织（Phase / Subphase / Slice 循环、mini-plan、review、GitHub Issue 映射、Agent 交接协议）见 `docs/workflow.md`
- 提交规范：Conventional Commits（详见 AGENTS.md 第 9 节）
- 每个 Phase 完成后暂停，等待下一条开发指令
- 大文件（视频/模型/训练数据）严禁入库，`.gitignore` 已覆盖；新增类型时同步更新

## 4. 代码组织（Phase 1 起）

- 源码：`src/`（包名建议 `ai_physics_tracker`，Phase 1 建立 src-layout + `pyproject.toml` 时确定）
- 测试：`tests/`，pytest
- 脚本：`scripts/`（环境安装、数据转换等辅助脚本）
- 资源：`resources/`（图标、UI 文件）
- 示例：`examples/`（不含大型视频；小型示例资产单独设计白名单）
- 代码风格与命名规范：`CODE_STANDARD.md`（根目录；写代码前必读）

## 5. 测试与验证要求

### Phase 3.3 图表依赖

`requirements.txt` 锁定 PyQtGraph 0.13.7 / SciPy 1.17.1。在项目虚拟环境运行
`python -m pip install -r requirements.txt` 对齐依赖，不安装第二套 Qt 绑定。
本地已验证 Python 3.12.13 + PySide6-Essentials 6.11.2 + NumPy 2.4.6 的
PlotWidget/InfiniteLine/offscreen smoke；Python 3.11 双平台仍以 Actions 实际结果为准。

图表默认位于窗口底部；关闭后通过 View → Kinematics charts 恢复。
在图表列表勾选轨迹，点击 Recompute checked tracks 后切换五种图表；
Measured/Smoothed position 只切换位置图，速度/加速度沿用记录的 SG 参数。
青色线是已呈现帧，橙色 seek 线是请求目标；点击图表导航会解除视频标注模式，
需要继续标注时重新点击视频侧 Track。详见 `docs/status/phase-3.3-plan.md` 的验收步骤。

3.4 标定管理：`Edit scale…` 编辑当前比例尺长度/单位/名称，保留 ID 与端点，
生效后派生结果标记 stale，需重算；取消或无改动不产生新历史。
`Delete inactive…` 仅列出非生效标定，删除不切换当前计算基准，保存前可 Undo。
`Save PNG…` 保存当前图表快照，不含面板外参数/近似时序说明；完整实验依据应连同项目保存
（ADR-0010）。本轮没有升级依赖或修改插件全局设置。

### Phase 2.4 FFprobe 工具

应用保留 OpenCV 解码；额外使用 FFprobe 完整时间索引验证 CFR。适用的 MP4/MOV
H.264/HEVC 走完整 packet PTS 快路径，其他媒体回退完整帧扫描。PATH 中有 FFprobe
即可使用；也可仅对一次启动指定 `AI_PHYSICS_FFPROBE` 的绝对路径，不改系统配置。
缺工具或验证失败仍可浏览/恢复数据，但不能新增测量。现有项目数据不会被重算或删除。

新视频首帧就绪后即可播放/跳帧/缩放，顶部常驻显示后台验证状态，可取消或重试。
验证通过 CFR 后自动启用 Add track；若显示 near-CFR，选择 `Use approximate timing…`
查看当前 Timeline FPS、全片网格误差和间隔误差，再明确 Yes 才允许测量。默认 No；
unknown/超预算 VFR 不提供近似绕过。该确认不跨重开复用，新点保存近似来源说明。
上限为 min(1 ms, 帧周期 1%)，**不保证速度/加速度精度**，见 ADR-0007。

CI 通过 `scripts/setup_ffprobe.py` 下载固定 `eugeneware/ffmpeg-static` release
`b6.1.1` 的平台资产并校验 SHA-256。该 tag 不等于各平台工具的版本号；本地验证的
darwin-arm64 资产实际报告 FFprobe 6.0。二进制只用作开发/CI，**不进入产品分发**，
最终打包的许可/安全维护方案留 Phase 9 审核。

macOS 已有环境的最短启动：

```bash
.venv/bin/python -m ai_physics_tracker
```

Windows 在仓库根目录从零启动（PowerShell，无需激活脚本或全局安装）：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts/setup_ffprobe.py --directory .tools/ffprobe
$env:AI_PHYSICS_FFPROBE = (Resolve-Path .tools/ffprobe/ffprobe.exe).Path
.venv\Scripts\python -m ai_physics_tracker
```

首次保存：File → Save，选择尚不存在的新项目目录名；重开时选择该目录中的
`project.json`。Save As 不默认复制外部视频。视频丢失时选 Relink video，不要用
Open video（新会话）替代重连。Unknown/VFR 的浏览与“已验证可测量”在状态栏区分。

### 验证命令

- 核心数据结构与物理计算必须有单元测试（pytest）
- 数值计算测试用已知解析解的合成数据（匀速、匀加速、单摆小角度）
- GUI 手动验收；逻辑层尽量与 GUI 剥离以便自动化测试
- Phase 1 起使用 pytest；Phase 2 GUI 测试增加 pytest-qt 4.5.0。本地运行 `python -m pytest`。GitHub Actions 在 `macos-latest` 与 `windows-latest` 上使用 Python 3.11、`QT_QPA_PLATFORM=offscreen` 运行同一测试矩阵。

## 6. 文档维护

每次开发周期结束时更新（详见 AGENTS.md 第 11 节）：README 当前阶段、roadmap 状态、architecture（如有变化）、development（如环境变化），新决策记 ADR。

## 7. GitHub

- 远程：`KYLeonis/ai-physics-tracker`（Private），默认分支：`main`
- 认证状态（2026-08-27 已配置）：HTTPS remote + macOS 钥匙串凭据（GitHub OAuth 设备授权获取的 token，scope: `repo`/`workflow`）。`git push` / `pull` 开箱即用，无需再输入密码。
- 说明：本机网络下 SSH 22/443 端口均被代理拦截不可达，必须使用 HTTPS remote。
- 凭据失效时：重新走一次 GitHub OAuth 设备授权流程并存入钥匙串；或在 GitHub → Settings → Applications 查看/撤销已有授权。
