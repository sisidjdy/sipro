"""meta_api — SATU konstanta versi Graph API untuk semua modul Meta (WA Cloud, CAPI, Ads).

Versi terpasang: v26.0 (rilis 29 Jul 2026, kedaluwarsa ±21 Jul 2028 — Meta menjamin ≥2 tahun).
Naikkan lewat env `META_GRAPH_VERSION` tanpa ubah kode. Jangan tulis literal versi di berkas lain
(dijaga gate `scripts/verify_auth_surface.py`).
"""
import os

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v26.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
