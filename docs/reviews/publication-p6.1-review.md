# Publication P6.1 Independent Review

- 日期：2026-10-02；reviewer gpt-6-luna/max，只读；主实现 root。
- 范围：P6.1 `40db20d..df920f4` 的打包/启动/资源worker源码/FFprobe支撑层，以及P6.2对其修复 `c890b5b`；不重审P0–P5科学算法。
- 最终代码结论：补充审查 **Approve with limitations**（`c890b5b`）；F1/F2 Closed，无开放major；最新Mac安装版HR随P6.2已获用户2026-10-02三项均通过，准备集成。Windows真机不在该HR通过范围内。

| ID | Finding | 修复与验证 | 复审状态 |
| --- | --- | --- | --- |
| F1 Major | bundle最低系统11.0与host NumPy/SciPy二进制minos14.0冲突 | LSMinimumSystemVersion改14.0、README同步；最新DMG重建通过 | Closed |
| F2 Blocking | 通用TaskPanel旧AI入口仍spawn frozen host，无Torch/DLC | frozen按钮禁用、任务卡引导Experiment setup、统一_start在准备/登记run之前拒绝；源代码开发模式保持原行为；train/infer两条回归 | Closed |

代表帧选择用OpenCV/sklearn，不调用DLC内部接口；host锁已补现有强制依赖scikit-learn。支持的AI入口为ModelActions/ExperimentInferenceActions，managed解释器只流向这些external worker路径。

Reviewer复核packaging、launch_context、__main__、FFprobe构建与package_root贯通，无开放Major。独立125项定向通过（与P6.2共享测试范围）；未逐页审阅上游license原件或核验新成品。root已完成新成品原生构建/setup/external hello smoke，原始许可校验与来源另见NOTICE/evidence。

CI原生构建成功不等于Windows真机验收；WindowsG1–G4/G5仍not_run。先前用户测试的frozen+显式外部venv推理证据保留；最新安装包体验由P6.2 HR共同复核，不提前标通过。
