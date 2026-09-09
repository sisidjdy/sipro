import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertCircle, CheckCircle2, Circle, Download, FileText, Lock, Sparkles, ArrowUpRight, MessageCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import StatusPill from "@/components/patterns/StatusPill";
import { LoadingCards, ErrorState } from "@/components/patterns/StateViews";
import { formatIDR, formatDateWIB } from "@/utils/formatters";
import { cn } from "@/lib/utils";
import api from "@/services/apiClient";
import { P91, P97 } from "@/constants/testIds";

const STATE = {
  done: { icon: CheckCircle2, cls: "text-emerald-600 border-emerald-300 bg-emerald-50", label: "Selesai" },
  active: { icon: Circle, cls: "text-primary border-primary/40 bg-primary/5", label: "Berjalan" },
  locked: { icon: Lock, cls: "text-muted-foreground border-border bg-muted/40", label: "Belum terbuka" },
  blocked: { icon: AlertCircle, cls: "text-rose-600 border-rose-300 bg-rose-50", label: "Terhenti" },
};

async function openPdf(url, filename) {
  const res = await api.get(url, { responseType: "blob" });
  const href = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  window.open(href, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(href), 60000);
}

function DocItem({ doc, idx, wa, entity, onSent }) {
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const pdf = async () => {
    setBusy(true);
    try { await openPdf(doc.pdf_url, doc.number || doc.label); }
    catch (e) { toast.error(e?.response?.data?.detail || "PDF belum tersedia untuk dokumen ini."); }
    finally { setBusy(false); }
  };
  const sendWa = async () => {
    setSending(true);
    try {
      const r = await api.post("/doc-history/send-wa", { entity_type: entity.type, entity_id: entity.id,
        pdf_url: doc.pdf_url, label: doc.label, number: doc.number || null });
      const m = r.data.data.message;
      toast.success(m.status === "simulated" ? `Dokumen tercatat terkirim (SIMULASI) ke ${m.to}.` : `Dokumen terkirim ke ${m.to}.`);
      onSent?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim dokumen via WhatsApp."); }
    finally { setSending(false); }
  };
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-2 shadow-[var(--shadow-card)]" data-testid={`${P91.docsItem}-${doc.kind}-${idx}`}>
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{doc.label}{doc.number ? <span className="ml-1.5 font-mono text-xs text-muted-foreground">{doc.number}</span> : null}</p>
        <p className="truncate text-xs text-muted-foreground">
          {doc.issued_at ? formatDateWIB(doc.issued_at) : "—"} · {doc.actor}{doc.note ? ` · ${doc.note}` : ""}
        </p>
      </div>
      {doc.amount ? <span className="text-sm font-semibold tabular-nums">{formatIDR(doc.amount)}</span> : null}
      {doc.status ? <StatusPill status={doc.status} /> : null}
      {doc.pdf_url ? (
        <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={pdf} data-testid={`${P91.docsPdf}-${doc.kind}-${idx}`}>
          <Download className="h-3.5 w-3.5" /> PDF
        </Button>
      ) : null}
      {doc.pdf_url && wa ? (
        <Button size="sm" variant={wa.enabled ? "secondary" : "outline"} className={cn("h-7", !wa.enabled && "border-dashed")}
          disabled={!wa.enabled || sending} onClick={sendWa} title={wa.enabled ? `Kirim PDF ke ${wa.phone}` : wa.reason}
          data-testid={`${P97.docSendWaBtn}-${doc.kind}-${idx}`}>
          <MessageCircle className="h-3.5 w-3.5" /> {sending ? "Mengirim…" : "Kirim via WhatsApp"}
        </Button>
      ) : null}
    </li>
  );
}

function ActionButton({ action, onDone }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (action.method === "POST" && action.endpoint) {
      setBusy(true);
      try {
        const r = await api.post(action.endpoint, action.body || {});
        toast.success(r.data?.message || `${action.label.replace(/^Terbitkan /, "")} diterbitkan${r.data?.data?.doc_number ? ` · ${r.data.data.doc_number}` : ""}.`);
        onDone?.();
      } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menerbitkan dokumen."); }
      finally { setBusy(false); }
      return;
    }
    if (action.href) navigate(action.href);
  };
  const enabled = action.enabled && (action.method || action.href);
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid={`${P91.docsAction}-${action.key}`}>
      <Button size="sm" variant={action.enabled ? "default" : "outline"} disabled={!enabled || busy} onClick={run}
        className={cn(!action.enabled && "border-dashed disabled:opacity-100 disabled:text-muted-foreground")}>
        {action.enabled ? <Sparkles className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
        {busy ? "Memproses…" : action.label}
        {action.enabled && !action.method && action.href ? <ArrowUpRight className="h-3.5 w-3.5" /> : null}
      </Button>
      {action.reason ? (
        <span className="text-xs text-muted-foreground" data-testid={`${P91.docsReason}-${action.key}`}>{action.reason}</span>
      ) : null}
    </div>
  );
}

