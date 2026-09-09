"""budget_engine.py — Fase 45: ANGGARAN & REALISASI 3 lapis (`docs/v2/32` §3 & §4).

Tugas modul ini: menjawab "berapa rencana, berapa komitmen, berapa realisasi, dan DARI MANA
angkanya" untuk satu proyek — dengan tiga aturan yang tidak bisa ditawar:

1. **Tidak ada dua kebenaran.** Item anggaran kategori `konstruksi` TIDAK menyimpan angka
   rencananya sendiri: `planned_amount` dihitung dari Σ `boq_items` yang ditaut (`docs/v2/32`
   §3). Realisasi konstruksi diambil dari rantai yang sudah dipakai layar Kendali Biaya
   (`spk_scope_items` + PO/AP), sehingga total di sini WAJIB tie-out dengan
   `opname.cost_control()` — dan gate memeriksanya.

2. **Tidak ada angka tanpa asal.** Setiap rupiah realisasi/komitmen membawa daftar dokumen
   penyusunnya (lapis 3). Σ dokumen = angka lapis 2 = angka lapis 1. Kalau tidak sama, itu
   kegagalan, bukan "pembulatan".

3. **0 ≠ belum ada data.** Proyek tanpa item anggaran TIDAK dilaporkan "Rp 0 (aman)" — ia
   dilaporkan `kosong` dengan menyebut apa yang kurang. Persentase dengan pembagi 0 = None.

Catatan penting soal DOUBLE COUNT (keputusan yang diambil sadar, bukan kelalaian):
`docs/v2/32` §4 menyebut pemakaian material sebagai sumber realisasi. Tetapi material yang
dibeli lewat PO sudah diakui saat tagihan vendor (AP) masuk; menjumlahkan pemakaiannya lagi
akan menghitung biaya yang sama dua kali. Karena itu pemakaian material ditampilkan sebagai
**angka pengendalian** (`material_usage`) dan hanya masuk realisasi bila dokumennya SECARA
EKSPLISIT menaut item anggaran (`by_cost_ref`) — mis. material dari stok awal yang tidak punya
PO. Alasannya dikirim ke layar, jadi pemakai tahu kenapa angkanya tidak dijumlahkan.
"""
import logging

import opname as op
from db import ORG_ID, db

logger = logging.getLogger("sipro.budget")

CONSTRUCTION = "konstruksi"
# PO yang masih menjadi KOMITMEN (sudah disahkan, belum tuntas ditagih).
PO_OPEN_STATUS = ("approved", "partially_received", "received")
# Tagihan vendor yang sudah menjadi BIAYA (dibatalkan/ditolak tidak dihitung).
AP_VOID_STATUS = ("cancelled", "rejected", "void", "draft")
CLAIM_REALIZED_STATUS = ("verified", "approved", "billed", "paid")
CLAIM_OPEN_STATUS = ("submitted", "under_review", "pending_approval")
HEALTH_EMPTY = "kosong"


def _i(v) -> int:
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def pct_of(part, whole):
    """Persen jujur: pembagi 0 → None (bukan 0%)."""
    if not whole:
        return None
    return round(part / whole * 100, 1)


def health_of(exposure: int, planned: int, alert_pct: float = 90) -> str:
    """Status anggaran (SSOT `budget_health`). Tanpa rencana → `kosong`, bukan `aman`."""
    if not planned:
        return HEALTH_EMPTY
    ratio = exposure / planned * 100
    if ratio > 100:
        return "overbudget"
    if ratio >= float(alert_pct or 90):
        return "waspada"
    return "aman"


def _doc(source: str, ref: str, label: str, amount: int, *, kind: str = "realisasi",
         date: str = None, link: str = None, status: str = None, note: str = None) -> dict:
    """Satu baris dokumen sumber untuk drill lapis 3."""
    return {"source": source, "ref": ref, "label": label, "amount": _i(amount), "kind": kind,
            "date": (date or "")[:10] or None, "link": link, "status": status, "note": note}


