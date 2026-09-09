import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Send, MessageSquare, Clock, ShieldCheck, ArrowDownLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatDateTimeWIB } from "@/utils/formatters";
import { PanelStateView } from "@/components/patterns/StateViews";
import api from "@/services/apiClient";
import { classifyRequestError } from "@/utils/panelLoad";
import { LEADS } from "@/constants/testIds";
import { cn } from "@/lib/utils";

/**
 * LeadWaPanel — WhatsApp DI DALAM record lead.
 *
 * Sebelumnya percakapan hanya ada di halaman /inbox dan tidak mempengaruhi lifecycle:
 * mengirim pesan tidak mencatat kontak pertama, tidak menghitung waktu respons, dan tidak
 * muncul di timeline lead. Sekarang pengiriman dari sini SEKALIGUS mencatat kontak pertama
 * (menaikkan tahap acquisition → nurturing) dan menutup tugas "hubungi lead".
 *
 * Mode pengiriman masih SIMULASI (kredensial Meta belum dikonfigurasi) dan ditandai jujur.
 */
export default function LeadWaPanel({ leadId, onChanged }) {
  const [data, setData] = useState(null);
  const [panel, setPanel] = useState(null);
  const [body, setBody] = useState("");
  const [tmpl, setTmpl] = useState("");
  const [busy, setBusy] = useState(false);
  const [inbound, setInbound] = useState("");
  const endRef = useRef(null);

  const load = useCallback(async () => {
    if (!leadId) return;
    setPanel(null);
    try {
      const res = await api.get(`/leads/${leadId}/wa`);
      setData(res.data.data);
    } catch (e) {
      // Fase 52 — dulu kegagalan di sini hanya memunculkan TOAST (yang hilang sendiri)
      // sementara panelnya tetap digambar sebagai percakapan KOSONG: "Belum ada percakapan.
      // Kirim sapaan pertama…". Untuk 403 itu menyesatkan (pesannya mungkin ADA, hanya
      // tidak boleh dibaca peran ini) dan untuk galat jaringan itu menyembunyikan masalah.
      setPanel(classifyRequestError(e));
    }
  }, [leadId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [data]);

  const send = async () => {
    if (!tmpl && !body.trim()) { toast.error("Tulis pesan atau pilih template."); return; }
    setBusy(true);
    try {
      const res = await api.post(`/leads/${leadId}/wa`,
        tmpl ? { template_code: tmpl, body: "" } : { body: body.trim() });
      toast.success(res.data.message_text || "Pesan terkirim (simulasi).");
      setBody(""); setTmpl("");
      await load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengirim pesan.");
    } finally { setBusy(false); }
  };

  const simulateInbound = async () => {
    if (!inbound.trim()) { toast.error("Tulis isi balasan pelanggan."); return; }
    setBusy(true);
    try {
      await api.post(`/leads/${leadId}/wa/inbound-demo`, { body: inbound.trim(), direction: "in" });
      toast.success("Balasan pelanggan disimulasikan — sesi 24 jam terbuka.");
      setInbound("");
      await load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal menyimulasikan balasan.");
    } finally { setBusy(false); }
  };

  const msgs = data?.messages || [];
  const windowOpen = !!data?.window_open;

  if (panel) {
    return (
      <div data-testid={LEADS.waPanel} className="space-y-2">
        <PanelStateView panel={panel} subject="Percakapan WhatsApp lead ini" onRetry={load}
          whoMay={"Percakapan WA lead dibuka untuk pemilik lead, Manajer Sales, Marketing "
            + "Admin, dan tim Digital Marketing."} />
      </div>
    );
  }

  return (
    <div data-testid={LEADS.waPanel} className="space-y-2 rounded-xl border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold">
          <MessageSquare className="h-4 w-4 text-emerald-600" /> WhatsApp
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
            SIMULASI
          </span>
        </p>
        <span data-testid={LEADS.waWindow}
          className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
            windowOpen ? "bg-emerald-100 text-emerald-800" : "bg-secondary text-muted-foreground")}>
          {windowOpen ? <ShieldCheck className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
          {windowOpen ? "Sesi 24 jam aktif" : "Sesi tertutup — wajib template"}
        </span>
      </div>

      <div data-testid={LEADS.waThread}
        className="max-h-64 space-y-1.5 overflow-y-auto rounded-lg border bg-secondary/30 p-2">
        {msgs.length ? msgs.map((m) => (
          <div key={m.id} data-testid={LEADS.waMessage}
            className={cn("max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs",
              m.direction === "out" ? "ml-auto bg-emerald-600 text-white"
                : "bg-card border")}>
            <p className="whitespace-pre-wrap">{m.body}</p>
            <p className={cn("mt-0.5 text-[10px]",
              m.direction === "out" ? "text-emerald-50/80" : "text-muted-foreground")}>
              {formatDateTimeWIB(m.created_at)}{m.is_template ? " · template" : ""}
            </p>
          </div>
        )) : (
          <p className="px-1 py-4 text-center text-xs text-muted-foreground">
            Belum ada percakapan. Kirim sapaan pertama — pengiriman ini otomatis tercatat
            sebagai kontak pertama.
          </p>
        )}
        <div ref={endRef} />
      </div>

      <div className="space-y-2">
        <Select value={tmpl} onValueChange={setTmpl}>
          <SelectTrigger data-testid={LEADS.waTemplate}>
            <SelectValue placeholder={windowOpen ? "Template (opsional)" : "Pilih template pra-approved…"} />
          </SelectTrigger>
          <SelectContent>
            {(data?.templates || []).map((t) => (
              <SelectItem key={t.code} value={t.code}>{t.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {tmpl ? (
          <p className="rounded-md bg-secondary/60 px-2.5 py-1.5 text-[11px] text-muted-foreground">
            {(data?.templates || []).find((t) => t.code === tmpl)?.body}
          </p>
        ) : (
          <Textarea data-testid={LEADS.waInput} rows={2} value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={windowOpen ? "Tulis pesan…"
              : "Sesi tertutup — pilih template di atas untuk membuka percakapan"}
            disabled={!windowOpen} />
        )}
        <Button size="sm" className="w-full" data-testid={LEADS.waSend} onClick={send}
          disabled={busy || (!tmpl && !windowOpen)}>
          <Send className="mr-1.5 h-4 w-4" /> Kirim WhatsApp
        </Button>
      </div>

      <details className="rounded-lg border bg-card p-2">
        <summary className="cursor-pointer text-[11px] text-muted-foreground">
          Uji alur: simulasikan balasan pelanggan
        </summary>
        <div className="mt-2 space-y-2">
          <Textarea rows={2} value={inbound} onChange={(e) => setInbound(e.target.value)}
            placeholder="mis. Berapa harga tipe 45? Saya mau survey Sabtu" />
          <Button size="sm" variant="outline" data-testid={LEADS.waSimulateIn}
            onClick={simulateInbound} disabled={busy}>
            <ArrowDownLeft className="mr-1.5 h-3.5 w-3.5" /> Simulasikan balasan masuk
          </Button>
          <p className="text-[10px] text-muted-foreground">
            Membuka sesi 24 jam & memicu otomasi kata kunci (harga/KPR/survey) — dipakai untuk
            menguji alur selama kredensial WhatsApp resmi belum dipasang.
          </p>
        </div>
      </details>
    </div>
  );
}
