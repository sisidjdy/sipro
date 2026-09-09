"""Leads (CRM) + Appointments — Slice A. RBAC + row-scope enforced."""
from fastapi import APIRouter, Depends, HTTPException

import listing as lst
import reference as ref
import stage_clock as clock
from core_utils import normalize_phone_e164
from denorm import cascade_master_change
from db import db, ORG_ID
from core_utils import new_id, now_iso, serialize_doc, parse_pagination, due_in, now
from rbac import require_permission, scope_query, is_scoped_sales, can, FULL_ACCESS_ROLES
import lead_lifecycle as lc
from engine import (emit, dispatch_pending, add_activity, auto_assign_lead,
                    compute_lead_score, auto_create_task)
from models import (LeadCreate, LeadUpdate, LeadStageUpdate, LeadAssign, LeadImport,
                    AppointmentCreate, AppointmentStatus, AppointmentUpdate)

router = APIRouter(tags=["sales"])

STAGES = list(ref.values("lead_stage"))  # SSOT: reference.GROUPS["lead_stage"]
STAGE_FLOW = {
    "acquisition": ["nurturing", "appointment", "lost", "recycle"],
    "nurturing": ["appointment", "booking", "lost", "recycle"],
    "appointment": ["booking", "nurturing", "lost", "recycle"],
    "booking": ["won", "lost"],
    "won": [],
    "recycle": ["nurturing", "lost"],
    "lost": ["recycle"],
}


async def _get_lead_scoped(lead_id: str, user: dict) -> dict:
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")
    if is_scoped_sales(user) and lead.get("assigned_to") != user.get("email"):
        raise HTTPException(status_code=403, detail="Akses ditolak: bukan lead Anda")
    return lead


# ----------------------------- Leads -----------------------------
# Fase 40: kolom yang BOLEH diurutkan server-side (whitelist — lihat listing.sort_spec).
LEAD_SORTS = {"name": "name", "phone": "phone", "stage": "stage", "source": "source",
              "score": "score", "assigned_to": "assigned_to", "created_at": "created_at",
              "updated_at": "updated_at", **clock.SORTS}


@router.get("/leads")
async def list_leads(stage: str = None, source: str = None, q: str = None,
                     assigned_to: str = None, score_band: str = None,
                     created_from: str = None, created_to: str = None,
                     sla: str = None, partner_id: str = None,
                     sort: str = None, direction: str = None,
                     skip: int = 0, limit: int = 50,
                     user: dict = Depends(require_permission("leads", "view"))):
    """Daftar lead: cari + filter MULTI (koma) + sort server-side + umur (aging).

    Fase 40: `stage`/`source`/`score_band`/`assigned_to` menerima beberapa nilai dipisah
    koma; sort dieksekusi di database (bukan di browser pada halaman aktif saja).
    Fase 41: `?sla=over|over2|ok|none` dijalankan DI DATABASE atas field `stage_due_at`
    (dulu "lewat SLA" hanya bisa dilihat mata di layar, tidak bisa difilter).
    Fase 42: `?partner_id=` untuk melihat lead yang dikirim mitra tertentu.
    """
    skip, limit = parse_pagination(skip, limit)
    base = {}
    lst.apply_in(base, "stage", stage, STAGES)
    lst.apply_in(base, "source", source)
    lst.apply_in(base, "score_band", score_band)
    lst.apply_in(base, "assigned_to", assigned_to)
    lst.apply_in(base, "partner_id", partner_id)
    clock.apply_sla_filter(base, "lead", sla)
    lst.apply_range(base, "created_at", created_from, created_to)
    lst.apply_search(base, q, ("name", "phone", "email", "campaign"))
    query = scope_query(user, base)
    total = await db.leads.count_documents(query)
    rows = await (db.leads.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, LEAD_SORTS, ("created_at", -1)))
                  .skip(skip).limit(limit).to_list(limit))
    # Fase 41: umur + ambang SLA berasal dari field tersimpan `stage_entered_at` /
    # `stage_sla_hours` (kebijakan Pusat Konfigurasi), bukan pemindaian riwayat per request.
    await clock.attach(rows, "lead", org_id=user.get("org_id", ORG_ID))
    # pipeline counts (respect scope)
    pipeline_q = scope_query(user, {})
    counts = {}
    for st in STAGES:
        counts[st] = await db.leads.count_documents({**pipeline_q, "stage": st})
    return {"data": serialize_doc(rows), "total": total, "counts": counts}


