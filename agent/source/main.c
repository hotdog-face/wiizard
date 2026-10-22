// wii-agent: network control of a Wii for the Mac-side `wii` MCP server (wii_mcp.py).
//
// Runs as a Homebrew Channel app (sd:/apps/wii-agent/boot.dol) and serves a line-based text protocol on TCP 4300,
// one client at a time. Every reply starts with "OK" or "ERR <message>". Paths are full libfat paths (sd:/..., usb:/...).
//   INFO                      OK agent=<ver> id=<device id> ip=<ip> ios=<n> sd=<0|1> usb=<0|1> fb=<w>x<h> uptime=<s>
//   LS <path>                 one line per entry: "D <name>" or "F <size> <name>", then OK <count>
//   GET <path>                OK <size>\n then the raw bytes
//   PUT <size> <path>         client sends <size> raw bytes right after the line; OK when written
//   PUTAT <offset> <size> <path>  write a chunk into <path>.part (offset 0 starts it); resumable uploads
//   COMMIT <size> <path>      <path>.part must be <size> bytes; it replaces <path>
//   STAT <path>               OK <size> | ERR
//   RM <path> | MKDIR <path> | MV <src>\t<dst> | DF <device:/>
//   SHOT                      OK <w> <h> <bytes>\n then the external framebuffer (YUYV, 2 bytes per pixel)
//   PAD <hex buttons> <ms>    hold virtual Wiimote buttons (WPAD_BUTTON_* bits) for <ms>
//   EXEC <path>[\t<arg>...]   boot a .dol/.elf from sd:/usb: with arguments (argv[0] = path), after OK is sent
//   LOG                       the recent log from RAM (the card copy is only written now and then): text, then OK
//   NLS <dir> | NGET <file>   read-only NAND access (ISFS): names, one per line, then OK / OK <size>\n + bytes
//   NPUT <size> <file>        NAND write, only for files in ALLOWED_NAND_WRITES (Priiloader's settings)
//   SCREEN [<width%> <height%> <x> <y>]  CRT overscan calibration (edge markers for 20 s); no args: current values
//   CLOCK <local time>        the Mac's wall-clock time as seconds since 1970 in local time: the menu's clock follows
//   GAMES                     one line per game: <index>\t<system>\t<id or zip>\t<title>, then OK <count>
//   PLAY <index|id|zip>       launch that game the way the launcher does (after OK); the Wii is then off the network
//   PLAYTEST <id>             the same, in test mode: GameCube games return here by themselves after 40 s of play
//   TESTQUEUE [<id> ...]      test those games back to back without the Mac (Wi-Fi is slow to return after each):
//                             each in test mode, 20 s apart; results in sd:/arcade/returns.tsv. No ids: stop
//   HBC | MENU | REBOOT | OFF exit to the Homebrew Channel / Wii Menu / restart / power off (after OK is sent)
//   UPDATE                    check the update server now (publish.py sends it after publishing)
//   QUIT                      close the connection
#include <gccore.h>
#include <network.h>
#include "netx.h"
#include <fat.h>
#include <wiiuse/wpad.h>
#include <ogc/lwp_watchdog.h>
#include <ogc/usbstorage.h>
#include <sdcard/wiisd_io.h>
#include <fcntl.h>
#include <ogc/machine/processor.h>
#include <stdio.h>
#include <malloc.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <dirent.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <time.h>
#include "catalog.h"
#include "resume.h"
#include "ui.h"
#include "cab.h"
#include "store.h"
#include "gfx.h"
#include "update.h"
#include "eth.h"
#include "lwnet.h"

void __exception_setreload(int t);      // libogc, not in its headers: reload after t s on a crash
extern u8 booter_start[], booter_end[];  // booter.S
#define AGENT_VERSION "0.11.3"
#define AGENT_PORT 4300
#define HEARTBEAT_PORT 4301                 // UDP "I'm here" every few seconds: keeps the Wi-Fi awake, lets the Mac find us
#define HEARTBEAT_MS 3000
#define LINK_CHECK_MS 20000                 // with no Mac contact for a minute: can we still reach the router?
#define LINK_FAILS_RELAUNCH 3               // that many failed checks in a row: relaunch with a fresh IOS
#define HOME_FILE "sd:/apps/wii-agent/home.txt"   // the Mac's address, written by the MCP server
#define CHUNK 8192
// busy indicator: top-right corner, clear of the console text (which stays left of x=520)
#define BUSY_SIZE 96
#define BUSY_X 528
#define BUSY_Y 24
#define BUSY_TEXT_ROW 8
#define BUSY_TEXT_COL 63
#define NET_RELAUNCH_TRIES 3               // Wi-Fi failures before relaunching with a fresh IOS (same IOS never recovers)
#define AGENT_SD_DOL "sd:/apps/wii-agent/boot.dol"
#define NET_DEAD_SECS 150                    // main-thread network watchdog (see the main loop)
#define NET_GIVE_UP_SECS 180                 // no Wi-Fi by then: go back to the Homebrew Channel (wiiload works there)
#ifndef IOS_O_NONBLOCK
#define IOS_O_NONBLOCK 0x04
#endif

enum { REQ_NONE, REQ_HBC, REQ_MENU, REQ_REBOOT, REQ_OFF, REQ_EXEC };

// EXEC keeps its data at the top of MEM2, reserved from the heap at startup so nothing else uses it:
// [ image (up to EXEC_MAX) | copy list | argv block | boot stub ]
#define EXEC_MAX (16 * 1024 * 1024)
#define EXEC_RESERVE (EXEC_MAX + 256 * 1024)
static u8 *exec_area;
static u32 *exec_list;
static u32 exec_entry;
#define PRII_MAIN_BIN "/title/00000001/00000002/data/main.bin"
// Priiloader's settings and its autoboot program; nothing else on the NAND can be written
// (main.nfo: Priiloader's settings for main.bin; its first byte = start main.bin with AHBPROT off)
static const char *ALLOWED_NAND_WRITES[] = { "/title/00000001/00000002/data/loader.ini", PRII_MAIN_BIN,
                                             "/title/00000001/00000002/data/main.nfo",
                                             "/shared2/sys/SYSCONF",            // (the Wii's settings: screen shape 4:3)
                                             "/shared2/sys/net/02/config.dat", NULL };   // (connection settings: wired)
static int wpad_up;
static int selftest;
static int safe_mode;                        // the launcher failed to stay up 3 boots running: text-only agent
#define BOOT_COUNT_FILE "sd:/arcade/bootcount"
#define HEALTHY_SECS 60                         // 1 = UI without network, 2 = network without UI; reboots after 40 s
static int autobooted;
static int game_ran;                         // ... and the game really ran (--game-ran): a quick quit is not a failed start
static int back_from_game;                   // started by our RetroArch on quit (--relaunch=game): straight back, no Priiloader
static int restarted;                        // a relaunch of our own (Wi-Fi, update): no power-on swirl                       // started by Priiloader's autoboot (argv[0] is its main.bin)

static GXRModeObj *rmode;
static void *xfb;
static char ip[16] = "";
static u32 device_id;
static int sd_ok, usb_ok;
static u64 boot_ticks;
static volatile int request = REQ_NONE;
static volatile int quitting = 0;
static volatile u32 virt_buttons;
static volatile u64 virt_until;
static volatile int clients_served;
static char last_cmd[96] = "-";
static volatile s32 net_err;
static volatile int net_tries;
static volatile int net_up;
static volatile int net_thread_done;
static game_t *lib_games;                    // the launcher's catalog (for GAMES / PLAY)
static int lib_count;
static volatile int play_request = -1;
static volatile int play_test;               // PLAYTEST: launch in test mode (our Nintendont returns after 40 s)
#define TEST_QUEUE_FILE "sd:/arcade/testqueue.txt"   // TESTQUEUE: ids still to test, one per line
static volatile int update_now;              // UPDATE command: check now, and fetch whenever no game runs
#define TEST_QUEUE_GAP_SECS 20                         // in attract between games: time to reach it, or stop it
static int test_queue;                       // 1 while a queue file exists
static int isfs_ok;
static u8 iobuf[CHUNK] ATTRIBUTE_ALIGN(32);
static volatile u64 last_activity;          // last command from the Mac (drives the busy indicator)
static volatile u64 last_net_ok;             // last proof the network works: a Mac command or a router check
static volatile int client_open;
static void netlog(const char *fmt, ...);
static void netlog_now(const char *fmt, ...);
static void log_flush(void);

static volatile int reset_pressed;            // Reset button / Wiimote HOME: back to attract mode, never out
static void on_reset(u32 irq, void *ctx) { reset_pressed = 1; }
static void on_power(void) { request = REQ_OFF; }
static void on_wpad_power(s32 chan) { request = REQ_OFF; }

// ---------------------------------------------------------------- sockets

typedef struct { s32 s; char buf[1024]; int len, pos; } conn_t;
static void cmd_log(conn_t *c);

static s32 set_blocking(s32 s, bool blocking) {
    s32 flags = net_fcntl(s, F_GETFL, 0);
    if (flags >= 0) flags = net_fcntl(s, F_SETFL, blocking ? (flags & ~IOS_O_NONBLOCK) : (flags | IOS_O_NONBLOCK));
    return flags;
}

// Client sockets are non-blocking: a connection that goes silent for IO_TIMEOUT_MS is dropped. Before this, a
// half-open connection (Wi-Fi dropped the FIN) blocked the single server thread forever: ping answered, TCP didn't.
#define IO_TIMEOUT_MS 20000

static int io_timed(s32 s, void *buf, int n, int sending) {
    u64 start = gettime();
    for (;;) {
        int r = sending ? net_send(s, buf, n, 0) : net_recv(s, buf, n, 0);
        if (r > 0) return r;
        if (r == 0) return sending ? -1 : 0; // peer closed
        if (r != -EAGAIN && r != -EWOULDBLOCK) return r;
        if (quitting || ticks_to_millisecs(gettime() - start) > IO_TIMEOUT_MS) return -ETIMEDOUT;
        usleep(2000);
    }
}

// Sends block: a non-blocking net_send can return -EAGAIN after IOS has already taken part of the data, and the
// retry then sent it twice (downloads had 4 KB repeated; up to 0.8.1). A blocking send reports what it really sent;
// against a dead peer it ends when TCP gives up. Receives stay non-blocking with their timeout (the old wedge).
static int send_all(conn_t *c, const void *data, int n) {
    const u8 *p = data;
    set_blocking(c->s, true);
    while (n > 0) {
        int r = net_send(c->s, (void *)p, n > CHUNK ? CHUNK : n, 0);
        if (r == -EAGAIN || r == -EWOULDBLOCK) { usleep(2000); continue; }
        if (r <= 0 || quitting) { set_blocking(c->s, false); return -1; }
        p += r; n -= r;
    }
    set_blocking(c->s, false);
    return 0;
}

static int sendf(conn_t *c, const char *fmt, ...) {
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    return send_all(c, line, n < (int)sizeof line ? n : (int)sizeof line - 1);
}

static int fill(conn_t *c) {
    c->pos = 0;
    c->len = io_timed(c->s, c->buf, sizeof c->buf, 0);
    return c->len;
}

// one line without the trailing \r\n; -1 when the client went away
static int read_line(conn_t *c, char *out, int max) {
    int n = 0;
    for (;;) {
        if (c->pos >= c->len && fill(c) <= 0) return -1;
        char ch = c->buf[c->pos++];
        if (ch == '\n') break;
        if (ch != '\r' && n < max - 1) out[n++] = ch;
    }
    out[n] = 0;
    return n;
}

static int read_exact(conn_t *c, u8 *out, int n) {
    while (n > 0) {
        if (c->pos < c->len) {
            int k = c->len - c->pos;
            if (k > n) k = n;
            memcpy(out, c->buf + c->pos, k);
            c->pos += k; out += k; n -= k;
        } else {
            int r = io_timed(c->s, out, n > CHUNK ? CHUNK : n, 0);
            if (r <= 0) return -1;
            out += r; n -= r;
        }
    }
    return 0;
}

// ---------------------------------------------------------------- commands

static void mkdirs(const char *path) {
    char tmp[512];
    snprintf(tmp, sizeof tmp, "%s", path);
    char *p = strchr(tmp, ':');
    p = p ? p + 2 : tmp + 1;
    for (; *p; p++) {
        if (*p == '/') { *p = 0; mkdir(tmp, 0777); *p = '/'; }
    }
    mkdir(tmp, 0777);
}

static void cmd_ls(conn_t *c, const char *path) {
    DIR *d = opendir(path);
    if (!d) { sendf(c, "ERR %s\n", strerror(errno)); return; }
    struct dirent *e;
    int count = 0;
    char full[600];
    struct stat st;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        snprintf(full, sizeof full, "%s%s%s", path, path[strlen(path) - 1] == '/' ? "" : "/", e->d_name);
        if (stat(full, &st) == 0 && S_ISDIR(st.st_mode)) sendf(c, "D %s\n", e->d_name);
        else sendf(c, "F %lld %s\n", (long long)(stat(full, &st) == 0 ? st.st_size : -1), e->d_name);
        count++;
    }
    closedir(d);
    sendf(c, "OK %d\n", count);
}

static void cmd_get(conn_t *c, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { sendf(c, "ERR %s\n", strerror(errno)); return; }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    sendf(c, "OK %ld\n", size);
    size_t r;
    while ((r = fread(iobuf, 1, CHUNK, f)) > 0)
        if (send_all(c, iobuf, r) < 0) break;
    fclose(f);
}

