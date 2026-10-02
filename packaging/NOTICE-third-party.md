# 第三方材料说明（Third-Party Notices）

本文件与 `resources/licenses/` 下的许可文本一起随应用分发。主程序源码许可为
仓库根 `LICENSE`（MIT）。本表为 P6.1 许可复查（2026-10-02）核实结果，逐项
可直接追溯到构建锁定集 `packaging/host_requirements.txt` 与对应 license 原件。

## 随包分发的组件

| 组件 | 版本 | 许可 | 证据/文本 |
| --- | --- | --- | --- |
| PySide6-Essentials / Qt 6 / shiboken6 | 6.11.2 | LGPL-3.0-only（构建亦提供 GPL-2/3 选项；本项目按 LGPL 动态链接使用） | `LGPL-3.0.txt` + `GPL-3.0.txt`（LGPL-3 以 GPL-3 为引用前提，两者均随包）；Qt 源码可获取于 https://download.qt.io ；wheel 本身不携带许可文本，故从 gnu.org 收录正本 |
| opencv-python-headless（cv2，含其捆绑的 FFmpeg/libav* 等 dylib） | 4.14.0.94 | OpenCV: Apache-2.0；捆绑组件（FFmpeg dylibs、libbluray、libmp3lame 等）按其各自许可 | `opencv-python-headless-4.14.0.94.LICENSE.txt` 与 `LICENSE-3RD-PARTY.txt`（wheel 原件，逐组件枚举） |
| FFprobe（时序探测，独立进程） | macOS: 7.1.1 源码自建 / Windows: BtbN n8.1.3-14 | LGPL（macOS 构建为 `--disable-gpl --disable-nonfree`，configure 确认 "LGPL version 2.1 or later"；Windows 为 BtbN FFmpeg-Builds win64-lgpl 包） | 见下"FFprobe 分发决定" |
| NumPy | 2.4.6 | BSD-3-Clause（含捆绑组件） | `numpy-2.4.6.LICENSE.txt` + `numpy-2.4.6-extra-licenses/`（wheel 原件） |
| SciPy | 1.17.1 | BSD-3-Clause（含捆绑组件） | `scipy-1.17.1.LICENSE.txt` |
| pandas | 2.3.3 | BSD-3-Clause | `pandas-2.3.3.LICENSE` |
| pyqtgraph | 0.13.7 | MIT | `pyqtgraph-0.13.7.LICENSE.txt` |
| PyYAML | 6.0.3 | MIT | `pyyaml-6.0.3.LICENSE` |
| python-dateutil | 2.9.0 | BSD-3-Clause OR Apache-2.0（双许可） | `python-dateutil-2.9.0.LICENSE` |
| pytz | 2026.4 | MIT | `pytz-2026.4.LICENSE.txt` |
| six | 1.17.0 | MIT | `six-1.17.0.LICENSE` |
| typing_extensions | 4.16.0 | PSF-2.0 | `typing-extensions-4.16.0.LICENSE` |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause（双许可） | `packaging-26.3.LICENSE.APACHE` / `.BSD` |
| tzdata（含 zone 数据） | 2026.4 | Apache-2.0（zone 数据公共领域/各自许可） | `tzdata-2026.4.LICENSE` + `tzdata-2026.4-zone-licenses/` |
| CPython（内嵌解释器与标准库） | 3.12 | PSF-2.0 | `CPython-3.12.PSF-LICENSE`（自 cpython 3.12 分支原件） |
| PyInstaller bootloader（嵌入可执行文件） | 6.22.3 | bootloader 随包部分适用 PyInstaller 许可中的例外条款（允许被打包程序不成为 GPL） | `pyinstaller-6.22.3.COPYING.txt`（原件，含例外条款全文） |

## FFprobe 分发决定（2026-10-02 复查结论）

初版（P6.1 首个 DMG/CI）使用 `eugeneware/ffmpeg-static` b6.1.1 预编译二进制。
复查发现其 macOS arm64 二进制为 `--enable-gpl --enable-nonfree` 构建（osxexperts.net），
按 FFmpeg 官方许可政策 **nonfree 构建不可再分发**；其 Windows 来源 gyan.dev 的
全部构建现为 GPLv3 且无法提供精确构建配置。因此公开发布前替换为：

- **macOS（arm64）**：`scripts/build_ffprobe_lgpl.sh` 从 ffmpeg.org 官方
  `ffmpeg-7.1.1.tar.xz`（SHA-256 `73398439…00e25`，独立二次下载核对）自建，
  configure 显式 `--disable-gpl --disable-nonfree --disable-version3`，仅启用
  file 协议、mov/avi/matroska/h264/mjpeg demuxer 与 h264/hevc/mpeg4/mjpeg/ffv1
  decoder（时序探测所需）；configure 输出确认 "LGPL version 2.1 or later"，
  脚本在该确认缺失时拒绝出货。LGPL 对应源码即上述官方 tarball + 脚本内的
  configure 参数（仓库内可复现）。
- **Windows（x64）**：`scripts/build_ffprobe_lgpl.ps1` 取 BtbN FFmpeg-Builds
  日期化 release `autobuild-2026-10-01-13-06` 的版本化资产
  `ffmpeg-n8.1.3-14-g330caae0c1-win64-lgpl-8.1.zip`（SHA-256
  `84e4495b…4006d`，GitHub asset digest），LGPL 变体，仅提取 `bin/ffprobe.exe`；
  对应源码可由该仓库同 tag 的源码资产获得。

单元测试/开发 CI（tests.yml）仍可使用 ffmpeg-static 的 ffprobe（不随产物分发，
无再分发问题）；`scripts/setup_ffprobe.py` 保留用于该用途。

## AGPL 边界声明

DeepLabCut（AGPL-3.0）与 PyTorch **不随本应用分发**：host 依赖闭包不含 AI 栈
（构建冒烟断言 torch/torchvision/deeplabcut 不得加载），AI 功能所需的独立
Python runtime 由用户自行获得。未来 P6.2 若实现"应用内安装 AI 环境"（随包或
代下载分发 DLC），必须先做 AGPL 材料审查并更新本文件；届时 MIT 主程序与 AGPL
组件的聚合方式、源码提供义务需重新评估。
