# pdf_service.py
"""
Generare PDF pentru KenoLib (folosește reportlab):
- export_inventory_pdf : lista de inventar, ca tabel printabil oficial;
- export_report_pdf    : raportul (statistici + cărți/categorie + top);
- generate_labels_pdf  : etichete de raft cu cod de bare (Code128) pentru
  propriile cărți -- închide bucla scanner-ului GM65 (scanezi la intrare,
  printezi etichete pentru catalog).

Diacriticele românești (ș, ț, ă, â, î) nu sunt în encodarea implicită a
fonturilor built-in reportlab (Helvetica/WinAnsi), așa că se înregistrează
Arial din fonturile Windows; dacă lipsește (alt sistem), se cade elegant
înapoi pe Helvetica.
"""

import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)
from reportlab.graphics.barcode import code128

# Accentul de brand KenoLib (același albastru ca în interfață).
BRAND = colors.HexColor("#2e6fb0")
BRAND_LIGHT = colors.HexColor("#e6f1fb")

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def _register_fonts():
    """Înregistrează Arial (Windows) pentru suport corect al diacriticelor
    românești. Fără efect dacă fonturile lipsesc -- rămâne Helvetica."""
    global FONT, FONT_BOLD
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    try:
        pdfmetrics.registerFont(TTFont("KLSans", os.path.join(fonts_dir, "arial.ttf")))
        pdfmetrics.registerFont(TTFont("KLSans-Bold", os.path.join(fonts_dir, "arialbd.ttf")))
        FONT, FONT_BOLD = "KLSans", "KLSans-Bold"
    except Exception:
        pass


_register_fonts()


def _footer(canvas_obj, doc):
    """Subsol comun: data generării + numărul paginii."""
    canvas_obj.saveState()
    canvas_obj.setFont(FONT, 8)
    canvas_obj.setFillColor(colors.grey)
    today = date.today().strftime("%d.%m.%Y")
    canvas_obj.drawString(15 * mm, 10 * mm, f"KenoLib · generat {today}")
    canvas_obj.drawRightString(
        doc.pagesize[0] - 15 * mm, 10 * mm, f"Pagina {doc.page}"
    )
    canvas_obj.restoreState()


def _title_style():
    return ParagraphStyle(
        "KLTitle", fontName=FONT_BOLD, fontSize=16, textColor=BRAND,
        spaceAfter=4,
    )


def _subtitle_style():
    return ParagraphStyle(
        "KLSub", fontName=FONT, fontSize=9, textColor=colors.grey, spaceAfter=10,
    )


# ---------------------------------------------------------------------------
# Export inventar
# ---------------------------------------------------------------------------
INVENTORY_HEADERS = ["Nr.", "ISBN", "Titlu", "Autor", "An", "Editură",
                     "Preț", "Ex.", "CZU", "Categorie"]
# Lățimi relative pe pagină A4 landscape (aprox. 270mm utilizabili).
INVENTORY_WIDTHS = [10, 26, 62, 42, 12, 34, 16, 10, 22, 36]


def export_inventory_pdf(path, rows, title="Inventar bibliotecă", summary_text=""):
    """Scrie un PDF cu lista de inventar. `rows` = dict-uri de carte (ca cele
    din Database.get_inventory)."""
    doc = SimpleDocTemplate(
        path, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title=title,
    )
    cell = ParagraphStyle("cell", fontName=FONT, fontSize=8, leading=10)
    story = [Paragraph(title, _title_style())]
    if summary_text:
        story.append(Paragraph(summary_text, _subtitle_style()))
    else:
        story.append(Spacer(1, 6))

    data = [INVENTORY_HEADERS]
    for i, book in enumerate(rows, start=1):
        price = book.get("price")
        data.append([
            str(i),
            book.get("isbn") or "",
            Paragraph(book.get("title") or "", cell),
            Paragraph(book.get("author") or "", cell),
            str(book.get("pub_year") or ""),
            Paragraph(book.get("publisher") or "", cell),
            f"{price:.2f}" if price is not None else "",
            str(book.get("copies") or 1),
            book.get("czu") or "",
            Paragraph(book.get("category_name") or "-", cell),
        ])

    usable = landscape(A4)[0] - 24 * mm
    scale = usable / sum(INVENTORY_WIDTHS)
    col_widths = [w * scale for w in INVENTORY_WIDTHS]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("ALIGN", (6, 0), (7, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


# ---------------------------------------------------------------------------
# Export raport
# ---------------------------------------------------------------------------
def export_report_pdf(path, stats, categories, top_books):
    """Raport printabil: carduri de statistici, cărți/împrumuturi pe
    categorie și clasamentul celor mai împrumutate cărți."""
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Raport bibliotecă",
    )
    h2 = ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=12, textColor=BRAND,
                        spaceBefore=12, spaceAfter=6)
    cell = ParagraphStyle("cell", fontName=FONT, fontSize=9, leading=11)
    story = [Paragraph("Raport bibliotecă", _title_style()),
             Paragraph(date.today().strftime("Generat la %d.%m.%Y"), _subtitle_style())]

    # Statistici sumare.
    stat_data = [[
        Paragraph("Total împrumuturi", cell),
        Paragraph("Împrumuturi active", cell),
        Paragraph("Restanțe", cell),
    ], [
        Paragraph(f"<b>{stats.get('total_loans', 0)}</b>", cell),
        Paragraph(f"<b>{stats.get('borrowed_count', 0)}</b>", cell),
        Paragraph(f"<b>{stats.get('overdue_count', 0)}</b>", cell),
    ]]
    usable = A4[0] - 32 * mm
    stat_table = Table(stat_data, colWidths=[usable / 3] * 3)
    stat_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("FONTSIZE", (0, 1), (-1, 1), 18),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
    ]))
    story.append(stat_table)

    # Cărți / împrumuturi pe categorie.
    story.append(Paragraph("Cărți pe categorie", h2))
    cat_data = [["Categorie", "Cărți", "Împrumuturi"]]
    for c in categories:
        cat_data.append([
            Paragraph(c.get("category_name") or "-", cell),
            str(c.get("book_count", 0)),
            str(c.get("loan_count", 0)),
        ])
    cat_table = Table(cat_data, colWidths=[usable * 0.6, usable * 0.2, usable * 0.2], repeatRows=1)
    cat_table.setStyle(_simple_table_style())
    story.append(cat_table)

    # Top cărți împrumutate.
    story.append(Paragraph("Cele mai împrumutate cărți", h2))
    if top_books:
        top_data = [["#", "Titlu", "Autor", "Împrumuturi"]]
        for i, b in enumerate(top_books, start=1):
            top_data.append([
                str(i),
                Paragraph(b.get("title") or "", cell),
                Paragraph(b.get("author") or "", cell),
                str(b.get("loan_count", 0)),
            ])
        top_table = Table(
            top_data, colWidths=[usable * 0.08, usable * 0.5, usable * 0.28, usable * 0.14],
            repeatRows=1,
        )
        top_table.setStyle(_simple_table_style())
        story.append(top_table)
    else:
        story.append(Paragraph("Nicio carte împrumutată încă.", cell))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def _simple_table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])


