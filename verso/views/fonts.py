"""Font decoding and glyph metrics for the content-stream interpreter.

The interpreter needs two things per font: how to turn raw string bytes into
Unicode (the "parser's view" of the text, and the source of the /ToUnicode
signal that A7 keys off), and how wide each glyph is (to build a bounding box).

Kept deliberately small and dependency-light. PyMuPDF supplies metrics for the
standard-14 fonts so we do not have to embed AFM tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pymupdf

# BaseFont (minus any "ABCDEF+" subset tag) -> PyMuPDF builtin metric name.
_STD14 = {
    "Helvetica": "helv", "Helvetica-Bold": "hebo", "Helvetica-Oblique": "heit",
    "Helvetica-BoldOblique": "hebi",
    "Times-Roman": "tiro", "Times-Bold": "tibo", "Times-Italic": "tiit",
    "Times-BoldItalic": "tibi",
    "Courier": "cour", "Courier-Bold": "cobo", "Courier-Oblique": "coit",
    "Courier-BoldOblique": "cobi",
    "Symbol": "symb", "ZapfDingbats": "zadb", "Arial": "helv",
    "Arial-Bold": "hebo", "ArialMT": "helv",
}

_SUBSET_RE = re.compile(r"^[A-Z]{6}\+")
_HEX_RE = re.compile(rb"<([0-9A-Fa-f\s]*)>")


def _strip_subset(name: str) -> str:
    return _SUBSET_RE.sub("", name)


def _utf16be_hex_to_str(h: str) -> str:
    h = h.strip()
    if not h:
        return ""
    if len(h) % 2:
        h += "0"
    try:
        return bytes.fromhex(h).decode("utf-16-be", errors="replace")
    except Exception:
        return ""


def _parse_tounicode(stream_bytes: bytes) -> dict[int, str]:
    """Parse a /ToUnicode CMap: bfchar and bfrange entries -> {code: unicode}."""
    text = stream_bytes
    mapping: dict[int, str] = {}

    # bfchar blocks: <src> <dst>
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", text, re.S):
        toks = _HEX_RE.findall(block)
        for i in range(0, len(toks) - 1, 2):
            src = toks[i].replace(b" ", b"").replace(b"\n", b"")
            dst = toks[i + 1].replace(b" ", b"").replace(b"\n", b"")
            try:
                code = int(src, 16)
            except ValueError:
                continue
            mapping[code] = _utf16be_hex_to_str(dst.decode("ascii", "ignore"))

    # bfrange blocks: <lo> <hi> <dst>  (array form is rarer; handled loosely)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", text, re.S):
        # Split into logical entries on '>' boundaries is messy; use a scanner.
        toks = _HEX_RE.findall(block)
        i = 0
        while i + 2 < len(toks) + 1 and i + 2 <= len(toks):
            try:
                lo = int(toks[i].replace(b" ", b""), 16)
                hi = int(toks[i + 1].replace(b" ", b""), 16)
            except (ValueError, IndexError):
                break
            dst_hex = toks[i + 2].replace(b" ", b"").decode("ascii", "ignore")
            base = _utf16be_hex_to_str(dst_hex)
            if base and len(base) == 1:
                start = ord(base)
                for k, code in enumerate(range(lo, hi + 1)):
                    mapping[code] = chr(start + k)
            else:
                for code in range(lo, hi + 1):
                    mapping[code] = base
            i += 3
    return mapping


@dataclass
class FontDecoder:
    two_byte: bool
    tounicode: Optional[dict[int, str]]
    widths: Optional[dict[int, float]]      # code -> width in 1000-unit glyph space
    default_width: float
    metric_name: Optional[str]              # PyMuPDF builtin, for standard-14
    simple_winansi: bool                    # decode single bytes via cp1252

    # ------------------------------------------------------------------ #
    def codes(self, raw: bytes) -> list[int]:
        if self.two_byte:
            return [
                (raw[i] << 8) | raw[i + 1]
                for i in range(0, len(raw) - 1, 2)
            ]
        return list(raw)

    def decode(self, raw: bytes) -> str:
        if self.tounicode:
            out = []
            for code in self.codes(raw):
                out.append(self.tounicode.get(code, ""))
            s = "".join(out)
            if s:
                return s
        if not self.two_byte and self.simple_winansi:
            try:
                return raw.decode("cp1252", errors="replace")
            except Exception:
                return raw.decode("latin-1", errors="replace")
        if not self.two_byte:
            return raw.decode("latin-1", errors="replace")
        # 2-byte without ToUnicode: nothing reliable to show.
        return "".join(chr(c) if 32 <= c < 0x300 else "�" for c in self.codes(raw))

    def string_width_pts(self, raw: bytes, decoded: str, fontsize: float) -> float:
        """Total glyph advance (no spacing) in points at ``fontsize``."""
        if self.widths is not None:
            total = 0.0
            for code in self.codes(raw):
                total += self.widths.get(code, self.default_width)
            return total / 1000.0 * fontsize
        if self.metric_name is not None and decoded:
            try:
                return pymupdf.get_text_length(
                    decoded, fontname=self.metric_name, fontsize=fontsize
                )
            except Exception:
                pass
        # Fallback: average width.
        n = len(self.codes(raw))
        return n * 0.5 * fontsize


def build_decoder(font_obj) -> FontDecoder:
    """Build a FontDecoder from a pikepdf font dictionary (best effort)."""
    subtype = str(font_obj.get("/Subtype", ""))
    two_byte = subtype == "/Type0"

    # ToUnicode
    tou: Optional[dict[int, str]] = None
    if "/ToUnicode" in font_obj:
        try:
            tou = _parse_tounicode(bytes(font_obj["/ToUnicode"].read_bytes()))
            if not tou:
                tou = None
        except Exception:
            tou = None

    # Widths (simple fonts)
    widths: Optional[dict[int, float]] = None
    default_width = 500.0
    metric_name: Optional[str] = None
    simple_winansi = False

    if not two_byte:
        if "/Widths" in font_obj and "/FirstChar" in font_obj:
            try:
                first = int(font_obj["/FirstChar"])
                arr = [float(w) for w in font_obj["/Widths"]]
                widths = {first + i: w for i, w in enumerate(arr)}
                if "/MissingWidth" in font_obj.get("/FontDescriptor", {}):
                    default_width = float(font_obj["/FontDescriptor"]["/MissingWidth"])
            except Exception:
                widths = None
        base = _strip_subset(str(font_obj.get("/BaseFont", "")).lstrip("/"))
        metric_name = _STD14.get(base)
        enc = font_obj.get("/Encoding")
        enc_name = str(enc) if enc is not None and not hasattr(enc, "keys") else ""
        simple_winansi = ("WinAnsi" in enc_name) or enc is None or hasattr(enc, "keys") \
            or "Standard" in enc_name or "MacRoman" in enc_name
    else:
        # Type0: try /W array on the descendant font for CID widths.
        try:
            desc = font_obj["/DescendantFonts"][0]
            if "/DW" in desc:
                default_width = float(desc["/DW"])
            if "/W" in desc:
                widths = _parse_cid_widths(desc["/W"])
        except Exception:
            pass

    return FontDecoder(
        two_byte=two_byte,
        tounicode=tou,
        widths=widths,
        default_width=default_width,
        metric_name=metric_name,
        simple_winansi=simple_winansi,
    )


def _parse_cid_widths(w_array) -> dict[int, float]:
    """Parse a Type0 /W array: [ c [w1 w2 ...]  cfirst clast w  ... ]."""
    widths: dict[int, float] = {}
    items = list(w_array)
    i = 0
    while i < len(items):
        try:
            c = int(items[i])
        except Exception:
            break
        if i + 1 < len(items) and hasattr(items[i + 1], "__iter__") \
                and not isinstance(items[i + 1], (int, float)):
            arr = list(items[i + 1])
            for k, wv in enumerate(arr):
                widths[c + k] = float(wv)
            i += 2
        elif i + 2 < len(items):
            cl = int(items[i + 1])
            wv = float(items[i + 2])
            for code in range(c, cl + 1):
                widths[code] = wv
            i += 3
        else:
            break
    return widths


# A neutral fallback decoder for when a font resource cannot be resolved.
FALLBACK_DECODER = FontDecoder(
    two_byte=False, tounicode=None, widths=None, default_width=500.0,
    metric_name="helv", simple_winansi=True,
)
