import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Building2, KeyRound, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import portalApi from "@/services/portalClient";
import { usePortalAuth, PORTAL_END_MESSAGE } from "@/context/PortalAuthContext";
import { PORTAL } from "@/constants/testIds";

export default function PortalLogin() {
  const nav = useNavigate();
  const { login, endReason } = usePortalAuth();
  const [step, setStep] = useState(1);
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState("");
  const [masked, setMasked] = useState("");
  const [busy, setBusy] = useState(false);

  const requestOtp = async () => {
    if (!identifier) { toast.error("Masukkan nomor HP atau email terdaftar."); return; }
    setBusy(true);
    try {
      const res = await portalApi.post("/portal/auth/request-otp", { identifier });
      setMasked(res.data.masked || "");
      setDevCode(res.data.dev_code || "");
      setStep(2);
      toast.success(res.data.message || "OTP dikirim.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengirim OTP.");
    } finally { setBusy(false); }
  };

  const verifyOtp = async () => {
    if (!code) { toast.error("Masukkan kode OTP."); return; }
    setBusy(true);
    try {
      const res = await portalApi.post("/portal/auth/verify-otp", { identifier, code });
      login(res.data.token, res.data.profile);
      toast.success("Berhasil masuk. Selamat datang!");
      nav("/portal", { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Verifikasi OTP gagal.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid={PORTAL.loginPage} className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-emerald-50 p-4">
      <div className="w-full max-w-md rounded-2xl border bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-600 text-white"><Building2 className="h-6 w-6" /></div>
          <div>
            <p className="font-heading text-lg font-semibold">Portal Pembeli SIPRO</p>
            <p className="text-xs text-slate-500">Transparansi progres, pembayaran & dokumen</p>
          </div>
        </div>

        {/* Fase 54 — pembeli yang sesinya berakhir dulu hanya melihat panel-panel gagal
            memuat, lalu tiba-tiba berada di halaman ini tanpa sebab; banyak yang mengira
            portalnya rusak. Sekarang halaman ini menjelaskan dirinya sendiri, dengan
            kalimat untuk PEMBELI (kode OTP), bukan istilah internal. */}
        {endReason ? (
          <div data-testid="portal-session-notice"
            className="mb-5 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{PORTAL_END_MESSAGE[endReason] || PORTAL_END_MESSAGE.expired}</span>
          </div>
        ) : null}
        {step === 1 ? (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="ident">Nomor HP / Email</Label>
              <Input id="ident" data-testid={PORTAL.identifierInput} value={identifier}
                onChange={(e) => setIdentifier(e.target.value)} placeholder="08xx atau email@anda.com"
                onKeyDown={(e) => e.key === "Enter" && requestOtp()} />
            </div>
            <Button data-testid={PORTAL.requestOtpBtn} className="w-full" onClick={requestOtp} disabled={busy}>
              <KeyRound className="mr-2 h-4 w-4" /> {busy ? "Mengirim…" : "Kirim Kode OTP"}
            </Button>
            <p className="text-center text-xs text-slate-400">Gunakan kontak yang terdaftar saat pembelian unit.</p>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">Kode OTP dikirim ke <b>{masked}</b>.</p>
            {devCode ? (
              <div data-testid={PORTAL.devCode} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                Mode simulasi — kode OTP: <b className="tabular-nums tracking-widest">{devCode}</b>
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="otp">Kode OTP</Label>
              <Input id="otp" data-testid={PORTAL.otpInput} value={code}
                onChange={(e) => setCode(e.target.value)} placeholder="6 digit" inputMode="numeric"
                onKeyDown={(e) => e.key === "Enter" && verifyOtp()} />
            </div>
            <Button data-testid={PORTAL.verifyOtpBtn} className="w-full" onClick={verifyOtp} disabled={busy}>
              <ShieldCheck className="mr-2 h-4 w-4" /> {busy ? "Memverifikasi…" : "Masuk"}
            </Button>
            <button className="w-full text-center text-xs text-slate-400 hover:text-slate-600"
              onClick={() => setStep(1)}>Ganti nomor / email</button>
          </div>
        )}
      </div>
    </div>
  );
}
