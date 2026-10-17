# 架构扫描复核与调整建议（草案）

- 日期：2026-10-17
- 代码基线：main `985fd7c`；只读核查产品代码，未启动重构或P6.3.1。
- 输入：GLM的`architecture-review-20261016-160921.html`，候选①任务生命周期、②Session计算与Undo、③pipeline契约、④执行状态装配、⑤图表渲染。
- 性质：讨论建议，未接受为ADR、未改变已冻结计划或验收标准。

## 总体判断

保留现有GUI / application / domain / infrastructure四层和既有数据体系。优先加深分析链路中的module，让调用方通过更小的interface获得更多leverage，让配方解释、计算和提交规则具有locality。文件行数、方法数量、`_poll`数量不能单独证明depth不足；拆文件而保留全部跨module知识不算收益。

不新增通用计算框架、结果依赖图、事件总线、任务队列、插件框架或全局状态容器。沿用ADR-0012、0017、0019、0020、0021；main与publication仍受控同步。

## 原报告需要修正的判断

1. **①不是Normal-risk。** 项目`docs/workflow.md` §6.2 / §10.2明确将后台生命周期 / 并发列为High-risk；③涉及科学配方 / 数据契约，也不能只因改动小就认定为低风险快赢。
2. **Undo并非无测试。** `tests/test_project_session.py`覆盖Correct / 删除人工点与审核状态的原子Undo；`tests/test_undo_run_integrity.py`覆盖run依赖、后台进展、保存和autosave。`chart_recipe`也由`tests/test_angular_chart_data.py`直接及经`build_chart_data`覆盖。应先识别具体缺口，不能按测试文件同名与否判断。
3. **不同guard不是可直接删除的重复。** `validated_batch`已经共用基础输入 / 目标版本检查，`validated_angular`补充参考定义，`validated_analysis`补充确切源 / 样本 / 公式 / 目标核对。共享机械生命周期不能替代这些科学条件。
4. **Session拆出计算不自动减少公共interface。** 保留兼容入口可以有价值；收益应是计算脱离会话写入、同步 / 后台共用同一implementation，而非承诺公开方法数下降。
5. **生命周期已有deep module。** `BackgroundTaskRunner`已集中spawn / IPC / 强制回收，decoder有自己的交付与关闭契约。独立走查确认9个poll类函数并非9份同一协议，不能仅据数量合并。

## 建议顺序

### 先收敛③，并采纳⑤中的源信号元数据

- 真实摩擦：Session写pipeline，`chart_recipe`解释配方，job做有效性校验，GUI又重建设置；`kinematics_job.run_kinematics_job`重复覆盖Session已经写过的`timing_context`。
- 最小方向：以既有`chart_recipe`为基础整理已知配方的共同解释 / 构造规则，再由不同用途施加自己的策略。只读显示旧缓存与准许新计算的interface有不同要求，不能混成一个valid布尔值。
- 保留JSON持久化、未知字段和未知步骤的原文；未知配方只读不等于准许计算，不引入全项目schema迁移或一套穷尽所有未来步骤的类型体系。
- `ChartPlot._legendName`目前通过`pipeline_summary.split(" · ")[0]`和`"Savitzky-Golay" in pipeline_summary`判断实际参考 / 平滑语义。由结构化源信号事实提供这些信息，文字只负责展示。
- 收益：同一处配方修改不再要求多处猜测；通过同一seam验证旧项目、未知扩展、时序、参考、步骤顺序和重建一致性。

### 结合6.3.1局部推进①与④

- 6.3.1本身要求合并连续预览、最新草稿胜出、手改保护、迟到拒绝、失败留痕；这些应由内聚的分析任务module集中维护。
- 明确区分草稿预览、显式正式计算、上次保存结果、尝试日志；日志不回滚成功结果或混入结果Undo。
- Qt adapter继续承担主线程交付；复用既有executor / runner。共享开始、取消、结束、回收等机械实现，科学输入与目标槽核对继续留在各自分析module。
- 共享事实采集可以减少兄弟module互查，但UI缓存身份、任务提交新鲜度、操作互锁是不同用途；不使用一个全局`hash(snapshot)`替代三者。
- 先在真实分析用途中证明seam；更大范围的thread / spawn / decoder统一另立维护计划，不把所有refresh / autosave都塞入一个JobSupervisor。
- 反例：`ProjectActions._saveCandidate`的保存阶段不可取消；模型导入允许同一项目切视频后接收结果，自检却要求原视频 / 代际；时序验证在保存忙时延后提交。一个统一guard不能代替这些有意不同的规则。
- ④中的明确小重复是`tracking_actions.refresh`同轮两次采集`_execution_input()`；局部复用一次采样即可，不需要新增全局module。已有`ExecutionInput` / `PlaybackSnapshot`继续各司其职。

### 再处理②中的计算，Undo后置

- `compute_kinematics` / `compute_angular`包含计算、DerivedData装配、扩展保留和提交；后台job又通过detached Session调用这些写入入口。
- 将计算与结果装配加深为无活动Session写入的application module，复用domain现有数值函数；同步与后台共用，Session继续拥有统一发布 / stale传播 / Undo事务。
- 先做deletion test：若提取后仍要把Session和大批内部回调传进去，只是移动复杂度，应重划seam。
- 暂缓拆Undo。七元组可读性是后续整理候选，但应保持run进展不回滚、scoped review、显式保存清历史 / autosave保留历史及Analysis栈顶限制；不能与计算提取同批改动。

### ⑤的统一渲染adapter按真实重复再定

`ChartPlot`拥有逐帧导航、选中与相空间；`AnalysisPlot`拥有初值 / 残差视图、参考线和页面滚轮。共享少量轴 / 网格样式可能有收益，但不足以证明需要通用ChartRenderer。先修结构化元数据，并在6.3.1将预览数值 / 解释计算移出GUI；避免靠大量分支 / 参数统一两种交互。

## 完成判据与验证

每次调整需能指出调用方删掉了哪些知识、哪些规则只有一个owner、哪些既有行为测试经过同一interface仍成立。保持真实帧 / 时间、NaN分段、时序授权、源与目标双版本、失败原子拒绝、未知字段往返。不得以减少文件数或行数替代这些判据。

本轮实际执行：`.venv/bin/python -m pytest -q tests/test_undo_run_integrity.py tests/test_angular_chart_data.py tests/test_signal_analysis_job.py`，**59 passed（2.62s）**。这是对报告测试判断的定向复核，不是完整覆盖率、性能结论或新架构验收；未运行全量、双平台CI或真人HR。

独立只读核查另执行下列命令，**137 passed，561 warnings（39.54s）**；验证已有任务 / 工作流回归，不宣称无warning：

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_task_runner.py tests/test_workflow_projection.py \
  tests/gui/test_project_actions.py tests/gui/test_tracking_actions.py \
  tests/gui/test_model_actions.py tests/gui/test_timing_actions.py \
  tests/gui/test_frame_selection_actions.py tests/gui/test_suggested_frame_review_actions.py \
  tests/gui/test_decode_delivery_bridge.py
```

下一步建议：先与用户确定③的最小范围及其与6.3.1的关系，再形成mini-plan / Review Gate；不凭本草案自动开工。