static void cmd_put(conn_t *c, char *args) {
    char *path = strchr(args, ' ');
    if (!path) { sendf(c, "ERR usage: PUT <size> <path>\n"); return; }
    *path++ = 0;
    long size = atol(args);
    char part[520];
    snprintf(part, sizeof part, "%s.part", path);
    FILE *f = fopen(part, "wb");
    long left = size;
    int ok = f != NULL;
    while (left > 0) {                       // always drain the payload so the protocol stays in step
        int n = left > CHUNK ? CHUNK : left;
        if (read_exact(c, iobuf, n) < 0) { ok = 0; break; }
        if (ok && fwrite(iobuf, 1, n, f) != (size_t)n) ok = 0;
        left -= n;
    }
    if (f) fclose(f);
    if (!ok) { remove(part); sendf(c, "ERR write failed\n"); return; }
    remove(path);
    if (rename(part, path) != 0) { sendf(c, "ERR rename: %s\n", strerror(errno)); return; }
    sendf(c, "OK %ld\n", size);
}

static void cmd_putat(conn_t *c, char *args) {
    unsigned long off, size;
    int n = 0;
    if (sscanf(args, "%lu %lu %n", &off, &size, &n) < 2 || !n) { sendf(c, "ERR usage: PUTAT <offset> <size> <path>\n"); return; }
    char part[520];
    snprintf(part, sizeof part, "%s.part", args + n);
    FILE *f = fopen(part, off ? "r+b" : "wb");
    int ok = f && fseek(f, off, SEEK_SET) == 0;
    unsigned long left = size;
    while (left > 0) {                       // always drain the payload so the protocol stays in step
        int k = left > CHUNK ? CHUNK : left;
        if (read_exact(c, iobuf, k) < 0) { ok = 0; break; }
        if (ok && fwrite(iobuf, 1, k, f) != (size_t)k) ok = 0;
        left -= k;
    }
    if (f) fclose(f);
    if (!ok) { sendf(c, "ERR write failed\n"); return; }
    sendf(c, "OK %lu\n", off + size);
}

static void cmd_commit(conn_t *c, char *args) {
    unsigned long size;
    int n = 0;
    if (sscanf(args, "%lu %n", &size, &n) < 1 || !n) { sendf(c, "ERR usage: COMMIT <size> <path>\n"); return; }
    const char *path = args + n;
    char part[520];
    snprintf(part, sizeof part, "%s.part", path);
    struct stat st;
    if (stat(part, &st) != 0 || (unsigned long)st.st_size != size) {
        sendf(c, "ERR part is %ld bytes, expected %lu\n", stat(part, &st) == 0 ? (long)st.st_size : -1L, size);
        return;
    }
    remove(path);
    if (rename(part, path) != 0) { sendf(c, "ERR rename: %s\n", strerror(errno)); return; }
    sendf(c, "OK %lu\n", size);
}

static void cmd_shot(conn_t *c) {
    u32 fb = (u32)(safe_mode ? VIDEO_GetCurrentFramebuffer() : gfx_front_buffer());   // the buffer on screen
    // (VIDEO_GetCurrentFramebuffer gave an all-black buffer while the launcher's picture was fine)
    int w = rmode->fbWidth, h = rmode->xfbHeight, n = w * h * VI_DISPLAY_PIX_SZ;
    if (!fb) fb = (u32)VIDEO_GetCurrentFramebuffer();
    if (!fb) fb = (u32)xfb;
    if (fb < 0x80000000) fb = (u32)MEM_PHYSICAL_TO_K1(fb);      // physical -> uncached
    else if (fb < 0xC0000000) fb = (u32)MEM_K0_TO_K1(fb);       // cached -> uncached; already uncached stays
    // Copy first: sending takes ~1 s over Wi-Fi, and this buffer becomes the back buffer on the next frame (the
    // capture showed two frames torn together; the TV never did).
    static u8 *snap;
    if (!snap) snap = memalign(32, n);
    if (snap) { memcpy(snap, (void *)fb, n); fb = (u32)snap; }
    sendf(c, "OK %d %d %d\n", w, h, n);
    send_all(c, (void *)fb, n);
}

static bool from_hbc(void) {               // the Homebrew Channel's return stub is in place
    return *(vu32 *)0x80001804 == 0x53545542 && *(vu32 *)0x80001808 == 0x48415858;   // "STUB" "HAXX"
}

// The Homebrew Channel's reload stub (installed by Priiloader at 0x80001800) is where crashes, exit() and games'
// "return to loader" land. Point it at the System Menu instead of HBC: Priiloader then autoboots us again, so
// nothing ever waits in HBC (whose Wi-Fi is unreliable) for a person. Title id = (r30 << 32) | r31, built by
// lis/ori pairs at 0x80001F5C..0x80001F68 in the 0.10/1.1 stub; patched only if those instructions match.
static void retarget_stub(void) {
    vu32 *code = (vu32 *)0x80001F5C;
    if (!from_hbc()) return;
    if (code[0] == 0x3FC00000 && code[2] == 0x63DE0001 && (code[1] & 0xFFFF) == 0 && (code[3] & 0xFFFF) == 2) return;
    if ((code[0] & 0xFFFF0000) != 0x3FC00000 || (code[1] & 0xFFFF0000) != 0x3FE00000 ||
        (code[2] & 0xFFFF0000) != 0x63DE0000 || (code[3] & 0xFFFF0000) != 0x63FF0000) {
        netlog("reload stub not recognised (%08x %08x %08x %08x); left alone", code[0], code[1], code[2], code[3]);
        return;
    }
    *(vu16 *)0x80001F5E = 0x0000;            // lis r30,0      -> upper 0x00000001 (with ori r30,r30,1)
    *(vu16 *)0x80001F62 = 0x0000;            // lis r31,0
    *(vu16 *)0x80001F6A = 0x0002;            // ori r31,r31,2  -> 00000001-00000002, the System Menu
    DCFlushRange((void *)0x80001800, 0x1800);
    ICInvalidateRange((void *)0x80001800, 0x1800);
    netlog("reload stub now returns to the System Menu (Priiloader -> agent)");
}

// for ui.c breadcrumbs
void agent_log(const char *fmt, ...) {
    char line[160];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    netlog("%s", line);
}

// ---------------------------------------------------------------- EXEC

static int list_add(u32 dst, u32 src, u32 len, char *err) {
    if (!len) return 0;
    if (dst < 0x80000000) dst |= 0x80000000;
    u32 lo = (u32)exec_area, hi = lo + EXEC_RESERVE;
    bool mem1 = dst >= 0x80003000 && dst + len <= 0x81800000;
    bool mem2 = dst >= 0x90000000 && dst + len <= 0x93400000 && (dst + len <= lo || dst >= hi);
    if (!mem1 && !mem2) { sprintf(err, "section at %08x+%x is outside usable memory", dst, len); return -1; }
    u32 n = exec_list[0]++;
    exec_list[1 + n * 3] = dst;
    exec_list[2 + n * 3] = src;
    exec_list[3 + n * 3] = len;
    return 0;
}

static u8 *image_at(u8 *img, u32 size, u32 addr, int dol) {   // file bytes that will land at addr (for "_arg")
    if (dol) {
        u32 *h = (u32 *)img;
        for (int i = 0; i < 18; i++)
            if (h[18 + i] <= addr && addr < h[18 + i] + h[36 + i] && h[i] + (addr - h[18 + i]) < size) return img + h[i] + (addr - h[18 + i]);
    } else {
        u32 phoff = *(u32 *)(img + 0x1c);
        u16 phnum = *(u16 *)(img + 0x2c), phsz = *(u16 *)(img + 0x2a);
        for (int i = 0; i < phnum; i++) {
            u32 *ph = (u32 *)(img + phoff + i * phsz);
            u32 va = ph[2] >= 0x80000000 ? ph[2] : (ph[3] | 0x80000000);
            if (ph[0] == 1 && va <= addr && addr < va + ph[4]) return img + ph[1] + (addr - va);
        }
    }
    return NULL;
}

// Reads the program into the reserved area and prepares the copy list; the jump happens in main(). Arguments may
// hold any bytes (Nintendont takes a binary settings block as argv[1]); argv[0] is the program's path.
static int exec_prepare_args(const char *spec, const char **args, const int *lens, int nargs, char *err) {
    FILE *f = fopen(spec, "rb");
    if (!f) { sprintf(err, "%s: %s", spec, strerror(errno)); return -1; }
    fseek(f, 0, SEEK_END);
    u32 size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size < 0x100 || size > EXEC_MAX) { fclose(f); sprintf(err, "bad size %u", size); return -1; }
    u8 *img = exec_area;
    u32 got = fread(img, 1, size, f);
    fclose(f);
    if (got != size) { sprintf(err, "short read"); return -1; }
    exec_list = (u32 *)(exec_area + EXEC_MAX);
    exec_list[0] = 0;
    int dol = memcmp(img, "\x7f" "ELF", 4) != 0;
    if (dol) {
        u32 *h = (u32 *)img;
        for (int i = 0; i < 18; i++) {
            if (!h[36 + i]) continue;
            if (h[i] + h[36 + i] > size) { sprintf(err, "section %d past end of file", i); return -1; }
            if (list_add(h[18 + i], (u32)img + h[i], h[36 + i], err)) return -1;
        }
        if (list_add(h[54], 0, h[55], err)) return -1;              // bss
        exec_entry = h[56];
    } else {
        if (img[4] != 1 || img[5] != 2) { sprintf(err, "not a 32-bit big-endian ELF"); return -1; }
        u32 phoff = *(u32 *)(img + 0x1c);
        u16 phnum = *(u16 *)(img + 0x2c), phsz = *(u16 *)(img + 0x2a);
        for (int i = 0; i < phnum; i++) {
            u32 *ph = (u32 *)(img + phoff + i * phsz);
            if (ph[0] != 1) continue;                                // PT_LOAD
            u32 va = ph[2] >= 0x80000000 ? ph[2] : (ph[3] | 0x80000000);
            if (ph[1] + ph[4] > size) { sprintf(err, "segment %d past end of file", i); return -1; }
            if (list_add(va, (u32)img + ph[1], ph[4], err)) return -1;
            if (ph[5] > ph[4] && list_add(va + ph[4], 0, ph[5] - ph[4], err)) return -1;
        }
        exec_entry = *(u32 *)(img + 0x18);
    }
    if (exec_entry < 0x80000000) exec_entry |= 0x80000000;
    // libogc/HBC argv protocol: "_arg" at entry+4, struct __argv at entry+8
    u8 *magic = image_at(img, size, exec_entry + 4, dol);
    if (magic && !memcmp(magic, "_arg", 4)) {
        u32 *argv = exec_list + 1 + 3 * 64;                          // after room for 64 copy entries
        char *cmd = (char *)(argv + 8);
        int len = sprintf(cmd, "%s", spec) + 1;
        for (int i = 0; i < nargs; i++) {
            if (len + lens[i] + 2 > 16 * 1024) { sprintf(err, "arguments too long"); return -1; }
            memcpy(cmd + len, args[i], lens[i]);
            len += lens[i];
            cmd[len++] = 0;
        }
        cmd[len++] = 0;
        argv[0] = 0x5f617267; argv[1] = (u32)cmd; argv[2] = len; argv[3] = 0; argv[4] = 0; argv[5] = 0;
        if (list_add(exec_entry + 8, (u32)argv, 24, err)) return -1;
    }
    return 0;
}

// "path<TAB>arg<TAB>arg" (text arguments, as sent by the Mac's EXEC command)
static int exec_prepare(char *spec, char *err) {
    const char *args[16];
    int lens[16], n = 0;
    char *a = strchr(spec, '\t');
    if (a) *a++ = 0;
    while (a && *a && n < 16) {
        char *t = strchr(a, '\t');
        if (t) *t = 0;
        args[n] = a;
        lens[n++] = strlen(a);
        a = t ? t + 1 : NULL;
    }
    return exec_prepare_args(spec, args, lens, n, err);
}

// Nintendont's settings block (common/include/CommonConfig.h, NIN_CFG_VERSION 10), passed as argv[1] with the
// autoboot flag, the way WiiFlow starts GameCube games.
#define NINTENDONT_DOL "sd:/apps/nintendont/boot.dol"
typedef struct {
    u32 Magicbytes, Version, Config, VideoMode, Language;
    char GamePath[255], CheatPath[255];
    u32 MaxPads, GameID;
    u8 MemCardBlocks;
    s8 VideoScale, VideoOffset;
    u8 NetworkProfile;
    u32 WiiUGamepadSlot;
} nin_cfg_t;
_Static_assert(sizeof(nin_cfg_t) == 548, "NIN_CFG layout must match Nintendont");

// Last launch, so a quick return (a failed boot) can be retried and a normal return lands on the same game.
#define LAST_LAUNCH_FILE "sd:/arcade/last_launch.txt"
#define FAILED_BOOT_SECS 30
#define FAILURES_FILE "sd:/arcade/failures.tsv"   // <epoch>\t<key>: launches that came back twice in a row
#define AUTOHIDE_FILE "sd:/arcade/autohide.txt"   // catalog.c hides these; the Mac's health report lists them
#define AUTOHIDE_AFTER 2                          // failures (on separate occasions) before a game is hidden

static void note_launch(const game_t *g, int attempt) {
    store_printf(LAST_LAUNCH_FILE, "%ld %d %s\n", (long)time(NULL), attempt, g->rom[0] ? g->rom : g->id);
}

