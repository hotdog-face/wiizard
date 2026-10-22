#!/bin/bash
# Builds the launcher (agent/) into agent/wii-agent.dol and hop (hop/) into hop/hop.dol with the devkitpro/devkitppc
# Docker image, so no local devkitPro install is needed.
#   ./build.sh                       build here (Docker Desktop / Colima)
#   BUILD_HOST=user@box ./build.sh   build on another machine with Docker (rsync + ssh), the DOLs copied back
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${IMAGE:-devkitpro/devkitppc:latest}"
if [ -z "${BUILD_HOST:-}" ]; then
    for d in agent hop; do
        (cd "$HERE/$d" && docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/src -w /src "$IMAGE" make)
    done
    ls -la "$HERE/agent/wii-agent.dol" "$HERE/hop/hop.dol"
    exit
fi
ssh -o BatchMode=yes "$BUILD_HOST" "mkdir -p wiizard-build"
for d in agent hop; do
    rsync -a --delete --exclude build --exclude '*.dol' --exclude '*.elf' "$HERE/$d/" "$BUILD_HOST:wiizard-build/$d/"
    ssh -o BatchMode=yes "$BUILD_HOST" "cd ~/wiizard-build/$d && docker run --rm -u \$(id -u):\$(id -g) -v \$PWD:/src -w /src $IMAGE make"
done
scp -q "$BUILD_HOST:wiizard-build/agent/wii-agent.dol" "$HERE/agent/wii-agent.dol"
scp -q "$BUILD_HOST:wiizard-build/hop/hop.dol" "$HERE/hop/hop.dol"
ls -la "$HERE/agent/wii-agent.dol" "$HERE/hop/hop.dol"
