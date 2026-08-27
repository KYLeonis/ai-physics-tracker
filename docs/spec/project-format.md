# 项目格式规范（Project Format Spec）— 持久化与项目目录

- 日期：2026-08-28 · 状态：**Accepted**（决策正文见 [ADR-0003](../decisions/0003-project-persistence-format.md)）
- 来源：`docs/research/software-spec-plan.md` 行动项 A4（持久化与项目格式，含跨平台路径规则）
- 输入：raw notes（kinovea `.kva` sidecar、deeplabcut 项目目录、sleap `.slp` 单文件、pose2sim 分阶段目录）、`docs/development.md` §1.1、`docs/spec/data-model.md`、补充业界 schema 版本迁移惯例调研
- 性质：本文件定义**存储形态**；数据对象与语义见 `data-model.md`

---

## 1. 候选方案对比与结论

| 维度 | 单文件 JSON | JSON 清单 + 外置数据 | SQLite | Parquet/CSV 混合 |
| --- | --- | --- | --- | --- |
| 依赖 | 仅标准库 | 仅标准库 | 仅标准库（sqlite3） | 需 pyarrow/pandas 写 |
| 人工可读 / 可 diff | ★ | ★ | ✗（二进制） | 部分（二进制/宽表） |
| 原子写入 | ★（临时文件 + 替换） | ★ | 事务内置，但 **WAL/句柄与 Windows 文件锁、目录整体复制冲突** | 一般 |
| 万级观测读写 | ★ 实测足够（§5） | ★ | ★ | ★（但 Phase 1 无必要） |
| 损坏风险 | 单文件（用备份缓解） | 单文件 + 多文件一致性 | 低（但损坏难人工恢复） | 多文件一致性 |
| 可移动项目目录 | ★ | ★ | △（打开时复制目录有锁风险） | ★ |
| schema 版本迁移 | ★（显式 version 字段） | ★ | `PRAGMA user_version` + 迁移 | 需每文件版本 |
| 未来扩展（引擎 HDF5、大型数组） | 需外置逃逸口 | ★ 天然支持 | 可但绕开标准库生态 | 适合数组但不适合关系型元数据 |

**结论（ADR-0003）**：采用 **JSON 清单优先的混合方案**——

1. 第一方数据（项目元数据、视频登记、Timeline、Track、TrackPoint、Calibration、DerivedData 定义与小型数值）全部存于项目根的**单一 `project.json`**（UTF-8、人类可读、可 diff、可整文件原子替换）。
2. 第三方引擎的批量原始输出（如 DLC 的 HDF5/Pickle）**不解析进 JSON**：引擎适配器直接把文件写入 `data/engines/`，`project.json` 只保存引用 + 摘要（run id、行数、文件哈希）。这同时满足"DLC 格式不是我们的领域模型、只是外部适配契约"（project map §3.4）与"大文件不入库"边界。
3. 超大数组（万帧以上的逐帧派生数值）通过 `DerivedData.payload_ref` 外置到 `data/derived/`（Phase 3 起才会用到；Phase 1 数值内嵌）。
4. `TrackStore` 接口（data-model.md §7.4）隐藏存储后端：若未来观测规模真的超出 JSON 舒适区（>10⁵ 行级），可把观测迁移为 NDJSON 外置文件 + 清单引用，属实现层切换 + additive 清单指针，**不需要改数据模型、不需要 schema 破坏性迁移**。

被否方案的理由存档：

- **SQLite**：查询能力在单机单用户场景收益为零；打开着的库文件让"整个项目目录复制到另一台机器"出现 Windows 文件锁/WAL 一致性风险（development.md §1.1 规则 3）；人不可读导致调试与版本对照成本高。标准库 `sqlite3` 的优点（事务、免依赖）被 JSON 的原子替换策略覆盖。
- **Parquet**：为"万级"规模引入 pyarrow 重依赖违背 Phase 1 最小化；数组型存储需求已被 `payload_ref` 外置路径覆盖（届时若选 Parquet/NumPy 再记 ADR）。
- **DLC/SLEAP 原生格式当主存储**：project map §7.12 明确反模式——外部格式是适配契约不是事实源。

---

## 2. 项目目录结构（可移动）

```text
MyExperiment/                        # 目录名 = 项目可移植单元；避免 Windows 保留名/非法字符
├── project.json                     # 全部第一方数据（schema_version 见 §4）
├── project.backup.json              # 保存成功后滚动写入的上一版本（自动，可用于人工恢复）
├── videos/                          # 可选：用户选择"把视频复制进项目"时的存放处
│   └── pendulum.mp4
├── data/
│   ├── engines/                     # 引擎原始输出（DLC HDF5 等），适配器写入，清单只引用
│   └── derived/                     # 外置派生数组（payload_ref 指向；Phase 3 起使用）
└── models/                          # 本项目训练/引用的模型（Phase 4 起；大文件，gitignore）
```

