"""A small, deterministic PDF content-stream interpreter.

It tracks the graphics state (CTM, fill colour, fill alpha) and the text state
(font, size, matrices, render mode) well enough to answer the questions the
structural detectors ask:

* where is each run of text on the page, in points (A2 needs off-canvas text
  that PyMuPDF silently clips away);
* was it drawn invisibly -- render mode 3/7, alpha 0, or a background colour (A1);
* what is its effective on-page size after the text and page matrices (A4);
* in what order were text and opaque fills/images painted (A3).

This is not a renderer. Bézier curves are bounded by their control points and
clipping is ignored; both are fine for presence/'where' questions. No text is
ever shown to a model here -- it is pure arithmetic over operators.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace as _dc_replace
from typing import Optional

import pikepdf

from ..models import BBox, PaintOp, TextSpan, SOURCE_STREAM
from .fonts import FALLBACK_DECODER, FontDecoder, build_decoder

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
MAX_FORM_DEPTH = 8


def mat_mul(m: Matrix, n: Matrix) -> Matrix:
    a = m[0] * n[0] + m[1] * n[2]
    b = m[0] * n[1] + m[1] * n[3]
    c = m[2] * n[0] + m[3] * n[2]
    d = m[2] * n[1] + m[3] * n[3]
    e = m[4] * n[0] + m[5] * n[2] + n[4]
    f = m[4] * n[1] + m[5] * n[3] + n[5]
    return (a, b, c, d, e, f)


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _num(o) -> float:
    try:
        return float(o)
    except Exception:
        return 0.0


def _cmyk_to_rgb(c, m, y, k) -> tuple[float, float, float]:
    return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))


@dataclass
class GState:
    ctm: Matrix = IDENTITY
    fill_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fill_alpha: float = 1.0
    fill_cs_ncomp: int = 1
    # text state
    font: Optional[FontDecoder] = None
    font_size: float = 0.0
    char_spacing: float = 0.0
    word_spacing: float = 0.0
    h_scale: float = 1.0
    leading: float = 0.0
    rise: float = 0.0
    render_mode: int = 0

    def copy(self) -> "GState":
        return _dc_replace(self)


@dataclass
class _Ctx:
    """Per-content-stream mutable context."""

    resources: object
    page_h: float
    page_index: int
    spans: list[TextSpan] = field(default_factory=list)
    paints: list[PaintOp] = field(default_factory=list)


class Interpreter:
    def __init__(self, page, page_index: int, page_top: float, page_x0: float = 0.0):
        # page_top is the PDF-space y of the mediabox top edge; page_x0 its left
        # edge. Converting a device point (X, Y) to top-left is
        #   (X - page_x0, page_top - Y).  For the common [0,0,w,h] box that is
        # (X, h - Y).
        self.page = page
        self.page_index = page_index
        self.page_h = page_top
        self.page_x0 = page_x0
        self._pi = 0
        self._font_cache: dict[int, FontDecoder] = {}
        self.spans: list[TextSpan] = []
        self.paints: list[PaintOp] = []

    # -- public ------------------------------------------------------------- #
    def run(self) -> tuple[list[TextSpan], list[PaintOp]]:
        resources = self.page.get("/Resources", pikepdf.Dictionary())
        try:
            instrs = pikepdf.parse_content_stream(self.page)
        except Exception:
            return [], []
        self._exec(instrs, GState(), resources, depth=0)
        return self.spans, self.paints

    # -- font resolution ---------------------------------------------------- #
    def _resolve_font(self, resources, name: str) -> FontDecoder:
        try:
            fonts = resources.get("/Font")
            if fonts is None:
                return FALLBACK_DECODER
            font_obj = fonts.get(name)
            if font_obj is None:
                return FALLBACK_DECODER
            key = id(font_obj)
            try:
                objgen = font_obj.objgen
                key = objgen if objgen != (0, 0) else id(font_obj)
            except Exception:
                pass
            cached = self._font_cache.get(key)
            if cached is None:
                cached = build_decoder(font_obj)
                self._font_cache[key] = cached
            return cached
        except Exception:
            return FALLBACK_DECODER

    # -- ext gstate (alpha) ------------------------------------------------- #
    def _apply_extgstate(self, resources, name: str, gs: GState) -> None:
        try:
            egs = resources.get("/ExtGState")
            if egs is None:
                return
            g = egs.get(name)
            if g is None:
                return
            if "/ca" in g:
                gs.fill_alpha = _num(g["/ca"])
        except Exception:
            pass

    # -- main loop ---------------------------------------------------------- #
    def _exec(self, instrs, gs: GState, resources, depth: int) -> None:
        stack: list[GState] = []
        tm: Matrix = IDENTITY
        tlm: Matrix = IDENTITY
        path_pts: list[tuple[float, float]] = []

        def tl_space_to_dev() -> Matrix:
            return mat_mul(tm, gs.ctm)

        for ins in instrs:
            op = str(ins.operator)
            ops = ins.operands
            try:
                if op == "q":
                    stack.append(gs.copy())
                elif op == "Q":
                    if stack:
                        gs = stack.pop()
                elif op == "cm":
                    m = tuple(_num(o) for o in ops[:6])  # type: ignore
                    gs.ctm = mat_mul(m, gs.ctm)  # type: ignore
                elif op == "gs":
                    self._apply_extgstate(resources, str(ops[0]), gs)

                # ---- colour ----
                elif op == "g":
                    v = _num(ops[0]); gs.fill_rgb = (v, v, v); gs.fill_cs_ncomp = 1
                elif op == "rg":
                    gs.fill_rgb = tuple(_num(o) for o in ops[:3])  # type: ignore
                    gs.fill_cs_ncomp = 3
                elif op == "k":
                    c, m, y, k = (_num(o) for o in ops[:4])
                    gs.fill_rgb = _cmyk_to_rgb(c, m, y, k); gs.fill_cs_ncomp = 4
                elif op == "cs":
                    gs.fill_cs_ncomp = self._cs_ncomp(resources, str(ops[0]))
                elif op in ("sc", "scn"):
                    nums = [o for o in ops if _is_num(o)]
                    if len(nums) == 1:
                        v = _num(nums[0]); gs.fill_rgb = (v, v, v)
                    elif len(nums) == 3:
                        gs.fill_rgb = tuple(_num(o) for o in nums)  # type: ignore
                    elif len(nums) == 4:
                        gs.fill_rgb = _cmyk_to_rgb(*[_num(o) for o in nums])
                    # pattern (name operand, no numbers): leave colour as-is

                # ---- text state ----
                elif op == "BT":
                    tm = tlm = IDENTITY
                elif op == "ET":
                    pass
                elif op == "Tc":
                    gs.char_spacing = _num(ops[0])
                elif op == "Tw":
                    gs.word_spacing = _num(ops[0])
                elif op == "Tz":
                    gs.h_scale = _num(ops[0]) / 100.0
                elif op == "TL":
                    gs.leading = _num(ops[0])
                elif op == "Ts":
                    gs.rise = _num(ops[0])
                elif op == "Tr":
                    gs.render_mode = int(_num(ops[0]))
                elif op == "Tf":
                    gs.font = self._resolve_font(resources, str(ops[0]))
                    gs.font_size = _num(ops[1])
                elif op == "Td":
                    tx, ty = _num(ops[0]), _num(ops[1])
                    tlm = mat_mul((1, 0, 0, 1, tx, ty), tlm); tm = tlm
                elif op == "TD":
                    tx, ty = _num(ops[0]), _num(ops[1])
                    gs.leading = -ty
                    tlm = mat_mul((1, 0, 0, 1, tx, ty), tlm); tm = tlm
                elif op == "Tm":
                    tm = tlm = tuple(_num(o) for o in ops[:6])  # type: ignore
                elif op == "T*":
                    tlm = mat_mul((1, 0, 0, 1, 0, -gs.leading), tlm); tm = tlm
                elif op == "Tj":
                    tm = self._show(bytes(ops[0]), gs, tm)
                elif op == "'":
                    tlm = mat_mul((1, 0, 0, 1, 0, -gs.leading), tlm); tm = tlm
                    tm = self._show(bytes(ops[0]), gs, tm)
                elif op == '"':
                    gs.word_spacing = _num(ops[0]); gs.char_spacing = _num(ops[1])
                    tlm = mat_mul((1, 0, 0, 1, 0, -gs.leading), tlm); tm = tlm
                    tm = self._show(bytes(ops[2]), gs, tm)
                elif op == "TJ":
                    tm = self._show_array(ops[0], gs, tm)

                # ---- path construction ----
                elif op == "m" or op == "l":
                    path_pts.append(apply(gs.ctm, _num(ops[0]), _num(ops[1])))
                elif op in ("c", "v", "y"):
                    coords = [_num(o) for o in ops]
                    for i in range(0, len(coords) - 1, 2):
                        path_pts.append(apply(gs.ctm, coords[i], coords[i + 1]))
                elif op == "re":
                    x, y, w, h = (_num(o) for o in ops[:4])
                    for cx, cy in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                        path_pts.append(apply(gs.ctm, cx, cy))

                # ---- path painting ----
                elif op in ("f", "F", "f*", "B", "B*", "b", "b*"):
                    self._emit_fill(path_pts, gs)
                    path_pts = []
                elif op in ("S", "s", "n"):
                    path_pts = []

                # ---- XObjects ----
                elif op == "Do":
                    self._do_xobject(resources, str(ops[0]), gs, depth)

            except Exception:
                # A single malformed operator must not sink the scan.
                continue

    # -- colour space arity ------------------------------------------------- #
    def _cs_ncomp(self, resources, name: str) -> int:
        base = name.lstrip("/")
        if base in ("DeviceGray", "CalGray", "G"):
            return 1
        if base in ("DeviceRGB", "CalRGB", "RGB", "Lab"):
            return 3
        if base in ("DeviceCMYK", "CMYK"):
            return 4
        return 3

    # -- text emission ------------------------------------------------------ #
    def _show_array(self, arr, gs: GState, tm: Matrix) -> Matrix:
        try:
            elements = list(arr)
        except Exception:
            return tm
        for el in elements:
            if _is_num(el):
                adj = -_num(el) / 1000.0 * gs.font_size * gs.h_scale
                tm = mat_mul((1, 0, 0, 1, adj, 0), tm)
            else:
                tm = self._show(bytes(el), gs, tm)
        return tm

    def _show(self, raw: bytes, gs: GState, tm: Matrix) -> Matrix:
        dec = gs.font or FALLBACK_DECODER
        fs = gs.font_size
        if fs == 0.0:
            fs = 1.0
        decoded = dec.decode(raw)
        glyph_w = dec.string_width_pts(raw, decoded, fs)
        ncodes = len(dec.codes(raw))
        nspace = raw.count(b" ") if not dec.two_byte else 0
        adv = (glyph_w + gs.char_spacing * ncodes + gs.word_spacing * nspace) * gs.h_scale

        asc, desc = 0.75 * fs, 0.25 * fs
        M = mat_mul(tm, gs.ctm)
        corners = [
            (0.0, gs.rise - desc), (adv, gs.rise - desc),
            (adv, gs.rise + asc), (0.0, gs.rise + asc),
        ]
        dev = [apply(M, x, y) for x, y in corners]
        xs = [p[0] - self.page_x0 for p in dev]
        ys = [p[1] for p in dev]
        x0, x1 = min(xs), max(xs)
        ylo, yhi = min(ys), max(ys)
        bbox = BBox(x0, self.page_h - yhi, x1, self.page_h - ylo)
        eff = fs * math.hypot(M[2], M[3])  # device height of one em

        if decoded.strip():
            self.spans.append(
                TextSpan(
                    text=decoded,
                    page=self.page_index,
                    bbox=bbox,
                    source=SOURCE_STREAM,
                    extra={
                        "render_mode": gs.render_mode,
                        "effective_size": round(eff, 3),
                        "nominal_size": round(fs, 3),
                        "fill_rgb": tuple(round(c, 4) for c in gs.fill_rgb),
                        "fill_alpha": round(gs.fill_alpha, 4),
                        "paint_index": self._pi,
                    },
                )
            )
            self._pi += 1
        # advance text matrix
        return mat_mul((1, 0, 0, 1, adv, 0), tm)

    def _emit_fill(self, path_pts, gs: GState) -> None:
        if not path_pts:
            return
        xs = [p[0] - self.page_x0 for p in path_pts]
        ys = [p[1] for p in path_pts]
        bbox = BBox(min(xs), self.page_h - max(ys), max(xs), self.page_h - min(ys))
        if bbox.area <= 0:
            return
        self.paints.append(
            PaintOp(
                kind="fill",
                page=self.page_index,
                bbox=bbox,
                paint_index=self._pi,
                opacity=round(gs.fill_alpha, 4),
                detail={"fill_rgb": tuple(round(c, 4) for c in gs.fill_rgb)},
            )
        )
        self._pi += 1

    def _do_xobject(self, resources, name: str, gs: GState, depth: int) -> None:
        try:
            xobjs = resources.get("/XObject")
            if xobjs is None:
                return
            xobj = xobjs.get(name)
            if xobj is None:
                return
            subtype = str(xobj.get("/Subtype", ""))
            if subtype == "/Image":
                # image drawn in the unit square under the CTM
                corners = [apply(gs.ctm, x, y) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
                xs = [p[0] - self.page_x0 for p in corners]; ys = [p[1] for p in corners]
                bbox = BBox(min(xs), self.page_h - max(ys), max(xs), self.page_h - min(ys))
                self.paints.append(
                    PaintOp(kind="image", page=self.page_index, bbox=bbox,
                            paint_index=self._pi, opacity=round(gs.fill_alpha, 4),
                            detail={"name": name})
                )
                self._pi += 1
            elif subtype == "/Form" and depth < MAX_FORM_DEPTH:
                fmatrix = xobj.get("/Matrix")
                sub_ctm = gs.ctm
                if fmatrix is not None:
                    m = tuple(_num(v) for v in fmatrix)  # type: ignore
                    sub_ctm = mat_mul(m, gs.ctm)
                sub_res = xobj.get("/Resources", resources)
                sub_gs = gs.copy()
                sub_gs.ctm = sub_ctm
                try:
                    sub_instrs = pikepdf.parse_content_stream(xobj)
                except Exception:
                    return
                self._exec(sub_instrs, sub_gs, sub_res, depth + 1)
        except Exception:
            return


def _is_num(o) -> bool:
    try:
        float(o)
        return not isinstance(o, (pikepdf.String,)) and not hasattr(o, "read_bytes")
    except Exception:
        return False


def interpret_page(page, page_index: int, page_top: float,
                   page_x0: float = 0.0) -> tuple[list[TextSpan], list[PaintOp]]:
    return Interpreter(page, page_index, page_top, page_x0).run()
