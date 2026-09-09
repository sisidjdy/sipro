#!/usr/bin/env python3
"""POC/verifikasi Fase 33 — UANG SUBKON HANYA MENGALIR MENGIKUTI BUKTI.

Yang dibuktikan di sini lewat API NYATA (bukan unit test terisolasi):

  A. Lingkup SPK berbasis item jadwal
     * SPK bisa dibayar per ITEM PEKERJAAN (bukan persen manual)
     * kandidat lingkup hanya item yang belum dipakai SPK lain
  B. INV-33-3 — satu pekerjaan hanya boleh masuk SATU SPK
  C. INV-33-4 — Σ nilai lingkup ≤ nilai kontrak SPK
  D. INV-33-5 — progres SPK mode item TIDAK BISA diketik manual
  E. INV-33-1 — termin hanya atas pekerjaan yang SUDAH DIVERIFIKASI
     * SPK yang lingkupnya belum terverifikasi: pengajuan DITOLAK + alasan jelas
  F. INV-33-6/7 — opname hanya boleh MENGURANGI + wajib beralasan; pengaju ≠ opname
  G. Persetujuan uang (finance): tagihan AP = Σ baris lolos opname, retensi sesuai SPK
  H. INV-33-2 — pekerjaan yang sudah dibayar tidak bisa ditagih dua kali; baris yang
     dikeluarkan/termin ditolak KEMBALI ke daftar siap-tagih (tidak hangus)
  I. Kendali biaya RAB: anggaran vs dikontrakkan vs terverifikasi vs ditagih tie-out,
     pemetaan RAB → langkah jadwal divalidasi
  J. RBAC/SoD: sales tak boleh lihat, site tak boleh ubah lingkup / menyetujui uang
  K. Regresi: SPK lump-sum lama tetap bisa opname persen & disetujui

Jalankan: python3 scripts/poc_33.py
"""
import os
import sys

import requests

BASE = os.environ.get("SIPRO_BASE", "http://localhost:8001/api")
PW = "Sipro#2026"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  PASS' if cond else '  FAIL'}  {name}"
          + (f" — {str(detail)[:170]}" if detail else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def g(h, p, **params):
    return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=90)


def po(h, p, body=None):
    return requests.post(f"{BASE}{p}", headers=h, json=body or {}, timeout=120)


def pu(h, p, body=None):
    return requests.put(f"{BASE}{p}", headers=h, json=body or {}, timeout=90)


def dl(h, p):
    return requests.delete(f"{BASE}{p}", headers=h, timeout=60)


