"""Findings overlay: render a flagged page and mark what was hidden.

Design follows the annotation-craft consensus (leader lines to the exact
feature, rounded callout balloons, numbered markers consistent with a legend,
one severity colour per finding, restraint) so the image emphasises the finding
and reduces misinterpretation.

Per finding, at its real coordinates:
* readable hidden text -> a rounded "reveal card" that blanks the strip and
  prints the extracted payload in the finding's severity colour ("here is what
  was hidden here");
* text too small to reveal (microtype) -> a numbered marker at the spot;
* text off the page or in metadata -> an arrow at the page edge (off-canvas) or
  a legend-only entry (metadata).
Every marker is numbered and linked by a leader line to a legend entry carrying
the rule id, the full excerpt and the coordinates.

Produced from the same finding data the receipt uses, so the picture can never
drift from what the scanner actually found.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .ingest.raster import points_to_pixels, render_page
from .models import SEV_HIGH, SEV_MEDIUM

# palette -------------------------------------------------------------------- #
INK = (24, 28, 36)
MUTED = (110, 118, 132)
FAINT = (150, 158, 170)
PANEL_BG = (247, 249, 251)
HEADER_BG = (16, 23, 36)
HAIRLINE = (222, 227, 234)
PAPER = (252, 252, 253)
GREEN = (34, 158, 90)
SEV_COLOR = {
    "high": (208, 42, 46),
    "medium": (194, 120, 12),
    "low": (120, 128, 140),
}
LEGEND_W = 430
PAD = 26
HEADER_H = 74
DPI = 200


# fonts ---------------------------------------------------------------------- #
def _font(size: int, bold: bool = False):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def _truncate(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"


def choose_page(scan_result) -> Optional[int]:
    highs = [f for f in scan_result.findings if f.severity == SEV_HIGH and f.bbox]
    located = highs or [f for f in scan_result.findings if f.bbox]
    if located:
        return min(f.page for f in located)
    return 0 if scan_result.findings else None


def _rounded(draw, box, r, fill=None, outline=None, width=1):
    try:
        draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)
    except Exception:
        draw.rectangle(box, fill=fill, outline=outline, width=width)


def render_overlay(scan_result, out_path, page: Optional[int] = None,
                   dpi: int = DPI) -> Path:
    if page is None:
        page = choose_page(scan_result)
    if page is None:
        page = 0

    base = render_page(scan_result.path, page, dpi=dpi).convert("RGB")
    pw, ph = base.size
    W, H = pw + LEGEND_W, ph + HEADER_H

    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    canvas.paste(base, (0, HEADER_H))
    draw = ImageDraw.Draw(canvas, "RGBA")

    f_h1 = _font(27, bold=True); f_h2 = _font(14)
    f_badge = _font(17, bold=True); f_num = _font(17, bold=True)
    f_rule = _font(17, bold=True); f_body = _font(14); f_small = _font(12)

    # ---- header ---------------------------------------------------------- #
    draw.rectangle([0, 0, W, HEADER_H], fill=HEADER_BG)
    draw.text((PAD, 16), "VERSO", font=f_h1, fill=(255, 255, 255))
    draw.text((PAD + 122, 24), "document firewall", font=f_h2, fill=(150, 160, 180))
    quar = scan_result.decision == "quarantined"
    dcolor = SEV_COLOR["high"] if quar else GREEN
    label = " QUARANTINED " if quar else " CLEAN "
    lw = draw.textlength(label, font=f_rule)
    _rounded(draw, [W - lw - PAD - 20, 20, W - PAD, 54], 7, fill=dcolor)
    draw.text((W - lw - PAD - 10, 26), label.strip(), font=f_rule, fill=(255, 255, 255))

    # legend panel background + divider
    draw.rectangle([pw, HEADER_H, W, H], fill=PANEL_BG)
    draw.line([pw, HEADER_H, pw, H], fill=HAIRLINE, width=2)

    # ---- classify findings for this page + the rest ---------------------- #
    page_h_hi = [f for f in scan_result.findings if f.severity == SEV_HIGH]
    all_findings = sorted(scan_result.findings, key=lambda f: f.sort_key())

    def to_px(b):
        return (points_to_pixels(b.x0, dpi), points_to_pixels(b.top, dpi) + HEADER_H,
                points_to_pixels(b.x1, dpi), points_to_pixels(b.bottom, dpi) + HEADER_H)

    def on_page(b):
        if b is None:
            return False
        x0, y0, x1, y1 = to_px(b)
        return x1 > 4 and x0 < pw - 4 and y1 > HEADER_H + 4 and y0 < H - 4

    items = []          # (num, finding, kind, anchor_xy)
    n = 0
    for f in all_findings:
        n += 1
        color = SEV_COLOR.get(f.severity, MUTED)
        if f.bbox is not None and on_page(f.bbox):
            x0, y0, x1, y1 = to_px(f.bbox)
            x0c, x1c = max(0, x0), min(pw, x1)
            y0c, y1c = max(HEADER_H, y0), min(H, y1)
            bh = y1c - y0c
            if bh >= 13 and (x1c - x0c) >= 44:
                _draw_reveal(draw, (x0c, y0c, x1c, y1c), f, color, n, f_num)
                anchor = (min(x1c + 4, pw), (y0c + y1c) / 2)
                items.append((n, f, "reveal", anchor))
            else:
                cx, cy = (x0c + x1c) / 2, (y0c + y1c) / 2
                _draw_marker(draw, cx, cy, color, n, f_num)
                items.append((n, f, "marker", (min(cx + 14, pw), cy)))
        elif f.bbox is not None:
            # off-canvas: arrow at the nearest page edge pointing outward
            anchor = _draw_edge_arrow(draw, f.bbox, color, n, f_num, pw, ph, dpi)
            items.append((n, f, "offcanvas", anchor))
        else:
            items.append((n, f, "meta", None))

    # ---- legend ---------------------------------------------------------- #
    lx = pw + PAD
    max_w = LEGEND_W - 2 * PAD
    ly = HEADER_H + PAD
    draw.text((lx, ly), "Findings", font=f_h1, fill=INK)
    cnt = f"{len(all_findings)}"
    draw.text((lx + draw.textlength("Findings", font=f_h1) + 12, ly + 8),
              cnt, font=f_rule, fill=FAINT)
    ly += 40
    draw.text((lx, ly), Path(scan_result.filename).name, font=f_small, fill=MUTED)
    ly += 18
    draw.text((lx, ly), f"sha256 {scan_result.sha256[:20]}…", font=f_small, fill=MUTED)
    ly += 26

    entry_y = {}
    for num, f, kind, _anchor in items:
        if ly > H - 78:
            draw.text((lx, ly), f"+ {len(items) - num + 1} more finding(s)…",
                      font=f_body, fill=MUTED)
            break
        color = SEV_COLOR.get(f.severity, MUTED)
        entry_y[num] = ly + 11
        _rounded(draw, [lx, ly, lx + 22, ly + 22], 6, fill=color)
        draw.text((lx + (6 if num < 10 else 3), ly + 2), str(num), font=f_num,
                  fill=(255, 255, 255))
        draw.text((lx + 32, ly + 1), f.rule, font=f_rule, fill=INK)
        # severity chip
        sev = f.severity.upper()
        cw = draw.textlength(sev, font=f_small)
        draw.text((lx + max_w - cw, ly + 3), sev, font=f_small, fill=color)
        ly += 26
        excerpt = f.excerpt + ("…" if f.excerpt_truncated else "")
        for line in _wrap(draw, f'“{excerpt}”', f_body, max_w - 32):
            draw.text((lx + 32, ly), line, font=f_body, fill=(60, 66, 78))
            ly += 18
        loc = ("off-canvas" if kind == "offcanvas" else
               "metadata / off-page" if kind == "meta" else
               f"page {f.page + 1}  ·  {f.bbox.as_list() if f.bbox else ''}")
        draw.text((lx + 32, ly), loc, font=f_small, fill=FAINT)
        ly += 30

    # ---- leader lines: marker -> legend entry ---------------------------- #
    for num, f, kind, anchor in items:
        if anchor is None or num not in entry_y:
            continue
        color = SEV_COLOR.get(f.severity, MUTED)
        ax, ay = anchor
        ey = entry_y[num]
        midx = (ax + pw) / 2
        draw.line([(ax, ay), (midx, ay), (midx, ey), (pw + 6, ey)],
                  fill=color + (150,), width=2, joint="curve")
        draw.ellipse([pw + 3, ey - 3, pw + 9, ey + 3], fill=color)

    # ---- footer ---------------------------------------------------------- #
    draw.text((lx, H - 30), "structural detection · deterministic · no model consulted",
              font=f_small, fill=FAINT)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
def _draw_reveal(draw, box, f, color, num, f_num):
    x0, y0, x1, y1 = box
    pad = 3
    rx0, ry0, rx1, ry1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    bw, bh = rx1 - rx0, ry1 - ry0
    # subtle shadow
    _rounded(draw, [rx0 + 2, ry0 + 3, rx1 + 2, ry1 + 3], 6, fill=(16, 23, 34, 40))
    # backing strip + reveal text
    _rounded(draw, [rx0, ry0, rx1, ry1], 6, fill=(252, 252, 253, 246))
    excerpt = (f.excerpt + ("…" if f.excerpt_truncated else "")).strip()
    if excerpt:
        fs = max(11, min(int(bh * 0.74), 30))
        rf = _font(fs)
        txt = _truncate(draw, excerpt, rf, bw - 12)
        draw.text((rx0 + 6, ry0 + max(0, (bh - fs) / 2) - 1), txt, font=rf, fill=color)
    _rounded(draw, [rx0, ry0, rx1, ry1], 6, outline=color, width=3)
    # numbered tab
    tab = 23
    ty = ry0 - tab if ry0 - tab >= HEADER_H else ry0
    _rounded(draw, [rx0, ty, rx0 + tab, ty + tab], 5, fill=color)
    draw.text((rx0 + (7 if num < 10 else 4), ty + 2), str(num), font=f_num,
              fill=(255, 255, 255))


def _draw_marker(draw, cx, cy, color, num, f_num):
    r = 13
    draw.ellipse([cx - r + 1, cy - r + 2, cx + r + 1, cy + r + 2], fill=(16, 23, 34, 45))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(255, 255, 255), width=2)
    draw.text((cx - (5 if num < 10 else 9), cy - 8), str(num), font=f_num, fill=(255, 255, 255))


def _draw_edge_arrow(draw, bbox, color, num, f_num, pw, ph, dpi):
    """Arrow at the nearest page edge pointing toward off-canvas text."""
    cx = points_to_pixels((bbox.x0 + bbox.x1) / 2, dpi)
    cy = points_to_pixels((bbox.top + bbox.bottom) / 2, dpi) + HEADER_H
    # clamp an anchor onto the page edge nearest the off-page centre
    ax = min(max(cx, 20), pw - 20)
    ay = min(max(cy, HEADER_H + 20), HEADER_H + ph - 20)
    # direction outward
    dx = -1 if cx < 0 else (1 if cx > pw else 0)
    dy = -1 if cy < HEADER_H else (1 if cy > HEADER_H + ph else 0)
    tip = (ax + dx * 26, ay + dy * 26)
    draw.line([(ax, ay), tip], fill=color, width=3)
    _draw_marker(draw, ax, ay, color, num, f_num)
    return (ax, ay)
