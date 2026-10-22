# Licences

Everything in this repository is MIT licensed (`LICENSE`, copyright (c) 2026 Mitchell Vizensky) **except** the
pieces below, which keep their own licences.

| Path | Licence | Notes |
|---|---|---|
| `agent/lwip/` | BSD 3-clause (lwIP) | lwIP 2.2.1, unmodified subset; see `agent/lwip/COPYING` |
| `retroarch/swiirl.patch`, `retroarch/patches/retroarch_*.patch` | GPL-3.0 | Patches against RetroArch (GPLv3); they are derivative of it and are distributed under its licence |
| `retroarch/patches/fbalpha2012_*.patch` | FB Alpha licence (non-commercial) | Patches against libretro's fbalpha2012, under that project's licence |
| `retroarch/patches/mame2000_tilemap_be.patch` | MAME licence (non-commercial) | Patch against mame2000-libretro, under that project's licence |
| `retroarch/build/*.sh` | MIT | Our build scripts |
| `nintendont/swiirl.patch` | GPL-2.0 | Patch against Nintendont (GPLv2) |
| `sim/dolphin-wiisim.patch` | GPL-2.0-or-later | Patch against Dolphin |
| `sdkit/fonts/Anton-Regular.ttf` | SIL Open Font License 1.1 | `sdkit/fonts/OFL-anton.txt` |
| `sdkit/fonts/ArchivoBlack-Regular.ttf` | SIL Open Font License 1.1 | `sdkit/fonts/OFL-archivoblack.txt` |

The wizard character and its artwork (`art/wizard-parts/`, `art/mockups/mitchell-wizard/`, `sdkit/ui/wizard.wza`,
`docs/wizard-intro.gif`) are Mitchell Vizensky's own art, included under the MIT licence with the rest of the project.

Screenshots, recordings, boards and design mockups (`screens/`, `docs/media/`, `art/mockups/*.jpg`, and the media on
the GitHub release) show the launcher's interface with games running in
it. The games, their footage and their names belong to their respective owners and are shown only to illustrate the
interface; no game data is included or licensed here.

The tools work with third-party software that is not part of this repository and keeps its own licence: libogc and
devkitPPC, SDL2 and its Wii port, RetroArch and the libretro cores, Nintendont, USB Loader GX, d2x cIOS, Priiloader,
the Homebrew Channel, and Dolphin.

The reel's music (on the release) is original: a chip-pop loop synthesised from scratch for it, no samples or
third-party material, released CC0.
