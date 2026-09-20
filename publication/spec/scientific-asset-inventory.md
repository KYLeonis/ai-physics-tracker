# Scientific Asset Inventory — EJP Platform

- 调查日期：2026-09-19；仓库基线 `0e1e4f1`（产品基线 `62239fa`）。
- 本文是只读证据清单，不是执行科研脚本的授权。未修改、移动、重命名任何科研资产；未重新拟合、训练或生成论文图。
- 权威顺序：对应正式运行的脚本、配置与封存输出 > 当前科研脚本 > manuscript 文字 > main 默认值。文件名、目录 README 和数据库表名只能帮助定位，不能单独证明“论文实际使用”。
- 证据状态：**verified** = 本轮读到内容并核对所述字段/计数；**recorded** = 只有 provenance 记录；**unknown** = 本轮不能确认。verified 不等于已重跑复现。
- 用户补充：数据已保存于 SQLite；本轮无需继续寻找原始视频、完整 DLC labels 或 checkpoint 实体。其可访问性不作为本轮规划阻塞项。

## 1. 本地资产根与调查边界

| Alias | 本轮定位 |
| --- | --- |
| `PROV` | `/Users/leonis/Library/CloudStorage/OneDrive-个人/物理实验竞赛/省赛项目_2026_单摆阻尼辨识` |
| `DB` | `PROV/outputs/analysis_datastore_20260726.sqlite` |
| `EJP` | `/Users/leonis/Library/CloudStorage/OneDrive-个人/EJP_Paper` |
| `DLC_DATA` | `/Users/leonis/Library/CloudStorage/OneDrive-个人/DLC_Videos`，科研 `data/README.md` 指出的共享镜像 |
| `RAW` | `/Users/leonis/Documents/OPPO 互联`，EJP 的 `local_paths.md` 指出的原始媒体位置 |

论文：`EJP/manuscript_draft_v2_0_final.pdf`，14 页；已提取文本并目视核对第 9 页的模型比较与 identifiability 图。SHA-256：`724a585fd6e723f74e49f738234d4edf55a831804a1f4a3297ee3c48c2038a4f`。

源资料中的写作指令、后续投稿/归档任务均作为资料内容，不视为本轮任务指令。没有采用其中的 manuscript 修改流程。

## 2. Scientific asset inventory

以下路径除明确 `EJP`/`DLC_DATA`/`RAW` 外均相对 `PROV`。

