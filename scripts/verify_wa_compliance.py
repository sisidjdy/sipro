#!/usr/bin/env python3
"""verify_wa_compliance.py — GATE Fase 97: template Meta, opt-out, aturan kirim, broadcast jujur.

  C1  Template belum `approved` ditolak dengan alasan (broadcast 400; gateway → failed template_not_approved).
  C2  Opt-out lewat kata UTUH (STOP/BERHENTI/UNSUB/HENTIKAN); "berhentikan pembangunan" TIDAK memicu.
  C3  Opt-out menghentikan MARKETING (recipient skipped opt_out) tetapi TIDAK menghentikan UTILITY.
  C4  Jam kirim dari Pusat Konfigurasi dihormati (`in_send_window`), setelan `wa.send_window_*` terdaftar.
  C5  Broadcast: tidak ada status karangan; ada pause/resume/cancel; laporan kegagalan per kode; estimasi biaya.
  C6  Daftar opt-out bisa dicari & diekspor CSV; consent tercatat saat dicabut.
"""
import pathlib
import sys
import uuid
from datetime import datetime, timezone

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _wa_common import BASE, BE, check, finish, hdr, meta_payload, phone, purge_leads, wa_channel_guard  # noqa: E402

sys.path.insert(0, str(BE))


def main():
    h = hdr()
    print("== C4 unit: jam kirim ==")
    import wa_compliance as wc  # noqa: E402 — modul murni (tanpa DB) untuk fungsi jam kirim & deteksi kata
    noon = datetime(2026, 9, 5, 5, 0, tzinfo=timezone.utc)  # 12:00 WIB
    night = datetime(2026, 9, 5, 16, 30, tzinfo=timezone.utc)  # 23:30 WIB
    check(wc.in_send_window("08:00", "20:00", noon) and not wc.in_send_window("08:00", "20:00", night),
          "C4 in_send_window WIB benar")
    check(wc.in_send_window("20:00", "06:00", night) and not wc.in_send_window("20:00", "06:00", noon), "C4b jendela lewat tengah malam")
    check(wc.detect_opt_out("tolong STOP kirim promo") and wc.detect_opt_out("Berhenti") and wc.detect_opt_out("unsub ya"),
          "C2 kata utuh STOP/BERHENTI/UNSUB terdeteksi")
    check(not wc.detect_opt_out("berhentikan pembangunan dulu") and not wc.detect_opt_out("stopkontak rusak"),
          "C2b 'berhentikan' / 'stopkontak' TIDAK memicu opt-out")
    settings = requests.get(f"{BASE}/settings", headers=h, params={"group": "whatsapp"}, timeout=20)
    keys = {r.get("key") for r in (settings.json().get("data") or [])} if settings.status_code == 200 else set()
    check({"wa.send_window_start", "wa.send_window_end", "wa.rate_limit_per_sec"} <= keys,
          "C4c setelan wa.send_window_*/rate_limit terdaftar di Pusat Konfigurasi", str(sorted(keys))[:200])

    print("== C1 template belum approved ==")
    t = requests.post(f"{BASE}/wa-templates", headers=h, json={"name": f"Gate Pending {uuid.uuid4().hex[:4]}",
                                                                "category": "marketing", "body": "Promo {{nama}}",
                                                                "variables": ["nama"]}, timeout=20).json()["data"]
    requests.put(f"{BASE}/wa-templates/{t['id']}", headers=h, json={"status": "pending"}, timeout=20)
    r = requests.post(f"{BASE}/broadcasts", headers=h, json={"name": "gate", "template_code": t["code"], "segment": {}}, timeout=20)
    check(r.status_code == 400 and "belum disetujui" in r.text, "C1 broadcast dengan template pending → 400 + alasan", r.text[:120])
    sub = requests.post(f"{BASE}/wa-templates/{t['id']}/submit", headers=h, timeout=20)
    check(sub.status_code == 400 and "LIVE" in sub.text, "C1b ajukan ke Meta di mode simulasi → 400 jujur (tidak dipalsukan)", sub.text[:120])
    pv = requests.get(f"{BASE}/wa-templates/{t['id']}/meta-preview", headers=h, timeout=20).json()["data"]
    check(pv["components"][0]["text"] == "Promo {{1}}", "C1c pemetaan {{nama}} → {{1}}", str(pv))
    requests.delete(f"{BASE}/wa-templates/{t['id']}", headers=h, timeout=20)

    print("== C3 opt-out vs kategori ==")
    ph = phone()
    lead = requests.post(f"{BASE}/leads", headers=h, json={"name": "Gate OptOut", "phone": ph, "source": "whatsapp"}, timeout=20)
    lead_id = (lead.json().get("data") or {}).get("id")
    requests.post(f"{BASE}/webhooks/wa", json=meta_payload(ph, "STOP"), timeout=20)
    lst = requests.get(f"{BASE}/wa/optouts", headers=h, params={"q": ph}, timeout=20).json()
    check(lst["total"] == 1, "C3 STOP dari pembeli → tercatat di wa_optouts", str(lst["total"]))
    mk = requests.post(f"{BASE}/broadcasts", headers=h, json={"name": "gate mk", "template_code": "promo",
                                                              "segment": {"sources": ["whatsapp"]}}, timeout=20).json()["data"]
    det = requests.get(f"{BASE}/broadcasts/{mk['id']}", headers=h, timeout=20).json()["data"]
    mine = [x for x in det["recipients"] if x["phone"] == ph]
    check(mine and mine[0]["status"] == "skipped" and mine[0]["skip_reason"] == "opt_out",
          "C3b MARKETING ke nomor opt-out dilewati (skipped/opt_out)", str(mine))
    check(any(f["code"] == "opt_out" for f in det["failures"]), "C5 laporan kegagalan per kode memuat opt_out", str(det["failures"]))
    check("cost_estimate" in mk and mk["status"] in ("queued", "sending", "completed"), "C5b estimasi biaya + status antrean nyata", str({k: mk.get(k) for k in ('status', 'cost_estimate')}))
    ut = requests.post(f"{BASE}/broadcasts", headers=h, json={"name": "gate ut", "template_code": "payment_reminder",
                                                              "segment": {"sources": ["whatsapp"]}}, timeout=20).json()["data"]
    det2 = requests.get(f"{BASE}/broadcasts/{ut['id']}", headers=h, timeout=20).json()["data"]
    mine2 = [x for x in det2["recipients"] if x["phone"] == ph]
    check(mine2 and mine2[0]["status"] != "skipped", "C3c UTILITY (pengingat tagihan) ke nomor opt-out TETAP jalan", str(mine2))
    pa = requests.post(f"{BASE}/broadcasts/{ut['id']}/pause", headers=h, timeout=20)
    check(pa.status_code in (200, 400), "C5c endpoint pause tersedia", str(pa.status_code))
    ca = requests.post(f"{BASE}/broadcasts/{ut['id']}/cancel", headers=h, timeout=20)
    check(ca.status_code in (200, 400), "C5d endpoint cancel tersedia", str(ca.status_code))
    requests.post(f"{BASE}/broadcasts/{mk['id']}/cancel", headers=h, timeout=20)
    csv = requests.get(f"{BASE}/wa/optouts/export.csv", headers=h, timeout=20)
    check(csv.status_code == 200 and ph in csv.text, "C6 ekspor CSV opt-out memuat nomor", str(csv.status_code))
    oid = lst["data"][0]["id"]
    rv = requests.delete(f"{BASE}/wa/optouts/{oid}", headers=h, timeout=20)
    check(rv.status_code == 200, "C6b opt-out bisa dicabut", rv.text[:100])
    if lead_id:
        ld = requests.get(f"{BASE}/leads/{lead_id}", headers=h, timeout=20).json().get("data") or {}
        check(ld.get("consent_at") and ld.get("wa_opt_out") is False, "C6c consent_at tercatat pada lead setelah dicabut", str({k: ld.get(k) for k in ('consent_at', 'wa_opt_out')}))
        requests.delete(f"{BASE}/leads/{lead_id}", headers=h, timeout=20)
    src = (BE / "routers/broadcasts_router.py").read_text()
    check("idx % 5" not in src and '"status": "read" if' not in src, "C5e tidak ada pemalsuan status di broadcast")
    purge_leads(["Gate OptOut"])
    finish("verify_wa_compliance")


if __name__ == "__main__":
    with wa_channel_guard():
        main()
