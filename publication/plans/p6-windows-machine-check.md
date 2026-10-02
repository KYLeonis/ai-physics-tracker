# Windows 真机验收便捷指南

日期：2026-10-02；状态：未执行。Mac HR已通过，不能据此勾选Windows门禁。

## 下载与启动

不需要pull源码或安装Git/Python。登录GitHub，下载已通过原生构建的Actions artifact：

- [Windows artifact](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37025219904/artifacts/11234523951)：`AIPhysicsTracker-windows-x64`，约201MiB，提交`6bb0ff8`，与已验收产品代码相同。
- 若直接链接失效，在[该次packaging页面](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37025219904)下方Artifacts点击同名包。
- GitHub外层ZIP中有`AIPhysicsTracker-0.1.0-win64.zip`；再解压内层ZIP。
- 把整个`AI Physics Tracker`目录放到本机短路径，例如`C:\APT-Test\`，运行其中`AIPhysicsTracker.exe`。保留全部随包子目录，不单独搬exe，不在ZIP预览内启动。

这是测试便携包，尚未创建GitHub Release/tag。

## 最小验收顺序

| 操作 | 预期 / 对应证据 |
| --- | --- |
| 打开exe；导入一小段本地视频，标注、保存、关闭重开 | 窗口/视频/随包FFprobe正常；G1及项目重开 |
| Settings → AI environment → Windows CPU → Install and use；Check current environment | 独立Python安装与Torch/DLC自检成功；G2。安装时取消一次，再重试，旧环境保留 |
| 建立单摆测试工程，推荐帧→四点标注；Advanced epochs=1、device=CPU；训练后用新模型推理 | 真正小型train+infer成功，显示进度/候选；G3。使用视频与工程副本，不覆盖原实验 |
| 在一次较长推理中点击Cancel；任务结束后重试，能再次完成 | GUI可响应、取消状态正确、重试可用；G4。进程树是否残留须另外核查，不能只凭UI写通过 |
| NVIDIA笔记本另装CUDA profile，Check通过后Advanced选auto或cuda，再做小训练/推理 | 记录实际backend为cuda及真实任务成功；CUDA单列，不以available替代train/infer |
| 保存工程，断网重开并用已有模型推理，导出分析图与CSV | 已安装环境离线可用、可携带工程/科学导出正常 |

首次AI安装与可能的预训练权重下载需要联网；离线项安排在成功训练/推理后。CPU基线先验证，再测CUDA，便于定位驱动/设备问题。

## 反馈与记录

返回Windows版本、显卡型号/驱动、CPU与CUDA分别通过/失败、失败截图。
安装问题用Settings中的Export diagnostics导出；训练/推理问题同时提供任务日志。
记录实际操作结果后才更新G1–G4/CUDA；现有开发机测试不能直接称为G5无Python干净机器通过。

G5真正无Python的Windows x64环境及外部学生pilot属于后续发行验收，仍not_run。
此指南是现有P6交付的验收说明，不启动P6.3实现，也不授权公开发布。
