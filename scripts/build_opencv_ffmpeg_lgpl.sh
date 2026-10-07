#!/usr/bin/env bash
# 为固定 Mac OpenCV wheels 构建同 major ABI 的 LGPL FFmpeg 动态库。
set -euo pipefail
DEST="${1:?usage: build_opencv_ffmpeg_lgpl.sh <output-dir>}"
DEST="$(mkdir -p "$DEST" && cd "$DEST" && pwd)"
SHA="733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1"
URL="https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz"
SOURCE="$DEST/ffmpeg-7.1.1.tar.xz"
if [ ! -f "$SOURCE" ]; then curl --fail -L --retry 5 -o "$SOURCE" "$URL"; fi
echo "$SHA  $SOURCE" | shasum -a 256 -c -
# 只缓存验证过的源码包；每次干净编译，不能把新源码 SHA 绑定旧缓存二进制。
WORK="$(mktemp -d "$DEST/compile-XXXXXX")"
tar -xf "$SOURCE" -C "$WORK"
cd "$WORK/ffmpeg-7.1.1"
    # 不自动发现 Homebrew 编解码器，避免 GPL 闭包重新进入产物。
    MACOSX_DEPLOYMENT_TARGET=14.0 ./configure \
        --prefix="$WORK/prefix" --enable-shared --disable-static \
        --disable-gpl --disable-nonfree --disable-version3 --disable-autodetect \
        --disable-programs --disable-doc --disable-network --disable-iconv \
        --disable-avfilter --disable-postproc --disable-indevs --disable-outdevs \
        --extra-cflags=-mmacosx-version-min=14.0 \
        --extra-ldflags=-mmacosx-version-min=14.0 > "$WORK/configure.log"
grep -q 'License: LGPL version 2.1 or later' "$WORK/configure.log"
make -j"${APT_BUILD_JOBS:-8}" > "$WORK/make.log" 2>&1
make install > "$WORK/install.log" 2>&1
for library in avcodec avformat avutil swscale swresample avdevice; do
    test -f "$WORK/prefix/lib/lib${library}.dylib"
done
cp "$WORK/configure.log" "$DEST/configure.log"
printf '%s\n' "$WORK/prefix" > "$DEST/prefix-path.txt"
echo "==> LGPL OpenCV FFmpeg built at $WORK/prefix/lib"
