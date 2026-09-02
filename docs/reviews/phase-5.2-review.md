# Review Record — Phase 5.2 Difficult Frame Mining

> **用法**：一个 subphase 一个文件，贯穿整个审查生命周期。
> **审查依据**：diff 与 Context 文档判断。流程规则见 `docs/workflow.md` §6。

- Subphase / Issue：5.2 — Difficult Frame Mining · [#19](https://github.com/KYLeonis/ai-physics-tracker/issues/19)
- Review 范围（commits）：
  - Slice 1：`d67f57d`（raw prediction 入口 + mining request 身份）
  - Slice 2：`7af74a0`（纯挖掘策略）
  - Slice 3 + Slice 1 审查修复：`9c14405`
  - Slice 2 审查修复：`dcb6819`
  - Slice 4：`5feefd1`（benchmark 工具链 + 真实开发集审计表）
- Context：`docs/spec/phase5-requirements.md` R2/R8、AC-2/3/4/10、`docs/status/phase-5.2-plan.md`、ADR-0008（savgol 分段）
- 轮次：R1 2026-09-02（Slice 1 独立审查）· R2 2026-09-02（Slice 2 数值审查）

## Checklist

**正确性**

- [x] 全帧 raw prediction 读取复用既有整批校验；低置信度/缺测不丢失（AC-2）
- [x] request/result 绑定 run/video/track/model/预测产物，指纹基线 + run 从属目录校验（R2.1/R8.2）
- [x] 四类信号、归一化、加权、时间去重在合成轨迹上被固定；同输入/参数/seed 结果相同（AC-4）
- [x] pipeline 顺序固定；连续异常段不垄断 Top N；放宽如实记录（AC-3）
- [x] 视觉多样性只复用 5.1 K-means（显式候选集）；失败按分数补齐并记录 diversity_status
- [x] 统一后台 runner、取消、原子结果；worker 不持有活动 session，不创建 TrackPoint
- [ ] 真实单摆开发集标注 + 冻结审计集 v1 与 lowest-confidence 基线比较（AC-10）
  —— **待用户人工标注**：开发集审计表已生成（`docs/benchmarks/phase-5.2-development.csv`，
  17 帧），标注后运行 score；冻结审计集须在开发集调参完成后从**不同的 infer run** emit。

**质量**

- [x] diff 无范围外改动（F3b 改名为 #18 顺带项，已获用户批准的计划内安排）
- [x] 命名符合 CODE_STANDARD §3.2 词汇表；NaN 语义引用 data-model.md §3.5
- [x] 数值测试使用解析已知解（手算 median/MAD/z、匀速直线合成轨迹）；MAD=0 与 MAD>0 两分支均覆盖

**流程**

- [x] 提交信息符合 Conventional Commits；无 ADR 级变更（复用 ADR-0008/0011/0012 既有决策）
- [x] 无 GUI 变化，不触发 Human Review（候选解释的真人体验随 5.3 队列验收）

## Findings

### R1 — Slice 1 独立审查（code-reviewer subagent）

结论 **request-changes**，全部处置如下：

| # | Severity | 问题 | 处置 | Commit |
| --- | --- | --- | --- | --- |
| H1 | High | 预测产物身份只有半套：无推理时指纹基线、无 run 从属校验，可被整批替换/串 run | `read_inference_result` 持久化 `prediction_file_info` 基线；prepare 校验产物必须位于本 run 的 `data/engines/<run_id>/` 目录、拒绝绝对引用、比对基线（旧 run 无基线按现状采集并容忍，测试钉住） | `9c14405` |
| M1 | Medium | 缺 `track.video_id == run.video_id` 交叉校验 | 已加 | `9c14405` |
| M2 | Medium | prepare 拒绝分支约半数无测试 | 补模型/视频缺失、legacy 容忍、无产物引用、绝对引用/串目录/篡改 7 例 | `9c14405` |
| M3 | Medium | HDF5 路径无测试（AC-2 明写 HDF5/CSV） | 补 h5 往返保留 NaN/低置信度用例（importorskip pandas/tables） | `9c14405` |
| L1 | Low | `MiningParams` 超大整数抛 OverflowError 而非 ValueError | `float()` 包 try/except | `9c14405` |
| L2 | Low | `zone_start/zone_end/fps_nominal` 无类型检查（bool 可通过） | 补 type guard | `9c14405` |
| L3 | Low | 绝对路径绕过逃逸检查 | 预测产物引用强制相对；模型路径保留旧绝对路径容忍（既有兼容语义，docstring 已注明） | `9c14405` |
| L4 | Low | 适配器 `frame_count` 可选，漏传静默关闭覆盖率校验 | 协议层改为必传 | `9c14405` |
| S1 | Suggestion | `_file_info` 出现第二份实现 | **延期**：两处调用点，下次共同触碰时合并（记入遗留） | — |
| S2 | Suggestion | 跨模块 import 私有 `_project_path` | 接受：仓库既有先例（tracking_job→inference_job） | — |
| S3 | Suggestion | prior 集合未按 zone 过滤；权重报错不指名字段 | 策略层已裁剪到 zone（有注释）；权重报错逐字段命名 | `9c14405` |
| S4 | Suggestion | `RawPrediction` 严格 float 拒绝 int/np.float32 | 接受：构造边界从严，内部构造路径均经 `float()` | — |

### R2 — Slice 2 数值审查（code-reviewer subagent）

结论 **approve-with-comments**（代码无数值缺陷，覆盖与舍入需补），全部处置：

| # | Severity | 问题 | 处置 | Commit |
| --- | --- | --- | --- | --- |
| 1 | High | MAD>0 主统计路径（z≥3.5、1.4826 常数）零测试覆盖 | 手算 median/MAD/z 单元测试 + 带噪轨迹 jump 判定测试 | `dcb6819` |
| 2 | Medium | `round` 半偶舍入使实际间隔低于请求最小值（0.25s@10fps→0.2s） | 改 `ceil` 并加注释与断言 | `dcb6819` |
| 3 | Low | 快照未记录放宽后最终生效的间隔 | `effective_gap_frames` 入 outcome/snapshot | `dcb6819` |
| 4 | Low | greedy 去重无早停，最坏 O(P·K) | cap 处早停（输出不变，测试锁定） | `dcb6819` |
| 5 | Low | z 阈值允许 0（整 zone 入池） | 校验改为严格正 | `dcb6819` |
| 6 | Nit | percentile 并列分组裸 `==` | 注释说明刻意精确相等（信号已量化） | `dcb6819` |

## Review Log

### R1 — 2026-09-02 · Slice 1（subagent 独立审查）

- 范围：`d67f57d`；隔离 worktree 跑被审 commit 测试 44/44 通过
- 结论：request-changes（H1 身份绑定半套 + 测试缺口）；修复见上表，随 `9c14405` 落地

### R2 — 2026-09-02 · Slice 2（subagent 数值审查）

- 范围：`7af74a0`；干净快照 530/530 通过；带噪轨迹探针验证 MAD>0 分支行为正确
- 结论：approve-with-comments；High（覆盖缺口）与 Medium（舍入）已在 `dcb6819` 关闭

### R2.5 — 2026-09-02 · 真实数据语义复审（AI_test2）

- 触发：真实规范训练 run（148 帧，defaults 50/8/mps）上策略返回 0 候选——信号计算正确
  （全部置信度 ≥0.65、jump z≤1.1、residual z≤3.06），暴露触发式池的产品死路
- 处置：`fddc391` 增加 screening 补齐语义（见 plan §Proposed Defaults 细化注记），
  队列不再空转；571 tests 全绿

### R3 — 待办 · 冻结审计集评估

- 开发集审计表已生成并入库（真实 2767 帧单摆 run）；**等待用户标注**后 score；
  开发集调参完成后从不同 infer run emit `phase-5.2-audit-v1.csv` 并写
  `phase-5.2-report.md`，AC-10 结论回填本节。

## Final Verdict

- [x] 修改后通过（R1/R2 findings 全部处置；代码、测试与工具链收口）
- [ ] 通过（首轮无 finding）
- [ ] 需要重做

- 最终结论：代码路径与基准工具链通过审查；AC-10 的真实数据比较因需要人工标注，
  作为明示遗留项由用户完成后回填 R3，5.2 方可整体收尾。
- 日期 / 依据轮次：2026-09-02 · R1 + R2（R3 待补）
