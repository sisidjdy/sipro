"""Konversi & validasi nilai sel Excel ke tipe kolom skema (tanpa akses DB)."""
import re

import reference as ref
from data_mgmt_schema import LOCAL_ENUMS, enum_options

_TRUE = {"true", "ya", "y", "1", "yes", "aktif", "benar"}
_FALSE = {"false", "tidak", "n", "0", "no", "nonaktif", "salah"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _to_int(v, label):
    if isinstance(v, bool):
        raise ValueError(f"{label}: harus angka.")
    if isinstance(v, (int, float)):
        return int(round(v))
    s = re.sub(r"[Rp\s]", "", str(v)).replace(".", "").replace(",", "")
    if not re.fullmatch(r"-?\d+", s):
        raise ValueError(f"{label}: '{v}' bukan angka bulat.")
    return int(s)


def _to_float(v, label):
    if isinstance(v, bool):
        raise ValueError(f"{label}: harus angka.")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"{label}: '{v}' bukan angka.")


def _to_bool(v, label):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ValueError(f"{label}: '{v}' harus TRUE/FALSE (atau Ya/Tidak).")


def _to_enum(v, f):
    opts = enum_options(f["enum"])
    s = str(v).strip()
    if s in opts:
        return s
    low = s.lower().replace(" ", "_")
    if low in opts:
        return low
    for val, lbl in opts.items():
        if str(lbl).lower() == s.lower():
            return val
    # Kamus non-strict (mis. addon_category) menerima nilai baru di aplikasi — impor harus
    # memakai aturan yang SAMA, bukan lebih ketat daripada formulir.
    if f["enum"] not in LOCAL_ENUMS and not ref.is_strict(f["enum"]):
        return ref.canonicalize(f["enum"], s)
    raise ValueError(f"{f['label']}: '{v}' tidak dikenal. Pilihan: {', '.join(opts)}.")


def _to_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [p.strip() for p in re.split(r"[;,\n]", str(v)) if p.strip()]


def coerce_value(f: dict, v):
    t, label = f["type"], f["label"]
    if t == "int":
        return _to_int(v, label)
    if t == "float":
        return _to_float(v, label)
    if t == "bool":
        return _to_bool(v, label)
    if t == "enum":
        return _to_enum(v, f)
    if t == "list":
        return _to_list(v)
    s = str(v).strip()
    if t == "email":
        s = s.lower()
        if not _EMAIL_RE.match(s):
            raise ValueError(f"{label}: '{v}' bukan email yang sah.")
    if t == "phone" and not re.search(r"\d{6,}", s):
        raise ValueError(f"{label}: '{v}' bukan nomor telepon.")
    return s


def coerce_row(ent: dict, raw: dict):
    """→ (values, errors). Nilai kosong memakai bawaan kolom."""
    values, errors = {}, []
    for f in ent["fields"]:
        v = raw.get(f["key"])
        if v is None or (isinstance(v, str) and not v.strip()):
            if f["required"]:
                errors.append(f"{f['label']} wajib diisi.")
            elif f["default"] is not None:
                values[f["key"]] = f["default"]
            else:
                values[f["key"]] = [] if f["type"] == "list" else None
            continue
        try:
            values[f["key"]] = coerce_value(f, v)
        except ValueError as e:
            errors.append(str(e))
    return values, errors
