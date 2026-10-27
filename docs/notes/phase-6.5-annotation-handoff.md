# P6.5 — 20帧人工标注交接

- 日期：2026-10-27；[mini-plan](../status/phase-6.5-plan.md) / [分析回归报告](../benchmarks/phase-6.5-pendulum-report.md)。
- 当前只需完成标注并保存。这不是最终Human Review；新AI训练与科学验收在标注后继续。
- Agent已启动本地GUI并完成真实K-means选帧，`actual_n=20`；本轮不代做人工标注或启动训练。若窗口关闭，可用下方命令重开。

## 启动

在仓库根目录运行：

```bash
.venv/bin/python experiment/p65-acceptance/2026-10-27-final/annotate.py
```

本地启动器直接打开独立工程`experiment/p65-acceptance/2026-10-27-final/manual-project/`，
并调用既有后台K-means入口选择20个代表帧。项目名为`P6.5 P011 — manual annotation / new AI`，
轨迹名为`marker_tip — dark dot at block centre`。时序和原标定已准备，原P011工程不变。
若不使用本地启动器，也可`.venv/bin/python -m ai_physics_tracker`后从File / Open Project打开此目录，
点击`Pick representative frames`，保留20 / K-means。

## 操作与预期

1. 等待选帧完成，顶部推荐应变为`Label suggested frames`；点击它。
2. 每帧点击**木块中央黑色圆点的中心**；程序沿实际推荐帧队列跳到下一帧。连续完成20个不同人工帧，不需要顺序遍历600帧。
3. 完成后显式Save，停在此处，回复“20帧已标好”；若有问题，附操作与实际结果。先不点击`Start learning`，由Agent核对标签 / 固定检查集与训练协议后继续。

后续首次训练时Keep默认4个固定检查帧，其余16帧用于训练；不必额外标4帧。
若真实错误需Correct，由用户亲自修正。总计最多启动两次训练，失败或取消也计次；当前0 / 2。

本轮自动准备 / offscreen核对不代替你的真实标注，也不替代最终HR。不要在旧冻结DLC工程上标注。
