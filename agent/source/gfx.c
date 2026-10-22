// GX 2D renderer: the usual libogc/GRRLIB setup (orthographic 640x480, one TEV stage, alpha blending) with
// explicit cache flushes and texture-cache invalidation, which SDL's Wii renderer got wrong for us (speckles,
// stray triangles).
#include <malloc.h>
#include <string.h>
#include "gfx.h"

#define FIFO_SIZE (256 * 1024)

static GXRModeObj *rmode;
static void *xfb[2];
static int back;                             // index of the framebuffer being drawn
static volatile void *front;

void gfx_init(GXRModeObj *mode) {
    rmode = mode;
    for (int i = 0; i < 2; i++) {
        xfb[i] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
        VIDEO_ClearFrameBuffer(rmode, xfb[i], COLOR_BLACK);
    }
    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb[0]);
    front = xfb[0];
    VIDEO_SetBlack(FALSE);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
    back = 1;

    void *fifo = memalign(32, FIFO_SIZE);
    memset(fifo, 0, FIFO_SIZE);
    GX_Init(fifo, FIFO_SIZE);
    GX_SetCopyClear((GXColor){ 0, 0, 0, 0xFF }, GX_MAX_Z24);
    GX_SetViewport(0, 0, rmode->fbWidth, rmode->efbHeight, 0, 1);
    f32 yscale = GX_GetYScaleFactor(rmode->efbHeight, rmode->xfbHeight);
    u32 xfb_height = GX_SetDispCopyYScale(yscale);
    GX_SetScissor(0, 0, rmode->fbWidth, rmode->efbHeight);
    GX_SetDispCopySrc(0, 0, rmode->fbWidth, rmode->efbHeight);
    GX_SetDispCopyDst(rmode->fbWidth, xfb_height);
    // A light vertical filter: the default interlace "deflicker" (7,7,12,12,12,7,7) blurred the menu on the CRTs;
    // this keeps a little smoothing against 1-line flicker but stays sharp.
    static u8 sharp[7] = { 0, 0, 21, 22, 21, 0, 0 };
    GX_SetCopyFilter(rmode->aa, rmode->sample_pattern, GX_TRUE, (rmode->viTVMode & 3) == VI_INTERLACE ? sharp : rmode->vfilter);
    GX_SetFieldMode(rmode->field_rendering, (rmode->viHeight == 2 * rmode->xfbHeight) ? GX_ENABLE : GX_DISABLE);
    GX_SetPixelFmt(rmode->aa ? GX_PF_RGB565_Z16 : GX_PF_RGB8_Z24, GX_ZC_LINEAR);
    GX_SetDispCopyGamma(GX_GM_1_0);
    GX_SetCullMode(GX_CULL_NONE);

    GX_ClearVtxDesc();
    GX_SetVtxDesc(GX_VA_POS, GX_DIRECT);
    GX_SetVtxDesc(GX_VA_CLR0, GX_DIRECT);
    GX_SetVtxDesc(GX_VA_TEX0, GX_DIRECT);
    GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_POS, GX_POS_XY, GX_F32, 0);
    GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_CLR0, GX_CLR_RGBA, GX_RGBA8, 0);
    GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_TEX0, GX_TEX_ST, GX_F32, 0);
    GX_SetNumChans(1);
    GX_SetNumTexGens(1);
    GX_SetTexCoordGen(GX_TEXCOORD0, GX_TG_MTX2x4, GX_TG_TEX0, GX_IDENTITY);
    GX_SetNumTevStages(1);
    GX_SetZMode(GX_FALSE, GX_LEQUAL, GX_FALSE);
    GX_SetBlendMode(GX_BM_BLEND, GX_BL_SRCALPHA, GX_BL_INVSRCALPHA, GX_LO_CLEAR);
    GX_SetAlphaUpdate(GX_TRUE);
    GX_SetColorUpdate(GX_TRUE);

    Mtx44 ortho;
    guOrtho(ortho, 0, 480, 0, 640, 0, 1000);
    GX_LoadProjectionMtx(ortho, GX_ORTHOGRAPHIC);
    gfx_set_calibration(100, 100, 0, 0);
}

