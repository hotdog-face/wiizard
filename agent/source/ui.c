// WIIZARD, the arcade launcher UI: 640x480 for the CRTs, drawn with our GX renderer (gfx.c).
// Look: "Maximal collage" (art direction 10, after Studio Moross; spec art/mockups/render20.py s10 and
// render_short.py kit10): pink halftone paper with cut blue/yellow shapes and starbursts (sd:/arcade/ui/bg.png),
// the selected game's clip on a taped, tilted photo on a white die-cut, neighbours as blue duotones, titles in
// Anton, yellow with a black stroke and offset shadow, slanted "tag" pills, a black bottom bar with square buttons.
//   GAMES:   cards for the games of one section; the center card plays the game's clip (gameplay first), side cards
//            show stills / box art. Left/right move, down (or B) goes to the category row, A plays, Y favourite.
//   FAVORITES / RECENT: virtual sections in front of the real ones (Y toggles a favourite; plays are counted).
//   COLLECTIONS (sd:/arcade/collections.tsv from the Mac): Quick Picks, Fighting, ... ordered by what gets played
//            on all cabinets, then ALL GAMES A-Z. Without the file: one section per system, as before.
//   Kid-proof: input is ignored for a moment after every screen change, so mashed buttons don't launch anything.
//   ATTRACT: when idle, a game (weighted toward favourites and what gets played) runs full screen with sound, a
//            slanted pink lower third and "PRESS A TO PLAY"; any button opens the menu on it.
//   INTRO (power-on): Mitchell's own wizard (art/wizard-anim, sd:/arcade/ui/wizard.wza) over the collage, the
//            WIIZARD logo slams in, then the game and system counts.
//   While the Mac works on this Wii: only a small pulsing dot by the clock (nothing branded for players).
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>                        // surfaces only (decoding/scaling); drawing is GX via gfx.c
#include <SDL2/SDL_image.h>
#include <SDL2/SDL_ttf.h>
#include <ogc/lwp_watchdog.h>
#include <wiiuse/wpad.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <strings.h>
#include <ctype.h>
#include <time.h>
#include <unistd.h>
#include <zlib.h>
#include "gfx.h"
#include "ui.h"
#include "video.h"
#include "audio.h"
#include "cab.h"
#include "store.h"
#include "resume.h"
#define W 640
#define H 480
#define FONT_UI "sd:/arcade/fonts/ui.ttf"            // fallbacks for a card without the collage fonts yet
#define FONT_DISPLAY "sd:/arcade/fonts/display.ttf"
#define FONT_POSTER "sd:/arcade/fonts/anton.ttf"     // Anton (OFL): titles, pills, buttons
#define FONT_TEXT "sd:/arcade/fonts/archivo.ttf"     // Archivo Black (OFL): sub-lines and small print
#define UI_BG "sd:/arcade/ui/bg.png"                 // the collage paper (art/make_ui.py)
#define UI_BAND "sd:/arcade/ui/band.png"             // attract: the slanted pink lower third
#define UI_WIZARD "sd:/arcade/ui/wizard.wza"         // Mitchell's wizard, animated (art/wizard-anim)
#define ATTRACT_SECS 9.0f
#define FADE_SECS 0.9f                       // attract: fade to black and back (calm, not a cut)
#define VIDEO_FADE_SECS 0.6f                 // a clip fades in over its still
#define IDLE_TO_ATTRACT_SECS 45.0f
#define COVER_CACHE 28
#define INPUT_LOCK_SECS 0.8f                 // after any screen change: mashed buttons don't fire off a game
#define BOOT_LOCK_SECS 2.0f                  // after start-up (e.g. back from a game with buttons still held)

// palette (RGBA): the collage. Yellow, hot pink, cobalt blue and black on pink paper.
#define C_YEL 0xFFE400FF
#define C_PNK 0xFF3C8CFF
#define C_BLU 0x2850FFFF
#define C_INK 0x0A0A0AFF
#define C_PAPER 0xFFAACDFF
#define C_WHITE 0xFFFFFFFF
#define C_TAPE 0xFFFFC8C8
#define C_DUO_LIGHT 0xFFDCF0FF               // neighbours: duotone blue -> this
static const SDL_Color WHITE = { 255, 255, 255, 255 }, INK = { 10, 10, 10, 255 }, YELLOW = { 255, 228, 0, 255 },
                       PINK = { 255, 60, 140, 255 };

enum { MODE_ATTRACT, MODE_GAMES };
#define SYS_FAVORITES 100
#define SYS_RECENT 101
#define SYS_ALL 102
#define SYS_COLLECTION 200                   // + index into coll_*
#define STATS_FILE "sd:/arcade/stats.tsv"
#define META_FILE "sd:/arcade/meta.tsv"
#define COLLECTIONS_FILE "sd:/arcade/collections.tsv"   // from the Mac: name<TAB>key,key,... (best first)
#define ATTRACT_VOLUME 110
#define SFX_VOLUME 100

static TTF_Font *f_top, *f_btn, *f_badge, *f_hint, *f_text;   // Anton 24 / 20 / 18, Archivo Black 18
static u64 ticks0;
static u32 now_ms(void) { return ticks_to_millisecs(gettime() - ticks0); }
static game_t *games;
static int ngames;

// sections in display order: Favorites and Recent (when they have games), then each system on the card
#define MAX_SYS 24
#define MAX_COLL 20
static int ncoll, *coll_list[MAX_COLL], coll_count[MAX_COLL];
static char coll_name[MAX_COLL][32], coll_upper[MAX_COLL][32];
static int nsys, sys_id[MAX_SYS], sys_count[MAX_SYS], sys_hero[MAX_SYS], sys_pos[MAX_SYS];
static int *sys_list[MAX_SYS];               // game indices of each section

// per game: plays, last played (epoch), favourite; metadata from the Mac (ScreenScraper)
static int *plays, *favs;
static long *last_play;
typedef struct { char players[12], genre[40], rating[8]; char *desc; } meta_t;
static meta_t *meta;
static char **hiscore;                       // per game: "12,340" or NULL (sd:/arcade/hiscores.tsv from the Mac)
static int fullscreen;                       // SHOWCASE: clip fills the screen

static int mode = MODE_ATTRACT;
static int shown = -1, next_shown = -1;     // attract: current game and the one fading in
static float attract_t, fade;
static int cur_sys;                          // browse: selected section (index into sys_*)
static int cat_focus;                        // browse: 1 = the category row has the focus, 0 = the game cards
static float carousel, sys_carousel;         // animated positions
static float carousel_v, sys_carousel_v;     // and their velocities (spring)

static void spring(float *x, float *v, float target, float dt) {
    const float k = 110.0f, c = 2.0f * 10.4880885f;   // stiffness; damping = 2*sqrt(k): critically damped
    for (int i = 0; i < 4; i++) {            // small steps keep it stable at 60 fps and after a slow frame
        float h = dt / 4;
        *v += (k * (target - *x) - c * *v) * h;
        *x += *v * h;
    }
    if (fabsf(target - *x) < 0.002f && fabsf(*v) < 0.01f) { *x = target; *v = 0; }
}
static float idle;
static float input_lock = BOOT_LOCK_SECS;
static u32 last_ticks;
static float clock_s;
static u32 repeat_dir;
static float repeat_t;
static volatile int cal_sx = 90, cal_sy = 90, cal_x, cal_y;
static volatile float cal_marks_until;
static char notice_head[64], notice_detail[96];
static float notice_until;
static void draw_notice(void);

static int frame_no;
static void crumb(const char *label) {      // breadcrumbs: first time each step is reached goes to the log
    if (frame_no < 2) { agent_log("ui f%d: %s", frame_no, label); return; }
    static const char *seen[32];
    for (int i = 0; i < 32; i++) {
        if (seen[i] == label) return;
        if (!seen[i]) { seen[i] = label; agent_log("ui: %s", label); return; }
    }
}

// ---------------------------------------------------------------- systems

static const char *sys_long(int s) {
    if (s >= SYS_COLLECTION) return coll_name[s - SYS_COLLECTION];
    switch (s) {
    case SYS_ALL: return "All Games";
    case SYS_FAVORITES: return "Favorites";
    case SYS_RECENT: return "Recently Played";
    case SYS_ARCADE: return "Arcade Classics";
    case SYS_CPS1: return "Capcom CPS-1";
    case SYS_CPS2: return "Capcom CPS-2";
    case SYS_NEOGEO: return "Neo Geo";
    case SYS_WII: return "Nintendo Wii";
    case SYS_GENESIS: return "Sega Genesis";
    case SYS_SNES: return "Super Nintendo";
    case SYS_NES: return "Nintendo NES";
    default: return "GameCube";
    }
}

static const char *sys_short(int s) {
    if (s >= SYS_COLLECTION) return coll_upper[s - SYS_COLLECTION];
    switch (s) {
    case SYS_ALL: return "ALL GAMES";
    case SYS_FAVORITES: return "FAVORITES";
    case SYS_RECENT: return "RECENT";
    case SYS_ARCADE: return "ARCADE";
    case SYS_CPS1: return "CPS-1";
    case SYS_CPS2: return "CPS-2";
    case SYS_NEOGEO: return "NEO GEO";
    case SYS_WII: return "WII";
    case SYS_GENESIS: return "GENESIS";
    case SYS_SNES: return "SNES";
    case SYS_NES: return "NES";
    default: return "GAMECUBE";
    }
}

// Flagship game shown on each system's card (first one present wins).
static const char *HEROES[][4] = {
    [SYS_ARCADE] = { "pacman", "dkong", "galaxian", NULL },
    [SYS_CPS1] = { "captcomm", "ffight", "sf2ce", NULL },
    [SYS_CPS2] = { "ssf2t", "sfa3", "mvsc", NULL },
    [SYS_NEOGEO] = { "mslug", "mslugx", "kof98", NULL },
    [SYS_GAMECUBE] = { "GALE01", "GM4E01", "GMSE01", NULL },
    [SYS_WII] = { "SMNE01", "SF8E01", "STKE08", NULL },
    [SYS_GENESIS] = { "mdsonc2", "mdsor2", "mdgunst", NULL },
    [SYS_SNES] = { "snsmw", "sntmnt4", "snsmk", NULL },
    [SYS_NES] = { "nesmb3", "necontr", "netmnt2", NULL },
};

static void add_section(int id, int *list, int n) {
    if (nsys >= MAX_SYS || n <= 0) { free(list); return; }
    sys_id[nsys] = id;
    sys_list[nsys] = list;
    sys_count[nsys] = n;
    sys_hero[nsys] = list[0];
    sys_pos[nsys] = 0;
    int found = 0;
    for (int h = 0; id > 0 && id <= SYS_NES && !found && HEROES[id][h]; h++)   // a flagship game on each real system's card
        for (int k = 0; k < n && !found; k++)
            if (!strcmp(games[list[k]].vkey, HEROES[id][h])) { sys_hero[nsys] = list[k]; found = 1; }
    nsys++;
}

static int by_title(const void *a, const void *b) {
    const char *x = games[*(const int *)a].title, *y = games[*(const int *)b].title;
    if (!strncasecmp(x, "the ", 4)) x += 4;
    if (!strncasecmp(y, "the ", 4)) y += 4;
    return strcasecmp(x, y);
}

static int by_last_play(const void *a, const void *b) {
    long x = last_play[*(const int *)a], y = last_play[*(const int *)b];
    return x < y ? 1 : x > y ? -1 : 0;
}

// (Re)build the sections; keeps the selected game where it can.
static void build_systems(void) {
    int keep_sys = nsys ? sys_id[cur_sys] : -1;
    int keep_game = nsys && sys_count[cur_sys] ? sys_list[cur_sys][sys_pos[cur_sys]] : -1;
    for (int s = 0; s < nsys; s++) free(sys_list[s]);
    nsys = 0;
    int *fav = malloc(ngames * sizeof *fav), nf = 0, *rec = malloc(ngames * sizeof *rec), nr = 0;
    for (int i = 0; i < ngames; i++) {
        if (favs && favs[i]) fav[nf++] = i;
        if (last_play && last_play[i] > 0) rec[nr++] = i;
    }
    if (nr) qsort(rec, nr, sizeof *rec, by_last_play);
    add_section(SYS_FAVORITES, fav, nf);
    add_section(SYS_RECENT, rec, nr > 15 ? 15 : nr);
    if (ncoll) {                             // collections from the Mac, then everything A-Z
        for (int c = 0; c < ncoll; c++) {
            if (!coll_count[c] || !cab_wants_collection(coll_name[c])) continue;
            int *list = malloc(coll_count[c] * sizeof *list);
            memcpy(list, coll_list[c], coll_count[c] * sizeof *list);
            add_section(SYS_COLLECTION + c, list, coll_count[c]);
        }
        int *all = malloc(ngames * sizeof *all);
        for (int i = 0; i < ngames; i++) all[i] = i;
        qsort(all, ngames, sizeof *all, by_title);
        add_section(SYS_ALL, all, ngames);
    }
    for (int i = 0; !ncoll && i < ngames;) {
        int j = i;
        while (j < ngames && games[j].system == games[i].system) j++;
        int *list = malloc((j - i) * sizeof *list);
        for (int k = i; k < j; k++) list[k - i] = k;
        add_section(games[i].system, list, j - i);
        i = j;
    }
    cur_sys = 0;
    for (int s = 0; s < nsys; s++) {
        if (sys_id[s] == keep_sys) {
            cur_sys = s;
            for (int k = 0; k < sys_count[s]; k++) if (sys_list[s][k] == keep_game) sys_pos[s] = k;
        }
    }
    if (keep_sys < 0) {                      // first build: start on the first real system
        for (int s = 0; s < nsys; s++) if (sys_id[s] < 100 || sys_id[s] >= SYS_COLLECTION) { cur_sys = s; break; }
    }
}