# ===================================================================== konstruksi (RAB)
async def enriched_scope(org: str, project_id: str) -> list:
    """Lingkup SPK yang sudah dilengkapi status pekerjaan lapangan — lewat `opname._enrich`.

    Kenapa memakai fungsi milik `opname` dan bukan membaca field sendiri: status
    `verified` pada lingkup SPK **tidak tersimpan** di dokumennya. Ia DITURUNKAN dari langkah
    jadwal yang ditaut (`build_items.status == verified` DAN ada `verified_by`) — yaitu
    "pekerjaannya sudah diperiksa manusia". POC Fase 45 menangkap kejadian nyata saat modul
    ini membaca `scope["verified"]` langsung: hasilnya 0 realisasi di mana-mana, sementara
    panel Kendali Biaya menampilkan Rp 30 juta. Memakai fungsi yang sama membuat dua layar
    itu mustahil berbeda.
    """
    scope = await db.spk_scope_items.find({"org_id": org, "project_id": project_id},
                                          {"_id": 0}).to_list(8000)
    if not scope:
        return []
    items = await db.build_items.find(
        {"org_id": org, "id": {"$in": [s.get("build_item_id") for s in scope]}},
        op.ITEM_FIELDS).to_list(8000)
    imap = {i["id"]: i for i in items}
    return [op._enrich(s, imap.get(s.get("build_item_id")) or {}) for s in scope]


async def construction_by_boq(org: str, project_id: str) -> dict:
    """Agregasi rantai konstruksi per `boq_item_id`.

    Kunci `None` menampung lingkup SPK yang BELUM ditaut ke item RAB — sengaja tidak dibuang,
    karena Σ seluruh kunci harus sama dengan `opname.cost_control()`; membuangnya akan membuat
    "realisasi RAB" terlihat lebih rapi daripada kenyataannya.
    """
    boq = await db.boq_items.find({"org_id": org, "project_id": project_id},
                                  {"_id": 0}).to_list(4000)
    scope = await enriched_scope(org, project_id)
    pos = await db.purchase_orders.find({"org_id": org, "project_id": project_id},
                                        {"_id": 0}).to_list(4000)
    out = {}

    def bucket(key):
        return out.setdefault(key, {"boq_item_id": key, "budget": 0, "contracted": 0,
                                    "verified": 0, "billed": 0, "po_committed": 0,
                                    "po_billed": 0, "docs": []})
    for b in boq:
        row = bucket(b["id"])
        row["budget"] += _i(b.get("amount"))
        row["cost_code"] = b.get("cost_code")
        row["category"] = b.get("category") or "lainnya"
        row["description"] = b.get("description")
    for s in scope:
        row = bucket(s.get("boq_item_id"))
        val = _i(s.get("value"))
        row["contracted"] += val
        verified = bool(s.get("verified"))
        row["verified"] += val if verified else 0
        row["billed"] += val if s.get("claim_id") else 0
        row["docs"].append(_doc(
            "spk_scope", s.get("spk_number") or s.get("spk_id"),
            f"{s.get('step_code') or '-'} {s.get('step_name') or ''} · unit "
            f"{s.get('unit_code') or '-'}", val,
            kind="realisasi" if verified else "komitmen",
            status="terverifikasi" if verified else "belum diverifikasi",
            link="/subcon", date=s.get("created_at")))
    for po in pos:
        total = _i(po.get("total"))
        billed = _i(po.get("billed_value"))
        open_po = po.get("status") in PO_OPEN_STATUS
        for line in po.get("items") or []:
            amount = _i(line.get("amount"))
            if not amount:
                continue
            share = amount / total if total else 0
            row = bucket(line.get("boq_item_id"))
            line_billed = _i(billed * share)
            row["po_billed"] += line_billed
            committed = max(0, amount - line_billed) if open_po else 0
            row["po_committed"] += committed
            if committed or line_billed:
                row["docs"].append(_doc(
                    "purchase_order", po.get("po_number"),
                    f"{line.get('description') or 'baris PO'} · {po.get('vendor') or '-'}",
                    committed or line_billed,
                    kind="komitmen" if committed else "realisasi",
                    status=po.get("status"), link="/procurement", date=po.get("created_at"),
                    note=("dialokasikan proporsional dari nilai PO"
                          if total and len(po.get("items") or []) > 1 else None)))
    return out


