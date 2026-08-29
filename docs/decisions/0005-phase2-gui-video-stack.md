# ADR 0005: Phase 2 采用 PySide6 Qt Widgets 与 OpenCV headless 视频适配器

## Status

Accepted (2026-08-29)

## Context

Phase 2 要交付第一版桌面视频分析应用。Phase 1 只有 Qt-free 领域模型与项目持久化，
尚无 GUI、视频解码器、播放会话或 GUI 测试工具。路线图已把 PySide6 与 OpenCV
列为首选，但要求进入 Phase 2 时正式确认。

约束：

1. 目标平台是 Windows 10/11 x64，开发平台是 macOS Apple Silicon；两端都要有
   Python 3.11 wheel 和 CI 验证。
2. GUI 不能直接持有 `cv2.VideoCapture`；领域层不能 import Qt。
3. 本项目不用 `cv2.imshow`，OpenCV 只负责解码/图像处理。
4. Phase 2.1 先验证最小同步读帧闭环；后台解码、请求合并和缓存进入 2.2。
5. OpenCV 的平均 FPS/帧数元数据不足以可靠判断 VFR。时序未验证的视频可以浏览，
   但在后续完成 CFR/VFR 探测前不得登记为可分析项目。

## Decision

1. GUI 使用 **PySide6 Qt Widgets**。Phase 2.1 锁定
   `PySide6-Essentials==6.11.2`；需要额外 Qt 模块时再显式增加 Addons。
2. 视频后端锁定 `opencv-python-headless==4.14.0.94`，并直接锁定
   `numpy==2.5.2`。选择 headless 是为了避免 OpenCV 自带 GUI/Qt 插件与 PySide6
   重复；项目中禁止 `cv2.imshow`。
3. GUI 测试使用 `pytest-qt==4.5.0`，CI 设置 `QT_QPA_PLATFORM=offscreen`。
4. 分层边界：
   - `application/` 定义 `VideoReader` Protocol、RGB `DecodedFrame` 和 Qt-free
     `VideoSession`；
   - `infrastructure/` 实现 `OpenCVVideoReader`，在适配器边界完成 BGR→RGB；
   - `gui/` 只依赖 application/domain，不直接 import `cv2`；
   - `domain/` 保持 Qt/OpenCV/NumPy 无关（既有数值对象除外）。
5. `python -m ai_physics_tracker` 是开发期桌面入口。Phase 2.1 只支持打开、显示、
   前后步进和帧号跳转；连续播放与异步解码进入 Phase 2.2。

## Consequences

- macOS/Windows 使用同一 Qt Widgets 代码与 wheel；应用层导航逻辑可脱离 GUI 测试。
- 运行环境体积和 CI 安装时间明显增加；发布时必须履行 Qt LGPLv3、OpenCV
  Apache-2.0、wheel 内 FFmpeg/第三方组件的许可义务。
- OpenCV 4.x 是刻意的保守选择；新发布的 OpenCV 5.x 在完成兼容性 spike 前不采用。
- 未来可在不改 GUI/领域 API 的前提下增加 FFmpeg/PyAV reader，但新增第二后端时应
  用真实用例复核 Protocol，而不是预先扩张接口。
- Phase 2.1 不声称可靠支持 VFR；后续 Subphase 必须在项目登记前完成时序验证与
  CFR 转码提示。
