# PHASE_5_PLAN — AI-assisted Annotation & Refinement

> 状态：**Accepted / 5.4 实现已合并但有复核收口项；5.5 mini-plan 草案待确认**
> 日期：2026-09-03
> 范围：只规划 Phase 5；本轮不创建产品代码、不改 schema、不引入依赖。  
> 需求入口：[phase5-requirements.md](../spec/phase5-requirements.md)

---

## 1. 进入基线

- `main @ 7e78053`，进入规划时工作区干净且与 `origin/main` 一致。
- Phase 4 + 4.5 已完成，基线 441 tests；Windows/CUDA 真机验收已批准延至 Phase 9 前。
- F1/F4/F5/F6 已关闭；Phase 5 规划接手 F2（结果 clear/activate/replace）、F3（任务双轨）和 F8（消费原始 confidence），其中 F3 已由 5.0 关闭。
- DLC 当前稳定版和本地安装均为 3.0.1；frame extraction、outlier、refinement、fixed split、snapshot resume/evaluation 已复核。

## 2. 实施原则

1. 先收敛任务生命周期，再添加新 task type。
2. 初始取帧直接复用 DLC；困难帧采用“DLC 输入/primitive + 本项目可解释策略层”。
3. prediction 是候选和参考，不是 label；只有 Correct 产生训练数据。
4. 新 inference 先成为可比较的 completed result，再由用户显式激活，不改 first-wins。
5. 固定 validation series 后才允许跨轮声称改善；coverage/confidence 只作筛查指标。
6. 每个 Subphase 单独计划、实现、验证和 review；用户可感知交互必须 Human Review。

---

## 3. Subphase 计划

### 5.0 — Tracking Pipeline Consolidation（F3）

**状态**：✅ 2026-09-02 完成；Review F3 Closed。结果见 [phase-5.0-plan.md](phase-5.0-plan.md)。

**目标**：消除 4.2/4.3 遗留长任务生命周期，建立 Phase 5 的单一任务骨架。

**Slices**

1. 盘点旧 coordinator 公共调用者与测试，标出统一 runner 仍使用的 prepare/read helpers。
2. 把 start/poll/cancel/cancel_all 行为测试迁移到 `TrackingJobRunner`，统一取消、迟到、归属和恢复断言。
3. 收缩或移除旧生命周期与不可达 CWD fallback；保持训练/推理产品行为不变。
4. 独立 architecture review，确认未来 Phase 5 task 只有一个生命周期入口。

**独立验收**：无新按钮；现有训练/评价/推理 smoke 与全回归不退化，F3 Closed。

### 5.1 — Representative Frame Selection

**状态**：✅ 2026-09-02 完成；Human Review 验收通过。结果见 [phase-5.1-plan.md](phase-5.1-plan.md)。

**目标**：第一次训练前，用少量分布良好的建议帧减少手工拖时间轴。

**Slices**

1. 定义 Qt-free request/result：video identity、working zone、排除帧、N、算法、seed、参数和帧号。
2. 在 `DLCAdapter` 包装 DLC uniform/K-means primitive；mock 提供确定性输出。
3. 接入统一后台 runner、取消和身份校验；长视频用 `cluster_step` 控制扫描量。
4. 最小 GUI：请求建议、列表/跳转、用户自行标注；不自动创建 TrackPoint。

**独立验收**：两种算法、排除已有标签、working zone、seed、取消与不足 N 行为有测试；完成 GUI Human Review。

### 5.2 — Difficult Frame Mining

**目标**：从一个 completed infer run 生成少量、有理由、去重且分布合理的 Top N。

**Slices**

1. 读取 run 原始 HDF5/CSV 的 x/y/likelihood/缺测，不受 Phase 4 导入阈值影响。
2. 生成 uncertainty/missing、jump、局部平滑残差、prior-correction neighborhood 信号，并保留 reason。
3. 实现候选合并 → 归一化排名 → 最小时间间隔 → DLC K-means/时间分桶多样性 → Top N。
4. 合成测试覆盖连续低 confidence、单点 jump、长 gap、候选不足、working zone 和跨 run 拒绝。
5. 冻结单摆人工审计集，记录 Precision@N/review yield 与 lowest-confidence-only 基线。

**独立验收**：连续异常段不垄断；每帧有解释；策略经调整后优于冻结基线。

### 5.3 — Suggested Frame Review & Correction