async def _ap_by_project(org: str, project_id: str) -> tuple:
    """Tagihan vendor proyek: (total realisasi, daftar dokumen)."""
    rows = await db.ap_invoices.find({"org_id": org, "project_id": project_id},
                                     {"_id": 0}).to_list(4000)
    total, docs = 0, []
    for inv in rows:
        if inv.get("status") in AP_VOID_STATUS:
            continue
        amount = _i(inv.get("claimed"))
        total += amount
        docs.append(_doc("ap_invoice", inv.get("no") or inv.get("id", "")[:8],
                         f"Tagihan {inv.get('vendor') or '-'} — {inv.get('note') or ''}".strip(),
                         amount, status=inv.get("status"), link="/finance?tab=ap",
                         date=inv.get("created_at")))
    return total, docs


async def _claims_by_project(org: str, project_id: str) -> tuple:
    """Termin subkon: realisasi hanya yang TERVERIFIKASI; yang masih diajukan = komitmen."""
    rows = await db.progress_claims.find({"org_id": org, "project_id": project_id},
                                         {"_id": 0}).to_list(4000)
    realized, committed, docs = 0, 0, []
    for c in rows:
        gross = _i(c.get("gross"))
        est = _i(c.get("gross_est"))
        if c.get("status") in CLAIM_REALIZED_STATUS and gross:
            realized += gross
            docs.append(_doc("progress_claim", c.get("claim_number"),
                             f"{c.get('period') or 'Termin'} — {c.get('subcontractor_name') or ''}",
                             gross, status=c.get("status"), link="/subcon",
                             date=c.get("created_at")))
        elif c.get("status") in CLAIM_OPEN_STATUS:
            committed += est
            docs.append(_doc("progress_claim", c.get("claim_number"),
                             f"{c.get('period') or 'Termin'} — {c.get('subcontractor_name') or ''}",
                             est, kind="komitmen", status=c.get("status"), link="/subcon",
                             date=c.get("created_at"),
                             note="nilai estimasi; belum diverifikasi opname"))
    return realized, committed, docs


# ===================================================================== buku besar (GL)
_SOURCE_PROJECT_FIELD = {
    "cash_advance": ("cash_advances", "project_id"),
    "marketing_fee": ("marketing_fees", "project_id"),
    "ap_bill": ("ap_invoices", "project_id"),
    "fixed_asset": ("fixed_assets", "project_id"),
    "asset_depreciation": ("asset_depreciations", "project_id"),
}


async def _project_of_entry(entry: dict, cache: dict) -> str:
    """Proyek sebuah jurnal: field langsung → dokumen sumbernya → lewat deal/unit.

    Jurnal di SIPRO tidak menyimpan `project_id` (rancangan lama). Daripada menebak atau
    menjumlahkan semuanya ke proyek mana pun, modul ini MENELUSURI dokumen sumbernya. Yang
    tetap tidak bisa ditelusuri dilaporkan sebagai "belum terpetakan" — bukan dibagi rata.
    """
    if entry.get("project_id"):
        return entry["project_id"]
    stype, sid = entry.get("source_type"), entry.get("source_id")
    if not sid:
        return None
    key = f"{stype}:{sid}"
    if key in cache:
        return cache[key]
    pid = None
    coll_field = _SOURCE_PROJECT_FIELD.get(stype)
    if coll_field:
        doc = await db[coll_field[0]].find_one({"id": sid}, {"_id": 0, coll_field[1]: 1})
        pid = (doc or {}).get(coll_field[1])
    elif stype in ("commission", "tax_accrual", "tax_setor", "receipt"):
        coll = {"commission": "commissions", "tax_accrual": "tax_records",
                "tax_setor": "tax_records", "receipt": "receipts"}[stype]
        doc = await db[coll].find_one({"id": sid}, {"_id": 0, "unit_id": 1, "deal_id": 1,
                                                    "project_id": 1})
        pid = (doc or {}).get("project_id")
        if not pid and (doc or {}).get("unit_id"):
            unit = await db.units.find_one({"id": doc["unit_id"]}, {"_id": 0, "project_id": 1})
            pid = (unit or {}).get("project_id")
        if not pid and (doc or {}).get("deal_id"):
            deal = await db.deals.find_one({"id": doc["deal_id"]},
                                           {"_id": 0, "project_id": 1, "unit_id": 1})
            pid = (deal or {}).get("project_id")
            if not pid and (deal or {}).get("unit_id"):
                unit = await db.units.find_one({"id": deal["unit_id"]},
                                               {"_id": 0, "project_id": 1})
                pid = (unit or {}).get("project_id")
    cache[key] = pid
    return pid


