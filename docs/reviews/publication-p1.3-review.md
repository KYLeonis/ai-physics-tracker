# Independent Review — Publication P1.3 (S1–S3)

- Date:2026-09-28;Scope:P1.3 S1–S3(external worker 协议、joint training request/result、TeacherModelReference),分支 `feat/p1.3-joint-training`,commits `787b169`…`f60a52d`。Reviewer 为 fresh-context 只读 code-reviewer subagent;处置由实现方(主会话)完成并复测。
- 依据:[runtime-boundary.md](../../publication/spec/runtime-boundary.md) Protocol v1、[contracts](../../publication/spec/experiment-run-derived-contracts.md) §2/§4/§6、[P1.3 执行 mini-plan](../../publication/plans/p1.3-joint-training-execution.md) S1–S3、CODE_STANDARD。
- 前置:S1 交付时已过一轮 slice 级只读 review(M1–M4/m1–m5 当轮闭环);本轮为计划规定的 S3 后 AI lifecycle/protocol 专项 gate。

## Findings 与处置(全部闭环)

| ID | 摘要 | 处置 |
| --- | --- | --- |
| B1 (Blocker) | `_model_snapshots` 的单 bodypart 守卫挡在训练路径:四 role 联合训练在真实 DLC 链路必然 failed(S6 smoke 才会暴露) | CLOSED:守卫参数化 `allowed_bodyparts`(仅推理/评价路径传 `("target",)`);multi-animal/cropping 守卫两路径保留;fake DLCLoader 回归测试(训练四 bodypart 可定位快照、推理路径守卫保持) |
| M1 (Major) | host 对 success result 缺 `outputs` 键 fail-open,输出完整性链有旁路 | CLOSED:`_validate_outputs` 对缺键 raise(空输出也须显式声明);verifier 交叉核对 section 路径 ∈ 声明 outputs(`do not cover` 拒绝);host 负例 + verifier 负例测试 |
| M2 (Major) | verifier 读错层级,`actual_device` 恒 None;测试断言两侧皆 None 空转 | CLOSED:改读 result 顶层;测试断言非 None 值("mps"/"cpu") |
| M3 (Major) | `validate_project` 不校验 model_references(悬空引用可注入);v1 拒绝清单不含 | CLOSED:`_validate_publication_collections` 增 model_id 唯一性、trained→source run 存在且 completed train、source_experiment 存在;v1 拒绝;构造期负例测试 |
| m1 | serializer 非 dict manifest 条目静默跳过 | CLOSED:显式 raise + 负例测试 |
| m2 | register 的 provenance 仅信任可变的 run config/extras | CLOSED:register 要求 extras 含 verifier 冻结的非空 `label_digest` 标记;负例测试 |
| m3 | verify 不复核磁盘视频(训练后视频被替换仍通过);role/video stale 负例缺 | CLOSED:verify 重算视频 sha(替换→拒绝"video changed");role 重绑经 digest stale 已结构性覆盖(测试注明) |
| m4 | `mark_run_completed` 裸 ValueError;terminal run 仍可被 verify | CLOSED:前置 `run.status ∈ {pending,running}` 检查;ValueError 包装为 ProjectSessionError;负例测试 |
| m5 | 快照注释过期 | CLOSED:注释改为"末两位 registry" |
| m6 | 跨模块 import 私有 `_file_sha256` + 三份实现 | CLOSED:提升 `infrastructure/hashing.file_sha256`,三处统一 |
| m7 | AC-1 的 config/seed/runtime identity 未落实 | CLOSED(文档):mini-plan AC 修订——request 冻结 config+请求身份(label/video digest);runtime identity 在 result 侧;seed 不作验收项(TrainingParams 无 seed,DLC 内部管理) |
| Nit ×3 | extra 可覆盖 `inputs`;i3② elapsed_s 未实现;TOCTOU 固有窗口 | CLOSED:reserved 全集保护;`ExternalJobHandle.elapsed_s` 落地;TOCTOU 记录为协议固有局限 |

Reviewer 同时确认"已查无问题"方向:digest 回显链闭合、迟到/强杀拒绝、EX4 唯一路径、快照 10 元素 undo/redo/save-reopen、availability symlink 语义、env 隔离、load 时遗留 pending/running→failed(i3③ 跨会话 lifecycle 闭环)。

## Verification

- 修复后全量 `python -m pytest`:**1054 passed, 9 subtests**(review 前基线 1044;新增 B1/M1/M1b/M2/M3/m1/m2/m3/m4 回归 10 个)。
- i3①(超时必须走 cancel)与 i3② 的 GUI 消费侧留 S6;Windows taskkill 分支维持 G4 真机门禁(P6 前)。

