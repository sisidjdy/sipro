"""DENDA KETERLAMBATAN TERJADWAL (Fase 68).

Fase 58 membangun SATU mesin denda (`late_fee_engine`) — tetapi menagihkannya tetap
menunggu tombol. Fase ini menambah opsi per organisasi (`payment.late.auto_apply`,
bawaan MATI) agar penjadwal harian menagihkan denda yang berlaku, dengan dua rem yang
bisa disetel pemilik usaha dari Pusat Konfigurasi:

  * `payment.late.auto_min_days`   — otomatis baru berjalan bila keterlambatan sudah
    melewati toleransi sebanyak ini (di bawahnya tetap bisa ditagihkan MANUAL);
  * `payment.late.auto_min_amount` — denda di bawah ambang ini tidak ditagihkan otomatis.

Aturan yang dipegang:
1. **Tidak ada mesin kedua.** Yang menagihkan tetap `late_fee_engine.apply` — berjurnal
   (Dr 1-1300 / Cr 4-1400) dan idempoten per (termin, bulan). Penjadwal yang berjalan dua
   kali TIDAK menagih dua kali.
2. **Menagih otomatis adalah keputusan bisnis.** Bawaan MATI; menyalakannya butuh izin
   `settings:manage` dan tercatat di riwayat setting. Keringanan tetap milik Manajer
   Keuangan (`late_fee:override`) — penjadwal tidak pernah meringankan.
3. **Setiap putaran ditulis** (`late_fee_auto_runs`): kapan, oleh siapa (scheduler/manusia),
   apa yang ditagihkan, apa yang ditahan aturan, dan apa yang gagal — layar membacanya
   apa adanya.
"""
import logging

import late_fee_engine as lf
import settings_store as cfg
from core_utils import new_id, now_iso
from db import ORG_ID, db
from finance_engine import notify_finance

logger = logging.getLogger("sipro.late_fee_auto")

KEY_ENABLED = "payment.late.auto_apply"
KEY_MIN_DAYS = "payment.late.auto_min_days"
KEY_MIN_AMOUNT = "payment.late.auto_min_amount"


def _rp(v) -> str:
    return f"Rp {int(v or 0):,}".replace(",", ".")


async def config(org: str = ORG_ID) -> dict:
    pol = await lf.policy(org)
    enabled = bool(await cfg.get(KEY_ENABLED, org_id=org))
    min_days = int(await cfg.get(KEY_MIN_DAYS, org_id=org) or 0)
    min_amount = int(await cfg.get(KEY_MIN_AMOUNT, org_id=org) or 0)
    return {
        "enabled": enabled, "min_days": min_days, "min_amount": min_amount,
        "policy": pol, "policy_sentence": lf.policy_sentence(pol),
        "rule_sentence": (
            f"Bila dinyalakan, penjadwal menagihkan denda SETIAP HARI (09:30 WIB) untuk "
            f"termin yang lewat toleransi ≥ {min_days} hari dan nilai dendanya ≥ "
            f"{_rp(min_amount)}. Nominal mengikuti kebijakan Pusat Konfigurasi "
            f"(payment.late.*), berjurnal, dan idempoten per termin per bulan — berjalan "
            f"dua kali tidak menagih dua kali."),
        "schedule": "Setiap hari 09:30 WIB (02:30 UTC).",
        "setting_keys": [KEY_ENABLED, KEY_MIN_DAYS, KEY_MIN_AMOUNT],
    }