static int cur_game(void) { return nsys && sys_count[cur_sys] ? sys_list[cur_sys][sys_pos[cur_sys]] : -1; }

// first section (system or collection, not Favorites/Recent/All) that holds game gi
static int sys_of(int gi) {
    for (int pass = 0; pass < 2; pass++)
    for (int s = 0; s < nsys; s++) {
        if (pass == 0 ? (sys_id[s] >= 100 && sys_id[s] < SYS_COLLECTION) : sys_id[s] != SYS_ALL) continue;
        for (int k = 0; k < sys_count[s]; k++) if (sys_list[s][k] == gi) { sys_pos[s] = k; return s; }
    }
    return 0;
}

// ---------------------------------------------------------------- stats and metadata

static void save_stats(void) {             // one whole-file write (power-cut safe), only on a play or a favourite
    int cap = 4096, n = 0;
    char *buf = malloc(cap);
    for (int i = 0; buf && i < ngames; i++) {
        if (!plays[i] && !favs[i]) continue;
        if (n + 96 > cap) { char *nb = realloc(buf, cap *= 2); if (!nb) break; buf = nb; }
        n += snprintf(buf + n, cap - n, "%s\t%d\t%ld\t%d\n", games[i].vkey, plays[i], last_play[i], favs[i]);
    }
    if (buf) store_write(STATS_FILE, buf, n);
    free(buf);
}

static int find_key(const char *key) {
    for (int i = 0; i < ngames; i++) if (!strcmp(games[i].vkey, key)) return i;
    return -1;
}

static void load_stats(void) {
    free(plays); free(favs); free(last_play);
    plays = calloc(ngames ? ngames : 1, sizeof *plays);
    favs = calloc(ngames ? ngames : 1, sizeof *favs);
    last_play = calloc(ngames ? ngames : 1, sizeof *last_play);
    FILE *f = store_open(STATS_FILE);
    char key[32];
    int p, fv;
    long l;
    while (f && fscanf(f, "%31[^\t]\t%d\t%ld\t%d\n", key, &p, &l, &fv) == 4) {
        int gi = find_key(key);
        if (gi >= 0) { plays[gi] = p; last_play[gi] = l; favs[gi] = fv; }
    }
    if (f) fclose(f);
}

static void load_hiscores(void) {           // key<TAB>score (formatted by the Mac, e.g. 12,340)
    if (hiscore) for (int i = 0; i < ngames; i++) free(hiscore[i]);
    free(hiscore);
    hiscore = calloc(ngames ? ngames : 1, sizeof *hiscore);
    FILE *f = fopen("sd:/arcade/hiscores.tsv", "r");
    char line[96];
    while (f && hiscore && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        char *tab = strchr(line, '\t');
        if (!tab || line[0] == '#') continue;
        *tab = 0;
        int gi = find_key(line);
        if (gi >= 0 && tab[1]) hiscore[gi] = strdup(tab + 1);
    }
    if (f) fclose(f);
}

static void load_collections(void) {
    for (int c = 0; c < ncoll; c++) free(coll_list[c]);
    ncoll = 0;
    FILE *f = fopen(COLLECTIONS_FILE, "r");
    static char line[8192];
    while (f && ncoll < MAX_COLL && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0;
        char *tab = strchr(line, '\t');
        if (line[0] == '#' || !tab) continue;
        *tab = 0;
        int c = ncoll, n = 0;
        coll_list[c] = malloc((ngames ? ngames : 1) * sizeof(int));
        for (char *k = strtok(tab + 1, ","); k && coll_list[c]; k = strtok(NULL, ",")) {
            if (k[0] == '@') {               // a whole system, from what's on this card: @gamecube, @wii, @arcade...
                int sys = !strcmp(k, "@gamecube") ? SYS_GAMECUBE : !strcmp(k, "@wii") ? SYS_WII : !strcmp(k, "@cps1") ? SYS_CPS1
                        : !strcmp(k, "@cps2") ? SYS_CPS2 : !strcmp(k, "@neogeo") ? SYS_NEOGEO : !strcmp(k, "@genesis") ? SYS_GENESIS
                        : !strcmp(k, "@snes") ? SYS_SNES : !strcmp(k, "@nes") ? SYS_NES : SYS_ARCADE;
                for (int gi = 0; gi < ngames && n < ngames; gi++) if (games[gi].system == sys) coll_list[c][n++] = gi;
                continue;
            }
            int gi = find_key(k);
            if (gi >= 0 && n < ngames) coll_list[c][n++] = gi;
        }
        if (!n) { free(coll_list[c]); coll_list[c] = NULL; continue; }
        coll_count[c] = n;
        snprintf(coll_name[c], sizeof coll_name[c], "%s", line);
        for (int i = 0; i < 32; i++) coll_upper[c][i] = toupper((unsigned char)coll_name[c][i]);
        ncoll++;
    }
    if (f) fclose(f);
}

// meta.tsv: key<TAB>players<TAB>rating 0..1<TAB>genre<TAB>description (one line)
static void load_meta(void) {
    if (meta) for (int i = 0; i < ngames; i++) free(meta[i].desc);
    free(meta);
    meta = calloc(ngames ? ngames : 1, sizeof *meta);
    FILE *f = fopen(META_FILE, "r");
    static char line[1600];
    while (f && fgets(line, sizeof line, f)) {
        char *field[5] = { 0 }, *p = line;
        for (int i = 0; i < 5 && p; i++) { field[i] = p; p = strchr(p, '\t'); if (p) *p++ = 0; }
        if (!field[4]) continue;
        field[4][strcspn(field[4], "\r\n")] = 0;
        int gi = find_key(field[0]);
        if (gi < 0) continue;
        snprintf(meta[gi].players, sizeof meta[gi].players, "%s", field[1]);
        snprintf(meta[gi].rating, sizeof meta[gi].rating, "%s", field[2]);
        snprintf(meta[gi].genre, sizeof meta[gi].genre, "%s", field[3]);
        meta[gi].desc = strdup(field[4]);
    }
    if (f) fclose(f);
}

#define MENU_POS_FILE "sd:/arcade/menu_pos.txt"   // where the player was: back there after the game

void ui_record_launch(int gi) {
    if (gi < 0 || gi >= ngames) return;
    plays[gi]++;
    last_play[gi] = (long)time(NULL);
    save_stats();
}

void ui_remember_spot(int gi) {               // the section the game was picked from (Fighting, Favorites...)
    if (gi < 0 || gi >= ngames) return;
    store_printf(MENU_POS_FILE, "%d %s\n", mode == MODE_GAMES && nsys ? sys_id[cur_sys] : -1, games[gi].vkey);
}

static int fav_anim_game = -1, fav_anim_on;   // the heart's pop / shrink after Y
static float fav_anim_t0;

static void toggle_favorite(int gi) {
    if (gi < 0) return;
    favs[gi] = !favs[gi];
    fav_anim_game = gi; fav_anim_on = favs[gi]; fav_anim_t0 = clock_s;
    save_stats();
    build_systems();
}

// ---------------------------------------------------------------- text

// Rendered text, cached as textures. Evicting one costs a GPU wait (gfx_tex_free), so the cache is roomy (192) and
// found by hash first, not by comparing every string.
#define TEXT_CACHE 192
typedef struct { TTF_Font *font; u32 hash; char text[520]; SDL_Color c; int wrap; gfx_tex *tex; int w, h; u32 used; } text_t;
static text_t texts[TEXT_CACHE];
static u32 str_hash(const char *s);

static gfx_tex *surface_tex(SDL_Surface *surf) {
    SDL_Surface *argb = surf->format->format == SDL_PIXELFORMAT_ARGB8888 ? surf
                      : SDL_ConvertSurfaceFormat(surf, SDL_PIXELFORMAT_ARGB8888, 0);
    if (!argb) return NULL;
    gfx_tex *t = gfx_tex_from_argb(argb->pixels, argb->w, argb->h, argb->pitch);
    if (argb != surf) SDL_FreeSurface(argb);
    return t;
}

static gfx_tex *text_tex(TTF_Font *font, const char *s, SDL_Color c, int wrap, int *w, int *h) {
    if (!font || !s || !*s) return NULL;
    text_t *slot = &texts[0];
    u32 hash = str_hash(s) ^ ((u32)c.r << 24 | (u32)c.g << 16 | (u32)c.b << 8 | (u32)wrap) ^ (u32)(uintptr_t)font;
    for (int i = 0; i < TEXT_CACHE; i++) {
        text_t *t = &texts[i];
        if (t->tex && t->hash == hash && t->font == font && t->wrap == wrap && !memcmp(&t->c, &c, sizeof c) && !strcmp(t->text, s)) {
            t->used = now_ms();
            *w = t->w; *h = t->h;
            return t->tex;
        }
        if (!t->tex || t->used < slot->used) slot = t;
    }
    if (slot->tex) gfx_tex_free(slot->tex);
    slot->tex = NULL;
    SDL_Surface *surf = wrap ? TTF_RenderUTF8_Blended_Wrapped(font, s, c, wrap) : TTF_RenderUTF8_Blended(font, s, c);
    if (!surf) return NULL;
    slot->tex = surface_tex(surf);
    slot->w = surf->w; slot->h = surf->h;
    SDL_FreeSurface(surf);
    if (!slot->tex) return NULL;
    slot->font = font; slot->c = c; slot->wrap = wrap; slot->used = now_ms(); slot->hash = hash;
    snprintf(slot->text, sizeof slot->text, "%s", s);
    *w = slot->w; *h = slot->h;
    return slot->tex;
}

// Text widths are measured a lot every frame (card titles, pills, fitting): measuring with FreeType is slow on
// the Wii, so widths are remembered (small direct-mapped cache, by font + string).
typedef struct { TTF_Font *font; u32 hash; int w; char s[96]; } width_t;
static width_t widths_cache[256];
static u32 str_hash(const char *s) { u32 h = 2166136261u; while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; } return h; }
static int text_w(TTF_Font *font, const char *s) {
    if (!font || !s || !*s) return 0;
    u32 h = str_hash(s) ^ (u32)(uintptr_t)font;
    width_t *c = &widths_cache[h & 255];
    if (c->font == font && c->hash == h && strlen(s) < sizeof c->s && !strcmp(c->s, s)) return c->w;
    int w = 0, hh = 0;
    TTF_SizeUTF8(font, s, &w, &hh);
    if (strlen(s) < sizeof c->s) { c->font = font; c->hash = h; c->w = w; snprintf(c->s, sizeof c->s, "%s", s); }
    return w;
}

static void upper(const char *s, char *out, int n) {
    int i = 0;
    for (; s && s[i] && i < n - 1; i++) out[i] = toupper((unsigned char)s[i]);
    out[i] = 0;
}
static int font_h(TTF_Font *f) { return f ? TTF_FontHeight(f) : 20; }

// align: 0 left, 1 center, 2 right (x is the anchor); y = top. Capitals, like every label in the collage.
// Returns the height drawn.
static int draw_text(TTF_Font *font, const char *s, SDL_Color c, int x, int y, int align, int wrap, Uint8 alpha) {
    int w, h;
    char up[520];
    upper(s, up, sizeof up);
    gfx_tex *t = text_tex(font, up, c, wrap, &w, &h);
    if (!t) return 0;
    float tx = align == 1 ? x - w / 2 : align == 2 ? x - w : x;
    gfx_tex_draw(t, tx, y, w, h, alpha);
    return h;
}

// White text tinted rgba (for colours that animate: one texture, not one per shade).
static int draw_tint(TTF_Font *font, const char *s, u32 rgba, int x, int y, int align) {
    int w, h;
    char up[160];
    upper(s, up, sizeof up);
    gfx_tex *t = text_tex(font, up, WHITE, 0, &w, &h);
    if (!t) return 0;
    float tx = align == 1 ? x - w / 2 : align == 2 ? x - w : x;
    gfx_tex_draw_tint(t, tx, y, w, h, rgba, rgba);
    return w;
}

// The offset from a line's top to the middle of its capitals (to centre capitals on a y).
static int p_cap_of(TTF_Font *f) {
    int minx, maxx, miny, maxy, adv;
    if (f && TTF_GlyphMetrics(f, 'H', &minx, &maxx, &miny, &maxy, &adv) == 0) return TTF_FontAscent(f) - maxy / 2;
    return font_h(f) / 2;
}