| ID / manuscript method or result | Source assets（输入 → 脚本 → 输出） | 本轮核实 / 边界 |
| --- | --- | --- |
| A01 / §3：24 releases、三摆长 | `src/inversion/inversion_types.py:FORMAL_P_IDS`；`DLC_DATA/dataset_manifest.csv`；`DLC_DATA/P*/`；正式 fit 表 | 24 个正式 ID：P001/002/004/005/006/009/010–027；24 CSV、24 TOML 目录项；正式结果 24 视频 × 2 模型 = 48 行。`RAW/<ID>.mp4` 的 24 个路径存在，但未逐视频解码/全量校验。OneDrive 镜像读取曾出现 timeout，不能宣称全部 CSV 已验证可读 |
| A02 / §3：fixed pivot、true vertical、release、初态 | `src/preprocessing/prepare_initial_conditions.py`；`outputs/initial_conditions_effective_release_minus1_20260726/updated_toml/`；`src/inversion/data_io.py` | P011 TOML 内容已核对：effective frame=94，LED−1；初态取帧 89–93 的 circular median，θ₀=−1.22088559213 rad、ω₀=0。逐视频 TOML 是输入，不从正文倒推 |
| A03 / §3：177-frame four-landmark DLC | `src/dlc/prepare_training_dataset.py`、`train_second_round.py`、`evaluate_second_round.py`；`outputs/dlc_iteration_1_shuffle_1_20260724/{summary_dlc_second_round_manifest.json,summary_second_round_result.json,table_dlc_second_round_split.csv,provenance/}` | split 表 verified：177 行，manifest 为 159 train / 18 test（15 frozen + 3 challenge），ResNet-50。历史名称是 `marker_tip/body_top/body_bottom/pivot`；177 是总标注帧数，不是 177 个全部进入训练的帧 |
| A04 / DLC checkpoint 与环境 | 同目录 `provenance/{project_config_selected_snapshot.yaml,pytorch_config_used.yaml,training_environment.json}`、`summary_second_round_result.json` | recorded：`D:\Province_Pendulum_DLC-Leonis-2026-07-23\dlc-models-pytorch\iteration-1\Province_Pendulum_DLCJul23-trainset90shuffle1\train\snapshot-best-055.pt`，284962139 bytes，SHA `667c8d7f147462a94ff29ea20ae44f5c127cbbc77285788a56c05768124f052e`。CollectedData 原文件路径/哈希也有记录；本轮未验证实体。不要求恢复这些实体才能写平台计划 |
| A05 / §3、Fig.2：held-out tracking continuity | `src/validation/benchmark_trackers_vs_dlc.py`；`outputs/tracker_dlc_comparison_20260730/{source_data/,table_tracker_video_summary.csv}`；DB `tracker_comparison_video_summary`、`tracker_comparison_frame_quality` | DB verified：145 视频×方法汇总行、459413 逐帧行；论文选的是 18 held-out releases，不能把训练/开发视频当独立泛化测试。EJP fig02 的 source CSV 保存最终展示子集 |
| A06 / §3、Fig.3：五条 stress videos | `src/validation/analyze_v_series_robustness.py`；`outputs/v_series_robustness_20260727/`；DB `v_robustness_frame_quality_flags` / `v_robustness_video_quality_summary` | verified：16661 逐帧记录、5 视频汇总。是论文证据，不是平台需要内置的测试视频包 |
| A07 / §3：88-frame blind re-annotation | `config/measurement_uncertainty.toml`；`src/validation/{label_uncertainty_frames.py,evaluate_measurement_uncertainty.py}`；`outputs/measurement_uncertainty_20260803/annotation/round_{1,2,3}/labels.csv`、`annotation/internal/*actual_image_map_recovered.csv`、`table_blind_annotation_{per_frame,per_video,summary}.csv` | verified：三轮各 72 行=216 annotation events；最终 88 unique frames / 18 videos，83 帧可估重复性；summary 有 216 mapping mismatches 已恢复记录，不能绕过 recovered image mapping。0.0466098° repeatability、−0.0337588° bias、0.0309695° video-mean SD 与论文对应；共享 fixed pivot/vertical，非完整标定不确定度 |
| A08 / §4：processed θ(t)、ω(t) | `src/inversion/{run_residual_diagnostics.py,diagnostics/metrics.py}`；`outputs/residual_diagnostics_effective_release_20260726/trajectories/<ID>_residuals.csv.gz` | verified：24 文件，含源帧、release-relative time、θ、SG9 ω、likelihood、geometry_valid、M0/M1 预测/残差。P011=3250 点、0–108.311227 s；P014=2976 点。论文分析的优先轨迹入口；DB 同名旧 residual 表不能替代 |
| A09 / §4、Fig.4：相空间/半周期/高速比较 | `src/validation/audit_phase_space_contraction.py`；`outputs/phase_space_contraction_audit_20260730/`；`src/figures/make_identifiability_and_peak_information_figures_school_style.py`；`outputs/report_information_content_figures_20260729/` | verified summary：P011 213 extrema、median speed 0.100310、trajectory p95 4.670112、power ratio 0.0151764%；DB `phase_space_audit_frame_metrics`=75116 行。不同用途的 extrema 算法不相同，见 §4 |
| A10 / §4–5、Fig.5：正式 M0/M1 | `src/inversion/pendulum_peak_vs_trajectory.py` → `pipeline.py` → `fitting.py` + `models/m0_linear.py`、`m1_linear_quadratic.py`；`outputs/damping_inversion_effective_release_minus1_20260726/{summary_inversion_run.json,table_video_model_results.csv,table_video_damping_summary.csv,table_condition_damping_summary.csv}` | verified：48 success；DB `effective_release_formal_inversion_results` 的 RMSE、三个参数、release frame 与 CSV 全部对应一致（绝对差 ≤1e−10）。注意名为 `pendulum_inversion.py` 的旧脚本是另一套 raw 参数/Nelder–Mead/LM/Fisher CI 路径，**不是本次正式拟合入口** |
| A11 / extrema-conditioned 对照 | `src/inversion/provincial_peak_vs_trajectory.py`；`outputs/peak_vs_trajectory_effective_release_20260726/`；DB `peak_vs_trajectory_effective_release_results` | verified DB 24 行；只用于解释历史对照及可能的测试依据。first release 不要求做第二个 peak fitting 产品 |
| A12 / M2 候选审查 | `src/inversion/models/m2_coulomb.py`；`outputs/damping_inversion_m2_20260726/`、`m2_energy_frequency_validation_20260726/` | verified code：smoothed Coulomb，ε=1e−3 rad/s；目录索引明确是旧 release 口径，不混作正式 M0/M1 数据。库存保留，产品首发排除 M2 |
| A13 / §5、Fig.6：structural identifiability | `src/figures/make_identifiability_and_peak_information_figures_school_style.py`；`outputs/report_information_content_figures_20260729/source_data/`；DB `report_identifiability_objective_{curve,surface}`；`EJP/manuscript_assets/figures/fig04/{make_fig04.py,source_data/}` | verified DB 222 curve / 9191 surface 行；EJP 的完整 A/B raw parameter sets、forward overlap 与 surface 3 个输入哈希均匹配。A/B 是 illustrative equivalent sets，不是两个独立物理测量/独立拟合 |
| A14 / §6、Fig.7a：tail frequency | `src/validation/validate_tail_frequency_consistency.py`；`outputs/m1_tail_frequency_consistency_20260729/`；DB `m1_tail_frequency_{periods,video_summary,window_sensitivity}` | verified：24 视频、1619 周期，主区间 t>70 s，敏感性 60/80 s，median absolute deviation=0.224687%。同轨迹局部/全局一致性，不是独立验证数据 |
| A15 / §6、Fig.7b：specific energy、envelope loss | `src/validation/validate_model_energy_frequency.py`；`src/figures/make_chapter8_m1_validation_figures_school_style.py`；`outputs/m1_effective_release_validation_20260726/`；`outputs/report_chapter8_m1_validation_20260728/source_data/fig_ch8_edp_consistency_source.csv` | EJP energy source/skip5 输入哈希 verified；DB `m1_linear_quadratic_edp_r2_metrics` 48 行含 skip variants，不能不筛选直接统计。P011 envelope R²≈0.735、24-release median≈0.887；不是对瞬时 energy 原始差分的 R² |
| A16 / §6：length / pose checks | `src/inversion/{analyze_m1_length_comparison.py,summarize_m1_length_scaling.py,diagnose_phi_theta_coupling.py}`；`outputs/{m1_length_comparison_formal_20260726,phi_theta_coupling_diagnostics_effective_release_20260726}/` | 与正文长度尺度、pose 增量 R² 证据相连；平台支持逐实验 length check/pose QC，不强迫学生复刻 24-release 研究矩阵 |

