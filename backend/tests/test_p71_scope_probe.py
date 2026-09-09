"""Probe T1: apakah counter kode cluster/blok terpisah per proyek/cluster (klaim 'per cluster')."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PASS = "Sipro#2026"
TAG = str(int(time.time()))[-6:]


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "owner@sipro.co.id", "password": PASS}, timeout=30)
    assert r.status_code == 200, r.text
    ses = requests.Session()
    ses.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return ses


def test_block_and_cluster_scope(s):
    codes = {}
    for i in (1, 2):
        proj = s.post(f"{BASE_URL}/api/projects",
                      json={"name": f"Uji Skop {TAG}-{i}", "code": ""}).json()["data"]
        cl = s.post(f"{BASE_URL}/api/masterplan/projects/{proj['id']}/clusters",
                    json={"code": "", "name": f"Cluster Uji Skop {i}"}).json()["data"]
        blks = []
        for _ in range(2):
            blks.append(s.post(f"{BASE_URL}/api/masterplan/clusters/{cl['id']}/blocks",
                               json={"code": ""}).json()["data"]["code"])
        codes[i] = {"project": proj["code"], "cluster": cl["code"], "blocks": blks}
    print("HASIL SKOP:", codes)
    assert codes[1]["blocks"][0] == "A" and codes[2]["blocks"][0] == "A", \
        f"blok pertama tiap cluster harus 'A' (bawaan per cluster), dapat {codes}"
    assert codes[1]["cluster"] == codes[2]["cluster"] == "C01", \
        f"cluster pertama tiap proyek harus C01, dapat {codes}"
