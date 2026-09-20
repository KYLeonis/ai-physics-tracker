# P0.1 Scientific Profiles and Golden Evidence Contract

版本 1.0.0，2026-09-20。本文与 `publication/profiles/*.json` 是 P1–P4 的科学行为契约；不是已经实现的 scientific core。用户本轮授权收敛政策；标为 **new_student_policy** 的项是本轮产品决策，没有冒称历史默认或新科研结论。

## 1. 权威、解析与来源

- [source-map.json](../evidence/source-map.json)：稳定 source ID、alias-relative 路径、SHA-256、ZIP member、SQLite 精确表/selection、method → profile → golden。inventory A01–A16 提供上下文，source-map 固定本次字节。第三方源码固定 SciPy tag。
- [legacy-publication-v1](../profiles/legacy-publication-v1.json)：正式 effective-release M0/M1 复现。
- [student-default-v1](../profiles/student-default-v1.json)：新学生视频默认。只继承 `inherit_sections` 所列 legacy 节；这些节的同名字段由 student 覆盖，未覆盖字段保留。其余节完整替换；显式指向 legacy 的算法公式依赖仍须解析。禁止隐式继承任意新字段、按字典顺序猜优先级或把 JSON 中公式字符串 `eval`。
- [diagnostics-v1](../profiles/diagnostics-v1.json)：每项诊断独立算法。student 的 gap、availability、tail、envelope-failure 政策覆盖历史诊断的相关字段，其他公式继承。
- 每节 `origin/sources` 是 provenance；混合节的 `implicit_fields` 明确来自指定 SciPy 版本，而非历史显式调用。student 继承数字表示本轮选择复用，有科学来源，不表示已证明适合所有实验。P0.2 应保存最终展开后的**值及逐字段来源**，不能只保存一个 profile 名称。
- JSON 是声明性配置契约，不是新配置框架/运行器。后续用普通 Qt-free 类型和显式解析实现；运行时不得依赖用户原科研目录、读取 Python 脚本或解释公式字符串。未知 profile/version/字段不得静默降级；Advanced 更改形成 resolved custom config 和新摘要，不能改写 frozen profile。

