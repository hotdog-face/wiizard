#!/bin/bash
# The Wii simulator on THIS Mac (same interface as sim.sh, which drives the slow one on the Linux build box): the launcher in
# Dolphin 2609a NoGUI (native arm64, Metal, headless: no window, no sound) with mac-cards/slot0.raw as its SD card.
# Its agent answers at 127.0.0.1:4300 (loopback only; --lan to expose it), so wiiagent.py / the wii MCP tools work against it.
#   sim/mac_sim.sh start [launcher.dol] [--fresh] [--fast]   (re)start slot 0 (--fresh: re-clone the card from master.raw)
#   sim/mac_sim.sh shot out.png                              screenshot (the launcher's SHOT, never the Mac's screen)
#   sim/mac_sim.sh perf                                      emulation speed (100% = real Wii)
#   sim/mac_sim.sh stop
# More (other slots, frame/audio dumps, RetroArch log): sim/macsim.py --help, sim/mac_atest.py, sim/mac_vrun.py.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
A="$1"; shift || true
case "$A" in
start)
    DOL=""; [ -n "$1" ] && [ "${1#--}" = "$1" ] && { DOL="--dol $1"; shift; }
    exec python3 "$HERE/macsim.py" start -s 0 $DOL "$@" ;;
shot) exec python3 "$HERE/macsim.py" shot "${1:-/tmp/sim.png}" -s 0 ;;
perf|stop|status|ralog) exec python3 "$HERE/macsim.py" "$A" -s 0 ;;
*) sed -n 2,10p "$0"; exit 1 ;;
esac
