"""target_engine.py — Fase 45: matematika TARGET proyek (`docs/v2/32` §2). FUNGSI MURNI.

Kenapa modul ini tidak menyentuh database sama sekali: bagian yang paling mudah salah pada
"target dinamis" bukan penyimpanannya, tetapi ARITMATIKANYA — dan aritmatika yang tidak bisa
diuji tanpa database praktis tidak pernah diuji. Semua fungsi di sini menerima angka dan
mengembalikan angka, sehingga `poc/poc_45.py` + gate bisa membuktikan lima janji berikut:

  1. **keep_total**: `Σ realisasi periode lampau + Σ rencana periode berjalan-ke-depan`
     PERSIS sama dengan total target. Pembulatan tidak boleh membuat target bocor.
  2. **lock_past**: rencana periode lampau TIDAK PERNAH berubah saat target dihitung ulang —
     kalau berubah, laporan historis ikut berubah diam-diam dan tidak ada yang bisa
     dipertanggungjawabkan.
  3. **carry_over yang bisa dijelaskan**: kekurangan periode lampau ditulis sebagai angka
     pada periode berikutnya, sehingga "kok target bulan ini naik?" punya jawaban, bukan
     kesan sistem mengarang.
  4. **0 ≠ belum ada data**: metode yang butuh bahan (bobot kurva-S, harga rata-rata,
     riwayat kecepatan jual) MENOLAK menghitung dan menyebut apa yang kurang, bukan
     mengirim rencana 0 unit yang terlihat sah.
  5. **cakupan berjenjang**: total target anak (cluster/sales) tidak boleh melewati induk.

Istilah: `period` = bulan dalam format `YYYY-MM` (bukan tanggal), karena semua janji target
di dokumen owner bersifat bulanan.
"""
import math
import re

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
METHODS = ("linear_remaining", "s_curve", "manual", "velocity_forecast", "revenue_first")
# Rumus ditulis di SATU tempat dan dikirim ke layar, supaya penjelasan di UI tidak bisa
# berbeda dengan yang benar-benar dijalankan.
METHOD_FORMULA = {
    "linear_remaining": "rencana_bulan = sisa_unit / sisa_bulan (dibagi rata, sisa pembagian "
                        "ditaruh di bulan-bulan terdepan)",
    "s_curve": "rencana_bulan = sisa_unit × (bobot_bulan / Σ bobot bulan tersisa)",
    "manual": "rencana_bulan = angka yang diisi pemakai; sistem menghitung deviasi Σ vs total",
    "velocity_forecast": "kecepatan = median(realisasi 3 bulan terakhir) × (1 + pertumbuhan); "
                         "rencana_bulan = kecepatan, proyeksi habis = sisa / kecepatan",
    "revenue_first": "rencana_pendapatan_bulan = sisa_pendapatan / sisa_bulan; "
                     "rencana_unit = rencana_pendapatan_bulan / harga_rata_rata",
}


# --------------------------------------------------------------------- kalender bulan
def valid_period(period: str) -> bool:
    return bool(period and MONTH_RE.match(str(period)))