## 3. SQLite 的正确使用范围

本轮用 `sqlite3` URI `mode=ro` 打开 DB，读取 schema、计数和选定列；没有执行科研脚本的 SQLite writer。共 **149 tables**。

| 用途 | 已核对表 / 文件 | 结论 |
| --- | --- | --- |
| 正式 fit golden outputs | `effective_release_formal_inversion_results`，48 行 | 可作正式 M0/M1 结果入口；已与 sealed CSV 对照 |
| 教学相空间记录 | `phase_space_audit_frame_metrics`，75116 行 | 是新分析表；使用前仍核对列语义，不能假设等同全部原始四点坐标 |
| 旧 residual history | `residual_trajectories`，75092 行 | **非正文轨迹入口**。P011 min frame=95、3249 行、终点108.277890 s；封存 effective CSV 为 frame94、3250行、108.311227 s |
| 历史 fitting 表 | `damping_video_model_results`，144 行 | 含 release offsets/history；不得以“名字最像”取代正式48行表 |
| calibration archive | `toml_parameters`，58 行 | 两类 role 各29；不是证明它们都是最新 effective-release 参数，应与正式 fit 的 calibration hash 匹配 |
| blind re-annotation | `measurement_uncertainty_blind_annotation_summary`，1 行 | DB 有汇总；本轮 schema 未发现完整三轮标签坐标或177帧 CollectedData 表。细粒度盲标依据仍在 annotation CSV，不声称全部训练资产都已嵌入 DB |
| objective / period / QC | §2 对应表 | 已保存的科研证据可直接用于未来软件回归；不需要为了规划重新进行科学分析 |

