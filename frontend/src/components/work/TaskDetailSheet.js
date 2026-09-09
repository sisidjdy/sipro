import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ExternalLink, HardHat, Play, Send, ShieldCheck, RotateCcw, UserCog, Info, Camera } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import PhotoUploader from "@/components/patterns/PhotoUploader";
import EvidenceUploader from "@/components/patterns/EvidenceUploader";
import AssignTaskDialog from "@/components/work/AssignTaskDialog";
import { formatDateTimeWIB, dueLabel } from "@/utils/formatters";
import { photoSrc } from "@/utils/photoSrc";
import api from "@/services/apiClient";
import { WORK } from "@/constants/testIds";

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value || "—"}</span>
    </div>
  );
}

/**
 * TaskDetailSheet — satu tempat untuk MENGERJAKAN tugas, bukan sekadar melihatnya.
 *
 * Sebelum Fase 29 sebuah tugas hanya bisa "diselesaikan" atau "ditunda" tanpa bukti dan
 * tanpa tautan ke data terkait. Di sini staf melihat apa yang diminta jobdesk (bukti apa,
 * siapa yang memverifikasi), melampirkan bukti, lalu mengajukannya; supervisor bisa
 * memverifikasi, mengembalikan dengan alasan, atau mengalihkan tugas.
 */
