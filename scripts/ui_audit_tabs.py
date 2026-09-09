#!/usr/bin/env python3
"""ui_audit_tabs.py — AUDIT VISUAL TIAP TAB (bukan hanya tab pertama).

Sebagian besar isi SIPRO tinggal di dalam tab (Progres & Mutu punya 7 tab, Keuangan 8,
Laporan Keuangan 6, dst). Audit halaman saja akan melewatkan cacat tampilan di sana.

Untuk setiap halaman: masuk, klik SETIAP `[role="tab"]` satu per satu, lalu ukur fakta yang
sama seperti `ui_audit_shots.py` (kartu berbingkai tanpa latar, teks yang tidak muat/terpotong,
error konsol) dan simpan tangkapan layarnya.

Jalankan: python3 scripts/ui_audit_tabs.py [peran]
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_audit_shots import PROBE, ROLES  # noqa: E402

BASE = os.environ.get("SIPRO_UI_BASE", "http://localhost:3000")
CHROME = "/usr/bin/google-chrome"
OUT = Path("/app/ui_audit")
PW = "Sipro#2026"
PAGES = [
    ("konstruksi", "/construction"), ("keuangan", "/finance"),
    ("laporan-akuntansi", "/accounting/reports"), ("akuntansi", "/accounting"),
    ("material", "/materials"), ("boq", "/boq"), ("subkon", "/subcon"),
    ("pengadaan", "/procurement"), ("pajak", "/tax"), ("aset", "/fixed-assets"),
    ("pembiayaan", "/corporate-financing"), ("marketing-fee", "/marketing-fee"),
    ("lapangan", "/field"), ("tugas", "/tasks"), ("lead", "/leads"),
    ("deal", "/deals"), ("siteplan", "/site-plan"), ("admin-master", "/admin/master-data"),
    ("kalibrasi", "/build-calibration"), ("komplain", "/complaints"),
]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "tab").lower()).strip("-")[:28] or "tab"


async def run(role: str, width: int = 1440):
    email = ROLES[role]
    outdir = OUT / f"{role}_tabs"
    outdir.mkdir(parents=True, exist_ok=True)
    findings = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME,
                                          args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width": width, "height": 1000})
        page = await ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text[:150]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR {str(e)[:150]}"))
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await page.fill("[data-testid=login-email-input]", email)
        await page.fill("[data-testid=login-password-input]", PW)
        await page.click("[data-testid=login-submit-button]")
        await page.wait_for_timeout(5000)

        for name, path in PAGES:
            await page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
            await page.wait_for_timeout(3500)
            tabs = await page.query_selector_all('[role="tab"]')
            labels = []
            for t in tabs:
                labels.append(((await t.inner_text()) or "").strip().split("\n")[0])
            print(f"\n{name} ({len(tabs)} tab): {labels}")
            for i, label in enumerate(labels):
                errors.clear()
                try:
                    tabs = await page.query_selector_all('[role="tab"]')
                    if i >= len(tabs):
                        break
                    await tabs[i].click()
                    await page.wait_for_timeout(3200)
                    probe = await page.evaluate(PROBE)
                    shot = outdir / f"{name}__{i}-{slug(label)}.png"
                    await page.screenshot(path=str(shot), full_page=True)
                    findings.append({
                        "page": name, "tab": label, "shot": str(shot),
                        "broken_cards": probe["brokenCards"][:8],
                        "broken_count": probe["counts"]["brokenCards"],
                        "text_overflow": probe["textOverflow"][:14],
                        "text_overflow_count": probe["counts"]["textOverflow"],
                        "page_overflow": probe["overflow"],
                        "console_errors": sorted(set(errors))[:5],
                    })
                    print(f"   {label[:26]:26s} kartu-tanpa-latar={probe['counts']['brokenCards']:3d}"
                          f" teks-tak-muat={probe['counts']['textOverflow']:3d}"
                          f" overflow={probe['overflow']} err={len(set(errors))}")
                except Exception as e:  # noqa: BLE001
                    print(f"   {label[:26]:26s} GAGAL {str(e)[:90]}")
        await browser.close()
    (OUT / f"report_{role}_tabs.json").write_text(
        json.dumps(findings, indent=1, ensure_ascii=False))
    print(f"\nRINGKAS: {sum(f['broken_count'] for f in findings)} kartu tanpa latar, "
          f"{sum(f['text_overflow_count'] for f in findings)} teks tidak muat pada "
          f"{len(findings)} tab. Laporan: {OUT}/report_{role}_tabs.json")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "owner"))
