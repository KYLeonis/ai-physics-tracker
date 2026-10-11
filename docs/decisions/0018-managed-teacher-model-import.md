# ADR-0018：受管教师模型与实际帧自检

- Status: Accepted
- Date: 2026-10-11
- Scope: main；用户授权的教师模型导入增量，Issue #24。

## Context

现有单轨推理要求当前 Track 的 completed train run。外部教师模型没有本工程的训练成员履历，不能伪造训练记录，也不能直接套用论文线四角色 / schema v2。模型导入必须在保存重开、Save as 后可用；静态文件检查不足以证明当前机器可以推理。

## Decision

- schema v1 增加可选 `imported_models` 集合；空集合不写入。旧 reader 按原有未知键保留规则保留它。每项含 UUID、名称、**有序** bodyparts、三个文件的 SHA256、自检证据和保留的未知键。
- 三份资产受管于 `models/<UUID>/{config.yaml,pytorch_config.yaml,checkpoint.pt}`。安全解析 YAML，分块复制 / 哈希至独占 staging，再 rename；拒绝符号链接逃逸与配置 / 关键点顺序不匹配。Save as 复用整个受管项目树复制。
- 本轮支持 single-animal、bottom-up、RGB、PyTorch、未裁剪模型；用户从多个 bodyparts 中选一个用于当前 Track。多动物、detector / top-down 不纳入本轮。加载权重强制 `load_weights_only=True`，不按源 YAML 放宽。
- 实际帧自检在独占 spawn worker 中解码**当前源视频的实际选定帧**、RGB 输入、加载指定权重并运行推理，检查全部关键点的形状、有限值与 confidence 范围。记录视频 UUID / 完整 source SHA256 / size+mtime、帧 hash、模型 manifest hash、Python/Torch/DLC/OS/架构和 requested / actual device。
- `auto` 复用 CUDA→MPS→CPU；不把失败伪装为 CPU 成功。模型内容、视频身份 / 内容、运行环境、所选 device 或 auto 的实际设备变化后要求重新自检。GUI 轻量 stat 检查，后台准备、推理前后及提交核对视频完整哈希；同尺寸同 mtime 替换也拒绝。重测先持久化撤销旧自检授权，保存失败不启动探针；取消、失败或上下文变化不接受迟到成功。导入是项目操作，可交付同项目切换视频后的会话；实际帧探针仍绑定原视频 / delivery generation。
- 全视频推理复用既有 TrackingRequest → worker → completed candidate → 显式 Activate/Replace。原 bodypart / 模型身份写入 infer config；单轨原始 CSV 使用内部 `target` 列，继续兼容困难帧筛查 / 预览。不产生虚假 train run，不自动采用，manual 优先。
- 自检只是运行兼容性证据；外部模型训练成员未知，固定验证比较资格保持 unknown，不宣称独立准确性。

## Consequences

不新增引擎栈；安全 YAML 使用 DLC 已有的 PyYAML（轻量 CI 环境显式锁定）。受管模型占工程磁盘空间，导入 / 推理 / 提交前 SHA256 增加后台 IO。这里只提供基础受管集合，Phase 7 完整模型版本库仍待立项。主线分析方程口径不受影响（ADR-0017）。
