"""Site Plan SVG (Fase 28) — geometri peta kavling.

Tiga hal yang ditangani file ini:
1. `generate_demo_plan()` — membangkitkan layout REALISTIS (boulevard, jalan utama,
   deret kavling menghadap jalan, busur kavling di cul-de-sac, taman, danau, clubhouse)
   sebagai pengganti grid kotak. Dipakai sampai SVG asli dari arsitek tersedia.
2. `parse_svg()` — membaca SVG unggahan dan MENGAMBIL GEOMETRINYA SAJA
   (`d` / `points` / x,y,w,h / cx,cy,r). Markup mentah TIDAK PERNAH disuntikkan ke DOM,
   sehingga tidak ada celah `<script>`/`onload` dari file pihak ketiga.
3. `auto_match()` — mencocokkan shape ke unit lewat id/label (mis. `lot-A-01`, `HS498`).

Bentuk shape (dipakai backend & frontend):
    {shape_id, kind, label, unit_id, geom:{type,...}, centroid:{x,y}}
    kind: lot | road | green | water | facility | boundary
"""
import math
import re

VIEW_W, VIEW_H = 1600, 1000
LOT_KINDS = ("lot",)
MAX_SHAPES = 4000

_ID_ATTRS = ("data-unit", "data-unit-code", "data-name", "inkscape:label", "id")
_KIND_HINTS = (
    ("road", ("road", "jalan", "street", "drive", "alley", "court", "lane", "aspal")),
    ("green", ("green", "taman", "park", "garden", "rumput", "lansekap", "playground")),
    ("water", ("water", "danau", "kolam", "pool", "sungai", "creek", "river")),
    ("facility", ("club", "facility", "fasilitas", "masjid", "musholla", "gate", "pos",
                  "parkir", "parking", "kantor", "office", "sport", "gym")),
    ("boundary", ("boundary", "batas", "outline", "site", "border")),
    ("lot", ("lot", "kav", "kavling", "unit", "homesite", "hs", "plot", "persil")),
)


def _poly(points) -> str:
    return " ".join(f"{round(x, 1)},{round(y, 1)}" for x, y in points)


def _centroid(points) -> dict:
    n = len(points) or 1
    return {"x": round(sum(p[0] for p in points) / n, 1),
            "y": round(sum(p[1] for p in points) / n, 1)}


def _shape(shape_id, kind, points, label=None, unit_id=None) -> dict:
    return {"shape_id": shape_id, "kind": kind, "label": label, "unit_id": unit_id,
            "geom": {"type": "polygon", "points": _poly(points)},
            "centroid": _centroid(points)}


# --------------------------------------------------------------------------
# 1. Generator layout realistis
# --------------------------------------------------------------------------
def _row_lots(units, y_front, y_back, x_start, width, skew=0.0, prefix="r"):
    """Deret kavling menghadap jalan. `skew` memberi kemiringan tipis agar tidak kaku."""
    out = []
    for i, u in enumerate(units):
        x0 = x_start + i * width
        x1 = x0 + width - 4
        dy = skew * i
        pts = [(x0, y_front + dy), (x1, y_front + dy + skew),
               (x1 + 3, y_back + dy + skew), (x0 + 3, y_back + dy)]
        out.append(_shape(f"{prefix}-{u['code']}", "lot", pts, u["code"], u["id"]))
    return out


def _arc_lots(units, cx, cy, r_in, r_out, a0_deg, a1_deg, prefix="c"):
    """Kavling berbentuk juring di sekitar cul-de-sac (bentuk khas cluster nyata)."""
    out = []
    n = max(1, len(units))
    span = (a1_deg - a0_deg) / n
    for i, u in enumerate(units):
        a0 = math.radians(a0_deg + i * span + 0.8)
        a1 = math.radians(a0_deg + (i + 1) * span - 0.8)
        steps = 4
        outer = [(cx + r_out * math.cos(a0 + (a1 - a0) * s / steps),
                  cy + r_out * math.sin(a0 + (a1 - a0) * s / steps)) for s in range(steps + 1)]
        inner = [(cx + r_in * math.cos(a1 - (a1 - a0) * s / steps),
                  cy + r_in * math.sin(a1 - (a1 - a0) * s / steps)) for s in range(steps + 1)]
        out.append(_shape(f"{prefix}-{u['code']}", "lot", outer + inner, u["code"], u["id"]))
    return out