// A game that gave up after its retry: logged; the second time it's hidden (the card keeps it; the Mac reports it).
// Returns 1 when it was just hidden.
static int record_failure(const game_t *g) {
    const char *key = g->rom[0] ? g->rom : g->id;
    char line[96];
    snprintf(line, sizeof line, "%ld\t%s\n", (long)time(NULL), key);
    store_append(FAILURES_FILE, line);
    int count = 0;
    FILE *f = fopen(FAILURES_FILE, "r");
    char l[96], k[64];
    long t;
    while (f && fgets(l, sizeof l, f)) if (sscanf(l, "%ld\t%63s", &t, k) == 2 && !strcmp(k, key)) count++;
    if (f) fclose(f);
    if (count < AUTOHIDE_AFTER) return 0;
    char stem[64];
    snprintf(stem, sizeof stem, "%s", key);
    char *dot = strrchr(stem, '.');
    if (g->rom[0] && dot) *dot = 0;
    snprintf(line, sizeof line, "%s:%s\n", g->rom[0] ? "rom" : "id", stem);
    store_append(AUTOHIDE_FILE, line);
    netlog_now("auto-hid %s after %d failed starts", key, count);
    return 1;
}

// -> game index to retry now (or -1); *resume gets the index to select (or -1); *failed is set when giving up.
static long last_launch_age(void) {           // seconds since the last launch record, -1 if none
    FILE *f = store_open(LAST_LAUNCH_FILE);
    if (!f) return -1;
    long when = 0;
    int ok = fscanf(f, "%ld", &when) == 1;
    fclose(f);
    return ok ? (long)time(NULL) - when : -1;
}

static int check_last_launch(game_t *games, int n, int *resume, int *failed, int *attempt_out) {
    *resume = -1; *failed = 0;
    FILE *f = store_open(LAST_LAUNCH_FILE);
    if (!f) return -1;
    long when = 0;
    int attempt = 0;
    char id[16] = "";
    int ok = fscanf(f, "%ld %d %15s", &when, &attempt, id) == 3;
    fclose(f);
    remove(LAST_LAUNCH_FILE);
    { char tmp[64]; snprintf(tmp, sizeof tmp, "%s.new", LAST_LAUNCH_FILE); remove(tmp); }
    if (!ok) return -1;
    int gi = -1;
    for (int i = 0; i < n; i++) if (!strcmp(games[i].id, id) || !strcmp(games[i].rom, id)) { gi = i; break; }
    if (gi < 0) return -1;
    long ago = (long)time(NULL) - when;
    *resume = gi;
    {   // every return, on the card (boot tests read it; Wi-Fi may take minutes to come back): key, seconds away
        char rec[96];
        snprintf(rec, sizeof rec, "%s\t%ld\t%d\n", id, ago, attempt);
        store_append("sd:/arcade/returns.tsv", rec);
    }
    if (ago >= 0 && ago < FAILED_BOOT_SECS && !game_ran) {   // (our RetroArch says when the game did run)
        netlog_now("%s came back after %lds (attempt %d): %s", id, ago, attempt, attempt < 2 ? "retrying" : "giving up");
        if (attempt < 2) { *attempt_out = attempt + 1; return gi; }
        *failed = 1;
    } else {
        netlog("back from %s after %lds", id, ago);
    }
    return -1;
}

#define USBLOADER_GX_DOL "sd:/apps/usbloader_gx/boot.dol"
#define AUTOTEST_FILE "sd:/arcade/autotest"    // read by our RetroArch: quit after that many seconds of play
#define AUTOTEST_SECS 60
#define RETROARCH_DIR "sd:/apps/retroarch-wii"

static int file_exists(const char *path) {
    struct stat st;
    return stat(path, &st) == 0;
}

// Every system boots straight into the game, never into a loader's own menu:
//   GameCube: Nintendont with its settings block and the autoboot flag (as WiiFlow does)
//   Wii:      USB Loader GX "-sdmode=1 <GAMEID>" -> QuickGameBoot (games in sd:/wbfs)
//   arcade:   RetroArch's FB Alpha 2012 core with argv[1] = ROM folder, argv[2] = zip (RetroArch's Wii frontend)
static int launch_game(const game_t *g, char *err) {
    if (g->system == SYS_WII) {
        if (!file_exists(USBLOADER_GX_DOL)) { sprintf(err, "USB Loader GX is missing"); return -1; }
        const char *args[2] = { "-sdmode=1", g->id };
        int lens[2] = { (int)strlen(args[0]), (int)strlen(args[1]) };
        netlog("launching %s (%s) via USB Loader GX", g->title, g->id);
        return exec_prepare_args(USBLOADER_GX_DOL, args, lens, 2, err);
    }
    if (g->rom[0]) {                         // arcade: the core named in arcade.tsv
        char core[120], dir[200];
        snprintf(core, sizeof core, "%s/%s_libretro_wii.dol", RETROARCH_DIR, g->core);
        if (!file_exists(core)) { sprintf(err, "RetroArch core missing: %s", core); return -1; }
        snprintf(dir, sizeof dir, "%s", g->path);
        char *slash = strrchr(dir, '/');
        if (slash) *slash = 0;
        // Our RetroArch (videos/fastexit): argv[3..] = its loading screen's title and our CRT calibration, and whether we
        // were autobooted; on quit it starts us again directly (--relaunch=game), keeping AHBPROT. Stock RetroArch
        // reads only argv[1..2] and ignores the rest.
        char title_arg[96], screen_arg[48];
        int sx, sy, cx, cy;
        ui_get_calibration(&sx, &sy, &cx, &cy);
        snprintf(title_arg, sizeof title_arg, "--wiizard-title=%s", g->title);
        snprintf(screen_arg, sizeof screen_arg, "--wiizard-screen=%d,%d,%d,%d", sx, sy, cx, cy);
        // Continue (resume.h): our RetroArch loads the game's resume state, after checking it still matches
        int resume = resume_take_next() && !play_test && resume_available(g, NULL);
        const char *args[6] = { dir, g->rom, title_arg, screen_arg, NULL, NULL };
        int lens[6] = { (int)strlen(dir), (int)strlen(g->rom), (int)strlen(title_arg), (int)strlen(screen_arg), 0, 0 };
        int nargs = 4;
        if (resume) { args[nargs] = "--wiizard-resume"; lens[nargs] = (int)strlen(args[nargs]); nargs++; }
        if (autobooted) { args[nargs] = "--autobooted"; lens[nargs] = (int)strlen(args[nargs]); nargs++; }
        // Test mode (PLAYTEST, TESTQUEUE): our RetroArch quits by itself AUTOTEST_SECS after the game starts
        if (play_test) store_printf(AUTOTEST_FILE, "%d\n", AUTOTEST_SECS);
        else remove(AUTOTEST_FILE);
        netlog("launching %s (%s) via RetroArch%s%s", g->title, g->rom, play_test ? " (test)" : "", resume ? " (continue)" : "");
        u64 t0 = gettime();
        int rc = exec_prepare_args(core, args, lens, nargs, err);
        netlog("read %s in %u ms", core, (unsigned)ticks_to_millisecs(gettime() - t0));
        return rc;
    }
    static nin_cfg_t cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.Magicbytes = 0x01070CF6;
    cfg.Version = 10;
    cfg.Config = (1 << 7) | (1 << 3);        // NIN_CFG_AUTO_BOOT | NIN_CFG_MEMCARDEMU (memory cards on SD)
    if (play_test) cfg.Config |= 1u << 30;   // NIN_CFG_AUTOTEST (our Nintendont): back here after 40 s of play
    cfg.VideoMode = 0;                       // NIN_VID_AUTO: the game's own mode
    cfg.Language = 0xFFFFFFFF;               // NIN_LAN_AUTO
    const char *colon = strchr(g->path, ':');
    snprintf(cfg.GamePath, sizeof cfg.GamePath, "%s", colon ? colon + 1 : g->path);   // "/games/.../game.iso" on SD
    cfg.MaxPads = 4;
    memcpy(&cfg.GameID, g->id, 4);
    const char *args[1] = { (const char *)&cfg };
    int lens[1] = { sizeof cfg };
    netlog("launching %s (%s) via Nintendont, cfg %u bytes", g->title, g->id, (unsigned)sizeof cfg);
    return exec_prepare_args(NINTENDONT_DOL, args, lens, 1, err);
}

// AHBPROT (hardware access Nintendont and USB Loader GX need) survives an IOS reload only if ES is patched first.
// Done exactly as Priiloader does it (src/Shared/IOS.cpp, ReloadIOS/PatchIOS/AhbProtPatcher): 16-bit access to the
// MEM2 protection register 0x0d8b420a (0 = off, verified), search IOS's MEM2 from the pointer at 0x80003130 for the
// ES "TMD access rights" check, make it load 0xFF (li r3,0xFF), protection back on. Up to 0.9.3 this wrote the
// register with a 32-bit store at a 2-byte address and used the wrong patch: with AHBPROT really off that crashed.
#define HAVE_AHBPROT (*(vu32 *)0xCD800064 == 0xFFFFFFFF)
static inline u16 reg16(u32 a) { return *(vu16 *)(0xC0000000 | a); }
static inline void reg16_set(u32 a, u16 v) { *(vu16 *)(0xC0000000 | a) = v; asm volatile("eieio"); }
static int keep_ahbprot(void) {
    static const u8 pattern[] = { 0x68, 0x5B, 0x22, 0xEC, 0x00, 0x52, 0x18, 0x9B, 0x68, 0x1B, 0x46, 0x98, 0x07, 0xDB };
    if (!HAVE_AHBPROT) return 0;
    if (reg16(0x0d8b420a)) reg16_set(0x0d8b420a, 0);
    if (reg16(0x0d8b420a)) return -2;
    u8 *p = (u8 *)*(vu32 *)0xC0003130;       // the u32 at 0x80003130, read uncached
    if ((u32)p < 0x90000000 || (u32)p >= 0x93FFFFFF) { reg16_set(0x0d8b420a, 1); return -3; }
    u32 len = 0x93FFFFFF - (u32)p;
    DCFlushRange(p, len);
    ICInvalidateRange(p, len);
    int found = 0;
    for (; (u32)p < 0x93FFFFFF - sizeof pattern; p++) {
        if (p[0] != 0x68 || memcmp(p, pattern, sizeof pattern)) continue;
        p[8] = 0x23; p[9] = 0xFF;            // ldr r3,[r3] -> movs r3,#0xFF: the TMD "has" every access right
        u8 *line = (u8 *)((u32)p & ~31);
        DCFlushRange(line, 64);
        ICInvalidateRange(line, 64);
        found = 1;
        break;
    }
    reg16_set(0x0d8b420a, 1);
    return found;
}

// IOSPATCH: the d2x cIOS installer's in-memory patches to the running IOS (applyAhbProtPatchs in its libios.c), for
// reading title contents/tickets and installing a fakesigned title (CIOSINSTALL). Every match in IOS's MEM2 is
// patched; they last until the next IOS reload (any game or relaunch). Nothing is written to NAND.
struct ios_patch { const char *name; u8 orig[6]; u8 origlen; u8 repl[6]; u8 repllen; u8 offset; };
static const struct ios_patch IOS_PATCHES[] = {
    { "isfs_permissions", { 0x42, 0x8B, 0xD0, 0x01, 0x25, 0x66 }, 6, { 0x42, 0x8B, 0xE0, 0x01, 0x25, 0x66 }, 6, 0 },
    { "es_setuid",        { 0xD1, 0x2A, 0x1C, 0x39 }, 4, { 0x46, 0xC0 }, 2, 0 },
    { "es_identify",      { 0x28, 0x03, 0xD1, 0x23 }, 4, { 0x00, 0x00 }, 2, 2 },
    { "hash_check",       { 0x20, 0x07, 0x23, 0xA2 }, 4, { 0x00 }, 1, 1 },
    { "new_hash_check",   { 0x20, 0x07, 0x4B, 0x0B }, 4, { 0x00 }, 1, 1 },
    { "es_version",       { 0xD2, 0x01, 0x4E, 0x56 }, 4, { 0xE0 }, 1, 0 },
};
static int ios_patch(char *out, int size) {
    if (!HAVE_AHBPROT) { snprintf(out, size, "no AHBPROT"); return -1; }
    if (reg16(0x0d8b420a)) reg16_set(0x0d8b420a, 0);
    if (reg16(0x0d8b420a)) { snprintf(out, size, "MEM2 protection stayed on"); return -2; }
    u8 *start = (u8 *)0x93400000, *end = (u8 *)0x94000000;
    DCFlushRange(start, end - start);
    int n = 0, total = 0;
    out[0] = 0;
    for (int k = 0; k < (int)(sizeof IOS_PATCHES / sizeof IOS_PATCHES[0]); k++) {
        const struct ios_patch *pt = &IOS_PATCHES[k];
        int hits = 0;
        for (u8 *p = start; p < end - 8; p++) {
            if (p[0] != pt->orig[0] || memcmp(p, pt->orig, pt->origlen)) continue;
            memcpy(p + pt->offset, pt->repl, pt->repllen);
            u8 *line = (u8 *)((u32)(p + pt->offset) & ~31);
            DCFlushRange(line, 64);
            ICInvalidateRange(line, 64);
            hits++;
        }
        total += hits;
        if (n < size) n += snprintf(out + n, size - n, "%s%s=%d", k ? " " : "", pt->name, hits);
    }
    reg16_set(0x0d8b420a, 1);
    return total;
}

