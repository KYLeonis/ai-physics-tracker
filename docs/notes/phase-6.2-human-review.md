# Phase 6.2 Human Review

2026-10-14；状态：**用户确认其余 HR 通过；轨迹多选修复待补测**。原科学 / 事务独立复审通过；最新控件修复 `76e9439` 的51项GUI回归及[macOS / Windows CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38580981879)通过，尚未合并 main。
分支 `feat/p6.2-angular-charts`；Issue #27 / draft PR #28。前轮 HR 不覆盖这些新图表 / 参考配置。

## 启动

macOS 项目已有 `.venv`，在仓库目录运行：

```bash
.venv/bin/python -m ai_physics_tracker
```

File → Open project，选本机合成工程：
`/Users/leonis/Documents/ai-physics-tracker/.zcode-control/hr-demo-project/project.json`。
三条轨迹 Bob 1 (gap 80-84) / Bob 2 / Pivot B；240 帧 / 30 fps，已有标定，固定支点 `(160, 40)` px。
Bob 1 的 80–84 帧故意没有观测。该工程仅供功能验收，不是实际实验准确性证据。
2026-10-14 已补齐工程内 `videos/angular-demo.avi`，更新合成工程的受管路径与文件指纹；实际 `open_project` 路径通过媒体身份、240 帧 CFR 与解码检查。等待时序验证完成后再测试重算。

## 操作 → 预期

- **A 参考与角量**：切 Analysis / θ(t)，只勾 Bob 1。把 pivot x 改161，再改回160；先不点击 Apply reference，重算应禁用。确认 pivot y=40，点击 Apply reference → Recompute checked tracks，θ/ω/α/θ–ω都有数据，图例有实际支点 / 当前单位，degree/rad切换可用；视频点击、A/S、Undo/Redo均不改观测。Measured position / Smoothed position 的 θ 来源可区分（wrapped / unwrapped）。
- **B 两点与多轨迹**：切 Reference track B，选择 Pivot B / Apply，再勾 Bob 1与Bob 2并重算。两曲线以同一A→B定义比较，图例有参考。若再勾Pivot B并请求重算，明确拒绝自引用而不改结果；取消勾选后可继续。
- **C 相图导航**：切x–vx并重算，复用线性数据，角参考不影响此动作；点击θ–ω或x–vx真实点能跳正确源帧，显示定位轨迹，相图没有时间直线。将视频跳到82帧时，Bob 1不高亮虚构点；缺口不画连接线。时间图点击 / 拖动仍保留请求与呈现的双游标。
- **D 保存恢复**：选θ–ω、degree、SG window=9 / Order=2后重算并Save，等待保存结束，关闭重开同工程。实际参考、SG、单位及图表页恢复；修改参考/SG后会明确提示未应用，已有缓存配方仍可检查。旧x/y/v/a/xy与Fit/Save PNG/面板滚轮正常。

## 用户反馈

2026-10-14 用户反馈：“在这个框无法勾选两个轨迹，其余HR通过”。截图中 Bob 1 有勾选记号，Bob 2 只有灰色高亮。对应 B 的多选交互阻塞；其余通过结果保留。

修复 `76e9439`：空框明确可见；点击轨迹名称或框均独立切换勾选，去掉容易误解为勾选的单行高亮；刷新保留当前行，方向键 / 空格可连续勾选，列表空格不启动视频播放。修复已同步到原 P6.2 工作分支，实际鼠标 / 键盘输入回归通过。

### 仅需补测轨迹多选

关闭旧应用，在主项目目录重启：

```bash
cd /Users/leonis/Documents/ai-physics-tracker
.venv/bin/python -m ai_physics_tracker
```

打开上方合成工程，Analysis 中参考 B 选 Pivot B / Apply：

1. 依次点击 Bob 1、Bob 2 的名称或复选框 → 两者可同时勾选；点击其中一个取消 → 另一个保持勾选。
2. 再勾回 Bob 1、Bob 2，重算 → 两条曲线都显示，Pivot B 保持未勾选。
3. 焦点在列表时用方向键 / 空格选择 → 正常切换勾选，视频不开始播放。

请只反馈这一项：通过 / 不通过（不通过注明现象）。

## 停止关卡

[AGENTS.md §7](../../AGENTS.md)要求“停止并等待用户亲自测试的反馈”。本轮反馈通过前不合并main、不结束P6.2、不进入6.3。自动化测试与独立review不替代体验验收。
