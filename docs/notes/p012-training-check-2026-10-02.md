# P012 training / inference read-only check — 2026-10-02

本轮只读文件与进程，未保存/重训/取消用户工程。时间为Asia/Shanghai；核查工程为`/Users/leonis/Documents/ai-physics-tracker-ejp/P012_teacher_test`。

## 训练结论

- 11:53:38–12:03:01，约9分23秒；worker `success`，实际CPU，DLC3.0.1 / Torch2.13.0。
- 21完整四点帧：17训练、4检查；检查帧378/1053/1242/1917；50 epochs，batch8。
- 选用`snapshot-best-040.pt`（94,983,123bytes），config/checkpoint存在且SHA-256与result清单一致。模型12:03:05–12:03:13 self-test `success`，四角色映射完整，实际CPU。

| Epoch | Check total loss | Check RMSE (px) | RMSE with likelihood cutoff (px) | mAP / mAR |
| --- | ---: | ---: | ---: | ---: |
| 40 (selected) | 0.001976136351 | 4.184875488 | 3.561297735 | 100% / 100% |
| 50 (last) | 0.002200112212 | 112.960464478 | 3.202646573 | 50% / 50% |

最后一轮检查表现下降，所选最佳40轮比最后50轮更合适。cutoff RMSE排除了低置信度点，不能单看它较小就选择50轮。检查集仅4帧，不能由此宣称全视频精度通过。

## 推理过程与完成状态

- request选择上述最佳040模型；3320帧，min confidence0.6，batch8，CPU。
- 14:11:44核查：worker PID65268仍存活（已运行约1时54分，CPU326.5%）；原始tqdm日志约37%（1239/3320），尚无result。此计数来自旧日志，不能当作新功能的后处理完成计数。
- 用户GUI尚未将训练后状态写入最后11:53:17的manifest；不能把其空模型/run数组解释为训练未发生。完成后由用户保存GUI状态。
- 上述是14:11的在途观察；最终worker于16:34:54返回`success`，实际CPU，从12:17:53开始共4小时17分02秒，3320/3320帧四角色坐标完整。完整计数不代表每点都达到confidence阈值或全视频标注精度通过；仍由用户审核/采用候选并保存GUI状态。
- `827f31f`的新进度及`5ada419`的auto路由仅在重启GUI后的新任务生效；无需重训已有模型。后处理计数→帧数/百分比/耗时/平均速度/约ETA；预测100%仍需保存与结果验证。

## 同模型加速核查（17:09，本机Apple M1 / 8 GB）

- runtime为Torch2.13.0 / DLC3.0.1；CUDA不可用，MPS可用。上述CPU任务结束后，使用其实际ResNet50GN `snapshot-best-040`，经生产external worker在独立临时目录执行`device=auto`单帧自检：`success`，`actual_device=mps`，四角色finite，含启动/加载约9.678秒。用户工程及模型文件未写入。
- 另用相同原视频1080p帧0/94/1660/3319做小样对照，batch1、multithreading关闭；每项重新建runner、先预热，计时前后MPS同步。编译缓存及临时目录完成后已清理。

| 模式 | 加载及预热 (s) | 同4帧推理 (s) | frames/s | 与CPU坐标最大差 (px) |
| --- | ---: | ---: | ---: | ---: |
| CPU FP32 | 2.111 | 5.851 | 0.684 | 0 |
| MPS FP32 | 3.113 | 3.111 | 1.286 | 0.000061 |
| MPS autocast | 2.845 | 3.220 | 1.242 | 0.010615 |
| MPS compile / inductor | 9.543 | 3.403 | 1.175 | 0.000061 |

四项输出均finite。本样本MPS FP32吞吐约CPU的1.88倍；autocast/compile没有进一步提速，因此保持两项false，不修改原模型config或hash。4帧/batch1结果不能外推全片耗时、其他batch、其他GPU或测量精度；Windows CUDA仅有路由自动化验证，未真机测速。8 GB机器建议先用batch1–2观察速度与内存，再按结果调整。

[DLC配置说明](https://deeplabcut.github.io/DeepLabCut/docs/pytorch/pytorch_config.html)：compile有初始化及兼容成本；autocast可能改变预测精度。开关可用不代表必然更快；优先用已验证GPU。

## 本地证据

均位于工程`data/engines/`下：

- 训练`84703a2a-e4de-424c-8d0f-dc5dae55e2b4/request.json`、`result.json`、`dlc-project/dlc-models-pytorch/iteration-0/dlc-projectOct02-trainset81shuffle1/train/learning_stats.csv`。
- 自检`selftest-3e5ba573-b2ed-4521-a52a-57175a95d4ac-1bfdef0d/result.json`。
- 推理`fdb7db0e-148d-4e85-b86a-94c6f1534534/request.json`、`worker.log`、`result.json`；最终result与GUI审核决定候选状态。

未提交视频、训练标签、模型权重或运行产物。