# ---------------------------------------------------------------------------
# Etichete de raft cu cod de bare
# ---------------------------------------------------------------------------
# Grilă de 3 coloane x 8 rânduri pe A4 portret = 24 etichete/pagină.
LABELS_COLS = 3
LABELS_ROWS = 8


def _barcode_value(book):
    """Valoarea codificată: ISBN-ul dacă există, altfel un cod intern stabil
    bazat pe id (ex. KL000042), ca fiecare carte să aibă un cod scanabil."""
    isbn = (book.get("isbn") or "").replace("-", "").replace(" ", "")
    if isbn:
        return isbn
    return f"KL{int(book['id']):06d}"


def generate_labels_pdf(path, books):
    """Etichete de raft: titlu, autor, CZU și un cod de bare Code128 scanabil,
    dispuse într-o grilă pe pagini A4."""
    page_w, page_h = A4
    margin_x, margin_y = 10 * mm, 12 * mm
    gutter = 4 * mm
    label_w = (page_w - 2 * margin_x - (LABELS_COLS - 1) * gutter) / LABELS_COLS
    label_h = (page_h - 2 * margin_y - (LABELS_ROWS - 1) * gutter) / LABELS_ROWS

    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle("Etichete KenoLib")
    per_page = LABELS_COLS * LABELS_ROWS

    for index, book in enumerate(books):
        slot = index % per_page
        if index > 0 and slot == 0:
            c.showPage()
        col = slot % LABELS_COLS
        row = slot // LABELS_COLS
        x = margin_x + col * (label_w + gutter)
        # rândurile se umplu de sus în jos
        y = page_h - margin_y - (row + 1) * label_h - row * gutter
        _draw_label(c, x, y, label_w, label_h, book)

    c.showPage()
    c.save()


def _draw_label(c, x, y, w, h, book):
    pad = 3 * mm
    max_text_w = w - 2 * pad
    # chenar subtil
    c.setStrokeColor(colors.HexColor("#bbbbbb"))
    c.setLineWidth(0.5)
    c.roundRect(x, y, w, h, 2 * mm, stroke=1, fill=0)

    # Text stivuit de sus în jos: titlu, autor, CZU.
    cursor_y = y + h - pad - 7
    c.setFillColor(colors.HexColor("#1a1a1a"))
    c.setFont(FONT_BOLD, 9)
    c.drawString(x + pad, cursor_y, _fit_text(c, book.get("title") or "", FONT_BOLD, 9, max_text_w))

    cursor_y -= 11
    c.setFont(FONT, 7.5)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(x + pad, cursor_y, _fit_text(c, book.get("author") or "", FONT, 7.5, max_text_w))

    czu = book.get("czu") or ""
    if czu:
        cursor_y -= 10
        c.setFont(FONT_BOLD, 7.5)
        c.setFillColor(BRAND)
        c.drawString(x + pad, cursor_y, _fit_text(c, f"CZU {czu}", FONT_BOLD, 7.5, max_text_w))

    # Cod de bare centrat, jos -- NEGRU (barele colorate scanează prost) --
    # cu valoarea lizibilă sub el.
    value = _barcode_value(book)
    barcode = code128.Code128(value, barHeight=7 * mm, barWidth=0.32 * mm)
    if barcode.width > max_text_w:
        barcode = code128.Code128(
            value, barHeight=7 * mm, barWidth=0.32 * mm * (max_text_w / barcode.width)
        )
    bx = x + (w - barcode.width) / 2
    by = y + pad + 6
    c.setFillColor(colors.black)
    barcode.drawOn(c, bx, by)
    c.setFont(FONT, 6)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawCentredString(x + w / 2, y + pad - 1, value)


def _fit_text(c, text, font_name, font_size, max_width):
    """Taie textul cu … dacă depășește lățimea disponibilă a etichetei."""
    if c.stringWidth(text, font_name, font_size) <= max_width:
        return text
    ellipsis = "…"
    while text and c.stringWidth(text + ellipsis, font_name, font_size) > max_width:
        text = text[:-1]
    return text + ellipsis