// One line that must fit: cut at maxw with "..." (upper-cased by draw_text).
typedef struct { TTF_Font *font; int maxw; u32 hash; char in[96], out[100]; } fit_t;
static fit_t fit_cache[64];
static const char *fit_line(TTF_Font *font, const char *s, int maxw) {
    u32 h = str_hash(s) ^ (u32)maxw * 2654435761u ^ (u32)(uintptr_t)font;
    fit_t *fc = &fit_cache[h & 63];
    if (fc->font == font && fc->maxw == maxw && fc->hash == h && !strcmp(fc->in, s)) return fc->out;   // fitted before
    static char buf[160];
    upper(s, buf, sizeof buf);
    if (text_w(font, buf) > maxw) {
        size_t n = strlen(buf);
        while (n > 1) {
            buf[--n] = 0;
            while (n > 1 && buf[n - 1] == ' ') buf[--n] = 0;
            char t[164]; snprintf(t, sizeof t, "%s...", buf);
            if (text_w(font, t) <= maxw) { snprintf(buf, sizeof buf, "%s", t); break; }
        }
    }
    if (strlen(s) < sizeof fc->in) {
        fc->font = font; fc->maxw = maxw; fc->hash = h;
        snprintf(fc->in, sizeof fc->in, "%s", s); snprintf(fc->out, sizeof fc->out, "%s", buf);
    }
    return buf;
}
static int draw_text_fit(TTF_Font *font, const char *s, SDL_Color c, int x, int y, int align, int maxw, Uint8 alpha) {
    return draw_text(font, fit_line(font, s, maxw), c, x, y, align, 0, alpha);
}

// ---------------------------------------------------------------- collage shapes

// A rotated local frame (cards and titles are tilted): local x, y around an origin, deg clockwise on screen.
typedef struct { float x, y, c, s; } frame_t;
static frame_t frame_at(float x, float y, float deg) {
    float r = deg * (float)M_PI / 180;
    return (frame_t){ x, y, cosf(r), sinf(r) };
}
static void fr_quad(const frame_t *f, float x, float y, float w, float h, float *q) {
    const float px[4] = { x, x + w, x + w, x }, py[4] = { y, y, y + h, y + h };
    for (int i = 0; i < 4; i++) {
        q[2 * i] = f->x + px[i] * f->c - py[i] * f->s;
        q[2 * i + 1] = f->y + px[i] * f->s + py[i] * f->c;
    }
}
static void fr_rect(const frame_t *f, float x, float y, float w, float h, u32 rgba) {
    float q[8];
    fr_quad(f, x, y, w, h, q);
    gfx_poly(q, 4, rgba);
}
static void fr_tex(const frame_t *f, gfx_tex *t, float x, float y, float w, float h, u32 rgba) {
    float q[8];
    fr_quad(f, x, y, w, h, q);
    gfx_tex_quad(t, q, rgba);
}
// Text in a frame, tinted rgba (rendered white once); y = top. Returns its width.
static int fr_text(const frame_t *f, TTF_Font *font, const char *s, u32 rgba, float x, float y, int align) {
    int w, h;
    char up[160];
    upper(s, up, sizeof up);
    gfx_tex *t = text_tex(font, up, WHITE, 0, &w, &h);
    if (!t) return 0;
    fr_tex(f, t, align == 1 ? x - w / 2.0f : align == 2 ? x - w : x, y, w, h, rgba);
    return w;
}

// A straight stroke from x0, y0 to x1, y1, wid pixels wide (outlines: never a 1-pixel line on a 480i CRT).
static void stroke(float x0, float y0, float x1, float y1, float wid, u32 rgba) {
    float dx = x1 - x0, dy = y1 - y0, l = sqrtf(dx * dx + dy * dy);
    if (l < 0.01f) return;
    float nx = -dy / l * wid / 2, ny = dx / l * wid / 2;
    float q[8] = { x0 + nx, y0 + ny, x1 + nx, y1 + ny, x1 - nx, y1 - ny, x0 - nx, y0 - ny };
    gfx_poly(q, 4, rgba);
}

// The slanted "tag" (a parallelogram leaning right, as cut from a poster): filled and/or outlined.
#define TAG_SLANT 8
static void tag(float x, float y, float w, float h, u32 fill, u32 line) {
    float q[8] = { x, y, x + w, y, x + w - TAG_SLANT, y + h, x - TAG_SLANT, y + h };
    if (fill & 0xFF) gfx_poly(q, 4, fill);
    if (line & 0xFF)
        for (int i = 0; i < 4; i++) stroke(q[2 * i], q[2 * i + 1], q[(2 * i + 2) % 8], q[(2 * i + 3) % 8], 2, line);
}

// Display type (Anton): a fill colour, a black stroke and a black offset shadow, rotated deg about its anchor.
// align 0: x = left edge, 1: x = centre; y = the vertical centre of the capitals. Returns the width drawn.
enum { P_86, P_58, P_48, P_40, P_34, P_28, P_N };
static const int P_SIZE[P_N] = { 86, 58, 48, 40, 34, 28 };
static TTF_Font *pf[P_N], *pf_line[P_N];     // fill and outlined twin of each size
static int p_out[P_N], p_cap[P_N];            // outline width; offset from the line's top to the middle of the caps
static float poster(int p, const char *s, float x, float y, int align, float deg, float scale, u32 fill, u8 alpha) {
    char up[160];
    upper(s, up, sizeof up);
    int fw, fh, sw = 0, sh = 0;
    gfx_tex *ft = text_tex(pf[p], up, WHITE, 0, &fw, &fh);
    if (!ft) return 0;
    gfx_tex *st = pf_line[p] ? text_tex(pf_line[p], up, WHITE, 0, &sw, &sh) : NULL;
    int o = st ? p_out[p] : 0;
    if (!st) { sw = fw; sh = fh; }
    frame_t f = frame_at(x, y, deg);
    float lx = align == 1 ? -sw * scale / 2 : 0, ly = -(p_cap[p] + o) * scale, sd = (p == P_86 ? 6 : 4) * scale;
    fr_tex(&f, st ? st : ft, lx + sd, ly + sd, sw * scale, sh * scale, (C_INK & 0xFFFFFF00) | alpha);
    if (st) fr_tex(&f, st, lx, ly, sw * scale, sh * scale, (C_INK & 0xFFFFFF00) | alpha);
    fr_tex(&f, ft, lx + o * scale, ly + o * scale, fw * scale, fh * scale, (fill & 0xFFFFFF00) | alpha);
    return sw * scale;
}
static int poster_w(int p, const char *s) {
    char up[160];
    upper(s, up, sizeof up);
    return text_w(pf_line[p] ? pf_line[p] : pf[p], up);
}
// The biggest size from `from` down to `to` that fits maxw (or `to`).
static int poster_fit(const char *s, int maxw, int from, int to) {
    for (int p = from; p < to; p++) if (poster_w(p, s) <= maxw) return p;
    return to;
}

// ---------------------------------------------------------------- art

typedef struct { int game; gfx_tex *tex; int w, h; u32 used; float born; } cover_t;
static cover_t covers[COVER_CACHE];

// Card pictures load on a worker thread (decoding a JPEG/PNG took long enough to make scrolling hitch): the main
// thread asks for a picture and draws nothing (then a short fade-in) until it's ready. Newest requests first.
// The picture: a still from the game's own clip (videos/stills on the Mac), so the card turns into its moving
// clip without a jump; box art / flyer only for games without one. WiiFlow's boxcovers: the front panel only.
#define COVER_REQ 12
static mutex_t cov_lock = LWP_MUTEX_NULL;
static int cov_req[COVER_REQ], cov_nreq, cov_working = -1;
static struct { int gi, w, h; u32 *pix; } cov_done[6];
static int cov_ndone;
static lwp_t cov_thread = LWP_THREAD_NULL;

static u32 *decode_cover(int gi, int *w_out, int *h_out) {
    char still[96];
    snprintf(still, sizeof still, "sd:/arcade/art/stills/%s.jpg", games[gi].vkey);
    SDL_Surface *img = IMG_Load(still);
    int is_still = img != NULL;
    if (!img && games[gi].cover[0]) img = IMG_Load(games[gi].cover);
    if (!img) return NULL;
    SDL_Surface *argb = SDL_ConvertSurfaceFormat(img, SDL_PIXELFORMAT_ARGB8888, 0);
    SDL_FreeSurface(img);
    if (!argb) return NULL;
    SDL_Rect src = { 0, 0, argb->w, argb->h };
    if (!is_still && strstr(games[gi].cover, "boxcovers") && argb->w > argb->h * 1.15f) {
        src.w = (int)(argb->h * 0.71f);
        src.x = argb->w - src.w;
    }
    int tw = 256, th = (int)(256.0f * src.h / src.w);
    if (th > 280) { th = 280; tw = (int)(280.0f * src.w / src.h); }
    SDL_Surface *small = SDL_CreateRGBSurfaceWithFormat(0, tw, th, 32, SDL_PIXELFORMAT_ARGB8888);
    u32 *pix = NULL;
    if (small) {
        SDL_Rect dst = { 0, 0, tw, th };
        SDL_BlitScaled(argb, &src, small, &dst);
        pix = malloc(tw * th * 4);
        if (pix) for (int y = 0; y < th; y++) memcpy(pix + y * tw, (u8 *)small->pixels + y * small->pitch, tw * 4);
        SDL_FreeSurface(small);
        // The alpha channel carries the picture's luminance, stretched to the full range (the neighbours' blue
        // duotone reads it, gfx_tex_quad_duo); pictures are drawn ignoring alpha (gfx_tex_quad_opaque).
        int lo = 255, hi = 0;
        for (int i = 0; pix && i < tw * th; i++) {
            u32 p = pix[i];
            int l = (((p >> 16) & 255) * 77 + ((p >> 8) & 255) * 150 + (p & 255) * 29) >> 8;
            pix[i] = (p & 0xFFFFFF) | (u32)l << 24;
            if (l < lo) lo = l;
            if (l > hi) hi = l;
        }
        int span = hi - lo > 16 ? hi - lo : 16;
        for (int i = 0; pix && i < tw * th; i++) {
            int l = ((int)(pix[i] >> 24) - lo) * 255 / span;
            pix[i] = (pix[i] & 0xFFFFFF) | (u32)(l < 0 ? 0 : l > 255 ? 255 : l) << 24;
        }
    }
    SDL_FreeSurface(argb);
    *w_out = tw; *h_out = th;
    return pix;
}

static void *cover_worker(void *unused) {
    for (;;) {
        int gi = -1;
        LWP_MutexLock(cov_lock);
        if (cov_nreq && cov_ndone < 6) { gi = cov_req[--cov_nreq]; cov_working = gi; }
        LWP_MutexUnlock(cov_lock);
        if (gi < 0) { usleep(4000); continue; }
        int w = 0, h = 0;
        u32 *pix = decode_cover(gi, &w, &h);
        LWP_MutexLock(cov_lock);
        cov_done[cov_ndone].gi = gi; cov_done[cov_ndone].pix = pix;
        cov_done[cov_ndone].w = w; cov_done[cov_ndone].h = h;
        cov_ndone++;
        cov_working = -1;
        LWP_MutexUnlock(cov_lock);
    }
    return NULL;
}

static unsigned char *no_cover;              // per game: nothing to show (no still, no art)

// Once per frame, before drawing: finished pictures become textures (cheap), replacing the least used.
static void covers_adopt(void) {
    if (cov_lock == LWP_MUTEX_NULL) return;
    LWP_MutexLock(cov_lock);
    for (int d = 0; d < cov_ndone; d++) {
        int gi = cov_done[d].gi;
        if (!cov_done[d].pix) { if (no_cover && gi < ngames) no_cover[gi] = 1; continue; }
        cover_t *slot = &covers[0];
        for (int i = 0; i < COVER_CACHE; i++) if (!covers[i].tex || covers[i].used < slot->used) slot = &covers[i];
        if (slot->tex) gfx_tex_free(slot->tex);
        slot->tex = gfx_tex_from_argb(cov_done[d].pix, cov_done[d].w, cov_done[d].h, cov_done[d].w * 4);
        free(cov_done[d].pix);
        slot->game = gi; slot->w = cov_done[d].w; slot->h = cov_done[d].h; slot->used = now_ms(); slot->born = clock_s;
    }
    cov_ndone = 0;
    LWP_MutexUnlock(cov_lock);
}

static void request_cover(int gi) {
    if (gi < 0 || gi >= ngames || (no_cover && no_cover[gi]) || cov_lock == LWP_MUTEX_NULL) return;
    for (int i = 0; i < COVER_CACHE; i++) if (covers[i].tex && covers[i].game == gi) return;
    LWP_MutexLock(cov_lock);
    int queued = gi == cov_working;
    for (int i = 0; i < cov_ndone && !queued; i++) queued = cov_done[i].gi == gi;
    for (int i = 0; i < cov_nreq; i++) if (cov_req[i] == gi) {   // already asked: move it to the front
        for (int j = i; j < cov_nreq - 1; j++) cov_req[j] = cov_req[j + 1];
        cov_nreq--;
        break;
    }
    if (!queued) {
        if (cov_nreq == COVER_REQ) { memmove(cov_req, cov_req + 1, (COVER_REQ - 1) * sizeof *cov_req); cov_nreq--; }
        cov_req[cov_nreq++] = gi;            // the newest is taken first
    }
    LWP_MutexUnlock(cov_lock);
}

