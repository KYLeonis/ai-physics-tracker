# Independent Review — Publication P1.2

- Date:2026-09-23;Scope:P1.2 S1–S6(experiment 帧集、同帧 4/4 join、引导标注、共享 fixed-check、四 bodypart exporter、真实 DLC smoke),分支 `feat/p1.2-complete-frame-annotation`,commits `1a1886e`…(见 git log)。Reviewer 均为 fresh-context 只读 agent,处置由实现方完成并复测。
- 计划:[P1.2 mini-plan](../../publication/plans/p1-four-landmark-measurement.md) §6 + [执行 mini-plan](../../publication/plans/p1.2-complete-frame-annotation-execution.md);契约 §3。

## R1 — S1 frame-set 专项

Verdict:NEEDS-FIX → 全部修复(`e321f96`)。

| Finding | 摘要 | 状态 |
| --- | --- | --- |
| FS1 (Medium) | frame_set working_zone 无内容语义校验(逆序/负起点可落盘) | CLOSED:构造期对齐 Timeline 先例;回归测试 |
| FS2 (Medium) | serializer 对畸形 working_zone 静默降级 None(违反 fail-closed 声明) | CLOSED:非二元 list 显式 raise;回归测试 |
| FS3 (Low) | session 负帧分支不可达死代码 | CLOSED:删除并注明 |
| FS4 (Low/Info) | P1.1 既有:v1 manifest 携带 publication 键在 v2 写出时静默丢弃(需手造 manifest) | WONTFIX(记录;域互斥已封死语义通道) |
| FS5 (Low) | 实现与 mini-plan 文本偏离(experiment_frames.py 未建) | CLOSED:mini-plan 同步并注明理由 |

## R2 — S1+S2 identity 专项(计划 gate 前半)

Verdict:**PASS**(5 项 Low/Info 全部顺手修复)。核心结论:role↔track 对齐被域不变量结构性排除错位;帧聚类按整数精确;五分类互斥;digest float 单射/无碰撞面;frame_set 与 join 零耦合;duplicate raise 是外部改写防线。修复:ID1(partial 帧坐标损坏进 nonfinite 诊断)、ID2(ROLE_ORDER 复用)、ID3(docstring 写明 defense-in-depth)、ID5(role 重绑 digest 敏感 + 残留计数回归)。

## R3 — S5 export / S4 fixed-check 专项(计划 gate 后半)

Verdict:**PASS**(EX1/EX2 Low 已修,EX3–EX5 记录)。核心结论:plan 划分严格(fixed_check_status fail closed + 独立重 join + 聚合校验三道防线);split_indices 与导出行序一致;exporter 与单轨版行为对齐且 bodypart 顺序错位整体拒绝;bound track 无法经旧单轨 export 路径导出(结构性隔离);S4 子集 digest 语义与契约"对应 frozen comparison"一致(检查帧外改动不失效,探针实证两端)。修复:EX1(坐标元数/有限性 defense-in-depth)、EX2(YAML 非 mapping 显式 RuntimeError)。EX4 为 P1.3 交接提醒:训练 request 必须唯一路径 build→rows→export→split_indices 并冻结全量 label digest。

## S3 测试驱动的 src 缺陷(测试 subagent 发现)

1. 引导按钮死路:`guide_skip/next/finish` 分发在一次原子回滚的编辑批次中丢失,真实 UI 点击无效果 → 已修复并补分发(`b490ea1`)。
2. skip 集合在全跳过时被误清 → 点击会落到被跳过 role → 修复为仅换帧清空(`b490ea1`)。

## Human Review(2026-09-24,经用户授权的自动化执行)

执行方式:用户 2026-09-24 指示"之前写的文档存在理解障碍,由 agent 用 computer use 完成尽可能多的 HR,完成后报告;HR 变动做好 git 管理,先不合并"。故本轮 HR 由 agent 以 macOS 真机 GUI 自动化(辅助功能树 + 原始鼠标/键盘事件 + 截图比对)驱动修复后代码(`f97aaf3`,全量 **981 passed**),GUI 不可达的环节使用与 GUI 完全相同的 session/后端代码路径。主观体验项仅提供功能性证据,最终裁定权在用户。测试对象:test1(Phase_5_2_test,148 帧 1920×1080 单摆视频,4 bound tracks,scale 225 mm / 2.6 px/mm,release 36,起点 168 observations)。

