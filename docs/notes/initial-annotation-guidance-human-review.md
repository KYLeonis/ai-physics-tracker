# Initial Annotation Guidance — Human Review

- 日期：2026-10-13；分支 `fix/initial-annotation-guidance`。
- 代码 `b9267e3`；最终全量 933 passed；Issue [#26](https://github.com/KYLeonis/ai-physics-tracker/issues/26)。
- 自动验证完成后待用户真人测试；本次反馈只覆盖首次标注 / 选帧入口，不替代前置三项增量的 A/B/C 反馈。

## 启动

macOS 现有 `.venv`，在仓库根目录执行：

```bash
.venv/bin/python -m ai_physics_tracker
```

## 操作 → 预期

1. 新建项目，导入至少 20 帧的实验视频、创建 Track、保存 → 顶部推荐显示 `0/20`；在“调整本次设置”中选帧数量为 `20`、算法为 `K-means`。
2. 点击推荐的 `Pick representative frames` → 默认请求 20 个 K-means 代表帧；候选不足时显示实际帧数，不自动标注。
3. 点击推荐旁的 `Custom frame selection…` → 弹窗直接显示 K-means / Uniform 及区别；选 Uniform 并确认后开始选帧，随后普通选帧按钮也沿用 Uniform；取消不启动任务、不更改算法。
4. 在建议帧列表选择一批并连续标注；检查 19 个不同人工帧时 → 显示 `19/20`、首次训练禁用；补标第 20 个不同帧后 → 推荐 `Start learning`、高级训练可用。重复修正同一帧不增加计数，跳过帧不算标签。无需为本次 HR 实际完成训练。
5. 新建另一个项目 → 选帧设置重新默认为 20 / K-means。

## 封闭反馈

- A：20 帧计数与首次训练放行时机是否正确？是 / 否。
- B：推荐框的自定义入口与两种算法说明是否清楚、方便？是 / 否。
- C：自定义确认、取消与新项目默认值是否符合上述预期？是 / 否。

已有成功训练的轨迹仍允许按原门槛再训练；教师模型自检 / 推理不受首次学习标注门槛限制。
少于 20 个可标帧的视频不能完成首次学习要求；本轮没有放宽这个要求，也未重测完整 DLC 训练。
