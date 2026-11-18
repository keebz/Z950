#!/usr/bin/env python3
"""make_skin.py - build the Z950 touch-screen skin into ../skins/ (needs Pillow).

    python3 tools/make_skin.py

Look: an Akai S950 front panel. Warm grey panel, black-bezelled green LCD with dot-matrix labels and a pixel grid
under the live values, fluted-skirt knobs with cream caps and a dot ring (red cap for the main control, like the S950
REC LEVEL), a big flat grey CONTROL-style wheel, dark grey sections with cream keys and a power-button style MODE key.
All artwork is drawn here from scratch.

Parameter indices must match enum ParamIndex in src/DeepStretch.cpp:
  0 cyclic 1 length 2 (spare, was Phase) 3 bits 4 rate 5 pitch 6 qual 7 width 8 mode 9 cue 10 jog 11 punchIn 12 punchOut 13 loopLen 14 loopBpm (display only)
  15 loopRun 16-18 spare (were Cut/Res and its storage) 19 speed 20 power 21 speedLive (display only) 22 filter 23 cycStore 24 styleStore (hidden)

Q-Link pages: the host numbers pages by Q-Link group, page n = Q-Links 4n-3..4n, and the qlinkBoundsData rectangle
number n is drawn for page n.  Page 1 = Cyclic Length Qual Width, page 2 = Bit Rate Filter Pitch, page 3 = Jog + Speed, page 4 = Loop dial.
"""
import json
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SKINS = os.path.join(os.path.dirname(HERE), "skins")

W, H = 1280, 628
PANEL = (205, 200, 187)
PANEL_DARK = (74, 74, 78)
INK = (44, 40, 36)
CREAM = (214, 209, 186)                  # button faces and knob caps
CREAM_HI = (240, 236, 212)               # lit button / cap highlight
CREAM_EDGE = (190, 184, 160)             # button border: a tad darker than the face
LCD_BEZEL = (16, 18, 16)
LCD_GREEN = (143, 190, 104)
LCD_INK = (18, 38, 14)

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# ---- layout ------------------------------------------------------------------------------------------------------
LCD_BOX = (8, 8, 1117, 122)              # bezel (the whole panel sits left; the right strip holds POWER, MODE and the badge)
LCD_IN = (18, 16, 1097, 106)             # green window
NCOL = 8
COLW = LCD_IN[2] / NCOL
CX = [int(round(LCD_IN[0] + COLW * (i + 0.5))) for i in range(NCOL)]
SEPS = [int(round(LCD_IN[0] + COLW * i)) for i in range(1, NCOL)]
# (name, parameter index, kind)
COLS = [("cyclic", 0, "knob"), ("length", 1, "red"), ("qual", 6, "knob"), ("width", 7, "knob"), ("bits", 3, "knob"),
        ("rate", 4, "knob"), ("filter", 22, "red"), ("pitch", 5, "key")]
COL_INDEX = {c[0]: i for i, c in enumerate(COLS)}
LCD_NAME = {"bits": "BIT"}
UNITS = {"cyclic": "SAMPLES", "length": "PERCENT", "filter": "CUTOFF", "bits": "BITS", "rate": "HZ", "qual": "PERCENT", "width": "PERCENT"}
KNOB_FS, KNOB_FRAMES, KNOB_CY = 112, 100, 236
SWEEP_MIN, SWEEP_MAX = -157.0, 155.0
KEY_S = (120, 84)                        # small key (Pitch, Punch In, Punch Out)
KEY_L = (150, 104)                       # large key (Cue)
MODE_KEY = (1159, 10, 88, 84)              # POWER key, the original power-button shape (x, y, w, h)
MODE_SMALL = (1163, 102, 80, 40)           # small CYCLIC / INTELL key under it
SEC_A = (576, 398, 549, 222)             # CUE / SCRUB / SPEED section (right)
SEC_B = (8, 398, 549, 222)             # LOOP section (left)
CUE_KEY = (775, 458)                     # centre of the CUE box (key centre on the same line as the wheel and the knob)
JOG_C, JOG_FS, JOG_FRAMES, JOG_TURNS = (1029, 510), 160, 100, 2      # 2 turns of travel over the strip (+-400 frames)
SPEED_C = (674, 510)                     # left of the CUE box; jog wheel, cue key and speed knob share the centre line y = 510
IN_KEY, OUT_KEY, RUN_KEY = (32, 458), (134, 458), (236, 458)      # Pitch-shaped keys
DIAL_C, DIAL_FS, N_DIAL = (434, 508), 112, 8
N_BITS = 4
KEY_P = (88, 108)                        # loop keys: same shape as the MODE key
PITCH_KEY = (CX[COL_INDEX["pitch"]] - KEY_P[0] // 2, KNOB_CY - KEY_P[1] // 2)     # the Pitch key has the whole last column to itself
PITCH_COL = COL_INDEX["pitch"]
RED_BASE, RED_HI = (176, 44, 42), (232, 104, 96)
DIM_INK = (101, 148, 82)                 # muted LCD text
HDR_Y = 12                               # top of the LCD header text inside the window
HDR_INTELL = ("INTELL", 0)               # (text, column) - the first column's header in INTELL mode
HDR_QUAL, HDR_WIDTH = ("QUAL", COL_INDEX["qual"]), ("WIDTH", COL_INDEX["width"])
HDR_PITCH = ("PITCH", PITCH_COL)

# ---- 5x7 dot-matrix font for the baked LCD labels -----------------------------------------------------------------
GLYPHS = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "G": "01110 10001 10000 10111 10001 10001 01111",
    "F": "11111 10000 10000 11110 10000 10000 10000", "H": "10001 10001 10001 11111 10001 10001 10001", "I": "01110 00100 00100 00100 00100 00100 01110",
    "L": "10000 10000 10000 10000 10000 10000 11111", "N": "10001 11001 10101 10011 10001 10001 10001",
    "P": "11110 10001 10001 11110 10000 10000 10000", "Q": "01110 10001 10001 10001 10101 10010 01101",
    "R": "11110 10001 10001 11110 10100 10010 10001", "S": "01111 10000 10000 01110 00001 00001 11110",
    "T": "11111 00100 00100 00100 00100 00100 00100", "U": "10001 10001 10001 10001 10001 10001 01110",
    "W": "10001 10001 10001 10101 10101 11011 10001", "Y": "10001 10001 01010 00100 00100 00100 00100",
}


def dot_text(d, text, cx, y, cell=3, col=LCD_INK):
    """draw text centred at cx with its top at y; each lit dot is a (cell-1) square"""
    wch = 5 * cell + cell                     # one blank column between letters
    x0 = cx - (len(text) * wch - cell) / 2
    for k, ch in enumerate(text):
        rows = GLYPHS[ch].split()
        for r, row in enumerate(rows):
            for c, bit in enumerate(row):
                if bit == "1":
                    x = x0 + k * wch + c * cell
                    d.rectangle([x, y + r * cell, x + cell - 2, y + r * cell + cell - 2], fill=col)


def font(path, size):
    return ImageFont.truetype(path, size)


