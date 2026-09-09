import React, { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, KeyRound, Radar, Smartphone, Webhook, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import StatusPill from "@/components/patterns/StatusPill";
import { formatDateTimeWIB } from "@/utils/formatters";
import api from "@/services/apiClient";
import { P100 } from "@/constants/testIds";

const Ok = ({ ok }) => (ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="h-4 w-4 shrink-0 text-rose-600" />);
const detailOf = (e, fb) => e?.response?.data?.detail || fb;

/**
 * WaSetupPanel — Penyiapan akun Cloud API tanpa terminal (Fase 100): diagnosa token/nomor/WABA,
 * daftarkan nomor (PIN), verifikasi ulang nomor (kode SMS/telepon), langganan webhook app→WABA.
 * Semua hasil apa adanya dari Meta — tidak ada sukses palsu.
 */
export default function WaSetupPanel({ data, onChanged }) {
  const [busy, setBusy] = useState("");
  const [pin, setPin] = useState("");
  const [regRes, setRegRes] = useState(null);
  const [reverify, setReverify] = useState(false);
  const [method, setMethod] = useState("SMS");
  const [code, setCode] = useState("");
  const diag = data?.diagnose || {};
  const phone = diag.phone || {};
  const token = diag.token || {};
  const hasCreds = !!data?.live_ready;

  const run = async (key, fn, okMsg) => {
    setBusy(key);
    try {
      const res = await fn();
      const d = res.data.data;
      if (d.ok) toast.success(okMsg); else toast.error(d.error_detail || d.detail || (d.problems || []).join("; ") || "Belum berhasil.");
      return d;
    } catch (e) { toast.error(detailOf(e, "Permintaan gagal.")); return null; }
    finally { setBusy(""); onChanged && onChanged(); }
  };

  const diagnose = () => run("diag", () => api.post("/wa/setup/diagnose"), "Diagnosa selesai.");
  const register = async () => {
    if (!/^\d{6}$/.test(pin)) { toast.error("PIN harus 6 digit angka."); return; }
    const d = await run("reg", () => api.post("/wa/setup/register", { pin }), "Nomor terdaftar ke Cloud API.");
    if (d) { setRegRes(d); if (d.needs_verification) setReverify(true); if (d.ok) diagnose(); }
  };
  const requestCode = () => run("req", () => api.post("/wa/setup/request-code", { method }), `Kode dikirim via ${method}.`);
  const verifyCode = () => run("ver", () => api.post("/wa/setup/verify-code", { code }), "Nomor terverifikasi — sekarang daftarkan dengan PIN.");
  const subscribe = () => run("sub", () => api.post("/wa/setup/subscribe"), "App berlangganan webhook WABA.");

  return (
    <div data-testid={P100.setupPanel} className="space-y-4 rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-center gap-2">
        <Radar className="h-4 w-4 text-primary" />
        <h3 className="section-title">Penyiapan akun Cloud API</h3>
        {diag.at ? <span className="text-[11px] text-muted-foreground">diagnosa terakhir {formatDateTimeWIB(diag.at)}</span> : null}
        <Button data-testid={P100.diagnoseBtn} size="sm" variant="outline" className="ml-auto" onClick={diagnose} disabled={busy === "diag" || !hasCreds}>
          <Radar className="mr-1.5 h-4 w-4" /> {busy === "diag" ? "Memeriksa…" : "Diagnosa"}
        </Button>
      </div>
      {!hasCreds ? <p className="text-xs text-amber-700">Simpan token + Phone ID dulu, lalu jalankan Diagnosa.</p> : null}
      {diag.problems?.length ? (
        <ul data-testid={P100.problems} className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          {diag.problems.map((p) => <li key={p} className="flex gap-1.5"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{p}</li>)}
        </ul>
      ) : diag.at ? <p className="text-xs text-emerald-700">Tidak ada masalah terdeteksi pada token, nomor, dan langganan webhook.</p> : null}

      {diag.at ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div data-testid={P100.tokenInfo} className="space-y-1 rounded-lg border p-3 text-xs">
            <p className="flex items-center gap-1.5 font-medium"><KeyRound className="h-3.5 w-3.5" /> Token <Ok ok={token.ok && !token.missing_scopes?.length} /></p>
            <p>Tipe: <b>{token.type || "-"}</b> · {token.permanent ? "permanen (tidak kedaluwarsa)" : token.expires_at ? `kedaluwarsa ${formatDateTimeWIB(new Date(token.expires_at * 1000).toISOString())}` : "-"}</p>
            <p className="text-muted-foreground">Izin: {(token.scopes || []).join(", ") || "-"}</p>
            {token.missing_scopes?.length ? <p className="text-rose-600">Kurang izin: {token.missing_scopes.join(", ")}</p> : null}
            {token.error ? <p className="text-rose-600">{token.error}</p> : null}
          </div>
          <div data-testid={P100.phoneStatus} className="space-y-1 rounded-lg border p-3 text-xs">
            <p className="flex items-center gap-1.5 font-medium"><Smartphone className="h-3.5 w-3.5" /> Nomor <Ok ok={!!phone.registered} />
              <StatusPill status={phone.registered ? "live" : "pending"} label={phone.status || "?"} /></p>
            <p>{phone.display_phone_number || "-"} · {phone.verified_name || "-"}</p>
            <p className="text-muted-foreground">Platform: {phone.platform_type || "-"} · kualitas {phone.quality_rating || "-"} · tier {phone.messaging_limit_tier || "-"}</p>
            {phone.hint ? <p data-testid={P100.phoneHint} className={phone.registered ? "text-emerald-700" : "text-amber-800"}>{phone.hint}</p> : null}
          </div>
        </div>
      ) : null}

      {hasCreds && diag.at && !phone.registered ? (
        <div className="space-y-2 rounded-lg border border-dashed p-3">
          <Label htmlFor="wa-setup-pin">Daftarkan nomor ke Cloud API — PIN verifikasi dua langkah (6 digit)</Label>
          <div className="flex flex-wrap gap-2">
            <Input id="wa-setup-pin" data-testid={P100.registerPin} className="w-40" inputMode="numeric" maxLength={6}
              placeholder="mis. 482913" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} autoComplete="off" />
            <Button data-testid={P100.registerBtn} onClick={register} disabled={busy === "reg"}>{busy === "reg" ? "Mendaftarkan…" : "Daftarkan nomor"}</Button>
            <Button data-testid={P100.reverifyToggle} variant="ghost" size="sm" onClick={() => setReverify((v) => !v)}>Nomor perlu verifikasi ulang?</Button>
          </div>
          <p className="text-[11px] text-muted-foreground">PIN ini menjadi PIN dua langkah nomor Anda — simpan baik-baik. Nomor harus sudah tidak aktif di aplikasi WhatsApp HP.</p>
          {regRes ? (
            <p data-testid={P100.registerResult} className={`text-xs ${regRes.ok ? "text-emerald-700" : "text-rose-600"}`}>
              {regRes.ok ? "Berhasil didaftarkan." : `Meta menolak (${regRes.error_code}): ${regRes.error_detail}`}
              {regRes.hint ? <span className="block text-amber-800">{regRes.hint}</span> : null}
            </p>
          ) : null}
          {reverify ? (
            <div className="flex flex-wrap items-end gap-2 border-t pt-2">
              <div className="space-y-1">
                <Label>Kirim kode via</Label>
                <Select value={method} onValueChange={setMethod}>
                  <SelectTrigger data-testid={P100.codeMethod} className="w-32"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="SMS">SMS</SelectItem><SelectItem value="VOICE">Telepon</SelectItem></SelectContent>
                </Select>
              </div>
              <Button data-testid={P100.requestCodeBtn} variant="outline" onClick={requestCode} disabled={busy === "req"}>Minta kode</Button>
              <div className="space-y-1">
                <Label htmlFor="wa-setup-code">Kode yang diterima</Label>
                <Input id="wa-setup-code" data-testid={P100.verifyCodeInput} className="w-36" inputMode="numeric" placeholder="6 digit"
                  value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} autoComplete="off" />
              </div>
              <Button data-testid={P100.verifyCodeBtn} variant="secondary" onClick={verifyCode} disabled={busy === "ver" || !code}>Verifikasi kode</Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {diag.at ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-xs">
          <Webhook className="h-3.5 w-3.5" />
          <span data-testid={P100.subscribedStatus} className="flex items-center gap-1.5 font-medium">
            Langganan webhook WABA <Ok ok={diag.subscribed === true} />
            <span className="text-muted-foreground">{diag.subscribed ? (diag.subscribed_apps || []).join(", ") : diag.subscribed === null ? "WABA ID kosong" : "belum ada app"}</span>
          </span>
          {!diag.subscribed ? (
            <Button data-testid={P100.subscribeBtn} size="sm" className="ml-auto" onClick={subscribe} disabled={busy === "sub" || !diag.waba?.id}>
              {busy === "sub" ? "Memproses…" : "Langganankan app"}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
