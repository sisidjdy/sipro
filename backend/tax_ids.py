"""Identitas pajak (NPWP / NIK) — SATU aturan untuk seluruh Fase 49.

Sebelum modul ini setiap tempat menilai NPWP dengan caranya sendiri: satu modul menolak
NPWP 15 digit lama, modul lain menerimanya apa adanya, dan layar tidak pernah menjelaskan
mana yang salah. Akibatnya berkas ekspor pajak bisa lahir dengan kolom identitas kosong —
kesalahan yang baru ketahuan setelah ditolak Coretax.

Aturan tunggal yang dipakai di sini:

* **16 digit** = bentuk yang dituntut Coretax (NPWP baru / NIK orang pribadi).
* **15 digit** = NPWP lama. Pemetaannya ke 16 digit BUKAN tebakan: PMK 112/PMK.03/2022
  menetapkan NPWP 15 digit dibaca dengan menambahkan angka **0 di depan**. Karena itu nilai
  15 digit DINORMALKAN (bukan ditolak), dan hasil normalisasinya selalu **diberi catatan**
  supaya pemakai tahu angka yang dikirim ke berkas berbeda dengan yang tersimpan.
* Panjang lain / kosong = **ditolak** dengan sebab yang menyebut panjang aslinya, karena
  menebak-nebak identitas pihak lain adalah cacat yang lebih berbahaya daripada ekspor gagal.
"""
import re

DIGITS = re.compile(r"\D")
LEN_NEW = 16
LEN_OLD = 15
NOTE_NORMALIZED = ("dinormalkan dari NPWP 15 digit lama dengan menambahkan 0 di depan "
                   "(PMK 112/PMK.03/2022)")


def digits(value) -> str:
    """Buang titik/strip/spasi — NPWP disimpan pemakai dalam banyak bentuk."""
    return DIGITS.sub("", str(value or ""))


def npwp16(value, *, label: str = "NPWP") -> dict:
    """Nilai siap-ekspor + kejujuran soal apa yang terjadi pada angkanya.

    Mengembalikan `{ok, value, raw, note, reason, normalized}`:
    * `ok=True`  → `value` berisi 16 digit yang boleh ditulis ke berkas.
    * `ok=False` → `reason` menjelaskan sebab + apa yang harus dilakukan pemakai.
    """
    raw = digits(value)
    if not raw:
        return {"ok": False, "value": "", "raw": raw, "note": "", "normalized": False,
                "reason": f"{label} belum diisi — lengkapi datanya sebelum berkas dibuat."}
    if len(raw) == LEN_NEW:
        return {"ok": True, "value": raw, "raw": raw, "note": "", "normalized": False,
                "reason": ""}
    if len(raw) == LEN_OLD:
        return {"ok": True, "value": "0" + raw, "raw": raw, "note": f"{label} {NOTE_NORMALIZED}",
                "normalized": True, "reason": ""}
    return {"ok": False, "value": "", "raw": raw, "note": "", "normalized": False,
            "reason": (f"{label} {raw} panjangnya {len(raw)} digit — yang sah 16 digit "
                       f"(atau 15 digit format lama). Perbaiki di data pihak terkait.")}


def mask(value) -> str:
    """Tampilan aman untuk log: 4 digit terakhir saja."""
    d = digits(value)
    return f"...{d[-4:]}" if len(d) > 4 else (d or "-")
