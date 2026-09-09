import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Circle, PlugZap, Send, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import PhoneInput from "@/components/patterns/PhoneInput";
import { ErrorState, LoadingCards } from "@/components/patterns/StateViews";
import WaSetupPanel from "@/components/config/WaSetupPanel";
import WaWebhookGuide from "@/components/config/WaWebhookGuide";
import WaChecklist from "@/components/config/WaChecklist";
import api from "@/services/apiClient";
import { P94 } from "@/constants/testIds";
import ReferenceItems from "@/components/patterns/ReferenceItems";

const FIELDS = [
  { key: "token", label: "WHATSAPP_TOKEN", help: "System User permanent token (Business Settings › System Users)" },
  { key: "phone_id", label: "WHATSAPP_PHONE_ID", help: "WhatsApp › API Setup › Phone number ID (nomor PRODUKSI)" },
  { key: "waba_id", label: "WHATSAPP_WABA_ID", help: "WhatsApp Business Account ID — sinkron template" },
  { key: "app_secret", label: "WHATSAPP_APP_SECRET", help: "App › Settings › Basic — verifikasi tanda tangan webhook" },
  { key: "verify_token", label: "WHATSAPP_VERIFY_TOKEN", help: "String acak buatan Anda — handshake GET /api/webhooks/wa" },
];

/**
 * WaIntegrationPanel — Pusat Konfigurasi › Integrasi WhatsApp (Fase 97-lite).
 * Nilai kredensial tersimpan terenkripsi, ditampilkan tersamar; "Tes koneksi" benar-benar
 * memanggil Graph API bila kredensial ada; checklist go-live jujur.
 */
