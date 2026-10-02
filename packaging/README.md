# packaging/

Publication 产品线的 P6 封装规划见 [P6 execution plan](../publication/plans/p6-packaging-execution-plan.md)（含四个 mini-plan）。2026-10-02 仅完成规划，未创建构建/安装脚本；实施前需补 Windows G1–G4 实机门禁。以下是 main 通用产品线的 Phase 9 原约定。

Windows 打包与发布相关内容，Phase 9 起填充：

- PyInstaller / Nuitka 打包配置（对比后择一，记 ADR）
- Inno Setup / NSIS 安装脚本
- CPU 版 / NVIDIA GPU 版（CUDA Runtime 分发）发布策略
- PyTorch Runtime 与模型文件管理方案

打包产物（`output/`、`dist/`、`build/`）已在 .gitignore 中忽略。
