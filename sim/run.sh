#!/bin/bash
# Superseded: the first attempt to run the GUI Dolphin.app here failed with "Failed to init core" because Dolphin 2609a
# rejects our launcher DOL (its last section isn't padded to 32 bytes). Use sim/mac_sim.sh (headless, pads the DOL).
exec "$(dirname "$0")/mac_sim.sh" start "$@"
