import React, { useCallback, useEffect, useState } from "react";
import { FileSignature, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import MoneyText from "@/components/patterns/MoneyText";
import EmptyState from "@/components/patterns/EmptyState";
import { LoadingCards, PanelStateView } from "@/components/patterns/StateViews";
import QuotationForm from "@/components/quotations/QuotationForm";
import QuotationDetailSheet from "@/components/quotations/QuotationDetailSheet";
import { useAuth } from "@/context/AuthContext";
import { formatDateWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { classifyRequestError } from "@/utils/panelLoad";
import { QUOTE } from "@/constants/testIds";

/**
 * QuotationsTab (Fase 47C) — penawaran harga milik satu calon pembeli.
 *
 * Kenapa ada di profil lead (bukan menu baru): penawaran adalah bagian dari percakapan
 * penjualan pada lead itu, sehingga harganya, diskonnya, dan keputusan manajernya harus
 * terbaca di tempat yang sama dengan riwayat & dokumen calon pembeli tersebut.
 */
export default function QuotationsTab({ leadId, leadName, onChanged }) {
  const { can } = useAuth();
  // Membuat penawaran dipaksakan router dengan `quotations:create`; peran yang hanya boleh
  // melihat (mis. finance) tetap bisa membaca daftar & rinciannya tanpa tombol mati.
  const canCreate = can("quotations", "create");
  const [rows, setRows] = useState(null);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [reviseFrom, setReviseFrom] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setPanel(null);
    try {
      const res = await api.get("/quotations", { params: { lead_id: leadId, limit: 50 } });
      setRows(res.data.data || []);
      setSummary(res.data.summary || {});
    } catch (e) {
      // Fase 52 — jangan meneruskan pesan penegak izin ke layar, dan jangan menyamakan
      // "tidak boleh dilihat" dengan "gagal dimuat": obatnya berbeda (minta hak akses vs
      // coba lagi).
      setPanel(classifyRequestError(e));
    } finally { setLoading(false); }
  }, [leadId]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setReviseFrom(null); setFormOpen(true); };
  const openRevise = (q) => { setReviseFrom(q); setFormOpen(true); };

  return (
    <div data-testid={QUOTE.panel} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-heading text-lg font-semibold">Penawaran harga</h3>
          <p className="text-sm text-muted-foreground">
            Simulasi harga, termin, dan angsuran KPR untuk {leadName || "calon pembeli"} —
            memakai mesin harga yang sama dengan tagihan.
          </p>
        </div>
        {canCreate ? (
          <Button data-testid={QUOTE.addBtn} onClick={openNew}>
            <Plus className="mr-1.5 h-4 w-4" /> Buat penawaran
          </Button>
        ) : null}
      </div>

      {summary.awaiting_approval ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {summary.awaiting_approval} penawaran menunggu persetujuan diskon manajer.
        </p>
      ) : null}

      {loading ? <LoadingCards count={2} /> : null}
      {panel ? (
        <PanelStateView panel={panel} subject="Penawaran harga" onRetry={load}
          whoMay={"Penawaran dibuka untuk tim Sales, Manajer Sales, Marketing Admin, "
            + "dan Keuangan."} />
      ) : null}

      {!loading && !panel && !(rows || []).length ? (
        <EmptyState icon={FileSignature} title="Belum ada penawaran"
          description="Buat penawaran untuk mengunci angka yang dijanjikan ke pembeli: harga, tambahan, potongan, termin, dan estimasi angsuran KPR — semuanya bisa dicetak dan dikirim."
          actionLabel={canCreate ? "Buat penawaran" : ""}
          onAction={canCreate ? openNew : null} />
      ) : null}

      {!loading && !panel && (rows || []).length ? (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-[var(--shadow-card)]">
          <table data-testid={QUOTE.table} className="w-full text-sm">
            <thead className="bg-secondary/60 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Nomor</th>
                <th className="px-3 py-2 text-left">Unit</th>
                <th className="px-3 py-2 text-right">Harga penawaran</th>
                <th className="px-3 py-2 text-right">Potongan</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Berlaku s/d</th>
                <th className="px-3 py-2 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((q) => (
                <tr key={q.id} data-testid={QUOTE.row} data-state={q.state}>
                  <td className="px-3 py-2">
                    <p className="font-mono text-xs font-medium">{q.no}</p>
                    <p className="text-xs text-muted-foreground">versi {q.version}</p>
                  </td>
                  <td className="px-3 py-2">{q.unit_code || "-"}</td>
                  <td className="px-3 py-2 text-right">
                    <MoneyText value={q.net_price} className="font-medium" />
                  </td>
                  <td className="px-3 py-2 text-right">
                    {q.discount_amount ? (
                      <span className="text-rose-700">
                        <MoneyText value={q.discount_amount} /> ({q.discount_pct}%)
                      </span>
                    ) : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={q.state} group="quotation_state" />
                  </td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">
                    {formatDateWIB(q.valid_until)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="outline" data-testid={QUOTE.detailBtn}
                      data-quotation={q.id}
                      aria-label={`Buka penawaran ${q.no} versi ${q.version}`}
                      onClick={() => setDetailId(q.id)}>
                      Buka
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <QuotationForm open={formOpen} onOpenChange={setFormOpen} leadId={leadId}
        source={reviseFrom} onDone={() => { load(); onChanged?.(); }} />
      <QuotationDetailSheet quotationId={detailId} open={!!detailId}
        onOpenChange={(v) => !v && setDetailId(null)}
        onChanged={() => { load(); onChanged?.(); }} onRevise={openRevise} />
    </div>
  );
}
