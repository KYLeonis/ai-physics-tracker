# packaging/

P6 论文产品线的原生封装资产。方案与决策见 [ADR-0021](../docs/decisions/0021-native-app-builds-pyinstaller-host-runtime-split.md)、总计划见 [P6 execution plan](../publication/plans/p6-packaging-execution-plan.md)；main 通用产品线的 Phase 9 原约定（PyInstaller/Nuitka 对比、Inno/NSIS、CUDA 分发策略）仍以该阶段为准，本目录当前服务于 publication 线 P6.1。

## 结构

| 文件 | 用途 |
| --- | --- |
| `host_requirements.txt` | host（GUI）构建依赖锁定集：与 CI `requirements.txt` 同源，去掉测试工具、**不含 torch/DeepLabCut** |
| `entry_point.py` | PyInstaller 入口：多进程 `freeze_support` + 组合根调用；`--apt-smoke` 冒烟模式（结果写 `APT_SMOKE_RESULT` 文件，windowed exe 不依赖 stdout） |
| `ai_physics_tracker.spec` | onedir spec：资源布局（`resources/worker-src`、`resources/ffprobe`、LICENSE/NOTICE）、excludes 兜底；依赖分离的判定是冒烟运行时断言，不是 excludes |
| `build_macos.sh` | macOS arm64：独立 build venv → 来源记录 → PyInstaller/可选Developer ID → 冒烟 → 可选Apple公证/装订 → DMG及候选manifest |
| `build_windows.ps1` | Windows x64：同流程 → onedir zip（Inno Setup 安装器未做，见下） |
| `NOTICE-third-party.md` | 随包第三方材料清单（P6.1 诚实清单，最终 material review 属 P6.4） |
| `SOURCE-MATERIALS.md` | 精确源码/构建入口及尚未关闭的发行材料门禁 |

普通用户见[安装指南](../publication/install-guide.md)；本文件以下构建命令供开发者使用。

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

## Mac 签名与公证（P6.4，实际执行待证书）

已有受控构建须先提交tracked改动。`APT_WORK`可指定独立build缓存，
`APT_FFPROBE_DIR`只能指向附带LGPL来源marker的合格缓存；不要使用共享开发venv。
每次构建在.app中记录build-info，并生成`dist/release-manifest.json`，关联完整
source commit/输入SHA、实际包版本、worker/资源核对、所有App物理文件SHA及DMG SHA。
构建时间和签名会造成产物SHA不同，不能宣称位级可复现。

默认仍是ad-hoc测试候选。正式商店外分发使用Apple Developer Program的
**Developer ID Application**证书，另在用户本机配置notarytool Keychain profile。
可用`xcrun notarytool store-credentials <profile>`交互录入凭据；不要提交密码、
私钥或profile密码到仓库/聊天，也不要把密码写入构建命令。

```bash
APT_CODESIGN_IDENTITY='Developer ID Application: <名称> (<TeamID>)' \
APT_NOTARY_PROFILE='<已配置的Keychain profile名称>' \
APT_DIST="$PWD/dist/p6.4-signed" bash packaging/build_macos.sh
```

证书不存在/类型不符会在构建前拒绝；公证参数没有证书也拒绝。
PyInstaller使用同一identity重签所有收集到的native code及App、启用hardened runtime，
FFprobe按binary收集以参与签名。不预置放宽JIT/library-validation的entitlements；
签名后的实际运行结果待验，出现具体需求再最小调整。
先ZIP提交App→Accepted→装订/验证App，再创建DMG→签名→提交→Accepted→装订/验证DMG，
最后Gatekeeper检查。每步失败即失败，不把unsigned产物当signed成功。
Apple返回的JSON保存在`APT_WORK/notary-app.json`、`notary-dmg.json`并写入manifest。
若失败，用返回ID执行`xcrun notarytool log <id> --keychain-profile <profile>`查看原因。

这些工具准备不等于实际公证通过。**当前本机0个有效签名identity**；需证书后
重建/公证并由用户从有隔离标记的真实下载检验双击安装、AI环境及训练推理。
没有用户明确“发”，脚本不会打tag、建立GitHub Release或上传GitHub资产。
参考：[Apple Developer ID](https://developer.apple.com/developer-id/)、
[PyInstaller签名说明](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing)。

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

- DMG/zip **当前测试候选未Developer ID签名、未公证**：Mac27实测右键打开不能
  解决“已损坏”；测试去隔离步骤见P6.3 HR，不作为普通用户安装方案。
- P6.4实际二进制检查发现Mac cv2附带FFmpeg7.1.1_3为`--enable-gpl`，包含x264/x265。
  既有独立LGPL ffprobe替换没有覆盖该库；材料门禁未关闭，等待用户裁定重建LGPL
  后端或准备GPL组合发行方案。当前不能宣称整个Mac包只含LGPL FFmpeg。
- Windows 为 zip 便携目录，无安装器/卸载器/文件关联（用户 2026-10-02 裁定 CI
  可运行即达标；Inno Setup 待后续）。
- Windows G1–G4 真机门禁、G5 clean-machine、学生 pilot 按用户裁定延期至发行前
  （P6.3/P6.4），CI 通过不冒充真机验收。
- macOS arm64 最低为 **14.0**（host 科学计算 wheels 与 AI profile 的要求）。
- Windows CUDA profile 必须通过显式 CUDA tensor 自检；不可用时安装失败并
  保留旧环境，用户可选择 CPU profile 重试。Windows 真机训练验证仍待补。
