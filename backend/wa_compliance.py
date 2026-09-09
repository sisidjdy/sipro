"""wa_compliance — kepatuhan kirim WhatsApp (Fase 97B/97C).

- Opt-out per organisasi per nomor (`wa_optouts`): kata UTUH STOP/BERHENTI/UNSUB/HENTIKAN.
  Menolak kategori MARKETING; UTILITY/AUTHENTICATION/SERVICE tetap jalan (tagihan bukan promosi).
- Jam kirim (WIB) dari Pusat Konfigurasi `wa.send_window_start/end` untuk antrean broadcast.
- Aturan template: di luar sesi 24 jam hanya template berstatus `approved`.
"""
import csv
import io
import re
from datetime import datetime, timedelta, timezone

import settings_store as st
from core_utils import new_id, now_iso
from db import db, ORG_ID

OPT_OUT_WORDS = frozenset({"stop", "berhenti", "unsub", "unsubscribe", "hentikan"})
_WORD = re.compile(r"[a-zA-Z]+")
WIB = timezone(timedelta(hours=7))
KIND_CATEGORY = {"otp": "authentication", "broadcast": "marketing", "reminder": "utility",
                 "document": "utility", "notification": "utility", "inbox": "service",
                 "test": "service", "playbook": "marketing"}


def detect_opt_out(text: str) -> bool:
    """Kata utuh saja: 'berhentikan pembangunan' TIDAK memicu opt-out."""
    words = {w.lower() for w in _WORD.findall(text or "")}
    return bool(words & OPT_OUT_WORDS)


def category_for(kind: str, template: dict = None) -> str:
    if template and template.get("category") in ("utility", "marketing", "authentication"):
        return template["category"]
    return KIND_CATEGORY.get(kind, "service")


# ------------------------------------------------------------------ opt-out
async def is_opted_out(org_id: str, phone: str) -> dict:
    return await db.wa_optouts.find_one({"org_id": org_id, "phone": phone, "active": True}, {"_id": 0})


async def register_opt_out(org_id: str, phone: str, *, source: str, actor: str = "contact",
                           conversation_id: str = None, note: str = None) -> dict:
    ts = now_iso()
    ex = await db.wa_optouts.find_one({"org_id": org_id, "phone": phone}, {"_id": 0})
    if ex and ex.get("active"):
        return {"created": False, "doc": ex}
    doc = {"id": (ex or {}).get("id") or new_id(), "org_id": org_id, "phone": phone, "source": source,
           "active": True, "created_at": ts, "created_by": actor, "conversation_id": conversation_id,
           "note": note, "revoked_at": None, "revoked_by": None}
    await db.wa_optouts.update_one({"org_id": org_id, "phone": phone}, {"$set": doc}, upsert=True)
    flag = {"wa_opt_out": True, "wa_opt_out_at": ts, "wa_opt_out_source": source}
    await db.leads.update_many({"org_id": org_id, "phone": phone}, {"$set": flag})
    await db.customers.update_many({"org_id": org_id, "phone": phone}, {"$set": flag})
    await db.wa_contacts.update_many({"org_id": org_id, "phone": phone}, {"$set": {"opt_out": True}})
    return {"created": True, "doc": doc}


async def revoke_opt_out(org_id: str, oid: str, *, actor: str) -> dict:
    ex = await db.wa_optouts.find_one({"org_id": org_id, "id": oid, "active": True}, {"_id": 0})
    if not ex:
        return None
    ts = now_iso()
    await db.wa_optouts.update_one({"id": oid}, {"$set": {"active": False, "revoked_at": ts, "revoked_by": actor}})
    await record_consent(org_id, ex["phone"], source=f"revoked_by:{actor}")
    return {**ex, "active": False, "revoked_at": ts}


