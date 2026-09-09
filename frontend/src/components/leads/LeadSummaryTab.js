import React, { useState } from "react";
import { toast } from "sonner";
import { Phone, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import LeadLifecyclePanel from "@/components/sales/LeadLifecyclePanel";
import LeadScoreCard from "@/components/leads/LeadScoreCard";
import { PanelStateView } from "@/components/patterns/StateViews";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { LEADS, LEADPROFILE } from "@/constants/testIds";
import { useReference } from "@/context/ReferenceContext";

function Field({ label, value }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm">{value || "-"}</p>
    </div>
  );
}

/**
 * LeadSummaryTab — tab “Ringkasan” Profil Lead: data diri, minat, gerbang tahap (bukti),
 * langkah berikutnya (NBA), dan catatan.
 *
 * `LeadLifecyclePanel` dipakai ulang apa adanya (di dalamnya sudah ada gerbang bukti,
 * SLIK, dan riwayat tahap) supaya pemindahan dari drawer ke halaman TIDAK menghilangkan
 * satu pun fungsi yang sudah lulus uji pada fase sebelumnya.
 *
 * Fase 52 — `lifecyclePanel` adalah keadaan permintaan `GET /leads/{id}/lifecycle`. Bila
 * permintaan itu ditolak/gagal, HANYA gerbang tahapnya yang diganti kalimat jujur: data
 * lead & catatan cepat di tab ini tetap bisa dipakai. Sebelumnya kegagalan yang sama
 * mematikan seluruh halaman.
 */
export default function LeadSummaryTab({
  lead, lifecycle, lifecyclePanel = null, onAction, onChanged,
}) {
  const { labelOf } = useReference();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const firstContact = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/leads/${lead.id}/first-contact`);
      const rt = res.data.data?.response_time_minutes;
      toast.success(`Kontak pertama dicatat${rt != null ? ` (respons ${rt} menit)` : ""}.`);
      onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mencatat kontak pertama."); }
    finally { setBusy(false); }
  };

  const addComment = async () => {
    if (!comment.trim()) return;
    setBusy(true);
    try {
      await api.post("/activities", {
        entity_type: "lead", entity_id: lead.id, body: comment, type: "comment",
      });
      setComment("");
      toast.success("Catatan tersimpan.");
      onChanged?.();
    } catch (e) { toast.error("Gagal menambah catatan."); }
    finally { setBusy(false); }
  };

  const lifecycleBlocked = lifecyclePanel && !lifecyclePanel.ok;

  return (
    <div data-testid={LEADPROFILE.summary} className="space-y-4">
      <section className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-3 font-heading text-base font-semibold">Data lead</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Telepon" value={lead.phone} />
          <Field label="Email" value={lead.email} />
          <Field label="Sumber" value={labelOf("lead_source", lead.source)} />
          <Field label="Kampanye" value={lead.campaign} />
          <Field label="PIC (sales)" value={lead.assigned_to} />
          <Field label="Minat tipe unit" value={lead.interest_unit_type} />
          <Field label="Kontak pertama"
            value={lead.first_contact_at ? formatDateTimeWIB(lead.first_contact_at) : "Belum"} />
          <Field label="Waktu respons"
            value={lead.response_time_minutes != null
              ? `${lead.response_time_minutes} menit` : "-"} />
        </div>
        {!lead.first_contact_at ? (
          <Button data-testid={LEADS.firstContactBtn} size="sm" className="mt-4"
            onClick={firstContact} disabled={busy}>
            <Phone className="mr-1.5 h-4 w-4" /> Catat Kontak Pertama
          </Button>
        ) : null}
      </section>

      <LeadScoreCard lead={lead} onChanged={onChanged} />

      {lifecycleBlocked ? (
        <PanelStateView panel={lifecyclePanel} subject="Gerbang tahap & langkah berikutnya"
          onRetry={onChanged}
          whoMay={"Gerbang tahap lead dibuka untuk tim Sales, Manajer Sales, dan Marketing "
            + "Admin. Data lead dan catatan di bawah tetap bisa Anda pakai."} />
      ) : (
        <LeadLifecyclePanel lead={lead} lifecycle={lifecycle} onAction={onAction}
          onChanged={onChanged} />
      )}

      <section className="rounded-lg border bg-card p-4 shadow-[var(--shadow-card)]">
        <h2 className="mb-2 font-heading text-base font-semibold">Catatan cepat</h2>
        <Label htmlFor="lead-note" className="text-xs">Catatan untuk lead ini</Label>
        <div className="mt-1.5 flex gap-2">
          <Textarea id="lead-note" data-testid={LEADS.commentInput} rows={2}
            placeholder="Mis. minta dihubungi setelah jam 5 sore…" value={comment}
            onChange={(e) => setComment(e.target.value)} />
          <Button data-testid={LEADS.commentSubmit} size="icon" onClick={addComment}
            disabled={busy || !comment.trim()} aria-label="Kirim catatan">
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">
          Catatan masuk ke tab Timeline beserta nama penulisnya.
        </p>
      </section>
    </div>
  );
}
