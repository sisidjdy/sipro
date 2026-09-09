import React, { useCallback, useEffect, useState } from "react";
import { Download, FileText, Receipt } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import ContractDocuments from "@/components/contracts/ContractDocuments";
import MoneyText from "@/components/patterns/MoneyText";
import StatusPill from "@/components/patterns/StatusPill";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards } from "@/components/patterns/StateViews";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";

export async function openPdf(url, errMsg) {
  try {
    const res = await api.get(url, { responseType: "blob" });
    const href = URL.createObjectURL(res.data);
    window.open(href, "_blank");
    setTimeout(() => URL.revokeObjectURL(href), 30000);
  } catch (e) {
    let detail = errMsg || "Gagal membuka PDF.";
    try { detail = JSON.parse(await e?.response?.data?.text())?.detail || detail; } catch { /* blob */ }
    toast.error(detail);
  }
}

/** Bagian invoice & kwitansi booking untuk satu transaksi (deal). */
function BillingDocs({ dealId }) {
  const [ar, setAr] = useState(null);
  const [state, setState] = useState("loading");

  useEffect(() => {
    let hidup = true;
    setState("loading");
    api.get(`/finance/ar/${dealId}`)
      .then((res) => { if (hidup) { setAr(res.data); setState("ok"); } })
      .catch((e) => { if (hidup) setState(e?.response?.status === 404 ? "kosong" : "gagal"); });
    return () => { hidup = false; };
  }, [dealId]);

  if (state === "loading") return <LoadingCards count={1} />;
  if (state === "kosong") {
    return (
      <p data-testid="issue-hub-ar-empty"
        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        Belum ada jadwal tagihan (AR) untuk transaksi ini — invoice & kwitansi tersedia
        setelah jadwal pembayaran dibuat pada tab Rencana Bayar pembeli.
      </p>
    );
  }
  if (state === "gagal") {
    return <p className="text-xs text-muted-foreground">Data tagihan tidak bisa dimuat.</p>;
  }
  const inv = ar?.data || {};
  const receipts = ar?.receipts || [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background p-3">
        <div className="text-sm">
          <p className="font-medium">Invoice / tagihan pembayaran</p>
          <p className="text-xs text-muted-foreground">
            Total <MoneyText value={inv.total} /> · dibayar <MoneyText value={inv.paid} /> ·
            sisa <MoneyText value={inv.outstanding} />
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={inv.status} group="ar_status" />
          <Button data-testid="issue-hub-invoice-pdf" size="sm" variant="outline"
            onClick={() => openPdf(`/finance/ar/${dealId}/invoice/pdf`)}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Invoice (PDF)
          </Button>
        </div>
      </div>
      <div className="space-y-1.5">
        <p className="text-[13px] font-medium">Kwitansi penerimaan ({receipts.length})</p>
        {!receipts.length ? (
          <p className="text-xs text-muted-foreground">
            Belum ada penerimaan tercatat — kwitansi terbit otomatis saat pembayaran dicatat.
          </p>
        ) : receipts.map((r) => (
          <div key={r.id} data-testid="issue-hub-receipt-row" data-receipt-id={r.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-background px-3 py-2 text-xs">
            <span>
              <Receipt className="mr-1.5 inline h-3.5 w-3.5 text-muted-foreground" />
              {r.receipt_no || r.id} · {formatDateWIB(r.created_at)} ·{" "}
              <b className="tabular-nums"><MoneyText value={r.amount} /></b>
            </span>
            <Button data-testid="issue-hub-receipt-pdf" data-receipt-id={r.id} size="sm" variant="ghost"
              className="h-7 px-2 text-xs"
              onClick={() => openPdf(`/finance/ar/receipts/${r.id}/pdf`)}>
              <Download className="mr-1 h-3 w-3" /> Kwitansi (PDF)
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * DocumentIssueHub — SATU tempat menerbitkan semua dokumen transaksi.
 *
 * Sebelumnya menerbitkan SPR/SPKT mengharuskan navigasi: Customer & Kontrak → cari pembeli →
 * tab kontrak → gulir ke panel dokumen. Di sini: pilih transaksi → semua dokumen (SPR sesuai
 * skema, SPKT, invoice, kwitansi) terbit & tercetak dari satu layar.
 */
export default function DocumentIssueHub() {
  const { can } = useAuth();
  const [contracts, setContracts] = useState([]);
  const [selId, setSelId] = useState("");
  const [contract, setContract] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/contracts?limit=100")
      .then((res) => setContracts(res.data.data || []))
      .catch(() => setContracts([]))
      .finally(() => setLoading(false));
  }, []);

  const pick = useCallback(async (id) => {
    setSelId(id);
    setContract(null);
    try {
      const res = await api.get(`/contracts/${id}`);
      setContract(res.data.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat kontrak.");
    }
  }, []);

  const reloadContract = () => { if (selId) pick(selId); };

  const label = (c) => [c.customer_name || c.lead_name || "Pembeli",
    c.unit_code ? `Unit ${c.unit_code}` : null,
    c.scheme ? c.scheme.toUpperCase() : null].filter(Boolean).join(" — ");

  if (loading) return <LoadingCards count={2} />;

  return (
    <div data-testid="document-issue-hub" className="space-y-4">
      <div className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
        <h3 className="section-title">Pilih transaksi</h3>
        <p className="mb-2 text-xs text-muted-foreground">
          Semua dokumen transaksi — SPR (sesuai skema), SPKT, invoice tagihan, dan kwitansi —
          diterbitkan dan dicetak dari satu tempat ini.
        </p>
        {!contracts.length ? (
          <EmptyState icon={FileText} title="Belum ada kontrak"
            description="Kontrak lahir saat lead dijadikan Pembeli (setelah booking). Setelah itu dokumennya bisa diterbitkan di sini." />
        ) : (
          <Select value={selId || undefined} onValueChange={pick}>
            <SelectTrigger data-testid="issue-hub-contract-select" className="max-w-xl">
              <SelectValue placeholder="Pilih pembeli / unit…" />
            </SelectTrigger>
            <SelectContent>
              {contracts.map((c) => (
                <SelectItem key={c.id} value={c.id}>{label(c)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {selId && !contract ? <LoadingCards count={1} /> : null}

      {contract ? (
        <>
          <ContractDocuments contract={contract} onChanged={reloadContract} />
          {can("finance", "view") ? (
            <section className="space-y-3 rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
              <div>
                <h3 className="section-title">Bukti pembayaran booking</h3>
                <p className="text-xs text-muted-foreground">
                  Invoice (jadwal tagihan) dan kwitansi resmi ber-kop untuk transaksi ini.
                </p>
              </div>
              <BillingDocs dealId={contract.deal_id} />
            </section>
          ) : (
            <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
              Invoice & kwitansi hanya terbuka untuk peran dengan akses Keuangan.
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