// Everything is drawn in 640x480 coordinates, scaled about the screen centre and shifted (CRT overscan).
void gfx_set_calibration(int scale_x_percent, int scale_y_percent, int x, int y) {
    Mtx mv;
    guMtxIdentity(mv);
    guMtxTransApply(mv, mv, -320, -240, 0);
    guMtxScaleApply(mv, mv, scale_x_percent / 100.0f, scale_y_percent / 100.0f, 1);
    guMtxTransApply(mv, mv, 320 + x, 240 + y, -100);
    GX_LoadPosMtxImm(mv, GX_PNMTX0);
}

void gfx_begin(void) {
    GX_InvalidateTexAll();
    GX_SetViewport(0, 0, rmode->fbWidth, rmode->efbHeight, 0, 1);
}

void gfx_end(void) {
    GX_DrawDone();
    GX_SetZMode(GX_FALSE, GX_LEQUAL, GX_FALSE);
    GX_SetColorUpdate(GX_TRUE);
    GX_CopyDisp(xfb[back], GX_TRUE);         // also clears the EFB for the next frame
    GX_DrawDone();
    VIDEO_SetNextFramebuffer(xfb[back]);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    front = xfb[back];
    back ^= 1;
}

void *gfx_front_buffer(void) { return (void *)front; }

static void quad(float x, float y, float w, float h, u32 rgba, float s1, float t1) {
    u8 r = rgba >> 24, g = rgba >> 16, b = rgba >> 8, a = rgba;
    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
    GX_Position2f32(x, y);         GX_Color4u8(r, g, b, a); GX_TexCoord2f32(0, 0);
    GX_Position2f32(x + w, y);     GX_Color4u8(r, g, b, a); GX_TexCoord2f32(s1, 0);
    GX_Position2f32(x + w, y + h); GX_Color4u8(r, g, b, a); GX_TexCoord2f32(s1, t1);
    GX_Position2f32(x, y + h);     GX_Color4u8(r, g, b, a); GX_TexCoord2f32(0, t1);
    GX_End();
}

void gfx_rect(float x, float y, float w, float h, u32 rgba) {
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    quad(x, y, w, h, rgba, 0, 0);
}

#include <math.h>
#define ARC_SEGS 6

static void vert(float x, float y, u8 r, u8 g, u8 b, u8 a) {
    GX_Position2f32(x, y); GX_Color4u8(r, g, b, a); GX_TexCoord2f32(0, 0);
}

void gfx_rrect(float x, float y, float w, float h, float r, u32 rgba) {
    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;
    if (r < 1) { gfx_rect(x, y, w, h, rgba); return; }
    u8 cr = rgba >> 24, cg = rgba >> 16, cb = rgba >> 8, ca = rgba;
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    // corner centres, clockwise from top-left; each arc runs over a quarter turn
    float cx[4] = { x + r, x + w - r, x + w - r, x + r }, cy[4] = { y + r, y + r, y + h - r, y + h - r };
    GX_Begin(GX_TRIANGLEFAN, GX_VTXFMT0, 2 + 4 * (ARC_SEGS + 1));
    vert(x + w / 2, y + h / 2, cr, cg, cb, ca);
    for (int c = 0; c < 4; c++)
        for (int i = 0; i <= ARC_SEGS; i++) {
            float a = (float)M_PI * (1.0f + c * 0.5f + 0.5f * i / ARC_SEGS);
            vert(cx[c] + r * cosf(a), cy[c] + r * sinf(a), cr, cg, cb, ca);
        }
    vert(x, y + r, cr, cg, cb, ca);          // close the fan back at the first arc's start
    GX_End();
}

void gfx_round_corners(float x, float y, float w, float h, float r, u32 rgba) {
    u8 cr = rgba >> 24, cg = rgba >> 16, cb = rgba >> 8, ca = rgba;
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    float px[4] = { x, x + w, x + w, x }, py[4] = { y, y, y + h, y + h };
    float cx[4] = { x + r, x + w - r, x + w - r, x + r }, cy[4] = { y + r, y + r, y + h - r, y + h - r };
    for (int c = 0; c < 4; c++) {
        GX_Begin(GX_TRIANGLEFAN, GX_VTXFMT0, ARC_SEGS + 2);
        vert(px[c], py[c], cr, cg, cb, ca);  // the square corner, fanned to the arc
        for (int i = 0; i <= ARC_SEGS; i++) {
            float a = (float)M_PI * (1.0f + c * 0.5f + 0.5f * i / ARC_SEGS);
            vert(cx[c] + r * cosf(a), cy[c] + r * sinf(a), cr, cg, cb, ca);
        }
        GX_End();
    }
}

