// hop: Priiloader's autoboot program (NAND .../data/main.bin). It only starts the arcade launcher from the SD card
// (sd:/apps/wii-agent/boot.dol), and it does so WITHOUT reloading IOS: Priiloader starts us with AHBPROT off, and an
// IOS reload would switch that protection back on. Nintendont (GameCube) and USB Loader GX (Wii) need it off; the
// launcher keeps it off across its own reloads (es_set_ahbprot patch). Small on purpose: it replaces the 0.2.3
// agent in a NAND file that can't grow. If the SD launcher is missing, it starts the Homebrew Channel instead.
#include <gccore.h>
#include <fat.h>
#include <sdcard/wiisd_io.h>
#include <ogc/machine/processor.h>
#include <stdio.h>
#include <string.h>

extern u8 booter_start[], booter_end[];
#define LAUNCHER "sd:/apps/wii-agent/boot.dol"
#define LAUNCHER_GOOD "sd:/apps/wii-agent/boot-good.dol"
#define MAX_IMAGE (16 * 1024 * 1024)
#define HBC_TITLE 0x000100014C554C5AULL      // "LULZ": the Homebrew Channel 1.1

static u32 *list;
static int add(u32 dst, u32 src, u32 len) {
    if (!len) return 0;
    if (dst < 0x80000000) dst |= 0x80000000;
    u32 n = list[0]++;
    list[1 + n * 3] = dst; list[2 + n * 3] = src; list[3 + n * 3] = len;
    return 0;
}

int main(int argc, char **argv) {
    u8 *area = (u8 *)(((u32)SYS_GetArena2Hi() - MAX_IMAGE - 256 * 1024) & ~0xFFFF);
    SYS_SetArena2Hi(area);
    if (!fatMountSimple("sd", &__io_wiisd)) goto fail;
    // Two slots: the launcher counts its starts in sd:/arcade/bootcount and clears it once it has run healthily
    // (or leaves on purpose). Two failed starts in a row: start the last copy that ran healthily (boot-good.dol,
    // which the launcher keeps). Five: the Homebrew Channel, which the Mac can always reach over Wi-Fi.
    int boots = 0;
    FILE *bc = fopen("sd:/arcade/bootcount", "r");
    if (bc) { if (fscanf(bc, "%d", &boots) != 1) boots = 0; fclose(bc); }
    const char *pick = LAUNCHER;
    if (boots >= 5) { fatUnmount("sd:"); goto fail; }
    if (boots >= 2) {
        FILE *g = fopen(LAUNCHER_GOOD, "rb");
        if (g) { fclose(g); pick = LAUNCHER_GOOD; }
    }
    FILE *f = fopen(pick, "rb");
    if (!f && pick != LAUNCHER) f = fopen(pick = LAUNCHER, "rb");
    if (!f) { fatUnmount("sd:"); goto fail; }
    u32 size = fread(area, 1, MAX_IMAGE, f);
    fclose(f);
    fatUnmount("sd:");
    if (size < 0x100) goto fail;
    u32 *h = (u32 *)area;
    list = (u32 *)(area + MAX_IMAGE);
    list[0] = 0;
    for (int i = 0; i < 18; i++) {           // text and data sections
        if (!h[36 + i]) continue;
        if (h[i] + h[36 + i] > size) goto fail;
        add(h[18 + i], (u32)area + h[i], h[36 + i]);
    }
    add(h[54], 0, h[55]);                     // bss
    u32 entry = h[56] | 0x80000000;
    // libogc argv: "_arg" at entry+4 -> struct at entry+8 (the launcher learns it was autobooted)
    u8 *magic = NULL;
    for (int i = 0; i < 18; i++)
        if (h[18 + i] <= entry + 4 && entry + 4 < h[18 + i] + h[36 + i]) magic = area + h[i] + (entry + 4 - h[18 + i]);
    if (magic && !memcmp(magic, "_arg", 4)) {
        u32 *av = list + 1 + 3 * 64;
        char *cmd = (char *)(av + 8);
        int len = sprintf(cmd, "%s", pick) + 1;  // argv[0] = the file actually started
        static const char rest[] = "--relaunch=hop\0--autobooted\0";
        memcpy(cmd + len, rest, sizeof rest);
        len += sizeof rest;
        av[0] = 0x5f617267; av[1] = (u32)cmd; av[2] = len; av[3] = av[4] = av[5] = 0;
        add(entry + 8, (u32)av, 24);
    }
    u8 *stub = (u8 *)list + 32 * 1024;
    memcpy(stub, booter_start, booter_end - booter_start);
    DCFlushRange(area, MAX_IMAGE + 256 * 1024);
    ICInvalidateRange(stub, booter_end - booter_start);
    SYS_ResetSystem(SYS_SHUTDOWN, 0, 0);      // no IOS reload: AHBPROT stays off
    u32 level;
    _CPU_ISR_Disable(level);
    ((void (*)(u32 *, u32))stub)(list, entry);
    return 0;
fail:
    WII_Initialize();
    WII_LaunchTitle(HBC_TITLE);               // the Mac can reach the Homebrew Channel (wiiload)
    return 0;
}
