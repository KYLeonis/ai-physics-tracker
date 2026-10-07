# 0.1.0 Mac release notes — draft

状态：**候选，尚未公开发布**。建议版本0.1.0/tag `v0.1.0`，尚未创建；仅用户明确说“发”后可执行。最终source commit、DMG SHA256和签名状态见候选清单；这份草案不授权上传。

## 本版功能

- 原生Apple Silicon桌面应用，内置GUI、视频播放与时序探测；应用内安装独立Python/PyTorch/DeepLabCut环境，不要求用户配置开发环境。
- 单摆实验创建，约20帧推荐与逐帧四点标注，联合训练/推理、显式候选采用、困难帧小批重标和重训循环；进度/取消/诊断入口。
- tip+fixed pivot角度、可配置SG、角速度/相图/reference energy、M0/M1拟合与残差/参数诊断、可行域与科学结果导出。
- 已修复安装版DLC推理完成但host读取HDF5失败的问题：使用已声明/哈希校验CSV；任务日志可追溯。项目空目录创建保护并发新增文件。

## 当前发行限制

Mac cv2视频后端实测带GPL FFmpeg；LGPL重建或GPL组合发行材料待用户裁定。当前测试包不能按旧LGPL清单宣称发行材料通过。

Mac14+，仅arm64。Developer ID签名、公证和有下载隔离标记的安装HR **待完成**；当前ad-hoc测试候选不能宣称普通用户正常双击首发通过。Windows CI通过但 **暂未实机验证**，不作为本次Mac版的真机支持声明。

安装版teacher-import、非开发学生两支pilot、完整安装版科学导出/恢复证据仍待补；已通过训练推理HR不替代这些门禁。固定AI环境下载約415 MB，首次训练可额外下载权重；视频、权重及用户实验不随发行包分发。

数值与数据限制见[安装指南](install-guide.md)；软件使用MIT，第三方各自许可/精确源码和构建入口见[SOURCE-MATERIALS](../packaging/SOURCE-MATERIALS.md)。不以RMSE或相图单独证明阻尼模型。

## 2026-10-07 Mac测试候选补充

用户授权将Mac host及新装runtime OpenCV的GPL FFmpeg替换为同ABI LGPL库，
原包/新包hash与精确来源归档随候选准备。已装AI环境不就地修改，需Repair
创建新环境。本轮为ad-hoc未公证测试包；公证需日后配置Developer ID Application
与Keychain profile。Windows仍暂未实机验证，没有公开tag/Release。
