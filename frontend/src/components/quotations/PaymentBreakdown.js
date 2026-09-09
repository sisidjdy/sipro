import React from "react";

import MoneyText from "@/components/patterns/MoneyText";

const GROUP_TONE = {
  potongan: "text-rose-700",
  potongan_biaya: "text-rose-700",
  subtotal: "font-medium",
  total: "font-semibold",
  deposit: "text-indigo-700",
};

/**
 * PaymentBreakdown — SATU tabel komponen pembayaran pembeli, apa adanya dari backend
 * (`quotation_engine.build_payment_breakdown`): harga unit, add-on, potongan harga, harga bersih,
 * komponen biaya all-in (kotor − potongan = bersih), total dibayar pembeli, booking fee.
 * Layar tidak menghitung sendiri — angka di sini identik dengan snapshot deal & piutang Finance.
 */
export default function PaymentBreakdown({ breakdown, title = "Komponen pembayaran pembeli", testId = "payment-breakdown", stale = false }) {
  if (!breakdown || !(breakdown.rows || []).length) return null;
  const rows = breakdown.rows;
  return (
    <div data-testid={testId} data-stale={stale ? "1" : "0"}
      className="rounded-lg border bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
        {breakdown.total_discount ? (
          <span data-testid={`${testId}-discount-total`} className="text-xs text-rose-700">
            total potongan <MoneyText value={breakdown.total_discount} />
          </span>
        ) : null}
      </div>
      <div className="mt-2 overflow-x-auto rounded-md border bg-background">
        <table className="w-full text-sm">
          <tbody className="divide-y">
            {rows.map((r) => {
              const isTotal = r.group === "total" || r.group === "subtotal";
              return (
                <tr key={r.code} data-testid={`${testId}-row`} data-code={r.code} data-group={r.group}
                  className={isTotal ? "bg-secondary/40" : ""}>
                  <td className="px-3 py-1.5">
                    <p className={GROUP_TONE[r.group] || ""}>
                      {r.label}
                      {r.developer_borne ? <span className="ml-1 rounded-full bg-slate-100 px-1.5 text-[10px] text-slate-700">developer</span> : null}
                      {r.kpr_excluded ? <span className="ml-1 rounded-full bg-amber-50 px-1.5 text-[10px] text-amber-800">bukan KPR</span> : null}
                      {r.kpr_base ? <span className="ml-1 rounded-full bg-sky-50 px-1.5 text-[10px] text-sky-800">dasar KPR</span> : null}
                      {r.pending ? <span className="ml-1 rounded-full bg-amber-100 px-1.5 text-[10px] text-amber-800">menunggu</span> : null}
                    </p>
                    {r.hint ? <p className="text-[11px] text-muted-foreground">{r.hint}</p> : null}
                  </td>
                  <td className={`px-3 py-1.5 text-right tabular-nums ${GROUP_TONE[r.group] || ""} ${r.developer_borne ? "text-muted-foreground line-through" : ""}`}>
                    <MoneyText value={r.amount} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Total dibayar pembeli = harga bersih unit + add-on {breakdown.has_costs ? "+ biaya all-in pembeli setelah potongan" : "(skema all-in belum dipilih — biaya belum termasuk)"}.
        Termin &amp; KPR hanya dari harga bersih unit; add-on dan biaya all-in ditagih terpisah.
        Booking fee bukan potongan: dibayar lebih dulu lalu dialihkan ke termin.
      </p>
    </div>
  );
}