def _context_shapes() -> list:
    """Jalan, taman, danau, clubhouse — konteks yang membuat peta terbaca sebagai site plan."""
    s = []
    s.append(_shape("boundary", "boundary",
                    [(40, 40), (1560, 40), (1560, 960), (40, 960)], "Batas Lahan"))
    # Boulevard masuk (vertikal) + jalan utama (horizontal) + jalan sekunder
    s.append(_shape("road-boulevard", "road",
                    [(96, 40), (152, 40), (152, 960), (96, 960)], "Boulevard Utama"))
    s.append(_shape("road-main", "road",
                    [(96, 470), (1560, 462), (1560, 520), (96, 526)], "Jalan Utama"))
    s.append(_shape("road-secondary", "road",
                    [(152, 792), (1180, 786), (1180, 828), (152, 834)], "Jalan Sekunder"))
    s.append(_shape("road-north", "road",
                    [(152, 176), (1120, 170), (1120, 208), (152, 214)], "Jalan Blok Utara"))
    # Cul-de-sac (bundaran) — didekati poligon 24 sisi agar konsisten satu tipe geom
    ring = [(1332 + 132 * math.cos(math.radians(a)), 742 + 132 * math.sin(math.radians(a)))
            for a in range(0, 360, 15)]
    s.append(_shape("road-culdesac", "road", ring, "Cul-de-sac"))
    inner = [(1332 + 58 * math.cos(math.radians(a)), 742 + 58 * math.sin(math.radians(a)))
             for a in range(0, 360, 20)]
    s.append(_shape("green-island", "green", inner, "Taman Bundaran"))
    # Taman utama + danau + clubhouse + parkir
    s.append(_shape("green-park", "green",
                    [(200, 866), (700, 862), (760, 940), (180, 944)], "Taman & Jogging Track"))
    s.append(_shape("water-pond", "water",
                    [(820, 872), (1010, 866), (1080, 926), (900, 946), (820, 920)], "Danau Retensi"))
    s.append(_shape("facility-clubhouse", "facility",
                    [(1188, 262), (1452, 258), (1452, 404), (1188, 408)], "Clubhouse & Kolam"))
    s.append(_shape("facility-gate", "facility",
                    [(60, 560), (152, 560), (152, 648), (60, 648)], "Gerbang & Pos Jaga"))
    s.append(_shape("facility-parking", "facility",
                    [(1188, 430), (1452, 426), (1452, 486), (1188, 490)], "Parkir Bersama"))
    return s


def generate_demo_plan(units: list) -> dict:
    """Bangun peta realistis untuk daftar unit (urut kode). Deterministik."""
    rows = sorted([{"id": u["id"], "code": u.get("code") or ""} for u in units],
                  key=lambda x: x["code"])
    n = len(rows)
    if not n:
        return {"view_box": f"0 0 {VIEW_W} {VIEW_H}", "shapes": _context_shapes()}
    n_arc = min(6, max(0, n // 4))
    rest = n - n_arc
    n_north = (rest + 1) // 2
    north, south = rows[:n_north], rows[n_north:n_north + (rest - n_north)]
    arc = rows[n_north + (rest - n_north):]
    w_north = max(74.0, min(132.0, 940 / max(1, len(north))))
    w_south = max(74.0, min(132.0, 940 / max(1, len(south))))
    shapes = _context_shapes()
    shapes += _row_lots(north, 300, 458, 200, w_north, skew=0.35, prefix="lot")
    shapes += _row_lots(south, 540, 700, 230, w_south, skew=-0.3, prefix="lot")
    shapes += _arc_lots(arc, 1332, 742, 148, 268, 196, 344, prefix="lot")
    return {"view_box": f"0 0 {VIEW_W} {VIEW_H}", "shapes": shapes}


# --------------------------------------------------------------------------
# 2. Parser SVG unggahan (ambil geometri saja)
# --------------------------------------------------------------------------
def _classify(text: str) -> str:
    low = (text or "").lower()
    for kind, hints in _KIND_HINTS:
        if any(h in low for h in hints):
            return kind
    return "lot" if re.search(r"\d", low) else "facility"


def _attrs(raw: str) -> dict:
    return {k.lower(): v for k, v in re.findall(r'([\w:.-]+)\s*=\s*"([^"]*)"', raw)}


def _num(a, key, default=0.0):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(a.get(key, default)) or "0") or 0)
    except ValueError:
        return default