// The texture if it's loaded (also its age, for the fade-in); otherwise asks for it and returns NULL.
static gfx_tex *load_cover_aged(int gi, int *w, int *h, float *age) {
    for (int i = 0; i < COVER_CACHE; i++) {
        if (covers[i].tex && covers[i].game == gi) {
            covers[i].used = now_ms();
            *w = covers[i].w; *h = covers[i].h;
            if (age) *age = clock_s - covers[i].born;
            return covers[i].tex;
        }
    }
    request_cover(gi);
    return NULL;
}


static int video_game = -1;
static float video_t0, settled_since;
static int settled_on = -1;
static unsigned char *no_video;

// The clip for game gi once it has been selected for a moment; NULL if it has none (yet).
static gfx_tex *game_video(int gi) {
    if (gi < 0 || gi >= ngames) return NULL;
    if (gi != settled_on) { settled_on = gi; settled_since = clock_s; }
    if (gi != video_game) {
        if (clock_s - settled_since < 0.35f || (no_video && no_video[gi])) return NULL;
        char path[96];
        snprintf(path, sizeof path, "sd:/arcade/video/%s.gvid", games[gi].vkey);
        if (!games[gi].vkey[0] || video_open(path) != 0) {
            if (no_video) no_video[gi] = 1;
            video_game = -1;
            return NULL;
        }
        crumb("video: opened");
        video_game = gi;
        video_t0 = clock_s;
    }
    return video_frame(clock_s - video_t0);
}

// Game picture fitted into the local box x, y, w, h of frame f, on black. play: the clip, when the game has one.
// duo: the blue duotone of the neighbours (covers carry their luminance in alpha, see decode_cover).
static void draw_pic(int gi, const frame_t *f, float x, float y, float w, float h, Uint8 alpha, int play, int duo) {
    fr_rect(f, x, y, w, h, ((duo ? C_BLU : C_INK) & 0xFFFFFF00) | alpha);
    gfx_tex *v = play ? game_video(gi) : NULL;
    float va = v ? fminf(1.0f, (clock_s - video_t0) / VIDEO_FADE_SECS) : 0;
    int tw, th;
    float age = 1;
    gfx_tex *t = !v || va < 1 ? load_cover_aged(gi, &tw, &th, &age) : NULL;   // the still under a clip fading in
    if (t) {
        float s = fminf(w / tw, h / th), dw = tw * s, dh = th * s, q[8];
        fr_quad(f, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, q);
        Uint8 a = (Uint8)(alpha * fminf(1, v ? 1 : age / 0.25f));
        if (duo) gfx_tex_quad_duo(t, q, C_BLU, C_DUO_LIGHT, a);
        else gfx_tex_quad_opaque(t, q, a);
    } else if (!v && no_cover && no_cover[gi]) {   // no picture at all: a title card (else: still loading, stay calm)
        TTF_Font *tf = w > 200 ? f_top : f_btn;
        fr_text(f, f_badge, sys_short(games[gi].system), (duo ? C_DUO_LIGHT : C_YEL) & (0xFFFFFF00 | alpha), x + w / 2, y + 10, 1);
        fr_text(f, tf, fit_line(tf, games[gi].title, (int)w - 20), (C_WHITE & 0xFFFFFF00) | alpha, x + w / 2, y + h / 2 - font_h(tf) / 2, 1);
    }
    if (v) {
        float q[8];
        fr_quad(f, x, y, w, h, q);
        gfx_tex_quad(v, q, 0xFFFFFF00 | (u32)(alpha * va));
    }
}

// ---------------------------------------------------------------- chrome

static gfx_tex *bg_tex, *band_tex;

static gfx_tex *load_png(const char *path) {
    SDL_Surface *img = IMG_Load(path);
    if (!img) { agent_log("ui: no %s", path); return NULL; }
    gfx_tex *t = surface_tex(img);
    SDL_FreeSurface(img);
    return t;
}

static void draw_bg(void) {                  // the collage paper (or plain pink on a card without it yet)
    if (bg_tex) gfx_tex_draw(bg_tex, 0, 0, W, H, 255);
    else gfx_rect(0, 0, W, H, C_PAPER);
}

// A square key cap (letter on yellow, A on pink) and its label in white; returns the total width. x = left edge.
#define KEY 28
static int key_w(const char *label) { return KEY + 8 + text_w(f_btn, label); }
static int key_button(int x, int y, char letter, const char *label) {
    gfx_rect(x, y, KEY, KEY, letter == 'A' ? C_PNK : C_YEL);
    char l[2] = { letter, 0 };
    int fh = font_h(f_btn);
    draw_text(f_btn, l, INK, x + KEY / 2, y + (KEY - fh) / 2 + 1, 1, 0, 255);
    draw_text(f_btn, label, WHITE, x + KEY + 8, y + (KEY - fh) / 2 + 1, 0, 0, 255);
    return key_w(label);
}

static void draw_topbar(const ui_state_t *st) {
    int fh = font_h(f_top);
    draw_text(f_top, "WIIZARD", INK, 24, 30 - fh / 2, 0, 0, 255);
    char clock[16];
    time_t now = time(NULL) + cab.clock_offset;   // the Wii's clock may be UTC: the Mac sends local time (CLOCK)
    struct tm *tm = gmtime(&now);
    int hr = tm ? (tm->tm_hour % 12 ? tm->tm_hour % 12 : 12) : 12;
    snprintf(clock, sizeof clock, "%d:%02d", hr, tm ? tm->tm_min : 0);
    int cw = text_w(f_top, clock);
    draw_text(f_top, clock, INK, W - 24, 30 - fh / 2, 2, 0, 255);
    // network: three bars left of the clock. Solid = connected; filling one by one = connecting; faint = none.
    int bx = W - 24 - cw - 34, base = 38;
    for (int b = 0; b < 3; b++) {
        int h = 8 + 5 * b;
        u32 col;
        if (st->online) col = C_INK;
        else if (st->status && !strncmp(st->status, "connecting", 10))
            col = ((int)(clock_s * 2.5f) % 4) > b ? C_PNK : 0x0A0A0A50;
        else col = 0x0A0A0A50;
        gfx_rect(bx + b * 8, base - h, 5, h, col);
    }
    if (st->busy) {                          // maintenance under way: a small, slow pulsing dot, nothing more
        float a = 0.45f + 0.4f * sinf(clock_s * 2.0f);
        gfx_rrect(bx - 18, base - 13, 10, 10, 5, (C_BLU & 0xFFFFFF00) | (u32)(255 * a));
    }
}

// The category row: slanted tags, the current one filled black (pink while the row has the focus) and centred.
#define PILL_H 30
static void draw_system_pills(int y) {
    if (!nsys) return;
    int widths[MAX_SYS], gap = 8, pad = 22;
    for (int s = 0; s < nsys; s++) widths[s] = text_w(f_btn, sys_short(sys_id[s])) + pad;
    int x = W / 2 - widths[cur_sys] / 2;
    for (int s = cur_sys - 1; s >= 0; s--) x -= widths[s] + gap;
    int fh = font_h(f_btn);
    for (int s = 0; s < nsys; s++) {
        if (x < W + 20 && x + widths[s] > -20) {
            int sel = s == cur_sys, yy = y;
            if (sel && cat_focus) yy -= (int)(3 * fabsf(sinf(clock_s * 5)));   // a little hop: "move me"
            tag(x, yy, widths[s], PILL_H, sel ? (cat_focus ? C_PNK : C_INK) : 0, C_INK);
            draw_text(f_btn, sys_short(sys_id[s]), sel ? (cat_focus ? WHITE : YELLOW) : INK,
                      x + widths[s] / 2 - TAG_SLANT / 2, yy + (PILL_H - fh) / 2 + 1, 1, 0, 255);
        }
        x += widths[s] + gap;
    }
}

// Bottom bar: the section's name in yellow and the position in pink on the left, the buttons on the right.
#define BAR_Y 404
static void draw_bottombar(const char *name, const char *count, int cat) {
    gfx_rect(0, BAR_Y, W, H - BAR_Y, C_INK);
    const char *labels[3];
    char letters[3];
    int n = 0;
    int gi = cur_game();
    letters[n] = 'B'; labels[n++] = "BACK";
    if (!cat) { letters[n] = 'Y'; labels[n++] = gi >= 0 && favs[gi] ? "UNFAVORITE" : "FAVORITE"; }
    letters[n] = 'A'; labels[n++] = cat ? "PICK" : "PLAY";
    int bw = 0;
    for (int i = 0; i < n; i++) bw += key_w(labels[i]) + (i ? 18 : 0);
    int x = W - 24 - bw, by = BAR_Y + (H - BAR_Y - KEY) / 2 - 2;
    for (int i = 0; i < n; i++) x += key_button(x, by, letters[i], labels[i]) + 18;
    int cw = text_w(f_btn, count), room = W - 24 - bw - 24 - 24 - cw - 12;
    TTF_Font *nf = text_w(pf[P_40], name) <= room ? pf[P_40] : text_w(pf[P_34], name) <= room ? pf[P_34] : pf[P_28];
    const char *nm = fit_line(nf, name, room);
    int nh = font_h(nf), ny = BAR_Y + (H - BAR_Y) / 2 - 2 - p_cap_of(nf);
    draw_text(nf, nm, YELLOW, 24, ny, 0, 0, 255);
    int fh = font_h(f_btn);
    draw_text(f_btn, count, PINK, 24 + text_w(nf, nm) + 12, ny + nh - fh - (nh - fh) / 4, 0, 0, 255);
}

// The 2P / high-score boxes on a card (pink, white type), in the card's frame; x, y = the first one's top-left.
static void card_badges(int gi, const frame_t *f, float x, float y, Uint8 alpha) {
    int players = meta ? atoi(meta[gi].players) : 0;
    char t[24];
    int h = 24, fh = font_h(f_badge);
    for (int k = 0; k < 2; k++) {
        if (k == 0 && players >= 2) snprintf(t, sizeof t, "%dP", players);
        else if (k == 1 && hiscore && hiscore[gi]) snprintf(t, sizeof t, "HI %s", hiscore[gi]);
        else continue;
        int w = text_w(f_badge, t) + 16;
        fr_rect(f, x, y, w, h, (C_PNK & 0xFFFFFF00) | alpha);
        fr_text(f, f_badge, t, (C_WHITE & 0xFFFFFF00) | alpha, x + w / 2.0f, y + (h - fh) / 2.0f + 1, 1);
        x += w + 6;
    }
}

// A game on the card row. c = how central it is (1 = selected: the taped photo on its white die-cut, tilted, in
// colour, playing its clip; 0 = a neighbour: smaller, flat, blue duotone). Returns the photo's frame.
#define CARD_W 304                          // 4:3, as big as the title, pills and bar under it allow
#define CARD_H 228
#define CARD_Y 166
static frame_t draw_card(int gi, float cx, float cy, float c, int play, float cw, float ch) {
    float k = 0.72f + 0.28f * c, w = cw * k, h = ch * k, x = cx - w / 2, y = cy - h / 2, ks = w / CARD_W;
    if (c > 0.01f) {                          // die-cut paper (corners as cut in the mockup) and its hard shadow
        u32 a = (u32)(255 * c);
        float q[8] = { x - 14 * ks, y - 10 * ks, x + w + 18 * ks, y - 22 * ks, x + w + 22 * ks, y + h + 6 * ks, x - 8 * ks, y + h + 20 * ks };
        float s[8];
        for (int i = 0; i < 8; i++) s[i] = q[i] + 8 * ks;
        gfx_poly(s, 4, (C_INK & 0xFFFFFF00) | (a * 7 / 8));
        gfx_poly(q, 4, (C_WHITE & 0xFFFFFF00) | a);
    }
    frame_t f = frame_at(cx, cy, 0);         // the picture itself stays level (Mitchell: no tilted clips)
    float smooth = c * c * (3 - 2 * c);
    if (c < 0.999f) draw_pic(gi, &f, -w / 2, -h / 2, w, h, 255, 0, 1);
    if (c > 0.001f) draw_pic(gi, &f, -w / 2, -h / 2, w, h, (Uint8)(255 * smooth), play && c > 0.97f, 0);
    if (c > 0.01f) {                          // tape across the top
        frame_t tf = frame_at(cx, y - 13 * ks, -3);
        fr_rect(&tf, -32 * ks, -9 * ks, 64 * ks, 18 * ks, (C_TAPE & 0xFFFFFF00) | (u32)(200 * c));
    }
    return f;
}

// The favourite heart in the photo's top-right corner (pops in, shrinks out; a burst of hearts on a new favourite).
static void card_heart(int gi, const frame_t *f, float w, float h) {
    float age = gi == fav_anim_game ? clock_s - fav_anim_t0 : 99;
    if (!favs[gi] && age >= 0.35f) return;
    float hx = f->x + (w / 2 - 22) * f->c - (-h / 2 + 20) * f->s, hy = f->y + (w / 2 - 22) * f->s + (-h / 2 + 20) * f->c;
    float sz = 24;
    if (age < 0.5f) {
        if (fav_anim_on) sz = 24 * (age < 0.2f ? 1.7f * age / 0.2f : 1.7f - 0.7f * fminf(1, (age - 0.2f) / 0.3f));
        else sz = 24 * fmaxf(0, 1 - age / 0.35f);
    }
    if (sz > 0.5f) {
        gfx_heart(hx - sz / 2 + 2, hy - sz / 2 + 2, sz, 0x0A0A0AA0);
        gfx_heart(hx - sz / 2, hy - sz / 2, sz, C_WHITE);
    }
    if (fav_anim_on && age < 0.7f) {          // a little burst of hearts
        u32 a = (u32)(255 * (1 - age / 0.7f));
        for (int k = 0; k < 6; k++) {
            float ang = k * 1.0472f + 0.3f, d = 12 + 46 * age / 0.7f, hs = 9 * (1 - age / 0.7f) + 3;
            gfx_heart(hx + cosf(ang) * d - hs / 2, hy + sinf(ang) * d - hs / 2, hs, ((k & 1) ? C_PNK : C_YEL) & (0xFFFFFF00 | a));
        }
    }
}

