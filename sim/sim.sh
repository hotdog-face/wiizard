#!/bin/bash
# The Wii simulator: the launcher in Dolphin (headless, OpenGL on Mesa, frame copies to RAM so SHOT works) in a
# container on a Linux box (WII_SIM_HOST, ~/wii-sim; image wii-sim). Its agent answers at $WII_SIM_IP:4300 like a real cabinet,
# so wiiagent.py / the wii MCP tools work against it (PAD presses, SHOT, LOG). Runs at ~1/5 speed: fine for screens.
#   sim/sim.sh start [launcher.dol]   copy the SD stand-in (sim/build_sd.py) + launcher there and (re)start
#   sim/sim.sh shot out.png           screenshot
#   sim/sim.sh stop
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${WII_SIM_HOST:?set WII_SIM_HOST (ssh host running the simulator)}"
SIM_IP="${WII_SIM_IP:?set WII_SIM_IP}"
case "$1" in
start)
    DOL="${2:-$HERE/../agent/wii-agent.dol}"
    rsync -a --delete "$HERE/sd/" "$HOST:wii-sim/sd/"
    scp -q "$DOL" "$HOST:wii-sim/wii-agent.dol"
    ssh -o BatchMode=yes $HOST 'cd ~/wii-sim && rm -f user/Load/WiiSD.raw; docker rm -f wii-sim >/dev/null 2>&1; docker run -d --name wii-sim --network host --shm-size=1g -u "$(id -u):$(id -g)" -e HOME=/sim -v "$PWD":/sim wii-sim /usr/games/dolphin-emu-nogui -p headless -u /sim/user -v OGL -e /sim/wii-agent.dol >/dev/null'
    for i in $(seq 1 40); do
        python3 -c "import sys; sys.path.insert(0, '$HERE/..'); import wiiagent; r = wiiagent.probe('$SIM_IP', 2); sys.exit(0 if r and r.startswith('OK') else 1)" && { echo "simulator up"; exit 0; }
        sleep 3
    done
    echo "simulator did not answer"; exit 1 ;;
shot)
    python3 -c "import sys; sys.path.insert(0, '$HERE/..'); import wiiagent
with wiiagent.Agent('$SIM_IP', timeout=60) as a: a.screenshot().save('${2:-/tmp/sim.png}')" ;;
stop)
    ssh -o BatchMode=yes $HOST 'docker rm -f wii-sim >/dev/null 2>&1' ;;
esac