正式 fitting.py 来自 ZIP，其哈希等于正式 run manifest；当前新增 warm_start_only 的脚本不取代它。其他正式源文件逐项哈希一致。诊断源码标记为 inspected（不假称全部拥有正式 fit run 的哈希背书）。SciPy 隐式默认由 [v1.17.1 least_squares](https://raw.githubusercontent.com/scipy/scipy/v1.17.1/scipy/optimize/_lsq/least_squares.py)、[Runge–Kutta](https://raw.githubusercontent.com/scipy/scipy/v1.17.1/scipy/integrate/_ivp/rk.py)、[solve_ivp](https://raw.githubusercontent.com/scipy/scipy/v1.17.1/scipy/integrate/_ivp/ivp.py) 源码恢复；URL 与字节哈希已固定。历史仅报告主要依赖版本，没有完整锁文件，不能承诺 bitwise refit。

## 2. 角度、时间、单位与缺失

图像 x 向右/y 向下；v 是 calibrated true vertical 的 top→bottom 单位向量，d=tip−calibrated fixed pivot；θ=atan2(vy·dx−vx·dy,vx·dx+vy·dy)。正竖直图像中向右摆为正，竖直向下为零。tracked pivot 仅 QC，body_top−body_bottom 定义 φ。legacy θ 不 unwrap，φ unwrap；student 的跨 ±π 跳变切断导数段，不当成完整旋转实验支持。

内部 θ rad、ω rad/s、α₁* s⁻¹、α₂* rad⁻¹、q=ωobs² s⁻²，长度 m、像素 px、时间 s；角度的 rad 在能量代理中按无量纲角处理，e* 报 s⁻²、功率 s⁻³，不能标 J/W。归档 theta/RMSE 的 `_deg` 列只在读取边界乘 π/180，不能把 degree residual 传入 rad loss。profile 的 `f_scale_rad` 已数值展开为 π/360。

时间只要求相邻dt>0（严格递增），不要求timestamp>0；release-relative t=0及pre-release负时间均合法。所有 frame 是源视频 0-based；absolute timestamp 与 release-relative time 分开保存。student `t=Timeline(frame)−Timeline(release)`；legacy 用 (frame−release)/fps。源帧即使被 mask 排除也不删除时间位置。IC 在 t=0，未必等于首个观测；postrelease 首个有效点若 t>0，仍从 0 积分。legacy TOML 已 effective=LED−1，绝不再减一次。

raw point/likelihood 保留；分析 mask、权重、逐项 reason 独立。JSON 缺失用 null+reason；数值数组允许 NaN 作为缺失载体，但 NaN 不是零角、零权重或已通过 QC。bool 必须实际 bool，不能把 CSV 字符串 `False` 转成 truthy。禁止在缺测处补轨迹作为观测、重新排列/压缩时间、跨 gap 求导或构造周期。

## 3. 已收敛的新学生政策

| 内容 | Legacy reproduction | Student default v1（新增政策） |
| --- | --- | --- |
| 四点/QC | archived geometry mask；finite 不检查 tracked pivot；无0.60 cut | 四个 adopted 点坐标完整；AI 各点 likelihood 有限且[0,1]；manual 可以 null。radius≤10%、body separation≤20%；正几何；人工排除取交集。pivot displacement 只报告，无未经证据支持的硬阈值 |
| body reference | whole-video nanmedian | whole-video、非显式排除、完整四点帧中正有限 body separation 的 median；保存数值与参与帧 digest；无参考则 unavailable |
| 人工权重 | 没有历史定义 | adopted manual tip 的分析 weight=1，confidence 仍 null；AI tip weight=clip(p,.05,1)，残差乘 sqrt(weight)。人工点不绕过 geometry gates；仅当前adopted source为AI的点缺likelihood才排除。当前adopted manual点忽略superseded AI likelihood（包括缺失值），不得因此排除 |
| release/IC | TOML 5 pre-effective 帧 circular median，ω₀=0 | 手选 release 无 offset；恰好前5连续有效帧+用户确认静止释放，才使用 circular median / ω₀=0。缺帧、非静止或未确认：needs_explicit_IC；Advanced 提供 t=0 的有限 θ₀/ω₀，并固定于两模型。没有自动运动阈值，没有悄悄取首观测/补零，没有同时拟合 IC |
| SG | 9/3 direct derivative；缩窗、<5 gradient；整数组 | 同9/3，但每连续QC-valid均匀段≥9帧，否则导数 unavailable；dt偏差≤1e−6×median_dt才视为均匀；不先平滑；边缘4帧带 edge flag |
| 拟合资格 | ≥max(50,floor(.5N)) | ≥max(50,ceil(.5N_interval))，有效时域跨度≥3Tref，Tref=2π√(L/g)。只是计算门槛，不证明信息充分；粗时间分辨率提示、收敛、界限、残差仍必查 |
| gap与seeds | seed 在 valid 子序列上探峰，有历史跨缺测风险 | seed 用最长连续均匀有效段，tie取最早；仅seed计算局部平移时间，q前35s；短段用历史fallback；正式残差时间不变。ODE跨gap连续积分，排除点不参与残差，不重启初态 |
| tail | strict t>70s，60/80s敏感性，≥10周期 | 默认选定分析时域最后1/3（strict > 边界）；可明确改start；≥10有效完整周期，否则 unavailable，不自动扩大窗口。不声称低振幅/小角；展示实际幅度 |
| 周期/相位匹配 | 相邻帧过零后crossings[i+2]；历史不查整周期跨gap | 同方向两个过零，中间恰好一个反方向过零，并在同连续段；相位比较在相同源时间段按方向和序号匹配，数量/方向序列不同则标 unmatched、不输出末端drift。不把漏检累积为相位误差 |
| halfcycle/EDP | ordinal extrema配对；EDP skip短数据有历史例外、包络失败可能p0 fallback | 选定区间有中断则该诊断 unavailable；不跨段ordinal拼接。EDP明确skip5，之后至少8extrema；包络失败 unavailable，不能冒称fit成功 |

student late-equilibrium只取选定区间末5s内QC-valid有限θ；无样本则unavailable，不对含NaN数组取median。预测非有限直接fit failure，禁止缩小评价mask掩盖失败。

IC五帧的valid指完整视频上的student base QC（四点source-valid、正几何、radius/body gates及非人工排除），在postrelease/fit interval截取之前计算。帧ID恰为r−5..r−1，时间严格递增；不能用postrelease mask检验这些帧。`N_interval=end_frame−release_frame+1`包含全部源帧（含缺点及QC排除）；valid time span为该区间base-QC有效帧中max(t)−min(t)，包含内部gap，不代表连续覆盖。

新学生阈值是保守首版 UX/可计算性政策，不是从24条视频推导的普适定律。后续教学验证可版本化调整；本轮没有未决数值要实现者猜。rest确认的GUI方式、请求/结果持久化字段布局属于P0.2/P1。

## 4. 拟合与比较的精确定义

M0/M1 是完整 sinθ 的 ODE。fit 配置、seeds、bounds、sampling、weights、积分与优化参数见 legacy JSON；student仅覆盖列明政策。g=9.80665；q bounds=[.20g/L,1.60g/L]；a₁/a₂ bounds=[0,.5]，L必须是明确的物理有效长度，不能把像素tip半径误称COM长度。

抽样最多500：在有效帧索引序列上 linspace→rint（ties-to-even）→unique；保留实际源帧及时间。不是时间压缩或严格时间均匀。M0三确定性起点；M1三起点加M0 warm（a₂=1e−8）。legacy接受有限非收敛M0 warm；student只接受收敛M0 warm。起点估计完整公式已固定，不使用随机seed。历史未保存每次start/result，未来必须保存实际resolved starts及逐start状态；不得把现在计算出的seed假称历史日志。

DOP853 fit rtol=2e−7/atol=2e−9，从0到最后所需时间，max_step=∞、first_step=null、vectorized=false、dense_output=false、events=null。least_squares：trf、2-point、ftol/xtol/gtol=1e−8、soft_l1、f_scale=0.5°转rad、x_scale=jac、max_nfev=180，dense Jacobian默认tr_solver解析为exact。保留diff_step=null的库选择语义并记录库版本，不把它伪装成固定绝对步长。候选以finite x/cost按最小cost选；即使某次不收敛也不隐藏，最终status单独报告。积分失败的历史惩罚向量为1000；student必须保留失败标志，最终forward失败不得被该惩罚产生的“收敛”掩盖。

objective r_i=√w_i·(θpred−θobs)，cost=Σ f²(√(1+(r_i/f)²)−1)。RMSE用**全部共同有效帧、无权**，不只500点；weighted exploratory RMSE=√mean(w·residual²)，非除Σw。比较必须同input/IC/时间/mask/weights/sampling/loss；否则标 not_comparable。百分改善=100(RMSE_M0−RMSE_M1)/RMSE_M0，零分母 unavailable；非收敛结果不排名。较低RMSE不能自动证明二次阻尼。

## 5. 每个诊断保持自己的算法

`information-extrema-v1` 的 argrelextrema order=max(8,int(fps/10)) 不插入初态，P011=213；不是fit seed、period或EDP的探峰器。

`phase-halfcycle-v1` 使用尾部median居中、abs peaks、0.30T distance、0.08°/1%A₀ prominence、0.4°/1.5%A₀ cutoff，初态插入、主skip2。相空间距离的频率尺度是 √(g/L)，半周期幅度能量代理也是g/L；与e*(q)分开。速度分层为观测有效absω的线性1/3、2/3 quantiles，high≥后者。half-cycle分层另用每个配对半周期中的最大absω再取quantiles（low判断优先）；contraction为有符号E_i−E_i+1，不能改成EDP的绝对损耗。SG相位诊断delta取median_dt，普通legacy derivative取1/fps，各自记录。

`tail-period-legacy-v1` 以尾段θ mean居中、逐周期 q_i=(2π/T_i)² 后取**算术均值**；不得改成均值周期再平方。视频内周期不是独立release。主正式结果使用70s，不沿用旧0.38%报告。

`energy-envelope-v1` 区分raw turning energy、5-step平均损耗、skip5平滑包络损耗；状态积分2e−9/2e−11，比fit更严；CubicSpline state ω、单半周期500点Simpson、5-step700点再除5；R²以对应observed损耗为分母且至少3pair。指数式为a₀exp(−γt)，offset式为(a₀−a∞)exp(−γt)+a∞，t从首保留peak归零。bounded curve_fit隐式trf/linear loss等与CubicSpline not-a-knot也已写入profile；其库默认来源为[versioned curve_fit](https://raw.githubusercontent.com/scipy/scipy/v1.17.1/scipy/optimize/_minpack_py.py)。不是又一次M1动力学拟合。

`identifiability-valley-v1` 的 mean robust objective=2*optimizer_cost/N，单位rad²；ratio才无量纲。固定starred damping，只扫描q并插值到(raw αa,ω₀²)平面，不叫profile likelihood。objective grid与完整A/B raw forward overlap是不同证据；legacy objective/energy从正式fit表的θ₀ deg转回rad，保留这一诊断特定round-trip；student直接用resolved IC。一个是fit精度条件曲面，一个是更严格容差独立raw RHS forward。参考raw不是被辨识的真实参数。

## 6. Qt-free输入/输出边界与 golden 使用

P0.2应定义不可变请求：profile ID/version/hash及展开值、input digest、源frame/t_abs/t_relative、θrad、mask/reasons、relative weights及manual/AI source、固定IC及来源、L/g、数值bounds/seeds、sampling frame IDs、solver/optimiser resolved设置。请求必须先验证时间严格递增、源帧唯一有序、数组长度一致、L/g及几何reference正有限、IC有限、bounds上下有序、solver tolerances/scale正有限、采样上限正整数；失败返回结构化原因，不排序修复、不吞异常、不用默认值补缺。科学函数只接收数值/枚举/普通数据；不接触Qt、视频控件、SQLite连接或文件路径。外层adapter负责读写/单位转换，worker负责取消/进度；Normal/Advanced构造同形请求。结果必须带status、所有start、参数单位、预测/残差、metrics、warnings、provenance及comparability digest。P0.1不实现这些领域类。

[Golden README](../evidence/README.md)规定分级证据、输入、字段、容差、禁止来源与后续synthetic cases。[verify_publication_evidence.py](../../scripts/verify_publication_evidence.py)只读验证本地冻结证据、算术关系、源哈希与metadata；不执行外部科研脚本。Frozen expected不从未来core输出重新生成。

结构交互后续纯函数必须验证 s=1+αa>0；λ>0，变换(λs−1,λα₁,λα₂,λω₀²)保持三个starred量。λ范围还要服从声明的raw物理bounds，非法输入显式失败。再用各自raw RHS两次积分比较轨迹，不能拷贝同一数组。之后才实现slider。synthetic验收覆盖identity、composition、invariance和domain；参见golden contract，不属于本轮GUI或P4实现。

## 7. 分歧关闭与剩余证据边界

D01/D02/D05/D06/U04已由命名profile及本轮new_student_policy收敛；不改论文、不改历史结果。D03通过正式来源allowlist+旧表denylist隔离；D04使用匹配正式hash的ZIP版本。U03已恢复隐式设置，仍无完整环境锁/跨平台数值重跑认证；该限制不妨碍P0.2数据契约。

angular acceleration α(t)没有论文验证的默认，本轮不设置profile；不是P1–P4必交付default，若以后需要应另立显式新政策。

未解决但不阻塞P0.2：原始四点逐帧和pre-release重建未纳入offline golden；历史逐start优化日志不可恢复；完整依赖lock缺失；cross-platform tolerances尚需P2–P4首次实现时实测；teacher model/原始视频实体按用户要求不继续追查。这些都不能靠把未确认值塞入historical default解决。未来实现若偏离frozen expected，先诊断版本/输入/算法，不自动更新golden或放宽门槛。
