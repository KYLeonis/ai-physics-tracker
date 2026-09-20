# Publication Status — EJP Undergraduate Pendulum Platform

- 最后更新：2026-09-20（2026-09-19启动的规划会话收尾）。
- Worktree：`ai-physics-tracker-ejp`；branch：`publication/ejp-damped-pendulum`。
- 当前状态：**requirements / scientific asset inventory / master plan已形成；P0–P6尚未开始实现**。
- 本线状态入口；main状态保留在[docs/status/current.md](../docs/status/current.md)，不能用main Phase6是否完成作为本线科学开发的前置条件。

## Current direction

依照用户本轮指令，本线是pendulum-focused undergraduate experiment platform：

```text
install → first-run AI runtime setup → own video → Pendulum experiment
→ fixed pivot / true vertical / scale / release frame
→ same-frame four-landmark annotation
→ train own DLC OR Import DLC Model…
→ inference / review / QC / adopt → θ(t) → phase / period / energy
→ M0/M1 full-trajectory fitting → model criticism
→ structural identifiability λ interaction → save / export
```

Windows x64 installer与macOS Apple Silicon app/dmg均是首发目标；轻量应用+首次AI环境配置，无GPU允许CPU运行；不提供通用pendulum预训练模型/统一训练视频。

## Recently completed — planning only

- [Platform requirements](spec/platform-requirements.md)：四点/角度/时间/QC/ODE/identifiability/runtime契约及R01–R12首发验收。
- [Scientific Asset Inventory](spec/scientific-asset-inventory.md)：A01–A16证据对应、真实参数恢复、SQLite表版本区分、discrepancy/unknown登记。
- [PHASE_PLAN](PHASE_PLAN.md)：P0–P6与Subphase边界、独立审查/真人验收、早期runtime spike、最小架构变更和首发blockers。
- [README](README.md)同步为publication-native方向，取代旧“等待main Phase6、打包非核心”的假设。
- 本轮只读调查科研资产与论文；未训练、拟合、生成图或修改原始数据；未新增产品代码、依赖或开始任何Phase。

## Evidence / verification boundary

- 仓库调查时HEAD `0e1e4f1`，工作区clean、分支与预期相符；产品基线`62239fa`。
- 论文PDF文本已阅读，第9页模型/identifiability图目视核对。
- SQLite用mode=ro核对149张表；正式fit48行与封存CSV关键参数/RMSE/release字段一致。
- processed θ：24份effective-release CSV.gz；P011 3250点/108.311227s。DB旧`residual_trajectories`是3249点，不作正文轨迹替代。
- 88-frame盲标与177-frame split记录已核对；11个最终figure-source输入hash匹配；封存zip内fitting.py匹配正式run hash。
- 用户补充：科研数据已保存SQLite，原始视频已保存且本轮不重要；不继续追查原始视频、labels/checkpoint实体，不将其列为规划前置条件。
- 未做历史科学全链复跑或新平台验证；804 tests/双平台CI是Phase5.7历史记录，不是本轮执行结果。
- Phase5.6 AC-9“≥5%可复现改善”未达成的历史缺口仍保留（最佳−3.3%）；本轮没有新增改善证据，也不为解决它规划论文补充实验。

## Planning review and document validation

- 已完成主Agent自查：核对本轮用户要求、科学来源与unknown标记、各Phase的scope/AC/review gates、只规划边界。
- 本地Markdown链接、代码围栏与`git diff --check`检查通过；变更仅为Markdown，无产品代码/依赖/科研资产修改。
- 独立只读审查已发起，但代理因usage limit退出，未返回结论；**独立审查未完成，不声称通过**。本轮是规划交付，不视为P0实施或其Independent Review gate完成；P0启动时须完成契约独立审查。
- 纯文档变更未运行产品测试；历史804 tests记录不作为本轮测试结果。

## Decisions / unresolved gates

已定：固定四role、fixed pivot→tip相对true vertical、manual release t=0、内部rad、M0/M1 shared core、完整λ教学交互、双平台轻量发行、publication独立交付。

P0需要裁定/明确：

1. D02：论文all-four QC vs正式拟合mask未检查tracked pivot finite；学生QC与legacy reproduction的关系、likelihood filtering/weighting。
2. 不同extrema/energy profile的命名与使用，不把skip2/skip5、g/L proxy/ωobs² energy混为一个default。
3. 缺测/短段、manual weights、预释放不足/非静止IC、短视频tail及有效样本门槛政策。
4. 多Track单run/四轨原子activation/多输入stale、旧项目兼容与teacher model reference契约。
5. managed runtime worker协议、真实双平台依赖组合与数值隐式默认恢复。

未修改既有Accepted ADR。ADR proposal主题已写入PHASE_PLAN，不为文档数量创建空ADR。

## Relevant Source Commits

| Source commit | 为什么本线需要 | 本线重新验证 | 状态 |
| --- | --- | --- | --- |
| `62239fa` | Phase5.7测量、DLC单点链路与交互地基 | 本轮静态核查training/inference/kinematics/charts/workflow projection；历史804 tests及双平台CI见原记录 | baseline，未新增同步 |

publication自有早期提交：`917cf1d` README、`0e1e4f1` STATUS。本轮没有cherry-pick或合入main；不再把旧文档声称的“落后main6提交”当当前已核验事实。

## Next Recommended Action

**本轮规划完成后停止，等待用户启动P0。** 获得下一轮指令后，Sol先读取requirements、inventory §4–6与PHASE_PLAN，编写 **P0.1 Evidence and resolved scientific profiles mini-plan**，明确source map、golden inputs/outputs、数值容差及D02/D05/D06/U03/U04的具体裁定项。随后按P0计划推进数据契约与runtime早期spike；不要先实现GUI或等待main Phase6。
