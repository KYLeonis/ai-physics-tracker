# Initial Annotation Guidance — Human Review

- 日期：2026-10-13；分支 `fix/initial-annotation-guidance`。
- 首轮代码 `b9267e3`；当时全量 933 passed；Issue [#26](https://github.com/KYLeonis/ai-physics-tracker/issues/26)。
- `85be73e` [双平台 CI success](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38349426753)；真人反馈仍待用户执行。
- 用户第一次实测发现“标成前 20 帧”，已定位到推荐标注入口忽略算法结果；本轮修复后需重新检查代表帧的连续跳转。本次反馈不替代前置三项增量的 A/B/C 反馈。
- 本轮修复 `2fa955a`，定向 88；测试时钟稳定性修复后最终全量 938 passed，`653e315` [双平台 CI success](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38361205836)；原实验四个文件 SHA256 未改变。

## 启动

macOS 现有 `.venv`，在仓库根目录执行：

```bash
.venv/bin/python -m ai_physics_tracker
```

## 操作 → 预期

1. 新建项目，导入至少 20 帧的实验视频、创建 Track、保存 → 顶部推荐显示 `0/20`；在“调整本次设置”中选帧数量为 `20`、算法为 `K-means`。
2. 点击推荐的 `Pick representative frames` → 默认请求 20 个 K-means 代表帧；完成后推荐 `Label suggested frames`。点击后跳到列表中第一个未标代表帧；每次点击目标后跳到下一个列表帧，逐个核对视频帧号与列表一致，不会顺序扫描前 20 帧。候选不足时显示实际数量，选帧本身不自动标注。
3. 点击推荐旁的 `Custom frame selection…` → 弹窗直接显示 K-means / Uniform 及区别；选 Uniform 并确认后开始选帧，标注也沿其结果。取消不启动任务、不更改算法。
4. 通过推荐按钮开始整批标注，或在建议帧列表自选一批；19 个不同人工帧时首次训练禁用，完成 20 个帧后推荐 `Start learning`。已有点不被自动覆盖，跳过帧不算标签。对于 `20261013_test5` 这类已有 20 标签的工程，点击 `Select more representative frames` 可重新选帧补标；已存标注保留。无需为本次 HR 实际完成训练。
5. 新建另一个项目 → 选帧设置重新默认为 20 / K-means。

## 封闭反馈

- A：推荐标注是否严格沿建议列表跳帧，不再标成前 20 帧？是 / 否。
- B：推荐框的自定义入口与两种算法说明是否清楚、方便？是 / 否。
- C：20 帧门槛、自定义确认 / 取消、新项目默认值是否符合上述预期？是 / 否。

已有成功训练的轨迹仍允许按原门槛再训练；教师模型自检 / 推理不受首次学习标注门槛限制。
少于 20 个可标帧的视频不能完成首次学习要求；本轮没有放宽这个要求，也未重测完整 DLC 训练。