// ---------------------------------------------------------------- screens

static void card_row(int s, float pos, int play_center) {
    if (sys_count[s]) {                      // pictures for the cards just off screen, before they arrive
        int c = (int)floorf(pos + 0.5f);
        for (int d = 4; d >= 3; d--)
            for (int side = -1; side <= 1; side += 2) {
                int k = c + d * side;
                if (k >= 0 && k < sys_count[s]) request_cover(sys_list[s][k]);
            }
    }
    for (int ring = 2; ring >= 0; ring--) {
        for (int side = -1; side <= 1; side += 2) {
            if (ring == 0 && side == 1) continue;
            int k = (int)floorf(pos + 0.5f) + ring * side;
            if (k < 0 || k >= sys_count[s]) continue;
            float d = k - pos, ad = fabsf(d), c = fmaxf(0, 1 - ad);
            float cx = W / 2 + d * 246;
            int gi = sys_list[s][k];
            frame_t f = draw_card(gi, cx, CARD_Y, c, ad < 0.05f && play_center, CARD_W, CARD_H);
            if (c > 0.5f) {
                float k2 = 0.72f + 0.28f * c, w = CARD_W * k2, h = CARD_H * k2;
                card_badges(gi, &f, -w / 2 + 8, -h / 2 + 8, (Uint8)(255 * fminf(1, (c - 0.5f) * 2)));
                card_heart(gi, &f, w, h);
            }
        }
    }
}

// The selected game's title under its card: yellow Anton with a black stroke and shadow, tilted up, popping a
// little when it changes; one or two lines, then the black year / maker / system strip.
static int title_game = -1;
static float title_t0;
static void draw_game_title(int gi) {
    if (gi < 0) return;
    if (gi != title_game) { title_game = gi; title_t0 = clock_s; }
    float age = clock_s - title_t0, sc = age < 0.16f ? 1.1f - 0.1f * age / 0.16f : 1;
    const char *t = games[gi].title;
    int p = poster_fit(t, 560, P_58, P_34);
    if (poster_w(p, t) <= 560) poster(p, t, W / 2, 300, 1, -3, sc, C_YEL, 255);
    else {                                   // two lines, split at the space nearest the middle
        char a[160], *b = NULL;
        snprintf(a, sizeof a, "%s", t);
        int n = strlen(a), best = -1;
        for (int i = 0; i < n; i++) if (a[i] == ' ' && (best < 0 || abs(i - n / 2) < abs(best - n / 2))) best = i;
        if (best > 0) { a[best] = 0; b = a + best + 1; }
        int p1 = poster_fit(a, 560, P_40, P_28), p2 = b ? poster_fit(b, 560, P_40, P_28) : p1;
        int pp = p1 > p2 ? p1 : p2;          // the same size for both lines
        float gap = P_SIZE[pp] * 0.86f, y1 = 279 - gap / 2 - 4;   // clear of the strip under it
        poster(pp, fit_line(pf_line[pp] ? pf_line[pp] : pf[pp], a, 560), W / 2 - 4, y1, 1, -3, sc, C_YEL, 255);
        if (b) poster(pp, fit_line(pf_line[pp] ? pf_line[pp] : pf[pp], b, 560), W / 2 + 4, y1 + gap, 1, -3, sc, C_YEL, 255);
    }
    char sub[96] = "";
    if (games[gi].year[0]) snprintf(sub, sizeof sub, "%s  /  %s  /  %s", games[gi].year, games[gi].maker, sys_short(games[gi].system));
    else snprintf(sub, sizeof sub, "%s", sys_long(games[gi].system));
    const char *s = fit_line(f_text, sub, 520);
    int sw = text_w(f_text, s) + 28, fh = font_h(f_text);
    gfx_rect(W / 2 - sw / 2, 324, sw, 28, C_INK);
    draw_text(f_text, s, WHITE, W / 2, 324 + (28 - fh) / 2 + 1, 1, 0, 255);
}

static float ease_back_ui(float u) {
    if (u <= 0) return 0;
    if (u >= 1) return 1;
    return 1 + 2.9f * powf(u - 1, 3) + 1.9f * powf(u - 1, 2);
}

// "Resume where you left off": A on a game with a saved state (RetroArch games, resume.c) asks CONTINUE or NEW GAME
// first. CONTINUE is the default, so mashing A continues; B goes back to the list. Attract, autoboot and tests never
// come through here, so they never resume.
static int choose_gi = -1, choose_sel;      // the game being asked about (-1: none); 0 = continue, 1 = new game
static float choose_t0;
static resume_info_t choose_info;

static void draw_resume_choice(void) {
    if (choose_gi < 0) return;
    float in = ease_back_ui((clock_s - choose_t0) / 0.3f);
    frame_t f = frame_at(W / 2, 312 + (1 - in) * 260, -2);
    fr_rect(&f, -250 + 9, -66 + 9, 500, 132, 0x0A0A0AD8);
    fr_rect(&f, -250, -66, 500, 132, C_WHITE);
    fr_rect(&f, 180, -76, 70, 20, C_TAPE);
    const char *opt[2] = { "CONTINUE", "NEW GAME" };
    TTF_Font *of = pf[P_34];
    int fh = font_h(of);
    for (int i = 0; i < 2; i++) {
        float bx = i == 0 ? -226 : 14, by = -50, bw = 212, bh = 52;
        int sel = i == choose_sel;
        if (sel) by -= 3 * fabsf(sinf(clock_s * 5));          // a little hop on the one A picks
        float q[8];
        fr_quad(&f, bx, by, bw, bh, q);
        q[4] -= TAG_SLANT; q[6] -= TAG_SLANT;                   // the slanted tag, as on the pills
        if (sel) gfx_poly(q, 4, C_PNK);
        for (int k = 0; k < 4; k++) stroke(q[2 * k], q[2 * k + 1], q[(2 * k + 2) % 8], q[(2 * k + 3) % 8], 3, C_INK);
        fr_text(&f, of, opt[i], sel ? C_WHITE : C_INK, bx + bw / 2 - TAG_SLANT / 2, by + (bh - fh) / 2 + 1, 1);
    }
    char line[64] = "";
    long ago = choose_info.saved_at ? (long)time(NULL) - choose_info.saved_at : -1;
    if (ago < 0) snprintf(line, sizeof line, "YOUR GAME IS SAVED");
    else if (ago < 90) snprintf(line, sizeof line, "SAVED JUST NOW");
    else if (ago < 3600) snprintf(line, sizeof line, "SAVED %ld MIN AGO", ago / 60);
    else if (ago < 2 * 86400) snprintf(line, sizeof line, "SAVED %ld HOUR%s AGO", ago / 3600, ago < 7200 ? "" : "S");
    else snprintf(line, sizeof line, "SAVED %ld DAYS AGO", ago / 86400);
    fr_text(&f, f_text, line, C_INK, 0, 22, 1);
}

static void draw_games(const ui_state_t *st) {
    int s = cur_sys;
    (void)st;
    card_row(s, carousel, fabsf(carousel - sys_pos[s]) < 0.05f);
    draw_game_title(cur_game());
    if (choose_gi < 0) {                     // (hidden while CONTINUE / NEW GAME is asked)
        draw_system_pills(355);
        const char *hint = cat_focus ? "UP: BACK TO THE GAMES" : "DOWN: CATEGORIES";
        draw_text(f_hint, hint, INK, W / 2, 393 - p_cap_of(f_hint), 1, 0, 170);
    }
    char count[32];
    snprintf(count, sizeof count, "%d / %d", sys_pos[s] + 1, sys_count[s]);
    char name[64];
    upper(sys_long(sys_id[s]), name, sizeof name);
    draw_bottombar(name, count, cat_focus || choose_gi >= 0);
    draw_resume_choice();
}

// After Gameplay Spotlight's showcase: the clip big on the left, the facts and description on the right.
// Attract: deals through the whole library, shuffled, before anything repeats; every 4th pick is a favourite or a
// game that gets played (when there are some). Up to 0.8.3 each pick was a fresh weighted random draw from a seed
// that barely changed between starts, and the launcher restarts after every game: the same few clips kept coming.
static int *deck, deck_n, deck_pos, attract_picks;

static void shuffle_deck(void) {
    free(deck);
    deck = malloc((ngames ? ngames : 1) * sizeof *deck);
    deck_n = deck ? ngames : 0;
    for (int i = 0; i < deck_n; i++) deck[i] = i;
    for (int i = deck_n - 1; i > 0; i--) {
        int j = rand() % (i + 1), t = deck[i];
        deck[i] = deck[j]; deck[j] = t;
    }
    deck_pos = 0;
}

static int pick_popular(void) {
    int best[24], nb = 0;
    for (int i = 0; i < ngames && nb < 24; i++) if (favs[i] || plays[i] >= 2) best[nb++] = i;
    return nb ? best[rand() % nb] : -1;
}

static int pick_random(void) {
    if (ngames < 2) return 0;
    if (++attract_picks % 4 == 0) {
        int g = pick_popular();
        if (g >= 0 && g != shown) return g;
    }
    for (int tries = 0; tries < 2; tries++) {
        if (deck_pos >= deck_n) shuffle_deck();
        while (deck_pos < deck_n) {
            int g = deck[deck_pos++];
            if (g != shown && g < ngames) return g;
        }
    }
    return rand() % ngames;
}

static int attract_audio_game = -1;

// Attract: the clip fills the screen; a slanted pink halftone lower third carries the title (tilted, stroked),
// year / maker / system, the 2P / high-score / genre tags and "PRESS A TO PLAY". Any button opens the menu on that
// game. Games change through black.
static void draw_attract(const ui_state_t *st) {
    (void)st;
    if (shown < 0 && ngames) shown = pick_random();
    gfx_rect(0, 0, W, H, 0x000000FF);
    if (!ngames) {
        draw_bg();
        poster(P_48, "No games on the card", W / 2, 220, 1, -3, 1, C_YEL, 255);
        return;
    }
    float a = 1;
    if (fade > 0) a = fade < 0.5f ? 1 - fade * 2 : (fade - 0.5f) * 2;
    int g = (fade >= 0.5f && next_shown >= 0) ? next_shown : shown;
    Uint8 alpha = (Uint8)(255 * a);
    gfx_tex *v = fade == 0 ? game_video(g) : NULL;   // only gameplay: black until the clip is there
    if (v) {
        float va = fminf(1.0f, (clock_s - video_t0) / VIDEO_FADE_SECS);
        gfx_tex_draw(v, 0, 0, W, H, (Uint8)(alpha * va));
    }
    if (fade == 0 && video_game == g && attract_audio_game != g) {   // sound fades in with the picture
        char path[96];
        snprintf(path, sizeof path, "sd:/arcade/audio/%s.gaud", games[g].vkey);
        audio_play(path, ATTRACT_VOLUME);
        attract_audio_game = g;
    }
    if (fade > 0 && attract_audio_game >= 0) { audio_fade_out(); attract_audio_game = -1; }
    // the lower third drops away with the old game and slides up with the new one
    float u = fade > 0 ? (fade < 0.5f ? fade * 2 : 2 - fade * 2) : 0, slide = u * u * 140;
    if (band_tex) gfx_tex_draw(band_tex, 0, 340 + slide, W, H - 340, 255);
    else { float q[8] = { 0, 372 + slide, W, 350 + slide, W, H, 0, H }; gfx_poly(q, 4, C_PNK); }
    // PRESS A TO PLAY: a black tag on the right, breathing
    const char *press = "PRESS A TO PLAY";
    int pw = text_w(f_top, press) + 32, ph = 38, px = W - 32 - pw, py = 388 + (int)slide;
    tag(px, py, pw, ph, C_INK, 0);
    float glow = 0.75f + 0.25f * sinf(clock_s * 4);
    u32 col = 0xFF000000 | (u32)(228 * glow + 27 * (1 - glow)) << 16 | (u32)(80 * (1 - glow)) << 8 | 0xFF;
    draw_tint(f_top, press, col, px + pw / 2 - TAG_SLANT / 2, py + (ph - font_h(f_top)) / 2 + 1, 1);
    // title: as big as fits left of the tag, else two sizes smaller, else cut
    int room = px - 36 - 24;
    const char *t = games[g].title;
    int p = poster_fit(t, room, P_48, P_28);
    poster(p, fit_line(pf_line[p] ? pf_line[p] : pf[p], t, room), 36, 404 + slide, 0, -4, 1, C_YEL, 255);
    char sub[96] = "";
    if (games[g].year[0]) snprintf(sub, sizeof sub, "%s  /  %s  /  %s", games[g].year, games[g].maker, sys_short(games[g].system));
    else snprintf(sub, sizeof sub, "%s", sys_long(games[g].system));
    draw_text_fit(f_text, sub, WHITE, 36, 440 + (int)slide, 0, 340, 255);
    // tags: players, high score, genre (black, yellow type), right-aligned under PRESS A TO PLAY
    char tg[3][48];
    int nt = 0, players = meta ? atoi(meta[g].players) : 0;
    if (players >= 2) snprintf(tg[nt++], 48, "%dP", players);
    if (hiscore && hiscore[g]) snprintf(tg[nt++], 48, "HI %s", hiscore[g]);
    if (meta && meta[g].genre[0] && nt < 3) snprintf(tg[nt++], 48, "%s", fit_line(f_badge, meta[g].genre, 190));
    int x = W - 32, fh = font_h(f_badge);
    for (int i = nt - 1; i >= 0; i--) {
        int w = text_w(f_badge, tg[i]) + 18;
        if (x - w < 390) break;              // never under the sub-line
        x -= w;
        tag(x, 438 + slide, w, 24, C_INK, 0);
        draw_text(f_badge, tg[i], YELLOW, x + w / 2 - TAG_SLANT / 2, 438 + (int)slide + (24 - fh) / 2 + 1, 1, 0, 255);
        x -= 10;
    }
    if (alpha < 255) gfx_rect(0, 0, W, H, 255 - alpha);   // the change of game: through black
}

