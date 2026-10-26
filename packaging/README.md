# packaging/

Mac教学试用与后续Windows正式发布的打包入口。当前main尚无本轮安装包；[首发目标](../docs/spec/first-deliverable-target.md)已于2026-10-26冻结，先6.5完整验收及最小科学导出 / 合成核查，再准备Mac arm64教学试用包。

另有[2026-10-09 v0.1.0历史Mac测试发行](https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0)，基于发行线提交`54638e484ca3160d2d335e8f78c0580bef21949a`，含独立AI环境安装 / Repair和许可材料。准备本轮试用包时先核对既有实现与main的差异，按[回移档案](../docs/status/main-backport-backlog.md)受控复用，不默认合并发行线。

本轮要求：试用者无需配置Python；首次联网准备后，已准备的支持流程离线使用；包不附第三方预训练 / 教师权重，从核实来源首次下载。接受未公证包的单应用手动放行，不要求关闭全局保护。原创代码MIT、实际随包组件 / 二进制 / 权重按各自条款准备材料，见[许可边界](../docs/licensing.md)。构建版本、环境锁定、离线 / 恢复及安装步骤须在实施mini-plan中固定和验证；本次未构建或上传新包。

后续Windows正式发布仍由Phase 9推进：

- PyInstaller / Nuitka 打包配置（对比后择一，记 ADR）
- Inno Setup / NSIS 安装脚本
- CPU 版 / NVIDIA GPU 版（CUDA Runtime 分发）发布策略
- PyTorch Runtime 与模型文件管理方案

打包产物（`output/`、`dist/`、`build/`）已在 .gitignore 中忽略。
