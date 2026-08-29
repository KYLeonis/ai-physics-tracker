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

## 2. 开发环境（2026-08 确定）

| 组件 | 选择 | 说明 |
| --- | --- | --- |
| OS（目标） | Windows 10 / 11 64-bit | 发布平台 |
| Python | **3.11** | 见下方依据；DeepLabCut 3.x 支持 3.10–3.12 |
| AI Framework | PyTorch（2.x，最新稳定版） | 先装 PyTorch 再装 deeplabcut |
| Tracking | DeepLabCut 3.x（PyTorch 引擎） | `pip install "deeplabcut[gui]"` 可作为参考安装 |
| GUI | PySide6-Essentials 6.11.2（Qt Widgets） | Phase 2 确认，见 ADR-0005 |
| Video | opencv-python-headless 4.14.0.94；FFmpeg 边界后续补充 | OpenCV 不提供 GUI，避免与 PySide6 Qt 插件冲突 |
| Array | NumPy 2.5.2 | 解码帧的 RGB 数组边界 |
| Sci Comp | NumPy、SciPy、Pandas | |
| Plotting | PyQtGraph（交互）、Matplotlib（导出） | Phase 3 前最终确认 |
| 包管理 | venv/conda + pip，`requirements.txt` / `pyproject.toml` | Phase 1 起锁定 |

### Python 3.11 选择依据（ADR-0002）

- DeepLabCut 官方安装文档要求 **Python 3.10–3.12**（2026-08 查证）
- PyTorch 稳定版对 3.11 支持最成熟；Python 3.13+ 曾出现 torch 轮子缺失问题
- PySide6、OpenCV、NumPy/SciPy/Pandas 在 3.11 上均有长期维护的轮子
- 当前机器 Homebrew Python 为 3.14（**不在 DLC 支持范围内**），开发环境需单独安装 3.11

### DeepLabCut 安装注意（Phase 4 时执行）

1. 创建独立环境（conda 或 venv，Python 3.11）
2. 先安装 PyTorch（GPU 版需选择匹配的 CUDA 轮子；CUDA runtime 随 PyTorch 轮子捆绑）
3. 再安装 `deeplabcut`（PyTorch 引擎为默认；`[gui]` extra 供参考，本项目自带 GUI 不需要）
4. 验证 `torch.cuda.is_available()`（GPU 环境）

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
