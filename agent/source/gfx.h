#ifndef GFX_H
#define GFX_H
// Minimal 2D renderer on the GX graphics chip (no SDL renderer): 640x480 coordinates, textured and solid quads,
// double-buffered external framebuffers, and a CRT calibration transform applied to everything drawn.
#include <gccore.h>

typedef struct {
    GXTexObj obj;
    void *data;
    int w, h;                                // visible size; the texture itself is padded to multiples of 4
    int tw, th;
} gfx_tex;

void gfx_init(GXRModeObj *mode);
void gfx_set_calibration(int scale_x_percent, int scale_y_percent, int x, int y);
void gfx_begin(void);                        // start a frame (screen cleared to black)
void gfx_end(void);                          // finish: copy to the back framebuffer, show it at the next vsync
void gfx_rect(float x, float y, float w, float h, u32 rgba);
// Rounded rectangle (r = corner radius; r = h/2 gives a pill or a circle).
void gfx_rrect(float x, float y, float w, float h, float r, u32 rgba);
// Paint the four corners outside a radius-r rounding in rgba: rounds off an image drawn at x, y, w, h.
void gfx_round_corners(float x, float y, float w, float h, float r, u32 rgba);
// Solid heart of the given width, top-left at x, y (favourites).
void gfx_heart(float x, float y, float size, u32 rgba);
void gfx_tex_draw(gfx_tex *t, float x, float y, float w, float h, u8 alpha);
// Part of a texture: texture coordinates s0..s1, t0..t1 in 0..1 of its visible area.
void gfx_tex_draw_part(gfx_tex *t, float x, float y, float w, float h, float s0, float t0, float s1, float t1, u8 alpha);
// ARGB8888 pixels (pitch in bytes) -> RGBA8 tiled texture. NULL on failure.
gfx_tex *gfx_tex_from_argb(const u32 *pixels, int w, int h, int pitch);
// Re-tile new pixels into an existing texture of the same size (video frames). Call between frames.
void gfx_tex_update_argb(gfx_tex *t, const u32 *pixels, int pitch);
// GX native RGB5A3 tiled data (e.g. Gameplay Spotlight stills), copied.
gfx_tex *gfx_tex_from_rgb5a3(const void *data, int w, int h);
void gfx_tex_draw_tint(gfx_tex *t, float x, float y, float w, float h, u32 top_rgba, u32 bottom_rgba);
void gfx_rect_gradient(float x, float y, float w, float h, u32 top_rgba, u32 bottom_rgba);
// Convex (or star-shaped about its first vertex) polygon as a triangle fan; xy = x0, y0, x1, y1, ...
void gfx_poly(const float *xy, int n, u32 rgba);
// Starburst: `points` spikes of radius r around cx, cy, inner radius r * inner, rotated by rot degrees.
void gfx_star(float cx, float cy, float r, float inner, int points, float rot, u32 rgba);
// A texture on any quad (corners TL, TR, BR, BL: rotated cards and titles), tinted by rgba (modulate).
void gfx_tex_quad(gfx_tex *t, const float *xy, u32 rgba);
// The same, ignoring the texture's alpha (pictures whose alpha holds something else, see gfx_tex_quad_duo).
void gfx_tex_quad_opaque(gfx_tex *t, const float *xy, u8 alpha);
// Duotone: the texture's ALPHA channel (a luminance) picks a colour from dark (0) to light (255).
void gfx_tex_quad_duo(gfx_tex *t, const float *xy, u32 dark, u32 light, u8 alpha);
// An empty RGB5A3 texture (w, h multiples of 4) to fill with pre-tiled texels (t->data), then gfx_tex_flush.
gfx_tex *gfx_tex_blank_rgb5a3(int w, int h);
void gfx_tex_flush(gfx_tex *t);              // (RGB5A3 textures from gfx_tex_blank_rgb5a3)
void gfx_blend_add(int on);                   // additive blending (glows) on/off
void gfx_tex_free(gfx_tex *t);               // waits for the GPU to finish with it first
void *gfx_front_buffer(void);                // the framebuffer currently on screen (for screenshots)

#endif