// CIOSINSTALL <dir>: install the title prepared in <dir> on the card (by cios/build_cios.py on the Mac): tik (signed
// ticket), tmd (signed TMD) and <index>.app per TMD content, already encrypted with the title key. Certificates are
// the console's own /sys/cert.sys. Needs IOSPATCH first (fakesigned ticket/TMD, downgrade). On any error the title
// install is cancelled, which leaves the installed title as it was.
static u8 *read_card_file(const char *path, u32 *len) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    u8 *b = memalign(32, (n + 31) & ~31);
    if (b && fread(b, 1, n, f) != (size_t)n) { free(b); b = NULL; }
    fclose(f);
    if (b) *len = n;
    return b;
}
static u8 *read_nand_file(const char *path, u32 *len) {
    static char np[ISFS_MAXPATH] ATTRIBUTE_ALIGN(32);
    static fstats st ATTRIBUTE_ALIGN(32);
    snprintf(np, sizeof np, "%s", path);
    s32 fd = ISFS_Open(np, ISFS_OPEN_READ);
    if (fd < 0) return NULL;
    u8 *b = NULL;
    if (ISFS_GetFileStats(fd, &st) >= 0 && (b = memalign(32, (st.file_length + 31) & ~31)) &&
        ISFS_Read(fd, b, st.file_length) != (s32)st.file_length) { free(b); b = NULL; }
    ISFS_Close(fd);
    if (b) *len = st.file_length;
    return b;
}
static void cmd_ciosinstall(conn_t *c, const char *dir) {
    char path[256];
    u32 tik_len = 0, tmd_len = 0, cert_len = 0;
    snprintf(path, sizeof path, "%s/tik", dir);
    u8 *tik = read_card_file(path, &tik_len);
    snprintf(path, sizeof path, "%s/tmd", dir);
    u8 *tmdb = read_card_file(path, &tmd_len);
    u8 *cert = read_nand_file("/sys/cert.sys", &cert_len);
    s32 r = 0;
    if (!tik || !tmdb || !cert) { sendf(c, "ERR missing %s%s%s\n", tik ? "" : "tik ", tmdb ? "" : "tmd ", cert ? "" : "cert.sys"); goto out; }
    tmd *t = (tmd *)SIGNATURE_PAYLOAD((signed_blob *)tmdb);
    netlog_now("cios: installing %016llx v%u, %u contents from %s", t->title_id, t->title_version, t->num_contents, dir);
    r = ES_AddTicket((signed_blob *)tik, tik_len, (signed_blob *)cert, cert_len, NULL, 0);
    netlog_now("cios: ES_AddTicket = %d", (int)r);
    if (r < 0) { sendf(c, "ERR ES_AddTicket %d\n", (int)r); goto out; }
    r = ES_AddTitleStart((signed_blob *)tmdb, tmd_len, (signed_blob *)cert, cert_len, NULL, 0);
    netlog_now("cios: ES_AddTitleStart = %d", (int)r);
    if (r < 0) { sendf(c, "ERR ES_AddTitleStart %d\n", (int)r); goto out; }
    tmd_content *tc = TMD_CONTENTS(t);
    for (int i = 0; i < t->num_contents && r >= 0; i++) {
        u32 len = 0;
        snprintf(path, sizeof path, "%s/%d.app", dir, tc[i].index);
        u8 *data = read_card_file(path, &len);
        if (!data) { r = -1000; netlog_now("cios: %s missing", path); break; }
        s32 cfd = ES_AddContentStart(t->title_id, tc[i].cid);
        if (cfd < 0) { r = cfd; netlog_now("cios: ES_AddContentStart(%08x) = %d", tc[i].cid, (int)cfd); free(data); break; }
        for (u32 off = 0; off < len && r >= 0; off += 0x4000) {
            u32 n = len - off < 0x4000 ? len - off : 0x4000;
            r = ES_AddContentData(cfd, data + off, n);
        }
        s32 f = ES_AddContentFinish(cfd);
        netlog_now("cios: content %d cid %08x %u bytes: data %d finish %d", i, tc[i].cid, len, (int)r, (int)f);
        if (r >= 0) r = f;
        free(data);
    }
    if (r >= 0) {
        r = ES_AddTitleFinish();
        netlog_now("cios: ES_AddTitleFinish = %d", (int)r);
    }
    if (r < 0) { ES_AddTitleCancel(); netlog_now("cios: cancelled (%d)", (int)r); sendf(c, "ERR install failed %d (cancelled)\n", (int)r); }
    else sendf(c, "OK installed %016llx v%u\n", t->title_id, t->title_version);
out:
    free(tik); free(tmdb); free(cert);
}

static void exec_jump(void) {
    u8 *stub = (u8 *)exec_list + 32 * 1024;
    u32 n = booter_end - booter_start;
    memcpy(stub, booter_start, n);
    DCFlushRange(exec_area, EXEC_RESERVE);
    ICInvalidateRange(stub, n);
    IOS_ReloadIOS(IOS_GetVersion());        // (ES already patched in leave: if AHBPROT is off, it stays off)        // the program starts on a freshly reset IOS (network, USB, ...)
    SYS_ResetSystem(SYS_SHUTDOWN, 0, 0);
    u32 level;
    _CPU_ISR_Disable(level);
    ((void (*)(u32 *, u32))stub)(exec_list, exec_entry);
}

// GameCube (Nintendont) and Wii (USB Loader GX) games need AHBPROT. Back from our RetroArch directly we normally
// still have it (RetroArch patches ES like keep_ahbprot before its IOS reload). If not, the slow path always restores
// it: a pending-launch record, then System Menu -> Priiloader (AHBPROT on) -> hop -> launcher, which starts the game
// by itself (check_pending). sd:/arcade/test_no_ahbprot (removed when read) pretends AHBPROT is missing (simulator).
#define PENDING_FILE "sd:/arcade/pending_launch.txt"
#define PENDING_MAX_SECS 600                  // older: a power cut on the way; just the menu
#define NO_AHBPROT_TEST_FILE "sd:/arcade/test_no_ahbprot"
static int fake_no_ahbprot;
static int ahbprot_ok(void) { return HAVE_AHBPROT && !fake_no_ahbprot; }
static int needs_ahbprot(const game_t *g) { return !g->rom[0]; }

static int slow_path_for(const game_t *g) {
    if (!needs_ahbprot(g) || ahbprot_ok() || !sd_ok) return 0;
    const char *key = g->rom[0] ? g->rom : g->id;
    store_printf(PENDING_FILE, "%ld %d %s\n", (long)time(NULL), play_test, key);
    netlog_now("no AHBPROT for %s (%s): restarting through Priiloader, it starts at the next launch", g->title, key);
    u64 t0 = gettime();
    for (float t = 0; t < 1.2f; t = ticks_to_millisecs(gettime() - t0) / 1000.0f)
        ui_term_frame(g->system == SYS_WII ? "> PREPARING WII..." : "> PREPARING GAMECUBE...", "  RESTARTING THE CONSOLE", t);
    request = REQ_MENU;                       // SYS_RETURNTOMENU: System Menu -> Priiloader autoboot -> hop -> us
    return 1;
}

static int pending_exists(void) {
    struct stat st;
    return sd_ok && stat(PENDING_FILE, &st) == 0;
}

// -> the game the slow path restarted for (and *test = it was a test launch), or -1. The record is used once.
static int check_pending(game_t *games, int n, int *test) {
    FILE *f = store_open(PENDING_FILE);
    if (!f) return -1;
    long when = 0;
    int t = 0;
    char key[64] = "";
    int ok = fscanf(f, "%ld %d %63s", &when, &t, key) == 3;
    fclose(f);
    remove(PENDING_FILE);
    { char tmp[64]; snprintf(tmp, sizeof tmp, "%s.new", PENDING_FILE); remove(tmp); }
    if (!ok) return -1;
    long ago = (long)time(NULL) - when;
    int gi = -1;
    for (int i = 0; i < n; i++) if (!strcmp(games[i].id, key) || !strcmp(games[i].rom, key)) { gi = i; break; }
    if (gi < 0 || ago < -60 || ago > PENDING_MAX_SECS) { netlog_now("pending launch %s dropped (%lds old)", key, ago); return -1; }
    if (!ahbprot_ok()) {                      // the slow path didn't bring it back either: don't loop
        netlog_now("pending launch %s: still no AHBPROT after the restart; giving up", key);
        ui_notice("Couldn't start this game", games[gi].title);
        ui_resume(gi);
        return -1;
    }
    netlog_now("pending launch %s after %lds (AHBPROT back)", key, ago);
    *test = t;
    return gi;
}

// The program is read from the card while the loading card is on screen (it used to be read afterwards, in the
// dark): a 15 MB RetroArch DOL takes seconds on the Wii's SD interface.
static const game_t *prep_game;
static volatile int prep_rc;
static char prep_err[160];
static void *prep_thread(void *unused) {
    prep_rc = launch_game(prep_game, prep_err);
    return NULL;
}
static int prepare_while_loading(const game_t *g, char *err) {
    lwp_t th = LWP_THREAD_NULL;
    prep_game = g;
    prep_rc = -1;
    prep_err[0] = 0;
    u64 t0 = gettime();
    if (LWP_CreateThread(&th, prep_thread, NULL, NULL, 64 * 1024, 40) < 0) th = LWP_THREAD_NULL;
    ui_show_loading(g);
    u64 t1 = gettime();
    if (th != LWP_THREAD_NULL) LWP_JoinThread(th, NULL);
    else prep_thread(NULL);
    netlog("loading card %u ms, program ready %u ms after it", (unsigned)ticks_to_millisecs(t1 - t0),
           (unsigned)ticks_to_millisecs(gettime() - t1));
    snprintf(err, 160, "%s", prep_err);
    return prep_rc;
}

// ---------------------------------------------------------------- NAND

static u8 nandbuf[CHUNK] ATTRIBUTE_ALIGN(32);
static char nandpath[ISFS_MAXPATH] ATTRIBUTE_ALIGN(32);

static void cmd_nls(conn_t *c, const char *path) {
    static char names[64 * 13] ATTRIBUTE_ALIGN(32);
    u32 num = 0;
    snprintf(nandpath, sizeof nandpath, "%s", path);
    s32 r = ISFS_ReadDir(nandpath, NULL, &num);
    if (r < 0) { sendf(c, "ERR ISFS_ReadDir %d\n", r); return; }
    if (num > 64) num = 64;
    r = ISFS_ReadDir(nandpath, names, &num);
    if (r < 0) { sendf(c, "ERR ISFS_ReadDir %d\n", r); return; }
    char *p = names;
    for (u32 i = 0; i < num; i++) { sendf(c, "N %s\n", p); p += strlen(p) + 1; }
    sendf(c, "OK %u\n", num);
}

static void cmd_nget(conn_t *c, const char *path) {
    snprintf(nandpath, sizeof nandpath, "%s", path);
    s32 fd = ISFS_Open(nandpath, ISFS_OPEN_READ);
    if (fd < 0) { sendf(c, "ERR ISFS_Open %d\n", fd); return; }
    static fstats st ATTRIBUTE_ALIGN(32);
    if (ISFS_GetFileStats(fd, &st) < 0) { ISFS_Close(fd); sendf(c, "ERR ISFS_GetFileStats\n"); return; }
    sendf(c, "OK %u\n", st.file_length);
    u32 left = st.file_length;
    while (left) {
        u32 n = left > CHUNK ? CHUNK : left;
        s32 r = ISFS_Read(fd, nandbuf, n);
        if (r <= 0) break;
        send_all(c, nandbuf, r);
        left -= r;
    }
    ISFS_Close(fd);
}

// Overwrites an existing NAND file in place from offset 0 (ISFS can't create or shrink files without permissions we
// don't have; trailing old bytes stay). The new data may not be longer than the file. OK <size> once all is written.
static void cmd_nput(conn_t *c, char *args) {
    char *path = strchr(args, ' ');
    if (!path) { sendf(c, "ERR usage: NPUT <size> <path>\n"); return; }
    *path++ = 0;
    u32 size = atol(args), left = size;
    int allowed = 0;
    for (int i = 0; ALLOWED_NAND_WRITES[i]; i++) allowed |= !strcmp(path, ALLOWED_NAND_WRITES[i]);
    s32 fd = -1;
    const char *err = allowed ? NULL : "NAND path not in the allowed list";
    static fstats st ATTRIBUTE_ALIGN(32);
    if (!err) {
        snprintf(nandpath, sizeof nandpath, "%s", path);
        fd = ISFS_Open(nandpath, ISFS_OPEN_RW);
        if (fd < 0) err = "ISFS_Open failed";
        else if (ISFS_GetFileStats(fd, &st) < 0) err = "ISFS_GetFileStats failed";
        else if (size > st.file_length) err = "new data is longer than the existing file";
        else if (ISFS_Seek(fd, 0, SEEK_SET) < 0) err = "ISFS_Seek failed";
    }
    while (left) {                           // always drain the payload so the protocol stays in step
        u32 n = left > CHUNK ? CHUNK : left;
        if (read_exact(c, nandbuf, n) < 0) { if (fd >= 0) ISFS_Close(fd); return; }
        if (!err && ISFS_Write(fd, nandbuf, n) != (s32)n) err = "ISFS_Write failed";
        left -= n;
    }
    if (fd >= 0) ISFS_Close(fd);
    if (err) { sendf(c, "ERR %s (%d)\n", err, fd); return; }
    netlog("NAND write %s: %u bytes", path, size);
    sendf(c, "OK %u\n", size);
}

