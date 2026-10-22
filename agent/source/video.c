// .gvid player: "GVD1", u16 w, u16 h, u16 fps*100, u16 0, u32 frames, u32 offset[frames + 1], JPEG frames.
// Decodes at most one frame per call (the UI calls once per vsync), straight into a texture that is re-tiled in
// place, so a playing clip costs one JPEG decode + one re-tile per new frame and no allocations.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include <turbojpeg.h>
#include "video.h"

static FILE *f;
static u32 *offsets;
static int frames, width, height, current = -1, first;   // first: first frame worth showing (skips blank lead-in)
static float fps;
static u8 *jpeg;
static u32 *pixels;                          // decoded frame, ARGB8888
static gfx_tex *tex;
static tjhandle tj;
static void find_first(void);

void video_close(void) {
    if (f) fclose(f);
    f = NULL;
    free(offsets);
    offsets = NULL;
    frames = 0;
    current = -1;
}

int video_is_open(void) { return f != NULL; }

int video_open(const char *path) {
    video_close();
    f = fopen(path, "rb");
    if (!f) return -1;
    u8 head[16];
    if (fread(head, 1, 16, f) != 16 || memcmp(head, "GVD1", 4)) { video_close(); return -1; }
    width = (head[4] << 8) | head[5];
    height = (head[6] << 8) | head[7];
    fps = ((head[8] << 8) | head[9]) / 100.0f;
    frames = (head[12] << 24) | (head[13] << 16) | (head[14] << 8) | head[15];
    if (frames <= 0 || frames > 20000 || width <= 0 || width > 640 || height <= 0 || height > 480 || fps <= 0) {
        video_close();
        return -1;
    }
    offsets = malloc((frames + 1) * 4);
    if (!offsets || fread(offsets, 4, frames + 1, f) != (size_t)(frames + 1)) { video_close(); return -1; }
    if (!tj) tj = tjInitDecompress();
    if (!jpeg) jpeg = malloc(256 * 1024);
    if (!pixels || !tex || tex->w != width || tex->h != height) {
        free(pixels);
        pixels = memalign(32, width * height * 4);
        if (tex) gfx_tex_free(tex);
        memset(pixels, 0, width * height * 4);
        tex = gfx_tex_from_argb(pixels, width, height, width * 4);
    }
    if (!(tj && jpeg && pixels && tex)) { video_close(); return -1; }
    find_first();
    return 0;
}

static int decode(int n) {
    u32 start = offsets[n], size = offsets[n + 1] - start;
    if (size == 0 || size > 256 * 1024 || fseek(f, start, SEEK_SET) || fread(jpeg, 1, size, f) != size) return -1;
    return tjDecompress2(tj, jpeg, size, (u8 *)pixels, width, width * 4, height, TJPF_ARGB, TJFLAG_FASTDCT);
}

// A frame that is one flat colour (fade-ins, blank boot screens): sample a grid and look at the spread.
static int flat(void) {
    int lo = 255 * 3, hi = 0;
    for (int y = height / 8; y < height; y += height / 8)
        for (int x = width / 8; x < width; x += width / 8) {
            u32 p = pixels[y * width + x];
            int v = ((p >> 16) & 255) + ((p >> 8) & 255) + (p & 255);
            if (v < lo) lo = v;
            if (v > hi) hi = v;
        }
    return hi - lo < 60;
}

// Skip a blank lead-in: probe every half second for the first frame with some picture in it.
static void find_first(void) {
    first = 0;
    int step = fps > 2 ? (int)(fps / 2) : 1;
    for (int n = 0; n < frames && n < 8 * step; n += step) {
        if (decode(n) == 0 && !flat()) { first = n; return; }
    }
}

gfx_tex *video_frame(float t) {
    if (!f) return NULL;
    int want = first + (int)(t * fps) % (frames - first);
    if (want == current) return tex;
    if (decode(want) != 0) return current >= 0 ? tex : NULL;
    gfx_tex_update_argb(tex, pixels, width * 4);
    current = want;
    return tex;
}