async def gl_expense_rows(org: str) -> list:
    """Semua baris jurnal berjenis beban, sudah dilengkapi proyek asalnya (bila bisa)."""
    entries = await db.journal_entries.find({"org_id": org}, {"_id": 0}).to_list(20000)
    cache, rows = {}, []
    for e in entries:
        pid = await _project_of_entry(e, cache)
        for line in e.get("lines") or []:
            if line.get("account_type") != "expense":
                continue
            amount = _i(line.get("debit")) - _i(line.get("credit"))
            if not amount:
                continue
            rows.append({
                "entry_id": e.get("id"), "entry_no": e.get("entry_no"), "date": e.get("date"),
                "account_code": line.get("account_code"), "account_name": line.get("account_name"),
                "amount": amount, "source_type": e.get("source_type"),
                "source_id": e.get("source_id"), "project_id": pid,
                "memo": line.get("memo") or e.get("memo"),
            })
    return rows


# ===================================================================== cost_ref & manual
COST_REF_SOURCES = [
    ("purchase_orders", "purchase_order", "po_number", "total", "/procurement"),
    ("ap_invoices", "ap_invoice", "no", "claimed", "/finance?tab=ap"),
    ("progress_claims", "progress_claim", "claim_number", "gross", "/subcon"),
    ("cash_advances", "cash_advance", "no", "expense_total", "/petty-cash"),
    ("marketing_fees", "marketing_fee", "no", "amount_gross", "/partners?hub=tagihan"),
    ("commissions", "commission", "unit_code", "amount", "/finance?tab=commissions"),
    ("tax_records", "tax_record", "type", "amount", "/tax"),
    # Fase 47D: upah harian tenaga kerja. Biaya upah dulu tidak pernah masuk realisasi
    # anggaran sama sekali (tidak ada dokumennya di sistem), padahal ia salah satu komponen
    # biaya konstruksi yang paling sering bocor.
    ("labor_payrolls", "labor_payroll", "no", "total", "/build?hub=lapangan"),
]
# `material_txns` SENGAJA TIDAK ada di daftar di atas. Ia punya penjaga sendiri
# (`_material_ref_docs`): pemakaian material hanya boleh masuk realisasi bila materialnya
# TIDAK pernah dibeli lewat PO pada proyek itu. Kalau ia dijadikan sumber biasa, material
# yang dibeli via PO akan terhitung dua kali — sekali saat tagihan vendor masuk, sekali saat
# dipakai. Uji-mutasi N13 membuktikan penjaga ini benar-benar bekerja.


def budget_ref_of(doc: dict) -> str:
    """Penanda item anggaran pada dokumen biaya (datar atau di dalam `cost_ref`)."""
    return doc.get("budget_item_id") or (doc.get("cost_ref") or {}).get("budget_item_id")


async def _material_ref_docs(org: str) -> dict:
    """Pemakaian material yang menaut item anggaran — DENGAN penjaga anti double-count.

    Aturannya: pemakaian material hanya menjadi realisasi bila materialnya **tidak pernah
    dibeli lewat PO** pada proyek itu (mis. material dari stok awal). Material yang dibeli
    lewat PO sudah diakui sebagai biaya saat tagihan vendor masuk; menjumlahkan pemakaiannya
    lagi berarti menghitung biaya yang sama dua kali. Yang ditolak TIDAK dibuang diam-diam —
    ia tetap muncul sebagai dokumen bersifat `informasi` dengan alasannya.
    """
    rows = await db.material_txns.find(
        {"org_id": org, "type": "out",
         "$or": [{"budget_item_id": {"$ne": None}},
                 {"cost_ref.budget_item_id": {"$ne": None}}]}, {"_id": 0}).to_list(4000)
    if not rows:
        return {}
    index, price_cache = {}, {}
    for t in rows:
        bid = budget_ref_of(t)
        if not bid:
            continue
        pid = t.get("project_id")
        if pid not in price_cache:
            price_cache[pid] = await material_prices(org, pid)
        prices = price_cache[pid]
        bought_via_po = t.get("material_id") in prices
        amount = _i(t.get("amount")) or _i(
            float(t.get("qty") or 0) * (prices.get(t.get("material_id")) or 0))
        index.setdefault(bid, []).append(_doc(
            "material_txn", t.get("ref") or t.get("id", "")[:8],
            t.get("note") or "Pemakaian material", amount,
            kind="informasi" if bought_via_po else "realisasi",
            status="sudah diakui lewat tagihan pembelian" if bought_via_po else "dari stok",
            link="/materials", date=t.get("created_at"),
            note=("TIDAK dijumlahkan (mencegah biaya terhitung dua kali): material ini "
                  "dibeli lewat PO, jadi biayanya sudah diakui saat tagihan vendor masuk"
                  if bought_via_po else
                  "material dari stok (tanpa PO pada proyek ini) — sah menjadi realisasi")))
    return index


