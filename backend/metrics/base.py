"""base.py — KONTRAK satu bentuk untuk semua metrik BI (Fase 44).

Pelajaran yang dikodekan di sini (Fase 36/37/43): **nol dan "belum ada data" adalah dua hal
yang berbeda.** Kalau keduanya digambar sama, kampanye tanpa biaya terlihat paling efisien,
proyek tanpa realisasi terlihat paling hemat, dan sales tanpa aktivitas tercatat terlihat
sama dengan sales yang benar-benar tidak bekerja. Karena itu setiap metrik mengembalikan:

  value      angka (atau None bila memang TIDAK BISA dihitung)
  complete   True hanya bila SEMUA input yang dibutuhkan ada
  missing    daftar input yang belum ada, ditulis dalam bahasa manusia
  coverage   {rows, total} bila angkanya dihitung dari SEBAGIAN baris (mis. hanya 30 dari 47
             lead punya waktu respons) — angkanya boleh tampil, tapi wajib berlabel
  inputs     bahan mentah yang dipakai, supaya bisa dihitung ulang tangan saat diaudit
  breakdown  rincian (untuk grafik & tabel drill-down)
  series     deret waktu bila metriknya punya sumbu waktu
  drill      tautan ke DAFTAR barisnya (aturan blueprint: KPI tanpa drill = belum selesai)

ATURAN KEJUJURAN yang ditegakkan fungsi `result` sendiri (bukan sekadar diserahkan ke
pemanggil): bila ada `missing` DAN tidak ada `coverage`, `value` DIPAKSA None. Jadi mustahil
mengirim angka "0" untuk metrik yang datanya tidak ada — sekalipun pemanggilnya lupa.
"""
UNITS = ("count", "idr", "pct", "days", "hours", "ratio", "text")
PERSONAS = {
    "eksekutif": "Eksekutif",
    "penjualan": "Penjualan & Lead",
    "marketing": "Marketing",
    "proyek": "Proyek & Biaya",
    "tim": "Kinerja Tim",
}
NOTE_INCOMPLETE = "data belum lengkap"


def result(code: str, value, *, label: str = None, unit: str = "count", breakdown=None,
           series=None, inputs=None, missing=None, coverage=None, note=None,
           drill: str = None) -> dict:
    """Bentuk baku hasil metrik (lihat docstring modul)."""
    missing = [m for m in (missing or []) if m]
    if unit not in UNITS:
        raise ValueError(f"satuan metrik tidak dikenal: {unit}")
    if missing and coverage is None:
        # Tidak ada input -> tidak ada angka. Ini pemaksaan, bukan saran.
        value = None
    complete = not missing
    if note is None and missing:
        note = f"{NOTE_INCOMPLETE}: " + "; ".join(missing)
    return {
        "code": code, "label": label, "value": value, "unit": unit,
        "complete": complete, "missing": missing, "coverage": coverage,
        "inputs": inputs or {}, "breakdown": breakdown or [], "series": series or [],
        "note": note, "drill": drill,
    }


def pct(part, whole, digits: int = 1):
    """Persen yang jujur: pembagi 0 -> None (bukan 0%)."""
    if not whole:
        return None
    return round(part / whole * 100, digits)


def div(part, whole, digits: int = 2):
    if not whole:
        return None
    return round(part / whole, digits)


def median(values: list):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return round((vals[mid - 1] + vals[mid]) / 2, 2)


def day_range_query(field: str, date_from: str = None, date_to: str = None) -> dict:
    """Rentang tanggal untuk field ISO string. `date_to` inklusif sepanjang hari."""
    cond = {}
    if date_from:
        cond["$gte"] = date_from
    if date_to:
        cond["$lte"] = f"{date_to}T23:59:59.999999+00:00"
    return {field: cond} if cond else {}


def month_of(iso: str) -> str:
    return (iso or "")[:7]


def date_of(iso: str) -> str:
    return (iso or "")[:10]


def bucket_days(days: float) -> str:
    """Ember umur seragam dengan laporan umur tahap (0–1h, 1–3h, 3–7h, >7h)."""
    if days is None:
        return "tidak diketahui"
    if days <= 1:
        return "0-1 hari"
    if days <= 3:
        return "1-3 hari"
    if days <= 7:
        return "3-7 hari"
    return ">7 hari"
