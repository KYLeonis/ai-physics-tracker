# ADR 0009: 交互图表与派生结果事务

## Status

Accepted（2026-08-30，用户确认 Phase 3.3 计划与项目内依赖变更）

## Context

3.2 已提供四类稀疏 DerivedData，但缺少图表与后台重算入口。绘图若忽略帧号间断、
单位或旧代际回调，会把错误时间/过期数据呈现为有效分析。现有 MainWindow 较大，
需要把图表、绘图数据适配和计算提交分开。

## Decision

1. 采用 PyQtGraph >=0.13,<0.14，开发/CI 锁定 0.13.7；Qt 绑定继续使用 PySide6。
   以 QWidget/PlotWidget 渲染，不启用 OpenGL，不引入第二套 Qt 绑定或导出功能。
2. GUI ChartPanel 负责五类图表与点击/拖拽信号；application 图表适配只消费 Project
   值对象，不依赖 Qt。适配按源帧号断线，以 Timeline 计算绝对时间；NaN 仅在内存显示。
3. 正式游标只跟随已呈现帧。拖拽目标为独立请求指示，解码交付前不能冒充当前帧；
   程序性更新不反向 seek。x-y 点击散点按携带的源帧号导航，不用横坐标当时间。
4. 计算使用独立 ProjectSession 快照；主线程提交时复核输入签名与 GUI 项目代际，
   只合并目标轨迹的四种派生结果。整个批次一次 Undo 快照；失败、取消或输入变化不提交。
   保存不丢失计算期间的用户修改；切换或退出不接收旧结果。
5. 沿用已有 `world_position(unit=px, calibration_ref=None)` 的兼容表示，不迁移格式。
   UI 按单位及标定引用区分像素/物理位置；首次 active 标定也必须使旧像素派生结果 stale。
   继续采用 ADR-0008 的短段窗口规则，不跨缺测插值。
6. 新重算要求当前时序授权；缓存数据允许只读查看，近似时间及导数精度限制持续可见。
   计算参数、时序近似来源和既有未知字段不能因图表或重算被静默丢弃。

## Consequences

- 不改 schema、raw 坐标/时间或媒体；图表查看不改变 dirty。
- 多出一个轻量绘图库及对应兼容性测试；首次安装只影响项目虚拟环境。
- 取消是丢弃结果并在轨迹间检查取消，不能强行中断 SciPy 的一次计算。
- Human Review 验证交互；macOS/Windows offscreen CI 仍需在获准 push 后真实运行。
- 依据：[PyQtGraph 0.13.7](https://pypi.org/project/pyqtgraph/0.13.7/)，
  [PlotDataItem](https://pyqtgraph.readthedocs.io/en/pyqtgraph-0.13.7/api_reference/graphicsItems/plotdataitem.html)。
