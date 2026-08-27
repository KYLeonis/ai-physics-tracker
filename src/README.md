# src/

源代码目录。Phase 1 起建立 Python 包结构（建议 src-layout：`src/ai_physics_tracker/`，随 `pyproject.toml` 确定）。

规划的包内划分（随 Phase 1–4 细化，详见 `docs/architecture.md`）：

```text
src/ai_physics_tracker/
├── core/        # 数据模型与领域逻辑（不依赖 Qt）
├── physics/     # 标定、坐标转换、运动学计算、数据处理
├── ai/          # DeepLabCut/PyTorch 适配器、训练/推理任务
├── gui/         # PySide6 界面
├── io/          # 持久化、导入导出
└── app/         # 应用服务层、后台任务、配置
```

Phase 0 阶段刻意不生成空 Python 文件，实现时再创建。
