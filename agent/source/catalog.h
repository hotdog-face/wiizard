#ifndef CATALOG_H
#define CATALOG_H

// Display order in the browser (one carousel per system).
enum { SYS_ARCADE = 1, SYS_CPS1 = 2, SYS_CPS2 = 3, SYS_NEOGEO = 4, SYS_GAMECUBE = 5, SYS_WII = 6,
       SYS_GENESIS = 7, SYS_SNES = 8, SYS_NES = 9 };   // consoles: ROMs in arcade.tsv like the arcade sets

typedef struct {
    char title[96];
    char id[8];                              // disc id (GameCube/Wii), e.g. GPIE01; arcade: short name prefix
    char path[256];                          // disc image or ROM zip on SD
    char rom[48];                            // arcade: zip file name, e.g. mslug.zip; consoles: ROM file, e.g. mdsor2.md
    char cover[128];                         // box art PNG on SD, "" if none
    char year[8], maker[48];                 // arcade metadata
    char core[40];                           // arcade: RetroArch core, e.g. fbalpha2012_cps2 (sd:/apps/retroarch-wii)
    char vkey[16];                           // gameplay clip: sd:/arcade/video/<vkey>.gvid (disc id or zip stem)
    int system;
} game_t;

// Scans the SD card and returns the games sorted by system, then title. *count gets the number.
//   GameCube: sd:/games (Nintendont layouts); Wii: sd:/wbfs/<Title [ID]>/<ID>.wbfs (USB Loader GX layout);
//   arcade: sd:/arcade/arcade.tsv written by the Mac (only sets checked against the cores' ROM lists):
//           system<TAB>zip<TAB>title<TAB>year<TAB>maker<TAB>core, ROMs in sd:/roms/<system>/.
game_t *catalog_scan(int *count);
const char *system_name(int system);

#endif
