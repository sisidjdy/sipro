"""wa_templates_meta — template WA ↔ Meta (Fase 97A).

Field Meta pada `wa_templates`: `meta_name`, `meta_id`, `meta_status` (NOT_SUBMITTED/PENDING/
APPROVED/REJECTED/PAUSED/DISABLED), `meta_reason`, `components`. Status lokal `status`
(pending/approved/rejected) adalah SATU kebenaran yang dipakai gateway: di mode simulasi template
baru langsung `approved` (dicatat jujur `meta_status=NOT_SUBMITTED`); di mode live `pending` sampai
disetujui Meta lewat sinkron atau webhook `message_template_status_update`.
"""
import logging
import re

import httpx

import wa_gateway as gw
from core_utils import now_iso
from db import db
from meta_api import GRAPH_BASE

logger = logging.getLogger("sipro.wa_templates_meta")
STATUS_MAP = {"APPROVED": "approved", "REJECTED": "rejected", "PAUSED": "rejected", "DISABLED": "rejected",
              "PENDING": "pending", "IN_APPEAL": "pending", "PENDING_DELETION": "rejected"}
_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


# Contoh nilai bawaan per nama variabel — Meta MEWAJIBKAN `example` untuk setiap placeholder
# (tanpa itu template ditolak INVALID_FORMAT; audit WA-13). Variabel di luar daftar ini harus
# diberi contoh eksplisit lewat `template.examples`.
DEFAULT_EXAMPLES = {
    "nama": "Budi Santoso", "name": "Budi Santoso", "unit": "A-01", "termin": "Termin 2",
    "nominal": "Rp 25.000.000", "tanggal": "15 Oktober 2026", "date": "15 Oktober 2026",
    "bagian": "Atap & talang", "sisa": "14", "bulan": "2", "terlama": "45",
    "dokumen": "Surat Pemesanan Rumah", "nomor": "SPR/2026/09/001", "org": "Harmony Land 5",
    "proyek": "Harmony Land 5", "harga": "Rp 850.000.000", "tipe": "Tipe 45/90",
}


def body_placeholders(body: str) -> list:
    """Placeholder bernama pada body, urut kemunculan, tanpa duplikat, tanpa `{{1}}` numerik."""
    out = []
    for v in _VAR.findall(body or ""):
        if not v.isdigit() and v not in out:
            out.append(v)
    return out


def validate_variables(body: str, variables: list, header_text: str = None) -> str:
    """Body ↔ variables harus SAMA persis (audit WA-04). Kembalikan pesan kesalahan atau ''.

    Saat pengajuan, Meta menomori `{{1}}..{{n}}` dari body; saat kirim, gateway menyusun
    parameter dari `variables`. Bila keduanya berbeda, jumlah parameter tidak cocok dan Meta
    menolak (#132000). Jadi ketidakcocokan ditolak di pintu simpan, bukan ditemukan di live.
    """
    vars_ = list(variables or [])
    if len(set(vars_)) != len(vars_):
        return "Daftar variabel memuat nama ganda."
    holders = body_placeholders(body) + [v for v in body_placeholders(header_text or "")
                                          if v not in body_placeholders(body)]
    hilang = [v for v in holders if v not in vars_]
    if hilang:
        return ("Placeholder {{%s}} dipakai di isi pesan tetapi tidak didaftarkan di kolom Variabel."
                % "}}, {{".join(hilang))
    nganggur = [v for v in vars_ if v not in holders]
    if nganggur:
        return ("Variabel '%s' didaftarkan tetapi tidak muncul di isi pesan sebagai {{%s}}."
                % ("', '".join(nganggur), nganggur[0]))
    return ""


def example_values(template: dict) -> tuple:
    """(daftar contoh urut `variables`, daftar variabel yang belum punya contoh)."""
    given = template.get("examples") or {}
    vals, missing = [], []
    for v in template.get("variables") or []:
        ex = (given.get(v) or DEFAULT_EXAMPLES.get(v) or "").strip() if isinstance(given, dict) else DEFAULT_EXAMPLES.get(v, "")
        if not ex:
            missing.append(v)
        vals.append(ex)
    return vals, missing


def to_meta_body(body: str, variables: list) -> str:
    """`{{nama}}` → `{{1}}` mengikuti urutan `variables` (variabel tak terdaftar ditambahkan di belakang)."""
    order = list(variables or [])
    for v in _VAR.findall(body or ""):
        if v not in order and not v.isdigit():
            order.append(v)
    out = body or ""
    for i, v in enumerate(order, 1):
        out = re.sub(r"\{\{\s*%s\s*\}\}" % re.escape(v), "{{%d}}" % i, out)
    return out


def meta_components(template: dict) -> list:
    comps = []
    if template.get("header_type") == "document":
        hdr = {"type": "HEADER", "format": "DOCUMENT"}
        if template.get("header_sample_handle"):
            hdr["example"] = {"header_handle": [template["header_sample_handle"]]}
        comps.append(hdr)
    elif template.get("header_type") == "image":
        comps.append({"type": "HEADER", "format": "IMAGE"})
    elif template.get("header_type") == "text" and template.get("header_text"):
        hdr = {"type": "HEADER", "format": "TEXT",
               "text": to_meta_body(template["header_text"], template.get("variables"))}
        hv = body_placeholders(template["header_text"])
        if hv:
            exmap = dict(zip(template.get("variables") or [], example_values(template)[0]))
            hdr["example"] = {"header_text": [exmap.get(v, "") for v in hv][:1]}
        comps.append(hdr)
    body_comp = {"type": "BODY", "text": to_meta_body(template.get("body", ""), template.get("variables"))}
    ex_vals, _missing = example_values(template)
    if body_placeholders(template.get("body", "")):
        # WA-13: tanpa `example.body_text` Meta menolak INVALID_FORMAT untuk template bervariabel.
        body_comp["example"] = {"body_text": [ex_vals]}
    comps.append(body_comp)
    for c in template.get("components") or []:
        if c.get("type") in ("HEADER", "FOOTER", "BUTTONS") and not (c.get("type") == "HEADER" and comps[0]["type"] == "HEADER"):
            comps.append(c)
    return comps


