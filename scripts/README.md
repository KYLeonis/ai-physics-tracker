# scripts/

开发辅助脚本目录，例如：

- 开发环境安装脚本（Python 3.11 + PyTorch + DeepLabCut 依赖安装）
- 合成测试数据生成（模拟单摆/匀加速轨迹视频）
- 数据格式转换、批量实验处理工具

脚本应可在仓库根目录以 `python scripts/<name>.py` 运行。

`setup_ffprobe.py --directory <目录>`：开发/CI 的可选工具取得脚本。固定 ffmpeg-static
`b6.1.1` 的 FFprobe 二进制及 SHA-256，校验后才写入指定目录；不修改系统 PATH，不覆盖
已有的不同内容文件。建议开发目录 `.tools/ffprobe/`（已忽略），CI 使用 runner 临时目录。
下载来源/许可随 release 保留，本脚本不是最终安装程序分发方案。

`smoke_test_dlc_infer.py [--output <不存在的目录>]`：4.3 的真实 CPU 闭环验证。
使用已有本地环境运行 `.venv/bin/python scripts/smoke_test_dlc_infer.py`，生成 10 帧
恒定帧率合成视频和 5 个人工点，经 TrainingCoordinator 在 spawn 进程训练 1 epoch，
再经 InferenceCoordinator 使用同一快照推理，检查真实帧进度、5 个新增 AI 点、人工点保护、
运动学计算及保存重开。默认使用新的临时目录；成功和失败的文件均保留，脚本会打印位置。
需要本地已安装 DLC/PyTorch/Pandas/PyTables；不用于无 DLC 的 CI，也不代表跟踪精度验收。

`smoke_test_gui_tracking.py`：4.4 的 GUI 组件集成冒烟。在 offscreen 平台创建主窗口，
使用独立合成视频/项目，通过 Task Panel 启动真实 CPU 训练、评价和推理并验证结果。
产物保留，不操作用户实验文件。它仅验证接线和数据，不替代 AGENTS.md 的真人 Human Review。
