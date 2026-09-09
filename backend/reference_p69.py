"""SSOT reference registry — TAMBAHAN Fase 69 (mesin harga: skema diskon, promo, kupon).

Diskon TIDAK lagi diketik bebas: nilainya lahir dari aturan yang dikonfigurasi (skema
diskon / promo / kupon). Kosakata jenis nilai dan status pemakaian kupon hidup di registry
supaya layar, gate, dan laporan menyebutnya dengan kata yang sama.
"""


def _o(value: str, label: str) -> dict:
    return {"value": value, "label": label}


GROUPS_P69: dict = {
    "discount_kind": {
        "label": "Jenis Nilai Potongan", "strict": True, "options": [
            _o("percent", "Persen dari harga"),
            _o("amount", "Nominal tetap (Rp)"),
        ],
    },
    "pricing_rule_kind": {
        "label": "Jenis Aturan Harga", "strict": True, "options": [
            _o("discount_scheme", "Skema diskon"),
            _o("promo", "Promo"),
            _o("coupon", "Kupon"),
        ],
    },
    "coupon_redemption_state": {
        "label": "Status Pemakaian Kupon", "strict": True, "options": [
            _o("used", "Terpakai"),
            _o("released", "Dilepas (transaksi batal)"),
        ],
    },
    # Fase 88C: potongan MENUJU komponen tertentu — bukan selalu memangkas harga total.
    "discount_target": {
        "label": "Sasaran Potongan", "strict": True, "options": [
            _o("price", "Harga jual (total kewajiban)"),
            _o("dp", "Uang muka / DP (termin pertama)"),
            _o("booking_fee", "Booking fee"),
            _o("cost", "Komponen biaya all-in (BPHTB, notaris, dll.)"),
        ],
    },
    "handover_settlement_policy": {
        "label": "Kebijakan Pelunasan sebelum BAST", "strict": True, "options": [
            _o("wajib_lunas", "Wajib lunas (menahan BAST)"),
            _o("minimal_persen", "Minimal persen terbayar"),
            _o("peringatan", "Hanya peringatan"),
        ],
    },
}
