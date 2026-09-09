"""reference_p44.py — SSOT kosakata TAMBAHAN Fase 44 (Analitik & BI).

Alasan grup-grup ini ada di SSOT, bukan diketik di layar:
  * `metric_persona` dipakai DUA kali (nama tab dashboard dan pengelompokan kamus metrik);
    kalau ditulis dua kali, tab "Kinerja Tim" bisa berbeda dengan judul kelompok metriknya.
  * `metric_state` adalah kosakata KEJUJURAN ANGKA untuk BI — kelanjutan `ads_cost_status`
    Fase 43, tetapi berlaku untuk SEMUA metrik: `lengkap` (semua input ada), `sebagian`
    (dihitung dari sebagian baris — angkanya boleh tampil TAPI wajib berlabel), `kosong`
    (input tidak ada — dilarang menampilkan angka).
  * `metric_unit` menentukan cara angka digambar (rupiah/persen/hari/rasio). Tanpa SSOT,
    satu metrik bisa tampil "53.7" di satu tempat dan "Rp 53,7" di tempat lain.
  * `analytics_granularity` & `analytics_period` menyeragamkan pilihan rentang di 5 dashboard.
  * `cac_component` membuat komposisi CAC bisa DIPILIH pemakai (Dok 31 LED-08) dengan
    kosakata yang sama di backend & layar.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P44: dict = {
    "metric_persona": {
        "label": "Dashboard Analitik", "strict": True, "options": [
            _o("eksekutif", "Eksekutif"), _o("penjualan", "Penjualan & Lead"),
            _o("marketing", "Marketing"), _o("proyek", "Proyek & Biaya"),
            _o("tim", "Kinerja Tim"),
        ],
    },
    "metric_state": {
        "label": "Kelengkapan Angka", "strict": True, "options": [
            _o("lengkap", "Data lengkap"),
            _o("sebagian", "Dihitung dari sebagian data"),
            _o("kosong", "Data belum ada"),
        ],
    },
    "metric_unit": {
        "label": "Satuan Metrik", "strict": True, "options": [
            _o("count", "Jumlah"), _o("idr", "Rupiah"), _o("pct", "Persen"),
            _o("days", "Hari"), _o("hours", "Jam"), _o("ratio", "Rasio"),
            _o("text", "Teks"),
        ],
    },
    "analytics_granularity": {
        "label": "Kerapatan Waktu", "strict": True, "options": [
            _o("day", "Harian"), _o("week", "Mingguan"), _o("month", "Bulanan"),
        ],
    },
    "analytics_period": {
        "label": "Rentang Analitik", "strict": True, "options": [
            _o("7d", "7 hari terakhir"), _o("30d", "30 hari terakhir"),
            _o("90d", "90 hari terakhir"), _o("ytd", "Tahun berjalan"),
            _o("all", "Seluruh data"),
        ],
    },
    "cac_component": {
        "label": "Komponen CAC", "strict": True, "options": [
            _o("ads", "Biaya iklan"), _o("partner", "Fee mitra disetujui"),
            _o("opex", "Biaya operasional marketing"),
        ],
    },
    "analytics_dimension": {
        "label": "Dimensi Analisis", "strict": True, "options": [
            _o("source", "Sumber lead"), _o("campaign", "Kampanye"),
            _o("partner", "Mitra"), _o("sales", "Sales"),
        ],
    },
    "demography_dimension": {
        "label": "Dimensi Demografi", "strict": True, "options": [
            _o("age", "Usia"), _o("occupation", "Pekerjaan"), _o("income", "Penghasilan"),
            _o("domicile", "Domisili"), _o("dependents", "Tanggungan"),
        ],
    },
}