### 结果(协议:[p1.2-human-review.md](../../publication/plans/p1.2-human-review.md))

| 项 | 结果 | 证据(全部为真机 GUI 实测) |
| --- | --- | --- |
| A1 进入引导 | PASS | "Mark landmark frames…"入口 → 引导条 "click the tip (0/4 done; remaining: tip → body_top → body_bottom → pivot)";track 选择被清除仍可标注;四条 role 轨迹点全部可见 |
| A2 顺序标注 | PASS | 147/12/27 三帧共 11 次落点,每次提示推进 tip→body_top→body_bottom→pivot,计数 1/4→4/4 即时更新;落点经视频坐标↔屏幕坐标仿射标定(残差 ~1–3 px)命中目标 landmark |
| A3 完成态 | PASS | 4/4 后显示 "complete (4/4)";两种变体均验证:无后帧时 "Finish guided marking",有后帧时 "Next frame (27)" |
| A4 帧集导航 | PASS | "Next frame (27)" → 跳至帧 27、引导重置 0/4;入口自动跳到帧集首个未完成帧(12)亦验证 |
| A5 Esc 退出 | PASS | Esc → 状态栏 "Browse mode";已标点全部保留(172 = 168+4);重进引导恢复 "Frame 147 complete (4/4)" |
| B1 跳过 | PASS | 标 2 role 后点 "Skip body_bottom" → 提示跳到 pivot 并标注 "skipping: body_bottom";标 pivot 后帧保持 3/4 partial |
| B2 partial 继续 | PASS | partial 帧上 "Next frame (42)" 允许推进;明示 "frame stays partial (never used for training)" |
| B3 Undo/Redo | PASS | Cmd+Z/Cmd+Shift+Z 单步往返(1/4↔0/4)与跨帧 3 步往返(180→177→180)计数精确;skip 集合换帧清除、重开后不残留(按设计) |
| C1 持久化 | PASS | Save→Close→Reopen:180 observations、kmeans 帧集、帧 27 的 3/4 partial 全部保留;引导可重入并正确跳到首个未完成帧 |
| C2 帧集替换 | PASS* | 真实 DLC 3.0.1 kmeans(n=10,8 s)→ 新帧集 (18,19,20,58,64,71,107,116,124,144) 替换旧集;session 层 set→undo(回旧集)→redo(应用新集)→save 闭环。*GUI 按钮路径受阻于 F3,见下 |
| D1 单轨禁用 | PASS | 全窗口不存在 Start learning/Training/Generate trajectory/Suggest/Infer 任何单轨 AI 入口;测量卡明示 "Single-track learning is disabled for experiment tracks; joint AI training arrives in a later phase (P1.3)"(较 P1.1 的"禁用+原因"更强:投影层直接移除,运行时 guard 仍在) |

数据安全一票否决项:引导标注丢点无(observations 单调 168→180,undo/redo 往返精确);重开丢帧集无;undo 破坏状态无。

### Q1–Q4(功能证据;主观判定留给用户真机复测)

- **Q1(引导顺序/提示)A**:每步显式点名当前 role,顺序恒定,计数与剩余列表实时更新。
- **Q2(partial 语义)A**:三处明示——引导条常驻 "Partial frames are saved but never used for training";跳过后 "frame stays partial";partial 帧允许 Next/Finish。
- **Q3(引导条按钮)A**:Skip/Next/Finish 行为全部符合预期(见 B1/B2/A3/A4)。
- **Q4(>10 s 迟疑)B(自动化语境)**:F1 首次入口跳帧失效曾造成迟疑;视频画布滚轮无响应(缩放需走 View 菜单)。请用户真机复测时留意此两点。

**真人首轮复测(2026-09-24 中午,用户本人,PID 24791 新实例)**:用户经引导流程连续完成帧集 18/19/20/58/64/71/116/124 八帧 4/4(35 笔新标注,时间戳间隔 2–4 s,pivot 坐标全部落在真值 ±2 px 内),107 帧缺 pivot(3/4),144 帧未标即停止;反馈"一直没有提示告诉我还要标记多少"。证实 **F4(Medium,UX):引导条只显示当前帧的 role 进度(X/4 done),不显示帧集进度(第几帧/共几帧/剩余帧数),用户无法判断循环有限还是无限**。建议 hint 增加帧集进度(如 "frame set 9/10");修复属 UX 类,由用户裁定修或延后。其余行为与自动化结论一致(HR 流程本身按设计工作,下一帧提示与 Finish 出口均正确)。

