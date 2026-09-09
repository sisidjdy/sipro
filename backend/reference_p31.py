"""SSOT reference registry — TAMBAHAN Fase 31 (Jadwal Pembangunan Berbukti per Unit).

Kenapa file terpisah? `reference.py` sudah ~790 baris (batas gate compliance 800).
Grup di sini digabungkan ke `reference.GROUPS` sehingga tetap SATU registry dan semua
dropdown frontend memakai `/api/reference` (tidak ada nilai enum yang diketik bebas).

Fase 31 memperbaiki cacat lama: progres konstruksi dulu berupa ANGKA PERSEN yang
diketik manual pada fase level PROYEK, lalu ditimpa ke SEMUA unit — jadi progres per
rumah tidak nyata dan mudah dicurangi. Sekarang progres lahir dari ITEM PEKERJAAN
per unit yang punya jadwal tanggal, gerbang (predecessor + waktu tunggu/curing +
hold point), bukti foto wajib, dan verifikasi supervisor.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P31: dict = {
    # ---------------- status item pekerjaan (siklus berbukti) ----------------
    "build_item_status": {
        "label": "Status Item Pekerjaan", "strict": True, "options": [
            _o("blocked", "Terkunci (gerbang belum terbuka)"),
            _o("ready", "Siap dikerjakan"),
            _o("in_progress", "Sedang dikerjakan"),
            _o("submitted", "Menunggu verifikasi"),
            _o("rework", "Dikembalikan (perbaiki)"),
            _o("done", "Selesai & terverifikasi"),
        ],
    },
    "build_schedule_status": {
        "label": "Status Jadwal Unit", "strict": True, "options": [
            _o("not_started", "Belum mulai"),
            _o("in_progress", "Berjalan"),
            _o("at_risk", "Terlambat / berisiko"),
            _o("on_hold", "Dihentikan sementara"),
            _o("done", "Selesai"),
        ],
    },
    # ---------------- gerbang mutu (kenapa sebuah item terkunci) ----------------
    "build_gate_reason": {
        "label": "Alasan Gerbang Terkunci", "strict": True, "options": [
            _o("predecessor", "Pekerjaan sebelumnya belum diverifikasi"),
            _o("wait_time", "Masih menunggu waktu tunggu / curing"),
            _o("hold_point", "Hold point wajib lulus dulu"),
            _o("schedule_hold", "Jadwal unit dihentikan sementara"),
        ],
    },
    # ---------------- kalender jadwal (bisa dikonfigurasi per template) ----------------
    "build_calendar_mode": {
        "label": "Perhitungan Hari", "strict": True, "options": [
            _o("working_days", "Hari kerja (lewati hari libur mingguan)"),
            _o("calendar_days", "Hari kalender (termasuk hari libur)"),
        ],
    },
    "build_work_week": {
        "label": "Hari Kerja per Minggu", "strict": True, "options": [
            _o("5", "5 hari (Sabtu & Minggu libur)"),
            _o("6", "6 hari (Minggu libur)"),
            _o("7", "7 hari (tanpa libur mingguan)"),
        ],
    },
    # ---------------- penyebab keterlambatan (analitik nyata, bukan tebakan) ----------------
    "build_delay_cause": {
        "label": "Penyebab Keterlambatan", "strict": True, "options": [
            _o("material_late", "Material belum datang"),
            _o("manpower_short", "Tukang kurang / tidak masuk"),
            _o("weather", "Cuaca (hujan)"),
            _o("design_change", "Perubahan desain / permintaan pembeli"),
            _o("payment_pending", "Pembayaran termin belum turun"),
            _o("subcon_issue", "Masalah subkontraktor"),
            _o("permit", "Perizinan belum selesai"),
            _o("rework", "Pengerjaan ulang karena mutu"),
            _o("other", "Lainnya (jelaskan)"),
        ],
    },
    # ---------------- alasan menerobos gerbang (dicatat & dilaporkan ke owner) ----------------
    "build_override_reason": {
        "label": "Alasan Menerobos Gerbang", "strict": True, "options": [
            _o("verified_offline", "Sudah diperiksa langsung di lapangan"),
            _o("schedule_recovery", "Percepatan mengejar keterlambatan"),
            _o("data_correction", "Koreksi data / salah input jadwal"),
            _o("owner_instruction", "Instruksi direksi"),
            _o("other", "Lainnya (jelaskan)"),
        ],
    },
    # ---------------- jenis bukti pekerjaan ----------------
    "build_evidence_kind": {
        "label": "Jenis Bukti Pekerjaan", "strict": True, "options": [
            _o("photo", "Foto pekerjaan"),
            _o("checklist", "Checklist mutu"),
            _o("measurement", "Hasil ukur / uji"),
            _o("document", "Dokumen (hasil tes, berita acara)"),
        ],
    },
}

# Label pendek dipakai backend saat menyusun pesan (agar tidak ada string ganda di UI).
ITEM_STATUS_LABEL = {o["value"]: o["label"] for o in GROUPS_P31["build_item_status"]["options"]}
GATE_REASON_LABEL = {o["value"]: o["label"] for o in GROUPS_P31["build_gate_reason"]["options"]}
DELAY_CAUSE_LABEL = {o["value"]: o["label"] for o in GROUPS_P31["build_delay_cause"]["options"]}