export default function TaskDetailSheet({ taskId, open, onOpenChange, onChanged }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState([]);
  const [waNote, setWaNote] = useState("");
  const [waEvidence, setWaEvidence] = useState([]);
  const [reason, setReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const res = await api.get(`/work/tasks/${taskId}`);
      setData(res.data.data);
      setNote(""); setPhotos([]); setReason(""); setShowReject(false);
      setWaNote(""); setWaEvidence([]);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal memuat detail tugas.");
    } finally { setLoading(false); }
  }, [taskId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const t = data?.task;
  const jd = data?.jobdesk;
  const refresh = () => { load(); onChanged && onChanged(); };

  const act = async (fn, okMsg) => {
    setBusy(true);
    try {
      const res = await fn();
      toast.success(res?.data?.message || okMsg);
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aksi gagal.");
    } finally { setBusy(false); }
  };

  if (!taskId) return null;
  const needsProof = (t?.proof_kind || "none") !== "none";
  const isOpenState = ["open", "snoozed"].includes(t?.status);
  // Fase 32: pekerjaan konstruksi punya penjaga sendiri (foto minimal, checklist mutu,
  // urutan pekerjaan, progres berbobot) sehingga TIDAK boleh diselesaikan dari sini.
  const buildItem = t?.meta?.build_item_id;
  const canSubmit = !buildItem && data?.can_work
    && ["open", "in_progress", "snoozed"].includes(t?.status);
  const canVerify = !buildItem && data?.can_verify && t?.status === "submitted";
  const canWaManual = canSubmit && t?.related_entity_type === "lead" && t?.related_entity_id
    && ["contact", "follow_up"].includes(t?.type);
  const due = t?.due_date ? dueLabel(t.due_date) : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent data-testid={WORK.taskDetail}
        className="w-full overflow-y-auto bg-background sm:max-w-lg">
        {loading || !t ? (
          <>
            <SheetHeader>
              <SheetTitle className="text-base">Detail tugas</SheetTitle>
              <SheetDescription>Memuat detail pekerjaan…</SheetDescription>
            </SheetHeader>
            <div className="py-10 text-center text-sm text-muted-foreground">Memuat…</div>
          </>
        ) : (
          <>
            <SheetHeader className="sticky top-0 z-10 -mx-6 border-b bg-background px-6 pb-3">
              <SheetTitle className="pr-6 text-base leading-snug">{t.title}</SheetTitle>
              <SheetDescription>
                {jd?.code ? `${jd.code} · ` : ""}
                {t.division ? (
                  <><RefLabel group="division" value={t.division} />{due?.text ? " · " : ""}</>
                ) : null}
                {due?.text || ""}
                {!jd?.code && !t.division && !due?.text ? "Detail tugas" : ""}
              </SheetDescription>
            </SheetHeader>

            <div className="mt-4 space-y-4 pb-24">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill status={t.status} group="task_status" />
                <StatusPill status={t.priority} group="priority" />
                {t.review !== "none" ? (
                  <StatusPill status={t.review} group="task_review" />
                ) : null}
                {t.sla_breached ? <StatusPill status="overdue" label="SLA lewat" /> : null}
              </div>

              {t.description ? (
                <p className="rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow-card)]">{t.description}</p>
              ) : null}

              <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                  <Info className="h-3.5 w-3.5" /> Aturan jobdesk
                </p>
                <Row label="Sumber tugas"
                  value={jd?.source ? <RefLabel group="jobdesk_source" value={jd.source} /> : "—"} />
                <Row label="Penerima" value={t.assigned_to} />
                <Row label="Ditugaskan oleh" value={t.assigned_by || "sistem"} />
                <Row label="Bukti wajib"
                  value={<RefLabel group="proof_kind" value={t.proof_kind || "none"} />} />
                <Row label="Verifikasi"
                  value={<RefLabel group="verify_mode" value={t.verify_mode || "none"} />} />
                <Row label="Jatuh tempo" value={formatDateTimeWIB(t.due_date)} />
                {data?.related ? (
                  <Row label="Kaitan" value={
                    <span data-testid="task-related-entity">
                      {data.related.label}: {data.related.name}
                    </span>} />
                ) : null}
                {(t.link || data?.related?.link) ? (
                  <Button variant="outline" size="sm" className="mt-2 w-full"
                    data-testid={WORK.taskLinkBtn}
                    onClick={() => navigate(t.link || data.related.link)}>
                    <ExternalLink className="mr-1.5 h-4 w-4" /> Buka halaman kerja
                  </Button>
                ) : null}
              </div>

              {t.rejected_reason && t.review === "rejected" ? (
                <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
                  <span className="font-semibold">Dikembalikan supervisor:</span> {t.rejected_reason}
                </p>
              ) : null}
              {t.verify_note ? (
                <p className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
                  <span className="font-semibold">Catatan verifikasi:</span> {t.verify_note}
                </p>
              ) : null}

              {(t.proof || []).length ? (
                <div className="rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                  <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                    Bukti kerja terlampir ({t.proof.length})
                  </p>
                  <div className="space-y-2">
                    {t.proof.filter((p) => p.kind === "note").map((p, i) => (
                      <p key={`n${i}`} className="rounded-md bg-secondary/60 px-2.5 py-1.5 text-xs">
                        {p.value}
                      </p>
                    ))}
                    <div className="grid grid-cols-3 gap-1.5">
                      {t.proof.filter((p) => p.kind === "photo").map((p, i) => (
                        <img key={`p${i}`} src={photoSrc({ file_id: p.value })} alt="Bukti kerja"
                          className="h-20 w-full rounded-md border bg-secondary object-cover" />
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}

              {buildItem ? (
                <div data-testid={WORK.taskBuildRedirect}
                  className="space-y-2 rounded-xl border border-sky-200 bg-sky-50 p-3">
                  <p className="text-sm font-semibold text-sky-900">
                    Pekerjaan konstruksi dikerjakan di Papan Mandor
                  </p>
                  <p className="text-[11px] text-sky-900">
                    Di sana Anda mengambil foto bukti langsung dari lokasi, menjawab
                    checklist mutu, dan sistem memeriksa urutan pekerjaan sebelum progres
                    rumah naik. Instruksi lengkapnya sudah tertulis pada tugas ini.
                  </p>
                  <Button size="sm" data-testid={WORK.taskBuildOpenBtn}
                    onClick={() => navigate(t.link || "/construction?tab=board")}>
                    <HardHat className="mr-1.5 h-4 w-4" /> Buka & ajukan hasil
                  </Button>
                </div>
              ) : null}

              {canWaManual ? (
                <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50/50 p-3">
                  <p className="flex items-center gap-1.5 text-sm font-semibold text-amber-900">
                    <Camera className="h-4 w-4" /> Chat lewat WA pribadi (di luar sistem)?
                  </p>
                  <p className="text-[11px] text-amber-900/80">
                    Catat di sini dengan tangkapan layar percakapan sebagai bukti — tugas
                    ini langsung ditutup tervalidasi, chat masuk ke thread WA lead, dan
                    kontak pertama tercatat bila belum ada.
                  </p>
                  <Textarea data-testid={WORK.taskWaManualNote} rows={2} value={waNote}
                    onChange={(e) => setWaNote(e.target.value)}
                    placeholder="Ringkasan chat, mis. Sudah di-follow-up via WA pribadi, minta jadwal survey Sabtu" />
                  <EvidenceUploader value={waEvidence} onChange={setWaEvidence}
                    ownerType="lead_wa_manual" ownerId={t.related_entity_id} max={3}
                    accept="image/*" testId={WORK.taskWaManualEvidence}
                    hint="hanya foto/tangkapan layar percakapan · maks 8MB · disimpan utuh sebagai bukti."
                    label="Lampirkan tangkapan layar percakapan WA" />
                  <Button size="sm" variant="outline" className="w-full"
                    data-testid={WORK.taskWaManualBtn}
                    disabled={busy || !waNote.trim() || !waEvidence.length}
                    onClick={() => act(() => api.post(`/leads/${t.related_entity_id}/wa/manual`, {
                      note: waNote.trim(), evidence_file_ids: waEvidence, task_id: taskId,
                    }), "Chat WA manual tercatat — tugas ditutup dengan bukti.")}>
                    <Camera className="mr-1.5 h-4 w-4" /> Catat WA Manual & Tutup Tugas
                  </Button>
                </div>
              ) : null}

              {canSubmit ? (
                <div className="space-y-3 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                  <p className="text-sm font-semibold">Ajukan hasil kerja</p>
                  {isOpenState ? (
                    <Button variant="outline" size="sm" data-testid={WORK.taskStartBtn}
                      disabled={busy}
                      onClick={() => act(() => api.post(`/work/tasks/${taskId}/start`),
                                         "Tugas ditandai sedang dikerjakan.")}>
                      <Play className="mr-1.5 h-4 w-4" /> Mulai Kerjakan
                    </Button>
                  ) : null}
                  <div className="space-y-1.5">
                    <Label>Catatan hasil kerja{needsProof ? " (wajib)" : ""}</Label>
                    <Textarea data-testid={WORK.taskSubmitNote} rows={3} value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Tulis apa yang Anda kerjakan & hasilnya…" />
                  </div>
                  {["photo", "document"].includes(t.proof_kind) ? (
                    <div className="space-y-1.5">
                      <Label>Lampiran bukti ({t.proof_kind === "photo" ? "foto" : "dokumen"})</Label>
                      <PhotoUploader value={photos} onChange={setPhotos} ownerType="task"
                        ownerId={taskId} max={4} testId={WORK.taskSubmitPhotos}
                        watermark={t.title ? `Bukti kerja: ${t.title}` : null}
                        label="Unggah bukti" />
                    </div>
                  ) : null}
                  <Button className="w-full" data-testid={WORK.taskSubmitBtn} disabled={busy}
                    onClick={() => act(() => api.post(`/work/tasks/${taskId}/submit`, {
                      note: note || null, photos,
                      documents: t.proof_kind === "document" ? photos : [],
                    }), "Hasil kerja diajukan.")}>
                    <Send className="mr-1.5 h-4 w-4" /> Ajukan Hasil
                  </Button>
                  <p className="text-[11px] text-muted-foreground">
                    {t.verify_mode === "supervisor"
                      ? "Hasil akan diperiksa supervisor divisi Anda."
                      : t.verify_mode === "system"
                        ? "Sistem akan memeriksa bukti pada data; bila belum ada, tugas menunggu verifikasi supervisor."
                        : "Tugas ini langsung selesai setelah diajukan."}
                  </p>
                </div>
              ) : null}

              {data?.can_verify ? (
                <div className="space-y-2 rounded-xl border bg-card p-3 shadow-[var(--shadow-card)]">
                  <p className="text-sm font-semibold">Tindakan supervisor</p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" data-testid={WORK.taskVerifyBtn} disabled={busy || !canVerify}
                      onClick={() => act(() => api.post(`/work/tasks/${taskId}/verify`,
                                                        { note: note || null }),
                                         "Tugas diverifikasi.")}>
                      <ShieldCheck className="mr-1.5 h-4 w-4" /> Verifikasi
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy || !canVerify}
                      onClick={() => setShowReject((v) => !v)}>
                      <RotateCcw className="mr-1.5 h-4 w-4" /> Kembalikan
                    </Button>
                    <Button size="sm" variant="outline" data-testid={WORK.taskAssignBtn}
                      disabled={busy} onClick={() => setAssignOpen(true)}>
                      <UserCog className="mr-1.5 h-4 w-4" /> Alihkan
                    </Button>
                  </div>
                  {!canVerify ? (
                    <p className="text-[11px] text-muted-foreground">
                      Verifikasi tersedia setelah staf mengajukan hasil kerja.
                    </p>
                  ) : null}
                  {showReject ? (
                    <div className="space-y-1.5">
                      <Label htmlFor="taskdetailsheet-alasan-pengembalian">Alasan pengembalian</Label>
                      <Textarea id="taskdetailsheet-alasan-pengembalian" data-testid={WORK.taskRejectReason} rows={2} value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Jelaskan apa yang perlu diperbaiki…" />
                      <Button size="sm" variant="destructive" data-testid={WORK.taskRejectBtn}
                        disabled={busy || reason.trim().length < 3}
                        onClick={() => act(() => api.post(`/work/tasks/${taskId}/reject`,
                                                          { reason }), "Tugas dikembalikan.")}>
                        Kirim pengembalian
                      </Button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>

            <AssignTaskDialog open={assignOpen} onOpenChange={setAssignOpen} taskId={taskId}
              division={t.division} onDone={refresh} />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
