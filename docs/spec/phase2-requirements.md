# Phase 2 需求与验收标准（Video Analysis MVP）

- 日期：2026-08-29 · 状态：**Draft / In Progress**
- 上游：`docs/roadmap.md` Phase 2、ADR-0005、Phase 1 data model/project format
- 目标：第一版可使用桌面应用，完成单视频人工测量闭环

## 1. 用户闭环

```text
启动应用 → 新建/打开项目 → 选择或 relink 视频
→ 显示视频 → 播放/暂停/逐帧/跳转/时间轴
→ 缩放/平移 → 创建 Track → 点击像素位置形成 manual TrackPoint
→ 保存 → 关闭 → 重开后恢复项目与标记
```

## 2. Phase 2 功能要求

### R1 桌面入口与项目会话

`python -m ai_physics_tracker` 启动 Qt Widgets 主窗口。应用层持有当前项目根、
`Project` 快照、当前视频/帧和 dirty 状态；Widget 不直接修改 frozen Project。

### R2 视频读取与时序边界

视频 reader 负责打开/关闭、元数据、0-based 随机读帧和 RGB 输出。OpenCV 的
`VideoCapture` 只出现在 infrastructure。无法可靠确认 CFR 时标记 timing unknown，
不得静默登记为可分析项目；VFR suspected 明确拒绝并提示转码。

### R3 导航与播放

帧号/时间换算只经 Phase 1 `Timeline` 函数。逐帧为整数步进；播放/暂停不阻塞 GUI；
拖动时间轴区分 scrub preview 与 commit decode，过期解码请求可丢弃。

### R4 视频视图

保持宽高比显示；支持缩放/平移。screen→pixel 逆映射发生在 GUI 边界，落点前钳位
并验证图像范围。

### R5 手工标记

用户创建/选择 Track 后，在当前帧点击写入 source=manual、confidence=null 的
TrackPoint；使用 `frame_to_time` 冻结时间，调用 TrackStore manual last-wins 语义，
再生成新的 Project 快照。

### R6 保存、恢复与 relink

保存必须接收 Repository 返回的新 Project（含 modified_at）。关闭/切换项目时处理
未保存修改；外部视频缺失进入 relink，不崩溃、不改观测。

## 3. Phase 2 验收标准

| # | 验收标准 | 判定方式 | 状态 |
| --- | --- | --- | --- |
| AC-1 | 常见 CFR MP4/H.264 可打开、播放、暂停、逐帧和跳转 | macOS + Windows 真机手动验收；帧/time label 同步 | [ ] |
| AC-2 | 时间轴与工作区遵守 0-based/绝对时间契约 | controller 单元测试 + GUI 手动验收 | [ ] |
| AC-3 | 视频视图可缩放/平移且 screen→pixel 映射正确 | 解析几何测试 + GUI 手动验收 | [ ] |
| AC-4 | 任意帧可添加/替换 manual TrackPoint | GUI 集成测试 + 手动验收 | [ ] |
| AC-5 | 保存、关闭、重开后 Video/Timeline/Track/TrackPoint 完整恢复 | 临时项目集成测试 + 手动验收 | [ ] |
| AC-6 | 解码/播放不把 cv2 或 Qt 泄漏进 domain，关闭后释放视频句柄 | import 边界检查 + 文件替换/关闭测试 | [ ] |
| AC-7 | 本地与 GitHub Actions macOS/Windows 测试全绿 | CI | [ ] |

## 4. Subphase 划分

### 2.1 Desktop Video Foundation（已完成）

桌面入口、同步 VideoReader、首帧显示、上一/下一/跳转。暂不连续播放、缩放、标记、
项目保存 UI。

### 2.2 Playback & Viewport（已完成）

播放/暂停、后台解码、latest-request coalescing、scrub/commit、缩放和平移。

### 2.3 Manual Annotation（已完成）

Track 选择/创建、screen→pixel、manual TrackPoint、overlay、Project 快照同步。

### 2.4 Project Workflow & Phase Close（当前：Plan）

新建/打开/保存/另存/relink/dirty 提示，MP4/H.264 Windows 真机验收，Phase 2 收尾。

计划草案见 [Phase 2.4 mini-plan](../status/phase-2.4-plan.md)；未获确认前不开始实现。

## 5. Phase 2.1 Acceptance Criteria

- [ ] `python -m ai_physics_tracker` 启动主窗口。
- [ ] 可打开可读 CFR 视频并显示第 0 帧，RGB 颜色与宽高比正确。
- [ ] 上一/下一/跳转按 0-based 帧号钳位，显示绝对 `time_s`。
- [ ] reader 切换/关闭释放句柄；无效或损坏文件返回明确错误。
- [ ] application/domain 无 Qt import，GUI 无 cv2 import。
- [ ] 运行时合成视频的 reader/session/Qt offscreen 测试与 Phase 1 回归全部通过。

## 6. 明确不做（Phase 2）

AI 训练/推理、自动跟踪、标定 UI、运动学计算、图表、科学导出、模型库和安装包。
