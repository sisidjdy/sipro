import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Download, FileSignature, ReceiptText } from "lucide-react";

import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatDateWIB, formatIDR } from "@/utils/formatters";
import { portalDownload, portalBlobError } from "@/utils/portalDownload";
import portalApi from "@/services/portalClient";
import { PORTAL, P51 } from "@/constants/testIds";

/**
 * Dokumen milik PEMBELI (portal).
 *
 * Fase 51C menutup tiga hal yang paling sering diminta manusia tetapi belum ada sampai
 * Fase 50:
 *   1. **Salinan BAST-nya sendiri** — sebelumnya hanya staf yang bisa mengunduhnya, padahal
 *      dokumen itulah dasar penghitungan masa garansi rumahnya.
 *   2. **Kwitansi pembayarannya** — tidak bisa diunduh siapa pun, jadi setiap permintaan
 *      salinan berubah menjadi pekerjaan manual.
 *   3. Keduanya diunduh lewat sesi portal (blob), BUKAN tautan bertoken di URL — supaya
 *      token sesi pembeli tidak tercatat di riwayat peramban/log proxy dan galatnya bisa
 *      dibaca sebagai kalimat, bukan JSON mentah.
 */
export default function DocumentsPanel() {
  const [docs, setDocs] = useState([]);
  const [bast, setBast] = useState(null);
  const [receipts, setReceipts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [d, h, r] = await Promise.all([
        portalApi.get("/portal/documents"),
        portalApi.get("/portal/handovers"),
        portalApi.get("/portal/receipts"),
      ]);
      setDocs(d.data.data || []);
      setBast(h.data);
      setReceipts(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Gagal memuat dokumen.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const open = async (url, name, key) => {
    setBusy(key);
    try {
      await portalDownload(url, { fallbackName: name, open: true });
    } catch (e) {
      toast.error(await portalBlobError(e, "Berkas tidak bisa dibuka."));
    } finally { setBusy(""); }
  };

  if (loading) return <LoadingCards count={3} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div data-testid={PORTAL.documentsPanel} className="space-y-5">
      {/* ---------- Berita acara serah terima (Fase 51C) ---------- */}
      <section data-testid={P51.portalBastSection} className="space-y-2">
        <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
          <FileSignature className="h-4 w-4 text-indigo-600" /> Berita acara serah terima
        </h3>
        {/* Keterangan hanya ditulis SEKALI: bila kosong ia jadi isi kotak kosong-jujur,
            bila ada isinya ia jadi subjudul. Menulis kalimat yang sama dua kali membuat
            layar tampak seperti galat berulang. */}
        {bast?.data?.length ? (
          <p className="text-sm text-slate-500">{bast?.detail}</p>
        ) : null}
        {!bast?.data?.length ? (
          <p data-testid={P51.portalBastEmpty}
            className="rounded-xl border bg-white p-4 text-sm text-slate-500">
            {bast?.detail}
          </p>
        ) : (
          <div className="divide-y rounded-xl border bg-white">
            {bast.data.map((h) => (
              <div key={h.id} data-testid={P51.portalBastRow}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="grid h-9 w-9 place-items-center rounded-lg bg-indigo-50 text-indigo-600">
                    <FileSignature className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">
                      {h.number} · rumah {h.unit_code || "—"}
                    </p>
                    <p className="text-xs text-slate-400">
                      diserahterimakan {h.handed_over_at}
                      {h.received_by ? ` · diterima ${h.received_by}` : ""}
                      {h.keys_handed !== null && h.keys_handed !== undefined
                        ? ` · ${h.keys_handed} kunci` : ""}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusPill status={h.state}
                    label={h.state === "cancelled" ? "Dibatalkan" : "Berlaku"} />
                  <button type="button" data-testid={P51.portalBastPdf}
                    disabled={busy === `bast-${h.id}`}
                    onClick={() => open(`/portal/handovers/${h.id}/pdf`, h.number,
                      `bast-${h.id}`)}
                    className="flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline disabled:opacity-50">
                    <Download className="h-4 w-4" />
                    {busy === `bast-${h.id}` ? "Membuka…" : "PDF"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ---------- Kwitansi pembayaran (Fase 51C) ---------- */}
      <section data-testid={P51.portalReceiptSection} className="space-y-2">
        <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
          <ReceiptText className="h-4 w-4 text-emerald-600" /> Kwitansi pembayaran saya
        </h3>
        {receipts?.data?.length ? (
          <p className="text-sm text-slate-500">{receipts?.detail}</p>
        ) : null}
        {!receipts?.data?.length ? (
          <p data-testid={P51.portalReceiptEmpty}
            className="rounded-xl border bg-white p-4 text-sm text-slate-500">
            {receipts?.detail}
          </p>
        ) : (
          <div className="divide-y rounded-xl border bg-white">
            {receipts.data.map((r) => (
              <div key={r.id} data-testid={P51.portalReceiptRow}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="grid h-9 w-9 place-items-center rounded-lg bg-emerald-50 text-emerald-600">
                    <ReceiptText className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">
                      {r.receipt_no || "Kwitansi"} · {formatIDR(r.amount)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {formatDateWIB(r.created_at)}
                      {r.unit_code ? ` · rumah ${r.unit_code}` : ""}
                    </p>
                  </div>
                </div>
                <button type="button" data-testid={P51.portalReceiptPdf}
                  disabled={busy === `kwt-${r.id}`}
                  onClick={() => open(`/portal/receipts/${r.id}/pdf`,
                    r.receipt_no || "kwitansi", `kwt-${r.id}`)}
                  className="flex items-center gap-1 text-sm font-medium text-emerald-700 hover:underline disabled:opacity-50">
                  <Download className="h-4 w-4" />
                  {busy === `kwt-${r.id}` ? "Membuka…" : "PDF"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ---------- Dokumen kontrak & legal (sudah ada sejak portal dibuka) ---------- */}
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
          <FileText className="h-4 w-4 text-slate-600" /> Dokumen kontrak &amp; legal
        </h3>
        {!docs.length ? (
          <p className="rounded-xl border bg-white p-4 text-sm text-slate-500">
            Belum ada dokumen kontrak yang diterbitkan untuk Anda — belum ada data.
          </p>
        ) : (
          <div className="divide-y rounded-xl border bg-white">
            {docs.map((d) => (
              <div key={d.id} data-testid={PORTAL.documentRow}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 text-slate-600">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{d.title}</p>
                    <p className="text-xs text-slate-400">
                      {d.doc_number} · {formatDateWIB(d.created_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusPill status={d.status}
                    label={d.status === "signed" ? "Ditandatangani"
                      : d.status === "finalized" ? "Final" : "Draf"} />
                  <button type="button" disabled={busy === `doc-${d.id}`}
                    onClick={() => open(`/portal/documents/${d.id}/pdf`,
                      d.doc_number || "dokumen", `doc-${d.id}`)}
                    className="flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline disabled:opacity-50">
                    <Download className="h-4 w-4" />
                    {busy === `doc-${d.id}` ? "Membuka…" : "PDF"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
