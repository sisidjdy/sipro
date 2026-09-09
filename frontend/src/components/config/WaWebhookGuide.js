import React, { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Copy, Eye, EyeOff, Link2, Webhook, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P100 } from "@/constants/testIds";
import LegalUrlsCard from "@/components/legal/LegalUrlsCard";

const PUBLIC_BASE = process.env.REACT_APP_BACKEND_URL;

const copy = async (text, label) => {
  try { await navigator.clipboard.writeText(text); toast.success(`${label} disalin.`); }
  catch { toast.error("Clipboard tidak tersedia — salin manual."); }
};

/**
 * WaWebhookGuide — panduan webhook siap-salin (Fase 100): Callback URL mengikuti domain aplikasi
 * (bukan hardcode), verify token bisa ditampilkan/disalin, field yang wajib dicentang, dan tombol
 * "Uji handshake" yang memanggil URL PUBLIK dari server — membuktikan domain/reverse proxy VPS benar.
 */
export default function WaWebhookGuide({ data }) {
  const [guide, setGuide] = useState(null);
  const [showToken, setShowToken] = useState(false);
  const [hs, setHs] = useState(null);
  const [busy, setBusy] = useState("");
  const url = `${PUBLIC_BASE}${data?.webhook?.path || "/api/webhooks/wa"}`;
  const wh = data?.webhook || {};

  const loadGuide = async () => {
    if (guide) { setShowToken((v) => !v); return; }
    setBusy("guide");
    try {
      const res = await api.get("/wa/setup/webhook-guide", { params: { public_base: PUBLIC_BASE } });
      setGuide(res.data.data); setShowToken(true);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memuat panduan."); }
    finally { setBusy(""); }
  };

  const handshake = async () => {
    setBusy("hs");
    try {
      const res = await api.post("/wa/setup/handshake", { public_base: PUBLIC_BASE });
      setHs(res.data.data);
      if (res.data.data.ok) toast.success("Handshake webhook berhasil."); else toast.error(res.data.data.detail);
    } catch (e) { toast.error(e?.response?.data?.detail || "Uji handshake gagal."); }
    finally { setBusy(""); }
  };

  return (
    <div data-testid={P100.webhookGuide} className="space-y-3 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-2"><Webhook className="h-4 w-4 text-primary" /><h3 className="section-title">Webhook — tempel di dashboard Meta</h3></div>
      {!PUBLIC_BASE?.startsWith("https://") ? <p className="text-xs text-rose-600">Meta hanya menerima Callback URL HTTPS — pasang sertifikat di domain Anda.</p> : null}
      <div className="space-y-1 text-xs">
        <p className="text-muted-foreground">Callback URL (mengikuti domain aplikasi ini)</p>
        <div className="flex items-center gap-1.5">
          <code data-testid={P100.webhookUrl} className="flex-1 break-all rounded bg-secondary/60 px-2 py-1">{url}</code>
          <Button data-testid={P100.copyUrlBtn} size="icon" variant="ghost" aria-label="Salin URL" onClick={() => copy(url, "Callback URL")}><Copy className="h-4 w-4" /></Button>
        </div>
      </div>
      <div className="space-y-1 text-xs">
        <p className="text-muted-foreground">Verify token</p>
        <div className="flex items-center gap-1.5">
          <code data-testid={P100.verifyTokenValue} className="flex-1 break-all rounded bg-secondary/60 px-2 py-1">
            {showToken && guide ? (guide.verify_token || "(belum diisi)") : "••••••••••••"}
          </code>
          <Button data-testid={P100.revealTokenBtn} size="icon" variant="ghost" aria-label="Tampilkan verify token" onClick={loadGuide} disabled={busy === "guide"}>
            {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </Button>
          <Button data-testid={P100.copyTokenBtn} size="icon" variant="ghost" aria-label="Salin verify token" disabled={!guide?.verify_token}
            onClick={() => copy(guide.verify_token, "Verify token")}><Copy className="h-4 w-4" /></Button>
        </div>
      </div>
      <div className="text-xs">
        <p className="text-muted-foreground">Field yang wajib di-subscribe di Meta</p>
        <p className="flex flex-wrap gap-1 pt-1">
          {["messages", "message_template_status_update", "phone_number_quality_update", "account_update"].map((f) => (
            <code key={f} className="rounded bg-secondary/60 px-1.5 py-0.5">{f}</code>
          ))}
        </p>
      </div>
      <ol className="list-decimal space-y-0.5 pl-4 text-[11px] text-muted-foreground">
        <li>developers.facebook.com › App Anda › WhatsApp › Configuration › Webhook › Edit.</li>
        <li>Tempel Callback URL + Verify token, klik <b>Verify and save</b> — SIPRO membalas hub.challenge.</li>
        <li>Klik <b>Manage</b>, centang field di atas.</li>
        <li>Klik <b>Langganankan app</b> di panel Penyiapan.</li>
        <li>Kirim WA dari HP lain ke nomor bisnis — "Terakhir diterima" di bawah harus terisi.</li>
      </ol>
      <div className="flex flex-wrap items-center gap-2 border-t pt-2">
        <Button data-testid={P100.handshakeBtn} size="sm" variant="outline" onClick={handshake} disabled={busy === "hs"}>
          <Link2 className="mr-1.5 h-4 w-4" /> {busy === "hs" ? "Menguji…" : "Uji handshake URL publik"}
        </Button>
        {hs ? (
          <span data-testid={P100.handshakeResult} className={`flex items-center gap-1 text-xs ${hs.ok ? "text-emerald-700" : "text-rose-600"}`}>
            {hs.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />} {hs.detail}
          </span>
        ) : null}
      </div>
      <div className="border-t pt-2"><LegalUrlsCard compact /></div>
      <dl className="grid grid-cols-2 gap-1 border-t pt-2 text-xs">
        <dt className="text-muted-foreground">Terakhir diterima</dt><dd>{wh.last_received_at ? formatDateTimeWIB(wh.last_received_at) : "belum pernah"}</dd>
        <dt className="text-muted-foreground">Tanda tangan</dt>
        <dd>{wh.last_signature_ok === true ? "sah" : wh.last_signature_ok === false ? "TIDAK sah" : "tidak diverifikasi (tanpa app secret)"}</dd>
        <dt className="text-muted-foreground">Jenis terakhir</dt><dd>{wh.last_kind || "-"}</dd>
      </dl>
    </div>
  );
}
