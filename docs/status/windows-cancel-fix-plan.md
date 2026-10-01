# Windows取消回收修复 — mini-plan（2026-10-01）

- Goal：修复论文分支CI run36810642925在北京时间11:32报告的任务取消后子进程仍存活。
- Context Pack：TaskHandle.cancel所有调用方、tracking_job.cancel_tracking_job、training_session/task_runner生命周期测试；Windows TerminateProcess异步退出契约；AGENTS dual-worktree受控同步。
- Scope / AC：沿用event→join→terminate→join→kill；强杀后使用原生join等待OS确认退出，成功返回必须已退出，不新增超时异常；不改科学/SG/数据格式或掩盖测试断言。先main修复验证，再cherry-pick到publication工作分支。
- Slices：失败日志/共享取消入口 → 最小生命周期修复与确定性慢退出回归 → 定向与Independent Review → main集成、论文同步、Windows/macOS CI闭环。
- Review Gate：后台生命周期High-risk，必须只读Independent Review；无新增GUI交互，不新增Human Review，P2既有HR仍待用户。
- CI证据：1 failed /1245 passed /5 skipped；唯一失败tests/test_training_session.py::test_session_close_cancels_unified_runner_and_persists_status，取消函数返回后is_alive为True；macOS通过。


## Execution

初版checkpoint bf8f0c5采用10s等待/TimeoutError，55项本地通过且CI36812278599 Windows/macOS双通过；独立审查发现新增异常被既有GUI取消路径吞掉，已改成更小的根因修复：kill后Process.join()原生等待实际退出，保留协作与terminate有界等待，不新增异常/改GUI。成功返回即进程已退出；OS异常I/O清理可能延长后台回收，GUI线程不做join。Windows异步终止来源：[Microsoft TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)。本地19 task/training/tracking、36 tracking/frame-selection GUI定向（合计55）通过；无新GUI交互。最终54项定向通过；独立复审Approve（7核心/13GUI），新异常findings因移除该分支而关闭；main集成后只cherry-pick代码提交到论文工作分支，记录source与双平台CI。

最终代码提交8a7d90d（承接bf8f0c5），合计净修复为kill后native join；仅同步两条代码提交到论文工作分支。P2既有HR未关闭。
