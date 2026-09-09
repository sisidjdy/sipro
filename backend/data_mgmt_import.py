"""Mesin impor master data dari hasil parse Excel (pratinjau & eksekusi).

Alur per baris: coerce tipe → validasi wajib/enum → resolusi rujukan → tentukan aksi
(insert / update / skip) → tulis bila bukan dry_run. Rujukan ke baris yang baru dibuat
pada berkas yang sama tetap terselesaikan (cache ctx) walau dry_run.
"""
import logging

from db import db
from core_utils import new_id, now_iso, normalize_phone_e164, normalize_nik
from security import hash_password
from data_mgmt_schema import ENTITIES, DEFAULT_IMPORT_PASSWORD, enum_options
from data_mgmt_coerce import coerce_row
import masterplan
import sequences as seq
from reference_p47 import LABOR_ROLE_LABEL

logger = logging.getLogger("sipro.data_mgmt")
ROW_LIMIT = 400


class RowError(Exception):
    pass


class Ctx:
    def __init__(self, org, actor, mode, dry_run):
        self.org, self.actor, self.mode, self.dry_run = org, actor, mode, dry_run
        self.cache = {}       # (coll, key) → doc (DB atau baris baru di berkas ini)
        self.seen = set()     # (entity, key) → duplikat dalam berkas
        self.touched_projects = set()
        self.ts = now_iso()

    async def lookup(self, coll: str, query: dict, cache_key: tuple = None):
        ck = (coll,) + (cache_key or tuple(sorted(query.items())))
        if ck in self.cache:
            return self.cache[ck]
        doc = await db[coll].find_one({**query, "org_id": self.org}, {"_id": 0})
        if doc:
            self.cache[ck] = doc
        return doc

    def remember(self, coll: str, doc: dict, *cache_keys):
        for ck in cache_keys:
            self.cache[(coll,) + ck] = doc

    async def write(self, coll: str, existing: dict, new_doc: dict, patch: dict) -> str:
        if existing:
            if self.mode == "skip":
                return "skip"
            if not self.dry_run:
                patch = {**patch, "updated_at": self.ts, "updated_by": self.actor}
                await db[coll].update_one({"id": existing["id"], "org_id": self.org}, {"$set": patch})
            existing.update(patch)
            return "update"
        if not self.dry_run:
            await db[coll].insert_one(dict(new_doc))
        return "insert"


def _base(ctx: Ctx, **fields) -> dict:
    return {"id": new_id(), "org_id": ctx.org, **fields, "created_by": ctx.actor,
            "created_at": ctx.ts, "updated_at": ctx.ts}


def _pick(v: dict, *keys) -> dict:
    return {k: v.get(k) for k in keys}


async def _project(ctx: Ctx, code: str) -> dict:
    p = await ctx.lookup("projects", {"code": code.upper()}, ("code", code.upper()))
    if not p:
        raise RowError(f"Proyek '{code}' tidak ada (di sistem maupun sheet Proyek).")
    return p


async def _cluster(ctx: Ctx, project: dict, code: str) -> dict:
    c = await ctx.lookup("clusters", {"project_id": project["id"], "code": code.upper()},
                         ("pc", project["id"], code.upper()))
    if not c:
        raise RowError(f"Cluster '{code}' tidak ada pada proyek {project['code']}.")
    return c


async def _block(ctx: Ctx, cluster: dict, code: str) -> dict:
    b = await ctx.lookup("blocks", {"cluster_id": cluster["id"], "code": code.upper()},
                         ("cb", cluster["id"], code.upper()))
    if not b:
        raise RowError(f"Blok '{code}' tidak ada pada cluster {cluster['code']}.")
    return b