export default function WaIntegrationPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState({});
  const [mode, setMode] = useState("simulation");
  const [busy, setBusy] = useState("");
  const [probe, setProbe] = useState(null);
  const [testPhone, setTestPhone] = useState("");
  const [testRes, setTestRes] = useState(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await api.get("/wa/config");
      setData(res.data.data); setMode(res.data.data.mode);
      const lp = res.data.data.last_probe;
      setProbe(lp && Object.keys(lp).length ? lp : null);
    } catch (e) { setError(e?.response?.data?.detail || "Gagal memuat konfigurasi WhatsApp."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (extra = {}) => {
    setBusy("save");
    try {
      const res = await api.put("/wa/config", { mode, ...form, ...extra });
      setData(res.data.data); setForm({});
      toast.success("Konfigurasi WhatsApp tersimpan (terenkripsi).");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan."); setMode(data?.mode || "simulation"); }
    finally { setBusy(""); }
  };

  const test = async () => {
    setBusy("test");
    try {
      const res = await api.post("/wa/config/test");
      setProbe(res.data.data);
      if (res.data.data.ok) toast.success("Koneksi ke Meta berhasil."); else toast.warning(res.data.data.detail || "Tes tidak berhasil.");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Tes koneksi gagal."); }
    finally { setBusy(""); }
  };

  const testMsg = async () => {
    if (!testPhone) { toast.error("Isi nomor tujuan."); return; }
    setBusy("msg");
    try {
      const res = await api.post("/wa/config/test-message", { to: testPhone });
      setTestRes(res.data.data);
      const s = res.data.data.status;
      if (s === "sent") toast.success("Pesan uji terkirim (live).");
      else if (s === "simulated") toast.info("Pesan uji tercatat sebagai SIMULASI (belum live).");
      else toast.error(`Gagal: ${res.data.data.error_detail || res.data.data.error_code}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim pesan uji."); }
    finally { setBusy(""); }
  };

  if (loading && !data) return <LoadingCards count={3} />;
  if (error && !data) return <ErrorState message={error} onRetry={load} />;
  const creds = data.credentials || {};

  return (
    <div data-testid={P94.configPanel} className="grid gap-4 lg:grid-cols-5">
      <div className="space-y-4 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)] lg:col-span-3">
        <div className="flex flex-wrap items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <h3 className="section-title">Kredensial Meta WhatsApp Cloud API</h3>
          <StatusPill status={data.effective_mode === "live" ? "live" : "simulation"}
            label={data.effective_mode === "live" ? "LIVE" : "SIMULASI"} />
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span>Channel aktif</span>
            <Switch checked={!!data.is_active} onCheckedChange={(v) => save({ is_active: v })} aria-label="Channel aktif" />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Nilai tersimpan terenkripsi dan hanya ditampilkan tersamar. Kosongkan kolom = tidak mengubah nilai lama;
          ketik <code>__clear__</code> untuk menghapus. Panduan: <code>memory/WA_META_CREDENTIALS_GUIDE.md</code>.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <div key={f.key} className="space-y-1">
              <Label htmlFor={`wa-cred-${f.key}`} className="flex items-center gap-1.5">
                {f.label}
                {creds[f.key]?.set ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <Circle className="h-3.5 w-3.5 text-muted-foreground" />}
                {creds[f.key]?.source === "env" ? <span className="text-[10px] text-muted-foreground">(.env)</span> : null}
              </Label>
              <Input id={`wa-cred-${f.key}`} data-testid={`${P94.configField}-${f.key}`} type={f.key === "phone_id" || f.key === "waba_id" ? "text" : "password"}
                aria-label={f.label} value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                placeholder={creds[f.key]?.set ? creds[f.key].masked : "belum diisi"} autoComplete="off" />
              <p className="text-[11px] text-muted-foreground">{f.help}</p>
            </div>
          ))}
          <div className="space-y-1">
            <Label>Mode</Label>
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger data-testid={P94.configMode}><SelectValue /></SelectTrigger>
              <SelectContent>
                <ReferenceItems group="integration_mode" />
              </SelectContent>
            </Select>
            {!data.live_ready && mode === "live" ? <p className="text-[11px] text-amber-700">Live butuh minimal token + phone ID.</p> : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button data-testid={P94.configSave} onClick={() => save()} disabled={busy === "save"}>Simpan</Button>
          <Button data-testid={P94.configTest} variant="outline" onClick={test} disabled={busy === "test"}>
            <PlugZap className="mr-1.5 h-4 w-4" /> Tes koneksi
          </Button>
        </div>
        {probe ? (
          <div className="rounded-lg border bg-secondary/40 p-3 text-xs">
            <p className="font-medium">{probe.ok ? "Koneksi OK" : "Belum terhubung"} · mode {probe.mode}</p>
            {probe.phone ? <p>Nomor {probe.phone.display_phone_number} · {probe.phone.verified_name} · kualitas {probe.phone.quality_rating || "-"}</p> : null}
            {probe.templates_approved !== undefined ? <p>Template APPROVED: {probe.templates_approved}</p> : null}
            {probe.detail ? <p className="text-muted-foreground">{probe.detail}</p> : null}
            {probe.error_code ? <p className="text-rose-600">Error {probe.error_code}</p> : null}
          </div>
        ) : null}
        <div className="space-y-2 border-t pt-3">
          <Label htmlFor="wa-test-phone">Kirim pesan uji ke nomor</Label>
          <div className="flex flex-wrap gap-2">
            <div className="min-w-[220px] flex-1">
              <PhoneInput id="wa-test-phone" value={testPhone} onChange={setTestPhone} testId={P94.configTestMsgPhone} />
            </div>
            <Button data-testid={P94.configTestMsgBtn} variant="secondary" onClick={testMsg} disabled={busy === "msg"}>
              <Send className="mr-1.5 h-4 w-4" /> Kirim uji
            </Button>
          </div>
          {testRes ? (
            <p className="text-xs">Status: <StatusPill status={testRes.status} label={testRes.status} /> {testRes.error_detail ? <span className="text-rose-600">{testRes.error_detail}</span> : null}
              {testRes.provider_message_id ? <span className="text-muted-foreground"> · {testRes.provider_message_id}</span> : null}</p>
          ) : null}
        </div>
      </div>

      <div className="space-y-4 lg:col-span-2">
        <WaSetupPanel data={data} onChanged={load} />
        <div data-testid={P94.configWebhook}><WaWebhookGuide data={data} /></div>
        <div data-testid={P94.configChecklist}><WaChecklist data={data} /></div>
      </div>
    </div>
  );
}
