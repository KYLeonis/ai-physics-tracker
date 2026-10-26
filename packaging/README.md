# packaging/

Windows 打包与发布相关内容，Phase 9 起填充：

这是当前通用main的目录状态。另有[2026-10-09 v0.1.0历史Mac测试发行](https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0)，基于发行线提交`54638e484ca3160d2d335e8f78c0580bef21949a`，含独立AI环境安装 / Repair和许可材料；不能据此宣称当前main已完成打包。后续可先核对既有实现与main的差异，再决定复用范围；不默认合并发行线。

- PyInstaller / Nuitka 打包配置（对比后择一，记 ADR）
- Inno Setup / NSIS 安装脚本
- CPU 版 / NVIDIA GPU 版（CUDA Runtime 分发）发布策略
- PyTorch Runtime 与模型文件管理方案

打包产物（`output/`、`dist/`、`build/`）已在 .gitignore 中忽略。
