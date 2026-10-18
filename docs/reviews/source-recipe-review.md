# 计算配方统一解释 — Review Record

2026-10-18；基线main `362ac85`；`codex/source-recipe`。High-risk，范围见[mini-plan](../status/source-recipe-plan.md)。

## Scope / Gate

`source_recipe`拥有已知步骤读取 / 结构自洽、SG参数与导数阶、角参考转换、时序来源；`chart_recipe`保留比较 / 图表披露与行读取策略，旧导入路径直接再导出同一函数。同步记录构造 / job校验 / 拟合与GUI设置恢复实际共用；图例使用明确的reference_label / source_smoothed，不再反解析pipeline_summary。

不改数值、JSON、未知扩展保留、图表 / 拟合 / 自动覆盖不同资格、源与目标版本、Undo及预览执行。没有新增交互或新视觉设计，本轮不新增HR关卡；若发现需改变这些契约，另列问题。

## Verification

- 定向142 passed（35.92s，325 warnings）：旧 / 坏 / 未知源、F1–F3、两类job与图表 / GUI / 分层规则。
- 新增同步 / 后台记录等价、旧入口同一实现、未知JSON不变、图例不受摘要措辞影响；所在两文件30 passed（20.24s，277 warnings）。
- 机械迁移20个函数 / 类型AST与基线一致。初次编辑误将展示函数插入检查列表，已修正并通过上述定向验证。
- 本机全量 / macOS与Windows CI待最终结果。
- Independent Reviewer `fit_source_final_review`只读审核完整diff，待回执；未宣称Approve。

## Findings / Result

待独立review；实现方处理finding，复审及全部Gate通过后才集成。
