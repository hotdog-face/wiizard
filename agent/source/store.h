#ifndef STORE_H
#define STORE_H
#include <stdio.h>

int store_write(const char *path, const void *data, int len);   // whole file, power-cut safe; 0 = ok
int store_printf(const char *path, const char *fmt, ...);        // the same from a format (up to 1 KB)
FILE *store_open(const char *path);                              // read; falls back to a swap cut short
int store_append(const char *path, const char *line);            // append one line and flush (rare events)

#endif
