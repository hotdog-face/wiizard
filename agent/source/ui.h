#ifndef UI_H
#define UI_H
#include <gccore.h>
#include "catalog.h"

// Input for one frame, already merged from GameCube pads, Wiimotes and the Mac's virtual presses.
enum {
    IN_UP = 1, IN_DOWN = 2, IN_LEFT = 4, IN_RIGHT = 8, IN_A = 16, IN_B = 32, IN_START = 64, IN_HOME = 128,
    IN_X = 256, IN_Y = 512, IN_Z = 1024, IN_L = 2048, IN_R = 4096,
};

typedef struct {
    int busy;                                // the Mac is working on this Wii: show Claw'd
    int online;                              // Wi-Fi up
    const char *ip;
    const char *status;                      // one short line for the footer
} ui_state_t;

int ui_init(GXRModeObj *mode);               // 0 on success; sets up video (GX) too
void ui_set_games(game_t *games, int count);
// One frame: reads input, animates, draws. Returns a game index to launch, or -1.
int ui_frame(u32 pressed, u32 held, const ui_state_t *st);
void ui_show_loading(const game_t *g);
void ui_show_message(const char *headline, const char *detail);   // full-screen card, shown once (e.g. RETRYING)
void ui_notice(const char *headline, const char *detail);         // banner over the menu for a few seconds
void ui_select(int game);                    // start on this game (e.g. the one just played)
void ui_record_launch(int game);
void ui_remember_spot(int game);             // the menu section it was picked from (for ui_resume)
void ui_resume(int game);                    // back from a game: the menu on that game, in that section             // count a play (Recent, attract weighting)       // draws the "loading" screen once (before the program switch)
void ui_shutdown(void);
void ui_splash_load(void);                  // the menu sounds (before the splash)
void ui_splash_frame(float t);
void ui_wait_frame(float t);
void ui_term_frame(const char *line1, const char *line2, float t);   // terminal screen (line2 NULL: library status)
void ui_splash_count(int n, const game_t *g);   // the library, once read (game and system counts for the intro)
float ui_idle_secs(void);                    // seconds since the last button press
int ui_in_attract(void);
const char *ui_mode_name(void);              // attract / browsing / showcase (for INFO)
void ui_go_attract(void);                    // Reset button / HOME: back to attract mode
// CRT overscan calibration: the picture is drawn at width/height % and shifted by x,y pixels (saved on SD).
void ui_set_calibration(int scale_x, int scale_y, int x, int y, int show_marks);
void ui_get_calibration(int *scale_x, int *scale_y, int *x, int *y);
void agent_log(const char *fmt, ...);        // main.c: one line to the agent log (RAM, flushed to the card now and then)

#endif
