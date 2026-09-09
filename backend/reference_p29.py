"""SSOT reference registry — TAMBAHAN Fase 29 (Domain Kerja: divisi, supervisor, jobdesk).

Kenapa file terpisah? `reference.py` sudah ~790 baris (batas gate compliance 800).
Grup di sini digabungkan ke `reference.GROUPS` sehingga tetap SATU registry.

Fase 29 menambahkan **domain kerja** yang sebelumnya tidak pernah ada di sistem:
setiap pengguna berada di satu **divisi** dengan **level** (supervisor/staf), dan setiap
pekerjaan berasal dari **jobdesk** yang punya sumber (event sistem / berulang / manual),
aturan penerima, SLA, bukti wajib, dan cara verifikasi.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P29: dict = {
    "division": {
        "label": "Divisi", "strict": True, "options": [
            _o("sales_marketing", "Sales & Marketing"),
            _o("technical", "Teknis & Proyek"),
            _o("digital_marketing", "Digital Marketing"),
            _o("finance", "Keuangan"),
        ],
    },
    "org_level": {
        "label": "Level Jabatan", "strict": True, "options": [
            _o("owner", "Direksi (lintas divisi)"),
            _o("supervisor", "Supervisor"),
            _o("staff", "Staf"),
        ],
    },
    "jobdesk_source": {
        "label": "Sumber Tugas", "strict": True, "options": [
            _o("event", "Otomatis dari event sistem"),
            _o("recurring", "Berulang sesuai jadwal"),
            _o("manual", "Manual (ditugaskan supervisor)"),
        ],
    },
    "assignee_rule": {
        "label": "Aturan Penerima Tugas", "strict": True, "options": [
            _o("record_owner", "Pemilik data terkait"),
            _o("round_robin", "Bergilir antar staf divisi"),
            _o("specific", "Orang tertentu"),
            _o("supervisor", "Supervisor divisi"),
            _o("all_staff", "Semua staf divisi (masing-masing dapat)"),
        ],
    },
    "proof_kind": {
        "label": "Bukti Wajib", "strict": True, "options": [
            _o("none", "Tanpa bukti"),
            _o("note", "Catatan hasil kerja"),
            _o("photo", "Foto"),
            _o("document", "Dokumen/berkas"),
            _o("record", "Data tersimpan di sistem"),
            _o("wa_message", "Pesan WhatsApp terkirim"),
        ],
    },
    "recurrence": {
        "label": "Perulangan", "strict": True, "options": [
            _o("daily", "Harian"), _o("weekly", "Mingguan"), _o("monthly", "Bulanan"),
        ],
    },
    "verify_mode": {
        "label": "Cara Verifikasi", "strict": True, "options": [
            _o("none", "Tidak perlu diverifikasi"),
            _o("system", "Diverifikasi otomatis oleh sistem"),
            _o("supervisor", "Diverifikasi supervisor (penilaian manusia)"),
        ],
    },
    "task_review": {
        "label": "Hasil Verifikasi", "strict": True, "options": [
            _o("none", "—"), _o("pending", "Menunggu verifikasi"),
            _o("approved", "Disetujui"), _o("rejected", "Dikembalikan"),
        ],
    },
    # ---------------- Fase 29b — kualitas percakapan lead ----------------
    "lead_disposition": {
        "label": "Respons Lead", "strict": True, "options": [
            _o("positive", "Positif (berminat)"),
            _o("neutral", "Netral (masih menimbang)"),
            _o("negative", "Negatif (tidak berminat)"),
            _o("no_response", "Tidak merespons"),
        ],
    },
    "lead_close_reason": {
        "label": "Alasan Lead Berhenti", "strict": True, "options": [
            _o("price", "Harga di luar anggaran"),
            _o("location", "Lokasi tidak sesuai"),
            _o("financing", "KPR/pembiayaan tidak lolos"),
            _o("competitor", "Memilih pengembang lain"),
            _o("no_response", "Tidak bisa dihubungi"),
            _o("not_serious", "Belum serius / iseng"),
            _o("duplicate", "Data ganda"),
            _o("other", "Lainnya"),
        ],
    },
    "wa_playbook": {
        "label": "Playbook WhatsApp", "strict": True, "options": [
            _o("first_touch", "Sapaan kontak pertama"),
            _o("followup_nurturing", "Follow-up lead menimbang"),
            _o("survey_reminder", "Pengingat survey H-1"),
            _o("payment_reminder", "Pengingat pembayaran"),
            _o("promo_blast", "Blasting promo"),
            _o("reengage", "Aktivasi ulang lead diam"),
        ],
    },
    # ---------------- Fase 30c: antrean lead gagal masuk (webhook iklan) ----------------
    "capture_failure_status": {
        "label": "Status Lead Gagal Masuk", "strict": True, "options": [
            _o("open", "Tertahan (perlu ditindak)"),
            _o("resolved", "Diselamatkan (lead dibuat)"),
            _o("discarded", "Dibuang (beralasan)"),
        ],
    },
    "capture_failure_kind": {
        "label": "Jenis Kegagalan", "strict": True, "options": [
            _o("data", "Data cacat (perlu koreksi manusia)"),
            _o("transient", "Gangguan sementara (dicoba ulang otomatis)"),
        ],
    },
}

# Divisi & level DEFAULT per peran (dipakai bila user belum punya field division/level).
# Peran lama tetap berjalan tanpa migrasi paksa; peran baru khusus divisi yang tadinya
# tidak punya pemimpin (Digital Marketing) atau tidak punya supervisor (Keuangan).
ROLE_DIVISION: dict = {
    "super_admin": None, "owner": None,
    "sales_manager": "sales_marketing",
    "marketing_admin": "sales_marketing",
    "sales": "sales_marketing",
    "project_manager": "technical",
    "site_engineer": "technical",
    "dm_supervisor": "digital_marketing",
    "dm_staff": "digital_marketing",
    "finance_manager": "finance",
    "finance": "finance",
    "legal_admin": None,
}

ROLE_LEVEL: dict = {
    "super_admin": "owner", "owner": "owner",
    "sales_manager": "supervisor", "marketing_admin": "staff", "sales": "staff",
    "project_manager": "supervisor", "site_engineer": "staff",
    "dm_supervisor": "supervisor", "dm_staff": "staff",
    "finance_manager": "supervisor", "finance": "staff",
    "legal_admin": "supervisor",
}

DIVISION_LABEL = {o["value"]: o["label"] for o in GROUPS_P29["division"]["options"]}