def initial_fields(code: str, live: bool) -> dict:
    return {"meta_name": code, "meta_id": None, "meta_status": "NOT_SUBMITTED", "meta_reason": None,
            "components": [], "status": "pending" if live else "approved",
            "status_note": ("Menunggu persetujuan Meta — ajukan lewat tombol 'Ajukan ke Meta'." if live else
                            "Mode simulasi: template dianggap disetujui agar alur bisa diuji; saat live wajib "
                            "diajukan dan disetujui Meta.")}


def apply_meta_status(tmpl_upd: dict, meta_status: str, reason: str = None) -> dict:
    ms = (meta_status or "").upper()
    tmpl_upd.update({"meta_status": ms or "NOT_SUBMITTED", "meta_reason": reason,
                     "status": STATUS_MAP.get(ms, "pending"), "meta_synced_at": now_iso()})
    return tmpl_upd


async def submit(org_id: str, tmpl: dict) -> dict:
    cfg = await gw.get_config(org_id)
    creds = cfg["creds"]
    if cfg["effective_mode"] != "live" or not creds.get("waba_id"):
        return {"ok": False, "error_code": "not_live",
                "detail": "Mengajukan template membutuhkan mode LIVE + WHATSAPP_WABA_ID. Di mode simulasi tidak ada "
                          "yang dikirim ke Meta (jujur: tidak dipalsukan)."}
    salah = validate_variables(tmpl.get("body", ""), tmpl.get("variables"), tmpl.get("header_text"))
    if salah:
        return {"ok": False, "error_code": "variables_mismatch", "detail": salah}
    _vals, missing = example_values(tmpl)
    if missing:
        return {"ok": False, "error_code": "example_required",
                "detail": ("Meta mewajibkan contoh nilai untuk setiap variabel. Belum ada contoh untuk: "
                           + ", ".join(missing) + ". Isi kolom 'Contoh nilai' pada template.")}
    payload = {"name": tmpl.get("meta_name") or tmpl["code"], "language": tmpl.get("language") or "id",
               "category": (tmpl.get("category") or "utility").upper(), "components": meta_components(tmpl)}
    if tmpl.get("header_type") in ("document", "image") and not tmpl.get("header_sample_handle"):
        return {"ok": False, "error_code": "header_sample_required",
                "detail": "Template berheader dokumen/gambar membutuhkan CONTOH berkas (header_handle dari "
                          "Resumable Upload API Meta) sebelum diajukan. Isi 'Contoh header (handle)' pada template."}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(f"{GRAPH_BASE}/{creds['waba_id']}/message_templates", json=payload,
                           headers={"Authorization": f"Bearer {creds['token']}"})
    if r.status_code >= 300:
        code, detail = gw.MetaCloudAdapter._err(r)
        await db.wa_templates.update_one({"id": tmpl["id"]}, {"$set": {"meta_last_error": f"{code}: {detail}"}})
        return {"ok": False, "error_code": code, "detail": detail}
    data = r.json()
    upd = apply_meta_status({"meta_id": data.get("id"), "meta_name": payload["name"], "meta_last_error": None},
                            data.get("status") or "PENDING")
    await db.wa_templates.update_one({"id": tmpl["id"]}, {"$set": upd})
    return {"ok": True, "meta": data, "template": {**tmpl, **upd}}


async def sync(org_id: str) -> dict:
    cfg = await gw.get_config(org_id)
    creds = cfg["creds"]
    if not (creds.get("token") and creds.get("waba_id")):
        return {"ok": False, "error_code": "no_credentials",
                "detail": "Sinkron template membutuhkan WHATSAPP_TOKEN + WHATSAPP_WABA_ID."}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(f"{GRAPH_BASE}/{creds['waba_id']}/message_templates",
                          params={"limit": 200, "fields": "id,name,status,category,language,rejected_reason,components"},
                          headers={"Authorization": f"Bearer {creds['token']}"})
    if r.status_code >= 300:
        code, detail = gw.MetaCloudAdapter._err(r)
        return {"ok": False, "error_code": code, "detail": detail}
    rows = r.json().get("data") or []
    matched = 0
    for m in rows:
        upd = apply_meta_status({"meta_id": m.get("id"), "meta_category": m.get("category")},
                                m.get("status"), m.get("rejected_reason"))
        res = await db.wa_templates.update_one(
            {"org_id": org_id, "$or": [{"meta_id": m.get("id")}, {"meta_name": m.get("name")}]}, {"$set": upd})
        matched += res.matched_count
    return {"ok": True, "remote": len(rows), "matched": matched,
            "approved": sum(1 for m in rows if m.get("status") == "APPROVED"), "templates": rows}


async def on_status_webhook(org_id: str, value: dict) -> dict:
    """`message_template_status_update` → status lokal ikut Meta; REJECTED otomatis tak bisa dipilih."""
    upd = apply_meta_status({}, value.get("event"), value.get("reason") or (value.get("other_info") or {}).get("description"))
    q = {"org_id": org_id, "$or": [{"meta_id": str(value.get("message_template_id"))},
                                   {"meta_name": value.get("message_template_name")}]}
    res = await db.wa_templates.update_one(q, {"$set": upd})
    return {"matched": res.matched_count, "status": upd["status"], "meta_status": upd["meta_status"]}