function Stage({ stage, last, onDone, wa, entity }) {
  const st = STATE[stage.state] || STATE.locked;
  const Icon = st.icon;
  return (
    <li className="relative pl-10" data-testid={`${P91.docsStage}-${stage.key}`}>
      {!last ? <span className="absolute left-[15px] top-8 h-[calc(100%-8px)] w-px bg-border" /> : null}
      <span className={cn("absolute left-0 top-0.5 flex h-8 w-8 items-center justify-center rounded-full border", st.cls)}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="space-y-2 pb-6">
        <div className="flex flex-wrap items-baseline gap-2">
          <h4 className="text-sm font-semibold">{stage.label}</h4>
          <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide", st.cls)}>{st.label}</span>
          <span className="text-xs text-muted-foreground">{stage.description}</span>
        </div>
        {stage.docs.length ? (
          <ul className="space-y-1.5">{stage.docs.map((d, i) => <DocItem key={`${d.kind}-${i}`} doc={d} idx={i} wa={wa} entity={entity} onSent={onDone} />)}</ul>
        ) : <p className="text-xs italic text-muted-foreground">Belum ada dokumen terbit pada tahap ini.</p>}
        {stage.actions.length ? (
          <div className="space-y-1.5">{stage.actions.map((a) => <ActionButton key={a.key} action={a} onDone={onDone} />)}</div>
        ) : null}
      </div>
    </li>
  );
}

/** Riwayat dokumen terbit per tahapan transaksi + aksi cepat penerbitan (Fase 91). */
export default function IssuedDocsTab({ entityType, entityId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api.get(`/doc-history/${entityType}/${entityId}`).then((r) => setData(r.data.data))
      .catch((e) => setError(e?.response?.data?.detail || "Gagal memuat riwayat dokumen."));
  }, [entityType, entityId]);
  useEffect(() => { load(); }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <LoadingCards count={3} />;
  return (
    <div className="space-y-4" data-testid={P91.docsTab}>
      <p className="rounded-lg border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
        Semua dokumen yang diterbitkan sistem sepanjang perjalanan transaksi — Booking → SPR → Tagihan & Kwitansi →
        Pajak & Biaya → Legal → BAST. Total <b className="text-foreground">{data.total_docs}</b> dokumen.
        Tombol bergaris putus berarti belum bisa diterbitkan; alasannya tertulis di sampingnya.
      </p>
      {data.wa_send ? (
        <p data-testid={P97.docSendWaReason} className={cn("rounded-lg border px-3 py-2 text-xs", data.wa_send.enabled
          ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800")}>
          <MessageCircle className="mr-1 inline h-3.5 w-3.5" />
          {data.wa_send.enabled
            ? <>Kirim via WhatsApp aktif ke <b>{data.wa_send.phone}</b> ({data.wa_send.mode === "live" ? "LIVE" : "mode simulasi — tercatat, tidak benar-benar terkirim"}).
              {data.wa_send.route ? <span data-testid={P97.docSendWaRoute} data-via={data.wa_send.route.via} className="block mt-0.5">{data.wa_send.route.note}</span> : null}</>
            : <>Kirim via WhatsApp nonaktif: {data.wa_send.reason}</>}
        </p>
      ) : null}
      {!data.deals.length ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground" data-testid={P91.docsEmpty}>
          Belum ada transaksi (reservasi unit) — dokumen mulai terbit setelah unit dipesan.
        </p>
      ) : data.deals.map((deal) => (
        <section key={deal.deal_id} className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]" data-testid={`${P91.docsDeal}-${deal.deal_id}`}>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-sm font-semibold">Unit {deal.unit_code}</h3>
            <StatusPill status={deal.deal_status} group="deal_status" />
            {deal.contract_number ? <span className="font-mono text-xs text-muted-foreground">{deal.contract_number}</span> : null}
            <span className="ml-auto text-xs text-muted-foreground">{deal.total_docs} dokumen</span>
          </div>
          <ol>{deal.stages.map((s, i) => <Stage key={s.key} stage={s} last={i === deal.stages.length - 1} onDone={load}
            wa={data.wa_send} entity={{ type: entityType, id: entityId }} />)}</ol>
        </section>
      ))}
      {data.wa_shares?.length ? (
        <section className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]" data-testid={P97.docWaShares}>
          <h3 className="mb-2 font-heading text-sm font-semibold">Riwayat kirim dokumen via WhatsApp</h3>
          <ul className="space-y-1">
            {data.wa_shares.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 text-xs">
                <MessageCircle className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-medium">{s.label}{s.number ? ` ${s.number}` : ""}</span>
                <span className="text-muted-foreground">→ {s.to} · {formatDateWIB(s.created_at)} · {s.created_by}</span>
                <StatusPill status={s.status} group="wa_send_status" />
                {s.error_detail ? <span className="text-rose-600">{s.error_code}: {s.error_detail}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
