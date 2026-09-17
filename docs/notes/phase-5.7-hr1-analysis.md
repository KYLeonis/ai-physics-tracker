# Phase 5.7 Human Review — Round 1 Findings 分析与修复方案

- 日期：2026-09-17；来源：用户实测反馈（7 条）。
- 状态：**待用户确认后执行**。本文档只做根因分析与方案，不改代码。
- 对应实现：`main @ 62205e3`（feat/p5.7-interaction-redesign 已合并）。
- 处置原则：全部为交互层修复，**不改 domain/persistence 契约**（ADR-0013/0014/0015/0016
  全部保持）；修复后重跑自动化并再次发起 Human Review。

---

## Finding 1 — 右侧窗口未自适应屏幕，部分内容超出屏幕

### 为什么

右侧 "Acquire trajectory" 面板是 `QDockWidget`，其初始宽度取自内容 sizeHint。
面板内容为纵向长堆叠（任务卡 + 进度 + 依据 + 折叠表单 + 审核组 + 历史），其中
多处子控件有固定 `setMinimumHeight` / 双列并排的表单布局有最小宽度；当内容最小
宽度超过 dock 分配宽度时，内层 `QScrollArea` 只在必要时出滚动条，而 dock 自身
初始可能过宽（把视频挤占）或在较矮屏幕上纵向放不下整卡。窗口初始尺寸固定
`resize(960, 720)`，没有针对小屏的约束。

### 怎么改

1. dock 装配时用 ` QMainWindow.resizeDocks` 给右侧面板一个合理初始宽度
   （约 380–420px），并允许用户继续拖动调整；
2. 面板内容横向 sizePolicy 统一为 Expanding，移除造成最小宽度溢出的固定值；
   "调整本次设置"内的双列表单在窄面板下改为单列（宽度阈值触发）；
3. 主动作行（卡片主按钮）在任何布局下保持可见（纵向滚动兜底）；
4. 新增小窗口冒烟测试（如 1024×640）：断言卡片主按钮可见、滚动条可用、
   无固定最小宽度把内容推出视口。

### 验收

1024×640 与常见笔记本分辨率下，右侧面板不遮挡主操作，无内容超出屏幕不可达。

---

## Finding 2 — 推理后画面上看不到 AI 轨迹，重新标点没有参照

### 为什么

这是 ADR-0014 的候选隔离契约的直接结果：推理完成只登记 completed infer run，
观测**不进入** TrackStore；视频画面上的 marker 只渲染当前**已采用**结果的
effective 投影。因此候选生成后画面上没有任何 AI 轨迹可看，用户只能靠审核队列
里逐帧的 prediction 快照标记判断对错——"不知道 AI 选对了没有"是真实缺口。
设计文档 §6.5 其实要求"视频切到明确标识的候选预览"，这一层在实现中被遗漏了。

### 怎么改（视图层候选预览，不改隔离契约）

1. `TrackingActions` 在投影显示存在候选时，从候选 run 的
   `extra_fields["observations_path"]` 用既有 `read_observation_exchange()` **只读**
   加载候选观测点（失败则不显示预览，不影响任何流程）；
2. `VideoView` 新增独立的 **preview marker 层**：与正式 marker 分离的图元集合，
   用不同颜色的空心菱形渲染，图例常显 "Preview: version N (not adopted)"；
3. 预览层是纯视图状态：不进 session、不进 effective 投影、不参与分析与 dirty；
   候选被采用或不再是候选时立即清除；
4. 与审核队列联动：审核跳帧时预览点随帧显示，Correct 的落点参照就是预览点。

### 验收

生成轨迹后，不打任何标注即可在视频上看到候选轨迹（明显区别于当前采用轨迹）；
采用该候选后预览层消失、正式轨迹更新；项目 dirty 状态不因预览变化。

---

## Finding 3 — Correct 模式光标不变十字，点击瞬间才变并直接跳帧

### 为什么

十字光标不是设在 viewport，而是设在 `_pixmap_item` 上（`VideoView._update_cursors`，
这是此前修过的 scene-hover 覆盖问题的正确做法）。但 **每次解码送帧都会重建
pixmap item**：进入 Correct 时 `startCorrectCurrent` 通常伴随 `seekFrame(candidate帧)`，
异步解码送达后新 pixmap item 没有重新应用光标 → 光标回到箭头；用户点击时
`_annotation_mode` 仍为真（点击有效、提交修正、退出模式），光标在这一瞬间被
刷新，随后自动跳到下一候选帧——形成"点击瞬间变十字、接着跳走"的观感。

### 怎么改

1. 在帧呈现路径（新 pixmap item 创建/替换处）统一调用 `_update_cursors()`，
   使任何模式下的光标跨帧保持；
2. `startCorrectCurrent` 与 `cancelCorrectMode` 之后各主动刷新一次光标；
3. 新增回归测试：进入 Correct 模式 → 等待送帧 → 断言 `_pixmap_item.cursor()`
   为 CrossCursor；Esc 退出后恢复 ArrowCursor。

### 验收

点击 Correct 按钮后（含伴随跳帧），鼠标移到视频上即为十字；点击提交后恢复箭头。

---

## Finding 4 — Check 与 Adopt 语义不清；检查像无止境标注；审核中无取消

### 为什么

三个叠加原因：
1. **文案**：卡片只写 "Check this trajectory / Adopt this trajectory"，没有解释
   check=逐帧确认候选哪里错、adopt=把候选设为当前分析轨迹，两者是先后关系；
2. **控件分离**：审核进行中，卡片的主动作是 "Review next frame"，而真正的
   A/S/C 按钮在下方审核组里，加上 Finding 1 的空间问题，用户感知就是
   "又是标点"；
