# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec（P6.1）：无 Torch/DLC 的 host + 受信资源。

资源布局（launch_context 约定 ``sys._MEIPASS/resources``）：
- ``resources/worker-src/ai_physics_tracker``：与本次构建同 commit 的 worker 源码
  （external runtime 经 PYTHONPATH 导入；host 哈希与子进程导入同源）；
- ``resources/ffprobe``：SHA 校验后的平台二进制；
- ``resources/LICENSE``、``resources/NOTICE-third-party.md``：许可材料。

分离红线：excludes 只兜底；真正的判定是 entry_point ``--apt-smoke`` 的
``FORBIDDEN_HOST_ROOTS`` 运行时断言（build venv 本身不装 AI 栈）。
构建脚本必须设置 ``APT_FFPROBE_DIR``（内含平台命名的 ffprobe 二进制）。
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "AI Physics Tracker"
EXECUTABLE_NAME = "AIPhysicsTracker"

ffprobe_dir = os.environ.get("APT_FFPROBE_DIR")
if not ffprobe_dir:
    raise SystemExit("APT_FFPROBE_DIR is required (run via packaging/build_*.sh|ps1)")
ffprobe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
ffprobe_path = Path(ffprobe_dir) / ffprobe_name
if not ffprobe_path.is_file():
    raise SystemExit(f"ffprobe binary missing under {ffprobe_dir}")

datas = [
    (str(REPO_ROOT / "resources" / "runtime"), "resources/runtime"),
    (str(ffprobe_path), "resources/ffprobe"),
    (str(REPO_ROOT / "LICENSE"), "resources"),
    (str(REPO_ROOT / "packaging" / "NOTICE-third-party.md"), "resources"),
]

# 第三方许可文本原件（P6.1 许可复查：NOTICE 逐项对应）
licenses_dir = REPO_ROOT / "packaging" / "licenses"
datas.append((str(licenses_dir), "resources/licenses"))

# worker 源码树：显式排除 __pycache__，保持源码纯净（host 会做字节 SHA）
for module_file in sorted((REPO_ROOT / "src" / "ai_physics_tracker").rglob("*.py")):
    relative = module_file.relative_to(REPO_ROOT / "src")
    datas.append((str(module_file), str(Path("resources/worker-src") / relative.parent)))

a = Analysis(
    [str(REPO_ROOT / "packaging" / "entry_point.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=[],
    datas=datas,
    # 不做 collect_submodules 大清单(计划明令禁止通用 hidden-import 堆砌):
    # 依赖闭包由静态分析+--apt-smoke 运行时断言把关,缺漏按冒烟错误精准补
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchvision", "deeplabcut", "matplotlib", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXECUTABLE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    bundle = BUNDLE(
        coll,
        name=APP_NAME + ".app",
        bundle_identifier="com.kyleonis.ai-physics-tracker",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",
            # 首发未签名/未公证（P6.4 处理），不注册文件关联
            "CFBundleDocumentTypes": [],
        },
    )
