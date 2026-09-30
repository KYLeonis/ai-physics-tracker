# Independent Review — Publication P2.1

- Date：2026-09-30；branch `feat/p2.1-theta-qc-core`，base `100b955`。
- Scope：Qt-free reconstruction / application snapshot 消费入口、QCExclusion domain/codec/session/persistence、相关 tests。依据 P2.1 mini-plan、scientific profiles、数据合同 §2/6/7、CODE_STANDARD。
- Reviewer：fresh-context 只读 subagent `p2_1_review`；独立执行输入探针、85 定向测试、1181 全量测试与 evidence verifier。实现和 findings 修复均由主 Agent 完成。
- 首轮 Verdict：**request-changes**；两项 finding 已修复；复审 **approve**，两项均 Closed。

| ID | Finding / evidence | Triage / Fix / status |
| --- | --- | --- |
| F1 (P1) | core 接受 manual confidence=0.5 并给 weight1；未落实 manual null 输入不变量 | FIX：AdoptedLandmark 构造期拒绝任何 manual 非 null confidence；回归覆盖 0/1/.5/NaN/Inf。Closed，独立探针与回归通过 |
| F2 (P2) | direct core request 的 int/float 表示影响 input digest，应用 snapshot 的规范化不能覆盖直接调用 | FIX：核心点坐标、confidence、绝对时间在构造期统一 Python float；identity 几何数值统一 float，frame IDs 保持 int。直接 core int/float 同输入得到相等完整结果回归。Closed，独立探针与回归通过 |

## Implementation self-review

- 在 review 前由保存重开测试发现既有 adopted measurement 摘要的 int/float 差异：shared snapshot builder 统一坐标/物理值/标定值为 float，TrueVertical endpoint digest 同样统一。整数人工坐标及整数 vertical 端点保存重开验证通过；无原始科研文件修改。
- 非有限几何与非法/压缩源帧、非递增时间、未确认 vertical、缺 setup、mutable array、非法 QC exclusions 均 fail closed；坐标缺测返回 None+reason，不补零。
- φ 连续有限 body-pair 内 unwrap，tracked pivot 仅位移诊断。body reference 从完整四点、正有限、未人工排除帧取 median，并冻结支持集 digest。AI 无硬置信阈值，weight 与共同 mask 分开。

## Verification / Final Verdict

- 首轮基线：1181 passed / 9 subtests；修复后定向 **91 passed**，全量 **1187 passed / 9 subtests**；evidence verifier 通过。
- 复审独立验证：核心30 tests；保存重开/QC transaction/旧 schema codec 2 tests；manual5值拒绝与 int/float同摘要探针。最终 Verdict **approve**，无开放 findings。
- 当前没有 GUI 新交互；Human Review 由 P2.3 执行，不能用数值测试替代。
