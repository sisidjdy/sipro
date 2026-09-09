"""SKEMA PEMBAYARAN YANG BISA DIKONFIGURASI (Fase 57A).

## Lubang yang ditutup

Sampai Fase 56, termin `cash keras` / `cash bertahap` / `KPR` disusun **di dalam kode**
(`contracts_engine.scheme_terms_spec`) dari beberapa ambang di Pusat Konfigurasi: DP 80%,
6× cicilan, tanggal 7, pelunasan 30 hari setelah bangunan 100%. Pengembang yang bisnisnya
berbeda — DP nominal Rp 50 juta, 12× cicilan, pelunasan menyusul AJB — tidak punya jalan
lain selain meminta ubah kode. Untuk produk SaaS itu berarti fiturnya tidak ada.

Sesudah fase ini: **pemakai membuat skema sendiri** (nama, jenis, daftar termin, dasar nilai,
cara jatuh tempo, tenggang, peristiwa pemicu, berlaku di proyek mana), dan kontrak memakai
skema itu apa adanya.

## Yang TIDAK berubah (dan tidak boleh berubah)

* **Satu mesin termin.** Nominal per termin tetap dihitung `finance_engine.compute_scheme_items`
  — fungsi yang sama dengan yang menagih. Tidak ada rumus kedua.
* **Jenis skema tetap jujur.** `kind` (cash_keras / cash_bertahap / kpr) menentukan tahap
  legal & komponen biaya KPR. Pemakai boleh menamai skemanya apa saja, tetapi harus memilih
  jenisnya — akad kredit tidak boleh muncul pada skema tunai hanya karena namanya "KPR-ish".
* **Kalimat jatuh tempo disusun MESIN** dari konfigurasi, bukan diketik pemakai, supaya
  dokumen yang ditandatangani pembeli tidak pernah menjanjikan aturan yang berbeda dari
  yang ditagihkan.
* **Tanggal yang belum pasti diakui belum pasti.** Termin berbasis peristiwa membawa
  `event_based: True`; layar/dokumen menyebutnya perkiraan.
"""
import logging
from datetime import datetime, timedelta

import finance_engine as fin
import reference as ref
from core_utils import new_id, now_iso, serialize_doc
from db import ORG_ID, db

logger = logging.getLogger("sipro.payment_scheme")

KINDS = ("cash_keras", "cash_bertahap", "kpr")
BASES = ("percent", "amount", "remaining")
DUE_MODES = ("offset_days", "monthly_day", "event")


def _blk(code: str, detail: str) -> dict:
    return {"code": code, "label": ref.label_of("scheme_block", code), "detail": detail}


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


# ------------------------------------------------------------------ kalimat jatuh tempo
def due_sentence(t: dict) -> str:
    """Aturan jatuh tempo dalam bahasa manusia — DISUSUN MESIN dari konfigurasi.

    Pemakai tidak mengetik kalimat ini: kalimat yang diketik bisa berbeda dari yang
    ditagihkan, dan yang membaca kalimat itu adalah pembeli di dokumen SPR.
    """
    mode = t.get("due_mode") or "offset_days"
    grace = int(t.get("grace_days") or 0)
    ekor = f" · toleransi {grace} hari" if grace else ""
    if mode == "monthly_day":
        return f"tanggal {int(t.get('due_day') or 1)} setiap bulan{ekor}"
    if mode == "event":
        peristiwa = ref.label_of("term_due_event", t.get("event_code") or "build_complete")
        hari = int(t.get("due_offset_days") or 0)
        jeda = f" (maks {hari} hari)" if hari else ""
        return f"{peristiwa.lower()}{jeda}{ekor} — tanggal pada jadwal masih perkiraan"
    hari = int(t.get("due_offset_days") or 0)
    if hari <= 0:
        return f"saat kontrak diaktifkan{ekor}"
    return f"{hari} hari setelah kontrak diaktifkan{ekor}"


def normalize_terms(terms: list) -> list:
    """Bentuk baku satu baris termin + kalimat aturan + penanda 'tanggal belum pasti'."""
    out = []
    for i, t in enumerate(terms or []):
        row = {
            "label": (t.get("label") or "").strip(),
            "basis": t.get("basis") or "percent",
            "value": float(t.get("value") or 0),
            "due_mode": t.get("due_mode") or "offset_days",
            "due_offset_days": int(t.get("due_offset_days") or 0),
            "due_day": (int(t["due_day"]) if t.get("due_day") else None),
            "month_index": (int(t["month_index"]) if t.get("month_index") is not None
                            else (i if (t.get("due_mode") == "monthly_day") else None)),
            "grace_days": int(t.get("grace_days") or 0),
            "event_code": t.get("event_code") or None,
            "note": (t.get("note") or None),
        }
        row["due_rule"] = due_sentence(row)
        row["event"] = row["due_mode"] == "event"
        out.append(row)
    return out


