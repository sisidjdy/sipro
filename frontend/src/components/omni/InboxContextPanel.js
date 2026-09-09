import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { UserRound, ArrowRight, CalendarPlus, ExternalLink, Sparkles, Send, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import RefLabel from "@/components/patterns/RefLabel";
import api from "@/services/apiClient";
import WaCaptureDialog from "@/components/wa/WaCaptureDialog";
import { INBOX, P94 } from "@/constants/testIds";

const NEXT_STAGE = {
  acquisition: "nurturing", nurturing: "appointment", appointment: "booking", booking: "won",
};

export default function InboxContextPanel({ leadId, conversationId, contactPhone, onChanged }) {
  const navigate = useNavigate();
  const [captureOpen, setCaptureOpen] = useState(false);
  const [lead, setLead] = useState(null);
  const [nba, setNba] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!leadId) { setLead(null); return; }
    setLoading(true);
    try {
      const res = await api.get(`/leads/${leadId}`);
      setLead(res.data.data);
    } catch { setLead(null); }
    finally { setLoading(false); }
  }, [leadId]);
  useEffect(() => { load(); }, [load]);

  const loadNba = useCallback(async () => {
    if (!conversationId) { setNba(null); return; }
    try {
      const res = await api.get(`/inbox/${conversationId}/nba`);
      setNba(res.data.data);
    } catch { setNba(null); }
  }, [conversationId]);
  useEffect(() => { loadNba(); }, [loadNba]);

  const advance = async () => {
    if (!lead) return;
    const next = NEXT_STAGE[lead.stage];
    if (!next) { toast.info("Tidak ada stage lanjutan."); return; }
    setBusy(true);
    try {
      await api.post(`/leads/${lead.id}/stage`, { stage: next, note: "Dimajukan dari Inbox (NBA)" });
      toast.success(`Stage lead dimajukan ke ${next}.`);
      await load(); await loadNba();
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memajukan stage."); }
    finally { setBusy(false); }
  };

  const sendTemplate = async (code) => {
    if (!conversationId || !code) return;
    setBusy(true);
    try {
      await api.post(`/inbox/${conversationId}/messages`, { body: "", direction: "out", template_code: code });
      toast.success("Template terkirim (simulasi).");
      await loadNba();
      onChanged && onChanged();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim template."); }
    finally { setBusy(false); }
  };

  const runSuggestion = (s) => {
    if (s.type === "send_template") return sendTemplate(s.template_code);
    if (s.type === "advance_stage") return advance();
    return null;
  };

  if (!leadId) {
    return (
      <div data-testid={INBOX.contextPanel} className="space-y-3 rounded-xl border bg-card p-4 text-sm shadow-[var(--shadow-card)]">
        <p className="text-muted-foreground">Percakapan ini belum tertaut ke lead.</p>
        {contactPhone ? (
          <>
            <p className="text-xs text-muted-foreground">Nomor {contactPhone} akan dicek duplikatnya terhadap lead & customer lama sebelum dibuat.</p>
            <Button data-testid={P94.convCaptureBtn} size="sm" onClick={() => setCaptureOpen(true)}>
              <UserRound className="mr-1.5 h-4 w-4" /> Jadikan lead
            </Button>
            <WaCaptureDialog open={captureOpen} onOpenChange={setCaptureOpen}
              target={{ phones: [contactPhone], count: 1 }}
              onDone={() => { setCaptureOpen(false); onChanged?.(); }} />
          </>
        ) : null}
      </div>
    );
  }
  if (loading) return <div className="rounded-xl border bg-card p-4 text-sm text-muted-foreground shadow-[var(--shadow-card)]">Memuat konteks…</div>;
  if (!lead) return <div className="rounded-xl border bg-card p-4 text-sm text-muted-foreground shadow-[var(--shadow-card)]">Lead tidak ditemukan.</div>;

  const attr = lead.attribution || {};
  const next = NEXT_STAGE[lead.stage];
  const intents = nba?.intents || [];
  const suggestions = nba?.suggestions || [];

  return (
    <div data-testid={INBOX.contextPanel} className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-2">
        <UserRound className="h-4 w-4 text-primary" />
        <p className="font-medium">{lead.name}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={lead.stage} group="lead_stage" />
        {lead.score_band ? <StatusPill status={lead.score_band} group="score_band" /> : null}
        <span className="text-xs text-muted-foreground">Skor {lead.score ?? "-"}</span>
      </div>
      <dl className="space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between gap-2"><dt>Telepon</dt><dd className="text-foreground">{lead.phone || "-"}</dd></div>
        <div className="flex justify-between gap-2"><dt>Sumber</dt><dd className="text-foreground"><RefLabel group="lead_source" value={lead.source} /></dd></div>
        <div className="flex justify-between gap-2"><dt>Campaign</dt><dd className="text-foreground">{lead.campaign || "-"}</dd></div>
        {attr.creative_id ? (
          <div className="flex justify-between gap-2"><dt>Creative</dt><dd className="text-foreground">{attr.creative_id}</dd></div>
        ) : null}
      </dl>

      {/* Detected intents from the last inbound message */}
      {intents.length ? (
        <div className="space-y-1.5 border-t pt-3">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <Tag className="h-3.5 w-3.5" /> Intent terdeteksi
          </p>
          <div className="flex flex-wrap gap-1.5">
            {intents.map((it) => (
              <span key={it} data-testid={INBOX.nbaIntent}
                className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium capitalize text-primary">
                {it}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-2 border-t pt-3">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" /> Next Best Action
        </p>

        {/* Dynamic, intent-driven suggestions from the backend */}
        {suggestions.map((s, i) => (
          <Button key={i} data-testid={s.type === "send_template" ? INBOX.nbaTemplateSend : INBOX.nbaSuggestion}
            size="sm" variant={s.type === "send_template" ? "default" : "outline"}
            className="w-full justify-start" onClick={() => runSuggestion(s)} disabled={busy}>
            {s.type === "send_template"
              ? <Send className="mr-1.5 h-4 w-4" />
              : <ArrowRight className="mr-1.5 h-4 w-4" />}
            {s.label}
          </Button>
        ))}

        {/* Always-available manual actions */}
        <Button data-testid={INBOX.nbaStage} size="sm" variant="outline" className="w-full justify-start"
          onClick={advance} disabled={busy || !next}>
          <ArrowRight className="mr-1.5 h-4 w-4" /> {next ? `Majukan ke ${next}` : "Stage final"}
        </Button>
        <Button data-testid={INBOX.nbaAppointment} size="sm" variant="ghost" className="w-full justify-start"
          onClick={() => navigate("/appointments")}>
          <CalendarPlus className="mr-1.5 h-4 w-4" /> Buat Agenda / Survey
        </Button>
        <Button size="sm" variant="ghost" className="w-full justify-start" onClick={() => navigate("/leads")}>
          <ExternalLink className="mr-1.5 h-4 w-4" /> Buka detail Lead
        </Button>
      </div>
    </div>
  );
}
