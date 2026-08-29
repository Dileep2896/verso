"""Meta view: everything outside page content that a naive ingestion pipeline
would happily concatenate and hand to a model.

Enumeration only -- this module tags *what* and *where*, never decides severity.
The A5 detector applies policy. Kinds emitted (extra['meta_kind']):

    info / info_custom        /Info dictionary values (standard vs non-standard key)
    xmp / xmp_custom          XMP packet; custom == a non-benign namespace prefix
    outline                   bookmark / outline titles
    annotation                annotation /Contents or /TU (with flag + rect info)
    form_field                AcroForm field /V, /DV, /TU
    javascript                document- or field-level JavaScript
    embedded_file             embedded file streams
    ocg                       optional content group names
    open_action / aa          document open / additional actions
"""

from __future__ import annotations

from typing import Any

import pikepdf
import pymupdf

from ..ingest.loader import Document
from ..models import BBox, TextSpan, SOURCE_META

STANDARD_INFO_KEYS = {
    "/Title", "/Author", "/Subject", "/Keywords", "/Creator",
    "/Producer", "/CreationDate", "/ModDate", "/Trapped",
}

# XMP namespace prefixes that appear in ordinary, benign documents.
BENIGN_XMP_PREFIXES = {
    "dc", "xmp", "xmpmm", "xmprights", "xmptpg", "pdf", "pdfaid", "pdfx",
    "pdfxid", "pdfuaid", "photoshop", "crs", "tiff", "exif", "aux",
    "iptc4xmpcore", "iptc4xmpext", "stevt", "stref", "stdim", "stfnt",
    "stmfs", "stversion", "stjob", "illustrator", "xmpg", "rdf", "x",
}

# Annotation flag bits (PDF 32000-1 table 165).
FLAG_HIDDEN = 1 << 1     # bit 2
FLAG_NOVIEW = 1 << 5     # bit 6


def _text_of(obj) -> str:
    # Every pikepdf.Object exposes read_bytes(), but it only works on streams;
    # calling it on a String/Name raises. So test for an actual stream first.
    try:
        if isinstance(obj, pikepdf.Stream):
            return obj.read_bytes().decode("utf-8", "replace")
        return str(obj)
    except Exception:
        return ""


def _rect_topleft(rect, page_h: float) -> BBox:
    x0, y0, x1, y1 = (float(v) for v in rect)
    return BBox(x0, page_h - y1, x1, page_h - y0)


def build_meta(doc: Document) -> list[TextSpan]:
    spans: list[TextSpan] = []
    pike = doc.pike
    root = pike.Root

    # ---- /Info dictionary -------------------------------------------------- #
    try:
        info = pike.trailer.get("/Info")
        if info is not None:
            for key in info.keys():
                val = _text_of(info[key])
                if not val or key in ("/CreationDate", "/ModDate"):
                    kind = "info"
                else:
                    kind = "info" if key in STANDARD_INFO_KEYS else "info_custom"
                spans.append(TextSpan(
                    text=val, page=0, bbox=None, source=SOURCE_META,
                    extra={"meta_kind": kind, "field": str(key)},
                ))
    except Exception:
        pass

    # ---- XMP metadata ------------------------------------------------------ #
    try:
        meta_stream = root.get("/Metadata")
        if meta_stream is not None:
            xmp = meta_stream.read_bytes().decode("utf-8", "replace")
            prefixes = _xmp_prefixes(xmp)
            custom = sorted(p for p in prefixes if p not in BENIGN_XMP_PREFIXES)
            kind = "xmp_custom" if custom else "xmp"
            spans.append(TextSpan(
                text=xmp[:4000], page=0, bbox=None, source=SOURCE_META,
                extra={"meta_kind": kind, "field": "/Metadata",
                       "custom_prefixes": custom},
            ))
    except Exception:
        pass

    # ---- outlines / bookmarks --------------------------------------------- #
    try:
        for title in _iter_outline_titles(pike):
            spans.append(TextSpan(
                text=title, page=0, bbox=None, source=SOURCE_META,
                extra={"meta_kind": "outline", "field": "/Outlines"},
            ))
    except Exception:
        pass

    # ---- annotations (via PyMuPDF for convenient flags + rect) ------------- #
    try:
        for pno in range(doc.n_pages):
            page = doc.mu[pno]
            page_h = float(page.mediabox.height)
            for annot in page.annots() or []:
                info = annot.info
                content = (info.get("content") or "").strip()
                title = (info.get("title") or "").strip()
                flags = int(getattr(annot, "flags", 0) or 0)
                rect = annot.rect
                bbox = _rect_topleft(
                    [rect.x0, page_h - rect.y1, rect.x1, page_h - rect.y0], page_h
                ) if rect else None
                # PyMuPDF rect is already top-left; wrap directly:
                if rect:
                    bbox = BBox(rect.x0, rect.y0, rect.x1, rect.y1)
                hidden = bool(flags & FLAG_HIDDEN)
                noview = bool(flags & FLAG_NOVIEW)
                subtype = annot.type[1] if annot.type else ""
                payload = content or title
                if payload:
                    spans.append(TextSpan(
                        text=payload, page=pno, bbox=bbox, source=SOURCE_META,
                        extra={"meta_kind": "annotation", "field": subtype,
                               "hidden": hidden, "noview": noview,
                               "flags": flags},
                    ))
    except Exception:
        pass

    # ---- AcroForm fields --------------------------------------------------- #
    try:
        acro = root.get("/AcroForm")
        if acro is not None:
            for field in _iter_form_fields(acro):
                spans.append(field)
    except Exception:
        pass

    # ---- document JavaScript ---------------------------------------------- #
    try:
        spans.extend(_collect_javascript(root))
    except Exception:
        pass

    # ---- embedded files ---------------------------------------------------- #
    try:
        spans.extend(_collect_embedded(root))
    except Exception:
        pass

    # ---- optional content group names ------------------------------------- #
    try:
        ocp = root.get("/OCProperties")
        if ocp is not None:
            for g in ocp.get("/OCGs", []):
                name = _text_of(g.get("/Name")) if hasattr(g, "get") else ""
                if name:
                    spans.append(TextSpan(
                        text=name, page=0, bbox=None, source=SOURCE_META,
                        extra={"meta_kind": "ocg", "field": "/OCG"},
                    ))
    except Exception:
        pass

    # ---- open action / additional actions --------------------------------- #
    try:
        if "/OpenAction" in root:
            oa = root["/OpenAction"]
            stype = str(oa.get("/S")) if hasattr(oa, "get") else ""
            if stype and stype != "/GoTo":
                spans.append(TextSpan(
                    text=f"OpenAction {stype}", page=0, bbox=None, source=SOURCE_META,
                    extra={"meta_kind": "open_action", "field": "/OpenAction",
                           "action": stype},
                ))
    except Exception:
        pass

    return spans


