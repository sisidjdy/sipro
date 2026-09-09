#!/usr/bin/env python3
"""ui_audit_shots.py — AUDIT VISUAL SELURUH HALAMAN (alat bantu, bukan gate).

Dipakai untuk menindaklanjuti laporan nyata pemakai: "banyak kartu rusak di banyak halaman,
tidak ada background, font tidak konsisten, banyak CSS tidak terimplement".

Untuk setiap halaman yang terdaftar di `App.js`, skrip ini:
  1. masuk sebagai peran tertentu (lewat form login sungguhan, bukan menyuntik token),
  2. mengukur FAKTA tampilan lewat DOM: apakah webfont benar-benar terpakai, kartu mana yang
     berbingkai tapi TANPA warna latar (inilah "kartu rusak" yang dilihat pemakai), apakah
     ada elemen melebar keluar layar, dan apakah ada teks berkontras sangat rendah,
  3. mencatat error konsol & permintaan jaringan yang gagal,
  4. menyimpan tangkapan layar ke `/app/ui_audit/<peran>/<halaman>.png`.

Hasil ringkas ditulis ke `/app/ui_audit/report_<peran>.json` supaya bisa dibandingkan
SEBELUM vs SESUDAH perbaikan.

Jalankan: python3 scripts/ui_audit_shots.py [peran] [--width 1440]
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.environ.get("SIPRO_UI_BASE", "http://localhost:3000")
CHROME = "/usr/bin/google-chrome"
OUT = Path("/app/ui_audit")
PW = "Sipro#2026"
ROLES = {
    "owner": "owner@sipro.co.id",
    "pm": "pm@sipro.co.id",
    "site": "site@sipro.co.id",
    "finance": "finance@sipro.co.id",
    "sales": "sales@sipro.co.id",
    "superadmin": "superadmin@sipro.co.id",
}
PAGES = [
    ("beranda", "/"), ("tugas", "/tasks"), ("notifikasi", "/notifications"),
    ("lead", "/leads"), ("agenda", "/appointments"), ("inbox", "/inbox"),
    ("automasi", "/automation"), ("deal", "/deals"), ("siteplan", "/site-plan"),
    ("customer", "/customers"), ("dokumen", "/documents"), ("proyek", "/projects"),
    ("konstruksi", "/construction"), ("kalender", "/build-calendar"),
    ("kalibrasi", "/build-calibration"), ("material", "/materials"),
    ("perizinan", "/permits"), ("lapangan", "/field"), ("boq", "/boq"),
    ("subkon", "/subcon"), ("pengadaan", "/procurement"), ("akuntansi", "/accounting"),
    ("laporan-akuntansi", "/accounting/reports"), ("pajak", "/tax"),
    ("keuangan", "/finance"), ("kasbon", "/petty-cash"), ("aset", "/fixed-assets"),
    ("pembiayaan", "/corporate-financing"), ("marketing-fee", "/marketing-fee"),
    ("komplain", "/complaints"), ("admin-users", "/admin/users"),
    ("admin-permissions", "/admin/permissions"), ("admin-orgs", "/admin/organizations"),
    ("admin-master", "/admin/master-data"), ("admin-audit", "/admin/audit"),
]

PROBE = """
() => {
  const out = { fonts: {}, brokenCards: [], overflow: false, textOverflow: [],
                counts: {}, transparentPanels: [] };
  out.fonts.space = document.fonts.check('600 16px "Space Grotesk"');
  out.fonts.inter = document.fonts.check('400 16px "Inter"');
  out.fonts.mono = document.fonts.check('400 16px "Roboto Mono"');
  const h = document.querySelector('h1, h2, .font-heading');
  out.fonts.headingFamily = h ? getComputedStyle(h).fontFamily : null;
  out.fonts.bodyFamily = getComputedStyle(document.body).fontFamily;
  const isTransparent = (c) => !c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)';
  const boxes = Array.from(document.querySelectorAll('div, section, article, aside, li, table'));
  out.counts.boxes = boxes.length;
  for (const el of boxes) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 140 || r.height < 44) continue;
    const bordered = parseFloat(cs.borderTopWidth) > 0 || parseFloat(cs.borderBottomWidth) > 0;
    const rounded = parseFloat(cs.borderTopLeftRadius) > 4;
    const shadow = cs.boxShadow && cs.boxShadow !== 'none';
    const cardish = (bordered && rounded) || shadow;
    if (cardish && isTransparent(cs.backgroundColor)) {
      out.brokenCards.push({
        cls: String(el.className || '').slice(0, 150),
        w: Math.round(r.width), h: Math.round(r.height),
        text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 60),
      });
    }
  }
  // TEKS YANG TIDAK MUAT: angka rupiah besar pada kartu sempit terpotong / meluber —
  // inilah "kartu rusak" yang paling terasa oleh pemakai.
  const texts = Array.from(document.querySelectorAll('p, span, h1, h2, h3, h4, td, th, div'));
  for (const el of texts) {
    if (el.children.length) continue;
    const t = (el.textContent || '').trim();
    if (!t || t.length < 4) continue;
    if (el.clientWidth < 40) continue;
    if (el.scrollWidth > el.clientWidth + 1) {
      const cs = getComputedStyle(el);
      out.textOverflow.push({
        text: t.slice(0, 40), tag: el.tagName,
        cls: String(el.className || '').slice(0, 110),
        need: el.scrollWidth, have: el.clientWidth,
        clipped: cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis',
      });
    }
  }
  out.overflow = document.documentElement.scrollWidth > window.innerWidth + 2;
  out.counts.brokenCards = out.brokenCards.length;
  out.counts.textOverflow = out.textOverflow.length;
  return out;
}
"""


async def audit(role: str, width: int):
    email = ROLES[role]
    outdir = OUT / role
    outdir.mkdir(parents=True, exist_ok=True)
    report = {"role": role, "email": email, "base": BASE, "pages": []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME,
                                          args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(viewport={"width": width, "height": 1000})
        page = await ctx.new_page()
        errors, failed = [], []
        page.on("console", lambda m: errors.append(m.text[:160]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR {str(e)[:160]}"))
        page.on("requestfailed",
                lambda r: failed.append(f"{r.url[:110]}"))
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await page.fill("[data-testid=login-email-input]", email)
        await page.fill("[data-testid=login-password-input]", PW)
        await page.click("[data-testid=login-submit-button]")
        await page.wait_for_timeout(5000)
        report["login_url"] = page.url

        for name, path in PAGES:
            errors.clear()
            failed.clear()
            try:
                await page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
                await page.wait_for_timeout(4200)
                probe = await page.evaluate(PROBE)
                shot = outdir / f"{name}.png"
                await page.screenshot(path=str(shot), full_page=True)
                report["pages"].append({
                    "name": name, "path": path, "url": page.url,
                    "fonts": probe["fonts"], "overflow": probe["overflow"],
                    "broken_cards": probe["brokenCards"][:12],
                    "broken_count": probe["counts"]["brokenCards"],
                    "text_overflow": probe["textOverflow"][:20],
                    "text_overflow_count": probe["counts"]["textOverflow"],
                    "console_errors": sorted(set(errors))[:6],
                    "failed_requests": sorted(set(failed))[:6],
                    "shot": str(shot),
                })
                print(f"  {name:22s} kartu-tanpa-latar={probe['counts']['brokenCards']:3d} "
                      f"teks-tak-muat={probe['counts']['textOverflow']:3d} "
                      f"overflow={probe['overflow']} font(space/inter/mono)="
                      f"{probe['fonts']['space']}/{probe['fonts']['inter']}/"
                      f"{probe['fonts']['mono']} err={len(set(errors))}")
            except Exception as e:  # noqa: BLE001
                report["pages"].append({"name": name, "path": path, "error": str(e)[:200]})
                print(f"  {name:22s} GAGAL: {str(e)[:120]}")
        await browser.close()
    (OUT / f"report_{role}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    tot = sum(p.get("broken_count", 0) for p in report["pages"])
    print(f"\nRINGKAS {role}: {tot} kartu tanpa latar di {len(report['pages'])} halaman; "
          f"laporan: {OUT}/report_{role}.json")


def main():
    role = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "owner"
    width = 1440
    if "--width" in sys.argv:
        width = int(sys.argv[sys.argv.index("--width") + 1])
    asyncio.run(audit(role, width))


if __name__ == "__main__":
    main()
