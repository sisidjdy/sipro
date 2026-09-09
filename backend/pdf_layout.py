"""MESIN CETAK DOKUMEN BERKOP (Fase 60) — satu renderer untuk semua dokumen.

Dipakai oleh SEMUA penerbit PDF (SPR/SPKT/BAP, BAST, kwitansi, penawaran, faktur, bupot,
laporan tabel) dan oleh PRATINJAU di layar konfigurasi. Satu mesin, karena pratinjau yang
dirender jalur berbeda dari dokumen sungguhan adalah pratinjau yang boleh berbohong.

Yang digambar mesin ini dan tidak pernah ada sebelumnya:
  * **Kop surat** — mode `system` (logo + identitas perusahaan + garis aksen, dirakit dari
    Pusat Konfigurasi Dokumen) atau mode `image` (gambar kop buatan desainer, penuh lebar).
  * **Footer** — identitas ringkas + nomor halaman, atau gambar footer sendiri.
  * **Watermark** — teks diagonal (mis. "SALINAN"/"DRAFT") atau gambar, dengan kepekatan
    yang bisa diatur; digambar DI BAWAH isi supaya tetap terbaca.
  * **Kolom tanda tangan** — jumlah kolom, judul peran, nama & jabatan, spesimen tanda
    tangan/cap perusahaan, materai, dan tempat-tanggal.
  * **Tabel biaya** yang menghormati konfigurasi: baris tersembunyi, urutan, label sendiri,
    dan baris bernilai nol yang tidak perlu tercetak. Nilai `None` tetap tercetak sebagai
    "belum ditetapkan" — bukan Rp 0.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER, legal
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

PAPER = {"A4": A4, "LETTER": LETTER, "LEGAL": legal}


def _hex(value, fallback="#0f766e"):
    try:
        return colors.HexColor(value or fallback)
    except (ValueError, AttributeError):
        return colors.HexColor(fallback)


def _rp(v) -> str:
    if v is None:
        return "belum ditetapkan"
    return f"Rp {int(v):,}".replace(",", ".")


def _reader(data):
    try:
        return ImageReader(io.BytesIO(data))
    except Exception:  # noqa: BLE001  (gambar rusak tidak boleh menggagalkan dokumen)
        return None


class _Frame:
    """Penggambar kop, footer, dan watermark pada SETIAP halaman."""

    def __init__(self, layout: dict, imgs: dict):
        self.b = layout.get("brand") or {}
        self.o = layout.get("options") or {}
        self.imgs = imgs or {}

    def __call__(self, canvas, doc):
        canvas.saveState()
        self._watermark(canvas, doc)
        self._header(canvas, doc)
        self._footer(canvas, doc)
        canvas.restoreState()

    # ---------------------------------------------------------------- kop
    def _header(self, canvas, doc):
        w, h = doc.pagesize
        mode = self.b.get("header_mode") or "system"
        if mode == "none":
            return
        if mode == "image" and self.imgs.get("header_image"):
            img = _reader(self.imgs["header_image"])
            if img:
                iw, ih = img.getSize()
                tinggi = min(30 * mm, (w * ih) / max(iw, 1))
                canvas.drawImage(img, 0, h - tinggi, width=w, height=tinggi,
                                 preserveAspectRatio=True, anchor="n", mask="auto")
                return
        left = float(self.b.get("margin_left_mm") or 20) * mm
        right = w - float(self.b.get("margin_right_mm") or 20) * mm
        top = h - 14 * mm
        x = left
        if self.imgs.get("logo"):
            img = _reader(self.imgs["logo"])
            if img:
                iw, ih = img.getSize()
                lh = 16 * mm
                lw = min(40 * mm, (lh * iw) / max(ih, 1))
                canvas.drawImage(img, left, top - lh + 3 * mm, width=lw, height=lh,
                                 preserveAspectRatio=True, anchor="sw", mask="auto")
                x = left + lw + 5 * mm
        canvas.setFillColor(_hex(self.b.get("text_color"), "#0f172a"))
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(x, top - 3 * mm, str(self.b.get("company_name") or ""))
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        baris = [self.b.get("tagline"), self.b.get("address"),
                 " · ".join(t for t in [self.b.get("phone"), self.b.get("email"),
                                        self.b.get("website")] if t),
                 f"NPWP {self.b.get('npwp')}" if self.b.get("npwp") else None]
        y = top - 8 * mm
        for line in [b for b in baris if b]:
            canvas.drawString(x, y, str(line)[:110])
            y -= 3.6 * mm
        canvas.setStrokeColor(_hex(self.b.get("accent_color")))
        canvas.setLineWidth(1.6)
        garis = min(y + 1.5 * mm, top - 9 * mm)
        canvas.line(left, garis, right, garis)

    # ---------------------------------------------------------------- footer
    def _footer(self, canvas, doc):
        w, _h = doc.pagesize
        left = float(self.b.get("margin_left_mm") or 20) * mm
        right = w - float(self.b.get("margin_right_mm") or 20) * mm
        if (self.b.get("footer_mode") or "system") == "image" \
                and self.imgs.get("footer_image"):
            img = _reader(self.imgs["footer_image"])
            if img:
                iw, ih = img.getSize()
                tinggi = min(22 * mm, (w * ih) / max(iw, 1))
                canvas.drawImage(img, 0, 0, width=w, height=tinggi,
                                 preserveAspectRatio=True, anchor="s", mask="auto")
                return
        if (self.b.get("footer_mode") or "system") == "none":
            return
        canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas.setLineWidth(0.6)
        canvas.line(left, 15 * mm, right, 15 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748b"))
        teks = self.b.get("footer_text") or " · ".join(
            t for t in [self.b.get("company_name"), self.b.get("address"),
                        self.b.get("phone"), self.b.get("website")] if t)
        canvas.drawString(left, 11 * mm, str(teks)[:150])
        if self.b.get("show_page_numbers", True):
            canvas.setFont("Helvetica", 7.5)
            canvas.drawRightString(right, 11 * mm, f"Halaman {canvas.getPageNumber()}")

    # ---------------------------------------------------------------- watermark
    def _watermark(self, canvas, doc):
        w, h = doc.pagesize
        alpha = max(0, min(int(self.b.get("watermark_opacity") or 8), 60)) / 100.0
        if self.imgs.get("watermark"):
            img = _reader(self.imgs["watermark"])
            if img:
                canvas.saveState()
                canvas.setFillAlpha(alpha)
                canvas.drawImage(img, w * 0.15, h * 0.3, width=w * 0.7, height=h * 0.35,
                                 preserveAspectRatio=True, anchor="c", mask="auto")
                canvas.restoreState()
                return
        teks = (self.b.get("watermark_text") or "").strip()
        if not teks:
            return
        canvas.saveState()
        canvas.setFillAlpha(alpha)
        canvas.setFillColor(_hex(self.b.get("accent_color")))
        canvas.setFont("Helvetica-Bold", 64)
        canvas.translate(w / 2, h / 2)
        canvas.rotate(38)
        canvas.drawCentredString(0, 0, teks[:28])
        canvas.restoreState()


def _styles(layout: dict) -> dict:
    b = layout.get("brand") or {}
    s = getSampleStyleSheet()
    return {
        "width": PAPER.get(b.get("paper") or "A4", A4)[0] -
                 (float(b.get("margin_left_mm") or 20) + float(b.get("margin_right_mm") or 20)) * mm - 12,
        "title": ParagraphStyle("t60", parent=s["Title"], fontSize=15, spaceAfter=1,
                                textColor=_hex(b.get("text_color"), "#0f172a")),
        "num": ParagraphStyle("n60", parent=s["Normal"], fontSize=9, alignment=TA_CENTER,
                              textColor=colors.HexColor("#64748b")),
        "body": ParagraphStyle("b60", parent=s["Normal"], fontSize=10, leading=15),
        "small": ParagraphStyle("s60", parent=s["Normal"], fontSize=8,
                                textColor=colors.HexColor("#64748b")),
        "right": ParagraphStyle("r60", parent=s["Normal"], fontSize=9.5, alignment=TA_RIGHT),
        "sec": ParagraphStyle("sec60", parent=s["Normal"], fontSize=10.5, spaceBefore=8,
                              spaceAfter=3, textColor=_hex(b.get("accent_color")),
                              fontName="Helvetica-Bold"),
    }


def _kv(rows, st, accent):
    t = Table([[Paragraph(f"<b>{k}</b>", st["body"]), Paragraph(str(v), st["body"])]
               for k, v in rows], colWidths=[st["width"] * .34, st["width"] * .66])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("LINEBELOW", (0, 0), (-1, -2), 0.3,
                            colors.HexColor("#eef2f7"))]))
    return t


def _tcfg(layout: dict) -> dict:
    """Gaya tabel efektif (Fase 66) — bawaan aman bila organisasi belum menyetelnya."""
    t = dict((layout or {}).get("table") or {})
    return {"grid": t.get("grid") or "full",
            "show_header": t.get("show_header", True) is not False,
            "header_fill": t.get("header_fill", True) is not False,
            "zebra": t.get("zebra", True) is not False,
            "total_highlight": t.get("total_highlight", True) is not False,
            "font_size": float(t.get("font_size") or 8.5),
            "grid_color": t.get("grid_color") or "#e2e8f0",
            "width_pct": float(t.get("width_pct") or 100),
            "alignment": t.get("alignment") or "left"}


def _table_style(cfg: dict, accent, *, has_header: bool, has_total: bool) -> list:
    """Perintah gaya tabel dari konfigurasi — SATU tempat, dipakai semua tabel dokumen."""
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 3),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    garis = cfg["grid"]
    warna = _hex(cfg["grid_color"], "#e2e8f0")
    if garis == "full":
        style.append(("GRID", (0, 0), (-1, -1), 0.3, warna))
    elif garis == "horizontal":
        style.append(("LINEBELOW", (0, 0), (-1, -2), 0.3, warna))
    # garis == "none": TIDAK ada perintah garis sama sekali (tabel transparan).
    if has_header and cfg["header_fill"]:
        style += [("BACKGROUND", (0, 0), (-1, 0), accent),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    if cfg["zebra"]:
        awal = 1 if has_header else 0
        style.append(("ROWBACKGROUNDS", (0, awal), (-1, -1),
                      [colors.white, colors.HexColor("#f8fafc")]))
    if has_total and cfg["total_highlight"]:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecfdf5")))
    return style


def _money_table(rows, st, accent, cfg=None):
    cfg = cfg or _tcfg({})
    st = {**st, "body": ParagraphStyle("money-body", parent=st["body"], fontSize=cfg["font_size"], leading=cfg["font_size"] + 3),
          "right": ParagraphStyle("money-right", parent=st["right"], fontSize=cfg["font_size"], leading=cfg["font_size"] + 3)}
    data = []
    if cfg["show_header"]:
        hbody = ParagraphStyle("money-head", parent=st["body"], textColor=colors.white if cfg["header_fill"] else colors.black)
        hright = ParagraphStyle("money-head-right", parent=hbody, alignment=TA_RIGHT)
        data.append([Paragraph("<b>Komponen</b>", hbody), Paragraph("<b>Nilai</b>", hright)])
    for r in rows:
        label = r["label"] + (" *" if r.get("manual") else "")
        data.append([Paragraph(label, st["body"]), Paragraph(_rp(r.get("amount")), st["right"])])
    width = st["width"] * cfg["width_pct"] / 100
    t = Table(data, colWidths=[width * .66, width * .34], hAlign=cfg["alignment"].upper(),
              repeatRows=1 if cfg["show_header"] else 0)
    t.setStyle(TableStyle(_table_style(cfg, accent, has_header=cfg["show_header"],
                                       has_total=False)))
    return t


def _grid(columns, rows, total_row, st, accent, cfg=None):
    """Tabel rincian umum (item PO, lingkup SPK, baris laporan) — satu gaya untuk semua.

    Gaya (garis penuh/horizontal/transparan, nama kolom tampil atau tidak, baris belang,
    ukuran huruf) diambil dari konfigurasi dokumen — bukan lagi tertanam di kode.
    """
    cfg = cfg or _tcfg({})
    small = ParagraphStyle("g66", parent=st["small"], fontSize=cfg["font_size"],
                           leading=cfg["font_size"] + 3)
    data = []
    if cfg["show_header"]:
        header = ParagraphStyle("grid-head", parent=small, textColor=colors.white if cfg["header_fill"] else colors.black)
        data.append([Paragraph(f"<b>{c}</b>", header) for c in columns])
    data += [[Paragraph(str(c), small) for c in r] for r in rows]
    if total_row:
        data.append([Paragraph(f"<b>{c}</b>", small) for c in total_row])
    if not data:
        return Spacer(1, 1)
    t = Table(data, colWidths=[st["width"] * cfg["width_pct"] / 100 / max(len(columns), 1)] * len(columns),
              hAlign=cfg["alignment"].upper(), repeatRows=1 if cfg["show_header"] else 0)
    t.setStyle(TableStyle(_table_style(cfg, accent, has_header=cfg["show_header"],
                                       has_total=bool(total_row))))
    return t


def _signature_block(layout: dict, imgs: dict, st):
    sigs = layout.get("signatures") or []
    if not sigs:
        return []
    o = layout.get("options") or {}
    flow = []
    if o.get("show_place_date", True):
        tempat = (o.get("place") or "").strip()
        flow.append(Paragraph(f"{tempat + ', ' if tempat else ''}{o.get('doc_date') or ''}",
                              st["right"]))
        flow.append(Spacer(1, 6))
    cells, lebar = [], st["width"] / max(len(sigs), 1)
    for i, s in enumerate(sigs):
        isi = [Paragraph(f"<b>{s.get('title') or ''}</b>", st["body"])]
        spesimen = imgs.get(f"sig{i}_sign") or (imgs.get(f"sig{i}_stamp")
                                               if s.get("show_stamp") else None)
        if spesimen:
            from reportlab.platypus import Image as RLImage
            img = _reader(spesimen)
            if img:
                iw, ih = img.getSize()
                hh = 18 * mm
                isi.append(Spacer(1, 3))
                isi.append(RLImage(io.BytesIO(spesimen), width=min(34 * mm,
                                                                   hh * iw / max(ih, 1)),
                                   height=hh))
        else:
            isi.append(Spacer(1, 20 * mm))
        if s.get("show_stamp") and o.get("show_materai", True) and i == 0:
            isi.append(Paragraph(o.get("materai_note") or "Bermeterai cukup", st["small"]))
        isi.append(Paragraph(f"<u>{s.get('name') or '(...............................)'}</u>",
                             st["body"]))
        if s.get("position"):
            isi.append(Paragraph(s["position"], st["small"]))
        cells.append(isi)
    t = Table([cells], colWidths=[lebar] * len(sigs))
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    flow.append(t)
    return flow


def _doc(layout: dict, title: str):
    b = layout.get("brand") or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=PAPER.get(b.get("paper") or "A4", A4),
        topMargin=float(b.get("margin_top_mm") or 32) * mm,
        bottomMargin=float(b.get("margin_bottom_mm") or 24) * mm,
        leftMargin=float(b.get("margin_left_mm") or 20) * mm,
        rightMargin=float(b.get("margin_right_mm") or 20) * mm, title=title)
    return buf, doc


def _attachment_flow(pages, st, accent, cfg=None):
    """Halaman LAMPIRAN (Fase 62): daftar berkas + gambar kerja yang dirender apa adanya."""
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak
    flow = []
    for page in pages or []:
        flow.append(PageBreak())
        flow.append(Paragraph(page.get("title") or "LAMPIRAN", st["title"]))
        if page.get("note"):
            flow.append(Paragraph(page["note"], st["small"]))
        flow.append(Spacer(1, 8))
        if page.get("table"):
            kolom, baris = page["table"]
            flow.append(_grid(kolom, baris, None, st, accent, cfg))
        for img in page.get("images") or []:
            reader = _reader(img.get("data"))
            if not reader:
                continue
            iw, ih = reader.getSize()
            skala = min(165 * mm / max(iw, 1), 200 * mm / max(ih, 1))
            flow.append(Spacer(1, 8))
            flow.append(Paragraph(img.get("caption") or "", st["small"]))
            flow.append(RLImage(io.BytesIO(img["data"]), width=iw * skala,
                                height=ih * skala))
    return flow


def section_order(layout: dict, defaults: list) -> list:
    """Kunci bagian yang TAMPIL, urut sesuai `layout.sections.order`; kunci tak dikenal di akhir."""
    secs = sorted(layout.get("sections") or [], key=lambda s: s.get("order") or 0)
    known = {s.get("key") for s in secs}
    out = [s["key"] for s in secs if s.get("visible", True) and s.get("key") in defaults]
    return out + [k for k in defaults if k not in known]


def _money_block(money_rows, st, accent, tcfg):
    """Judul + tabel biaya + catatan baris manual, sebagai satu blok (posisi ikut konfigurasi)."""
    items = [Paragraph("Rincian biaya", st["sec"]), _money_table(money_rows, st, accent, tcfg)]
    if any(r.get("manual") for r in money_rows):
        items.append(Paragraph("* baris tambahan yang diisi manual oleh penerbit dokumen.",
                               st["small"]))
    items.append(Spacer(1, 4))
    return KeepTogether(items)


def _content_flow(content, st, accent, tcfg, markers=None):
    from document_richtext import is_rich, rich_flow
    markers = markers or {}
    if is_rich(content):
        table_body = ParagraphStyle("rich-table-body", parent=st["body"], fontSize=tcfg["font_size"], leading=tcfg["font_size"] + 3)
        table_head = ParagraphStyle("rich-table-head", parent=table_body, fontName="Helvetica-Bold",
                                    textColor=colors.white if tcfg["header_fill"] else colors.black)
        st = {**st, "table_body": table_body, "table_head": table_head}
        def table_factory(data, has_header):
            t = Table(data, colWidths=[st["width"] * tcfg["width_pct"] / 100 / len(data[0])] * len(data[0]),
                      hAlign=tcfg["alignment"].upper(), repeatRows=1 if has_header else 0)
            t.setStyle(TableStyle(_table_style(tcfg, accent, has_header=has_header, has_total=False)))
            return t
        return rich_flow(content, st, table_factory, markers)
    body = []
    for raw in (content or "").split("\n"):
        line = raw.rstrip()
        if line.strip() in markers:
            body.extend(markers[line.strip()]())
        elif not line.strip():
            body.append(Spacer(1, 5))
        elif " : " in line:
            k, v = line.split(":", 1)
            body.append(_kv([(k.strip(), v.strip())], st, accent))
        else:
            body.append(Paragraph(line, st["body"]))
    return body


def render_letter(layout: dict, imgs: dict, *, title: str, doc_number: str = "",
                  content: str = "", meta=None, money_rows=None, clauses=None,
                  note: str = "", signatures_override=None, item_table=None,
                  attachment_pages=None, system_content: str = "") -> bytes:
    """Surat/berita acara/kwitansi: kop, isi, tabel biaya, ketentuan, tanda tangan."""
    st = _styles(layout)
    o = layout.get("options") or {}
    accent = _hex((layout.get("brand") or {}).get("accent_color"))
    tcfg = _tcfg(layout)
    buf, doc = _doc(layout, doc_number or title)
    flow = []
    if o.get("show_title", True):
        flow.append(Paragraph(title, st["title"]))
    if doc_number and o.get("show_doc_number", True):
        flow.append(Paragraph(f"Nomor: {doc_number}", st["num"]))
    flow.append(Spacer(1, 10))
    # Blok per BAGIAN dokumen — urutan & tampil/tidak mengikuti `layout.sections`
    # (identitas → meta, biaya → tabel biaya, termin → tabel rincian, ketentuan → naskah + pasal,
    # catatan → penutup). Dulu urutan ini dikodekan mati sehingga konfigurasi tidak berpengaruh.
    inline_money = "{{tabel_biaya}}" in (content or "")
    blocks = {"identitas": [], "unit": [], "biaya": [], "termin": [], "ketentuan": [], "catatan": []}
    if meta:
        blocks["identitas"] += [_kv(meta, st, accent), Spacer(1, 6)]
    if money_rows and not inline_money:
        blocks["biaya"].append(_money_block(money_rows, st, accent, tcfg))
    if item_table and "{{tabel_rincian}}" not in (content or ""):
        kolom, baris, total = item_table
        blocks["termin"] += [Paragraph("Rincian", st["sec"]),
                             _grid(kolom, baris, total, st, accent, tcfg), Spacer(1, 4)]
    if system_content and "{{tabel_rincian}}" not in (content or ""):
        blocks["termin"].extend(_content_flow(system_content, st, accent, tcfg))
    body = blocks["ketentuan"]
    body.extend(_content_flow(content, st, accent, tcfg, {
        "{{tabel_biaya}}": lambda: [_money_block(money_rows, st, accent, tcfg)] if money_rows else [],
        "{{tabel_rincian}}": lambda: [_grid(*item_table, st, accent, tcfg)] if item_table else _content_flow(system_content, st, accent, tcfg),
    }))
    if clauses:
        body.append(Paragraph("Ketentuan", st["sec"]))
        for i, c in enumerate(clauses, 1):
            body += [Paragraph(f"{i}. {c}", st["body"]), Spacer(1, 2)]
    if o.get("closing_note"):
        blocks["catatan"] += [Spacer(1, 6), Paragraph(o["closing_note"], st["body"])]
    if note:
        blocks["catatan"] += [Spacer(1, 6), Paragraph(note, st["small"])]
    for key in section_order(layout, list(blocks)):
        flow += blocks.get(key) or []
    flow.append(Spacer(1, 14))
    sig_layout = dict(layout)
    if signatures_override is not None:
        sig_layout["signatures"] = signatures_override
    flow.append(KeepTogether(_signature_block(sig_layout, imgs, st)))
    flow += _attachment_flow(attachment_pages, st, accent, tcfg)
    doc.build(flow, onFirstPage=_Frame(layout, imgs), onLaterPages=_Frame(layout, imgs))
    return buf.getvalue()


def render_table(layout: dict, imgs: dict, *, title: str, subtitle: str = "", columns,
                 rows, total_row=None, note: str = "", intro: str = "") -> bytes:
    """Laporan tabel — kop & footer yang sama dengan surat, jadi satu identitas.

    `intro` adalah NASKAH laporan (Fase 66): kalimat pembuka yang tercetak di atas tabel,
    sehingga laporan pun punya isi, bukan tabel telanjang.
    """
    st = _styles(layout)
    accent = _hex((layout.get("brand") or {}).get("accent_color"))
    tcfg = _tcfg(layout)
    buf, doc = _doc(layout, title)
    flow = [Paragraph(title, st["title"])] if (layout.get("options") or {}).get("show_title", True) else []
    if subtitle:
        flow.append(Paragraph(subtitle, st["num"]))
    flow.append(Spacer(1, 10))
    grid = lambda: [_grid(columns, rows, total_row, st, accent, tcfg)]
    blocks = {"ketentuan": _content_flow(intro, st, accent, tcfg, {
        "{{tabel_rincian}}": grid, "{{tabel_biaya}}": grid}),
        "termin": [] if any(t in (intro or "") for t in ("{{tabel_rincian}}", "{{tabel_biaya}}")) else grid(),
        "catatan": [Spacer(1, 10), Paragraph(note, st["small"])] if note else []}
    for key in section_order(layout, list(blocks)):
        flow.extend(blocks[key])
    doc.build(flow, onFirstPage=_Frame(layout, imgs), onLaterPages=_Frame(layout, imgs))
    return buf.getvalue()