def parse_svg(svg_text: str) -> dict:
    """Ekstrak viewBox + geometri shape. Elemen skrip/gaya dibuang total."""
    if not svg_text or "<svg" not in svg_text.lower():
        raise ValueError("Berkas bukan SVG yang sah (tag <svg> tidak ditemukan).")
    clean = re.sub(r"<(script|style|foreignObject)\b.*?</\1>", "", svg_text,
                   flags=re.S | re.I)
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', clean, re.I)
    view_box = m.group(1).strip() if m else None
    if not view_box:
        w = re.search(r'\bwidth\s*=\s*"([\d.]+)', clean)
        h = re.search(r'\bheight\s*=\s*"([\d.]+)', clean)
        view_box = f"0 0 {w.group(1) if w else VIEW_W} {h.group(1) if h else VIEW_H}"
    shapes, seen = [], set()
    for tag, raw in re.findall(r"<(path|polygon|polyline|rect|circle|ellipse)\b([^>]*)>",
                               clean, re.I):
        if len(shapes) >= MAX_SHAPES:
            break
        a = _attrs(raw)
        ident = next((a[k] for k in _ID_ATTRS if a.get(k)), "")
        label = ident or None
        kind = _classify(f"{ident} {a.get('class', '')}")
        tag = tag.lower()
        geom = None
        if tag == "path" and a.get("d"):
            geom = {"type": "path", "d": a["d"]}
        elif tag in ("polygon", "polyline") and a.get("points"):
            geom = {"type": "polygon", "points": a["points"].strip()}
        elif tag == "rect":
            x, y, w, h = _num(a, "x"), _num(a, "y"), _num(a, "width"), _num(a, "height")
            if w > 0 and h > 0:
                geom = {"type": "polygon",
                        "points": _poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])}
        elif tag in ("circle", "ellipse"):
            cx, cy = _num(a, "cx"), _num(a, "cy")
            rx = _num(a, "r") or _num(a, "rx")
            ry = _num(a, "r") or _num(a, "ry") or rx
            if rx > 0:
                pts = [(cx + rx * math.cos(math.radians(t)), cy + ry * math.sin(math.radians(t)))
                       for t in range(0, 360, 15)]
                geom = {"type": "polygon", "points": _poly(pts)}
        if not geom:
            continue
        sid = ident or f"{tag}-{len(shapes) + 1}"
        while sid in seen:
            sid = f"{sid}_{len(shapes) + 1}"
        seen.add(sid)
        centroid = None
        if geom["type"] == "polygon":
            pairs = re.findall(r"(-?[\d.]+)[\s,]+(-?[\d.]+)", geom["points"])
            pts = [(float(px), float(py)) for px, py in pairs]
            centroid = _centroid(pts) if pts else None
        shapes.append({"shape_id": sid, "kind": kind, "label": label, "unit_id": None,
                       "geom": geom, "centroid": centroid})
    if not shapes:
        raise ValueError("Tidak ada bentuk (path/polygon/rect) yang bisa dibaca dari SVG ini.")
    return {"view_box": view_box, "shapes": shapes}


# --------------------------------------------------------------------------
# 3. Auto-match shape -> unit
# --------------------------------------------------------------------------
def _norm(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def auto_match(shapes: list, units: list) -> int:
    """Cocokkan shape berjenis `lot` ke unit berdasarkan id/label. Kembalikan jumlah cocok."""
    by_code = {_norm(u.get("code")): u["id"] for u in units if u.get("code")}
    taken = {s["unit_id"] for s in shapes if s.get("unit_id")}
    hit = 0
    for s in shapes:
        if s.get("unit_id") or s["kind"] not in LOT_KINDS:
            continue
        key = _norm(f"{s.get('label') or ''}{s['shape_id']}")
        match = by_code.get(_norm(s.get("label") or "")) or by_code.get(_norm(s["shape_id"]))
        if not match:
            for code, uid in by_code.items():
                if code and len(code) >= 3 and code in key and uid not in taken:
                    match = uid
                    break
        if match and match not in taken:
            s["unit_id"] = match
            taken.add(match)
            hit += 1
    return hit


def plan_stats(shapes: list, units: list) -> dict:
    lots = [s for s in shapes if s["kind"] in LOT_KINDS]
    mapped = [s for s in lots if s.get("unit_id")]
    mapped_ids = {s["unit_id"] for s in mapped}
    return {"total_shapes": len(shapes), "total_lots": len(lots), "mapped": len(mapped),
            "unmapped_lots": len(lots) - len(mapped),
            "unmapped_units": [u["id"] for u in units if u["id"] not in mapped_ids],
            "coverage_pct": round(len(mapped) / len(units) * 100) if units else 0}