// ---------------------------------------------------------------- wired (our own ASIX driver + lwIP)
//   ETH STAT | ETH SNIFF  (the last 16 frames received)
static char eth_seen[16][80];
static volatile int eth_seen_n;
static void eth_sniff(const u8 *f, int len) {
    int i = eth_seen_n++ % 16;
    snprintf(eth_seen[i], sizeof eth_seen[i], "%02x:%02x:%02x:%02x:%02x:%02x > %02x:%02x:%02x:%02x:%02x:%02x %04x %d",
             f[6], f[7], f[8], f[9], f[10], f[11], f[0], f[1], f[2], f[3], f[4], f[5], f[12] << 8 | f[13], len);
}

static void cmd_eth(conn_t *c, char *arg) {
    char msg[320];
    if (!strncmp(arg, "STAT", 4)) {
        lwnet_status(msg, sizeof msg);
        sendf(c, "OK %s\n", msg);
    } else if (!strncmp(arg, "SNIFF", 5)) {
        int n = eth_seen_n, from = n > 16 ? n - 16 : 0;
        for (int i = from; i < n; i++) sendf(c, "F %s\n", eth_seen[i % 16]);
        sendf(c, "OK %d\n", n);
    } else if (!strncmp(arg, "MDIO ", 5)) {   // ETH MDIO <reg>
        sendf(c, "OK %04x\n", eth_mdio_read(atoi(arg + 5)) & 0xffff);
    } else if (!strncmp(arg, "CMD ", 4)) {    // ETH CMD <in 0|1> <cmd> <value> <index> <len> [hex bytes]: raw vendor request
        int in = 0, cmd = 0, value = 0, index = 0, len = 0;
        char hex[80] = "";
        sscanf(arg + 4, "%i %i %i %i %i %79s", &in, &cmd, &value, &index, &len, hex);
        u8 d[32] = { 0 };
        for (int i = 0; i < len && i < 32 && hex[2 * i] && hex[2 * i + 1]; i++) { unsigned v; sscanf(hex + 2 * i, "%2x", &v); d[i] = v; }
        int r = eth_vendor(in, cmd, value, index, len, d);
        char out[80] = "";
        for (int i = 0; in && i < len && i < 32; i++) snprintf(out + 2 * i, sizeof out - 2 * i, "%02x", d[i]);
        sendf(c, "OK r=%d %s\n", r, out);
    } else sendf(c, "ERR usage: ETH STAT|SNIFF|MDIO <reg>|CMD <in> <cmd> <value> <index> <len> [hex]\n");
}

static void handle(conn_t *c, char *line) {
    char *arg = strchr(line, ' ');
    if (arg) *arg++ = 0; else arg = "";
    snprintf(last_cmd, sizeof last_cmd, "%s %.80s", line, arg);
    last_activity = gettime();
    last_net_ok = gettime();
    if (!strcmp(line, "INFO") || !strcmp(line, "PING")) {
        u32 up = ticks_to_secs(gettime() - boot_ticks);
        sendf(c, "OK agent=%s id=%u ip=%s ios=%d sd=%d usb=%d fb=%dx%d tv=%d uptime=%u ahbprot=%d hbc=%d caps=exec,nand,screen,putat,log%s autobooted=%d cab=%s mode=%s idle=%d update=%s\n", AGENT_VERSION,
              device_id, ip, IOS_GetVersion(), sd_ok, usb_ok, rmode->fbWidth, rmode->xfbHeight, CONF_GetVideo(), up,
              *(vu32 *)0xCD800064 == 0xFFFFFFFF, from_hbc(), safe_mode ? ",safe" : "", autobooted, cab.name,
              safe_mode ? "safe" : ui_mode_name(), (int)ui_idle_secs(), update_status());
    } else if (!strcmp(line, "LS")) cmd_ls(c, arg);
    else if (!strcmp(line, "GET")) cmd_get(c, arg);
    else if (!strcmp(line, "PUT")) cmd_put(c, arg);
    else if (!strcmp(line, "PUTAT")) cmd_putat(c, arg);
    else if (!strcmp(line, "COMMIT")) cmd_commit(c, arg);
    else if (!strcmp(line, "STAT")) {
        struct stat st;
        if (stat(arg, &st) == 0) sendf(c, "OK %lld\n", (long long)st.st_size); else sendf(c, "ERR %s\n", strerror(errno));
    }
    else if (!strcmp(line, "RM")) {
        if (remove(arg) == 0 || rmdir(arg) == 0) sendf(c, "OK\n"); else sendf(c, "ERR %s\n", strerror(errno));
    } else if (!strcmp(line, "MKDIR")) { mkdirs(arg); sendf(c, "OK\n"); }
    else if (!strcmp(line, "MV")) {
        char *dst = strchr(arg, '\t');
        if (!dst) { sendf(c, "ERR usage: MV <src>\\t<dst>\n"); return; }
        *dst++ = 0;
        if (rename(arg, dst) == 0) sendf(c, "OK\n"); else sendf(c, "ERR %s\n", strerror(errno));
    } else if (!strcmp(line, "DF")) {
        struct statvfs v;
        if (statvfs(*arg ? arg : "sd:/", &v) != 0) { sendf(c, "ERR %s\n", strerror(errno)); return; }
        sendf(c, "OK %llu %llu\n", (unsigned long long)v.f_bfree * v.f_bsize, (unsigned long long)v.f_blocks * v.f_bsize);
    } else if (!strcmp(line, "SHOT")) cmd_shot(c);
    else if (!strcmp(line, "PAD")) {
        u32 buttons = strtoul(arg, &arg, 16);
        u32 ms = strtoul(arg, NULL, 10);
        virt_buttons = buttons;
        virt_until = gettime() + millisecs_to_ticks(ms ? ms : 150);
        sendf(c, "OK\n");
    } else if (!strcmp(line, "EXEC")) {
        char err[160];
        if (exec_prepare(arg, err) < 0) sendf(c, "ERR %s\n", err);
        else { sendf(c, "OK entry=%08x ranges=%u\n", exec_entry, exec_list[0]); request = REQ_EXEC; }
    }
    else if (!strcmp(line, "SCREEN")) {
        int sx, sy, x, y;
        if (sscanf(arg, "%d %d %d %d", &sx, &sy, &x, &y) == 4) ui_set_calibration(sx, sy, x, y, 1);
        else if (sscanf(arg, "%d %d %d", &sx, &x, &y) == 3) ui_set_calibration(sx, sx, x, y, 1);
        ui_get_calibration(&sx, &sy, &x, &y);
        sendf(c, "OK %d %d %d %d\n", sx, sy, x, y);
    }
    else if (!strcmp(line, "CLOCK")) {
        long off = atol(arg) - (long)time(NULL);
        if (labs(off - cab.clock_offset) > 120) { cab.clock_offset = off; cab_save(); }   // card write only on a change
        sendf(c, "OK %ld\n", cab.clock_offset);
    }
    else if (!strcmp(line, "GAMES")) {
        for (int i = 0; i < lib_count; i++)
            sendf(c, "%d\t%s\t%s\t%s\n", i, system_name(lib_games[i].system),
                  lib_games[i].rom[0] ? lib_games[i].rom : lib_games[i].id, lib_games[i].title);
        sendf(c, "OK %d\n", lib_count);
    }
    else if (!strcmp(line, "PLAY") || !strcmp(line, "PLAYTEST") || !strcmp(line, "PLAYRESUME")) {
        play_test = !strcmp(line, "PLAYTEST");
        resume_set_next(!strcmp(line, "PLAYRESUME"));   // Continue the saved game (resume.h); ignored without one
        int gi = -1;
        char *end;
        long n = strtol(arg, &end, 10);
        if (*arg && !*end && n >= 0 && n < lib_count) gi = n;
        for (int i = 0; gi < 0 && i < lib_count; i++)
            if (!strcasecmp(lib_games[i].id, arg) || !strcasecmp(lib_games[i].rom, arg)) gi = i;
        if (gi < 0) sendf(c, "ERR no such game: %s\n", arg);
        else { sendf(c, "OK %s\n", lib_games[gi].title); play_request = gi; }
    }
    else if (!strcmp(line, "TESTQUEUE")) {
        char buf[4096];
        int len = 0, n = 0;
        for (char *save, *t = strtok_r(arg, " \t", &save); t && len < (int)sizeof buf - 40; t = strtok_r(NULL, " \t", &save), n++)
            len += snprintf(buf + len, sizeof buf - len, "%s\n", t);
        if (n) { store_write(TEST_QUEUE_FILE, buf, len); test_queue = 1; }
        else {                               // stop: and no test mode left over for the next game a person starts
            remove(TEST_QUEUE_FILE); remove(AUTOTEST_FILE);
            test_queue = play_test = 0;
        }
        netlog_now("test queue: %d games", n);
        sendf(c, "OK %d\n", n);
    }
    else if (!strcmp(line, "LOG")) cmd_log(c);
    else if (!strcmp(line, "ETH")) cmd_eth(c, arg);
    else if (!strcmp(line, "IOSPATCH")) {
        char out[200];
        int r = ios_patch(out, sizeof out);
        netlog_now("iospatch: %d (%s)", r, out);
        sendf(c, r < 0 ? "ERR %s\n" : "OK %s\n", out);
    }
    else if (!strcmp(line, "CIOSINSTALL")) cmd_ciosinstall(c, arg);
    else if (!strcmp(line, "NLS")) cmd_nls(c, arg);
    else if (!strcmp(line, "NGET")) cmd_nget(c, arg);
    else if (!strcmp(line, "NPUT")) cmd_nput(c, arg);
    else if (!strcmp(line, "UPDATE")) { sendf(c, "OK\n"); update_now = 1; }
    else if (!strcmp(line, "HBC")) { sendf(c, "OK\n"); request = REQ_HBC; }
    else if (!strcmp(line, "MENU")) { sendf(c, "OK\n"); request = REQ_MENU; }
    else if (!strcmp(line, "REBOOT")) { sendf(c, "OK\n"); request = REQ_REBOOT; }
    else if (!strcmp(line, "OFF")) { sendf(c, "OK\n"); request = REQ_OFF; }
    else sendf(c, "ERR unknown command %s\n", line);
}

static volatile int link_dead;               // set by the network thread, acted on by main()
static int link_fails;
static u32 home_addr;                        // network order; 0 = unknown

static void load_home(void) {
    FILE *f = sd_ok ? fopen(HOME_FILE, "r") : NULL;
    char line[32] = "";
    if (f) { fgets(line, sizeof line, f); fclose(f); }
    struct in_addr a;
    home_addr = (line[0] && inet_aton(line, &a)) ? a.s_addr : 0;
}

// Outbound UDP to the gateway, the subnet broadcast and the Mac: the Wii's Wi-Fi stops answering incoming traffic
// after a while unless it sends something itself.
static void heartbeat(s32 us) {
    char msg[96];
    int n = snprintf(msg, sizeof msg, "WIIAGENT %s %u %s", AGENT_VERSION, device_id, ip);
    u32 self = inet_addr(ip);                // network order
    u32 targets[3] = { (self & htonl(0xFFFFFF00)) | htonl(1), self | htonl(0xFF), home_addr };
    for (int i = 0; i < 3; i++) {
        if (!targets[i]) continue;
        struct sockaddr_in to = { .sin_family = AF_INET, .sin_port = htons(HEARTBEAT_PORT) };
        to.sin_addr.s_addr = targets[i];
        net_sendto(us, msg, n, 0, (struct sockaddr *)&to, sizeof to);
    }
}

// TCP connect to the router's DNS port (non-blocking, polled like ftpii): 1 = reachable, 0 = not.
static int link_ok(void) {
    s32 t = net_socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (t < 0) return 0;
    set_blocking(t, false);
    struct sockaddr_in gw = { .sin_family = AF_INET, .sin_port = htons(53) };
    gw.sin_addr.s_addr = (inet_addr(ip) & htonl(0xFFFFFF00)) | htonl(1);
    int ok = 0;
    for (int i = 0; i < 40; i++) {          // up to ~4 s
        s32 r = net_connect(t, (struct sockaddr *)&gw, sizeof gw);
        if (r >= 0 || r == -EISCONN) { ok = 1; break; }
        if (r != -EINPROGRESS && r != -EALREADY && r != -EAGAIN) break;
        usleep(100 * 1000);
    }
    net_close(t);
    return ok;
}

static void *server(void *unused) {
    s32 ls = net_socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    struct sockaddr_in addr = { .sin_family = AF_INET, .sin_port = htons(AGENT_PORT), .sin_addr.s_addr = INADDR_ANY };
    if (ls < 0 || net_bind(ls, (struct sockaddr *)&addr, sizeof addr) < 0 || net_listen(ls, 2) < 0) {
        snprintf(last_cmd, sizeof last_cmd, "listen failed (%d)", ls);
        netlog_now("server: listen failed (socket %d)", ls);
        return NULL;
    }
    set_blocking(ls, false);                 // poll accept so the thread can stop when we exit
    s32 us = net_socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    u64 last_beat = 0, last_check = gettime();
    load_home();
    static conn_t c;
    char line[600];
    while (!quitting) {
        struct sockaddr_in peer;
        u32 plen = sizeof peer;
        s32 s = net_accept(ls, (struct sockaddr *)&peer, &plen);
        if (s < 0) {
            if (us >= 0 && ticks_to_millisecs(gettime() - last_beat) >= HEARTBEAT_MS) { heartbeat(us); last_beat = gettime(); }
            if (ticks_to_millisecs(gettime() - last_check) >= LINK_CHECK_MS &&
                ticks_to_millisecs(gettime() - last_activity) >= 60000) {
                last_check = gettime();
                if (link_ok()) {
                    last_net_ok = gettime();
                    if (link_fails) netlog("router reachable again after %d failed checks", link_fails);
                    link_fails = 0;
                } else {
                    netlog("router unreachable (check %d)", ++link_fails);
                    if (link_fails >= LINK_FAILS_RELAUNCH) link_dead = 1;
                }
            }
            usleep(50 * 1000);
            continue;
        }
        set_blocking(s, false);              // reads/writes time out instead of hanging (io_timed)
        c.s = s; c.len = c.pos = 0;
        clients_served++;
        client_open = 1;
        while (!quitting && request == REQ_NONE && read_line(&c, line, sizeof line) >= 0) {
            if (!strcmp(line, "QUIT")) break;
            if (line[0]) handle(&c, line);
        }
        net_close(s);
        client_open = 0;
        last_activity = gettime();
    }
    if (us >= 0) net_close(us);
    net_close(ls);
    return NULL;
}

