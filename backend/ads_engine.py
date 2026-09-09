"""ads_engine.py — Fase 43: master kampanye + biaya iklan (manual/CSV) yang bisa dipercaya.

Masalah nyata yang ditutup modul ini (`docs/v2/30_MARKETING_INTEGRATION_SPEC.md` §4–§5):

1. **Biaya iklan tidak pernah ada di sistem.** Semua metrik pemasaran (CPL, CAC, ROAS)
   selama ini tidak bisa dihitung sama sekali; angka "CPL" di layar lama sengaja
   dikosongkan. Tanpa `ad_spend` tidak ada satu pun keputusan anggaran yang bisa diaudit.
2. **Impor CSV yang tidak idempoten = uang dihitung dua kali.** Tim marketing mengunduh
   laporan platform per minggu dan rentang tanggalnya sering bertumpuk. Karena itu kunci
   natural `(org_id, platform, campaign_id, adset_id, ad_id, date)` dijaga UNIQUE di
   database, dan impor kedua atas berkas yang sama menghasilkan `unchanged`, bukan baris
   kedua. Bila angka berubah, baris LAMA diperbarui dan nilai sebelumnya disimpan di
   `history` — biaya tidak boleh berubah diam-diam.
3. **Berkas cacat diterima diam-diam.** Setiap baris divalidasi lebih dulu (dry-run) dan
   yang ditolak WAJIB menyebut alasannya: tanggal tidak dikenal, tanggal di masa depan,
   kampanye belum terdaftar, mata uang tidak didukung, angka bukan bilangan, atau baris
   kembar di dalam berkas yang sama. Tidak ada "last write wins" senyap.
4. **Mata uang selain IDR ditolak, bukan dikonversi.** Tidak ada kurs yang bisa
   dipertanggungjawabkan di dalam aplikasi; mengalikan dengan kurs karangan akan merusak
   seluruh laporan biaya. Jadi barisnya ditolak dengan alasan jelas.

Modul ini murni data+logika (tanpa FastAPI) supaya bisa diuji langsung oleh POC & gate.
"""
import csv
import hashlib
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import reference as ref
import sequences as seq
from core_utils import new_id, now_iso, today_iso_date
from db import db, ORG_ID

logger = logging.getLogger("sipro.ads")

CURRENCY = "IDR"
MAX_IMPORT_ROWS = 5000

# Kolom CSV (SSOT nama kolom) — spec §5. Wajib: 4 kolom pertama.
CSV_REQUIRED = ("date", "platform", "campaign_name", "spend")
CSV_OPTIONAL = ("campaign_id", "adset_name", "adset_id", "ad_name", "ad_id",
                "impressions", "clicks", "leads_platform", "currency")
CSV_COLUMNS = CSV_REQUIRED + CSV_OPTIONAL
# Kunci natural baris biaya (tanpa org_id, ditambahkan saat query).
KEY_FIELDS = ("platform", "campaign_id", "adset_id", "ad_id", "date")
# Field yang dibandingkan untuk memutuskan "unchanged" vs "update".
VALUE_FIELDS = ("spend", "impressions", "clicks", "leads_platform", "currency",
                "campaign_name", "adset_name", "ad_name", "campaign_external_id")

# Sinonim header CSV → nama kanonik. Laporan Meta/Google memakai judul kolom yang
# berbeda-beda; tanpa peta ini pemakai harus mengedit berkas ekspor secara manual.
HEADER_SYNONYMS = {
    "tanggal": "date", "day": "date", "date_start": "date", "reporting_starts": "date",
    "platform": "platform", "kanal": "platform",
    "campaign": "campaign_name", "campaign_name": "campaign_name", "kampanye": "campaign_name",
    "nama_kampanye": "campaign_name", "campaign_id": "campaign_id",
    "adset": "adset_name", "ad_set_name": "adset_name", "adset_name": "adset_name",
    "ad_group": "adset_name", "ad_group_name": "adset_name", "adset_id": "adset_id",
    "ad_set_id": "adset_id", "ad_group_id": "adset_id",
    "ad": "ad_name", "ad_name": "ad_name", "ad_id": "ad_id",
    "spend": "spend", "biaya": "spend", "cost": "spend", "amount_spent": "spend",
    "amount_spent_idr": "spend", "biaya_iklan": "spend",
    "impressions": "impressions", "impresi": "impressions", "impr": "impressions",
    "clicks": "clicks", "klik": "clicks", "link_clicks": "clicks",
    "leads": "leads_platform", "leads_platform": "leads_platform", "results": "leads_platform",
    "prospek": "leads_platform",
    "currency": "currency", "mata_uang": "currency",
}