# ------------------------------------------------------------------ penjagaan
def blocks(terms: list) -> list:
    """Sebab satu skema BELUM boleh disimpan — masing-masing dengan kalimatnya.

    Aturan yang dipaksakan (dan alasannya):
    * tanpa termin → tidak ada yang bisa ditagihkan;
    * semua persen → jumlahnya WAJIB tepat 100% (kalau 95%, 5% harga rumah tidak pernah
      tertagih dan tidak ada yang tahu sampai penutupan buku);
    * campuran nominal & persen hanya boleh bila ada satu termin **sisa harga** paling
      akhir — itu satu-satunya cara jujur menutup selisih tanpa mengarang;
    * nilai nol/negatif ditolak: termin kosong adalah tagihan yang tidak menagih apa pun.
    """
    t = normalize_terms(terms)
    if not t:
        return [_blk("tanpa_termin", "Skema harus punya minimal satu termin.")]
    out = []
    for i, r in enumerate(t):
        if r["basis"] != "remaining" and r["value"] <= 0:
            out.append(_blk("nilai_tidak_wajar",
                            f"Termin '{r['label']}' bernilai {r['value']:g} — nilai termin "
                            "harus lebih besar dari nol."))
    sisa_idx = [i for i, r in enumerate(t) if r["basis"] == "remaining"]
    pct = sum(r["value"] for r in t if r["basis"] == "percent")
    ada_nominal = any(r["basis"] == "amount" for r in t)
    if len(sisa_idx) > 1:
        out.append(_blk("sisa_ganda", "Hanya boleh ada SATU termin 'sisa harga'."))
    if sisa_idx and sisa_idx[-1] != len(t) - 1:
        out.append(_blk("sisa_bukan_terakhir",
                        "Termin 'sisa harga' harus berada di baris paling akhir."))
    if sisa_idx:
        if pct >= 100:
            out.append(_blk("persen_melebihi_100",
                            f"Persen termin sudah {pct:g}% padahal masih ada termin 'sisa "
                            "harga' — tidak ada sisa yang bisa ditagihkan."))
    else:
        if ada_nominal:
            out.append(_blk("nominal_tanpa_sisa",
                            "Ada termin nominal tetap. Tambahkan satu termin 'sisa harga' "
                            "di baris terakhir supaya seluruh harga jual tertagih."))
        elif abs(pct - 100) > 0.01:
            out.append(_blk("persen_bukan_100",
                            f"Jumlah persen termin {pct:g}% — harus tepat 100% supaya tidak "
                            "ada bagian harga rumah yang tidak pernah tertagih."))
    return out


# ------------------------------------------------------------------ pratinjau
def simulate(scheme: dict, price: int, base_date: str = None) -> dict:
    """Pratinjau jadwal atas satu harga — memakai MESIN TERMIN YANG SAMA dengan penagihan."""
    price = int(price or 0)
    items = fin.compute_scheme_items(scheme, price, base_date or now_iso())
    terms = normalize_terms(scheme.get("items") or scheme.get("terms") or [])
    rows = []
    for i, it in enumerate(items):
        t = terms[i] if i < len(terms) else {}
        rows.append({**it, "no": i + 1, "due_rule": t.get("due_rule"),
                     "event_based": bool(t.get("event")),
                     "basis_label": ref.label_of("term_basis", it.get("basis") or "percent")})
    total = sum(int(r["amount"] or 0) for r in rows)
    return {"rows": rows, "total": total, "price": price,
            "difference": total - price,
            "balanced": total == price,
            "note": (None if total == price else
                     f"Jadwal ini menagih {_rp(total)} sedangkan harga jual {_rp(price)} — "
                     f"selisih {_rp(abs(total - price))}. Perbaiki termin sebelum dipakai.")}