def rr(d, box, radius, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ---- the KEEBZ950 wordmark, after the MPC2000XL / S950 badge (the same typeface). Measured on a photo of the MPC2000XL logo (H = letter height):
#   * letters are about 1.15 H wide (M and X about 1.3 H) and the gap between ALL letters is the same, about 0.18 H
#   * the digits are solid with a stroke of about 0.165 H, flat ends, outer corners rounded (about 0.13 H), inner corners nearly square
#   * the letters are tubes of about 0.14 H drawn as TWO thin parallel lines: at a junction or a corner the lines are joined, but a free end of
#     a tube is OPEN (no end cap): the stem of an L, the arms of an X, both ends of the C
# Here KEEBZ is the open-ended tube lettering and 950 the solid digits. Drawn from stroke centre lines, supersampled.
WM_H = 5.0
WM_GAP = 0.9                                              # gap between letters (0.18 H)
WM_TS, WM_TH = 0.85, 0.7                                  # solid stroke, tube width (units)
WM_WIDTH = {"K": 6.2, "E": 5.75, "B": 5.75, "Z": 5.75, "9": 5.6, "5": 5.6, "0": 5.6}


def _round_poly(pts, r, n=10):
    """polyline with every interior corner replaced by a quadratic arc that starts/ends r from the corner"""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        v, pr, nx = pts[i], pts[i - 1], pts[i + 1]
        d1 = (pr[0] - v[0], pr[1] - v[1]); d2 = (nx[0] - v[0], nx[1] - v[1])
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        k = min(r, l1 / 2.0, l2 / 2.0)
        a = (v[0] + d1[0] / l1 * k, v[1] + d1[1] / l1 * k)
        b = (v[0] + d2[0] / l2 * k, v[1] + d2[1] / l2 * k)
        for j in range(n + 1):
            t = j / n
            out.append(((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * v[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * v[1] + t * t * b[1]))
    out.append(pts[-1])
    return out


def wm_strokes(ch):
    """centre lines: list of (points, corner radius, width, open ends). 'open ends' lists which ends of a tube are FREE (no cap): 0 = start, 1 = end.
    Everything stays inside the letter box [0, W] x [0, H]."""
    H = WM_H
    W = WM_WIDTH[ch]
    m = H / 2
    if ch in "950":
        t = WM_TS; h = t / 2; rc = 0.10 * H
        if ch == "0":
            return [([(h, h), (W - h, h), (W - h, H - h), (h, H - h), (h, h)], rc, t, ())]
        if ch == "5":
            return [([(W - h, h), (h, h), (h, m), (W - h, m), (W - h, H - h), (h, H - h)], rc, t, ())]
        return [([(h, H - h), (W - h, H - h), (W - h, h), (h, h), (h, m), (W - h, m)], rc, t, ())]
    t = WM_TH; h = t / 2
    if ch == "E":
        return [([(h, 0), (h, H)], 0, t, ()), ([(0, h), (W, h)], 0, t, (1,)), ([(0, m), (W * 0.86, m)], 0, t, (1,)), ([(0, H - h), (W, H - h)], 0, t, (1,))]
    if ch == "K":
        w2 = t * 1.35
        xc = W - 1.15                                                         # where an arm meets the top / bottom edge of the letter
        sx, sy = t * 0.55, 0.1
        ex = sx + (xc - sx) * (m + sy + 0.6) / (m + sy)                       # run the arm 0.6 past the edge: the box clip cuts it flat
        return [([(h, 0), (h, H)], 0, t, (0, 1)),
                ([(sx, m + sy), (ex, -0.6)], 0, w2, (("h", 0.0),)),
                ([(sx, m - sy), (ex, H + 0.6)], 0, w2, (("h", H),))]
    if ch == "Z":
        return [([(0, h), (W, h)], 0, t, (0,)), ([(0, H - h), (W, H - h)], 0, t, (1,)),
                ([(W - 0.55, h), (0.55, H - h)], 0, t * 1.5, ())]
    if ch == "B":
        wb = W - h
        r = 0.16 * H
        return [([(h, 0), (h, H)], 0, t, ()),
                ([(0, h), (wb - r, h), (wb, r + h), (wb, m - 0.12 * H), (wb - 0.12 * H, m), (0, m)], r, t, ()),
                ([(0, m), (wb - 0.12 * H, m), (wb, m + 0.14 * H), (wb, H - r - h), (wb - r, H - h), (0, H - h)], r, t, ())]
    raise KeyError(ch)


def _path(pts, rad):
    return _round_poly(pts, rad) if rad > 0 else list(pts)


def _stroke_union(draw, pts, rad, wd, k, pad, flat_ends):
    """draw one stroke into a mask: a flat-ended quad for a straight bar, discs along a curved one"""
    q = _path(pts, rad)
    if len(q) == 2 and rad == 0:
        (x0, y0), (x1, y1) = q
        dx, dy = x1 - x0, y1 - y0
        l = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / l * wd / 2, dx / l * wd / 2
        draw.polygon([(pad + (x0 + nx) * k, pad + (y0 + ny) * k), (pad + (x1 + nx) * k, pad + (y1 + ny) * k),
                      (pad + (x1 - nx) * k, pad + (y1 - ny) * k), (pad + (x0 - nx) * k, pad + (y0 - ny) * k)], fill=255)
        return
    if flat_ends and not (len(q) > 2 and q[0] == q[-1]):                      # run open ends past the box: the clip makes them flat
        ex = wd * 0.8
        for i0, i1 in ((0, 1), (-1, -2)):
            dx, dy = q[i0][0] - q[i1][0], q[i0][1] - q[i1][1]
            l = math.hypot(dx, dy) or 1.0
            ext = (q[i0][0] + dx / l * ex, q[i0][1] + dy / l * ex)
            q = [ext] + q if i0 == 0 else q + [ext]
    pp = [(pad + x * k, pad + y * k) for x, y in q]
    wpx = wd * k
    for i in range(len(pp) - 1):
        draw.line([pp[i], pp[i + 1]], fill=255, width=max(1, int(round(wpx))))
    for (x, y) in pp:
        draw.ellipse([x - wpx / 2, y - wpx / 2, x + wpx / 2, y + wpx / 2], fill=255)


def wm_letter_masks(ch, u, ss, pad, line_px):
    """(mask, ring): for digits the solid shape (ring None); for letters the union of the tubes and a thin isotropic outline of it with the free
    tube ends opened"""
    W = WM_WIDTH[ch]
    k = u * ss
    w, h = int(W * k) + 2 * pad, int(WM_H * k) + 2 * pad
    solid = ch in "950"
    union = Image.new("L", (w, h), 0)
    ud = ImageDraw.Draw(union)
    strokes = wm_strokes(ch)
    for pts, rad, wd, opens in strokes:
        _stroke_union(ud, pts, rad, wd, k, pad, solid)
    box = Image.new("L", (w, h), 0)
    ImageDraw.Draw(box).rectangle([pad, pad, pad + W * k - 1, pad + WM_H * k - 1], fill=255)
    union = ImageChops.multiply(union, box)
    if solid:
        return union, None
    sig = max(1.0, line_px)
    blur = union.filter(ImageFilter.GaussianBlur(sig))
    ring = blur.point(lambda v: 255 if 127.5 - 51 < v < 127.5 + 51 else 0)       # an isotropic outline about line_px wide
    rd = ImageDraw.Draw(ring)
    for pts, rad, wd, opens in strokes:                                          # open the free ends: wipe the cap
        q = _path(pts, rad)
        for end in opens:
            if isinstance(end, tuple):                                           # a band cut flat by the top / bottom edge of the letter box
                y_edge = end[1]
                (x0, y0), (x1, y1) = q[0], q[-1]
                tt = (y_edge - y0) / (y1 - y0)
                xcen = x0 + (x1 - x0) * tt
                ang = math.hypot(x1 - x0, y1 - y0)
                hx = (wd / 2) / (abs(y1 - y0) / ang)                             # half of the band's horizontal extent at the edge
                along = 2.2 * line_px
                a0 = pad + (xcen - hx) * k + 1.6 * line_px
                a1 = pad + (xcen + hx) * k - 1.6 * line_px
                ye = pad + y_edge * k
                rd.rectangle([a0, ye - along, a1, ye + along], fill=0)
                continue
            e, nb = (q[0], q[1]) if end == 0 else (q[-1], q[-2])
            dx, dy = e[0] - nb[0], e[1] - nb[1]
            l = math.hypot(dx, dy) or 1.0
            dx, dy = dx / l, dy / l
            nx, ny = -dy, dx
            along = 2.2 * line_px
            across = wd * k / 2 + 2.2 * line_px
            c = (pad + e[0] * k, pad + e[1] * k)
            rd.polygon([(c[0] - dx * along + nx * across, c[1] - dy * along + ny * across), (c[0] + dx * along + nx * across, c[1] + dy * along + ny * across),
                        (c[0] + dx * along - nx * across, c[1] + dy * along - ny * across), (c[0] - dx * along - nx * across, c[1] - dy * along - ny * across)], fill=0)
    return union, ring


def wordmark_keebz950(u=8.0, keeb_ink=(104, 100, 92), z_ink=INK, solid_ink=(20, 20, 20), ss=5, line=1.5, word="KEEBZ950"):
    """KEEBZ as open-ended tubes (two thin lines), 950 as solid digits; reads from the bottom up. u = letter-unit size in pixels (H = 5 u)."""
    pad = 10
    k = u * ss
    xs, x = [], pad
    for ch in word:
        xs.append(x)
        x += int((WM_WIDTH[ch] + WM_GAP) * k)
    Wd = x + pad
    Hd = int(WM_H * k) + 2 * pad
    out = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    for ch, x0 in zip(word, xs):
        solid = ch in "950"
        ink = solid_ink if solid else (z_ink if ch == "Z" else keeb_ink)
        union, ring = wm_letter_masks(ch, u, ss, pad, line * ss)
        body = union if solid else ring
        out.paste(Image.new("RGBA", body.size, ink + (255,)), (x0 - pad, 0), body)
    bbox = out.getbbox()
    out = out.crop(bbox).resize((max(1, (bbox[2] - bbox[0]) // ss), max(1, (bbox[3] - bbox[1]) // ss)), Image.LANCZOS)
    return out.rotate(90, expand=True)


def ctext(d, text, cx, y, f, fill):
    d.text((cx - d.textlength(text, font=f) / 2, y), text, font=f, fill=fill)


# ---- artwork ----------------------------------------------------------------------------------------------------------
def lcd_mask():
    """pixel grid; baked into the background UNDER the live LCD text"""
    w, h = LCD_IN[2], LCD_IN[3]
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    for y in range(h):
        for x in range(w):
            if x % 4 == 3 or y % 4 == 3:
                px[x, y] = (30, 70, 22, 70)
    return im


def clean_lcd():
    """the LCD window without any text: vignette, pixel grid and column dividers"""
    lcd = Image.new("RGB", (LCD_IN[2], LCD_IN[3]), LCD_GREEN)
    ld = ImageDraw.Draw(lcd)
    for i in range(10):                                                     # vignette
        a = 22 - 2 * i
        ld.rectangle([i, i, LCD_IN[2] - 1 - i, LCD_IN[3] - 1 - i], outline=(143 - a, 190 - a, 104 - a))
    for x in SEPS:
        ld.line([x - LCD_IN[0], 10, x - LCD_IN[0], LCD_IN[3] - 10], fill=(90, 130, 66), width=2)
    lcd = lcd.convert("RGBA")
    lcd.alpha_composite(lcd_mask())
    return lcd


def patch_geom(col):
    """absolute x, y, w, h of the header patch of one LCD column"""
    px0 = int(round(COLW * col)) + 12
    return LCD_IN[0] + px0, LCD_IN[1] + 8, int(round(COLW)) - 24, 30


def header_patch(text, col, ink):
    """a patch that replaces the baked header of one LCD column; returns (image, absolute x, absolute y)"""
    lcd = clean_lcd()
    px0 = int(round(COLW * col)) + 12
    pw = int(round(COLW)) - 24
    py0, ph = 8, 30
    patch = lcd.crop((px0, py0, px0 + pw, py0 + ph))
    d = ImageDraw.Draw(patch)
    dot_text(d, text, CX[col] - LCD_IN[0] - px0, HDR_Y - py0, col=ink)
    return patch, LCD_IN[0] + px0, LCD_IN[1] + py0


def unit_caption_geom(col):
    return CX[col] - 50, 326, 100, 18


def unit_caption(text):
    """a word printed under a knob in place of the baked unit (a panel-coloured patch that covers it)"""
    im = Image.new("RGBA", (100, 18), PANEL + (255,))
    ctext(ImageDraw.Draw(im), text, 50, 4, font(FONT_B, 10), (96, 90, 82))
    return im


def bezel_key(face, on, label=None, size=None):
    """black bezel, inset face (the original power-button shape)"""
    w, h = size or (MODE_KEY[2], MODE_KEY[3])
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rr(d, [0, 0, w - 1, h - 1], 6, fill=(22, 22, 24, 255))
    inset = 10 if not on else 12
    rr(d, [inset, inset, w - 1 - inset, h - 1 - inset - (0 if not on else 2)], 3, fill=face + (255,))
    hi = tuple(min(255, c + 30) for c in face)
    d.line([inset + 2, inset + 2, w - 3 - inset, inset + 2], fill=hi + (255,), width=2)
    if label:
        ctext(d, label, w / 2, h / 2 - 8, font(FONT_B, 13), (178, 36, 30))
    return im


def make_bg():
    im = Image.new("RGB", (W, H), PANEL)
    d = ImageDraw.Draw(im)
    rr(d, [LCD_BOX[0], LCD_BOX[1], LCD_BOX[0] + LCD_BOX[2], LCD_BOX[1] + LCD_BOX[3]], 10, fill=LCD_BEZEL)
    lcd = clean_lcd()
    ld = ImageDraw.Draw(lcd)
    for i, (name, _, _) in enumerate(COLS):
        dot_text(ld, LCD_NAME.get(name, name.upper()), CX[i] - LCD_IN[0], HDR_Y)
    im.paste(lcd.convert("RGB"), (LCD_IN[0], LCD_IN[1]))
    for x in SEPS:                                                          # panel dividers under the LCD
        d.line([x, 150, x, 342], fill=(120, 116, 106), width=2)
        d.line([x + 2, 150, x + 2, 342], fill=(236, 232, 220), width=1)
    f_u, f_m = font(FONT_B, 10), font(FONT_B, 9)
    for ci, (name, p, kind) in enumerate(COLS):                             # unit under the value, MIN/MAX beside each knob
        cx = CX[ci]
        if name in UNITS:
            ctext(d, UNITS[name], cx, 330, f_u, (96, 90, 82))
        if kind in ("knob", "red"):
            d.text((cx - 54, KNOB_CY + 36), "MIN", font=f_m, fill=INK)
            d.text((cx + 54 - d.textlength("MAX", font=f_m), KNOB_CY + 36), "MAX", font=f_m, fill=INK)
    wm = wordmark_keebz950(u=7.4, z_ink=INK)                                  # KEEBZ950 badge, reads from the bottom up
    im.paste(wm, (1203 - wm.width // 2, 160), wm)
    f_t = font(FONT_B, 16)                                                  # dark sections like the S950 keypad block
    for box, title in ((SEC_A, ""), (SEC_B, "LOOP")):
        rr(d, [box[0], box[1], box[0] + box[2], box[1] + box[3]], 8, fill=PANEL_DARK)
        if title:
            d.text((box[0] + 16, box[1] + 10), title, font=f_t, fill=(236, 234, 226))
    f_s, f_x = font(FONT_B, 13), font(FONT_B, 11)
    light = (236, 234, 226)
    ctext(d, "<<  SCRUB  >>", JOG_C[0], SEC_A[1] + 12, f_t, light)
    ctext(d, "SPEED", SPEED_C[0], SEC_A[1] + 12, f_t, light)
    ctext(d, "-100", SPEED_C[0] - 50, SPEED_C[1] + 44, f_x, light)
    ctext(d, "+100", SPEED_C[0] + 50, SPEED_C[1] + 44, f_x, light)
    ctext(d, "0", SPEED_C[0], SPEED_C[1] - 70, f_x, light)
    ctext(d, "CUE", CUE_KEY[0] + KEY_L[0] // 2, CUE_KEY[1] + KEY_L[1] + 10, f_s, light)
    ctext(d, "1/8 S STUTTER", CUE_KEY[0] + KEY_L[0] // 2, CUE_KEY[1] + KEY_L[1] + 32, f_x, (190, 188, 180))
    ctext(d, "PUNCH IN", IN_KEY[0] + KEY_P[0] // 2, IN_KEY[1] + KEY_P[1] + 8, f_s, light)
    ctext(d, "PUNCH OUT", OUT_KEY[0] + KEY_P[0] // 2, OUT_KEY[1] + KEY_P[1] + 8, f_s, light)
    ctext(d, "STOP / START", RUN_KEY[0] + KEY_P[0] // 2, RUN_KEY[1] + KEY_P[1] + 8, f_s, light)
    for i, lab in enumerate(["FREE", "1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]):   # printed positions around the loop dial
        a = math.radians(-135 + 270 * i / (N_DIAL - 1))
        cx, cy = DIAL_C[0] + math.sin(a) * 66, DIAL_C[1] - math.cos(a) * 66
        ctext(d, lab, cx, cy - 7, f_x, light)
    return im


def shade_disc(d, c, r, light, dark, steps=18, off=0.0):
    """disc with a soft light-from-top-left gradient: stacked circles shifting towards the light"""
    for i in range(steps):
        k = i / (steps - 1)
        rr_ = r * (1 - 0.22 * k)
        sh = -off * r * k
        v = tuple(int(light[j] * k + dark[j] * (1 - k)) for j in range(3))
        d.ellipse([c + sh - rr_, c + sh - rr_, c + sh + rr_, c + sh + rr_], fill=v + (255,))


def knob_frame(frac, red=False, ss=3, grey=False, pointer=True, dots=11):
    """S950 style: dot ring, fluted silver skirt, cream (or red) cap with a pointer line to the rim"""
    S = KNOB_FS * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S / 2
    R = S * 0.5
    for i in range(dots):                                                            # dot ring printed on the panel
        a = math.radians(SWEEP_MIN + (SWEEP_MAX - SWEEP_MIN) * i / (dots - 1))
        x, y = c + math.sin(a) * R * 0.92, c - math.cos(a) * R * 0.92
        rd = ss * 2.2
        d.ellipse([x - rd, y - rd, x + rd, y + rd], fill=(40, 36, 32, 255))
    r = R * 0.80                                                                      # soft shadow under the knob
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([c - r * 0.96 + ss * 3, c - r * 0.96 + ss * 5, c + r * 1.0 + ss * 3, c + r * 1.0 + ss * 5], fill=(0, 0, 0, 90))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(ss * 3)))
    d = ImageDraw.Draw(im)
    d.ellipse([c - r, c - r, c + r, c + r], fill=(120, 120, 118, 255))               # silver fluted skirt
    shade_disc(d, c, r, (206, 206, 202), (128, 128, 126), 16, 0.10)
    for i in range(60):                                                               # vertical flutes
        a = i * math.pi * 2 / 60
        shade = int(96 + 50 * math.cos(a - math.radians(-45)))                        # lit from the top-left
        d.line([c + math.sin(a) * r * 0.66, c - math.cos(a) * r * 0.66, c + math.sin(a) * r * 0.99, c - math.cos(a) * r * 0.99],
               fill=(shade, shade, shade - 2, 255), width=max(1, int(ss * 1.1)))
    rc = R * 0.60                                                                     # cap
    cx0, cy0 = c - ss * 1.5, c - ss * 2.5                                             # cap sits a little higher (seen from above)
    if grey:
        base, hi = (176, 176, 172), (206, 206, 202)
    elif red:
        base, hi = (176, 44, 42), (232, 104, 96)
    else:
        base, hi = CREAM, CREAM_HI
    shade_disc(d, cx0, rc, hi, base, 14, 0.12)
    d.ellipse([cx0 - rc, cy0 - rc, cx0 + rc, cy0 + rc], outline=(70, 64, 58, 255), width=ss)
    ang = math.radians(SWEEP_MIN + frac * (SWEEP_MAX - SWEEP_MIN))
    x0, y0 = cx0 + math.sin(ang) * rc * 0.10, cy0 - math.cos(ang) * rc * 0.10
    x1, y1 = cx0 + math.sin(ang) * rc * 0.97, cy0 - math.cos(ang) * rc * 0.97
    if pointer:
        d.line([x0, y0, x1, y1], fill=(250, 250, 248, 255) if red else ((120, 120, 118, 255) if grey else (34, 30, 26, 255)), width=int(ss * 3.6))
    out = im.resize((KNOB_FS, KNOB_FS), Image.LANCZOS)
    if grey:                                                                          # washed-out: muted knob
        wash = Image.new("RGBA", out.size, PANEL + (110,))
        out = Image.composite(Image.alpha_composite(out, wash), out, out.split()[3])
    return out


def dial_frame(idx, ss=3):
    S = DIAL_FS * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S / 2
    r = S * 0.34
    d.ellipse([c - r * 1.12, c - r * 1.12, c + r * 1.12, c + r * 1.12], fill=(130, 130, 128, 255))
    shade_disc(d, c, r * 1.12, (206, 206, 202), (128, 128, 126), 14, 0.10)
    for i in range(48):
        a = i * math.pi * 2 / 48
        shade = int(96 + 50 * math.cos(a - math.radians(-45)))
        d.line([c + math.sin(a) * r * 0.86, c - math.cos(a) * r * 0.86, c + math.sin(a) * r * 1.11, c - math.cos(a) * r * 1.11],
               fill=(shade, shade, shade - 2, 255), width=max(1, int(ss * 1.0)))
    cc = c - ss
    shade_disc(d, cc, r, CREAM_HI, CREAM, 12, 0.12)
    d.ellipse([cc - r, cc - r, cc + r, cc + r], outline=(70, 64, 58, 255), width=ss)
    ang = math.radians(-135 + 270 * idx / (N_DIAL - 1))
    d.line([cc + math.sin(ang) * r * 0.10, cc - math.cos(ang) * r * 0.10, cc + math.sin(ang) * r * 0.97, cc - math.cos(ang) * r * 0.97],
           fill=(34, 30, 26, 255), width=int(ss * 3.4))
    return im.resize((DIAL_FS, DIAL_FS), Image.LANCZOS)


def jog_frame(ang_deg, ss=2):
    """the S950 CONTROL knob: a big flat-topped grey cylinder.  Lighting is fixed, only the small position dot turns."""
    S = JOG_FS * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = S / 2
    R = S * 0.49
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([c - R + ss * 2, c - R + ss * 5, c + R + ss * 2, c + R + ss * 5], fill=(0, 0, 0, 110))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(ss * 4)))
    d = ImageDraw.Draw(im)
    d.ellipse([c - R, c - R, c + R, c + R], fill=(70, 72, 78, 255))                  # dark outer wall
    shade_disc(d, c, R * 0.99, (172, 174, 180), (84, 86, 92), 16, 0.06)              # lit side wall
    rt = R * 0.90                                                                     # flat top face
    d.ellipse([c - rt, c - rt, c + rt, c + rt], fill=(104, 106, 112, 255))
    shade_disc(d, c - ss * 1.2, rt * 0.99, (140, 142, 148), (104, 106, 112), 14, 0.05)
    d.ellipse([c - rt, c - rt, c + rt, c + rt], outline=(70, 72, 78, 255), width=max(1, ss))
    a = math.radians(ang_deg)
    px, py = c + math.sin(a) * R * 0.72, c - math.cos(a) * R * 0.72                   # position dot
    rd = R * 0.045
    d.ellipse([px - rd, py - rd, px + rd, py + rd], fill=(60, 62, 68, 255))
    return im.resize((JOG_FS, JOG_FS), Image.LANCZOS)


def cream_key(size, on, led, label=None, red=False, edge=None, fs=15):
    """cream face with a slightly darker cream border (no black box); a small LED bar shows the state.
    red: a red face"""
    w, h = size
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rr(d, [0, 0, w - 1, h - 1], 7, fill=(edge or ((118, 28, 26) if red else CREAM_EDGE)) + (255,))
    top = 4 if not on else 6
    face = (RED_HI if on else RED_BASE) if red else (CREAM_HI if on else CREAM)
    rr(d, [5, top, w - 6, h - 8 - (0 if not on else 2)], 4, fill=face + (255,))
    hi = tuple(min(255, c + 22) for c in face)
    d.line([9, top + 2, w - 10, top + 2], fill=hi + (255,), width=2)
    if label:
        ctext(d, label, w / 2, top + (h - 8 - top) / 2 - fs / 2 - 1 - (6 if led is not None else 0), font(FONT_B, fs), (250, 246, 240) if red else INK)
    if led is not None:
        lc = led if on else tuple(max(0, c - 22) for c in CREAM)
        d.rectangle([w // 2 - 15, h - 8 - (0 if not on else 2), w // 2 + 15, h - 4 - (0 if not on else 2)], fill=lc + (255,))
    return im


def power_key_img(on):
    """POWER: the original power-button shape with a power symbol. The face stays grey; the symbol glows bright red while the plugin
    is on and is a dull dark red when it is bypassed."""
    w, h = MODE_KEY[2], MODE_KEY[3]
    im = bezel_key((138, 138, 136), on, None, size=(w, h))
    cx, cy = w / 2, h / 2 - (1 if on else 0)
    r = 14
    if on:
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.arc([cx - r, cy - r + 2, cx + r, cy + r + 2], start=-60, end=240, fill=(255, 70, 50, 200), width=9)
        gd.line([cx, cy - r - 2, cx, cy + 2], fill=(255, 70, 50, 200), width=9)
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4)))
    d = ImageDraw.Draw(im)
    ink = (255, 52, 38, 255) if on else (112, 52, 48, 255)
    d.arc([cx - r, cy - r + 2, cx + r, cy + r + 2], start=-60, end=240, fill=ink, width=4)
    d.line([cx, cy - r - 2, cx, cy + 2], fill=ink, width=4)
    return im


def mode_small_img(on):
    """CYCLIC / INTELL: cream like Pitch; the outline turns red for INTELL"""
    return cream_key(MODE_SMALL[2:], on, None, "INTELL" if on else "CYCLIC", edge=RED_BASE if on else None, fs=13)


def pitch_key_img(on):
    return cream_key(KEY_P, on, (90, 220, 90), "PITCH")


# ---- JSON builders -----------------------------------------------------------------------------------------------------
def bounds(x, y, w, h, focus="No", show="Show", when="Always"):
    return {"version": 1, "acceptsHWFocus": focus, "showWhenDataModelInvalid": show, "whenVisible": when,
            "boundsType": "Absolute", "bounds": "%g %g %g %g" % (x, y, w, h)}


def bounds2(x, y, w, h, handles, focus="No"):
    """bounds that are only valid (visible) while every handle is valid"""
    return {"version": 2, "acceptsHWFocus": focus, "showWhenDataModelInvalid": "Show", "whenVisible": "Always",
            "boundsType": "Absolute", "bounds": "%g %g %g %g" % (x, y, w, h), "additionalInvalidatingHandles": handles}


def entry(name, typ, data, b, remap=None):
    return {"version": 2, "componentData": {"version": 1, "name": name, "type": typ, "data": data},
            "handle remapping": {"version": 1, "map": [{"key": k, "value": v} for k, v in (remap or {}).items()]},
            "bounds": b}


def textstyle(font_name, style, size, colour, just, case="Original"):
    return {"version": 1, "font": {"version": 1, "name": font_name, "style": style, "height": size}, "colour": colour,
            "justification": just, "case": case}


def label_value(handle, x, y, w, h, size, colour, just, case="Original", style="Medium", fname="Roboto", vis=None):
    return entry("val", "Label", {"version": 1, "textStyle": textstyle(fname, style, size, colour, just, case), "type": "Value",
                                  "handleName": handle}, bounds2(x, y, w, h, vis) if vis else bounds(x, y, w, h))


def label_text(text, x, y, w, h, size, colour, just, style="Medium", fname="Roboto", vis=None):
    return entry("txt", "Label", {"version": 1, "textStyle": textstyle(fname, style, size, colour, just), "type": "Text",
                                  "handleName": "Data", "text": text}, bounds2(x, y, w, h, vis) if vis else bounds(x, y, w, h))


def image_entry(path, x, y, w, h, vis=None):
    return entry("img", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": path},
                 bounds2(x, y, w, h, vis) if vis else bounds(x, y, w, h))


def button_entry(on, off, handle, x, y, w, h):
    return entry("btn", "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": 1, "numButtonsInGroup": 1,
                                   "handleName": handle, "gestureBehaviour": "Instant"}, bounds(x, y, w, h))


def transparent_bg():
    return {"version": 1, "focussed": {"version": 1, "colour": "0", "image": ""},
            "unfocussed": {"version": 1, "colour": "0", "image": ""}}


def component(children, actions=None):
    return {"version": 2, "actions": actions or [], "backgroundData": transparent_bg(), "ignoreMousePresses": False,
            "disableCoarseDataWheel": False, "componentsData": children}


QLINK_ACTION = [{"version": 1, "onAction": "Mouse Down", "handler": "Q-Link", "handleName": "Data", "additionalData": ""},
                {"version": 1, "onAction": "Double Click", "handler": "Show Overlay", "handleName": "Data", "additionalData": "knob overlay"},
                {"version": 1, "onAction": "Enter Pressed", "handler": "Show Overlay", "handleName": "Data", "additionalData": "knob overlay"}]


def knob_component(strip, frames, size):
    return component([entry("knob", "Knob", {"version": 3, "knobType": "FilmStrip", "filmStrip": strip, "numFrames": frames,
                                             "invert": False, "dragOrientation": "Vertical", "handleName": "Data"},
                            bounds(0, 0, size, size))], QLINK_ACTION)


def tab_root(children):
    return {"version": 2, "actions": [],
            "backgroundData": {"version": 1, "focussed": {"version": 1, "colour": "ffcdc8bb", "image": ""},
                               "unfocussed": {"version": 1, "colour": "ffcdc8bb", "image": ""}},
            "ignoreMousePresses": False, "disableCoarseDataWheel": False, "componentsData": children}


def build_tui():
    c = [image_entry("bg.png", 0, 0, W, H)]
    labels = []                                                                  # every text label is added last so nothing paints over it
    CYC_ON = ["IndexedEnabling/0/2/Parameter 8"]          # visible only while the mode is CYCLIC
    INT_ON = ["IndexedEnabling/1/2/Parameter 8"]          # visible only while the mode is INTELL
    INK_V, INK_C = "ff12240d", "ff2c2824"
    DIM_V, DIM_C = "ff659452", "ff9d998d"
    # state overlays on the LCD: the first column reads INTELL in INTELL mode; Qual / Width headers are dim in CYCLIC mode
    c.append(image_entry("ov_intell_hdr.png", *patch_geom(HDR_INTELL[1]), INT_ON))
    c.append(image_entry("ov_dim_qual.png", *patch_geom(HDR_QUAL[1]), CYC_ON))
    c.append(image_entry("ov_dim_width.png", *patch_geom(HDR_WIDTH[1]), CYC_ON))
    c.append(image_entry("ov_dim_pitch.png", *patch_geom(HDR_PITCH[1]), ["IndexedEnabling/0/2/Parameter 5"]))   # PITCH header dim while off
    c.append(image_entry("ov_style_caption.png", *unit_caption_geom(0), INT_ON))
    for i, (name, p, kind) in enumerate(COLS):
        cx = CX[i]
        h = "Parameter %d" % p
        case = "Upper Case" if name == "pitch" else "Original"
        by, bh, bs = (46, 34, 30.0) if name == "pitch" else (50, 56, 36.0)          
        big = lambda ink, vis=None: label_value(h, cx - 66, by, 132, bh, bs, ink, "horizontallyCentred verticallyCentred",
                                                case=case, style="Bold", fname="Roboto", vis=vis)
        cap = lambda ink, vis=None: label_value(h, cx - 60, 304, 120, 22, 16.0, ink, "horizontallyCentred verticallyCentred", vis=vis)
        kb = lambda comp, vis: entry(name, comp, {"version": 1, "handleName": "Data"},
                                     bounds2(cx - KNOB_FS // 2, KNOB_CY - KNOB_FS // 2, KNOB_FS, KNOB_FS, vis, focus="Yes"), {"Data": h})
        if kind == "key":
            c.append(button_entry("pitch_on.png", "pitch_off.png", h, PITCH_KEY[0], PITCH_KEY[1], *KEY_P))
        elif name == "cyclic":                                  # CYCLIC only: in INTELL mode the knob is greyed and the number is gone
            c.append(kb("creamKnob", CYC_ON))                     # the same parameter is the INTELL style: a two-position knob
            c.append(kb("styleKnob", INT_ON))
            labels.append(big(INK_V, CYC_ON)); labels.append(cap(INK_C, CYC_ON))
            labels.append(big(INK_V, INT_ON)); labels.append(cap(INK_C, INT_ON))
        elif name in ("qual", "width"):                         # INTELL only: static greyed knob and "--" in CYCLIC mode
            c.append(kb("creamKnob", INT_ON))
            c.append(image_entry("knob_idle.png", cx - KNOB_FS // 2, KNOB_CY - KNOB_FS // 2, KNOB_FS, KNOB_FS, CYC_ON))
            labels.append(big(INK_V, INT_ON)); labels.append(cap(INK_C, INT_ON))
            labels.append(label_text("--", cx - 66, 50, 132, 56, 36.0, DIM_V, "horizontallyCentred verticallyCentred",
                                     style="Bold", fname="Roboto", vis=CYC_ON))
        else:
            comp = "redKnob" if kind == "red" else ("bitKnob" if name == "bits" else "creamKnob")
            c.append(entry(name, comp, {"version": 1, "handleName": "Data"},
                           bounds(cx - KNOB_FS // 2, KNOB_CY - KNOB_FS // 2, KNOB_FS, KNOB_FS, focus="Yes"), {"Data": h}))
            labels.append(big(INK_V)); labels.append(cap(INK_C))
    # POWER key (bypass) with the small CYCLIC / INTELL key under it
    c.append(button_entry("power_on.png", "power_off.png", "Parameter 20", MODE_KEY[0], MODE_KEY[1], MODE_KEY[2], MODE_KEY[3]))
    c.append(button_entry("modes_on.png", "modes_off.png", "Parameter 8", MODE_SMALL[0], MODE_SMALL[1], MODE_SMALL[2], MODE_SMALL[3]))
    # CUE / SCRUB
    c.append(button_entry("key_l_on.png", "key_l_off.png", "Parameter 9", CUE_KEY[0], CUE_KEY[1], *KEY_L))
    c.append(entry("jog", "jogKnob", {"version": 1, "handleName": "Data"},
                   bounds(JOG_C[0] - JOG_FS // 2, JOG_C[1] - JOG_FS // 2, JOG_FS, JOG_FS, focus="Yes"), {"Data": "Parameter 10"}))
    # LOOP
    c.append(button_entry("key_p_on.png", "key_p_off.png", "Parameter 11", IN_KEY[0], IN_KEY[1], *KEY_P))
    c.append(button_entry("key_p_on.png", "key_p_off.png", "Parameter 12", OUT_KEY[0], OUT_KEY[1], *KEY_P))
    c.append(button_entry("key_r_on.png", "key_r_off.png", "Parameter 15", RUN_KEY[0], RUN_KEY[1], *KEY_P))
    c.append(entry("dial", "dialKnob", {"version": 1, "handleName": "Data"},
                   bounds(DIAL_C[0] - DIAL_FS // 2, DIAL_C[1] - DIAL_FS // 2, DIAL_FS, DIAL_FS, focus="Yes"), {"Data": "Parameter 13"}))
    SP_ON = ["IndexedEnabling/1/2/Parameter 21"]          # Speed only acts on a running loop or on Cue
    SP_OFF = ["IndexedEnabling/0/2/Parameter 21"]
    c.append(entry("speed", "creamKnob", {"version": 1, "handleName": "Data"},
                   bounds2(SPEED_C[0] - KNOB_FS // 2, SPEED_C[1] - KNOB_FS // 2, KNOB_FS, KNOB_FS, SP_ON, focus="Yes"), {"Data": "Parameter 19"}))
    c.append(image_entry("knob_idle.png", SPEED_C[0] - KNOB_FS // 2, SPEED_C[1] - KNOB_FS // 2, KNOB_FS, KNOB_FS, SP_OFF))
    labels.append(label_value("Parameter 19", SPEED_C[0] - 45, SEC_A[1] + SEC_A[3] - 40, 90, 28, 18.0, "ffece9df", "horizontallyCentred verticallyCentred",
                              style="Bold", vis=SP_ON))
    labels.append(label_text("--", SPEED_C[0] - 45, SEC_A[1] + SEC_A[3] - 40, 90, 28, 18.0, "ff8a8a84", "horizontallyCentred verticallyCentred",
                             style="Bold", vis=SP_OFF))
    labels.append(label_value("Parameter 13", DIAL_C[0] - 40, SEC_B[1] + SEC_B[3] - 34, 80, 28, 16.0, "ffece9df", "horizontallyCentred verticallyCentred",
                              style="Bold"))
    # the tempo of the running loop, above the Punch keys (a Free loop counts as 1/1)
    labels.append(label_value("Parameter 14", IN_KEY[0], IN_KEY[1] - 38, RUN_KEY[0] + KEY_P[0] - IN_KEY[0], 28, 19.0, "ffece9df",
                              "horizontallyCentred verticallyCentred", style="Bold"))
    c.extend(labels)
    # one rectangle per Q-Link page, in page order (page n = Q-Links 4n-3 .. 4n)
    qb = ["%d 150 %d 206" % (LCD_IN[0] + 4, int(COLW * 4) - 8),
          "%d 150 %d 206" % (int(LCD_IN[0] + COLW * 4) + 4, int(COLW * 4) - 8),
          "%d 430 %d 184" % (SPEED_C[0] - KNOB_FS // 2 - 14, JOG_C[0] + JOG_FS // 2 + 14 - (SPEED_C[0] - KNOB_FS // 2 - 14)),   # page 3: speed + jog wheel
          "%d 428 %d 164" % (DIAL_C[0] - 84, 168)]                                          # page 4: the loop dial
    tab1 = {"version": 1, "tabName": "STRETCH", "fnKeyIndex": 0, "fnKeySubIndex": 0,
            "componentDefinition": tab_root(c), "qlinkBoundsData": qb}
    tab2 = {"version": 1, "tabName": "HELP", "fnKeyIndex": 1, "fnKeySubIndex": 0,
            "componentDefinition": tab_root([image_entry("help1.png", 0, 0, W, H)]),
            "qlinkBoundsData": []}
    tab3 = {"version": 1, "tabName": "HELP 2", "fnKeyIndex": 1, "fnKeySubIndex": 1,
            "componentDefinition": tab_root([image_entry("help2.png", 0, 0, W, H)]),
            "qlinkBoundsData": []}
    return {"pageData": {"version": 1,
                         "componentDefinitions": {"version": 2, "importFiles": [],
                                                  "localComponentDefinitions": [
                                                      {"key": "creamKnob", "value": knob_component("knob_cream.png", KNOB_FRAMES, KNOB_FS)},
                                                      {"key": "redKnob", "value": knob_component("knob_red.png", KNOB_FRAMES, KNOB_FS)},
                                                      {"key": "bitKnob", "value": knob_component("knob_bits.png", N_BITS, KNOB_FS)},
                                                      {"key": "styleKnob", "value": knob_component("knob_style.png", 2, KNOB_FS)},
                                                      {"key": "jogKnob", "value": knob_component("jog_strip.png", JOG_FRAMES, JOG_FS)},
                                                      {"key": "dialKnob", "value": knob_component("dial_strip.png", N_DIAL, DIAL_FS)},
                                                      "@@OVERLAY@@"]},
                         "replacementStrings": [
                             {"key": "Parameter 3", "value": ["8", "12", "16", "24"]},
                             {"key": "Parameter 5", "value": ["Off", "On"]},
                             {"key": "Parameter 8", "value": ["CYCLIC", "INTELL"]},
                             {"key": "Parameter 9", "value": ["Off", "On"]},
                             {"key": "Parameter 11", "value": ["Off", "On"]},
                             {"key": "Parameter 12", "value": ["Off", "On"]},
                             {"key": "Parameter 15", "value": ["Off", "On"]},
                             {"key": "Parameter 20", "value": ["Off", "On"]},
                             {"key": "Parameter 21", "value": ["Off", "On"]},
                             {"key": "Parameter 13", "value": ["Free", "1/1", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]}],
                         "info": {"version": 1, "type": "CompleteDescription"},
                         "tabs": [tab1, tab2, tab3]}}


def build_qlinks():
    q = {("Q-Link %d" % i): -1 for i in range(1, 17)}
    for k, p in enumerate((0, 1, 6, 7)):
        q["Q-Link %d" % (1 + k)] = p                # page 1: Cyclic Length Qual Width
    for k, p in enumerate((3, 4, 22, 5)):
        q["Q-Link %d" % (5 + k)] = p                # page 2: Bit Rate Filter Pitch
    q["Q-Link 9"] = 19                              # page 3: Speed (left), Jog wheel (right), in screen order
    q["Q-Link 10"] = 10
    q["Q-Link 13"] = 13                             # page 4: Loop dial (ratio)
    prog = [0, 1, 6, 7, 3, 4, 22, 5, 19, 10, -1, -1, 13, -1, -1, -1]
    blank = {("Q-Link %d" % i): -1 for i in range(1, 17)}
    return {"version": 4, "info": {"version": 1, "type": "CompleteDescription"},
            "Screen Mode Q-Links": {"version": 4, "map": [
                {"Tab": 1, "SubTab": 1, "Bank Direction": "Row", "Q-Links": q},
                {"Tab": 2, "SubTab": 1, "Bank Direction": "Row", "Q-Links": dict(blank)},
                {"Tab": 2, "SubTab": 2, "Bank Direction": "Row", "Q-Links": dict(blank)}]},
            "Program Mode Q-Links": {("Q-Link %d" % (i + 1)): prog[i] for i in range(16)}}


# ---- help pages (two pages on the same function key: press HELP again for page 2) --------------------------------------------
FINE = ("FINE TUNING", "Hold SHIFT while turning a Q-Link (or the main encoder) to change a value in finer steps. It helps most on LENGTH "
        "(especially with PITCH on), CYCLIC, RATE, FILTER and the JOG wheel.")
HELP1 = [
    ("WHAT IT DOES", "An insert effect. Put it on a track and play audio through it: it records the live input and can stretch it (time stretch "
     "like an Akai S-series sampler), loop it, or cue / scrub it like a CD deck. With Length 100, Bit 24, Rate 44100, Cue off and no loop the "
     "audio passes through untouched, with no delay."),
    ("POWER  (key, top left)", "Pressing it takes the plugin out of the circuit: the audio passes straight through, with no delay and no effect, and any loop is dropped. "
     "Press it again to switch it on (the power symbol glows bright red); it starts clean from live."),
    ("MODE  (small key under POWER)", "Switches the stretcher between CYCLIC and INTELL, as on the Akai S1000; the outline turns red for INTELL. Both insert a whole cycle of "
     "the sound again and again. CYCLIC inserts the cycle length you set with Cyclic. INTELL searches for the best cycle itself (usually the "
     "pitch period), so it suits speech, music and drum patterns and is usually the better choice. In INTELL the first column reads INTELL, the "
     "first knob becomes the STYLE (see CYCLIC) and Qual / Width come alive; in CYCLIC it is the other way round. Pitch works in both modes."),
    ("LENGTH  (red knob)", "The main performance control. 100% = off. Raise it to stretch the sound WITHOUT changing its pitch: 200% = twice as "
     "long (half speed), up to 2000%. The longer you hold it the further you fall behind the live signal; bring it back to 100 and you snap "
     "back to live, so your sequence stays in time. Assign it to a pad (Q-Link edit: pressure or X/Y) or a Q-Link and punch it in. With PITCH "
     "on, the same knob spans only 100-300% so you can tune it finely."),
    ("CYCLIC  /  STYLE  (first knob)", "CYCLIC mode: the length in samples (0-2000) of the cycle that is inserted. Big = stuttery repeats (the S-series 'flam'), small = buzzy "
     "and metallic. Aim for the pitch period of the sound. 0 = AUTO: the cycle is searched like in INTELL. INTELL mode: the same knob is the STYLE. ORIG (left) is the "
     "S1000's lag search exactly as its ROM has it; on drums and hi-hats it ends on the shortest cycle (about 1 ms) and sounds washy. CLEAN (right, the default) "
     "repeats that search for cycles of 5 ms or more when it ends on the shortest, which removes the wash and leaves tonal sounds alone. Each mode keeps its own value."),
    ("QUAL / WIDTH", "INTELL mode only, and only while Length is above 100. QUAL (0-100) is how many points are compared when searching for the "
     "best cycle (QUAL + 1): low = quick guess, high = accurate. WIDTH (0-100) sets the crossfade between the original and the inserted cycle: "
     "(WIDTH + 1) cycles, up to the whole gap between insertions, so it matters most for gentle stretches. 90 and 90 works well almost every time."),
    ("BIT", "Output bit depth: 8, 12, 16 or 24. All the way right (24) leaves the sound untouched; turn left for crunchier. 12 is S950 grit, 8 is lo-fi."),
    ("RATE", "44100 down to 8000 Hz. True sample-rate reduction for lo-fi grit (22500 only removes the top octave, go lower to hear it)."),
    ("FILTER  (red knob)", "The Akai S900/S950 low-pass, 1:1, last in the chain so it also tames the aliasing of BIT and RATE. The S950's filter chip is a 6th-order "
     "Butterworth (-36 dB per octave) with NO resonance, and so is this. The knob uses the S950's own 0-99 scale and cutoff law, read from its ROM: from 0 to about "
     "22 the cutoff sits at 314 Hz, from 22 to 80 it sweeps six octaves up to 20 kHz in the S950's clock-divider steps, above 80 it is open (out of the circuit)."),
    ("PITCH  (key)", "On: Length shifts the PITCH instead (stretch, then resample, like an S-series). 200% = one octave up, same duration. The PITCH header is greyed while it is off."),
    FINE,
]
HELP2 = [
    ("CUE  (key)", "Pauses the audio and stutters the last 1/8 second, like a CD deck on cue. Press again to go back to live. Inside a loop, "
     "releasing CUE moves the loop's START to where the stutter began: loop playing, CUE on, JOG to the new start point, CUE off, and the loop now "
     "starts there (it rotates inside its own audio, the end moves with it). The key is lit while cue is on."),
    ("<< SCRUB >>  (jog wheel, touch strip)", "While CUE is on, turn the big wheel (touch-drag, main encoder or Q-Link) to step the cue point forward or back one "
     "CD frame (13 ms) at a time, 400 frames (about 5 s) each way. TOUCH STRIP: the MPC sends no MIDI to effect plugins, so the strip's Pitch / Mod / "
     "Expression modes cannot reach it. Instead put the strip in CROSSFADER mode and assign the JOG parameter to it in the MPC (an MPC setting, not "
     "something the plugin can pre-set). Press CUE, then sweep the strip: the scrub is relative to where the strip was when you pressed CUE. The main "
     "encoder (data wheel) also turns the wheel when it is selected."),
    ("SPEED  (knob, left of CUE)", "Turntable-style speed, -100 to +100 (0 = normal, +100 = twice as fast, -100 = stopped; the knob catches at 0). It changes the speed of the audio stored in the looper and of the Cue "
     "stutter only, at once, and is greyed out (--) while no loop runs and Cue is off; it never touches the live signal. In Cue the stutter repeats faster or "
     "slower. PITCH off keeps the pitch; PITCH on makes the pitch follow, like a record."),
    ("PUNCH IN / PUNCH OUT / STOP-START", "PUNCH IN marks the loop start (lit while a start is set). PUNCH OUT marks the end and starts the loop "
     "(lit while a loop exists); press it again to throw the loop away. STOP / START (lit while the loop runs) stops the loop WITHOUT dumping it: the live "
     "audio comes straight back, and the next press starts the same loop again from its start. A stopped loop is remembered for about 40 seconds. "
     "The loop's tempo is shown above the three keys."),
    ("LOOP DIAL", "With the dial on FREE, PUNCH IN / OUT make a loop of exactly the length you tapped. That loop is NOT tied to the sequence tempo: it "
     "counts as 1/1 and its BPM is shown above the keys. Turn the dial to cut it: 1/2 = half of the loop, 1/4 = a quarter ... 1/64, and back to 1/1 or FREE "
     "for the whole loop. The cut is measured from the loop's START and playback restarts there, so a loop that starts on a kick always plays the kick. "
     "If you choose a length BEFORE punching in, the loop is tempo-locked instead: PUNCH IN snaps to the sequence grid and it follows tempo changes."),
    ("Q-LINK PAGES", "Page 1: Cyclic, Length, Qual, Width.   Page 2: Bit, Rate, Filter, Pitch.   Page 3: Jog wheel, Speed.   Page 4: Loop dial (ratio).   The Q-Link box on the "
     "screen shows which page you are on."),
    FINE,
    ("NEEDS", "MPC OS 3.10.1+, External Plugin Support on. Experimental, provided AS IS."),
]
CONTACT = [("Keebz.com", None), ("Instagram: @LeeKebler", None), ("Github: Github.com/Keebz", None)]


def wrap(d, text, f, width):
    lines, cur = [], ""
    for w_ in text.split():
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def make_help_page(title, entries, footer=None):
    """lay the entries out in two columns, using the largest font that fits"""
    top, bottom = 48, H - (46 if footer else 8)
    col_x, col_w = [24, 650], 606
    for body_size in (16, 15, 14, 13, 12):
        im = Image.new("RGB", (W, H), (28, 30, 28))
        d = ImageDraw.Draw(im)
        f_h, f_b = font(FONT_B, body_size + 1), font(FONT_R, body_size)
        lh = body_size + 3
        d.text((24, 10), title, font=font(FONT_B, 21), fill=(176, 226, 130))
        x_i, y, ok = 0, top, True
        for head, body in entries:
            lines = wrap(d, body, f_b, col_w)
            need = lh + 2 + len(lines) * lh + 8
            if y + need > bottom:
                if x_i == 0:
                    x_i, y = 1, top
                else:
                    ok = False
                    break
            x = col_x[x_i]
            d.text((x, y), head, font=f_h, fill=(176, 226, 130))
            y += lh + 2
            for ln in lines:
                d.text((x, y), ln, font=f_b, fill=(222, 226, 214))
                y += lh
            y += 8
        if ok:
            break
    if footer:
        d.line([24, H - 38, W - 24, H - 38], fill=(70, 90, 60), width=1)
        f_c = font(FONT_B, 17)
        xs = [24, 330, 760]
        for (txt, _), x in zip(footer, xs):
            d.text((x, H - 30), txt, font=f_c, fill=(176, 226, 130))
    return im, body_size


def main():
    os.makedirs(SKINS, exist_ok=True)
    make_bg().save(os.path.join(SKINS, "bg.png"))
    for name, red in (("knob_cream.png", False), ("knob_red.png", True)):
        strip = Image.new("RGBA", (KNOB_FS, KNOB_FS * KNOB_FRAMES), (0, 0, 0, 0))
        for i in range(KNOB_FRAMES):
            strip.paste(knob_frame(i / (KNOB_FRAMES - 1), red), (0, i * KNOB_FS))
        strip.save(os.path.join(SKINS, name))
    bs = Image.new("RGBA", (KNOB_FS, KNOB_FS * N_BITS), (0, 0, 0, 0))                     # Bit knob: four positions, four dots
    for i in range(N_BITS):
        bs.paste(knob_frame(i / (N_BITS - 1), dots=N_BITS), (0, i * KNOB_FS))
    bs.save(os.path.join(SKINS, "knob_bits.png"))
    unit_caption("STYLE").save(os.path.join(SKINS, "ov_style_caption.png"))
    ks = Image.new("RGBA", (KNOB_FS, KNOB_FS * 2), (0, 0, 0, 0))                          # INTELL style knob: ORIG (left) / CLEAN (right)
    for i in range(2):
        ks.paste(knob_frame(float(i), dots=2), (0, i * KNOB_FS))
    ks.save(os.path.join(SKINS, "knob_style.png"))
    js = Image.new("RGBA", (JOG_FS, JOG_FS * JOG_FRAMES), (0, 0, 0, 0))
    for i in range(JOG_FRAMES):
        js.paste(jog_frame(360.0 * JOG_TURNS * i / (JOG_FRAMES - 1)), (0, i * JOG_FS))
    js.save(os.path.join(SKINS, "jog_strip.png"))
    ds = Image.new("RGBA", (DIAL_FS, DIAL_FS * N_DIAL), (0, 0, 0, 0))
    for i in range(N_DIAL):
        ds.paste(dial_frame(i), (0, i * DIAL_FS))
    ds.save(os.path.join(SKINS, "dial_strip.png"))
    header_patch(HDR_PITCH[0], HDR_PITCH[1], DIM_INK)[0].save(os.path.join(SKINS, "ov_dim_pitch.png"))
    pitch_key_img(False).save(os.path.join(SKINS, "pitch_off.png"))
    pitch_key_img(True).save(os.path.join(SKINS, "pitch_on.png"))
    knob_frame(0.0, False, 3, True, False).save(os.path.join(SKINS, "knob_idle.png"))     # muted, no pointer: not interactive
    header_patch(HDR_INTELL[0], HDR_INTELL[1], LCD_INK)[0].save(os.path.join(SKINS, "ov_intell_hdr.png"))
    header_patch(HDR_QUAL[0], HDR_QUAL[1], DIM_INK)[0].save(os.path.join(SKINS, "ov_dim_qual.png"))
    header_patch(HDR_WIDTH[0], HDR_WIDTH[1], DIM_INK)[0].save(os.path.join(SKINS, "ov_dim_width.png"))
    cream_key(KEY_P, False, (0, 0, 0)).save(os.path.join(SKINS, "key_p_off.png"))
    cream_key(KEY_P, True, (240, 70, 50)).save(os.path.join(SKINS, "key_p_on.png"))
    cream_key(KEY_P, False, (0, 0, 0)).save(os.path.join(SKINS, "key_r_off.png"))
    cream_key(KEY_P, True, (90, 220, 90)).save(os.path.join(SKINS, "key_r_on.png"))
    cream_key(KEY_L, False, (0, 0, 0)).save(os.path.join(SKINS, "key_l_off.png"))
    cream_key(KEY_L, True, (255, 160, 20)).save(os.path.join(SKINS, "key_l_on.png"))
    power_key_img(False).save(os.path.join(SKINS, "power_off.png"))
    power_key_img(True).save(os.path.join(SKINS, "power_on.png"))
    mode_small_img(False).save(os.path.join(SKINS, "modes_off.png"))
    mode_small_img(True).save(os.path.join(SKINS, "modes_on.png"))
    h1, sz1 = make_help_page("Z950  -  HELP  1 / 2        (press the HELP key again for page 2)", HELP1, CONTACT)
    h2, sz2 = make_help_page("Z950  -  HELP  2 / 2        (press the HELP key again for page 1)", HELP2, CONTACT)
    h1.save(os.path.join(SKINS, "help1.png"))
    h2.save(os.path.join(SKINS, "help2.png"))
    with open(os.path.join(SKINS, "TUI.json"), "w") as f:
        text = json.dumps(build_tui(), indent=1)
        with open(os.path.join(HERE, "overlay_def.json")) as g:      # holds the duplicate "version" keys Python dicts cannot
            text = text.replace('"@@OVERLAY@@"', g.read().strip())
        f.write(text)
    with open(os.path.join(SKINS, "Q-Links.json"), "w") as f:
        json.dump(build_qlinks(), f, indent=1)
    print("skin written to", SKINS, "| help font sizes:", sz1, sz2)


if __name__ == "__main__":
    main()
