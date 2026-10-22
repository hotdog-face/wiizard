#ifndef AUDIO_H
#define AUDIO_H
// Looping clip audio for attract mode (.gaud files) and the menu's sound effects. volume 0..255.
enum { SFX_MOVE, SFX_SELECT, SFX_BACK, SFX_COIN, SFX_COUNT };
int audio_play(const char *path, int volume);
void audio_stop(void);
void audio_fade_out(void);                   // the clip's sound, gently
void audio_tick(void);                       // once per frame: runs the fades
void audio_sfx_load(void);                   // sd:/arcade/sfx/*.gaud into RAM (missing files: silent)
void audio_sfx(int id, int volume);
void audio_shutdown(void);                   // call before handing the Wii to another program
#endif
