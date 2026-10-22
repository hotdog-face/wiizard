// The game library: GameCube discs in sd:/games, in either layout Nintendont reads ("Name (USA).iso" or
// "Name [GAMEID]/game.iso"); Wii discs in sd:/wbfs (USB Loader GX); arcade sets listed in sd:/arcade/arcade.tsv.
// Box art from USB Loader GX / WiiFlow / RVLoader covers when there is some.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <dirent.h>
#include <sys/stat.h>
#include <gccore.h>
#include "catalog.h"

#define GAMES_DIR "sd:/games"
#define WBFS_DIR "sd:/wbfs"
#define ARCADE_TSV "sd:/arcade/arcade.tsv"
#define HIDDEN_TXT "sd:/arcade/hidden.txt"   // curation: games kept on the card but not shown (one rule per line)
#define AUTOHIDE_TXT "sd:/arcade/autohide.txt" // the launcher's own: games that failed to start twice (same rules)

static const char *COVER_DIRS[] = { "sd:/arcade/art/covers", "sd:/wiiflow/boxcovers", "sd:/wiiflow/covers", "sd:/apps/usbloader_gx/images",
                                     "sd:/rvloader/covers", NULL };

const char *system_name(int system) {
    switch (system) {
    case SYS_ARCADE: return "ARCADE CLASSICS";
    case SYS_CPS1: return "CAPCOM CPS-1";
    case SYS_CPS2: return "CAPCOM CPS-2";
    case SYS_NEOGEO: return "NEO GEO";
    case SYS_WII: return "NINTENDO WII";
    case SYS_GENESIS: return "SEGA GENESIS";
    case SYS_SNES: return "SUPER NINTENDO";
    case SYS_NES: return "NINTENDO NES";
    default: return "NINTENDO GAMECUBE";
    }
}

static int has_ext(const char *name, const char *ext) {
    size_t n = strlen(name), e = strlen(ext);
    return n > e && !strcasecmp(name + n - e, ext);
}

static int exists(const char *path) {
    struct stat st;
    return stat(path, &st) == 0;
}

// Disc id: the first 6 bytes of the image (CISO images start their data at 0x8000).
static int read_id(const char *path, char *id) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    unsigned char buf[6];
    int ok = fread(buf, 1, 6, f) == 6;
    if (ok && !memcmp(buf, "CISO", 4)) ok = fseek(f, 0x8000, SEEK_SET) == 0 && fread(buf, 1, 6, f) == 6;
    fclose(f);
    for (int i = 0; ok && i < 6; i++) ok = isalnum(buf[i]);
    if (ok) { memcpy(id, buf, 6); id[6] = 0; }
    return ok;
}

// "Burnout 2 - Point of Impact (USA).iso" -> "Burnout 2 - Point of Impact"; "Pikmin [GPIE01]" -> "Pikmin"
static void clean_title(const char *name, char *out, size_t size) {
    snprintf(out, size, "%s", name);
    char *dot = strrchr(out, '.');
    if (dot && (has_ext(out, ".iso") || has_ext(out, ".gcm") || has_ext(out, ".ciso"))) *dot = 0;
    for (char *p = out; *p; p++) {
        if (*p == '(' || *p == '[') { *p = 0; break; }
    }
    size_t n = strlen(out);
    while (n && (out[n - 1] == ' ' || out[n - 1] == '_')) out[--n] = 0;
    // No-Intro style "Legend of Zelda, The - The Wind Waker": the article goes back to the front
    static const char *const ART[] = { ", The", ", A", ", An" };
    for (int k = 0; k < 3; k++) {
        char *p = strstr(out, ART[k]);
        size_t al = strlen(ART[k]);
        if (!p || (p[al] && strncmp(p + al, " - ", 3))) continue;
        char head[96], rest[128];
        snprintf(head, sizeof head, "%.*s", (int)(p - out), out);
        snprintf(rest, sizeof rest, "%s", p + al);
        snprintf(out, size, "%s %s%s", ART[k] + 2, head, rest);
        break;
    }
}

static void find_cover(game_t *g) {
    char path[160];
    g->cover[0] = 0;
    for (int i = 0; COVER_DIRS[i]; i++) {
        snprintf(path, sizeof path, "%s/%s.png", COVER_DIRS[i], g->id);
        if (exists(path)) { snprintf(g->cover, sizeof g->cover, "%s", path); return; }
    }
}

static const char *sort_key(const char *t) { return strncasecmp(t, "The ", 4) ? t : t + 4; }   // A-Z ignores "The"
static int by_system_title(const void *a, const void *b) {
    const game_t *x = a, *y = b;
    if (x->system != y->system) return x->system - y->system;
    return strcasecmp(sort_key(x->title), sort_key(y->title));
}

static game_t *push(game_t *games, int *n, int *cap, const game_t *g) {
    if (*n == *cap) {
        game_t *more = realloc(games, (*cap *= 2) * sizeof *games);
        if (!more) return games;
        games = more;
    }
    games[(*n)++] = *g;
    return games;
}

// sd:/wbfs/<Title [ID]>/<ID>.wbfs
static game_t *scan_wii(game_t *games, int *n, int *cap) {
    DIR *d = opendir(WBFS_DIR);
    struct dirent *e;
    while (d && (e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char *lb = strrchr(e->d_name, '['), *rb = lb ? strchr(lb, ']') : NULL;
        if (!lb || !rb || rb - lb != 7) continue;
        game_t g;
        memset(&g, 0, sizeof g);
        memcpy(g.id, lb + 1, 6);
        snprintf(g.path, sizeof g.path, "%s/%s/%s.wbfs", WBFS_DIR, e->d_name, g.id);
        if (!exists(g.path)) continue;
        clean_title(e->d_name, g.title, sizeof g.title);
        g.system = SYS_WII;
        snprintf(g.vkey, sizeof g.vkey, "%s", g.id);
        find_cover(&g);
        games = push(games, n, cap, &g);
    }
    if (d) closedir(d);
    return games;
}

// system<TAB>zip<TAB>title<TAB>year<TAB>maker per line; the zip lives in sd:/roms/<system>/
static game_t *scan_arcade(game_t *games, int *n, int *cap) {
    FILE *f = fopen(ARCADE_TSV, "r");
    char line[400];
    while (f && fgets(line, sizeof line, f)) {
        char *field[6] = { 0 };
        char *p = line;
        for (int i = 0; i < 6 && p; i++) {
            field[i] = p;
            p = strchr(p, '\t');
            if (p) *p++ = 0;
        }
        if (!field[4]) continue;
        field[4][strcspn(field[4], "\r\n")] = 0;
        if (field[5]) field[5][strcspn(field[5], "\r\n")] = 0;
        game_t g;
        memset(&g, 0, sizeof g);
        if (!strcmp(field[0], "neogeo")) g.system = SYS_NEOGEO;
        else if (!strcmp(field[0], "cps1")) g.system = SYS_CPS1;
        else if (!strcmp(field[0], "cps2")) g.system = SYS_CPS2;
        else if (!strcmp(field[0], "arcade")) g.system = SYS_ARCADE;
        else if (!strcmp(field[0], "genesis")) g.system = SYS_GENESIS;
        else if (!strcmp(field[0], "snes")) g.system = SYS_SNES;
        else if (!strcmp(field[0], "nes")) g.system = SYS_NES;
        else continue;
        snprintf(g.core, sizeof g.core, "%s", field[5] && field[5][0] ? field[5]
                 : g.system == SYS_NEOGEO ? "fbalpha2012_neogeo" : g.system == SYS_GENESIS ? "genesis_plus_gx"
                 : g.system == SYS_SNES ? "snes9x2010" : g.system == SYS_NES ? "fceumm" : "fbalpha2012_cps1");
        snprintf(g.vkey, sizeof g.vkey, "%.*s", (int)strcspn(field[1], "."), field[1]);
        snprintf(g.rom, sizeof g.rom, "%s", field[1]);
        snprintf(g.path, sizeof g.path, "sd:/roms/%s/%s", field[0], field[1]);
        snprintf(g.title, sizeof g.title, "%s", field[2]);
        snprintf(g.year, sizeof g.year, "%s", field[3]);
        snprintf(g.maker, sizeof g.maker, "%s", field[4]);
        snprintf(g.id, sizeof g.id, "%.7s", field[1]);
        char art[160];
        snprintf(art, sizeof art, "sd:/arcade/art/%s/%.*s.png", field[0], (int)strcspn(field[1], "."), field[1]);
        if (exists(art)) snprintf(g.cover, sizeof g.cover, "%s", art);
        if (exists(g.path)) games = push(games, n, cap, &g);
    }
    if (f) fclose(f);
    return games;
}

// hidden.txt rules: "id:GXXE01" (disc id), "rom:mslug" (arcade zip stem), "path:(Disc 2)" (substring of the path).
static char hidden[400][64];
static int nhidden;

static void load_hidden(void) {
    const char *files[] = { HIDDEN_TXT, AUTOHIDE_TXT };
    char line[96];
    nhidden = 0;
    for (int i = 0; i < 2; i++) {
        FILE *f = fopen(files[i], "r");
        while (f && nhidden < 400 && fgets(line, sizeof line, f)) {
            line[strcspn(line, "\r\n")] = 0;
            if (line[0] && line[0] != '#') snprintf(hidden[nhidden++], sizeof hidden[0], "%s", line);
        }
        if (f) fclose(f);
    }
}

static int is_hidden(const game_t *g) {
    for (int i = 0; i < nhidden; i++) {
        const char *r = hidden[i];
        if (!strncmp(r, "id:", 3) && !strcasecmp(r + 3, g->id)) return 1;
        if (!strncmp(r, "rom:", 4) && g->rom[0] && !strncasecmp(r + 4, g->rom, strcspn(g->rom, "."))
            && strlen(r + 4) == strcspn(g->rom, ".")) return 1;
        if (!strncmp(r, "path:", 5) && strstr(g->path, r + 5)) return 1;
    }
    return 0;
}

// The finished list is cached on the card (catalog.cache): reading every disc header and probing art folders took
// ~7 s at each start, i.e. after every game. The cache is used while nothing it depends on changed: the names in
// sd:/games and sd:/wbfs, arcade.tsv, hidden.txt, autohide.txt and installed.tsv (rewritten by every update and
// card install, so new art or files invalidate it too).
#define CATALOG_CACHE "sd:/arcade/catalog.cache"
#define CATALOG_MAGIC 0x57495A31u            // "WIZ1"
static u32 fnv(u32 h, const void *p, size_t n) {
    const unsigned char *b = p;
    while (n--) { h ^= *b++; h *= 16777619u; }
    return h;
}
static u32 hash_file(u32 h, const char *path) {
    FILE *f = fopen(path, "rb");
    char buf[2048];
    size_t n;
    while (f && (n = fread(buf, 1, sizeof buf, f)) > 0) h = fnv(h, buf, n);
    if (f) fclose(f);
    return h;
}
static u32 hash_dir(u32 h, const char *dir) {
    DIR *d = opendir(dir);
    struct dirent *e;
    while (d && (e = readdir(d))) h = fnv(h, e->d_name, strlen(e->d_name) + 1);
    if (d) closedir(d);
    return h;
}
static u32 catalog_signature(void) {
    u32 h = fnv(2166136261u, "v1", 2);
    u32 sz = sizeof(game_t);
    h = fnv(h, &sz, sizeof sz);
    h = hash_dir(h, GAMES_DIR);
    h = hash_dir(h, WBFS_DIR);
    h = hash_file(h, ARCADE_TSV);
    h = hash_file(h, HIDDEN_TXT);
    h = hash_file(h, AUTOHIDE_TXT);
    struct stat st;
    if (stat("sd:/arcade/installed.tsv", &st) == 0) { h = fnv(h, &st.st_size, sizeof st.st_size); h = fnv(h, &st.st_mtime, sizeof st.st_mtime); }
    return h;
}
static game_t *catalog_scan_full(int *count);
game_t *catalog_scan(int *count) {
    u32 sig = catalog_signature(), hdr[3];
    FILE *f = fopen(CATALOG_CACHE, "rb");
    if (f && fread(hdr, sizeof hdr, 1, f) == 1 && hdr[0] == CATALOG_MAGIC && hdr[1] == sig && hdr[2] < 5000) {
        game_t *games = malloc((hdr[2] ? hdr[2] : 1) * sizeof *games);
        if (games && fread(games, sizeof *games, hdr[2], f) == hdr[2]) {
            fclose(f);
            *count = (int)hdr[2];
            return games;
        }
        free(games);
    }
    if (f) fclose(f);
    game_t *games = catalog_scan_full(count);
    if (games) {                             // write the cache (whole file, via .new: power-cut safe)
        FILE *o = fopen(CATALOG_CACHE ".new", "wb");
        u32 h2[3] = { CATALOG_MAGIC, sig, (u32)*count };
        int ok = o && fwrite(h2, sizeof h2, 1, o) == 1 && fwrite(games, sizeof *games, *count, o) == (size_t)*count;
        if (o) { fflush(o); ok &= fclose(o) == 0; }
        if (ok) { remove(CATALOG_CACHE); rename(CATALOG_CACHE ".new", CATALOG_CACHE); }
        else remove(CATALOG_CACHE ".new");
    }
    return games;
}

static game_t *catalog_scan_full(int *count) {
    load_hidden();
    int cap = 64, n = 0;
    game_t *games = malloc(cap * sizeof *games);
    DIR *d = opendir(GAMES_DIR);
    struct dirent *e;
    while (d && games && (e = readdir(d))) {
        if (e->d_name[0] == '.') continue;   // also skips macOS "._" files
        game_t g;
        memset(&g, 0, sizeof g);
        char full[300];
        snprintf(full, sizeof full, "%s/%s", GAMES_DIR, e->d_name);
        if (has_ext(e->d_name, ".iso") || has_ext(e->d_name, ".gcm") || has_ext(e->d_name, ".ciso")) {
            snprintf(g.path, sizeof g.path, "%s", full);
        } else {
            const char *inner[] = { "game.iso", "game.ciso", "game.gcm", NULL };
            for (int i = 0; inner[i] && !g.path[0]; i++) {
                char p[300];
                snprintf(p, sizeof p, "%s/%s", full, inner[i]);
                if (exists(p)) snprintf(g.path, sizeof g.path, "%s", p);
            }
            if (!g.path[0]) continue;        // e.g. the "Wii" folder (Wii discs are read from sd:/wbfs)
        }
        if (!read_id(g.path, g.id)) continue;
        clean_title(e->d_name, g.title, sizeof g.title);
        if (!g.title[0]) snprintf(g.title, sizeof g.title, "%s", g.id);
        g.system = SYS_GAMECUBE;
        snprintf(g.vkey, sizeof g.vkey, "%s", g.id);
        find_cover(&g);
        games = push(games, &n, &cap, &g);
    }
    if (d) closedir(d);
    if (games) games = scan_wii(games, &n, &cap);
    if (games) games = scan_arcade(games, &n, &cap);
    int kept = 0;                            // drop curated-out games
    for (int i = 0; games && i < n; i++)
        if (!is_hidden(&games[i])) games[kept++] = games[i];
    n = kept;
    if (games) qsort(games, n, sizeof *games, by_system_title);
    *count = n;
    return games;
}
