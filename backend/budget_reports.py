"""budget_reports.py — Fase 45: margin, biaya belum terpetakan, RAB vs realisasi, peringatan.

Dipisah dari `budget_engine.py` agar kedua file tetap di bawah batas NFR 800 baris (gate
`validate_compliance`) dan agar tanggung jawabnya jelas: `budget_engine` MENGHITUNG angka
anggaran, modul ini MEMBACA angka itu untuk laporan & peringatan.

Tiga hal yang sengaja dibuat "tidak nyaman tetapi jujur":

  * **Margin tidak dipaksa keluar.** Kalau pendapatan diakui belum ada (`revenue_recognitions`
    kosong), margin dilaporkan `None` + menyebut apa yang kurang, sementara kas masuk
    (`receipts`) ditampilkan TERPISAH supaya tidak tertukar dengan pendapatan (`docs/v2/32` §5).
  * **Biaya yang belum bisa dipetakan tetap terlihat.** Justru laporan inilah yang membuat
    `budget.enforce_cost_ref` bisa dinyalakan bertahap tanpa membekukan pekerjaan orang.
  * **Peringatan hanya sekali per tingkat.** Naik `aman → waspada → overbudget` memicu
    notifikasi + tugas; tetap di tingkat yang sama TIDAK memicu apa pun. Tanpa aturan ini,
    sweeper harian akan mengirim pesan yang sama tiap hari sampai orang mematikan notifikasi.
"""
import logging

import budget_engine as be
import settings_store as cfg
import workhub as wh
from core_utils import new_id, now_iso
from db import ORG_ID, db
from engine import create_notification

logger = logging.getLogger("sipro.budget.reports")

ALERT_JOBDESK = "FN-11"
LEVELS = {"kosong": 0, "aman": 0, "waspada": 1, "overbudget": 2}
NOTIFY_FALLBACK_ROLES = ("owner", "super_admin")


# ===================================================================== margin
async def margin(org: str, project_id: str) -> dict:
    """Margin proyek + margin proyeksi (`docs/v2/32` §4 rumus).

    margin      = pendapatan diakui − realisasi biaya total
    margin_pro  = harga jual seluruh unit − (RAB total + budget operasional total)
    """
    alert_pct = await cfg.get("budget.alert_pct", org_id=org, project_id=project_id)
    summary = await be.compute_project(org, project_id, alert_pct=alert_pct)
    realized = (summary["totals"] or {}).get("realized", 0)

    recs = await db.revenue_recognitions.find({"org_id": org, "project_id": project_id},
                                              {"_id": 0}).to_list(4000)
    revenue = sum(be._i(r.get("amount")) for r in recs)
    units = await db.units.find({"org_id": org, "project_id": project_id},
                                {"_id": 0, "id": 1, "code": 1, "price": 1, "status": 1}) \
        .to_list(4000)
    unit_ids = [u["id"] for u in units]
    receipts = await db.receipts.find({"org_id": org, "unit_id": {"$in": unit_ids}},
                                      {"_id": 0}).to_list(4000) if unit_ids else []
    cash_in = sum(be._i(r.get("amount")) for r in receipts)

    # Fase 81b: RAB total = RAB terstruktur (tipe × unit + add-on terjual + fasum/umum + item lama),
    # bukan lagi Σ boq_items flat — supaya margin proyeksi di BI sama dengan Ringkasan & HPP.
    import rab_engine as re_
    rab_total = (await re_.project_summary(org, project_id))["total_rab"]
    opex_total = sum(be._i(i["planned"]) for i in summary["items"]
                     if i["category"] != be.CONSTRUCTION)
    sellable = sum(be._i(u.get("price")) for u in units)
    unpriced = len([u for u in units if not be._i(u.get("price"))])

    missing = []
    if not recs:
        missing.append("pendapatan diakui belum ada (koleksi `revenue_recognitions` kosong) — "
                       "margin tidak dihitung dari kas masuk supaya tidak tertukar")
    if not summary["items"]:
        missing.append("budget operasional belum disusun — margin proyeksi belum lengkap")
    if unpriced:
        missing.append(f"{unpriced} unit belum punya harga jual")
    margin_value = (revenue - realized) if recs else None
    margin_pro = (sellable - (rab_total + opex_total)) if (sellable and
                                                           (rab_total or opex_total)) else None
    return {
        "project_id": project_id, "project_name": summary.get("project_name"),
        "margin": margin_value,
        "margin_pct": be.pct_of(margin_value, revenue) if margin_value is not None else None,
        "margin_projected": margin_pro,
        "margin_projected_pct": be.pct_of(margin_pro, sellable) if margin_pro is not None
        else None,
        "components": {
            "pendapatan_diakui": revenue if recs else None,
            "kas_masuk": cash_in, "realisasi_biaya": realized,
            "rab_total": rab_total, "budget_operasional": opex_total,
            "harga_jual_seluruh_unit": sellable, "unit_count": len(units),
        },
        "state": "kosong" if not recs and margin_pro is None else (
            "sebagian" if missing else "lengkap"),
        "missing": missing,
        "note": "Kas masuk BUKAN pendapatan: kas masuk ditampilkan terpisah agar tidak dipakai "
                "sebagai pengganti pendapatan yang diakui.",
    }