# --------------------------------------------------------------------- helper nilai
def _s(value) -> str:
    return "" if value is None else str(value).strip()


def canonical_header(header: str) -> str:
    """'Amount spent (IDR)' -> 'spend'. Mengembalikan '' bila kolom tidak dikenal."""
    raw = _s(header).lower()
    raw = re.sub(r"\(.*?\)", " ", raw)
    raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if raw in CSV_COLUMNS:
        return raw
    return HEADER_SYNONYMS.get(raw, "")


def parse_date(value):
    """-> (tanggal ISO 'YYYY-MM-DD', error). Menerima YYYY-MM-DD dan DD/MM/YYYY."""
    raw = _s(value)
    if not raw:
        return None, "tanggal kosong"
    raw = raw.split("T")[0].split(" ")[0]
    forms = ((r"^(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"),
             (r"^(\d{4})/(\d{1,2})/(\d{1,2})$", "ymd"),
             (r"^(\d{1,2})/(\d{1,2})/(\d{4})$", "dmy"),
             (r"^(\d{1,2})-(\d{1,2})-(\d{4})$", "dmy"))
    for pattern, order in forms:
        m = re.match(pattern, raw)
        if not m:
            continue
        a, b, c = m.groups()
        y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
        try:
            return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc).date().isoformat(), None
        except ValueError:
            return None, f"tanggal '{raw}' tidak ada di kalender"
    return None, f"format tanggal '{raw}' tidak dikenal (pakai YYYY-MM-DD atau DD/MM/YYYY)"


def parse_amount(value, *, field="Biaya", blank_ok=False):
    """Angka rupiah dari teks laporan platform -> (int, error).

    Menerima '1.234.567', '1,234,567', '1234567,50', 'Rp 1.234.567'. Aturan pemisah:
    bila ada '.' DAN ',' maka yang paling kanan dianggap desimal; bila hanya '.' dengan
    3 digit di belakang -> pemisah ribuan (konvensi Indonesia). Nilai desimal dibulatkan
    ke rupiah terdekat karena biaya iklan dibukukan dalam rupiah utuh.
    """
    raw = _s(value).replace("\u00a0", " ")
    raw = re.sub(r"(?i)\brp\b\.?", "", raw).replace(" ", "")
    if not raw:
        return (None, None) if blank_ok else (None, f"{field} kosong")
    negative = raw.startswith("-")
    raw = raw.lstrip("+-")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        head, _, tail = raw.rpartition(",")
        raw = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else raw.replace(",", "")
    elif raw.count(".") >= 1:
        head, _, tail = raw.rpartition(".")
        if len(tail) == 3 and head:
            raw = raw.replace(".", "")
    if not re.fullmatch(r"\d+(\.\d+)?", raw):
        return None, f"{field} '{value}' bukan angka"
    if negative:
        return None, f"{field} tidak boleh negatif ({value})"
    # Pembulatan HALF_UP, bukan pembulatan bawaan Python (half-even): 2.500.000,50 harus
    # menjadi 2.500.001 seperti yang dilakukan orang keuangan dengan kalkulator, bukan
    # 2.500.000. Selisih satu rupiah tidak penting; yang penting hasilnya bisa diprediksi
    # dan sama dengan hitungan tangan saat diaudit.
    return int(Decimal(raw).quantize(Decimal("1"), rounding=ROUND_HALF_UP)), None


def key_of(row: dict, org_id: str = ORG_ID) -> dict:
    """Kunci natural sebagai query Mongo. Nilai kosong dinormalkan ke '' (bukan None)
    supaya index unik konsisten — di MongoDB `null` dan field yang tidak ada berbeda."""
    out = {"org_id": org_id}
    for f in KEY_FIELDS:
        out[f] = _s(row.get(f))
    return out