// The log lives in RAM (LOG reads it) and goes to sd:/apps/wii-agent/agent.log only every few minutes, before
// leaving for a game, and right away for events that matter after a crash or power cut (netlog_now). Writing every
// line straight to the card (as up to 0.7) meant a card write every 2 s: wear, and a power cut mid-write can
// damage the FAT. The card copy is capped: past LOG_MAX it becomes agent.old.log.
#define LOG_FILE "sd:/apps/wii-agent/agent.log"
#define LOG_OLD "sd:/apps/wii-agent/agent.old.log"
#define LOG_RING (32 * 1024)
#define LOG_MAX (256 * 1024)
#define LOG_FLUSH_MS (10 * 60 * 1000)
static char log_ring[LOG_RING];
static u32 log_head, log_flushed;            // bytes written in total / up to here on the card
static mutex_t log_lock = LWP_MUTEX_NULL;
static u64 log_last_flush;

static void log_flush(void) {
    if (!sd_ok || log_lock == LWP_MUTEX_NULL) return;
    LWP_MutexLock(log_lock);
    u32 from = log_flushed, to = log_head;
    if (to - from > LOG_RING) from = to - LOG_RING;
    static char out[LOG_RING];
    u32 n = 0;
    for (u32 i = from; i < to; i++) out[n++] = log_ring[i % LOG_RING];
    log_flushed = to;
    LWP_MutexUnlock(log_lock);
    log_last_flush = gettime();
    if (!n) return;
    struct stat st;
    if (stat(LOG_FILE, &st) == 0 && st.st_size > LOG_MAX) { remove(LOG_OLD); rename(LOG_FILE, LOG_OLD); }
    mkdir("sd:/apps", 0777);
    mkdir("sd:/apps/wii-agent", 0777);
    FILE *f = fopen(LOG_FILE, "a");
    if (!f) return;
    fwrite(out, 1, n, f);
    fflush(f);
    fsync(fileno(f));
    fclose(f);
}

static void vlog(int now, const char *fmt, va_list ap) {
    char line[768];                          // (the wired driver's start-up line lists every step)
    int n = snprintf(line, sizeof line, "[%u %s] ", (unsigned)ticks_to_secs(gettime() - boot_ticks), AGENT_VERSION);
    n += vsnprintf(line + n, sizeof line - n - 1, fmt, ap);
    if (n > (int)sizeof line - 2) n = sizeof line - 2;
    line[n++] = '\n';
    LWP_MutexLock(log_lock);
    for (int i = 0; i < n; i++) log_ring[log_head++ % LOG_RING] = line[i];
    LWP_MutexUnlock(log_lock);
    if (now) log_flush();
}

static void netlog(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vlog(0, fmt, ap);
    va_end(ap);
}

static void netlog_now(const char *fmt, ...) {   // and write it to the card right away
    va_list ap;
    va_start(ap, fmt);
    vlog(1, fmt, ap);
    va_end(ap);
}

static void cmd_log(conn_t *c) {
    LWP_MutexLock(log_lock);
    u32 from = log_head > LOG_RING ? log_head - LOG_RING : 0, to = log_head;
    static char out[LOG_RING];
    u32 n = 0;
    for (u32 i = from; i < to; i++) out[n++] = log_ring[i % LOG_RING];
    LWP_MutexUnlock(log_lock);
    send_all(c, out, n);
    sendf(c, "OK %u\n", n);
}

// Updates: a thread of its own, so the server stays responsive. First check a minute after the network is up, then
// every UPDATE_EVERY_SECS; files are fetched only while the cabinet sits idle in attract mode.
#define UPDATE_EVERY_SECS (3 * 3600)
static int update_may_continue(void) {
    if (update_now) return !quitting && net_up && !safe_mode && !client_open;
    return !quitting && net_up && !safe_mode && ui_in_attract() && ui_idle_secs() > 60 && !client_open;
}
static void *updater(void *unused) {
    u64 last = 0;
    while (!quitting) {
        usleep(5 * 1000 * 1000);
        if (!net_up || safe_mode || selftest) continue;
        if (!update_now && last && ticks_to_secs(gettime() - last) < UPDATE_EVERY_SECS) continue;
        if ((!update_now && ticks_to_secs(gettime() - boot_ticks) < 60) || !update_may_continue()) continue;
        if (update_now) netlog_now("update: pushed");
        int r = update_run(update_may_continue, netlog_now);
        update_now = 0;
        last = gettime();
        if (r < 0) last -= secs_to_ticks(UPDATE_EVERY_SECS - 300);   // server not reached: try again in 5 min
    }
    return NULL;
}

// Joins Wi-Fi (the console's own connection settings, DHCP) and serves clients; starts over if the network drops.
// Retries back off (5, 10, 20, 40, then every 60 s): Wi-Fi and the SD card share the IOS, and a tight retry loop
// on dead Wi-Fi made the menu and the attract clips crawl.
static void net_backoff(int fails) {
    int secs = fails <= 0 ? 0 : fails >= 5 ? 60 : 5 << (fails - 1);
    for (int i = 0; i < secs * 10 && !quitting; i++) usleep(100 * 1000);
}
static volatile int scan_done;               // (main) the library is loaded
static void *network(void *unused) {
    int fails = 0;
    // The menu first: Wi-Fi and the SD card share the IOS, and a Wi-Fi join timing out (dead Wi-Fi: ~11 s each)
    // stretched the library load at every start and every return from a game from ~1 s to ~9 s.
    for (int i = 0; i < 200 && !scan_done && !quitting; i++) usleep(100 * 1000);
    int wired = 0;                           // 1 = our driver and lwIP are running, -1 = couldn't start them
    while (!quitting) {
        s32 r;
        // Wired first when an ASIX adapter is plugged in: our own driver (IOS's can't run cab1's), lwIP, DHCP.
        // DHCP keeps going in the background, so a Wi-Fi round below doesn't stop the cable from coming up.
        if (!wired && eth_present(NULL)) {
            char m[700];
            wired = lwnet_start(m, sizeof m) ? -1 : 1;
            netlog_now("wired: %s%s", wired > 0 ? "adapter up, " : "couldn't start: ", m);
            if (wired > 0) lwnet_sniff_hook(eth_sniff);
        }
        if (wired > 0) {
            u32 a = 0;
            int wait = net_tries ? 5 : 20;
            for (int i = 0; i < wait * 10 && !quitting && !(a = lwnet_ip()); i++) usleep(100 * 1000);
            if (a) {
                net_tries++;
                netx_wired = 1;
                snprintf(ip, sizeof ip, "%u.%u.%u.%u", a >> 24, (a >> 16) & 255, (a >> 8) & 255, a & 255);
                net_up = 1;
                fails = 0;
                netlog_now("up %s (wired) after %us, attempt %d, router %s", ip,
                           (unsigned)ticks_to_secs(gettime() - boot_ticks), net_tries, link_ok() ? "reachable" : "NOT reachable");
                server(NULL);
                if (!quitting) { net_up = 0; netlog("server stopped, rejoining"); usleep(2000 * 1000); }
                continue;
            }
            char st[320];
            lwnet_status(st, sizeof st);
            netlog_now("wired: no address yet (%s); trying Wi-Fi", st);
            netx_wired = 0;
        }
        net_backoff(fails++);
        net_tries++;
        netlog("net: attempt %d", net_tries);
        net_deinit();
        while ((r = net_init()) == -EAGAIN && !quitting) usleep(100 * 1000);
        if (r < 0) {                         // like ftpii: start over after a hard failure
            net_err = r;
            netlog("net_init failed %d", (int)r);
            usleep(1000 * 1000);
            continue;
        }
        netlog("net: init ok (%d)", (int)r);
        u32 addr = 0;                        // DHCP can finish well after net_init returns: keep asking
        for (int i = 0; i < 300 && !quitting && !(addr = net_gethostip()); i++) usleep(100 * 1000);
        if (!addr) {
            net_err = -1000;
            netlog("net_init ok but no address after 30 s");
            continue;
        }
        snprintf(ip, sizeof ip, "%u.%u.%u.%u", addr >> 24, (addr >> 16) & 255, (addr >> 8) & 255, addr & 255);
        netlog("net: address %s", ip);
        netx_wired = 0;
        net_up = 1;
        fails = 0;
        netlog("up %s after %us, attempt %d, router %s", ip, (unsigned)ticks_to_secs(gettime() - boot_ticks), net_tries,
               link_ok() ? "reachable" : "NOT reachable");
        server(NULL);                        // returns only when quitting or listening failed
        if (!quitting) { net_up = 0; netlog("server stopped, rejoining"); usleep(2000 * 1000); }
    }
    net_thread_done = 1;
    return NULL;
}

// Boots the agent's SD copy (fresh IOS, fresh start). Keeps the autobooted flag across the hop.
#define NET_FAILS_FILE "sd:/arcade/netfails"   // network relaunches in a row, across relaunches
static int net_fails_read(void) {
    int n = 0;
    FILE *f = store_open(NET_FAILS_FILE);
    if (f) { if (fscanf(f, "%d", &n) != 1) n = 0; fclose(f); }
    return n;
}

// ---------------------------------------------------------------- wired / Wi-Fi
// IOS joins only the console's selected connection, the way that connection is set up: a USB LAN adapter is ignored
// while it's a Wi-Fi one. config.dat: 8-byte header, then 3 connections of 0x91C bytes, flags at +0 (bit 0 = wired,
// bit 7 = selected). We flip bit 0 of the selected connection in place (its Wi-Fi settings stay for flipping back);
// IOS reads the file at start-up, so a relaunch on a fresh IOS follows. Original kept in sd:/arcade/net-config.orig.
#define NETCFG_PATH "/shared2/sys/net/02/config.dat"
#define NETCFG_SIZE 0x1B5C
#define NETCFG_BACKUP "sd:/arcade/net-config.orig"
#define NET_MODE_FILE "sd:/arcade/netmode"       // one-shot "wired" | "wifi" from the Mac
#define NET_REBOOT_FILE "sd:/arcade/netreboot"   // our own network restart of the console: not a power-on
#define USB_VID_ASIX 0x0b95                      // Nintendo's LAN adapter and the third-party ones the Wii supports
static u8 netcfg[NETCFG_SIZE] ATTRIBUTE_ALIGN(32);

// -> the selected connection (0-2) with *wired set, or -1 (file unreadable or nothing selected)
static int netcfg_read(int *wired) {
    if (!isfs_ok) return -1;
    s32 fd = ISFS_Open(NETCFG_PATH, ISFS_OPEN_READ);
    if (fd < 0) return -1;
    s32 r = ISFS_Read(fd, netcfg, NETCFG_SIZE);
    ISFS_Close(fd);
    if (r != NETCFG_SIZE) return -1;
    for (int i = 0; i < 3; i++) {
        u8 flags = netcfg[8 + i * 0x91C];
        if (flags & 0x80) { *wired = flags & 1; return i; }
    }
    return -1;
}

static int netcfg_set_wired(int wired) {
    int cur, sel = netcfg_read(&cur);
    if (sel < 0) { netlog_now("network: no selected connection in %s, can't switch", NETCFG_PATH); return 0; }
    if (cur == wired) return 1;
    if (sd_ok && !file_exists(NETCFG_BACKUP)) {
        FILE *f = fopen(NETCFG_BACKUP, "wb");
        int ok = f && fwrite(netcfg, 1, NETCFG_SIZE, f) == NETCFG_SIZE;
        if (f) { fflush(f); fsync(fileno(f)); ok &= fclose(f) == 0; }
        if (!ok) { remove(NETCFG_BACKUP); netlog_now("network: couldn't back up %s, not switching", NETCFG_PATH); return 0; }
    }
    netcfg[8 + sel * 0x91C] = (netcfg[8 + sel * 0x91C] & ~1) | (wired ? 1 : 0);
    s32 fd = ISFS_Open(NETCFG_PATH, ISFS_OPEN_RW), r = -1;
    if (fd >= 0) { if (ISFS_Seek(fd, 0, SEEK_SET) >= 0) r = ISFS_Write(fd, netcfg, NETCFG_SIZE); ISFS_Close(fd); }
    netlog_now("network: connection %d switched to %s (%s)", sel + 1, wired ? "wired" : "Wi-Fi",
               r == NETCFG_SIZE ? "ok" : "WRITE FAILED");
    return r == NETCFG_SIZE;
}

// 1 = an ASIX LAN adapter is plugged in, 0 = not seen (IOS's own driver may hide it), and *list = what USB shows
static int usb_lan_present(char *list, int size) {
    static usb_device_entry devs[8] ATTRIBUTE_ALIGN(32);
    u8 cnt = 0;
    int found = 0, n = 0;
    list[0] = 0;
    if (USB_GetDeviceList(devs, 8, 0, &cnt) < 0) { snprintf(list, size, "list failed"); return 0; }
    for (int i = 0; i < cnt; i++) {
        found |= devs[i].vid == USB_VID_ASIX;
        if (n < size) n += snprintf(list + n, size - n, "%s%04x:%04x", i ? " " : "", devs[i].vid, devs[i].pid);
    }
    if (!cnt) snprintf(list, size, "none");
    return found;
}

