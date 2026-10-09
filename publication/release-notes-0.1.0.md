# v0.1.0 — 未公证 Mac 测试版

面向 Apple Silicon Mac（arm64，macOS 14+）。本次发布按用户指令跳过付费 Apple Developer 签名/公证，标为 **prerelease**。最低 macOS 14 未做真机验收；已完成 Mac 冷装、自训/推理、Repair 的用户验收。

## 下载与安装

下载 `AIPhysicsTracker-0.1.0-arm64.dmg`，核对 `SHA256SUMS`，拖入 Applications。详细步骤见随包 `INSTALL.md`。若首次打开被 Gatekeeper 拦截，核对来源和校验值后，对本应用执行：

```sh
xattr -dr com.apple.quarantine "/Applications/AI Physics Tracker.app"
open "/Applications/AI Physics Tracker.app"
```

应用内 Settings → AI environment… → Install and use 安装独立 AI 环境，无需预装 Python。固定下载约 415 MB；首次训练可能另下权重，建议至少预留 4 GiB 加视频/模型空间。已有环境应用 OpenCV 修复需 Repair / reinstall；不要求重训。

## 功能与修复

- 单摆实验创建、约 20 帧推荐、每帧四点连续标注、自训/教师模型入口、推理真实进度、显式采用、困难帧小批重标循环。
- tip + fixed pivot 分析、自定义 SG、相图/reference energy、M0/M1 拟合、残差/参数图、可行域与科学结果导出。
- 修复安装版推理完成却无法读取 HDF5：采用受声明和 hash 校验的 CSV。
- 修复普通鼠标滚轮视频缩放、深色模式顶部推荐文字；触控板平移/捏合保留。
- Mac OpenCV 原 GPL FFmpeg 动态库已替换为同 ABI 的 LGPL 库，实际库许可和视频读写/seek 已核验；精确源码与构建脚本随发行提供。

## 来源与限制

二进制固定 source **54638e484ca3160d2d335e8f78c0580bef21949a**；[tests CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37735873436) 与 [packaging CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37735873042) 均双平台通过。DMG 196,260,240 bytes，SHA256：

```text
cf6afbbeaf11be77322761faa74418b814ac7986b3cb582f3f786bb45ab3e0e0
```

`release-manifest.json` 保留原 CI 构建时快照（其中 public_release_authorized=false 是历史值）；`release-decision.json` 记录随后用户授权此次公开测试发行。二者均不冒充 Developer ID、公证或新源码构建。

**未执行付费签名/Apple 公证。Windows 仅提供 Actions 测试包，本 Release 不分发 Windows 二进制；完整 Windows 实机/CUDA 门禁及新滚轮/深色提示真人复验仍待完成。** 安装版 teacher-import、非开发学生两条 pilot、完整安装版科学导出/恢复仍待补。新 GUI 视觉/滚轮改动有自动回归，尚未单独获得新版真人反馈。

缺帧保留缺失；near-CFR 需显式同意近似时序；reference energy 非焦耳；RMSE 下降不证明二次阻尼或唯一参数。ADR-0020 历史数值差异保留。

主程序 MIT；第三方各自许可，允许修改库与为调试库修改而进行逆向工程。`SOURCE-MATERIALS.md`、对应源码归档与原许可同页提供。下载的独立 AI runtime 另含 imageio-ffmpeg GPL 程序；不能称整个 AI 环境 GPL-free。用户视频、训练标签、权重、私钥不随发行分发。

## 随二进制发行的 VMAF 许可通知

Mac OpenCV 的 libaom 依赖 libvmaf 3.0.0。下面的上游全文及 `THIRD-PARTY-NOTICES.md` 与安装包一起提供，请保留：

```text
LICENSE - BSD+Patent
SPDX short identifier: BSD-2-Clause-Patent

Note: This license is designed to provide: a) a simple permissive license; b) that is compatible with the GNU General
Public License (GPL), version 2; and c) which also has an express patent grant included.

Copyright (c) 2020 Netflix, Inc.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
disclaimer in the documentation and/or other materials provided with the distribution.

Subject to the terms and conditions of this license, each copyright holder and contributor hereby grants to those
receiving rights under this license a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except
for failure to satisfy the conditions of this license) patent license to make, have made, use, offer to sell, sell,
import, and otherwise transfer this software, where such license applies only to those patent claims, already acquired
or hereafter acquired, licensable by such copyright holder or contributor that are necessarily infringed by:

(a) their Contribution(s) (the licensed copyrights of copyright holders and non-copyrightable additions of contributors,
in source or binary form) alone; or

(b) combination of their Contribution(s) with the work of authorship to which such Contribution(s) was added by such
copyright holder or contributor, if, at the time the Contribution is added, such addition causes such combination to be
necessarily infringed. The patent license shall not apply to any other combinations which include the Contribution.

Except as expressly stated above, no rights or licenses from any copyright holder or contributor is granted under this
license, whether expressly, by implication, estoppel or otherwise.

DISCLAIMER

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