# ------------------------------------------------------------------ pembantu cicilan
def build_installments(count: int, percent_total: float, start_month: int, due_day: int,
                       grace_days: int, label_prefix: str = "Cicilan") -> list:
    """'Buat N cicilan' → tetap menjadi baris termin biasa yang bisa diubah satu per satu.

    Pembagian sisa pembulatan TIDAK disembunyikan: baris terakhir memikul selisihnya supaya
    jumlah persen tetap tepat.
    """
    count = max(1, int(count))
    per = round(float(percent_total) / count, 4)
    rows = []
    for i in range(count):
        nilai = per if i < count - 1 else round(float(percent_total) - per * (count - 1), 4)
        rows.append({"label": f"{label_prefix} {i + 1}/{count}", "basis": "percent",
                     "value": nilai, "due_mode": "monthly_day",
                     "due_day": int(due_day), "month_index": int(start_month) + i,
                     "grace_days": int(grace_days)})
    return rows


# ------------------------------------------------------------------ simpanan (CRUD)
def _slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in (name or "").strip()]
    s = "".join(keep).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s[:40] or "skema"


async def listing(org: str = ORG_ID, *, kind: str = None, project_id: str = None,
                  active: bool = None) -> dict:
    q = {"org_id": org}
    if kind:
        q["kind"] = kind
    if active is not None:
        q["active"] = active
    rows = await db.payment_schemes.find(q, {"_id": 0}).sort("name", 1).to_list(200)
    out = []
    for r in rows:
        if project_id and (r.get("applies_project_ids") or []):
            if project_id not in r["applies_project_ids"]:
                continue
        r["kind_label"] = ref.label_of("payment_scheme_kind", r.get("kind") or "")
        r["terms"] = normalize_terms(r.get("items") or [])
        r["used_by_contracts"] = await db.contracts.count_documents(
            {"org_id": org, "payment_scheme_id": r["id"]})
        out.append(r)
    return {"data": serialize_doc(out), "total": len(out),
            "reason": (None if out else
                       "Belum ada skema pembayaran yang cocok dengan penyaring ini.")}


