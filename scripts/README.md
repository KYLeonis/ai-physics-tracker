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
