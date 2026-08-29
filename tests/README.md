# tests/

测试目录，Phase 1 起使用 pytest。

约定：

- 核心数据结构与物理计算必须有单元测试（见 `AGENTS.md` 第 7 节）
- 数值计算测试使用已知解析解的合成数据（匀速、匀加速、单摆小角度）
- 小型测试资产放入 `tests/fixtures/`（.gitignore 已对小型 png/jpg/svg 白名单）
- 视频/模型等大文件不入库；需要视频的集成测试应在运行时合成或跳过
- GUI 测试放 `tests/gui/`，使用 pytest-qt 与 offscreen 平台；目录细则见 `tests/gui/README.md`
