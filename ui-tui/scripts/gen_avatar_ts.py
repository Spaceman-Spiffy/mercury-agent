#!/usr/bin/env python3
"""Generate the Mercury avatar as truecolor half-block ANSI rows, emit a TS module.
Each row is one terminal line: fg=top pixel, bg=bottom pixel, glyph U+2580 (upper half block).
Width = COLS cells, height = COLS/2 rows (square aspect)."""
import subprocess, json

SRC = "/home/peterb/Pictures/Gemini_Generated_Image_nolnlinolnlinoln.png"
COLS = 64
ROWS = COLS // 2
PXW, PXH = COLS, ROWS * 2
BG = (17, 20, 26)                  # slate #11141a (matches mercury skin backdrop)
OUT_TS = "/home/peterb/.hermes/hermes-agent/ui-tui/src/mercuryAvatar.ts"

ppm = subprocess.run(
    ["magick", SRC, "-background", f"rgb({BG[0]},{BG[1]},{BG[2]})",
     "-alpha", "remove", "-alpha", "off",
     "-resize", f"{PXW}x{PXW}^", "-gravity", "center", "-extent", f"{PXW}x{PXW}",
     "-resize", f"{PXW}x{PXH}!", "ppm:-"],
    check=True, capture_output=True).stdout

assert ppm[:2] == b"P6"
idx = 2; vals = []
while len(vals) < 3:
    while idx < len(ppm) and ppm[idx:idx+1].isspace(): idx += 1
    if ppm[idx:idx+1] == b"#":
        while ppm[idx:idx+1] != b"\n": idx += 1
        continue
    s = idx
    while idx < len(ppm) and not ppm[idx:idx+1].isspace(): idx += 1
    vals.append(int(ppm[s:idx]))
w, h, maxv = vals
idx += 1
px = bytearray(ppm[idx:])

# circular disc mask in pixel space (aspect-correct)
cx = (w - 1) / 2.0; cy = (h - 1) / 2.0; rad = w / 2.0 - 0.5
sy = w / float(h)
for y in range(h):
    for x in range(w):
        dx = x - cx; dy = (y - cy) * sy
        if dx * dx + dy * dy > rad * rad:
            o = (y * w + x) * 3
            px[o], px[o+1], px[o+2] = BG

def rgb(x, y):
    o = (y * w + x) * 3
    return px[o], px[o+1], px[o+2]

ESC = "\x1b"
rows = []
for ry in range(0, h - 1, 2):
    parts = []
    for x in range(w):
        tr, tg, tb = rgb(x, ry)
        br, bgc, bb = rgb(x, ry + 1)
        parts.append(f"{ESC}[38;2;{tr};{tg};{tb};48;2;{br};{bgc};{bb}m\u2580")
    parts.append(f"{ESC}[0m")
    rows.append("".join(parts))

# emit TS module: array of rows + width, JSON-encoded so escapes survive esbuild verbatim
ts = (
    "// AUTO-GENERATED — Mercury avatar, circle-cropped truecolor half-block art.\n"
    "// Regenerate with scripts/gen_avatar_ts.py. Each row is one terminal line\n"
    "// (fg=top pixel, bg=bottom pixel, U+2580). Consumed by <RawAnsi> in branding.tsx.\n"
    f"export const MERCURY_AVATAR_WIDTH = {w}\n"
    f"export const MERCURY_AVATAR_HEIGHT = {len(rows)}\n"
    "export const MERCURY_AVATAR_ROWS: string[] = " + json.dumps(rows, ensure_ascii=False) + "\n"
)
open(OUT_TS, "w", encoding="utf-8").write(ts)
print(f"wrote {OUT_TS}: {w}x{len(rows)} cells, {len(rows)} rows, {sum(len(r) for r in rows)} chars")
