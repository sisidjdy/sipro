import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Info, ScrollText } from "lucide-react";

import EmptyState from "@/components/patterns/EmptyState";
import MoneyText from "@/components/patterns/MoneyText";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { formatDateWIB } from "@/utils/formatters";
import { CRMC } from "@/constants/testIds";

/**
 * Tab “Kontrak & Harga” pada profil pelanggan.
 *
 * Kenapa layar ini akhirnya ada: tab ini sempat MATI dengan tulisan “belum aktif —
 * dijadwalkan Fase 43”. Nomor itu sudah lewat (Fase 43 yang benar-benar dikerjakan adalah
 * Kampanye & Biaya Iklan), jadi pemakai membaca janji yang tidak pernah datang — padahal
 * DASAR HARGA-nya sudah lama ada di sistem: penawaran (harga unit, add-on, diskon, skema
 * bayar) dan transaksi yang jadi.
 *
 * Aturan layar ini:
 *  1. Yang ditampilkan hanya angka NYATA dari `deals` & `quotations`. Tidak ada satu pun
 *     komponen biaya yang dikarang.
 *  2. Yang BELUM ADA dinyatakan terang-terangan: kontrak formal (PPJB/AJB) beserta rincian
 *     biaya per komponen (BPHTB, notaris, biaya bank, hook, kelebihan tanah, promo) belum
 *     menjadi data di sistem. Itu bukan tabel yang boleh dikosongkan diam-diam.
 */