@router.get("/leads/owners")
async def lead_owners(user: dict = Depends(require_permission("leads", "view"))):
    """Daftar PIC (sales) yang benar-benar memegang lead dalam cakupan pemakai + jumlahnya.

    Fase 40: filter \"PIC\" pada daftar lead butuh pilihan orang, tetapi `/admin/users` hanya
    boleh dibuka owner/super_admin. Endpoint ini memberi tepat yang dibutuhkan (nama +
    email + jumlah lead) tanpa membocorkan data pengguna lain, dan otomatis mengikuti
    cakupan baris: sales hanya melihat dirinya sendiri.
    CATATAN URUTAN RUTE: harus terdaftar SEBELUM `/leads/{lead_id}` agar tidak tertelan
    path param (pelajaran verify_api_contract).
    """
    org = user.get("org_id", ORG_ID)
    query = scope_query(user, {})
    emails = [e for e in await db.leads.distinct("assigned_to", query) if e]
    people = await db.users.find({"org_id": org, "email": {"$in": emails}},
                                 {"_id": 0, "email": 1, "name": 1}).to_list(200)
    names = {p["email"]: p.get("name") or p["email"] for p in people}
    out = []
    for email in sorted(emails):
        out.append({"value": email, "label": names.get(email, email),
                    "hint": await db.leads.count_documents({**query, "assigned_to": email})})
    return {"data": out, "total": len(out)}


async def _resolve_partner(payload, phone: str, org: str, lead_id: str = None) -> tuple:
    """(partner_id, sengketa) — Fase 42: siapa mitra yang berhak atas lead ini.

    Aturan yang ditegakkan di sini:
      * `source="partner"` WAJIB menyebut mitranya (kalau tidak, tagihan fee kelak tidak
        punya dasar dan analitik mitra menghitung angka milik entah siapa),
      * mitra harus ADA dan berstatus aktif (mitra ditangguhkan tidak boleh menyetor lead),
      * nomor yang sama dari mitra berbeda dalam jendela dedup diputuskan model atribusi
        Pusat Konfigurasi (`partner.attribution_model`), sengketanya dicatat.
    """
    import partner_engine as pengine
    partner_id = getattr(payload, "partner_id", None)
    source = getattr(payload, "source", None)
    if source == "partner" and not partner_id:
        raise HTTPException(status_code=400,
                            detail="Lead bersumber mitra wajib memilih mitranya "
                                   "(tanpa itu hak fee tidak bisa dipertanggungjawabkan).")
    if not partner_id:
        return None, None
    partner = await db.agents.find_one({"id": partner_id, "org_id": org}, {"_id": 0})
    if not partner:
        raise HTTPException(status_code=404, detail="Mitra tidak ditemukan.")
    if partner.get("status") != "active":
        raise HTTPException(status_code=400,
                            detail=f"Mitra {partner['name']} berstatus {partner['status']} — "
                                   "tidak boleh menyetor lead baru.")
    toggles = await pengine.toggles(org)
    if toggles.get("partner.require_contract_active"):
        ok, why = pengine.contract_active(partner)
        if not ok:
            raise HTTPException(status_code=400, detail=f"{why} Perbarui kontrak mitra dulu.")
    result = await pengine.attribute(partner_id=partner_id, phone=phone, org_id=org,
                                    lead_id=lead_id)
    return result["partner_id"], result.get("conflict")