# ============================================================ biaya belum terpetakan
UNMAPPED_SOURCES = [
    ("purchase_orders", "purchase_order", "po_number", "total", "/procurement"),
    ("ap_invoices", "ap_invoice", "no", "claimed", "/finance?tab=ap"),
    ("cash_advances", "cash_advance", "no", "disbursed_amount", "/petty-cash"),
    ("marketing_fees", "marketing_fee", "no", "amount_gross", "/partners?hub=tagihan"),
]


async def unmapped_costs(org: str, project_id: str = None) -> dict:
    """Dokumen biaya yang belum menyebut item anggaran + jurnal yang belum bisa dipetakan.

    Ini "peta pekerjaan", bukan tuduhan: dokumen lama memang dibuat sebelum item anggaran ada.
    Laporan ini yang membuat `budget.enforce_cost_ref` bisa dinyalakan tanpa menghentikan
    pekerjaan — rapikan dulu daftar di sini.
    """
    rows, totals = [], {}
    for coll, source, ref_field, amount_field, link in UNMAPPED_SOURCES:
        q = {"org_id": org, "budget_item_id": None, "cost_ref.budget_item_id": None}
        if project_id:
            q["project_id"] = project_id
        try:
            docs = await db[coll].find(q, {"_id": 0}).to_list(2000)
        except Exception:  # noqa: BLE001
            continue
        for d in docs:
            amount = be._i(d.get(amount_field))
            if not amount:
                continue
            rows.append(be._doc(source, str(d.get(ref_field) or d.get("id", ""))[:24],
                                d.get("note") or d.get("purpose") or source, amount,
                                kind="belum terpetakan", status=d.get("status"), link=link,
                                date=d.get("created_at")))
            totals[source] = totals.get(source, 0) + amount
    gl = await be.gl_expense_rows(org)
    gl_unresolved = [r for r in gl if r["project_id"] is None]
    gl_total = sum(r["amount"] for r in gl_unresolved)
    if gl_total:
        totals["journal_entry"] = gl_total
        for r in sorted(gl_unresolved, key=lambda x: -x["amount"])[:50]:
            rows.append(be._doc("journal_entry", r["entry_no"],
                                f"{r['account_name']} — {r.get('memo') or ''}".strip(" —"),
                                r["amount"], kind="belum terpetakan",
                                status=r.get("source_type"), link="/accounting",
                                date=r.get("date"),
                                note="jurnal ini belum bisa ditelusuri ke proyek mana pun"))
    enforce = await cfg.get("budget.enforce_cost_ref", org_id=org)
    return {
        "project_id": project_id, "enforce_cost_ref": bool(enforce),
        "total": sum(totals.values()),
        "by_source": [{"source": k, "amount": v} for k, v in
                      sorted(totals.items(), key=lambda kv: -kv[1])],
        "documents": sorted(rows, key=lambda d: -d["amount"])[:200],
        "document_count": len(rows),
        "note": ("Wajib pilih item anggaran SUDAH menyala untuk dokumen baru."
                 if enforce else
                 "Wajib pilih item anggaran masih MATI: dokumen baru boleh tanpa item "
                 "anggaran, tetapi akan muncul di daftar ini. Nyalakan di Pusat Konfigurasi "
                 "(`budget.enforce_cost_ref`) setelah daftar ini rapi."),
    }