def key_string(row: dict) -> str:
    return "|".join(_s(row.get(f)) for f in KEY_FIELDS)


def changed_fields(existing: dict, row: dict) -> list:
    diff = []
    for f in VALUE_FIELDS:
        before, after = existing.get(f), row.get(f)
        if (before or None) != (after or None):
            diff.append({"field": f, "before": before, "after": after})
    return diff


# ------------------------------------------------------------------ master kampanye
async def campaign_index(org_id: str = ORG_ID) -> dict:
    """Indeks kampanye untuk mencocokkan baris CSV (per platform: id eksternal & nama)."""
    rows = await db.campaigns.find({"org_id": org_id}, {"_id": 0}).to_list(MAX_IMPORT_ROWS)
    by_ext, by_name = {}, {}
    for r in rows:
        if r.get("external_id"):
            by_ext[(r["platform"], _s(r["external_id"]).lower())] = r
        by_name[(r["platform"], _s(r.get("name")).lower())] = r
    return {"rows": rows, "by_ext": by_ext, "by_name": by_name}


def resolve_campaign(index: dict, platform: str, *, external_id=None, name=None):
    if external_id:
        hit = index["by_ext"].get((platform, _s(external_id).lower()))
        if hit:
            return hit
    if name:
        hit = index["by_name"].get((platform, _s(name).lower()))
        if hit:
            return hit
    return None


async def create_campaign(payload: dict, *, org_id: str = ORG_ID, actor: str = "system") -> dict:
    """Simpan kampanye baru. Nama per platform harus unik supaya baris CSV bisa dicocokkan
    tanpa ambigu (dua kampanye bernama sama = biaya tidak bisa dipertanggungjawabkan)."""
    platform = payload.get("platform")
    name = _s(payload.get("name"))
    dup = await db.campaigns.find_one({"org_id": org_id, "platform": platform, "name": name},
                                      {"_id": 0, "code": 1})
    if dup:
        raise ValueError(f"Kampanye '{name}' sudah terdaftar di platform ini ({dup['code']}).")
    if payload.get("external_id"):
        dup_ext = await db.campaigns.find_one(
            {"org_id": org_id, "platform": platform, "external_id": payload["external_id"]},
            {"_id": 0, "name": 1})
        if dup_ext:
            raise ValueError(f"ID platform '{payload['external_id']}' sudah dipakai kampanye "
                             f"{dup_ext['name']}.")
    if payload.get("start_date") and payload.get("end_date") \
            and payload["end_date"] < payload["start_date"]:
        raise ValueError("Tanggal berakhir tidak boleh sebelum tanggal mulai.")
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id,
        "code": await seq.next_number("campaign", org_id, prefix="CMP", width=4),
        "platform": platform, "external_id": payload.get("external_id") or None,
        "name": name, "objective": payload.get("objective") or "leads",
        "project_ids": payload.get("project_ids") or [], "cluster_ids": payload.get("cluster_ids") or [],
        "audience_note": payload.get("audience_note"),
        "budget_daily": int(payload.get("budget_daily") or 0),
        "budget_total": int(payload.get("budget_total") or 0),
        "start_date": payload.get("start_date"), "end_date": payload.get("end_date"),
        "status": payload.get("status") or "draft",
        "owner_email": payload.get("owner_email") or actor,
        "source": payload.get("source") or "manual", "last_synced_at": None,
        "note": payload.get("note"),
        "created_by": actor, "created_at": ts, "updated_at": ts,
    }
    await db.campaigns.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_campaign(campaign_id: str, patch: dict, *, org_id: str = ORG_ID,
                          actor: str = "system") -> dict:
    cur = await db.campaigns.find_one({"id": campaign_id, "org_id": org_id}, {"_id": 0})
    if not cur:
        raise ValueError("Kampanye tidak ditemukan.")
    body = {k: v for k, v in (patch or {}).items() if v is not None}
    name = _s(body.get("name"))
    if name and name.lower() != _s(cur.get("name")).lower():
        dup = await db.campaigns.find_one(
            {"org_id": org_id, "platform": body.get("platform") or cur["platform"],
             "name": name, "id": {"$ne": campaign_id}}, {"_id": 0, "code": 1})
        if dup:
            raise ValueError(f"Kampanye '{name}' sudah terdaftar di platform ini ({dup['code']}).")
    start = body.get("start_date", cur.get("start_date"))
    end = body.get("end_date", cur.get("end_date"))
    if start and end and end < start:
        raise ValueError("Tanggal berakhir tidak boleh sebelum tanggal mulai.")
    body["updated_at"] = now_iso()
    body["updated_by"] = actor
    await db.campaigns.update_one({"id": campaign_id}, {"$set": body})
    return await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})


