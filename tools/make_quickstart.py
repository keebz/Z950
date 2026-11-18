#!/usr/bin/env python3
"""make_quickstart.py - build docs/Z950-QuickStart.pdf (system python with Pillow; no other dependency):

    python3 -I tools/make_quickstart.py

Pages are drawn as images (US Letter, 150 dpi) and saved as a PDF. The screen figures are composed from the real skin artwork in
skins/ (so run tools/make_skin.py first); the diagrams are drawn here.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import make_skin as M  # noqa: E402

SK = os.path.join(PROJ, "skins")
DOCS = os.path.join(PROJ, "docs")
FIG = os.path.join(DOCS, "qs")
os.makedirs(FIG, exist_ok=True)
FB, FR = M.FONT_B, M.FONT_R
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


INK, GOLD, GREY, RED, GREEN = (28, 26, 24), (176, 116, 8), (120, 120, 116), (170, 36, 24), (0, 110, 50)
ACCENT = (233, 168, 37)
PW, PH, MARGIN = 1275, 1650, 105           # US Letter at 150 dpi


# ---- screen figures (composed from the real skin images) -------------------------------------------------------------
def screen(intell=False, lit=(False, False, False), bpm="---", cue=False, pitch=False, power=True, vals=None, markers=None, rects=None,
           speed_frac=0.5, speed_txt="+0.0", speed_live=False):
    """the main tab as it looks on the MPC (the live LCD text is drawn with a similar font here)"""
    im = Image.open(os.path.join(SK, "bg.png")).convert("RGBA")
    d = ImageDraw.Draw(im)
    fv, fc = font(FB, 36), font(FR, 16)
    if intell:
        o = Image.open(os.path.join(SK, "ov_intell_hdr.png")).convert("RGBA")
        g = M.patch_geom(0)
        im.alpha_composite(o, (g[0], g[1]))
    else:
        for f, col in (("ov_dim_qual.png", M.COL_INDEX["qual"]), ("ov_dim_width.png", M.COL_INDEX["width"])):
            o = Image.open(os.path.join(SK, f)).convert("RGBA")
            g = M.patch_geom(col)
            im.alpha_composite(o, (g[0], g[1]))
    if not pitch:
        g = M.patch_geom(M.PITCH_COL)
        im.alpha_composite(Image.open(os.path.join(SK, "ov_dim_pitch.png")).convert("RGBA"), (g[0], g[1]))
    v = {"cyclic": ("2000", 1.0), "length": ("100", 0.0), "filter": ("99", 1.0), "bits": ("24", 1.0), "rate": ("44100", 1.0),
         "pitch": ("OFF", 0.0), "qual": ("90", 0.9), "width": ("90", 0.9)}
    if vals:
        v.update(vals)
    for i, (name, p, kind) in enumerate(M.COLS):
        txt, fr = v[name]
        cx = M.CX[i]
        idle = name in ("qual", "width") and not intell
        style = name == "cyclic" and intell                              # INTELL: the first knob is the style (ORIG / CLEAN)
        if style:
            txt, fr = "CLEAN", 1.0
            im.alpha_composite(M.unit_caption("STYLE"), M.unit_caption_geom(0)[:2])
        if idle and name in ("qual", "width"):
            d.text((cx - d.textlength("--", font=fv) / 2, 54), "--", font=fv, fill=(101, 148, 82))
        elif kind == "key":
            pass                                                         # Pitch has no number: its header is active or greyed
        elif not idle:
            d.text((cx - d.textlength(txt, font=fv) / 2, 54), txt, font=fv, fill=(18, 36, 13))
        if kind == "key":
            im.alpha_composite(M.pitch_key_img(pitch), M.PITCH_KEY)
        elif idle:
            im.alpha_composite(Image.open(os.path.join(SK, "knob_idle.png")).convert("RGBA"), (cx - 56, M.KNOB_CY - 56))
        else:
            im.alpha_composite(M.knob_frame(fr, red=(kind == "red"), dots=(M.N_BITS if name == "bits" else (2 if style else 11))), (cx - 56, M.KNOB_CY - 56))
            d.text((cx - d.textlength(txt, font=fc) / 2, 306), txt, font=fc, fill=(44, 40, 36))
    im.alpha_composite(M.power_key_img(power), (M.MODE_KEY[0], M.MODE_KEY[1]))
    im.alpha_composite(M.mode_small_img(intell), (M.MODE_SMALL[0], M.MODE_SMALL[1]))
    im.alpha_composite(Image.open(os.path.join(SK, "key_l_on.png" if cue else "key_l_off.png")).convert("RGBA"), M.CUE_KEY)
    im.alpha_composite(Image.open(os.path.join(SK, "key_p_on.png" if lit[0] else "key_p_off.png")).convert("RGBA"), M.IN_KEY)
    im.alpha_composite(Image.open(os.path.join(SK, "key_p_on.png" if lit[1] else "key_p_off.png")).convert("RGBA"), M.OUT_KEY)
    im.alpha_composite(Image.open(os.path.join(SK, "key_r_on.png" if lit[2] else "key_r_off.png")).convert("RGBA"), M.RUN_KEY)
    fb = font(FB, 19)
    w = M.RUN_KEY[0] + M.KEY_P[0] - M.IN_KEY[0]
    d.text((M.IN_KEY[0] + w / 2 - d.textlength(bpm, font=fb) / 2, M.IN_KEY[1] - 34), bpm, font=fb, fill=(236, 233, 223))
    im.alpha_composite(M.jog_frame(100), (M.JOG_C[0] - M.JOG_FS // 2, M.JOG_C[1] - M.JOG_FS // 2))
    im.alpha_composite(M.dial_frame(0), (M.DIAL_C[0] - 56, M.DIAL_C[1] - 56))
    if speed_live:
        sf = M.knob_frame(speed_frac, dots=11)
        txt, ink = speed_txt, (236, 233, 223)
    else:                                                                # greyed out: no loop running and Cue off
        sf = Image.open(os.path.join(SK, "knob_idle.png")).convert("RGBA")
        txt, ink = "--", (138, 138, 132)
    im.alpha_composite(sf, (M.SPEED_C[0] - 56, M.SPEED_C[1] - 56))
    d.text((M.SPEED_C[0] - d.textlength(txt, font=fb) / 2, M.SEC_A[1] + M.SEC_A[3] - 36), txt, font=fb, fill=ink)
    d.text((M.DIAL_C[0] - d.textlength("Free", font=fb) / 2, M.SEC_B[1] + M.SEC_B[3] - 32), "Free", font=fb, fill=(236, 233, 223))
    for r, col in (rects or []):
        d.rounded_rectangle(r, 10, outline=col, width=5)
    for n, (x, y) in (markers or {}).items():
        d.ellipse((x - 15, y - 15, x + 15, y + 15), fill=(210, 40, 28), outline=(255, 255, 255), width=2)
        d.text((x, y), str(n), font=font(FB, 17), fill=(255, 255, 255), anchor="mm")
    return im.convert("RGB")


def marker_positions():
    kc = lambda i: (M.CX[i] - 54, M.KNOB_CY - 50)
    mk = {1: (132, 68), 2: (700, 143), 3: kc(0), 4: kc(1), 5: kc(2), 6: kc(3), 7: kc(4), 8: kc(5), 9: kc(6),
            10: (M.PITCH_KEY[0] - 4, M.PITCH_KEY[1] + 4),
            12: (M.CUE_KEY[0] - 8, M.CUE_KEY[1] - 6), 13: (M.JOG_C[0] - 82, M.JOG_C[1] - 70),
            14: (M.IN_KEY[0] - 6, M.IN_KEY[1] - 6), 15: (M.OUT_KEY[0] - 6, M.OUT_KEY[1] - 6), 16: (M.RUN_KEY[0] - 6, M.RUN_KEY[1] - 6),
            17: (M.IN_KEY[0] + 52, M.IN_KEY[1] - 28), 18: (M.DIAL_C[0] - 62, M.DIAL_C[1] - 62), 19: (M.SPEED_C[0] - 62, M.SPEED_C[1] - 62)}
    mk = {(k - 1 if k >= 12 else k): v for k, v in mk.items()}
    out = {1: (M.MODE_KEY[0] + 80, M.MODE_KEY[1] + 8), 2: (M.MODE_SMALL[0] + 76, M.MODE_SMALL[1] + 6)}
    out.update({(k + 1 if k >= 2 else k): v for k, v in mk.items() if k != 1})
    return out


def fig_screens():
    figs = {}
    figs["hero"] = screen(vals={"length": ("100", 0.0)})
    figs["annot"] = screen(bpm="128.0 BPM", markers=marker_positions())
    figs["intell"] = screen(intell=True, vals={"length": ("250", 0.08)})
    figs["intell"] = figs["intell"].crop((0, 0, 1280, 350))
    figs["cyclic_top"] = screen(vals={"length": ("250", 0.08)}).crop((0, 0, 1280, 350))
    figs["bottom"] = screen(cue=False, lit=(True, True, True), bpm="128.0 BPM").crop((130, 390, 710, 628))
    figs["cue_on"] = screen(cue=True, speed_frac=0.62, speed_txt="+12.0", speed_live=True).crop((700, 390, 1280, 628))
    # Q-Link pages
    t = json.load(open(os.path.join(SK, "TUI.json")))
    rects = [tuple(int(float(v)) for v in r.split()) for r in t["pageData"]["tabs"][0]["qlinkBoundsData"]]
    pages = []
    for i, r in enumerate(rects):
        rr = (r[0], r[1], r[0] + r[2], r[1] + r[3])
        s = screen(vals={"length": ("100", 0.0)}, rects=[(rr, (233, 130, 20))])
        pages.append(s.resize((620, 304), Image.LANCZOS))
    figs["qlinks"] = pages
    for k, v in figs.items():
        if k != "qlinks":
            v.save(os.path.join(FIG, "fig_%s.png" % k))
    return figs


def wrap_lines(d, text, f, width):
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


# ---- diagrams ------------------------------------------------------------------------------------------------------------
def cyc(t):
    return math.sin(2 * math.pi * t) + 0.38 * math.sin(4 * math.pi * t + 1.1)


def fig_stretch():
    """one cycle copied into the signal now and then: the signal gets longer, the pitch stays"""
    W, H = 1100, 470
    im = Image.new("RGB", (W, H), (248, 246, 240))
    d = ImageDraw.Draw(im)
    f, fb, fs = font(FR, 20), font(FB, 22), font(FR, 19)
    x0, cw, amp = 40, 64, 34

    def draw_row(y, cycles, title):
        d.text((x0, y - 70), title, font=fb, fill=INK)
        x = x0
        for src, inserted in cycles:
            env = 0.55 + 0.45 * math.sin(math.pi * (src + 0.5) / 12.0)     # a slowly changing level, so the copy is visible
            pts = [(x + k * cw / 40.0, y - amp * env * cyc(k / 40.0)) for k in range(41)]
            if inserted:
                d.rectangle((x, y - amp - 8, x + cw, y + amp + 8), fill=(255, 226, 170))
            d.line(pts, fill=(200, 80, 10) if inserted else INK, width=3)
            d.line((x, y - amp - 8, x, y + amp + 8), fill=(190, 188, 182), width=1)
            x += cw
        return x
    draw_row(110, [(i, False) for i in range(12)], "original sound: 12 cycles")
    seq = []
    for i in range(12):
        seq.append((i, False))
        if i % 2 == 1:
            seq.append((i, True))                                                # a copy of the cycle that just played
    draw_row(280, seq, "stretched to 150%: one cycle (orange) is copied back in every 2 cycles")
    note = ("The pitch does not change, only the length. In CYCLIC mode the copied cycle is the Cyclic length; in INTELL mode Z950 searches for "
            "the best cycle (usually the pitch period). Every join is a crossfade, so there are no clicks. (Diagram only: real sounds are not this regular.)")
    y = 360
    for line in wrap_lines(d, note, fs, W - 2 * x0):
        d.text((x0, y), line, font=fs, fill=GREY)
        y += 28
    im.save(os.path.join(FIG, "fig_stretch.png"))
    return im


def fig_punch():
    """raise Length: you fall behind live; release: you snap back"""
    W, H = 1100, 400
    im = Image.new("RGB", (W, H), (248, 246, 240))
    d = ImageDraw.Draw(im)
    fb, fs = font(FB, 21), font(FR, 19)
    ox, oy, w, h = 60, 350, 1000, 270
    d.line((ox, oy, ox + w, oy), fill=INK, width=3)
    d.line((ox, oy, ox, oy - h), fill=INK, width=3)
    d.text((ox + w, oy + 12), "time", font=fs, fill=GREY, anchor="ra")
    d.text((ox + 12, oy - h - 6), "what you hear", font=fs, fill=GREY, anchor="la")
    t1, t2, t3 = 0.22, 0.68, 1.0
    s_ = 0.9
    live = [(ox, oy), (ox + w * t3, oy - h * t3 * s_)]
    d.line(live, fill=(150, 150, 146), width=3)
    p0 = (ox, oy)
    p1 = (ox + w * t1, oy - h * t1 * s_)
    p2 = (ox + w * t2, p1[1] - h * (t2 - t1) * s_ * 0.4)
    p3 = (ox + w * t2, oy - h * t2 * s_)
    p4 = (ox + w * t3, oy - h * t3 * s_)
    for a_, b_, wd in ((p0, p1, 6), (p1, p2, 6), (p2, p3, 3), (p3, p4, 6)):
        d.line((a_, b_), fill=(200, 80, 10), width=wd)
    for x_, lab in (((p0[0] + p1[0]) / 2, "Length 100"), ((p1[0] + p2[0]) / 2, "Length held at 300"), ((p3[0] + p4[0]) / 2, "released")):
        tw = d.textlength(lab, font=fb)
        d.rectangle((x_ - tw / 2 - 8, oy - 46, x_ + tw / 2 + 8, oy - 14), fill=(248, 246, 240))
        d.text((x_, oy - 30), lab, font=fb, fill=INK, anchor="mm")
    d.text(((p1[0] + p2[0]) / 2, p2[1] + 26), "slower and slower, same pitch", font=fs, fill=(200, 80, 10), anchor="mm")
    d.text((p3[0] + 14, (p2[1] + p3[1]) / 2), "snap back to live", font=fb, fill=INK, anchor="lm")
    d.text((ox + w * 0.30, oy - h * 0.30 * s_ - 56), "live input", font=fs, fill=GREY, anchor="mm")
    im.save(os.path.join(FIG, "fig_punch.png"))
    return im


def bar(d, x, y, w, h, segs, label=None, lf=None):
    """a loop drawn as a bar of coloured parts: segs = [(fraction, colour, text)]"""
    cx = x
    for frac, col, txt in segs:
        sw = w * frac
        d.rectangle((cx, y, cx + sw, y + h), fill=col, outline=INK, width=2)
        if txt:
            d.text((cx + sw / 2, y + h / 2), txt, font=lf, fill=INK, anchor="mm")
        cx += sw
    if label:
        d.text((x - 16, y + h / 2), label, font=lf, fill=INK, anchor="rm")


def fig_loop():
    W, H = 1100, 680
    im = Image.new("RGB", (W, H), (248, 246, 240))
    d = ImageDraw.Draw(im)
    fb, fs, fsm = font(FB, 22), font(FR, 19), font(FB, 17)
    kick, snare, hat, rest = (244, 190, 120), (170, 205, 240), (205, 232, 190), (232, 230, 224)
    x, w, h = 150, 880, 54
    d.text((20, 14), "A loop tapped with the dial on FREE counts as 1/1 (the whole loop):", font=fb, fill=INK)
    ys = [84, 158, 232]
    bar(d, x, ys[0], w, h, [(0.25, kick, "KICK"), (0.25, hat, "hat"), (0.25, snare, "SNARE"), (0.25, hat, "hat")], "1/1", fsm)
    bar(d, x, ys[1], w, h, [(0.5, kick, "KICK  hat"), (0.5, rest, "")], "1/2", fsm)
    bar(d, x, ys[2], w, h, [(0.25, kick, "KICK"), (0.75, rest, "")], "1/4", fsm)
    y = 300
    for line in wrap_lines(d, "Turn the dial while it plays: the loop is cut to that fraction, measured from the START, and playback restarts there.", fs, W - 40):
        d.text((20, y), line, font=fs, fill=GREY)
        y += 26
    d.text((20, 352), "Cue + Jog moves the start:  Cue on, Jog to the SNARE, Cue off.", font=fb, fill=INK)
    ys2 = [424, 498, 572]
    bar(d, x, ys2[0], w, h, [(0.25, snare, "SNARE"), (0.25, hat, "hat"), (0.25, kick, "KICK"), (0.25, hat, "hat")], "1/1", fsm)
    bar(d, x, ys2[1], w, h, [(0.5, snare, "SNARE  hat"), (0.5, rest, "")], "1/2", fsm)
    bar(d, x, ys2[2], w, h, [(0.25, snare, "SNARE"), (0.75, rest, "")], "1/4", fsm)
    y = 636
    for line in wrap_lines(d, "Same audio, new start: the loop turns around inside itself and the ratio cuts now begin on the snare.", fs, W - 40):
        d.text((20, y), line, font=fs, fill=GREY)
        y += 26
    for yy in (ys[0], ys2[0]):
        d.line((x, yy - 6, x, yy - 28), fill=RED, width=4)
        d.polygon([(x, yy - 4), (x - 8, yy - 16), (x + 8, yy - 16)], fill=RED)
        d.text((x + 14, yy - 22), "start", font=fsm, fill=RED, anchor="lm")
    im.save(os.path.join(FIG, "fig_loop.png"))
    return im


def fig_install():
    W, H = 1000, 400
    im = Image.new("RGB", (W, H), (245, 243, 238))
    d = ImageDraw.Draw(im)
    f, fb = font(FM, 24), font(FB, 22)
    d.text((24, 16), "Your SD card / USB drive (top level)", font=fb, fill=INK)
    rows = [(0, "VST2 Plugins/", "your existing folder: keep it", GREY, False),
            (1, "Some Other Plugin/", "already there: leave it alone", GREY, False),
            (1, "Keebz - VST - Z950/", "NEW: the only thing you add", GREEN, True),
            (2, "VST/, Plugin Skins/ ...", "leave these as they are", GREY, False)]
    y = 66
    for lvl, name, note, col, hot in rows:
        x = 40 + lvl * 44
        if hot:
            d.rounded_rectangle((x - 10, y - 6, W - 20, y + 38), 8, fill=(214, 240, 222), outline=GREEN, width=3)
        d.text((x, y), name, font=f, fill=INK if not hot else (0, 80, 30))
        d.text((600, y + 3), note, font=font(FR, 20), fill=col)
        y += 62
    im.save(os.path.join(FIG, "fig_install.png"))
    return im


# ---- page layout -----------------------------------------------------------------------------------------------------
class Doc:
    def __init__(self):
        self.pages, self.im, self.d, self.y = [], None, None, 0
        self.new_page()

    def new_page(self):
        if self.im:
            self.finish_page()
        self.im = Image.new("RGB", (PW, PH), (255, 255, 255))
        self.d = ImageDraw.Draw(self.im)
        self.d.rectangle((0, 0, PW, 14), fill=ACCENT)
        self.y = MARGIN

    def finish_page(self):
        n = len(self.pages) + 1
        self.d.text((MARGIN, PH - 70), "Z950 by Keebz - Quick Start     (experimental software, provided AS IS)", font=font(FR, 18), fill=GREY)
        self.d.text((PW - MARGIN, PH - 70), "page %d" % n, font=font(FR, 18), fill=GREY, anchor="ra")
        self.pages.append(self.im)

    def room(self, h):
        if self.y + h > PH - 110:
            self.new_page()

    def wrap(self, text, f, width):
        lines = []
        for para in text.split("\n"):
            cur = ""
            for w in para.split(" "):
                t = (cur + " " + w).strip()
                if self.d.textlength(t, font=f) <= width:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines

    def h1(self, text):
        self.room(150)
        self.y += 20
        self.d.text((MARGIN, self.y), text, font=font(FB, 44), fill=INK)
        self.y += 68

    def h2(self, text):
        self.room(110)
        self.y += 14
        self.d.text((MARGIN, self.y), text, font=font(FB, 29), fill=GOLD)
        self.y += 46

    def p(self, text, size=23, color=INK, indent=0, gap=12, bold=False):
        f = font(FB if bold else FR, size)
        for line in self.wrap(text, f, PW - 2 * MARGIN - indent):
            self.room(size + 14)
            self.d.text((MARGIN + indent, self.y), line, font=f, fill=color)
            self.y += int(size * 1.5)
        self.y += gap

    def step(self, n, text):
        f = font(FR, 23)
        lines = self.wrap(text, f, PW - 2 * MARGIN - 70)
        self.room(len(lines) * 35 + 16)
        self.d.ellipse((MARGIN, self.y - 2, MARGIN + 40, self.y + 38), fill=ACCENT)
        self.d.text((MARGIN + 20, self.y + 18), str(n), font=font(FB, 24), fill=INK, anchor="mm")
        for line in lines:
            self.d.text((MARGIN + 66, self.y), line, font=f, fill=INK)
            self.y += 35
        self.y += 12

    def bullet(self, text, indent=0):
        f = font(FR, 23)
        lines = self.wrap(text, f, PW - 2 * MARGIN - 40 - indent)
        self.room(len(lines) * 35 + 8)
        self.d.ellipse((MARGIN + indent + 6, self.y + 12, MARGIN + indent + 16, self.y + 22), fill=GOLD)
        for line in lines:
            self.d.text((MARGIN + indent + 36, self.y), line, font=f, fill=INK)
            self.y += 35
        self.y += 6

    def item(self, n, title, text):
        """numbered legend entry that matches a red marker in a figure"""
        f, fb = font(FR, 21), font(FB, 21)
        lines = self.wrap(title + "  " + text, f, PW - 2 * MARGIN - 62)
        self.room(len(lines) * 31 + 12)
        self.d.ellipse((MARGIN, self.y, MARGIN + 36, self.y + 36), fill=(210, 40, 28))
        self.d.text((MARGIN + 18, self.y + 18), str(n), font=font(FB, 20), fill=(255, 255, 255), anchor="mm")
        first = True
        for line in lines:
            if first and line.startswith(title):
                self.d.text((MARGIN + 54, self.y + 2), title, font=fb, fill=INK)
                tw = self.d.textlength(title + " ", font=fb)
                self.d.text((MARGIN + 54 + tw, self.y + 2), line[len(title):].strip(), font=f, fill=INK)
            else:
                self.d.text((MARGIN + 54, self.y + 2), line, font=f, fill=INK)
            first = False
            self.y += 31
        self.y += 10

    def box(self, title, text, fill=(255, 244, 214), edge=(200, 140, 20), tcol=INK):
        f, fb = font(FR, 21), font(FB, 23)
        lines = self.wrap(text, f, PW - 2 * MARGIN - 50)
        h = 30 + 36 + len(lines) * 31 + 16
        self.room(h + 16)
        self.d.rounded_rectangle((MARGIN, self.y, PW - MARGIN, self.y + h), 12, fill=fill, outline=edge, width=3)
        self.d.text((MARGIN + 25, self.y + 18), title, font=fb, fill=tcol)
        yy = self.y + 18 + 38
        for line in lines:
            self.d.text((MARGIN + 25, yy), line, font=f, fill=INK)
            yy += 31
        self.y += h + 20

    def image(self, im, width=None, caption=None):
        width = width or (PW - 2 * MARGIN)
        im = im.convert("RGB")
        h = int(im.height * width / im.width)
        self.room(h + 60)
        im = im.resize((width, h), Image.LANCZOS)
        x = (PW - width) // 2
        self.im.paste(im, (x, self.y))
        self.d.rectangle((x, self.y, x + width, self.y + h), outline=(190, 188, 182), width=2)
        self.y += h + 8
        if caption:
            self.d.text((PW // 2, self.y), caption, font=font(FR, 18), fill=GREY, anchor="ma")
            self.y += 34
        self.y += 10


def main():
    figs = fig_screens()
    f_stretch, f_punch, f_loop, f_install = fig_stretch(), fig_punch(), fig_loop(), fig_install()
    D = Doc()

    # ---- cover -------------------------------------------------------------------------------------------------------
    D.d.text((MARGIN, D.y), "Z950", font=font(FB, 66), fill=INK)
    D.y += 90
    D.p("by Keebz   -   Quick Start", size=32, color=GOLD, bold=True, gap=16)
    D.p("A live time-stretch and pitch-shift insert effect for the Akai MPC, in the spirit of the time-stretch of the Akai S-series rack samplers "
        "(S950, S1000, S3000). Put it on a track, play audio through it and punch the stretch in: the sound gets longer and slower without changing "
        "pitch, then snaps back to live. Add S-series style lo-fi, a CD-deck cue and scrub wheel, and a looper that can cut a loop in note fractions "
        "and move its start point.", gap=18)
    D.image(figs["hero"], caption="The Z950 screen (a picture of the design: fonts on the MPC differ slightly)")
    D.box("REQUIREMENTS",
          "An Akai MPC running MPC OS 3.10.1 or later, with Preferences > Enhancements (Beta) > Enable Enhancements and External Plugin Support turned on. "
          "Z950 is an insert effect: it stretches the audio that plays through the track it is inserted on. It works on any track, and also as a sampler FX on live audio input. It was made and tested on the MPC Live III. "
          "Other MPC models that run external plugins should load it but are untested.", fill=(235, 244, 255), edge=(60, 110, 190))
    D.box("EXPERIMENTAL - PROVIDED \"AS IS\"",
          "Z950 is experimental software, provided \"AS IS\", without warranty of any kind, express or implied. You use it entirely at your own risk. "
          "External plugin support on the MPC is itself a beta feature and third-party plugins can crash the MPC: save your projects often and back up your "
          "card before installing. Not affiliated with or endorsed by Akai Professional or inMusic; \"Akai\", \"MPC\" and the S-series names belong to their owners.",
          fill=(255, 232, 228), edge=RED, tcol=RED)

    # ---- install -----------------------------------------------------------------------------------------------------
    D.new_page()
    D.h1("1.  Install")
    D.p("You need an SD card or USB drive (or the MPC's internal drive in computer mode) and a computer.", gap=6)
    D.h2("A.  Your drive has no \"VST2 Plugins\" folder yet")
    D.step(1, "Unzip the download. Inside is one folder called VST2 Plugins, and inside that one folder called \"Keebz - VST - Z950\".")
    D.step(2, "Copy the whole VST2 Plugins folder to the top level of your SD card or USB drive (not inside another folder).")
    D.h2("B.  You already have a \"VST2 Plugins\" folder")
    D.box("DO NOT REPLACE YOUR EXISTING VST2 PLUGINS FOLDER",
          "Your other plugins live in it. If your computer asks whether to Replace the folder, choose Stop / Cancel: on a Mac, Replace deletes what was in "
          "your folder. Add only the Z950 folder, as below.", fill=(255, 232, 228), edge=RED, tcol=RED)
    D.step(1, "Open the VST2 Plugins folder from the download. You will see one folder: \"Keebz - VST - Z950\".")
    D.step(2, "Open your drive and its existing VST2 Plugins folder, then copy only the \"Keebz - VST - Z950\" folder into it. Keep the name exactly as it is.")
    D.image(f_install, width=640, caption="Z950 sits next to your other plugins. Nothing else is touched.")
    D.h2("Switch it on in the MPC")
    D.step(1, "On the MPC open Preferences > Enhancements (Beta) and turn on Enable Enhancements and External Plugin Support. Read the warning. The plugin stays hidden until both are on.")
    D.step(2, "On the track whose audio you want to stretch, add an insert effect: the browser lists External Plugins > Z950 (by Keebz). Play audio through the track: with every control at its starting value the sound passes through untouched, with no delay. "
           "It works on any track, and you can also use it as a sampler FX on live audio input.")

    # ---- the screen --------------------------------------------------------------------------------------------------
    D.new_page()
    D.h1("2.  The screen at a glance")
    D.image(figs["annot"], width=470, caption="Everything is on one screen. The numbers match the list below.")
    items = [
        (1, "Power key.", "Takes the plugin out of the circuit: the audio passes straight through. The power symbol glows bright red while the plugin is on."),
        (2, "Mode key.", "CYCLIC or INTELL stretching. The outline turns red for INTELL."),
        (2, "The readout.", "Shows every value. The first column reads CYCLIC (with the cycle length) or INTELL."),
        (3, "Cyclic / Style.", "CYCLIC mode: the cycle length. INTELL mode: the style, ORIG (the S1000 as it is) or CLEAN (default)."),
        (4, "Length (red).", "The main control. 100% = off. Raise it to stretch, release to snap back to live."),
        (5, "Qual.", "INTELL only: how carefully it looks for the best cycle."),
        (6, "Width.", "INTELL only: how smooth the joins are."),
        (7, "Bit.", "Bit depth: 8, 12, 16 or 24 (all the way right = untouched)."),
        (8, "Rate.", "Sample-rate reduction, 44100 down to 8000 Hz."),
        (9, "Filter.", "The S900/S950 low-pass, 1:1 (6th-order Butterworth, no resonance), on the S950's own 0-99 scale."),
        (10, "Pitch.", "On = Length shifts the pitch instead of stretching. The word PITCH is greyed while it is off."),
        (11, "Cue.", "Stutters the last 1/8 second like a CD deck on cue."),
        (12, "Scrub wheel.", "While Cue is on, steps the cue point back and forward one CD frame at a time."),
        (13, "Punch In.", "Marks the loop start."),
        (14, "Punch Out.", "Marks the loop end and starts the loop."),
        (15, "Stop / Start.", "Stops the loop without losing it; starts it again."),
        (16, "Loop BPM.", "The tempo of the running loop."),
        (17, "Loop dial.", "Cuts the loop to Free, 1/1, 1/2 ... 1/64."),
        (18, "Speed.", "Turntable speed of a running loop or of the Cue stutter, -100 to +100. Greyed out otherwise. A new loop resets it to 0."),
    ]
    items = items[:2] + [(t[0] + 1,) + tuple(t[1:]) for t in items[2:]]
    for it in items:
        D.item(*it)

    D.new_page()
    D.h1("Q-Link knobs: four pages")
    D.p("The Q-Link knobs work in pages of four, in the same order as the screen. The orange box on the screen shows which page you are on.", gap=6)
    cap = ["Page 1: Cyclic, Length, Qual, Width", "Page 2: Bit, Rate, Filter, Pitch", "Page 3: scrub wheel, Speed", "Page 4: the loop dial (ratio)"]
    pg = figs["qlinks"]
    sheet = Image.new("RGB", (1290, 700), (255, 255, 255))
    sd = ImageDraw.Draw(sheet)
    for i, im in enumerate(pg):
        x, y = (i % 2) * 650, (i // 2) * 350
        sheet.paste(im, (x, y))
        sd.text((x + 310, y + 312), cap[i], font=font(FB, 19), fill=INK, anchor="ma")
    D.image(sheet, width=960, caption="The Q-Link page you are on is boxed in orange")
    D.box("FINER TUNING",
          "Hold SHIFT while turning a Q-Link (or the main encoder) to change a value in finer steps. It helps most on Length (especially with Pitch on), "
          "Cyclic, Rate, Filter, Speed and the scrub wheel. The HELP tab inside the plugin (two pages, press the HELP key again for page 2) repeats all of this.",
          fill=(235, 244, 255), edge=(60, 110, 190))
    D.h2("Built-in presets")
    rows = [("Default", "everything off: a clean passthrough"), ("Punch 300%", "Length 300, ready to punch in"),
            ("Intell 200%", "INTELL mode, Length 200"), ("Jungle Stretch", "Cyclic 1200, Length 450, 12-bit, 32 kHz"),
            ("Chipmunk +1oct", "Pitch on, an octave up"), ("Dark Tape", "Length 250, Filter 33 (about 670 Hz)"),
            ("S950 12-bit", "Length 150, 12-bit at 36 kHz"), ("Lo-Fi 8-bit", "Length 200, 8-bit at 12 kHz"),
            ("Beat Repeat 1/8", "Cyclic 600 with the loop dial on 1/8")]
    f, fb = font(FR, 22), font(FB, 22)
    for name, desc in rows:
        D.room(40)
        D.d.text((MARGIN + 10, D.y), name, font=fb, fill=INK)
        D.d.text((MARGIN + 330, D.y), desc, font=f, fill=INK)
        D.y += 38
    D.y += 10

    # ---- stretching --------------------------------------------------------------------------------------------------
    D.new_page()
    D.h1("3.  Stretching")
    D.p("Z950 records what comes in and plays it back slower, without changing the pitch, the way the Akai S-series samplers did their time stretch: "
        "whole cycles of the sound are repeated, with crossfades hiding the joins.", gap=8)
    D.image(f_stretch, width=840, caption="The idea: one cycle at a time is copied back into the sound")

    D.h2("Punch it in with Length")
    D.step(1, "Play a loop or a sustained sound through the track.")
    D.step(2, "Raise LENGTH (the red knob). 100% is off. 200% plays the sound at half speed, 300% at a third. It goes up to 2000%.")
    D.step(3, "Hold it as long as you like: the longer you hold, the further behind live you fall, always at the original pitch.")
    D.step(4, "Bring LENGTH back to 100 and you snap straight back to the live signal, so your sequence stays in time.")
    D.image(f_punch, width=800, caption="Held Length falls behind live; releasing it snaps back")
    D.p("Tip: put LENGTH on a pad (Q-Link edit, pad pressure or X/Y) or on a Q-Link and play it like an instrument. While the stretch is working "
        "the sound is about 50 to 60 ms behind live; at 100% there is no delay. With PITCH on it is about 25 to 90 ms late.", size=21, color=GREY)
    D.new_page()
    D.h2("CYCLIC or INTELL: the MODE key (small key under POWER)")
    D.image(figs["cyclic_top"], width=820, caption="CYCLIC mode: Cyclic is live, Qual and Width are greyed out")
    D.bullet("CYCLIC: you choose the cycle that is copied with CYCLIC (0 to 2000 samples). Long cycles give the stuttery, flam-like repeats of the S-series; short ones sound buzzy and metallic. Aim for the pitch period of the sound. At 0 (Auto) the cycle is searched for you. It suits single notes.")
    D.bullet("INTELL: Z950 searches for the best cycle itself, usually the pitch period, so the joins are smooth. It suits speech, music and drum patterns and is usually the better choice. The first knob becomes the STYLE: CLEAN (default) or ORIG. ORIG is the S1000's search exactly as its ROM has it, which on drums and hi-hats ends on the shortest cycle (about 1 ms) and sounds washy; CLEAN repeats that search for cycles of 5 ms or more in that case and leaves tonal sounds alone.")
    D.image(figs["intell"], width=820, caption="INTELL mode: the first column reads INTELL, the first knob is the ORIG / CLEAN style, Qual and Width are live")
    D.bullet("QUAL (0 to 100): how many points are compared when searching for the best cycle. Low = a quick guess, high = accurate. 90 or more works well.")
    D.bullet("WIDTH (0 to 100): how long the crossfade is. Higher = smoother, softer joins. It matters most on gentle stretches (Length 105 to 150). 90 and 90 works well almost every time.")
    D.p("Qual and Width only do something while LENGTH is above 100 and the mode is INTELL.", size=21, color=GREY)

    # ---- pitch, phase, bit, rate -------------------------------------------------------------------------------------
    D.new_page()
    D.h1("4.  Pitch, Bit, Rate and Filter")
    D.h2("PITCH: the chipmunk key")
    D.p("Switch PITCH on and LENGTH changes meaning: instead of making the sound longer, it shifts the pitch while the duration stays the same, the "
        "classic S-series way (stretch, then resample). 200% = one octave up, 300% = a fifth above that. With Pitch on, the LENGTH knob spans only "
        "100 to 300% so you can tune it more finely. Hold SHIFT for even finer steps. Pitch works in both CYCLIC and INTELL mode; INTELL usually sounds smoother.", gap=10)
    D.h2("FILTER: the S950 low-pass")
    D.p("The Akai S900/S950 low-pass filter, 1:1, the last stage before the output, so it also smooths the edges that BIT and RATE create. The S950's "
        "filter chip is a 6th-order Butterworth (-36 dB per octave) with no resonance, and so is this. The red knob uses the S950's own 0 to 99 scale "
        "and cutoff law, read from the S950 ROM:", gap=6)
    D.bullet("0 to about 22: the cutoff stays at its lowest, 314 Hz. The S950 does not go lower.")
    D.bullet("About 22 to 80: it sweeps six octaves up to 20 kHz, in the S950's clock-divider steps (a little over a semitone each).")
    D.bullet("Above 80 and at 99: the filter is open (out of the circuit).")
    D.h2("BIT and RATE: S-series grit")
    D.bullet("BIT: 8, 12, 16 or 24 bits. All the way right (24) leaves the sound untouched. 12 gives the grit of the older S-series samplers; 8 is lo-fi.")
    D.bullet("RATE: true sample-rate reduction from 44100 down to 8000 Hz. 22050 only removes the top octave, so go lower to hear it clearly.")
    D.p("Bit, Rate and Filter also work on the looper and the cue stutter. With every control at its starting value, the sound passes through untouched.", size=21, color=GREY)
    D.h2("Recipes")
    D.step(1, "Drum break, tail of a bar: INTELL mode, Qual 90, Width 90. Punch LENGTH up to 150 for the last beat only, then release.")
    D.step(2, "Vocal slow-down: INTELL, Length 300 held for a word, Filter 60, Bit 12 for grit.")
    D.step(3, "Synth riser: Pitch on, slowly raise LENGTH from 100 to 300 with a Q-Link.")
    D.step(4, "Old sampler vibe: Bit 12, Rate 30000, Length a little over 100 in CYCLIC mode with Cyclic around 1500.")

    # ---- cue and scrub -----------------------------------------------------------------------------------------------
    D.new_page()
    D.h1("5.  Cue and scrub")
    D.p("The bottom-right of the screen is a CD deck's jog wheel, cue key and speed (turntable pitch) knob.", gap=8)
    D.image(figs["cue_on"], width=380, caption="Cue lit (on): the audio is stuttering the last 1/8 second")
    D.step(1, "Press CUE: the audio pauses and the last 1/8 of a second repeats, like the stutter of a CD player on cue. The key lights.")
    D.step(2, "While CUE is on, turn the big SCRUB wheel: every step moves the cue point one CD frame (1/75 second) back or forward. Touch-drag it, or use the main encoder or a Q-Link. You have 400 frames, about 5 seconds, each way from where you pressed CUE.")
    D.step(3, "Press CUE again to go back to live.")
    D.p("Scrubbing forward past the live input is not possible (live audio has no future), but inside a loop both directions work.", size=21, color=GREY)
    D.h2("SPEED: the turntable pitch control")
    D.p("The knob on the left of the cue box works like the pitch fader of a turntable, 100% either way (-100 to +100, 0 in the middle; the knob catches "
        "at 0, so it is easy to reset). It changes how fast the audio stored in the looper plays, and the speed of the Cue stutter. It is greyed out "
        "(shows --) unless a loop is running or Cue is on, and it never touches the live signal.", gap=6)
    D.bullet("Loop: it acts at once, because the loop is already in memory. +100 plays it twice as fast, -50 at half speed, -100 stops it. A new loop always starts at 0.")
    D.bullet("Cue: the stutter repeats faster or slower: at +100 the repeats come twice as often, at -50 half as often.")
    D.bullet("PITCH off keeps the pitch; PITCH on makes it follow, like a record. SHIFT = finer steps. Q-Link page 3.")
    D.h2("Using the touch strip as the scrub wheel")
    D.p("The scrub wheel is a normal parameter (it is on Q-Link page 3), so you can put the Live III touch strip on it. The strip's Pitch Bend, Mod and "
        "Expression modes send MIDI, and the MPC does not pass MIDI to effect plugins, so use the strip's Crossfader mode and assign the Jog / scrub "
        "parameter to it in the MPC (an MPC setting; it cannot be pre-set by the plugin). Press CUE, then sweep the strip: the scrub is relative to where the strip "
        "was when you pressed CUE.", gap=8)

    # ---- looper ------------------------------------------------------------------------------------------------------
    D.new_page()
    D.h1("6.  The looper")
    D.image(figs["bottom"], width=700, caption="The looper: Punch In, Punch Out, Stop / Start, the loop's BPM and the ratio dial")
    D.step(1, "PUNCH IN marks the start (the key lights). PUNCH OUT marks the end and starts the loop (it lights too, and so does STOP / START).")
    D.step(2, "With the dial on FREE, the loop is exactly the length you tapped. It is not tied to the sequence tempo: it counts as one whole note (1/1) and its BPM is shown above the keys.")
    D.step(3, "Turn the LOOP DIAL while it plays to cut the loop: 1/2 = the first half, 1/4 = the first quarter ... 1/64. The cut always starts at the loop START and playback restarts there, so a loop that starts on a kick always plays the kick.")
    D.step(4, "STOP / START stops the loop but does not dump it: the live audio comes straight back. Press it again and the same loop restarts from its start. A stopped loop is remembered for about 40 seconds.")
    D.step(5, "PUNCH OUT again (or a new PUNCH IN) throws the loop away; all the keys go dark.")
    D.image(f_loop, width=600, caption="Ratio cuts start at the start; Cue + Jog moves the start")

    D.new_page()
    D.h2("Move the start of a running loop")
    D.p("With a loop playing: press CUE, turn the SCRUB wheel to the spot you want as the new start (hear it stutter), then press CUE again. The loop "
        "rotates inside itself: it now starts where you scrubbed to, and ratio cuts start there too. The audio is the same, only where it begins changes.", gap=8)
    D.h2("Tempo-locked loops")
    D.p("If you choose a length on the dial (1/1 to 1/64) BEFORE you press Punch In, the loop is tied to the sequence tempo instead: Punch In snaps to the grid, "
        "the loop starts by itself after that length, and it follows tempo changes.", gap=6)

    # ---- troubleshooting ---------------------------------------------------------------------------------------------
    D.h1("7.  If something is not working")
    D.bullet("Nothing happens when I turn things: LENGTH must be above 100 to stretch. At 100, with Bit at 24 and Rate at 44100, the sound passes through untouched.")
    D.bullet("Qual or Width do nothing: they work only in INTELL mode (MODE key outlined red) and only while LENGTH is above 100.")
    D.bullet("The first knob reads CLEAN or ORIG instead of a number: that is INTELL mode (it picks the cycle itself). Press the MODE key to go back to CYCLIC.")
    D.bullet("The sound is a little late while stretching: that is normal, about 50 to 60 ms. At LENGTH 100 there is no delay. With PITCH on the delay is about 25 to 90 ms.")
    D.bullet("The loop disappeared: a loop stopped for more than about 40 seconds has left the memory and cannot be restarted. Press PUNCH IN to make a new one.")
    D.bullet("The touch strip does nothing: see \"Using the touch strip as the scrub wheel\". Use Crossfader mode and assign the Jog parameter to it.")
    D.h2("Limits")
    D.bullet("Stretching works on the live input and has a memory of about 40 seconds. It is modelled on how the Akai S1000 stretches (whole cycles inserted with crossfades, a CYCLIC and an INTELL mode), but it is not a sample-accurate copy of any Akai machine.")
    D.bullet("Very long stretches of complex sounds can sound rough, as on the old samplers: try INTELL, Qual 90, Width 90.")
    D.h2("About")
    D.p("Keebz.com", size=26, color=GOLD, bold=True, gap=2)
    D.p("Instagram: @LeeKebler", size=26, color=GOLD, bold=True, gap=2)
    D.p("Github: Github.com/Keebz", size=26, color=GOLD, bold=True, gap=14)
    D.p("Built with the inMusic MPC Plugin SDK (MIT): github.com/inmusic-software/mpc-plugin-builder-sdk. Z950 is MIT licensed and contains no Akai code or data. Not affiliated with Akai Professional or inMusic.", size=18, color=GREY, gap=0)

    D.finish_page()
    out = os.path.join(DOCS, "Z950-QuickStart.pdf")
    D.pages[0].save(out, "PDF", resolution=150.0, save_all=True, append_images=D.pages[1:])
    for i, pg_ in enumerate(D.pages):
        pg_.save(os.path.join(FIG, "page%d.png" % (i + 1)))
    print("wrote", out, "(%d pages)" % len(D.pages))


if __name__ == "__main__":
    main()
