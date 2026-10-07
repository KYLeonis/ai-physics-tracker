# ADR-0023 — Mac OpenCV 使用同 ABI 的 LGPL FFmpeg

- Status: Accepted（2026-10-07 用户明确授权直接处理发现的 GPL FFmpeg）
- Scope: publication/P6.4；补充 ADR-0021/0022，不改主程序 MIT。

## Context

host OpenCV4.14.0.94 与 runtime4.11.0.86 的实际 Mac wheels 都打包 Homebrew
GPL FFmpeg7.1.x；上游 README 的 LGPL 概括与实际二进制不一致。只替换独立
ffprobe 或回退 OpenCV 版本不能移除这个闭包。共享 venv、旧 runtime 与用户数据
必须保留。

## Decision

用固定官方 FFmpeg7.1.1 源码/SHA 与 Apple clang/make，自建 LGPL2.1+ 动态库，
关闭 GPL/nonfree/version3、第三方自动发现。使用内置编解码器，保留 libavcodec61、
avformat61、avutil59、swscale8、swresample5、avdevice61 major ABI；不改 OpenCV
源代码/API。固定并校验三个上游 Mac wheels，替换 FFmpeg 动态库并重定位 install
names，仅保留 OpenCV 非 FFmpeg 所需动态闭包，重新签名 Mach-O、重写 RECORD。
原 wheel notices 不删除，追加本项目的替换来源清单。GPL x264/x265 等不进入新包。

host 安装修复后的4.14 wheel。App 携带重打包 wheels 与 hash 清单，新 runtime
仍验证固定原下载，然后使用匹配 original_sha256/name/version/filename 且实际
hash 校验过的随包4.11 wheel。原下载 manifest/schema、项目格式不变；安装日志
记录 replacement 身份，验证完成后才发布新指针。不就地修改已装环境；Repair
新安装生效，高级用户自定义环境仍由用户管理。

随最终二进制准备 FFmpeg 精确源码及构建脚本/配置归档；来源脚本保留全部上游
SHA/动态库 hash。Developer ID 可用时替换 wheels 中的 Mach-O 亦按同身份签名。
公证与真实下载 HR、其他第三方材料义务分别保留门禁。

## Consequences

编解码器以 LGPL FFmpeg 内置实现为准；不带 GPL libx264/libx265 编码器，MP4
导出继续使用 MPEG-4/mp4v，H.264/HEVC解码仍支持。OpenCV build-info 为原始
编译记录，实际动态 FFmpeg license/configuration 检查作为本次库替换证据。
Windows wheel 不做 Mac Mach-O 修复；Windows真机未验收。AI runtime中的其他
组件（例如独立 imageio-ffmpeg 可执行文件）仍按各自许可处理，不能据此宣称
整个 AI runtime 无 GPL。公开 tag/Release 仍须用户另行说“发”。
