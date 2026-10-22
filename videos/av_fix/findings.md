# A/V fix (2026-10-17): Donkey Kong, Ghosts'n Goblins, arcade picture/sound on the CRT
Causes:
1. mame2000 tilemap.c memcpybitmask8/16 is little-endian only: transparent tilemap pixels are swapped in pairs on
   the Wii (gng, commando, pacmania, galaga88). Patched.
2. current_resolution_id 20 (640x240) for every game gave non-integer nearest scaling. Now per-game overrides give
   native lines 1:1 in 240p and an exact width multiple (make_overrides.py, geometry.json).
3. The picture was 10% narrow: a 4:3 NTSC picture is ~711 VI samples, not 640. Global video_viwidth 664 plus
   per-game viwidth fixes it; vertical games are 3:4 inside cab1's calibrated area (custom viewport).
4. Clicks: gx_audio.c DMA chunks weren't 32-byte aligned, giving a 500 Hz buzz. Patched (dkong 180 -> 0 spikes/s).
5. audio_resampler "nearest" was silently sinc 1; now sinc 2 explicitly.
6. fbalpha2012 samples.cpp read 16-bit WAVs in native byte order, so they played as noise. Patched.
7. The stale "bubble" image couldn't be reproduced in the sim; gx_gfx.c now clears the EFB at mode set and every frame.
Trade-off: 1:1 240p loses ~4 top / ~7 bottom lines to cab1's overscan (as an original board would); the alternative
is 480i (id 27, 512x424, viwidth 628), which keeps everything visible.
Patched DOLs: ~/ra-build/out-avfix (copy in dols/); patches in patches/; evidence in this folder.

## 2026-10-21: squashed, off-centre picture on cab1 (fix-aspect-20261021/)
Symptom (Mitchell, CRT): Mega Man - The Power Battle (CPS-1) squashed, bigger black bar on the right.
Cause: cab1's Wii is set to 16:9 (SYSCONF IPL.AR=1, backups/cab1-SYSCONF.20261015-232010). The av_fix overrides used
aspect_ratio_index 0 ("4:3"); RetroArch's GX driver letterboxes that against CONF_GetAspectRatio(), so every 4:3
game was drawn at 75% of its framebuffer width, and gx_resize moved the offset into the VI origin (hence the
asymmetry). Dolphin's SYSCONF is 4:3, so the sim never showed it. Reproduced in the sim with
SIMCONF=SYSCONF.IPL.AR=1 sim/mac_vrun.py: megaman lit x 8-302 of 384, snsmw 26-409 of 512 before; full width after.
Fix (make_overrides.py): every horizontal game and the console cores use aspect_ratio_index 23 with a custom viewport
covering the whole framebuffer (independent of the Wii's aspect setting), and the VI width follows the real dot
clock, as a MiSTer outputs it (VI samples run at 13.5 MHz, so samples = pixels x 13.5 / dot clock):
  CPS-1/CPS-2 384 px @ 8 MHz -> 648 | Neo Geo @ 6 MHz: 304 px -> 684, 320 px -> 720 | SNES/NES/Mega Drive -> 644
  (47.7 us active) | other arcade boards: 4:3 estimate, 664 at 224 lines, 704 at 240 | vertical games unchanged.
134 files; previous set in backup/config-before-640-20261021. On cab1 21:06, read back byte for byte; Mitchell:
"fills the screen, looks right" (CPS-1 games, 2026-10-21 ~21:10).

What the Wii can and can't do (for MiSTer-like output):
- 240p: RetroArch picks VI_NON_INTERLACE when the framebuffer has <= 240 lines, so one game line = one scanline (no
  doubling, no interlace). Refresh is the Wii's 240p rate (~59.83 Hz, 263 lines); games run vsynced to it (CPS
  59.64 Hz +0.3%, Neo Geo 59.19 Hz +1%, SNES 60.1 Hz -0.4%), audio follows through RetroArch's rate control.
- Horizontal: the VI always outputs 13.5 MHz samples; it can't use a board's own dot clock. A framebuffer narrower than
  video_viwidth is widened by the VI's hardware horizontal scaler (upscale only, up to 2x; a filtered resample, not
  point sampling). That is the single resample per game here (video_smooth off: GX draws texels 1:1 or exact 2x).
  Truly sharp columns would need an integer sample ratio, which no board has at 13.5 MHz (CPS 1.6875, SNES 2.51).
  On a CRT this filtered resample looks like a slightly soft analogue picture, which is close to what the tube does
  anyway.
- Not done: fbWidth = viWidth with GX nearest (uneven 1/2-sample columns that shimmer when scrolling), or GX bilinear
  to 640 then the VI (two resamples, softer).
- The Wii's 16:9 setting also makes Wii games (USB Loader GX) anamorphic on a 4:3 CRT; Mitchell asked for the cab
  to be switched to 4:3 (to do when cab1 is free; SYSCONF backed up first).

## 2026-10-21 night: locked baseline
Mitchell on the CRT: "the video resolution looks fantastic on the CRT. its excellent. looking pixel perfect so far on
the games Ive seen. arcade titles look particularly good with the scan lines". This set (the fix-aspect overrides
plus the global retroarch.cfg video keys) is frozen in baseline-20261021/. check_baseline.py compares sdkit against it
and must pass before publishing. The same night, RetroArch's on-screen text was turned off (video_font_enable,
notification_show_*); none of those are video keys.
