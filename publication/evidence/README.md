# Frozen scientific regression evidence — P0.1

本目录是小型软件回归资产，不含视频、DLC标签图像、模型或数据库副本。原件只读；本地副本总计约1.1MB。`source-map.json`记录输入来源、SHA、表selection、论文method与profile关联，以及全部golden的有序fields/type/unit/nullability/provenance/comparison。CSV headers按manifest精确匹配；单位以显式unit字段为准（校验器额外防护degree/time后缀），不是凭读者猜列名。inputs24嵌套标定字段和TOML路径也列明。`golden/`文件是归档输出/输入元数据的冻结拷贝或确定性提取，**不是本轮重新拟合的结果**。

## Evidence tiers

| Tier / future gate | 输入 → 预期输出 / 比较字段 | 单位及比较 |
| --- | --- | --- |
| E0 identity（本轮已检查） | source bytes、24 IC metadata、48正式fit、P011/P014完整effective轨迹、diagnostic source | SHA严格相等；ID/frame/count/bool/profile/key严格相等；时间(frame−release)/fps；归档prediction−observation=residual；残差RMSE与fit表对应 |
| E1 deterministic P2 | 两完整θ轨迹+fps+legacy SG profile → `omega_savgol9_rad_s`；P011→信息图213extrema；tail70s→P011逐周期及24视频summary；energy inputs+M1参数+state→skip5 envelope/EDP | SG rad/s atol1e−8 rtol1e−8；frame/peak/count严格；crossing/period s atol1e−8 rtol1e−8；q s⁻² atol1e−7 rtol1e−7；energy s⁻²及R² atol1e−6 rtol1e−5 |
| E2 fixed-parameter forward P3 | 完整θ输入中的时间、`inputs24` θ₀/ω₀、48表参数+fit DOP853 → 两模型prediction列 | 角度rad max absolute≤1e−5；此门槛是拟定软件验收值，尚未跨平台校准；full RMSE deg绝对差≤1e−4 |
| E3 refit P3 | 相同时间/θ/mask/likelihood+IC/L+legacy resolved profile → 正式M0/M1参数、optimizer_cost、full RMSE、status、comparison | q: atol1e−4 rtol1e−5；a₁/a₂: atol1e−5 rtol1e−3；RMSE deg atol1e−3 rtol1e−3；cost atol1e−7 rtol1e−3。must pass converged status/同mask与samples；排名之外还要pass E2。nfev、Jac condition不要求bitwise，但报告差异 |
| E4 identifiability P4 | frozen P011 θ+IC+fit+222 q-curve → objective curve/101×91 surface；完整raw A/B参数+时间 → overlap；另有analytic cases | mean objective rad² atol1e−9 rtol1e−4；ratio/log10 atol1e−5 rtol1e−4；raw overlap max rad≤1e−7；exact lump invariance浮点 atol1e−12 rtol1e−12 |

`abs(actual−expected) <= atol + rtol*abs(expected)`用于注明atol/rtol的字段；max absolute项按指定最大差。所有容差是**新 regression acceptance policy**，并非历史误差条、论文置信区间或本轮实测跨平台性能。版本差异超限必须解释及独立审查，不能自动放宽或拿新输出覆盖expected。

P011/P014两case可离线完整从processed θ开始复现，不需要原视频/原网络。24个case的完整输入轨迹路径和哈希均已固定于source-map；其余22条需显式给PROV根从read-only原件读取后验hash，缺失时标`not_run`，不得用两case冒充48 fits全覆盖。P3收尾仍需24×2正式fit regression；本轮只冻结预期。

`inputs24.json`的IC/calibration来自逐视频effective TOML，并已与正式表calibration_sha256对应。其θ₀是TOML已舍入的**实际输入rad数值**，不能由fit输出deg反算再作为输入。时间由归档fps重建，P011 frame94、3250 rows；P014与各自正式记录对应。processed trajectories含mask，仅能验证使用mask，不能验证原四点→mask；raw reconstruction/circular median应使用synthetic cases，不声称归档IC已重新算过。

## Diagnostic exact fields

