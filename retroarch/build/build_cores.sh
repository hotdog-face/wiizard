#!/bin/sh
# Wii static libs of the eight cores, with the same 2019 toolchain RetroArch links with (run in devkitppc:20190212)
export PATH=/opt/devkitpro/devkitPPC/bin:$PATH
cd /src/fbalpha2012/svn-current/trunk && make -f makefile.libretro platform=wii -j4 >/src/fba.log 2>&1
cd /src/fbalpha2012_cps1 && make -f makefile.libretro platform=wii -j4 >/src/cps1.log 2>&1
cd /src/fbalpha2012_cps2 && make -f makefile.libretro platform=wii -j4 >/src/cps2.log 2>&1
cd /src/fbalpha2012_neogeo && make platform=wii -j4 >/src/neogeo.log 2>&1
cd /src/mame2000-libretro && make platform=wii -j4 >/src/mame2000.log 2>&1
# Genesis Plus GX at e48a3717 (2025-11-21, RetroArch 1.22.2 era). Wii fix: add -DUSE_DYNAMIC_ALLOC (WiiU already has
# it). Without it the 15.8 MB cart/CD union "ext" is static bss, the DOL's bss ends at 0x819f9c40, past the end of
# MEM1 (0x81800000), and the DOL dies before RetroArch starts. With it, ext is calloc'd (RetroArch's MEM2 heap).
cd /src/Genesis-Plus-GX && git checkout -q -f e48a3717 && \
  sed -i 's/^\(      PLATFORM_DEFINES += -DHW_RVL -mrvl\)$/\1 -DUSE_DYNAMIC_ALLOC/' Makefile.libretro && \
  make -f Makefile.libretro platform=wii -j4 >/src/genesis_plus_gx.log 2>&1
# snes9x2010 at f9ae8fd (2024-11-19, the long-standing libretro version). Do not use the 2026 commits: their
# libretro-common has memstream_open(data, size, writing), which clashes at static link with RetroArch 1.22.2's
# memstream_open(writing) (griffin.o's definition wins), so the ROM stream has no buffer: "ROM: Unable to load ROM".
cd /src/snes9x2010 && git checkout -q f9ae8fd && make platform=wii -j4 >/src/snes9x2010.log 2>&1
cd /src/libretro-fceumm && make platform=wii -j4 >/src/fceumm.log 2>&1
ls -la /src/*/*_wii.a /src/fbalpha2012/svn-current/trunk/*_wii.a
echo CORES DONE
