#ifndef UPDATE_H
#define UPDATE_H
// Pull-style updates from the update server (update.c). may_continue: 1 while it's fine to fetch (cabinet idle).
int update_run(int (*may_continue)(void), void (*log)(const char *fmt, ...));
const char *update_status(void);
extern int launcher_updated;
#endif
