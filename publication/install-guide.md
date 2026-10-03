# AI Physics Tracker 0.1.0 — 安装与使用

这是 **Mac 首发候选说明**，尚未公开发行。当前候选未取得 Developer ID 签名/Apple 公证，首次下载启动可能被系统拦截；普通用户双击安装的验收尚未完成。正式下载地址将在发布获授权后补入。

## 支持范围与空间

| 平台 | 当前范围 | 验证情况 |
| --- | --- | --- |
| Apple Silicon Mac，macOS 14.0 或更新 | CPU / MPS；不需要预装Python | 原生构建、独立AI环境、用户训练/推理HR通过；另一台M5/macOS27冷装通过但需去隔离。最低系统14.0是包要求，未在14.0真机验收 |
| Intel Mac | 不提供此版本 | arm64 DMG不能作为Intel安装包 |
| Windows x64，Windows10/11目标 | CPU / NVIDIA CUDA13.0候选 | 双平台CI通过；**暂未实机验证**，不作为本次Mac发行支持承诺；portable zip，无安装器 |

P6.3实测：DMG约141 MB、应用本体约304 MB；最终P6.4体积以候选清单为准。Mac AI环境固定下载 **415,025,090 bytes（约396 MiB）**；本机一个已就绪环境含Python共 **1,603,141,698 bytes（约1.49 GiB）**，另有约396 MiB下载缓存。建议首次安装预留至少 **4 GiB空闲空间**，另给视频、模型和训练结果留空间；不是训练硬件最低规格测试。修复会保留旧环境，因此还需空间。预训练权重在首次训练时可能另外下载，未计入上述固定量。

## 安装与首次打开

1. 下载适合Apple Silicon的DMG。打开后把 **AI Physics Tracker** 拖入 **Applications（应用程序）**。
2. 弹出磁盘映像，从Applications双击应用。无需下载源码、配置Python或启动终端。
3. 若系统报“已损坏/无法验证开发者”，当前包尚未达到正式下载启动门禁；记录系统版本和提示反馈给维护者。新系统上右键打开不一定有效。测试人员已授权的去隔离方法仅在[Mac测试HR文档](plans/p6.3-mac-human-review.md)中提供；它不是普通用户安装要求。

## 安装AI环境

1. 打开 **Settings → AI environment…**，选择 **Apple Silicon (CPU + MPS)**，点击 **Install and use**。
2. 下载显示实际字节进度；解包、安装和自检显示阶段/耗时。网络或空间不足会明确失败，可点击 **Export diagnostics…** 保存日志。**Cancel** 后等待任务停止，再重试。
3. 验证成功后点 **Check current environment**。以后重开会沿用这个独立环境，无需每次安装。
4. 已有环境出错时使用 **Repair / reinstall**。失败或取消保留原有可用环境及项目，成功后采用新环境；不要在训练/推理活动时升级或替换应用。

## 标注 → 训练 → 推理 → 改善

1. 在 **Experiment setup** 创建单摆实验，选视频和一个空项目文件夹（或已有父文件夹内的新文件夹）。完整填写标尺、固定pivot、真实竖直、tip半径参考、L/g和release frame。
2. **Acquire trajectory → Recommend 20 frames → Label recommended frames**。每帧按提示依次标tip、body_top、body_bottom、pivot，四点完成后自动跳到下一推荐帧。
3. **Run joint training**。Advanced的device默认 **auto**：Mac选择可用MPS，否则CPU。也可显式选CPU用于诊断；显式后端失败会报告错误，不悄悄重跑CPU。compile/autocast目前默认关闭。
4. **Verify / run inference**，查看实际帧数进度。完成后先检查候选，再显式采用；推理成功不代表所有位置都可信。
5. **Mine difficult frames**，从推荐困难帧中选自己愿意重标的小批，标完重训→再推理→审核采用，可反复继续。不要一键接受未经检查的所有帧。

也可 **Import teacher model…**，通过本机模型自检后推理。此功能有自动检查，P6.3最新安装包的teacher-import完整真人验收仍待补，教师模型不随安装包分发。

## 图表与科学限制

采用的tip和fixed pivot用于角度/角速度/相图，body_top/body_bottom为辅助诊断。新候选预览不自动进入分析；修改、采用或更改设置后需重新计算。

SG窗口/阶数可设置，导数需要足够连续的有效帧；缺帧保留缺失，不能靠跨长缺口补点制造相图。ODE拟合使用有效原始角度，SG不阻挡拟合。near-CFR视频需明确 **Use approximate timing** 后计算，界面会显示近似误差；真正VFR不按平均FPS伪装测量。

M0/M1对比、残差、参数/起点诊断和可行域是模型检验工具；RMSE变小不等于证明二次阻尼，也不保证参数唯一。reference energy是代理量，非焦耳。完整安装版科学/导出/恢复及非开发学生双路径pilot仍有发行待补证据，参见[当前状态](STATUS.md)。

## 离线、升级与卸载

- 首次安装AI环境需网络；首次训练可能需要权重下载。环境与对应模型/权重齐备后，视频测量、已有模型推理及图表/导出可离线运行。现有模型离线MPS推理已有验证，不能推断所有首次训练都能离线。
- 更新前保存项目、等待活动任务停止、退出应用，然后替换Applications中的.app。项目与AI环境在应用之外，不随.app替换删除。没有自动更新器。
- 卸载应用：把Applications中的.app移入废纸篓。默认保留用户工程及AI环境。若确定不再使用，可在Finder **前往 → 前往文件夹…** 输入 `~/Library/Application Support/KYLeonis/AI Physics Tracker/`，确认无任务运行后把该目录移入废纸篓；这会移除AI环境、缓存和日志，下次使用需重新安装。
- 项目目录及自己的视频由用户自行管理，不在上述应用数据目录中自动清理。工程复制/跨平台重开仍需实际验证，不把Windows CI当作该验证。

## 许可与反馈

主程序MIT；Qt、FFmpeg、DLC等保留各自许可。**AI environment → Third-party licenses and source details…** 可查看原许可和来源；[打包材料](../packaging/NOTICE-third-party.md)与[源码入口](../packaging/SOURCE-MATERIALS.md)随候选附带。反馈请提供应用版本、系统/芯片、操作和导出的诊断，不必发送视频或私钥。