@router.post("/leads")
async def create_lead(payload: LeadCreate,
                      user: dict = Depends(require_permission("leads", "create"))):
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    phone = normalize_phone_e164(payload.phone)
    dup = await db.leads.find_one({"org_id": org, "phone": phone},
                                  {"_id": 0, "id": 1, "name": 1, "assigned_to": 1, "stage": 1})
    if dup:
        raise HTTPException(status_code=409, detail=(
            f"Nomor {phone} sudah terdaftar sebagai lead '{dup.get('name')}' "
            f"(tahap {dup.get('stage')}, pemilik {dup.get('assigned_to')}). "
            "Gunakan lead yang ada agar tidak duplikat."))
    assignee = payload.assigned_to
    if is_scoped_sales(user):
        assignee = user.get("email")  # sales create own leads
    if not assignee:
        assignee = await auto_assign_lead(org) or user.get("email")
    # Fase 42 — ATRIBUSI MITRA. Lead bersumber mitra tanpa `partner_id` membuat hak fee
    # tidak bisa dipertanggungjawabkan; dan bila nomor yang sama sudah pernah dikirim mitra
    # lain dalam jendela dedup, pemiliknya ditentukan model atribusi (bukan siapa yang
    # menekan Simpan lebih dulu) + sengketanya dicatat untuk ditinjau.
    partner_id, conflict = await _resolve_partner(payload, phone, org)
    lead = {
        "id": new_id(), "org_id": org, "name": payload.name, "phone": phone,
        "email": payload.email, "source": payload.source, "campaign": payload.campaign,
        "stage": "acquisition", "assigned_to": assignee,
        "interest_unit_type": payload.interest_unit_type, "notes": payload.notes,
        "first_contact_at": None, "response_time_minutes": None,
        "partner_id": partner_id,
        "partner_attributed_at": now_iso() if partner_id else None,
        "created_at": ts, "updated_at": ts, "created_by": user.get("email"),
    }
    lead.update(compute_lead_score(lead))
    lead.update(await clock.patch_for("lead", "acquisition", org_id=org, at=ts))
    await db.leads.insert_one(lead)
    if conflict:
        await db.partner_attribution_conflicts.update_one(
            {"id": conflict["id"]}, {"$set": {"lead_id": lead["id"]}})
    await emit("lead.created", "lead", lead["id"], {"source": payload.source}, org_id=org)
    await dispatch_pending()
    lead.pop("_id", None)
    if partner_id:
        import partner_engine as pengine
        await pengine.refresh_stats(partner_id, org_id=org)
    return {"data": serialize_doc(lead), "attribution_conflict": serialize_doc(conflict)}


@router.post("/leads/import")
async def import_leads(payload: LeadImport,
                       user: dict = Depends(require_permission("leads", "create"))):
    org = user.get("org_id", ORG_ID)
    created = 0
    for item in payload.leads:
        ts = now_iso()
        assignee = item.assigned_to or (user.get("email") if is_scoped_sales(user)
                                        else await auto_assign_lead(org)) or user.get("email")
        lead = {
            "id": new_id(), "org_id": org, "name": item.name, "phone": item.phone,
            "email": item.email, "source": item.source or "import", "campaign": item.campaign,
            "stage": "acquisition", "assigned_to": assignee,
            "interest_unit_type": item.interest_unit_type, "notes": item.notes,
            "first_contact_at": None, "response_time_minutes": None,
            "created_at": ts, "updated_at": ts, "created_by": user.get("email"),
        }
        lead.update(compute_lead_score(lead))
        await db.leads.insert_one(lead)
        await emit("lead.created", "lead", lead["id"], {"source": lead["source"]}, org_id=org)
        created += 1
    await dispatch_pending()
    return {"data": {"created": created}}


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user: dict = Depends(require_permission("leads", "view"))):
    lead = await _get_lead_scoped(lead_id, user)
    await clock.attach([lead], "lead", org_id=user.get("org_id", ORG_ID))
    return {"data": serialize_doc(lead)}


def _force_or_403(user, force: bool, reason: str):
    """Hapus paksa (beserta transaksi): hanya akses penuh (owner/super_admin) + alasan ≥10 huruf."""
    if not force:
        return
    import force_delete as fd
    if not fd.may_force(user):
        raise HTTPException(status_code=403, detail="Hapus paksa beserta transaksi hanya untuk Direksi/Super Admin.")
    if len((reason or "").strip()) < 10:
        raise HTTPException(status_code=400, detail="Hapus paksa wajib alasan (minimal 10 huruf).")


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, force: bool = False, reason: str = None,
                      user: dict = Depends(require_permission("leads", "delete"))):
    """Hapus lead salah input/duplikat. Ditolak bila sudah punya deal aktif, customer, atau unit terikat —
    kecuali `force=true` (akses penuh + alasan): deal & seluruh transaksinya ikut dihapus."""
    import master_delete as md
    from rbac import audit_log
    lead = await _get_lead_scoped(lead_id, user)
    org = user.get("org_id", ORG_ID)
    _force_or_403(user, force, reason)
    if force:
        import force_delete as fd
        await fd.delete_deals_of(org, {"lead_id": lead_id}, user.get("email"))
        await db.customers.update_many({"org_id": org, "lead_id": lead_id}, {"$unset": {"lead_id": ""}})
        await db.units.update_many({"org_id": org, "lead_id": lead_id}, {"$unset": {"lead_id": "", "lead_name": ""}})
        await audit_log(user, "force_delete", "leads", lead_id, {"reason": reason})
    try:
        out = await md.delete_lead(org, lead)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_log(user, "delete", "leads", lead_id, {"name": lead.get("name"), "removed": out["removed"]})
    return {"data": out}


