# Development — AI Physics Tracker

开发环境、版本选择依据、开发与验证工作流。

---

## 1. 目标与开发平台

- **目标发布平台**：Windows 10 / 11 64-bit（桌面应用）
- **开发平台**：Windows 为主；当前 Phase 0 在 macOS (arm64) 上完成仓库初始化
- 跨平台开发注意事项：
  - 统一使用 `pathlib` 处理路径，避免硬编码分隔符
  - 文件名大小写敏感差异（Windows 不敏感、macOS/Linux 敏感）
  - Qt 平台差异（DPI 缩放、视频绘制后端）在 GUI 开发阶段验证

## 2. 开发环境（2026-08 确定）

| 组件 | 选择 | 说明 |
| --- | --- | --- |
| OS（目标） | Windows 10 / 11 64-bit | 发布平台 |
| Python | **3.11** | 见下方依据；DeepLabCut 3.x 支持 3.10–3.12 |
| AI Framework | PyTorch（2.x，最新稳定版） | 先装 PyTorch 再装 deeplabcut |
| Tracking | DeepLabCut 3.x（PyTorch 引擎） | `pip install "deeplabcut[gui]"` 可作为参考安装 |
| GUI | PySide6（最新稳定 6.x） | Phase 2 前最终确认并记 ADR |
| Video | OpenCV（opencv-python）、FFmpeg | |
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
main（稳定） ← 工作分支 feat/<phase>-<topic> / fix/<topic> / docs/<topic>
```

- 提交规范：Conventional Commits（详见 AGENTS.md 第 9 节）
- 每个 Phase 完成后暂停，等待下一条开发指令
- 大文件（视频/模型/训练数据）严禁入库，`.gitignore` 已覆盖；新增类型时同步更新

## 4. 代码组织（Phase 1 起）

- 源码：`src/`（包名建议 `ai_physics_tracker`，Phase 1 建立 src-layout + `pyproject.toml` 时确定）
- 测试：`tests/`，pytest
- 脚本：`scripts/`（环境安装、数据转换等辅助脚本）
- 资源：`resources/`（图标、UI 文件）
- 示例：`examples/`（不含大型视频；小型示例资产单独设计白名单）

## 5. 测试与验证要求

- 核心数据结构与物理计算必须有单元测试（pytest）
- 数值计算测试用已知解析解的合成数据（匀速、匀加速、单摆小角度）
- GUI 手动验收；逻辑层尽量与 GUI 剥离以便自动化测试
- 当前 Phase 0 无代码，无测试

## 6. 文档维护

每次开发周期结束时更新（详见 AGENTS.md 第 11 节）：README 当前阶段、roadmap 状态、architecture（如有变化）、development（如环境变化），新决策记 ADR。

## 7. GitHub

- 远程：`KYLeonis/ai-physics-tracker`（Private），默认分支：`main`
- 认证状态（2026-08-27 已配置）：HTTPS remote + macOS 钥匙串凭据（GitHub OAuth 设备授权获取的 token，scope: `repo`/`workflow`）。`git push` / `pull` 开箱即用，无需再输入密码。
- 说明：本机网络下 SSH 22/443 端口均被代理拦截不可达，必须使用 HTTPS remote。
- 凭据失效时：重新走一次 GitHub OAuth 设备授权流程并存入钥匙串；或在 GitHub → Settings → Applications 查看/撤销已有授权。
