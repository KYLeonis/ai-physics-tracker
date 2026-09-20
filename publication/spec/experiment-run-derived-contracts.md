# P0.2 Experiment / Run / Derived Contracts

Contract v1，2026-09-20；只定义后续实现与验收，不声称本轮产品已读写新格式。科学数值行为继承[P0.1](scientific-profiles.md)，本合同不改冻结profiles。

## 1. 存储与兼容决策

继续单一project.json清单+immutable外置payload，复用Track/TrackPoint/Timeline及原子save。**publication项目采用schema_version=2**；不把多Track语义偷偷塞入v1 extra_fields。现有repository在解码domain前拒绝version>1，但v1未知字段会被保留而被旧业务忽略：后者无法保护四轨activation，因此不能作为安全兼容方案。见[Accepted ADR-0017](../../docs/decisions/0017-publication-project-contract.md)。本轮不提升CURRENT_SCHEMA_VERSION、不实现迁移。

未来loader读取v1：原样支持legacy项目；创建第一个Pendulum experiment时显式Save as publication project到新目录，复制原项目管理资产、保留原manifest及外部媒体locator；迁移失败不改原项目。新目录v2、migration记录source schema/source manifest SHA、保留所有UUID及未知extension siblings。没有四role时不能猜角色、release或标定；普通legacy项目可继续v1保存。v2降级v1不提供；CSV结果导出不是可降级项目。未知future schema拒绝；未知required capability拒绝写入；未知可选字段保留但不执行。

schema2顶层required_capabilities固定包含pendulum-four-role-v1与scientific-results-v1；读者必须理解全部required项才能写入。schema2允许：既有videos/timelines/tracks/observations/calibrations/legacy derived；tracking_runs按下述membership更新；新增publication对象（contract_version=1、experiments、model_references、scientific_results）。这些集合是project内对象映射，key=UUID且必须等于对象自身对应ID（experiment_id/model_id/result_id/run_id等），引用必须存在；load拒绝key/id不一致。所有项目管理路径相对根、POSIX分隔符；拒绝绝对路径、..、symlink escape、Windows保留名。视频继续现有external locator/relink规则。runtime安装路径属于本机设置，不进入可移动project事实。

## 2. PendulumExperiment

首版每video最多一个普通Pendulum experiment；一个Track不能同时绑定两个role或两个experiment。字段：

| 字段 | 类型 / invariant |
| --- | --- |
| experiment_id, video_id | UUID，video存在 |
| mode, contract_version | pendulum, 1 |
| roles | 恰好tip/body_top/body_bottom/pivot→四个不同、同video Track UUID；规范role顺序固定 |
| measurement_revision | 单调非负整数；事务提交后更新，不依赖mtime |
| pendulum_geometry | fixed_pivot_px=null或有限[x,y]；true_vertical=null或完整{top_px,bottom_px}非重合有限坐标；tip_radius_reference_px=null或正有限数；缺项明确null，允许分步保存，不用0代替 |
| scale_binding | 固定active_calibration_by_video；从同video既有active Calibration解析，不另存第二个可冲突active指针。运行snapshot冻结calibration_id及完整值 |
| physical | length_m与g_m_s2均为正有限数（length为effective pivot-to-COM）；length_source及g的profile provenance非空；load/request均拒绝0、负值、NaN/Inf |
| release_frame | null或[0,video.frame_count)整数；null时可标注，不可分析/fit |
| scientific_profile | ID/version/原始文件SHA；用户参数覆盖单独保存，运行前展开 |
| qc_overrides | 明确排除frame ID集合、reason；不改raw points |
| active_infer_run_id | null或同experiment_id/video_id的completed infer run，恰好四members与当前roles及run.role_bindings一致；加载时也验证，唯一activation真值 |
| activation_history | 不可变事务记录id、from/to、每role采用/保留manual计数、timestamp及input digest；role编辑记录old/new role_bindings完整快照与binding revision（即使无active run），result provenance引用对应revision |

scale来源为既有Calibration（scale_end_1_px/scale_end_2_px、known_length、unit m/cm/mm、origin_px、rotation_deg）；转换沿用CalibrationTransform，默认origin=null意味着图像左下角，snapshot记录解析后的origin和video.height，不默认为pivot。true vertical与rotation_deg不是同一量，不由world rotation覆盖角度参考。物理L由明确measurement/source指定，可引用scale转换测量，但不能自动用tip半径替代COM长度。

true_vertical的top→bottom是用户明确确认的重力向下方向，不按像素y自动排序；geometry还记录direction_confirmed及该确认绑定的端点digest。缺确认可保存但不可分析；改端点撤销确认，加载时核对digest，方向和确认均进入运行snapshot/input digest。

