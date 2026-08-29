# ADR 0004: 外部视频使用可空项目路径与绝对 locator

## Status

Accepted (2026-08-29)

Supersedes the external-video clause of ADR-0003 Decision 4：项目管理的数据路径继续使用相对路径，但外部视频的
`original_path` 不再只是提示缓存；当 `file_path = null` 时，它是实际 locator。

## Context

ADR-0003 要求项目内路径相对项目根，同时把 `original_path` 定义为仅供重连提示。
这与“视频默认只引用、不复制”的产品行为在 Windows 跨盘符场景下冲突：项目位于
`C:`、视频位于 `D:` 时不存在可由 `os.path.relpath` 表达的相对路径。

可选方案只有两类：强制把跨盘符视频复制进项目；或在清单中显式区分项目管理资源
与外部资源。前者会默认复制大型视频，违背既定工作流，也增加磁盘和等待成本。

## Decision

1. `Video.file_path` 为 `str | null`。非 null 时只允许项目根内、POSIX 分隔符、
   Windows-safe 的相对路径；禁止 drive、`..`、保留名和非法字符。
2. `Video.original_path` 是唯一允许的绝对路径。`file_path = null` 时，它是外部
   视频的实际 locator；`file_path` 非 null 时，它可作为原始位置 fallback。
3. 解析顺序为：存在的项目内 `file_path` → 当前平台存在的 `original_path` →
   relink。解析边界再次验证项目内目标没有逃逸项目根。
4. 外部 relink 更新 `original_path` 并保持 `file_path = null`；用户选择复制进项目
   后才写相对 `file_path`。两者均不修改任何观测。
5. 清单可随目录移动并打开；只有项目内资源保证随目录移动后仍可解析。外部视频在
   新机器上 locator 不存在时进入 relink，这是显式的非便携状态而非静默失败。

## Consequences

- Windows 任意盘符上的视频都可默认只引用，不必复制大型文件。
- `project.json` 如实区分“项目自包含资源”和“外部依赖”，可移动性承诺不再含糊。
- 读取方必须处理 `file_path = null`，并把无法解析返回为 relink 状态。
- schema v1 尚未发布，因此本变更直接封入 v1，不创建迁移函数；未来已发布格式再发生
  同类不兼容变更时必须递增 `schema_version`。
