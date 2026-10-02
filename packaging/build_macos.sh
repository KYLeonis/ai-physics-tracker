#!/usr/bin/env bash
# P6.1 macOS arm64 原生构建：独立 build venv → PyInstaller onedir/.app → 冒烟 → DMG。
# 不触碰共享开发 venv；产物在 dist/（已 gitignore）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="AI Physics Tracker"
VERSION="$(cd "$REPO_ROOT" && python3 -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
DIST="${APT_DIST:-$REPO_ROOT/dist}"
WORK="${APT_WORK:-$(mktemp -d /tmp/apt-p6-build-XXXXXX)}"
BUILD_ENV="$WORK/venv"
FFPROBE_DIR="$WORK/ffprobe"

echo "==> repo: $REPO_ROOT  version: $VERSION"
echo "==> build env: $BUILD_ENV"

python3.12 -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --quiet --upgrade pip
"$BUILD_ENV/bin/python" -m pip install --quiet -r "$REPO_ROOT/packaging/host_requirements.txt" "pyinstaller==6.22.3"
# host 可导入即可，依赖由 host_requirements 锁定（--no-deps 防 DLC 回流）
"$BUILD_ENV/bin/python" -m pip install --quiet --no-deps -e "$REPO_ROOT"

"$BUILD_ENV/bin/python" "$REPO_ROOT/scripts/setup_ffprobe.py" --directory "$FFPROBE_DIR"

echo "==> PyInstaller"
APT_FFPROBE_DIR="$FFPROBE_DIR" "$BUILD_ENV/bin/python" -m PyInstaller \
    --clean --noconfirm \
    --distpath "$DIST" --workpath "$WORK/pyinstaller" \
    "$REPO_ROOT/packaging/ai_physics_tracker.spec"

APP="$DIST/$APP_NAME.app"
BIN="$APP/Contents/MacOS/AIPhysicsTracker"
test -x "$BIN"

echo "==> frozen smoke (offscreen)"
SMOKE_RESULT="$WORK/smoke.json"
QT_QPA_PLATFORM=offscreen APT_SMOKE_RESULT="$SMOKE_RESULT" "$BIN" --apt-smoke
test "$(python3 -c 'import json;print(json.load(open("'"$SMOKE_RESULT"'"))["status"])')" = "ok"
echo "    smoke: $(cat "$SMOKE_RESULT")"

echo "==> DMG"
STAGING="$WORK/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
DMG="$DIST/AIPhysicsTracker-$VERSION-arm64.dmg"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
echo "==> done: $DMG"
