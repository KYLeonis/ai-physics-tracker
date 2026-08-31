# ADR 0010: 当前图表 PNG 快照

## Status

Accepted（2026-08-31；补记 3.3 Human Review 已批准、已合并的交付）

仅取代 ADR-0009 Decision 1 的“不引入导出功能”排除条款，其他决定保持不变。

## Context

3.3 原计划排除导出，后续 Human Review 明确要求保存当前图表图片，形成
`71a33fe`，随 `51c1cce` 合入 main。原 ADR/spec 尚未反映这一例外。
3.4 只补齐记录和回归，不重新设计已通过 HR 的功能。

## Decision

1. 保留图表面板的 Save PNG，保存当前 tab 的 PlotWidget 显示快照，包含该图中的
   曲线、坐标轴、图例和当前可见游标。通过现有 Qt grab/save 完成，不增加依赖。
2. PNG 是当前显示内容，不是可复现的科学数据文件；面板外的 SG 参数和近似时序说明
   不包含在此快照中。实验依据仍应连同 Project 的 raw/DerivedData/pipeline 保存，
   不用 PNG 单独证明导数精度。3.4 验收记录这一限制，不自动增加水印或新格式。
3. 取消不产生输出，保存失败应报告；操作不得修改项目 raw、标定或派生数据。
4. CSV/Excel、矢量/PDF、定版科学出图、批量导出及视频导出仍留 Phase 8。

## Consequences

- 用户可保存眼前图表；使用系统文件选择器和既有 Qt，无新架构或安装要求。
- 图片受当前视图范围、窗口尺寸和设备像素比影响，不承诺出版级布局或固定 DPI。
- 3.4 增补带数据的当前 tab、取消与失败回归；真机外观仍由 Human Review 判断。
