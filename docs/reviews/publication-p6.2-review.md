# Publication P6.2 Independent Review

- 日期：2026-10-02；主实现 root；reviewer gpt-6-luna/max，只读。
- 范围：`df920f4..c890b5b`，完整 managed runtime 安装/取消/激活/GUI/诊断/随包依赖材料。P6.1 支撑层另记本目录 P6.1 record。
- 最终代码结论：R3 **Approve with limitations**（`c890b5b`），无开放Blocking/Major；真人HR未测。Windows真机、CUDA训练与clean-machine仍not_run。Reviewer未核验新DMG成品；成品由root单独构建/冒烟验证。

## Findings / dispositions

| ID | Finding | 修复与证据 | 复审状态 |
| --- | --- | --- | --- |
| F1 Major | Mac依赖要求14+，安装前未验证最低OS | manifest min_os_version + profile_supported提前拒绝；旧OS负例 | Closed |
| F2 Major | Qt-free安装事务使用QLockFile | stdlib fcntl/msvcrt原生文件锁，失败/取消释放可重试 | Closed |
| F3 Major | Cancel与pointer替换存在竞态 | RuntimeCancellation同锁串行set/commit，指针作为最后提交点；负例 | Closed |
| F4 Major | frozen指针不要求ready证据 | 全形态要求ready/executable身份，拒绝非dict/缺失/损坏JSON；显式env覆盖另保留 | Closed |
| F5 Major | 更换runtime后每次显式推理重复完整模型自检 | 按模型manifest/device缓存当前会话成功证据，换解释器清空；auto每次仍重检 | Closed |
| F6 Major | `python -m`可被当前目录同名包遮蔽 | worker argv增加-P，受信PYTHONPATH优先；真实cwd影子包hello负例通过 | Closed |
| F7 Major | CUDA profile用auto自检，可回退CPU而激活 | 强制cuda，CPU profile强制cpu；CUDA不可用保持旧pointer回归 | Closed |

F5的严重性由主实现方按明显性能回归裁定为Major。managed/frozen重启后首次自检避免沿用别的解释器证据；不改科学数据/schema。

## Verification

- 初轮后真实Mac安装、pip check、tensor/DLC自检、CPU训练与CPU/MPS推理、断网重开已有模型推理通过；原始路径与版本见 `publication/evidence/runtime/p6.2-validation.md`。
- `c890b5b` 主定向 **130 passed (24.92s)**：runtime_install、external_worker、launch_context、runtime_setup UI、experiment_inference UI、tracking_actions。
- Reviewer独立 **125 passed (27.81s)**，`-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`，未改源码或共享环境；复核上述findings与P6.1支撑层闭环，代码Approve with limitations。
- 新Mac DMG构建/完整MainWindow/setup入口/host不导入AI栈/随包FFprobe/受信external hello通过；`LSMinimumSystemVersion=14.0`实测。最终`c890b5b` [tests](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37023438111) 与 [packaging](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37023439440) 双平台success；Mac1438/Windows1436passed，各1既有strictxfail，非数值通过。
- 真实Windows install/train/CUDA/整树取消、clean-machine/pilot保持not_run。用户HR参见 `publication/plans/p6.2-human-review.md`，未过不集成。
