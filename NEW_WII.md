# New Wii -> garage cabinet

The checklist for turning a softmodded Wii into a cabinet like cab1, with as little of the owner's time as possible.
Based on what was done for cab1 (2026-10-14..16), README.md, `wii_mcp.py`, and a full dry run of a new 128 GB card
onto a disk image (2026-10-16). Steps marked **OWNER** need hands on the console. Everything else the agent does
from the Mac. NAND writes (step 12) need **the owner's explicit OK for each console**, every time.

## What a cabinet needs

| Item | Notes |
| --- | --- |
| Original Wii (RVL-001, GameCube ports) | Any region. GameCube pads in the ports. Component or composite to the CRT. |
| Homebrew Channel (HBC) | Required: the fallback when the launcher is broken, and how the agent gets in the first time. |
| Priiloader | Required: power-on goes Priiloader -> hop (NAND) -> launcher (SD). The card has the 0.9.1 installer in `apps/priiloader`. |
| BootMii backup | Strongly recommended before any NAND write (`nand.bin` + `keys.bin`; on cab1 they live on the SD card). |
| cIOS | **Not required** for GameCube (Nintendont) or arcade/console games (RetroArch). Only Wii discs need cIOS 249 (d2x). Install it remotely with the cios/ tools (README: cIOS 249): nandgrab.py -> build_cios.py <nand> <release> 56 249 <out> -> sdput.py -> install_cios.py. cab1 has d2x v11-beta3 base 56 since 2026-10-21. |
| Wi-Fi | The Wii's own connection settings (System Menu). The agent can't write those. |
| SD card | SanDisk Ultra 128 GB (119 GiB usable), FAT32, **32 KB clusters**. Built on the Mac (step 1); the installer refuses a card that isn't FAT32, has other clusters, or lacks the space. |
| TV settings | **480i, 60 Hz, 4:3** (480p = no picture on a 15 kHz CRT; 50 Hz rolls; 16:9 squashes). Checked by `new_wii.py check`, set by `new_wii.py apply` (SYSCONF IPL.PGS / IPL.E60 / IPL.AR), step 12; nobody opens Wii Settings -> Screen. |
| Wii Remote | Only for the one-time owner steps in part B (the Wii Menu needs one). Not needed afterwards. |

## Time

