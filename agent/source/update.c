// Pull-style updates: the cabinet fetches what changed from the update server (the always-on Ubuntu MacBook,
// http://<server>/manifest.txt, published by the Mac's publish.py) instead of the Mac pushing files over flaky
// Wi-Fi. manifest.txt: one line per file, "<size> <crc32 hex> <sd path>". A file is fetched when its size or CRC
// differs from what this card last installed (sd:/arcade/installed.tsv, so unchanged files are never re-read),
// into <path>.new, checked against the CRC, then swapped in. Runs on the network thread, one file at a time, and
// only while the cabinet sits idle in attract mode (it waits between files otherwise). A new launcher takes effect
// at the next start; the start-up program's two slots cover a bad one.
// 0.9.21+: manifest2.txt adds the size of a gzip copy (<file>.gz, 0 = none). Those come over compressed (about half
// the bytes for DOLs), resumable like the rest, and are inflated on the card; the CRC is of the inflated file.
#include <gccore.h>
#include <zlib.h>
#include <network.h>
#include "netx.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <ogc/lwp_watchdog.h>
#include "update.h"
#include "store.h"

#define SERVER_CFG "sd:/arcade/update.cfg"   // "server = <host>:8088"
#define INSTALLED "sd:/arcade/installed.tsv" // <sd path>\t<size>\t<crc32>
#define IO_MS 20000

static u32 crc_table[256];
static void crc_init(void) {
    for (u32 i = 0; i < 256; i++) {
        u32 c = i;
        for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
        crc_table[i] = c;
    }
}
static u32 crc_update(u32 crc, const u8 *p, u32 n) {
    crc = ~crc;
    while (n--) crc = crc_table[(crc ^ *p++) & 255] ^ (crc >> 8);
    return ~crc;
}

static int server_addr(struct sockaddr_in *sa, char *host, int hostlen) {
    FILE *f = fopen(SERVER_CFG, "r");
    char line[128], ip[64] = "";
    int port = 8088;
    while (f && fgets(line, sizeof line, f))
        if (sscanf(line, " server = %63[^:\r\n]:%d", ip, &port) >= 1) break;
    if (f) fclose(f);
    if (!ip[0]) return -1;
    memset(sa, 0, sizeof *sa);
    sa->sin_family = AF_INET;
    sa->sin_port = htons(port);
    if (!inet_aton(ip, &sa->sin_addr)) return -1;
    snprintf(host, hostlen, "%s:%d", ip, port);
    return 0;
}

static int wait_io(s32 s, void *buf, int n, int sending) {
    u64 t0 = gettime();
    for (;;) {
        int r = sending ? net_send(s, buf, n, 0) : net_recv(s, buf, n, 0);
        if (r >= 0) return r;
        if (r != -EAGAIN && r != -EWOULDBLOCK) return r;
        if (ticks_to_millisecs(gettime() - t0) > IO_MS) return -ETIMEDOUT;
        usleep(2000);
    }
}

// GET path -> out file (or memory when out_mem). Returns bytes received, or <0. *crc gets the CRC of the body.
// offset > 0: resume a file download (Range request, appending); a server that ignores Range (200) starts over.
static int http_get_at(const char *path, const char *out_file, char *out_mem, int mem_max, u32 *crc, long offset);
static int http_get(const char *path, const char *out_file, char *out_mem, int mem_max, u32 *crc) {
    return http_get_at(path, out_file, out_mem, mem_max, crc, 0);
}
static int http_get_at(const char *path, const char *out_file, char *out_mem, int mem_max, u32 *crc, long offset) {
    struct sockaddr_in sa;
    char host[80];
    if (server_addr(&sa, host, sizeof host) < 0) return -1;
    s32 s = net_socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (s < 0) return -2;
    if (net_connect(s, (struct sockaddr *)&sa, sizeof sa) < 0) { net_close(s); return -3; }
    s32 fl = net_fcntl(s, F_GETFL, 0);
    net_fcntl(s, F_SETFL, fl | 4);           // non-blocking (IOS_O_NONBLOCK): every read times out
    char req[400];
    char range[48] = "";
    if (offset > 0 && out_file) snprintf(range, sizeof range, "Range: bytes=%ld-\r\n", offset);
    int n = snprintf(req, sizeof req, "GET /%s HTTP/1.0\r\nHost: %s\r\n%sConnection: close\r\n\r\n", path, host, range);
    if (wait_io(s, req, n, 1) != n) { net_close(s); return -4; }
    static char buf[16384] ATTRIBUTE_ALIGN(32);
    int got = 0, header = 1, total = 0, status = 0;
    FILE *out = NULL;
    if (out_file) { out = fopen(out_file, offset > 0 ? "ab" : "wb"); if (!out) { net_close(s); return -5; } }
    *crc = 0;
    char head[1024];
    int hl = 0;
    for (;;) {
        int r = wait_io(s, buf, sizeof buf, 0);
        if (r < 0) { total = r; break; }
        if (r == 0) break;
        char *p = buf;
        if (header) {                        // collect up to the blank line, then pass the rest on as body
            int take = r < (int)sizeof head - 1 - hl ? r : (int)sizeof head - 1 - hl;
            memcpy(head + hl, buf, take);
            hl += take;
            head[hl] = 0;
            char *end = strstr(head, "\r\n\r\n");
            if (!end) { if (hl >= (int)sizeof head - 1) { total = -6; break; } continue; }
            sscanf(head, "HTTP/%*s %d", &status);
            int body_in_head = hl - (int)(end + 4 - head);
            p = buf + (take - body_in_head);
            r = body_in_head + (r - take);
            header = 0;
            if (status == 200 && offset > 0 && out) {   // the whole file after all: start the file over
                fclose(out); out = fopen(out_file, "wb"); offset = 0;
                if (!out) { total = -5; break; }
            }
            if (status != 200 && status != 206) { total = -status; break; }
        }
        if (r <= 0) continue;
        *crc = crc_update(*crc, (u8 *)p, r);
        if (out && fwrite(p, 1, r, out) != (size_t)r) { total = -7; break; }
        if (out_mem) {
            if (got + r >= mem_max) { total = -8; break; }
            memcpy(out_mem + got, p, r);
        }
        got += r;
        total = got;
    }
    net_close(s);
    if (out) { fflush(out); fsync(fileno(out)); fclose(out); }
    if (out_mem && total >= 0) out_mem[got] = 0;
    return header ? -9 : total;
}

