"""KATALOG TEMPLATE JADWAL PEMBANGUNAN (Fase 31) — default yang bisa dikonfigurasi.

Sumber isi: standar pelaksanaan rumah tapak 1 lantai (60 hari kerja / 9 minggu) yang
dipakai owner, termasuk **hold point** dan **waktu tunggu kritis** yang paling sering
menyebabkan cacat bangunan:

    Pondasi → Sloof        : 1–2 hari
    Cor sloof → Bata       : 3–7 hari
    Bata → Plester         : 3–5 hari
    Plester → Acian        : 2–3 hari
    Acian → Cat            : 7–14 hari
    Atap → Plafon          : setelah tes siram (tidak bocor)
    Keramik → Sanitair     : setelah nat kering

Template ini SEED AWAL: supervisor (Manajer Proyek/owner) boleh menduplikasi lalu
mengubah durasi, bobot, waktu tunggu, checklist, dan jumlah foto wajib lewat UI —
tanpa menyentuh kode. `unit_types` memakai nilai SSOT grup `unit_type`.
"""

SITE = "site_engineer"
PM = "project_manager"


def _s(code, week, name, day_from, day_to, weight, category, *, pred=(), wait=0,
       wait_reason=None, hold=False, hold_note=None, photos=2, checks=(), tasks=(),
       role=SITE, verify_role=PM, handover=False) -> dict:
    """Satu item pekerjaan. `checks` = [(teks, kritis?)] — item kritis WAJIB lulus."""
    return {
        "code": code, "week": week, "name": name, "day_from": day_from, "day_to": day_to,
        "weight": float(weight), "work_category": category,
        "predecessors": list(pred), "wait_days": wait, "wait_reason": wait_reason,
        "hold_point": hold, "hold_note": hold_note, "min_photos": photos,
        "checklist": [{"code": f"{code}-C{i + 1}", "text": t, "critical": bool(c)}
                      for i, (t, c) in enumerate(checks)],
        "tasks": list(tasks), "assignee_role": role, "verify_role": verify_role,
        "handover_gate": handover,
    }


