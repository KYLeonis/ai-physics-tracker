# P0.3 Runtime Boundary / Feasibility Contract

这是可丢弃的执行边界spike；不实现正式installer或GUI。现有`TrackingJobRunner`使用当前解释器的multiprocessing spawn，不能把frozen app的sys.executable当managed Python。P1适配时复用现有prepare/结果validation/主线程事务，将执行端移到外置worker，不复制科学逻辑。

## Protocol v1

最小方案为每job独占目录中的request.json、result.json、cancel.request和worker.log；stdout/stderr都进入日志，不把DLC打印当协议JSON。Host通过绝对受信runtime Python路径，以shell=false参数列表启动受信worker.py；禁止pickle跨解释器交换。request记录protocol_version=1、job_id、operation、input/config digest、声明的输入/输出路径与device；worker不接受任意命令/eval/用户插件。spike的request_digest对完整canonical request取SHA256，包含worker源字节SHA、op/device/repo；DLC smoke输出至少声明project.json的size/SHA。spike不提交ProjectSession candidate，因此真实项目capture digest重比属于P1 adapter的强制实现项，本轮不冒称该产品事务已实现。spike只允许hello/selftest/wait/stubborn/fail/dlc_smoke，不是产品API。

worker exit约定success/cancelled→0、failed→1；host自行forced cancellation不采用worker terminal，单独记录信号退出码。device请求为backend，实际cuda:0/mps:0与相应backend匹配并保留完整actual_device；不得用字符串cuda==cuda:0错误拒绝。result先写临时文件再os.replace，包含同version/job_id、terminal status、结果/错误class/message、实际platform/python/runtime/device与时间（后续产品必须）。本spike只要求所有success有python/executable/platform/machine，host记录elapsed_s；selftest另有versions/actual_device，DLC smoke固定CPU并在日志记录版本，不提供完整产品runtime identity/timestamp。此限制不可作为P1缺少字段的理由。Host校验身份、版本、exit code、status、payload schema、输出文件存在/hash和capture input digest后才向application交付candidate；worker绝不修改project.json。超时/取消之后即使迟到success文件存在也不得采用；取消状态以host lifecycle为准。重复job目录拒绝，重试新id。

取消：先发marker并给有限grace；不能响应的native training强制回收整个进程树。POSIX独立session+killpg；Windows需要Job Object或经真机验证的taskkill /T /F；child被留下即失败，不能仅杀worker parent冒称支持取消。stderr traceback和依赖日志保留，失败不清理诊断。硬终止后partial模型只作为failed产物，不作teacher模型/active结果。

## Installer / dependency selection合同（未正式实现）

轻量host与AI runtime两条依赖闭包；现有pyproject强制DLC需要未来拆分optional worker依赖，不直接改现有环境。安装到用户数据目录的versioned staging，校验Python/ABI/architecture、wheel来源/hash、Torch及DLC约束、执行selftest后才atomic切换active runtime pointer。失败保留旧runtime可用并给阶段/错误/日志路径/重试建议；取消不发布半安装环境。磁盘空间、网络/proxy、中断恢复、长路径/Unicode权限均需真实验证。

Python候选仍3.11或3.12；不将P0.1历史3.13科研环境作为DLC发行基线。先选择platform/arch与GPUdriver，再用受控版本清单安装兼容torch/torchvision及DLC，禁止“升级到最新”漂移。CPU始终提供；CUDA availability与驱动/wheel兼容、MPS availability与实际DLC算子可用分别验证。硬件探测≠可训练证明；MPS失败可显式CPU fallback并记录device/原因，不隐藏。本spike不自动fallback：所选backend不可用即失败；用户可另发CPU请求。上述受记录的fallback是后续产品合同，未作为本轮实测行为。

离线大包非首发要求；断网时已有runtime继续可用，新安装明确失败而非无限等待。license、Win签名与Mac codesign/notarization在P6首发门禁，P0不签发或购买账号。

## 来源与风险

- [DLC官方安装](https://deeplabcut.github.io/DeepLabCut/docs/installation.html)：平台/Python与先安装PyTorch；最终release要冻结实际tested组合。
- [PyTorch安装选择](https://pytorch.org/get-started/locally/)：按平台与compute backend选择；官方可用轮子不等于本项目DLC已通过。
- [PyInstaller跨平台构建](https://www.pyinstaller.org/en/stable/usage.html)：各OS分别构建，Mac不能产Win x64。
- [PyInstaller外部程序](https://pyinstaller.org/en/latest/common-issues-and-pitfalls.html)：frozen环境可能污染外部动态库搜索；host启动外置解释器应清理PYTHONHOME/PYTHONPATH/PyInstaller内部变量、恢复LD_LIBRARY_PATH，Windows DLL搜索路径需清理/恢复。不能把源代码启动成功当冻结启动成功。

## Evidence levels / gate

G1 frozen host真实启动外置worker并识别其独立解释器；G2 CPU/Torch/DLC依赖selftest；G3小型真实DLC train+infer；G4协作取消与强制树回收/错误日志；G5 first-run clean-machine依赖安装/repair。Mac arm64与Win x64逐项记录pass/failed/not_run；CUDA/MPS作为单独行。G1–G4是P0.3调查门禁，G5完整GUI/发行体验属于P6，但安装兼容性应尽早取证。spike中的hello/wait/fail只证明协议，不证明DLC。

当前结果与运行命令见[feasibility evidence](../evidence/runtime/README.md)。没有机器或环境时保持not_run；P0.4可以收敛合同和风险，但不能自行宣称未测platform已通过。