async def cost_ref_index(org: str) -> dict:
    """`{budget_item_id: [dokumen…]}` dari SEMUA koleksi biaya yang menaut item anggaran."""
    index = {}
    for coll, source, ref_field, amount_field, link in COST_REF_SOURCES:
        query = {"org_id": org, "$or": [{"budget_item_id": {"$ne": None}},
                                        {"cost_ref.budget_item_id": {"$ne": None}}]}
        try:
            rows = await db[coll].find(query, {"_id": 0}).to_list(4000)
        except Exception:  # noqa: BLE001 — koleksi belum ada di database baru
            continue
        for d in rows:
            bid = budget_ref_of(d)
            if not bid:
                continue
            amount = _i(d.get(amount_field) or d.get("amount") or d.get("total"))
            kind = "komitmen" if (source == "purchase_order"
                                  and d.get("status") in PO_OPEN_STATUS
                                  and _i(d.get("billed_value")) < _i(d.get("total"))) \
                else "realisasi"
            index.setdefault(bid, []).append(_doc(
                source, str(d.get(ref_field) or d.get("id", ""))[:24],
                d.get("note") or d.get("purpose") or d.get("description") or source,
                amount, kind=kind, status=d.get("status"), link=link,
                date=d.get("created_at")))
    for bid, docs in (await _material_ref_docs(org)).items():
        index.setdefault(bid, []).extend(docs)
    return index


async def manual_index(org: str) -> dict:
    """Pencatatan manual (`budget_manual_entries`) — untuk item ber-`match_rule=manual`."""
    rows = await db.budget_manual_entries.find({"org_id": org}, {"_id": 0}).to_list(4000)
    index = {}
    for r in rows:
        index.setdefault(r.get("budget_item_id"), []).append(_doc(
            "manual_entry", r.get("ref_no") or r.get("id", "")[:8],
            r.get("note") or "Pencatatan manual", _i(r.get("amount")),
            kind=r.get("kind") or "realisasi", status="dicatat manual",
            date=r.get("created_at"),
            note=f"dicatat oleh {r.get('created_by') or '-'}"))
    return index


# ===================================================================== material (info)
async def material_prices(org: str, project_id: str = None) -> dict:
    """Harga satuan material dari PO (rata-rata tertimbang). Material tanpa PO → tanpa harga."""
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    pos = await db.purchase_orders.find(q, {"_id": 0, "items": 1}).to_list(4000)
    acc = {}
    for po in pos:
        for line in po.get("items") or []:
            mid = line.get("material_id")
            qty = float(line.get("qty") or 0)
            if not mid or qty <= 0:
                continue
            a = acc.setdefault(mid, {"qty": 0.0, "value": 0})
            a["qty"] += qty
            a["value"] += _i(line.get("amount"))
    return {mid: _i(a["value"] / a["qty"]) for mid, a in acc.items() if a["qty"] > 0}