# ============================ RUMAH TAPAK 1 LANTAI — 60 HARI ============================
RUMAH_9W = {
    "code": "RUMAH-9W",
    "name": "Rumah Tapak 1 Lantai — 9 Minggu (60 hari kerja)",
    "unit_types": ["Tipe 36/72", "Tipe 45/90", "Tipe 54/105", "Tipe 70/120"],
    "calendar_mode": "working_days",
    "work_days_per_week": 6,
    "description": ("Urutan pelaksanaan rumah tapak dengan hold point & waktu tunggu "
                    "kritis (pondasi→sloof, sloof→bata, bata→plester, plester→acian, "
                    "acian→cat, atap→plafon, keramik→sanitair)."),
    "steps": [
        # ---------------- MINGGU 1 — PERSIAPAN + PONDASI ----------------
        _s("W1-01", 1, "Pekerjaan persiapan (pembersihan, pengukuran, bowplank)", 1, 2, 2,
           "persiapan", photos=2,
           tasks=["Pembersihan lokasi", "Pengukuran", "Pemasangan bowplank"],
           checks=[("As bangunan sesuai siteplan", True),
                   ("Elevasi lantai aman dari jalan & drainase", True),
                   ("Bowplank kuat, siku, dan tidak mudah bergeser", False)]),
        _s("W1-02", 1, "Pekerjaan tanah & pondasi (galian, urugan pasir, batu belah)", 3, 7, 8,
           "struktur", pred=["W1-01"], photos=3, hold=True,
           hold_note=("HOLD POINT: tidak boleh lanjut sloof sebelum pondasi benar-benar "
                      "terkunci (pasangan batu belah penuh, tidak ada rongga)."),
           tasks=["Galian pondasi", "Urugan pasir", "Pasangan batu belah"],
           checks=[("Kedalaman & lebar galian sesuai gambar", True),
                   ("Urugan pasir dipadatkan dan rata", False),
                   ("Pasangan batu belah terkunci penuh, spesi mengisi rongga", True),
                   ("Tidak ada bagian pondasi yang menggantung/ambles", True)]),
        # ---------------- MINGGU 2 — STRUKTUR BAWAH ----------------
        _s("W2-01", 2, "Pembesian & bekisting sloof + kolom praktis", 8, 10, 6,
           "struktur", pred=["W1-02"], wait=2,
           wait_reason="Pondasi batu kali minimal 1–2 hari sebelum sloof dikerjakan",
           photos=3,
           tasks=["Pembesian sloof", "Pembesian kolom praktis", "Pemasangan bekisting"],
           checks=[("Diameter & jumlah besi sesuai gambar", True),
                   ("Beton decking (selimut beton) terpasang", True),
                   ("Bekisting kokoh, lurus, tidak bocor", False)]),
        _s("W2-02", 2, "Pengecoran sloof, kolom praktis & talang beton", 11, 11, 6,
           "struktur", pred=["W2-01"], photos=2,
           tasks=["Pengecoran sloof", "Pengecoran kolom praktis", "Talang beton"],
           checks=[("Mutu/slump beton sesuai spesifikasi", True),
                   ("Pengecoran padat, tidak keropos/segregasi", True),
                   ("Tanggal & jam pengecoran dicatat", True)]),
        _s("W2-03", 2, "Curing beton & pembongkaran bekisting", 12, 14, 3,
           "struktur", pred=["W2-02"], wait=1,
           wait_reason="Bekisting samping minimal 24 jam setelah pengecoran",
           photos=2, hold=True,
           hold_note=("HOLD POINT: bekisting jangan dibuka/dibebani terlalu cepat — "
                      "samping 24 jam, beban berat 7 hari, kuat optimal 28 hari."),
           tasks=["Perawatan beton (curing)", "Buka bekisting samping"],
           checks=[("Curing disiram/ditutup minimal 7 hari", True),
                   ("Tidak ada retak susut besar / keropos", True),
                   ("Tanggal pembongkaran bekisting dicatat", False)]),
        # ---------------- MINGGU 3 — DINDING ----------------
        _s("W3-01", 3, "Pasangan dinding bata merah", 15, 21, 8,
           "arsitektur", pred=["W2-03"], wait=3,
           wait_reason="Cor sloof minimal 3–7 hari sebelum pasangan bata dimulai",
           photos=3,
           tasks=["Pasangan bata merah", "Kolom praktis lanjutan"],
           checks=[("Pasangan tegak, lurus, dan siku", True),
                   ("Spesi terisi penuh (tidak ada rongga)", True),
                   ("Angkur kolom praktis terpasang tiap 6 lapis", False)]),
        _s("W3-02", 3, "Jalur plumbing & conduit listrik tanam (sebelum plester)", 15, 21, 4,
           "mep", pred=["W3-01"], photos=3, hold=True,
           hold_note=("HOLD POINT: jangan plester sebelum jalur plumbing & conduit tanam "
                      "selesai, diuji, dan difoto sebagai as-built."),
           tasks=["Jalur air bersih & kotor tanam", "Conduit listrik tanam"],
           checks=[("Jalur air diuji tekan tanpa kebocoran", True),
                   ("Conduit utuh, tidak tertekuk/pecah", True),
                   ("Foto as-built jalur diambil sebelum ditutup", True)]),
        # ---------------- MINGGU 4 — RING BALOK + ATAP ----------------
        _s("W4-01", 4, "Ring balok & ring gevel", 22, 24, 6,
           "struktur", pred=["W3-01", "W3-02"], photos=2,
           tasks=["Pembesian & bekisting ring balk", "Pengecoran ring balk", "Ring gevel"],
           checks=[("Pembesian ring balk sesuai gambar", True),
                   ("Pengecoran padat & elevasi rata", True),
                   ("Angkur kuda-kuda disiapkan", False)]),
        _s("W4-02", 4, "Rangka atap baja ringan, penutup atap, lisplank", 25, 27, 8,
           "arsitektur", pred=["W4-01"], wait=3,
           wait_reason="Ring balok perlu mengeras minimal 3 hari sebelum dibebani rangka atap",
           photos=4, hold=True,
           hold_note=("HOLD POINT: jangan lanjut plafon bila atap masih bocor — wajib TES "
                      "SIRAM AIR dan cek kemiringan talang."),
           tasks=["Rangka atap baja ringan", "Genteng metal / atap spandek", "Lisplank"],
           checks=[("Jarak kuda-kuda & reng sesuai spesifikasi", True),
                   ("Sambungan/screw lengkap dan kencang", False),
                   ("Tes siram air: tidak ada kebocoran", True),
                   ("Kemiringan talang mengalir, tidak menggenang", True)]),
        # ---------------- MINGGU 5 — PLESTER + ACIAN ----------------
        _s("W5-01", 5, "Plester dinding", 28, 32, 6,
           "arsitektur", pred=["W3-02", "W4-02"], wait=3,
           wait_reason="Mortar bata harus stabil 3–5 hari agar plester tidak retak rambut",
           photos=3,
           tasks=["Plester dinding dalam", "Plester dinding luar"],
           checks=[("Permukaan rata, tegak, tidak bergelombang", True),
                   ("Sudut siku dan tajam", False),
                   ("Tidak ada bagian kosong/berongga saat diketuk", True)]),
        _s("W5-02", 5, "Acian dinding", 33, 35, 4,
           "arsitektur", pred=["W5-01"], wait=3,
           wait_reason="Plester perlu 2–3 hari sebelum diaci",
           photos=2, hold=True,
           hold_note=("HOLD POINT: jangan mengecat saat dinding masih basah — acian minimal "
                      "7–14 hari sebelum cat (risiko cat menggelembung, lembab, jamur)."),
           tasks=["Acian dinding dalam", "Acian dinding luar"],
           checks=[("Acian halus, tanpa retak rambut", True),
                   ("Tidak ada bagian mengelupas / berdebu", False)]),
        # ---------------- MINGGU 6 — PLAFON + KUSEN ----------------
        _s("W6-01", 6, "Plafon (rangka hollow, gypsum, list)", 36, 38, 5,
           "arsitektur", pred=["W4-02"], photos=2,
           tasks=["Rangka hollow", "Pemasangan gypsum", "List gypsum"],
           checks=[("Rangka hollow rata & kuat (tidak melendut)", True),
                   ("Sambungan gypsum di-compound rapi", False),
                   ("List gypsum lurus & rapat ke dinding", False)]),
        _s("W6-02", 6, "Kusen, daun pintu, jendela & kaca", 39, 41, 5,
           "arsitektur", pred=["W5-02"], photos=3,
           tasks=["Kusen pintu", "Daun pintu", "Kusen jendela", "Kaca"],
           checks=[("Kusen tegak, terkunci, dan tidak goyang", True),
                   ("Pintu & jendela menutup rapat, kunci berfungsi", True),
                   ("Kaca tanpa gores/retak dan sealant rapi", False)]),
        # ---------------- MINGGU 7 — KERAMIK + SANITASI ----------------
        _s("W7-01", 7, "Keramik lantai, dinding KM & backsplash dapur", 42, 45, 7,
           "finishing", pred=["W5-02", "W6-01"], photos=4,
           tasks=["Keramik lantai utama", "Keramik kamar mandi",
                  "Keramik dinding KM", "Keramik backsplash dapur"],
           checks=[("Nat lurus, seragam, dan terisi penuh", True),
                   ("Tidak kopong saat diketuk", True),
                   ("Kemiringan lantai KM mengarah ke floor drain", True)]),
        _s("W7-02", 7, "Sanitasi & jalur air bersih (closet, kran, sink, septictank)", 46, 47, 5,
           "mep", pred=["W7-01"], wait=1,
           wait_reason="Nat keramik harus kering sebelum pemasangan sanitair",
           photos=3,
           tasks=["Closet", "Kran", "Sink dapur", "Septictank & resapan", "Jalur air bersih"],
           checks=[("Tes aliran air lancar di semua titik", True),
                   ("Tidak ada kebocoran pada sambungan", True),
                   ("Septictank & resapan sesuai spesifikasi", False)]),
        # ---------------- MINGGU 8 — LISTRIK + CAT + LUAR ----------------
        _s("W8-01", 8, "Instalasi listrik (lampu, saklar, stop kontak)", 48, 50, 4,
           "mep", pred=["W3-02", "W6-01"], photos=3,
           tasks=["Lampu", "Saklar", "Stop kontak", "Pengujian titik"],
           checks=[("Semua titik diuji dan menyala", True),
                   ("Tidak ada kabel terbuka / sambungan liar", True),
                   ("MCB & grounding sesuai spesifikasi", True)]),
        _s("W8-02", 8, "Pengecatan interior, eksterior, plafon & lisplank", 51, 53, 5,
           "finishing", pred=["W5-02", "W6-01"], wait=7,
           wait_reason="Acian minimal 7–14 hari agar dinding kering sebelum dicat",
           photos=3, hold=True,
           hold_note="HOLD POINT: dinding wajib kering (uji lembab) sebelum cat dasar.",
           tasks=["Cat interior", "Cat eksterior", "Cat plafon", "Cat lisplank"],
           checks=[("Dinding kering saat diuji kelembaban", True),
                   ("Cat rata minimal 2 lapis, tidak belang", True),
                   ("Tidak ada cipratan pada kusen/keramik", False)]),
        _s("W8-03", 8, "Pekerjaan luar (carport, dinding samping, taman)", 54, 54, 3,
           "lansekap", pred=["W8-02"], photos=2,
           tasks=["Carport", "Dinding samping", "Taman"],
           checks=[("Carport rata, air tidak menggenang", True),
                   ("Area luar bersih dan rapi", False)]),
        # ---------------- MINGGU 9 — FINAL CHECK ----------------
        _s("W9-01", 9, "Pembersihan akhir & perbaikan defect", 55, 58, 3,
           "finishing", pred=["W8-01", "W8-02", "W8-03"], photos=3,
           tasks=["Pembersihan akhir", "Repair defect / punch list"],
           checks=[("Semua temuan punch list sudah ditutup", True),
                   ("Bebas sisa material & puing", True)]),
        _s("W9-02", 9, "Final QC & siap akad / serah terima", 59, 60, 2,
           "finishing", pred=["W9-01"], photos=4, hold=True, handover=True,
           hold_note=("HOLD POINT: unit tidak boleh dinyatakan siap serah terima sebelum "
                      "Final QC lulus (air, listrik, bocor, kunci, dokumen)."),
           tasks=["Final QC", "Serah terima kunci & dokumen"],
           checks=[("Air & listrik berfungsi normal", True),
                   ("Tidak ada kebocoran atap/plumbing", True),
                   ("Kunci, dokumen, dan manual siap diserahkan", True),
                   ("Pembeli/QC menandatangani hasil final", False)]),
    ],
}

