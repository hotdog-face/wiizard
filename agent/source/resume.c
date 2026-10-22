#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include "resume.h"

#define RESUME_DIR "sd:/arcade/resume"

static int next_resume;

// the record's "key value" line for key, into out
static int field(const char *text, const char *key, char *out, int size) {
    size_t kl = strlen(key);
    for (const char *p = text; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
        if (strncmp(p, key, kl) || p[kl] != ' ') continue;
        const char *v = p + kl + 1, *e = strchr(v, '\n');
        int n = e ? (int)(e - v) : (int)strlen(v);
        if (n >= size) n = size - 1;
        memcpy(out, v, n);
        out[n] = 0;
        return 1;
    }
    return 0;
}

int resume_available(const game_t *g, resume_info_t *info) {
    if (!g->rom[0]) return 0;                // RetroArch games only
    char path[128], text[1024], state[256], v[32];
    snprintf(path, sizeof path, "%s/%s.txt", RESUME_DIR, g->rom);
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    size_t n = fread(text, 1, sizeof text - 1, f);
    fclose(f);
    text[n] = 0;
    if (strncmp(text, "wzresume 1\n", 11) || !field(text, "state", state, sizeof state) || !field(text, "size", v, sizeof v))
        return 0;
    struct stat st;
    if (stat(state, &st) != 0 || (unsigned long)st.st_size != strtoul(v, NULL, 10)) return 0;
    if (info) {
        // RetroArch's 2019 libogc clock can be far off (2038 in the simulator): 0 = unknown, don't show a date
        long t = field(text, "time", v, sizeof v) ? strtol(v, NULL, 10) : 0;
        info->saved_at = (t > 1577836800L && t < (long)time(NULL) + 86400) ? t : 0;
        info->played_secs = field(text, "played", v, sizeof v) ? atoi(v) : 0;
    }
    return 1;
}

void resume_set_next(int on) { next_resume = on; }

int resume_take_next(void) {
    int r = next_resume;
    next_resume = 0;
    return r;
}
