# Subphase Plan — Phase 3.3 Interactive Charts

- Issue：[#9](https://github.com/KYLeonis/ai-physics-tracker/issues/9)。
- 工作分支：`feat/p3.3-interactive-charts`。
- 日期 / 状态：2026-08-31 · **已完成，merge `51c1cce`，Issue #9 已关闭**。
- 仓库基线：`main` / `e49132a`；3.2 已由 `3d3ad90` 合并，无需再次合并。
- 规划验证：本地 **260 passed**，`pip check` 通过；这是已有代码基线，不是 3.3 验收。

## Goal

让用户在视频旁查看手工轨迹的位置、速度、加速度和空间轨迹，能在图表与视频之间
定位同一帧，并通过明确的“重新计算”更新过期结果；不改写原始观测。

## Scope

**做**：

- 底部 `QDockWidget` 图表面板，可停靠右侧、浮动、关闭，并从 View 菜单重新打开。
- 五个标签页：x-t、y-t、v-t、a-t、x-y；位置图可选择测量位置/平滑位置，
  速度固定显示 vx/vy，加速度固定显示 ax/ay，不在本次增加另一组大小曲线。
- 当前视频内的多 Track 勾选叠加，沿用 Track 颜色，图例标明轨迹名与分量。
- 提供 SG 窗口/阶数输入和“重新计算选中轨迹”；复用 3.2 数值引擎及 DerivedData。
- 展示无数据、短段无法求导、未标定、过期、单位不兼容、近似时序等状态。
- 正反向帧同步、项目切换隔离、保存/重开后的已有结果显示，以及必要的应用层接口补齐。
- 引入 PyQtGraph；Qt offscreen 测试、独立 review、Human Review 交付。

**不做**：

- 不做 AI 跟踪、物理拟合、θ/ω/α、相图、误差传播、插值补点或替换 SG 算法。
- 原计划不做导出；后续 HR 已批准当前图表 **Save PNG** 例外。CSV/Excel/PDF/视频及
  Phase 8 科学导出仍不在本次范围，完整 HR 变更见末尾收尾补记。
- 不做跨视频/多相机叠加、数据表编辑器、派生结果历史管理器、安装包或 GPU 图表。
- 不改 schema、不迁移历史观测、不写回图表临时 NaN，不自动清理项目文件。
- 不在每个视频帧回调中重新跑运动学计算；不将 3.4 的 Phase 收尾提前宣布完成。

## 已核对的现状与风险

1. 当前 `main` 已包含 Calibration UI 和运动学引擎。`current.md` 的旧下一步仍写着
   合并 3.2；roadmap 顶部仍标 3.0，均应按实际 Git 历史订正为 3.3 规划。
2. 当前未安装 PyQtGraph，也未写入依赖文件。spec 范围为 `>=0.13,<0.14`；建议在
   `pyproject.toml` 保留此范围，在 `requirements.txt` 固定 **0.13.7**，不擅自升至 0.14。
   0.13.7 元数据声明 Python >=3.9、MIT；与本项目 Qt/NumPy 组合仍需真实 smoke test。
3. 本地 `.venv` 为 Python 3.12.13 / SciPy 1.18.1；锁文件是 SciPy 1.17.1，CI 为
   Python 3.11。260 项通过不等于锁定环境通过；确认后先对齐本地项目依赖，再复跑。
4. `DerivedData.frames` 是稀疏源帧号，不能直接连成跨缺测的折线，更不能用数组行号当时间。
5. spec §7.2 的短段说明与 Accepted ADR-0008 D4 不完全一致。沿用 ADR 的缩短奇数窗口
   规则；本次只补 UI 提示和文档澄清，不重设计已完成的数值算法。
6. 真实接口为 `compute_kinematics(track_id, *, window_length=7, polyorder=2)`，返回
   四类 DerivedData 并提交一次 Undo 快照；`derived_data(track_id, kind)` 只返回该组合的
   最后一条，**不是集合属性**。重算替换同 Track/kind 旧记录，不保留历史版本。
7. 已有一个集成缺口：无标定时计算出的 px 数据，在首次添加 active calibration 后
   不会被当前 stale 传播覆盖。3.3 必须补回归和修复，不能只绘图而继续显示“有效的旧像素结果”。
8. 现有引擎把未标定位置也存为 `world_position(unit=px, calibration_ref=None)`，与
   R4 的“无标定不产生物理坐标”措辞有歧义。拟保持兼容读取和已有 kind，不迁移历史记录；
   UI 必须标为像素位置，不能称作世界坐标；确认后先在 spec 澄清这一兼容约定。
9. `compute_kinematics` 当前不检查时序授权；MainWindow 也没有已呈现帧/分析输入变化/
   项目接管的统一通知。接入时需补最小公共入口与通知，不能把后台 `frameDelivered`
   （可能是旧代际）直接接到图表，也不能只监听会在恢复时被 block 的 Track 列表信号。

## 交互与数据契约（拟采用）

### 图表与坐标

| 图表 | 数据来源 | 显示约定 |
| --- | --- | --- |
| x-t / y-t | 测量位置或 smoothed_position 对应分量 | 横轴源视频绝对秒，纵轴数据实际单位 |
| v-t | velocity 的 vx / vy | 同轨迹同色，x 实线、y 虚线，图例区分 |
| a-t | acceleration 的 ax / ay | 同上，单位为长度/s² |
| x-y | 测量位置或平滑位置的两列 | 等比例坐标；世界系 y 向上，像素系 y 向下并标 px |

- 使用实际 `DerivedData.unit`，不能因为标定输入是 mm 就假设引擎输出也是 mm；
  不把 stale 的旧单位结果与当前单位结果混在同一坐标轴上。
- 从 `frames` 经 `frame_to_time` 构造时间，不使用 `row_index/fps`，不改已有点的 `time_s`。
- 按当前 working zone 筛选显示，但时间不从零重置。保留完整派生数据，不为裁剪视图删数据。
- 缺测用内存 NaN/分段连接掩码断线；孤立测量点仍以散点可见。短段没有有效导数时显示
  “连续点不足”，而不是画零值或补值。`values=None` 的外置结果明确提示暂不支持读取。
- 图表适配只消费已知 kind 的二维位置/分量数据；形状不符或未知类型给出状态提示，不猜列。
- 轨迹勾选与视频标注模式分离；操作图表不能新增点、修改 raw 或意外开启标注模式。

### 双向同步

- 四个时间图以已呈现帧更新当前帧竖线，x-y 以该帧的点高亮；缺测帧不吸附邻帧假装有点。
- 时间图点击/拖拽游标先暂停播放，使用 `time_to_frame` 与 working-zone 钳位发出 seek。
  拖拽请求复用已有 latest-wins 解码；程序性游标更新不再次发出 seek，防止回路。
- 在途请求位置与实际帧位置明确区分；正式当前帧高亮仅在解码交付后更新，失败保留旧帧。
- x-y 没有时间轴，不放时间竖线；点击实际轨迹散点可跳到其源帧号。重合点优先当前活动
  Track，再选距当前帧最近者、最后按源帧号排序，使往复轨迹的选择可重复。
- 无媒体仍可查看保存的数据，但禁用视频反向跳转。切换/关闭项目立即解绑旧数据与回调。

### 重算与过期状态

- 默认 SG 为 window=7 / polyorder=2，窗口必须为奇数，且满足二阶微分所需的
  `2 <= polyorder < window_length`；提示窗口单位是帧。无效参数在开始前拒绝，不改已有结果。
- 默认勾选当前 Track，允许选多个同视频 Track；按钮明确计算范围。修改参数只是待应用
  设置，不能把旧曲线标成已使用新参数；显示当前结果的实际 pipeline 参数。
- 标注/标定变更后保留旧图并醒目标注 stale（降透明度 + 文案，不与分量虚线混淆）。
  删除轨迹即移除对应曲线。无结果时提示重算；不暗中在绘图函数内生成持久化数据。
- 计算在后台消费独立快照。结果只提交派生记录，不用整个旧 Project 覆盖当前会话；
  提交前核对项目/视频代际、输入点、Timeline、标定、参数。期间输入变化或用户取消时，
  丢弃旧结果并提示重算；保存、切换、退出均不能让迟到结果复活旧项目。
- 一次多 Track 重算全部成功后提交；失败保留原结果、dirty/历史及 raw。成功结果入既有
  DerivedData 并按现有持久化流程保存；沿用计算可 Undo/Redo 的既有语义，同一次多 Track
  提交形成一个快照，不另造撤销或结果历史管理器。只替换目标 Track 的四种已知 kind，
  其余 Track、custom/未知派生记录及未知字段保留。
- 不绕过 ADR-0007：新计算尊重当前时序授权；已保存结果可以只读查看。近似时序须常驻
  提示名义时间及误差来源，不能宣称速度/加速度精度已经得到保证。
- 普通播放只更新游标/高亮，不重建曲线或自动缩放；数据/图表类型变化时适配一次范围，
  用户缩放和平移后保留视图，提供 Fit 重置。

## Acceptance Criteria

| # | 可独立验证的判定 | 证据 |
| --- | --- | --- |
| P33-1 | 面板可关闭/恢复、停靠/浮动；五个标签页都显示对应量及正确单位 | Qt smoke + Human Review；对应 R7/AC-7 |
| P33-2 | 同视频两条 Track 可叠加/隐藏，颜色/分量图例一致；不混入其他视频或不兼容单位 | 两轨迹/多视频/标定单位切换测试 |
| P33-3 | 稀疏帧与短段不跨缺测连线、不补值，像素/世界 y 方向和 x-y 比例正确 | 合成有间断数据、单点、短段、解析坐标测试 |
| P33-4 | 播放/步进/scrub 更新呈现帧游标；图表 seek 钳位正确，无循环/过期回调覆盖 | 慢解码、29.97 FPS、非零 working zone、连续拖拽测试 + HR；对应 AC-8 |
| P33-5 | SG 默认/合法参数触发选中轨迹重算；非法参数不改数据；近似授权不被绕过 | 应用/Qt 参数与时序状态测试 |
| P33-6 | 标注及标定增改/切换/删除、Undo/Redo 后图表反映正确 stale/valid 状态 | 计算→修改→stale→重算→valid 操作序列；对应 R6/R9/AC-10 |
| P33-7 | 后台完成期间发生保存/输入变更/项目切换/关闭时，不丢 raw、不提交旧结果 | Event 控制任务时机、取消/异常/跨代际回归 |
| P33-8 | 保存/重开显示原 DerivedData、pipeline 与单位；视图操作不令项目 dirty | Repository round-trip + GUI 恢复；对应 AC-9 |
| P33-9 | 锁定依赖 smoke、全回归、既有 macOS/Windows CI 无关键跳过；用户 HR 通过 | 实际命令/CI 记录；需要 push 时单独请求授权 |

## Slices

- [x] Slice 1：确认 PyQtGraph 方案并记录 ADR-0009；同步依赖/开发文档，锁定环境，
  运行真实 PlotWidget + InfiniteLine smoke test，不改变 CI 配置。
- [x] Slice 2：补齐派生数据查询/选择与 Qt-free 图表数据适配，确定 kind/列/单位契约，
  实现缺测断线、working-zone 过滤与数值状态测试；补首次标定 stale 回归。
- [x] Slice 3：QDockWidget + 五标签页 + Track 勾选/图例 + 位置来源切换及状态提示，
  Qt 测试覆盖空态/多轨迹/未标定/重开；先不增加双向 seek。
- [x] Slice 4：双向帧同步、x-y 点选、视图范围保持；验证呈现帧/请求帧隔离、无反馈环。
- [x] Slice 5：SG 参数与后台重算、stale 刷新和项目生命周期整合；补事务/取消/保存竞态测试。
- [x] Slice 6：完整回归、独立 Luna-max review、Human Review；通过后按授权同步 Issue/CI/
  合并与状态，再进入 3.4 的整体集成验收，不直接开始 Phase 4。

每个 Slice 自带测试；确认计划前不创建实现文件、不安装依赖。主模型负责跨模块设计，
Luna-max 仅承担有界接口盘点、测试或独立复审。

最小接口方向（实现时定名）：GUI 的已呈现帧通知/公开 seek、Track 选择通知、分析输入
变化通知、项目接管/关闭通知；应用层的时序权限查询、批次结果校验与原子提交。
Qt-free 数据适配与绘图控件分离，不再把图表和后台任务堆入已有近千行 MainWindow。

## Relevant Context

- `AGENTS.md` §6–§11、`CODE_STANDARD.md`、`docs/workflow.md`、`docs/roadmap.md` Phase 3。
- `docs/spec/phase3-requirements.md` R4–R9、§7.2/§7.4、AC-7…AC-10。
- `docs/spec/data-model.md` §3.8/§5/§6.3；`docs/spec/project-format.md`；ADR-0007/0008。
- `docs/research/open-source-project-map.md` §3.1/§3.3/§6.2/§6.7/§7.9/§7.11；
  `docs/research/raw/openphysics-tracklab-notes.md` 的 Kinematics and plotting、`docs/research/raw/tracker-notes.md`
  的 Kinematics, filtering and plots（只借鉴接口/行为，不复制受限源码）。
- [PyQtGraph 0.13.7 发布元数据](https://pypi.org/project/pyqtgraph/0.13.7/)。
- [PlotDataItem：缺测断线](https://pyqtgraph.readthedocs.io/en/pyqtgraph-0.13.7/api_reference/graphicsItems/plotdataitem.html)、
  [InfiniteLine：交互信号](https://pyqtgraph.readthedocs.io/en/pyqtgraph-0.13.7/api_reference/graphicsItems/infiniteline.html)。

## Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m pip check`、`git diff --check`；另外核对安装版本与 requirements 锁一致。
- 数值/适配使用匀速、匀加速、单摆与间断合成数据；GUI 使用 pytest-qt 和运行时生成视频。
- 既有 Actions 是 macOS/Windows Python 3.11 矩阵，不默认更改 YAML；本机 Python 3.12
  通过不等于 Windows 已通过。Phase 2 已延后的 Windows 真人验收继续单独记录。

### 实现后 Human Review（自动化与复审通过后发起）

启动方式仍为仓库内 `.venv/bin/python -m ai_physics_tracker`（依赖按确认后的锁文件安装）。

1. 打开视频，连续标注至少 9 帧并标定 → 勾选 Track、重算，五个图表有数据和单位。
2. 播放/步进 → 游标跟随；点击/拖拽时间游标与 x-y 实际点 → 视频定位正确，不误标点。
3. 勾选两条轨迹、切换图表、缩放/平移、拖动停靠/浮动、关闭/恢复面板 → 颜色/图例与视图操作符合预期。
4. 修改标定或标记 → 旧结果明确 stale；调整 SG 后重算 → 状态/结果更新，缺测处仍断开。
5. 保存、关闭、重开 → 结果/单位/参数保留；取消未保存切换 → 当前数据不丢失。

届时逐条回答“是/否”；发起后停止等待，不以 computer-use/截图自检替代真人反馈。

## 首次本地交付记录（2026-08-30；历史状态，现状见收尾补记）

- 用户已确认计划及项目内依赖变更；实施到 Human Review。本轮不改 CI、不 push。
- 已确认：本计划范围，以及引入 PyQtGraph 0.13.7、在项目 `.venv` 对齐锁定依赖。
  代价是多一项绘图库依赖与 Qt/NumPy 兼容验证；若 smoke 不通过，停下来报告，不擅自改版本范围。
- 确认后：建立 Issue/工作分支 → Slice 1 验证依赖 → 逐 Slice 实现/测试 → 独立 review → HR。
  原视频和原始标注不迁移，实施中可停止或调整未完成 Slice；不会以破坏性 Git 操作回退。
- 本地功能提交：`f50bb36`（依赖/契约）、`79c4795`（数据适配/批次）、`69c0864`（图表/帧身份）。
  尚未合并、push 或关闭 Issue #9；不宣称 Subphase 已收尾。
- 验证：锁定环境 **297 passed**（Python 3.12.13 / SciPy 1.17.1 / NumPy 2.4.6 /
  PySide6-Essentials 6.11.2 / PyQtGraph 0.13.7）；compileall、pip check、diff check 通过。
  真实 PlotWidget/InfiniteLine、五图曲线数与 x-y 点选 smoke 通过，未用截图代替 HR。
- 复审：Luna-max 交叉独立复审通过。受 agent 数量上限限制，无法新建复审会话，改为
  适配器作者仅审查其未实现的 GUI/批次模块，回归作者审查其未实现的适配器；主模型集成。
  GUI 复审发现旧请求交付/失败覆盖新目标的 Blocker，已通过 DecodeDelivery 请求编号修复；
  真实 worker 的迟到成功/失败、相同帧不同请求编号均有回归，定点复审通过。
- 额外防护：缺媒体时撤销候选复制的旧时序权限；同单位但不同标定的 valid 缓存仅以
  stale 状态显示，不篡改已保存 Project；首次标定使已有像素派生结果失效。
- P33-1…P33-8 的核心数据/交互自动化分支已覆盖；停靠/浮动等实际体验仍需按上节逐项确认。P33-9 的远端
  macOS/Windows CI 尚未运行（未获准 push），Human Review 尚未完成。
- 下一步：等待用户 Human Review 反馈；通过后申请 push 授权运行双平台 CI，再处理
  Issue/合并和 3.4。不得跳过人测直接收尾。

## 收尾补记（2026-08-31）

- 依据最新 `current.md`、[Issue #9 Result](https://github.com/KYLeonis/ai-physics-tracker/issues/9)
  与 Git 历史补齐本地记录；不删除此前首次交付的过程记录。
- merge `51c1cce`；P33-1…P33-9 在 Issue 中已核对完成，Human Review 5 轮通过。
- HR 增量：`7bda4c8` 多选视频 overlay 与 currentItem 标注目标；`b78f10b` / `968489e`
  修复帮助提示（最终为自绘气泡）；`71a33fe` 当前图表 Save PNG，合入 `eed7974`。
- **303 tests**；[CI run 33353856199](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33353856199)
  对应上述 merge，macOS/Windows Python 3.11 jobs 均成功（本轮只读核实）。
- PNG 例外尚需在 3.4 补记 ADR/spec，与原始“不导出”条款保持可追溯关系；不意味着
  Phase 8 完整导出已完成。Phase 2 延后的 Windows 真机事项继续保留。
- 后续为 [3.4 Integration & Phase Close](phase-3.4-plan.md) 的整体闭环验收；不重复3.3独立HR，不直接启动 Phase 4。
