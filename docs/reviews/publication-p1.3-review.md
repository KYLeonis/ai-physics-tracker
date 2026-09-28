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

## Verdict

Reviewer:request-changes → **处置后闭环**(B1+M1–M3+m1–m7+Nit 全部修复并复测,含既有 mock 适配 3 处)。S1–S3 gate 通过,进入 S4(teacher import core)。
