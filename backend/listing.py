"""listing.py — Fase 40: kontrak query daftar (cari + filter multi + sort) yang JUJUR.

Kenapa modul ini ada (bukan kerapian, tapi cacat nyata yang ditutup):

1. **Sort di frontend pada data terpaginasi = bohong.** Sebelum Fase 40 daftar dikirim
   terpaginasi (20–50 baris) lalu diurutkan di browser, sehingga yang terurut hanyalah
   halaman aktif — pemakai yang mengurutkan "harga tertinggi" hanya melihat harga tertinggi
   *di halaman itu*. Semua sort sekarang dieksekusi server-side atas SELURUH hasil query.
2. **Filter hanya satu nilai.** `?stage=booking` tidak bisa menjawab "tampilkan nurturing DAN
   booking". Semua filter sekarang menerima daftar dipisah koma → `$in`.
3. **Sort field sembarang berbahaya.** Nama kolom dari URL tidak boleh langsung masuk
   `.sort()` (bisa mengurutkan field internal / memaksa scan mahal). Karena itu setiap
   endpoint mendaftarkan WHITELIST kolom yang boleh diurutkan.
4. **Pencarian dengan regex mentah bisa pecah** bila pemakai mengetik `(` atau `+`
   (mis. nomor telepon `+62`). Semua pencarian di-escape.

Dipakai oleh: leads, units, deals, customers, tasks, AR, documents, complaints.
"""
import re
from datetime import datetime, timezone
from typing import Iterable

MAX_MULTI = 40  # batas nilai per filter (menahan URL raksasa / query $in tak terbatas)


# --------------------------------------------------------------------------- filter
def multi(value) -> list:
    """'a,b , a' -> ['a','b'] (buang kosong & duplikat, jaga urutan)."""
    if value is None or value == "":
        return []
    raw = value if isinstance(value, (list, tuple)) else str(value).split(",")
    out = []
    for item in raw:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out[:MAX_MULTI]


def apply_in(query: dict, field: str, value, allowed: Iterable = None) -> dict:
    """Filter satu-atau-banyak nilai. Nilai di luar `allowed` dibuang (bukan error senyap:
    kalau SEMUA nilai ditolak, query dibuat mustahil supaya hasilnya kosong dan pemakai
    sadar filternya tidak dikenal — lebih baik daripada mengabaikan filter diam-diam)."""
    vals = multi(value)
    if not vals:
        return query
    if allowed is not None:
        allow = set(allowed)
        kept = [v for v in vals if v in allow]
        if not kept:
            query[field] = {"$in": []}
            return query
        vals = kept
    query[field] = vals[0] if len(vals) == 1 else {"$in": vals}
    return query


def apply_search(query: dict, q: str, fields: Iterable[str]) -> dict:
    """Pencarian teks (case-insensitive) pada beberapa field. Regex di-escape."""
    if not q or not str(q).strip():
        return query
    pat = re.escape(str(q).strip())
    ors = [{f: {"$regex": pat, "$options": "i"}} for f in fields]
    if "$and" in query:
        query["$and"].append({"$or": ors})
    elif "$or" in query:
        query["$and"] = [{"$or": query.pop("$or")}, {"$or": ors}]
    else:
        query["$or"] = ors
    return query


def apply_range(query: dict, field: str, start=None, end=None) -> dict:
    """Rentang inklusif untuk tanggal ISO (string) maupun angka."""
    cond = {}
    if start not in (None, ""):
        cond["$gte"] = start
    if end not in (None, ""):
        # tanggal ISO: '2026-08-16' harus mencakup seluruh hari
        cond["$lte"] = f"{end}T23:59:59.999999+00:00" if _is_date_only(end) else end
    if cond:
        query[field] = {**query.get(field, {}), **cond} if isinstance(query.get(field), dict) \
            else cond
    return query


def _is_date_only(v) -> bool:
    return isinstance(v, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))


# ----------------------------------------------------------------------------- sort
def sort_spec(sort: str = None, direction: str = None, allowed: dict = None,
              default: tuple = ("created_at", -1)) -> list:
    """Terjemahkan `?sort=<kolom>&direction=asc|desc` menjadi spesifikasi Motor.

    `allowed` = {kolom_publik: field_mongo}. Kolom di luar whitelist diabaikan (jatuh ke
    default) supaya URL tidak bisa memaksa sort pada field internal.
    Tie-breaker `id` selalu ditambahkan agar paginasi stabil (tanpa itu baris bisa muncul
    dua kali / hilang antar halaman saat nilai kunci sama).
    """
    allowed = allowed or {}
    field, dirn = default
    key = (sort or "").strip()
    if key and key in allowed:
        field = allowed[key]
        dirn = -1 if str(direction or "asc").lower().startswith("desc") else 1
    spec = [(field, dirn)]
    if field != "id":
        spec.append(("id", 1))
    return spec


# ---------------------------------------------------------------------------- aging
def _parse_iso(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_iso(value):
    """Publik: ubah string ISO / datetime menjadi datetime ber-timezone (None bila gagal).

    Dipakai `stage_clock` (Fase 41) untuk menghitung `stage_due_at` dari field tersimpan.
    """
    return _parse_iso(value)


def hours_since(value, ref: datetime = None) -> float:
    """Umur dalam jam (dibulatkan 2 desimal). None bila tanggal tidak terbaca."""
    dt = _parse_iso(value)
    if not dt:
        return None
    ref = ref or datetime.now(timezone.utc)
    return round(max(0.0, (ref - dt).total_seconds() / 3600.0), 2)


def stage_entered_at(doc: dict, history_field: str = "stage_history",
                     stage_field: str = "stage") -> str:
    """Kapan dokumen MASUK tahap sekarang.

    Fase 40 belum boleh menambah field `stage_entered_at` tersimpan (itu milik Fase 41 yang
    juga mengubah mesin tahap). Nilainya diturunkan dari jejak yang SUDAH dicatat
    `lead_lifecycle.record()`, dengan urutan kepercayaan:
      1. `stage_changed_at` (ditulis setiap perpindahan tahap),
      2. entri terakhir `stage_history` yang `to == tahap sekarang`,
      3. `created_at` — bila belum pernah pindah tahap, umur tahap = umur sejak masuk.
    Semuanya fakta yang tercatat, bukan tebakan.
    """
    if doc.get("stage_changed_at"):
        return doc["stage_changed_at"]
    cur = doc.get(stage_field)
    for entry in reversed(doc.get(history_field) or []):
        if not isinstance(entry, dict):
            continue
        if entry.get("to") == cur or entry.get("stage") == cur:
            return entry.get("at") or entry.get("created_at") or doc.get("created_at")
    return doc.get("created_at")


def attach_aging(rows: list, history_field: str = "stage_history",
                 stage_field: str = "stage") -> list:
    """Tambahkan `stage_entered_at`, `age_hours` (umur total), `stage_age_hours` (umur tahap).

    Read-only turunan — TIDAK ditulis ke database (agar Fase 41 bebas menjadikannya field
    nyata tanpa harus membereskan data setengah jadi).
    """
    ref = datetime.now(timezone.utc)
    for row in rows or []:
        entered = stage_entered_at(row, history_field, stage_field) if stage_field in row \
            else row.get("created_at")
        row["stage_entered_at"] = entered
        row["age_hours"] = hours_since(row.get("created_at"), ref)
        row["stage_age_hours"] = hours_since(entered, ref)
    return rows
