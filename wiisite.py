"""Your own network's settings: none of them live in the repo.
Each one comes from an environment variable (WII_<NAME>) or from wiisite.json next to this file (copy
wiisite.example.json). Anything left empty switches the feature that needs it off (or the script says what's missing)."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
try:
    with open(os.path.join(_HERE, "wiisite.json")) as _f:
        _CFG = json.load(_f)
except FileNotFoundError:
    _CFG = {}


def get(name, default=""):
    return os.environ.get("WII_" + name.upper(), _CFG.get(name, default))


SUBNET = get("subnet", "192.168.0")        # the /24 the Wiis get DHCP leases on: `status` scans <SUBNET>.1-254
UPDATE_SERVER = get("update_server")       # host:port the cabinets pull updates from (publish.py serves dist/ there)
PUBLISH_HOST = get("publish_host")         # ssh host that runs the update server (python3 -m http.server)
PUBLISH_ROOT = get("publish_root", "wii-fleet/dist")   # its dist folder, relative to that host's home
COLLECTOR = get("collector")               # ssh host running `fleet.py collect` from cron
NAS = get("nas")                           # user@host of the NAS holding the game library and card backups (ssh)
NAS_WII = get("nas_wii")                   # the NAS folder with the Wii WBFS files
NAS_BACKUP = get("nas_backup")             # the master card's backup on the NAS (Priiloader files, games)
SIM_HOST = get("sim_host")                 # ssh host running the Docker Dolphin simulator (sim/sim.sh)
SIM_IP = get("sim_ip")                     # that simulator's address (fleet.py skips it when scanning)
USBLGX_PASSWORD = get("usblgx_password")   # USB Loader GX's parental-lock password written to the card (empty: no lock)
