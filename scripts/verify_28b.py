"""verify_28b.py — POC/verifikasi Fase 28b (Site Plan lanjutan, foto nyata, showroom publik).

Menguji KONTRAK NYATA lewat HTTP (bukan unit test palsu):
  A. Peta demo ter-generate otomatis + metrik heatmap (harga/m², days on market).
  B. Foto lapangan nyata: unggah ke object storage → file_id → tampil di detail kavling
     (dan foto base64 warisan tetap bisa dirender).
  C. Foto bukti perbaikan punch (sebelum → sesudah).
  D. Master unit: luas/orientasi/hoek sebagai field nyata + enum liar ditolak 400.
  E. Showroom publik: token, data aman (tanpa identitas pembeli), form lead → pipeline,
     dedup, honeypot, pembatas laju, dan tutup halaman (404).
  F. Portal pembeli: peta kavling sendiri + foto progres + berkas foto berizin.

Jalankan: python3 scripts/verify_28b.py
"""
import base64
import io
import sys
import time

import requests

BASE = "http://localhost:8001"
API = BASE + "/api"
PW = "Sipro#2026"


def make_photo(label: str, tone=(64, 110, 92)) -> bytes:
    """Gambar uji berukuran nyata (bukan 1x1) supaya galeri benar-benar terlihat."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (480, 300), tone)
        d = ImageDraw.Draw(img)
        for y in range(300):
            d.line([(0, y), (480, y)],
                   fill=(tone[0] + y // 6, tone[1] + y // 8, tone[2] + y // 10))
        d.rectangle([20, 200, 460, 280], fill=(255, 255, 255))
        d.text((32, 232), label[:46], fill=(20, 40, 30))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:                                    # pragma: no cover
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8//8/AAX+Av6nNckR"
            "AAAAAElFTkSuQmCC")


PNG = make_photo("Foto uji verifikasi 28b")
DATA_URL = "data:image/png;base64," + base64.b64encode(
    make_photo("Foto warisan base64")).decode()

ok_count, fail = 0, []


def check(label, cond, extra=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"  PASS  {label}")
    else:
        fail.append(label)
        print(f"  FAIL  {label} {extra}")


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    tok = login("owner@sipro.co.id")
    h = H(tok)

    print("\nA. Peta demo otomatis + metrik heatmap")
    pid = requests.get(f"{API}/projects", headers=h, timeout=15).json()["data"][0]["id"]
    sp = requests.get(f"{API}/site-plan/{pid}", headers=h, timeout=20).json()["data"]
    units = sp["units"]
    plan = sp.get("plan") or {}
    check("peta SVG demo sudah ada tanpa buka Studio", bool(plan.get("shapes")),
          f"shapes={len(plan.get('shapes') or [])}")
    check("cakupan pemetaan shape→unit 100%",
          (plan.get("stats") or {}).get("coverage_pct") == 100, str(plan.get("stats")))
    check("setiap unit punya days_on_market",
          all("days_on_market" in u for u in units))
    check("harga per m² dihitung untuk unit berluas tanah",
          any(u.get("price_per_m2") for u in units))
    u1 = units[0]

    print("\nB. Foto lapangan NYATA (object storage) muncul di detail kavling")
    up = requests.post(f"{API}/files/upload", headers=h, timeout=30,
                       files={"file": ("progres.png", io.BytesIO(make_photo("Pengecoran kolom lantai 1")), "image/png")},
                       data={"owner_type": "site_diary", "owner_id": pid})
    check("POST /files/upload berhasil", up.status_code == 200, up.text[:200])
    fid = up.json()["data"]["id"]
    r = requests.post(f"{API}/field/diary", headers=h, timeout=20, json={
        "project_id": pid, "work_description": "Pengecoran kolom lantai 1 blok A",
        "weather": "cerah", "workforce": 14, "photos": [fid]})
    check("buku harian menerima daftar file_id", r.status_code == 200, r.text[:200])
    check("dokumen buku harian menyimpan photos[]",
          (r.json().get("data") or {}).get("photos") == [fid])

    up2 = requests.post(f"{API}/files/upload", headers=h, timeout=30,
                        files={"file": ("temuan.png", io.BytesIO(make_photo("Retak rambut dinding", (140, 70, 60))), "image/png")},
                        data={"owner_type": "punch_item", "owner_id": pid})
    fid2 = up2.json()["data"]["id"]
    r = requests.post(f"{API}/field/punchlist", headers=h, timeout=20, json={
        "project_id": pid, "unit_id": u1["id"], "title": "Retak rambut dinding kamar utama",
        "severity": "medium", "category": "finishing", "photos": [fid2]})
    check("temuan punch menerima daftar file_id", r.status_code == 200, r.text[:200])
    punch_id = r.json()["data"]["id"]

    # Foto warisan base64 harus tetap didukung (tanpa regresi).
    r = requests.post(f"{API}/field/punchlist", headers=h, timeout=20, json={
        "project_id": pid, "unit_id": u1["id"], "title": "Nat keramik tidak rapi",
        "severity": "low", "category": "finishing", "photo": DATA_URL})
    check("temuan punch dengan foto base64 warisan tetap diterima", r.status_code == 200)

    det = requests.get(f"{API}/site-plan/{pid}/unit/{u1['id']}", headers=h, timeout=20).json()["data"]
    photos = det["construction"]["photos"]
    by_file = [p for p in photos if p.get("file_id")]
    inline = [p for p in photos if p.get("inline")]
    check("detail kavling mengembalikan foto", len(photos) >= 3, f"n={len(photos)}")
    check("foto object storage dirujuk sebagai file_id (bukan data URL)",
          all(not str(p["file_id"]).startswith("data:") for p in by_file))
    check("foto base64 warisan dikirim sebagai inline (bisa dirender)", len(inline) >= 1)
    check("cakupan foto ditandai unit/proyek",
          {p["scope"] for p in photos} <= {"unit", "proyek"} and len({p["scope"] for p in photos}) == 2)
    img = requests.get(f"{API}/files/{by_file[0]['file_id']}", headers=h, timeout=20)
    check("GET /files/{id} mengembalikan gambar 200",
          img.status_code == 200 and img.headers.get("content-type", "").startswith("image/"),
          f"{img.status_code} {img.headers.get('content-type')}")

    print("\nC. Foto bukti perbaikan (sebelum → sesudah)")
    up3 = requests.post(f"{API}/files/upload", headers=h, timeout=30,
                        files={"file": ("sesudah.png", io.BytesIO(make_photo("Sesudah diaci & dicat", (60, 90, 140))), "image/png")},
                        data={"owner_type": "punch_item", "owner_id": pid})
    fid3 = up3.json()["data"]["id"]
    r = requests.post(f"{API}/field/punchlist/{punch_id}/status", headers=h, timeout=20,
                      json={"status": "closed", "photos": [fid3],
                            "note": "Sudah diaci & dicat ulang"})
    check("status punch + foto perbaikan tersimpan", r.status_code == 200, r.text[:200])
    check("fix_photos terisi", r.json()["data"].get("fix_photos") == [fid3])
    det = requests.get(f"{API}/site-plan/{pid}/unit/{u1['id']}", headers=h, timeout=20).json()["data"]
    labels = [p["label"] for p in det["construction"]["photos"]]
    check("galeri kavling memberi label 'Perbaikan: …'",
          any(str(x).startswith("Perbaikan:") for x in labels), str(labels)[:200])

    # --- Bukti kerja BERPASANGAN (sebelum → sesudah) ---
    reps = det["construction"].get("repairs") or []
    check("detail kavling mengembalikan pasangan bukti perbaikan", len(reps) >= 1, f"n={len(reps)}")
    mine_pair = next((r for r in reps if r["punch_id"] == punch_id), None)
    check("pasangan untuk temuan yang ditutup ditemukan", mine_pair is not None)
    if mine_pair:
        check("pasangan punya foto SEBELUM & SESUDAH",
              len(mine_pair["before"]) >= 1 and len(mine_pair["after"]) >= 1,
              f"before={len(mine_pair['before'])} after={len(mine_pair['after'])}")
        check("pasangan ditandai sudah diperbaiki (resolved)", mine_pair["resolved"] is True,
              str(mine_pair.get("status")))
        check("catatan pengerjaan tersimpan di temuan",
              "diaci" in str(mine_pair.get("note", "")).lower(), str(mine_pair.get("note")))
        check("tanggal lapor & tanggal perbaikan tersedia",
              bool(mine_pair.get("opened_at")) and bool(mine_pair.get("fixed_at")))
    open_pair = next((r for r in reps if r["resolved"] is False), None)
    check("temuan yang MASIH ditangani tetap tampil (jujur, tanpa foto sesudah)",
          open_pair is not None and not open_pair["after"],
          "tidak ada temuan terbuka berfoto pada unit ini")
    check("bukti yang sudah tuntas diurutkan lebih dulu",
          reps[0]["resolved"] is True if reps else False)

    print("\nD. Master unit: luas / orientasi / hoek sebagai field nyata")
    r = requests.put(f"{API}/projects/{pid}/units/{u1['id']}", headers=h, timeout=20,
                     json={"luas_tanah": 132, "luas_bangunan": 58,
                           "orientation": "timur_laut", "corner": True})
    check("PUT unit menerima luas/orientasi/hoek", r.status_code == 200, r.text[:300])
    fresh = r.json()["data"]
    check("nilai luas tersimpan", fresh.get("luas_tanah") == 132 and fresh.get("luas_bangunan") == 58)
    check("orientasi tersimpan kanonik", fresh.get("orientation") == "timur_laut")
    check("hoek tersimpan", fresh.get("corner") is True)
    r = requests.put(f"{API}/projects/{pid}/units/{u1['id']}", headers=h, timeout=20,
                     json={"orientation": "sebelah kanan pos ronda"})
    check("orientasi liar ditolak 400 + pesan Indonesia",
          r.status_code == 400 and "Orientasi" in r.text, f"{r.status_code} {r.text[:160]}")
    sp2 = requests.get(f"{API}/site-plan/{pid}", headers=h, timeout=20).json()["data"]
    up_unit = next(u for u in sp2["units"] if u["id"] == u1["id"])
    check("peta memakai luas dari field (bukan turunan nama tipe)",
          up_unit["luas_tanah"] == 132 and up_unit["price_per_m2"] == round(up_unit["price"] / 132))

    print("\nE. Showroom publik + tangkap lead")
    r = requests.post(f"{API}/site-plan/{pid}/showroom", headers=h, timeout=20,
                      json={"enabled": True, "headline": "Cluster Asri — tinggal 17 kavling",
                            "contact_wa": "081234567890", "show_price": True})
    check("aktifkan showroom publik", r.status_code == 200, r.text[:200])
    cfg = r.json()["data"]
    token = cfg["token"]
    check("token & path share tersedia", bool(token) and cfg["path"] == f"/showroom/{token}")
    pub = requests.get(f"{API}/public/showroom/{token}", timeout=20)
    check("halaman publik bisa diakses TANPA login", pub.status_code == 200, pub.text[:200])
    pdata = pub.json()["data"]
    raw = pub.text.lower()
    check("tidak ada identitas pembeli / deal di payload publik",
          "buyer" not in raw and "deal_id" not in raw and "lead" not in raw)
    check("kavling publik berisi kode/tipe/luas/harga/status",
          all(k in pdata["units"][0] for k in ("code", "type", "luas_tanah", "price", "status")))
    check("label enum dikirim dari SSOT (frontend tidak hardcode)",
          set(pdata["labels"]) >= {"unit_status", "unit_type", "unit_orientation"})
    check("peta ikut dikirim ke halaman publik", bool((pdata.get("plan") or {}).get("shapes")))
    check("statistik ringkas tersedia",
          pdata["stats"]["total"] > 0 and pdata["stats"]["available"] >= 0)

    lead_phone = "08125" + str(int(time.time()))[-6:]   # unik per run (index unik telepon)
    r = requests.post(f"{API}/public/showroom/{token}/lead", timeout=20, json={
        "name": "Rina Puspita", "phone": lead_phone, "unit_code": pdata["units"][0]["code"],
        "message": "Saya ingin survey lokasi akhir pekan ini."})
    check("form lead publik diterima", r.status_code == 200, r.text[:250])
    leads = requests.get(f"{API}/leads", headers=h, params={"source": "showroom_public"},
                         timeout=20).json()
    check("lead masuk pipeline dengan sumber showroom_public", leads["total"] >= 1)
    mine = [x for x in leads["data"] if str(x.get("phone", "")).endswith(lead_phone[-8:])]
    check("lead dari form ini ditemukan lewat nomor WhatsApp", len(mine) == 1,
          f"cocok={len(mine)}")
    lead = mine[0] if mine else leads["data"][0]
    check("lead otomatis ditugaskan ke sales", bool(lead.get("assigned_to")), str(lead)[:200])
    check("lead punya skor & band", bool(lead.get("score")) and bool(lead.get("score_band")))
    check("catatan lead menyebut kavling yang diminati",
          pdata["units"][0]["code"] in str(lead.get("notes")), str(lead.get("notes")))
    r = requests.post(f"{API}/public/showroom/{token}/lead", timeout=20, json={
        "name": "Rina Puspita", "phone": lead_phone, "message": "cek lagi"})
    check("kiriman ulang nomor sama tidak membuat lead kembar",
          r.status_code == 200 and r.json()["data"]["duplicate"] is True, r.text[:200])
    r = requests.post(f"{API}/public/showroom/{token}/lead", timeout=20, json={
        "name": "Bot Spam", "phone": "081200000001", "website": "http://spam.example"})
    check("honeypot menolak bot (400)", r.status_code == 400, r.text[:120])
    r = requests.post(f"{API}/public/showroom/{token}/lead", timeout=20,
                      json={"name": "A", "phone": "0812"})
    check("validasi nama/telepon terlalu pendek ditolak 400", r.status_code == 400)

    codes = set()
    for i in range(8):
        rr = requests.post(f"{API}/public/showroom/{token}/lead", timeout=20, json={
            "name": f"Pengunjung {i}", "phone": f"08129900{i:04d}"})
        codes.add(rr.status_code)
    check("pembatas laju melindungi form dari spam (429)", 429 in codes, str(codes))

    r = requests.post(f"{API}/site-plan/{pid}/showroom", headers=h, timeout=20,
                      json={"enabled": True, "regenerate": True, "show_price": False})
    new_token = r.json()["data"]["token"]
    check("token bisa diputar ulang bila link tersebar", new_token and new_token != token)
    check("token lama langsung mati (404)",
          requests.get(f"{API}/public/showroom/{token}", timeout=20).status_code == 404)
    pub2 = requests.get(f"{API}/public/showroom/{new_token}", timeout=20).json()["data"]
    check("mode sembunyikan harga dihormati",
          all(u["price"] is None for u in pub2["units"]) and pub2["project"]["show_price"] is False)
    r = requests.post(f"{API}/site-plan/{pid}/showroom", headers=h, timeout=20,
                      json={"enabled": False})
    check("tutup showroom → halaman publik 404",
          requests.get(f"{API}/public/showroom/{new_token}", timeout=20).status_code == 404)
    # Aktifkan kembali untuk pengujian UI berikutnya (harga tampil).
    r = requests.post(f"{API}/site-plan/{pid}/showroom", headers=h, timeout=20,
                      json={"enabled": True, "regenerate": True, "show_price": True,
                            "headline": "Cluster Asri Blok A — hunian asri di tengah kota",
                            "contact_wa": "081234567890"})
    final_token = r.json()["data"]["token"]
    print(f"       (token showroom untuk uji UI: /showroom/{final_token})")

    print("\nF. Portal pembeli: peta kavling + foto progres")
    custs = requests.get(f"{API}/customers", headers=h, timeout=20).json().get("data") or []
    ident = None
    for c in custs:
        if c.get("phone"):
            ident = c["phone"]
            break
    if not ident:
        check("ada customer untuk uji portal", False, "tidak ada customer berponsel")
    else:
        requests.post(f"{API}/portal/auth/request-otp", json={"identifier": ident}, timeout=20)
        rv = requests.post(f"{API}/portal/auth/verify-otp",
                           json={"identifier": ident, "code": "000000"}, timeout=20)
        check("login portal (OTP master) berhasil", rv.status_code == 200, rv.text[:200])
        ptok = rv.json()["token"]
        ph = {"Authorization": f"Bearer {ptok}"}
        sp = requests.get(f"{API}/portal/site-plan", headers=ph, timeout=20)
        check("GET /portal/site-plan 200", sp.status_code == 200, sp.text[:200])
        projs = sp.json()["data"]["projects"]
        check("portal mengembalikan minimal 1 proyek", len(projs) >= 1, str(sp.json())[:200])
        if projs:
            p0 = projs[0]
            mine = [u for u in p0["units"] if u["mine"]]
            others = [u for u in p0["units"] if not u["mine"]]
            check("kavling milik pembeli ditandai", len(mine) >= 1)
            check("harga & data tetangga disembunyikan",
                  all(o["price"] is None and o.get("type") is None for o in others))
            check("peta ikut dikirim ke portal", bool((p0.get("plan") or {}).get("shapes")))
        pg = requests.get(f"{API}/portal/progress", headers=ph, timeout=20).json()["data"]
        pf = [p for row in pg for p in (row.get("photos") or [])]
        check("portal progres menyertakan foto lapangan", len(pf) >= 1, f"n={len(pf)}")
        prs = [r for row in pg for r in (row.get("repairs") or [])]
        check("portal menyertakan bukti perbaikan berpasangan", len(prs) >= 1, f"n={len(prs)}")
        if prs:
            check("pasangan portal memuat sisi sebelum & sesudah",
                  any(r["before"] and r["after"] for r in prs))
            check("portal tidak membocorkan id internal selain punch_id",
                  all(set(r) <= {"punch_id", "title", "severity", "status", "resolved", "note",
                                 "opened_at", "fixed_at", "before", "after"} for r in prs),
                  str(sorted(set().union(*[set(r) for r in prs])))[:200])
        fids = [p["file_id"] for p in pf if p.get("file_id")]
        if fids:
            img = requests.get(f"{API}/portal/files/{fids[0]}?auth={ptok}", timeout=20)
            check("foto portal bisa dirender (200 image)",
                  img.status_code == 200 and img.headers.get("content-type", "").startswith("image/"),
                  f"{img.status_code}")
        bogus = requests.get(f"{API}/portal/files/tidak-ada-id?auth={ptok}", timeout=20)
        check("berkas asing ditolak 404 (izin diverifikasi nyata)", bogus.status_code == 404)
        staff_try = requests.get(f"{API}/portal/site-plan", headers=h, timeout=20)
        check("token staf tidak bisa dipakai di endpoint portal", staff_try.status_code == 401)

    print("\nG. RBAC resource baru `showroom` (kelola tautan publik)")
    # TEMUAN NYATA: endpoint POST showroom sempat memakai izin `projects.update` sehingga
    # sales_manager/marketing_admin (pemilik proses marketing) mendapat 403. Dijaga di sini.
    expected = {
        "manager": (200, 200),      # sales_manager
        "marketing": (200, 200),    # marketing_admin
        "pm": (200, 200),           # project_manager
        "sales": (200, 403),
        "finance": (200, 403),
        "site": (403, 403),         # site_engineer tidak berkepentingan
    }
    for user, (want_get, want_post) in expected.items():
        tk = login(f"{user}@sipro.co.id")
        hh = H(tk)
        pj = requests.get(f"{API}/projects", headers=hh, timeout=15).json().get("data") or [{}]
        p_id = pj[0].get("id")
        g = requests.get(f"{API}/site-plan/{p_id}/showroom", headers=hh, timeout=15).status_code
        p = requests.post(f"{API}/site-plan/{p_id}/showroom", headers=hh, timeout=15,
                          json={"enabled": True, "show_price": True}).status_code
        check(f"{user}: GET showroom {want_get} & POST showroom {want_post}",
              (g, p) == (want_get, want_post), f"dapat ({g}, {p})")

    print("\n" + "=" * 62)
    print(f"HASIL: {ok_count} PASS / {len(fail)} FAIL")
    for f in fail:
        print("  - GAGAL:", f)
    print("=" * 62)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