**状态**：✅ 2026-09-03 完成；Issue [#20](https://github.com/KYLeonis/ai-physics-tracker/issues/20)
已关闭，Human Review 通过。见 [phase-5.3-plan.md](phase-5.3-plan.md)。

**目标**：实现 `查看 → Accept / Correct / Skip → 下一帧` 队列。

**Slices**

1. 定义 review disposition 与 run-scoped progress；确认持久化落点不需要 schema migration。
2. Suggested Frames panel：显示 AI prediction、原因、进度、前后导航。
3. Accept 只记录审核；Correct 复用 manual 事务并保留 prediction；Skip 不造点。
4. 覆盖保存/重开、中途退出、Undo/Redo、track/video 切换和候选已被修正等变化。

**独立验收**：三种动作严格符合 spec；自动化完成后发起 Human Review并停止等待反馈。

### 5.4 — Iteration History & Result Activation（F2）

**状态**：⚠️ 2026-09-03 实现已合并、Human Review 通过；复核发现 2 项 AC 证据/展示缺口与
ADR writer 形态偏差，列为 5.5 实现前 Entry Gate。GitHub Issue 未创建（流程遗漏）。见
[phase-5.4-plan.md](phase-5.4-plan.md)。

**目标**：让不同推理结果可比较、可显式激活，并建立固定验证序列。

**Slices**

1. 冻结 iteration/history 最小字段与 fixed validation series；优先复用 `TrackingRun.config/extra_fields` 和 run 目录。
2. 分离 completed infer result 与 active AI result；无旧结果时首次激活，后续保持为比较候选。
3. 原子 clear/activate/replace：保留 manual、旧 run/原始产物，重建选定 run 观测，派生 stale，支持 Undo/Redo。
4. 历史显示 labels/corrections/params/snapshot/evaluation/coverage/remaining candidates。

**决策门**：若真实实现必须改 schema，先提交 ADR/迁移方案并按项目规则请求用户批准。

**独立验收**：重复推理不再等同“0 inserted 无结果”；两个 completed run 可切换，保存重开、撤销和失败回滚正确；Human Review 通过。

### 5.5 — Training Advisor & Retraining

**状态**：📝 mini-plan 草案待用户确认，见 [phase-5.5-plan.md](phase-5.5-plan.md)。

**目标**：根据已有证据提出有限下一步，并复用 DLC 完成可控 resume/restart。

**Slices**

0. 关闭 5.4 收尾复核发现的 ADR writer、双轮/跨 series 证据与 history details 缺口。
1. 定义 Qt-free Advisor action + evidence + limits，并用表驱动测试固定规则优先级和有限参数档位。
2. 训练请求增加可选 parent snapshot；接通 DLC PyTorch resume/fine-tune，restart 保持现有隔离路径。
3. UI 可手选 mode/source，也可把建议填入表单，但不自动启动。
4. 覆盖 OOM、无/失效 fixed validation、缺失 snapshot、取消/迟到和上下文切换；完成独立 review、
   真实 DLC smoke 与 Human Review。

**独立验收**：规则确定、有限、可解释；无验证数据不声称最佳；真实 DLC resume/restart smoke 通过。

### 5.6 — Refinement Loop Integration & Acceptance

**目标**：把 5.1–5.5 串成一个可完成、可量化的单摆闭环。

**Slices**

1. 从零执行：代表帧 → 标注/固定 validation → train → infer → mine → review/correct → advisor → retrain → reinfer。
2. 记录 fixed-validation RMSE、coverage/confidence、remaining difficult frames、review yield；用户确认后才激活新结果。
3. 全量自动化、真实 CPU smoke、独立 review；修复 findings 后复审。
4. macOS Human Review；逐项更新 roadmap/status/README/AGENTS，合并、CI、push 后停止。

**独立验收**：Phase 5 AC-1–AC-11 全有证据；至少一次冻结基准上的 refinement 改善可复现。Windows/CUDA 不在本 Phase 关闭。

---

## 4. 依赖关系

```text
5.0 F3 cleanup
  ├─→ 5.1 representative frames
  └─→ 5.2 difficult mining → 5.3 review/correction
                              ↓
                    5.4 history + F2 activation
                              ↓
                    5.5 advisor + retraining
                              ↓
                    5.6 integrated acceptance
```

5.1 与 5.2 在 5.0 后技术上可并行，但按一个 Subphase 一条工作分支顺序交付，减少 runner/GUI 冲突。
5.4 不提前决定 Phase 7 模型库结构。

## 5. 验证策略

- 纯策略：合成 confidence/trajectory/history，固定 seed，不依赖 Qt/DLC。
- Adapter：mock 固定契约；真实 DLC 3.0.1 smoke 验证 uniform/K-means、fixed split、resume。
- Session：Accept/Correct/Skip、F2 replace、Undo/Redo、保存重开、派生 stale。
- GUI offscreen：任务取消/迟到/上下文切换、队列导航、历史和 Advisor 表单。
- 真实基准：冻结单摆 validation/audit frames，报告全部 iteration，不挑有利结果。
- Human Review：5.1、5.3、5.4、5.5、5.6 的交互交付前由用户亲测。
- 每个 Subphase 运行 `QT_QPA_PLATFORM=offscreen python -m pytest`；Phase 收尾跑双平台 CI。

## 6. 当前入口

5.0–5.3 已完成；5.4 实现已合并并通过 Review/Human Review，但复核发现 2 项 AC 证据/展示缺口
与 ADR writer 形态偏差，详见 [phase-5.4-plan.md](phase-5.4-plan.md)。5.5 mini-plan 已形成草案，
其 Slice 0 先关闭这些债务，再进入 Advisor；等待用户确认规则阈值、resume/fine-tune 语义与
持久化扩展。

## Result

Phase 5 总计划已接受；5.4 收口与 5.5 mini-plan 待确认。
