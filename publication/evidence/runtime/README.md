# P0.3 Feasibility Evidence

2026-09-20；本目录记录spike证据，不是首发runtime认证。合同：[runtime-boundary](../../spec/runtime-boundary.md)。

## Environment inventory

Host：Mac arm64。EJP无.venv；system Python3.14不属于产品支持范围。外置worker复用主仓库已有Python3.12.13 venv，DLC3.0.1、torch2.13.0、torchvision0.28.0；PySide6 6.11.2、OpenCV4.11.0.86、NumPy1.26.4、SciPy1.17.1、Pandas2.3.3。仅作为本机已测试组合，不直接宣称Windows同版本可安装或全DLC功能兼容。

独立临时build venv安装PyInstaller6.22.3（hooks2026.7），只冻结stdlib host，没有打包DLC/PyTorch，也没有改变现有worker环境或pyproject依赖。构建日志、完整runtime产物留在`/tmp/ejp-p03-*`；本目录保存[results.json](results.json)、[小型日志](transcripts/)和摘要，不提交模型/视频/venv/二进制。

## Gate matrix（最终以results.json为准）

| Gate | Mac arm64 | Win x64 | 边界 |
| --- | --- | --- | --- |
| G1 frozen host→external Python | PASS（最终v3冻结版本） | not_run | source-host tests不替代frozen证据 |
| G2 CPU tensor+DLC import | 已实测 | not_run | 不是DLC train/infer |
| G3 existing 1-epoch CPU DLC train/infer/save-reopen | PASS（最终v3冻结版本） | not_run | 10帧/5manual、单bodypart；不是P1四点功能或精度证明 |
| G4 cooperative/forced tree cancel/error logs | PASS（最终v3冻结版本） | not_run | Windows taskkill必须原生验证 |
| CUDA | unavailable（本机无CUDA） | not_run | 不能由Mac推断 |
| MPS | PASS tensor forward/backward，actual mps:0 | not_run | 未承诺DLC MPS完整训练 |
| G5 clean-machine first-run installation/repair | not_run | not_run | P6完整发行门禁；现有venv复用不能冒充clean install |

初次真实DLC调用已训练并推理10帧，但旧smoke脚本的`import_summary.inserted`断言过期而失败。修正脚本为验证candidate不自动生效→显式Activate→5manual保留/5AI生效后重跑成功。初次失败及最终成功日志均入库；未改产品src或降低科学验收。

最终8个场景结果均符合预期：hello/CPU/MPS/DLC成功，协作/强制取消及DLC启动期取消为cancelled，故意错误为failed且traceback保留。强制取消的测试子PID复核已不存在。DLC取消发生在启动/import阶段，不宣称已验证训练epoch中或GPU kernel中的取消。20项contract tests通过；source hashes与binary hash见results.json。Windows G1–G4仍not_run；2026-09-20用户明确批准延期，作为进入P6前必须完成的门禁，P0据此收尾。

## Reproduce on macOS

从repo根使用Python3.12独立构建环境：

```sh
python3.12 -m venv /tmp/ejp-p03-build-env
/tmp/ejp-p03-build-env/bin/python -m pip install pyinstaller==6.22.3
/tmp/ejp-p03-build-env/bin/python -m PyInstaller --clean --onedir --name ejp-runtime-host --distpath /tmp/ejp-p03-dist --workpath /tmp/ejp-p03-work --specpath /tmp/ejp-p03-work scripts/publication_runtime_spike/host.py
```

运行（--output必须不存在；替换外置Python路径）：

```sh
/tmp/ejp-p03-dist/ejp-runtime-host/ejp-runtime-host --python /path/to/runtime/bin/python --worker "$PWD/scripts/publication_runtime_spike/worker.py" --output /tmp/ejp-hello-new --operation hello
/tmp/ejp-p03-dist/ejp-runtime-host/ejp-runtime-host --python /path/to/runtime/bin/python --worker "$PWD/scripts/publication_runtime_spike/worker.py" --output /tmp/ejp-selftest-new --operation selftest --device cpu --timeout 60
/tmp/ejp-p03-dist/ejp-runtime-host/ejp-runtime-host --python /path/to/runtime/bin/python --worker "$PWD/scripts/publication_runtime_spike/worker.py" --repo "$PWD" --output /tmp/ejp-dlc-new --operation dlc_smoke --timeout 660
```

取消：`--operation wait --cancel-after 0.3`与`--operation stubborn --cancel-after 1`（后者启动固定sleep子进程验证tree kill）；错误：`--operation fail`预期退出1、failed及traceback；真实DLC取消可对dlc_smoke加cancel-after并记录取消时所处实际阶段。所有命令返回host-result.json、request.json、worker.log；协作worker另有result.json。没有用截图或mock替代科学结果。

## Windows handoff（用户批准延期，进入P6前必须完成）

在原生Windows x64 checkout本分支，已有DLC Python环境记为`$RuntimePython`；build环境与AI环境分开。以下PowerShell只构建探针，不安装完整产品：

```powershell
$ProbeBuild = Join-Path $env:TEMP ("ejp-p03-build-" + [guid]::NewGuid())
py -3.12 -m venv $ProbeBuild
& "$ProbeBuild\Scripts\python.exe" -m pip install pyinstaller==6.22.3
& "$ProbeBuild\Scripts\python.exe" -m PyInstaller --clean --onedir --name ejp-runtime-host --distpath "$ProbeBuild\dist" --workpath "$ProbeBuild\work" --specpath $ProbeBuild scripts/publication_runtime_spike/host.py
$RuntimePython = 'C:\path\to\dlc-runtime\Scripts\python.exe'
$HostProbe = "$ProbeBuild\dist\ejp-runtime-host\ejp-runtime-host.exe"
$WorkerProbe = Join-Path $PWD 'scripts\publication_runtime_spike\worker.py'
& $HostProbe --python $RuntimePython --worker $WorkerProbe --output "$ProbeBuild\hello" --operation hello
& $HostProbe --python $RuntimePython --worker $WorkerProbe --output "$ProbeBuild\selftest-cpu" --operation selftest --device cpu --timeout 60
& $HostProbe --python $RuntimePython --worker $WorkerProbe --repo $PWD --output "$ProbeBuild\dlc-cpu" --operation dlc_smoke --timeout 660
& $HostProbe --python $RuntimePython --worker $WorkerProbe --output "$ProbeBuild\cancel" --operation stubborn --cancel-after 1
& $HostProbe --python $RuntimePython --worker $WorkerProbe --output "$ProbeBuild\fail" --operation fail
```

有NVIDIA环境再单独selftest device=cuda；回传每个job的host-result.json、worker.log及实际版本，强制取消后验证子PID不再运行。`fail`场景退出1是预期，不可把其他场景失败忽略。没有兼容DLC环境时先报告缺项，不用Mock代替。repo现有Windows CI仅运行无DLC测试，不能算上述通过。
