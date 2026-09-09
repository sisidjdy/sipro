"""Safe rich document content, shared by preview and issued PDFs. Legacy text stays valid."""
import re
from html import escape

import bleach
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup, NavigableString
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

BLOCK = re.compile(r'<(?:p|h[1-3]|table|ul|ol|blockquote|div)(?:\s|>)', re.I)
TABLE_TOKENS = {"tabel_biaya", "tabel_rincian"}
ALIGN = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
TAGS = {"p", "h1", "h2", "h3", "br", "strong", "b", "em", "i", "u", "s", "span",
        "ul", "ol", "li", "blockquote", "table", "thead", "tbody", "tr", "th", "td", "div"}


def is_rich(content):
    return bool(BLOCK.search(content or ""))


def sanitize(content):
    if not is_rich(content):
        return content
    soup = BeautifulSoup(content, "html.parser")
    for node in soup.find_all(["script", "style", "iframe", "object", "svg", "img"]):
        node.decompose()
    return bleach.clean(str(soup), tags=TAGS, attributes={
        "*": ["style"], "td": ["colspan", "rowspan", "colwidth", "style"],
        "th": ["colspan", "rowspan", "colwidth", "style"], "ol": ["start"],
    }, css_sanitizer=CSSSanitizer(allowed_css_properties=["text-align"]), strip=True)


def substitute(content, context, missing=None):
    rich = is_rich(content)
    def sub(m):
        key = m.group(1)
        if key in TABLE_TOKENS:
            return "{{" + key + "}}"
        value = context.get(key)
        if value is None:
            return missing(key) if missing else "{{" + key + "}}"
        value = str(value)
        return escape(value).replace("\n", "<br/>") if rich else value
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", sub, content or "")


def _inline(node):
    if isinstance(node, NavigableString):
        return escape(str(node))
    tag = {"strong": "b", "em": "i", "s": "strike"}.get(node.name, node.name)
    if tag == "br":
        return "<br/>"
    text = "".join(_inline(c) for c in node.children)
    return f"<{tag}>{text}</{tag}>" if tag in {"b", "i", "u", "strike"} else text


def rich_flow(content, st, table_factory, markers=None):
    """No browser HTML is sent directly to ReportLab's XML parser."""
    markers = markers or {}
    soup = BeautifulSoup(sanitize(content), "html.parser")
    flow = []

    def emit(node, depth=0, prefix=""):
        if isinstance(node, NavigableString):
            if str(node).strip():
                # Mixed legacy + rich content from system-composed letters.
                for line in str(node).splitlines():
                    if line.strip():
                        flow.append(Paragraph(escape(line), st["body"]))
            return
        text = node.get_text().strip()
        if node.name in {"p", "div"} and text in markers:
            flow.extend(markers[text]())
            return
        if node.name == "table":
            flow.append(_rich_table(node, st, table_factory))
            flow.append(Spacer(1, 7))
            return
        if node.name in {"ul", "ol"}:
            try:
                start = max(1, int(node.get("start", 1)))
            except (ValueError, TypeError):
                start = 1
            for i, li in enumerate(node.find_all("li", recursive=False), start):
                emit(li, depth + 1, f"{i}. " if node.name == "ol" else "• ")
            return
        if node.name == "li":
            first = True
            for child in node.children:
                emit(child, depth, prefix if first else "")
                if not isinstance(child, NavigableString) or str(child).strip():
                    first = False
            return
        if node.name in {"div", "blockquote", "tbody", "thead"}:
            for child in node.children:
                emit(child, depth, prefix)
            return
        alignment = re.search(r'text-align\s*:\s*(left|center|right|justify)', node.get("style", ""))
        size = {"h1": 16, "h2": 13, "h3": 11}.get(node.name, st["body"].fontSize)
        style = ParagraphStyle("rich", parent=st["body"], fontSize=size,
                               leading=size * 1.5, spaceAfter=5,
                               fontName="Helvetica-Bold" if node.name.startswith("h") else st["body"].fontName,
                               alignment=ALIGN[alignment[1]] if alignment else st["body"].alignment,
                               leftIndent=depth * 14, firstLineIndent=-12 if prefix else 0)
        flow.append(Paragraph(escape(prefix) + _inline(node), style) if text else Spacer(1, 8))

    for node in soup.children:
        emit(node)
    return flow


def _rich_table(node, st, table_factory):
    rows, spans, occupied = [], [], set()
    for ri, row in enumerate(node.find_all("tr", recursive=True)):
        cells, ci = {}, 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (ri, ci) in occupied:
                ci += 1
            def count(attr):
                try:
                    return max(1, min(20, int(cell.get(attr, 1))))
                except (ValueError, TypeError):
                    return 1
            cs, rs = count("colspan"), count("rowspan")
            # Nested tables are not editable in this editor; render their text safely.
            if cell.find("table"):
                cells[ci] = [Paragraph(escape(cell.get_text(" ")), st["body"])]
            else:
                cell_st = {**st, "body": st.get("table_head" if cell.name == "th" else "table_body", st["body"])}
                cells[ci] = rich_flow(cell.decode_contents(), cell_st, table_factory) or [Paragraph("", cell_st["body"])]
            if cs > 1 or rs > 1:
                spans.append(("SPAN", (ci, ri), (ci + cs - 1, ri + rs - 1)))
            for dr in range(rs):
                for dc in range(cs):
                    occupied.add((ri + dr, ci + dc))
            ci += cs
        rows.append(cells)
    if not rows:
        return Spacer(1, 1)
    ncol = max(c for _, c in occupied) + 1 if occupied else 1
    nrow = max(len(rows), max((r for r, _ in occupied), default=0) + 1)
    data = [[(rows[r] if r < len(rows) else {}).get(c, "") for c in range(ncol)] for r in range(nrow)]
    table = table_factory(data, bool(node.find("th")))
    table.setStyle(TableStyle(spans))
    return table