# ------------------------------------------------------------------ handler per entitas
async def h_users(ctx, v, warn):
    email = v["email"]
    ex = await ctx.lookup("users", {"email": email}, ("email", email))
    pw = v.get("password")
    if not ex and not pw:
        warn.append(f"Sandi awal bawaan '{DEFAULT_IMPORT_PASSWORD}' dipakai — minta pengguna mengganti.")
    doc = _base(ctx, name=v["name"], email=email, role=v["role"], phone=v.get("phone"),
                is_active=v.get("is_active", True),
                password_hash=hash_password(pw or DEFAULT_IMPORT_PASSWORD))
    patch = _pick(v, "name", "role", "phone", "is_active")
    if pw:
        patch["password_hash"] = hash_password(pw)
    act = await ctx.write("users", ex, doc, patch)
    ctx.remember("users", ex or doc, ("email", email))
    return act, email


async def h_projects(ctx, v, warn):
    code = v["code"].upper()
    ex = await ctx.lookup("projects", {"code": code}, ("code", code))
    members = []
    for m in v.get("members") or []:
        m = m.lower()
        if await ctx.lookup("users", {"email": m}, ("email", m)):
            members.append(m)
        else:
            warn.append(f"Anggota '{m}' bukan pengguna terdaftar — dilewati.")
    doc = _base(ctx, name=v["name"], code=code, location=v.get("location"),
                status=v.get("status") or "active", members=members)
    patch = {**_pick(v, "name", "location", "status"), "members": members}
    act = await ctx.write("projects", ex, doc, patch)
    ctx.remember("projects", ex or doc, ("code", code))
    ctx.touched_projects.add((ex or doc)["id"])
    return act, code


async def h_clusters(ctx, v, warn):
    p = await _project(ctx, v["project_code"])
    code = v["code"].upper()
    ex = await ctx.lookup("clusters", {"project_id": p["id"], "code": code}, ("pc", p["id"], code))
    body = _pick(v, "name", "order", "status", "price_multiplier", "land_area", "unit_target",
                 "description")
    doc = _base(ctx, project_id=p["id"], code=code, **body)
    act = await ctx.write("clusters", ex, doc, body)
    ctx.remember("clusters", ex or doc, ("pc", p["id"], code))
    ctx.touched_projects.add(p["id"])
    return act, f"{p['code']}/{code}"


async def h_blocks(ctx, v, warn):
    p = await _project(ctx, v["project_code"])
    c = await _cluster(ctx, p, v["cluster_code"])
    code = v["code"].upper()
    ex = await ctx.lookup("blocks", {"cluster_id": c["id"], "code": code}, ("cb", c["id"], code))
    body = _pick(v, "order", "orientation", "notes")
    body["name"] = v.get("name") or f"Blok {code}"
    doc = _base(ctx, project_id=p["id"], cluster_id=c["id"], cluster_code=c["code"], code=code,
                **body)
    act = await ctx.write("blocks", ex, doc, body)
    ctx.remember("blocks", ex or doc, ("cb", c["id"], code))
    ctx.touched_projects.add(p["id"])
    return act, f"{p['code']}/{c['code']}/{code}"


async def h_unit_types(ctx, v, warn):
    code = v["code"].upper()
    ex = await ctx.lookup("unit_types", {"code": code}, ("code", code))
    body = _pick(v, "name", "building_area", "land_area_std", "base_price", "bedrooms",
                 "bathrooms", "floors", "active")
    doc = _base(ctx, code=code, spec={}, **body)
    act = await ctx.write("unit_types", ex, doc, body)
    ctx.remember("unit_types", ex or doc, ("code", code))
    return act, code