## S4 slice review(2026-09-28,同日实现后即时派发)

只读 review(独立于 S1–S3 gate):Verdict request-changes → **处置闭环**。

| ID | 摘要 | 处置 |
| --- | --- | --- |
| M1 (Major) | 源 config bodyparts 自身重复项经集合比较放行 | CLOSED:parse 阶段拒绝 duplicates;负例测试 |
| M2 (Major) | 同 basename 冲突分支无测试(plan 点名) | CLOSED:补 checkpoint↔extra 同名负例(注:config↔checkpoint 对互异源文件不可达,reviewer 前提修正)+ extra↔extra 用例 |
| m1 | staging 残留在 session 路径永不清理 | CLOSED:导入开始统一清扫 `models/*.staging`(幂等);测试 |
| m2 | engine 键缺失放行(旧 TF config) | CLOSED:显式 `engine == "pytorch"` 才接受;负例 |
| m3 | 原 config provenance 只剩 SHA | CLOSED:extra_fields 增 original_project_path |
| m4 | video_sets 不重写无显式决策记录 | CLOSED:代码注释 + extra_fields 决策记录 |
| Info ×4 | 测试死代码/误导名等 | CLOSED:清理 |

已确认无问题:发布原子性(staging 同卷兄弟目录+os.replace 末位)、路径安全(resolve+is_relative_to 全覆盖)、undo 后受管文件留存语义、Windows os.replace 同卷原子。

**验证:全量 1077 passed(+23 S4 测试,含 5 个 review 回归)。**

## S5 slice review(2026-09-28)

只读 review(对照安装的 DLC 3.0.1 源码核验真实行为):Verdict request-changes → **处置闭环**。

| ID | 摘要 | 处置 |
| --- | --- | --- |
| B1 (Blocker) | trained 模型 pose_cfg glob 用 TF 时代布局(`dlc-models/*/train/pose_cfg.yaml`),真实 PyTorch 引擎是 `dlc-models-pytorch/*/*/train/pytorch_config.yaml` → trained 半边 self-test 上线即死(Phase 4.3 同类教训重现) | CLOSED:glob 改真实 pytorch 布局(两级中间目录)+ mock 布局兼容保留;真实布局 fixture 测试;多匹配 warning |
| B2 (Blocker) | worker 假设 runner 输出是 bodypart→ndarray;真实 bottom-up 输出是 `{"bodyparts": ndarray(n_ind, n_bp, 3)}`(输出名键)→ 成功推理也判 missing | CLOSED:按真实结构读 `found["bodyparts"]`,形状(n, 4, ≥2)+有限性校验;adapter docstring 更正;协议级测试(真实 worker 进程 + 假 deeplabcut/torch 注入)钉住契约 |
| M1 (Major) | pose_cfg/pytorch_config 内容未冻结进证据(契约 §4 "换 config 内容撤销") | CLOSED:payload/worker 复核回显/verify/evidence 四处加 pose_cfg_sha256;组合入口对 trained 复哈希裁决 |
| M2 (Major) | effective_compatibility_state 无生产调用方,失效裁决是死代码 | CLOSED:新增组合入口 `model_effective_state`(availability → 证据裁决 → trained pose_cfg 复哈希),GUI/导出侧唯一裁决入口;优先级测试(unavailable > unverified) |
| m1–m4 | 多匹配静默、frame_index/VideoCapture 健壮性、状态机转移未声明未测、协议级测试缺口 | CLOSED:warning 日志;frame_index≥0 校验 + isOpened 检查;docstring 声明转移 + incompatible→compatible/mark-undo 测试;6 个回归测试 |

**验证:全量 1097 passed(+20 S5,含 6 review 回归;协议级测试经真实 worker 进程)。真实 DLC 推理链路(DLCLoader→runner→单帧)仍待 S6 smoke 实测。**

## S6 slice review(2026-09-28)

只读 review:Verdict request-changes → **处置闭环**。

