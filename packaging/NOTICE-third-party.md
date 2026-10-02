# 第三方材料说明（随包分发）

本文件随应用打包进 `resources/`。完整的依赖/material review 属于 P6.4 首发收尾；
当前为 P6.1 构建的诚实清单，**不构成最终许可结论**。

| 材料 | 来源 | 版本/摘要 | 说明 |
| --- | --- | --- | --- |
| FFprobe 二进制 | github.com/eugeneware/ffmpeg-static（release b6.1.1） | darwin-arm64 `bb2db6f5…`、darwin-x64 `fa3add0c…`、win32-x64 `3a7e2dc0…`（SHA-256，构建时校验） | 来自 FFmpeg；许可审查（GPL/LGPL 组合）在 P6.4 完成前仅作测试候选分发 |
| PySide6 / Qt | PySide6-Essentials 6.11.2（LGPL-3.0） | requirements 锁定 | 动态链接的 LGPL 组合，notices 待 P6.4 正式整理 |
| OpenCV | opencv-python-headless 4.14.0.94（Apache-2.0） | requirements 锁定 | — |
| NumPy / SciPy / pandas / pyqtgraph / PyYAML | 各自 BSD/MIT 类许可 | requirements 锁定 | — |
| CPython | python-build-standalone 或系统 3.12（构建机） | 见构建日志 | host 仅作为冻结归档的一部分分发 |
| PyInstaller | 6.22.3（构建工具，GPL with exception） | 不随包分发 | 只用于构建过程 |

应用自身的 LICENSE 仍为 TBD（见仓库根 LICENSE）；不因本文件改变任何许可决定。
