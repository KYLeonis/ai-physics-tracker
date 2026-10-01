# Windows任务取消退出确认 — Independent Review（2026-10-01）

- Scope：TaskHandle.cancel最终强杀后退出确认，task/training/tracking与GUI取消调用方；source base4158058，代码bf8f0c5→8a7d90d。High-risk后台生命周期。
- 首轮Request changes：10s有界等待新增TimeoutError被TrackingActions捕获后仍结束cancel，FrameSelection等fire-and-forget不读取失败（P1/P2）。该方案虽55项和CI36812278599双平台通过，不作为最终交付。
- FIX：原生Process.join()等待kill后OS确认退出；不引入新TimeoutError、保留None接口。Windows WaitForSingleObject(INFINITE)契约，macOS/Linux也等待回收。请求协作与terminate等待仍有界，最终退出等待在既有executor执行。
- 复审Approve：新增异常分支已移除，两项finding关闭；既有frame-selection逻辑取消未被本diff扩大。独立7核心、13取消GUI通过，diff通过；主会话54项通过。OS异常I/O可延长后台回收，但不在Qt线程等待。
- 原始失败CI36810642925：Windows1失败/1245通过/5跳过，macOS通过；唯一取消后is_alive断言。最终代码跨平台CI待验证。
