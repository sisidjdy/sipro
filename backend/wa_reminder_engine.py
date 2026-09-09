"""wa_reminder_engine — pengingat WhatsApp otomatis dari data yang SUDAH dimiliki sistem.

## Masalah yang ditutup modul ini (Fase 51B)

Sistem sudah menyimpan semua tanggal yang penting bagi pembeli: jatuh tempo tiap termin,
tunggakan yang lewat jatuh tempo, dan tanggal habis garansi per bagian rumah (sejak BAST
diterbitkan di Fase 50). Tetapi TIDAK ADA satu pun yang memberi tahu pembelinya. Pengingat
dikirim manual oleh staf — artinya: tidak konsisten, tidak ada jejak siapa sudah diingatkan,
dan kalau stafnya sibuk, tunggakan berkembang diam-diam sementara garansi habis tanpa pembeli
tahu haknya akan berakhir.

## Aturan keras modul ini

1. **Kandidat DIHITUNG, tidak diketik.** Tidak ada daftar penerima manual: kandidat lahir dari
   `ar_invoices.items[].due_date` dan `unit_handovers.warranties[].expires_at`.
2. **Ambang batas dari Pusat Konfigurasi**, bukan angka mati di kode (`reminder.*`).
3. **Satu periode satu pengingat.** `dedup_key` = (jenis, id sasaran, ember waktu) dijaga
   index unik. Menjalankan dua kali TIDAK mengirim dua kali — penting karena scheduler,
   tombol manual, dan percobaan ulang bisa terjadi bersamaan.
4. **Jujur soal status.** Tanpa kredensial WhatsApp, status ditulis `simulasi` (bukan
   `terkirim`). Penerima tanpa nomor ditulis `dilewati` beserta sebabnya — bukan dihitung
   sebagai keberhasilan, dan bukan disembunyikan.
5. **Isi pesan dari template yang disetujui** (`wa_templates`), sehingga kalimatnya bisa
   diubah tanpa menyentuh kode; template hilang = `dilewati` dengan sebab, bukan pesan
   karangan.
6. **Tidak mengingatkan hal yang sudah beres**: termin lunas, tagihan lunas, garansi habis,
   dan rumah yang belum diserahterimakan tidak menghasilkan kandidat.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

import reference as ref
import settings_store as st
from core_utils import new_id, now_iso
from db import db, ORG_ID
from notifications import send_whatsapp

logger = logging.getLogger("sipro.reminder")

COLL = "wa_reminders"
KINDS = ("warranty_expiring", "installment_due", "installment_overdue", "arrears_warning",
         "booking_fee_due")
# Template bawaan per jenis. Sengaja memakai template yang SUDAH disetujui sejak Fase 29b
# supaya pengingat tidak menunggu approval baru; bisa diganti dari Pusat Konfigurasi.
TEMPLATE_KEYS = {
    "warranty_expiring": "reminder.template_warranty",
    "installment_due": "reminder.template_installment",
    "installment_overdue": "reminder.template_overdue",
    "arrears_warning": "reminder.template_arrears",
    "booking_fee_due": "booking_fee.reminder_template",
}
SETTING_KEYS = ("reminder.enabled", "reminder.warranty_days",
                "reminder.installment_days_before", "reminder.overdue_every_days",
                "reminder.arrears_enabled", "reminder.arrears_min_amount",
                "reminder.arrears_min_months", "reminder.arrears_every_days",
                "booking_fee.reminder_days_before",
                *TEMPLATE_KEYS.values())


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _rp(n) -> str:
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def _d(value) -> date:
    return date.fromisoformat(str(value)[:10])


async def config(org: str = ORG_ID) -> dict:
    """Setelan pengingat + mode kirim yang JUJUR (simulasi bila kredensial belum ada)."""
    vals = await st.get_many(list(SETTING_KEYS), org_id=org)
    import wa_gateway as gw
    live = (await gw.get_config(org))["effective_mode"] == "live"
    return {
        "enabled": bool(vals.get("reminder.enabled", True)),
        "warranty_days": int(vals.get("reminder.warranty_days") or 30),
        "installment_days_before": int(vals.get("reminder.installment_days_before") or 3),
        "overdue_every_days": int(vals.get("reminder.overdue_every_days") or 7),
        "arrears_enabled": bool(vals.get("reminder.arrears_enabled", True)),
        "arrears_min_amount": int(vals.get("reminder.arrears_min_amount") or 0),
        "arrears_min_months": int(vals.get("reminder.arrears_min_months") or 1),
        "arrears_every_days": int(vals.get("reminder.arrears_every_days") or 7),
        "booking_fee_days_before": int(vals.get("booking_fee.reminder_days_before") or 0),
        "templates": {k: vals.get(key) for k, key in TEMPLATE_KEYS.items()},
        "mode": "nyata" if live else "simulasi",
        "mode_detail": ("Kredensial WhatsApp Cloud API terpasang & mode live — pesan benar-benar dikirim "
                        "sebagai TEMPLATE (di luar sesi 24 jam teks bebas ditolak Meta #131047)."
                        if live else
                        "Mode simulasi / kredensial WhatsApp belum diisi: pesan TIDAK dikirim, "
                        "hanya dicatat sebagai simulasi supaya isinya bisa diperiksa."),
        "setting_keys": list(SETTING_KEYS),
    }


async def _buyer_of_unit(org: str, unit: dict) -> dict:
    """Penerima untuk satu rumah: pelanggan dulu, lead sebagai cadangan.

    Mengembalikan `recipient_type` supaya id-nya disimpan di kolom yang BENAR. Sebelum ini
    id lead ditulis ke `customer_id`, jadi setiap laporan yang menyambung
    `wa_reminders.customer_id → customers` diam-diam tidak menemukan apa pun dan audit
    forensik melaporkannya sebagai FK yatim (CRITICAL). Rumah yang belum akad memang belum
    punya pelanggan — itu keadaan sah, jadi yang harus benar adalah NAMA KOLOMNYA.
    """
    cust = None
    if unit.get("customer_id"):
        cust = await db.customers.find_one({"id": unit["customer_id"], "org_id": org},
                                           {"_id": 0, "name": 1, "phone": 1, "id": 1})
        if cust:
            return {**cust, "recipient_type": "customer"}
    if unit.get("lead_id"):
        lead = await db.leads.find_one({"id": unit["lead_id"], "org_id": org},
                                       {"_id": 0, "name": 1, "phone": 1, "id": 1})
        if lead:
            return {**lead, "recipient_type": "lead"}
    return {}


async def _buyer_of_invoice(org: str, inv: dict) -> dict:
    if inv.get("unit_id"):
        unit = await db.units.find_one({"id": inv["unit_id"], "org_id": org},
                                       {"_id": 0, "customer_id": 1, "lead_id": 1})
        if unit:
            cust = await _buyer_of_unit(org, unit)
            if cust:
                return cust
    if inv.get("lead_id"):
        lead = await db.leads.find_one({"id": inv["lead_id"], "org_id": org},
                                       {"_id": 0, "name": 1, "phone": 1, "id": 1})
        if lead:
            return {**lead, "recipient_type": "lead"}
    return {}


def _recipient(buyer: dict) -> dict:
    """Kolom identitas penerima yang jujur: id lead TIDAK pernah masuk `customer_id`."""
    jenis = buyer.get("recipient_type")
    return {
        "customer_id": buyer.get("id") if jenis == "customer" else None,
        "lead_id": buyer.get("id") if jenis == "lead" else None,
        "recipient_type": jenis,
        "recipient_type_label": ref.label_of("reminder_recipient", jenis) if jenis else None,
        "name": buyer.get("name"),
        "phone": buyer.get("phone"),
    }



def _bucket_week(d: date) -> str:
    """Ember waktu mingguan untuk tunggakan: satu pengingat per rentang, bukan tiap hari."""
    return f"{d.isocalendar().year}W{d.isocalendar().week:02d}"


async def candidates(org: str = ORG_ID) -> list:
    """Semua pengingat yang LAYAK dikirim hari ini, beserta alasan yang bisa diperiksa."""
    cfg = await config(org)
    today = _today()
    out = []

    # ---------- 1. Garansi hampir habis ----------
    ambang = cfg["warranty_days"]
    hos = await db.unit_handovers.find(
        {"org_id": org, "state": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000)
    for ho in hos:
        unit = await db.units.find_one({"id": ho.get("unit_id"), "org_id": org},
                                       {"_id": 0, "code": 1, "customer_id": 1, "lead_id": 1,
                                        "id": 1}) or {}
        buyer = await _buyer_of_unit(org, unit)
        for w in (ho.get("warranties") or []):
            if not w.get("expires_at"):
                continue
            sisa = (_d(w["expires_at"]) - today).days
            if sisa < 0 or sisa > ambang:
                continue
            label = ref.label_of("warranty_category", w.get("category"))
            out.append({
                "kind": "warranty_expiring",
                "kind_label": ref.label_of("reminder_kind", "warranty_expiring"),
                "entity_type": "unit_handover", "entity_id": ho["id"],
                "unit_id": unit.get("id"), "unit_code": ho.get("unit_code") or unit.get("code"),
                **_recipient(buyer),
                "amount": None,
                "due_date": str(w["expires_at"])[:10],
                "days_left": sisa,
                "reason": (f"Garansi {label} rumah {ho.get('unit_code') or '-'} habis "
                           f"{str(w['expires_at'])[:10]} (sisa {sisa} hari, ambang "
                           f"{ambang} hari)."),
                "dedup_key": f"warranty_expiring:{ho['id']}:{w.get('category')}:"
                             f"{str(w['expires_at'])[:10]}",
                "vars": {"nama": buyer.get("name") or "Bapak/Ibu",
                         "bagian": label, "unit": ho.get("unit_code") or "-",
                         "tanggal": str(w["expires_at"])[:10], "sisa": str(sisa)},
            })

    # ---------- 2 & 3. Termin jatuh tempo & tunggakan ----------
    hn = cfg["installment_days_before"]
    invs = await db.ar_invoices.find(
        {"org_id": org, "status": {"$ne": "paid"}}, {"_id": 0}).to_list(2000)
    for inv in invs:
        buyer = await _buyer_of_invoice(org, inv)
        for item in (inv.get("items") or []):
            # Item termin menyimpan `paid_amount` (finance_engine.compute_scheme_items);
            # `paid` hanya ada di level invoice. Lihat memory/FIELD_MAP.md.
            sisa_bayar = int(item.get("amount") or 0) - int(item.get("paid_amount") or 0)
            if sisa_bayar <= 0 or item.get("status") == "paid" or not item.get("due_date"):
                continue
            selisih = (_d(item["due_date"]) - today).days
            base = {
                "entity_type": "ar_invoice", "entity_id": inv["id"],
                "unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
                **_recipient(buyer), "amount": sisa_bayar,
                "due_date": str(item["due_date"])[:10],
                "vars": {"nama": buyer.get("name") or "Bapak/Ibu",
                         "termin": item.get("label") or "termin",
                         "nominal": _rp(sisa_bayar),
                         "tanggal": str(item["due_date"])[:10],
                         "unit": inv.get("unit_code") or "-"},
            }
            if 0 <= selisih <= hn:
                out.append({**base, "kind": "installment_due",
                            "kind_label": ref.label_of("reminder_kind", "installment_due"),
                            "days_left": selisih,
                            "reason": (f"{item.get('label')} {_rp(sisa_bayar)} jatuh tempo "
                                       f"{str(item['due_date'])[:10]} (H-{selisih}, ambang "
                                       f"H-{hn})."),
                            "dedup_key": f"installment_due:{inv['id']}:"
                                         f"{item.get('item_id') or item.get('label')}:"
                                         f"{str(item['due_date'])[:10]}"})
            elif selisih < 0:
                out.append({**base, "kind": "installment_overdue",
                            "kind_label": ref.label_of("reminder_kind",
                                                       "installment_overdue"),
                            "days_left": selisih,
                            "reason": (f"{item.get('label')} {_rp(sisa_bayar)} TERLAMBAT "
                                       f"{abs(selisih)} hari (jatuh tempo "
                                       f"{str(item['due_date'])[:10]})."),
                            "dedup_key": f"installment_overdue:{inv['id']}:"
                                         f"{item.get('item_id') or item.get('label')}:"
                                         f"{_bucket_week(today)}"})

    # ---------- 4. Tunggakan lewat toleransi — pra-Surat Peringatan (Fase 68) ----------
    # Pembeli tidak boleh baru tahu ada masalah saat SP1 datang. Bulan tunggakan dihitung
    # mesin yang SAMA dengan SP & kandidat pembatalan (`late_fee_engine` + `arrears_engine`);
    # nominal minimum, bulan minimum, dan jeda ulang disetel dari Pusat Konfigurasi.
    if cfg["arrears_enabled"]:
        import arrears_engine as arr
        import late_fee_engine as lf
        bucket = today.toordinal() // max(1, cfg["arrears_every_days"])
        for inv in invs:
            if inv.get("status") not in ("unpaid", "partial") or not inv.get("deal_id"):
                continue
            hitung = await lf.assess(org, inv["deal_id"])
            a = arr.months_in_arrears(hitung.get("rows") or [])
            if a["months"] < cfg["arrears_min_months"] \
                    or a["overdue_amount"] < cfg["arrears_min_amount"]:
                continue
            buyer = await _buyer_of_invoice(org, inv)
            sudah_sp = await db.warning_letters.count_documents(
                {"org_id": org, "deal_id": inv["deal_id"]})
            tertua = min((str(t.get("due_date"))[:10] for t in a["terms"]
                          if t.get("due_date")), default=None)
            out.append({
                "kind": "arrears_warning",
                "kind_label": ref.label_of("reminder_kind", "arrears_warning"),
                "entity_type": "ar_invoice", "entity_id": inv["id"],
                "unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
                **_recipient(buyer), "amount": a["overdue_amount"],
                "due_date": tertua, "days_left": -a["max_days_late"],
                "reason": (f"Tunggakan {a['months']} bulan LEWAT TOLERANSI "
                           f"({_rp(a['overdue_amount'])}, terlama {a['max_days_late']} "
                           f"hari) pada unit {inv.get('unit_code') or '-'}"
                           + (f"; SP{sudah_sp} sudah pernah terbit — pengingat ini "
                              f"mendahului tingkat berikutnya."
                              if sudah_sp else
                              "; belum ada Surat Peringatan — pengingat ini datang "
                              "SEBELUM SP1.")),
                "dedup_key": f"arrears_warning:{inv['deal_id']}:{bucket}",
                "vars": {"nama": buyer.get("name") or "Bapak/Ibu",
                         "unit": inv.get("unit_code") or "-",
                         "nominal": _rp(a["overdue_amount"]),
                         "bulan": str(a["months"]),
                         "terlama": str(a["max_days_late"])},
            })

    # ---------- 5. Booking fee menjelang jatuh tempo (Fase 69B) ----------
    # Tagihan paling awal: belum ada pelanggan, penerimanya LEAD; sales pemilik deal ikut
    # diberi tahu (in-app + WA bila nomornya ada) supaya tidak ada unit yang lepas diam-diam.
    hb = cfg["booking_fee_days_before"]
    bfs = await db.booking_fee_invoices.find(
        {"org_id": org, "status": {"$in": ["unpaid", "partial"]}}, {"_id": 0}).to_list(2000)
    for inv in bfs:
        if not inv.get("due_date"):
            continue
        deal = await db.deals.find_one({"id": inv["deal_id"], "org_id": org},
                                       {"_id": 0, "status": 1}) or {}
        if deal.get("status") != "reserved":
            continue
        selisih = (_d(inv["due_date"]) - today).days
        if selisih < 0 or selisih > hb:
            continue
        lead = await db.leads.find_one({"id": inv.get("lead_id"), "org_id": org},
                                       {"_id": 0, "name": 1, "phone": 1, "id": 1}) or {}
        buyer = {**lead, "recipient_type": "lead"} if lead else {}
        sisa = int(inv.get("outstanding") or 0)
        out.append({
            "kind": "booking_fee_due",
            "kind_label": ref.label_of("reminder_kind", "booking_fee_due"),
            "entity_type": "booking_fee_invoice", "entity_id": inv["id"],
            "unit_id": inv.get("unit_id"), "unit_code": inv.get("unit_code"),
            **_recipient(buyer), "amount": sisa,
            "due_date": str(inv["due_date"])[:10], "days_left": selisih,
            "cc_sales_email": inv.get("assigned_to"),
            "reason": (f"Booking fee {inv['no']} unit {inv.get('unit_code') or '-'} "
                       f"{_rp(sisa)} jatuh tempo {str(inv['due_date'])[:10]} (H-{selisih}); "
                       "bila terlewat, reservasi dapat dilepas."),
            "dedup_key": f"booking_fee_due:{inv['id']}:{str(inv['due_date'])[:10]}",
            "vars": {"nama": lead.get("name") or "Bapak/Ibu", "termin": "booking fee",
                     "nominal": _rp(sisa), "tanggal": str(inv["due_date"])[:10],
                     "unit": inv.get("unit_code") or "-"},
        })

    # Sebab yang MENGHALANGI pengiriman ditulis apa adanya — kandidat tidak disembunyikan,
    # supaya "kenapa pembeli ini tidak pernah diingatkan" bisa dijawab dari layar.
    sudah = set()
    if out:
        rows = await db.wa_reminders.find(
            {"org_id": org, "dedup_key": {"$in": [c["dedup_key"] for c in out]}},
            {"_id": 0, "dedup_key": 1}).to_list(5000)
        sudah = {r["dedup_key"] for r in rows}
    from doc_share import wa_url
    for c in out:
        # Tautan `wa.me` untuk pengiriman MANUAL: sistem menyiapkan pesan, manusia menekan
        # kirim dari nomor perusahaan (pola Fase 62 — tanpa kredensial yang tidak dimiliki).
        c["wa_link"] = wa_url(c["phone"], c["reason"]) if c.get("phone") else None
        if not c.get("phone"):
            c["blocked_reason"] = ("Nomor WhatsApp penerima belum dicatat — pengingat tidak "
                                  "bisa dikirim.")
            c["blocked_code"] = "no_phone"
        elif c["dedup_key"] in sudah:
            c["blocked_reason"] = "Sudah diingatkan untuk periode ini."
            c["blocked_code"] = "already_sent"
        elif not cfg["enabled"]:
            c["blocked_reason"] = "Pengingat otomatis dimatikan di Pusat Konfigurasi."
            c["blocked_code"] = "disabled"
        else:
            c["blocked_reason"] = None
            c["blocked_code"] = None
    out.sort(key=lambda c: (c["kind"], str(c.get("due_date"))))
    return out


async def _template(org: str, kind: str, cfg: dict) -> dict:
    code = (cfg.get("templates") or {}).get(kind)
    if not code:
        return {}
    return await db.wa_templates.find_one(
        {"org_id": org, "code": code, "status": "approved"}, {"_id": 0}) or {}


def _render(template: dict, cand: dict) -> str:
    """Isi pesan PERSIS seperti yang diterima pembeli: template + parameter, tanpa tempelan.

    `cand['reason']` tetap tersimpan di kolom `reason` untuk staf; ia TIDAK pernah dikirim
    Meta, jadi tidak boleh masuk `body` (riwayat harus jujur — audit WA-03).
    """
    body = template.get("body") or ""
    for k, v in (cand.get("vars") or {}).items():
        body = body.replace("{{%s}}" % k, str(v))
    return body.strip()


async def _record(org: str, cand: dict, *, status: str, reason_code: str = None,
                  detail: str = None, body: str = None, template_code: str = None,
                  actor: str = "system") -> dict:
    doc = {
        "id": new_id(), "org_id": org, "kind": cand["kind"],
        "dedup_key": cand["dedup_key"], "entity_type": cand.get("entity_type"),
        "entity_id": cand.get("entity_id"), "unit_id": cand.get("unit_id"),
        "unit_code": cand.get("unit_code"), "customer_id": cand.get("customer_id"),
        "lead_id": cand.get("lead_id"),
        "recipient_type": cand.get("recipient_type"),
        "recipient_type_label": cand.get("recipient_type_label"),
        "name": cand.get("name"), "phone": cand.get("phone"),
        "amount": cand.get("amount"), "due_date": cand.get("due_date"),
        "days_left": cand.get("days_left"), "reason": cand.get("reason"),
        "status": status, "reason_code": reason_code, "detail": detail,
        "body": body, "template_code": template_code,
        "run_by": actor, "created_at": now_iso(),
    }
    try:
        await db.wa_reminders.insert_one(dict(doc))
    except DuplicateKeyError:
        # Dua pengirim berlomba untuk penanda yang sama: yang kedua BUKAN kiriman baru.
        return {"duplicate": True}
    doc.pop("_id", None)
    return doc


async def _notify_sales(org: str, cand: dict) -> None:
    """Tembusan ke sales pemilik deal: in-app selalu, WA bila nomornya tercatat."""
    from engine import create_notification
    email = cand.get("cc_sales_email")
    await create_notification(user_email=email, title="Booking fee pembeli akan jatuh tempo",
                              body=cand["reason"], type="finance",
                              related_entity_type="deal", related_entity_id=cand.get("entity_id"),
                              org_id=org)
    user = await db.users.find_one({"email": email, "org_id": org}, {"_id": 0, "phone": 1})
    if user and user.get("phone"):
        await send_whatsapp(user["phone"], f"[SIPRO] {cand['reason']} Pembeli: "
                                           f"{cand.get('name') or '-'}.")


async def run(org: str = ORG_ID, *, actor: str = "system", kinds=None,
              limit: int = 200) -> dict:
    """Kirim pengingat yang layak. Ringkasannya JUJUR: terkirim / simulasi / dilewati."""
    cfg = await config(org)
    rows = await candidates(org)
    if kinds:
        rows = [c for c in rows if c["kind"] in set(kinds)]
    hasil = {"sent": 0, "simulated": 0, "failed": 0, "skipped": 0,
             "per_kind": {}, "mode": cfg["mode"], "notes": []}
    if not cfg["enabled"]:
        hasil["notes"].append("Pengingat otomatis dimatikan di Pusat Konfigurasi "
                              "(reminder.enabled = tidak).")
    terkirim_kunci = set()
    for cand in rows[:limit]:
        per = hasil["per_kind"].setdefault(cand["kind"], {"sent": 0, "simulated": 0,
                                                          "failed": 0, "skipped": 0})
        if cand["dedup_key"] in terkirim_kunci:
            continue
        if cand.get("blocked_code"):
            # "Sudah diingatkan" tidak perlu baris baru — barisnya sudah ada dari run lalu.
            if cand["blocked_code"] != "already_sent":
                await _record(org, cand, status="dilewati",
                              reason_code=cand["blocked_code"],
                              detail=cand["blocked_reason"], actor=actor)
            hasil["skipped"] += 1
            per["skipped"] += 1
            terkirim_kunci.add(cand["dedup_key"])
            continue
        tmpl = await _template(org, cand["kind"], cfg)
        if not tmpl:
            await _record(org, cand, status="dilewati", reason_code="template_missing",
                          detail=(f"Template WhatsApp '{(cfg['templates'] or {}).get(cand['kind'])}' "
                                  "belum ada atau belum disetujui."), actor=actor)
            hasil["skipped"] += 1
            per["skipped"] += 1
            terkirim_kunci.add(cand["dedup_key"])
            continue
        body = _render(tmpl, cand)
        # Fase 95E — kirim sebagai TEMPLATE lewat gateway; parameter {{1}}..{{n}} mengikuti urutan variabel.
        import wa_gateway as gw
        res = await send_whatsapp(cand["phone"], body, kind="reminder", template=tmpl,
                                  template_params=gw.template_params(tmpl, cand.get("vars")))
        if res.get("status") == "sent":
            status, kode, detail = "terkirim", None, "Dikirim lewat WhatsApp Cloud API."
            hasil["sent"] += 1
            per["sent"] += 1
        elif res.get("status") == "failed":
            # 95C — GAGAL dicatat gagal (bukan "simulasi"), beserta kode & alasan Meta.
            status, kode = "gagal", str(res.get("error_code") or "failed")
            detail = f"{res.get('error_code')}: {res.get('error_detail')}"
            hasil["failed"] += 1
            per["failed"] += 1
        else:
            status, kode = "simulasi", None
            detail = cfg["mode_detail"]
            hasil["simulated"] += 1
            per["simulated"] += 1
        saved = await _record(org, cand, status=status, reason_code=kode, detail=detail,
                              body=body, template_code=tmpl.get("code"), actor=actor)
        if cand.get("cc_sales_email") and not saved.get("duplicate"):
            await _notify_sales(org, cand)
        if saved.get("duplicate"):
            # Kalah lomba: batalkan hitungan supaya ringkasan tidak melebih-lebihkan.
            if status == "terkirim":
                hasil["sent"] -= 1
                per["sent"] -= 1
            elif status == "gagal":
                hasil["failed"] -= 1
                per["failed"] -= 1
            else:
                hasil["simulated"] -= 1
                per["simulated"] -= 1
            hasil["skipped"] += 1
            per["skipped"] += 1
        terkirim_kunci.add(cand["dedup_key"])
    hasil["candidates"] = len(rows)
    hasil["detail"] = (f"{hasil['sent']} terkirim, {hasil['simulated']} simulasi, {hasil['failed']} gagal, "
                       f"{hasil['skipped']} dilewati dari {len(rows)} kandidat.")
    return hasil


async def history(org: str = ORG_ID, *, kind: str = None, status: str = None,
                  customer_id: str = None, limit: int = 100, skip: int = 0) -> dict:
    q = {"org_id": org}
    if kind:
        q["kind"] = kind
    if status:
        q["status"] = status
    if customer_id:
        q["customer_id"] = customer_id
    total = await db.wa_reminders.count_documents(q)
    rows = await db.wa_reminders.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)
    agg = {}
    for r in await db.wa_reminders.find({"org_id": org}, {"_id": 0, "status": 1}).to_list(5000):
        agg[r.get("status")] = agg.get(r.get("status"), 0) + 1
    return {"rows": rows, "total": total, "by_status": agg}


async def tick() -> dict:
    """Scheduler harian: jalankan pengingat untuk semua organisasi yang menyalakannya."""
    out = {}
    orgs = await db.orgs.distinct("id") or [ORG_ID]
    for org in orgs:
        try:
            cfg = await config(org)
            if not cfg["enabled"]:
                continue
            res = await run(org, actor="scheduler")
            if res["sent"] or res["simulated"]:
                out[org] = res["detail"]
        except Exception:  # noqa: BLE001 — satu organisasi gagal jangan mematikan sisanya
            logger.exception("Pengingat WA gagal untuk org %s", org)
    return out


def next_run_hint() -> str:
    besok = _today() + timedelta(days=1)
    return f"Pemeriksaan otomatis berikutnya: {besok.isoformat()} 08:00 WIB."