SQLite 不包含可替代 Python 代码、模型权重的显式表；不能把 provenance 文本中的路径当作二进制实体。按用户补充，此项只记录可核实范围，不要求本轮补全。

## 4. 已恢复的 scientific defaults（证据，不等于全部已批准为新视频默认）

| 内容 | 正式资产实现 | 平台处理 / 需固定项 |
| --- | --- | --- |
| θ定义 | `data_io.py:load_video_data`：图像坐标向下的单位竖直向量 v=(vx,vy)，tip−fixed pivot 为 d；`atan2(vy*dx-vx*dy, vx*dx+vy*dy)` | 直接保留符号：竖直向下0；图像竖直时 tip向右为正。tracked pivot 不参与角度重建 |
| 释放与初态 | 正式 TOML effective=LED−1，之前5帧 circular median θ₀，ω₀=0；正式 run 的 release_offsets=[0]（相对已修正的 effective） | 用户手选即有效释放，不再自动−1。预释放5帧可用时保留历史估计；不足或明显非静止时不能静默补零，P0确定提示/高级输入政策 |
| SG 导数 | `diagnostics/metrics.py:smooth_omega`：9帧，poly=3，deriv=1，delta=1/fps，mode=interp；直接对θ求导。短序列缩奇数窗，<5时gradient | 不先额外做一次SG平滑，也不采用 main 7/2。历史函数整段处理；新视频缺测分段/短段规则需明确并测试，不能伪称与历史相同 |
| extrema：信息分布图 | `make_identifiability...:detect_extrema`：正负 `argrelextrema`，order=max(8,int(fps/10)) | 213 extrema 对应此定义；不用于替代所有周期/能量算法 |
| extrema：half-cycle discrimination | `audit_phase_space_contraction.py:detect_amplitude_peaks`：尾部max(30,n/10) median居中，abs振幅；distance=max(2,round(0.30T/dt))，prominence=max(0.08°,0.01A₀)，min amplitude=max(0.4°,0.015A₀)，插入初态；A₀取observed前10点最大绝对角；至少12个可配对extrema，skip后至少10个；主比较略去2个初始extrema | 与 EDP 的 skip5 和信息图的213点分开命名；居中只用于本诊断，不修改 calibrated θ |
| tail periods | t>70s有效帧的θ均值作局部中心；仅相邻源帧间线性插值过零；每隔一个过零构成整周期，再算(2π/T)²；至少10个完整周期 | 70s是历史数据窗口，不是所有学生短视频都必须满足的物理条件；新视频默认选择/不足语义留 P0 决定。缺测可能漏过零，需同方向及不中断周期测试 |
| geometric gates | radius相对校准length_px≤10%；body separation相对whole-video median≤20% | 重建几何半径与物理pivot-to-COM L分开。正式拟合finite检查没有纳入tracked pivot坐标，见 D02 |
| fitting interval / samples | 从effective release到record end；valid帧至少max(50,50% post-release帧数)；`evenly_spaced_indices`：valid索引列表上linspace→rint→unique，最多500点 | 是按有效帧序号抽样，不是缺测后重新压缩时间，也不保证缺测不均时严格时间等距；记录实际frame/time列表与排除原因 |
| weights | `sqrt(clip(tip_likelihood,0.05,1))`乘角度残差；仅相对质量权重 | 非概率、非逆方差；manual correction无likelihood时如何赋权需P0明确。不继承产品0.60阈值过滤后的点集作为论文默认 |
| bounds | α₁*∈[0,0.5] s⁻¹；α₂*∈[0,0.5] rad⁻¹；ωobs²∈[0.20g/L,1.60g/L] s⁻²；g=9.80665 | 显示L的物理定义；保存实际数值和单位，不能仅存“默认” |
| initial seeds | `fitting.py:estimate_omega2/estimate_alpha1`；频率seed factor [0.975,1,1.025]；M0三起点；M1三起点+M0 warm start（α₂=1e−8） | 保存实际起点和每次结果；不是随机多起点。精确振幅衰减/频率估计规则以函数源码为准 |
| integrator | `solve_ivp(method='DOP853',rtol=2e−7,atol=2e−9,t_eval=selected_times)`，从0积分；未显式设置max_step | 必须把继承库默认的设置也在版本化配置中显式化；不能给未知值猜一个论文参数 |
| optimiser | `least_squares` bounded，soft_l1，f_scale=rad(0.5°)，max_nfev=180，x_scale=jac；最小cost有限candidate获选 | method/ftol/xtol/gtol/jac没有显式传入；历史环境SciPy1.17.1，P0需恢复该版本隐式默认。nonconverged应独立显示，不能当success |
| objective / RMSE | objective是在抽样点的加权robust residual；RMSE在所有geometry-valid post-release帧，不加权，单位deg供展示 | 区分 optimiser cost、weighted exploratory RMSE、full RMSE；M0/M1比较使用共同输入/区间/IC/QC配置 |
| phase/high-speed comparison | `audit_phase_space_contraction.py`：distance²=(Δθ)²+(Δω/sqrt(g/L))²；valid observed速度的1/3、2/3分位数划分，高速为上1/3；zero-crossing诊断见`diagnostics/metrics.py`，按顺序配对observed/model过零 | 缺失过零/段断开时不能继续盲目ordinal配对；新视频行为P0固定；指标不得与纯θ RMSE互换 |
| physical diagnostics | fitted bound flags、Jacobian rank/condition、late equilibrium、early/late residual；e*=ω²/2+ωobs²(1−cosθ)，de*/dt=−α₁*ω²−α₂*|ω|³ | rank/condition是数值诊断，不替代结构不可辨识证明；energy单位s⁻²，不伪称J |
| EDP图 | `validate_model_energy_frequency.py`：order=max(3,round(0.22π/(sqrt(ωobs²)dt)))；振幅门槛max(0.4°,1.5%max)，skip0/5，正文图skip5；指数或带offset指数拟合振幅包络；相邻能量均值/绝对差；模型ω CubicSpline后每半周期500点Simpson | 该包络处理不是重新拟合M1；保留raw/envelope区别。状态积分使用DOP853 rtol2e−9/atol2e−11，非拟合容差；N_STEP=5分支另有700点评估，不混进正文单半周期量 |
| valley图 | 固定α₁*、α₂*，扫描q=ω₀²/(1+αa)，robust objective用逐点平均尺度；插值成101×91 surface，αa0–0.12 | 条件截面，非所有其余参数重新优化后的profile。GUI必须解释保持不变的量；不能将插值的图当新的独立拟合证据 |

