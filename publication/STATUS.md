# Publication Status — EJP Undergraduate Pendulum Platform

- 最后更新：2026-09-20。
- Worktree：`ai-physics-tracker-ejp`；integration branch：`publication/ejp-damped-pendulum`。
- 当前：**P0.1 Evidence and Resolved Scientific Profiles — 完成，Independent Scientific Review PASS；可进入P0.2（尚未启动）**。
- P0.2–P6未开始；main通用线状态仍在[docs/status/current.md](../docs/status/current.md)。本线科学开发不等待main Phase6。

## Current direction

own video → Pendulum experiment → fixed calibration / manual release → four landmarks → own DLC training OR teacher model import → infer/review/QC → θ/phase/period/energy → M0/M1 → criticism/structural identifiability → export。首发Windows x64 + macOS arm64，轻量app + first-run runtime。

## P0.1 deliverables

- [Scientific profiles contract](spec/scientific-profiles.md)：legacy/student/diagnostic边界、精确科学语义、Qt-free请求契约、证据限制。
- [Legacy JSON](profiles/legacy-publication-v1.json)、[student JSON](profiles/student-default-v1.json)、[diagnostics JSON](profiles/diagnostics-v1.json)：数值/公式、边界规则及provenance；不是科学功能实现。
- [Source map](evidence/source-map.json)：正式source版本、ZIP成员、逐视频input/trajectory hash、SQLite table selection、method→profile→golden。
- [Golden evidence](evidence/README.md)：15个小型冻结文件，包括24输入元数据、48正式fit、2个完整processed轨迹及诊断；E0–E4字段/单位/比较门槛；synthetic cases合同；其余22条完整轨迹按路径/hash读取原件。
- [Read-only verifier](../scripts/verify_publication_evidence.py)与[13 contract tests](../tests/publication/test_evidence_contract.py)。
- [Mini-plan](plans/p0.1-scientific-profiles.md)；[Independent Scientific Review](../docs/reviews/publication-p0.1-review.md)。

## Resolved scientific decisions

- D01：publication SG9/3独立于main7/2；历史短段策略与student≥9点分段策略分别命名。
- D02：legacy保留原mask（不检查tracked pivot finite）；student严格完整四点+geometry+explicit exclusion，无0.60 hardcut；人工tip相对weight1且confidence保留null。
- D03/D04：正式effective-release source allowlist；旧residual/history表不能作正式golden；fitting.py使用正式hash匹配的ZIP版本。
- D05：information extrema、phase halfcycle skip2、EDP skip5、tail、objective各自保留算法和积分容差。halfcycle signed contraction与EDP abs loss分开；速度分层frame/interval分开。
- D06/U04：manual release无自动−1；前5有效帧且确认静止才默认IC；否则显式fixed IC。student gap不桥接、tail最后1/3且≥10完整周期、fit count/跨度门槛等均标new_student_policy。
- U03：SciPy1.17.1隐式参数已按版本源码恢复；保留run-reported environment，未伪造完整lock或跨平台数值等价结果。

## Verification boundary / remaining items

本轮：13 unittest通过；core.autocrlf=true暂存树临时checkout的哈希验证通过（非Windows数值实测）；离线15文件/48fit/2完整trajectory检查通过；带root的83个外部来源只读hash/表selection核验通过；4个public-library URL源码在恢复时按固定版本取hash。正式source11项均匹配run manifest；全部24 IC hash对应正式fit。未修改科研原件、执行历史分析脚本、重拟合、训练或生成论文图。

这些是证据/契约验证，**不是P2–P4数值功能或48fit复跑已通过**。拟定数值容差待未来实现逐项实测；非bitwise依赖lock缺失如实保留。剩余非阻塞项：raw四点→θ/mask及pre-release median没有offline历史重算；历史逐start日志缺失；部分完整轨迹仍从外部根读取；模型/原视频实体按用户要求不追查。angular acceleration无历史默认，本轮不纳入必交付。

main Phase5.6 AC-9未达到改善目标的历史缺口不受影响；main历史804 tests不能冒称本轮运行结果。P0.1无GUI增量，不触发GUI Human Review。

## Review / integration

Independent Scientific Review已完成：F1–F4修复并独立复审关闭，最终PASS、无未关闭blocking finding。具体处置与验证见review record。未改Accepted ADR；没有引入依赖、产品代码、runtime或数据schema迁移。

## Next Recommended Action

P0.1已完成，提交/集成至publication分支后停止。**用户下一轮可启动P0.2 — Experiment / run / derived contracts**：先读P0.1 profiles/evidence，写mini-plan，固定四role/release/calibration/teacher-model、多轨事务、multi-input stale、resolved scientific request/result持久化与旧项目兼容。不要开始P1实现或等待main Phase6。