export default function CustomerContractTab({ customer }) {
  const [deals, setDeals] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const leadId = customer?.lead_id;

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [d, q] = await Promise.all([
        leadId ? api.get("/deals", { params: { lead_id: leadId, limit: 50 } })
          : Promise.resolve({ data: { data: [] } }),
        leadId ? api.get("/quotations", { params: { lead_id: leadId, limit: 50 } })
          .catch(() => ({ data: { data: [] } }))
          : Promise.resolve({ data: { data: [] } }),
      ]);
      setDeals(d.data.data || []);
      setQuotes(q.data.data || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat kontrak & harga pelanggan.");
    } finally { setLoading(false); }
  }, [leadId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingCards count={2} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  const gap = (
    <div data-testid={CRMC.contractGap}
      className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[13px] text-amber-900">
      <p className="flex items-center gap-1.5 font-medium">
        <Info className="h-4 w-4" /> Yang sudah ada dan yang belum
      </p>
      <p className="mt-1">
        Yang tampil di bawah adalah <b>dasar harga nyata</b>: harga unit, add-on, diskon, dan
        skema pembayaran dari penawaran serta transaksi yang jadi. <b>Kontrak formal
        (PPJB/AJB) beserta rincian biaya per komponen</b> — BPHTB, notaris, biaya bank, hook,
        kelebihan tanah, promo — <b>belum menjadi data di sistem</b>, jadi tidak ada angkanya
        di sini. Dokumen legal yang sudah terbit bisa dilihat di tab “Dokumen & Legal”.
      </p>
    </div>
  );

  if (!leadId || (!deals.length && !quotes.length)) {
    return (
      <div className="space-y-4">
        {gap}
        <div data-testid={CRMC.contractEmpty}>
          <EmptyState icon={ScrollText} title="Belum ada transaksi atau penawaran"
            description={leadId
              ? "Pelanggan ini belum punya penawaran maupun transaksi yang bisa menjadi dasar harga."
              : "Pelanggan ini belum terikat ke data lead, jadi penawaran & transaksinya tidak bisa ditelusuri."} />
        </div>
      </div>
    );
  }

  return (
    <div data-testid={CRMC.contractTab} className="space-y-5">
      {gap}

      <div className="space-y-2">
        <h3 className="section-title">Transaksi (dasar kontrak)</h3>
        {!deals.length ? (
          <p className="text-[13px] text-muted-foreground">
            Belum ada transaksi yang jadi — baru penawaran.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
            <table className="w-full text-[13px]">
              <thead className="bg-secondary/60 text-left text-[12px] text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Unit</th>
                  <th className="px-3 py-2">Keadaan</th>
                  <th className="px-3 py-2 text-right">Harga transaksi</th>
                  <th className="px-3 py-2 text-right">Booking fee</th>
                  <th className="px-3 py-2">Tanggal booking</th>
                </tr>
              </thead>
              <tbody>
                {deals.map((d) => (
                  <tr key={d.id} data-testid={CRMC.contractDealRow} className="border-t">
                    <td className="px-3 py-2 font-medium">
                      {d.unit_id ? (
                        <Link to={`/units/${d.unit_id}`} className="text-primary hover:underline">
                          {d.unit_code || "unit"}
                        </Link>
                      ) : (d.unit_code || "—")}
                    </td>
                    <td className="px-3 py-2">
                      <StatusPill group="deal_status" status={d.status} />
                    </td>
                    <td className="px-3 py-2 text-right"><MoneyText value={d.price} /></td>
                    <td className="px-3 py-2 text-right">
                      <MoneyText value={d.booking_fee} />
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {d.booked_at ? formatDateWIB(d.booked_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <h3 className="section-title">
          Penawaran & rincian harga yang tercatat
        </h3>
        {!quotes.length ? (
          <p className="text-[13px] text-muted-foreground">
            Belum ada penawaran untuk pelanggan ini.
          </p>
        ) : quotes.map((q) => (
          <div key={q.id} data-testid={CRMC.contractQuotationRow}
            className="space-y-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-medium">
                  {q.no || q.number || "Penawaran"}
                  {q.version ? ` (v${q.version})` : ""} · {q.unit_code || "unit"}
                </p>
                <p className="text-[12px] text-muted-foreground">
                  Dibuat {formatDateWIB(q.created_at)}
                  {q.valid_until ? ` · berlaku sampai ${formatDateWIB(q.valid_until)}` : ""}
                  {q.scheme?.name ? ` · skema ${q.scheme.name}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusPill group="quotation_state" status={q.state} />
                <Link to={`/quotations?q=${encodeURIComponent(q.no || "")}`}
                  data-testid={CRMC.contractOpenQuotation}
                  className="inline-flex items-center gap-1 text-[12px] font-medium text-primary hover:underline">
                  Buka penawaran <ExternalLink className="h-3 w-3" />
                </Link>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-4">
              {[["Harga unit", q.base_price], ["Add-on", q.addon_total],
                ["Diskon", q.discount_amount], ["Harga neto", q.net_price]].map(([label, val]) => (
                <div key={label} className="rounded-lg border bg-secondary/40 px-2.5 py-1.5">
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {label}
                  </p>
                  <p className="font-semibold tabular-nums">
                    {val === null || val === undefined ? "belum ada data"
                      : <MoneyText value={val} />}
                  </p>
                </div>
              ))}
            </div>
            {(q.addons || []).length ? (
              <div className="overflow-x-auto rounded-lg border bg-card shadow-[var(--shadow-card)]">
                <table className="w-full text-[12px]">
                  <thead className="bg-secondary/60 text-left text-muted-foreground">
                    <tr>
                      <th className="px-2.5 py-1.5">Add-on / biaya tambahan</th>
                      <th className="px-2.5 py-1.5">Perlakuan</th>
                      <th className="px-2.5 py-1.5 text-right">Nilai</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(q.addons || []).map((a, i) => (
                      <tr key={`${a.code || a.label || i}`} data-testid={CRMC.contractAddonRow}
                        className="border-t">
                        <td className="px-2.5 py-1.5">
                          {a.name || a.label || a.code}
                          {a.formula ? (
                            <span className="ml-1 text-muted-foreground">({a.formula})</span>
                          ) : null}
                        </td>
                        <td className="px-2.5 py-1.5 text-muted-foreground">
                          {a.finance_treatment === "revenue" ? "Pendapatan"
                            : a.finance_treatment === "reimbursement" ? "Titipan/reimburse"
                              : (a.finance_treatment || "—")}
                        </td>
                        <td className="px-2.5 py-1.5 text-right tabular-nums">
                          <MoneyText value={a.amount ?? a.total ?? a.unit_price} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-[12px] text-muted-foreground">
                Penawaran ini tanpa add-on — hanya harga unit.
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