def month_add(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_diff(a: str, b: str) -> int:
    """Jumlah bulan dari `a` ke `b` (bisa negatif)."""
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def month_list(start: str, end: str) -> list:
    if not (valid_period(start) and valid_period(end)) or month_diff(start, end) < 0:
        return []
    return [month_add(start, i) for i in range(month_diff(start, end) + 1)]


# --------------------------------------------------------------------- pembagian eksak
def distribute(total: int, count: int, weights: list = None) -> list:
    """Bagi `total` ke `count` bagian sehingga Σ bagian PERSIS `total`.

    Pembulatan adalah tempat target biasanya "bocor" beberapa unit: kalau tiap bulan
    dibulatkan sendiri-sendiri, jumlahnya tidak lagi sama dengan target dan tidak ada yang
    sadar. Di sini sisa pembagian dibagikan secara deterministik (bulan terdepan lebih dulu
    untuk bobot rata; sisa terbesar lebih dulu untuk bobot kurva-S).
    """
    total = int(total or 0)
    if count <= 0:
        return []
    if not weights:
        base, rem = divmod(total, count)
        return [base + (1 if i < rem else 0) for i in range(count)]
    wsum = float(sum(max(0.0, float(w or 0)) for w in weights))
    if wsum <= 0:
        return distribute(total, count)
    raw = [total * max(0.0, float(w or 0)) / wsum for w in weights]
    out = [int(math.floor(v)) for v in raw]
    rem = total - sum(out)
    order = sorted(range(count), key=lambda i: (-(raw[i] - out[i]), i))
    for i in range(rem):
        out[order[i % count]] += 1
    return out


def median(values: list):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def _period_row(period: str, **kw) -> dict:
    row = {"period": period, "unit_plan": None, "revenue_plan": None,
           "unit_actual": 0, "revenue_actual": 0, "locked": False, "carry_over": 0,
           "note": None}
    row.update(kw)
    return row


# --------------------------------------------------------------------- inti perhitungan
def _baseline_plan(method: str, months: list, unit_target: int, weights: dict,
                   manual: dict) -> dict:
    """Rencana AWAL seluruh horizon — dipakai mengisi periode lampau saat target dibuat
    di tengah jalan.

    Kenapa periode lampau tidak dibiarkan kosong: tanpa rencana lampau, `carry_over` mustahil
    dihitung (tidak ada pembanding), sehingga kenaikan target bulan berjalan kembali menjadi
    misteri. Rencana lampau ini langsung DIKUNCI: ia catatan sejarah, bukan janji yang masih
    bisa diubah.
    """
    if method == "manual":
        return {m: int(manual.get(m) or 0) for m in months}
    if method == "s_curve" and any(float(weights.get(m) or 0) for m in months):
        vals = distribute(int(unit_target or 0), len(months),
                          [float(weights.get(m) or 0) for m in months])
    else:
        vals = distribute(int(unit_target or 0), len(months))
    return dict(zip(months, vals))


def compute_periods(*, method: str, months: list, unit_target: int = 0,
                    revenue_target: int = 0, avg_price: int = 0, actuals: dict = None,
                    existing: dict = None, weights: dict = None, manual: dict = None,
                    growth_pct: float = 0, today: str = None, lock_past: bool = True,
                    keep_total: bool = True) -> dict:
    """Hitung rencana per bulan untuk satu target.

    Argumen yang penting dimengerti:
      * `actuals`  : `{period: {"unit": n, "revenue": rp}}` — realisasi NYATA dari penjualan.
                     Ini datang dari metrik penjualan, BUKAN diinput ulang oleh pemakai.
      * `existing` : `{period: {"unit_plan":…, "revenue_plan":…, "locked":bool}}` — rencana
                     yang sudah tersimpan. Dipakai untuk menghormati `lock_past`.
      * `today`    : bulan berjalan (`YYYY-MM`). Bulan SEBELUM ini disebut "lampau".

    Hasil: `{periods, totals, warnings, missing, projection, formula}`.
    `missing` yang tidak kosong berarti rencana TIDAK BISA dihitung — periode tetap dikirim
    dengan `unit_plan = None` supaya layar menulis "belum bisa dihitung", bukan 0.
    """
    actuals = actuals or {}
    existing = existing or {}
    weights = weights or {}
    manual = manual or {}
    warnings, missing = [], []
    if method not in METHODS:
        return {"periods": [], "totals": {}, "warnings": [],
                "missing": [f"metode target '{method}' tidak dikenal"],
                "projection": None, "formula": None}
    if not months:
        return {"periods": [], "totals": {}, "warnings": [],
                "missing": ["horizon target belum diisi (bulan mulai & selesai)"],
                "projection": None, "formula": METHOD_FORMULA[method]}
    today = today if valid_period(today) else months[0]

    past = [m for m in months if m < today]
    future = [m for m in months if m >= today]
    baseline = _baseline_plan(method, months, unit_target, weights, manual)
    rows = {}
    for m in months:
        act = actuals.get(m) or {}
        prev = existing.get(m) or {}
        is_past = m in past
        # Periode lampau: pakai rencana yang SUDAH tersimpan bila ada (itulah inti `lock_past`);
        # bila target baru dibuat di tengah horizon, isi dengan rencana awal merata/berbobot
        # supaya `carry_over` punya pembanding. Keduanya ditandai terkunci.
        if is_past:
            plan = prev.get("unit_plan")
            from_baseline = plan is None
            if from_baseline:
                plan = baseline.get(m)
            rows[m] = _period_row(
                m, unit_actual=int(act.get("unit") or 0),
                revenue_actual=int(act.get("revenue") or 0), locked=bool(lock_past),
                unit_plan=plan,
                revenue_plan=(prev.get("revenue_plan") if not from_baseline else
                              (int(plan) * int(avg_price) if plan is not None
                               and int(avg_price or 0) else None)),
                note=("rencana awal periode lampau (dikunci)" if from_baseline
                      else "periode lampau dikunci") if lock_past else None)
            continue
        rows[m] = _period_row(
            m, unit_actual=int(act.get("unit") or 0),
            revenue_actual=int(act.get("revenue") or 0))

    unit_actual_past = sum(rows[m]["unit_actual"] for m in past)
    revenue_actual_past = sum(rows[m]["revenue_actual"] for m in past)
    plan_past = sum(int(rows[m]["unit_plan"] or 0) for m in past)
    carry_over = max(0, plan_past - unit_actual_past)

    if not future:
        warnings.append("Horizon target sudah lewat — tidak ada bulan yang bisa direncanakan "
                        "lagi. Perpanjang horizon atau tutup target ini.")
        return _wrap(method, months, rows, unit_target, revenue_target, unit_actual_past,
                     revenue_actual_past, warnings, missing, None, keep_total)

    # Sisa yang harus dikejar. Periode lampau yang belum tercapai TIDAK hilang: ia masuk ke
    # sisa, dan itulah sebabnya target bulan berjalan bisa naik (dijelaskan via carry_over).
    remaining_unit = int(unit_target or 0) - unit_actual_past
    remaining_revenue = int(revenue_target or 0) - revenue_actual_past
    achieved = remaining_unit <= 0 and (method != "revenue_first" or remaining_revenue <= 0)

    # -------------------------------------------------------------- per metode
    if achieved:
        for m in future:
            rows[m]["unit_plan"] = 0
            rows[m]["revenue_plan"] = 0
            rows[m]["note"] = "target sudah tercapai dari realisasi periode sebelumnya"
        warnings.append("Target sudah tercapai — rencana bulan berikutnya 0 karena realisasi "
                        "sudah melewati total target (ini nol yang benar, bukan data kosong).")
    elif method == "linear_remaining":
        for m, val in zip(future, distribute(max(0, remaining_unit), len(future))):
            rows[m]["unit_plan"] = val
    elif method == "s_curve":
        wl = [float(weights.get(m) or 0) for m in future]
        total_w = sum(float(weights.get(m) or 0) for m in months)
        if sum(wl) <= 0:
            missing.append("bobot kurva-S belum diisi untuk bulan-bulan tersisa "
                           "(Σ bobot bulan tersisa masih 0)")
        else:
            if abs(total_w - 100) > 0.5:
                warnings.append(f"Σ bobot seluruh horizon {round(total_w, 2)}% (idealnya 100%). "
                                "Rencana dihitung proporsional atas bobot bulan tersisa.")
            for m, val in zip(future, distribute(max(0, remaining_unit), len(future), wl)):
                rows[m]["unit_plan"] = val
    elif method == "manual":
        filled = [m for m in future if manual.get(m) is not None]
        if not filled:
            missing.append("angka manual per bulan belum diisi")
        else:
            for m in future:
                rows[m]["unit_plan"] = int(manual.get(m) or 0)
            total_manual = sum(int(manual.get(m) or 0) for m in future)
            dev = total_manual + unit_actual_past - int(unit_target or 0)
            if dev:
                warnings.append(
                    f"Σ angka manual + realisasi lampau = {total_manual + unit_actual_past} unit, "
                    f"beda {dev:+d} unit dari total target {unit_target}. Sistem TIDAK "
                    "membetulkan angka Anda — deviasi ini ditampilkan apa adanya.")
    elif method == "velocity_forecast":
        hist = [rows[m]["unit_actual"] for m in past[-3:]]
        vel_raw = median([h for h in hist if h is not None]) if hist else None
        if not hist:
            missing.append("belum ada bulan lampau di horizon ini untuk mengukur kecepatan jual")
        elif not vel_raw:
            missing.append("realisasi 3 bulan terakhir masih 0 — kecepatan jual belum bisa "
                           "diukur (proyeksi tidak boleh dikarang)")
        else:
            vel = vel_raw * (1 + float(growth_pct or 0) / 100)
            per_month = int(math.ceil(vel)) if vel > 0 else 0
            for m in future:
                rows[m]["unit_plan"] = per_month
                rows[m]["note"] = (f"kecepatan {round(vel, 2)} unit/bulan dari median 3 bulan "
                                   f"terakhir ({', '.join(str(h) for h in hist)})")
    elif method == "revenue_first":
        if not int(revenue_target or 0):
            missing.append("target pendapatan belum diisi")
        if not int(avg_price or 0):
            missing.append("harga rata-rata unit belum diketahui (asumsi `avg_price`) — "
                           "unit tidak bisa diturunkan dari pendapatan")
        if not missing:
            for m, val in zip(future, distribute(max(0, remaining_revenue), len(future))):
                rows[m]["revenue_plan"] = val
                rows[m]["unit_plan"] = int(math.ceil(val / int(avg_price)))

    # Rencana pendapatan untuk metode berbasis unit: hanya bila harga rata-rata diketahui.
    if method != "revenue_first" and not missing:
        for m in future:
            plan = rows[m]["unit_plan"]
            rows[m]["revenue_plan"] = (int(plan) * int(avg_price)
                                       if plan is not None and int(avg_price or 0) else None)
    if missing:
        for m in future:
            rows[m]["unit_plan"] = None
            rows[m]["revenue_plan"] = None
    if carry_over and future:
        rows[future[0]]["carry_over"] = carry_over
        note = (f"termasuk kekurangan {carry_over} unit dari bulan sebelumnya "
                f"(rencana lampau {plan_past} vs realisasi {unit_actual_past})")
        rows[future[0]]["note"] = ((rows[future[0]]["note"] + "; " + note)
                                   if rows[future[0]]["note"] else note)

    projection = _projection(method, rows, future, remaining_unit, missing)
    return _wrap(method, months, rows, unit_target, revenue_target, unit_actual_past,
                 revenue_actual_past, warnings, missing, projection, keep_total)


def _projection(method: str, rows: dict, future: list, remaining_unit: int,
                missing: list) -> dict:
    """Proyeksi bulan habis terjual — hanya bila kecepatannya punya dasar (bukan tebakan)."""
    if missing or not future:
        return None
    per_month = rows[future[0]]["unit_plan"] or 0
    if method == "velocity_forecast" and per_month > 0 and remaining_unit > 0:
        need = int(math.ceil(remaining_unit / per_month))
        return {"months_needed": need, "sold_out_period": month_add(future[0], need - 1),
                "beyond_horizon": need > len(future), "per_month": per_month,
                "basis": "median realisasi 3 bulan terakhir"}
    if remaining_unit <= 0:
        return {"months_needed": 0, "sold_out_period": None, "beyond_horizon": False,
                "per_month": per_month, "basis": "target sudah tercapai"}
    return None


def _wrap(method, months, rows, unit_target, revenue_target, unit_actual_past,
          revenue_actual_past, warnings, missing, projection, keep_total) -> dict:
    periods = [rows[m] for m in months]
    plan_future = sum(int(r["unit_plan"] or 0) for r in periods
                      if r["unit_plan"] is not None and not r["locked"])
    rev_future = sum(int(r["revenue_plan"] or 0) for r in periods
                     if r["revenue_plan"] is not None and not r["locked"])
    totals = {
        "unit_target": int(unit_target or 0), "revenue_target": int(revenue_target or 0),
        "unit_actual_total": sum(int(r["unit_actual"] or 0) for r in periods),
        "revenue_actual_total": sum(int(r["revenue_actual"] or 0) for r in periods),
        "unit_actual_past": unit_actual_past, "revenue_actual_past": revenue_actual_past,
        "unit_plan_future": plan_future, "revenue_plan_future": rev_future,
        "unit_plan_locked": sum(int(r["unit_plan"] or 0) for r in periods if r["locked"]),
        "carry_over": sum(int(r["carry_over"] or 0) for r in periods),
        "months": len(months),
    }
    # Invarian keep_total, DIHITUNG (bukan diklaim): realisasi lampau + rencana ke depan
    # harus sama dengan total target. Dikirim ke layar & gate supaya bisa diperiksa.
    totals["keep_total_ok"] = (bool(missing) or
                               (unit_actual_past + plan_future == int(unit_target or 0))
                               if keep_total else None)
    if keep_total and not missing and not totals["keep_total_ok"]:
        warnings.append(
            f"Σ rencana ke depan ({plan_future}) + realisasi lampau ({unit_actual_past}) "
            f"= {plan_future + unit_actual_past} unit, tidak sama dengan total target "
            f"{unit_target} unit.")
    return {"periods": periods, "totals": totals, "warnings": warnings, "missing": missing,
            "projection": projection, "formula": METHOD_FORMULA.get(method),
            "method": method}


# --------------------------------------------------------------------- recalc + jejak
def recalc(target: dict, *, actuals: dict, today: str = None, reason: str,
           actor: str = "system") -> dict:
    """Hitung ulang periode target dan CATAT jejaknya.

    Jejak (`history[]`) memuat `before`/`after` per periode yang berubah + alasan, karena
    "target berubah tanpa penjelasan" adalah cara tercepat membuat target tidak dipercaya.
    Periode lampau dikunci bila `recalc_policy.lock_past` (bawaan True).
    """
    policy = target.get("recalc_policy") or {}
    horizon = target.get("horizon") or {}
    months = month_list(horizon.get("start"), horizon.get("end"))
    existing = {p["period"]: p for p in (target.get("periods") or [])}
    assumptions = target.get("assumptions") or {}
    out = compute_periods(
        method=target.get("method") or "linear_remaining", months=months,
        unit_target=target.get("unit_target") or 0,
        revenue_target=target.get("revenue_target") or 0,
        avg_price=assumptions.get("avg_price") or 0, actuals=actuals, existing=existing,
        weights=target.get("weights") or {}, manual=target.get("manual_plan") or {},
        growth_pct=assumptions.get("growth_pct") or 0, today=today,
        lock_past=policy.get("lock_past", True), keep_total=policy.get("keep_total", True))
    changes = []
    for row in out["periods"]:
        before = (existing.get(row["period"]) or {}).get("unit_plan")
        if before != row["unit_plan"]:
            changes.append({"period": row["period"], "before": before,
                            "after": row["unit_plan"]})
    out["changes"] = changes
    out["history_entry"] = {
        "at": None,  # diisi pemanggil dengan `now_iso()` (modul ini bebas efek samping)
        "by": actor, "method": out["method"], "reason": reason,
        "changes": changes[:24], "changed_periods": len(changes),
        "carry_over": out["totals"].get("carry_over", 0),
    }
    return out


def validate_scope(parent_total: int, children: list) -> list:
    """Total target anak (cluster/sales) tidak boleh melewati induk (`docs/v2/32` §2.1)."""
    total = sum(int(c.get("unit_target") or 0) for c in children)
    problems = []
    if parent_total and total > int(parent_total):
        problems.append(
            f"Σ target anak {total} unit melewati target induk {parent_total} unit "
            f"(selisih {total - int(parent_total)}). Kurangi salah satu target anak.")
    return problems
