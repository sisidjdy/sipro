import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ThumbsUp, ThumbsDown } from "lucide-react";

import portalApi from "@/services/portalClient";
import { P51 as T } from "@/constants/testIds";

/**
 * Pengakuan pembeli bahwa perbaikan garansi memang SELESAI (Fase 51C).
 *
 * Mesin klaim garansi Fase 50 MEWAJIBKAN pengakuan pembeli untuk menutup klaim — tetapi
 * tidak pernah memberi pembeli pintunya, jadi selama ini stafnya yang mengetik atas nama
 * pembeli. Pengakuan yang diketik orang lain bukan pengakuan; ia hanya formalitas yang
 * membuat jejaknya tidak bisa dipercaya saat ada sengketa.
 *
 * Dua jawaban, dua akibat yang jujur:
 *   • “Sudah beres” → klaim DITUTUP atas nama pembeli (riwayatnya tetap tersimpan).
 *   • “Belum beres” → klaim DIKEMBALIKAN ke pengerjaan + tim diberi tahu. Tidak ditutup.
 */
export default function ClaimAckDialog({ claim, onOpenChange, onDone }) {
  const [satisfied, setSatisfied] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setSatisfied(null); setNote(""); }, [claim]);

  if (!claim) return null;

  const submit = async () => {
    if (satisfied === null) {
      toast.error("Pilih dulu: perbaikannya sudah beres atau belum.");
      return;
    }
    if (!satisfied && note.trim().length < 5) {
      toast.error("Tulis apa yang masih belum beres supaya tim tahu harus memperbaiki apa.");
      return;
    }
    setBusy(true);
    try {
      const res = await portalApi.post(`/portal/warranty/claims/${claim.id}/ack`, {
        satisfied, note: note.trim() || null,
      });
      toast.success(res.data?.message || "Terima kasih, tanggapan Anda tersimpan.");
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan tanggapan Anda.");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-slate-900/40 p-4">
      <div data-testid={T.portalAckDialog}
        className="w-full max-w-md rounded-2xl bg-white p-4 shadow-xl">
        <p className="flex items-center gap-2 font-heading text-base font-semibold">
          <CheckCircle2 className="h-5 w-5 text-emerald-600" /> Perbaikan sudah beres?
        </p>
        <p className="mt-0.5 text-xs text-slate-500">
          Klaim {claim.number} — {claim.title}. Tim kami menyatakan perbaikannya selesai dan
          sudah diperiksa mutunya. Klaim baru ditutup setelah <b>Anda</b> mengakuinya, dan
          pengakuan itu tercatat atas nama Anda.
        </p>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <button type="button" data-testid={T.portalAckYes}
            onClick={() => setSatisfied(true)}
            className={`flex items-center justify-center gap-1.5 rounded-xl border p-3 text-sm font-medium ${
              satisfied === true
                ? "border-emerald-500 bg-emerald-50 text-emerald-800"
                : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
            <ThumbsUp className="h-4 w-4" /> Sudah beres
          </button>
          <button type="button" data-testid={T.portalAckNo}
            onClick={() => setSatisfied(false)}
            className={`flex items-center justify-center gap-1.5 rounded-xl border p-3 text-sm font-medium ${
              satisfied === false
                ? "border-rose-500 bg-rose-50 text-rose-800"
                : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
            <ThumbsDown className="h-4 w-4" /> Belum beres
          </button>
        </div>

        <div className="mt-3 space-y-1">
          <label className="text-xs font-medium" htmlFor="ack-note">
            Catatan {satisfied === false ? "(wajib)" : "(opsional)"}
          </label>
          <textarea id="ack-note" data-testid={T.portalAckNote} rows={3} value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={satisfied === false
              ? "mis. bocornya berkurang tapi masih menetes saat hujan besar"
              : "mis. sudah rapi, terima kasih"}
            className="w-full rounded-lg border bg-white px-3 py-2 text-sm" />
        </div>

        {satisfied === false ? (
          <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
            Klaim TIDAK akan ditutup. Ia dikembalikan ke pengerjaan dan tim yang menangani
            langsung diberi tahu.
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button type="button" data-testid={T.portalAckCancel} onClick={() => onOpenChange(false)}
            disabled={busy}
            className="rounded-lg border px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            Batal
          </button>
          <button type="button" data-testid={T.portalAckSubmit} onClick={submit} disabled={busy}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
            {busy ? "Menyimpan…" : "Kirim tanggapan"}
          </button>
        </div>
      </div>
    </div>
  );
}
