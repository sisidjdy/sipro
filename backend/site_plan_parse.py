"""Parser SVG site plan yang lebih kaya (Fase 72).

Perbedaan dengan parser lama (`site_plan_svg.parse_svg`):
* `<g transform>` bersarang dihitung (translate/scale/rotate/matrix) → koordinat absolut.
* `<path d>` disederhanakan menjadi poligon (titik ujung tiap segmen) sehingga bisa
  dihitung centroid, luas, dan uji titik-dalam-poligon.
* `<text>` dibaca; teks yang jatuh DI DALAM bentuk dipakai sebagai label kavling
  (mis. "A-01" dari gambar arsitek) → bahan pencocokan otomatis ke unit.
* Deteksi kavling berbasis LUAS: bentuk kecil yang ukurannya mirip satu sama lain
  dianggap kavling walau tidak diberi id; bentuk raksasa = batas/jalan.
Markup mentah tidak pernah disuntikkan ke DOM — hanya titik poligon yang disimpan.
"""
import math
import re

VIEW_W, VIEW_H = 1600, 1000
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
_TAG_RE = re.compile(r"<(/?)(g|svg|path|polygon|polyline|rect|circle|ellipse|text|tspan)\b([^>]*?)(/?)>",
                     re.I | re.S)
_NUM_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?", re.I)
CODE_RE = re.compile(r"^([A-Z]{1,3})[\s\-/.]*0*(\d{1,4})([A-Z]?)$")
# blok berangka (mis. "A1-05", "Q9 03") — pemisah wajib agar tidak ambigu
CODE_RE_NUMBLOCK = re.compile(r"^([A-Z]{1,3}\d{1,2})[\s\-/.]+0*(\d{1,4})([A-Z]?)$")


