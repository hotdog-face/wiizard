#ifndef VIDEO_H
#define VIDEO_H
#include "gfx.h"

// Gameplay clips (.gvid, made by videos/convert.py on the Mac): silent Motion-JPEG, decoded with libjpeg-turbo
// one frame per call into a reused GX texture.
int video_open(const char *path);            // 0 on success; closes any clip that was open
// The frame for time t (seconds since the clip started, loops). NULL if no clip is open.
gfx_tex *video_frame(float t);
void video_close(void);
int video_is_open(void);

#endif