# ============================ RUKO 2 LANTAI — 90 HARI ============================
RUKO_14W = {
    "code": "RUKO-14W",
    "name": "Ruko 2 Lantai — 15 Minggu (90 hari kerja)",
    "unit_types": ["Ruko"],
    "calendar_mode": "working_days",
    "work_days_per_week": 6,
    "description": ("Ruko 2 lantai: tambahan plat lantai & tangga beton dengan waktu tunggu "
                    "bekisting plat yang lebih panjang (beban berat 7–14 hari)."),
    "steps": [
        _s("R-01", 1, "Persiapan & pengukuran (bowplank, direksi keet)", 1, 2, 2,
           "persiapan", photos=2,
           tasks=["Pembersihan lokasi", "Pengukuran", "Bowplank"],
           checks=[("As bangunan sesuai siteplan & GSB", True),
                   ("Elevasi lantai aman dari jalan/drainase", True)]),
        _s("R-02", 1, "Tanah, footplat & pondasi batu belah", 3, 8, 8,
           "struktur", pred=["R-01"], photos=3, hold=True,
           hold_note="HOLD POINT: footplat & pondasi harus terkunci sebelum sloof.",
           tasks=["Galian footplat", "Pembesian footplat", "Cor footplat",
                  "Pasangan batu belah"],
           checks=[("Dimensi & kedalaman footplat sesuai gambar", True),
                   ("Pembesian footplat sesuai gambar", True),
                   ("Pasangan batu belah terkunci penuh", True)]),
        _s("R-03", 2, "Pembesian & bekisting sloof + kolom utama lantai 1", 9, 13, 7,
           "struktur", pred=["R-02"], wait=2,
           wait_reason="Pondasi minimal 1–2 hari sebelum sloof",
           photos=3,
           tasks=["Pembesian sloof", "Pembesian kolom utama", "Bekisting"],
           checks=[("Diameter & jumlah besi sesuai gambar", True),
                   ("Beton decking terpasang", True),
                   ("Bekisting kokoh & vertikal", False)]),
        _s("R-04", 2, "Pengecoran sloof & kolom lantai 1", 14, 16, 7,
           "struktur", pred=["R-03"], photos=3,
           tasks=["Cor sloof", "Cor kolom lantai 1"],
           checks=[("Mutu beton sesuai spesifikasi (uji slump)", True),
                   ("Pengecoran padat, tidak keropos", True),
                   ("Tanggal pengecoran dicatat", True)]),
        _s("R-05", 3, "Curing & bongkar bekisting kolom lantai 1", 17, 19, 3,
           "struktur", pred=["R-04"], wait=1,
           wait_reason="Bekisting samping minimal 24 jam",
           photos=2, hold=True,
           hold_note="HOLD POINT: bekisting kolom jangan dibuka sebelum 24 jam.",
           tasks=["Curing", "Bongkar bekisting"],
           checks=[("Curing dijaga minimal 7 hari", True),
                   ("Tidak ada keropos besar/retak struktural", True)]),
        _s("R-06", 4, "Dinding lantai 1 + jalur ME tanam", 20, 28, 8,
           "arsitektur", pred=["R-05"], wait=3,
           wait_reason="Cor sloof minimal 3–7 hari sebelum pasangan bata",
           photos=3, hold=True,
           hold_note="HOLD POINT: jalur ME tanam harus diuji & difoto sebelum ditutup.",
           tasks=["Pasangan bata lantai 1", "Jalur plumbing tanam", "Conduit listrik tanam"],
           checks=[("Pasangan tegak, lurus, siku", True),
                   ("Jalur air diuji tekan tanpa bocor", True),
                   ("Foto as-built jalur ME diambil", True)]),
        _s("R-07", 5, "Bekisting & pembesian plat lantai 2 + tangga", 29, 34, 8,
           "struktur", pred=["R-06"], photos=3,
           tasks=["Perancah & bekisting plat", "Pembesian plat lantai 2", "Pembesian tangga"],
           checks=[("Perancah kuat & tidak melendut", True),
                   ("Pembesian plat 2 lapis sesuai gambar", True),
                   ("Elevasi bekisting rata (waterpass)", True)]),
        _s("R-08", 6, "Pengecoran plat lantai 2 & tangga", 35, 36, 7,
           "struktur", pred=["R-07"], photos=3, hold=True,
           hold_note=("HOLD POINT: perancah plat tidak boleh dibongkar sebelum 7–14 hari "
                      "(beban berat) — risiko lendutan permanen."),
           tasks=["Cor plat lantai 2", "Cor tangga"],
           checks=[("Mutu beton sesuai spesifikasi", True),
                   ("Ketebalan plat sesuai gambar", True),
                   ("Tanggal pengecoran dicatat", True)]),
        _s("R-09", 6, "Curing plat & pembongkaran perancah", 37, 43, 3,
           "struktur", pred=["R-08"], wait=7,
           wait_reason="Plat lantai memikul beban berat: perancah minimal 7 hari",
           photos=2, hold=True,
           hold_note="HOLD POINT: dilarang membebani plat sebelum curing 7 hari selesai.",
           tasks=["Curing plat", "Bongkar perancah"],
           checks=[("Curing plat dijaga minimal 7 hari", True),
                   ("Tidak ada lendutan/retak pada plat", True)]),
        _s("R-10", 8, "Dinding lantai 2 + jalur ME tanam", 44, 52, 7,
           "arsitektur", pred=["R-09"], wait=3,
           wait_reason="Plat lantai 2 perlu 3 hari sebelum pasangan dinding di atasnya",
           photos=3,
           tasks=["Pasangan bata lantai 2", "Jalur plumbing & conduit lantai 2"],
           checks=[("Pasangan tegak, lurus, siku", True),
                   ("Jalur ME diuji & difoto sebelum ditutup", True)]),
        _s("R-11", 9, "Ring balok, rangka & penutup atap", 53, 60, 8,
           "arsitektur", pred=["R-10"], wait=3,
           wait_reason="Ring balok perlu mengeras 3 hari sebelum dibebani rangka atap",
           photos=4, hold=True,
           hold_note="HOLD POINT: tes siram air wajib lulus sebelum plafon dikerjakan.",
           tasks=["Ring balok", "Rangka atap", "Penutup atap", "Lisplank"],
           checks=[("Jarak kuda-kuda & reng sesuai spesifikasi", True),
                   ("Tes siram air: tidak bocor", True),
                   ("Talang & kemiringan mengalir benar", True)]),
        _s("R-12", 11, "Plester & acian 2 lantai", 61, 70, 8,
           "arsitektur", pred=["R-11"], wait=3,
           wait_reason="Mortar bata stabil 3–5 hari sebelum plester; acian 2–3 hari setelah plester",
           photos=4, hold=True,
           hold_note="HOLD POINT: acian minimal 7–14 hari sebelum pengecatan.",
           tasks=["Plester lantai 1 & 2", "Acian lantai 1 & 2"],
           checks=[("Permukaan rata, tegak, tidak bergelombang", True),
                   ("Acian halus tanpa retak rambut", True),
                   ("Tidak ada bagian kopong", True)]),
        _s("R-13", 12, "Plafon, kusen, rolling door & kaca", 71, 76, 6,
           "arsitektur", pred=["R-12"], photos=3,
           tasks=["Rangka & gypsum plafon", "Kusen & pintu", "Rolling door", "Kaca"],
           checks=[("Rangka plafon rata & kuat", True),
                   ("Rolling door berfungsi halus & terkunci", True),
                   ("Kaca tanpa gores/retak", False)]),
        _s("R-14", 13, "Keramik & sanitasi", 77, 81, 6,
           "finishing", pred=["R-13"], wait=1,
           wait_reason="Nat keramik harus kering sebelum sanitair dipasang",
           photos=4,
           tasks=["Keramik lantai 1 & 2", "Keramik KM", "Closet, kran, sink", "Septictank"],
           checks=[("Nat lurus & tidak kopong", True),
                   ("Kemiringan lantai KM ke floor drain benar", True),
                   ("Tes aliran air lancar tanpa bocor", True)]),
        _s("R-15", 14, "Instalasi listrik & pengecatan", 82, 86, 7,
           "mep", pred=["R-12", "R-13"], wait=7,
           wait_reason="Acian minimal 7–14 hari agar dinding kering sebelum dicat",
           photos=4, hold=True,
           hold_note="HOLD POINT: dinding wajib kering (uji lembab) sebelum cat.",
           tasks=["Lampu, saklar, stop kontak", "Panel & MCB", "Cat interior & eksterior"],
           checks=[("Semua titik listrik diuji & aman", True),
                   ("Grounding & MCB sesuai spesifikasi", True),
                   ("Cat rata minimal 2 lapis", True)]),
        _s("R-16", 15, "Final QC & siap serah terima", 87, 90, 5,
           "finishing", pred=["R-14", "R-15"], photos=4, hold=True, handover=True,
           hold_note="HOLD POINT: Final QC wajib lulus sebelum unit dinyatakan siap.",
           tasks=["Pembersihan akhir", "Repair defect", "Final QC", "Serah terima"],
           checks=[("Air & listrik berfungsi normal", True),
                   ("Tidak ada kebocoran", True),
                   ("Punch list tertutup semua", True),
                   ("Dokumen & kunci siap diserahkan", True)]),
    ],
}

DEFAULT_TEMPLATES = [RUMAH_9W, RUKO_14W]

# Tipe unit yang MEMANG tidak punya jadwal pembangunan (dijual sebagai tanah).
NO_BUILD_UNIT_TYPES = {"Kavling"}


def total_weight(tpl: dict) -> float:
    return round(sum(float(s.get("weight") or 0) for s in tpl.get("steps") or []), 2)


def by_code(code: str) -> dict:
    for t in DEFAULT_TEMPLATES:
        if t["code"] == code:
            return t
    return None