@router.get("/leads/{lead_id}/delete-check")
async def lead_delete_check(lead_id: str, user: dict = Depends(require_permission("leads", "view"))):
    import master_delete as md
    lead = await _get_lead_scoped(lead_id, user)
    blockers = await md.blockers_of(user.get("org_id", ORG_ID), "lead", lead)
    import force_delete as fd
    return {"data": {"can_delete": not blockers, "blockers": blockers, "can_force": fd.may_force(user)}}


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate,
                      user: dict = Depends(require_permission("leads", "update"))):
    lead = await _get_lead_scoped(lead_id, user)
    org = user.get("org_id", ORG_ID)
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates.get("phone"):
        # Normalisasi E.164 + cegah tabrakan dengan lead lain (dulu tidak diperiksa,
        # sehingga nomor sama bisa masuk dua kali dengan format berbeda).
        updates["phone"] = normalize_phone_e164(updates["phone"])
        dup = await db.leads.find_one({"org_id": org, "phone": updates["phone"],
                                       "id": {"$ne": lead_id}}, {"_id": 0, "name": 1})
        if dup:
            raise HTTPException(status_code=409, detail=(
                f"Nomor {updates['phone']} sudah dipakai lead '{dup.get('name')}'."))
    updates["updated_at"] = now_iso()
    if "partner_id" in updates or updates.get("source") == "partner":
        merged_payload = type("P", (), {
            "partner_id": updates.get("partner_id", lead.get("partner_id")),
            "source": updates.get("source", lead.get("source"))})()
        partner_id, conflict = await _resolve_partner(
            merged_payload, updates.get("phone") or lead.get("phone"), org, lead_id=lead_id)
        updates["partner_id"] = partner_id
        updates["partner_attributed_at"] = now_iso() if partner_id else None
    merged = {**lead, **updates}
    import lead_scoring
    updates.update(await lead_scoring.rescore(org, merged))
    await db.leads.update_one({"id": lead_id}, {"$set": updates})
    if updates.get("partner_id"):
        import partner_engine as pengine
        await pengine.refresh_stats(updates["partner_id"], org_id=org)
    fresh = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    # SSOT: nama lead yang dikopi ke tagihan/agenda/survey ikut disamakan.
    synced = await cascade_master_change("leads", lead_id, fresh)
    return {"data": serialize_doc(fresh), "denorm_synced": synced}


@router.post("/leads/{lead_id}/first-contact")
async def first_contact(lead_id: str, user: dict = Depends(require_permission("leads", "update"))):
    """Catat kontak pertama (telepon/kunjungan). Untuk WA gunakan `POST /leads/{id}/wa`."""
    lead = await _get_lead_scoped(lead_id, user)
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    # Fase 29b: SATU pintu (lead_lifecycle) supaya kontak pertama, waktu respons,
    # penutupan tugas, riwayat tahap, dan kenaikan stage selalu konsisten.
    fresh = await lc.mark_first_contact(lead, actor=user.get("email"), channel="manual",
                                        note="Kontak pertama dicatat manual")
    # follow-up task
    await auto_create_task(
        source_event=f"lead.followup:{lead_id}:{ts}", jobdesk_code="SM-10",
        title=f"Follow-up lead: {lead.get('name')}", type="follow_up",
        related_entity_type="lead", related_entity_id=lead_id,
        assigned_to=lead.get("assigned_to"), due_date=due_in(days=1), priority="high", org_id=org)
    await add_activity(entity_type="lead", entity_id=lead_id, type="system",
                       body=f"Kontak pertama dilakukan oleh {user.get('name')}.",
                       actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(fresh)}