加载时active calibration引用必须存在且同video，null合法表示未标定；geometry的非null子对象必须整体有限合法。切换active_calibration_by_video、编辑active Calibration的scale/origin/rotation、video.height改变都计入experiment calibration digest并使依赖结果stale，后台capture snapshot重新比较。删除active calibration把绑定解析为null且失效，不能偷选另一个Calibration。

未设置标定/release属于setup-incomplete，允许保存；禁止以0填缺。编辑任何role绑定需四role整体合法后提交，并在同一事务Clear旧四成员AI projection/active指针（保留manual），记录旧bindings历史并使科学结果stale；不得将旧active run重新解释为新role。不允许部分绑定的普通experiment，只可在UI draft暂存。当前Track refinement_state单轨active指针对属于Pendulum的Track不再权威；迁移时清除/归档旧指针到migration history，新workflow从experiment事实投影。未绑定generic tracks仍用legacy单轨机制。对experiment-bound tracks，所有旧单轨AI mutator（activate_infer_run、replace_active_infer_run、clear_active_ai_observations、直接infer import/activation）必须显式拒绝，或在调用前明确路由至完整四轨experiment事务；不得仅忽略旧active指针而允许单轨写入。人工单点修正仍合法，但必须更新measurement revision与stale，不改变active run身份。

## 3. 一个dataset / 一个run / 四个bodyparts

schema2 TrackingRun保留run_id/video_id/engine/version/task_type/config/status/时间/错误/产物；将单track_id替为member_track_ids（唯一UUID有序列表），可选experiment_id及role_bindings快照。legacy v1 run迁移为一个member，不假装四点run；v2 Pendulum run必须恰好四个members且与快照映射一致。角色快照用于历史解释，不随experiment编辑而改写。所有run成员必须存在且属于run.video_id。Pendulum run的experiment_id与role_bindings必须同时存在；快照keys恰好四个规范role，无额外项，按规范顺序映射到members。仅generic/legacy run可省略二者；load时拒绝缺成员、跨video或不完整快照。

Train request冻结：共同代表帧、每frame四manual label坐标/point ID/revision、共同train/test分割、fixed-check排除、bodypart映射、engine/config/seed、input digest。complete training frame=同一源frame上4个当前manual、finite、非superseded labels；不得拼邻帧，不能用AI代替未标点。DLC实际名称可有显式marker_tip→tip映射；普通产品写出规范四名称；dataset完整性和科学QC分开（标注训练不要求当前geometry gate先通过）。

Inference request冻结同一模型reference、四role映射、video/timing identity、任务范围、runtime identity。单run单目录、单次DLC调用、按bodypart回填；每frame角色缺测单独保留，缺某点不丢弃整个raw frame。结果统计包含每role和4/4完整帧，不能四次独立推理冒充一个联合run。

生命周期pending→running→completed/failed/cancelled；terminal不可原地重试，retry新run_id。训练success必须验证选定checkpoint/config及产物；推理success必须验证输出video/frame/bodypart/坐标与metadata，再成为candidate，不自动activate。Import model不是train run，不伪造completed training history。

## 4. TeacherModelReference

字段model_id、origin(trained/imported)、source_train_run_id（imported必须null）、engine=deeplabcut_pytorch、DLC/PyTorch/model architecture版本、bodypart mapping、engine配置引用、checkpoint引用、manifest hash、created_at、compatibility_state及self-test evidence。

origin=trained时source_train_run_id必须引用本项目completed train run，checkpoint/config产物manifest与model manifest一致，四role mapping与来源run快照对应；来源experiment明确保留，可显式应用到另一experiment但不能冒充其训练历史。load/import均校验，失败拒绝引用。

Import DLC Model…导入config+checkpoint+必要engine config组成的bundle（可为目录）；复制到models/<model_id>/，逐文件relative path/size/SHA256、明确checkpoint选择与原始basename。不执行用户脚本，不依赖原老师绝对路径；YAML仅安全解析，必要路径在复制后显式重写到managed副本并保留original/config mapping。teacher model只接受四bodypart单动物模型；重复/missing角色、multi-animal/object身份模型拒绝，不引入通用model library。

state=unverified/compatible/incompatible/unavailable；版本/配置静态通过只是unverified；当前runtime实际加载+一次合法输入infer通过才compatible。换runtime版本、checkpoint/config内容或bodypart mapping后撤销兼容证据；旧fit仍可查看但不替代模型加载。CPU可用性不从GPU成功推断；MPS不可用时记录CPU fallback，用户看到实际device。模型文件缺失只阻断需要它的新infer，已冻结measurement/scientific结果按自己的inputs判断，不把所有历史结果判坏。

## 5. 四轨原子activation与失效