# --------------------------------------------------------------------------- #
def _xmp_prefixes(xmp: str) -> set[str]:
    import re
    return {m.lower() for m in re.findall(r"xmlns:([A-Za-z0-9_]+)\s*=", xmp)}


def _iter_outline_titles(pike) -> list[str]:
    titles: list[str] = []
    try:
        with pike.open_outline() as ol:
            def walk(items):
                for it in items:
                    if it.title:
                        titles.append(str(it.title))
                    walk(it.children)
            walk(ol.root)
    except Exception:
        pass
    return titles


def _iter_form_fields(acro) -> list[TextSpan]:
    out: list[TextSpan] = []
    fields = acro.get("/Fields")
    if fields is None:
        return out

    def walk(f):
        try:
            for sub in ("/V", "/DV", "/TU"):
                if sub in f:
                    val = _text_of(f[sub])
                    if val:
                        out.append(TextSpan(
                            text=val, page=0, bbox=None, source=SOURCE_META,
                            extra={"meta_kind": "form_field", "field": sub},
                        ))
            for kid in f.get("/Kids", []):
                walk(kid)
        except Exception:
            return

    for field in fields:
        walk(field)
    return out


def _collect_javascript(root) -> list[TextSpan]:
    out: list[TextSpan] = []

    def add(js_obj, where):
        js = ""
        try:
            if hasattr(js_obj, "get") and "/JS" in js_obj:
                js = _text_of(js_obj["/JS"])
            else:
                js = _text_of(js_obj)
        except Exception:
            js = ""
        if js:
            out.append(TextSpan(
                text=js, page=0, bbox=None, source=SOURCE_META,
                extra={"meta_kind": "javascript", "field": where},
            ))

    # Names -> JavaScript name tree
    try:
        names = root.get("/Names")
        if names is not None and "/JavaScript" in names:
            arr = names["/JavaScript"].get("/Names", [])
            for i in range(1, len(arr), 2):
                add(arr[i], "/Names/JavaScript")
    except Exception:
        pass

    # OpenAction with JS
    try:
        oa = root.get("/OpenAction")
        if oa is not None and hasattr(oa, "get") and str(oa.get("/S")) == "/JavaScript":
            add(oa, "/OpenAction")
    except Exception:
        pass

    # Document additional actions
    try:
        aa = root.get("/AA")
        if aa is not None:
            for k in aa.keys():
                add(aa[k], f"/AA{k}")
    except Exception:
        pass

    return out


def _collect_embedded(root) -> list[TextSpan]:
    out: list[TextSpan] = []
    try:
        names = root.get("/Names")
        if names is None or "/EmbeddedFiles" not in names:
            return out
        arr = names["/EmbeddedFiles"].get("/Names", [])
        for i in range(0, len(arr) - 1, 2):
            fname = _text_of(arr[i])
            spec = arr[i + 1]
            excerpt = fname
            try:
                ef = spec.get("/EF")
                if ef is not None and "/F" in ef:
                    data = ef["/F"].read_bytes()[:400]
                    excerpt = f"{fname}: " + data.decode("utf-8", "replace")
            except Exception:
                pass
            out.append(TextSpan(
                text=excerpt, page=0, bbox=None, source=SOURCE_META,
                extra={"meta_kind": "embedded_file", "field": fname},
            ))
    except Exception:
        pass
    return out
