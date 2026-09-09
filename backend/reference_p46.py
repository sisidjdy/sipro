"""SSOT reference registry — TAMBAHAN Fase 46 (Konsolidasi Proyek & Konstruksi).

Kenapa file terpisah? `reference.py` sudah mendekati batas gate compliance (800 baris).
Grup di sini digabungkan ke `reference.GROUPS` sehingga tetap SATU registry dan semua
dropdown/label frontend membacanya dari `/api/reference` (tidak ada label enum yang
ditulis ulang di layar).

Fase 46 menutup tiga cacat lama yang dicatat dok `docs/v2/29_CONSTRUCTION_SPEC.md`:

1. **Perizinan menggantung di proyek saja.** Padahal IMB/PBG bisa terbit per blok, dan SLF
   per unit. Karena itu `permits` mendapat `scope` + `scope_id` (proyek/cluster/blok/unit)
   sehingga izin MENEMPEL pada objek yang benar dan bisa ditanyakan dari Unit 360.
2. **Kesehatan izin tidak pernah dinilai.** Izin "disetujui" tetapi sudah kedaluwarsa
   dulu tampak aman. Sekarang ada kosakata `permit_health` yang jujur.
3. **Gerbang "Mulai Bangun" hanya ada di kertas.** Setting `build.require_dp_before_start`
   ada sejak Fase 39 tetapi tidak pernah dibaca satu jalur kode pun. Fase 46 memberi
   kosakata alasan (`build_gate_code`) agar penolakan/peringatan bisa dijelaskan ke user
   dengan bahasa manusia, bukan "tombol mati tanpa sebab".
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P46: dict = {
    # ---------------- tingkat objek yang bisa dilekati izin ----------------
    "permit_scope": {
        "label": "Cakupan Izin", "strict": True, "options": [
            _o("project", "Proyek (berlaku untuk semua unit)"),
            _o("cluster", "Cluster"),
            _o("block", "Blok"),
            _o("unit", "Unit (rumah tertentu)"),
        ],
    },
    # ---------------- kesehatan izin (bukan hanya status administrasi) ----------------
    "permit_health": {
        "label": "Kesehatan Izin", "strict": True, "options": [
            _o("ok", "Aktif & aman"),
            _o("expiring", "Menjelang kedaluwarsa"),
            _o("expired", "Sudah kedaluwarsa"),
            _o("in_process", "Masih diproses"),
            _o("rejected", "Ditolak instansi"),
            _o("missing", "Belum ada"),
        ],
    },
    # ---------------- kesiapan memulai pembangunan satu unit ----------------
    "build_readiness_state": {
        "label": "Kesiapan Mulai Bangun", "strict": True, "options": [
            _o("ready", "Siap dimulai"),
            _o("warning", "Boleh dimulai dengan peringatan"),
            _o("blocked", "Belum bisa dimulai"),
            _o("started", "Sudah berjalan"),
        ],
    },
    # ---------------- alasan gerbang (dipakai peringatan & penolakan) ----------------
    "build_gate_code": {
        "label": "Alasan Gerbang Pembangunan", "strict": True, "options": [
            _o("no_schedule", "Belum ada jadwal pembangunan unit"),
            _o("schedule_on_hold", "Jadwal sedang dihentikan sementara"),
            _o("no_ready_item", "Langkah pertama belum terbuka"),
            _o("no_payment_plan", "Belum ada rencana bayar (termin)"),
            _o("dp_unpaid", "Termin pertama (DP) belum terbayar"),
            _o("permit_missing", "Izin wajib belum ada"),
            _o("permit_expired", "Izin sudah kedaluwarsa"),
            _o("permit_expiring", "Izin menjelang kedaluwarsa"),
            _o("already_started", "Pembangunan sudah berjalan"),
        ],
    },
    # ---------------- tingkat peringatan yang dipakai gerbang ----------------
    "gate_severity": {
        "label": "Tingkat Gerbang", "strict": True, "options": [
            _o("blocker", "Menghalangi (tidak bisa dilanjutkan)"),
            _o("warning", "Peringatan (boleh lanjut dengan konfirmasi)"),
            _o("info", "Informasi"),
        ],
    },
}


def _labels(group: str) -> dict:
    return {o["value"]: o["label"] for o in GROUPS_P46[group]["options"]}


PERMIT_SCOPE_LABEL = _labels("permit_scope")
PERMIT_HEALTH_LABEL = _labels("permit_health")
READINESS_LABEL = _labels("build_readiness_state")
GATE_LABEL = _labels("build_gate_code")
SEVERITY_LABEL = _labels("gate_severity")

PERMIT_SCOPES = tuple(PERMIT_SCOPE_LABEL)
# Izin yang boleh dipakai sebagai bukti "aman": aktif, atau aktif tetapi mendekati
# kedaluwarsa (masih sah hari ini — tetap dijadikan PERINGATAN, bukan penghalang).
PERMIT_OK_HEALTH = ("ok", "expiring")
# SSOT `construction_status` (Fase 39): not_started, scheduled, in_progress, qc_hold,
# done, on_hold. "Sudah berjalan" = pekerjaan fisik memang sudah dimulai. Didefinisikan
# SEKALI di sini supaya papan unit & evaluator kesiapan tidak punya dua definisi.
STARTED_UNIT_STATUS = ("in_progress", "qc_hold", "done")