@router.post("/leads/{lead_id}/stage")
async def change_stage(lead_id: str, payload: LeadStageUpdate,
                       user: dict = Depends(require_permission("leads", "update"))):
    """Pindah tahap lead — Fase 29b: GERBANG BUKTI, bukan dropdown bebas.

    Dulu endpoint ini hanya memeriksa ketetanggaan graf sehingga `nurturing → booking`
    lolos tanpa deal dan `booking → won` lolos tanpa akad. Sekarang setiap tahap punya
    syarat yang diperiksa pada DATA; `won` hanya lahir dari event legal deal; `lost` dan
    `recycle` wajib beralasan; semua perpindahan tercatat di `stage_history`.
    """
    lead = await _get_lead_scoped(lead_id, user)
    cur = lead.get("stage")
    target = payload.stage
    if target not in STAGES:
        raise HTTPException(status_code=400, detail="Stage tidak valid")
    if target == cur:
        raise HTTPException(status_code=400, detail="Lead sudah berada pada tahap tersebut.")
    if target == "won":
        raise HTTPException(status_code=400, detail=(
            "Tahap 'Menang' tidak bisa dipilih manual. Tahap ini otomatis saat deal "
            "menyelesaikan akad/AJB (atau lunas) di halaman Deal & Unit."))
    if target not in lc.MANUAL_FLOW.get(cur, []):
        raise HTTPException(status_code=400, detail=(
            f"Transisi {cur} → {target} tidak diizinkan. Lanjutkan lewat aksi yang sesuai "
            "(kontak pertama, jadwalkan survey, buat reservasi)."))
    reason = (payload.note or "").strip() or None
    if target in lc.REASON_REQUIRED and not reason:
        raise HTTPException(status_code=400, detail=(
            "Alasan wajib diisi saat menandai lead 'Hilang' atau 'Daur Ulang' "
            "(dipakai untuk analisis kebocoran pipeline)."))
    ok, blocked, evidence = await lc.gate(lead, target)
    if not ok:
        raise HTTPException(status_code=400, detail=blocked)
    fresh = await lc.record(lead, target, actor=user.get("email"), reason=reason,
                            evidence=evidence, source="manual")
    await dispatch_pending()
    return {"data": serialize_doc(fresh)}


@router.post("/leads/{lead_id}/assign")
async def assign_lead(lead_id: str, payload: LeadAssign,
                      user: dict = Depends(require_permission("leads", "assign"))):
    org = user.get("org_id", ORG_ID)
    lead = await db.leads.find_one({"id": lead_id, "org_id": org}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan")
    target = await db.users.find_one({"email": payload.assigned_to, "org_id": org})
    if not target:
        raise HTTPException(status_code=400, detail="Pengguna tujuan tidak ditemukan")
    ts = now_iso()
    await db.leads.update_one({"id": lead_id}, {"$set": {"assigned_to": payload.assigned_to, "updated_at": ts}})
    await add_activity(entity_type="lead", entity_id=lead_id, type="system",
                       body=f"Lead di-assign ke {target.get('name')}.", actor=user.get("email"), org_id=org)
    fresh = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}


# ----------------------------- Appointments -----------------------------
# Fase 63: kolom yang BOLEH diurutkan server-side (bukan sort di browser atas halaman
# aktif saja, yang selalu berbohong pada data terpaginasi).
APPT_SORTS = {"scheduled_at": "scheduled_at", "title": "title", "type": "type",
              "status": "status", "kind": "kind", "lead_name": "lead_name",
              "assigned_to": "assigned_to", "created_at": "created_at"}
APPT_TYPES = list(ref.values("appointment_type"))
APPT_KINDS = list(ref.values("agenda_kind"))


def _appt_scope(user: dict, base: dict) -> dict:
    """Cakupan baris agenda: sales melihat agendanya sendiri DAN agenda tempat ia diundang.

    Tanpa cabang `participants`, staf yang diundang ke rapat tidak akan pernah melihat
    rapat itu di kalendernya — undangan yang tidak kelihatan sama saja dengan tidak
    diundang.
    """
    q = scope_query(user, base)
    if is_scoped_sales(user):
        own = q.pop("assigned_to", None)
        if own:
            invited = {"participants": own}
            q["$and"] = [*q.get("$and", []), {"$or": [{"assigned_to": own}, invited]}]
    return q