async def campaign_spend_totals(campaign_ids: list, *, org_id: str = ORG_ID,
                                date_from: str = None, date_to: str = None) -> dict:
    """{campaign_id: {spend, impressions, clicks, leads_platform, days, sources[]}} — agregasi
    dijalankan di DATABASE (bukan menarik seluruh baris ke Python)."""
    match = {"org_id": org_id}
    if campaign_ids:
        match["campaign_id"] = {"$in": list(campaign_ids)}
    _apply_date_match(match, date_from, date_to)
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$campaign_id",
            "spend": {"$sum": "$spend"}, "impressions": {"$sum": "$impressions"},
            "clicks": {"$sum": "$clicks"}, "leads_platform": {"$sum": "$leads_platform"},
            "days": {"$addToSet": "$date"}, "sources": {"$addToSet": "$source"},
            "rows": {"$sum": 1},
        }},
    ]
    out = {}
    async for row in db.ad_spend.aggregate(pipeline):
        out[row["_id"]] = {
            "spend": int(row.get("spend") or 0),
            "impressions": int(row.get("impressions") or 0),
            "clicks": int(row.get("clicks") or 0),
            "leads_platform": int(row.get("leads_platform") or 0),
            "days": sorted(d for d in (row.get("days") or []) if d),
            "sources": sorted(s for s in (row.get("sources") or []) if s),
            "rows": int(row.get("rows") or 0),
        }
    return out


def _apply_date_match(match: dict, date_from: str, date_to: str):
    cond = {}
    if date_from:
        cond["$gte"] = date_from
    if date_to:
        cond["$lte"] = date_to
    if cond:
        match["date"] = cond
    return match


# ------------------------------------------------------------------- biaya: upsert
async def upsert_spend(row: dict, *, org_id: str = ORG_ID, source: str = "manual",
                       actor: str = "system", import_id: str = None) -> tuple:
    """Simpan satu baris biaya harian. -> ('inserted'|'updated'|'unchanged', dokumen).

    Idempoten pada kunci natural. Perubahan nilai TIDAK menimpa diam-diam: nilai lama
    disimpan di `history` beserta siapa & kapan mengubahnya.
    """
    query = key_of(row, org_id)
    existing = await db.ad_spend.find_one(query, {"_id": 0})
    ts = now_iso()
    values = {f: row.get(f) for f in VALUE_FIELDS}
    values["currency"] = values.get("currency") or CURRENCY
    if not existing:
        doc = {"id": new_id(), **query, **values, "source": source, "import_id": import_id,
               "created_by": actor, "created_at": ts, "updated_by": actor, "updated_at": ts,
               "revisions": 0, "history": []}
        await db.ad_spend.insert_one(dict(doc))
        doc.pop("_id", None)
        return "inserted", doc
    diff = changed_fields(existing, values)
    if not diff:
        return "unchanged", existing
    await db.ad_spend.update_one({"id": existing["id"]}, {
        "$set": {**values, "source": source, "import_id": import_id,
                 "updated_by": actor, "updated_at": ts},
        "$inc": {"revisions": 1},
        "$push": {"history": {"at": ts, "by": actor, "source": source, "changes": diff}},
    })
    fresh = await db.ad_spend.find_one({"id": existing["id"]}, {"_id": 0})
    return "updated", fresh