## 5. 论文图 → 最终源文件

v2.0 的图编号与历史目录号不同；已核对 `manuscript_draft_v2_0.tex` 的 include 顺序。

| 正文图 | EJP asset directory / producer | 主要source data与科研入口 |
| --- | --- | --- |
| 1 | `manuscript_assets/figures/fig01/make_fig01_v1_4.py` → `figure1_v1_4.pdf` | calibrated P011 frames、apparatus images；A02/A05；装置视觉不属于平台实现 |
| 2 | `fig02/make_fig02*.py` → `figure2.pdf` | `fig02_heldout_geometry_usable.csv`、`fig02_csrt_reset_heldout.csv`；A05 |
| 3 | `fig_illumination/make_fig_illumination.py` → `figure3_imaging_conditions.pdf` | stress-condition frame assets；A06 |
| 4 | `fig03/make_fig03.py` + frozen option5b rendering → `figure3_v1_1.pdf` | `fig03_p011_measured_phase_and_speed.csv`、`fig03_information_comparison_summary.csv`；A08/A09 |
| 5 | `fig05/make_fig05.py` → `figure5.pdf` | `fig05_representative_trajectories.csv`、`fig05_all_video_rmse_improvements.csv`；A08/A10 |
| 6 | `fig04/make_fig04.py` → `figure4.pdf` | `fig04_objective_surface.csv`、`fig04_complete_raw_parameter_sets.csv`、`fig04_raw_set_trajectory_overlap.csv`；A13 |
| 7 | `fig06/make_fig06.py` → `figure6.pdf` | `fig06_tail_frequency_all_videos.csv`、`fig06_energy_p011_envelope.csv`、`fig06_energy_skip5_all_videos.csv`、`fig06_length_frequency_all_videos.csv`；A14–A16 |

