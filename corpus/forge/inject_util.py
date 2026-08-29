"""Low-level PDF plumbing shared by the generators.

This module is *plumbing only* -- add a font resource, append a content stream,
attach a metadata object. It contains no attack semantics: what makes a payload
invisible, off-canvas, tiny, occluded or hostile-in-metadata lives entirely in
each a*_*.py generator, duplicated on purpose so the corpus never imports a
detector's definition of the thing it is trying to measure.

Geometry here duplicates the detector's top-left/points convention deliberately
(see the taxonomy). If the two ever disagree, IoU on the eval will expose it --
which is the whole reason they are kept apart.
"""

from __future__ import annotations

import pikepdf
import pymupdf
from pikepdf import Dictionary, Name, String

Name_Font = Name("/Font")
Name_ExtGState = Name("/ExtGState")
Name_XObject = Name("/XObject")


# --------------------------------------------------------------------------- #
# geometry (forge-local; NOT imported from verso)
# --------------------------------------------------------------------------- #
def text_bbox_topleft(x: float, baseline_y: float, size: float, text: str,
                      page_top: float, fontname: str = "helv") -> list[float]:
    """Bounding box of a drawn string, top-left origin, in points.

    Matches the ascent/descent fractions the interpreter uses (0.75 / 0.25 em)
    so a correctly placed payload scores ~1.0 IoU against a correct detector.
    """
    width = pymupdf.get_text_length(text, fontname=fontname, fontsize=size)
    asc, desc = 0.75 * size, 0.25 * size
    x0, x1 = x, x + width
    top = page_top - (baseline_y + asc)
    bottom = page_top - (baseline_y - desc)
    return [round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1)]


