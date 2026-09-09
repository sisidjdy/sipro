"""wa_template_governance — aturan tata kelola template WA (audit WA-05..WA-09, WA-14).

Satu kebenaran: template diatur dari Pusat Konfigurasi › Integrasi WhatsApp › Template.
Modul ini menjawab tiga pertanyaan yang dulu tidak pernah ditanya sebelum menyimpan/menghapus:
- Di mana template ini DIPAKAI? (playbook, otomasi, pemetaan pengingat)  → tidak boleh dihapus
- Apakah kategorinya masuk akal dengan isinya?                          → peringatan, bukan blokir
- Template mana untuk pengingat apa?                                    → pemetaan di satu tempat
"""
import re

import settings_store as cfg
from db import db
from wa_reminder_engine import TEMPLATE_KEYS

REMINDER_KIND_META = {
    "installment_due": ("Termin akan jatuh tempo", "Dikirim H-n sebelum termin jatuh tempo (reminder.installment_days_before)."),
    "installment_overdue": ("Termin terlambat", "Dikirim berkala selagi termin lewat jatuh tempo (reminder.overdue_every_days)."),
    "arrears_warning": ("Tunggakan lewat toleransi", "Dikirim bila tunggakan melewati batas bulan/nominal perjanjian."),
    "warranty_expiring": ("Masa garansi akan habis", "Dikirim H-n sebelum garansi berakhir (reminder.warranty_days)."),
    "booking_fee_due": ("Booking fee jatuh tempo", "Dikirim H-n sebelum tenggat booking fee (booking_fee.reminder_days_before)."),
}

# Penanda promosi: template `utility` yang memuat kata ini kemungkinan salah kategori (WA-07).
PROMO_MARKERS = ("diskon", "promo", "penawaran", "harga mulai", "cashback", "hadiah", "gratis",
                 "bonus", "cicilan ringan", "terbatas", "segera hubungi", "jangan lewatkan")


def category_hints(body: str, category: str) -> list:
    """Peringatan bila isi bertentangan dengan kategori. Pemeriksaan bantu, TIDAK memblokir."""
    low = (body or "").lower()
    hits = [m for m in PROMO_MARKERS if m in low]
    if category == "utility" and hits:
        return [("Isi memuat penanda promosi (%s) tetapi kategorinya UTILITY. Meta bisa menurunkan/menolak "
                 "template ini, dan nomor yang opt-out akan tetap menerimanya. Pertimbangkan kategori MARKETING."
                 % ", ".join(hits[:3]))]
    if category == "marketing" and re.search(r"\b(jatuh tempo|tagihan|angsuran|termin|invoice|kwitansi)\b", low) and not hits:
        return ["Isi terbaca seperti pengingat tagihan tetapi kategorinya MARKETING — nomor opt-out tidak akan "
                "menerimanya. Pertimbangkan kategori UTILITY."]
    return []


async def reminder_mapping(org: str) -> dict:
    """{kind: template_code} dari settings (satu sumber: TEMPLATE_KEYS)."""
    vals = await cfg.get_many(list(TEMPLATE_KEYS.values()), org_id=org)
    return {kind: vals.get(key) for kind, key in TEMPLATE_KEYS.items()}


async def usage_map(org: str) -> dict:
    """{template_code: [{"type","label","id"}]} — semua tempat yang merujuk sebuah template."""
    out: dict = {}

    def add(code, item):
        if code:
            out.setdefault(code, []).append(item)

    async for pb in db.wa_playbooks.find({"org_id": org}, {"_id": 0, "id": 1, "name": 1, "template_code": 1}):
        add(pb.get("template_code"), {"type": "playbook", "label": f"Playbook: {pb.get('name') or pb['id']}", "id": pb["id"]})
    async for rule in db.automation_rules.find({"org_id": org}, {"_id": 0, "id": 1, "name": 1, "actions": 1}):
        for a in rule.get("actions") or []:
            if a.get("type") == "send_template":
                add(a.get("template_code"), {"type": "automation", "label": f"Otomasi: {rule.get('name') or rule['id']}", "id": rule["id"]})
    mapping = await reminder_mapping(org)
    for kind, code in mapping.items():
        add(code, {"type": "reminder", "label": f"Pengingat: {REMINDER_KIND_META[kind][0]}", "id": kind})
    async for b in db.broadcasts.find({"org_id": org, "status": {"$in": ["draft", "queued", "running", "paused"]}},
                                      {"_id": 0, "id": 1, "name": 1, "template_code": 1}):
        add(b.get("template_code"), {"type": "broadcast", "label": f"Broadcast aktif: {b.get('name') or b['id']}", "id": b["id"]})
    return out


def frozen_fields_changed(cur: dict, upd: dict) -> list:
    """Field yang dibekukan setelah Meta APPROVED (WA-06): isi & struktur parameter."""
    changed = []
    for f in ("body", "variables", "header_type", "header_text", "category", "language"):
        if f in upd and upd[f] != cur.get(f):
            changed.append(f)
    return changed