- SG：`omega_savgol9_rad_s`；info图 summary只是跨视频汇总，不单独证明各video算法正确。`P011-information-extrema.csv`冻结213个已归档flag选中的源frame/time、maximum/minimum、theta和omega，按有序frame及type严格比较，而非仅比count。来源fig03原始measured-phase CSV的is_detected_extremum（hash匹配provenance），frame按完整trajectory逐行/time join；type由归档相邻theta大小确定，本轮不重新探峰。external verifier核对全部flag的time序列，offline核对source join与type。
- tail：P011逐周期按`period_index_0based`匹配（JSON存储序不作为数值时间顺序）；`start/end_crossing_time_s`、`period_s`、`omega2_tail_period_s_inv2`；24表按video_id比较`period_count/zero_crossing_count/tail_equilibrium_mean_deg/omega2_tail_mean_s_inv2/tail_vs_m1_abs_deviation_pct`。
- energy：`fig06_energy_p011_envelope`按video_id/series及原始行序比较Ebar、observed/model损耗和R²；24表按video_id/model/skip_initial_extrema=5/n_step=5比较peak_count/half_period_count、三种R²、envelope_model/gamma。raw/envelope不可互换。
- objective：按`omega2_observed_s_inv2`对应222曲线点；按(alpha_a,omega0_sq_s_inv2)匹配surface的q/ratio/log10；raw sets按set匹配四raw和三个starred；overlap按time_s匹配θ_A/θ_B（归档deg→rad）。不把归档插值surface当每格直接ODE计算。
- length/fig03 summary是附加归档证据；没有将全部展示列都提升为P2必实现功能。

## Source exclusion

正式effective-release golden的入口只允许manifest指定的sealed CSV.gz与`effective_release_formal_inversion_results`（48行，须和sealed fit CSV对应）。**禁止**旧`residual_trajectories`、144行`damping_video_model_results`、无calibration hash对应的`toml_parameters`、旧`pendulum_inversion.py`的raw/LM/Fisher路径、M2旧release表、旧0.38% tail报告。表名相似、模型相同或RMSE接近都不能绕过版本校验。校验失败报错，不自动挑“最近的”文件。

## Future synthetic evidence（contract，未声称数值实现通过）

P2：向下/向右/向左已知角度与旋转竖直；零向量非法；rad/deg往返；release absolute/relative；手工confidence=null+weight1，即便superseded AI likelihood缺失仍保留；当前AI source缺likelihood则排除；缺pivot但有tip可preview不能fit；严格QC边界；source gaps不压时间；SG polynomial解析导数（9点及边界）、8帧不可用、非均匀时间不可用；周期方向/缺过零/跨gap禁止；energy无阻尼常量及有阻尼耗散；IC前5帧不足/非静止需显式值。

P3：无噪声M0/M1参数恢复、linear limit a₂=0、fixed IC与非零ω₀、非均匀sample时刻、有限最小cost但不收敛、积分失败不能success、50点/ceil门槛/3Tspan、gaps持续积分、manual权重与mask分离、不同request不能comparison、RMSE分母0。

P4 analytic fixture：raw=(0.2,0.024,0.036,48)，lumped=(0.02,0.03,40)；λ=2→raw=(1.4,0.048,0.072,96)。identity/composition与一组不同IC/timeline合成forward重叠；λ≤0或s≤0拒绝，启用αa≥0时λ<1/1.2拒绝。objective mean=2cost/N；直接若干q节点vs插值surface；明确条件截面而非profile optimisation。

这些是实现前的输入/expected/拒绝条件；实施时测试必须调用真正的core，不用在测试里复制整个算法来假装验证。

## Read-only validation

```sh
python3 scripts/verify_publication_evidence.py
python3 -m unittest discover -s tests/publication -v
python3 scripts/verify_publication_evidence.py --prov-root /path/to/scientific-assets --ejp-root /path/to/EJP_Paper
```

默认离线校验冻结文件，不安装依赖、不运行历史脚本、不写外部资产；带root时额外验对应文件/ZIP内容hash及SQLite选定table rows。public URL默认不请求网络，source bytes已在P0.1恢复时核对；未来有必要时按固定URL/hash核验。本轮检查不能替代后续numerical regression。

Git存储契约：`.gitattributes`对golden禁用text换行转换以保持原件SHA（含CRLF），对profiles强制LF；本轮在core.autocrlf=true临时checkout完成离线验证。这是跨平台字节可移植检查，不冒称Windows科学数值运行。