# ------------------------------------------------------------------ matriks
def _mat_mul(a, b):
    """a·b untuk matriks affine (a b c d e f)."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def parse_transform(s: str):
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        v = [float(x) for x in _NUM_RE.findall(args)]
        name = name.lower()
        if name == "translate":
            t = (1, 0, 0, 1, v[0] if v else 0, v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0] if v else 1, 0, 0, v[1] if len(v) > 1 else (v[0] if v else 1), 0, 0)
        elif name == "rotate":
            a = math.radians(v[0] if v else 0)
            t = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) >= 3:
                t = _mat_mul(_mat_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "skewx":
            t = (1, 0, math.tan(math.radians(v[0] if v else 0)), 1, 0, 0)
        elif name == "skewy":
            t = (1, math.tan(math.radians(v[0] if v else 0)), 0, 1, 0, 0)
        else:
            continue
        m = _mat_mul(m, t)
    return m


def _apply(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


# ------------------------------------------------------------------ geometri
def _attrs(raw: str) -> dict:
    return {k.lower(): v for k, v in re.findall(r'([\w:.-]+)\s*=\s*"([^"]*)"', raw)}


def _num(a, key, default=0.0):
    m = _NUM_RE.search(str(a.get(key, "")))
    return float(m.group(0)) if m else default


def path_points(d: str) -> list:
    """Titik ujung tiap perintah path (M L H V C S Q T A Z) → poligon sederhana."""
    pts, cur, start = [], (0.0, 0.0), (0.0, 0.0)
    for cmd, args in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d or ""):
        v = [float(x) for x in _NUM_RE.findall(args)]
        rel = cmd.islower()
        c = cmd.upper()
        if c == "Z":
            if pts and pts[0] != pts[-1]:
                cur = start
            continue
        step = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}[c]
        i = 0
        while i + step <= len(v):
            seg = v[i:i + step]
            if c == "H":
                nxt = ((cur[0] if rel else 0) + seg[0], cur[1])
            elif c == "V":
                nxt = (cur[0], (cur[1] if rel else 0) + seg[0])
            else:
                x, y = seg[-2], seg[-1]
                nxt = ((cur[0] + x, cur[1] + y) if rel else (x, y))
            if c == "M" and i == 0:
                start = nxt
            pts.append(nxt)
            cur = nxt
            i += step
    return pts


def area(pts) -> float:
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroid(pts) -> dict:
    n = len(pts) or 1
    return {"x": round(sum(p[0] for p in pts) / n, 1), "y": round(sum(p[1] for p in pts) / n, 1)}


def point_in(pts, x, y) -> bool:
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i - 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            inside = not inside
    return inside


def poly_str(pts) -> str:
    return " ".join(f"{round(x, 1)},{round(y, 1)}" for x, y in pts)


def points_of(geom: dict) -> list:
    if not geom:
        return []
    if geom.get("type") == "path":
        return path_points(geom.get("d"))
    return [(float(a), float(b)) for a, b in
            re.findall(r"(-?[\d.]+)[\s,]+(-?[\d.]+)", geom.get("points") or "")]


def _classify(text: str):
    low = (text or "").lower()
    for kind, hints in _KIND_HINTS:
        if any(h in low for h in hints):
            return kind
    return None


# ------------------------------------------------------------------ parser utama
def parse_svg_rich(svg_text: str) -> dict:
    if not svg_text or "<svg" not in svg_text.lower():
        raise ValueError("Berkas bukan SVG yang sah (tag <svg> tidak ditemukan).")
    clean = re.sub(r"<(script|style|foreignObject|defs|metadata)\b.*?</\1>", "", svg_text,
                   flags=re.S | re.I)
    clean = re.sub(r"<!--.*?-->", "", clean, flags=re.S)
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', clean, re.I)
    view_box = m.group(1).strip() if m else None
    if not view_box:
        w = re.search(r'<svg[^>]*\bwidth\s*=\s*"([\d.]+)', clean, re.I | re.S)
        h = re.search(r'<svg[^>]*\bheight\s*=\s*"([\d.]+)', clean, re.I | re.S)
        view_box = f"0 0 {w.group(1) if w else VIEW_W} {h.group(1) if h else VIEW_H}"
    vb = [float(x) for x in view_box.split()]
    vb_area = (vb[2] * vb[3]) if len(vb) == 4 else VIEW_W * VIEW_H

    stack = [(1, 0, 0, 1, 0, 0)]
    shapes, texts, seen = [], [], set()
    pos = 0
    for tm in _TAG_RE.finditer(clean):
        closing, tag, raw, selfclose = tm.group(1), tm.group(2).lower(), tm.group(3), tm.group(4)
        a = _attrs(raw)
        if tag in ("g", "svg"):
            if closing:
                if len(stack) > 1:
                    stack.pop()
            elif not selfclose:
                stack.append(_mat_mul(stack[-1], parse_transform(a.get("transform"))))
            continue
        if closing:
            continue
        mat = _mat_mul(stack[-1], parse_transform(a.get("transform")))
        if tag == "text":
            end = clean.find("</text>", tm.end())
            inner = re.sub(r"<[^>]+>", " ", clean[tm.end():end if end > 0 else tm.end()])
            content = re.sub(r"\s+", " ", inner).strip()
            if content and len(content) <= 24:
                x, y = _apply(mat, _num(a, "x"), _num(a, "y"))
                texts.append({"text": content, "x": x, "y": y})
            continue
        if tag == "tspan":
            continue
        if len(shapes) >= MAX_SHAPES:
            break
        pts = []
        if tag == "path" and a.get("d"):
            pts = path_points(a["d"])
        elif tag in ("polygon", "polyline") and a.get("points"):
            v = [float(x) for x in _NUM_RE.findall(a["points"])]
            pts = list(zip(v[0::2], v[1::2]))
        elif tag == "rect":
            x, y, w, h = _num(a, "x"), _num(a, "y"), _num(a, "width"), _num(a, "height")
            if w > 0 and h > 0:
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        elif tag in ("circle", "ellipse"):
            cx, cy = _num(a, "cx"), _num(a, "cy")
            rx = _num(a, "r") or _num(a, "rx")
            ry = _num(a, "r") or _num(a, "ry") or rx
            if rx > 0:
                pts = [(cx + rx * math.cos(math.radians(t)), cy + ry * math.sin(math.radians(t)))
                       for t in range(0, 360, 15)]
        if len(pts) < 3:
            continue
        pts = [_apply(mat, x, y) for x, y in pts]
        ident = next((a[k] for k in _ID_ATTRS if a.get(k)), "")
        sid = ident or f"{tag}-{len(shapes) + 1}"
        while sid in seen:
            sid = f"{sid}_{len(shapes) + 1}"
        seen.add(sid)
        hint = _classify(f"{ident} {a.get('class', '')}")
        shapes.append({"shape_id": sid, "kind": hint, "label": ident or None, "unit_id": None,
                       "geom": {"type": "polygon", "points": poly_str(pts)},
                       "centroid": centroid(pts), "_pts": pts, "_area": area(pts),
                       "_hinted": bool(hint), "_auto_id": not ident})
        pos = tm.end()
    if not shapes:
        raise ValueError("Tidak ada bentuk (path/polygon/rect) yang bisa dibaca dari SVG ini.")
    labeled = _attach_texts(shapes, texts)
    lots = _detect_lots(shapes, vb_area)
    for s in shapes:
        for k in ("_pts", "_area", "_hinted", "_auto_id"):
            s.pop(k, None)
    return {"view_box": view_box, "shapes": shapes,
            "detected": {"shapes": len(shapes), "texts": len(texts), "labeled": labeled,
                         "lots": lots}}


def _attach_texts(shapes: list, texts: list) -> int:
    """Teks yang berada di dalam bentuk kecil → label bentuk itu (teks terkecil menang)."""
    small = sorted([s for s in shapes if s["_area"] > 0], key=lambda s: s["_area"])
    hit = 0
    for t in texts:
        for s in small:
            if s.get("_labeled"):
                continue
            if point_in(s["_pts"], t["x"], t["y"]):
                looks_code = bool(re.search(r"\d", t["text"])) and len(t["text"]) <= 12
                if looks_code or s["_auto_id"]:
                    s["label"] = t["text"]
                    s["_labeled"] = True
                    hit += 1
                break
    return hit


def _detect_lots(shapes: list, vb_area: float) -> int:
    """Bentuk tanpa petunjuk id: kavling bila luasnya mirip bentuk berlabel/berukuran sedang."""
    labeled = [s["_area"] for s in shapes if s.get("_labeled") and s["_area"] > 0]
    pool = labeled or sorted(s["_area"] for s in shapes
                             if 0 < s["_area"] < vb_area * 0.02)
    ref = sorted(pool)[len(pool) // 2] if pool else 0
    n = 0
    for s in shapes:
        if s["_area"] >= vb_area * 0.15 and not s["_hinted"]:
            s["kind"] = "boundary"
        elif s["_hinted"]:
            pass
        elif s.get("_labeled") or (ref and 0.25 * ref <= s["_area"] <= 4 * ref
                                   and 3 <= len(s["_pts"]) <= 40):
            s["kind"] = "lot"
        else:
            s["kind"] = "facility"
        if s["kind"] == "lot":
            n += 1
    return n


def parse_code(label: str):
    """'A-01' / 'A 1' / 'B12' / 'C-07A' → (blok, no) atau None."""
    raw = (label or "").upper().strip()
    m = CODE_RE_NUMBLOCK.match(raw) or CODE_RE.match(re.sub(r"\s+", "", raw))
    if not m:
        return None
    return m.group(1), str(int(m.group(2))).zfill(2) + m.group(3)