async def material_usage(org: str, project_id: str) -> dict:
    """Nilai pemakaian material (ANGKA PENGENDALIAN, tidak dijumlahkan ke realisasi).

    Lihat docstring modul: material yang dibeli lewat PO sudah diakui saat tagihan masuk.
    """
    prices = await material_prices(org, project_id)
    txns = await db.material_txns.find({"org_id": org, "project_id": project_id, "type": "out"},
                                       {"_id": 0}).to_list(8000)
    total, unvalued, docs = 0, 0, []
    for t in txns:
        price = prices.get(t.get("material_id"))
        if not price:
            unvalued += 1
            continue
        amount = _i(float(t.get("qty") or 0) * price)
        total += amount
        docs.append(_doc("material_txn", t.get("ref") or t.get("id", "")[:8],
                         t.get("note") or "Pemakaian material", amount,
                         kind="informasi", link="/materials", date=t.get("created_at"),
                         note=f"{t.get('qty')} × Rp {price:,}".replace(",", ".")))
    missing = []
    if unvalued:
        missing.append(f"{unvalued} transaksi pemakaian material belum punya harga satuan "
                       "(materialnya belum pernah dibeli lewat PO)")
    return {"value": total if (docs or not txns) else None, "docs": docs,
            "transactions": len(txns), "unvalued": unvalued, "missing": missing,
            "note": "Pemakaian material TIDAK dijumlahkan ke realisasi agar biaya pembelian "
                    "tidak terhitung dua kali (sudah diakui saat tagihan vendor masuk)."}


# ===================================================================== konteks & item
async def build_context(org: str, project_id: str, *, alert_pct: float = 90) -> dict:
    """Ambil sekali semua bahan yang dipakai berulang oleh perhitungan item."""
    return {
        "org": org, "project_id": project_id, "alert_pct": float(alert_pct or 90),
        "construction": await construction_by_boq(org, project_id),
        "gl": await gl_expense_rows(org),
        "cost_ref": await cost_ref_index(org),
        "manual": await manual_index(org),
    }


def _construction_figures(item: dict, ctx: dict) -> dict:
    """Rencana & realisasi item konstruksi = agregasi item RAB yang ditaut (read-only).

    **Partisi komitmen vs realisasi** (penyempurnaan `docs/v2/32` §4 yang ditemukan POC 45):
    dokumen menulis `komitmen = Σ SPK belum DIKLAIM`. Kalau diterjemahkan apa adanya, lingkup
    yang pekerjaannya SUDAH diverifikasi opname tetapi dokumen klaimnya belum dibuat akan
    terhitung DUA kali — sekali sebagai realisasi (pekerjaan sudah diakui selesai) dan sekali
    sebagai komitmen. Karena itu pembagiannya dibuat saling lepas:

        realisasi = lingkup TERVERIFIKASI + bagian PO yang sudah ditagih
        komitmen  = lingkup BELUM terverifikasi + PO terbuka yang belum ditagih
        contracted = realisasi_lingkup + komitmen_lingkup   (tidak ada yang dobel, tidak ada
                                                             yang hilang)

    Alasannya juga benar secara ekonomi: pekerjaan yang sudah diverifikasi lapangan SUDAH
    menjadi biaya (subkon berhak atas nilainya) walau kertas klaimnya belum terbit.
    """
    ids = list(item.get("boq_item_ids") or [])
    planned = committed = realized = 0
    docs, unmapped_ids = [], []
    for bid in ids:
        row = ctx["construction"].get(bid)
        if not row:
            unmapped_ids.append(bid)
            continue
        planned += row["budget"]
        committed += (row["contracted"] - row["verified"]) + row["po_committed"]
        realized += row["verified"] + row["po_billed"]
        docs.extend(row["docs"])
    missing = []
    if not ids:
        missing.append("item anggaran konstruksi ini belum menaut item RAB — rencananya "
                       "tidak bisa dihitung dari RAB")
    if unmapped_ids:
        missing.append(f"{len(unmapped_ids)} tautan item RAB tidak ditemukan lagi "
                       "(item RAB mungkin sudah dihapus)")
    return {"planned": planned if ids and not unmapped_ids else (planned if ids else None),
            "committed": committed, "realized": realized, "docs": docs, "missing": missing,
            "planned_source": "boq", "boq_linked": len(ids) - len(unmapped_ids)}