static void net_log_setup(void) {
    int wired = 0, sel = netcfg_read(&wired);
    if (sel >= 0 && wired) netcfg_set_wired(0);   // see net_pick_mode
    char list[96];
    int lan = usb_lan_present(list, sizeof list);
    if (sel < 0) netlog("network: no selected connection (config.dat unreadable or empty)");
    else netlog("network: connection %d, %s; USB LAN adapter %s (USB: %s)", sel + 1, wired ? "wired" : "Wi-Fi",
                lan ? "plugged in" : "not seen", list);
}

// Before a network relaunch: IOS's own connection stays a Wi-Fi one. Wired goes through our driver (lwnet), which
// IOS's wired mode would only get in the way of (it disables Wi-Fi and can't run cab1's adapter anyway). 0.9.24-0.9.26
// flipped IOS to wired; this undoes that. (sd:/arcade/netmode can still ask for IOS wired by hand.)
static void net_pick_mode(int n) {
    int wired, sel = netcfg_read(&wired);
    if (sel >= 0 && wired) netcfg_set_wired(0);
}

static int relaunch_self(const char *why) {
    static int net_gave_up;                  // 12 network restarts in a row: stay offline, the games don't need it
    int net_why = !strcmp(why, "wifi") || !strncmp(why, "net-", 4) || !strcmp(why, "link");
    if (net_why && net_gave_up) return 0;
    // Wi-Fi that stays dead through relaunches (seen after GameCube games) only came back with a power cycle: every
    // fourth time in a row, restart the whole console instead (boot2 -> Priiloader -> hop -> here), at most 3 times.
    if (sd_ok && (!strcmp(why, "wifi") || !strncmp(why, "net-", 4) || !strcmp(why, "link"))) {
        int n = net_fails_read() + 1;
        if (n > 12) {
            net_gave_up = 1;
            netlog_now("network: %d restarts in a row didn't bring it back; staying offline until the next power-on", n - 1);
            return 0;
        }
        store_printf(NET_FAILS_FILE, "%d\n", n);
        net_pick_mode(n);
        if (n % 4 == 0 && n <= 12) {
            netlog_now("network still down after %d relaunches (%s): restarting the console", n - 1, why);
            store_printf(NET_REBOOT_FILE, "1\n");
            request = REQ_REBOOT;
            return 1;
        }
    }
    char spec[160], err[160];
    snprintf(spec, sizeof spec, "%s\t--relaunch=%s%s", AGENT_SD_DOL, why, autobooted ? "\t--autobooted" : "");
    if (!sd_ok || exec_prepare(spec, err) < 0) return 0;
    netlog("relaunching (%s)", why);
    request = REQ_EXEC;
    return 1;
}

// ---------------------------------------------------------------- main

// Once this version has run healthily: it becomes boot-good.dol, the slot hop falls back to if a newer boot.dol
// fails to start twice. Copied only when the version changes (good.txt), so normally no card write at all.
static void keep_good_copy(void) {
    char ver[32] = "";
    FILE *f = fopen("sd:/apps/wii-agent/good.txt", "r");
    if (f) { if (!fgets(ver, sizeof ver, f)) ver[0] = 0; fclose(f); }
    ver[strcspn(ver, "\r\n")] = 0;
    if (!strcmp(ver, AGENT_VERSION)) return;
    FILE *in = fopen(AGENT_SD_DOL, "rb");
    if (!in) return;
    FILE *out = fopen("sd:/apps/wii-agent/boot-good.new", "wb");
    int ok = out != NULL;
    size_t n;
    while (ok && (n = fread(iobuf, 1, sizeof iobuf, in)) > 0) ok = fwrite(iobuf, 1, n, out) == n;
    fclose(in);
    if (out) { fflush(out); fsync(fileno(out)); ok &= fclose(out) == 0; }
    if (!ok) { remove("sd:/apps/wii-agent/boot-good.new"); return; }
    remove("sd:/apps/wii-agent/boot-good.dol");
    rename("sd:/apps/wii-agent/boot-good.new", "sd:/apps/wii-agent/boot-good.dol");
    store_printf("sd:/apps/wii-agent/good.txt", "%s\n", AGENT_VERSION);
    netlog_now("this version (%s) is now the known-good fallback", AGENT_VERSION);
}

#define SPLASH_MIN_SECS 5.4f                 // the WIIZARD terminal has typed the name and the game count
static game_t *scan_games;
static int scan_count;
static volatile int scan_done;
static void *scan_thread(void *unused) {
    scan_games = catalog_scan(&scan_count);
    scan_done = 1;
    return NULL;
}

