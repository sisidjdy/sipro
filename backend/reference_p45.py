"""reference_p45.py — SSOT kosakata TAMBAHAN Fase 45 (Target Proyek & Budget/RAB).

Kenapa grup-grup ini tinggal di SSOT dan bukan diketik di layar:

  * `target_method` dipakai TIGA kali (validasi payload, label pilihan di dialog target, dan
    penjelasan rumus di pratinjau dampak). Kalau ditulis ulang, "Linear sisa" di dropdown bisa
    berbeda dengan metode yang benar-benar dijalankan mesin — dan pemakai tidak akan pernah
    tahu angka targetnya datang dari rumus yang mana.
  * `budget_category` SENGAJA `dynamic` (keputusan D6 pada `docs/v2/32` §3): admin boleh
    menambah kategori biaya tanpa ubah kode. Nilai bawaan tetap ada di sini supaya sistem
    punya kerangka akun yang masuk akal sejak hari pertama.
  * `budget_match_rule` adalah kosakata KEJUJURAN untuk anggaran: satu item anggaran harus
    menyatakan DARI MANA realisasinya diambil. Tanpa ini, "realisasi" hanya angka yang muncul
    tanpa asal — dan itu tepat cacat yang fase ini ada untuk menutup.
  * `budget_health` menyeragamkan ambang status (aman / waspada / overbudget) di 3 lapis
    tampilan + notifikasi + tugas otomatis, sehingga satu proyek tidak bisa disebut "waspada"
    di kartu tetapi "aman" di tabel.
  * `cost_source` adalah daftar jenis dokumen sumber pada drill lapis-3. Daftar ini juga
    dipakai laporan "biaya belum terpetakan", jadi harus satu.
  * `target_basis` & `target_scope` merekam keputusan D6 ("basis unit DAN pendapatan",
    "cakupan proyek, opsional cluster/sales").
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P45: dict = {
    "target_method": {
        "label": "Metode Target", "strict": True, "options": [
            _o("linear_remaining", "Linear sisa (bawaan)"),
            _o("s_curve", "Kurva-S (bobot per bulan)"),
            _o("manual", "Manual per bulan"),
            _o("velocity_forecast", "Proyeksi kecepatan jual"),
            _o("revenue_first", "Pendapatan dulu (turunkan ke unit)"),
        ],
    },
    "target_status": {
        "label": "Status Target", "strict": True, "options": [
            _o("draft", "Draf"), _o("active", "Aktif"), _o("closed", "Ditutup"),
        ],
    },
    "target_basis": {
        "label": "Basis Target", "strict": True, "options": [
            _o("unit", "Unit terjual"), _o("revenue", "Pendapatan"),
            _o("both", "Unit dan pendapatan"),
        ],
    },
    "target_scope": {
        "label": "Cakupan Target", "strict": True, "options": [
            _o("project", "Proyek"), _o("cluster", "Cluster"), _o("sales", "Sales (per orang)"),
        ],
    },
    "target_recalc_mode": {
        "label": "Penyesuaian Target", "strict": True, "options": [
            _o("monthly", "Tiap awal bulan (dinamis)"),
            _o("manual", "Hanya bila diminta"),
        ],
    },
    "budget_category": {
        # dynamic=True → kategori yang sudah dipakai di DB ikut tampil, sehingga admin bisa
        # MENAMBAH kategori (keputusan D6) tanpa menunggu rilis kode.
        "label": "Kategori Anggaran", "strict": False, "dynamic": True,
        "source": {"collection": "budget_items", "field": "category"},
        "options": [
            _o("lahan", "Lahan"), _o("konstruksi", "Konstruksi (RAB)"),
            _o("prasarana", "Prasarana & Fasum"), _o("perizinan", "Perizinan"),
            _o("operasional", "Operasional"), _o("marketing", "Marketing"),
            _o("komisi_fee", "Komisi & Fee Mitra"), _o("pembiayaan", "Pembiayaan"),
            _o("pajak", "Pajak"), _o("overhead", "Overhead"), _o("lainnya", "Lainnya"),
        ],
    },
    "budget_match_rule": {
        "label": "Cara Mencocokkan Realisasi", "strict": True, "options": [
            _o("by_boq_item", "Dari item RAB (rantai konstruksi)"),
            _o("by_gl_account", "Dari akun buku besar"),
            _o("by_cost_ref", "Dari dokumen yang menyebut item ini"),
            _o("manual", "Dicatat manual (beralasan)"),
        ],
    },
    "budget_period": {
        "label": "Periode Anggaran", "strict": True, "options": [
            _o("project", "Sepanjang proyek"), _o("monthly", "Bulanan"),
        ],
    },
    "budget_health": {
        "label": "Status Anggaran", "strict": True, "options": [
            _o("aman", "Aman"), _o("waspada", "Waspada (mendekati batas)"),
            _o("overbudget", "Overbudget"), _o("kosong", "Belum ada anggaran"),
        ],
    },
    "cost_source": {
        "label": "Jenis Dokumen Biaya", "strict": True, "options": [
            _o("purchase_order", "Pesanan Pembelian (PO)"),
            _o("ap_invoice", "Tagihan Vendor (AP)"),
            _o("progress_claim", "Termin Subkontraktor"),
            _o("spk_scope", "Lingkup SPK (borongan)"),
            _o("material_txn", "Pemakaian Material"),
            _o("journal_entry", "Jurnal Buku Besar"),
            _o("cash_advance", "Kas Bon"),
            _o("marketing_fee", "Fee Mitra"),
            _o("commission", "Komisi Sales"),
            _o("tax_record", "Catatan Pajak"),
            _o("loan_payment", "Angsuran Pembiayaan"),
            _o("manual_entry", "Pencatatan Manual"),
        ],
    },
}