def _gl_figures(item: dict, ctx: dict) -> dict:
    """Realisasi dari akun buku besar. Beban yang proyeknya tak terlacak TIDAK dijumlahkan."""
    account = (item.get("gl_account") or "").strip()
    if not account:
        return {"planned": None, "committed": 0, "realized": 0, "docs": [],
                "missing": ["akun buku besar belum dipilih — realisasi tidak bisa dicocokkan"],
                "planned_source": "input"}
    pid = item.get("project_id")
    realized, docs, unresolved, unresolved_total = 0, [], 0, 0
    for row in ctx["gl"]:
        if row["account_code"] != account:
            continue
        if pid and row["project_id"] != pid:
            if row["project_id"] is None:
                unresolved += 1
                unresolved_total += row["amount"]
            continue
        realized += row["amount"]
        docs.append(_doc("journal_entry", row["entry_no"],
                         f"{row['account_name']} — {row.get('memo') or ''}".strip(" —"),
                         row["amount"], status=row.get("source_type"),
                         link="/accounting", date=row.get("date")))
    missing = []
    if unresolved:
        missing.append(f"{unresolved} baris jurnal akun {account} belum bisa dipetakan ke "
                       f"proyek (total Rp {unresolved_total:,}) — angka ini TIDAK dijumlahkan"
                       .replace(",", "."))
    return {"planned": None, "committed": 0, "realized": realized, "docs": docs,
            "missing": missing, "planned_source": "input",
            "unresolved": {"rows": unresolved, "amount": unresolved_total}}


def _ref_figures(item: dict, ctx: dict, *, source: str) -> dict:
    """Realisasi dari dokumen yang MENYEBUT item ini (`by_cost_ref`) atau catatan manual."""
    docs = list((ctx[source] or {}).get(item["id"]) or [])
    realized = sum(d["amount"] for d in docs if d["kind"] == "realisasi")
    committed = sum(d["amount"] for d in docs if d["kind"] == "komitmen")
    missing = []
    if not docs:
        missing.append("belum ada dokumen biaya yang menaut item anggaran ini"
                       if source == "cost_ref" else
                       "belum ada pencatatan realisasi manual untuk item ini")
    return {"planned": None, "committed": committed, "realized": realized, "docs": docs,
            "missing": missing, "planned_source": "input"}


def item_figures(item: dict, ctx: dict) -> dict:
    """Angka lengkap satu item anggaran + dokumen penyusunnya (bahan lapis 2 & 3)."""
    rule = item.get("match_rule") or "manual"
    if rule == "by_boq_item":
        fig = _construction_figures(item, ctx)
    elif rule == "by_gl_account":
        fig = _gl_figures(item, ctx)
    elif rule == "by_cost_ref":
        fig = _ref_figures(item, ctx, source="cost_ref")
    else:
        fig = _ref_figures(item, ctx, source="manual")
    planned = fig["planned"] if fig.get("planned_source") == "boq" else _i(
        item.get("planned_amount"))
    exposure = _i(fig["realized"]) + _i(fig["committed"])
    variance = (planned - exposure) if planned is not None else None
    missing = list(fig.get("missing") or [])
    if not planned:
        missing.append("rencana anggaran item ini belum diisi (Rp 0) — persentase & status "
                       "tidak dihitung supaya tidak menyesatkan")
    return {
        "id": item["id"], "code": item.get("code"), "name": item.get("name"),
        "category": item.get("category") or "lainnya", "match_rule": rule,
        "gl_account": item.get("gl_account"), "owner_role": item.get("owner_role"),
        "period": item.get("period") or "project", "boq_item_ids": item.get("boq_item_ids") or [],
        "planned": planned, "planned_source": fig.get("planned_source"),
        "planned_readonly": fig.get("planned_source") == "boq",
        "committed": _i(fig["committed"]), "realized": _i(fig["realized"]),
        "exposure": exposure, "variance": variance,
        "pct": pct_of(exposure, planned or 0),
        "health": health_of(exposure, planned or 0, ctx["alert_pct"]),
        "documents": sorted(fig["docs"], key=lambda d: -d["amount"]),
        "document_count": len(fig["docs"]), "missing": missing,
        "unresolved": fig.get("unresolved"), "revision_count": len(item.get("revision") or []),
        "active": item.get("active", True), "note": item.get("note"),
    }


async def project_items(org: str, project_id: str) -> list:
    return await db.budget_items.find({"org_id": org, "project_id": project_id},
                                      {"_id": 0}).sort([("order", 1), ("code", 1)]).to_list(2000)


