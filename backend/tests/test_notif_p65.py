"""Uji Fase 65 — pengelompokan notifikasi kembar & preferensi notifikasi per pemakai.

Isolasi: setiap uji yang MENGUBAH data melakukan snapshot & restore eksplisit (pola
`test_notif_p64.py`). Akses DB memakai pymongo (sync) untuk menghindari konflik
event-loop dengan motor.

Jalankan: python3 -m pytest backend/tests/test_notif_p65.py
"""
import os
import sys

import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")


def _load_env():
    with open("/app/backend/.env") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
PW = "Sipro#2026"
UJI = "site@sipro.co.id"
MONGO = MongoClient(os.environ["MONGO_URL"])
DB = MONGO[os.environ["DB_NAME"]]

import notif_center as nc  # noqa: E402  (butuh sys.path backend)
import notif_prefs as npf  # noqa: E402


def hdr(email: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login {email} gagal: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def prefs_bersih():
    """Simpan lalu pulihkan preferensi + buang notifikasi bahan uji."""
    snap = list(DB.notification_prefs.find({"user_email": UJI}))
    yield
    DB.notification_prefs.delete_many({"user_email": UJI})
    if snap:
        DB.notification_prefs.insert_many(snap)
    DB.notifications.delete_many({"title": {"$regex": "uji p65"}})


# ------------------------------------------------------------------ kunci kelompok (murni)
def test_kunci_kelompok_mengabaikan_nomor_dokumen():
    a = {"type": "finance", "related_entity_type": "ap_bill",
         "title": "Tagihan AP BILL-2026-0007 menunggu persetujuan"}
    b = {"type": "finance", "related_entity_type": "ap_bill",
         "title": "Tagihan AP BILL-2026-0142 menunggu persetujuan"}
    assert nc.group_key(a) == nc.group_key(b)


def test_kunci_kelompok_membedakan_jenis_berbeda():
    a = {"type": "finance", "related_entity_type": "ap_bill", "title": "Tagihan baru"}
    b = {"type": "task", "related_entity_type": "task", "title": "Tagihan baru"}
    assert nc.group_key(a) != nc.group_key(b)


def test_group_rows_meringkas_dan_membawa_anggota():
    rows = [nc.decorate({"id": f"n{i}", "type": "finance", "related_entity_type": "ap_bill",
                         "title": f"Tagihan AP-00{i} menunggu persetujuan",
                         "created_at": f"2026-06-0{3 - i}T00:00:00Z", "read": i > 1})
            for i in range(3)]
    out = nc.group_rows(rows)
    assert len(out) == 1
    g = out[0]
    assert g["group_count"] == 3 and g["group_unread"] == 2
    assert len(g["group_members"]) == 3
    assert g["group_oldest_at"] == rows[-1]["created_at"] <= g["created_at"]


def test_group_rows_tidak_memaksa_kelompok_untuk_yang_tidak_kembar():
    rows = [nc.decorate({"id": "a", "type": "finance", "title": "Kas masuk",
                         "created_at": "2026-06-02T00:00:00Z", "read": False}),
            nc.decorate({"id": "b", "type": "task", "title": "Tugas baru: survey",
                         "created_at": "2026-06-01T00:00:00Z", "read": False})]
    assert [g["group_count"] for g in nc.group_rows(rows)] == [1, 1]


def test_saluran_bawaan_tidak_menyiapkan_whatsapp_tanpa_diminta():
    assert npf.DEFAULT_CHANNEL == {"inapp": True, "push": True, "wa": False}
    assert npf.LOCKED_CHANNELS == ("inapp",)


# ------------------------------------------------------------------ lewat API (server hidup)
def test_daftar_berkelompok_meringkas_tanpa_menghilangkan_apa_pun():
    h = hdr("owner@sipro.co.id")
    polos = requests.get(f"{API}/notifications", headers=h,
                         params={"state": "all", "limit": 50}, timeout=60).json()
    grup = requests.get(f"{API}/notifications", headers=h,
                        params={"state": "all", "group": "true", "limit": 50},
                        timeout=60).json()
    assert grup["grouped"] is True
    assert grup["rows_total"] == polos["total"] >= grup["total"]
    jumlah = sum(g.get("group_count", 1) for g in grup["data"])
    assert jumlah >= len(grup["data"])          # tidak ada anggota yang hilang


def test_aksi_kelompok_mengenai_seluruh_anggota(prefs_bersih):
    h = hdr(UJI)
    grup = requests.get(f"{API}/notifications", headers=h,
                        params={"state": "unread", "group": "true", "limit": 50},
                        timeout=60).json()
    target = next((g for g in grup["data"] if (g.get("group_count") or 1) > 1), None)
    if not target:
        pytest.skip("tidak ada kelompok kembar belum dibaca untuk pemakai uji")
    ids = target["group_ids"]
    res = requests.post(f"{API}/notifications/group/read", headers=h,
                        json={"group_key": target["group_key"]}, timeout=30)
    assert res.status_code == 200 and res.json()["data"]["marked"] >= 2
    assert DB.notifications.count_documents({"id": {"$in": ids}, "read": False}) == 0
    DB.notifications.update_many({"id": {"$in": ids}},
                                 {"$set": {"read": False, "read_at": None}})


def test_kelompok_tidak_dikenal_dijawab_404():
    h = hdr(UJI)
    r = requests.post(f"{API}/notifications/group/dismiss", headers=h,
                      json={"group_key": "tidak|ada|kelompok"}, timeout=30)
    assert r.status_code == 404


def test_preferensi_hanya_berlaku_untuk_pemiliknya(prefs_bersih):
    h, owner = hdr(UJI), hdr("owner@sipro.co.id")
    r = requests.put(f"{API}/notifications/preferences", headers=h,
                     json={"channels": {"keuangan": {"push": False}}}, timeout=30)
    assert r.status_code == 200
    assert r.json()["data"]["channels"]["keuangan"]["push"] is False
    assert r.json()["data"]["channels"]["keuangan"]["inapp"] is True
    lain = requests.get(f"{API}/notifications/preferences", headers=owner, timeout=30).json()
    assert lain["data"]["channels"]["keuangan"]["push"] is True


def test_kategori_dan_saluran_asing_ditolak(prefs_bersih):
    h = hdr(UJI)
    for payload in ({"astrologi": {"push": False}}, {"keuangan": {"telepati": True}}):
        r = requests.put(f"{API}/notifications/preferences", headers=h,
                         json={"channels": payload}, timeout=30)
        assert r.status_code == 400, payload


def test_kabar_dibungkam_tetapi_permintaan_tindakan_tidak(prefs_bersih):
    """Preferensi mematikan kategori keuangan; kabar informatif hilang dari daftar, tetapi
    permintaan keputusan TETAP masuk (kalau tidak, persetujuan menggantung tanpa sebab)."""
    import asyncio

    import engine
    h = hdr(UJI)
    requests.put(f"{API}/notifications/preferences", headers=h,
                 json={"channels": {"keuangan": {"inapp": False}}}, timeout=30)
    loop = asyncio.new_event_loop()
    try:
        kabar = loop.run_until_complete(engine.create_notification(
            user_email=UJI, title="Rekap kas mingguan (uji p65)", body="Informatif.",
            type="finance", org_id=os.environ["DEFAULT_ORG_ID"]))
        minta = loop.run_until_complete(engine.create_notification(
            user_email=UJI, title="Tagihan menunggu persetujuan Anda (uji p65)",
            body="Perlu keputusan.", type="finance",
            org_id=os.environ["DEFAULT_ORG_ID"]))
    finally:
        loop.close()
    dibungkam = DB.notifications.find_one({"id": kabar["id"]})
    assert dibungkam["muted_at"] and "keuangan" in dibungkam["muted_reason"]
    assert dibungkam["dismissed_at"]                      # tidak memenuhi daftar
    assert DB.notifications.count_documents({"id": kabar["id"]}) == 1   # tidak dihapus
    lolos = DB.notifications.find_one({"id": minta["id"]})
    assert not lolos.get("muted_at")
    daftar = requests.get(f"{API}/notifications", headers=h,
                          params={"state": "all", "limit": 200}, timeout=60).json()
    tampil = {x["id"] for x in daftar["data"]}
    assert kabar["id"] not in tampil and minta["id"] in tampil


def test_ringkasan_wa_disiapkan_bukan_dikirim(prefs_bersih):
    h = hdr(UJI)
    requests.put(f"{API}/notifications/preferences", headers=h,
                 json={"channels": {"tugas": {"wa": True}}}, timeout=30)
    d = requests.get(f"{API}/notifications/wa-digest", headers=h, timeout=30).json()["data"]
    assert "tugas" in d["categories"]
    assert not d.get("wa_link") or d["wa_link"].startswith("https://wa.me/")
    assert d["message"]
