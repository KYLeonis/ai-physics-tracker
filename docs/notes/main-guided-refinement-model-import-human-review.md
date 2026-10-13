# 本轮 Human Review：只读分析、连续修正与教师模型

日期：2026-10-11；分支 `feat/main-guided-refinement-model-import`；Issue [#24](https://github.com/KYLeonis/ai-physics-tracker/issues/24)。上一轮 HR 已通过，本轮是新增交互的独立验收。规则：AGENTS.md §7 / workflow.md §5.1，真人反馈后才集成 main。

## 启动

```sh
cd /Users/leonis/Documents/ai-physics-tracker
.venv/bin/python -m ai_physics_tracker
```

测试时打开一个实验视频，创建 Track，Save as 到一个尚不存在的新测试工程目录。不要用唯一的原实验工程做改写测试。

## 操作 → 预期

1. 在 Acquire 选 Track 标一点，再切 Analysis；点击视频 / 跳帧 / 选 Track、Ctrl/Cmd+Z/Y、审阅快捷键 A/S → 不改标注、审核记录或标定。返回 Acquire → 可以按原工作流编辑。
2. 点击推荐的 Pick representative frames → 可见建议列表；用 Cmd/Ctrl 或 Shift 多选 → Label selected frames；逐帧点目标 → 自动到下一张**选定**帧；Skip this frame → 不造点；Esc / Analysis → 暂停，Resume batch → 从保留的队列位置继续。做完且确有标注 / 足够 manual → 显示 Start learning 推荐，未点击前不会训练；全跳过时不声称已修正。
3. 对 completed inference 先筛查困难帧；多选一部分 → Correct selected frames；逐帧点击修正 → 写 manual 和 corrected 记录；未选帧保留；Skip 保存 skipped 审阅记录但不造标签，重开后仍已跳过；已有 corrected 项不会被 Skip 覆盖。完成 → 推荐再训练。若有足够 manual，可点击 Start learning 检查固定检查帧确认，再确认启动；需要时 Cancel。
4. Teacher model 的 Import（或 File → Import teacher model）依次选择同一模型的 DLC `config.yaml`、训练 `pytorch_config.yaml`、`.pt` checkpoint → 模型和关键点列表出现，尚不能 Generate。本轮支持单动物 PyTorch bottom-up RGB 未裁剪模型。
5. 显示视频的一帧，Self-test on displayed frame → UI 可响应 / 可取消；成功显示实际设备和帧号；auto 在本机优先 MPS，机器有 CUDA 则优先 CUDA。改变 device → Generate 禁用，必须重测；重测前先保存旧授权的撤销；失败 / 取消以及重开后不显示通过。切换视频 → 必须在该视频重测；同项目导入时切换视频不会丢掉模型。
6. 选择要跟踪的 bodypart，Generate trajectory with teacher → 只产生候选，不自动改当前轨迹；显式采用后已有 manual 点保留。Save / 关掉 / 重开，以及 Save as → 模型保留；同一视频内容、运行环境与 device 匹配时可继续用；视频重链接 / 内容变化要求重测，模型文件变化拒绝推理并提示重新导入。

## 反馈（通过 / 不通过）

- A：Analysis 只读且 Acquire 编辑正常？
- B：多选、自动推进、暂停 / 继续、跳过及完成后的训练推荐都顺手且符合预期？
- C：教师模型导入、自检、取消、选关键点生成候选、保存重开流程可用且提示清楚？

请用 `A/B/C：通过`，或注明不通过的具体步骤。自动化测试和截图不替代这些体验结论。