| ID | 摘要 | 处置 |
| --- | --- | --- |
| B1 (major) | 完成回调无 session 上下文守卫;训练中可换项目 → 结果异常逃逸 Qt slot、UI 永久 busy | CLOSED:guarded/openVideo/AI _start 阻断 model busy;控制器捕获 session 身份,swap 即静默放弃+cancel;finish 路径 update_tracking_run 兜底 try |
| M1 (major) | 真实训练取消(强杀路径)被标 failed 而非 cancelled | CLOSED:cancel() 置 `_user_cancel`,read_result 抛错且标志置位 → cancelled 语义 |
| M2 (major) | prepare 成功但 start 失败留下孤儿 pending run,experiment 被 active-run 守卫永久锁死 | CLOSED:start 失败即 mark_run_failed + refresh;回归测试含"可再次 prepare" |
| M3 (major) | QComboBox 自动选中第 0 项,漏选 role 静默获得未显式选择的映射 | CLOSED:setCurrentIndex(-1),collect 的未映射分支复活;负例测试 |
| M4/m5/m6/m9 | 取消提示/`_job_dir` 状态/类型注解/启动即 running | CLOSED 逐一 |
| 补充缺口 | fixed check 冻结无 GUI 入口(P1.2 S4 只交付 session 动作)——没有它联合训练无法从界面走通 | CLOSED:测量卡第三动作 "Freeze fixed-check frames"(C1 预选 + 确认框),accept/decline 测试 |
| m7/m8 | 测试缺口(B1/M1/M2/关窗/映射负例)与 smoke 证据 | CLOSED:5+2 个回归;smoke 打印完整 runtime/versions 证据行 |

已确认无问题:迟到 success 无旁路、job 目录唯一性、device 链、verify 链未弱化、RecursionError 修复方向、定时器生命周期。

**验证:全量 1110 passed(+13);真实 DLC 双路径 smoke PASS(A:训练→引用→自检 compatible;B:导入→源目录移走→compatible)。**

## S6 后三路回归扫描(2026-09-28,用户指令:三个 subagent 扫库)

三个并行只读扫描(worker/协议域、训练数据域、模型引用/导入/GUI 域),对照 3f06de9 全量 diff + 通读 + 只读实验。**结论:无 Blocker、无数据损坏级 Major。** 共 1 个 Major-low + 14 Minor,处置如下(全部闭环或记档):

| ID | 域 | 摘要 | 处置 |
| --- | --- | --- | --- |
| W-F1 (Major-low) | worker | train_experiment 设备双源:GUI 宣称 CPU 但 params.device=auto → worker detect→MPS;host 不校验 train 的 actual_device | CLOSED:协议 device 为权威(worker auto 才自解析);host 对 train 的 actual_device 做 backend 匹配校验 |
| W-F2/F3/F4 | worker | job 目录为文件时裸 NotADirectoryError;Windows taskkill FileNotFoundError 逃逸;outputs 整文件读入内存 | CLOSED:包 OSError;taskkill 日志化(已有);改流式 file_sha256 |
| D-F1 (Minor) | 数据 | rebind_pendulum_roles 无 pending-run 守卫 + run 无删除 API → 潜在死锁(rebind 无 GUI 调用方,不可达) | 记档:rebind GUI 化时必须加 run 守卫;run 删除 API 列 P1.4 backlog |
| D-F2 (Minor) | 数据 | split 身份不在 digest/config(fixed check 被重冻结后旧模型溯源断裂) | CLOSED:request/config/worker 回显/verify 四处携带 check_frames |
| D-F3 (Minor) | 数据 | worker 丢 extra_params | CLOSED:改 TrainingParams.from_config(保留 extras) |
| D-F4 (Minor) | 数据 | verify 不检查 run 仍在 registry | CLOSED:registry 成员检查 |
| D-F5 (Minor) | 数据 | extras 的 engine_version 撞 canonical 键,save/reopen 后消失 | CLOSED:改名 worker_engine_version |
| G-F1 (Minor) | GUI | 忙碌守卫不对称(frame selection 在途可发起联合训练,digest stale 白烧训练) | CLOSED:三入口对称检查 |
| G-F2 (Minor) | GUI | importDlcModel 绕过 models.busy | CLOSED:补守卫 |
| G-F3 (Minor) | 域 | manifest sha 大小写不归一 → availability 永久误报(仅手改文件可达) | CLOSED:构造期归一小写 |
| G-F4 (Minor) | GUI | 导入向导只认 pose_cfg.yaml,真实 pytorch bundle(pytorch_config.yaml)无法自检 | CLOSED:向导双名接受;文案与 checkbox 联动更新 |
| G-F5 (Minor) | GUI | 非 ModelWorkerError(OSError)启动失败留孤儿 run;verify/register 的 ValueError 穿透 | CLOSED:except 扩 (ModelWorkerError, OSError) / (ProjectSessionError, ValueError) |
| G-F6 (Minor UX) | GUI | frame_set None 时禁用原因失真 | CLOSED:文案区分"先产帧集"与"先冻结检查帧" |

