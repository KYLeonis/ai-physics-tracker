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
FFPROBE_DIR="${APT_FFPROBE_DIR:-$WORK/ffprobe}"   # 外部缓存可避免重复编译 ffmpeg
IDENTITY="${APT_CODESIGN_IDENTITY:-}"
NOTARY_PROFILE="${APT_NOTARY_PROFILE:-}"

# 签名不是构建的隐式回退：先检查证书，避免缺证书时耗时构建或上传。
if [ -n "$NOTARY_PROFILE" ] && [ -z "$IDENTITY" ]; then
    echo "APT_NOTARY_PROFILE requires APT_CODESIGN_IDENTITY (Developer ID Application)." >&2
    exit 1
fi
if [ -n "$IDENTITY" ]; then
    case "$IDENTITY" in
        "Developer ID Application: "*) ;;
        *) echo "Use the full Developer ID Application identity name." >&2; exit 1 ;;
    esac
    if ! security find-identity -v -p codesigning | grep -Fq "\"$IDENTITY\""; then
        echo "Developer ID identity unavailable in this Keychain." >&2
        exit 1
    fi
fi
if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]; then
    echo "Commit tracked changes before building a candidate with source provenance." >&2
    exit 1
fi

echo "==> repo: $REPO_ROOT  version: $VERSION"
echo "==> build env: $BUILD_ENV"

python3.12 -m venv "$BUILD_ENV"
"$BUILD_ENV/bin/python" -m pip install --quiet --upgrade pip
"$BUILD_ENV/bin/python" -m pip install --quiet -r "$REPO_ROOT/packaging/host_requirements.txt" "pyinstaller==6.22.3"
# host 可导入即可，依赖由 host_requirements 锁定（--no-deps 防 DLC 回流）
"$BUILD_ENV/bin/python" -m pip install --quiet --no-deps -e "$REPO_ROOT"
"$BUILD_ENV/bin/python" -m pip check

# LGPL ffprobe：源码固定版本自建（ffmpeg-static 的 macOS 二进制含 nonfree，不可再分发）
bash "$REPO_ROOT/scripts/build_ffprobe_lgpl.sh" "$FFPROBE_DIR"

echo "==> PyInstaller"
BUILD_INFO="$WORK/build-info.json"
"$BUILD_ENV/bin/python" "$REPO_ROOT/scripts/release_manifest.py" provenance --output "$BUILD_INFO"
APT_BUILD_INFO_FILE="$BUILD_INFO" APT_FFPROBE_DIR="$FFPROBE_DIR" PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1 "$BUILD_ENV/bin/python" -m PyInstaller \
    --clean --noconfirm \
    --distpath "$DIST" --workpath "$WORK/pyinstaller" \
    "$REPO_ROOT/packaging/ai_physics_tracker.spec"

APP="$DIST/$APP_NAME.app"
BIN="$APP/Contents/MacOS/AIPhysicsTracker"
test -x "$BIN"

echo "==> frozen smoke (offscreen)"
SMOKE_RESULT="$WORK/smoke.json"
QT_QPA_PLATFORM=offscreen APT_SMOKE_RESULT="$SMOKE_RESULT" APT_SMOKE_PYTHON="$BUILD_ENV/bin/python" "$BIN" --apt-smoke
test "$(python3 -c 'import json;print(json.load(open("'"$SMOKE_RESULT"'"))["status"])')" = "ok"
echo "    smoke: $(cat "$SMOKE_RESULT")"

if [ -n "$IDENTITY" ]; then
    codesign --verify --deep --strict --verbose=2 "$APP"
fi

# Keychain profile预先由用户在本机配置；不接受密码/私钥参数，不替用户购买会员。
notarize() {
    local artifact="$1" receipt="$2"
    xcrun notarytool submit "$artifact" --keychain-profile "$NOTARY_PROFILE" \
        --wait --timeout 30m --output-format json > "$receipt"
    "$BUILD_ENV/bin/python" -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r.get("status")=="Accepted" else "Notarization was not Accepted; inspect the receipt and Apple log.")' "$receipt"
}
if [ -n "$NOTARY_PROFILE" ]; then
    ditto -c -k --keepParent "$APP" "$WORK/notary-app.zip"
    notarize "$WORK/notary-app.zip" "$WORK/notary-app.json"
    xcrun stapler staple "$APP"
    xcrun stapler validate "$APP"
fi

echo "==> DMG"
STAGING="$WORK/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
DMG="$DIST/AIPhysicsTracker-$VERSION-arm64.dmg"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
if [ -n "$IDENTITY" ]; then
    codesign --force --timestamp --sign "$IDENTITY" "$DMG"
    codesign --verify --strict "$DMG"
fi
if [ -n "$NOTARY_PROFILE" ]; then
    notarize "$DMG" "$WORK/notary-dmg.json"
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
    spctl --assess --type execute --verbose=2 "$APP"
    spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
fi
MANIFEST_ARGS=()
if [ -n "$NOTARY_PROFILE" ]; then
    MANIFEST_ARGS=(--notary-app "$WORK/notary-app.json" --notary-dmg "$WORK/notary-dmg.json")
fi
"$BUILD_ENV/bin/python" "$REPO_ROOT/scripts/release_manifest.py" candidate \
    --app "$APP" --dmg "$DMG" --smoke "$SMOKE_RESULT" \
    --output "$DIST/release-manifest.json" "${MANIFEST_ARGS[@]}"
echo "==> done: $DMG"
