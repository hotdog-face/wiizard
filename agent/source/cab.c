// Per-cabinet settings, kept on every card and picked by the console's id, so any card works in any cabinet:
//   sd:/arcade/cabs/<console id>.cfg, else sd:/arcade/cabs/default.cfg; "key = value" lines:
//     name = cab1
//     screen = 99 89 0 -3        CRT overscan: width %, height %, x, y (the `screen` tool sets it)
//     idle_off_minutes = 45      power off after this long untouched in attract mode (0 = never)
//     collections = Quick Picks, Fighting     only these collections on this cabinet (empty = all)
// Older cards: the screen comes from sd:/arcade/screen.cfg until the cabinet's own file has one.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <sys/stat.h>
#include "cab.h"
#include "store.h"

#define CABS_DIR "sd:/arcade/cabs"
#define LEGACY_SCREEN "sd:/arcade/screen.cfg"

cab_t cab = { .name = "", .screen = { 90, 90, 0, 0 }, .idle_off_minutes = 45 };
static char path[64];

static char *trim(char *s) {
    while (isspace((unsigned char)*s)) s++;
    char *e = s + strlen(s);
    while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
    return s;
}

static int load(const char *file) {
    FILE *f = store_open(file);
    if (!f) return 0;
    char line[300];
    while (fgets(line, sizeof line, f)) {
        char *eq = strchr(line, '=');
        if (line[0] == '#' || !eq) continue;
        *eq = 0;
        char *k = trim(line), *v = trim(eq + 1);
        if (!strcmp(k, "name")) snprintf(cab.name, sizeof cab.name, "%s", v);
        else if (!strcmp(k, "screen")) {
            int s[4];
            if (sscanf(v, "%d %d %d %d", &s[0], &s[1], &s[2], &s[3]) == 4) { memcpy(cab.screen, s, sizeof s); cab.has_screen = 1; }
        } else if (!strcmp(k, "idle_off_minutes")) cab.idle_off_minutes = atoi(v);
        else if (!strcmp(k, "collections")) snprintf(cab.collections, sizeof cab.collections, "%s", v);
        else if (!strcmp(k, "clock_offset")) cab.clock_offset = atol(v);
    }
    fclose(f);
    return 1;
}

void cab_load(unsigned device_id) {
    snprintf(path, sizeof path, "%s/%u.cfg", CABS_DIR, device_id);
    load(CABS_DIR "/default.cfg");
    int default_screen = cab.has_screen;
    cab.has_screen = 0;
    load(path);
    if (!cab.has_screen) {                   // this TV's screen.cfg (older cards) beats the default
        FILE *f = fopen(LEGACY_SCREEN, "r");
        int s[4], n = f ? fscanf(f, "%d %d %d %d", &s[0], &s[1], &s[2], &s[3]) : 0;
        if (f) fclose(f);
        if (n == 3) { s[3] = s[2]; s[2] = s[1]; s[1] = s[0]; }
        if (n >= 3) { memcpy(cab.screen, s, sizeof s); cab.has_screen = 1; }
        else cab.has_screen = default_screen;
    }
    if (!cab.name[0]) snprintf(cab.name, sizeof cab.name, "%u", device_id);
}

int cab_save(void) {
    mkdir(CABS_DIR, 0777);
    return store_printf(path, "name = %s\nscreen = %d %d %d %d\nidle_off_minutes = %d\ncollections = %s\nclock_offset = %ld\n",
                        cab.name, cab.screen[0], cab.screen[1], cab.screen[2], cab.screen[3], cab.idle_off_minutes,
                        cab.collections, cab.clock_offset);
}

int cab_wants_collection(const char *name) {
    if (!cab.collections[0]) return 1;
    char list[256];
    snprintf(list, sizeof list, "%s", cab.collections);
    for (char *t = strtok(list, ","); t; t = strtok(NULL, ","))
        if (!strcasecmp(trim(t), name)) return 1;
    return 0;
}