async def record_consent(org_id: str, phone: str, *, source: str) -> None:
    ts = now_iso()
    flag = {"wa_opt_out": False, "consent_at": ts, "consent_source": source}
    await db.leads.update_many({"org_id": org_id, "phone": phone}, {"$set": flag})
    await db.customers.update_many({"org_id": org_id, "phone": phone}, {"$set": flag})
    await db.wa_contacts.update_many({"org_id": org_id, "phone": phone}, {"$set": {"opt_out": False}})


async def listing(org_id: str, *, q: str = "", skip: int = 0, limit: int = 50, active: bool = True) -> dict:
    query = {"org_id": org_id}
    if active:
        query["active"] = True
    if q:
        query["phone"] = {"$regex": re.escape(q)}
    total = await db.wa_optouts.count_documents(query)
    rows = await db.wa_optouts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    phones = [r["phone"] for r in rows]
    names = {}
    for coll in ("leads", "customers"):
        async for d in db[coll].find({"org_id": org_id, "phone": {"$in": phones}}, {"_id": 0, "phone": 1, "name": 1}):
            names.setdefault(d["phone"], d.get("name"))
    for r in rows:
        r["name"] = names.get(r["phone"])
    return {"data": rows, "total": total}


def to_csv(rows: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nomor", "Nama", "Sumber", "Tanggal", "Catatan"])
    for r in rows:
        w.writerow([r.get("phone"), r.get("name") or "", r.get("source"), r.get("created_at"), r.get("note") or ""])
    return buf.getvalue()


# ------------------------------------------------------------------ jam kirim
def _hhmm(v, default: str) -> tuple:
    try:
        h, m = str(v or default).split(":")[:2]
        return int(h), int(m)
    except (ValueError, AttributeError):
        h, m = default.split(":")
        return int(h), int(m)


async def send_window(org_id: str = ORG_ID) -> dict:
    vals = await st.get_many(["wa.send_window_start", "wa.send_window_end", "wa.rate_limit_per_sec"], org_id=org_id)
    return {"start": str(vals.get("wa.send_window_start") or "08:00"),
            "end": str(vals.get("wa.send_window_end") or "20:00"),
            "rate": max(1, int(vals.get("wa.rate_limit_per_sec") or 20))}


def in_send_window(start: str, end: str, now: datetime = None) -> bool:
    """WIB. start == end berarti tanpa batas jam."""
    now = (now or datetime.now(timezone.utc)).astimezone(WIB)
    sh, sm = _hhmm(start, "08:00")
    eh, em = _hhmm(end, "20:00")
    cur, lo, hi = now.hour * 60 + now.minute, sh * 60 + sm, eh * 60 + em
    if lo == hi:
        return True
    return lo <= cur < hi if lo < hi else (cur >= lo or cur < hi)


def next_window_start(start: str, now: datetime = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(WIB)
    sh, sm = _hhmm(start, "08:00")
    cand = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if cand <= now:
        cand += timedelta(days=1)
    return cand.astimezone(timezone.utc).isoformat()


# ------------------------------------------------------------------ aturan kirim
async def check_outbound(org_id: str, *, phone: str, category: str, template: dict, window_open: bool,
                         live: bool) -> tuple:
    """-> (error_code, error_detail, warning). error_code None = boleh kirim."""
    if category == "marketing" and await is_opted_out(org_id, phone):
        return ("opt_out", "Nomor ini menolak pesan promosi (opt-out). Pesan MARKETING tidak dikirim; "
                           "pengingat tagihan/utility tetap boleh.", None)
    if template is not None and template.get("status") != "approved":
        return ("template_not_approved",
                f"Template '{template.get('name') or template.get('code')}' belum disetujui Meta "
                f"(status {template.get('meta_status') or template.get('status')}). Di luar sesi 24 jam hanya "
                "template APPROVED yang bisa dikirim.", None)
    if template is None and not window_open:
        note = ("Sesi 24 jam tertutup: Meta menolak teks bebas di luar sesi (#131047). "
                "Gunakan template APPROVED.")
        if live:
            return ("131047", note, None)
        return (None, None, f"{note} (mode simulasi: pesan tetap dicatat)")
    return (None, None, None)
