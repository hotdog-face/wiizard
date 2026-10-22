// Attract-mode sound: a clip's audio track (.gaud, made by videos/audio.py on the Mac) looped on one ASND voice.
// .gaud: "GAU1", u32 sample rate, u32 samples, then signed 16-bit big-endian mono samples (padded to 32 bytes).
#include <gccore.h>
#include <asndlib.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>
#include "audio.h"

#define VOICE 0
static int started;
static int vol_now, vol_target, fading_out;   // clip sound fades (audio_tick)
static void *buf;
static int buf_size;

static void start(void) {
    if (!started) {
        ASND_Init();
        ASND_Pause(0);
        started = 1;
    }
}

// .gaud file -> 32-byte aligned buffer (size rounded up to 32); 0 on failure.
static void *load_gaud(const char *path, u32 *rate_out, int *size_out) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    u8 head[12];
    if (fread(head, 1, 12, f) != 12 || memcmp(head, "GAU1", 4)) { fclose(f); return NULL; }
    u32 rate = (head[4] << 24) | (head[5] << 16) | (head[6] << 8) | head[7];
    u32 samples = (head[8] << 24) | (head[9] << 16) | (head[10] << 8) | head[11];
    if (!rate || rate > 48000 || !samples || samples > 48000 * 5) { fclose(f); return NULL; }
    int size = (samples * 2 + 31) & ~31;
    void *b = memalign(32, size);
    if (b) {
        memset(b, 0, size);
        if (fread(b, 1, samples * 2, f) < 16) { free(b); b = NULL; }
        else DCFlushRange(b, size);
    }
    fclose(f);
    *rate_out = rate; *size_out = size;
    return b;
}

// Menu sounds (sd:/arcade/sfx/*.gaud, made by videos/sfx.py): short, in RAM, on voices 1-15 (0 is the clip's).
static const char *SFX_FILES[SFX_COUNT] = { "move", "select", "back", "coin" };
static void *sfx_buf[SFX_COUNT];
static u32 sfx_rate[SFX_COUNT];
static int sfx_size[SFX_COUNT];

void audio_sfx_load(void) {
    char path[64];
    for (int i = 0; i < SFX_COUNT; i++) {
        snprintf(path, sizeof path, "sd:/arcade/sfx/%s.gaud", SFX_FILES[i]);
        sfx_buf[i] = load_gaud(path, &sfx_rate[i], &sfx_size[i]);
    }
}

void audio_sfx(int id, int volume) {
    if (id < 0 || id >= SFX_COUNT || !sfx_buf[id]) return;
    start();
    for (int v = 1; v < 16; v++) {
        if (ASND_StatusVoice(v) != SND_UNUSED) continue;
        ASND_SetVoice(v, VOICE_MONO_16BIT, sfx_rate[id], 0, sfx_buf[id], sfx_size[id], volume, volume, NULL);
        return;
    }
}

int audio_play(const char *path, int volume) {
    audio_stop();
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    u8 head[12];
    if (fread(head, 1, 12, f) != 12 || memcmp(head, "GAU1", 4)) { fclose(f); return -1; }
    u32 rate = (head[4] << 24) | (head[5] << 16) | (head[6] << 8) | head[7];
    u32 samples = (head[8] << 24) | (head[9] << 16) | (head[10] << 8) | head[11];
    if (!rate || rate > 48000 || !samples || samples > 48000 * 60) { fclose(f); return -1; }
    int size = (samples * 2 + 31) & ~31;
    if (size > buf_size) {
        free(buf);
        buf = memalign(32, size);
        buf_size = buf ? size : 0;
    }
    if (!buf) { fclose(f); return -1; }
    memset(buf, 0, size);
    size_t got = fread(buf, 1, samples * 2, f);
    fclose(f);
    if (got < 64) return -1;
    DCFlushRange(buf, size);
    start();
    ASND_SetInfiniteVoice(VOICE, VOICE_MONO_16BIT, rate, 0, buf, size, 0, 0);
    vol_now = 0; vol_target = volume; fading_out = 0;
    return 0;
}

// Fades: the clip's sound ramps in over ~0.5 s and out over ~0.4 s instead of starting and stopping dead.

void audio_tick(void) {
    if (!started || vol_now == vol_target) return;
    int step = fading_out ? 10 : 4;
    vol_now += vol_now < vol_target ? (vol_target - vol_now < step ? vol_target - vol_now : step)
                                    : -(vol_now - vol_target < step ? vol_now - vol_target : step);
    ASND_ChangeVolumeVoice(VOICE, vol_now, vol_now);
    if (fading_out && vol_now == 0) { ASND_StopVoice(VOICE); fading_out = 0; }
}

void audio_fade_out(void) {
    if (!started || ASND_StatusVoice(VOICE) == SND_UNUSED) return;
    vol_target = 0;
    fading_out = 1;
}

void audio_stop(void) {
    if (started) ASND_StopVoice(VOICE);
}

void audio_shutdown(void) {
    if (!started) return;
    ASND_StopVoice(VOICE);
    ASND_Pause(1);
    ASND_End();                              // nothing may keep running into the next program
    started = 0;
}