async def manual_entry(payload: dict, *, org_id: str = ORG_ID, actor: str = "system") -> tuple:
    """Entri manual harian (form ringkas). Kampanye WAJIB sudah terdaftar."""
    campaign = await db.campaigns.find_one({"id": payload.get("campaign_id"), "org_id": org_id},
                                           {"_id": 0})
    if not campaign:
        raise ValueError("Kampanye tidak ditemukan — daftarkan kampanyenya lebih dulu.")
    date_iso, err = parse_date(payload.get("date"))
    if err:
        raise ValueError(err.capitalize())
    if date_iso > today_iso_date():
        raise ValueError(f"Tanggal {date_iso} ada di masa depan — biaya iklan hanya bisa "
                         "dicatat untuk hari yang sudah berjalan.")
    spend, err = parse_amount(payload.get("spend"))
    if err:
        raise ValueError(err.capitalize())
    row = {
        "platform": campaign["platform"], "campaign_id": campaign["id"],
        "campaign_external_id": campaign.get("external_id"), "campaign_name": campaign["name"],
        "adset_id": _s(payload.get("adset_id")), "adset_name": _s(payload.get("adset_name")) or None,
        "ad_id": _s(payload.get("ad_id")), "ad_name": _s(payload.get("ad_name")) or None,
        "date": date_iso, "spend": spend, "currency": CURRENCY,
    }
    for field, label in (("impressions", "Impresi"), ("clicks", "Klik"),
                         ("leads_platform", "Lead platform")):
        val, err = parse_amount(payload.get(field), field=label, blank_ok=True)
        if err:
            raise ValueError(err.capitalize())
        row[field] = val
    return await upsert_spend(row, org_id=org_id, source="manual", actor=actor)


# ---------------------------------------------------------------------- impor CSV
def parse_csv(text: str, mapping: dict = None) -> tuple:
    """-> (rows, error). rows = [{'line': n, 'raw': {kolom_kanonik: nilai}}]."""
    if not _s(text):
        return [], "Berkas CSV kosong."
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return [], "Header CSV tidak terbaca."
    header_map, unknown = {}, []
    for head in reader.fieldnames:
        key = _s((mapping or {}).get(head) or (mapping or {}).get(_s(head).lower())) \
            or canonical_header(head)
        if key in CSV_COLUMNS:
            header_map[head] = key
        else:
            unknown.append(_s(head))
    missing = [c for c in CSV_REQUIRED if c not in header_map.values()]
    if missing:
        return [], ("Kolom wajib tidak ditemukan: " + ", ".join(missing)
                    + ". Kolom yang terbaca: " + (", ".join(unknown + list(header_map.values()))
                                                  or "(tidak ada)")
                    + ". Pakai pemetaan kolom bila judul berkas berbeda.")
    rows = []
    for i, raw in enumerate(reader, start=2):
        if all(not _s(v) for v in raw.values()):
            continue  # baris kosong di akhir berkas: bukan cacat
        rows.append({"line": i, "raw": {header_map[h]: raw.get(h) for h in header_map}})
        if len(rows) > MAX_IMPORT_ROWS:
            return [], (f"Berkas terlalu besar (>{MAX_IMPORT_ROWS} baris). Pecah per bulan "
                        "supaya laporan impornya masih bisa diperiksa manusia.")
    if not rows:
        return [], "Tidak ada baris data di bawah header."
    return rows, None


