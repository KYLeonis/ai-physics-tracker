# packaging/

Windows 打包与发布相关内容，Phase 9 起填充：

- PyInstaller / Nuitka 打包配置（对比后择一，记 ADR）
- Inno Setup / NSIS 安装脚本
- CPU 版 / NVIDIA GPU 版（CUDA Runtime 分发）发布策略
- PyTorch Runtime 与模型文件管理方案

打包产物（`output/`、`dist/`、`build/`）已在 .gitignore 中忽略。
