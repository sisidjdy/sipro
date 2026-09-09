#!/usr/bin/env python3
"""verify_wa_gateway.py — GATE Fase 95: satu pintu keluar WhatsApp.

  G1  Semua pemanggil kirim WA lewat `wa_gateway` — tidak ada `"mode": "simulation"` hardcoded di
      jalur kirim (inbox_router, engine.send_template_message, broadcasts, wa_reminder_engine, notifications).
  G2  Tidak ada fallback simulasi yang menelan kegagalan: `notifications.py` tanpa try/except → simulation.
  G3  Setiap pesan keluar punya `mode`, `status`, `category`, `provider_message_id` (live: kirim uji → simulated + sim-wamid).
  G4  Gagal tercatat GAGAL: nomor tidak valid → status `failed` + `error_code`, bukan `simulated`.
  G5  Indeks unik wamid `uq_messages_wamid` didaftarkan; kosakata wa_send_status/wa_mode/wa_message_category ada di /reference.
  G6  Pengingat mengirim TEMPLATE (bukan teks bebas) dan mencatat `gagal` bila Meta menolak.
  G7  Antrean `wa_outbox` ada: enqueue/process, galat sementara diulang (backoff), permanen tidak.
"""
import pathlib
import re
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _wa_common import BASE, BE, check, finish, hdr, wa_channel_guard  # noqa: E402


def main():
    print("== G1/G2 statis ==")
    for f in ("routers/inbox_router.py", "engine.py", "routers/broadcasts_router.py", "wa_reminder_engine.py",
              "notifications.py", "wa_docs.py", "routers/wa_router.py"):
        src = (BE / f).read_text()
        uses_gw = "wa_gateway" in src or "send_whatsapp" in src or "wa_outbox" in src
        check(uses_gw, f"G1 {f} memakai gateway/outbox")
    inbox = (BE / "routers/inbox_router.py").read_text()
    out_block = inbox.split('if direction == "out":')[1].split("else:")[0] if 'if direction == "out":' in inbox else ""
    check('"mode": "simulation"' not in out_block, "G1b inbox jalur keluar tanpa mode hardcoded")
    eng = (BE / "engine.py").read_text()
    stm = eng.split("async def send_template_message")[1].split("\nasync def ")[0]
    check('"mode": "simulation"' not in stm and "wa_gateway" in stm, "G1c engine.send_template_message lewat gateway")
    notif = (BE / "notifications.py").read_text()
    check("graph.facebook.com" not in notif and '"provider": "simulation", "status": "logged"}' not in notif.split("async def send_whatsapp")[0],
          "G2 notifications tanpa jalur Graph mati & tanpa fallback diam-diam")
    bc = (BE / "routers/broadcasts_router.py").read_text()
    check("idx % 5" not in bc and "is_read" not in bc, "G2b broadcast tidak mengarang status dibaca")
    check("wa_outbox" in bc and "enqueue(" in bc, "G7 broadcast memakai antrean wa_outbox")
    ob = (BE / "wa_outbox.py").read_text()
    check("MAX_ATTEMPTS" in ob and "BACKOFF_SECONDS" in ob and "is_transient" in ob, "G7b outbox: retry + backoff + galat permanen")
    check("uq_messages_wamid" in (BE / "server.py").read_text(), "G5 indeks unik wamid didaftarkan")
    rem = (BE / "wa_reminder_engine.py").read_text()
    check("template=tmpl" in rem and 'status, kode = "gagal"' in rem, "G6 pengingat kirim template & catat gagal")

    print("== G3/G4/G5 live ==")
    h = hdr()
    ref = requests.get(f"{BASE}/reference", headers=h, timeout=20).json()
    groups = ref.get("data") or ref
    for g in ("wa_send_status", "wa_mode", "wa_message_category", "broadcast_status", "wa_meta_template_status"):
        check(g in groups, f"G5 grup SSOT {g} ada di /reference")
    ok = requests.post(f"{BASE}/wa/config/test-message", headers=h, json={"to": "+6281355500011"}, timeout=20).json()["data"]
    check(ok["status"] in ("simulated", "sent") and ok["provider_message_id"], "G3 kirim uji → status jujur + wamid",
          str(ok))
    check(ok["mode"] in ("simulation", "live"), "G3b mode dibaca dari channel", ok.get("mode"))
    bad = requests.post(f"{BASE}/wa/config/test-message", headers=h, json={"to": "0812"}, timeout=20).json()["data"]
    check(bad["status"] == "failed" and bad["error_code"] == "invalid_phone", "G4 nomor tidak valid → failed (bukan simulated)", str(bad))
    rows = requests.get(f"{BASE}/wa/messages", headers=h, params={"kind": "test", "limit": 5}, timeout=20).json()["data"]
    check(rows and all(r.get("category") for r in rows), "G3c pesan keluar punya field category", str([r.get("category") for r in rows]))
    ob_rows = requests.get(f"{BASE}/wa/outbox", headers=h, params={"limit": 1}, timeout=20)
    check(ob_rows.status_code == 200, "G7c endpoint /wa/outbox hidup", str(ob_rows.status_code))
    finish("verify_wa_gateway")


if __name__ == "__main__":
    with wa_channel_guard():
        main()
