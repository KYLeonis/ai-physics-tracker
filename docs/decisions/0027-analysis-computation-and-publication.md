# ADR-0027 — 分析计算与工程发布职责分离

## Status

Accepted，2026-10-18；用户明确启动R04整体方案。实现状态见architecture-progress及analysis-workflow-plan。

## Context

线性 / 角运动后台job携带detached Session并调用有写入 / Undo语义的compute入口。活动工程没有被worker直接修改，但计算必须携带并理解会话。拟合 / 重复间隔已使用冻结数据；同步与后台需要通过一致的科学核对及原子发布，GUI应消费共同的准备事实。

## Decision

- application.motion_computation拥有AnalysisInputs及线性 / 角运动的无Session写入计算和DerivedData构造，复用domain算法与source_recipe；仅返回候选记录，不访问Qt、repository、活动Session或文件。
- AnalysisInputs旧导入路径兼容再导出；内部线性 / 角运动job移除snapshot字段，只持有必要冻结输入、参数及目标版本。观测值对象沿用不可变约定，嵌套扩展字段不与活动会话可写共享；不复制整个工程、Undo或保存基线。
- prepare采集并检查输入；run执行计算及取消；validated_*保留来源 / 输入 / 目标版本与特有科学校验；Session.apply_*保留唯一写入 / 失效传播 / Undo所有权。
- Session.compute_*保留外部调用方式，作为同步prepare/run/apply协调入口；同步与后台经过同一计算及结果核对路径。detached()为保存等其他用途保留。
- application提供源准备与当前资格的共同事实，GUI采集控件意图和瞬时执行事实、控制线程交付及视图；不新增全局控制器、单一valid、通用hash或统一任务队列。预览与正式执行隔离，自动刷新不触发滚动定位。
- 数值、JSON、未知扩展保留、正式Fit/Measure的显式意图、历史只读和保存 / Undo语义不变；AI、解码与文件保存保留专属协议。

## Consequences

计算可以独立测试，不再借用临时Session写入。同步与后台共享核对规则；GUI减少对准备细节的了解。迁移必须覆盖所有真实入口，并通过数值等价、无会话写入、版本拒绝、事务和联动回归；内部job字段测试需随旧路径退出调整，不改变持久化格式。