void gfx_heart(float x, float y, float size, u32 rgba) {
    u8 cr = rgba >> 24, cg = rgba >> 16, cb = rgba >> 8, ca = rgba;
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    const int n = 40;
    float s = size / 34.0f, cx = x + size / 2, cy = y + size * 0.42f;
    GX_Begin(GX_TRIANGLEFAN, GX_VTXFMT0, n + 2);
    vert(cx, cy, cr, cg, cb, ca);
    for (int i = 0; i <= n; i++) {           // the classic parametric heart
        float t = 2 * (float)M_PI * i / n, st = sinf(t);
        float hx = 16 * st * st * st;
        float hy = 13 * cosf(t) - 5 * cosf(2 * t) - 2 * cosf(3 * t) - cosf(4 * t);
        vert(cx + hx * s, cy - hy * s, cr, cg, cb, ca);
    }
    GX_End();
}

void gfx_tex_draw(gfx_tex *t, float x, float y, float w, float h, u8 alpha) {
    if (!t) return;
    GX_LoadTexObj(&t->obj, GX_TEXMAP0);
    GX_SetTevOp(GX_TEVSTAGE0, GX_MODULATE);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    quad(x, y, w, h, 0xFFFFFF00 | alpha, (float)t->w / t->tw, (float)t->h / t->th);
}

void gfx_tex_draw_part(gfx_tex *t, float x, float y, float w, float h, float s0, float t0, float s1, float t1, u8 alpha) {
    if (!t) return;
    float sx = (float)t->w / t->tw, sy = (float)t->h / t->th;
    GX_LoadTexObj(&t->obj, GX_TEXMAP0);
    GX_SetTevOp(GX_TEVSTAGE0, GX_MODULATE);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
    GX_Position2f32(x, y);         GX_Color4u8(255, 255, 255, alpha); GX_TexCoord2f32(s0 * sx, t0 * sy);
    GX_Position2f32(x + w, y);     GX_Color4u8(255, 255, 255, alpha); GX_TexCoord2f32(s1 * sx, t0 * sy);
    GX_Position2f32(x + w, y + h); GX_Color4u8(255, 255, 255, alpha); GX_TexCoord2f32(s1 * sx, t1 * sy);
    GX_Position2f32(x, y + h);     GX_Color4u8(255, 255, 255, alpha); GX_TexCoord2f32(s0 * sx, t1 * sy);
    GX_End();
}

static gfx_tex *tex_alloc(int w, int h, int bytes_per_px) {
    gfx_tex *t = calloc(1, sizeof *t);
    if (!t) return NULL;
    t->w = w; t->h = h;
    t->tw = (w + 3) & ~3; t->th = (h + 3) & ~3;
    t->data = memalign(32, t->tw * t->th * bytes_per_px);
    if (!t->data) { free(t); return NULL; }
    return t;
}

static void tile_argb(gfx_tex *t, const u32 *pixels, int pitch) {
    u8 *out = t->data;
    int w = t->w, h = t->h;
    for (int by = 0; by < t->th; by += 4) {
        for (int bx = 0; bx < t->tw; bx += 4) {
            u8 *ar = out, *gb = out + 32;    // RGBA8 block: 16 AR pairs, then 16 GB pairs
            for (int py = 0; py < 4; py++) {
                const u32 *row = (const u32 *)((const u8 *)pixels + (by + py) * pitch);
                for (int px = 0; px < 4; px++) {
                    int x = bx + px;
                    u32 p = (x < w && by + py < h) ? row[x] : 0;
                    *ar++ = p >> 24; *ar++ = p >> 16;
                    *gb++ = p >> 8;  *gb++ = p;
                }
            }
            out += 64;
        }
    }
    DCFlushRange(t->data, t->tw * t->th * 4);
}