- 视频默认**只引用不复制**（`file_path` 可指向项目外）；"复制进项目"是用户可选项，用于打包归档。
- 整个目录复制/移动到另一台机器（mac ↔ Windows）后项目必须可直接打开——这是格式验收标准（§6）。
- 目录内文件均为常规文件：不使用 symlink（development.md §1.1 规则 7）。

---

## 3. 路径规则（跨平台）

1. `project.json` 内一切路径以**相对项目根**存储，分隔符统一 `/`（posix 风格），实现用 `pathlib.PurePosixPath` 存储、`Path` 解析（Windows 自动适配）。
2. `videos[].original_path` 是唯一允许的绝对路径，仅作重连提示，绝不参与解析。
3. 解析顺序：相对路径基于项目根解析 → 存在则用；不存在 → 按 `original_path` 与文件名在最近已知位置提示用户重连（relink）→ 重连成功只更新 `file_path`，不触碰任何观测数据。
4. 编码：`project.json` 及一切导出文件显式 UTF-8（development.md §1.1 规则 2）。
5. 项目目录名/轨迹名等用户可输入的名称在落盘为文件/目录时过滤 Windows 保留名与非法字符 `<>:"/\|?*`（development.md §1.1 规则 5）；`project.json` 内部字段不受此限。
6. 路径长度：实现保留对项目根总长的警告（MAX_PATH 260），尤其 Phase 4 的 DLC 子目录层级深。

---

## 4. schema 版本与迁移策略

`project.json` 根对象第一个字段恒为：

```json
{ "schema_version": 1, "project_id": "…", "…": "…" }
```

规则（业界惯例 + 仓库内先例）：

1. **从 v1 起就带版本字段**；此后任何**不兼容**变更必须递增整数版本。
2. **兼容性追加不递增**：新增可选字段、新增枚举注册值（source/unit/flag）、`ui_state` 内部变化，读取方必须容忍未知键并在保存时**原样保留**（tolerant read / faithful write-back）。判断口诀："旧版软件读到新字段会不会坏？不会就不升版本。"
3. **加载守卫**：`schema_version` 高于实现支持值 → 明确拒绝加载，提示"文件由更新版本创建"（旧软件不猜新格式）；低于 → 走迁移链。
4. **迁移链**：实现按 `v(n-1)→v(n)` 顺序执行一系列**纯数据变换函数**直至当前版本；迁移不依赖 GUI/业务对象；每个迁移函数有独立单元测试（含幂等性/最小样本）；**已发布的迁移函数永不修改，只追加**。迁移在内存完成后走正常保存流程（原子替换 + 备份滚动），原文件在保存成功前保持不动。
5. 仓库内先例（作为格式一致性参照）：Kinovea `.kva` 带格式版本且"先读图像尺寸/时序再读坐标"（加载顺序即兼容性设计）；DLC `ProjectConfig` 带 validation/version migration/legacy 别名。本项目采用同思路、JSON 载体。

---

## 5. 万级观测的读写方式（ADR 支撑结论）

微基准（2026-08-28，CPython 3.14，stdlib json，单条观测 15 字段的完整 TrackPoint 结构）：

| 观测数 | 文件体积 | json.dumps | json.loads |
| ---: | ---: | ---: | ---: |
| 10 000 | ~4 MB | ~47 ms | ~41 ms |
| 36 000（10 min @ 60 fps 单轨迹） | ~14 MB | ~167 ms | ~139 ms |
| 100 000 | ~40 MB | ~483 ms | ~386 ms |

结论：Phase 1 与可预见 Phase 2–5 规模（手工标注几十~几百点；模板/引擎跟踪万级点）下，整文件 JSON 读写在**亚秒级**，完全可接受；保存每次全量写 + 原子替换。超出舒适区（>10⁵ 观测）时的逃逸口见 §1 结论 4——引擎海量原始输出从一开始就不进 JSON（§1 结论 2），因此第一方 JSON 的规模上限主要由"修正后保留的有效观测"决定，天然远小于原始推理输出。

保存策略（Windows 安全）：

1. 序列化到同目录临时文件 `project.json.tmp` → `os.replace` 原子替换（development.md §1.1 规则 3：绝不原地覆写）；
2. 替换成功后，把**替换前**的旧文件滚动复制为 `project.backup.json`（保留一个版本即可，深备份链不做）；
3. 保存含 `modified_at` 更新；加载失败时提示用户 `project.backup.json` 的存在，不自动覆盖。

---

## 6. 验收标准（对应 PLAN A4）

- [ ] 目标目录结构为 `MyExperiment/ + project.json + data/…`；
- [ ] 整目录复制/移动（mac ↔ Windows）后项目可打开：路径解析只依赖相对路径（§3）；
- [ ] 万级观测读写方式有明确结论与数据（§5）；
- [ ] schema 带 `schema_version` 且升级策略成文（§4）；
- [ ] 视频/模型等大文件只引用不复制入清单（§1/§2）；
- [ ] Phase 1 需求文档（phase1-requirements.md）引用本文件作为持久化验收依据。
