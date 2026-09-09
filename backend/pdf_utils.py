"""PDF generation via reportlab (no object storage — returned as bytes/stream)."""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def build_document_pdf(*, title: str, doc_number: str, content: str,
                       signatures=None, org_name: str = "PT SIPRO Land",
                       layout: dict = None, images: dict = None, meta=None,
                       money_rows=None, clauses=None, note: str = "", script_context=None) -> bytes:
    """Render a SIPRO document to a PDF byte string.

    content is plain text with lines; lines shaped 'Label : Value' render as a table
    for a clean, formal look. signatures is a list of {role, name, signed_at}.
    """
    if layout:
        # Fase 60: kop surat, footer identitas, watermark, dan kolom tanda tangan yang bisa
        # dikonfigurasi. Dokumen tanpa layout tetap memakai jalur lama (kompatibel).
        import pdf_layout as _pl
        import doc_layout as _dl
        from doc_script import pdf_intro
        auto_codes = {"KWITANSI", "BKM", "BKK", "PENAWARAN", "BAST", "FAKTUR", "BUPOT"}
        intro = pdf_intro(layout, {"doc_number": doc_number, **(script_context or {})}) if layout.get("code") in auto_codes else ""
        sigs = _dl.signatures_for(layout) if not signatures else [
            {"title": (s.get("role") or "").title(), "name": s.get("name"),
             "position": None, "show_stamp": False} for s in signatures]
        return _pl.render_letter(layout, images or {}, title=title, doc_number=doc_number,
                                 content=intro or content, system_content=content if intro else "", meta=meta, money_rows=money_rows,
                                 clauses=clauses, note=note, signatures_override=sigs)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=22 * mm, bottomMargin=20 * mm,
        leftMargin=22 * mm, rightMargin=22 * mm, title=doc_number,
    )
    styles = getSampleStyleSheet()
    h_org = ParagraphStyle("org", parent=styles["Normal"], fontSize=10,
                           textColor=colors.HexColor("#0f766e"), alignment=TA_CENTER)
    h_title = ParagraphStyle("title", parent=styles["Title"], fontSize=16,
                             textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    h_num = ParagraphStyle("num", parent=styles["Normal"], fontSize=9,
                           textColor=colors.HexColor("#64748b"), alignment=TA_CENTER)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=15)

    flow = [
        Paragraph(org_name, h_org),
        Spacer(1, 4),
        Paragraph(title, h_title),
        Paragraph(f"Nomor: {doc_number}", h_num),
        Spacer(1, 14),
    ]

    rows = []
    for raw in content.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if rows:
                flow.append(_kv_table(rows))
                rows = []
            flow.append(Spacer(1, 8))
            continue
        if " : " in line or line.rstrip().endswith(":"):
            parts = line.split(":", 1)
            rows.append([parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")])
        else:
            if rows:
                flow.append(_kv_table(rows))
                rows = []
            flow.append(Paragraph(line, body))
    if rows:
        flow.append(_kv_table(rows))

    flow.append(Spacer(1, 22))
    if signatures:
        sig_cells = []
        for s in signatures:
            sig_cells.append(Paragraph(
                f"<b>{(s.get('role') or '').title()}</b><br/><br/><br/>"
                f"{s.get('name') or ''}<br/><font size=8 color='#64748b'>Ditandatangani</font>",
                body))
        while len(sig_cells) < 2:
            sig_cells.append(Paragraph("", body))
        t = Table([sig_cells], colWidths=[80 * mm, 80 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        flow.append(t)

    doc.build(flow)
    return buf.getvalue()


def _kv_table(rows):
    t = Table([[Paragraph(f"<b>{k}</b>", getSampleStyleSheet()["Normal"]), v] for k, v in rows],
              colWidths=[55 * mm, 105 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#0f172a")),
    ]))
    return t



_REPORT_NOTE = "Angka worksheet-level (belum GL penuh / e-Faktur). Dihasilkan otomatis oleh SIPRO."


def build_table_pdf(*, title: str, subtitle: str = "", columns, rows,
                    total_row=None, org_name: str = "PT SIPRO Land",
                    layout: dict = None, images: dict = None, intro: str = "",
                    note: str = None, script_context=None) -> bytes:
    """Render a tabular finance report to PDF bytes (header + optional total row)."""
    if layout:
        import pdf_layout as _pl
        if not intro and layout.get("code") == "LAPORAN":
            from doc_script import pdf_intro
            intro = pdf_intro(layout, script_context)
        return _pl.render_table(layout, images or {}, title=title, subtitle=subtitle,
                                columns=columns, rows=rows, total_row=total_row,
                                note=_REPORT_NOTE if note is None else note, intro=intro)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm, title=title,
    )
    styles = getSampleStyleSheet()
    h_org = ParagraphStyle("org2", parent=styles["Normal"], fontSize=10,
                           textColor=colors.HexColor("#0f766e"), alignment=TA_CENTER)
    h_title = ParagraphStyle("title2", parent=styles["Title"], fontSize=15,
                             textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    h_sub = ParagraphStyle("sub2", parent=styles["Normal"], fontSize=9,
                           textColor=colors.HexColor("#64748b"), alignment=TA_CENTER)
    note = ParagraphStyle("note2", parent=styles["Normal"], fontSize=8,
                          textColor=colors.HexColor("#94a3b8"))

    flow = [Paragraph(org_name, h_org), Spacer(1, 4), Paragraph(title, h_title)]
    if subtitle:
        flow.append(Paragraph(subtitle, h_sub))
    flow.append(Spacer(1, 12))

    data = [list(columns)] + [[str(c) for c in r] for r in rows]
    if total_row:
        data.append([str(c) for c in total_row])

    t = Table(data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]
    if total_row:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecfdf5")))
        style.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    flow.append(t)
    flow.append(Spacer(1, 16))
    flow.append(Paragraph(_REPORT_NOTE, note))
    doc.build(flow)
    return buf.getvalue()
