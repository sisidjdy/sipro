import React from "react";
import { Calculator, Info } from "lucide-react";

import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import PaymentBreakdown from "@/components/quotations/PaymentBreakdown";
import { formatDateWIB } from "@/utils/formatters";
import { QUOTE } from "@/constants/testIds";

const MISSING_LABEL = {
  tenor_bulan: "tenor (bulan)",
  bunga_tahunan: "bunga per tahun",
  persen_dp: "persentase DP",
};

function Line({ label, value, hint, strong = false, tone = "" }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <div>
        <p className={strong ? "text-sm font-medium" : "text-sm"}>{label}</p>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      <MoneyText value={value} className={`text-sm ${strong ? "font-semibold" : ""} ${tone}`} />
    </div>
  );
}

/**
 * QuotationBreakdown — angka penawaran yang BISA DIHITUNG ULANG oleh pembeli.
 *
 * Dua aturan yang dijaga komponen ini:
 *   1. **Tidak ada rumus kedua.** Termin datang APA ADANYA dari mesin AR
 *      (`finance_engine.compute_scheme_items`) — layar tidak pernah menghitung sendiri,
 *      sehingga angka di penawaran identik dengan tagihan yang nanti terbit.
 *   2. **Simulasi KPR yang jujur.** Bila tenor/bunga/DP belum diisi, kotak KPR menulis
 *      “belum ada data” beserta apa yang kurang — bukan menampilkan Rp 0 yang terlihat
 *      seperti angsuran nol.
 */