# ============================================================ RAB vs realisasi
async def rab_vs_actual(org: str, project_id: str, group_by: str = "item") -> dict:
    """RAB vs realisasi dikelompokkan per item / langkah / unit / kategori.

    Angkanya diambil dari agregasi `budget_engine.construction_by_boq()` yang SAMA dengan
    yang dipakai lapis 1/2, jadi tabel ini tidak bisa berbeda dengan kartu ringkasannya.
    """
    con = await be.construction_by_boq(org, project_id)
    boq = await db.boq_items.find({"org_id": org, "project_id": project_id},
                                  {"_id": 0}).to_list(4000)
    bmap = {b["id"]: b for b in boq}
    scope = await be.enriched_scope(org, project_id)
    groups = {}

    def bucket(key, label, extra=None):
        row = groups.setdefault(key, {"key": key, "label": label, "budget": 0, "contracted": 0,
                                      "verified": 0, "billed": 0, "po_committed": 0})
        row.update(extra or {})
        return row

    if group_by in ("step", "unit"):
        # Agregasi per langkah jadwal / unit hanya bisa dari lingkup SPK (di situlah unit &
        # langkah tercatat). Anggaran RAB tidak punya unit, jadi kolom anggaran dikosongkan
        # (None) — BUKAN 0 — supaya tidak terbaca "anggarannya nol".
        for s in scope:
            key = (s.get("step_code") if group_by == "step" else s.get("unit_code")) or "(tanpa)"
            label = (s.get("step_name") if group_by == "step" else s.get("unit_code")) or key
            row = bucket(key, label)
            val = be._i(s.get("value"))
            row["contracted"] += val
            row["verified"] += val if s.get("verified") else 0
            row["billed"] += val if s.get("claim_id") else 0
            row["budget"] = None
    elif group_by == "category":
        for bid, row in con.items():
            b = bmap.get(bid) or {}
            key = b.get("category") or ("(tanpa item RAB)" if bid is None else "lainnya")
            g = bucket(key, key)
            g["budget"] += row["budget"]
            for k in ("contracted", "verified", "billed", "po_committed"):
                g[k] += row[k]
    else:
        for bid, row in con.items():
            b = bmap.get(bid) or {}
            key = bid or "(tanpa item RAB)"
            label = b.get("cost_code") or ("(lingkup tanpa item RAB)" if bid is None else key)
            g = bucket(key, label, {"description": b.get("description"),
                                    "category": b.get("category")})
            g["budget"] += row["budget"]
            for k in ("contracted", "verified", "billed", "po_committed"):
                g[k] += row[k]
    rows = []
    for g in groups.values():
        budget = g["budget"]
        exposure = g["verified"] + g["po_committed"] + (g["contracted"] - g["billed"])
        g["exposure"] = exposure
        g["variance"] = (budget - exposure) if budget is not None else None
        g["pct"] = be.pct_of(exposure, budget or 0)
        g["health"] = be.health_of(exposure, budget or 0, 90)
        rows.append(g)
    tie = await be.tie_out(org, project_id)
    return {"project_id": project_id, "group_by": group_by,
            "data": sorted(rows, key=lambda r: -(r["budget"] or 0)),
            "totals": tie["mine"], "tie_out": tie,
            "missing": [] if tie["ok"] else
            ["agregasi RAB tidak cocok dengan panel Kendali Biaya — laporkan sebagai cacat"]}


# ============================================================ peringatan anggaran
async def _alert_recipients(org: str, owner_role: str) -> list:
    roles = [r for r in [owner_role] if r] + list(NOTIFY_FALLBACK_ROLES)
    users = await db.users.find({"org_id": org, "role": {"$in": roles}, "is_active": True},
                                {"_id": 0, "email": 1, "role": 1}).to_list(100)
    return sorted({u["email"] for u in users if u.get("email")})


