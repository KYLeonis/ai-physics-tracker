# EJP Publication Line: Damped Pendulum Study

本目录与所在分支（`publication/ejp-damped-pendulum`）是 AI Physics Tracker 为计划投稿至 *European Journal of Physics* (EJP) 的阻尼单摆研究（damped-pendulum manuscript）建立的专用 publication line。

---

## 1. Purpose

* **论文支撑**：支撑面向 *European Journal of Physics* 的单摆物理测量与分析论文，提供可验证、可复现的专用软件基线。
* **复现与归档**：用于存放论文相关的软件基准、复现材料、配置、审稿修订（revision changes）追踪与最终论文出版归档（publication archive）。
* **分支边界**：本分支**不是**通用 AI Physics Tracker 桌面应用的产品开发主线；通用功能研发、架构重构与后续 Phase 规划始终在 `main` 主分支上进行。

---

## 2. Baseline

* **Baseline Commit SHA**: `62239faee60ad45770d81aeaf2e17abdcada2dfb`
* **Baseline Immutable Tag**: `ejp-damped-pendulum-baseline-phase5.7`
* **Creation Date**: 2026-09-18
* **Repository State**: Phase 5 / Subphase 5.7 已全面收官并通过 Human Review 与双平台 CI；Phase 6（Advanced Physics Analysis）尚未开始实现。

---

## 3. Scope

未来允许有选择性进入本分支的内容：

* 与论文直接相关的稳定 tracking / calibration / analysis 能力
* 角度轨迹重建（Angular trajectory reconstruction: $\theta$, $\omega$, $\alpha$）
* 相空间分析（Phase-space analysis）
* 周期与衰减分析（Period analysis）
* 物理模型拟合与模型比较能力（Fitting / model-comparison capability）
* 复现脚本、Notebook 与实验配置（Reproducibility scripts / notebooks / configs）
* 运行环境规范与锁定清单（Environment specification）
* 论文支撑文档与图表生成说明（Manuscript-support documentation）
* 实验复现必需的缺陷修复（Reproduction-required bug fixes）

---

## 4. Non-goals

以下内容**不**应仅因为 `main` 存在就自动同步或合入本分支：

* 与论文研究无关的通用平台功能
* 投机性或实验性的多目标跟踪（Multi-object tracking）
* 与论文工作流无关的 UI/UX 试验
* Phase 7+ 的非论文必需能力（如通用模型库管理、泛化桌面打包、非单摆特定插件等）

---

## 5. Synchronization Policy

* **主要同步方向**：
  ```text
  main → publication/ejp-damped-pendulum
  ```
* **通用缺陷修复流程**：
  1. 通用 bug 与核心算法修复必须**优先在 `main` 上修复并验证**（保持测试套件与 CI 完整覆盖）；
  2. 验证通过后再挑选（cherry-pick）或受控同步到 publication branch。
* **避免分叉演化**：严禁将 publication branch 发展为第二个并行产品分支；任何非论文专属能力均留在主线。

---

## 6. Publication / Release Policy

未来预期的发布与归档工作流：

```text
publication branch
→ reproducibility verification (在干净受控环境下完成全流程验证)
→ immutable manuscript tag (创建不可变论文状态标签)
→ GitHub Release (发布附带构建产物与说明的 Release)
→ archival repository / DOI (长期归档至 Zenodo 等平台并分配永久 DOI)
```

未来预留的里程碑 Tag 命名规范（**当前暂不创建**，仅在对应事件真实发生时打标）：

* `ejp-damped-pendulum-v1.0-submission`：初次投稿冻结版本
* `ejp-damped-pendulum-v1.1-revision1`：一审修订版本（如审稿人提出补充实验或算法调整）
* `ejp-damped-pendulum-v1.2-published`：最终接收与正式出版归档版本
