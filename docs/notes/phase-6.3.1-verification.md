# P6.3.1 实现验证记录（自动Gate通过，HR待用户）

契约 / 实现前样本：[ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)。Issue #31；新HR已发起，待用户反馈。

## 数值准备

- 冻结的线性 / 二次 / 阻尼和无阻尼振荡、改名 / 换序、seed631噪声、1e-6和1e6尺度、信息不足回退、Fixed / 边界采用规则：18项初值测试通过；含原拟合模块27项通过。
- 小尺度测试发现原求解器的绝对gtol可过早停止。用源最大绝对值（零信号用1）统一缩放所有残差，仍是原单次、等权、有界求解；输出恢复原单位，并在摘要记录`residual_scale`。完整复审另发现参数坐标未缩放可使巨大/微小参数假收敛，因此按非零初值绝对值（零初值用预算内模型响应探针，无效则回退1）缩放自由参数坐标和边界，并记录`parameter_scales`。原单位输出、等权目标和单次求解保持；不是换损失函数、自动多起点或参数不确定度计算。
- 原表达式/拟合/准备契约已通过核心独立复审及最终全量；不把有限结构测试当作任意信号均能拟合成功。

## P011只读验证

2026-10-16读取原冻结`benchmark-project`、`benchmark-protocol.json`，项目SHA256仍为`92c549a2b53e35c212cbb6e5cce8869a2215fbb073d6d40af65febfbde117ebb`。仅在独立内存Session沿用户已授权的该片段Near-CFR报告确认时序；不apply、不保存、不改正在试用的`analysis-result-project`。

原协议区间[0,214]、215个实际样本，用户选择的`c+A*exp(-beta*t)*cos(Omega*t+phi)`，由估算初值进入一次既有求解：

| 源量 | 拟合状态 | RMSE | 用户公式T=2*pi/Omega |
| --- | --- | --- | --- |
| x | success | 0.00666675846 m | 1.04236267707 s |
| y | success | 0.00556987939 m | 0.52125300987 s |
| theta | success | 0.02090237656 rad | 1.04240721177 s |

θ换算与独立人工周期约1.0389815s的相对差约0.33%，仍在原5%阈值内。y信号的拟合频率约为θ的两倍；以上T只是用户参数换算，不自动认定为实验基本周期。原P6.3重复间隔协议和阈值保持不变。

## GUI / 生命周期

过程验证含旧定向25项（公式渲染、入口/只读、缩放、时序门）及独立日志11项；之后完成核心57项、GUI28项独立复审及收尾回归，最终证据见下。本轮HR另由用户亲测。


## R2修复后的真实对照

最终求解坐标缩放后再跑原协议：x T=1.04236267710s、误差减少95.13484396%；y T=0.52125300988s、减少81.82102191%；theta T=1.04240721167s、减少96.61617511%。改善只比较同一实际样本的常数均值RMSE，不是物理正确/置信度分数。原冻结project.json SHA再次核对不变，未apply或保存真实基准。

R1/R2共18项finding及R3数值/来源返工经核心与GUI独立复审通过；最终Gate证据见下。本地独立HR副本与启动器已实际打开视频首帧，Near-CFR仍需本次人工确认；这不是体验验收。


## Windows CI接管与修复（2026-10-16）

- GLM的日志兼容修复3275ca0有效：路径父目录被文件占用时，Windows FileNotFoundError不能当日志缺失；保留统一读取分类。最新旧CI38876986811的21项日志测试均通过；Luna新增复审日志/应用24项通过。
- GLM先后尝试Ignored标签size policy、三层layout invalidate/activate及测试wait，最终86de567 Windows仍为1415≠1292；不能据临时probe通过宣称修复或真实用户不受影响。原“均已修复 / probe已删除”段落撤回。
- Codex本机24pt字体重现同类问题：切回Acquire后实际1670、预期1449。a6da1a3先刷新用途卡再显示dock，最后显式更新central widget的父布局尺寸缓存并激活主布局。原resize断言不改、不加wait；新增大字体往返回归。删除无效标签策略/布局补丁及临时probe。
- 同时修复showAttempts在session清空过渡期的None访问，并补回归。本次定向 **58 passed（21.46s）**；独立GUI收尾复审几何/空session6项通过。

最终代码a6da1a3本机全量 **1199 passed（146.65s）**；[最终CI38890193235](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38890193235) macOS / Windows Python3.11各 **1197 passed / 2 skipped**，均success；两项跳过因CI未安装可选pandas，本机含pandas的1199项全部通过。本轮HR使用独立副本，原main、论文worktree及用户实验未改；HR通过前不集成main。

## 最终自动Gate与停止点

- a6da1a3：本机1199 passed；独立核心/GUI及收尾复审通过，F1–F25均闭环；无新增依赖、无日志/项目格式破坏。
- 文档收尾提交只修改文档，产品与测试树须和a6da1a3相同；不把文档HEAD冒称已运行CI。
- AGENTS、README、roadmap、phase master/mini-plan、current、review索引和协作经验同步；PR #32保留draft、Issue #31保持open。
- [本轮HR](phase-6.3.1-human-review.md) A–E待用户，体验和集成AC不勾选；用户通过后才合并main并关闭Issue，不进入6.4/6.5。Windows/CUDA真机验收未由offscreen CI替代。

## 第二轮HR返工：公式身份与反馈可见性

