# 省赛成功推理结果：P3.4 UI 测试工程

日期：2026-10-01。用户授权准备本地测试数据；P3.4 Human Review及四项反馈修复已获用户“通过，收尾”确认。

## 打开与体验

```bash
cd /Users/leonis/Documents/ai-physics-tracker-ejp
PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m ai_physics_tracker
```

File → Open project，选择下列任一工程中的 `project.json`：

- `provincial_ui_test/P011/project.json`
- `provincial_ui_test/P014/project.json`

进入 Analysis charts。Kinematics已有全片Angle、Angular velocity、Phase portrait与Reference energy；ODE fitting已有M0角度overlay、原始残差、参数/单位及完整区间RMSE，无需训练、推理或重标。

原视频为near-CFR，用户已明确同意本次UI测试使用平均帧率近似。每次打开GUI会重新检测；如显示Use approximate timing，点击并确认后可重新计算/编辑。这个确认不改变已有轨迹。

ODE拟合初始条件显式取自原TOML的历史θ₀/ω₀，预先计算释放后约20秒（601个源帧）以便快速测试。全视频与全部原始推理数据完整保留；可扩大Last source frame或选Compare M0+M1再运行。M0结果仅用于检查UI，不能当作M1或原省赛全片拟合的等价复现。

## 实际准备与验证

| 工程 | 视频帧数 | 有效θ | 可用ω/参考能量 | 已存M0状态 | 20秒区间RMSE(rad) | 历史effective release / LED帧 |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| P011 | 3344 | 3344 | 3250 | success | 0.02203917 | 94 / 95 |
| P014 | 3077 | 3077 | 2976 | success | 0.01154777 | 101 / 102 |

- 原视频字节复制，CSV/TOML/训练配置与划分日志各17份文件，复制前后SHA256一致；原件与test1/test2未修改。
- 四role映射：tip→marker_tip，其余同名。原likelihood保留，采用阈值0.6；辅助点不阻断tip+fixed pivot角分析。历史CSV是已完成推理的导入记录，不是当前机器重新推理。
- 历史effective release来自原TOML中明确保存的字段；不是重新对LED帧静默减1。平均FPS最大网格误差：P011约0.1385ms、P014约0.1567ms，精确探测见import-report.json。
- typed project保存/重开、immutable analysis/fit校验均有效。实际两工程payload送入Qt offscreen两个panel通过；各有601个ODE观测与601个原始残差。这不替代用户真人体验验收。
- `provincial_ui_test/import-report.json`记录输入源路径、各文件SHA/大小、时序报告、导入授权、结果计数和缺失项。整个数据目录约484MiB，已.gitignore，不提交到Git。

## 训练产物待补

已保存原训练配置、环境/训练摘要、177帧train/test划分等provenance。真正的snapshot-best-055.pt（原报告SHA256：667c8d7f147462a94ff29ea20ae44f5c127cbbc77285788a56c05768124f052e）与177帧labeled-data原始标签/图片未在本机找到；用户确认预计位于Windows，后续提供。当前工程无虚构train run或compatible模型引用，因此还不能用该省赛模型运行新的推理/微调。

用户提供Windows DLC完整项目（config.yaml、labeled-data、选中snapshot及pytorch_config.yaml）后，再用现有教师模型导入与真实self-test闭环。

## 下一步

P3.4已获用户整体验收及四项UI修复复测通过；运行步骤保留在[P3.4计划](../../publication/plans/p3.4-fit-ui.md)。停止等待P4指令，Windows训练产物待用户后续提供。