**真人二轮复测(2026-09-24 下午)**:用户补完 107 的 pivot 与 144 全帧——**kmeans 帧集 10/10 全部 4/4 complete(磁盘 modified_at 12:59,共 220 observations),P1.2 共享标注数据目标达成**。同轮:用户成功展开 "▸ Adjust this run's settings" 并点击 Suggest Frames(kmeans n=10,后台产物 `data/engines/bf366ebc-…`:工作区 0–147、排除已标 28 帧、120 个候选帧参与聚类、推荐 [24,30,43,60,72,73,74,104,117,121])→ **F3 关闭:折叠按钮对真人可正常操作,自动化环境下的失效应归因自动化栈**。该次推荐结果未保存到 project.json(磁盘帧集仍为已完成的那 10 帧);运行日志/进度提示未向用户解释"120 候选/10 推荐"的区别,归入 F4 同主题。新增 **F5(Medium,UX,用户提出):测量卡不显示帧集状态**——补标时卡片仍只显示通用 "Mark landmark frames",不显示"帧集 9/10、下一缺帧 107 的 pivot"这类直接指引;建议卡片常显帧集完成度并直接命名下一缺帧。与 F4 合并处置,由用户裁定。

### Findings(均非阻塞)

- **F1(Medium,P2)→ 已修复(用户裁定"尝试修复",`fix: retry deferred guide-entry jump`)**:项目加载后的**第一次**引导标注入口不执行帧集跳帧(worklist start_frame 不生效,呈现帧停在原处);同会话退出再进入即正常。离线复现 2/2(两次 project reload 后首入均失败);插桩后多次尝试未复现,守卫全绿,判定为加载窗口期的瞬态竞态。修复:入口跳帧不再依赖单次 seekFrame——`_beginGuideJump` 记录目标帧,200ms 定时器有界重试(至多 25 次/5s),直到呈现目标帧、引导退出或超时提示;Esc/Finish 均清理重试状态。回归测试 `test_guide_entry_jump_retries_after_transient_seek_rejection`(变异验证:无修复时失败);真机重测:reopen → Previous(143) → 首次进入 → 正确落到 144。
- **F2(Low,P3)→ 用户裁定按设计保留(WONTFIX)**:全局 Space 快捷键仅用于播放/暂停,不激活按钮——用户确认为预期行为,关闭。
- **F3(已关闭,2026-09-24)**:真人二轮复测可正常展开折叠区并点击 Suggest Frames——折叠按钮本身无缺陷,自动化环境下的失效率归因自动化栈。关闭。

### 结论

HR-A/B/C/D 全部 PASS(无 N-A),数据安全否决项全部干净。**Q1–Q4 用户真人裁定全部通过(2026-09-24 下午)**;F3 关闭(真人可操作);F2 用户裁定按设计保留;F1 已修复 + 回归测试 + 真机重测通过(982 passed)。按协议 §4 通过标准全部满足:**P1.2 Human Review 通过**,具备合并条件;按用户指示暂不合并、暂不 push,等待用户明确指令后执行 `--no-ff` 合并回 `publication/ejp-damped-pendulum`。F4/F5(帧集进度可见性,UX)转入用户裁定队列,不阻塞合并。

## Verification

- 全量 `python -m pytest`:**980 passed, 9 subtests**(P1.1 基线 921 + P1.2 新增 59);`compileall` 通过。
- 真实 DLC smoke(macOS arm64,DLC 3.0.1):`PYTHONPATH=src python scripts/smoke_test_dlc_p12_dataset.py` → **PASS**:合成四标记视频 → 四 bodypart config → `export_experiment_annotations`(7 行×8 坐标)→ `create_training_dataset` 共同 split(train 4/test 3)→ 独立解析生成 CSV 确认 4 规范 bodyparts 与完整坐标行。结构/生命周期 smoke,不训练、不声称精度。

## Boundary

训练执行与 teacher import 属 P1.3(EX4 交接);θ/QC mask 属 P2;Windows G1–G4 仍为 P6 前门禁。
