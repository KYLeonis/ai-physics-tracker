#!/usr/bin/env bash
# 构建可再分发的最小 LGPL ffprobe（P6.1 许可复查后替换 ffmpeg-static 预编译）。
#
# 原因：ffmpeg-static 的 macOS arm64 二进制为 --enable-gpl --enable-nonfree 构建，
# 按 FFmpeg 官方许可政策 nonfree 构建不可再分发。本脚本从固定版本+SHA 的官方
# 源码自建 --disable-gpl --disable-nonfree 的最小 ffprobe（configure 输出
# License: LGPL version 2.1 or later），只启用时序探测所需组件。
set -euo pipefail

FFMPEG_VERSION="7.1.1"
FFMPEG_SHA256="733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1"
FFMPEG_URL="https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"

DEST="${1:?usage: build_ffprobe_lgpl.sh <output-dir>}"
WORK="${APT_FFMPEG_WORK:-$(mktemp -d /tmp/apt-ffprobe-build-XXXXXX)}"
MARKER="$DEST/ffprobe.built-sha"

mkdir -p "$DEST"
if [ -f "$DEST/ffprobe" ] && [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$FFMPEG_SHA256" ]; then
    echo "==> cached LGPL ffprobe at $DEST/ffprobe"
    exit 0
fi

TARBALL="$WORK/ffmpeg-${FFMPEG_VERSION}.tar.xz"
if [ ! -f "$TARBALL" ]; then
    curl -sL --retry 5 -C - -o "$TARBALL" "$FFMPEG_URL"
fi
echo "$FFMPEG_SHA256  $TARBALL" | shasum -a 256 -c -

SRC="$WORK/ffmpeg-${FFMPEG_VERSION}"
if [ ! -d "$SRC" ]; then
    tar -xf "$TARBALL" -C "$WORK"
fi

cd "$SRC"
./configure \
    --disable-gpl --disable-nonfree --disable-version3 \
    --disable-everything --disable-autodetect --disable-doc --disable-network \
    --disable-iconv --disable-ffmpeg --disable-ffplay \
    --disable-avdevice --disable-swresample --disable-swscale --disable-avfilter \
    --enable-protocol=file \
    --enable-demuxer=mov,avi,matroska,h264,mjpeg \
    --enable-parser=h264,hevc,mpeg4video,mjpeg \
    --enable-decoder=h264,hevc,mpeg4,mjpeg,ffv1 \
    --prefix="$WORK/prefix" > "$WORK/configure.log"
if ! grep -q "LGPL version 2.1 or later" "$WORK/configure.log"; then
    echo "configure did not report LGPL-2.1+; refusing to ship" >&2
    exit 1
fi
make -j"$(sysctl -n hw.ncpu 2>/dev/null || echo 4)" ffprobe > "$WORK/make.log"
./ffprobe -version | head -1

cp "$SRC/ffprobe" "$DEST/ffprobe"
chmod +x "$DEST/ffprobe"
echo "$FFMPEG_SHA256" > "$MARKER"
echo "==> LGPL ffprobe installed: $DEST/ffprobe"
