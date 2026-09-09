import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, FileCheck2, Loader2, Upload, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import StatusPill from "@/components/patterns/StatusPill";
import { PanelStateView } from "@/components/patterns/StateViews";
import api, { API, TOKEN_KEY } from "@/services/apiClient";
import { classifyRequestError } from "@/utils/panelLoad";
import { formatDateTimeWIB } from "@/utils/formatters";
import { DOCCHK } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";
import { useAuth } from "@/context/AuthContext";

const TONE = {
  verified: "completed", pending: "pending", rejected: "rejected", missing: "low",
};

/**
 * DocChecklist — checklist dokumen syarat untuk SATU entitas (lead / pelanggan / mitra).
 *
 * Mengapa ada: master `doc_requirements` (Fase 39) sudah bisa diatur admin di Pusat
 * Konfigurasi, tetapi tidak pernah tampil di layar kerja siapa pun. Akibatnya syarat
 * dokumen hanya jadi daftar di database — sales tidak tahu berkas apa yang kurang, dan
 * `doc_submissions` tidak mungkin terisi karena tidak ada satu pun form yang menulisnya.
 *
 * Konteks (tahap lead, skema KPR, legal pelanggan) TIDAK dihitung di sini: komponen hanya
 * mengirim entitasnya dan backend (`doc_registry.contexts_for`) yang menentukan syarat
 * mana yang berlaku — supaya aturannya tidak punya dua versi.
 *
 * `canVerify` default mengikuti IZIN NYATA pengguna (`documents.verify` dari `/auth/me`),
 * bukan ditebak dari peran: sales yang MENGUNGGAH berkas tidak boleh memverifikasi
 * berkasnya sendiri (`docs/v2/24_CRM_LEAD_SPEC.md` §13).
 */
