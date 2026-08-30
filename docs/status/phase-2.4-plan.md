# Subphase Plan — Phase 2.4 Project Workflow & Phase Close

- Issue：[#5](https://github.com/KYLeonis/ai-physics-tracker/issues/5)。
- 分支：`feat/p2.4-project-workflow`。
- 日期 / 状态：2026-08-30 · **In Progress — 用户已确认计划、FFprobe 与 CI 方案**
- 仓库基线：`main` / `a2dc642`；2.3 已合并并记录 Human Review 通过。
- 本地验证：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **124 passed**。
- Luna-max 定点盘点：ProjectSession/Repository 相关测试 **29 passed**；仅审计现有接口，非实现验收。

## Goal

让用户能把当前视频及手工标记保存为实验项目，关闭后完整恢复，移动项目或重连视频时
不丢轨迹；建立未保存修改保护，并完成 Phase 2 的跨平台和真人验收。

## Scope

**做**：

- File 菜单提供 New Project、Open Project、Save、Save As、Close Project 与 Relink
  Video；保留 Open Video 的明确入口，区分“打开媒体”与“打开项目”。
- 补齐 ProjectSession 的首存、加载、另存、绑定根目录和切换流程；复用现有
  ProjectRepository，保持 application 通过端口调用、组合根注入。
- 统一 dirty（未保存内容变更）保护：新建、打开项目、替换当前视频、关闭项目/窗口
  走相同的 Save / Discard / Cancel 流程；保存取消或失败不能继续丢弃会话。
- 重开后恢复原对象 ID、Video/Timeline/Track/TrackPoint、已有 Calibration/DerivedData、
  registry 和未知字段；不因解码器重新 open 而生成第二套项目时间轴。
- 保留多视频清单，只有一个当前活动视频；必要的选择与 Track 过滤不等于多相机同步。
- 使用既有 `ui_state` 的应用专属命名空间保存当前视频/帧和最小视图上下文；未知 UI 键
  原样保留。重开总是暂停、标注模式关闭，防止自动播放或误点。
- 外部视频缺失时仍可打开项目和查看轨迹数据；重连校验身份/元数据，成功后才换 locator。
- 补上 CFR/VFR 时序验证关卡，禁止把 unknown 静默当成 CFR；保留 OpenCV 解码后端。
- 独立 review、双平台 CI、macOS/Windows Human Review、验收和文档同步。

**不做**：

- 不新增 AI、标定 UI、物理计算、图表、导出、自动备份管理器或安装包。
- 不重新设计已经通过 Human Review 的播放/缩放/标注交互。
- 不自动转码、不覆盖原视频、不重新计算已有观测的 `time_s`。
- 不新增 FPS 编辑/重算界面；本 Subphase 只恢复、校验已有 Timeline。
- 不自动清理用户文件，不覆盖已有目标项目，不进行破坏性 schema 迁移。
- 不增加多相机联动、最近项目库或通用任务框架。

## 现状与实现约束

1. `ProjectSession.save()` 已实现，但只服务有根目录的会话；Repository 的 `create()`
   生成空项目、`save_as()` 要求既有源目录。首次保存必须直接保留当前项目的 ID 与标记，
   不能先创建新的空项目替换当前状态。
2. `MainWindow.openVideo()` 当前会先清空呈现状态并创建新 ProjectSession；2.4 改为
   “保护旧会话 → 准备/验证候选项目与视频 → 成功后统一切换”。取消、加载失败、首帧失败
   或超时不得丢掉旧项目、旧标记和未保存状态。
3. `VideoSession.open()` 当前按容器信息创建新 Timeline。加载项目时必须绑定保存的
   `video_id`、`fps_nominal`、`working_zone`，校验媒体信息，不能静默覆盖保存的约定。
4. `register_external_video()` 尚未消费 `VideoStreamInfo.timing_status`，而 reader 恒为
   unknown。这是 ADR-0005 既定限制的实现缺口，不能在 Phase 2 收尾时略过。
5. 既有 Undo/Redo 只保存 Track/Observation 快照，成功 save 清栈。默认保留这条已经
   通过 HR 的语义；失败 save 不清栈、不清 dirty。加载/切换时不把旧撤销记录带入新项目。
   视频登记/relink 不扩展为通用撤销命令；对用户明确 Undo/Redo 的标注范围。
6. 保存记录已呈现帧，不用领先于画面的请求帧号。旧 worker 的迟到回调必须携带与原请求
   绑定的会话标识，不能用回调发生时的可变“当前代际”冒充归属。

## 已确认的行为

- **首次保存**：选择新的目标项目目录；完整保存当前内存 Project。成功后才绑定根目录，
  失败/取消保留原会话。只操作这次明确创建的暂存目标，不触碰已有项目。
- **另存为**：复制项目内资源，外部视频继续只引用；拒绝同目录、源目录的子目录和已有
  目标，避免递归复制和覆盖。复制/保存失败时原项目、原文件和会话绑定不变。
- **加载/恢复**：先校验清单，再解析视频、恢复已保存 Timeline 和已呈现帧；无效 UI 状态
  使用安全默认值，但不能静默修复领域数据。缺视频是 relink 状态，不是清单丢失。
  损坏清单明确拒绝并提示已有 backup，不自动用备份覆盖主文件；IO 回滚失败单独报告。
- **重连**：不生成新 Video ID。已记录 SHA-256 时必须匹配；没有哈希时检查尺寸、帧数
  和容器时序，并明确提示“元数据一致不等于文件身份已证实”。不匹配时不提交替换。
- **dirty**：内容修改驱动标题/保存提示，单纯播放或缩放不触发未保存警告；视图上下文在
  显式保存时一并记录。以保存内容快照为基线，Undo 回到相同内容应恢复 clean；relink
  导致的 locator 变更仍算 dirty。不把“发生过一次写操作”直接当成“仍有未保存内容”。
- **时序**：建议新增 FFprobe 探测端口，以逐帧时间信息验证 CFR；只比较平均 FPS 或少量
  抽样不能证明整个文件为 CFR。探测在后台可取消，错误/超时/缺工具保持 unknown。
  unknown/VFR 可以浏览和恢复已有数据，但禁用新增测量；不自动改写历史点。

## Acceptance Criteria

| # | 可独立验证的判定 | 证据 |
| --- | --- | --- |
| P24-1 | 根目录为空的标注会话首次保存后，project/video/track/point ID 与数据不变 | real Repository 临时目录集成测试 |
| P24-2 | Save/Save As 成功后绑定正确根目录并清 dirty；失败/取消保留绑定、内容和 Undo/Redo | 注入 IO/复制失败，逐字段比较 |
| P24-3 | Save As/目录移动后项目内视频可解析；外部视频不被默认复制；危险目标被拒绝 | 中文路径、不同根目录、同目录/子目录/已有目标测试 |
| P24-4 | New/Open/换视频/Close 的 Save/Discard/Cancel 分支不会静默丢失标记 | Qt offscreen 对话框分支测试，含保存失败后取消 |
| P24-5 | 新会话加载清单后恢复全部持久化对象；播放器沿用保存的 Timeline，未知键保留 | 非默认 fps/working zone、多视频、未知 UI 键 round-trip |
| P24-6 | 缺视频时项目数据仍在；取消/错误重连不改 locator，成功重连不改 raw 点和 ID | 缺失、错误尺寸/帧数/hash、正确重连测试 |
| P24-7 | 切换/退出后旧解码结果不能覆盖新项目；资源明确释放 | 慢 reader、迟到回调、快速切换及 Windows 文件句柄测试 |
| P24-8 | 确认 CFR 才允许新增测量；VFR/unknown/探测不可用不被当成 CFR | 合成固定/变间隔时间戳、真实 CFR fixture、超时/缺工具路径 |
| P24-9 | 本地回归与 macOS/Windows CI 全绿，没有为通过 CI 跳过关键测试 | pytest、compileall、pip check、Actions 日志 |
| P24-10 | 用户亲测项目生命周期及 Windows MP4/H.264 全流程通过，之后逐项核对 Phase 2 AC | Human Review 反馈 + phase2-requirements/roadmap 证据 |

P24-10 未完成前不把 Phase 2 标成 Completed。HEVC 按已有解码矩阵补 Windows 实测，
不把未经承诺的 4K 实时播放变成新验收标准。

## Relevant Context

- `AGENTS.md` §6/§7/§11；`docs/workflow.md` §3/§5.1/§6/§8.1。
- `docs/roadmap.md` Phase 2；`docs/spec/phase2-requirements.md` R1/R2/R6 与 AC-1…AC-7。
- `docs/spec/data-model.md` §3/§5/§7；`docs/spec/project-format.md`；ADR-0003/0004/0005。
- `docs/research/open-source-project-map.md` §3.2/§3.5/§6.7/§7.9；
  `docs/research/raw/kinovea-notes.md` Persistence and undo；
  `docs/research/raw/sleap-notes.md` GUI state and commands / Data model, annotation and persistence。
- `docs/development.md` §1.1：Windows 真机要求与已有视频解码矩阵。
- FFprobe 能力依据：<https://ffmpeg.org/ffprobe.html>（`show_frames` / `show_streams`）。

## Slices

- [x] Slice 1：细化状态/失败契约，确认时序探测与工具交付方案；补 spec，必要时新增 ADR。
- [x] Slice 2：补首存/另存服务和 Repository 端口；验证无根目录会话、危险目标与失败不提交。
- [x] Slice 3：加载/恢复/重连应用流程；绑定持久化 Timeline，隔离旧异步结果，验证数据不丢失。
- [x] Slice 4：File 菜单、标题 dirty、统一未保存提示、视频选择与恢复 UI；保持 Qt 与 IO 分层。
- [x] Slice 5：接入时序探测和 analysis gate；测试 CFR/VFR/unknown、取消和缺工具。
- [ ] Slice 6：端到端回归与 CI，Luna-max 独立 review，Human Review，Issue/Phase 2 收尾。

每个 Slice 自带测试，不等到 Slice 6 才验证；未勾选项不得视为完成。

## Verification

- 本地：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`。
- 本地：`.venv/bin/python -m compileall -q src tests`、`.venv/bin/python -m pip check`、
  `git diff --check`。
- 自动化测试只使用 `tmp_path` 和合成数据；不移动/删除真实实验视频来测试 relink。
- CI 保留 macOS/Windows Python 3.11；若添加 FFprobe/FFmpeg 下载、版本和校验，先获
  用户对 CI 改动的授权。不得只用 mock 宣称实际探测器已通过双平台验证。
- 独立 review 使用 Luna-max，任务限定为当前 diff + spec；架构取舍由主模型负责。

### Human Review（代码与自动化验证完成后再发起，发起后停止）

最短启动：`.venv/bin/python -m ai_physics_tracker`（仓库内）。

1. 打开 CFR 视频并标两帧 → 首次 Save → 关闭/重开项目；轨迹、时间、保存帧恢复，初始暂停。
2. Save As 到新目录 → 只修改副本 → 重开原项目；原项目没有被副本操作改变。
3. 添加标记后尝试 New/Open/Close → Cancel、保存后继续、Discard；取消或保存失败不丢点。
4. 在用户准备的可丢弃副本中测试缺视频/relink → 取消保持数据，正确重连后标记仍锚定原帧。
5. Windows x64 上打开 MP4/H.264 完成播放→标注→保存→重开；补记 HEVC 兼容性结果。

届时只问各条“是否符合预期（是/否）”，不以 computer-use、截图或 offscreen 代替反馈。

## 授权边界

- 本轮默认不改 schema 版本；`ui_state` 内兼容追加应用字段时仍保留未知键。
- 已批准把 FFprobe 作为外部时序探测工具：本机已有 `/opt/homebrew/bin/ffprobe`，但这
  不代表 Windows 环境已有。建议明确工具发现/路径选择；缺工具时浏览可用、新增测量禁用。
- 已批准开发/CI 中 FFprobe 的可复现取得方式；不自动安装全局依赖、不改系统 PATH，
  不提前发布打包产物。若选择不同工具或必须改格式，另停下来讨论。
- CI 修改已获本次确认；git push、媒体删除/覆盖未获授权。
- Issue/工作分支已建立；Human Review 和 CI 尚未完成。

## Result（收尾时填写）

- 完成日期 / 合并 commit：未收尾，尚未合并；最新功能提交 `2a139ce`。
- 本地验证：173 tests passed；compileall/pip check/diff check 通过；固定来源 FFprobe 的
  macOS 下载/摘要/实际执行通过。P24-9 的远端 CI、P24-10 的 Human Review 尚待完成。
- 独立 review：Luna-max，两个持久化 Blocker 已修复并定点复查通过。
- 实现订正：unknown/VFR 保存浏览媒体引用但不授予测量权限；未知 workflow 版本不降级。
- 提交粒度：Slice 2–5 的互相关联应用/GUI 集成合为一次功能提交，测试仍逐步运行；
  FFprobe/生命周期测试由 Luna-max 执行有界子任务，主模型负责架构与最终集成。
- Human Review：已准备五条验收步骤，必须停止等用户亲测；不以自动化 UI 代替。
- 遗留：Windows 真机反馈、远端 CI 与 git push 授权未落实。