@router.get("/appointments")
async def list_appointments(lead_id: str = None, status: str = None, type: str = None,
                            kind: str = None, assigned_to: str = None, q: str = None,
                            date_from: str = None, date_to: str = None,
                            sort: str = None, direction: str = None,
                            skip: int = 0, limit: int = 200,
                            user: dict = Depends(require_permission("appointments", "view"))):
    """Daftar agenda: cari + filter MULTI (koma) + sort server-side + rentang tanggal.

    Fase 63: halaman Agenda & Survey dulu hanya bisa menampilkan agenda SATU HARI yang
    dipilih di kalender, tanpa cari/filter/urut — sehingga "rapat minggu depan" hanya bisa
    ditemukan dengan menebak tanggalnya satu per satu.
    """
    skip, limit = parse_pagination(skip, limit)
    base = {}
    if lead_id:
        base["lead_id"] = lead_id
    lst.apply_in(base, "status", status, ref.values("appointment_status"))
    lst.apply_in(base, "type", type, APPT_TYPES)
    lst.apply_in(base, "kind", kind, APPT_KINDS)
    lst.apply_in(base, "assigned_to", assigned_to)
    # Filter rentang tanggal untuk kalender/agenda (scheduled_at disimpan ISO-8601).
    lst.apply_range(base, "scheduled_at", date_from, date_to)
    lst.apply_search(base, q, ("title", "lead_name", "location", "notes", "assigned_to"))
    query = _appt_scope(user, base)
    total = await db.appointments.count_documents(query)
    rows = await (db.appointments.find(query, {"_id": 0})
                  .sort(lst.sort_spec(sort, direction, APPT_SORTS, ("scheduled_at", 1)))
                  .skip(skip).limit(limit).to_list(limit))
    return {"data": serialize_doc(rows), "total": total}


@router.get("/appointments/staff")
async def appointment_staff(user: dict = Depends(require_permission("appointments", "view"))):
    """Staf yang bisa diundang sebagai peserta agenda (nama + email + peran).

    Sengaja TIDAK memakai `/admin/users` (hanya owner/super_admin) dan tidak membocorkan
    apa pun selain yang dibutuhkan pemilih peserta.
    CATATAN URUTAN RUTE: harus di ATAS `/appointments/{appt_id}`.
    """
    org = user.get("org_id", ORG_ID)
    people = await db.users.find({"org_id": org, "is_active": {"$ne": False}},
                                 {"_id": 0, "email": 1, "name": 1, "role": 1}
                                 ).sort("name", 1).to_list(200)
    return {"data": [{"value": p["email"], "label": p.get("name") or p["email"],
                      "hint": p.get("role")} for p in people], "total": len(people)}


async def _clean_participants(org: str, emails) -> list:
    """Peserta harus pengguna yang BENAR-BENAR ada; email asing ditolak, bukan disimpan."""
    wanted = sorted({e.strip().lower() for e in (emails or []) if e and e.strip()})
    if not wanted:
        return []
    found = await db.users.distinct("email", {"org_id": org, "email": {"$in": wanted}})
    unknown = [e for e in wanted if e not in {str(f).lower() for f in found}]
    if unknown:
        raise HTTPException(status_code=400, detail=(
            f"Peserta tidak dikenal: {', '.join(unknown)}. Pilih dari daftar staf."))
    return [str(f) for f in found]