static u32 file_crc(const char *path) {
    static u8 buf[32768] ATTRIBUTE_ALIGN(32);
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    u32 crc = 0;
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) crc = crc_update(crc, buf, n);
    fclose(f);
    return crc;
}

// gz file -> out file. Returns the inflated size, or <0.
static long gunzip_file(const char *gz, const char *out_path) {
    static u8 buf[32768] ATTRIBUTE_ALIGN(32);
    gzFile in = gzopen(gz, "rb");
    if (!in) return -1;
    FILE *out = fopen(out_path, "wb");
    if (!out) { gzclose(in); return -2; }
    long total = 0;
    int n;
    while ((n = gzread(in, buf, sizeof buf)) > 0) {
        if (fwrite(buf, 1, n, out) != (size_t)n) { total = -3; break; }
        total += n;
    }
    if (n < 0) total = -4;
    gzclose(in);
    fflush(out); fsync(fileno(out)); fclose(out);
    return total;
}

typedef struct { char path[160]; u32 size, crc; } entry_t;

static int load_installed(entry_t **list) {
    int n = 0, cap = 512;
    *list = malloc(cap * sizeof **list);
    FILE *f = store_open(INSTALLED);
    char line[256];
    while (f && *list && fgets(line, sizeof line, f)) {
        if (n == cap) { entry_t *nl = realloc(*list, (cap *= 2) * sizeof **list); if (!nl) break; *list = nl; }
        if (sscanf(line, "%159[^\t]\t%u\t%x", (*list)[n].path, &(*list)[n].size, &(*list)[n].crc) == 3) n++;
    }
    if (f) fclose(f);
    return n;
}

static void save_installed(entry_t *list, int n) {
    int cap = n * 200 + 64, len = 0;
    char *buf = malloc(cap);
    if (!buf) return;
    for (int i = 0; i < n; i++) len += snprintf(buf + len, cap - len, "%s\t%u\t%08x\n", list[i].path, list[i].size, list[i].crc);
    store_write(INSTALLED, buf, len);
    free(buf);
}

static void mkdirs_for(const char *path) {
    char tmp[200];
    snprintf(tmp, sizeof tmp, "%s", path);
    char *p = strchr(tmp, ':');
    for (p = p ? p + 2 : tmp + 1; *p; p++) if (*p == '/') { *p = 0; mkdir(tmp, 0777); *p = '/'; }
}

static char status_line[96] = "not-run-yet";
int launcher_updated;                        // a new boot.dol came in: main relaunches into it when idle
const char *update_status(void) { return status_line; }