用户的四次Fit均已实际完成；theta和cos(theta)无t，属于常数模型；二次式相比同样本常数均值误差仅改善0.07945%。日志留痕/求解不是“换公式未生效”，但原UI把含义和记录公式藏在滚动/折叠区域，体验**未通过**。详情与复测见[HR第二轮](phase-6.3.1-human-review.md#第二轮反馈与复测2026-10-16)。

b9a5311：显示曲线实际公式/参数直接位于图上方；Previous saved result更名Last saved result，明确最近Save快照而非上一尝试；图旁展示无t解释、初值保护/估算回退/超范围提示及常数线误差对照；显式操作定位反馈区域，自动预览不滚动。标准QCheckBox替代五个checkable QGroupBox，方框/文字/space实测；提交被拒绝不会再标完成。无数值求解/项目格式/依赖变化。

- 定向47项通过；全量1205 passed（149.38s）。之后仅补初值超范围提示，最终guided定向20项通过（40.54s）。
- 用户项目/日志只读，检查末尾project.json SHA256仍67e727a2e430c9ab5fe4202269422849fe4a508bd9d85d0d0a16e7ca9fb0ae57，日志SHA256仍b4a825c4d801902c16b1be7d890197d333eeed7fca67c5aad91a0b674652b945。
- 最终产品d90bd85，本机全量 **1206 passed（166.80s）**；新增GUI复审Approve with limits，F26–F30闭环；最终guided20、状态3、crossing恢复1项通过。最新macOS / Windows CI通过；Human Review重点复测三项，未合并main。
- 对用户最近保存的600点二次式结果，按记录的参数与相对时间重新纯计算核对：预测逐点与已存values一致（rtol/atol=1e-12）；RMSE=0.11956111771472985 m，常数基线=0.11965618951161017 m，改善=0.07945414045722465%。模型峰峰值约0.01605 m，实测约0.39733 m，解释了视觉上几乎不变；不重新Fit、不apply、不保存用户工程。
- 相同600个已存样本的只读数学对照：内置Cosine经初值估算后单次Fit，RMSE=0.02467825026546338 m、相对常数误差减少79.375701%；Damped cosine RMSE=0.019109132415307636 m、减少84.029967%。只用于确认含t公式可产生不同模型/误差；不是用户点击记录，不写attempt日志、不保存/激活，不将数学效果当作物理模型正确。

最终产品d90bd85的[CI38895710081](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38895710081)与PR CI38895717058均success：macOS / Windows Python3.11各 **1204 passed / 2 skipped**（可选pandas）；本机含pandas全量1206项通过。后续仅文档同步，产品/测试树与此SHA保持一致；R5自动Gate通过，等待用户重点复测，不宣称HR通过。

## 第三轮HR返工：完整配方回看与底部尝试响应

产品`97d7238`：历史选择同步记录的公式、初值 / 约束、源 / 平滑 / 区间及结果状态；表单只读，原草稿保留。Return恢复，Use才复用设置。底部activated选择同样响应，成功记录仅在原源ID / 指纹 / 单位 / 样本数及当前prepare守卫通过时后台评估已记录参数，不重跑Fit或激活结果；失败 / 缺源清旧图。交付核对Project对象、代际、视频、时序授权 / 近似说明；Save busy等待，返回 / 换选择 / 换页后拒绝迟到值。

- 修复前两批全量分别1226 / 1228通过；独立R6发现全Fixed、离开Analysis、采用crossing设置后旧事件线三个边界，修复后新应用 / GUI26项通过（15.87s）。Reviewer独立26项通过（21.76s），`97d7238` **Approve**，F31–F35 Closed。最终同SHA全量和双平台CI回执补在下方。
- 全Fixed预测与原求解结果存在约1 ULP差异（4与4.000000000000001），评估使用记录的表达式 / 参数，测试采用显式rel/abs=1e-12；不以逐位相等错误拒绝合法结果。
- 本轮再次只读检查用户副本：project.json SHA仍`67e727a2e430c9ab5fe4202269422849fe4a508bd9d85d0d0a16e7ca9fb0ae57`，原冻结benchmark SHA仍`92c549a2b53e35c212cbb6e5cce8869a2215fbb073d6d40af65febfbde117ebb`。当前attempt日志已有6次（用户新增`exp(theta*t)`及`A*exp(-gamma*t)*cos(omega*t + phi) + y0`），不能沿用第二轮4次时的日志SHA宣称文件完全没变。新增两次均600样本 / completed；RMSE分别0.12367583594m、0.01910913242m，后者相对同源常数基线改善约84.03%。磁盘项目仍为二次式；未把日志中的新结果写入 / 激活或保存，已提示用户重启前保存当前GUI。
- 原main仍985fd7c、论文线154f262，两个工作树均clean；没有进入6.4 / 6.5。[第三轮HR](phase-6.3.1-human-review.md#第三轮反馈与复测2026-10-16)仍须用户亲测，不把自动Gate当HR通过。

最终`97d7238`本机全量 **1232 passed（176.50s）**；[push CI38901656875](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38901656875)与[PR CI38901662270](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38901662270)均success，macOS / Windows Python3.11各 **1230 passed / 2 skipped**（可选pandas），测试及安装 / FFprobe / 清理步骤全部完成。后续仅文档同步，产品 / 测试树与该SHA相同；不将文档HEAD当作另跑过CI的产品。
