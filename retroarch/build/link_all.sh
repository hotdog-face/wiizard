#!/bin/sh
# RetroArch (network commands on) linked with each core -> /src/out/<core>_libretro_wii.dol (devkitppc:20190212)
# Core commits are pinned in build_cores.sh (genesis_plus_gx e48a3717 + USE_DYNAMIC_ALLOC, snes9x2010 f9ae8fd).
# build_two.sh rebuilds and relinks just those two (griffin.o reused).
export PATH=/opt/devkitpro/devkitPPC/bin:$PATH
mkdir -p /src/out
cd /src/RetroArch
rm -f griffin/griffin.o   # griffin.o only depends on griffin.c in Makefile.griffin: rebuild so source edits (runloop.c, command.c) are in
for c in fbalpha2012:fbalpha2012/svn-current/trunk/fbalpha2012_libretro_wii.a \
         fbalpha2012_cps1:fbalpha2012_cps1/fbalpha2012_cps1_libretro_wii.a \
         fbalpha2012_cps2:fbalpha2012_cps2/fbalpha2012_cps2_libretro_wii.a \
         fbalpha2012_neogeo:fbalpha2012_neogeo/fbalpha2012_neogeo_libretro_wii.a \
         mame2000:mame2000-libretro/mame2000_libretro_wii.a \
         genesis_plus_gx:Genesis-Plus-GX/genesis_plus_gx_libretro_wii.a \
         snes9x2010:snes9x2010/snes9x2010_libretro_wii.a \
         fceumm:libretro-fceumm/fceumm_libretro_wii.a; do
  name=${c%%:*}; lib=${c#*:}
  cp /src/$lib libretro_wii.a
  rm -f retroarch_wii.elf retroarch_wii.dol
  make -f Makefile.griffin platform=wii GX_PTHREAD_LEGACY=0 HAVE_NETWORKING=1 HAVE_NETWORK_CMD=1 HAVE_COMMAND=1 -j8 > /src/link_$name.log 2>&1
  if [ -f retroarch_wii.dol ]; then cp retroarch_wii.dol /src/out/${name}_libretro_wii.dol; echo "$name ok"; else echo "$name FAILED"; grep -E " error|undefined" /src/link_$name.log | head -5; fi
done
echo LINK DONE
