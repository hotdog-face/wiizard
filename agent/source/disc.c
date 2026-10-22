// See disc.h. libdi notes (libogc libdi/di.c): DI_Init needs AHBPROT; DI_Mount spins the disc up and, through its
// cover callback chain, picks the read command that works (D0 for DVD-capable drives on DVDs, A8 otherwise) and ends in
// DVD_READY; DI_CheckDVDSupport = firmware date <= 2008-07-14 (the later D3-2 drives can't read DVDs at all).
#include <gccore.h>
#include <di/di.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "disc.h"

static int di_ready;                         // DI_Init done
static u8 *sec;                              // 32-byte aligned sector buffer (16 sectors)
#define SEC_BUF 16

static int ensure_init(char *out, int size) {
    if (!sec) sec = memalign(32, 2048 * SEC_BUF);
    if (!sec) { snprintf(out, size, "ERR no memory"); return -1; }
    if (!di_ready) {
        int r = DI_Init();
        if (r < 0 || (r == 0 && *(vu32 *)0xCD800064 != 0xFFFFFFFF)) { snprintf(out, size, "ERR DI_Init %d (AHBPROT?)", r); return -1; }
        di_ready = 1;
    }
    return 0;
}

// Spin up and wait for libdi's mount chain: DVD_READY (with D0 or A8), DVD_NO_DISC or DVD_UNKNOWN. -> status
static int mount(void) {
    DI_Mount();
    for (int i = 0; i < 150 && (DI_GetStatus() & DVD_INIT); i++) usleep(100 * 1000);
    return DI_GetStatus();
}

static void cmd_info(char *out, int size) {
    if (ensure_init(out, size)) return;
    DI_DriveID id ATTRIBUTE_ALIGN(32);
    memset(&id, 0, sizeof id);
    int r = DI_Identify(&id);
    u32 cover = 0, err = 0;
    DI_GetCoverRegister(&cover);
    int n = snprintf(out, size, "OK identify=%d rev=%04x dev=%04x date=%08x dvd=%s cover=%x", r, id.rev, id.dev_code,
                     (unsigned)id.rel_date, r == 0 ? (id.rel_date <= 0x20080714 ? "yes" : "no") : "?", (unsigned)cover);
    if (!(cover & DVD_COVER_DISC_INSERTED)) { snprintf(out + n, size - n, " disc=none"); return; }
    int st = mount();
    DI_GetError(&err);
    n += snprintf(out + n, size - n, " status=%x%s%s error=%08x", st, st & DVD_D0 ? " D0" : "", st & DVD_A8 ? " A8" : "",
                  (unsigned)err);
    if (!(st & DVD_READY)) return;
    // Sector 0: a GameCube/Wii disc header (id at 0, Wii magic at 0x18, GameCube magic at 0x1C, title at 0x20)
    if (DI_ReadDVD(sec, 1, 0) == 0) {
        u32 wii = *(u32 *)(sec + 0x18), gc = *(u32 *)(sec + 0x1C);
        if (wii == 0x5D1C9EA3 || gc == 0xC2339F3D) {
            char title[65];
            memcpy(title, sec + 0x20, 64); title[64] = 0;
            for (char *p = title; *p; p++) if (*p == '\t' || *p == '\n') *p = ' ';
            n += snprintf(out + n, size - n, " kind=%s id=%.6s title=%s", wii == 0x5D1C9EA3 ? "wii" : "gamecube", sec, title);
            return;
        }
    } else n += snprintf(out + n, size - n, " read0=fail");
    // Sector 16: ISO9660 primary volume descriptor ("\1CD001", volume id at 40); DVD-Video also has VIDEO_TS (UDF bridge)
    if (DI_ReadDVD(sec, 1, 16) == 0) {
        if (!memcmp(sec + 1, "CD001", 5)) {
            char vol[33];
            memcpy(vol, sec + 40, 32); vol[32] = 0;
            for (int i = 31; i >= 0 && vol[i] == ' '; i--) vol[i] = 0;
            u32 blocks = *(u32 *)(sec + 84);  // both-endian field: the big-endian copy
            snprintf(out + n, size - n, " kind=iso9660 volume=%s blocks=%u", vol, (unsigned)blocks);
        } else snprintf(out + n, size - n, " kind=unknown s16=%02x%02x%02x%02x%02x%02x", sec[0], sec[1], sec[2], sec[3], sec[4], sec[5]);
    } else snprintf(out + n, size - n, " read16=fail");
}

static void cmd_read(const char *arg, char *out, int size) {
    unsigned lba = 0, count = 0;
    char path[200] = "";
    if (sscanf(arg, "%u %u %199s", &lba, &count, path) != 3 || !count || count > 4096) {
        snprintf(out, size, "ERR usage: DISC READ <lba> <count <= 4096> <file>"); return;
    }
    if (ensure_init(out, size)) return;
    if (!(DI_GetStatus() & DVD_READY) && !(mount() & DVD_READY)) { snprintf(out, size, "ERR not ready (status %x)", DI_GetStatus()); return; }
    FILE *f = fopen(path, "wb");
    if (!f) { snprintf(out, size, "ERR can't write %s", path); return; }
    unsigned done = 0, bad = 0;
    while (done < count) {
        unsigned n = count - done < SEC_BUF ? count - done : SEC_BUF;
        int r = DI_ReadDVD(sec, n, lba + done);
        if (r) { bad++; memset(sec, 0, n * 2048); if (bad > 8) break; }
        fwrite(sec, 2048, n, f);
        done += n;
    }
    fclose(f);
    u32 err = 0;
    DI_GetError(&err);
    snprintf(out, size, "%s %u sectors from %u to %s, %u failed reads, error=%08x", bad > 8 ? "ERR" : "OK", done, lba, path,
             bad, (unsigned)err);
}

void disc_command(const char *arg, char *out, int size) {
    if (!strncmp(arg, "INFO", 4)) cmd_info(out, size);
    else if (!strncmp(arg, "READ ", 5)) cmd_read(arg + 5, out, size);
    else if (!strncmp(arg, "CLOSE", 5)) {
        if (di_ready) { DI_StopMotor(); DI_Close(); di_ready = 0; }
        snprintf(out, size, "OK closed");
    } else snprintf(out, size, "ERR usage: DISC INFO|READ <lba> <count> <file>|CLOSE");
}