def validate_row(entry: dict, index: dict, *, today: str, seen: dict) -> tuple:
    """-> (baris bersih | None, alasan penolakan | None)."""
    raw = entry["raw"]
    platform = ref.canonicalize("ad_platform", raw.get("platform"))
    if platform not in ref.values("ad_platform"):
        return None, (f"platform '{_s(raw.get('platform')) or '(kosong)'}' tidak dikenal "
                      f"(pilihan: {', '.join(ref.values('ad_platform'))})")
    date_iso, err = parse_date(raw.get("date"))
    if err:
        return None, err
    if date_iso > today:
        return None, f"tanggal {date_iso} ada di masa depan"
    currency = (_s(raw.get("currency")) or CURRENCY).upper()
    if currency != CURRENCY:
        return None, (f"mata uang {currency} tidak didukung — tidak ada kurs yang bisa "
                      "dipertanggungjawabkan di sistem, konversikan dulu ke IDR")
    spend, err = parse_amount(raw.get("spend"))
    if err:
        return None, err
    campaign = resolve_campaign(index, platform, external_id=raw.get("campaign_id"),
                               name=raw.get("campaign_name"))
    if not campaign:
        return None, (f"kampanye '{_s(raw.get('campaign_name')) or _s(raw.get('campaign_id'))}' "
                      f"belum terdaftar di platform {platform} — daftarkan dulu di tab Kampanye "
                      "supaya biayanya punya pemilik")
    row = {
        "platform": platform, "campaign_id": campaign["id"],
        "campaign_external_id": campaign.get("external_id") or _s(raw.get("campaign_id")) or None,
        "campaign_name": campaign["name"],
        "adset_id": _s(raw.get("adset_id")), "adset_name": _s(raw.get("adset_name")) or None,
        "ad_id": _s(raw.get("ad_id")), "ad_name": _s(raw.get("ad_name")) or None,
        "date": date_iso, "spend": spend, "currency": CURRENCY,
    }
    for field, label in (("impressions", "impresi"), ("clicks", "klik"),
                         ("leads_platform", "lead platform")):
        val, err = parse_amount(raw.get(field), field=label, blank_ok=True)
        if err:
            return None, err
        row[field] = val
    key = key_string(row)
    if key in seen:
        return None, (f"baris kembar di dalam berkas ini (sama dengan baris {seen[key]}): "
                      "satu kampanye/adset/iklan hanya boleh punya satu angka per tanggal")
    seen[key] = entry["line"]
    return row, None


async def plan_import(text: str, *, org_id: str = ORG_ID, mapping: dict = None) -> dict:
    """Dry-run: validasi seluruh berkas TANPA menyimpan apa pun."""
    rows, err = parse_csv(text, mapping)
    checksum = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    if err:
        return {"ok": False, "error": err, "checksum": checksum, "rows": [],
                "summary": {"total": 0, "new": 0, "update": 0, "unchanged": 0, "rejected": 0,
                            "spend_total": 0}}
    index = await campaign_index(org_id)
    today = today_iso_date()
    seen, out, summary = {}, [], {"total": 0, "new": 0, "update": 0, "unchanged": 0,
                                  "rejected": 0, "spend_total": 0}
    for entry in rows:
        summary["total"] += 1
        clean, reason = validate_row(entry, index, today=today, seen=seen)
        if reason:
            summary["rejected"] += 1
            out.append({"line": entry["line"], "status": "rejected", "reason": reason,
                        "raw": entry["raw"]})
            continue
        existing = await db.ad_spend.find_one(key_of(clean, org_id), {"_id": 0})
        if not existing:
            status, diff = "new", []
        else:
            diff = changed_fields(existing, clean)
            status = "update" if diff else "unchanged"
        summary[status] += 1
        summary["spend_total"] += int(clean["spend"])
        out.append({"line": entry["line"], "status": status, "reason": None, "row": clean,
                    "key": key_string(clean), "diff": diff})
    return {"ok": True, "error": None, "rows": out, "summary": summary, "checksum": checksum}


async def save_import(plan: dict, *, org_id: str = ORG_ID, actor: str = "system",
                      filename: str = None, mapping: dict = None, dry_run: bool = True) -> dict:
    """Simpan laporan impor. Statusnya SELALU `preview` sampai `apply_import` benar-benar
    menulis ke `ad_spend` (dulu commit langsung ditandai `committed` di sini, sehingga
    `apply_import` menganggapnya sudah pernah dijalankan dan TIDAK menyimpan satu baris pun —
    impor tampak sukses padahal biayanya tidak masuk)."""
    ts = now_iso()
    doc = {
        "id": new_id(), "org_id": org_id, "filename": filename or "biaya-iklan.csv",
        "checksum": plan.get("checksum"), "mapping": mapping or {},
        "status": "preview" if plan.get("ok") else "failed",
        "dry_run": bool(dry_run),
        "error": plan.get("error"), "summary": plan.get("summary"),
        "rows": plan.get("rows"), "imported_by": actor, "created_at": ts,
        "committed_at": None,
        "platforms": sorted({r["row"]["platform"] for r in plan.get("rows") or []
                             if r.get("row")}),
    }
    await db.ads_imports.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def apply_import(import_doc: dict, *, org_id: str = ORG_ID, actor: str = "system") -> dict:
    """Terapkan baris yang lolos validasi ke `ad_spend` (idempoten per kunci natural)."""
    if import_doc.get("status") == "committed":
        return import_doc  # sudah pernah dikomit: jangan menghitung uang dua kali
    if not import_doc.get("rows"):
        raise ValueError("Laporan impor ini tidak punya baris yang bisa disimpan.")
    applied = {"inserted": 0, "updated": 0, "unchanged": 0}
    for r in import_doc["rows"]:
        if r.get("status") == "rejected" or not r.get("row"):
            continue
        status, _doc = await upsert_spend(r["row"], org_id=org_id, source="csv", actor=actor,
                                         import_id=import_doc["id"])
        applied[status] += 1
        r["applied"] = status
    ts = now_iso()
    await db.ads_imports.update_one({"id": import_doc["id"]}, {"$set": {
        "status": "committed", "committed_at": ts, "applied": applied,
        "rows": import_doc["rows"], "committed_by": actor}})
    if import_doc.get("mapping"):
        for platform in import_doc.get("platforms") or []:
            await db.ads_import_profiles.update_one(
                {"org_id": org_id, "platform": platform},
                {"$set": {"mapping": import_doc["mapping"], "updated_at": ts,
                          "updated_by": actor},
                 "$setOnInsert": {"id": new_id(), "created_at": ts}}, upsert=True)
    return await db.ads_imports.find_one({"id": import_doc["id"]}, {"_id": 0})