async def h_units(ctx, v, warn):
    p = await _project(ctx, v["project_code"])
    c = await _cluster(ctx, p, v["cluster_code"])
    b = await _block(ctx, c, v["block_code"])
    utype = None
    if v.get("unit_type_code"):
        utype = await ctx.lookup("unit_types", {"code": v["unit_type_code"].upper()},
                                 ("code", v["unit_type_code"].upper()))
        if not utype:
            raise RowError(f"Tipe unit '{v['unit_type_code']}' tidak ada.")
    code = masterplan.unit_code(b["code"], v["no"])
    ex = await ctx.lookup("units", {"project_id": p["id"], "code": code}, ("pu", p["id"], code))
    status = v.get("status") or "available"
    if ex:
        patch = {}
        if utype:
            patch.update({"unit_type_id": utype["id"], "unit_type_code": utype["code"],
                          "type": utype["name"]})
        for src, dst in (("land_area", "luas_tanah"), ("building_area", "luas_bangunan"),
                         ("price", "price"), ("is_hook", "corner"),
                         ("excess_land_m2", "excess_land_m2"), ("notes", "notes")):
            if v.get(src) is not None:
                patch[dst] = v[src]
        if status != ex.get("status"):
            if ex.get("status") == "available":
                patch["status"] = status
                patch["status_history"] = (ex.get("status_history") or []) + [
                    {"field": "status", "from": "available", "to": status, "at": ctx.ts,
                     "actor": ctx.actor, "reason": "Migrasi data (Excel)"}]
            else:
                warn.append(f"Status tetap '{ex.get('status')}' — unit sudah bertransaksi.")
        act = await ctx.write("units", ex, None, patch)
    else:
        if status in ("reserved", "booked"):
            raise RowError(f"Status '{status}' hanya lahir dari transaksi (reservasi/booking) di aplikasi.")
        doc = await masterplan._new_unit_doc(
            b, c, p, utype, no=v["no"], price=v.get("price"), corner=v.get("is_hook", False),
            luas_tanah=v.get("land_area"), luas_bangunan=v.get("building_area"),
            excess=v.get("excess_land_m2", 0), actor=ctx.actor, notes=v.get("notes"))
        if status != "available":
            doc["status"] = status
            doc["status_history"].append({"field": "status", "from": "available", "to": status,
                                          "at": ctx.ts, "actor": ctx.actor,
                                          "reason": "Migrasi data (Excel)"})
            warn.append(f"Unit ditandai '{status}' tanpa transaksi — tautkan pembeli lewat aplikasi.")
        act = await ctx.write("units", None, doc, {})
        ctx.remember("units", doc, ("pu", p["id"], code))
    ctx.touched_projects.add(p["id"])
    return act, f"{p['code']}/{code}"


async def h_addons(ctx, v, warn):
    code = v["code"].upper()
    ex = await ctx.lookup("addon_items", {"code": code}, ("code", code))
    body = _pick(v, "name", "category", "pricing_mode", "unit_price", "uom", "finance_treatment",
                 "gl_account", "negotiable", "active", "note")
    doc = _base(ctx, code=code, applies_project_ids=[], applies_unit_types=[], **body)
    act = await ctx.write("addon_items", ex, doc, body)
    return act, code


async def h_customers(ctx, v, warn):
    nik = normalize_nik(v.get("nik")) or None
    phone = normalize_phone_e164(v.get("phone")) if v.get("phone") else None
    if nik:
        q, label = {"nik": nik}, f"NIK {nik}"
    elif phone:
        q, label = {"phone": phone}, phone
    else:
        q, label = {"name": v["name"]}, v["name"]
        warn.append("Tanpa NIK/HP — duplikat hanya dicek dari nama.")
    ex = await ctx.lookup("customers", q)
    body = _pick(v, "name", "email", "npwp", "address", "occupation", "monthly_income",
                 "spouse_name", "spouse_nik", "heir_name", "heir_relation", "notes")
    body.update({"nik": nik, "phone": phone})
    doc = _base(ctx, kyc_files=[], kyc_status="pending", **body)
    act = await ctx.write("customers", ex, doc, body)
    return act, label


async def h_vendors(ctx, v, warn):
    code = v["code"].upper()
    ex = await ctx.lookup("vendors", {"code": code}, ("code", code))
    body = _pick(v, "name", "category", "npwp", "phone", "email", "address", "pic_name",
                 "payment_terms_days", "bank_name", "bank_account_no", "bank_account_holder",
                 "is_active", "note")
    act = await ctx.write("vendors", ex, _base(ctx, code=code, **body), body)
    return act, code


