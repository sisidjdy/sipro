import React, { useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle, CheckCircle2, ClipboardCheck, FileText, History, ShieldQuestion,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import EvidenceUploader from "@/components/patterns/EvidenceUploader";
import { formatDateTimeWIB } from "@/utils/formatters";
import { fileUrl } from "@/utils/photoSrc";
import api from "@/services/apiClient";
import { LEADS } from "@/constants/testIds";

/**
 * LeadSlikPanel — pra-skrining BI/SLIK sebagai GERBANG BERBUKTI sebelum Booking.
 *
 * Kejujuran yang dipaksakan di layar ini (bukan sekadar tulisan):
 *   * hasil yang MELOLOSKAN lead (Clear/Perlu review) tidak bisa disimpan tanpa lampiran
 *     iDeb — tombolnya mati sampai buktinya diunggah;
 *   * hasil Ditolak wajib beralasan, menahan lead, dan langsung memunculkan tugas tindak
 *     lanjut + jalan keluar (tutup lead dengan alasan "KPR/pembiayaan tidak lolos");
 *   * seluruh pemeriksaan tersimpan sebagai riwayat yang bisa dibuka lampirannya.
 */
export default function LeadSlikPanel({ lead, lifecycle, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const slik = lifecycle?.slik || null;
  const options = lifecycle?.slik_options || [];
  const history = lifecycle?.slik_history || [];
  const task = lifecycle?.slik_followup_task || null;
  const needEvidence = evidence.length === 0;

  const names = {};
  (slik?.evidence || []).forEach((e) => { names[e.file_id] = e.filename || e.content_type; });

  const submit = async (status) => {
    if (status === "rejected" && note.trim().length < 3) {
      toast.error("Tulis alasan penolakan (dipakai saat menutup lead).");
      return;
    }
    if (status !== "rejected" && needEvidence) {
      toast.error("Lampirkan bukti hasil iDeb SLIK lebih dulu.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post(`/leads/${lead.id}/slik-prescreen`, {
        status, note: note.trim() || null, evidence_file_ids: evidence,
      });
      const t = res.data?.followup_task;
      toast.success(t
        ? `Hasil tersimpan. Tugas tindak lanjut dibuat untuk ${t.assigned_to || "sales"}.`
        : "Hasil pra-skrining BI/SLIK tersimpan.");
      setNote("");
      setEvidence([]);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimpan hasil SLIK.");
    } finally { setBusy(false); }
  };

  const closeAsLost = async () => {
    setBusy(true);
    try {
      await api.post(`/leads/${lead.id}/stage`, {
        stage: "lost",
        note: `KPR/pembiayaan tidak lolos — SLIK ditolak: ${slik?.note || "tanpa catatan"}`,
      });
      toast.success("Lead ditutup: KPR/pembiayaan tidak lolos (tercatat di riwayat).");
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menutup lead.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={LEADS.slikPanel} className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
      <p className="mb-1 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
        <ShieldQuestion className="h-3.5 w-3.5 text-primary" /> Pra-skrining BI/SLIK
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold normal-case text-amber-800">
          SIMULASI
        </span>
        {slik ? (
          <span data-testid={LEADS.slikStatus}
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium normal-case ${
              slik.holding ? "bg-rose-100 text-rose-800"
                : slik.status === "clear" ? "bg-emerald-100 text-emerald-800"
                  : "bg-amber-100 text-amber-900"}`}>
            {slik.label || slik.status}
          </span>
        ) : null}
      </p>
      <p className="mb-2 text-[11px] text-muted-foreground">
        Wajib sebelum lead naik ke tahap Booking. Hasil <b>Clear</b>/<b>Perlu review</b> harus
        dilampiri bukti iDeb (tangkapan layar/PDF); hasil <b>Ditolak</b> wajib beralasan dan
        menahan lead. OJK tidak menyediakan API publik, jadi hasil dicatat manual dari kanal
        resmi — laporan tetap jujur karena buktinya ikut tersimpan.
      </p>

      {slik?.evidence?.length ? (
        <div data-testid={LEADS.slikEvidenceList} className="mb-2 flex flex-wrap gap-1.5">
          {slik.evidence.map((e) => (
            <a key={e.file_id} href={fileUrl(e.file_id)} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 rounded-full border bg-secondary px-2 py-1 text-[11px] hover:underline">
              <FileText className="h-3.5 w-3.5 text-primary" />
              <span className="max-w-[170px] truncate">{e.filename || "Bukti iDeb"}</span>
            </a>
          ))}
        </div>
      ) : null}

      {slik?.holding ? (
        <div data-testid={LEADS.slikRejectedAlert}
          className="mb-2 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-900">
          <p className="flex items-center gap-1.5 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" /> SLIK ditolak — lead tertahan di bawah Booking
          </p>
          <p className="mt-1">Alasan: {slik.note || "-"}</p>
          {task ? (
            <p data-testid={LEADS.slikTask} className="mt-1">
              Tugas tindak lanjut: <b>{task.title}</b> → {task.assigned_to || "-"}
              {task.due_date ? ` · tenggat ${formatDateTimeWIB(task.due_date)}` : ""}
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" variant="destructive" disabled={busy}
              data-testid={LEADS.slikCloseLead} onClick={closeAsLost}>
              Tutup lead: KPR/pembiayaan tidak lolos
            </Button>
            <span className="text-[11px]">
              atau tawarkan skema tunai bertahap lalu periksa ulang di bawah.
            </span>
          </div>
        </div>
      ) : null}

      <div className="space-y-2 rounded-lg border bg-secondary/30 p-2.5">
        <div className="space-y-1.5">
          <Label htmlFor="slik-note" className="text-[11px]">
            Catatan hasil pemeriksaan (wajib bila ditolak)
          </Label>
          <Textarea id="slik-note" data-testid={LEADS.slikNote} rows={2} value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="mis. Kolektibilitas 1, tidak ada tunggakan · atau: kol-4 di 2 bank" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-[11px]">Bukti hasil iDeb SLIK</Label>
          <EvidenceUploader value={evidence} onChange={setEvidence} ownerType="lead"
            ownerId={lead.id} max={3} testId={LEADS.slikEvidenceInput}
            label="Unggah bukti iDeb SLIK" names={names} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {options.map((o) => {
            const blocked = o.value !== "rejected" && needEvidence;
            return (
              <Button key={o.value} size="sm" disabled={busy || blocked}
                variant={slik?.status === o.value ? "default" : "outline"}
                title={blocked ? "Lampirkan bukti iDeb terlebih dahulu" : undefined}
                data-testid={`${LEADS.slikOptionPrefix}-${o.value}`}
                onClick={() => submit(o.value)}>
                {o.value === "clear" ? <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> : null}
                {o.label}
              </Button>
            );
          })}
        </div>
        {needEvidence ? (
          <p className="text-[11px] text-amber-800">
            Tombol Clear/Perlu review terbuka setelah bukti iDeb dilampirkan.
          </p>
        ) : null}
      </div>

      {history.length ? (
        <div className="mt-2">
          <Button size="sm" variant="ghost" className="h-7 px-1.5 text-[11px]"
            data-testid={LEADS.slikHistoryToggle} onClick={() => setShowHistory((v) => !v)}>
            <History className="mr-1.5 h-3.5 w-3.5" />
            Riwayat pemeriksaan ({history.length})
          </Button>
          {showHistory ? (
            <div className="mt-1.5 space-y-1.5">
              {history.map((h, i) => (
                <div key={i} data-testid={LEADS.slikHistoryItem}
                  className="rounded-lg bg-secondary/50 px-2.5 py-1.5 text-[11px]">
                  <span className="font-medium text-foreground">{h.label || h.status}</span>
                  <span className="ml-1.5 text-muted-foreground">
                    {formatDateTimeWIB(h.checked_at)} · {h.checked_by}
                    {h.evidence_count ? ` · ${h.evidence_count} bukti` : " · tanpa bukti"}
                  </span>
                  {h.note ? <span className="block text-muted-foreground">{h.note}</span> : null}
                  {(h.evidence || []).length ? (
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {h.evidence.map((e) => (
                        <a key={e.file_id} href={fileUrl(e.file_id)} target="_blank" rel="noreferrer"
                          className="flex items-center gap-1 rounded border bg-card px-1.5 py-0.5 hover:underline shadow-[var(--shadow-card)]">
                          <ClipboardCheck className="h-3 w-3" />
                          <span className="max-w-[140px] truncate">{e.filename || "bukti"}</span>
                        </a>
                      ))}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
