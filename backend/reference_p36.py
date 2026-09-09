"""SSOT reference registry — TAMBAHAN Fase 36 (Kalender Jadwal & Master Kalender Kerja).

Alasan file terpisah sama seperti Fase 31/33/34/35: `reference.py` sudah menyentuh batas
gate compliance (<=800 baris). Grup di sini digabungkan ke `reference.GROUPS` sehingga
seluruh dropdown/label frontend tetap SATU sumber (`GET /api/reference`) — tidak ada peta
label yang diketik ulang di React (dilarang gate `audit_forms_deep` E5).

Fase 36 menutup dua kebutaan lama:
  1. Tenggat pekerjaan hanya terlihat per rumah / per daftar, sehingga BENTROK
     (satu mandor kebagian banyak tenggat di hari yang sama, tumpukan pekerjaan kritis,
     tenggat mendarat di hari libur) baru terasa setelah telat.
  2. Hari libur & pola hari kerja tidak punya master data: `build_templates.holidays`
     selalu kosong pada data nyata, jadi mesin jadwal menaruh tenggat di 17 Agustus / Idul Fitri
     dan tidak ada satu pun tempat admin bisa mengaturnya.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P36: dict = {
    # ---------------- jenis acara yang muncul di kalender ----------------
    # Dipakai sebagai FILTER di UI dan sebagai penanda tiap acara. Nilainya harus sama
    # dengan `build_calendar_view.KINDS` (dijaga gate verify_36).
    "calendar_event_kind": {
        "label": "Jenis Acara Kalender", "strict": True, "options": [
            _o("work_deadline", "Tenggat pekerjaan konstruksi"),
            _o("schedule_start", "Mulai pembangunan rumah"),
            _o("schedule_finish", "Target selesai rumah"),
            _o("inspection", "Inspeksi / QC terjadwal"),
            _o("punch", "Punch list jatuh tempo"),
            _o("task", "Tugas Work Hub tim proyek"),
        ],
    },
    # ---------------- jenis hari pada kalender kerja ----------------
    "calendar_day_kind": {
        "label": "Jenis Hari", "strict": True, "options": [
            _o("full", "Hari kerja penuh"),
            _o("half", "Setengah hari kerja"),
            _o("off", "Libur mingguan"),
            _o("holiday", "Hari libur (tanggal khusus)"),
        ],
    },
    # ---------------- jenis bentrok yang diperingatkan ----------------
    "calendar_conflict_kind": {
        "label": "Jenis Bentrok Jadwal", "strict": True, "options": [
            _o("overload", "Beban pelaksana menumpuk di satu hari"),
            _o("critical_stack", "Pekerjaan kritis/hold point menumpuk di satu hari"),
            _o("non_workday", "Tenggat jatuh pada hari libur / bukan hari kerja"),
        ],
    },
    # ---------------- pola hari kerja mingguan (master data) ----------------
    # Terpisah dari `calendar_day_kind` karena pola MINGGUAN tidak boleh bernilai
    # 'holiday' (hari libur adalah TANGGAL tertentu, bukan pola tiap minggu).
    "calendar_work_pattern": {
        "label": "Pola Hari Kerja", "strict": True, "options": [
            _o("full", "Hari kerja penuh"),
            _o("half", "Setengah hari kerja"),
            _o("off", "Libur mingguan"),
        ],
    },
    # ---------------- jenis hari libur (master data) ----------------
    "holiday_kind": {
        "label": "Jenis Hari Libur", "strict": True, "options": [
            _o("national", "Libur nasional"),
            _o("religious", "Hari besar keagamaan"),
            _o("company", "Libur perusahaan / cuti bersama"),
            _o("local", "Libur daerah / adat setempat"),
        ],
    },
    # ---------------- cakupan tampilan kalender ----------------
    "calendar_scope": {
        "label": "Cakupan Kalender", "strict": True, "options": [
            _o("project", "Satu proyek"),
            _o("all", "Semua proyek (portofolio)"),
        ],
    },
    # ---------------- cakupan PENGATURAN kalender kerja (master data) ----------------
    # Berbeda dari `calendar_scope` (yang mengatur TAMPILAN): grup ini menentukan dokumen
    # master mana yang sedang diubah. Dibuat setelah cacat nyata: dialog dulu diam-diam
    # menulis kalender KHUSUS PROYEK hanya karena halaman sedang menampilkan satu proyek,
    # dan itu menghapus seluruh hari libur nasional untuk proyek tersebut.
    "calendar_settings_scope": {
        "label": "Cakupan Pengaturan Kalender", "strict": True, "options": [
            _o("org", "Kalender organisasi (berlaku semua proyek)"),
            _o("project", "Kalender khusus proyek ini"),
        ],
    },
    # ---------------- asal sebuah hari libur pada kalender efektif ----------------
    "holiday_source": {
        "label": "Asal Hari Libur", "strict": True, "options": [
            _o("org", "Diwarisi dari kalender organisasi"),
            _o("project", "Khusus proyek ini"),
        ],
    },
}

EVENT_KINDS = tuple(o["value"] for o in GROUPS_P36["calendar_event_kind"]["options"])
DAY_KINDS = tuple(o["value"] for o in GROUPS_P36["calendar_day_kind"]["options"])
CONFLICT_KINDS = tuple(o["value"] for o in GROUPS_P36["calendar_conflict_kind"]["options"])
HOLIDAY_KINDS = tuple(o["value"] for o in GROUPS_P36["holiday_kind"]["options"])
EVENT_LABEL = {o["value"]: o["label"] for o in GROUPS_P36["calendar_event_kind"]["options"]}
