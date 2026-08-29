# src/

源代码目录。Phase 1 起建立 Python 包结构（建议 src-layout：`src/ai_physics_tracker/`，随 `pyproject.toml` 确定）。

包内划分（以 `CODE_STANDARD.md` 的分层与命名为准，随 Phase 2–4 扩展）：

```text
src/ai_physics_tracker/
├── domain/          # 数据模型、Timeline、TrackStore、标定（不依赖 Qt）
├── infrastructure/  # 项目持久化、未来的视频/引擎适配器
├── application/     # Phase 2 起：用例编排与后台任务
└── gui/             # Phase 2 起：PySide6 界面
```

只在对应 Phase 确有实现时创建模块，不预生成空文件。