3. **无退出**：审核队列一旦开始没有显式"结束检查"入口（Esc 只退出 Correct
   落点模式，不退出队列），pending 永远挂在那里。

### 怎么改

1. **文案与流程**：Check 按钮改 "Check this trajectory (mark wrong positions)"；
   Adopt 改 "Adopt for analysis"；候选就绪卡的说明加一句两步关系
   （"Check finds wrong positions; adopting makes it the trajectory your charts use"）；
2. **审核态卡片升级**：pending>0 时卡片标题为
   "Current: checking version N (not adopted) · M of K frames"，并把
   Accept / Correct / Skip 三个动作直接呈现在卡片动作区（复用同一信号，不新建
   执行路径），原审核组保留在面板作为完整列表；
3. **新增 "Finish checking" 按钮**：随时结束本批审核——批次状态保留（pending
   计入分析限制，正是现有语义），卡片回到采用结论；不删除任何记录；
4. **Correct 模式可见取消**：correcting 状态下卡片/审核区显示
   "Cancel placement (Esc)" 按钮，调用既有 `cancelCorrectMode`。

### 验收

用户能说出 check 与 adopt 的区别；审核中随时可结束且知道剩余未判帧去哪了；
Correct 有可见取消。

---

## Finding 5 — 全程没有标定提示，坐标一直是像素

### 为什么

标定按设计是可选、可后置的能力：流程不强制，且唯一提示在分析页来源条
"Units: px (no calibration)"——用户在前段流程完全看不到。设计 §6.1 要求
"无标定时明确只能用像素量，并提供设置尺度入口"，提示层没有做够。

### 怎么改

1. 投影 `AnalysisFacts.limitations` 增加
   "no scale set — positions and charts are in pixels"（无活动标定时），
   状态头 limitations 行即刻可见（该行 5.7 已实现）；
2. "Start learning" 就绪卡与候选采用卡的次要动作增加 **"Set scale & units"**
   （路由到既有 drawScale 标定模式并切到 Experiment setup 工作区，不新建能力）；
3. 采用卡 evidence 在无标定时提示 "positions are in pixels until a scale is set"。

### 验收

不设标定时，状态头与采用卡都能看到像素限制；一键进入设置尺度流程；设完限制消失。

---

## Finding 6 — 刚生成一次轨迹后又提示 Generate trajectory，导致重复生成

### 为什么

`learned_not_generated`（"已学习未生成"）用**时间戳**比较最新 completed train
与最新 completed infer（`latest_train.created_at > latest_infer.created_at`）。
平台时钟粒度与快速连续操作下，该判据与用户心智（"这个模型还没应用到视频"）
不符，产生已经生成过却再次提示 Generate 的状态。

### 怎么改

把判据从时间戳改为**lineage 匹配**：取最新 completed train run T；若不存在
completed infer run 满足 `config.training_run_id == T.run_id`，才显示
Generate trajectory。语义精确等于"最新模型尚未应用"，对时间戳平局免疫；
继续优化（新 train）后自然再次出现 Generate。

### 验收

同一次学习只提示一次 Generate；优化后重新出现；重复生成不再由误导触发。
回归：`test_projection_from_real_session_lifecycle` 扩展 lineage 断言。

---

## Finding 7 — 关键步骤没有保存

### 为什么

自动保存目前只有两个触发点：AI 任务完成后（`projectActions.autosave`）与
每 10 个标注点。采用轨迹、审核批次完成、检查帧冻结、Correct 修正这些**改变
项目数据的关键事务**都不保存，异常退出即丢。

### 怎么改

在以下事务成功后调用既有静默 `projectActions.autosave(reason)`（busy 保护、
无对话框、保存期间新改动由 `accept_saved_snapshot` 保留——均为既有语义）：

1. `_adopt_candidate` 成功（activate/replace）之后；
2. 审核批次 pending 归零（批次完成）时；
3. `_confirm_fixed_check_set` KEEP 冻结检查帧之后；
4. 每次 Correct 提交之后（修正点少而重要）。

边界：保存清空应用内 Undo 是既有契约（ADR-0013），不因新增触发点改变；
autosave 失败静默跳过（既有实现），失败可见性维持现状（保存失败在显式保存时
独立显现）。

### 验收

完成上述任一步后直接杀进程重开，对应变更已在磁盘上。

---

## 实施顺序与测试计划

| 序 | Finding | 主要改动面 | 验证 |
| --- | --- | --- | --- |
| 1 | F6 lineage 判据 | `workflow_projection` | 投影单测扩展 |
| 2 | F3 光标跨帧 | `video_view` + review actions | GUI 回归 |
| 3 | F2 候选预览层 | `video_view` + `tracking_actions` | GUI 隔离/显示测试 |
| 4 | F4 审核 UX | `task_panel` + `tracking_actions` + 投影文案 | GUI 测试 |
| 5 | F5 标定提示 | 投影 + 卡片次要动作 | 投影/GUI 测试 |
| 6 | F7 关键步保存 | `tracking_actions` + review actions | GUI 测试（磁盘断言） |
| 7 | F1 面板自适应 | `task_panel` + dock 装配 | 小窗口冒烟 |

全部完成后：全量 pytest + compileall + 双平台 CI → 更新
`docs/reviews/phase-5.7-review.md`（HR round 1 记录与处置）→ **再次发起
Human Review**（重点复测上述 7 条原场景）。

## 明确不做

- 不自动采用候选、不自动串联训练/推理（Finding 2 用视图预览解决，不动 ADR-0014）；
- 不强制标定（保持可选后置，只加提示与入口）；
- 不改 Undo/保存契约（F7 只加触发点）；
- 不重做视觉样式。
