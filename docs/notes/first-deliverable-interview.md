# 首个可交付版本：目标任务与许可 / 分发访谈

- 日期：2026-10-26。
- 状态：第一轮Q1 / Q2待用户回答；建议未冻结，未选择新许可证或授权新发行。
- 范围：当前通用产品线main；P6.4完成，6.5尚未开始。历史发行单独记账。
- 方法：用户指定grill-me / grilling；按决策依赖分轮，事实由Agent核验，产品与授权取舍由用户决定，最终共同理解获确认后再实施。

## 已核实的前提

1. GitHub仓库当前public；根LICENSE仍为TBD占位。[ADR-0011](../decisions/0011-deeplabcut-integration-architecture.md)的D7已有MIT方向，Accepted内容保留，不以本次文档校正重写历史决策。
2. [v0.1.0](https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0)在2026-10-09作为未公证Apple Silicon Mac测试版公开。源提交为`54638e484ca3160d2d335e8f78c0580bef21949a`，本地归属`codex/ejp-p6-4-release`发行线，不在当前main历史中。发布说明声明主程序MIT，包含独立AI环境安装 / Repair、第三方notices与源码材料。该发行不代表当前main已打包，不自动授权下一次发行。
3. main已经有`Save PNG…`，是当前可见图表快照；依据[ADR-0010](../decisions/0010-current-chart-png-snapshots.md)，不含面板外设置 / 时序说明。完整CSV / Excel科学数据文件与归档仍待Phase 8，不把PNG快照重复列为从零开发项。
4. 当前requirements与本机为NumPy1.26.4 / OpenCV-headless4.11.0.86；本机Python3.12.13 / PyTorch2.13.0 / DLC3.0.1，CI用Python3.11轻环境。pyproject中DLC是版本范围，完整AI环境尚未在main锁定。
5. DeepLabCut实际3.0.1的分发元数据为LGPL-3.0-or-later，官方[项目说明](https://github.com/DeepLabCut/DeepLabCut)也说明以LGPL为主；原AGPL说法应校正。LGPL库、具体FFmpeg等二进制、模型权重分别核对，不能用主程序许可证代替它们的条款。
6. 默认DLC训练路径使用ImageNet预训练初始化；[timm许可说明](https://github.com/huggingface/pytorch-image-models#licenses)与[ImageNet访问条款](https://www.image-net.org/download)说明需要分别考虑权重和训练数据条件。当前没有据此认定应用或所有训练产物能 / 不能商业使用；首发是否附带模型、对外承诺什么使用范围仍待决策。
7. [MIT原文](https://opensource.org/license/mit)允许商业使用和再分发，要求保留版权 / 许可声明，不强制改版继续开源。此处只讨论原创软件代码的授权目标，不是整个AI运行环境的合规结论。

## 决策树与当前前沿

- 根A：主要用户与要完成的任务 → 实验 / 视频边界 → 首发必要功能与输出 → 验收与试用。
- 根B：原创代码的授权意愿 → 具体许可与历史决策衔接 → 第三方 / 模型边界。
- A / B明确后：分发对象、平台与安装要求 → 运行环境 / 权重交付 → 版本范围及完成条件。
- 所有分支闭合后：汇总共同理解，等待用户确认，再冻结计划与正式许可 / 分发决定。

本轮只问前沿的Q1 / Q2；没有把其余分支的建议当成已接受决定。

## 第一轮

### Q1：主要用户与目标任务（待回答）

建议：先面向大学物理实验的学生 / 教师，让他们把一段二维实验视频处理成可复核、能用于实验报告的数据和图。

替代方向：优先服务本人 / 科研同行的研究复现，或优先交付通用视频跟踪工具。

### Q2：原创代码的授权边界（待回答）

原Q2将开源与继续提供源码绑定，事实补查后已明确替换，不再作为本轮推荐。

当前建议：沿用既有MIT方向，允许使用 / 修改 / 商业使用 / 再分发，保留版权和许可声明；不强制别人的修改版继续开源。第三方库和模型权重各自遵守原许可，商业模型分发条件另行核对。

替代方向：希望改版再分发也必须开源，或希望限制为非商业 / 教育科研用途。用户可自由说明其他目标。

## 本轮文档事实校正

已校正development的环境版本、CI与完整AI环境的区别、Windows源码安装缺少`pip install -e .`及Public状态；README / roadmap / AGENTS / LICENSE占位中的DLC许可事实与历史MIT记录同步，补充历史Mac发行与main的区别；健康度报告的PNG与安装实现判断修正。

这些更正不选择新许可证、不修改已接受ADR、不改变仓库可见性或发布资产，也不进入6.5 / 新功能实现。当前LICENSE仍为占位，正式授权文本及下一版分发范围等待访谈收敛。