def photo(h, label, owner_id):
    """Unggah foto lewat jalur NYATA (kompresi + watermark + hash anti-daur-ulang)."""
    import io
    import uuid

    from PIL import Image, ImageDraw
    nonce = uuid.uuid4().hex
    img = Image.new("RGB", (860, 560), (64, 92, 110))
    d = ImageDraw.Draw(img)
    for y in range(0, 560, 3):
        d.line([(0, y), (860, y)], fill=(64, min(255, 92 + y // 6), 110))
    d.text((26, 480), label[:70], fill=(255, 255, 255))
    d.text((26, 520), nonce, fill=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    r = requests.post(f"{BASE}/files/upload", headers=h,
                      files={"file": (f"p33-{nonce[:8]}.jpg", buf.getvalue(), "image/jpeg")},
                      data={"owner_type": "build_item", "owner_id": owner_id}, timeout=120)
    r.raise_for_status()
    return r.json()["data"]["id"]


def finish_item(site, pm, item_id, label):
    """Kerjakan → ajukan (foto + checklist) → verifikasi supervisor, lewat API nyata."""
    it = g(site, f"/build/items/{item_id}").json()["data"]
    if it.get("status") == "ready":
        po(site, f"/build/items/{item_id}/start")
        it = g(site, f"/build/items/{item_id}").json()["data"]
    if it.get("status") in ("ready", "in_progress", "rework"):
        n = max(1, int(it.get("min_photos") or 1))
        ids = [photo(site, f"{label} {i + 1}", item_id) for i in range(n)]
        po(site, f"/build/items/{item_id}/submit", {
            "note": f"POC33 {label}: pekerjaan dituntaskan sesuai checklist mutu.",
            "photo_file_ids": ids,
            "checklist": [{"code": c["code"], "result": "pass", "note": "sesuai spesifikasi"}
                          for c in (it.get("checklist") or [])]})
        it = g(site, f"/build/items/{item_id}").json()["data"]
    if it.get("status") == "submitted":
        po(pm, f"/build/items/{item_id}/verify", {"note": "Diverifikasi POC33"})
    return g(pm, f"/build/items/{item_id}").json()["data"]


def fresh_workset(pm, project_id, spk_id, pool):
    """Sediakan rantai pekerjaan yang bisa dikerjakan: jadwalkan unit yang belum terjadwal.

    Tanpa ini, POC bergantung pada sisa item 'ready' di database sehingga hanya bisa
    dijalankan sekali. Dengan menjadwalkan unit baru, bukti kerja selalu bisa dibuat
    lewat jalur nyata (kerjakan → foto → ajukan → verifikasi).
    """
    from datetime import date, timedelta
    free = [u for u in g(pm, "/build/unscheduled", project_id=project_id).json()["data"]
            if u.get("buildable")]
    if not free:
        return pool
    start = (date.today() - timedelta(days=3)).isoformat()
    r = po(pm, "/build/schedules", {"unit_id": free[0]["id"], "start_date": start})
    if r.status_code != 200:
        return pool
    cand = g(pm, f"/subcon/spk/{spk_id}/scope/candidates", unit_id=free[0]["id"]).json()["data"]
    items = [it for u in cand["units"] for it in u["items"]]
    return items or pool


def head(t):
    print(f"\n{t}\n" + "-" * len(t))


def main():
    owner = login("owner@sipro.co.id")
    pm = login("pm@sipro.co.id")
    site = login("site@sipro.co.id")
    fin = login("finance@sipro.co.id")
    sales = login("sales@sipro.co.id")

    # ============================ A. lingkup hasil seed ============================
    head("A. SPK borongan berbasis item (data awal nyata)")
    spks = g(pm, "/subcon/spk").json().get("data") or []
    item_spks = [s for s in spks if s.get("scope_mode") == "items"
                 and not str(s.get("title") or "").startswith("POC33")]
    item_spk = max(item_spks, key=lambda s: int(s.get("scope_items") or 0)) if item_spks else None
    if not check("ada SPK mode item pekerjaan", bool(item_spk),
                 [s.get("spk_number") for s in spks]):
        return summary()
    sid = item_spk["id"]
    sc = g(pm, f"/subcon/spk/{sid}/scope").json()
    rows = sc.get("data") or []
    s = sc.get("summary") or {}
    check("lingkup SPK berisi item jadwal nyata", len(rows) >= 3, f"{len(rows)} baris")
    check("Σ nilai lingkup = nilai kontrak (kontrak terurai penuh)",
          sc["contract"]["allocated"] == sc["contract"]["contract_value"],
          sc.get("contract"))
    check("setiap baris menunjuk unit + langkah + nilai",
          all(r.get("unit_code") and r.get("step_code") and int(r.get("value") or 0) > 0
              for r in rows))
    check("progres SPK = nilai terverifikasi ÷ nilai lingkup (bukan angka manual)",
          int(sc["spk"].get("progress_pct") or 0)
          == round(s["verified_value"] / s["scope_value"] * 100),
          f"spk={sc['spk'].get('progress_pct')} hitung={s['verified_value']}/{s['scope_value']}")
    op = g(pm, f"/subcon/spk/{sid}/opname").json()["data"]
    check("pratinjau opname hanya memuat pekerjaan TERVERIFIKASI & belum ditagih",
          bool(op["lines"]) and all(l["verified"] and not l.get("claim_id")
                                    for l in op["lines"]), f"{len(op['lines'])} baris")
    gross_expect = sum(int(l["value"]) for l in op["lines"])
    check("nilai opname = Σ nilai baris terverifikasi", op["gross"] == gross_expect,
          f"{op['gross']} vs {gross_expect}")
    check("retensi dihitung dari % SPK",
          op["retention_est"] == round(op["gross"] * op["retention_pct"] / 100)
          and op["net_est"] == op["gross"] - op["retention_est"], op)
    check("alasan pekerjaan lain belum bisa ditagih dijelaskan (bukan disembunyikan)",
          isinstance(op.get("blockers"), list) and bool(op["blockers"]), op.get("blockers"))

    # ====================== B/C/D. SPK baru: guard lingkup ======================
    head("B/C/D. Guard lingkup: anti dua SPK, plafon kontrak, progres tak bisa diketik")
    proj_id = item_spk["project_id"]
    subs = g(pm, "/subcon/subcontractors").json()["data"]
    sub2 = next((x for x in subs if x["id"] != item_spk.get("subcontractor_id")), subs[0])
    new_spk = po(pm, "/subcon/spk", {
        "subcontractor_id": sub2["id"], "project_id": proj_id,
        "title": "POC33 borongan arsitektur", "contract_value": 40_000_000,
        "retention_pct": 5}).json().get("data")
    if not check("PM bisa membuat SPK baru", bool(new_spk and new_spk.get("id"))):
        return summary()
    nid = new_spk["id"]
    taken = rows[0]["build_item_id"]
    r = po(pm, f"/subcon/spk/{nid}/scope", {"lines": [{"build_item_id": taken, "value": 1_000_000}]})
    check("INV-33-3 pekerjaan milik SPK lain DITOLAK", r.status_code == 400
          and "SPK" in r.json().get("detail", ""), r.text[:180])
    cand = g(pm, f"/subcon/spk/{nid}/scope/candidates").json()["data"]
    pool = [it for u in cand["units"] for it in u["items"]]
    used_ids = {x["build_item_id"] for x in rows}
    check("kandidat tidak memuat pekerjaan yang sudah dipakai SPK lain",
          not (used_ids & {p["build_item_id"] for p in pool}), f"{len(pool)} kandidat")
    check("kandidat membawa harga acuan RAB", cand["rab_mapped"]
          and any(int(p.get("suggested_value") or 0) > 0 for p in pool))
    # Fixture mandiri & bisa diulang: pakai unit yang BELUM punya jadwal supaya rantai
    # bukti (kerjakan → ajukan → verifikasi) selalu tersedia, bukan bergantung sisa data.
    pool = fresh_workset(pm, proj_id, nid, pool)
    unverified = [p for p in pool if not p["verified"]
                  and p["status"] in ("ready", "in_progress", "submitted")][:1]
    if not check("ada kandidat pekerjaan BELUM terverifikasi untuk uji INV-33-1",
                 len(unverified) == 1, len(unverified)):
        return summary()
    nxt = next((p for p in pool if p["build_item_id"] != unverified[0]["build_item_id"]
                and p["unit_id"] == unverified[0]["unit_id"]
                and (p.get("order") or 0) > (unverified[0].get("order") or 0)), None)
    if not check("ada pekerjaan berikutnya di unit yang sama (uji urutan bukti)", bool(nxt)):
        return summary()
    unverified.append(nxt)
    v1, v2 = 5_000_000, 4_000_000
    r = po(pm, f"/subcon/spk/{nid}/scope", {"lines": [
        {"build_item_id": unverified[0]["build_item_id"], "value": v1},
        {"build_item_id": unverified[1]["build_item_id"], "value": v2}]})
    check("PM bisa mengisi lingkup dengan nilai borongan", r.status_code == 200
          and r.json()["data"]["added"] == 2, r.text[:150])
    r = po(pm, f"/subcon/spk/{nid}/scope", {"lines": [
        {"build_item_id": pool[-1]["build_item_id"], "value": 90_000_000}]})
    check("INV-33-4 Σ lingkup > nilai kontrak DITOLAK", r.status_code == 400
          and "nilai kontrak" in r.json().get("detail", ""), r.text[:180])
    r = po(pm, f"/subcon/spk/{nid}/scope", {"lines": [
        {"build_item_id": pool[-1]["build_item_id"], "value": 0}]})
    check("nilai borongan 0 DITOLAK (pekerjaan tanpa nilai tak bisa ditagih)",
          r.status_code == 400, r.text[:150])
    r = pu(pm, f"/subcon/spk/{nid}", {"progress_pct": 80})
    check("INV-33-5 progres SPK mode item tidak bisa diketik manual",
          r.status_code == 400 and "dihitung otomatis" in r.json().get("detail", ""),
          r.text[:180])
    r = pu(pm, f"/subcon/spk/{nid}", {"contract_value": 1_000_000})
    check("nilai kontrak tidak bisa diturunkan di bawah total lingkup",
          r.status_code == 400, r.text[:150])
    r = po(pm, f"/subcon/spk/{nid}/status", {"status": "completed"})
    check("SPK tak bisa ditutup selama ada pekerjaan belum diverifikasi",
          r.status_code == 400 and "belum diverifikasi" in r.json().get("detail", ""),
          r.text[:170])

    # ====================== E. INV-33-1 termin butuh bukti ======================
    head("E. INV-33-1 — termin hanya atas pekerjaan yang sudah DIVERIFIKASI")
    r = po(site, "/subcon/claims", {"spk_id": nid})
    check("pengajuan termin tanpa pekerjaan terverifikasi DITOLAK", r.status_code == 400
          and "terverifikasi" in r.json().get("detail", ""), r.text[:200])
    check("penolakan menyebut kondisi nyata pekerjaannya",
          "menunggu verifikasi" in r.text.lower() or "belum selesai" in r.text.lower(),
          r.text[:200])

    # ====================== F/G. pengajuan → opname → setujui ======================
    head("F/G. Bukti dulu, uang kemudian: verifikasi pekerjaan → ajukan → opname → setujui")
    for i, cnd in enumerate(unverified):
        it = finish_item(site, pm, cnd["build_item_id"], f"pekerjaan {i + 1}")
        if not check(f"pekerjaan {cnd['step_code']} berhasil diverifikasi lewat jalur nyata",
                     it.get("status") == "done" and bool(it.get("verified_by")),
                     it.get("status")):
            return summary()
    opn = g(pm, f"/subcon/spk/{nid}/opname").json()["data"]
    check("pekerjaan yang baru diverifikasi LANGSUNG muncul sebagai siap-tagih",
          opn["gross"] == v1 + v2 and len(opn["lines"]) == 2, opn["gross"])
    r = po(site, "/subcon/claims", {"spk_id": nid, "period": "POC33 termin 1"})
    claim = r.json().get("data") if r.status_code == 200 else None
    if not check("pelaksana bisa mengajukan termin (nilai dihitung sistem)", bool(claim),
                 r.text[:200]):
        return summary()
    cid = claim["id"]
    check("termin memakai basis item pekerjaan", claim.get("basis") == "items")
    check("nilai termin = Σ pekerjaan terverifikasi (tanpa ketik persen)",
          claim["gross_est"] == v1 + v2, f"{claim['gross_est']} vs {v1 + v2}")
    check("baris termin membekukan bukti verifikasi (siapa & kapan)",
          all(l.get("verified_by") and l.get("verified_at") for l in claim["lines"]))
    r2 = po(site, "/subcon/claims", {"spk_id": nid})
    check("tidak bisa mengajukan dua termin sekaligus untuk SPK sama", r2.status_code == 400,
          r2.text[:140])
    op2 = g(pm, f"/subcon/spk/{nid}/opname").json()["data"]
    check("pekerjaan yang sedang diajukan tidak muncul lagi sebagai siap-tagih",
          op2["gross"] == 0 and op2["open_claim"] and op2["open_claim"]["id"] == cid,
          op2["gross"])
    r = po(site, f"/subcon/claims/{cid}/verify", {})
    check("INV-33-7 pengaju tidak boleh meng-opname sendiri", r.status_code == 403,
          r.text[:160])
    r = po(pm, f"/subcon/claims/{cid}/verify", {"exclude": ["item-palsu-123"], "reason": "coba"})
    check("INV-33-6 opname tidak bisa MENAMBAH baris", r.status_code == 400
          and "MENGURANGI" in r.json().get("detail", ""), r.text[:170])
    drop = next(l for l in claim["lines"] if int(l["value"]) == v1)
    keep_val = v2
    r = po(pm, f"/subcon/claims/{cid}/verify", {"exclude": [drop["scope_item_id"]]})
    check("pengurangan tanpa alasan DITOLAK", r.status_code == 400, r.text[:150])
    r = po(pm, f"/subcon/claims/{cid}/verify", {
        "exclude": [drop["scope_item_id"]],
        "reason": "volume acian kurang 4 m2, plester belum rata di sisi timur"})
    ver = r.json().get("data") if r.status_code == 200 else {}
    check("opname mengurangi baris + alasan tercatat", r.status_code == 200
          and ver.get("excluded_items") == 1 and ver.get("excluded_value") == v1
          and ver.get("gross_est") == keep_val, r.text[:200])
    r = po(pm, f"/subcon/claims/{cid}/approve")
    check("PM tidak boleh menyetujui uang (SoD)", r.status_code == 403, r.text[:140])
    r = po(site, f"/subcon/claims/{cid}/approve")
    check("pelaksana tidak boleh menyetujui uang (SoD)", r.status_code == 403, r.text[:140])
    r = po(fin, f"/subcon/claims/{cid}/approve")
    appr = r.json().get("data") if r.status_code == 200 else {}
    check("finance menyetujui → nilai = Σ baris lolos opname",
          appr.get("status") == "approved" and appr.get("gross") == keep_val, r.text[:200])
    check("retensi & net sesuai % SPK",
          appr.get("retention_held") == round(keep_val * appr.get("retention_pct", 0) / 100)
          and appr.get("net") == keep_val - appr.get("retention_held"),
          {k: appr.get(k) for k in ("gross", "retention_held", "net", "retention_pct")})
    bills = g(fin, "/finance/ap/bills").json().get("data") or []
    bill = next((b for b in bills if b["id"] == appr.get("ap_bill_id")), None)
    check("tagihan AP nyata terbentuk & terposting (approved)",
          bool(bill) and bill.get("claimed") == keep_val
          and bill.get("status") in ("approved", "partially_paid", "paid"),
          bill and {k: bill.get(k) for k in ("claimed", "net", "status")})

    # ====================== H. anti bayar ganda & baris kembali ======================
    head("H. INV-33-2 — tidak bisa ditagih dua kali; baris dikeluarkan tidak hangus")
    sc2 = g(pm, f"/subcon/spk/{nid}/scope").json()
    paid = [r_ for r_ in sc2["data"] if r_.get("claim_id")]
    check("pekerjaan yang dibayar ditandai SUDAH DITAGIH + nomor termin",
          len(paid) == 1 and paid[0].get("claim_number") == appr.get("claim_number")
          and paid[0]["state"] == "billed", f"{len(paid)} baris")
    check("nilai ditagih pada ringkasan SPK = nilai tagihan AP",
          sc2["summary"]["billed_value"] == keep_val, sc2["summary"])
    check("progres & persen tertagih SPK dihitung dari nilai (bukan diketik)",
          sc2["spk"]["progress_pct"] == round((v1 + v2) / sc2["summary"]["scope_value"] * 100)
          and sc2["spk"]["billed_pct"] == round(keep_val / sc2["summary"]["scope_value"] * 100),
          {k: sc2["spk"].get(k) for k in ("progress_pct", "billed_pct")})
    op3 = g(pm, f"/subcon/spk/{nid}/opname").json()["data"]
    check("baris yang dikeluarkan opname KEMBALI ke daftar siap-tagih",
          op3["gross"] == v1 and [l["id"] for l in op3["lines"]] == [drop["scope_item_id"]],
          op3["gross"])
    r = po(site, "/subcon/claims", {"spk_id": nid, "period": "POC33 termin 2"})
    c2 = r.json().get("data") if r.status_code == 200 else {}
    check("termin berikutnya hanya memuat pekerjaan yang belum dibayar",
          len(c2.get("lines") or []) == 1 and c2["gross_est"] == v1
          and c2["lines"][0]["scope_item_id"] == drop["scope_item_id"], r.text[:200])
    r = po(fin, f"/subcon/claims/{c2['id']}/reject", {"note": "Tunggu perbaikan selesai"})
    check("termin bisa ditolak", r.status_code == 200
          and r.json()["data"]["status"] == "rejected", r.text[:140])
    op4 = g(pm, f"/subcon/spk/{nid}/opname").json()["data"]
    check("termin ditolak → pekerjaan kembali siap-tagih (tidak hangus)",
          op4["gross"] == v1 and not op4["open_claim"], op4["gross"])
    r = dl(pm, f"/subcon/spk/{nid}/scope/{paid[0]['id']}")
    check("baris yang sudah ditagih tidak bisa dihapus dari lingkup", r.status_code == 400
          and "sudah ditagih" in r.json().get("detail", ""), r.text[:170])
    free = next(r_ for r_ in sc2["data"] if not r_.get("claim_id"))
    r = dl(pm, f"/subcon/spk/{nid}/scope/{free['id']}")
    check("baris yang belum ditagih bisa dikeluarkan dari lingkup", r.status_code == 200,
          r.text[:150])

    # ====================== I. kendali biaya RAB ======================
    head("I. Kendali biaya RAB: anggaran vs dikontrakkan vs terverifikasi vs ditagih")
    cc = g(pm, "/boq/control", project_id=proj_id).json()["data"]
    all_scope = []
    for sp in g(pm, "/subcon/spk", project_id=proj_id).json()["data"]:
        all_scope += g(pm, f"/subcon/spk/{sp['id']}/scope").json()["data"]
    exp_contracted = sum(int(x["value"]) for x in all_scope)
    exp_verified = sum(int(x["value"]) for x in all_scope if x.get("verified"))
    exp_billed = sum(int(x["value"]) for x in all_scope if x.get("claim_id"))
    check("total dikontrakkan = Σ lingkup seluruh SPK proyek",
          cc["totals"]["contracted"] == exp_contracted,
          f"{cc['totals']['contracted']} vs {exp_contracted}")
    check("total terverifikasi & ditagih tie-out dengan lingkup",
          cc["totals"]["verified"] == exp_verified and cc["totals"]["billed"] == exp_billed,
          cc["totals"])
    check("anggaran RAB tampil per kategori & per kode biaya",
          bool(cc["categories"]) and bool(cc["cost_codes"])
          and cc["totals"]["budget"] > 0, cc["totals"])
    check("selisih anggaran vs kontrak dihitung",
          cc["totals"]["variance"] == cc["totals"]["budget"] - cc["totals"]["contracted"])
    steps = g(pm, "/boq/steps", project_id=proj_id).json()["data"]
    check("daftar langkah jadwal proyek tersedia untuk pemetaan RAB",
          len(steps) >= 5 and all(x.get("step_code") for x in steps), len(steps))
    boq = g(pm, "/boq/items", project_id=proj_id).json()["data"]
    target = next((b for b in boq if b.get("cost_code") == "FIN-01"), boq[0])
    r = pu(pm, f"/boq/items/{target['id']}/steps", {"step_codes": ["TIDAK-ADA"]})
    check("pemetaan ke langkah yang tidak ada DITOLAK", r.status_code == 400, r.text[:150])
    keep = steps[0]["step_code"]
    r = pu(pm, f"/boq/items/{target['id']}/steps", {"step_codes": [keep]})
    check("pemetaan RAB → langkah jadwal tersimpan", r.status_code == 200
          and r.json()["data"]["step_codes"] == [keep], r.text[:150])
    pu(pm, f"/boq/items/{target['id']}/steps", {"step_codes": target.get("step_codes") or []})
    check("item RAB tanpa pemetaan terhitung sebagai anggaran belum dipetakan",
          isinstance(cc.get("unmapped_budget"), int))

    # ====================== J. RBAC ======================
    head("J. RBAC & pemisahan tugas")
    check("sales tidak bisa melihat lingkup SPK",
          g(sales, f"/subcon/spk/{sid}/scope").status_code == 403)
    check("sales tidak bisa melihat kendali biaya RAB",
          g(sales, "/boq/control", project_id=proj_id).status_code == 403)
    check("pelaksana (site) tidak bisa mengubah lingkup SPK",
          po(site, f"/subcon/spk/{nid}/scope", {"lines": []}).status_code == 403)
    check("pelaksana bisa MELIHAT lingkup (transparansi kerja)",
          g(site, f"/subcon/spk/{sid}/scope").status_code == 200)
    check("owner bisa melihat semuanya",
          g(owner, f"/subcon/spk/{sid}/opname").status_code == 200)

    # ====================== K. regresi lump-sum ======================
    head("K. Regresi — SPK lump-sum lama tetap berjalan")
    lump = next((x for x in spks if x.get("scope_mode") != "items"
                 and x.get("status") == "active"), None)
    if lump:
        claims = g(pm, "/subcon/claims", spk_id=lump["id"]).json()["data"]
        open_c = next((c for c in claims if c.get("status") == "submitted"), None)
        if not open_c:
            open_c = po(site, "/subcon/claims", {
                "spk_id": lump["id"],
                "progress_pct": int(lump.get("progress_pct") or 0) + 5}).json().get("data")
        check("termin lump-sum bisa diajukan dengan persen kumulatif", bool(open_c))
        if open_c:
            vp = int(open_c["claimed_pct"])
            r = po(pm, f"/subcon/claims/{open_c['id']}/verify", {"verified_pct": vp})
            check("opname lump-sum (persen) masih berjalan", r.status_code == 200, r.text[:150])
            r = po(fin, f"/subcon/claims/{open_c['id']}/approve")
            check("persetujuan lump-sum tetap membuat tagihan AP", r.status_code == 200
                  and r.json()["data"].get("ap_bill_id"), r.text[:150])
    else:
        check("ada SPK lump-sum untuk regresi", False)

    return summary()


def summary():
    print("\n" + "-" * 60)
    print(f"HASIL: {len(PASS)} PASS, {len(FAIL)} FAIL")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        print("POC 33 GAGAL")
        return 1
    print("POC 33 LULUS — uang subkon hanya mengalir mengikuti bukti terverifikasi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