// ---------------------------------------------------------------- calibration

static void load_calibration(void) {       // per cabinet (cab.c), so the card can move between cabinets
    const int *v = cab.screen;
    if (cab.has_screen && v[0] >= 60 && v[0] <= 110 && v[1] >= 60 && v[1] <= 110) {
        cal_sx = v[0]; cal_sy = v[1]; cal_x = v[2]; cal_y = v[3];
    }
}

static int clamp_scale(int s) { return s < 60 ? 60 : s > 110 ? 110 : s; }

void ui_set_calibration(int scale_x, int scale_y, int x, int y, int show_marks) {
    cal_sx = clamp_scale(scale_x); cal_sy = clamp_scale(scale_y); cal_x = x; cal_y = y;
    if (show_marks) cal_marks_until = clock_s + 20;
    cab.screen[0] = cal_sx; cab.screen[1] = cal_sy; cab.screen[2] = x; cab.screen[3] = y;
    cab.has_screen = 1;
    cab_save();
}

void ui_get_calibration(int *scale_x, int *scale_y, int *x, int *y) {
    *scale_x = cal_sx; *scale_y = cal_sy; *x = cal_x; *y = cal_y;
}

static void draw_calibration_marks(void) {
    if (clock_s > cal_marks_until) return;
    gfx_rect(0, 0, W, 3, 0xFFFFFFFF);
    gfx_rect(0, H - 3, W, 3, 0xFFFFFFFF);
    gfx_rect(0, 0, 3, H, 0xFFFFFFFF);
    gfx_rect(W - 3, 0, 3, H, 0xFFFFFFFF);
    for (int k = 0; k < 24; k += 2) {
        gfx_rect(0, k, 24 - k, 2, 0xFFFFFFFF);
        gfx_rect(W - 24 + k, k, 24 - k, 2, 0xFFFFFFFF);
        gfx_rect(0, H - 2 - k, 24 - k, 2, 0xFFFFFFFF);
        gfx_rect(W - 24 + k, H - 2 - k, 24 - k, 2, 0xFFFFFFFF);
    }
    char line[64];
    snprintf(line, sizeof line, "SCREEN  %d%% x %d%%   X %+d   Y %+d", cal_sx, cal_sy, cal_x, cal_y);
    tag(W / 2 - 200, H / 2 - 22, 400, 44, C_INK, 0);
    draw_text(f_top, line, YELLOW, W / 2 - TAG_SLANT / 2, H / 2 - font_h(f_top) / 2, 1, 0, 255);
}

// ---------------------------------------------------------------- API

// Fonts open from RAM: each font file is read once and shared by all its sizes. Opened from the card, every size
// kept a file open (16 of them), and with the clip, its sound and the log open too, an outline face failed to open
// now and then (the titles lost their stroke).
static TTF_Font *font_mem(const char *path, int size) {
    static struct { const char *path; void *data; long len; } files[4];
    int i = 0;
    while (i < 4 && files[i].path && strcmp(files[i].path, path)) i++;
    if (i == 4) return NULL;
    if (!files[i].path) {
        files[i].path = path;
        FILE *f = fopen(path, "rb");
        if (f && !fseek(f, 0, SEEK_END) && (files[i].len = ftell(f)) > 0 && !fseek(f, 0, SEEK_SET)
            && (files[i].data = malloc(files[i].len)) && fread(files[i].data, 1, files[i].len, f) != (size_t)files[i].len) {
            free(files[i].data);
            files[i].data = NULL;
        }
        if (f) fclose(f);
    }
    SDL_RWops *rw = files[i].data ? SDL_RWFromConstMem(files[i].data, files[i].len) : NULL;
    return rw ? TTF_OpenFontRW(rw, 1, size) : NULL;
}
static TTF_Font *open_font(const char *path, int size, const char *fallback) {
    TTF_Font *f = font_mem(path, size);
    if (!f && fallback) f = font_mem(fallback, size * 4 / 5);   // the rounded face runs wider than Anton
    if (!f) agent_log("ui: no font %s %d", path, size);
    return f;
}

int ui_init(GXRModeObj *rmode) {
    ticks0 = gettime();
    gfx_init(rmode);
    IMG_Init(IMG_INIT_PNG | IMG_INIT_JPG);
    TTF_Init();
    // Anton (condensed display, OFL) for everything big or labelled; Archivo Black for the small print. Sizes stay
    // at 18 px and up: thin strokes and small type shimmer on a 480i CRT.
    f_top = open_font(FONT_POSTER, 24, FONT_UI);
    f_btn = open_font(FONT_POSTER, 20, FONT_UI);
    f_badge = open_font(FONT_POSTER, 18, FONT_UI);
    f_hint = f_badge;
    f_text = open_font(FONT_TEXT, 18, FONT_UI);
    for (int p = 0; p < P_N; p++) {
        pf[p] = open_font(FONT_POSTER, P_SIZE[p], FONT_DISPLAY);
        pf_line[p] = open_font(FONT_POSTER, P_SIZE[p], FONT_DISPLAY);
        p_out[p] = P_SIZE[p] >= 58 ? 3 : 2;
        if (pf_line[p]) TTF_SetFontOutline(pf_line[p], p_out[p]);
        p_cap[p] = p_cap_of(pf[p]);
    }
    agent_log("ui: fonts %s", f_top && f_btn && f_text && pf[P_58] ? "loaded" : "MISSING");
    bg_tex = load_png(UI_BG);
    band_tex = load_png(UI_BAND);
    load_calibration();
    last_ticks = now_ms();
    srand((u32)time(NULL) ^ (u32)gettime() ^ (u32)(gettime() >> 32));   // the real clock: differs every start
    return 0;
}

static void wiz_close(void);

void ui_set_games(game_t *g, int n) {
    wiz_close();                             // the intro is over: its frame buffer and texture go
    games = g;
    ngames = n;
    free(no_video);
    no_video = n > 0 ? calloc(n, 1) : NULL;
    free(no_cover);
    no_cover = n > 0 ? calloc(n, 1) : NULL;
    for (int i = 0; i < COVER_CACHE; i++) covers[i].game = -1;   // indices change with a new list
    if (cov_lock == LWP_MUTEX_NULL) {
        LWP_MutexInit(&cov_lock, false);
        LWP_CreateThread(&cov_thread, cover_worker, NULL, NULL, 128 * 1024, 40);
    }
    LWP_MutexLock(cov_lock);
    cov_nreq = 0;
    LWP_MutexUnlock(cov_lock);
    video_close();
    video_game = -1;
    shown = next_shown = -1;
    load_stats();
    load_meta();
    load_collections();
    load_hiscores();
    deck_n = deck_pos = 0;                   // reshuffled on the next attract pick
    nsys = 0;
    build_systems();
    sys_carousel = cur_sys;
    carousel = nsys ? sys_pos[cur_sys] : 0;
}

static void enter_games(int s) {
    mode = MODE_GAMES;
    cur_sys = s;
    carousel = sys_pos[s];
    sys_carousel = cur_sys;
}

static void leave_attract(void) {
    audio_fade_out();
    attract_audio_game = -1;
}

int ui_frame(u32 pressed, u32 held, const ui_state_t *st) {
    u32 now = now_ms();
    float dt = (now - last_ticks) / 1000.0f;
    if (dt > 0.1f) dt = 0.1f;
    last_ticks = now;
    clock_s += dt;
    audio_tick();                            // sound fades
    covers_adopt();                          // pictures the worker finished
    int launch = -1;

    u32 dir = held & (IN_LEFT | IN_RIGHT);   // held left/right repeats
    if (dir && dir == repeat_dir) {
        repeat_t += dt;
        if (repeat_t > 0.36f) { pressed |= dir; repeat_t -= 0.11f; }
    } else { repeat_dir = dir; repeat_t = 0; }
    if (input_lock > 0) {                    // kid-proofing: a moment after each screen change, the action buttons
        input_lock -= dt;                    // do nothing (moving around still works)
        if (pressed) idle = 0;               // still counts as someone being there
        pressed &= ~(IN_A | IN_START | IN_X | IN_Y | IN_Z);
    }
    if (pressed) idle = 0; else idle += dt;
    int mode_before = mode, sys_before = cur_sys, pos_before = nsys ? sys_pos[cur_sys] : 0, fav_before = -1;
    if (cur_game() >= 0) fav_before = favs[cur_game()];

    int focus_before = cat_focus;
    if (mode == MODE_ATTRACT) {
        attract_t += dt;
        if (fade > 0) {
            fade += dt / FADE_SECS / 2;
            if (fade >= 1) { shown = next_shown; fade = 0; attract_t = 0; }
        } else if (attract_t > ATTRACT_SECS + 6 && ngames > 1) {
            next_shown = pick_random();
            fade = 0.001f;
            agent_log("attract: %s", games[next_shown].vkey);   // RAM log only (LOG): checks the rotation
        }
        if (pressed && ngames) {             // any button: the menu, on the game that was showing
            leave_attract();
            int gi = (fade >= 0.5f && next_shown >= 0) ? next_shown : (shown >= 0 ? shown : 0);
            enter_games(sys_of(gi));
            cat_focus = 0;
        }
    } else {
        // Browse: the game cards on top, the category row under them. Left/right moves along the focused row;
        // down/up moves between the rows; L/R triggers flip categories from anywhere. A plays (or, on the
        // category row, goes back up to its games); B goes to the category row, then to attract mode.
        int *pos = &sys_pos[cur_sys], n = sys_count[cur_sys];
        int cat_step = (pressed & IN_L) ? -1 : (pressed & IN_R) ? 1 : 0;
        if (choose_gi >= 0) {                // CONTINUE / NEW GAME is up: it takes every button
            cat_step = 0;
            if (pressed & (IN_LEFT | IN_RIGHT | IN_UP | IN_DOWN)) choose_sel ^= 1;
            if (pressed & (IN_A | IN_START)) {
                resume_set_next(choose_sel == 0);
                launch = choose_gi;
                choose_gi = -1;
            } else if (pressed & IN_B) choose_gi = -1;
        } else if (cat_focus) {
            if (pressed & IN_LEFT) cat_step = -1;
            if (pressed & IN_RIGHT) cat_step = 1;
            if (pressed & (IN_UP | IN_A | IN_START)) cat_focus = 0;
            else if (pressed & IN_B) { mode = MODE_ATTRACT; shown = cur_game(); attract_t = 0; fade = 0; }
        } else {
            if (pressed & IN_LEFT && *pos > 0) (*pos)--;
            if (pressed & IN_RIGHT && *pos < n - 1) (*pos)++;
            if (pressed & (IN_DOWN | IN_B)) cat_focus = 1;
            else if (pressed & (IN_A | IN_START)) {
                int gi = cur_game();
                if (gi >= 0 && resume_available(&games[gi], &choose_info)) {   // ask first: continue or new game
                    choose_gi = gi; choose_sel = 0; choose_t0 = clock_s;
                    input_lock = 0.3f;       // the press that opened it doesn't also pick
                } else {
                    resume_set_next(0);
                    launch = gi;
                }
            }
            if (pressed & IN_Y) toggle_favorite(cur_game());
        }
        if (cat_step) {
            int s2 = cur_sys + cat_step;
            if (s2 >= 0 && s2 < nsys) { cur_sys = s2; carousel = sys_pos[s2]; carousel_v = 0; }
        }
        if (idle > IDLE_TO_ATTRACT_SECS) { choose_gi = -1; mode = MODE_ATTRACT; shown = cur_game(); attract_t = 0; fade = 0; cat_focus = 0; }
    }
    if (mode != mode_before) input_lock = INPUT_LOCK_SECS;
    if (pressed && launch < 0) {             // menu sounds, only for what a button did (not idle timeouts)
        int deeper = mode_before == MODE_ATTRACT && mode != MODE_ATTRACT;
        if (mode != mode_before) audio_sfx(deeper ? SFX_SELECT : SFX_BACK, SFX_VOLUME);
        else if (cat_focus != focus_before) audio_sfx(cat_focus ? SFX_BACK : SFX_SELECT, SFX_VOLUME);
        else if (cur_game() >= 0 && fav_before >= 0 && favs[cur_game()] != fav_before) audio_sfx(SFX_SELECT, SFX_VOLUME);
        else if (cur_sys != sys_before || (nsys && sys_pos[cur_sys] != pos_before)) audio_sfx(SFX_MOVE, SFX_VOLUME);
    }
    if (launch >= 0) input_lock = BOOT_LOCK_SECS;
    // Rows glide on a critically damped spring: velocity carries across presses (holding a direction scrolls
    // smoothly instead of stepping), and they settle without overshoot.
    if (nsys) spring(&carousel, &carousel_v, sys_pos[cur_sys], dt);
    spring(&sys_carousel, &sys_carousel_v, cur_sys, dt);

    gfx_begin();
    gfx_set_calibration(cal_sx, cal_sy, cal_x, cal_y);
    if (mode != MODE_ATTRACT) draw_bg();
    if (mode == MODE_ATTRACT) draw_attract(st);
    else draw_games(st);
    if (mode == MODE_ATTRACT) { }                // full-screen clip: nothing on top
    else draw_topbar(st);
    draw_notice();
    draw_calibration_marks();
    gfx_end();
    if (frame_no < 2) crumb("frame shown");
    frame_no++;
    static u32 fps_t0;                       // frame rate, now and then (RAM log): the collage must keep 60
    static int fps_n;
    if (!fps_t0) fps_t0 = now_ms();
    if (++fps_n == 1800) {
        u32 t = now_ms();
        agent_log("ui: %.1f fps (%s)", 1800000.0f / (t - fps_t0 + 1), mode == MODE_ATTRACT ? "attract" : "menu");
        fps_n = 0;
        fps_t0 = t;
    }
    return launch;
}

