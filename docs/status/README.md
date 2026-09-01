# 状态与计划草案

- `current.md`：当前阶段、阻塞和下一步的唯一入口；每个会话结束同步。
- `phase-<N>-plan.md`：整个 Phase 在实现前的总计划草案，承接 requirements/roadmap，定义
  Subphase 顺序、依赖、验收与决策门；用户确认后再为首个 Subphase 建分支和 Issue。
- `phase-<N.M>-plan.md`：尚待用户确认的 Subphase mini-plan 草案，按
  `docs/templates/subphase-plan.md` 组织。确认后将计划同步到对应 GitHub Issue，
  并在草案头部写入 Issue 链接；不把草案当作已接受 spec 或提前勾选验收。
- 计划调整保留原因；收尾时填写 Result。已完成计划保留作交接记录，不自动删除。
- 不放运行日志、测试产物、媒体或凭据；测试结论仅保留命令、结果和证据链接。
