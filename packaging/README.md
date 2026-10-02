# packaging/

P6 论文产品线的原生封装资产。方案与决策见 [ADR-0021](../docs/decisions/0021-native-app-builds-pyinstaller-host-runtime-split.md)、总计划见 [P6 execution plan](../publication/plans/p6-packaging-execution-plan.md)；main 通用产品线的 Phase 9 原约定（PyInstaller/Nuitka 对比、Inno/NSIS、CUDA 分发策略）仍以该阶段为准，本目录当前服务于 publication 线 P6.1。

## 结构

| 文件 | 用途 |
| --- | --- |
| `host_requirements.txt` | host（GUI）构建依赖锁定集：与 CI `requirements.txt` 同源，去掉测试工具、**不含 torch/DeepLabCut** |
| `entry_point.py` | PyInstaller 入口：多进程 `freeze_support` + 组合根调用；`--apt-smoke` 冒烟模式（结果写 `APT_SMOKE_RESULT` 文件，windowed exe 不依赖 stdout） |
| `ai_physics_tracker.spec` | onedir spec：资源布局（`resources/worker-src`、`resources/ffprobe`、LICENSE/NOTICE）、excludes 兜底；依赖分离的判定是冒烟运行时断言，不是 excludes |
| `build_macos.sh` | macOS arm64：独立 build venv → PyInstaller → 冒烟 → `.app` + DMG（hdiutil UDZO） |
| `build_windows.ps1` | Windows x64：同流程 → onedir zip（Inno Setup 安装器未做，见下） |
| `NOTICE-third-party.md` | 随包第三方材料清单（P6.1 诚实清单，最终 material review 属 P6.4） |

产物在仓库根 `dist/`（已 gitignore）：macOS 为 `AIPhysicsTracker-<version>-arm64.dmg`，Windows 为 `AIPhysicsTracker-<version>-win64.zip`。CI：`.github/workflows/packaging.yml` 双平台构建并上传 artifact。

## 构建方式

```bash
# macOS（本机 arm64，脚本自建独立 build venv，不碰开发环境）
./packaging/build_macos.sh
# Windows（原生 PowerShell，python 3.11+ 在 PATH）
powershell -File packaging\build_windows.ps1
```

冒烟在构建脚本内自动执行：offscreen 构造完整 MainWindow、断言 host 未加载
torch/torchvision/deeplabcut（`launch_context.FORBIDDEN_HOST_ROOTS`）、随包
FFprobe 存在且可执行。冒烟失败即构建失败。

## Frozen 形态行为

- AI 训练/自检/推理依赖外部 Python runtime（Protocol v1 worker）。frozen 且无
  managed runtime 时，AI 入口打开 Settings → AI environment 安装界面（P6.2）。
  安装自检成功后才原子发布 `<AppDataLocation>/runtimes/active.txt`，重开时要求
  对应 `runtime-ready.json` 身份有效。高级覆盖：
  `AI_PHYSICS_RUNTIME_PYTHON=<解释器绝对路径>`。
- 本发行版 AI 流程从 Experiment setup 创建单摆实验后使用联合训练/推理。
  通用单轨的旧 AI 入口在 frozen 下禁用并显示引导；手工单轨测量仍可用。
- 手工标注、标定、运动学/ODE 拟合/批评、导出全部可用；FFprobe 用包内二进制
  （构建时 SHA-256 校验）。
- 文件日志：`<AppDataLocation>/logs/app.log`（仅 frozen）。

## 已知限制（诚实清单）

- DMG/zip **未签名未公证**（P6.4）：浏览器下载的 DMG 首次打开需右键 → 打开，
  或 `xattr -dr com.apple.quarantine "AI Physics Tracker.app"` 去隔离；ffprobe
  子进程同样受 Gatekeeper 影响。
- Windows 为 zip 便携目录，无安装器/卸载器/文件关联（用户 2026-10-02 裁定 CI
  可运行即达标；Inno Setup 待后续）。
- Windows G1–G4 真机门禁、G5 clean-machine、学生 pilot 按用户裁定延期至发行前
  （P6.3/P6.4），CI 通过不冒充真机验收。
- macOS arm64 最低为 **14.0**（host 科学计算 wheels 与 AI profile 的要求）。
- Windows CUDA profile 必须通过显式 CUDA tensor 自检；不可用时安装失败并
  保留旧环境，用户可选择 CPU profile 重试。Windows 真机训练验证仍待补。