| Part | Who | Time |
| --- | --- | --- |
| Card, installer from the NAS | agent | dry run: **39 min** for 98 GiB (~43 MB/s from the NAS); on a real card expect 40-60 min (SanDisk Ultra writes ~30-60 MB/s). A re-run on a finished card: ~11 s (it CRC-checks every published file) |
| Card, clone of the prepared image | agent | about the same per card (the card's write speed is the limit), but no NAS/Wi-Fi in the loop and two card readers can run at once |
| Owner, at the console | **OWNER** | 5-10 min per Wii (most of it typing the Wi-Fi password once) |
| Remote setup, NAND writes, checks | agent | 10-15 min per Wii |
| CRT calibration | agent + owner says what's cut off | 2-5 min |

## A. The card (on the Mac)

1. **Format** (agent; only a new, empty card, after checking it is the right disk with `diskutil list` -
   "external, physical", about 127.9 GB, SD reader):

       diskutil eraseDisk FAT32 WIISD MBRFormat /dev/diskN
       mdutil -i off /Volumes/WIISD          # no Spotlight index on the card

   Checked on the dry run: on a 127.9 GB card this gives FAT32 with 32768-byte clusters, what Nintendont wants.
   The installer checks this itself before writing anything (`diskutil info`): the path must be the card volume's
   own mount point (nothing is ever created on another volume, not even `apps/`), FAT32, 32 KB clusters
   (`--any-cluster-size` to accept others), and enough free space for what that run copies. Only the check:
   `python3 sdkit_install.py /Volumes/WIISD --games /tmp/master-games.tsv --check-only` (~15 s, asks the NAS for sizes).

2. **Fill it.** Pick one. Fastest in practice: one card at a time -> the installer (one command, nothing to keep
   in sync); several cards at once -> clone the image to each in parallel (one SD reader per card).

   - **Installer (always the newest of everything; needs the NAS):**

         cd wiizard
         scp <collector>:wii-fleet/cabs/<master console id>/games.tsv /tmp/master-games.tsv   # the live cab1 list
         python3 sdkit_install.py /Volumes/WIISD --games /tmp/master-games.tsv

     `fleet/cabs/<console id>/games.tsv` on the Mac is only refreshed by the 9 pm report; the collector's copy is the
     live one (refreshed every 15 min while cab1 is on). The installer can be re-run any time: it skips what's there,
     resumes half-done copies, and removes the macOS `._*` files it caused.

     What it installs: every file publish.py published (`dist/manifest.txt`, copied from `dist/files`: launcher,
     hop, Nintendont, USB Loader GX, RetroArch cores/config/overrides, clips, art, metadata, console ROMs), so a new
     card runs exactly what the fleet runs. Something new in the working tree (a launcher build, new clips) reaches
     the card only after `publish.py`, or with `--working-tree` (installs the working tree instead; not what the
     fleet runs). Not from dist: arcade ROMs and discs (NAS), the Priiloader installer, salamander, the
     `hiscore.dat` lists (FB Alpha 2012: `retroarch/system/fbalpha2012/` and `retroarch/savefiles/FB Alpha 2012/`;
     MAME 2000: `roms/arcade/hiscore.dat`, it looks in the ROM folder). Nothing hidden in `sdkit/hidden.txt` is
     copied (by disc id, path rule or ROM name: the 3 Wii discs, 10.7 GiB, the Japanese-menu GameCube discs, ...).
     GameCube: disc 1 as `game.ciso`, disc 2 as `disc2.ciso` in the same folder (Nintendont swaps to it when the game
     asks; Resident Evil, Code Veronica, RE4, RE Zero, MGS The Twin Snakes), never a hack build where the retail disc
     exists (Melee is the USA disc, not 20XX). A disc already on the card under one of these ids is checked against
     the NAS image and replaced if it is the wrong disc/build.

   - **Clone the prepared image (the NAS is only asked for a few file sizes; good for several cards at once):**
     the dry-run image `~/wii-cards/wiisd-128-dryrun.sparseimage` is a complete card (topped up 2026-10-17 with the
     published state, see the end). Bring it up to date, then copy it file by file onto each formatted card (file
     copy, not `dd`: no `sudo`, and card sizes differ slightly between batches). It still holds discs hidden since
     it was made (the 3 Wii discs, the Japanese-menu GameCube discs): the `rsync` below leaves `wbfs/` out; the
     hidden GameCube folders (~6 GiB) come along, invisible in the menu. Check the Mac's free space first: the
     image grows by whatever the top-up writes (`--check-only` says how much).

         hdiutil attach ~/wii-cards/wiisd-128-dryrun.sparseimage            # -> /Volumes/WIISD
         python3 sdkit_install.py /Volumes/WIISD --games /tmp/master-games.tsv  # top-up, seconds to minutes
         diskutil eraseDisk FAT32 WIISD2 MBRFormat /dev/diskN               # the new card, as WIISD2
         rsync -rt --exclude '._*' --exclude '.Spotlight-V100' --exclude '.fseventsd' --exclude 'wbfs/' /Volumes/WIISD/ /Volumes/WIISD2/
         python3 sdkit_install.py /Volumes/WIISD2 --games /tmp/master-games.tsv   # checks it, removes ._ files, installed.tsv
         hdiutil detach /Volumes/WIISD

     The label doesn't matter to the Wii. Don't let Finder copy it (it adds `._*` files and a `.Trashes`).

3. **Check the card** before ejecting (agent): the last lines of the installer say `installed.tsv: N of the
   published files are on the card as published` (N = the line count of `dist/manifest.txt`, 1769 on 2026-10-17),
   no `WARNING: ... don't match dist/manifest.txt` (that means a publish was running: re-run), and
   `done; NN GiB free on the card`. Full check (1 min):
   a verify script (not in this repo) (manifest sizes/CRCs, boot chain files,
   every listed game, clips/art, no `._*`). Then `diskutil eject /Volumes/WIISD`.

What's on a new card: `apps/wii-agent/boot.dol` (the launcher/agent), `hop.dol` (the copy for Priiloader's NAND
slot), `meta.xml`; `apps/nintendont` (our build), `apps/usbloader_gx` (r1283 + r1272, settings locked),
`apps/retroarch-wii` (salamander, 8 cores, retroarch.cfg), `apps/priiloader` (installer), `retroarch/` (core
options, hiscore.dat, overrides, bezels), `roms/` (arcade sets + console ROMs; `roms/arcade/hiscore.dat` for MAME
2000), `games/<Title [ID]>/game.ciso` (+ `disc2.ciso` for two-disc games), `wbfs/<Title [ID]>/<ID>.wbfs` (none
while the Wii discs are hidden), `arcade/` (arcade.tsv, meta, hidden, collections, hiscores, fonts incl. term.ttf,
clips, sounds, art, sfx, `cabs/*.cfg`, `update.cfg`, `installed.tsv`). No `nand.bin` (that's per console).

## B. At the console (OWNER, once per Wii)

Do these with the Wii on its CRT, a Wii Remote synced, and the new card in the SD slot.

> **ACTION NEEDED** (one time per new Wii, ~5-10 min)
> B1. With the Wii off, put the new SD card in the front slot (label up). Plug in the GameCube pad(s).
> B2. Power on. If the Wii Menu appears, go on to B3. (If the arcade launcher already appears, skip to the end: the
>    Wii already has Priiloader set up.) **No picture, or a rolling/flickering one?** This Wii is set to 480p or
>    50 Hz, which the CRT can't show. Don't change it in Wii Settings: do B3-B4 on the cable's yellow composite plug
>    (always 480i) or on any flat TV; Claude switches the Wii to 480i / 60 Hz / 4:3 remotely in step 12.
> B3. **Wi-Fi:** Wii Menu -> Wii button (bottom left) -> Wii Settings -> page 2 -> Internet -> Connection Settings ->
>    an empty Connection -> Wireless Connection -> Search for an Access Point -> pick the garage Wi-Fi -> type the
>    password -> Save -> OK. It runs a connection test. **If it asks to do a system update, choose "No" / "Cancel"**
>    (a system update can break the softmod). You should see "The connection test was successful".
> B4. Back to the Wii Menu -> Homebrew Channel -> Start -> pick **wii-agent** -> Load. The green WIIZARD terminal
>    intro plays, then the arcade menu. Tell Claude "it's on". (If Claude asks for it instead: just leave the HBC
>    screen up; the agent can push the launcher over Wi-Fi, but HBC's Wi-Fi is the flaky part.)
> B5. *Only if Claude says Priiloader is missing:* in the HBC, pick **Priiloader** -> Load -> press (+) on the Wii
>    Remote (or A on a GameCube pad) to install -> wait until it says it's done -> it returns to the HBC.
> B6. *Only if Claude says Priiloader has no boot file (main.bin):* turn the Wii off; hold RESET while pressing
>    POWER until the Priiloader menu shows -> **Load/Install File** -> highlight **wii-agent** -> press A to
>    *install* it (if it offers Load or Install, pick Install) -> back -> **System Menu**. Then do B4 again. (This only
>    creates the file; Claude then swaps it for the small start-up program and sets autoboot remotely, step 12.)
>
> That's all. From here the Wii is driven from the Mac; the Wii Remote can go back in the drawer.

## C. Remote setup (agent, from the Mac)

7. `status` - the new Wii shows with its launcher version and console id at its DHCP address and is recorded in
   `devices.json` (or as "Homebrew Channel (wiiload)": then `start_agent wii=<ip>` pushes the launcher; retry, HBC's
   Wi-Fi is flaky). `start_agent` also brings an older launcher up to the current build in place.
8. `screenshot` - the launcher's attract mode (or the WIIZARD terminal intro the first time).
9. `python3 new_wii.py <ip> check` (read-only): Priiloader present and its autoboot, what main.bin holds and its
   size, main.nfo byte 0, AHBPROT, the card's hop.dol / update.cfg / cab cfg, and the **TV settings** (what the
   owner would otherwise set in Wii Settings -> Screen): TV Resolution 480i = SYSCONF IPL.PGS = 0 (not EDTV/HDTV
   480p) and IPL.E60 = 1 (60 Hz, not 50 Hz 576i; only PAL Wiis have the item, NTSC is always 60 Hz); Widescreen
   Setting Standard (4:3) = IPL.AR = 0; and the running video mode from INFO (`tv=`, `fb=640x480`; 574 lines =
   50 Hz). It says what's TODO; apply (step 12) fixes all three.
   - Priiloader missing -> owner step B5. main.bin missing or smaller than hop.dol (310,864 bytes) -> owner step B6
     (the agent can only overwrite NAND files in place, never create or grow them). Installing the 3.6 MB launcher
     there through Priiloader makes a main.bin big enough; apply then overwrites it with hop (310 KB).
10. **NAND backup** before any write. If the Wii came with an SD card, it probably holds the BootMii backup
    (`nand.bin` + `keys.bin`, as cab1's did): keep that old card, and copy it to the NAS
    (`sd_backup.py /Volumes/<old card> <NAS folder>/Wii-Backups/<name>`). If there is none, making one
    needs BootMii and the console's buttons (owner: HBC -> BootMii -> Backup, ~10 min) - ask the owner whether they
    want it before the NAND writes (the four files are also backed up individually by step 12).
11. Name it: `python3 new_wii.py <ip> cab cab2` writes `sdkit/cabs/<console id>.cfg` (name + default.cfg's
    screen, idle_off_minutes 45, all collections), puts it on the card, and adds it to `devices.json`
    (`rename` does the devices.json part alone). Every later card gets it too (sdkit_install copies sdkit/cabs).
12. **NAND writes - ask the owner first, per console** ("OK to write Priiloader's boot program, its AHBPROT flag, the
    autoboot setting and the screen settings (480i, 60 Hz, 4:3) on cab2's NAND? Backups are taken first."). With a
    clear yes:

        python3 new_wii.py <ip> apply --yes

    It backs up the four files to `backups/<console id>-*.<time>`, tests hop from the card first (EXEC
    `sd:/apps/wii-agent/hop.dol` must bring the launcher back with autobooted=1; nothing is written otherwise),
    then writes and reads back each one:
    - Priiloader `data/main.bin` = `hop/hop.dol` (in place; the old program stays in the backup),
    - `data/main.nfo` byte 0 = 1 (Priiloader starts main.bin with AHBPROT off: Nintendont and USB Loader GX need it),
    - `data/loader.ini` byte 0 = 4 (autoboot = installed file),
    - `/shared2/sys/SYSCONF`, one write for the screen: IPL.AR = 0 (4:3; RetroArch and the menus take the screen
      shape from it), IPL.PGS = 0 (480i: the launcher, RetroArch and the Wii Menu pick 480p from it on a component
      cable, and the CRT shows nothing), IPL.E60 = 1 (60 Hz, if the console has the item; a PAL Wii without it is
      refused); only the bytes that differ change, the file keeps its size,
    then Wii Menu -> Priiloader -> hop -> launcher (the new screen settings take effect there), and re-runs the
    check: it wants `ahbprot=1 autobooted=1` and `fb=640x480`. (Nintendont never sets progressive itself.)
    (These are the only NAND files the agent can write: ALLOWED_NAND_WRITES in agent/source/main.c.)
13. Power-on test without the owner: `power reboot` -> the launcher must come back by itself in ~20 s with
    `autobooted=1` (`status`). The WIIZARD intro plays on every power-on.
14. CRT calibration: `screen` (shows a white edge frame for 20 s; ask the owner which edges are cut off, adjust,
    repeat). Saved to the card's `arcade/cabs/<id>.cfg`; the 9 pm report copies it into `sdkit/cabs`.
15. Fleet: nothing to register. The collector's cron (`fleet.py collect`, every 15 min) finds every launcher on the
    LAN by itself, and the 9 pm report includes it. Pull updates work from the first idle minute
    (`arcade/update.cfg` -> the update server; `installed.tsv` already lists what the card has, so it only fetches
    what was published after the card was made). Check after ~15 min: `ssh <collector> tail ~/wii-fleet/collect.log`
    shows the new console id.
16. Optional game check: `play` one arcade game, one GameCube game; `game action=quit` for arcade. GameCube exits
    with L + R + Z + START on the pad (owner, or wait for the 40 s autotest via the launcher's PLAYTEST).

## If something goes wrong

- Launcher fails 2 starts in a row -> hop starts `boot-good.dol`; 5 -> the Homebrew Channel (the agent can always
  reach HBC: `start_agent`). 3 failed starts -> SAFE MODE (text-only agent).
- The Wii stays on a black screen after the NAND writes: power off/on (owner). Priiloader's own menu (hold RESET at
  power-on) can always set autoboot back to the System Menu; the backups in `backups/` restore the old files
  (`new_wii.py` can't restore by itself; write them back with `wiiagent.Agent(ip).nput(path, data)`).
- No Wi-Fi in the launcher: it retries and relaunches itself; the card works without Wi-Fi anyway (no updates).

## Dry run, 2026-10-16 night (what was checked)

- Image `~/wii-cards/wiisd-128-dryrun.sparseimage`, the exact size of a SanDisk Ultra 128 GB (127,865,454,592 bytes),
  formatted with the README command above: FAT32, 32 KB clusters. `sdkit_install.py --games` (cab1's live list,
  `~/wii-cards/master-games-cab1-20261016.tsv`) ran 39 min; re-run 16 s, nothing re-copied.
- All 1621 files of `dist/manifest.txt` on the card with the published size and CRC; boot chain and non-manifest
  files present (launcher = agent/wii-agent.dol 0.9.17, hop.dol, Priiloader installer, Nintendont, USB Loader GX
  r1283 + r1272 locked, RetroArch salamander + 8 cores, retroarch tree, term.ttf, cabs/default.cfg + cab1, update.cfg,
  installed.tsv); 87/87 GameCube discs as CISO (headers and disc ids checked; Pikmin compared block by block with
  the NAS image); 158 arcade + 52 console games, every one with a clip and art; no `._*` or `.part` files.
  (cab1's list still has docastle, hidden since: not copied, on purpose.)
- Simulator (Dolphin, slot 9, container `fresh9` on the Linux build box, agent on port 4319): booted **hop.dol** from
  the card -> launcher 0.9.17 with `autobooted=1`; WIIZARD intro rendered (term.ttf), 297 games found (87 GameCube,
  158 arcade, 52 console), attract mode and the browse menu render; Streets of Rage 2 started through the new
  genesis_plus_gx core (RetroArch GET_STATUS: PLAYING). `new_wii.py check` / `cab` run against it.
- Not testable without a real console: Priiloader, the NAND writes, the return from a game (Dolphin has no System
  Menu, so it stops where a Wii would go Priiloader -> hop -> launcher).

## Top-up, 2026-10-17 (the fixed installer)

- `sdkit_install.py /Volumes/WIISD --games <live cab1 list>` on the attached image: card check passed (FAT32, 32 KB
  clusters, "adds about 6.8 GiB", 21.1 GiB free); 203 published files written from `dist/files` (launcher 0.9.17 ->
  the published one), the MAME 2000 / FB Alpha `hiscore.dat` copies, and the six wrong GameCube discs fixed: Melee
  was the 20XX hack (later put back: the owner wants 20XX as Melee, "more arcady" — GC_PREFER in the installer), RE, Code Veronica, RE4, RE Zero and MGS Twin Snakes held disc 2 as `game.ciso`; now disc 1 +
  `disc2.ciso`. The hidden discs (Wii, Japanese-menu GameCube) were not copied again; the ones already on the image
  stay (invisible). 4 min; the image grew 6.8 GiB (the replaced discs were overwritten in place). Re-run: 11 s, nothing
  written.
- Check: all 1769 `dist/manifest.txt` paths on the image with the published size and CRC, installed.tsv 1769 rows,
  boot chain present, no `._*` / `.part` files, 14.6 GiB free on the card.
