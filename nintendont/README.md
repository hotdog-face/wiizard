# Nintendont, SWIIRL build

Upstream FIX94/Nintendont (6.509, commit 09a072e) + swiirl.patch + background.png (loader/data/):
- L + R + Z + START exits to the loader (same as the arcade games); the START+Z+R in-game reset is gone.
- NIN_CFG_AUTOTEST (Config bit 30): the controller code exits to the loader after 40 s of play (unattended
  boot tests; the launcher's PLAYTEST command sets it).
- Dark SWIIRL background; loader text colours made light for it.

Build (the Linux build box): ~/nin-build with image nin-build-2019 (devkitpro/devkitppc:20190212 + devkitARM from
devkitarm:20190212 + zip from archive.debian.org; newer toolchains break Nintendont's return-to-loader):
    docker run --rm -u $(id -u):$(id -g) -v ~/nin-build:/src -w /src nin-build-2019 sh -c \
      'export PATH=/opt/devkitpro/devkitPPC/bin:/opt/devkitpro/devkitARM/bin:$PATH; make clean; make'
Output nintendont/boot.dol -> sdkit/nintendont-swiirl.dol.

2026-10-16 night:
- Real GameCube pads (the native SI path) now exit on L + R + Z + START too. Before, only the Wii Remote /
  Classic / HID path had it, so on a GC pad that combo hit the stock START + Z + R *reset*. L and R count when
  clicked or pressed past 0xB0 (kids rarely click them fully). Every START + Z + R reset is removed.
- Auto-boot from the launcher (argsboot) shows no Nintendont text; that was ~10 s of black. It now draws the SWIIRL
  background with a turning, breathing ring of soft dots in every wait, and fades to black just before the game.

2026-10-17 (kid-safe / idle exit; built as videos/fastexit/nintendont-kid.dol, not yet copied to sdkit/):
- Idle exit: after NIN_IDLE_MINUTES (15, common/include/CommonConfig.h) without any button, stick or trigger change
  on any port, PADReadGC.c takes the same exit as L+R+Z+START (back to the launcher). Sticks/triggers count when they
  move more than 16 from their value at the last change. 64-bit time base. The kernel passes the seconds at
  0x93003078 (kernel/Patch.c, next to the autotest's 0x93003074); the reference pad copy lives at
  0x930030A0-0x930030CF (free in mem_map.txt) because PADReadGC.bin must fit in 0x3000 bytes (8 bytes spare now).
- Test mode: if sd:/arcade/idletest exists when the loader starts the game, NIN_CFG bit 29 (NIN_CFG_IDLETEST, set
  only in memory after nincfg.bin is written) makes it NIN_IDLE_TEST_MINUTES (1). The file is only checked.
- Not testable in the simulator (no GameCube disc on the sim card): build + code reading only.
- Previous patch: swiirl.patch.before-kidsafe. Previous build sources on the Linux build box: ~/nin-kidsafe-backup/before.tgz.