async def h_subcons(ctx, v, warn):
    code = v["code"].upper()
    ex = await ctx.lookup("subcontractors", {"code": code}, ("code", code))
    body = _pick(v, "name", "specialty", "phone", "email", "npwp", "address", "pic_name",
                 "rating", "is_active", "notes")
    act = await ctx.write("subcontractors", ex, _base(ctx, code=code, **body), body)
    return act, code


KIND_TO_AGENT_TYPE = {"agen_perorangan": "agen_properti", "kantor_broker": "broker_kantor",
                      "aggregator": "lainnya", "referral_pembeli": "referral_pembeli",
                      "influencer": "influencer", "korporat": "mitra_korporat"}


async def h_agents(ctx, v, warn):
    phone = normalize_phone_e164(v["phone"])
    ex = None
    if v.get("code"):
        ex = await ctx.lookup("agents", {"code": v["code"]})
        if not ex:
            raise RowError(f"Kode mitra '{v['code']}' tidak ditemukan — kosongkan kode untuk mitra baru.")
    else:
        ex = await ctx.lookup("agents", {"phone": phone})
    body = _pick(v, "name", "partner_kind", "entity_type", "company", "email", "nik", "npwp",
                 "address", "pic_name", "pic_phone", "bank_name", "bank_account",
                 "bank_account_name", "status")
    body["phone"] = phone
    body["agent_type"] = KIND_TO_AGENT_TYPE.get(v["partner_kind"], "lainnya")
    if ex:
        act = await ctx.write("agents", ex, None, body)
        return act, ex["code"]
    code = "(otomatis)" if ctx.dry_run else await seq.next_number("agent", ctx.org, prefix="AGN",
                                                                    width=4)
    doc = _base(ctx, code=code, **body,
                contract={"number": None, "start_date": None, "end_date": None,
                          "signed_by": None, "status": "draft", "file_ids": []},
                settings={}, portal={"enabled": False, "user_id": None, "last_login_at": None},
                stats={}, fee_total=0, fee_paid=0, deals_count=0)
    act = await ctx.write("agents", None, doc, {})
    return act, f"{v['name']} ({code})"


async def h_materials(ctx, v, warn):
    p = await _project(ctx, v["project_code"])
    code = v["code"].upper()
    ex = await ctx.lookup("materials", {"project_id": p["id"], "code": code})
    body = _pick(v, "name", "uom", "budget_qty")
    doc = _base(ctx, project_id=p["id"], project_name=p["name"], code=code, boq_item_id=None,
                consumed_qty=0.0, over_budget=False, **body)
    act = await ctx.write("materials", ex, doc, body)
    return act, f"{p['code']}/{code}"


async def h_workers(ctx, v, warn):
    ex = await ctx.lookup("workers", {"name": v["name"]})
    pids = []
    for code in v.get("project_codes") or []:
        try:
            pids.append((await _project(ctx, code))["id"])
        except RowError as e:
            warn.append(str(e))
    body = _pick(v, "role", "daily_wage", "phone", "is_active", "note")
    body.update({"role_label": LABOR_ROLE_LABEL.get(v["role"]), "project_ids": pids})
    doc = _base(ctx, name=v["name"], subcon_id=None, **body)
    act = await ctx.write("workers", ex, doc, body)
    return act, v["name"]


async def h_accounts(ctx, v, warn):
    code = v["code"]
    ex = await ctx.lookup("accounts", {"code": code}, ("code", code))
    if v.get("parent_code") and not await ctx.lookup("accounts", {"code": v["parent_code"]},
                                                     ("code", v["parent_code"])):
        warn.append(f"Akun induk '{v['parent_code']}' tidak ada.")
    body = _pick(v, "name", "type", "parent_code", "is_active")
    doc = {"id": new_id(), "org_id": ctx.org, "code": code, **body, "created_at": ctx.ts}
    act = await ctx.write("accounts", ex, doc, body)
    ctx.remember("accounts", ex or doc, ("code", code))
    return act, code


