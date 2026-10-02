# 0021. P6.1 原生应用构建：PyInstaller onedir host 与外部 AI runtime 分离

- Status: Accepted（2026-10-02，用户裁定 Windows G1–G4 真机门禁延期至发行前；macOS DMG 为 P6.1 优先交付物）
- Scope: publication 产品线 P6.1（native application builds）

## Context

P6 目标是普通用户免 Python 环境安装使用。P0.3 已验证 frozen host + 外部 Python worker 的
可行性（PyInstaller 6.22.3，Mac arm64 G1–G4 通过）。原 P6 计划要求先补 Windows G1–G4 真机
门禁才进入实现；2026-10-02 用户明确裁定：**Windows 真机限制暂不考虑，以 GitHub CI 双平台
通过、Windows 产物可运行且无关键 bug 为准；优先封装 macOS 并产出 DMG**。该裁定改变的是
验收时点，不是验收标准本身——Windows G1–G4、G5 clean-machine 与学生 pilot 仍是发行前
（P6.3/P6.4）待补项。

约束：host（GUI/视频/科学计算/导出）与 AI 栈（torch/DeepLabCut）必须依赖分离——CI 早已在
无 DLC 环境跑全量测试，证明 host 闭包本就不含 DLC；但 `pyproject.toml` 仍把 deeplabcut 列
为必装依赖。external worker 通过 `PYTHONPATH=<受信源码根>` 在独立解释器中运行
`ai_physics_tracker.worker`，host 对 worker 源做字节 SHA 并 fail-closed 校验，因此 frozen
包必须携带与自身同 commit 的 worker 源码。

## Decision

1. **Host 打包**：PyInstaller `onedir`（非 onefile；便于检查依赖闭包与增量更新）。
   macOS 产出 `.app` 并用系统 `hdiutil` 生成 UDZO DMG；Windows 产出 onedir 目录并压 zip
   （Inno Setup 安装器留待后续，用户已裁定 CI 可运行即达标）。
2. **依赖分离**：`deeplabcut` 从核心 dependencies 移到 optional extra `ai`；
   host 构建用独立 build venv（`packaging/host_requirements.txt`，与 CI 锁定集同源去掉
   测试工具），绝不安装 torch/DLC。spec 的 `excludes` 仅兜底，**判定以
   `entry_point.py --apt-smoke` 运行时断言为准**：frozen 进程不得加载
   torch/torchvision/deeplabcut（`launch_context.FORBIDDEN_HOST_ROOTS`）。
3. **frozen 运行环境解析**（`gui/launch_context.py`，组合根唯一来源）：
   - dev：runtime python = `sys.executable`，FFprobe 走 PATH——与 P6.1 之前行为完全一致；
   - frozen：FFprobe 用随包二进制（构建时 SHA-256 校验）；runtime python 按
     `AI_PHYSICS_RUNTIME_PYTHON`（测试后门）→ managed runtime 指针
     （`<AppDataLocation>/runtimes/active.txt`，P6.2 实现安装）→ `None`；
     为 `None` 时 AI 训练/推理入口显示"安装 AI 环境"占位并拒绝启动（不递归启动 GUI、
     不借用开发 venv），手工标注/分析/导出不受影响。
4. **worker 源码资源**：`src/ai_physics_tracker`（纯 `.py`，排除 `__pycache__`）作为数据
   打包进 `resources/worker-src/`；`ModelWorkerRunner`/`build_request`/`ExternalWorkerRunner`
   显式传入该 package_root（frozen 下 host 归档内的 `__file__` 不再可用于默认回推）。
5. **入口**：`packaging/entry_point.py` 负责多进程 `freeze_support` 与组合根调用；
   `__main__.py` 保持 `python -m` 兼容。windowed exe 的 stdout 不可靠，冒烟结果写
   JSON 文件（`APT_SMOKE_RESULT`）+ 退出码判定。
6. **CI**：新增 `.github/workflows/packaging.yml`（与 tests.yml 分离），双平台
   build→smoke→artifact；tests.yml 不变。

## Consequences

- 正面：macOS DMG 与 Windows zip 可从每次 push 的 CI 直接取得；host 包不含 AI 栈，
  体积与攻击面可控；dev 行为零变化（全部既有测试通过）；worker 身份校验链
  （源码 SHA/PYTHONPATH 同源）在 frozen 下语义保持。
- 代价/限制：
  - DMG/zip 未签名未公证（P6.4）：从浏览器下载的 DMG 需右键打开或
    `xattr -dr com.apple.quarantine` 去隔离；ffprobe 子进程同样受 Gatekeeper 影响。
  - Windows 无安装器（zip 解压即用）；文件关联、开始菜单、卸载器均无。
  - managed runtime 尚无安装实现（P6.2）：frozen 版 AI 功能默认不可用，只有
    env 覆盖后门可接真实 runtime 做开发验证。
  - PyInstaller 6.22.3 锁定（P0.3 已测组合）；升级需重新验证。
- 后续：P6.2 managed runtime 安装/修复；P6.3 clean-machine R01–R12；P6.4 签名、
  Inno Setup/DMG 完工与许可 material review（`packaging/NOTICE-third-party.md` 目前
  只是诚实清单，不是最终结论）。
