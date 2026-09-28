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

## Verdict

Reviewer:request-changes → **处置后闭环**(B1+M1–M3+m1–m7+Nit 全部修复并复测,含既有 mock 适配 3 处)。S1–S3 gate 通过,进入 S4(teacher import core)。
