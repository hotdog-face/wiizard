#!/bin/bash
# Builds the Mac simulator's Dolphin (sim/DolphinNoGUI.app): Dolphin 2609a NoGUI from the official source, native
# arm64, Metal + OpenGL (no Qt, no Vulkan), with dolphin-wiisim.patch (IOS socket port offset / bind address for
# side-by-side slots, SO_REUSEADDR, and a "perf speed=..% max=..%" stdout line every DOLPHIN_PERF_LOG seconds).
# Needs Xcode CLT + Homebrew cmake ninja pkg-config ffmpeg sdl3 (the binary links Homebrew's ffmpeg/sdl3/zstd/lz4/lzo:
# after a "brew upgrade" that bumps their major versions, rerun this). ~5 min on this Mac.
set -e
cd "$(dirname "$0")"
TAG=${1:-2609a}
[ -d dolphin-src ] || { git clone -q --depth 1 --branch "$TAG" https://github.com/dolphin-emu/dolphin.git dolphin-src
    git -C dolphin-src submodule update --init --depth 1 --jobs 8; git -C dolphin-src apply ../dolphin-wiisim.patch; }
mkdir -p dolphin-build && cd dolphin-build
cmake ../dolphin-src -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 -DENABLE_QT=OFF -DENABLE_NOGUI=ON \
  -DENABLE_VULKAN=OFF -DENABLE_TESTS=OFF -DENABLE_ANALYTICS=OFF -DENABLE_AUTOUPDATE=OFF -DUSE_DISCORD_PRESENCE=OFF \
  -DUSE_RETRO_ACHIEVEMENTS=OFF -DENABLE_LLVM=OFF -DUSE_UPNP=OFF -DUSE_MGBA=OFF -DUSE_SANITIZERS=OFF >/dev/null
ninja dolphin-nogui
cd ..
B=DolphinNoGUI.app/Contents
mkdir -p $B/MacOS $B/Resources
cp dolphin-build/Binaries/dolphin-emu-nogui $B/MacOS/
rm -rf $B/Resources/Sys && cp -R dolphin-src/Data/Sys $B/Resources/Sys
echo "built $B/MacOS/dolphin-emu-nogui"