async def alert_scan(org: str = ORG_ID, *, project_id: str = None, actor: str = "scheduler",
                     force: bool = False) -> dict:
    """Periksa semua item anggaran; kirim notifikasi + tugas saat TINGKAT status naik.

    `force=True` mengabaikan tingkat tersimpan (dipakai gate & tombol "Periksa sekarang"),
    tetapi tetap idempoten di level tugas karena `source_event` menyertakan tingkatnya.
    """
    q = {"org_id": org}
    if project_id:
        q["project_id"] = project_id
    pids = sorted({p for p in await db.budget_items.distinct("project_id", q) if p})
    created, checked = [], 0
    for pid in pids:
        alert_pct = await cfg.get("budget.alert_pct", org_id=org, project_id=pid)
        summary = await be.compute_project(org, pid, alert_pct=alert_pct)
        for row in summary["items"]:
            checked += 1
            level = LEVELS.get(row["health"], 0)
            stored = await db.budget_items.find_one({"id": row["id"]},
                                                    {"_id": 0, "alert_level": 1, "owner_role": 1})
            prev = LEVELS.get((stored or {}).get("alert_level") or "aman", 0)
            if level <= prev and not force:
                continue
            if level == 0:
                await db.budget_items.update_one(
                    {"id": row["id"]}, {"$set": {"alert_level": row["health"],
                                                 "alert_at": now_iso()}})
                continue
            title = (f"Anggaran overbudget: {row['code'] or row['name']}" if level == 2
                     else f"Anggaran mendekati batas: {row['code'] or row['name']}")
            body = (f"{summary.get('project_name') or pid} · rencana Rp "
                    f"{be._i(row['planned']):,} · exposure Rp {row['exposure']:,} "
                    f"({row['pct']}% dari rencana, ambang {alert_pct}%)").replace(",", ".")
            emails = await _alert_recipients(org, (stored or {}).get("owner_role"))
            for email in emails:
                await create_notification(user_email=email, title=title, body=body,
                                          type="budget", related_entity_type="budget_item",
                                          related_entity_id=row["id"], org_id=org)
            tasks = await wh.spawn(
                org, ALERT_JOBDESK, source_event=f"budget.alert:{row['id']}:{row['health']}",
                title=title, description=body, entity_type="budget_item", entity_id=row["id"],
                assignee_override=emails[0] if emails else None, assigned_by=actor,
                link=f"/boq?hub=realisasi&project_id={pid}", strict_once=True,
                meta={"budget_item_id": row["id"], "health": row["health"],
                      "pct": row["pct"], "project_id": pid})
            await db.budget_items.update_one(
                {"id": row["id"]}, {"$set": {"alert_level": row["health"],
                                             "alert_at": now_iso()},
                                    "$push": {"alerts": {"$each": [{
                                        "at": now_iso(), "level": row["health"],
                                        "pct": row["pct"], "exposure": row["exposure"],
                                        "notified": emails,
                                        "task_ids": [t["id"] for t in tasks]}], "$slice": -20}}})
            created.append({"budget_item_id": row["id"], "code": row["code"],
                            "health": row["health"], "pct": row["pct"],
                            "notified": emails, "tasks": len(tasks)})
    return {"checked": checked, "projects": len(pids), "alerts": created,
            "created": len(created)}


async def alert_tick() -> int:
    """Job harian. Gagal satu organisasi tidak menjatuhkan scheduler."""
    try:
        out = await alert_scan()
        if out["created"]:
            logger.info("Peringatan anggaran terkirim: %s item", out["created"])
        return out["created"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Peringatan anggaran gagal: %s", exc)
        return 0


# ============================================================ revisi anggaran
async def revise_item(org: str, item_id: str, *, planned_amount: int, reason: str,
                      actor: str) -> dict:
    """Revisi rencana anggaran — WAJIB beralasan, dan jejaknya disimpan permanen."""
    item = await db.budget_items.find_one({"id": item_id, "org_id": org}, {"_id": 0})
    if not item:
        return {}
    if (item.get("category") == be.CONSTRUCTION
            and (item.get("match_rule") == "by_boq_item")):
        raise ValueError(
            "Item anggaran konstruksi mengambil rencananya dari total item RAB yang ditaut "
            "(read-only). Ubah nilainya di RAB/BoQ, atau ubah daftar item RAB yang ditaut — "
            "supaya tidak ada dua angka anggaran konstruksi yang berbeda.")
    entry = {"at": now_iso(), "by": actor, "from": be._i(item.get("planned_amount")),
             "to": be._i(planned_amount), "reason": reason.strip()}
    await db.budget_items.update_one(
        {"id": item_id, "org_id": org},
        {"$set": {"planned_amount": be._i(planned_amount), "updated_at": now_iso(),
                  "updated_by": actor},
         "$push": {"revision": {"$each": [entry], "$slice": -50}}})
    return entry


async def add_manual_entry(org: str, item_id: str, *, amount: int, note: str, actor: str,
                           kind: str = "realisasi", ref_no: str = None) -> dict:
    """Catat realisasi manual (untuk item ber-`match_rule=manual`), selalu ber-jejak."""
    doc = {"id": new_id(), "org_id": org, "budget_item_id": item_id,
           "amount": be._i(amount), "kind": kind, "note": note.strip(), "ref_no": ref_no,
           "created_by": actor, "created_at": now_iso()}
    await db.budget_manual_entries.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc
