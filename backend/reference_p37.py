"""SSOT reference registry — TAMBAHAN Fase 37 (Kalibrasi Sekali Klik).

Alasan file terpisah sama seperti Fase 31/33/34/35/36: `reference.py` sudah menyentuh batas
gate compliance (<=800 baris). Grup di sini digabungkan ke `reference.GROUPS` sehingga
seluruh dropdown/label frontend tetap SATU sumber (`GET /api/reference`).

Fase 37 menutup dua hal:
  1. Analitik Telat sudah memberi rekomendasi kalibrasi, tetapi ujungnya hanya kalimat
     "buka Template Jadwal" — supervisor harus pindah layar & mengetik ulang seluruh
     template, sehingga dalam praktiknya kalibrasi tidak pernah dilakukan.
  2. Perubahan durasi/waktu tunggu template tidak punya JEJAK (siapa, kapan, atas dasar
     data apa, alasannya) dan tidak bisa dikembalikan bila keliru.

Catatan kejujuran yang dipegang: mengubah template TIDAK menggeser jadwal unit yang sudah
berjalan (bukti kerja tidak boleh bergeser). Angka baru berlaku untuk jadwal BERIKUTNYA;
mengubah tanggal jadwal berjalan tetap lewat Fase 34 (geser massal beralasan).
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P37: dict = {
    # ---------------- jenis kalibrasi template ----------------
    # Nilainya harus sama dengan `build_calibration.KINDS` (dijaga gate verify_37).
    "calibration_kind": {
        "label": "Jenis Kalibrasi Template", "strict": True, "options": [
            _o("step_duration", "Ubah durasi langkah (hari kerja)"),
            _o("wait_time", "Ubah waktu tunggu wajib sebelum langkah"),
            _o("wait_into_plan", "Masukkan waktu tunggu ke tanggal rencana"),
        ],
    },
    # ---------------- alasan kalibrasi (wajib dipilih) ----------------
    # Sengaja BUKAN teks bebas: alasan dipakai untuk membaca pola keputusan perencanaan
    # lintas waktu ("berapa kali template dilonggarkan karena cuaca?").
    "calibration_cause": {
        "label": "Alasan Kalibrasi", "strict": True, "options": [
            _o("data_telat", "Bukti keterlambatan berulang dari data"),
            _o("waktu_tunggu_fisik", "Waktu tunggu fisik (curing/kering) belum masuk rencana"),
            _o("cuaca_musiman", "Musim hujan / cuaca daerah"),
            _o("kapasitas_tukang", "Kapasitas tukang / regu tidak cukup"),
            _o("material_lead_time", "Waktu tunggu pengadaan material"),
            _o("metode_berubah", "Metode kerja / spesifikasi berubah"),
            _o("koreksi_salah_input", "Koreksi kesalahan pengisian template"),
            _o("pembatalan_kalibrasi", "Pembatalan kalibrasi sebelumnya (rollback)"),
        ],
    },
}

CALIBRATION_KINDS = tuple(o["value"] for o in GROUPS_P37["calibration_kind"]["options"])
CALIBRATION_CAUSES = tuple(o["value"] for o in GROUPS_P37["calibration_cause"]["options"])
KIND_LABEL = {o["value"]: o["label"] for o in GROUPS_P37["calibration_kind"]["options"]}
CAUSE_LABEL = {o["value"]: o["label"] for o in GROUPS_P37["calibration_cause"]["options"]}
