import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Clock, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import { fromNow } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { P97 } from "@/constants/testIds";
import WaReplySuggestions from "@/components/wa/WaReplySuggestions";

const NONE = "__none__";

/** Balas kontak WA langsung dari antrean (tanpa pindah ke Inbox). Aturan sesi 24 jam sama dengan Inbox. */
export default function WaQuickReplyDialog({ contact, onOpenChange, onDone }) {
  const [data, setData] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [body, setBody] = useState("");
  const [tmpl, setTmpl] = useState(NONE);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!contact) return;
    setData(null); setBody(""); setTmpl(NONE);
    Promise.all([api.get(`/wa/contacts/${contact.id}/messages`), api.get("/wa-templates")])
      .then(([m, t]) => { setData(m.data.data); setTemplates((t.data.data || []).filter((x) => x.status === "approved")); })
      .catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat percakapan."));
  }, [contact]);

  const windowOpen = !!data?.window_open;
  const useTemplate = tmpl !== NONE;
  const canSend = useTemplate || (windowOpen && body.trim());

  // Saran: sesi terbuka → isi teks bebas (bisa disunting); tertutup → pilih template approved-nya.
  const pickSuggestion = (s) => {
    if (windowOpen) { setTmpl(NONE); setBody(s.body || ""); }
    else if (s.ready && s.template_code) { setTmpl(s.template_code); }
  };

  const send = async () => {
    setBusy(true);
    try {
      await api.post(`/wa/contacts/${contact.id}/reply`, useTemplate ? { template_code: tmpl } : { body: body.trim() });
      toast.success("Balasan tercatat & dikirim lewat gateway WhatsApp.");
      onDone?.(); onOpenChange(false);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim balasan."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={!!contact} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid={P97.replyDialog}>
        <DialogHeader>
          <DialogTitle>Balas {contact?.name || contact?.phone}</DialogTitle>
          <DialogDescription>{contact?.phone} · balasan tercatat di percakapan Inbox yang sama.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div data-testid={P97.replyHistory} className="max-h-56 space-y-1.5 overflow-y-auto rounded-lg border bg-secondary/40 p-2">
            {!data ? <p className="text-xs text-muted-foreground">Memuat…</p> : null}
            {data && !data.messages.length ? <p className="text-xs italic text-muted-foreground">Belum ada pesan.</p> : null}
            {(data?.messages || []).map((m) => (
              <div key={m.id} className={cn("max-w-[85%] rounded-lg px-2.5 py-1.5 text-sm", m.direction === "out"
                ? "ml-auto bg-primary/10" : "bg-card border")}>
                <p className="whitespace-pre-line">{m.body}</p>
                <p className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                  {fromNow(m.created_at)}{m.direction === "out" ? <StatusPill status={m.status} group="wa_send_status" /> : null}
                </p>
              </div>
            ))}
          </div>
          <p data-testid={P97.replyWindow} className={cn("flex items-center gap-1.5 text-xs", windowOpen ? "text-emerald-700" : "text-amber-700")}>
            <Clock className="h-3.5 w-3.5" />
            {data ? (windowOpen ? "Sesi 24 jam terbuka — teks bebas boleh." : "Sesi 24 jam tertutup — gunakan template pra-approved.") : "…"}
            {data?.opt_out ? <span className="text-rose-600">· nomor opt-out (promosi ditolak)</span> : null}
          </p>
          {data ? <WaReplySuggestions contactId={contact?.id} onPick={pickSuggestion} /> : null}
          <Select value={tmpl} onValueChange={setTmpl}>
            <SelectTrigger data-testid={P97.replyTemplate} aria-label="Template WA"><SelectValue placeholder="Tanpa template" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Tanpa template (teks bebas)</SelectItem>
              {templates.map((t) => <SelectItem key={t.id} value={t.code}>{t.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {!useTemplate ? (
            <Textarea data-testid={P97.replyBody} rows={3} value={body} onChange={(e) => setBody(e.target.value)}
              disabled={!windowOpen} aria-label="Isi balasan"
              placeholder={windowOpen ? "Tulis balasan…" : "Sesi tertutup: pilih template di atas"} />
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Tutup</Button>
          <Button data-testid={P97.replySubmit} onClick={send} disabled={busy || !canSend}>
            <Send className="mr-1.5 h-4 w-4" /> {busy ? "Mengirim…" : "Kirim balasan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
