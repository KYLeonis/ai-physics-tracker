# 许可与分发边界

2026-10-26用户在[首发访谈Q17](notes/first-deliverable-interview.md)确认整体目标；本文件记录当前原创代码许可及后续教学试用的分发目标。具体交付范围见[首个可交付版本目标](spec/first-deliverable-target.md)。

## 原创软件

原创软件代码与本项目原创软件文档采用[MIT License](../LICENSE)，包元数据以`License-Expression: MIT`声明。该决定沿用[ADR-0011 D7](decisions/0011-deeplabcut-integration-architecture.md#d7-license-合规)及历史Mac发行的MIT方向。

按[MIT原文](https://opensource.org/license/mit)，允许使用、修改、商业使用和再分发，保留版权及许可声明；不强制修改版继续开源，也不增加仅限教育科研 / 非商业的原创软件使用限制。

第三方软件、二进制、模型权重与视频素材各自适用原有条款；本项目MIT不替它们重新授权。Accepted ADR保留当时记录，具体发行审核以实际版本 / 文件和对应条款为准。

## 默认AI与模型权重

- 首发验证默认AI路径用于教学科研，不承诺所有预训练 / 教师权重均可商用；需要商业AI场景时另行核实相应权重，不因此修改原创代码MIT。
- 官方安装包不附带第三方预训练 / 教师权重；首次准备从核实来源下载必要初始化权重，记录具体版本 / 文件、来源与适用条款。准备后已缓存的支持路径应可离线使用。
- 用户训练得到的模型保存在本机；其使用 / 分发条件按所采用的权重及相关条款核实，不能仅据本项目MIT认定。按需下载也不替代许可核对。
- 默认初始化涉及timm / ImageNet，依据[timm许可说明](https://github.com/huggingface/pytorch-image-models#licenses)、[ImageNet条款](https://www.image-net.org/download)及具体权重卡逐项记录，不把库许可当作所有权重许可。

## 第三方材料与具体发行

已核验的DeepLabCut 3.0.1为LGPL-3.0-or-later，见[官方项目](https://github.com/DeepLabCut/DeepLabCut)；此前AGPL描述不再作为当前依据。PySide6 / Qt、FFmpeg等二进制需按实际版本、模块及构建选项核对，不能把完整AI环境统一标为MIT或假定均无GPL成分。

下一次制作试用包时，按实际随包组件提供相应版权 / 许可声明及适用的源码、修改或替换材料；已有[Matplotlib及字体许可原文](../resources/licenses/matplotlib-3.8.4/)应随相关组件保留。最终清单与构建来源在打包计划中固定；本次源码MIT收口不等于具体安装包的第三方许可审查已完成。

真实单摆素材须有供试用者使用 / 分发的授权记录。研究目录中的现有视频不自动具备教学包再分发权；合成样例须标明生成方法、参数及合成身份。

## 分发目标与历史发行

当前main的首次交付目标为Mac arm64小范围教学试用：我们提供安装包、环境准备入口、样例及教程，试用者无需配置Python。允许首次联网准备，准备后支持流程离线；本轮接受未公证包的单应用手动放行，正式签名 / 公证不设为本轮门槛。

[v0.1.0](https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0)是2026-10-09基于`54638e484ca3160d2d335e8f78c0580bef21949a`的历史Mac测试发行，遵循自身许可材料，包含独立AI环境安装 / Repair。当前main须受控核对复用范围并重新验证；本次目标冻结不自动创建或上传新发行资产。更广泛公开发行与Windows正式交付后续推进。