async def import_csv(text: str, *, org_id: str = ORG_ID, actor: str = "system",
                     filename: str = None, mapping: dict = None, dry_run: bool = True) -> dict:
    """Satu pintu: dry-run (default) atau langsung commit. Selalu meninggalkan laporan."""
    plan = await plan_import(text, org_id=org_id, mapping=mapping)
    doc = await save_import(plan, org_id=org_id, actor=actor, filename=filename,
                            mapping=mapping, dry_run=dry_run or not plan["ok"])
    if dry_run or not plan["ok"]:
        return doc
    return await apply_import(doc, org_id=org_id, actor=actor)


# ------------------------------------------------------------------ agregasi biaya
WEEK_START = "%G-W%V"


def bucket_of(date_iso: str, period: str) -> str:
    """Label bucket agregasi ('2026-08-17' / '2026-W34' / '2026-08')."""
    if period == "monthly":
        return date_iso[:7]
    if period == "weekly":
        dt = datetime.fromisoformat(date_iso).replace(tzinfo=timezone.utc)
        return dt.strftime(WEEK_START).replace("-W", "-W")
    return date_iso


async def spend_series(*, org_id: str = ORG_ID, date_from: str = None, date_to: str = None,
                       period: str = "daily", platform: str = None,
                       campaign_id: str = None) -> list:
    """Deret biaya per bucket waktu (agregasi di database, lalu dikelompokkan per periode)."""
    match = {"org_id": org_id}
    if platform:
        match["platform"] = platform
    if campaign_id:
        match["campaign_id"] = campaign_id
    _apply_date_match(match, date_from, date_to)
    pipeline = [{"$match": match}, {"$group": {
        "_id": "$date", "spend": {"$sum": "$spend"}, "impressions": {"$sum": "$impressions"},
        "clicks": {"$sum": "$clicks"}, "leads_platform": {"$sum": "$leads_platform"},
        "sources": {"$addToSet": "$source"},
    }}, {"$sort": {"_id": 1}}]
    buckets = {}
    async for row in db.ad_spend.aggregate(pipeline):
        key = bucket_of(row["_id"], period)
        b = buckets.setdefault(key, {"bucket": key, "spend": 0, "impressions": 0, "clicks": 0,
                                     "leads_platform": 0, "days": 0, "sources": []})
        b["spend"] += int(row.get("spend") or 0)
        b["impressions"] += int(row.get("impressions") or 0)
        b["clicks"] += int(row.get("clicks") or 0)
        b["leads_platform"] += int(row.get("leads_platform") or 0)
        b["days"] += 1
        for s in row.get("sources") or []:
            if s and s not in b["sources"]:
                b["sources"].append(s)
    return [buckets[k] for k in sorted(buckets)]


def default_range(days: int = 30) -> tuple:
    """Rentang bawaan: `days` hari terakhir termasuk hari ini (tanggal ISO)."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()