gfx_tex *gfx_tex_from_argb(const u32 *pixels, int w, int h, int pitch) {
    if (w <= 0 || h <= 0 || w > 1024 || h > 1024) return NULL;
    gfx_tex *t = tex_alloc(w, h, 4);
    if (!t) return NULL;
    tile_argb(t, pixels, pitch);
    GX_InitTexObj(&t->obj, t->data, t->tw, t->th, GX_TF_RGBA8, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjLOD(&t->obj, GX_LINEAR, GX_LINEAR, 0, 0, 0, GX_DISABLE, GX_DISABLE, GX_ANISO_1);
    return t;
}

void gfx_tex_update_argb(gfx_tex *t, const u32 *pixels, int pitch) {
    if (!t) return;
    tile_argb(t, pixels, pitch);             // gfx_begin() invalidates the texture cache every frame
}

gfx_tex *gfx_tex_from_rgb5a3(const void *data, int w, int h) {
    if ((w & 3) || (h & 3)) return NULL;
    gfx_tex *t = tex_alloc(w, h, 2);
    if (!t) return NULL;
    memcpy(t->data, data, w * h * 2);
    DCFlushRange(t->data, w * h * 2);
    GX_InitTexObj(&t->obj, t->data, w, h, GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjLOD(&t->obj, GX_LINEAR, GX_LINEAR, 0, 0, 0, GX_DISABLE, GX_DISABLE, GX_ANISO_1);
    return t;
}

void gfx_tex_free(gfx_tex *t) {
    if (!t) return;
    GX_DrawDone();
    free(t->data);
    free(t);
}

// A texture tinted by a vertical gradient (vertex colours multiply the texels): white text -> coloured text.
void gfx_tex_draw_tint(gfx_tex *t, float x, float y, float w, float h, u32 top, u32 bottom) {
    if (!t) return;
    float s1 = (float)t->w / t->tw, t1 = (float)t->h / t->th;
    GX_LoadTexObj(&t->obj, GX_TEXMAP0);
    GX_SetTevOp(GX_TEVSTAGE0, GX_MODULATE);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
    GX_Position2f32(x, y);         GX_Color4u8(top >> 24, top >> 16, top >> 8, top);             GX_TexCoord2f32(0, 0);
    GX_Position2f32(x + w, y);     GX_Color4u8(top >> 24, top >> 16, top >> 8, top);             GX_TexCoord2f32(s1, 0);
    GX_Position2f32(x + w, y + h); GX_Color4u8(bottom >> 24, bottom >> 16, bottom >> 8, bottom); GX_TexCoord2f32(s1, t1);
    GX_Position2f32(x, y + h);     GX_Color4u8(bottom >> 24, bottom >> 16, bottom >> 8, bottom); GX_TexCoord2f32(0, t1);
    GX_End();
}

// A rectangle shaded from top colour to bottom colour.
void gfx_rect_gradient(float x, float y, float w, float h, u32 top, u32 bottom) {
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
    vert(x, y, top >> 24, top >> 16, top >> 8, top);
    vert(x + w, y, top >> 24, top >> 16, top >> 8, top);
    vert(x + w, y + h, bottom >> 24, bottom >> 16, bottom >> 8, bottom);
    vert(x, y + h, bottom >> 24, bottom >> 16, bottom >> 8, bottom);
    GX_End();
}

// Additive blending (light adds up: glows, particles) on/off; off = normal alpha blending.
void gfx_blend_add(int on) {
    GX_SetBlendMode(GX_BM_BLEND, GX_BL_SRCALPHA, on ? GX_BL_ONE : GX_BL_INVSRCALPHA, GX_LO_CLEAR);
}

void gfx_poly(const float *xy, int n, u32 rgba) {
    if (n < 3) return;
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    GX_Begin(GX_TRIANGLEFAN, GX_VTXFMT0, n);
    for (int i = 0; i < n; i++) vert(xy[2 * i], xy[2 * i + 1], rgba >> 24, rgba >> 16, rgba >> 8, rgba);
    GX_End();
}

void gfx_star(float cx, float cy, float r, float inner, int points, float rot, u32 rgba) {
    if (points < 3 || points > 32) return;
    u8 cr = rgba >> 24, cg = rgba >> 16, cb = rgba >> 8, ca = rgba;
    GX_SetTevOp(GX_TEVSTAGE0, GX_PASSCLR);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORDNULL, GX_TEXMAP_NULL, GX_COLOR0A0);
    GX_Begin(GX_TRIANGLEFAN, GX_VTXFMT0, 2 * points + 2);
    vert(cx, cy, cr, cg, cb, ca);
    for (int i = 0; i <= 2 * points; i++) {
        float rr = (i & 1) ? r * inner : r, a = (rot - 90 + i * 180.0f / points) * (float)M_PI / 180;
        vert(cx + rr * cosf(a), cy + rr * sinf(a), cr, cg, cb, ca);
    }
    GX_End();
}

static void tex_quad_verts(gfx_tex *t, const float *xy, u32 rgba) {
    float s1 = (float)t->w / t->tw, t1 = (float)t->h / t->th;
    const float st[8] = { 0, 0, s1, 0, s1, t1, 0, t1 };
    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
    for (int i = 0; i < 4; i++) {
        GX_Position2f32(xy[2 * i], xy[2 * i + 1]);
        GX_Color4u8(rgba >> 24, rgba >> 16, rgba >> 8, rgba);
        GX_TexCoord2f32(st[2 * i], st[2 * i + 1]);
    }
    GX_End();
}

void gfx_tex_quad(gfx_tex *t, const float *xy, u32 rgba) {
    if (!t) return;
    GX_LoadTexObj(&t->obj, GX_TEXMAP0);
    GX_SetTevOp(GX_TEVSTAGE0, GX_MODULATE);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    tex_quad_verts(t, xy, rgba);
}

void gfx_tex_quad_opaque(gfx_tex *t, const float *xy, u8 alpha) {
    if (!t) return;
    GX_LoadTexObj(&t->obj, GX_TEXMAP0);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    GX_SetTevColorIn(GX_TEVSTAGE0, GX_CC_ZERO, GX_CC_TEXC, GX_CC_RASC, GX_CC_ZERO);   // texture x vertex colour
    GX_SetTevColorOp(GX_TEVSTAGE0, GX_TEV_ADD, GX_TB_ZERO, GX_CS_SCALE_1, GX_TRUE, GX_TEVPREV);
    GX_SetTevAlphaIn(GX_TEVSTAGE0, GX_CA_ZERO, GX_CA_ZERO, GX_CA_ZERO, GX_CA_RASA);   // vertex alpha only
    GX_SetTevAlphaOp(GX_TEVSTAGE0, GX_TEV_ADD, GX_TB_ZERO, GX_CS_SCALE_1, GX_TRUE, GX_TEVPREV);
    tex_quad_verts(t, xy, 0xFFFFFF00 | alpha);
}

void gfx_tex_quad_duo(gfx_tex *t, const float *xy, u32 dark, u32 light, u8 alpha) {
    if (!t) return;
    GX_LoadTexObj(&t->obj, GX_TEXMAP0);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLOR0A0);
    GX_SetTevColor(GX_TEVREG0, (GXColor){ dark >> 24, dark >> 16, dark >> 8, 255 });
    GX_SetTevColor(GX_TEVREG1, (GXColor){ light >> 24, light >> 16, light >> 8, 255 });
    GX_SetTevColorIn(GX_TEVSTAGE0, GX_CC_C0, GX_CC_C1, GX_CC_TEXA, GX_CC_ZERO);      // dark + (light - dark) * texA
    GX_SetTevColorOp(GX_TEVSTAGE0, GX_TEV_ADD, GX_TB_ZERO, GX_CS_SCALE_1, GX_TRUE, GX_TEVPREV);
    GX_SetTevAlphaIn(GX_TEVSTAGE0, GX_CA_ZERO, GX_CA_ZERO, GX_CA_ZERO, GX_CA_RASA);
    GX_SetTevAlphaOp(GX_TEVSTAGE0, GX_TEV_ADD, GX_TB_ZERO, GX_CS_SCALE_1, GX_TRUE, GX_TEVPREV);
    tex_quad_verts(t, xy, 0xFFFFFF00 | alpha);
}

gfx_tex *gfx_tex_blank_rgb5a3(int w, int h) {
    if ((w & 3) || (h & 3) || w <= 0 || h <= 0 || w > 1024 || h > 1024) return NULL;
    gfx_tex *t = tex_alloc(w, h, 2);
    if (!t) return NULL;
    memset(t->data, 0, w * h * 2);
    DCFlushRange(t->data, w * h * 2);
    GX_InitTexObj(&t->obj, t->data, w, h, GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjLOD(&t->obj, GX_LINEAR, GX_LINEAR, 0, 0, 0, GX_DISABLE, GX_DISABLE, GX_ANISO_1);
    return t;
}

void gfx_tex_flush(gfx_tex *t) {
    if (t) DCFlushRange(t->data, t->tw * t->th * 2);   // RGB5A3 (gfx_tex_blank_rgb5a3)
}
