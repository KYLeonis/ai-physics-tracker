# ADR 0003: 项目持久化采用"JSON 清单优先"的混合方案

## Status

Superseded in part by ADR-0004 (2026-08-29). All decisions except the external
video locator clause in Decision 4 remain Accepted (2026-08-28).

## Context

Phase 1（Project & Data Foundation）需要确定项目的持久化格式。约束与输入：

1. **数据形态**：项目元数据、视频登记、Timeline、Track、逐帧观测（TrackPoint，稀疏、万级以内）、标定、派生数据定义（`docs/spec/data-model.md`）；未来还有引擎批量原始输出（DLC HDF5/Pickle 等）与大型逐帧数组。
2. **可移动性**：整个项目目录必须能复制/移动到另一台机器（mac ↔ Windows）后直接打开——路径只能相对引用，且保存不得与文件锁冲突（Windows 打开句柄不可覆盖，见 `docs/development.md` §1.1）。
3. **规模**：单摆基准场景为手工标注几十~几百点、引擎跟踪万级点；2026-08-28 微基准（CPython stdlib json，完整 TrackPoint 结构）显示 10k 观测 ≈ 4 MB / 读写 ~45 ms，36k ≈ 14 MB / ~150 ms，100k ≈ 40 MB / ~0.5 s（`docs/spec/project-format.md` §5）。
4. **候选**：单文件 JSON、JSON 清单 + 外置数据、SQLite、Parquet/CSV 混合（对比见 `docs/spec/project-format.md` §1）。
5. **调研先例**：Kinovea 用带版本号的 `.kva` XML sidecar（视频不入库、先读尺寸/时序再读坐标）；DLC 用 config.yaml + labeled-data + H5/CSV 分层目录；SLEAP 用 .slp 单文件 + 分析导出分离；Pose2Sim 用分阶段目录。同时 project map §7.12 明确"把引擎输出格式当领域模型"是反模式。

## Decision

采用 **JSON 清单优先的混合方案**：

1. 全部第一方数据存于项目根单一 `project.json`（UTF-8，人类可读，原子替换写入，滚动备份 `project.backup.json`）。
2. 引擎批量原始输出不进 JSON：适配器直写 `data/engines/`，清单只保存引用与摘要；大型派生数组经 `DerivedData.payload_ref` 外置 `data/derived/`。
3. 根对象首个字段恒为 `schema_version`（整数）：旧软件拒开新版本文件；版本落后走"纯函数迁移链"逐级升级；新增可选字段/枚举值不升版本，读取必须容忍未知键并原样保留。
4. 路径以相对项目根为准（posix 分隔符存储），绝对路径仅作重连提示缓存；写策略为"临时文件 + `os.replace` 原子替换"，绝不原地覆写。
5. `TrackStore` 接口隐藏存储后端，未来若观测规模超出 JSON 舒适区（>10⁵ 行），可切换为 NDJSON 外置 + 清单引用（实现层变更 + additive 指针），不破坏数据模型。

**否决**：SQLite（查询能力无收益；打开的库文件使目录复制在 Windows 上有文件锁/WAL 一致性风险；不可读难调试）；Parquet（为当前规模引入 pyarrow 重依赖，数组需求已由外置路径覆盖）；外部格式（DLC/SLEAP 原生）作主存储（反模式，见上）。

## Consequences

- **正面**：零第三方依赖、可 diff 可人工检查、目录级可移植性最直接、原子写入简单可靠、schema 版本策略一目了然；引擎海量输出从一开始就被隔离在清单之外，第一方文件规模天然受控。
- **负面/代价**：每次保存全量序列化（当前规模亚秒级，可接受）；无查询/事务能力（单机单用户无此需求）；超大观测规模需要未来切换实现（接口已预留）。
- **跟进**：Phase 1 按 `project-format.md` 实现并验证 §6 验收项；schema v1 随 Phase 1 落地；迁移链自 v2 起生效（v1 无迁移）；未来外置数组格式（NumPy/Parquet）选择届时另记 ADR。