@router.post("/appointments")
async def create_appointment(payload: AppointmentCreate,
                             user: dict = Depends(require_permission("appointments", "create"))):
    """Buat agenda — terkait lead (survei/presentasi) ATAU internal (rapat, kunjungan).

    Aturan yang ditegakkan:
      * agenda yang MENYEBUT LEAD hanya boleh dibuat pemakai yang berhak melihat lead
        (`leads:view`), sehingga menjadwalkan survei pembeli tetap milik sales/marketing;
      * agenda internal TIDAK menyentuh tahap lead dan tidak menerbitkan tugas survei —
        rapat mingguan bukan bukti kemajuan pipeline;
      * peserta wajib pengguna yang ada.
    """
    org = user.get("org_id", ORG_ID)
    ts = now_iso()
    internal = not payload.lead_id
    lead = None
    if not internal:
        if not await can(user.get("role"), "leads", "view"):
            raise HTTPException(status_code=403, detail=(
                "Agenda yang menyebut lead hanya boleh dibuat pemakai yang berhak melihat "
                "lead. Untuk rapat internal, kosongkan pilihan lead."))
        lead = await _get_lead_scoped(payload.lead_id, user)
    appt = {
        "id": new_id(), "org_id": org, "lead_id": payload.lead_id, "title": payload.title,
        "lead_name": (lead or {}).get("name"),
        "kind": "internal" if internal else "sales",
        "scheduled_at": payload.scheduled_at, "type": payload.type,
        "location": payload.location, "project_id": payload.project_id,
        "participants": await _clean_participants(org, payload.participants),
        "notes": payload.notes, "status": "scheduled",
        "assigned_to": (lead or {}).get("assigned_to") or user.get("email"),
        "created_by": user.get("email"), "created_at": ts, "updated_at": ts,
    }
    await db.appointments.insert_one(appt)
    appt.pop("_id", None)
    if internal:
        return {"data": serialize_doc(appt)}
    # Tahap naik sebagai AKIBAT aksi (jadwal survey dibuat) + tercatat di riwayat.
    if lead.get("stage") in ("acquisition", "nurturing"):
        await lc.record(lead, "appointment", actor=user.get("email"), source="appointment",
                        evidence={"appointment_id": appt["id"]})
    await auto_create_task(
        source_event=f"appointment:{appt['id']}",
        title=f"Survey/janji temu: {lead.get('name')}", type="survey",
        related_entity_type="lead", related_entity_id=payload.lead_id,
        assigned_to=lead.get("assigned_to"), due_date=payload.scheduled_at,
        sla_due_at=payload.scheduled_at, priority="high", org_id=org)
    await add_activity(entity_type="lead", entity_id=payload.lead_id, type="system",
                       body=f"Appointment dijadwalkan: {payload.title}", actor=user.get("email"), org_id=org)
    return {"data": serialize_doc(appt)}


async def _get_appt_scoped(appt_id: str, user: dict) -> dict:
    appt = await db.appointments.find_one(
        {"id": appt_id, "org_id": user.get("org_id", ORG_ID)}, {"_id": 0})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment tidak ditemukan")
    if is_scoped_sales(user) and appt.get("assigned_to") != user.get("email") \
            and user.get("email") not in (appt.get("participants") or []):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    return appt


@router.put("/appointments/{appt_id}")
async def update_appointment(appt_id: str, payload: AppointmentUpdate,
                             user: dict = Depends(require_permission("appointments", "update"))):
    """Ubah/geser agenda. Agenda yang sudah SELESAI tidak bisa diubah lagi.

    Jadwal yang sudah dilaksanakan adalah catatan sejarah: mengubahnya sesudahnya membuat
    berita acara survei & laporan aktivitas bercerita hal yang tidak pernah terjadi.
    """
    appt = await _get_appt_scoped(appt_id, user)
    if appt.get("status") in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail=(
            "Agenda yang sudah selesai/dibatalkan tidak bisa diubah — buat agenda baru "
            "bila jadwalnya diulang."))
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan yang dikirim.")
    if "participants" in updates:
        updates["participants"] = await _clean_participants(
            user.get("org_id", ORG_ID), updates["participants"])
    updates["updated_at"] = now_iso()
    await db.appointments.update_one({"id": appt_id}, {"$set": updates})
    fresh = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if fresh.get("lead_id"):
        await add_activity(entity_type="lead", entity_id=fresh["lead_id"], type="system",
                           body=f"Agenda diperbarui: {fresh.get('title')} "
                                f"({fresh.get('scheduled_at')})",
                           actor=user.get("email"), org_id=user.get("org_id", ORG_ID))
    return {"data": serialize_doc(fresh)}


@router.post("/appointments/{appt_id}/status")
async def appointment_status(appt_id: str, payload: AppointmentStatus,
                             user: dict = Depends(require_permission("appointments", "update"))):
    appt = await _get_appt_scoped(appt_id, user)
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": payload.status, "updated_at": now_iso()}})
    fresh = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    return {"data": serialize_doc(fresh)}
