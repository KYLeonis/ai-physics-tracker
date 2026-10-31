# 第二作者开发与 Windows 测试交接

整理日期：2026-10-31。用户本轮要求集中整理测试视频、实验数据，规范文件命名，供第二作者继续开发与 Windows 实机测试。

## 交付位置与入口

本机交接目录：`~/Documents/APT_Coauthor_20261031/`。整个文件夹转交即可；Windows 建议放在 `C:\APT\`。

- `00_START_HERE.html`：可离线打开的导航与开始步骤。
- `README.md`：素材用途、目录说明、缺项。
- `02_NAMING_AND_DATA.md`：编号、命名、后续管理与数据解释。
- `03_WINDOWS_TEST_GUIDE.md`：14 项测试的步骤、预期与证据要求。
- `04_DEVELOPMENT_HANDOFF.md`：源码恢复、分支关系和 Windows 开发命令。
- `05_TEACHER_MODELS.md`：模型适用视频与导入方法。
- `asset_catalog.csv` / `file_manifest.csv`：视频目录 / 全量文件来源、新旧名称、大小与 SHA256。
- `tools/Verify-Files.ps1` / `tools/verify_files.py`：接收后的完整性校验。
- `validation_report.json`：本轮实际检查与未执行项。

文件夹在仓库外；原视频、模型和训练数据没有加入 Git。原始来源保留，只在交接副本中规范命名。

最终为 420 个文件、8650016759 bytes（约 8.65 GB / 8.06 GiB）；清单覆盖其中
419 个交付文件，不对自身递归取 hash。`file_manifest.csv` SHA256 为
`88e7a825dcccf2fd7355fe882bbc95f8c44692f4f623e19fc1236b18ca5d77ab`。
完整 Python 校验结果：419 files checked / 0 failures。以 `C:\APT\` 为根的最长路径为 208 字符。

## 包含的素材

| 目录 | 内容 |
| --- | --- |
| `01_videos` | 24 段 P 系列正式原片、5 段 V 系列光照压力原片，另有 T001 合成 36 帧、T002 实拍 148 帧、T003 P011 既有 600 帧裁剪 |
| `02_experiment_data` | 29 套 DLC best055 预测、effective-release TOML、参考帧；采集清单/矩阵/装置照片；后续平台 P012 人工标注 |
| `03_reference_results` | 24 条 effective-release 轨迹、48 行正式 M0/M1、冻结 golden/source-map、历史 SQLite、论文训练拆分及配置元数据 |
| `04_projects` | P011/P014 参考工程与 T001 已训练工程；均含托管视频 |
| `05_teacher_models` | P012 best020、T001 best010 两套实际已训练 ResNet50 教师包 |
| `06_development` | `154f262` 的离线 Git bundle 与上下文摘录 |
| `07_windows_build` | 源码 `54638e4` 的 Windows 测试便携 ZIP 与下载来源 |
| `08_test_results` | 14 项初始 `not_run` 测试记录、机器信息模板与结果目录规则 |

Windows 来源：packaging run `37735873042`，artifact `11531871823`，源码
`54638e484ca3160d2d335e8f78c0580bef21949a`。2026-10-31 经 GitHub connector 核对未过期并下载；外层 ZIP 为 210557843 bytes，SHA256
`71cbd76c8bf441fc5f352b5a0dca0e8242fad322b27d3f6901d9bf4fc4a22b7b`。
外层与内层 CRC 均通过，交接包只保留可直接解压使用的内层 ZIP。
开发快照 `154f262` 的 `src/` 与 `tests/` 和二进制源码一致，之后有发行文档与许可材料差异。
本次不切换/集成分支，不将通用 main 的后续开发混入论文线测试基线。

## 命名与科学语义

- 实验关联键保留 `Pxxx/Vxxx`；软件测试素材另用 `T001–T003`。不补造缺号，不猜拍摄日期。
- 原片例：`P011_pendulum_L245mm_A065deg_stable_original.mp4`。L/角度来自原采集清单的名义条件，实测初态和标定以 TOML 为准。
- 配套文件例：`P011_dlc_tracks_resnet50_best055.csv`、`P011_calibration_effective_release.toml`、`P011_reference_frame000000.png`。
- 新结果目录：`WIN_YYYYMMDD_HHMM_machine01_cpu_run01/`；CUDA 独立记录。
- 工程外层目录可规范命名；内部 UUID、run 路径、DLC 配置名和 checkpoint 名受引用约束，保留。TOML/config 中的原路径是 provenance，新包路径查索引。
- T001 工程仅在交接副本调整显示名称、嵌入原字节视频和相对媒体定位；未改观测、run、模型或科学输出，backup 同步可携带定位。
- DLC 预测不是人工真值；historical `marker_tip` 对应平台 `tip`。源帧号从 0 开始，effective release 已是 LED−1，不再重复减一。
- T003 为既有裁剪，未证明逐帧无损对应；不得套用原 P011 的释放帧。P012 已被后续平台模型训练使用，不能对该模型继续称为独立 holdout。

## 检查与缺项

- 29 段原视频与原采集 SHA256 一致；32 段独立素材经 ffprobe，并在 macOS 解码首/中/末帧，未做全帧解码或 Windows 解码声明。
- 配套 CSV 与 TOML 内嵌 hash 一致，24 正式实验与冻结 IC 的帧数、释放帧、长度对应；50 份 source-map 文件 hash 与 2 个 SQLite table extract hash 一致。
- SQLite quick_check 为 ok；正式拟合表 48 行。离线 frozen verifier 为 15 files / 48 fits / 2 cases。
- 3 个工程可由当前仓储加载，托管媒体 hash 正确；T001 原训练模型文件与 manifest 一致。
- 两教师包通过当前应用的静态导入、受管配置/权重校验；未执行新的 runtime 自检或 Windows 推理。
- Git bundle 通过 verify、临时 clone 与冻结证据校验。文件名符合 Windows 约束，按 `C:\APT\` 计算路径长度低于 260 字符。
- Python 文件校验器经过有效文件、同大小篡改、缺失文件检查；PowerShell 脚本未在本机执行。
- 论文 177 帧完整原标签与正式 `snapshot-best-055.pt` 未在本次检查的本地来源中定位。提供了原训练元数据和后续平台真实模型/标签；没有将其混称为正文模型。
- Windows G1–G5/CUDA、GUI HR、外部学生及完整安装版科学导出恢复保持 pending/not_run；本次文件交接不关闭任何实机门禁，ADR-0020 保留。

## 下一步

第二作者先校验文件，按 T001 CPU → T001 教师导入 → P012 实拍推理 → P011/P014 跨平台科学/导出 → 取消与 CUDA → 干净机器/压力场景执行。
将实际结果、源码 SHA、设备、run id、诊断和截图放入独立运行目录，再据真实证据更新 `publication/STATUS.md`。
