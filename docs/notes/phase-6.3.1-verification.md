# P6.3.1 实现验证记录（进行中）

契约 / 实现前样本：[ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)。Issue #31；新HR尚未发起。

## 数值准备

- 冻结的线性 / 二次 / 阻尼和无阻尼振荡、改名 / 换序、seed631噪声、1e-6和1e6尺度、信息不足回退、Fixed / 边界采用规则：18项初值测试通过；含原拟合模块27项通过。
- 小尺度测试发现原求解器的绝对gtol可过早停止。用源最大绝对值（零信号用1）统一缩放所有残差，仍是原单次、等权、有界求解；输出恢复原单位，并在摘要记录`residual_scale`。完整复审另发现参数坐标未缩放可使巨大/微小参数假收敛，因此按非零初值绝对值（零用1）缩放自由参数坐标和边界，并记录`parameter_scales`。原单位输出、等权目标和单次求解保持；不是换损失函数、自动多起点或参数不确定度计算。
- 原表达式/拟合/准备契约回归尚待最终全量和独立复审；不把初值测试当作任意信号均能拟合成功。

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

进行中。已验证旧定向25项（含公式渲染、入口/只读、缩放、时序门）和独立日志11项；最终集成测试、双平台CI、全新复审和本轮HR仍须完成。


## R2修复后的真实对照

最终求解坐标缩放后再跑原协议：x T=1.04236267710s、误差减少95.13484396%；y T=0.52125300988s、减少81.82102191%；theta T=1.04240721167s、减少96.61617511%。改善只比较同一实际样本的常数均值RMSE，不是物理正确/置信度分数。原冻结project.json SHA再次核对不变，未apply或保存真实基准。

R2共18项finding（含R1）按review记录修复；最终完整Gate仍待回执。本地独立HR副本与启动器已实际打开视频首帧，Near-CFR仍需本次人工确认；这不是体验验收。


## Windows CI失败诊断与修复（接续会话，2026-10-16）

原会话额度中断时双平台CI未收口。取回Windows日志定位到两个平台特有失败，均已修复并记录为R2的F19/F20：

1. **日志读故障误分类（F19）**：Windows对“路径组件被普通文件占用”报FileNotFoundError（WinError 2/3），POSIX报NotADirectoryError；`_load_root`/`bind`/`_recover_read`原把FileNotFoundError一律当“日志不存在”，恢复时None基线与真实磁盘文件冲突→永久只读、内存尝试丢失。新增`_read_existing`统一分类（parent存在且非目录=读故障；真缺文件=新日志），并补Windows异常形态的monkeypatch回归。
2. **窗口最小宽度测试仅Windows失败（F20）**：临时探针测试取回Windows真实数据（栈页806/922、header 1129、dock 280、回退字体`Sans Serif` 9pt使`Fit formula / Measure intervals`按钮达384px）后定位真实成因链：44654b3新增的analysis图表页任务卡在访问期间显示3个宽按钮，切回acquire后按钮已隐藏，但测试在两次`setWorkspace`之间不跑事件循环，布局项缓存的最小宽度未失效，header按1129参与窗口最小值（+dock 280≈1415）。真实交互中每次点击都会跑事件循环并投递LayoutRequest，用户不受影响。修复：测试往返后`qtbot.wait(10)`让布局稳定再断言；同时保留换行状态标签水平sizePolicy=Ignored作防御（Windows上换行标签minimumSizeHint即整行文本宽度，真实长工程/视频名文案否则会顶宽窗口最小宽度）。

修复后本机全量 **1197 passed（112.97s）**；macOS CI先转绿（38865523780 macos success），Windows最终CI见下方回执。临时探针`tests/gui/test_windows_layout_probe.py`已移除。
