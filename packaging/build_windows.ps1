# P6.1 Windows x64 原生构建：独立 build venv -> PyInstaller onedir -> 冒烟 -> zip。
# 在原生 Windows（GitHub Actions windows-latest 或本机 PowerShell）执行；
# 不触碰开发环境；产物在 dist\（已 gitignore）。
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppName = "AI Physics Tracker"
$Version = (python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
$Dist = if ($env:APT_DIST) { $env:APT_DIST } else { Join-Path $RepoRoot "dist" }
$Work = if ($env:APT_WORK) { $env:APT_WORK } else { Join-Path ([System.IO.Path]::GetTempPath()) ("apt-p6-build-" + [guid]::NewGuid().ToString("N").Substring(0, 8)) }
$BuildEnv = Join-Path $Work "venv"
$FfprobeDir = Join-Path $Work "ffprobe"

Write-Host "==> repo: $RepoRoot  version: $Version"
New-Item -ItemType Directory -Force -Path $Work | Out-Null

python -m venv $BuildEnv
$Python = Join-Path $BuildEnv "Scripts\python.exe"
& $Python -m pip install --quiet --upgrade pip
& $Python -m pip install --quiet -r (Join-Path $RepoRoot "packaging\host_requirements.txt") "pyinstaller==6.22.3"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
# host 可导入即可，依赖由 host_requirements 锁定（--no-deps 防 DLC 回流）
& $Python -m pip install --quiet --no-deps -e $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "editable install failed" }

& $Python (Join-Path $RepoRoot "scripts\setup_ffprobe.py") --directory $FfprobeDir
if ($LASTEXITCODE -ne 0) { throw "ffprobe setup failed" }

Write-Host "==> PyInstaller"
$env:APT_FFPROBE_DIR = $FfprobeDir
& $Python -m PyInstaller --clean --noconfirm `
    --distpath $Dist --workpath (Join-Path $Work "pyinstaller") `
    (Join-Path $RepoRoot "packaging\ai_physics_tracker.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Bin = Join-Path $Dist "$AppName\AIPhysicsTracker.exe"
if (-not (Test-Path $Bin)) { throw "built exe missing: $Bin" }

Write-Host "==> frozen smoke (offscreen)"
$SmokeResult = Join-Path $Work "smoke.json"
$env:QT_QPA_PLATFORM = "offscreen"
$env:APT_SMOKE_RESULT = $SmokeResult
& $Bin --apt-smoke
if ($LASTEXITCODE -ne 0) { throw "smoke failed with exit $LASTEXITCODE" }
$Status = (& $Python -c "import json;print(json.load(open(r'$SmokeResult'))['status'])")
if ($Status -ne "ok") { throw "smoke status was $Status" }
Write-Host "    smoke: $Status"

Write-Host "==> zip"
$Zip = Join-Path $Dist "AIPhysicsTracker-$Version-win64.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path (Join-Path $Dist $AppName) -DestinationPath $Zip
Write-Host "==> done: $Zip"