export default function QuotationBreakdown({ calc, hideKpr = false, stale = false }) {
  if (!calc) return null;
  const kpr = calc.kpr || {};
  const taxes = calc.taxes || {};

  return (
    <div data-testid={QUOTE.breakdown} className="space-y-3">
      <PaymentBreakdown breakdown={calc.payment_breakdown} stale={stale} />
      <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Rincian harga
        </p>
        <div className="mt-1.5 divide-y">
          <Line label={`Harga unit ${calc.unit?.code || calc.unit_code || ""}`}
            value={calc.base_price} hint={calc.unit?.type} />
          {(calc.discount_lines || []).filter((dl) => dl.target !== "addon").map((dl) => (
            <Line key={`${dl.source}-${dl.rule_id}`} value={-Math.abs(dl.amount)}
              tone={dl.pending ? "text-amber-700" : "text-rose-700"}
              label={`${dl.source_label} · ${dl.name || dl.code}${dl.target && dl.target !== "price" ? ` (potong ${dl.target_label})` : ""}`}
              hint={`${dl.code} · ${dl.formula}${dl.requires_approval ? " · perlu persetujuan" : ""}${dl.pending ? " · pilih skema all-in yang memuat komponen ini lalu hitung ulang" : ""}${dl.note ? ` · ${dl.note}` : ""}`} />
          ))}
          {calc.cost_discount_amount ? (
            <Line label="Potongan biaya transaksi" value={-Math.abs(calc.cost_discount_amount)} tone="text-rose-700"
              hint="dikurangkan dari komponen biaya pembeli (lihat komponen pembayaran di atas), bukan dari harga unit" />
          ) : null}
          {calc.discount_amount ? (
            <Line label="Total potongan harga" value={-Math.abs(calc.discount_amount)}
              tone="text-rose-700"
              hint={`${calc.discount_pct}%${calc.discount_limit_pct != null ? ` · batas kewenangan sales ${calc.discount_limit_pct}%` : ""}`} />
          ) : null}
          <Line label="Harga bersih unit — dasar termin / KPR" value={calc.net_price} strong />
          {(calc.addons || []).filter((a) => (a.finance_treatment || "revenue") !== "info").map((a) => (
            <Line key={a.code} label={`Add-on · ${a.name}`} value={a.amount}
              hint={`${a.formula} · tagihan terpisah, tidak masuk KPR`} />
          ))}
          {calc.addon_net_total != null && calc.addon_net_total !== calc.addon_total ? (
            <Line label="Potongan add-on" value={-Math.abs((calc.addon_total || 0) - calc.addon_net_total)} tone="text-rose-700" />
          ) : null}
          {calc.costs ? (
            <Line label="Biaya all-in pembeli" value={calc.costs.buyer_total || 0}
              hint={`${calc.costs.scheme_name || "skema all-in"} · ditagih terpisah (invoice biaya)`} />
          ) : null}
          {calc.buyer_total != null ? (
            <Line label="Total dibayar pembeli (unit + add-on + biaya all-in)" value={calc.buyer_total} strong />
          ) : null}
        </div>
      </div>

      <div className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Skema pembayaran · {calc.scheme?.name || "belum dipilih"}
          </p>
          <span className="text-xs text-muted-foreground">
            Σ termin unit <MoneyText value={calc.terms_total ?? calc.net_price} /> · add-on &amp; biaya all-in ditagih terpisah
          </span>
        </div>
        <div className="mt-2 overflow-x-auto rounded-md border bg-background">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 text-left">Termin</th>
                <th className="px-3 py-1.5 text-left">Jatuh tempo</th>
                <th className="px-3 py-1.5 text-right">Nominal</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {(calc.terms || []).map((t) => (
                <tr key={t.id}>
                  <td className="px-3 py-1.5">{t.label}
                    {t.discount ? <span className="ml-1 text-xs text-rose-700">(−<MoneyText value={t.discount} /> potongan)</span> : null}
                  </td>
                  <td className="px-3 py-1.5 tabular-nums text-muted-foreground">
                    {formatDateWIB(t.due_date)}
                  </td>
                  <td className="px-3 py-1.5 text-right"><MoneyText value={t.amount} /></td>
                </tr>
              ))}
              {!(calc.terms || []).length ? (
                <tr><td colSpan={3} className="px-3 py-2 text-sm text-muted-foreground">
                  Skema pembayaran belum dipilih — termin belum bisa dihitung.
                </td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {hideKpr ? null : (
      <div data-testid={QUOTE.kprBox}
        className={`rounded-lg border p-3 ${kpr.state === "complete"
          ? "border-sky-200 bg-sky-50" : "border-amber-200 bg-amber-50"}`}>
        <div className="flex items-center gap-2">
          <Calculator className="h-4 w-4" />
          <p className="text-sm font-medium">Simulasi KPR</p>
          <StatusPill status={kpr.state || "missing_data"} group="estimate_state" />
        </div>
        {kpr.state === "complete" ? (
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Angsuran / bulan</p>
              <MoneyText value={kpr.monthly_installment}
                className="font-heading text-lg font-semibold" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Pokok pinjaman</p>
              <MoneyText value={kpr.loan_amount} className="text-sm font-medium" />
              <p className="text-xs text-muted-foreground">
                DP {kpr.dp_pct}% (<MoneyText value={kpr.dp_amount} />)
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Tenor & bunga</p>
              <p className="text-sm font-medium tabular-nums">
                {kpr.tenor_months} bulan · {kpr.annual_rate_pct}% / tahun
              </p>
              <p className="text-xs text-muted-foreground">
                Total bunga <MoneyText value={kpr.total_interest} />
              </p>
            </div>
          </div>
        ) : (
          <p className="mt-1.5 text-sm text-amber-900">
            <b>Belum ada data</b> — isi {(kpr.missing || []).map((m) => MISSING_LABEL[m] || m)
              .join(", ") || "tenor, bunga, dan DP"} agar angsuran bisa dihitung. Angka nol
            TIDAK ditampilkan supaya tidak dibaca sebagai “tanpa angsuran”.
          </p>
        )}
        {kpr.note ? (
          <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5" /> {kpr.note}
          </p>
        ) : null}
      </div>
      )}
      {taxes.ppn != null || taxes.bphtb != null ? (
        <p data-testid="quotation-tax-note" className="text-xs text-muted-foreground">
          Perkiraan pajak &amp; biaya (di luar harga): PPN {taxes.ppn_rate}%{" "}
          <MoneyText value={taxes.ppn} /> · BPHTB {taxes.bphtb_rate}%{" "}
          <MoneyText value={taxes.bphtb} />. Dipakai untuk penjelasan ke pembeli, bukan
          bagian dari termin.
        </p>
      ) : null}
    </div>
  );
}
