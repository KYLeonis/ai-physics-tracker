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

## 在途推理

- request选择上述最佳040模型；3320帧，min confidence0.6，batch8，CPU。
- 14:11:44核查：worker PID65268仍存活（已运行约1时54分，CPU326.5%）；原始tqdm日志约37%（1239/3320），尚无result。此计数来自旧日志，不能当作新功能的后处理完成计数。
- 用户GUI尚未将训练后状态写入最后11:53:17的manifest；不能把其空模型/run数组解释为训练未发生。完成后由用户保存GUI状态。
- 保持当前运行。`827f31f`的新进度仅在重启GUI后的新worker生效：后处理计数→帧数/百分比/耗时/平均速度/约ETA；预测100%仍需保存与结果验证。

## 本地证据

均位于工程`data/engines/`下：

- 训练`84703a2a-e4de-424c-8d0f-dc5dae55e2b4/request.json`、`result.json`、`dlc-project/dlc-models-pytorch/iteration-0/dlc-projectOct02-trainset81shuffle1/train/learning_stats.csv`。
- 自检`selftest-3e5ba573-b2ed-4521-a52a-57175a95d4ac-1bfdef0d/result.json`。
- 推理`fdb7db0e-148d-4e85-b86a-94c6f1534534/request.json`、`worker.log`；上述在途状态是核查时点，后续应以最终result及GUI审核为准。

未提交视频、训练标签、模型权重或运行产物。
