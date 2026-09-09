#!/usr/bin/env python3
"""ui_audit_dialogs.py — AUDIT VISUAL DI DALAM DIALOG (alat bantu, bukan gate).

Kenapa perlu skrip terpisah: `ui_audit_shots.py` dan `ui_audit_tabs.py` hanya mengukur
halaman pada keadaan awal. Padahal keluhan nyata pemakai ("tidak ada background",
"kartu rusak", "kotak isian tidak kelihatan") paling banyak terjadi DI DALAM DIALOG —
tempat field bertumpuk di atas panel berwarna, dan tempat tombol simpan bisa terdorong
keluar layar sehingga formulir tidak bisa diselesaikan sama sekali.

Untuk setiap halaman: masuk sebagai satu peran, cari tombol yang membuka dialog
(berdasarkan kata kerja pada labelnya), klik satu per satu, lalu ukur FAKTA di dalam dialog:

  D1  panel berbingkai/berbayang TANPA warna latar  -> "kartu rusak" versi dialog
  D2  field (input/textarea/pemilih) TANPA latar sendiri -> keluhan "tidak ada background"
  D3  dialog terpotong: tombol aksi terakhir berada di luar layar / tidak bisa digulir
  D4  teks tidak muat (terpotong) di dalam dialog
  D5  field tanpa label/aria-label/placeholder (tidak jelas & tidak bisa diuji)
  D6  kontras teks sangat rendah (< 3:1) terhadap latar efektifnya

Hasil: /app/ui_audit/report_dialogs_<peran>.json + tangkapan layar tiap dialog di
/app/ui_audit/dialogs/<peran>/. Jalankan:

    python3 scripts/ui_audit_dialogs.py [peran] [--pages beranda,lead] [--max 6]
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_audit_shots import PAGES, ROLES  # noqa: E402

BASE = os.environ.get("SIPRO_UI_BASE", "http://localhost:3000")
CHROME = "/usr/bin/google-chrome"
OUT = Path("/app/ui_audit")
PW = "Sipro#2026"

# Kata kerja pembuka dialog pada label tombol. Sengaja kata kerja (bukan testid) supaya
# tombol yang lupa diberi testid pun tetap ikut diaudit.
TRIGGER_WORDS = (
    "tambah", "buat", "baru", "ajukan", "kalibrasi", "atur", "ubah", "edit", "jadwalkan",
    "geser", "bayar", "catat", "unggah", "kirim", "pengaturan", "terbitkan", "impor",
    "setel", "tutup buku", "verifikasi", "balas", "proses", "alokasi", "posting",
    "daftarkan", "tandai", "selesaikan", "tolak", "setujui", "hitung", "pilih tanggal",
)
SKIP_WORDS = ("keluar", "logout", "hapus semua", "unduh", "ekspor", "cetak", "muat ulang")

FIND_TRIGGERS = """
({ words, skips }) => {
  const btns = Array.from(document.querySelectorAll('button:not([disabled])'));
  const out = [];
  btns.forEach((b, i) => {
    const t = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
    if (!t || t.length > 48) return;
    if (skips.some((s) => t.includes(s))) return;
    if (!words.some((w) => t.includes(w))) return;
    const r = b.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return;
    out.push({ i, label: t.slice(0, 40), testid: b.getAttribute('data-testid') || '' });
  });
  return out;
}
"""

DIALOG_PROBE = """
() => {
  const dlg = document.querySelector('[role="dialog"], [role="alertdialog"]');
  if (!dlg) return null;
  const isTr = (c) => !c || c === 'transparent' || c === 'rgba(0, 0, 0, 0)'
    || /rgba\\(\\s*\\d+,\\s*\\d+,\\s*\\d+,\\s*0\\s*\\)/.test(c);
  const rgb = (c) => {
    const m = String(c).match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x));
    if (p.length > 3 && p[3] === 0) return null;
    return p.slice(0, 3);
  };
  const lum = (p) => {
    const f = p.map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  };
  const effBg = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = getComputedStyle(n).backgroundColor;
      const p = rgb(c);
      if (p) return p;
      n = n.parentElement;
    }
    return [255, 255, 255];
  };
  const ratio = (a, b) => {
    const l1 = lum(a); const l2 = lum(b);
    const hi = Math.max(l1, l2); const lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  };

  const out = { panels: [], fields: [], textOverflow: [], lowContrast: [], cut: null,
                title: (dlg.querySelector('h2, [id$="title"]') || {}).innerText || '' };
  const dr = dlg.getBoundingClientRect();
  out.rect = { top: Math.round(dr.top), bottom: Math.round(dr.bottom),
               h: Math.round(dr.height), vh: window.innerHeight };
  const dcs = getComputedStyle(dlg);
  out.dialogBg = dcs.backgroundColor;

  // D1: panel di dalam dialog yang berbingkai/berbayang tetapi tanpa latar sendiri.
  for (const el of Array.from(dlg.querySelectorAll('div, section, ul, table'))) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 120 || r.height < 36) continue;
    const bordered = parseFloat(cs.borderTopWidth) > 0 || parseFloat(cs.borderBottomWidth) > 0;
    const rounded = parseFloat(cs.borderTopLeftRadius) > 4;
    const shadow = cs.boxShadow && cs.boxShadow !== 'none';
    if (((bordered && rounded) || shadow) && isTr(cs.backgroundColor)) {
      out.panels.push({ cls: String(el.className || '').slice(0, 130),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 60) });
    }
  }

  // D2 + D5: setiap kotak isian.
  const fieldSel = 'input:not([type=hidden]), textarea, select, [role="combobox"]';
  for (const el of Array.from(dlg.querySelectorAll(fieldSel))) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 12) continue;
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['checkbox', 'radio', 'range', 'file'].includes(type)) continue;
    const id = el.getAttribute('id');
    // Pemilih shadcn adalah <button role=combobox>: bila sudah menampilkan teks pilihan
    // (atau placeholder) maka pemakai TAHU isian apa itu — jangan dilaporkan sebagai
    // "tanpa label" hanya karena tidak ada atribut. Yang dikejar temuan ini adalah kotak
    // isian yang benar-benar bisu.
    const role = el.getAttribute('role') || '';
    const shownText = (el.innerText || '').trim();
    const labelled = !!(el.getAttribute('aria-label') || el.getAttribute('placeholder')
      || el.getAttribute('aria-labelledby')
      || (id && document.querySelector(`label[for="${id}"]`))
      || (el.closest('label'))
      || (role === 'combobox' && shownText.length > 0));
    const rec = { tag: el.tagName, type, bg: cs.backgroundColor,
                  cls: String(el.className || '').slice(0, 110),
                  name: el.getAttribute('name') || el.getAttribute('data-testid') || '',
                  transparent: isTr(cs.backgroundColor), labelled };
    if (rec.transparent || !labelled) out.fields.push(rec);
  }

  // D3: apakah tombol aksi terakhir masih terjangkau?
  const btns = Array.from(dlg.querySelectorAll('button')).filter((b) => {
    const r = b.getBoundingClientRect();
    return r.width > 40 && r.height > 20;
  });
  const last = btns[btns.length - 1];
  const scrollable = dlg.scrollHeight > dlg.clientHeight + 2;
  const canScroll = ['auto', 'scroll'].includes(dcs.overflowY);
  out.cut = {
    tallerThanViewport: dr.height > window.innerHeight + 2,
    outsideViewport: dr.bottom > window.innerHeight + 2 || dr.top < -2,
    scrollable, canScroll,
    lastButton: last ? { text: (last.innerText || '').slice(0, 30),
                         bottom: Math.round(last.getBoundingClientRect().bottom),
                         visible: last.getBoundingClientRect().bottom
                           <= window.innerHeight + 2 } : null,
  };

  // D4 + D6
  for (const el of Array.from(dlg.querySelectorAll('p, span, h2, h3, label, td, th, div'))) {
    if (el.children.length) continue;
    const t = (el.textContent || '').trim();
    if (!t || t.length < 4) continue;
    if (el.clientWidth >= 40 && el.scrollWidth > el.clientWidth + 1) {
      const cs2 = getComputedStyle(el);
      out.textOverflow.push({ text: t.slice(0, 40),
                              clipped: cs2.overflowX === 'hidden'
                                || cs2.textOverflow === 'ellipsis' });
    }
    const fg = rgb(getComputedStyle(el).color);
    if (fg) {
      const cr = ratio(fg, effBg(el));
      if (cr < 3) out.lowContrast.push({ text: t.slice(0, 40), ratio: Math.round(cr * 10) / 10 });
    }
  }
  return out;
}
"""


def _findings(probe: dict) -> list:
    """Terjemahkan hasil ukur menjadi temuan yang bisa ditindak (tanpa menghakimi)."""
    f = []
    for p in probe["panels"]:
        f.append(f"D1 panel tanpa latar ({p['w']}x{p['h']}) cls='{p['cls'][:70]}' "
                 f"teks='{p['text'][:40]}'")
    for x in probe["fields"]:
        if x["transparent"]:
            f.append(f"D2 field tanpa latar {x['tag']}/{x['type']} name='{x['name']}' "
                     f"bg={x['bg']}")
        if not x["labelled"]:
            f.append(f"D5 field tanpa label/placeholder {x['tag']}/{x['type']} "
                     f"name='{x['name']}'")
    c = probe["cut"] or {}
    reachable = bool(c.get("scrollable") and c.get("canScroll"))
    # Tombol di bawah garis lipat BUKAN cacat bila panelnya memang bisa digulir — itu
    # kelakuan normal panel samping yang isinya panjang. Yang benar-benar merusak adalah
    # tombol yang tidak bisa dijangkau dengan cara apa pun.
    if c.get("lastButton") and not c["lastButton"]["visible"] and not reachable:
        f.append(f"D3 tombol terakhir '{c['lastButton']['text']}' tidak terjangkau "
                 f"(bottom={c['lastButton']['bottom']} vh={probe['rect']['vh']}, "
                 f"panel tidak bisa digulir)")
    if c.get("tallerThanViewport") and not c.get("canScroll"):
        f.append("D3 dialog lebih tinggi dari layar dan tidak bisa digulir")
    for t in probe["textOverflow"]:
        if not t["clipped"]:
            f.append(f"D4 teks meluber tanpa elipsis: '{t['text']}'")
    for t in probe["lowContrast"][:6]:
        f.append(f"D6 kontras rendah {t['ratio']}:1 pada '{t['text']}'")
    return f


async def audit(role: str, pages: list, per_page: int):
    email = ROLES[role]
    vw_tag = os.environ.get("SIPRO_UI_WIDTH", "1440")
    shots = OUT / "dialogs" / f"{role}_{vw_tag}"
    shots.mkdir(parents=True, exist_ok=True)
    report = {"role": role, "base": BASE, "dialogs": [], "pages_scanned": 0}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME,
                                          args=["--no-sandbox", "--disable-dev-shm-usage"])
        # SIPRO_UI_WIDTH=390 untuk sapuan ponsel (matriks visual per perangkat)
        vw = int(os.environ.get("SIPRO_UI_WIDTH", "1440"))
        ctx = await browser.new_context(viewport={"width": vw, "height": 900 if vw > 600 else 844},
                                        is_mobile=vw <= 600, has_touch=vw <= 600)
        page = await ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text[:140]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR {str(e)[:140]}"))
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await page.fill("[data-testid=login-email-input]", email)
        await page.fill("[data-testid=login-password-input]", PW)
        await page.click("[data-testid=login-submit-button]")
        await page.wait_for_timeout(5000)

        for name, path in pages:
            try:
                await page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
                await page.wait_for_timeout(3800)
            except Exception as e:  # noqa: BLE001
                print(f"  {name:20s} GAGAL buka: {str(e)[:80]}")
                continue
            report["pages_scanned"] += 1
            trig = await page.evaluate(FIND_TRIGGERS,
                                       {"words": list(TRIGGER_WORDS),
                                        "skips": list(SKIP_WORDS)})
            opened = 0
            for t in trig:
                if opened >= per_page:
                    break
                errors.clear()
                try:
                    btns = page.locator("button:not([disabled])")
                    await btns.nth(t["i"]).click(force=True, timeout=4000)
                    await page.wait_for_timeout(1600)
                    probe = await page.evaluate(DIALOG_PROBE)
                    if not probe:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(400)
                        continue
                    opened += 1
                    slug = f"{name}_{opened}_{t['label'][:18].replace(' ', '-')}"
                    shot = shots / f"{slug}.png"
                    await page.screenshot(path=str(shot))
                    fnd = _findings(probe)
                    report["dialogs"].append({
                        "page": name, "path": path, "trigger": t["label"],
                        "testid": t["testid"], "title": probe["title"][:80],
                        "dialog_bg": probe["dialogBg"], "rect": probe["rect"],
                        "findings": fnd, "console_errors": sorted(set(errors))[:4],
                        "shot": str(shot),
                    })
                    mark = "OK " if not fnd else f"{len(fnd)} temuan"
                    print(f"  {name:18s} [{t['label'][:24]:24s}] {mark}")
                    for line in fnd[:4]:
                        print(f"      - {line}")
                except Exception as e:  # noqa: BLE001
                    print(f"  {name:18s} [{t['label'][:24]:24s}] gagal klik: {str(e)[:60]}")
                finally:
                    for _ in range(2):
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(250)
        await browser.close()

    (OUT / f"report_dialogs_{role}_{vw_tag}.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False))
    tot = sum(len(d["findings"]) for d in report["dialogs"])
    bad = len([d for d in report["dialogs"] if d["findings"]])
    print(f"\nRINGKAS dialog {role}: {len(report['dialogs'])} dialog dibuka di "
          f"{report['pages_scanned']} halaman; {bad} dialog bermasalah; {tot} temuan.")
    print(f"laporan: {OUT}/report_dialogs_{role}.json")


def main():
    role = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "owner"
    pages = PAGES
    if "--pages" in sys.argv:
        want = set(sys.argv[sys.argv.index("--pages") + 1].split(","))
        pages = [p for p in PAGES if p[0] in want]
    per_page = 6
    if "--max" in sys.argv:
        per_page = int(sys.argv[sys.argv.index("--max") + 1])
    asyncio.run(audit(role, pages, per_page))


if __name__ == "__main__":
    main()