async def preview(org: str = ORG_ID) -> dict:
    """Apa yang AKAN ditagihkan hari ini — beserta yang ditahan aturan & sebabnya."""
    conf = await config(org)
    invs = await db.ar_invoices.find(
        {"org_id": org, "status": {"$in": ["unpaid", "partial"]}},
        {"_id": 0, "deal_id": 1}).to_list(2000)
    rows = []
    for inv in invs:
        if not inv.get("deal_id"):
            continue
        hitung = await lf.assess(org, inv["deal_id"])
        if hitung.get("block"):
            continue
        for r in hitung.get("rows") or []:
            if r.get("state") != "terlambat" or int(r.get("denda_billable") or 0) <= 0:
                continue
            hold = None
            if int(r["days_late"]) < conf["min_days"]:
                hold = (f"Baru {r['days_late']} hari lewat toleransi — otomatis menunggu "
                        f"≥ {conf['min_days']} hari; manual tetap boleh.")
            elif int(r["denda_billable"]) < conf["min_amount"]:
                hold = (f"Denda {_rp(r['denda_billable'])} di bawah ambang otomatis "
                        f"{_rp(conf['min_amount'])}; manual tetap boleh.")
            rows.append({"deal_id": hitung["deal_id"], "unit_code": hitung.get("unit_code"),
                         "lead_name": hitung.get("lead_name"), "item_id": r["item_id"],
                         "term": r["label"], "days_late": r["days_late"],
                         "amount": r["denda_billable"], "eligible": hold is None,
                         "hold_reason": hold})
    rows.sort(key=lambda x: (-int(x["eligible"]), -int(x["amount"])))
    return {"rows": rows,
            "eligible_count": sum(1 for x in rows if x["eligible"]),
            "eligible_total": sum(int(x["amount"]) for x in rows if x["eligible"]),
            "config": conf}


async def run(org: str = ORG_ID, *, actor: str = "scheduler", mode: str = "auto") -> dict:
    """Tagihkan yang memenuhi aturan. Manual = manusia menekan tombol; auto = penjadwal."""
    conf = await config(org)
    if mode == "auto" and not conf["enabled"]:
        return {"mode": mode, "skipped_reason": "disabled", "charged_count": 0,
                "charged_total": 0,
                "detail": ("Denda otomatis dimatikan (payment.late.auto_apply) — penjadwal "
                           "tidak menagihkan apa pun.")}
    pre = await preview(org)
    charged, failed = [], []
    for row in pre["rows"]:
        if not row["eligible"]:
            continue
        try:
            res = await lf.apply(org, row["deal_id"], actor, item_id=row["item_id"])
            for c in res.get("created") or []:
                charged.append({"deal_id": row["deal_id"], "unit_code": row["unit_code"],
                                "lead_name": row["lead_name"], "term": c["term"],
                                "amount": c["amount"], "days_late": c["days_late"],
                                "journal_id": c["journal_id"]})
        except ValueError as e:
            failed.append({"deal_id": row["deal_id"], "term": row["term"],
                           "reason": str(e)})
    total = sum(c["amount"] for c in charged)
    doc = {
        "id": new_id(), "org_id": org, "at": now_iso(), "actor": actor, "mode": mode,
        "charged_count": len(charged), "charged_total": total, "charged": charged,
        "failed": failed, "candidates": len(pre["rows"]),
        "eligible": pre["eligible_count"],
        "config": {k: conf[k] for k in ("enabled", "min_days", "min_amount")},
        "detail": (f"{len(charged)} denda ditagihkan ({_rp(total)}) dari "
                   f"{pre['eligible_count']} yang memenuhi aturan"
                   + (f"; {len(failed)} gagal." if failed else ".")),
    }
    await db.late_fee_auto_runs.insert_one(dict(doc))
    doc.pop("_id", None)
    if charged and mode == "auto":
        await notify_finance(org, "Denda otomatis ditagihkan",
                             (f"Penjadwal menagihkan {len(charged)} denda keterlambatan "
                              f"({_rp(total)}) sesuai aturan Pusat Konfigurasi."),
                             "finance", "deal", None)
    logger.info("Denda auto (%s/%s) org %s: %s", mode, actor, org, doc["detail"])
    return doc


async def status(org: str = ORG_ID) -> dict:
    runs = await db.late_fee_auto_runs.find({"org_id": org}, {"_id": 0}) \
        .sort("at", -1).limit(10).to_list(10)
    pre = await preview(org)
    return {"config": pre["config"], "preview": pre, "runs": runs}