// sd:/arcade/controls.tsv (from the controls audit): <rom stem or @system><TAB>one line, e.g.
// "ffight\tA ATTACK   B JUMP   X SPECIAL   Z COIN". A game without its own line gets its system's (@genesis...).
#define CONTROLS_FILE "sd:/arcade/controls.tsv"
static int controls_line(const game_t *g, char *out, int outlen) {
    static const char *sysname[] = { [SYS_GAMECUBE] = "@gamecube", [SYS_WII] = "@wii", [SYS_ARCADE] = "@arcade",
                                     [SYS_CPS1] = "@arcade", [SYS_CPS2] = "@arcade", [SYS_NEOGEO] = "@neogeo",
                                     [SYS_GENESIS] = "@genesis", [SYS_SNES] = "@snes", [SYS_NES] = "@nes" };
    char stem[48];
    snprintf(stem, sizeof stem, "%s", g->rom[0] ? g->rom : g->id);
    char *dot = strrchr(stem, '.');
    if (dot) *dot = 0;
    const char *sys = g->system >= 0 && g->system < (int)(sizeof sysname / sizeof *sysname) ? sysname[g->system] : NULL;
    FILE *f = fopen(CONTROLS_FILE, "r");
    char line[256];
    int found = 0;
    out[0] = 0;
    while (f && fgets(line, sizeof line, f)) {
        char *tab = strchr(line, '\t');
        if (line[0] == '#' || !tab) continue;
        *tab++ = 0;
        tab[strcspn(tab, "\r\n")] = 0;
        if (!*tab) continue;
        if (!strcmp(line, stem)) { snprintf(out, outlen, "%s", tab); found = 1; break; }
        if (sys && !strcmp(line, sys)) snprintf(out, outlen, "%s", tab);   // the fallback, unless the game has one
    }
    if (f) fclose(f);
    return found || out[0];
}

static float ease_out(float u) { u = u < 0 ? 0 : u > 1 ? 1 : u; return 1 - (1 - u) * (1 - u) * (1 - u); }
static float ease_back(float u) {            // overshoots a little, then settles (things popping onto the paper)
    if (u <= 0) return 0;
    if (u >= 1) return 1;
    float c = 1.9f;
    return 1 + (c + 1) * powf(u - 1, 3) + c * powf(u - 1, 2);
}

// A game's title as big as fits a box maxw wide: one line, or two at the space nearest the middle. Left-aligned at
// x, centred on y, tilted deg.
static void poster_block(const char *t, float x, float y, int maxw, float deg, float scale) {
    int p = poster_fit(t, maxw, P_58, P_40);
    if (poster_w(p, t) <= maxw) { poster(p, t, x, y, 0, deg, scale, C_YEL, 255); return; }
    char a[160], *b = NULL;
    snprintf(a, sizeof a, "%s", t);
    int n = strlen(a), best = -1;
    for (int i = 0; i < n; i++) if (a[i] == ' ' && (best < 0 || abs(i - n / 2) < abs(best - n / 2))) best = i;
    if (best > 0) { a[best] = 0; b = a + best + 1; }
    int p1 = poster_fit(a, maxw, P_58, P_28), p2 = b ? poster_fit(b, maxw, P_58, P_28) : p1, pp = p1 > p2 ? p1 : p2;
    TTF_Font *m = pf_line[pp] ? pf_line[pp] : pf[pp];
    float gap = P_SIZE[pp] * 1.08f / 2;
    poster(pp, fit_line(m, a, maxw), x, y - (b ? gap : 0), 0, deg, scale, C_YEL, 255);
    if (b) poster(pp, fit_line(m, b, maxw), x + 4, y + gap, 0, deg, scale, C_YEL, 255);
}

// The controls line from controls.tsv ("A = SHOOT   B = BOMB   Z = COIN"): black keys with white letters, labels
// in black; wraps onto a second row when it has to.
static void draw_controls(const char *ctl, int x0, int y, int maxw) {
    char buf[200];
    snprintf(buf, sizeof buf, "%s", ctl);
    int x = x0, fh = font_h(f_btn);
    for (char *chunk = buf; chunk && *chunk;) {
        char *next = strstr(chunk, "   ");
        if (next) { *next = 0; next += 3; while (*next == ' ') next++; }
        char *eq = strstr(chunk, " = "), *label = "";
        if (eq) { *eq = 0; label = eq + 3; }
        if (!eq) {                           // a note ("LIGHT TO HEAVY"): plain text
            int w = text_w(f_btn, chunk);
            if (x + w > x0 + maxw && x > x0) { x = x0; y += KEY + 6; }
            draw_text(f_btn, chunk, INK, x, y + (KEY - fh) / 2 + 1, 0, 0, 255);
            x += w + 26;
            chunk = next;
            continue;
        }
        char keys[64];
        snprintf(keys, sizeof keys, "%.63s", chunk);
        int w = 0;                           // measure: one key cap per word before " = ", then the label
        for (char *k = strtok(keys, " "); k; k = strtok(NULL, " ")) w += (strlen(k) <= 2 ? KEY : text_w(f_btn, k) + 16) + 6;
        w += 4 + text_w(f_btn, label);
        if (x + w > x0 + maxw && x > x0) { x = x0; y += KEY + 6; }
        snprintf(keys, sizeof keys, "%.63s", chunk);
        for (char *k = strtok(keys, " "); k; k = strtok(NULL, " ")) {
            int kw = strlen(k) <= 2 ? KEY : text_w(f_btn, k) + 16;
            gfx_rect(x, y, kw, KEY, C_INK);
            draw_text(f_btn, k, WHITE, x + kw / 2, y + (KEY - fh) / 2 + 1, 1, 0, 255);
            x += kw + 6;
        }
        draw_text(f_btn, label, INK, x + 4, y + (KEY - fh) / 2 + 1, 0, 0, 255);
        x += 4 + text_w(f_btn, label) + 26;
        chunk = next;
    }
}

// While the game loads (held ~3 s, a fresh A press skips): the game on its taped photo, the title, a progress bar,
// the game's controls, and how to get back to the menu. Arcade and GameCube share one exit: L + R + Z + START
// together (RetroArch's L1+R1+Start+Select combo, and Nintendont's R+Z+Start inside it). Wii games: HOME on the
// Wii Remote, then Wii Menu.
void ui_show_loading(const game_t *g) {
    audio_stop();                            // the clip's sound; the coin plays over the card
    audio_sfx(SFX_COIN, SFX_VOLUME + 10);
    video_close();                           // the next program gets the SD card to itself
    video_game = -1;
    int gi = (int)(g - games);
    int wii = g->system == SYS_WII;
    char ctl[200];
    controls_line(g, ctl, sizeof ctl);
    int players = meta && gi >= 0 && gi < ngames ? atoi(meta[gi].players) : 0;
    char foot[48];
    if (players >= 2) snprintf(foot, sizeof foot, "1-%d PLAYERS  /  FREE PLAY", players);
    else snprintf(foot, sizeof foot, "1 PLAYER  /  FREE PLAY");
    int tw, th;
    if (gi >= 0 && gi < ngames && !load_cover_aged(gi, &tw, &th, NULL) && !(no_cover && no_cover[gi])) {
        int w = 0, h = 0;                    // not decoded yet: do it now (the worker competes with the game's
        u32 *pix = decode_cover(gi, &w, &h); // program being read from the card)
        if (pix && cov_lock != LWP_MUTEX_NULL) {
            LWP_MutexLock(cov_lock);
            if (cov_ndone < 6) { cov_done[cov_ndone].gi = gi; cov_done[cov_ndone].pix = pix; cov_done[cov_ndone].w = w; cov_done[cov_ndone].h = h; cov_ndone++; pix = NULL; }
            LWP_MutexUnlock(cov_lock);
        }
        free(pix);
        covers_adopt();
    }
    int a_released = 0;
    for (int frame = 0; frame < 180; frame++) {
        PAD_ScanPads();                      // a fresh press of A skips the wait (the press that launched doesn't)
        WPAD_ScanPads();
        int a_held = 0;
        for (int i = 0; i < 4; i++)
            a_held |= (PAD_ButtonsHeld(i) & PAD_BUTTON_A) || (WPAD_ButtonsHeld(i) & (WPAD_BUTTON_A | WPAD_CLASSIC_BUTTON_A));
        if (!a_held) a_released = 1;
        else if (a_released && frame > 20) break;
        covers_adopt();
        clock_s += 1 / 60.0f;                // ui_frame isn't running: keep the picture's fade-in moving
        float in = ease_out(frame / 16.0f), pop = ease_back(frame / 14.0f);
        gfx_begin();
        gfx_set_calibration(cal_sx, cal_sy, cal_x, cal_y);
        draw_bg();
        draw_card(gi, 466 + (1 - in) * 300, 168, 1, 0, 296, 222);   // the photo slides in from the right
        const char *sys = sys_short(g->system);
        int sw = text_w(f_btn, sys) + 32;
        tag(40, 64, sw, 30, C_PNK, 0);
        draw_text(f_btn, sys, WHITE, 40 + sw / 2 - TAG_SLANT / 2, 64 + (30 - font_h(f_btn)) / 2 + 1, 1, 0, 255);
        if (pop > 0.01f) poster_block(g->title, 34, 178, 290, -4, pop);
        // progress (the hand-over takes about this long) and LOADING with ticking dots
        float p = fminf(1, frame / 170.0f);
        gfx_rect(32, 284, 576, 18, C_INK);
        gfx_rect(35, 287, 570, 12, C_WHITE);
        gfx_rect(35, 287, 570 * (1 - (1 - p) * (1 - p)), 12, C_PNK);
        char ld[16];
        snprintf(ld, sizeof ld, "LOADING%.*s", (frame / 12) % 4, "...");
        draw_text(f_top, ld, INK, 32, 320 - p_cap_of(f_top), 0, 0, 255);
        draw_text(f_btn, foot, INK, 608, 320 - p_cap_of(f_btn), 2, 0, 255);
        if (ctl[0]) draw_controls(ctl, 32, 338, 576);
        // the way back, on the black bar like the menu's: in pink, then the detail kids need (a half-pressed trigger
        // doesn't count: RetroArch 50 %, Nintendont 69 %)
        gfx_rect(0, 404, W, H - 404, C_INK);
        const char *ex = wii ? "EXIT:  HOME, THEN WII MENU" : "EXIT:  L + R + Z + START";
        draw_text(pf[P_28], ex, PINK, 32, 428 - p_cap_of(pf[P_28]), 0, 0, 255);
        draw_text(f_btn, wii ? "ON THE WII REMOTE" : "HOLD L AND R ALL THE WAY, THEN PRESS Z AND START", WHITE, 32,
                  458 - p_cap_of(f_btn), 0, 0, 255);
        if (frame < 8) gfx_rect(0, 0, W, H, (u32)(255 * (1 - frame / 8.0f)) & 0xFF);
        gfx_end();
    }
    for (int i = 0; i < 20; i++) VIDEO_WaitVSync();   // let the coin finish
    audio_shutdown();                        // no sound DMA may run into the next program
}

// ---------------------------------------------------------------- power-on: Mitchell's wizard
// His 2017 wizard, animated by the main session (art/wizard-anim: pop-in, blink, the Wii Remote flicked like a
// wand, a wink, then an idle loop), streamed one frame at a time from sd:/arcade/ui/wizard.wza (see art/make_ui.py):
// zlib-compressed RGB5A3 texels inflated straight into one texture (~6 ms a frame, no picture held in RAM).
static FILE *wz_f;
static u32 *wz_off;
static u8 *wz_buf;
static int wz_n, wz_loop, wz_cur = -1, wz_tried, wz_w, wz_h;
static float wz_fps;
static gfx_tex *wz_tex;
static int splash_count = -1, splash_systems;

static void wiz_close(void) {
    if (wz_f) fclose(wz_f);
    wz_f = NULL;
    free(wz_off); wz_off = NULL;
    free(wz_buf); wz_buf = NULL;
    if (wz_tex) gfx_tex_free(wz_tex);
    wz_tex = NULL;
    wz_cur = -1;
}

static int wiz_open(void) {
    if (wz_tried) return wz_tex != NULL;
    wz_tried = 1;
    wz_f = fopen(UI_WIZARD, "rb");
    u8 h[16];
    if (!wz_f || fread(h, 1, 16, wz_f) != 16 || memcmp(h, "WZA1", 4)) { wiz_close(); return 0; }
    wz_w = h[4] << 8 | h[5]; wz_h = h[6] << 8 | h[7];
    wz_fps = (h[8] << 8 | h[9]) / 100.0f;
    wz_loop = h[10] << 8 | h[11];
    wz_n = h[12] << 24 | h[13] << 16 | h[14] << 8 | h[15];
    if (wz_n <= 0 || wz_n > 2000 || wz_fps <= 0 || wz_loop >= wz_n) { wiz_close(); return 0; }
    wz_off = malloc((wz_n + 1) * 4);       // big-endian on the disc and on the Wii
    if (!wz_off || fread(wz_off, 4, wz_n + 1, wz_f) != (size_t)(wz_n + 1)) { wiz_close(); return 0; }
    u32 most = 0;
    for (int i = 0; i < wz_n; i++) if (wz_off[i + 1] - wz_off[i] > most) most = wz_off[i + 1] - wz_off[i];
    wz_buf = most < 4 * 1024 * 1024 ? malloc(most) : NULL;
    wz_tex = gfx_tex_blank_rgb5a3(wz_w, wz_h);
    if (!wz_buf || !wz_tex) { wiz_close(); return 0; }
    agent_log("ui: wizard %dx%d, %d frames", wz_w, wz_h, wz_n);
    return 1;
}

// The frame for t seconds in (the tail loops from loop_from); call before gfx_begin().
static gfx_tex *wiz_frame(float t) {
    if (t < 0 || !wiz_open()) return NULL;
    int i = (int)(t * wz_fps);
    if (i >= wz_n) i = wz_loop + (i - wz_loop) % (wz_n - wz_loop);
    if (i != wz_cur) {
        u32 sz = wz_off[i + 1] - wz_off[i];
        uLongf out = wz_w * wz_h * 2;
        if (fseek(wz_f, wz_off[i], SEEK_SET) || fread(wz_buf, 1, sz, wz_f) != sz
            || uncompress(wz_tex->data, &out, wz_buf, sz) != Z_OK) return wz_cur >= 0 ? wz_tex : NULL;
        gfx_tex_flush(wz_tex);
        wz_cur = i;
    }
    return wz_tex;
}

void ui_splash_count(int n, const game_t *g) {
    splash_count = n;
    int seen[32] = { 0 };
    splash_systems = 0;
    for (int i = 0; g && i < n; i++)
        if (g[i].system >= 0 && g[i].system < 32 && !seen[g[i].system]) { seen[g[i].system] = 1; splash_systems++; }
}

// One frame of the power-on intro (t seconds in): the collage fades up, a blue starburst pops behind the wizard,
// he pops in and waves his Wii Remote, WIIZARD slams down (the paper shakes), the ARCADE tag slides in and the
// game and system counts tick up.
void ui_splash_frame(float t) {
    gfx_tex *wz = wiz_frame(t - 0.15f);
    gfx_begin();
    float ti = t - 0.73f, shake = ti > 0 && ti < 0.35f ? 7 * (1 - ti / 0.35f) * sinf(ti * 70) : 0;
    gfx_set_calibration(cal_sx, cal_sy, cal_x + (int)shake, cal_y + (int)(shake * 0.6f));
    draw_bg();
    float bs = ease_back((t - 0.1f) / 0.45f);
    if (bs > 0) {
        gfx_star(476, 296, 190 * bs, 0.8f, 18, t * 6, C_INK & 0xFFFFFF40);
        gfx_star(470, 290, 190 * bs, 0.8f, 18, t * 6, C_BLU);
    }
    if (wz) {                                 // his canvas is 360x500 with the feet bottom-centre; the crop sits at 32, 136
        float x = 470 - (180 - 32), y = 468 - (500 - 136);
        gfx_tex_draw_tint(wz, x + 8, y + 8, wz_w, wz_h, 0x0A0A0A90, 0x0A0A0A90);
        gfx_tex_draw(wz, x, y, wz_w, wz_h, 255);
    }
    float ls = t - 0.55f;                     // WIIZARD: drops from big to its place, a small bounce on impact
    if (ls > 0) {
        float w = poster_w(P_86, "WIIZARD"), fit = w > 300 ? 300 / w : 1;
        float sc = ls < 0.18f ? 2.6f - 1.6f * (ls / 0.18f) * (ls / 0.18f) : 1 + 0.07f * sinf((ls - 0.18f) * 28) * expf(-(ls - 0.18f) * 9);
        poster(P_86, "WIIZARD", 30 + w * fit / 2, 190, 1, -4, sc * fit, C_YEL, (u8)(255 * fminf(1, ls / 0.06f)));
        if (ls > 0.18f) {                     // a pink burst where it lands
            float u = ease_back((ls - 0.18f) / 0.3f);
            gfx_star(318, 126, 30 * u, 0.55f, 10, 12, C_PNK);
        }
    }
    float ta = ease_out((t - 1.0f) / 0.3f);
    if (t > 1.0f) {
        int aw = text_w(f_top, "ARCADE") + 36;
        float x = -aw - 20 + (34 + aw + 20) * ta;
        tag(x, 262, aw, 36, C_PNK, 0);
        draw_text(f_top, "ARCADE", WHITE, (int)x + aw / 2 - TAG_SLANT / 2, 262 + (36 - font_h(f_top)) / 2 + 1, 1, 0, 255);
    }
    if (t > 1.35f) {
        char line[48];
        if (splash_count > 0) {
            float p = ease_out((t - 1.35f) / 0.7f);
            if (splash_systems > 1) snprintf(line, sizeof line, "%d GAMES  /  %d SYSTEMS", (int)(p * splash_count + 0.5f), splash_systems);
            else snprintf(line, sizeof line, "%d GAMES", (int)(p * splash_count + 0.5f));
        } else snprintf(line, sizeof line, "OPENING THE SPELLBOOK%.*s", (int)(t * 3) % 4, "...");
        draw_text(f_top, line, INK, 36, 322 - p_cap_of(f_top), 0, 0, 255);
    }
    if (t < 0.25f) gfx_rect(0, 0, W, H, (u32)(255 * (1 - t / 0.25f)) & 0xFF);
    gfx_end();
}

void ui_wait_frame(float t) { ui_term_frame("> RETURNING TO WIIZARD", NULL, t); }

// A waiting screen (back from a game, preparing a GameCube/Wii start): l1 big on the collage (a "> " prefix and
// trailing dots are dropped: they were the old terminal's), a yellow starburst turning behind it, l2 on a black strip
// (NULL: the library being read).
void ui_term_frame(const char *l1, const char *l2_in, float t) {
    char line[64];
    snprintf(line, sizeof line, "%s", l1 && !strncmp(l1, "> ", 2) ? l1 + 2 : l1 ? l1 : "");
    for (int n = strlen(line); n > 0 && line[n - 1] == '.'; n--) line[n - 1] = 0;
    char l2[64];
    if (l2_in) snprintf(l2, sizeof l2, "%s", l2_in[0] == ' ' ? l2_in + strspn(l2_in, " ") : l2_in);
    else if (splash_count > 0) snprintf(l2, sizeof l2, "%d GAMES READY", splash_count);
    else snprintf(l2, sizeof l2, "LOADING THE GAMES%.*s", (int)(t * 3) % 4, "...");
    gfx_begin();
    gfx_set_calibration(cal_sx, cal_sy, cal_x, cal_y);
    draw_bg();
    float in = ease_back(t / 0.35f);
    gfx_star(W / 2, 214, 150 * in, 0.78f, 16, t * 30, C_YEL);
    int p = poster_fit(line, 560, P_58, P_34);
    poster(p, line, W / 2, 214, 1, -3, 0.6f + 0.4f * in, C_YEL, 255);
    const char *s = fit_line(f_text, l2, 520);
    int sw = text_w(f_text, s) + 28;
    gfx_rect(W / 2 - sw / 2, 262, sw, 28, C_INK);
    draw_text(f_text, s, WHITE, W / 2, 262 + (28 - font_h(f_text)) / 2 + 1, 1, 0, 255);
    if (t < 0.2f) gfx_rect(0, 0, W, H, (u32)(255 * (1 - t / 0.2f)) & 0xFF);
    gfx_end();
}

void ui_splash_load(void) {
    audio_sfx_load();
}

float ui_idle_secs(void) { return idle; }
int ui_in_attract(void) { return mode == MODE_ATTRACT; }
const char *ui_mode_name(void) {
    return mode == MODE_ATTRACT ? "attract" : "browsing";
}

// Reset button / Wiimote HOME in the menu: back to attract mode (never out of the launcher).
void ui_go_attract(void) {
    leave_attract();
    choose_gi = -1;
    mode = MODE_ATTRACT;
    fullscreen = 0;
    attract_t = 0; fade = 0;
    shown = cur_game();
    input_lock = INPUT_LOCK_SECS;
}

// Back from a game: the menu, in the section it was started from, on that game (not attract mode).
void ui_resume(int game) {
    if (game < 0 || game >= ngames) return;
    int id = -1, s = -1;
    char key[32] = "";
    FILE *f = fopen(MENU_POS_FILE, "r");
    if (f) { if (fscanf(f, "%d %31s", &id, key) != 2) id = -1; fclose(f); }
    for (int i = 0; i < nsys && s < 0 && id >= 0 && !strcmp(key, games[game].vkey); i++)
        if (sys_id[i] == id)
            for (int k = 0; k < sys_count[i]; k++) if (sys_list[i][k] == game) { sys_pos[i] = k; s = i; break; }
    if (s < 0) s = sys_of(game);
    shown = game;
    enter_games(s);
    cat_focus = 0;
    idle = 0;
    attract_t = 0;
}

void ui_select(int game) {
    if (game < 0 || game >= ngames) return;
    shown = game;
    cur_sys = sys_of(game);                  // also positions that system on the game
    carousel = sys_pos[cur_sys];
    sys_carousel = cur_sys;
    attract_t = 0;
}

void ui_notice(const char *headline, const char *detail) {
    snprintf(notice_head, sizeof notice_head, "%s", headline);
    snprintf(notice_detail, sizeof notice_detail, "%s", detail ? detail : "");
    notice_until = clock_s + 6;
}

// A note over the menu: a tilted white card with a hard shadow and a strip of tape, the headline in yellow display
// type, the detail in black. It drops in and leaves the same way.
static void draw_notice(void) {
    if (clock_s > notice_until) return;
    float age = clock_s - (notice_until - 6), left = notice_until - clock_s;
    float in = ease_back(age / 0.35f) * fminf(1, left / 0.25f);
    frame_t f = frame_at(W / 2, 226 - (1 - in) * 340, -2);
    fr_rect(&f, -236 + 9, -60 + 9, 472, 120, 0x0A0A0AD8);
    fr_rect(&f, -236, -60, 472, 120, C_WHITE);
    fr_rect(&f, -250, -70, 70, 20, C_TAPE);
    float hx = f.x - (-18) * f.s, hy = f.y + (-18) * f.c;   // local (0, -18) on screen
    int p = poster_fit(notice_head, 430, P_40, P_28);
    poster(p, notice_head, hx, hy, 1, -2, 1, C_YEL, 255);
    fr_text(&f, f_text, fit_line(f_text, notice_detail, 430), C_INK, 0, 14, 1);
}

void ui_show_message(const char *headline, const char *detail) {
    for (int i = 0; i < 2; i++) {
        gfx_begin();
        gfx_set_calibration(cal_sx, cal_sy, cal_x, cal_y);
        draw_bg();
        int p = poster_fit(headline, 560, P_58, P_34);
        poster(p, headline, W / 2, 200, 1, -3, 1, C_YEL, 255);
        const char *s = fit_line(f_text, detail, 540);
        int sw = text_w(f_text, s) + 28;
        gfx_rect(W / 2 - sw / 2, 246, sw, 28, C_INK);
        draw_text(f_text, s, WHITE, W / 2, 246 + (28 - font_h(f_text)) / 2 + 1, 1, 0, 255);
        gfx_end();
    }
}

void ui_shutdown(void) {
    audio_shutdown();
    GX_DrawDone();
    TTF_Quit();
    IMG_Quit();
}