int main(int argc, char **argv) {
    boot_ticks = gettime();
    LWP_MutexInit(&log_lock, false);
    int from_nand = argc > 0 && argv[0] && !strcmp(argv[0], PRII_MAIN_BIN);
    autobooted = from_nand;
    for (int i = 1; i < argc; i++) {
        autobooted |= !strcmp(argv[i], "--autobooted");
        if (!strncmp(argv[i], "--relaunch=", 11) && strcmp(argv[i] + 11, "hop") && strcmp(argv[i] + 11, "autoboot")) restarted = 1;   // wifi, update, game...
        if (!strcmp(argv[i], "--relaunch=game")) back_from_game = 1;   // our RetroArch, on quit
        if (!strcmp(argv[i], "--game-ran")) game_ran = 1;
        if (!strcmp(argv[i], "--selftest=ui")) selftest = 1;
        if (!strcmp(argv[i], "--selftest=net")) selftest = 2;
    }
    __exception_setreload(5);               // on a crash, return to the loader after 5 s instead of waiting for a person
    exec_area = (u8 *)(((u32)SYS_GetArena2Hi() - EXEC_RESERVE) & ~0xFFFF);
    SYS_SetArena2Hi(exec_area);
    retarget_stub();
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    ES_GetDeviceID(&device_id);
    isfs_ok = ISFS_Initialize() >= 0;
    sd_ok = fatMountSimple("sd", &__io_wiisd);
    usb_ok = fatMountSimple("usb", &__io_usbstorage);
    if (sd_ok && file_exists(NO_AHBPROT_TEST_FILE)) { fake_no_ahbprot = 1; remove(NO_AHBPROT_TEST_FILE); }
    // Priiloader boots the copy in NAND; it only hands off to the SD copy so updates never need a NAND write
    lwp_t th = LWP_THREAD_NULL;
    if (from_nand && relaunch_self("autoboot")) goto leave;

    // Boot-loop guard: count starts that never reached HEALTHY_SECS; after 3, come up without the UI.
    int boots = 0;
    if (sd_ok) {
        FILE *bf = store_open(BOOT_COUNT_FILE);
        if (bf) { if (fscanf(bf, "%d", &boots) != 1) boots = 0; fclose(bf); }
        if (boots >= 3 && !selftest) { safe_mode = 1; boots = 0; }
        store_printf(BOOT_COUNT_FILE, "%d\n", boots + 1);
    }
    // A real power-on gives the network a fresh 12 tries (up to 0.9.23 "staying offline until the next power-on"
    // lasted forever: the count was only cleared once online). Our own network restart of the console isn't one.
    if (sd_ok && !restarted) {
        if (file_exists(NET_REBOOT_FILE)) remove(NET_REBOOT_FILE);
        else if (net_fails_read()) store_printf(NET_FAILS_FILE, "0\n");
    }
    // sd:/arcade/netmode ("wired" or "wifi", put there from the Mac with the card out): switch once, then a fresh IOS
    if (sd_ok && isfs_ok && file_exists(NET_MODE_FILE)) {
        char mode[16] = "";
        FILE *f = fopen(NET_MODE_FILE, "r");
        if (f) { if (!fgets(mode, sizeof mode, f)) mode[0] = 0; fclose(f); }
        remove(NET_MODE_FILE);
        int wired = !strncmp(mode, "wired", 5);
        if ((wired || !strncmp(mode, "wifi", 4)) && netcfg_set_wired(wired) && relaunch_self("netmode")) goto leave;
    }
    if (selftest != 1) net_log_setup();
    if (selftest != 1) LWP_CreateThread(&th, network, NULL, NULL, 64 * 1024, 50);
    lwp_t upd;
    if (sd_ok && selftest != 1) LWP_CreateThread(&upd, updater, NULL, NULL, 64 * 1024, 30);
    else net_thread_done = 1;
    if (selftest) netlog("selftest %s", selftest == 1 ? "ui (no network)" : "network (no ui)");
    WPAD_Init();
    PAD_Init();
    wpad_up = 1;
    SYS_SetResetCallback(on_reset);
    SYS_SetPowerCallback(on_power);
    WPAD_SetPowerButtonCallback(on_wpad_power);
    static void *safe_xfb;
    if (safe_mode) {                         // plain text console, like the bare agent
        netlog_now("safe mode: the launcher failed to stay up 3 times; UI skipped");
        safe_xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
        console_init(safe_xfb, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
        VIDEO_Configure(rmode);
        VIDEO_SetNextFramebuffer(safe_xfb);
        VIDEO_SetBlack(FALSE);
        VIDEO_Flush();
        VIDEO_WaitVSync();
        printf("\x1b[2;0H  wii-agent %s - SAFE MODE\n\n  The arcade launcher failed to start 3 times.\n"
               "  Waiting for the Mac (wii MCP) to fix it.\n", AGENT_VERSION);
    } else if (selftest != 2) {
        if (sd_ok) cab_load(device_id);
        ui_init(rmode);
        ui_splash_load();
    }
    int ngames = 0;
    game_t *games = NULL;
    if (sd_ok && !safe_mode && selftest != 2) {   // the library loads in the background; the sign animates meanwhile
        lwp_t scan;
        LWP_CreateThread(&scan, scan_thread, NULL, NULL, 128 * 1024, 60);
        u64 t0 = gettime();
        float t = 0;
        // The swirl is the power-on sign only: back from a game, after a Wi-Fi restart or an update it would play
        // far too often. Then just the calm background while the list loads.
        // libogc sets the time base from the RTC at every start, so "time since power-on" isn't available. A launch
        // record means "back from a game", unless it's hours old: then the power went off mid-game (power strip
        // at night) and this is a real power-on, so drop the record (no resume, no retry).
        long ll_age = last_launch_age();
        if (ll_age > 3 * 3600) { remove(LAST_LAUNCH_FILE); netlog_now("stale launch record (%lds): power-on", ll_age); ll_age = -1; }
        int pending = pending_exists();       // restarted for a GameCube game: no intro, it starts right away
        int power_on = !restarted && ll_age < 0 && !net_fails_read() && !pending;
        if (back_from_game) netlog_now("back from RetroArch directly%s; ahbprot %s", game_ran ? " (game ran)" : "",
                                       HAVE_AHBPROT ? "off (kept)" : "ON (lost)");
        while (!scan_done || t < (power_on ? SPLASH_MIN_SECS : 0.8f)) {   // the return note stays readable
            if (scan_done) ui_splash_count(scan_count, scan_games);
            if (power_on) ui_splash_frame(t); // paced by the display (one frame per vsync)
            else if (pending) ui_term_frame("> PREPARING GAMECUBE...", NULL, t);
            else ui_wait_frame(back_from_game ? t + 0.5f : t);   // RetroArch showed this line already: no retyping
            t = ticks_to_millisecs(gettime() - t0) / 1000.0f;
        }
        LWP_JoinThread(scan, NULL);
        games = scan_games;
        ngames = scan_count;
    } else if (sd_ok && !safe_mode) games = catalog_scan(&ngames);
    netlog_now("library: %d games; ahbprot %s%s", ngames, HAVE_AHBPROT ? "off (good: GameCube/Wii games can start)" : "ON",
               fake_no_ahbprot ? " (test: treated as ON)" : "");
    ui_set_games(games, ngames);
    lib_games = games;
    lib_count = ngames;
    if (sd_ok && selftest == 0) {
        struct stat qst;
        if (stat(TEST_QUEUE_FILE, &qst) == 0) test_queue = play_test = 1;
    }
    if (sd_ok && !test_queue) remove(AUTOTEST_FILE);
    int resume = -1, failed = 0, retry_attempt = 1;
    int retry = (sd_ok && selftest == 0) ? check_last_launch(games, ngames, &resume, &failed, &retry_attempt) : -1;
    if (failed && record_failure(&games[resume])) {     // hidden now: reload the library without it
        char title[96];
        snprintf(title, sizeof title, "%s", games[resume].title);
        free(games);
        games = catalog_scan(&ngames);
        ui_set_games(games, ngames);
        lib_games = games;
        lib_count = ngames;
        resume = -1;
        ui_notice(title, "Couldn't start - taken off the menu until it's fixed");   // named: not the game in attract
        netlog_now("library: %d games after hiding %s", ngames, title);
    } else if (failed) ui_notice("Couldn't start this game", games[resume].title);
    if (resume >= 0) ui_resume(resume);
    int pend_test = 0;
    int pend = (sd_ok && selftest == 0 && retry < 0) ? check_pending(games, ngames, &pend_test) : -1;
    if (pend >= 0) {
        char err[160];
        if (pend_test) play_test = 1;
        ui_resume(pend);
        int prep = prepare_while_loading(&games[pend], err);
        note_launch(&games[pend], 1);
        if (prep == 0) {
            request = REQ_EXEC;
            if (!play_test) ui_record_launch(pend);
        } else { netlog_now("pending launch failed: %s", err); remove(LAST_LAUNCH_FILE); ui_notice("Couldn't start this game", games[pend].title); }
    }
    if (retry >= 0 && slow_path_for(&games[retry])) retry = -1;
    if (retry >= 0) {
        char err[160];
        ui_show_message("RETRYING", games[retry].title);
        note_launch(&games[retry], retry_attempt);
        if (launch_game(&games[retry], err) == 0) request = REQ_EXEC;
        else { netlog("retry failed: %s", err); remove(LAST_LAUNCH_FILE); ui_notice("Couldn't start this game", games[retry].title); }
    }

    netlog("menu ready %u ms after start", (unsigned)ticks_to_millisecs(gettime() - boot_ticks));
    while (request == REQ_NONE) {
        static int loops;
        if (loops < 5) netlog("main: loop %d scan pads", loops);
        WPAD_ScanPads();
        PAD_ScanPads();
        if (loops++ < 5) netlog("main: pads scanned");
        u32 wd = 0, wh = 0, gd = 0, gh = 0;
        for (int i = 0; i < 4; i++) {
            wd |= WPAD_ButtonsDown(i); wh |= WPAD_ButtonsHeld(i);
            gd |= PAD_ButtonsDown(i); gh |= PAD_ButtonsHeld(i);
        }
        if (virt_buttons && gettime() < virt_until) { wd |= virt_buttons; virt_buttons = 0; }
        if (wd & (WPAD_BUTTON_HOME | WPAD_CLASSIC_BUTTON_HOME)) reset_pressed = 1;   // kids: never out of the launcher
        if (reset_pressed) {
            reset_pressed = 0;
            if (safe_mode) request = REQ_HBC;
            else { ui_go_attract(); netlog("reset/HOME: back to attract"); }
        }
        u32 pressed = 0, held = 0;
        #define MAP(bits_w, bits_g, flag) do { if (wd & (bits_w) || gd & (bits_g)) pressed |= flag; \
                                              if (wh & (bits_w) || gh & (bits_g)) held |= flag; } while (0)
        MAP(WPAD_BUTTON_UP | WPAD_CLASSIC_BUTTON_UP, PAD_BUTTON_UP, IN_UP);
        MAP(WPAD_BUTTON_DOWN | WPAD_CLASSIC_BUTTON_DOWN, PAD_BUTTON_DOWN, IN_DOWN);
        MAP(WPAD_BUTTON_LEFT | WPAD_CLASSIC_BUTTON_LEFT, PAD_BUTTON_LEFT, IN_LEFT);
        MAP(WPAD_BUTTON_RIGHT | WPAD_CLASSIC_BUTTON_RIGHT, PAD_BUTTON_RIGHT, IN_RIGHT);
        MAP(WPAD_BUTTON_A | WPAD_BUTTON_2 | WPAD_CLASSIC_BUTTON_A, PAD_BUTTON_A, IN_A);
        MAP(WPAD_BUTTON_B | WPAD_BUTTON_1 | WPAD_CLASSIC_BUTTON_B, PAD_BUTTON_B, IN_B);
        MAP(WPAD_BUTTON_PLUS | WPAD_CLASSIC_BUTTON_PLUS, PAD_BUTTON_START, IN_START);
        MAP(WPAD_CLASSIC_BUTTON_X, PAD_BUTTON_X, IN_X);
        MAP(WPAD_BUTTON_MINUS | WPAD_CLASSIC_BUTTON_Y, PAD_BUTTON_Y, IN_Y);
        MAP(WPAD_CLASSIC_BUTTON_ZR, PAD_TRIGGER_Z, IN_Z);
        MAP(WPAD_CLASSIC_BUTTON_FULL_L, PAD_TRIGGER_L, IN_L);
        MAP(WPAD_CLASSIC_BUTTON_FULL_R, PAD_TRIGGER_R, IN_R);
        #undef MAP
        for (int i = 0; i < 4; i++) {        // GameCube analog stick as a d-pad
            s8 x = PAD_StickX(i), y = PAD_StickY(i);
            if (x < -50) held |= IN_LEFT;
            if (x > 50) held |= IN_RIGHT;
            if (y > 50) held |= IN_UP;
            if (y < -50) held |= IN_DOWN;
        }
        static u32 stick_prev;
        u32 stick = held & (IN_LEFT | IN_RIGHT | IN_UP | IN_DOWN);
        pressed |= stick & ~stick_prev;
        stick_prev = stick;
        // Test queue: the next game after TEST_QUEUE_GAP_SECS in attract mode. Any button stops it (a person is here).
        if (test_queue && (pressed || held)) {
            remove(TEST_QUEUE_FILE); remove(AUTOTEST_FILE);
            test_queue = play_test = 0;
            netlog_now("test queue: stopped by a button");
        }
        if (test_queue && ui_in_attract() && ui_idle_secs() > TEST_QUEUE_GAP_SECS && play_request < 0) {
            char *buf = NULL, key[32] = "";
            FILE *f = store_open(TEST_QUEUE_FILE);
            long len = 0;
            if (f) {
                fseek(f, 0, SEEK_END); len = ftell(f); fseek(f, 0, SEEK_SET);
                buf = calloc(1, len + 1);
                if (buf && fread(buf, 1, len, f) != (size_t)len) len = 0;
                fclose(f);
            }
            char *rest = buf ? buf : "";
            while (*rest && !key[0]) {                    // first id; the rest goes back to the card
                int k = strcspn(rest, "\r\n");
                snprintf(key, sizeof key, "%.*s", k < 31 ? k : 31, rest);
                rest += k;
                rest += strspn(rest, "\r\n");
            }
            if (!key[0]) { remove(TEST_QUEUE_FILE); test_queue = play_test = 0; netlog_now("test queue: done"); }
            else {
                store_write(TEST_QUEUE_FILE, rest, strlen(rest));
                int gi = -1;
                for (int i = 0; gi < 0 && i < lib_count; i++)
                    if (!strcasecmp(lib_games[i].id, key) || !strcasecmp(lib_games[i].rom, key)) gi = i;
                if (gi < 0) { char rec[64]; snprintf(rec, sizeof rec, "%s\t-1\t0\n", key); store_append("sd:/arcade/returns.tsv", rec); }
                else { netlog_now("test queue: %s", key); play_test = 1; play_request = gi; }
            }
            free(buf);
        }

        u32 up = ticks_to_secs(gettime() - boot_ticks);
        char status_line[64];
        if (net_up) snprintf(status_line, sizeof status_line, "online");
        else snprintf(status_line, sizeof status_line, "connecting... attempt %d", net_tries);
        // Network restarts only while the cabinet sits untouched in attract mode: they used to fire mid-browse
        // (a sudden black screen, and every 4th one a console restart) whenever Wi-Fi was bad.
        int net_restart_ok = !safe_mode && ui_in_attract() && ui_idle_secs() > 120 && !client_open;
        if (net_restart_ok && !net_up && net_tries > NET_RELAUNCH_TRIES && net_err < 0 && relaunch_self("wifi")) break;
        if (net_restart_ok && link_dead && relaunch_self("link")) break;
        if (launcher_updated && ui_in_attract() && ui_idle_secs() > 60 && !client_open && relaunch_self("update")) break;
        // Watchdog (the network thread can't fix itself if it's the thing that's stuck): no proof of a working
        // network for NET_DEAD_SECS, or no address for that long, while the cabinet sits idle in attract mode ->
        // restart, which brings Wi-Fi up from scratch. Never while someone is browsing.
        {
            static u64 down_since;
            u64 ok_at = net_up ? last_net_ok : 0;
            if (!net_up && !down_since) down_since = gettime();
            if (net_up) down_since = 0;
            u64 since = net_up ? (ok_at ? ok_at : boot_ticks) : down_since;
            if (!safe_mode && selftest == 0 && ui_in_attract() && ui_idle_secs() > 60 && !client_open &&
                ticks_to_secs(gettime() - since) > NET_DEAD_SECS && relaunch_self(net_up ? "net-silent" : "net-down")) break;
        }
        if (!net_up && up >= NET_GIVE_UP_SECS && from_hbc() && !autobooted) request = REQ_HBC;   // no SD copy to relaunch

        static u32 frames;
        static u64 last_alive;
        frames++;
        if (ticks_to_millisecs(gettime() - last_alive) >= 2000) {
            last_alive = gettime();
            netlog("alive: frame %u, net_up %d", frames, net_up);
        }
        ui_state_t st = { .busy = client_open || ticks_to_millisecs(gettime() - last_activity) < 2500,
                          .online = net_up, .ip = ip, .status = status_line };
        static int net_fails_cleared;
        if (net_up && !net_fails_cleared && sd_ok) {
            net_fails_cleared = 1;
            if (net_fails_read()) store_printf(NET_FAILS_FILE, "0\n");
        }
        static int healthy;
        if (!healthy && up >= HEALTHY_SECS && sd_ok) {
            healthy = 1;
            store_printf(BOOT_COUNT_FILE, "0\n");
            keep_good_copy();                // the start-up program's fallback slot
        }
        if (selftest && up >= 40) { netlog("selftest passed 40 s"); request = REQ_REBOOT; break; }
        if (selftest == 2 || safe_mode) {
            if (safe_mode) printf("\x1b[7;0H  %-56.56s", status_line);
            VIDEO_WaitVSync();
            continue;
        }
        // Energy: untouched in attract mode for idle_off_minutes (and the Mac not working on it) -> power off.
        // The last 30 s show a warning; any button keeps it on.
        if (cab.idle_off_minutes > 0 && ui_in_attract() && !st.busy &&
            ticks_to_secs(gettime() - last_activity) > 600 && !client_open) {
            float left = cab.idle_off_minutes * 60.0f - ui_idle_secs();
            static float warned;
            if (left <= 30 && left > 0 && (warned == 0 || warned - left >= 5)) {
                warned = left;
                ui_notice("Saving power", "Turning off soon - press any button to keep playing");
            }
            if (left > 30) warned = 0;
            if (left <= 0) {
                netlog_now("idle %d min in attract: powering off", cab.idle_off_minutes);
                request = REQ_OFF;
                break;
            }
        }
        if (ticks_to_millisecs(gettime() - log_last_flush) >= LOG_FLUSH_MS) log_flush();
        int pick = ui_frame(pressed, held, &st);
        if (pick >= 0) play_test = 0;            // a person picked it: never a test launch (RetroArch autotest quit)
        if (play_request >= 0) { pick = play_request; play_request = -1; usleep(300 * 1000); }
        if (pick >= 0 && slow_path_for(&games[pick])) { ui_remember_spot(pick); break; }
        if (pick >= 0) {
            char err[160];
            ui_remember_spot(pick);
            int prep = prepare_while_loading(&games[pick], err);   // the loading card, the program read meanwhile
            note_launch(&games[pick], 1);
            store_printf(BOOT_COUNT_FILE, "0\n");
            if (prep == 0) {
                request = REQ_EXEC;
                if (!play_test) ui_record_launch(pick);   // plays count only when the game really starts (not tests)
            } else {
                netlog_now("launch failed: %s", err);
                remove(LAST_LAUNCH_FILE);
                ui_notice("Couldn't start this game", games[pick].title);
            }
        }
    }

leave:
    // A deliberate exit (a game, a Wi-Fi relaunch, power off) isn't a failed start: only crashes and hangs may count
    // toward safe mode. (Up to 0.8.0, Wi-Fi relaunches counted, and a morning of flaky Wi-Fi ended in safe mode.)
    if (sd_ok && !safe_mode && !selftest) store_printf(BOOT_COUNT_FILE, "0\n");
    netlog_now("leaving: request %d", request);
    usleep(200 * 1000);                      // let the last OK reach the Mac
    quitting = 1;
    for (int i = 0; i < 20 && !net_thread_done; i++) usleep(50 * 1000);
    // No join and no net_deinit: the thread may sit in a blocking call, and the loader reloads IOS anyway, which
    // resets the network. Waiting on either here is what can strand a console.
    VIDEO_SetBlack(TRUE);                    // stop the picture cleanly before the next program takes over
    VIDEO_Flush();
    VIDEO_WaitVSync();
    GX_AbortFrame();
    if (wpad_up) WPAD_Shutdown();
    if (eth_is_open()) {                     // no USB transfer may be in flight across the IOS reload below (eth.c)
        int ms = eth_close();
        netlog_now("eth closed for request %d (rx stopped %s, %d ms)", request, ms >= 0 ? "ok" : "TIMEOUT", ms);
    }
    if (request == REQ_EXEC) {               // keep AHBPROT across the IOS reload (logged while the card is mounted)
        int kept = keep_ahbprot();
        netlog_now("exec: ahbprot %s, keep patch %d", HAVE_AHBPROT ? "off" : "on", kept);
    }
    if (sd_ok) fatUnmount("sd:");
    if (usb_ok) fatUnmount("usb:");
    if (isfs_ok) ISFS_Deinitialize();
    if (request == REQ_EXEC) exec_jump();
    switch (request) {
    case REQ_MENU: SYS_ResetSystem(SYS_RETURNTOMENU, 0, 0); break;
    case REQ_REBOOT: SYS_ResetSystem(SYS_RESTART, 0, 0); break;
    case REQ_OFF: SYS_ResetSystem(SYS_POWEROFF_STANDBY, 0, 0); break;
    }
    return 0;                                // REQ_HBC: back to the loader
}