async def compute_project(org: str, project_id: str, *, alert_pct: float = 90) -> dict:
    """LAPIS 1 & 2: angka umum proyek + tabel per kategori + daftar item berikut dokumennya."""
    proj = await db.projects.find_one({"id": project_id, "org_id": org},
                                      {"_id": 0, "id": 1, "name": 1})
    items = await project_items(org, project_id)
    ctx = await build_context(org, project_id, alert_pct=alert_pct)
    rows = [item_figures(it, ctx) for it in items]
    totals = {"planned": 0, "committed": 0, "realized": 0, "exposure": 0}
    cats = {}
    for r in rows:
        totals["planned"] += _i(r["planned"])
        totals["committed"] += r["committed"]
        totals["realized"] += r["realized"]
        totals["exposure"] += r["exposure"]
        c = cats.setdefault(r["category"], {"category": r["category"], "planned": 0,
                                            "committed": 0, "realized": 0, "exposure": 0,
                                            "items": 0, "items_incomplete": 0,
                                            "unresolved_amount": 0, "missing": []})
        c["planned"] += _i(r["planned"])
        c["committed"] += r["committed"]
        c["realized"] += r["realized"]
        c["exposure"] += r["exposure"]
        c["items"] += 1
        if r["missing"]:
            c["items_incomplete"] += 1
            c["missing"].extend(r["missing"])
        if r.get("unresolved"):
            c["unresolved_amount"] += _i(r["unresolved"].get("amount"))
    for c in cats.values():
        c["variance"] = c["planned"] - c["exposure"]
        c["pct"] = pct_of(c["exposure"], c["planned"])
        c["health"] = health_of(c["exposure"], c["planned"], alert_pct)
        # Lapis 2 ikut membawa kejujurannya: kategori yang angkanya belum lengkap TIDAK
        # boleh terlihat sama rapi dengan kategori yang datanya utuh (pelajaran Fase 44).
        c["state"] = ("kosong" if not c["planned"] else
                      "sebagian" if (c["items_incomplete"] or c["unresolved_amount"])
                      else "lengkap")
        c["missing"] = sorted(set(c["missing"]))[:4]
    totals["variance"] = totals["planned"] - totals["exposure"]
    totals["pct"] = pct_of(totals["exposure"], totals["planned"])
    totals["health"] = health_of(totals["exposure"], totals["planned"], alert_pct)

    missing, warnings = [], []
    if not items:
        missing.append("belum ada item anggaran untuk proyek ini — susun master anggaran "
                       "dulu (kategori konstruksi otomatis mengambil total dari RAB)")
    if not totals["planned"] and items:
        missing.append("seluruh item anggaran masih Rp 0 — rencana belum diisi")
    for r in rows:
        if r["health"] == "overbudget":
            warnings.append(f"{r['code'] or r['name']}: exposure Rp {r['exposure']:,} melewati "
                            f"rencana Rp {_i(r['planned']):,} — perlu revisi anggaran "
                            "beralasan atau change order.".replace(",", "."))
        elif r["health"] == "waspada":
            warnings.append(f"{r['code'] or r['name']}: sudah {r['pct']}% dari rencana "
                            f"(ambang {alert_pct}%).")
    state = "kosong" if missing and not totals["planned"] else (
        "sebagian" if any(r["missing"] for r in rows) else "lengkap")
    return {
        "project_id": project_id, "project_name": (proj or {}).get("name"),
        "state": state, "alert_pct": alert_pct,
        "totals": None if state == "kosong" else totals,
        "categories": sorted(cats.values(), key=lambda c: -c["planned"]),
        "items": rows, "item_count": len(rows), "missing": missing, "warnings": warnings,
    }


async def tie_out(org: str, project_id: str) -> dict:
    """Bukti TIDAK ADA DUA KEBENARAN: agregasi modul ini vs `opname.cost_control()`.

    Dipakai POC + gate. Kalau selisihnya bukan 0, salah satu layar sedang membohongi pemakai.
    """
    con = await construction_by_boq(org, project_id)
    control = await op.cost_control(org, project_id)
    mine = {k: sum(r[k] for r in con.values())
            for k in ("budget", "contracted", "verified", "billed")}
    theirs = {k: _i(control["totals"].get(k)) for k in mine}
    return {"mine": mine, "control": theirs,
            "diff": {k: mine[k] - theirs[k] for k in mine},
            "ok": all(mine[k] == theirs[k] for k in mine)}