# --------------------------------------------------------------------------- #
# text escaping
# --------------------------------------------------------------------------- #
def pdf_escape(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    out = bytearray()
    for b in raw:
        ch = bytes([b])
        if ch in (b"(", b")", b"\\"):
            out += b"\\" + ch
        elif b < 32 or b > 126:
            out += b"\\%03o" % b
        else:
            out += ch
    return bytes(out)


# --------------------------------------------------------------------------- #
# resources
# --------------------------------------------------------------------------- #
def add_font(pdf: pikepdf.Pdf, page: pikepdf.Page, name: str = "/FVso") -> str:
    font = pdf.make_indirect(Dictionary(
        Type=Name("/Font"), Subtype=Name("/Type1"),
        BaseFont=Name("/Helvetica"), Encoding=Name("/WinAnsiEncoding"),
    ))
    page.add_resource(font, Name_Font, Name(name), replace_existing=True)
    return name


def add_alpha_gstate(pdf: pikepdf.Pdf, page: pikepdf.Page, alpha: float,
                     name: str = "/GSao") -> str:
    gs = pdf.make_indirect(Dictionary(
        Type=Name("/ExtGState"), ca=alpha, CA=alpha,
    ))
    page.add_resource(gs, Name_ExtGState, Name(name), replace_existing=True)
    return name


def append_content(page: pikepdf.Page, body: bytes) -> None:
    """Append a content fragment, isolated in its own q/Q graphics scope."""
    page.contents_add(b"q\n" + body + b"\nQ\n", prepend=False)


# --------------------------------------------------------------------------- #
# metadata attachment (for A5)
# --------------------------------------------------------------------------- #
def add_document_javascript(pdf: pikepdf.Pdf, js: str, name: str = "VersoJS") -> None:
    action = pdf.make_indirect(Dictionary(
        Type=Name("/Action"), S=Name("/JavaScript"), JS=String(js),
    ))
    names = pdf.Root.get("/Names")
    if names is None:
        names = pdf.make_indirect(Dictionary())
        pdf.Root.Names = names
    js_tree = pdf.make_indirect(Dictionary(Names=pikepdf.Array([String(name), action])))
    names.JavaScript = js_tree


def add_embedded_file(pdf: pikepdf.Pdf, filename: str, data: bytes) -> None:
    stream = pikepdf.Stream(pdf, data)
    stream.Type = Name("/EmbeddedFile")
    ef = pdf.make_indirect(Dictionary(F=stream))
    filespec = pdf.make_indirect(Dictionary(
        Type=Name("/Filespec"), F=String(filename), UF=String(filename), EF=ef,
    ))
    names = pdf.Root.get("/Names")
    if names is None:
        names = pdf.make_indirect(Dictionary())
        pdf.Root.Names = names
    names.EmbeddedFiles = pdf.make_indirect(
        Dictionary(Names=pikepdf.Array([String(filename), filespec]))
    )


def add_custom_info(pdf: pikepdf.Pdf, key: str, value: str) -> None:
    info = pdf.trailer.get("/Info")
    if info is None:
        info = pdf.make_indirect(Dictionary())
        pdf.trailer.Info = info
    info[Name("/" + key.lstrip("/"))] = String(value)


CUSTOM_XMP = """<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/'>
 <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
  <rdf:Description rdf:about=''
    xmlns:agentcmd='https://verso.example/ns/agent-directive/1.0'>
   <agentcmd:instruction>{payload}</agentcmd:instruction>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""


def add_custom_xmp(pdf: pikepdf.Pdf, payload: str) -> None:
    xml = CUSTOM_XMP.format(payload=payload).encode("utf-8")
    stream = pikepdf.Stream(pdf, xml)
    stream.Type = Name("/Metadata")
    stream.Subtype = Name("/XML")
    pdf.Root.Metadata = pdf.make_indirect(stream)


def add_annotation(pdf: pikepdf.Pdf, page: pikepdf.Page, rect: list[float],
                   contents: str, *, hidden: bool = False, noview: bool = False,
                   subtype: str = "/FreeText") -> None:
    """Add a FreeText annotation. rect is [x0,y0,x1,y1] in PDF (bottom-left) space."""
    flags = 0
    if hidden:
        flags |= (1 << 1)     # Hidden
    if noview:
        flags |= (1 << 5)     # NoView
    annot = pdf.make_indirect(Dictionary(
        Type=Name("/Annot"), Subtype=Name(subtype),
        Rect=pikepdf.Array([float(v) for v in rect]),
        Contents=String(contents), F=flags,
        DA=String("/Helv 10 Tf 0 g"),
    ))
    annots = page.obj.get("/Annots")
    if annots is None:
        page.obj.Annots = pikepdf.Array([annot])
    else:
        annots.append(annot)


def add_form_field(pdf: pikepdf.Pdf, page: pikepdf.Page, rect: list[float],
                   name: str, value: str) -> None:
    field = pdf.make_indirect(Dictionary(
        Type=Name("/Annot"), Subtype=Name("/Widget"), FT=Name("/Tx"),
        T=String(name), V=String(value), DV=String(value),
        Rect=pikepdf.Array([float(v) for v in rect]),
        F=4, DA=String("/Helv 10 Tf 0 g"),
    ))
    annots = page.obj.get("/Annots")
    if annots is None:
        page.obj.Annots = pikepdf.Array([field])
    else:
        annots.append(field)
    acro = pdf.Root.get("/AcroForm")
    if acro is None:
        pdf.Root.AcroForm = pdf.make_indirect(
            Dictionary(Fields=pikepdf.Array([field]), NeedAppearances=True))
    else:
        acro.Fields.append(field)


def add_outlines(pdf: pikepdf.Pdf, titles: list[str]) -> None:
    """Build a flat outline (bookmark) tree by hand -- deterministic and simple."""
    page0 = pdf.pages[0].obj
    items = []
    for t in titles:
        item = pdf.make_indirect(Dictionary(
            Title=String(t),
            Dest=pikepdf.Array([page0, Name("/Fit")]),
        ))
        items.append(item)
    for i, item in enumerate(items):
        if i > 0:
            item.Prev = items[i - 1]
        if i < len(items) - 1:
            item.Next = items[i + 1]
    outlines = pdf.make_indirect(Dictionary(
        Type=Name("/Outlines"),
        First=items[0], Last=items[-1], Count=len(items),
    ))
    for item in items:
        item.Parent = outlines
    pdf.Root.Outlines = outlines


# --------------------------------------------------------------------------- #
# save
# --------------------------------------------------------------------------- #
def save_bytes(pdf: pikepdf.Pdf) -> bytes:
    import io
    buf = io.BytesIO()
    pdf.save(buf, deterministic_id=True, compress_streams=True)
    return buf.getvalue()


FIXED_DATE = "D:20260101000000Z"


def normalize(data: bytes) -> bytes:
    """Fix /Info dates and the file /ID so corpus bytes are stable across runs.

    Standard-key /Info values only; any custom keys (an A5 payload) are preserved.
    """
    import io
    pdf = pikepdf.open(io.BytesIO(data))
    info = pdf.trailer.get("/Info")
    if info is None:
        info = pdf.make_indirect(Dictionary())
        pdf.trailer.Info = info
    info[Name("/CreationDate")] = String(FIXED_DATE)
    info[Name("/ModDate")] = String(FIXED_DATE)
    info[Name("/Producer")] = String("Verso Corpus")
    info[Name("/Creator")] = String("Verso Corpus")
    # Drop any existing (random) /ID so the deterministic_id save derives it
    # purely from content -- otherwise the old random ID feeds the hash.
    if "/ID" in pdf.trailer:
        del pdf.trailer["/ID"]
    return save_bytes(pdf)