fig03/04/05/06 的 `provenance_manuscript.json` 中 **11个输入文件 SHA-256 全部匹配**。未声称所有最终PDF的二进制哈希均已与脚本输出一一核验；本轮目标是平台方法来源，不是重新生产论文。

## 6. Version recovery / discrepancies / unknowns

| ID | 事实与影响 | 后续处置（本轮不改科学结论） |
| --- | --- | --- |
| D01 | main SG7/2 vs论文及分析SG9/3；论文导数是直接SG derivative | publication独立profile；不改main默认，不沿用额外预平滑 |
| D02 | 论文§3“all four finite/valid”；`data_io.py` fitting geometry_valid检查θ、φ、tip likelihood、radius、body length，未检查tracked pivot finite；且没有0.60 likelihood硬截断。benchmark四点完整率是另一套检查 | P0由用户裁定：legacy reproduction mask与学生严格四点QC如何区分。不得默默重算论文结果或把二者叫同一mask |
| D03 | DB `residual_trajectories`旧LED版本；正文用effective CSV；部分DB的TOML同样有历史role | P0固定有版本的source map；本轮不修DB，不覆盖旧历史 |
| D04 | 当前`fitting.py` SHA `fc16f4af0a65169fe678b003fe62905dde7016d6db308aedf746fc9cfde3f939`与正式manifest不符 | 已在`20260726模型选取存档.zip::src/inversion/fitting.py`恢复匹配SHA `e9158712782bb56900535f103f8b268cb59112b74b7593a88a2891c179e1e163`的字节；只读zip。差异仅新增`warm_start_only=False`及其条件分支，正式默认路径未变；仍优先封存版本 |
| D05 | 三种extrema、两类能量量、不同求解容差服务不同诊断 | 不能设计全局一个“extrema default”覆盖所有图；参数按分析profile完整记录 |
| D06 | 历史LED−1、70s tail、最少50点/50% valid基于原实验，未证明对任意学生视频合理 | 保留历史profile，学生UX政策P0显式裁定；unknown不得伪装科学默认 |
| U01 | 177标签坐标/模型实体只验证到manifest；用户确认保存且要求不继续寻找 | 不阻塞规划，不把“已保存”升级成“本轮训练/加载通过” |
| U02 | 全部本地镜像输入哈希未完成：OneDrive读取timeout；未执行历史脚本或全链复跑 | 后续使用可读SQLite+封存文件建立golden fixture；逐文件恢复/验证按mini-plan进行，不要求原始视频复分析 |
| U03 | SciPy隐式默认、历史依赖完全锁定尚未从安装锁文件证实；formal summary是Python3.13.0/NumPy2.4.3/Pandas3.0.1/SciPy1.17.1，产品约束Python3.11–3.12 | P0记录显式算法设置与跨版本数值容差，P3软件回归，不把旧环境版本直接当runtime发行推荐 |
| U04 | 当前资产没有定义新视频缺测、manual权重、预释放不足、短tail情况下的统一学生政策 | 属产品契约待定，不是需要追加论文实验；必须先决定再实现对应分支 |

正文方法已能找到可审查来源；尚未做“新平台输出等价于论文输出”的认证。该认证属于后续软件实现与回归验收，不属于本轮科研补充分析。
