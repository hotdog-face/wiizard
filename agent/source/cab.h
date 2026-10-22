#ifndef CAB_H
#define CAB_H

typedef struct {
    char name[32];
    int screen[4];                           // width %, height %, x, y
    int has_screen;
    int idle_off_minutes;
    long clock_offset;                       // seconds to add to the Wii's clock for local time (CLOCK command)
    char collections[256];                   // comma-separated; empty = all
} cab_t;

extern cab_t cab;
void cab_load(unsigned device_id);           // before ui_init
int cab_save(void);                          // writes sd:/arcade/cabs/<id>.cfg
int cab_wants_collection(const char *name);

#endif
