"""metrics — lapisan metrik BI (Fase 44), acuan `docs/v2/31_ANALYTICS_BI_SPEC.md`.

SATU metrik = SATU fungsi murni yang mengembalikan bentuk baku `base.result(...)`. Alasannya
bukan kerapian: sebelum lapisan ini, angka yang sama dihitung ulang di beberapa layar dan
mulai berbeda ("AR di beranda" vs "AR di laporan"). Sekarang setiap angka punya SATU rumus
yang bisa diuji sendiri, dan setiap angka WAJIB mengaku kalau datanya belum lengkap.

Registry di bawah adalah KAMUS METRIK yang dipakai:
  * `GET /api/analytics/metrics` (kamus untuk layar & audit),
  * dashboard per persona (`persona`),
  * job snapshot harian (`snapshot`),
  * gate `verify_analytics.py` (memeriksa tiap metrik menepati kontraknya).

Metrik yang BELUM bisa dihitung karena datanya memang belum ada di sistem TIDAK dihapus dari
kamus — ia tetap terdaftar dan mengembalikan `value=None` + `missing=[...]`, sehingga peta
kekosongan data terlihat (itu informasi, bukan kekurangan yang perlu disembunyikan).
"""
from metrics import budget as _budget
from metrics import leads as _leads
from metrics import marketing as _marketing
from metrics import pricing as _pricing
from metrics import project as _project
from metrics import rab as _rab
from metrics import sales as _sales
from metrics import team as _team
from metrics.base import PERSONAS, UNITS, result  # noqa: F401  (re-export kontrak)

MODULES = (_sales, _leads, _marketing, _project, _team, _budget, _pricing, _rab)

REGISTRY: dict = {}
for _m in MODULES:
    for _code, _spec in _m.METRICS.items():
        if _code in REGISTRY:
            raise RuntimeError(f"kode metrik kembar: {_code}")
        REGISTRY[_code] = {**_spec, "module": _m.__name__.rsplit(".", 1)[-1]}


def codes(persona: str = None) -> list:
    """Kode metrik (opsional difilter per persona dashboard)."""
    return [c for c, s in REGISTRY.items() if not persona or s["persona"] == persona]


def catalog(persona: str = None) -> list:
    """Kamus metrik untuk layar: kode, nama, rumus, satuan, persona, kebutuhan data."""
    out = []
    for code in codes(persona):
        spec = REGISTRY[code]
        out.append({
            "code": code, "label": spec["label"], "persona": spec["persona"],
            "unit": spec["unit"], "formula": spec.get("formula"),
            "requires": spec.get("requires") or [], "drill": spec.get("drill"),
            "module": spec["module"], "snapshot": bool(spec.get("snapshot")),
        })
    return sorted(out, key=lambda r: r["code"])


async def compute(code: str, **kwargs) -> dict:
    """Hitung satu metrik. Argumen tak dikenal DIBUANG (setiap metrik memakai apa yang perlu)."""
    spec = REGISTRY.get(code)
    if not spec:
        raise ValueError(f"Metrik '{code}' tidak ada di kamus metrik.")
    return await spec["fn"](**kwargs)


async def compute_many(code_list: list, **kwargs) -> dict:
    """Beberapa metrik sekaligus -> {kode: hasil}. Kegagalan satu metrik TIDAK menjatuhkan
    seluruh dashboard: yang gagal dilaporkan sebagai metrik tak lengkap dengan pesannya,
    supaya satu bug tidak membuat halaman kosong tanpa penjelasan."""
    out = {}
    for code in code_list:
        try:
            out[code] = await compute(code, **kwargs)
        except Exception as exc:  # noqa: BLE001 — dilaporkan, bukan disembunyikan
            spec = REGISTRY.get(code) or {}
            out[code] = result(code, None, label=spec.get("label") or code,
                               unit=spec.get("unit") or "count",
                               missing=[f"perhitungan gagal: {exc}"],
                               note="Metrik ini gagal dihitung — laporkan ke pengelola sistem.")
    return out