int update_run(int (*may_continue)(void), void (*log)(const char *fmt, ...)) {
    static int inited;
    if (!inited) { crc_init(); inited = 1; }
    static char manifest[256 * 1024];
    u32 mcrc;
    int v2 = 1;
    int mlen = http_get("manifest2.txt", NULL, manifest, sizeof manifest, &mcrc);
    if (mlen == -404) { v2 = 0; mlen = http_get("manifest.txt", NULL, manifest, sizeof manifest, &mcrc); }
    if (mlen <= 0) { snprintf(status_line, sizeof status_line, "no-manifest(%d)", mlen); return mlen; }
    entry_t *inst;
    int ninst = load_installed(&inst);
    int fetched = 0, failed = 0, pending = 0, recorded = 0;
    char *save;
    for (char *line = strtok_r(manifest, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        u32 size, crc, zsize = 0;
        char path[160];
        if (v2 ? sscanf(line, "%u %x %u %159[^\r\n]", &size, &crc, &zsize, path) != 4
               : sscanf(line, "%u %x %159[^\r\n]", &size, &crc, path) != 3) continue;
        if (strncmp(path, "sd:/", 4)) continue;
        int k = -1;
        for (int i = 0; i < ninst; i++) if (!strcmp(inst[i].path, path)) { k = i; break; }
        struct stat st;
        int exists = stat(path, &st) == 0;
        int have = exists && (u32)st.st_size == size;
        // Files the cabinet rewrites itself (RetroArch saves its core options at every game; the launcher keeps
        // its clock and screen in cabs/*.cfg) never match the published copy: fetch them only when the published
        // one changes, or every game would re-download them (and roll a new cabinet's calibration back).
        int own = !strcmp(path, "sd:/retroarch/retroarch-core-options.cfg") || !strncmp(path, "sd:/arcade/cabs/", 16);
        if (own && exists && (k < 0 || inst[k].crc == crc)) {
            if (k < 0) {                         // the card's own copy (card install): adopt it as this version
                if (ninst % 512 == 0) { entry_t *nl = realloc(inst, (ninst + 512) * sizeof *inst); if (nl) inst = nl; }
                k = ninst++;
                snprintf(inst[k].path, sizeof inst[k].path, "%s", path);
                inst[k].size = size; inst[k].crc = crc;
                recorded++;
            }
            continue;
        }
        if (k >= 0 && have && inst[k].crc == crc) continue;      // already installed
        if (k < 0 && have && file_crc(path) == crc) {           // on the card already (card install): just record it
            if (ninst % 512 == 0) { entry_t *nl = realloc(inst, (ninst + 512) * sizeof *inst); if (nl) inst = nl; }
            k = ninst++;
            snprintf(inst[k].path, sizeof inst[k].path, "%s", path);
            inst[k].size = size; inst[k].crc = crc;
            if (++recorded % 50 == 0) save_installed(inst, ninst);
            continue;
        }
        if (!may_continue()) { pending++; continue; }           // someone is playing: next time
        char tmp[200], ztmp[200], url[200];
        snprintf(tmp, sizeof tmp, "%s.new", path);
        snprintf(ztmp, sizeof ztmp, "%s.gz.new", path);
        u32 want = zsize ? zsize : size;         // bytes to download
        const char *dl = zsize ? ztmp : tmp;
        struct stat pst;                         // a partial download from last time: carry on from there
        long have_bytes = stat(dl, &pst) == 0 && (u32)pst.st_size < want ? (long)pst.st_size : 0;
        int u = snprintf(url, sizeof url, "files/");  // percent-encode (paths have spaces: "FB Alpha 2012")
        for (const char *c = path + 4; *c && u < (int)sizeof url - 4; c++) {
            if ((*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') || (*c >= '0' && *c <= '9') || strchr("/._-", *c))
                url[u++] = *c;
            else u += snprintf(url + u, sizeof url - u, "%%%02X", (unsigned char)*c);
        }
        if (zsize) u += snprintf(url + u, sizeof url - u, ".gz");
        url[u] = 0;
        mkdirs_for(path);
        u32 got_crc;
        int r = http_get_at(url, dl, NULL, 0, &got_crc, have_bytes);
        struct stat tst;
        long now_bytes = stat(dl, &tst) == 0 ? (long)tst.st_size : 0;
        if (now_bytes < (long)want) {            // broke off (Wi-Fi): keep what arrived, resume next time
            failed++;
            log("update: %s interrupted at %ld of %u bytes (%d)%s%s", path, now_bytes, want, r,
                zsize ? " gz" : "", have_bytes ? ", was resuming" : "");
            continue;
        }
        if (zsize) {                             // inflate the compressed copy into <path>.new
            long out = gunzip_file(ztmp, tmp);
            remove(ztmp);                        // a bad .gz starts over next time
            if (out < 0) { remove(tmp); failed++; log("update: %s gunzip failed (%ld)", path, out); continue; }
            stat(tmp, &tst);
            now_bytes = (long)tst.st_size;
        }
        got_crc = file_crc(tmp);                 // complete: check the whole file (the parts came separately)
        if (now_bytes != (long)size || got_crc != crc) {
            remove(tmp);
            failed++;
            log("update: %s failed (%ld bytes, crc %08x)", path, now_bytes, got_crc);
            continue;
        }
        remove(path);
        rename(tmp, path);
        if (!strcmp(path, "sd:/apps/wii-agent/boot.dol")) launcher_updated = 1;
        if (k < 0 && ninst % 512 == 0) { entry_t *nl = realloc(inst, (ninst + 512) * sizeof *inst); if (nl) inst = nl; }
        if (k < 0) k = ninst++;
        snprintf(inst[k].path, sizeof inst[k].path, "%s", path);
        inst[k].size = size; inst[k].crc = crc;
        fetched++;
        if (fetched % 10 == 0) save_installed(inst, ninst);
    }
    if (fetched || recorded) save_installed(inst, ninst);
    free(inst);
    snprintf(status_line, sizeof status_line, "%d-updated,%d-failed,%d-waiting,%d-checked", fetched, failed, pending, recorded);
    if (fetched || failed) log("update: %s", status_line);
    return failed ? -failed : fetched;      // anything left over (Wi-Fi broke off): the caller retries in 5 min
}