async def h_bank_accounts(ctx, v, warn):
    acct = await ctx.lookup("accounts", {"code": v["gl_account_code"]}, ("code", v["gl_account_code"]))
    if not acct:
        raise RowError(f"Akun GL '{v['gl_account_code']}' tidak ada di Bagan Akun.")
    ex = await ctx.lookup("bank_accounts", {"account_no": v["account_no"]})
    body = _pick(v, "name", "bank_name", "holder", "gl_account_code", "opening_balance",
                 "is_active", "note")
    body["gl_account_name"] = acct.get("name")
    doc = _base(ctx, account_no=v["account_no"], **body)
    act = await ctx.write("bank_accounts", ex, doc, body)
    return act, v["account_no"]


HANDLERS = {"users": h_users, "projects": h_projects, "clusters": h_clusters, "blocks": h_blocks,
            "unit_types": h_unit_types, "units": h_units, "addon_items": h_addons,
            "customers": h_customers, "vendors": h_vendors, "subcontractors": h_subcons,
            "agents": h_agents, "materials": h_materials, "workers": h_workers,
            "accounts": h_accounts, "bank_accounts": h_bank_accounts}


def _dup_key(ent: dict, v: dict) -> str:
    vals = [str(v.get(k) or "").strip().lower() for k in ent["key_fields"]]
    return "|".join(vals) if any(vals) else ""


async def run_import(sheets: dict, org: str, actor: str, mode: str, dry_run: bool) -> dict:
    ctx = Ctx(org, actor, mode, dry_run)
    entities, totals = [], {"rows": 0, "insert": 0, "update": 0, "skip": 0, "error": 0, "warning": 0}
    for ent in ENTITIES:
        rows = sheets.get(ent["key"]) or []
        if not rows:
            continue
        summ = {"key": ent["key"], "sheet": ent["sheet"], "total": len(rows), "insert": 0,
                "update": 0, "skip": 0, "error": 0, "warning": 0, "rows": []}
        for raw in rows:
            v, errors = coerce_row(ent, raw)
            warn, action, label = [], "error", ""
            if not errors:
                dk = _dup_key(ent, v)
                if dk and (ent["key"], dk) in ctx.seen:
                    errors.append("Duplikat kunci di dalam berkas (baris sebelumnya sudah memuatnya).")
                elif dk:
                    ctx.seen.add((ent["key"], dk))
            if not errors:
                try:
                    action, label = await HANDLERS[ent["key"]](ctx, v, warn)
                except RowError as e:
                    errors.append(str(e))
                except (ValueError, LookupError) as e:
                    errors.append(str(e))
                except Exception as e:  # noqa: BLE001 — satu baris rusak tidak boleh menghentikan pratinjau
                    logger.exception("import row failed")
                    errors.append(f"Galat tak terduga: {e}")
            if errors:
                action = "error"
            summ[action] += 1
            if warn:
                summ["warning"] += 1
            if len(summ["rows"]) < ROW_LIMIT or errors:
                summ["rows"].append({"row": raw.get("row"), "key": label, "action": action,
                                     "errors": errors, "warnings": warn})
        for k in ("insert", "update", "skip", "error", "warning"):
            totals[k] += summ[k]
        totals["rows"] += summ["total"]
        entities.append(summ)
    if not dry_run and ctx.touched_projects:
        for pid in ctx.touched_projects:
            await masterplan.recompute_stats(pid, org)
    return {"dry_run": dry_run, "mode": mode, "entities": entities, "totals": totals,
            "at": ctx.ts}


def enum_hint(group: str) -> str:
    return ", ".join(enum_options(group).keys())