async def get(org: str, scheme_id: str) -> dict:
    doc = await db.payment_schemes.find_one({"id": scheme_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise LookupError("Skema pembayaran tidak ditemukan.")
    doc["terms"] = normalize_terms(doc.get("items") or [])
    doc["kind_label"] = ref.label_of("payment_scheme_kind", doc.get("kind") or "")
    return doc


async def save(org: str, payload: dict, actor: str, scheme_id: str = None) -> dict:
    kind = payload.get("kind")
    if kind not in KINDS:
        raise ValueError(f"Jenis skema '{kind}' tidak dikenal.")
    b = blocks(payload.get("terms") or [])
    if b:
        raise ValueError(" ".join(x["detail"] for x in b))
    items = normalize_terms(payload.get("terms") or [])
    code = (payload.get("code") or _slug(payload.get("name"))).strip()
    bentrok = await db.payment_schemes.find_one(
        {"org_id": org, "code": code, "id": {"$ne": scheme_id or ""}}, {"_id": 0, "id": 1})
    if bentrok:
        raise ValueError(f"Kode skema '{code}' sudah dipakai skema lain.")
    ts = now_iso()
    common = {
        "name": payload["name"].strip(), "kind": kind, "code": code,
        "active": bool(payload.get("active", True)),
        "applies_project_ids": list(payload.get("applies_project_ids") or []),
        "note": payload.get("note"), "items": items,
        "updated_at": ts, "updated_by": actor,
    }
    if scheme_id:
        lama = await get(org, scheme_id)
        # Skema yang sudah dipakai kontrak BERUANG (ada penerimaan) tidak boleh diubah
        # diam-diam: jadwal kewajiban yang sudah dibayar sebagian akan berubah tanpa jejak.
        terpakai = await _contracts_with_money(org, scheme_id)
        if terpakai and items != (lama.get("items") or []):
            raise ValueError(
                f"Skema ini dipakai {terpakai} kontrak yang sudah ada penerimaannya. Buat "
                "skema BARU (atau salin skema ini) daripada mengubah jadwal yang sudah "
                "berjalan — pembeli sudah membayar berdasarkan termin lama.")
        await db.payment_schemes.update_one({"id": scheme_id}, {"$set": common, "$push": {
            "history": {"at": ts, "by": actor, "action": "update",
                        "terms_before": lama.get("items") or []}}})
        doc = await get(org, scheme_id)
    else:
        doc = {"id": new_id(), "org_id": org, "is_default": bool(payload.get("is_default")),
               "source": "user", "created_at": ts, "created_by": actor,
               "history": [{"at": ts, "by": actor, "action": "create"}], **common}
        await db.payment_schemes.insert_one(dict(doc))
        doc.pop("_id", None)
    if payload.get("is_default"):
        await db.payment_schemes.update_many(
            {"org_id": org, "id": {"$ne": doc["id"]}}, {"$set": {"is_default": False}})
        await db.payment_schemes.update_one({"id": doc["id"]},
                                            {"$set": {"is_default": True}})
    return await get(org, doc["id"])


async def _contracts_with_money(org: str, scheme_id: str) -> int:
    n = 0
    async for c in db.contracts.find({"org_id": org, "payment_scheme_id": scheme_id},
                                     {"_id": 0, "deal_id": 1}):
        inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": c["deal_id"]},
                                           {"_id": 0, "paid": 1})
        if int((inv or {}).get("paid") or 0) > 0:
            n += 1
    return n


# ------------------------------------------------------------------ dipakai kontrak
async def resolve_for_contract(org: str, contract: dict) -> dict:
    """Skema mana yang berlaku untuk satu kontrak — beserta ASALNYA (jujur).

    Urutan: (1) skema yang dipilih di kontrak, (2) skema bawaan organisasi yang jenisnya
    sama & berlaku di proyek kontrak, (3) skema apa pun yang jenisnya sama. Kalau tidak ada
    satu pun, dikembalikan `None` beserta sebabnya — BUKAN termin karangan.
    """
    sid = contract.get("payment_scheme_id")
    if sid:
        doc = await db.payment_schemes.find_one({"id": sid, "org_id": org}, {"_id": 0})
        if doc:
            return {"scheme": doc, "source": "kontrak", "reason": None}
    kind = contract.get("scheme")
    kandidat = await db.payment_schemes.find(
        {"org_id": org, "kind": kind, "active": True}, {"_id": 0}).to_list(100)
    pid = contract.get("project_id")
    cocok = [c for c in kandidat
             if not (c.get("applies_project_ids") or []) or pid in c["applies_project_ids"]]
    for c in sorted(cocok, key=lambda x: (not x.get("is_default"), x.get("name") or "")):
        return {"scheme": c, "source": "bawaan organisasi", "reason": None}
    return {"scheme": None, "source": None,
            "reason": (f"Belum ada skema pembayaran aktif berjenis "
                       f"'{ref.label_of('payment_scheme_kind', kind or '')}' untuk proyek "
                       "ini. Buat dahulu di Pusat Konfigurasi › Skema Pembayaran.")}


async def set_for_contract(org: str, contract: dict, scheme_id: str, actor: str,
                           reason: str) -> dict:
    """Tetapkan skema pada satu kontrak. Ditolak bila uang sudah masuk (bukan diam-diam)."""
    doc = await db.payment_schemes.find_one({"id": scheme_id, "org_id": org}, {"_id": 0})
    if not doc:
        raise LookupError("Skema pembayaran tidak ditemukan.")
    if doc.get("kind") != contract.get("scheme"):
        raise ValueError(
            f"Skema '{doc['name']}' berjenis "
            f"{ref.label_of('payment_scheme_kind', doc.get('kind') or '')}, sedangkan "
            f"kontrak ini berjenis "
            f"{ref.label_of('payment_scheme_kind', contract.get('scheme') or '')}. Ubah "
            "jenis kontrak lebih dahulu — jenis menentukan tahap legal & biaya yang berlaku.")
    proyek = doc.get("applies_project_ids") or []
    if proyek and contract.get("project_id") not in proyek:
        raise ValueError(f"Skema '{doc['name']}' tidak berlaku untuk proyek kontrak ini.")
    inv = await db.ar_invoices.find_one({"org_id": org, "deal_id": contract["deal_id"]},
                                       {"_id": 0, "paid": 1})
    if int((inv or {}).get("paid") or 0) > 0:
        raise ValueError(
            f"Sudah ada penerimaan {_rp((inv or {}).get('paid'))} pada kontrak ini. "
            "Mengganti skema akan menyusun ulang jadwal yang sebagian sudah dibayar — "
            "terbitkan adendum, jangan menimpa jadwal berjalan.")
    ts = now_iso()
    await db.contracts.update_one({"id": contract["id"]}, {
        "$set": {"payment_scheme_id": scheme_id, "payment_scheme_name": doc.get("name"),
                 "updated_at": ts},
        "$push": {"payment_scheme_history": {
            "from": contract.get("payment_scheme_id"), "to": scheme_id,
            "to_name": doc.get("name"), "at": ts, "by": actor, "reason": reason}}})
    return await db.contracts.find_one({"id": contract["id"]}, {"_id": 0})