一个ProjectSession事务完成：校验candidate及四成员→构建四轨AI projection（preserve manual，AI retained as superseded where适用）→更新experiment唯一active指针/history→增加measurement_revision→mark affected科学结果stale→提交一个新Project快照/一次undo命令。异常/取消/成员不符/输入代际过期返回原快照，不能逐role发布或出现混合run。Clear也四轨整体执行，只清active AI投影、保留manual与历史raw产物；Undo恢复全部四轨、指针和history对应状态。

外部文件先写run独占staging，完成后验证hash并atomic rename到immutable run目录，最后manifest原子发布。崩溃可留下未引用孤立产物，但不能manifest指向尚未完成的payload；失败不删旧结果或科研原件。删除被experiment/run/result引用的track/video/model必须被引用检查阻止，提供显式删除关联experiment/result计划后才执行，不自动断引用。UI不保存第二套workflow truth。

## 6. Multi-input identity / stale

运行请求记录canonical JSON digest（UTF8、sort_keys、separators固定、allow_nan=false，明确float64表示）及组件digest：video内容identity+timing、四role绑定、每role adopted observations含manual/AI provenance、active run ID、calibration、release、physical L/g、QC exclusions/reference、resolved scientific config、upstream result payload hash及core version。digest包含解析后的scale calibration ID+全部scale/origin/rotation及单位/height、pendulum geometry独立字段。不能只用track_id、rowcount或mtime。changed_at仅审计，不作为内容相等证据。

Dependencies按实际读取字段记录；首版可保守将measurement/calibration/release/physical/QC改变置全部experiment科学结果stale。显示degree/rad、颜色/缩放变化不改变numerical signature。模型不可用不改变已冻结点，单纯模型目录移动但内容不变不使θ变值。新fit参数使依赖fit的energy/criticism/valley stale，不使原θ stale。publication结果仍用input digest复核，即使旧stale布尔漏更新也不得返回valid。后台完成时先对照capture digest再commit；失败保存日志但不替换当前valid result，取消后迟到结果拒绝。

## 7. Scientific request/result与导出

Qt-free request无widget/session/文件I/O：request_id、experiment_id、kind、input digest、frame IDs、t_absolute/t_relative、θrad、各role source、fit_mask/reasons、relative weights、IC及来源、L/g、已展开profile与逐字段provenance、实际bounds/seeds/sample IDs、solver/optimiser、core/dependency versions。数组长度、递增时间/unique frame、finite/missing、units严格按P0.1。Normal/Advanced唯一不同是用户如何编辑resolved values，不选择另一scientific实现。

结果record：result_id/kind/schema/core_version/created_at/input digest、upstream IDs、config snapshot、execution_status(success/nonconverged/failed/cancelled/insufficient_data)、freshness(valid/stale)分开；typed payload columns name/dtype/unit、frame/time mapping、mask+reasons；fit parameters/units、各start状态、predicted/residual、cost/full RMSE、warnings/comparability。不得把scalar θ塞进既有2-column chart values。旧DerivedData供legacy kinematics使用；publication scientific_results是新typed collection，不造tip anchor掩盖多输入。

轻量scalar metadata写manifest；bulk payload为标准JSON（null+reason）或CSV+声明schema，明确编码/空值，引用path/size/SHA。P0不增加Parquet依赖；后续若需NPZ应另明确安全load与版本，禁止pickle作为第一方payload。Payload不可原地覆盖，新结果新ID。

可移动export manifest包括profile版本/展开参数/provenance、源frame/absolute和relative times、four points/source/confidence/QC、θω、period/energy、fit/残差/diagnostics以及不可用原因。原始媒体/模型默认不导出，明确可选bundle；导出不改变实验、不给缺失点补零、不输出frame独立CI。跨模型比较先验证共同input/IC/interval/mask/weights/sampling/loss digest；保持P0.1零分母/非收敛政策。

## 8. P1实现前的验收序列

1. v1 unknown fields round-trip、旧reader拒v2；Save-as migration不改原目录，失败回滚；未知required capability拒写。
2. 四role同video/无重复；missing calibration可保存但分析门禁；manual confidence=null不转1。
3. 共同4/4 frame join和split/fixed-check排除；teacher import不造train，mapping/config missing拒绝。
4. 四轨activation/clear/undo/取消/失败/迟到result事务一致；对bound track调用每个旧单轨AI mutator均拒绝且整个快照不变；generic unbound旧路径仍可用。
5. 每组件变化stale、无关GUI改动不stale；跨结果dependency传播；save/reopen签名一致。
6. request/result完整单位+missing语义、Normal/Advanced相同resolved配置同core调用；export原始frame/time无压缩。

本轮compatibility probe只验证当前旧reader边界与unknown字段保留；以上产品实现测试在P1/P2对应mini-plan落地，不能把本合同或示例fixture称为产品实现完成。
