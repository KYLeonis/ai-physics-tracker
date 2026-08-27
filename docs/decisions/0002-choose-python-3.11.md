# ADR 0002: 选择 Python 3.11 作为开发运行版本

## Status

Accepted (2026-08-27)

## Context

项目需要确定 Python 版本以指导后续环境搭建（Phase 1 起）。约束条件：

1. **DeepLabCut 3.x 官方要求 Python 3.10–3.12**（2026-08 查证官方安装文档：https://deeplabcut.github.io/DeepLabCut/docs/installation.html）
2. PyTorch 稳定版对新版 Python 的轮子支持通常滞后（3.13+ 曾出现 `torch` 安装失败）
3. PySide6（Qt 6）需要长期稳定的 CPython 版本
4. OpenCV、NumPy/SciPy/Pandas 等科学计算栈对主流版本支持最好
5. 当前初始化机器为 macOS arm64（Homebrew Python 3.14），但目标发布平台为 Windows 10/11

候选：3.10（较旧，接近下限）、3.11、3.12。

## Decision

采用 **Python 3.11** 作为项目开发与运行版本（支持范围 3.10–3.12 内的最稳选择）。

- 虚拟环境（conda 或 venv）必须使用 Python 3.11
- 后续 `pyproject.toml` 的 `requires-python` 设为 `>=3.10,<3.13`（具体在 Phase 1 确定，可 revisit）
- DeepLabCut 依赖将在 Phase 4 引入；届时若 DLC 支持范围变化，重新评估并更新本 ADR

## Consequences

- 正面：DLC 3.x + PyTorch + PySide6 + 科学计算栈兼容性最佳；3.11 性能较 3.10 有明显提升。
- 负面：当前 macOS 初始化机器的 Homebrew Python 3.14 不可直接使用，需单独安装 3.11（开发环境搭建成本）。
- 跟进：Phase 4 接入 DeepLabCut 时验证依赖组合；Phase 9 打包时随 PyTorch/DLC 版本 recheck。
