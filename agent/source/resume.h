#ifndef RESUME_H
#define RESUME_H
#include "catalog.h"

// "Resume where you left off" (RetroArch games: arcade and consoles; GameCube/Wii have no save states here).
// Our RetroArch saves a state when a game that was really played exits (quit combo, RESET, POWER, idle quit for
// consoles; never in test runs) and writes sd:/arcade/resume/<rom>.txt next to it (format: wiizard_wii.c). Started
// with --wiizard-resume it loads that state, after checking build, core, size and CRC; anything that doesn't match
// starts a fresh game and the record is removed, so a stale or broken state never traps anyone.

typedef struct {
    long saved_at;        // unix time of the save (the Wii's clock)
    int played_secs;      // length of the session that was saved
} resume_info_t;

// 1 when "Continue" can be offered for g (a record that names an existing state file of the recorded size).
int resume_available(const game_t *g, resume_info_t *info);

// The next launch (launch_game) continues the saved game instead of starting a new one. One shot: cleared by the
// launch. Ignored for test launches (PLAYTEST / TESTQUEUE) and games without a record.
void resume_set_next(int on);
int resume_take_next(void);    // launch_game: the flag, cleared

#endif
