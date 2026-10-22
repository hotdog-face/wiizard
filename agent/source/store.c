// Card writes that survive a power cut (kids pull plugs): every file is written whole to <path>.new, flushed, and
// only then swapped in. If the power goes in the instant between removing the old file and renaming the new one,
// readers fall back to <path>.new. Small files only.
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include "store.h"

int store_write(const char *path, const void *data, int len) {
    char tmp[200];
    snprintf(tmp, sizeof tmp, "%s.new", path);
    FILE *f = fopen(tmp, "wb");
    if (!f) return -1;
    int ok = len == 0 || fwrite(data, 1, len, f) == (size_t)len;
    ok &= fflush(f) == 0;
    fsync(fileno(f));
    ok &= fclose(f) == 0;
    if (!ok) { remove(tmp); return -1; }
    remove(path);
    return rename(tmp, path) == 0 ? 0 : -1;
}

int store_printf(const char *path, const char *fmt, ...) {
    static char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n < 0 || n >= (int)sizeof buf) return -1;
    return store_write(path, buf, n);
}

FILE *store_open(const char *path) {
    FILE *f = fopen(path, "rb");
    if (f) return f;
    char tmp[200];
    snprintf(tmp, sizeof tmp, "%s.new", path);
    return fopen(tmp, "rb");
}

int store_append(const char *path, const char *line) {
    FILE *f = fopen(path, "a");
    if (!f) return -1;
    fputs(line, f);
    fflush(f);
    fsync(fileno(f));
    return fclose(f);
}