export default function DocChecklist({
  entityType, entityId, canVerify, onChanged, className = "",
}) {
  const { labelOf } = useReference();
  const { can } = useAuth();
  const mayVerify = canVerify === undefined ? can("documents", "verify") : canVerify;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState(null);
  const [busyCode, setBusyCode] = useState("");
  const [rejectFor, setRejectFor] = useState(null);
  const [reason, setReason] = useState("");
  // Satu input berkas PER BARIS syarat. Dulu ada SATU input tersembunyi bersama +
  // `pickFor` (ref) yang diisi saat tombol diklik: bila berkas dipilih tanpa lewat tombol,
  // handler diam-diam berhenti — cacat gagal-senyap yang nyata (dan membuat alur ini tak
  // bisa diuji otomatis). Sekarang kode syarat dibawa langsung oleh elemennya.
  const fileRefs = useRef({});

  const load = useCallback(async () => {
    if (!entityId) return;
    setLoading(true); setPanel(null);
    try {
      const res = await api.get("/doc/matrix", {
        params: { entity_type: entityType, entity_id: entityId },
      });
      setData(res.data.data);
    } catch (e) {
      // Fase 52 — 403 di sini BUKAN "gagal memuat" dan pesan teknisnya ("tidak memiliki izin
      // 'view' pada 'documents'") tidak berguna bagi pemakai. Panel ini dipakai di dalam
      // halaman profil lead & pelanggan, jadi ia harus bercerita sendiri tanpa membocorkan
      // nama izin internal dan tanpa berpura-pura checklist-nya kosong.
      setPanel(classifyRequestError(e));
    } finally { setLoading(false); }
  }, [entityType, entityId]);

  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  const onPick = async (e, code) => {
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;
    if (!code) { toast.error("Syarat dokumen tidak dikenali — muat ulang halaman."); return; }
    setBusyCode(code);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("owner_type", entityType);
      fd.append("owner_id", entityId);
      // Berkas syarat adalah BUKTI: disimpan utuh, tanpa kompresi/watermark.
      fd.append("optimize", "false");
      const up = await api.post("/files/upload", fd);
      const fileId = up.data?.data?.id;
      if (!fileId) throw new Error("unggah gagal");
      await api.post("/doc/submissions", {
        requirement_code: code, entity_type: entityType, entity_id: entityId,
        file_id: fileId,
      });
      toast.success(`Dokumen ${code} terunggah — menunggu verifikasi.`);
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal mengunggah dokumen.");
    } finally {
      setBusyCode("");
      if (input) input.value = "";
    }
  };

  const doVerify = async (sub) => {
    setBusyCode(sub.requirement_code);
    try {
      await api.post(`/doc/submissions/${sub.id}/verify`);
      toast.success(`${sub.requirement_label} diverifikasi.`);
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal memverifikasi.");
    } finally { setBusyCode(""); }
  };

  const doReject = async () => {
    if (!reason.trim()) { toast.error("Alasan penolakan wajib diisi."); return; }
    setBusyCode(rejectFor.requirement_code);
    try {
      await api.post(`/doc/submissions/${rejectFor.id}/reject`, { reason: reason.trim() });
      toast.success("Dokumen ditolak — pemilik berkas diminta mengunggah ulang.");
      setRejectFor(null); setReason("");
      refresh();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Gagal menolak dokumen.");
    } finally { setBusyCode(""); }
  };

  const fileUrl = (fid) => `${API}/files/${fid}?auth=${localStorage.getItem(TOKEN_KEY)}`;
  const counts = data?.counts || {};
  const rows = data?.rows || [];

  return (
    <section data-testid={DOCCHK.panel} data-entity={entityId}
      className={`rounded-xl border bg-card p-4 ${className}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <FileCheck2 className="h-4 w-4 text-primary" /> Checklist Dokumen Syarat
        </h3>
        {data ? (
          <span data-testid={DOCCHK.completeBadge} data-complete={String(!!data.complete)}
            data-empty={String((data.rows || []).length === 0)}>
            {/* Jangan mengaku "lengkap" saat memang BELUM ADA syaratnya: `complete` bernilai
                true untuk daftar kosong (tidak ada syarat wajib yang gagal), dan itu terbaca
                seolah berkas pemesan sudah beres. */}
            {(data.rows || []).length === 0 ? (
              <StatusPill status="info" label="Belum ada syarat pada tahap ini" />
            ) : (
              <StatusPill status={data.complete ? "completed" : "pending"}
                label={data.complete ? "Syarat wajib lengkap" : "Syarat wajib belum lengkap"} />
            )}
          </span>
        ) : null}
      </div>

      {loading ? (
        <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Memuat checklist…
        </p>
      ) : panel ? (
        <PanelStateView panel={panel} subject="Checklist dokumen syarat" onRetry={load}
          whoMay={"Berkas syarat dibuka untuk tim Sales, Marketing Admin, dan Keuangan; "
            + "verifikasinya dipegang peran selain pengunggah."} />
      ) : (
        <>
          <div data-testid={DOCCHK.summary}
            className="mb-3 flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="rounded-full border bg-secondary px-2 py-0.5">
              {counts.required || 0} wajib
            </span>
            <span className="rounded-full border px-2 py-0.5 text-emerald-700">
              {counts.verified || 0} terverifikasi
            </span>
            <span className="rounded-full border px-2 py-0.5 text-amber-700">
              {counts.pending || 0} menunggu
            </span>
            <span className="rounded-full border px-2 py-0.5 text-rose-700">
              {counts.rejected || 0} ditolak
            </span>
            <span className="rounded-full border px-2 py-0.5 text-muted-foreground">
              {counts.missing || 0} belum ada
            </span>
            {(data?.contexts || []).map((c) => (
              <span key={c} data-testid={DOCCHK.contextChip} data-context={c}
                className="rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-primary">
                {labelOf("doc_context", c)}
              </span>
            ))}
          </div>

          {rows.length === 0 ? (
            <p data-testid={DOCCHK.empty}
              className="rounded-lg border border-dashed bg-secondary/40 px-3 py-4 text-xs text-muted-foreground">
              Belum ada syarat dokumen untuk konteks ini
              {(data?.contexts || []).length
                ? ` (${(data.contexts || []).map((c) => labelOf("doc_context", c)).join(", ")})`
                : ""}.
              Syarat muncul begitu entitas masuk tahap yang membutuhkannya; daftar syarat
              diatur di <b>Pusat Konfigurasi → Dokumen Syarat</b>.
            </p>
          ) : (
            <div className="space-y-2">
              {rows.map((r) => {
                const req = r.requirement || {};
                const latest = (r.submissions || [])[0];
                const busy = busyCode === req.code;
                return (
                  <div key={req.code} data-testid={DOCCHK.row} data-requirement={req.code}
                    data-status={r.status}
                    className="rounded-lg border bg-background p-2.5">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-medium">
                          {req.label}
                          {req.mandatory ? (
                            <span className="ml-1.5 rounded border border-rose-200 bg-rose-50 px-1 py-0.5 text-[10px] font-semibold text-rose-700">
                              WAJIB
                            </span>
                          ) : (
                            <span className="ml-1.5 rounded border bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
                              opsional
                            </span>
                          )}
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          {req.code}{req.group ? ` · ${req.group}` : ""}
                          {req.conditional_note ? ` · ${req.conditional_note}` : ""}
                        </p>
                      </div>
                      <span data-testid={DOCCHK.status} data-requirement={req.code}>
                        <StatusPill status={r.status} tone={TONE[r.status] || "low"}
                          label={r.status_label} />
                      </span>
                    </div>

                    {latest ? (
                      <div className="mt-2 rounded-md border bg-secondary/50 px-2 py-1.5 text-[11px]">
                        <a data-testid={DOCCHK.fileLink} data-requirement={req.code}
                          href={fileUrl(latest.file_id)} target="_blank" rel="noreferrer"
                          className="font-medium text-primary underline-offset-2 hover:underline">
                          {latest.file?.original_filename || "Lihat berkas"}
                        </a>
                        <span className="text-muted-foreground">
                          {" "}· diunggah {formatDateTimeWIB(latest.created_at)} oleh{" "}
                          {latest.created_by || "-"}
                        </span>
                        {latest.verified_at ? (
                          <span className="block text-emerald-700">
                            Diverifikasi {formatDateTimeWIB(latest.verified_at)} oleh{" "}
                            {latest.verified_by}
                          </span>
                        ) : null}
                        {latest.reject_reason ? (
                          <span className="block text-rose-700">
                            Ditolak: {latest.reject_reason}
                          </span>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <input ref={(el) => { fileRefs.current[req.code] = el; }}
                        data-testid={DOCCHK.uploadInput} data-requirement={req.code}
                        type="file" className="hidden" accept="image/*,application/pdf"
                        aria-label={`Berkas ${req.label}`}
                        onChange={(e) => onPick(e, req.code)} />
                      <Button data-testid={DOCCHK.uploadBtn} data-requirement={req.code}
                        aria-label={`Unggah berkas ${req.label}`} size="sm" variant="outline"
                        disabled={busy} onClick={() => fileRefs.current[req.code]?.click()}>
                        {busy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                          : <Upload className="mr-1.5 h-3.5 w-3.5" />}
                        {latest ? "Unggah ulang" : "Unggah"}
                      </Button>
                      {mayVerify && latest && latest.status === "pending" ? (
                        <>
                          <Button data-testid={DOCCHK.verifyBtn} data-requirement={req.code}
                            aria-label={`Verifikasi ${req.label}`} size="sm" disabled={busy}
                            onClick={() => doVerify(latest)}>
                            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Verifikasi
                          </Button>
                          <Button data-testid={DOCCHK.rejectBtn} data-requirement={req.code}
                            aria-label={`Tolak ${req.label}`} size="sm" variant="outline"
                            disabled={busy} onClick={() => { setRejectFor(latest); setReason(""); }}>
                            <XCircle className="mr-1.5 h-3.5 w-3.5" /> Tolak
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      <Dialog open={!!rejectFor} onOpenChange={(v) => !v && setRejectFor(null)}>
        <DialogContent className="bg-background">
          <DialogHeader>
            <DialogTitle>Tolak dokumen {rejectFor?.requirement_label}</DialogTitle>
            <DialogDescription>
              Alasan disimpan pada riwayat dokumen beserta nama Anda, dan terlihat oleh
              pengunggah agar bisa memperbaiki berkasnya.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="docchk-reason">Alasan penolakan</Label>
            <Textarea id="docchk-reason" data-testid={DOCCHK.rejectReason} rows={3}
              className="bg-background" value={reason}
              placeholder="Contoh: KTP tidak terbaca / masa berlaku habis"
              onChange={(e) => setReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectFor(null)}>Batal</Button>
            <Button data-testid={DOCCHK.rejectSubmit} onClick={doReject}
              disabled={!reason.trim() || !!busyCode}>
              Tolak dokumen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
