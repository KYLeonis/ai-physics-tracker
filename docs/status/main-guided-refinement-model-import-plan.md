# Main Guided Refinement and Model Import Plan

- 日期：2026-10-11；分支 `feat/main-guided-refinement-model-import`，base main `6296617`。
- 用户明确授权三项：Analysis 视频只读；建议帧批量选择 / 连续修正 / 完成后推荐再训练；教师模型导入 / 实际帧自检。
- 状态：S1–S6 完成；2026-10-13 用户确认 Human Review A/B/C 全部通过，已 `--no-ff` 集成 main（`126e71d`）；Issue [#24](https://github.com/KYLeonis/ai-physics-tracker/issues/24)。
- 风险：High-risk（受管模型持久化、模型身份 / 后台自检、现有 review 原子修正）。

## Goal / Scope

1. Analysis 中视频不产生标注或标定编辑；Acquire 恢复正常编辑。
2. 代表帧与困难帧可选择一批，逐帧点击标注 / 修正、跳过 / 暂停 / 继续；未选项与审核记录保留。完成后只推荐训练，用户显式启动；建议 / Accept / Skip 不造 manual 标签。
3. 导入单动物 RGB bottom-up PyTorch DLC config + pytorch_config + checkpoint，安全解析、受管复制与 SHA256 manifest；支持从多 bodyparts 选择一个用于当前 Track。实际视频帧加载指定权重自检，明确 requested / actual device，成功后可生成主线候选轨迹，仍显式采用。
4. 主线保持 schema v1 的 additive 模型集合，保存重开 / Save as 受管资产保留；旧单轨训练 / 推理行为保持。不引入 publication experiment、四 role 约束、科学 ODE、external runtime 或 License 修改。
5. 按 ADR-0017 明确用户方程口径，旧 Phase 6 草案暂停实施；其余事项进入[后续档案](main-backport-backlog.md)。

## Agent Context Pack

- AGENTS.md §6–8、CODE_STANDARD.md、docs/workflow.md §5.1 / §6 / §10.2。
- spec/data-model.md、spec/project-format.md、spec/phase5-requirements.md；ADR-0013 review / ADR-0014 activation / ADR-0015 lineage / ADR-0016 workflow。
- research/open-source-project-map.md §3.4 / §3.5；前次完整区别文档 §3–8。
- 论文参考：42e853d（Analysis 保护）；批次重标 / teacher import / selftest 仅提炼通用行为，不整体 cherry-pick。
- 不变式：raw 像素 / 源帧时间；manual 优先、Correct 原子写点并保留预测 provenance；候选不自动采用；Accept / Skip 非标签；worker 独占请求，活动 session 仅 GUI 修改；迟到 / 取消结果不得登记 compatible；模型 / 配置 / 视频内容 / runtime / device 身份变化撤销旧兼容证据；重测前先保存授权撤销。

## Acceptance Criteria / Slices

- [x] S1：Analysis 切换 / 选轨 / 建议跳帧均只读，回 Acquire 可编辑；数据回归。
- [x] S2：双类建议帧多选；连续修正、暂停 / Esc、跳过 / 恢复；源帧错位拒绝、换 track/project 解除；完成明确推荐再训练。
- [x] S3：模型导入边界 / SHA / 原子发布 / schema v1 roundtrip / Save as；无伪训练 run。
- [x] S4：实际帧后台自检 / GPU 路由 / 取消 / 身份复核；导入模型推理 / 候选登记 / 显式采用。
- [x] S5：定向 + 全量、Independent Review（处置 findings）、分支双平台 CI、文档同步。
- [x] S6：新 GUI Human Review A/B/C 全部通过，--no-ff 合入 main（`126e71d`）；push / Issue 收尾见 current。

## Review Gate

- Independent Review：必须，完成可检查 diff 后由独立只读 reviewer 检查持久化、路径 / YAML 边界、取消 / 输入身份、review / AI 激活回归。
- PR：可选完整 diff 容器。
- Human Review：必须，三项交付完整后一次给出启动 / 操作→预期 / 封闭问题并停止等待。上一轮 HR 不覆盖新功能。

## Validation / Delivery

使用现有 synthetic fixtures、mock engine / runner 验证边界；实际 DLC 自检用已有开发环境和只读本地模型，成功证据仅声明实际覆盖。产品 / 测试改动在 src / tests，视频 / 权重不入库。

## Result

代码 checkpoint `1743f61` / `229b7d4` / `c998fd0` / `8018566` / `0c71910` 已 push。R1 F1–F6 处置见[review record](../reviews/main-guided-refinement-model-import-review.md)，R2 已关闭 F1/F2/F3/F5/F6，R3 Approve，F4 `0c71910` 补漏已关闭。修复定向 **45 passed（5.18 s）**；全量 **865 passed（77.50 s）**；[CI 38144024802](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38144024802) macOS/Windows Python 3.11 均 success（`0c71910`）。真实 DLC spawn 四关键点 actual-frame probe、3 帧 tip infer：`auto → mps` 成功。末轮 GUI guard 定向 28 passed，最新代码双平台 CI 已最终确认。

2026-10-13 用户确认 Analysis 只读 / Acquire 编辑（A）、连续标注修正 / Skip / Esc / Resume / 训练推荐（B）、教师模型导入 / 实际帧自检 / 关键点候选 / 显式采用 / 保存重开（C）全部通过。合并 `126e71d` 的树与分支 `a36007e` 完全相同；后续 6.1 和 20 帧引导按序集成，最终 main 产品 / 测试与 `653e315` 双平台 success CI 一致。main 验证及 Issue 收尾见 current。用户未提供逐项设备 / 平台详情，不扩大为 Windows CUDA 真机验收。