同时修复用户 HR 前实测反馈:**"Run joint training" 可点但失败只写在一闪而过的状态栏,读作死按钮** → prepare 失败改模态提示;过期文案 "joint AI training arrives in a later phase (P1.3)" 更新。

**验证:全量 1110 passed(净增 6:寄存器检查/check_frames 回显/守卫对称/冻结入口等)。已查无问题方向:digest 链、取消语义、行序三方一致、序列化 round-trip、导入原子性、DLC 3.0.1 真实布局与 runner 契约(对照安装源码)。**

## Human Review(2026-09-29,用户真人两轮 + 自动化预执行)

执行方式:agent 先以 GUI 自动化预执行 HR-A(联合训练主流程),用户本人随后真机完成两轮(标注补全、导入、训练、反馈)。协议:[p1.3-human-review.md](../../publication/plans/p1.3-human-review.md)。

### 结果

- **HR-A 联合训练:PASS**。用户经 Freeze fixed-check → Run joint training 在 test1 完成真实训练(外部 worker,result.json success,checkpoint-best-020.pt,DLC 日志含 test.mAR);数据链(prepare 唯一路径/digest 冻结/verify/register)全程闭环。
- **HR-B 教师导入:PASS(两轮)**。第一轮暴露自检配置选错(见 F-HR5),修复后第二轮导入 test1 训练产物并自检通过——test2_pendulum 中 imported 引用状态 **compatible**,导入→自检链端到端打通。
- **HR-C 持久化:PASS**(save/reopen 状态保留,自动化预验证 + 用户确认)。
- **HR-D 单轨回归:PASS**。
- **Q1–Q4:用户裁定通过**;数据安全否决项无(模型引用/训练产物/undo 均干净)。

### 用户反馈项(全部已修复;修复 commit 见括号)

| ID | 反馈 | 处置 |
| --- | --- | --- |
| F-HR1 | "Run joint training"点击无反应(失败只写状态栏 + 过期文案 "joint AI training arrives in a later phase") | CLOSED:prepare 失败改模态弹窗;按钮邻接禁用原因(fixed_check_valid);文案更新(`dbeb525`) |
| F-HR2 | 引导模式头部显示 "No track" 无提示 | CLOSED:guided context 显示 "Guided marking — clicks land on the prompted role"(`231e4d8`) |
| F-HR3 | Task history 无时间戳,多次 run 难区分 | CLOSED:条目前缀 "MM-DD HH:MM"(`231e4d8`) |
| F-HR4 | 导入向导窗口不自适应、不可调整大小 | CLOSED:resize(760,560)+size grip+wordWrap+combo 自适应(`920f0db`) |
| F-HR5 | 导入后自检失败 "11 validation errors for PoseConfig metadata" | CLOSED:根因=向导/resolve 把 test/pose_cfg.yaml 当模型配置;修复为 train/pytorch_config.yaml 优先(向导只收 pytorch_config;resolve 优先级重写);自检失败改模态弹窗(`1cdf615`) |
| F-HR6 | checkpoint 下拉为空(DLC 训练产物在嵌套布局深处) | CLOSED:向导递归扫描 dlc-models-pytorch/**/train/(`920f0db`) |
| F-HR7 | L source / g source 字段无解释,读作莫名其妙的必填项 | CLOSED:对话框顶部溯源说明 + tooltips + 窗口加宽(`ab8a8b7`);另确认 source 不参与计算,契约非空要求保留 |

### 概念澄清记录(用户提问,入档备查)

- **Calibration 标定长度 vs L**:前者是图像空间的 px↔mm 换算比率(换标定物即变);后者是摆的物理参数(悬点→质心),进周期/能量公式。数值巧合相等(用户沿摆长画 225mm 标定线)不代表语义相同。P2 两者都用:标定做几何换算(θ),L/g 进动力学模型。
- **tracked pivot 只作 QC**:物理计算(θ 重建)只用 fixed_pivot_px + true vertical,P1 计划明文。
- **推理按钮缺失是计划边界**:使用 compatible 模型做全视频推理→审核→四轨激活属 P1.4,非缺陷。

### 结论

用户裁定 HR 通过。P1.3 全部验收标准满足(S1–S6 + 四轮 review + 三路扫描 + 双路径真实 DLC smoke + HR)。**P1.3 关闭,合并 `feat/p1.3-joint-training` → `publication/ejp-damped-pendulum` 并 push。下一步 P1.4(joint inference/review/activation)待立项。**

## Verdict

Reviewer:request-changes → **处置后闭环**(B1+M1–M3+m1–m7+Nit 全部修复并复测,含既有 mock 适配 3 处)。S1–S3 gate 通过,进入 S4(teacher import core)。
