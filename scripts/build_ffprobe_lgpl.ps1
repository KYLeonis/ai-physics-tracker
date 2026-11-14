# 构建侧获取可再分发的 LGPL ffprobe.exe（P6.1 许可复查后替换 ffmpeg-static 预编译）。
#
# 原因：ffmpeg-static 的 Windows 二进制取自 gyan.dev，该站全部构建现为 GPLv3，
# 且我们无法提供其精确构建配置作为 corresponding source。本脚本改用 BtbN
# FFmpeg-Builds 的版本化 win64-lgpl 包（LGPL-3.0+，GitHub 发布 SHA-256），
# 只提取 bin\ffprobe.exe。
$ErrorActionPreference = "Stop"

# 固定月末保留包：上游日常包只保留14天，月末最后一包保留两年。
# https://github.com/FFmpeg-Builds/FFmpeg-Builds#release-retention-policy
# 更新时选择月末版本并复核 GitHub asset digest；不使用浮动 latest。
$Tag = "autobuild-2026-10-31-12-59"
$Asset = "ffmpeg-n8.1.3-27-g8dca1586f4-win64-lgpl-8.1.zip"
$Sha256 = "d4c2a42673917b4a97104a3e9f082729a9730796b98664e37c0b7eba6c6c613d"
$Url = "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/$Tag/$Asset"

$Dest = if ($args[0]) { $args[0] } else { throw "usage: build_ffprobe_lgpl.ps1 <output-dir>" }
$Marker = Join-Path $Dest "ffprobe.built-sha"

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
if ((Test-Path (Join-Path $Dest "ffprobe.exe")) -and (Test-Path $Marker) -and ((Get-Content $Marker) -eq $Sha256)) {
    Write-Host "==> cached LGPL ffprobe at $Dest\ffprobe.exe"
    exit 0
}

$Work = Join-Path ([System.IO.Path]::GetTempPath()) ("apt-ffprobe-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$Zip = Join-Path $Work $Asset
Invoke-WebRequest -Uri $Url -OutFile $Zip
$Actual = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLower()
if ($Actual -ne $Sha256) { throw "SHA-256 mismatch: expected $Sha256, got $Actual" }

Expand-Archive -Path $Zip -DestinationPath $Work
$Probe = Get-ChildItem -Path $Work -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
if (-not $Probe) { throw "ffprobe.exe not found in archive" }
& $Probe.FullName -version | Select-Object -First 1

Copy-Item $Probe.FullName (Join-Path $Dest "ffprobe.exe") -Force
Set-Content -Path $Marker -Value $Sha256
Write-Host "==> LGPL ffprobe installed: $Dest\ffprobe.exe"
