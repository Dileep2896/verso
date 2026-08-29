"""Realistic host documents for the corpus.

Not single-paragraph synthetic PDFs -- these have headings, numbered clauses,
tables, headers, footers and page numbers, so the recall numbers do not collapse
the moment a judge drops a real contract on the scanner. Four contract-shaped
hosts (lease, MSA, NDA, invoice) plus clean-control variants (scanned, annotated,
footnotes, watermark, white-on-dark, two-column, table-heavy, bookmarked).

Deterministic: no randomness, and the build step normalizes /Info dates and the
file /ID so bytes are stable across runs.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

PAGE_W, PAGE_H = LETTER


# --------------------------------------------------------------------------- #
# Document text templates (kept terse but structurally realistic).
# --------------------------------------------------------------------------- #
_LOREM = (
    "The parties acknowledge that the obligations set forth herein are material "
    "and that each party has relied upon the representations of the other in "
    "entering into this agreement. No waiver of any provision shall be effective "
    "unless made in writing and signed by an authorized representative."
)

TEMPLATES = {
    "lease": {
        "title": "Residential Lease Agreement",
        "subtitle": "Between Landlord and Tenant",
        "clauses": [
            ("1. Premises", "The Landlord leases to the Tenant the residential premises located at 118 Alder Street, Unit 4B. " + _LOREM),
            ("2. Term", "The term of this Lease shall be twelve (12) months commencing on the first day of the month. " + _LOREM),
            ("3. Rent", "Tenant shall pay monthly rent of $2,400, due on the first day of each calendar month without demand. " + _LOREM),
            ("4. Security Deposit", "Tenant shall deposit $2,400 as security for the faithful performance of the Tenant's obligations. " + _LOREM),
            ("5. Maintenance", "Tenant shall keep the premises in clean and sanitary condition and shall not make alterations. " + _LOREM),
            ("6. Default", "Any failure to pay rent when due shall constitute a default under the terms of this Lease. " + _LOREM),
        ],
        "table": None,
    },
    "msa": {
        "title": "Master Services Agreement",
        "subtitle": "Statement of Work and General Terms",
        "clauses": [
            ("1. Services", "Provider shall perform the services described in each Statement of Work executed by the parties. " + _LOREM),
            ("2. Fees", "Client shall pay the fees set forth below within thirty (30) days of receipt of a valid invoice. " + _LOREM),
            ("3. Term and Termination", "This Agreement remains in effect until terminated by either party upon sixty days notice. " + _LOREM),
            ("4. Confidentiality", "Each party shall protect the Confidential Information of the other with reasonable care. " + _LOREM),
            ("5. Limitation of Liability", "Neither party shall be liable for indirect or consequential damages arising hereunder. " + _LOREM),
            ("6. Governing Law", "This Agreement shall be governed by the laws of the State of Delaware. " + _LOREM),
        ],
        "table": [
            ["Milestone", "Deliverable", "Fee (USD)"],
            ["Kickoff", "Project plan", "10,000"],
            ["Phase 1", "Integration", "45,000"],
            ["Phase 2", "Rollout", "60,000"],
            ["Acceptance", "Final sign-off", "15,000"],
        ],
    },
    "nda": {
        "title": "Mutual Non-Disclosure Agreement",
        "subtitle": "Confidentiality Terms",
        "clauses": [
            ("1. Purpose", "The parties wish to explore a business relationship and may disclose confidential information. " + _LOREM),
            ("2. Definition", "Confidential Information means any non-public information disclosed by one party to the other. " + _LOREM),
            ("3. Obligations", "The Receiving Party shall not disclose Confidential Information to any third party. " + _LOREM),
            ("4. Exclusions", "Confidential Information does not include information that becomes publicly available. " + _LOREM),
            ("5. Term", "The obligations of confidentiality shall survive for a period of three (3) years. " + _LOREM),
            ("6. Remedies", "The parties agree that monetary damages may be inadequate and injunctive relief is appropriate. " + _LOREM),
        ],
        "table": None,
    },
    "invoice": {
        "title": "Invoice",
        "subtitle": "Bill To: Acme Corporation",
        "clauses": [
            ("Invoice Number", "INV-2026-0417. Payment is due within fifteen (15) days of the invoice date. " + _LOREM),
            ("Remittance", "Please remit payment to the account specified in the Master Services Agreement. " + _LOREM),
            ("Notes", "Late payments are subject to a service charge of 1.5% per month on the outstanding balance. " + _LOREM),
        ],
        "table": [
            ["Item", "Description", "Qty", "Unit", "Amount"],
            ["A-100", "Consulting services", "40", "180.00", "7,200.00"],
            ["A-220", "Integration support", "12", "200.00", "2,400.00"],
            ["A-330", "Training session", "2", "1,500.00", "3,000.00"],
            ["", "", "", "Subtotal", "12,600.00"],
            ["", "", "", "Tax (8%)", "1,008.00"],
            ["", "", "", "Total", "13,608.00"],
        ],
    },
}


def _styles():
    ss = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=ss["BodyText"], fontName="Helvetica",
                          fontSize=10, leading=14, spaceAfter=8)
    h = ParagraphStyle("H", parent=ss["Heading2"], fontName="Helvetica-Bold",
                       fontSize=12, leading=15, spaceBefore=10, spaceAfter=4)
    title = ParagraphStyle("Title", parent=ss["Title"], fontName="Helvetica-Bold",
                           fontSize=20, leading=24)
    sub = ParagraphStyle("Sub", parent=ss["Normal"], fontName="Helvetica",
                         fontSize=11, leading=14, textColor=colors.HexColor("#555555"),
                         spaceAfter=14)
    small = ParagraphStyle("Small", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=6, leading=8, textColor=colors.HexColor("#666666"))
    return {"body": body, "h": h, "title": title, "sub": sub, "small": small}


def _header_footer(title: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(inch, PAGE_H - 0.6 * inch, title)
        canvas.drawRightString(PAGE_W - inch, PAGE_H - 0.6 * inch, "CONFIDENTIAL")
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.line(inch, PAGE_H - 0.68 * inch, PAGE_W - inch, PAGE_H - 0.68 * inch)
        canvas.drawCentredString(PAGE_W / 2, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def _story(kind: str, styles, *, footnote: bool = False):
    tpl = TEMPLATES[kind]
    story = [Paragraph(tpl["title"], styles["title"]),
             Paragraph(tpl["subtitle"], styles["sub"])]
    if tpl["table"] and kind == "invoice":
        story.append(_make_table(tpl["table"]))
        story.append(Spacer(1, 12))
    for head, bodytext in tpl["clauses"]:
        story.append(Paragraph(head, styles["h"]))
        story.append(Paragraph(bodytext, styles["body"]))
    if tpl["table"] and kind == "msa":
        story.append(Spacer(1, 10))
        story.append(Paragraph("Fee Schedule", styles["h"]))
        story.append(_make_table(tpl["table"]))
    if footnote:
        story.append(Spacer(1, 16))
        story.append(Paragraph(
            "Footnote: All capitalized terms not defined herein have the meaning "
            "given in the Master Agreement. This 6pt notice is legitimate small "
            "print and must not be flagged as a microtype attack. "
            "Rev. 2026-01. Section 12(a)(iii). Ref. no. 44-Q.", styles["small"]))
    return story


def _make_table(rows):
    t = Table(rows, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a55")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f8")]),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _build(story, title: str, *, two_column: bool = False, bookmarks=None,
           on_page=None) -> bytes:
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=LETTER,
                          leftMargin=inch, rightMargin=inch,
                          topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                          title=title, author="Contracts Dept",
                          subject="Agreement", creator="Verso Corpus")
    if two_column:
        gap = 0.3 * inch
        cw = (PAGE_W - 2 * inch - gap) / 2
        f1 = Frame(inch, 0.9 * inch, cw, PAGE_H - 1.8 * inch, id="c1")
        f2 = Frame(inch + cw + gap, 0.9 * inch, cw, PAGE_H - 1.8 * inch, id="c2")
        frames = [f1, f2]
    else:
        frames = [Frame(inch, 0.9 * inch, PAGE_W - 2 * inch, PAGE_H - 1.8 * inch, id="c")]
    doc.addPageTemplates([PageTemplate(id="main", frames=frames,
                                       onPage=on_page or _header_footer(title))])
    doc.build(list(story))
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Public generators
# --------------------------------------------------------------------------- #
def generate_host(kind: str) -> bytes:
    styles = _styles()
    return _build(_story(kind, styles), TEMPLATES[kind]["title"])


def generate_clean(kind: str) -> bytes:
    """Clean-control variants. ``kind`` selects the tricky-but-legitimate case."""
    styles = _styles()
    if kind == "footnotes":
        return _build(_story("msa", styles, footnote=True), "Master Services Agreement")
    if kind == "two_column":
        return _build(_story("nda", styles), "Mutual Non-Disclosure Agreement",
                      two_column=True)
    if kind == "table_heavy":
        return _build(_story("invoice", styles), "Invoice")
    if kind == "watermark":
        return _watermark_doc(styles)
    if kind == "white_on_dark":
        return _white_on_dark_doc(styles)
    if kind == "scanned":
        return _scanned_doc(styles)
    if kind == "annotated":
        return generate_host("lease")   # annotations added later via pikepdf
    if kind == "bookmarked":
        return generate_host("msa")     # outlines added later via pikepdf
    # plain clean variants reuse the host content
    if kind in TEMPLATES:
        return generate_host(kind)
    raise ValueError(f"unknown clean kind: {kind}")


def _watermark_doc(styles) -> bytes:
    """A translucent 'DRAFT' watermark drawn OVER the text -- the honest A3 trap."""
    def on_page(canvas, doc):
        _header_footer("Master Services Agreement")(canvas, doc)
        canvas.saveState()
        canvas.translate(PAGE_W / 2, PAGE_H / 2)
        canvas.rotate(45)
        canvas.setFillColor(colors.Color(0.6, 0.6, 0.6, alpha=0.15))  # translucent
        canvas.setFont("Helvetica-Bold", 90)
        canvas.drawCentredString(0, 0, "DRAFT")
        canvas.restoreState()
    return _build(_story("msa", styles), "Master Services Agreement", on_page=on_page)


def _white_on_dark_doc(styles) -> bytes:
    """A cover page with genuinely white text on a dark filled banner."""
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#12233f"))          # dark banner
        canvas.rect(0, PAGE_H - 3 * inch, PAGE_W, 3 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.white)                        # white text ON dark
        canvas.setFont("Helvetica-Bold", 28)
        canvas.drawString(inch, PAGE_H - 1.8 * inch, "ANNUAL REPORT 2026")
        canvas.setFont("Helvetica", 13)
        canvas.drawString(inch, PAGE_H - 2.3 * inch,
                          "Prepared for the Board of Directors")
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(PAGE_W / 2, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()
    body = _styles()
    story = [Spacer(1, 2.4 * inch)]
    story += _story("nda", body)[2:]  # skip title/subtitle, banner supplies it
    return _build(story, "Annual Report 2026", on_page=on_page)


def _scanned_doc(styles) -> bytes:
    """A page with NO text layer at all -- an image of text, like a real scan."""
    from reportlab.pdfgen import canvas as rl_canvas
    from PIL import Image, ImageDraw, ImageFont
    # Render text to an image, then place the image as the whole page.
    scale = 2
    img = Image.new("RGB", (int(PAGE_W * scale), int(PAGE_H * scale)), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
        fbig = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
        fbig = font
    d.text((80, 80), "Scanned Agreement", font=fbig, fill="black")
    lines = [
        "This document has been scanned from paper and contains no text layer.",
        "Every glyph on this page exists only as pixels in a raster image.",
        "A reviewer that reads the text layer sees nothing; a human sees this.",
        "Verso must treat a fully image-only page as advisory, not a quarantine.",
    ]
    y = 180
    for ln in lines:
        d.text((80, y), ln, font=font, fill="black")
        y += 44
    ibuf = io.BytesIO()
    img.save(ibuf, format="PNG")
    ibuf.seek(0)

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=LETTER)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(ibuf), 0, 0, width=PAGE_W, height=PAGE_H)
    c.showPage()
    c.save()
    return buf.getvalue()
